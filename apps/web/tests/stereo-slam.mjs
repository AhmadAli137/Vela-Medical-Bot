/** Ground truth exists only in this independent synthetic image renderer.
 * node --test apps/web/tests/stereo-slam.mjs
 */
import assert from 'node:assert/strict';
import test,{after} from 'node:test';
import {readFileSync,writeFileSync} from 'node:fs';
import {inflateSync} from 'node:zlib';
import ts from 'typescript';

const source=readFileSync(new URL('../src/stereoSlam.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {StereoSlam}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const guardSource=readFileSync(new URL('../src/visualTrackingGuard.ts',import.meta.url),'utf8');
const guardCompiled=ts.transpileModule(guardSource,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {VisualTrackingGuard}=await import(`data:text/javascript;base64,${Buffer.from(guardCompiled).toString('base64')}`);
const calibration={width:320,height:240,fx:120,fy:120,cx:160,cy:120,baselineM:.054};
const evidence={input_contract:'RGBA stereo pixels, calibration and timestamp only; ground truth restricted to independent test renderer',cases:[]};
after(()=>writeFileSync(new URL('../../../artifacts/stereo-slam-tests.json',import.meta.url),JSON.stringify(evidence,null,2)+'\n'));
let randomState=8141;
function random(){randomState=(Math.imul(randomState,1664525)+1013904223)>>>0;return randomState/4294967296}
const texture=Float32Array.from({length:512*512},()=>20+random()*220);
function tex(x,y,offset){
  x=x*24+256+offset;y=y*24+256+offset;
  const ix=Math.floor(x),iy=Math.floor(y),a=x-ix,b=y-iy;
  const at=(u,v)=>texture[((v%512+512)%512)*512+(u%512+512)%512];
  return (1-b)*((1-a)*at(ix,iy)+a*at(ix+1,iy))+b*((1-a)*at(ix,iy+1)+a*at(ix+1,iy+1));
}
function rotate(v,yaw,roll){const a=[Math.cos(yaw)*v[0]+Math.sin(yaw)*v[2],v[1],-Math.sin(yaw)*v[0]+Math.cos(yaw)*v[2]];return [Math.cos(roll)*a[0]-Math.sin(roll)*a[1],Math.sin(roll)*a[0]+Math.cos(roll)*a[1],a[2]]}
const planes=[{z:1.5,x0:-1.2,x1:-.35,y0:-.8,y1:.65,id:0},{z:1.8,x0:.35,x1:1.2,y0:-.65,y1:.8,id:41},{z:2.5,x0:-10,x1:10,y0:-10,y1:10,id:93}];
function renderEye(position,yaw,roll,right=false){
  const c=calibration,origin=position.map((v,i)=>v+rotate([right?c.baselineM:0,0,0],yaw,roll)[i]);
  const rgba=new Uint8ClampedArray(c.width*c.height*4);
  for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++){
    const direction=rotate([(x-c.cx)/c.fx,(y-c.cy)/c.fy,1],yaw,roll);let nearest=Infinity,value=128;
    for(const plane of planes){const d=(plane.z-origin[2])/direction[2];if(d<=0||d>=nearest)continue;const xx=origin[0]+d*direction[0],yy=origin[1]+d*direction[1];if(xx>=plane.x0&&xx<=plane.x1&&yy>=plane.y0&&yy<=plane.y1){nearest=d;value=tex(xx,yy,plane.id)}}
    const index=(y*c.width+x)*4;rgba[index]=rgba[index+1]=rgba[index+2]=value;rgba[index+3]=255;
  }
  return rgba;
}
function pair(position=[0,0,0],yaw=0,roll=0,time=1){return {left:renderEye(position,yaw,roll),right:renderEye(position,yaw,roll,true),timestampMs:time}}
const blank=()=>new Uint8ClampedArray(calibration.width*calibration.height*4);
// Lossless, test-only decoder for the captured 8-bit RGB/RGBA PNG fixtures.
function pngPixels(name){
  const file=readFileSync(new URL(`./fixtures/stereo-room/${name}.png`,import.meta.url)),compressed=[];
  assert.equal(file.subarray(0,8).toString('hex'),'89504e470d0a1a0a');
  let width,height,channels;
  for(let offset=8;offset<file.length;){const length=file.readUInt32BE(offset),type=file.toString('ascii',offset+4,offset+8),data=file.subarray(offset+8,offset+8+length);
    if(type==='IHDR'){width=data.readUInt32BE(0);height=data.readUInt32BE(4);assert.equal(data[8],8);assert([2,6].includes(data[9]));assert.equal(data[12],0);channels=data[9]===6?4:3}
    if(type==='IDAT')compressed.push(data);offset+=length+12;
  }
  assert.equal(width,calibration.width);assert.equal(height,calibration.height);
  const rows=inflateSync(Buffer.concat(compressed)),stride=width*channels,decoded=new Uint8Array(stride*height);
  const paeth=(a,b,c)=>{const p=a+b-c,pa=Math.abs(p-a),pb=Math.abs(p-b),pc=Math.abs(p-c);return pa<=pb&&pa<=pc?a:pb<=pc?b:c};
  for(let y=0;y<height;y++){const filter=rows[y*(stride+1)];assert(filter<=4);
    for(let x=0;x<stride;x++){const i=y*stride+x,a=x>=channels?decoded[i-channels]:0,b=y?decoded[i-stride]:0,c=y&&x>=channels?decoded[i-stride-channels]:0;
      const predicted=filter===0?0:filter===1?a:filter===2?b:filter===3?Math.floor((a+b)/2):paeth(a,b,c);decoded[i]=(rows[y*(stride+1)+1+x]+predicted)&255}}
  const rgba=new Uint8ClampedArray(width*height*4);for(let i=0;i<width*height;i++){rgba[i*4]=decoded[i*channels];rgba[i*4+1]=decoded[i*channels+1];rgba[i*4+2]=decoded[i*channels+2];rgba[i*4+3]=channels===4?decoded[i*channels+3]:255}return rgba;
}
function positionError(state,target){return state.pose?Math.hypot(...state.pose.position.map((v,i)=>v-target[i])):Infinity}
function rotationError(state,yaw,roll=0){
  if(!state.pose)return Infinity;const expected=[-Math.sin(roll/2)*Math.sin(yaw/2),Math.cos(roll/2)*Math.sin(yaw/2),Math.sin(roll/2)*Math.cos(yaw/2),Math.cos(roll/2)*Math.cos(yaw/2)];
  return 2*Math.acos(Math.min(1,Math.abs(expected.reduce((sum,v,i)=>sum+v*state.pose.orientation[i],0))));
}

test('stereo pixels initialize a metric landmark map without pose/depth inputs',()=>{
  const slam=new StereoSlam(calibration);slam.start();const state=slam.frame(pair());
  evidence.cases.push({name:'initialize',status:state.status,metrics:state.metrics,landmarks:state.map.length});
  assert.equal(state.status,'tracking',JSON.stringify(state.metrics));assert(state.map.length>=18);
  assert.deepEqual(state.pose.position,[0,0,0]);assert(state.map.every(p=>p.position.every(Number.isFinite)&&p.position[2]>0));
  assert(state.features.filter(f=>f.disparity!==null).length>=18);
});

test('translation and rotation are recovered from image changes, not a motion timer',()=>{
  const slam=new StereoSlam(calibration);slam.start();slam.frame(pair());
  let state;
  for(let i=1;i<=4;i++)state=slam.frame(pair([i*.03,-i*.004,i*.003],i*.015,i*.004,i*200+1));
  const target=[.12,-.016,.012],pe=positionError(state,target),re=rotationError(state,.06,.016);
  evidence.cases.push({name:'combined_motion',status:state.status,estimated:state.pose,ground_truth:{position:target,yaw:.06,roll:.016},position_error_m:pe,rotation_error_rad:re,metrics:state.metrics});
  assert(state.pose,JSON.stringify(state.metrics));assert(pe<.06,`Translation error ${pe}`);assert(re<.04,`Rotation error ${re}`);
  assert(state.pose.position[0]>.06,'A frozen zero pose must not pass');assert(Math.abs(state.pose.orientation[1])>.01,'Identity rotation must not pass');
});

test('blank or unrelated images lose tracking and revisiting mapped pixels relocalizes',()=>{
  const slam=new StereoSlam(calibration);slam.start();const first=slam.frame(pair());
  const moved=slam.frame(pair([.03,0,0],.015,0,201));assert(moved.pose);
  const lost=slam.frame({left:blank(),right:blank(),timestampMs:401});
  assert.equal(lost.status,'lost');assert.equal(lost.pose,null);assert.equal(lost.confidence,0);assert.equal(lost.map.length,first.map.length);assert(lost.lastGoodPose);
  const unrelated=Uint8ClampedArray.from({length:calibration.width*calibration.height*4},(_,i)=>i%4===3?255:Math.floor(random()*256));
  const rejected=slam.frame({left:unrelated,right:unrelated,timestampMs:501});
  assert.equal(rejected.status,'lost');assert.equal(rejected.pose,null);assert.equal(rejected.confidence,0);
  const recovered=slam.frame(pair([0,0,0],0,0,601));
  evidence.cases.push({name:'loss_and_relocalization',lost_status:lost.status,recovered_status:recovered.status,metrics:recovered.metrics,error_m:positionError(recovered,[0,0,0])});
  assert.equal(recovered.status,'relocalized',JSON.stringify(recovered.metrics));assert(positionError(recovered,[0,0,0])<.03);
});

test('advancing timestamps with an unchanged image do not invent camera motion',()=>{
  const slam=new StereoSlam(calibration),images=pair();slam.frame(images);
  const state=slam.frame({...images,timestampMs:60001});
  assert.equal(state.status,'tracking');assert(positionError(state,[0,0,0])<1e-8);assert(rotationError(state,0)<1e-7);
  evidence.cases.push({name:'stationary_pixels_despite_elapsed_time',position_error_m:positionError(state,[0,0,0]),metrics:state.metrics});
});

test('blank/occluded stereo cannot initialize invented depth or a pose',()=>{
  const slam=new StereoSlam(calibration);slam.start();
  const empty=slam.frame({left:blank(),right:blank(),timestampMs:1});assert.equal(empty.status,'initializing');assert.equal(empty.pose,null);assert.equal(empty.map.length,0);
  const occluded=slam.frame({...pair(),right:blank(),timestampMs:201});
  assert.equal(occluded.pose,null);assert.equal(occluded.map.length,0);assert.equal(occluded.metrics.stereoMatches,0);
  evidence.cases.push({name:'blank_and_stereo_occlusion',blank:empty.status,occluded:occluded.status,occluded_metrics:occluded.metrics});
});

test('a mapped left image still localizes with a blank right image without claiming fresh stereo',()=>{
  const slam=new StereoSlam(calibration),first=slam.frame(pair());
  const state=slam.frame({...pair([.03,0,0],.015,0,201),right:blank()});
  assert.equal(state.status,'tracking',JSON.stringify(state.metrics));
  assert.equal(state.metrics.stereoMatches,0);assert(state.features.every(feature=>feature.disparity===null));
  assert.equal(state.map.length,first.map.length);assert(state.metrics.inliers>=12);
  assert(positionError(state,[.03,0,0])<.03);
  evidence.cases.push({name:'existing_map_with_missing_right_eye',status:state.status,metrics:state.metrics,position_error_m:positionError(state,[.03,0,0]),new_stereo_depth:false});
});

test('contradictory accepted right disparities cannot masquerade as an unchanged verified stereo pose',()=>{
  const slam=new StereoSlam(calibration),images=pair();slam.frame(images);
  // Keep the left image stationary while shifting the right scene farther
  // left. Patches still match and triangulate, but disagree with the existing
  // metric map. A left-only objective would incorrectly report zero error.
  const corrupted=blank(),shift=8;
  for(let y=0;y<calibration.height;y++)for(let x=0;x<calibration.width-shift;x++){
    const target=(y*calibration.width+x)*4,from=(y*calibration.width+x+shift)*4;
    corrupted.set(images.right.subarray(from,from+4),target);
  }
  const state=slam.frame({...images,right:corrupted,timestampMs:201});
  assert(state.metrics.stereoMatches>=18,'Corruption must retain real stereo patch matches to exercise geometric verification');
  assert.equal(state.status,'lost',JSON.stringify(state.metrics));assert.equal(state.pose,null);
  evidence.cases.push({name:'contradictory_right_disparity',status:state.status,metrics:state.metrics,corruption_shift_px:shift});
});

test('reset removes landmarks/history and malformed or stale frames produce no current pose',()=>{
  const slam=new StereoSlam(calibration);slam.frame(pair());
  const stale=slam.frame(pair());assert.equal(stale.pose,null);assert.match(stale.error,/timestamps/);
  const malformed=slam.frame({left:new Uint8Array(4),right:blank(),timestampMs:100});assert.equal(malformed.pose,null);assert.match(malformed.error,/dimensions/);
  const reset=slam.reset();assert.equal(reset.map.length,0);assert.equal(reset.trajectory.length,0);assert.equal(reset.lastGoodPose,null);assert.equal(reset.status,'initializing');
  assert.throws(()=>new StereoSlam({...calibration,baselineM:0}),/calibration/);
  evidence.cases.push({name:'reset_and_input_validation',passed:true});
});

test('actual rendered hospital stereo pixels map external features; corrupted right eye cannot initialize',()=>{
  const images={left:pngPixels('left'),right:pngPixels('right'),timestampMs:1};
  const slam=new StereoSlam(calibration),first=slam.frame(images),tracked=slam.frame({...images,timestampMs:201});
  assert.equal(first.status,'tracking');assert(first.map.length>=18);assert.equal(tracked.status,'tracking');assert(tracked.metrics.inliers>=12);
  assert(positionError(tracked,[0,0,0])<1e-7);
  const invalid=new StereoSlam(calibration).frame({...images,right:blank()});
  assert.equal(invalid.pose,null);assert.equal(invalid.map.length,0);assert.equal(invalid.metrics.stereoMatches,0);
  evidence.cases.push({name:'actual_hospital_pixels',fixture:'tests/fixtures/stereo-room; robot-lens self-view eliminated before capture',initial_landmarks:first.map.length,tracking:tracked.metrics,right_eye_occlusion:{status:invalid.status,map_size:invalid.map.length}});
});

test('pixel-derived tracking loss activates the pause guard and image recovery cannot auto-resume',()=>{
  const images={left:pngPixels('left'),right:pngPixels('right'),timestampMs:1},slam=new StereoSlam(calibration),guard=new VisualTrackingGuard();
  const tracked=slam.frame(images);assert(tracked.pose);
  const input=(state,nowMs)=>({enabled:true,moving:true,nowMs,frameAtMs:nowMs,status:state.status,hasPose:state.pose!==null});
  assert.equal(guard.evaluate(input(tracked,0)),false);
  const lost=slam.frame({left:blank(),right:blank(),timestampMs:201});assert.equal(lost.status,'lost');
  assert.equal(guard.evaluate(input(lost,200)),false);assert.equal(guard.evaluate(input(lost,1699)),false);assert.equal(guard.evaluate(input(lost,1700)),true);
  const recovered=slam.frame({...images,timestampMs:1801});assert.equal(recovered.status,'relocalized');
  assert.equal(guard.evaluate(input(recovered,1800)),true);
  guard.reset();assert.equal(guard.evaluate(input(recovered,1900)),false);
  evidence.cases.push({name:'real_pixel_loss_to_pause_guard',lost_status:lost.status,recovered_status:recovered.status,pause_requested_after_ms:1500,automatic_resume:false});
});
