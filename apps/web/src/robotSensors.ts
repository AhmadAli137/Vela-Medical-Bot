import * as THREE from 'three';
import { StereoSlam, type StereoSlamState } from './stereoSlam';
import { createSensorRoomEnvelope } from './sensorRoomEnvelope';

export const SENSOR_NAMES = ['head_rgb', 'head_stereo_right', 'left_wrist', 'right_wrist'] as const;
export type SensorName = typeof SENSOR_NAMES[number];
export type SensorPose = {position:[number,number,number];rotation:number[];fovy_deg:number;convention:'mujoco_opengl'};
export type SensorSnapshot = {slam:StereoSlamState;frames:number;timestampMs:number;frameRate:number;width:number;height:number;evaluation:{groundTruthPosition:number[]|null;positionErrorM:number|null}};
export type SensorCanvasSet = Partial<Record<SensorName, HTMLCanvasElement | null>>;
const WIDTH=320, HEIGHT=240;

/** Camera images are rendered from the measured MuJoCo extrinsics. Only their
 * pixels, timestamps, and stereo calibration enter the visual estimator. */
export class RobotSensors {
  private cameras=new Map<SensorName,THREE.PerspectiveCamera>();
  private target=new THREE.WebGLRenderTarget(WIDTH,HEIGHT,{depthBuffer:true});
  private raw=new Uint8Array(WIDTH*HEIGHT*4);
  private images=new Map<SensorName,Uint8ClampedArray>();
  private slam=new StereoSlam({width:WIDTH,height:HEIGHT,fx:120,fy:120,cx:160,cy:120,baselineM:.054},{maxFeatures:240,maxLandmarks:1400});
  private frames=0;
  private lastAt=-Infinity;
  private previousTime=-1;
  private startedAt=0;
  private evaluationOrigin:SensorPose|null=null;
  private enclosure=createSensorRoomEnvelope();
  constructor(private renderer:THREE.WebGLRenderer,private scene:THREE.Scene){
    scene.add(this.enclosure);
    this.target.texture.colorSpace=THREE.SRGBColorSpace;
    for(const name of SENSOR_NAMES){this.cameras.set(name,new THREE.PerspectiveCamera(name.startsWith('head')?90:75,WIDTH/HEIGHT,.015,25));this.images.set(name,new Uint8ClampedArray(WIDTH*HEIGHT*4))}
    this.slam.start();
  }
  reset(){this.slam.reset();this.frames=0;this.startedAt=0;this.previousTime=-1;this.lastAt=-Infinity;this.evaluationOrigin=null}
  sample(poses:Partial<Record<SensorName,SensorPose>>,simulationTime:number,now:number,canvases:SensorCanvasSet):SensorSnapshot|null{
    if(simulationTime<this.previousTime-.01)this.reset();
    if(now-this.lastAt<200)return null;
    if(!SENSOR_NAMES.every(name=>poses[name]))return null;
    this.lastAt=now;this.previousTime=simulationTime;
    if(!this.startedAt)this.startedAt=now;
    const previousTarget=this.renderer.getRenderTarget();
    const previousXr=this.renderer.xr.enabled;
    const shadows=this.renderer.shadowMap.autoUpdate;
    this.renderer.xr.enabled=false;this.renderer.shadowMap.autoUpdate=false;
    this.enclosure.visible=true;
    try{
      for(const name of SENSOR_NAMES){
        const pose=poses[name]!,camera=this.cameras.get(name)!,r=pose.rotation;
        camera.position.fromArray(pose.position);
        camera.quaternion.setFromRotationMatrix(new THREE.Matrix4().set(r[0],r[1],r[2],0,r[3],r[4],r[5],0,r[6],r[7],r[8],0,0,0,0,1));
        camera.fov=pose.fovy_deg;camera.updateProjectionMatrix();camera.updateMatrixWorld(true);
        this.renderer.setRenderTarget(this.target);this.renderer.clear();this.renderer.render(this.scene,camera);
        this.renderer.readRenderTargetPixels(this.target,0,0,WIDTH,HEIGHT,this.raw);
        const pixels=this.images.get(name)!;
        for(let y=0;y<HEIGHT;y++)pixels.set(this.raw.subarray((HEIGHT-1-y)*WIDTH*4,(HEIGHT-y)*WIDTH*4),y*WIDTH*4);
        const canvas=canvases[name],context=canvas?.getContext('2d');
        if(canvas&&context){if(canvas.width!==WIDTH)canvas.width=WIDTH;if(canvas.height!==HEIGHT)canvas.height=HEIGHT;context.putImageData(new ImageData(new Uint8ClampedArray(pixels),WIDTH,HEIGHT),0,0);canvas.dataset.frames=String(this.frames+1)}
      }
    }finally{this.enclosure.visible=false;this.renderer.setRenderTarget(previousTarget);this.renderer.xr.enabled=previousXr;this.renderer.shadowMap.autoUpdate=shadows}
    const slam=this.slam.frame({left:this.images.get('head_rgb')!,right:this.images.get('head_stereo_right')!,timestampMs:now});
    this.frames++;
    // Simulator truth is isolated AFTER estimation for reproducible accuracy
    // checks. It is never supplied to StereoSlam or drawn as its map/path.
    if(slam.pose&&!this.evaluationOrigin)this.evaluationOrigin=structuredClone(poses.head_rgb!);
    let groundTruthPosition:number[]|null=null,positionErrorM:number|null=null;
    if(this.evaluationOrigin){const origin=this.evaluationOrigin,r=origin.rotation,d=poses.head_rgb!.position.map((v,i)=>v-origin.position[i]);groundTruthPosition=[r[0]*d[0]+r[3]*d[1]+r[6]*d[2],-(r[1]*d[0]+r[4]*d[1]+r[7]*d[2]),-(r[2]*d[0]+r[5]*d[1]+r[8]*d[2])];if(slam.pose)positionErrorM=Math.hypot(...slam.pose.position.map((v,i)=>v-groundTruthPosition![i]))}
    return {slam,frames:this.frames,timestampMs:now,frameRate:this.frames*1000/Math.max(200,now-this.startedAt),width:WIDTH,height:HEIGHT,evaluation:{groundTruthPosition,positionErrorM}};
  }
  dispose(){this.target.dispose()}
}
