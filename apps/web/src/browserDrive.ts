/** Differential drive through actual MuJoCo tire contacts, with upright guides.
 * Mirrors sim/reference_drive.py; it never writes body poses or base qpos.
 */
import type {MainModule,MjData,MjModel} from '@mujoco/mujoco';

export type Navigation={kind:'turn'|'drive'|'face';reverse:boolean;goal:[number,number,number]};
export type NavigationStage={name:string;duration_s:number;target_qpos:number[];action_phase?:string;navigation?:Navigation};
export type DriveMetrics={forward_velocity_m_s:number;lateral_velocity_m_s:number;yaw_rate_rad_s:number;wheel_ground_contacts:Record<'left'|'right',boolean>;wheel_normal_force_n:Record<'left'|'right',number>;actuator_count:number;base_pose:{x:number;y:number;z:number;yaw:number};constraint:'upright_unvalidated'};
const SIDES=['left','right'] as const;
const BASE=['base_x','base_y','base_yaw'];
const RADIUS=.13,TRACK=.40;
const clip=(value:number,low:number,high:number)=>Math.max(low,Math.min(high,value));
export const wrapAngle=(angle:number)=>Math.atan2(Math.sin(angle),Math.cos(angle));

export class DifferentialDrive{
  readonly baseQ:number[];
  readonly baseDofs:number[];
  readonly wheelActuators:number[];
  readonly positionActuators:number[];
  readonly positionQ:number[];
  readonly positionDofs:number[];
  private readonly baseBody:number;
  private readonly timestep:number;
  constructor(private engine:MainModule,private model:MjModel,private data:MjData){
    const jointIds=BASE.map(name=>engine.mj_name2id(model,engine.mjtObj.mjOBJ_JOINT.value,name));
    this.baseQ=jointIds.map(id=>model.jnt_qposadr[id]);this.baseDofs=jointIds.map(id=>model.jnt_dofadr[id]);
    this.wheelActuators=SIDES.map(side=>engine.mj_name2id(model,engine.mjtObj.mjOBJ_ACTUATOR.value,`ctrl_${side}_wheel_joint`));
    this.positionActuators=Array.from({length:model.nu},(_,index)=>index).filter(index=>!this.wheelActuators.includes(index));
    this.positionQ=this.positionActuators.map(index=>model.jnt_qposadr[model.actuator_trnid[index*2]]);
    this.positionDofs=this.positionActuators.map(index=>model.jnt_dofadr[model.actuator_trnid[index*2]]);
    this.baseBody=engine.mj_name2id(model,engine.mjtObj.mjOBJ_BODY.value,'robot_base');
    const option=model.opt;this.timestep=option.timestep;option.delete();
    if(model.nu!==22||jointIds.some(id=>id<0)||this.wheelActuators.some(id=>id<0)||BASE.some(name=>engine.mj_name2id(model,engine.mjtObj.mjOBJ_ACTUATOR.value,`ctrl_${name}`)>=0))throw new Error('Expected two wheel velocity motors and 20 position actuators, without planar base actuators');
  }

  apply(target:number[],navigation?:Navigation){
    const [x,y,yaw]=this.baseQ.map(q=>this.data.qpos[q]),[goalX,goalY,goalYaw]=this.baseQ.map(q=>target[q]);
    const dx=goalX-x,dy=goalY-y;
    const forwardError=Math.cos(goalYaw)*dx+Math.sin(goalYaw)*dy,crossError=-Math.sin(goalYaw)*dx+Math.cos(goalYaw)*dy;
    let headingError=wrapAngle(goalYaw-yaw),velocity:number,angular:number;
    if(navigation?.kind==='drive'){
      velocity=clip(1.6*forwardError,-.25,.25);
      const correction=Math.atan2(2*crossError,Math.max(.08,Math.abs(forwardError)));
      headingError+=correction*(navigation.reverse?-1:1);
      velocity*=Math.max(0,Math.cos(headingError));angular=clip(3*headingError,-.65,.65);
    }else if(navigation){velocity=0;angular=clip(3*headingError,-.65,.65)}
    else{velocity=clip(2*forwardError,-.04,.04);angular=clip(3*headingError,-.15,.15)}
    const desired=[(velocity-TRACK*angular/2)/RADIUS,(velocity+TRACK*angular/2)/RADIUS];
    this.wheelActuators.forEach((actuator,index)=>{
      const change=clip(desired[index]-this.data.ctrl[actuator],-8*this.timestep,8*this.timestep);
      this.data.ctrl[actuator]=clip(this.data.ctrl[actuator]+change,-6,6);
    });
  }

  error(target:number[]){
    const actual=this.baseQ.map(q=>this.data.qpos[q]),goal=this.baseQ.map(q=>target[q]);
    return{position_m:Math.hypot(actual[0]-goal[0],actual[1]-goal[1]),heading_rad:Math.abs(wrapAngle(actual[2]-goal[2]))};
  }

  expandStages<T extends NavigationStage>(initial:number[],stages:T[]):T[]{
    let previous=[...initial];const result:T[]=[];
    for(const source of stages){
      const target=[...source.target_qpos],before=this.baseQ.map(q=>previous[q]),after=this.baseQ.map(q=>target[q]);
      const dx=after[0]-before[0],dy=after[1]-before[1],distance=Math.hypot(dx,dy),current=[...previous];
      const phase=source.action_phase??source.name;
      const segment=(kind:Navigation['kind'],seconds:number,reverse=false)=>{
        result.push({name:`${source.name}_${kind}`,action_phase:phase,target_qpos:[...current],duration_s:seconds,navigation:{kind,reverse,goal:this.baseQ.map(q=>current[q]) as [number,number,number]}} as T);
      };
      if(distance>1e-7){
        let heading=Math.atan2(dy,dx);const reverse=Math.abs(wrapAngle(heading-before[2]))>Math.PI/2;
        if(reverse)heading=wrapAngle(heading+Math.PI);
        const turn=Math.abs(wrapAngle(heading-before[2]));
        if(turn>1e-5){current[this.baseQ[2]]=heading;segment('turn',turn/.45+2)}
        current[this.baseQ[0]]=after[0];current[this.baseQ[1]]=after[1];segment('drive',distance/.22+4,reverse);
        const face=Math.abs(wrapAngle(after[2]-heading));
        if(face>1e-5){current[this.baseQ[2]]=after[2];segment('face',face/.45+2)}
      }else if(Math.abs(wrapAngle(after[2]-before[2]))>1e-5){
        current[this.baseQ[2]]=after[2];segment('face',Math.abs(wrapAngle(after[2]-before[2]))/.45+2);
      }
      const final={...source,target_qpos:target,action_phase:phase};
      if(distance>1e-7&&Math.max(...this.positionQ.map(q=>Math.abs(target[q]-previous[q])))<1e-7)final.duration_s=1;
      result.push(final);previous=target;
    }
    return result;
  }

  observe():DriveMetrics{
    const q=this.baseQ.map(index=>this.data.qpos[index]),velocity=this.baseDofs.map(index=>this.data.qvel[index]);
    const loads={left:0,right:0};
    if(this.data.ncon){
      const contacts=this.data.contact,wrench=new this.engine.DoubleBuffer(6);
      try{
        for(let index=0;index<this.data.ncon;index++){
          const contact=contacts.get(index);if(!contact)continue;
          try{
            const names=[contact.geom1,contact.geom2].map(id=>this.engine.mj_id2name(this.model,this.engine.mjtObj.mjOBJ_GEOM.value,id));
            if(!names.includes('floor'))continue;
            for(const side of SIDES)if(names.includes(`${side}_wheel_geom`)){
              this.engine.mj_contactForce(this.model,this.data,index,wrench);loads[side]+=Math.max(0,wrench.GetView()[0]);
            }
          }finally{contact.delete()}
        }
      }finally{contacts.delete();wrench.delete()}
    }
    const position=this.baseBody*3;
    return{forward_velocity_m_s:Math.cos(q[2])*velocity[0]+Math.sin(q[2])*velocity[1],lateral_velocity_m_s:-Math.sin(q[2])*velocity[0]+Math.cos(q[2])*velocity[1],yaw_rate_rad_s:velocity[2],wheel_ground_contacts:{left:loads.left>.01,right:loads.right>.01},wheel_normal_force_n:loads,actuator_count:this.model.nu,base_pose:{x:this.data.xpos[position],y:this.data.xpos[position+1],z:this.data.xpos[position+2],yaw:q[2]},constraint:'upright_unvalidated'};
  }
}
