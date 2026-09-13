/** Bounded, image-only rectified-stereo landmark mapping/localization.
 * Inputs deliberately contain no simulator pose, depth, geometry or object IDs.
 * Coordinates: first accepted left camera; x right, y down, z forward, metres.
 * FAST segment test: https://www.edwardrosten.com/work/fast.html
 * Binary patch descriptors: https://www.epfl.ch/labs/cvlab/research/descriptors-and-keypoints/research-detect-brief/
 * Rigid alignment: https://web.stanford.edu/class/cs273/refs/Absolute-OPT.pdf
 * Custom implementation, not ORB-SLAM. No bundle adjustment, loop-closure
 * optimization, IMU, dense reconstruction, obstacle map or navigation guarantee.
 */
export type Vec3=[number,number,number];
type Mat3=[number,number,number,number,number,number,number,number,number];
export type StereoCalibration={width:number;height:number;fx:number;fy:number;cx:number;cy:number;baselineM:number};
export type StereoFrame={left:Uint8Array|Uint8ClampedArray;right:Uint8Array|Uint8ClampedArray;timestampMs:number};
export type StereoPose={position:Vec3;orientation:[number,number,number,number];timestampMs:number};
export type StereoLandmark={id:number;position:Vec3;observations:number};
export type StereoFeature={x:number;y:number;score:number;disparity:number|null;depthM:number|null;tracked:boolean;landmarkId:number|null};
export type StereoSlamState={status:'initializing'|'tracking'|'lost'|'relocalized';pose:StereoPose|null;lastGoodPose:StereoPose|null;
  // Confidence is a bounded support/reprojection heuristic, not a probability.
  map:StereoLandmark[];trajectory:StereoPose[];features:StereoFeature[];confidence:number;error:string|null;
  metrics:{detected:number;stereoMatches:number;mapMatches:number;inliers:number;reprojectionErrorPx:number|null;processingMs:number;keyframes:number;relocalizations:number}};
export type StereoSlamOptions={maxFeatures?:number;maxLandmarks?:number;minDisparity?:number;maxDepthM?:number;cornerThreshold?:number};
type Feature=StereoFeature&{descriptor:Uint32Array;point:Vec3|null};
type Landmark=StereoLandmark&{descriptors:Uint32Array[]};
type Pose={r:Mat3;t:Vec3};
type Correspondence={feature:Feature;landmark:Landmark;distance:number};
const I:Mat3=[1,0,0,0,1,0,0,0,1];
const add=(a:Vec3,b:Vec3):Vec3=>[a[0]+b[0],a[1]+b[1],a[2]+b[2]];
const sub=(a:Vec3,b:Vec3):Vec3=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]];
const scale=(a:Vec3,s:number):Vec3=>[a[0]*s,a[1]*s,a[2]*s];
const norm=(a:Vec3)=>Math.hypot(...a);
const cross=(a:Vec3,b:Vec3):Vec3=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const mv=(r:Mat3,v:Vec3):Vec3=>[r[0]*v[0]+r[1]*v[1]+r[2]*v[2],r[3]*v[0]+r[4]*v[1]+r[5]*v[2],r[6]*v[0]+r[7]*v[1]+r[8]*v[2]];
const transpose=(r:Mat3):Mat3=>[r[0],r[3],r[6],r[1],r[4],r[7],r[2],r[5],r[8]];
function mm(a:Mat3,b:Mat3):Mat3{return Array.from({length:9},(_,i)=>a[Math.floor(i/3)*3]*b[i%3]+a[Math.floor(i/3)*3+1]*b[i%3+3]+a[Math.floor(i/3)*3+2]*b[i%3+6]) as Mat3}
function quaternion(r:Mat3):[number,number,number,number]{
  const trace=r[0]+r[4]+r[8];let q:number[];
  if(trace>0){const s=2*Math.sqrt(trace+1);q=[(r[7]-r[5])/s,(r[2]-r[6])/s,(r[3]-r[1])/s,s/4]}
  else if(r[0]>r[4]&&r[0]>r[8]){const s=2*Math.sqrt(1+r[0]-r[4]-r[8]);q=[s/4,(r[1]+r[3])/s,(r[2]+r[6])/s,(r[7]-r[5])/s]}
  else if(r[4]>r[8]){const s=2*Math.sqrt(1+r[4]-r[0]-r[8]);q=[(r[1]+r[3])/s,s/4,(r[5]+r[7])/s,(r[2]-r[6])/s]}
  else{const s=2*Math.sqrt(1+r[8]-r[0]-r[4]);q=[(r[2]+r[6])/s,(r[5]+r[7])/s,s/4,(r[3]-r[1])/s]}
  const length=Math.hypot(...q);return q.map(v=>v/length) as [number,number,number,number];
}
function fromQuaternion(q:number[]):Mat3{const [w,x,y,z]=q;return [1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w),2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w),2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]}
function rotation(axis:number,angle:number):Mat3{const c=Math.cos(angle),s=Math.sin(angle);return axis===0?[1,0,0,0,c,-s,0,s,c]:axis===1?[c,0,s,0,1,0,-s,0,c]:[c,-s,0,s,c,0,0,0,1]}
function perturb(p:Pose,axis:number,amount:number):Pose{return axis<3?{r:p.r,t:p.t.map((v,i)=>v+(i===axis?amount:0)) as Vec3}:{r:mm(p.r,rotation(axis-3,amount)),t:p.t}}
function cameraPoint(p:Pose,world:Vec3):Vec3{return mv(transpose(p.r),sub(world,p.t))}
// A right observation exists only after current-image stereo matching passes
// uniqueness, depth and left/right consistency checks. Missing right pixels
// retain ordinary 2D-to-map tracking, without inventing a stereo measurement.
function observed(match:Correspondence):number[]{const f=match.feature;return f.disparity===null?[f.x,f.y]:[f.x,f.y,f.x-f.disparity]}
function projectMatch(p:Pose,match:Correspondence,c:StereoCalibration):number[]|null{
  const v=cameraPoint(p,match.landmark.position);if(v[2]<=.05)return null;
  const uv=[c.fx*v[0]/v[2]+c.cx,c.fy*v[1]/v[2]+c.cy];
  if(match.feature.disparity!==null)uv.push(c.fx*(v[0]-c.baselineM)/v[2]+c.cx);
  return uv;
}
function reprojectionSquared(p:Pose,match:Correspondence,c:StereoCalibration):number{
  const predicted=projectMatch(p,match,c);if(!predicted)return Infinity;
  const measurement=observed(match);return predicted.reduce((sum,value,i)=>sum+(measurement[i]-value)**2,0);
}
function publicPose(p:Pose,time:number):StereoPose{return {position:[...p.t],orientation:quaternion(p.r),timestampMs:time}}

function gray(rgba:Uint8Array|Uint8ClampedArray,w:number,h:number):Float32Array{
  const raw=new Float32Array(w*h),out=new Float32Array(w*h);
  for(let i=0;i<raw.length;i++)raw[i]=.299*rgba[i*4]+.587*rgba[i*4+1]+.114*rgba[i*4+2];
  out.set(raw);
  for(let y=1;y<h-1;y++)for(let x=1;x<w-1;x++){const i=y*w+x;out[i]=(raw[i]*4+2*(raw[i-1]+raw[i+1]+raw[i-w]+raw[i+w])+raw[i-w-1]+raw[i-w+1]+raw[i+w-1]+raw[i+w+1])/16}
  return out;
}
const circle=[[0,-3],[1,-3],[2,-2],[3,-1],[3,0],[3,1],[2,2],[1,3],[0,3],[-1,3],[-2,2],[-3,1],[-3,0],[-3,-1],[-2,-2],[-1,-3]];
let descriptorSeed=91317;
const random=()=>{descriptorSeed=(Math.imul(1664525,descriptorSeed)+1013904223)>>>0;return descriptorSeed/4294967296};
const pairs=Array.from({length:128},()=>Array.from({length:4},()=>Math.floor(random()*15)-7));
function descriptor(g:Float32Array,w:number,x:number,y:number){const bits=new Uint32Array(4);for(let i=0;i<128;i++){const [ax,ay,bx,by]=pairs[i];if(g[(y+ay)*w+x+ax]<g[(y+by)*w+x+bx])bits[i>>>5]|=1<<(i&31)}return bits}
function popcount(v:number){v-=v>>>1&0x55555555;v=(v&0x33333333)+(v>>>2&0x33333333);return (((v+(v>>>4))&0x0f0f0f0f)*0x01010101)>>>24}
function hamming(a:Uint32Array,b:Uint32Array){let sum=0;for(let i=0;i<4;i++)sum+=popcount(a[i]^b[i]);return sum}
function corners(g:Float32Array,w:number,h:number,limit:number,threshold:number):Feature[]{
  const candidates:{x:number;y:number;score:number}[]=[],scores=new Float32Array(w*h);
  for(let y=9;y<h-9;y++)for(let x=9;x<w-9;x++){
    const center=g[y*w+x];let light=0,dark=0,score=0;
    for(let i=0;i<16;i++){const d=g[(y+circle[i][1])*w+x+circle[i][0]]-center;if(d>threshold)light|=1<<i;if(d<-threshold)dark|=1<<i;score+=Math.abs(d)}
    let l=light|(light<<16),d=dark|(dark<<16),runL=l,runD=d;
    for(let j=1;j<9;j++){runL&=l>>>j;runD&=d>>>j}
    if((runL|runD)&65535){scores[y*w+x]=score;candidates.push({x,y,score})}
  }
  candidates.sort((a,b)=>b.score-a.score);
  const accepted:Feature[]=[],occupied=new Uint8Array(w*h);
  // Spatial suppression distributes features across the image instead of
  // allowing one high-contrast object to claim every landmark.
  const cells=new Uint8Array(8*6),perCell=Math.ceil(limit/32);
  for(const point of candidates){
    const {x,y,score}=point,cell=Math.min(5,Math.floor(y/h*6))*8+Math.min(7,Math.floor(x/w*8));
    if(occupied[y*w+x]||cells[cell]>=perCell)continue;
    let local=true;for(let yy=-1;yy<=1;yy++)for(let xx=-1;xx<=1;xx++)if(scores[(y+yy)*w+x+xx]>score)local=false;
    if(!local)continue;
    accepted.push({...point,descriptor:descriptor(g,w,x,y),point:null,disparity:null,depthM:null,tracked:false,landmarkId:null});cells[cell]++;
    for(let yy=-5;yy<=5;yy++)for(let xx=-5;xx<=5;xx++)occupied[(y+yy)*w+x+xx]=1;
    if(accepted.length>=limit)break;
  }
  return accepted;
}
function sample(g:Float32Array,w:number,x:number,y:number){const ix=Math.floor(x),iy=Math.floor(y),a=x-ix,b=y-iy;return (1-b)*((1-a)*g[iy*w+ix]+a*g[iy*w+ix+1])+b*((1-a)*g[(iy+1)*w+ix]+a*g[(iy+1)*w+ix+1])}
function patchCost(a:Float32Array,b:Float32Array,w:number,ax:number,bx:number,y:number):number{
  let sa=0,sb=0,aa=0,bb=0,ab=0;
  for(let dy=-3;dy<=3;dy++)for(let dx=-3;dx<=3;dx++){const u=sample(a,w,ax+dx,y+dy),v=sample(b,w,bx+dx,y+dy);sa+=u;sb+=v;aa+=u*u;bb+=v*v;ab+=u*v}
  const va=aa-sa*sa/49,vb=bb-sb*sb/49;
  return va>300&&vb>300?1-(ab-sa*sb/49)/Math.sqrt(va*vb):2;
}
function stereo(features:Feature[],left:Float32Array,right:Float32Array,c:StereoCalibration,minDisparity:number,maxDepth:number){
  for(const f of features){
    const max=Math.min(90,f.x-8),costs:number[]=[];let best=2,at=-1;
    for(let d=1;d<=max;d++){const cost=patchCost(left,right,c.width,f.x,f.x-d,f.y);costs[d]=cost;if(cost<best){best=cost;at=d}}
    if(at<2||at>=max||best>.23)continue;
    let second=2;for(let d=1;d<=max;d++)if(Math.abs(d-at)>2)second=Math.min(second,costs[d]);
    if(best>.8*second||second-best<.015)continue;
    const curvature=costs[at-1]-2*best+costs[at+1];
    const disparity=at+(curvature>1e-6?Math.max(-.5,Math.min(.5,.5*(costs[at-1]-costs[at+1])/curvature)):0);
    if(disparity<minDisparity)continue;
    const depth=c.fx*c.baselineM/disparity;if(depth>.05&&depth<=maxDepth){
      // Left-right consistency rejects occluded/ambiguous stereo patches.
      const rx=f.x-disparity;let reverseBest=2,reverseX=0;
      for(let x=Math.max(8,Math.ceil(rx+1));x<Math.min(c.width-8,rx+91);x++){
        const cost=patchCost(right,left,c.width,rx,x,f.y);if(cost<reverseBest){reverseBest=cost;reverseX=x}
      }
      if(Math.abs(reverseX-f.x)>1.5||reverseBest>.23)continue;
      f.disparity=disparity;f.depthM=depth;f.point=[(f.x-c.cx)*depth/c.fx,(f.y-c.cy)*depth/c.fy,depth];
    }
  }
}

/** Horn's unit-quaternion least-squares rigid transform: current -> map. */
function align(correspondences:Correspondence[]):Pose|null{
  if(correspondences.length<3)return null;
  let a:Vec3=[0,0,0],b:Vec3=[0,0,0];
  for(const c of correspondences){if(!c.feature.point)return null;a=add(a,c.feature.point);b=add(b,c.landmark.position)}
  a=scale(a,1/correspondences.length);b=scale(b,1/correspondences.length);
  if(norm(cross(sub(correspondences[1].feature.point!,correspondences[0].feature.point!),sub(correspondences[2].feature.point!,correspondences[0].feature.point!)))<1e-4)return null;
  const s=Array(9).fill(0);for(const c of correspondences){const x=sub(c.feature.point!,a),y=sub(c.landmark.position,b);for(let i=0;i<3;i++)for(let j=0;j<3;j++)s[i*3+j]+=x[i]*y[j]}
  const [xx,xy,xz,yx,yy,yz,zx,zy,zz]=s,tr=xx+yy+zz;
  const n=[[tr,yz-zy,zx-xz,xy-yx],[yz-zy,xx-yy-zz,xy+yx,zx+xz],[zx-xz,xy+yx,-xx+yy-zz,yz+zy],[xy-yx,zx+xz,yz+zy,-xx-yy+zz]];
  const eigen=Array.from({length:4},(_,i)=>Array.from({length:4},(_,j)=>Number(i===j)));
  for(let sweep=0;sweep<40;sweep++){
    let p=0,q=1;for(let i=0;i<4;i++)for(let j=i+1;j<4;j++)if(Math.abs(n[i][j])>Math.abs(n[p][q])){p=i;q=j}
    if(Math.abs(n[p][q])<1e-12)break;
    const angle=.5*Math.atan2(2*n[p][q],n[q][q]-n[p][p]),co=Math.cos(angle),si=Math.sin(angle);
    const pp=n[p][p],qq=n[q][q],pq=n[p][q];n[p][p]=co*co*pp-2*si*co*pq+si*si*qq;n[q][q]=si*si*pp+2*si*co*pq+co*co*qq;n[p][q]=n[q][p]=0;
    for(let k=0;k<4;k++){if(k!==p&&k!==q){const kp=n[k][p],kq=n[k][q];n[k][p]=n[p][k]=co*kp-si*kq;n[k][q]=n[q][k]=si*kp+co*kq}const vp=eigen[k][p],vq=eigen[k][q];eigen[k][p]=co*vp-si*vq;eigen[k][q]=si*vp+co*vq}
  }
  let best=0;for(let i=1;i<4;i++)if(n[i][i]>n[best][best])best=i;
  const r=fromQuaternion(eigen.map(row=>row[best]));return {r,t:sub(b,mv(r,a))};
}
function solve(a:number[][],b:number[]):number[]|null{
  const m=a.map((row,i)=>[...row,b[i]]),size=b.length;
  for(let i=0;i<size;i++){let p=i;for(let j=i+1;j<size;j++)if(Math.abs(m[j][i])>Math.abs(m[p][i]))p=j;
    if(Math.abs(m[p][i])<1e-10)return null;[m[i],m[p]]=[m[p],m[i]];const pivot=m[i][i];for(let k=i;k<=size;k++)m[i][k]/=pivot;
    for(let j=0;j<size;j++)if(j!==i){const f=m[j][i];for(let k=i;k<=size;k++)m[j][k]-=f*m[i][k]}}
  return m.map(row=>row[size]);
}
/** Robust left and accepted right-image reprojection; no known simulator pose. */
function refine(initial:Pose,matches:Correspondence[],c:StereoCalibration,iterations=10):Pose{
  let p={r:[...initial.r] as Mat3,t:[...initial.t] as Vec3};
  for(let iteration=0;iteration<iterations;iteration++){
    const normal=Array.from({length:6},()=>Array(6).fill(0)),rhs=Array(6).fill(0);let used=0;
    for(const match of matches){const uv=projectMatch(p,match,c);if(!uv)continue;
      const measurement=observed(match),residual=measurement.map((value,i)=>value-uv[i]);
      const leftLength=Math.hypot(residual[0],residual[1]),leftWeight=leftLength>3?3/leftLength:1;
      const weights=residual.map((value,i)=>i<2?leftWeight:Math.min(1,3/(Math.abs(value)+1e-12)));
      const j=Array.from({length:residual.length},()=>Array(6).fill(0));
      for(let axis=0;axis<6;axis++){const epsilon=axis<3?1e-4:1e-5,q=projectMatch(perturb(p,axis,epsilon),match,c);if(q)for(let row=0;row<residual.length;row++)j[row][axis]=(q[row]-uv[row])/epsilon}
      for(let axis=0;axis<6;axis++)for(let row=0;row<residual.length;row++){
        rhs[axis]+=weights[row]*j[row][axis]*residual[row];
        for(let other=0;other<6;other++)normal[axis][other]+=weights[row]*j[row][axis]*j[row][other];
      }used++;
    }
    if(used<6)break;for(let i=0;i<6;i++)normal[i][i]+=1e-4;
    const delta=solve(normal,rhs);if(!delta||!delta.every(Number.isFinite))break;
    const factor=Math.min(1,.25/(Math.hypot(...delta.slice(0,3))+1e-12),.15/(Math.hypot(...delta.slice(3))+1e-12));
    for(let axis=0;axis<6;axis++)p=perturb(p,axis,delta[axis]*factor);
    if(Math.hypot(...delta)<1e-6)break;
  }
  return p;
}
function inliers(p:Pose,matches:Correspondence[],c:StereoCalibration,threshold=2.5){return matches.filter(match=>{
  const uv=projectMatch(p,match,c);if(!uv)return false;const measurement=observed(match);
  return Math.hypot(uv[0]-measurement[0],uv[1]-measurement[1])<=threshold&&(uv.length===2||Math.abs(uv[2]-measurement[2])<=threshold);
})}
function spread(features:StereoFeature[],w:number,h:number){return features.length>0&&(Math.max(...features.map(f=>f.x))-Math.min(...features.map(f=>f.x)))>w*.18&&(Math.max(...features.map(f=>f.y))-Math.min(...features.map(f=>f.y)))>h*.18}

export class StereoSlam{
  readonly calibration:StereoCalibration;
  private options:Required<StereoSlamOptions>;
  private landmarks:Landmark[]=[];
  private path:StereoPose[]=[];
  private previous:Pose|null=null;
  private keyframe:Pose|null=null;
  private lastGood:StereoPose|null=null;
  private lastTime=-Infinity;
  private wasLost=false;
  private nextId=1;
  private keyframes=0;
  private relocalizations=0;
  private frameCount=0;
  constructor(calibration:StereoCalibration,options:StereoSlamOptions={}){
    const c=calibration;
    if(!Object.values(c).every(Number.isFinite)||!Number.isInteger(c.width)||!Number.isInteger(c.height)||c.width<32||c.height<32||c.width>640||c.height>480||c.fx<=0||c.fy<=0||c.baselineM<=0||c.cx<0||c.cx>=c.width||c.cy<0||c.cy>=c.height)throw new Error('Invalid rectified stereo calibration');
    this.calibration={...c};this.options={maxFeatures:options.maxFeatures??180,maxLandmarks:options.maxLandmarks??700,minDisparity:options.minDisparity??1.5,maxDepthM:options.maxDepthM??5,cornerThreshold:options.cornerThreshold??12};
    if(!Object.values(this.options).every(value=>Number.isFinite(value)&&value>0)||this.options.maxFeatures>400||this.options.maxLandmarks>2000)throw new Error('Invalid bounded stereo options');
  }
  start():StereoSlamState{return this.reset()}
  reset():StereoSlamState{this.landmarks=[];this.path=[];this.previous=null;this.keyframe=null;this.lastGood=null;this.lastTime=-Infinity;this.wasLost=false;this.nextId=1;this.keyframes=0;this.relocalizations=0;this.frameCount=0;return this.result('initializing',null,[],0,'Waiting for a synchronized stereo pair',0,0,null,0)}
  private result(status:StereoSlamState['status'],pose:StereoPose|null,features:Feature[],confidence:number,error:string|null,matches:number,count:number,rms:number|null,ms:number):StereoSlamState{
    return {status,pose,lastGoodPose:this.lastGood?structuredClone(this.lastGood):null,map:this.landmarks.map(l=>({id:l.id,position:[...l.position],observations:l.observations})),trajectory:structuredClone(this.path),
      features:features.map(({x,y,score,disparity,depthM,tracked,landmarkId})=>({x,y,score,disparity,depthM,tracked,landmarkId})),confidence,error,
      metrics:{detected:features.length,stereoMatches:features.filter(f=>f.point).length,mapMatches:matches,inliers:count,reprojectionErrorPx:rms,processingMs:ms,keyframes:this.keyframes,relocalizations:this.relocalizations}};
  }
  frame(frame:StereoFrame):StereoSlamState{
    const began=performance.now(),c=this.calibration;
    const fail=(features:Feature[],reason:string,matches=0,count=0,rms:number|null=null)=>{this.wasLost=this.landmarks.length>0;return this.result(this.landmarks.length?'lost':'initializing',null,features,0,reason,matches,count,rms,performance.now()-began)};
    if(!Number.isFinite(frame.timestampMs)||frame.timestampMs<=this.lastTime)return fail([],'Stereo timestamps must increase');
    if(frame.left.length!==c.width*c.height*4||frame.right.length!==c.width*c.height*4)return fail([],'Stereo RGBA dimensions do not match calibration');
    this.lastTime=frame.timestampMs;this.frameCount++;
    const left=gray(frame.left,c.width,c.height),right=gray(frame.right,c.width,c.height),features=corners(left,c.width,c.height,this.options.maxFeatures,this.options.cornerThreshold);
    stereo(features,left,right,c,this.options.minDisparity,this.options.maxDepthM);
    const depthFeatures=features.filter(f=>f.point);
    if(!this.landmarks.length){
      if(depthFeatures.length<18||!spread(depthFeatures,c.width,c.height))return fail(features,'Insufficient distributed, unambiguous stereo features');
      this.previous={r:[...I],t:[0,0,0]};this.keyframe=this.previous;this.keyframes=1;
      for(const f of depthFeatures)this.addLandmark(f,this.previous);
      const pose=publicPose(this.previous,frame.timestampMs);this.lastGood=pose;this.path.push(pose);
      // The first camera defines the map origin; this is stereo map creation,
      // not independent temporal pose verification or measured zero error.
      return this.result('tracking',pose,features,Math.min(.7,depthFeatures.length/100),null,0,0,null,performance.now()-began);
    }
    const matches=this.match(features);
    if(matches.length<8||!spread(matches.map(m=>m.feature),c.width,c.height))return fail(features,'Too few distributed map correspondences',matches.length);
    let best=this.previous!,consensus=inliers(best,matches,c),bestError=Infinity;
    const consider=(candidate:Pose|null)=>{if(!candidate)return;const group=inliers(candidate,matches,c);let error=0;for(const m of group)error+=Math.sqrt(reprojectionSquared(candidate,m,c));
      if(group.length>consensus.length||(group.length===consensus.length&&error<bestError)){best=candidate;consensus=group;bestError=error}};
    consider(refine(this.previous!,matches,c,8));
    const stereoMatches=matches.filter(m=>m.feature.point);
    let seed=this.frameCount*8179+17;
    const pick=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed%stereoMatches.length};
    if(stereoMatches.length>=6){consider(align(stereoMatches));for(let trial=0;trial<64;trial++){const indices=new Set<number>();while(indices.size<3)indices.add(pick());consider(align([...indices].map(i=>stereoMatches[i])))}}
    if(consensus.length>=6){best=refine(best,consensus,c);consensus=inliers(best,matches,c);if(consensus.length>=6){best=refine(best,consensus,c,5);consensus=inliers(best,matches,c)}}
    const rms=consensus.length?Math.sqrt(consensus.reduce((sum,m)=>sum+reprojectionSquared(best,m,c),0)/consensus.length):Infinity;
    const minimum=this.wasLost?12:8,ratio=consensus.length/matches.length;
    if(consensus.length<minimum||ratio<(this.wasLost?.45:.35)||rms>2||!spread(consensus.map(m=>m.feature),c.width,c.height)||![...best.r,...best.t].every(Number.isFinite))return fail(features,'Geometric pose verification failed',matches.length,consensus.length,Number.isFinite(rms)?rms:null);
    for(const m of consensus){m.feature.tracked=true;m.feature.landmarkId=m.landmark.id;m.landmark.observations++}
    const relocalized=this.wasLost;if(relocalized)this.relocalizations++;
    this.wasLost=false;this.previous=best;
    const pose=publicPose(best,frame.timestampMs);this.lastGood=pose;
    if(!this.path.length||norm(sub(pose.position,this.path[this.path.length-1].position))>.015||this.frameCount%5===0){this.path.push(pose);if(this.path.length>400)this.path.shift()}
    const change=mm(transpose(this.keyframe!.r),best.r),angle=Math.acos(Math.max(-1,Math.min(1,(change[0]+change[4]+change[8]-1)/2)));
    if(norm(sub(best.t,this.keyframe!.t))>.10||angle>.10){
      this.keyframe={r:[...best.r],t:[...best.t]};this.keyframes++;
      for(const m of consensus)if(m.landmark.descriptors.length<3)m.landmark.descriptors.push(m.feature.descriptor);
      for(const f of depthFeatures)if(!f.tracked&&this.landmarks.length<this.options.maxLandmarks)this.addLandmark(f,best);
    }
    const confidence=Math.min(1,consensus.length/40)*ratio*Math.max(0,1-rms/4);
    return this.result(relocalized?'relocalized':'tracking',pose,features,confidence,null,matches.length,consensus.length,rms,performance.now()-began);
  }
  private addLandmark(feature:Feature,pose:Pose){const id=this.nextId++;this.landmarks.push({id,position:add(mv(pose.r,feature.point!),pose.t),observations:1,descriptors:[feature.descriptor]});feature.landmarkId=id;feature.tracked=true}
  private match(features:Feature[]):Correspondence[]{
    const selected=new Map<number,Correspondence>();
    for(const feature of features){let nearest:Landmark|null=null,best=129,second=129;
      for(const landmark of this.landmarks){let distance=129;for(const d of landmark.descriptors)distance=Math.min(distance,hamming(feature.descriptor,d));if(distance<best){second=best;best=distance;nearest=landmark}else second=Math.min(second,distance)}
      if(!nearest||best>38||best>=second*.82||second-best<5)continue;
      const old=selected.get(nearest.id);if(!old||best<old.distance)selected.set(nearest.id,{feature,landmark:nearest,distance:best});
    }
    return [...selected.values()];
  }
}
