/** Actual MuJoCo WebAssembly dynamics for the public static demonstration.
 * Same estimated model and bounded controllers as sim/reference_runtime.py.
 * No robot, hospital API, uploaded media, or replayed pose animation is involved.
 */
import type {MainModule, MjData, MjModel} from '@mujoco/mujoco';

export type Vec3=[number,number,number];
export type Quat=[number,number,number,number];
export type PhysicsCommand='joint_demo'|'reach_demo'|'pause'|'reset';
export type ReferenceDescriptors={model_hash:string;body_specs:{name:string;joint?:string;initial_q?:number}[];hardware_model_verified:false};
type Contact={geoms:[string,string];distance_m:number;self_collision:boolean};
type ReachPlan={target:Vec3;side:'left'|'right';residual_m:number;reachable:boolean;collision_free_samples:boolean;sample_count:number;contacts:Contact[];target_qpos:number[];start_qpos?:number[];duration_s?:number};
export type BrowserPhysicsState={
  bodies:Record<string,{position:Vec3;quaternion:Quat}>;
  joints:Record<string,number>;
  mode:'idle'|'joint_demo'|'reach_demo';paused:boolean;simulation_time:number;
  target:{position:Vec3};end_effectors:Record<string,Vec3>;
  metrics:{physics_steps:number;finite_dynamics:boolean;contacts:Contact[];stop_reason:string|null;grasp_success:null;object_attached:false;reach?:{target:Vec3;ik_residual_m:number;actual_endpoint_error_m:number;endpoint_reached:boolean;sampled_collision_gate_passed:boolean;samples:number}};
  model_hash:string;hardware_model_verified:false;authorizes_hardware:false;source:string;engine:'mujoco-wasm';engine_version:string;
};

const INITIAL_ARM_Q=[0,-.30,0,-1.50,0,-.15,0];
const clamp=(value:number,minimum:number,maximum:number)=>Math.max(minimum,Math.min(maximum,value));
const norm=(values:number[])=>Math.sqrt(values.reduce((sum,value)=>sum+value*value,0));
const read3=(values:ArrayLike<number>,offset:number):Vec3=>[values[offset],values[offset+1],values[offset+2]];

/** Solve a small positive definite 3x3 system, with finite pivot checks. */
function solve3(matrix:number[][],rhs:number[]):number[]{
  const work=matrix.map((row,i)=>[...row,rhs[i]]);
  for(let column=0;column<3;column++){
    let pivot=column;
    for(let row=column+1;row<3;row++)if(Math.abs(work[row][column])>Math.abs(work[pivot][column]))pivot=row;
    [work[column],work[pivot]]=[work[pivot],work[column]];
    const diagonal=work[column][column];
    if(!Number.isFinite(diagonal)||Math.abs(diagonal)<1e-12)throw new Error('Singular synthetic IK system');
    for(let j=column;j<4;j++)work[column][j]/=diagonal;
    for(let row=0;row<3;row++)if(row!==column){const scale=work[row][column];for(let j=column;j<4;j++)work[row][j]-=scale*work[column][j]}
  }
  return work.map(row=>row[3]);
}

export class BrowserPhysics {
  private readonly model:MjModel;
  private readonly data:MjData;
  private readonly initialQ:number[];
  private readonly initialCtrl:number[];
  private readonly bodyIds=new Map<string,number>();
  private readonly robotBodies=new Set<number>();
  private readonly jointIds=new Map<string,number>();
  private readonly actuatorIds=new Map<string,number>();
  private readonly siteIds=new Map<string,number>();
  private readonly jointNames:string[]=[];
  private readonly timestep:number;
  private mode:'idle'|'joint_demo'|'reach_demo'='idle';
  private paused=false;
  private modeStarted=0;
  private lastClock=performance.now();
  private lastContacts:Contact[]=[];
  private stopReason:string|null=null;
  private reachPlan:ReachPlan|null=null;
  private stepCount=0;
  private accumulator=0;
  private disposed=false;

  constructor(private readonly engine:MainModule,xml:string,private readonly descriptors:ReferenceDescriptors){
    if(descriptors.hardware_model_verified!==false||!Array.isArray(descriptors.body_specs))throw new Error('Expected unverified reference descriptors');
    this.model=engine.MjModel.from_xml_string(xml);
    try{this.data=new engine.MjData(this.model)}catch(error){this.model.delete();throw error}
    const option=this.model.opt;this.timestep=option.timestep;option.delete();
    if(this.model.nq!==25||this.model.nu!==25){this.data.delete();this.model.delete();throw new Error('Unexpected reference model topology')}
    for(let i=0;i<this.model.njnt;i++){
      const name=engine.mj_id2name(this.model,engine.mjtObj.mjOBJ_JOINT.value,i);
      this.jointNames.push(name);this.jointIds.set(name,i);
    }
    for(let i=0;i<this.model.nu;i++)this.actuatorIds.set(engine.mj_id2name(this.model,engine.mjtObj.mjOBJ_ACTUATOR.value,i),i);
    for(const body of descriptors.body_specs){
      const id=engine.mj_name2id(this.model,engine.mjtObj.mjOBJ_BODY.value,body.name);
      if(id<0){this.dispose();throw new Error(`Reference body missing: ${body.name}`)}
      this.bodyIds.set(body.name,id);this.robotBodies.add(id);
      if(body.joint)this.data.qpos[this.qindex(body.joint)]=body.initial_q??0;
    }
    for(const side of ['left','right'])this.siteIds.set(side,engine.mj_name2id(this.model,engine.mjtObj.mjOBJ_SITE.value,`${side}_ee`));
    for(let i=0;i<this.model.nu;i++)this.data.ctrl[i]=this.data.qpos[this.model.jnt_qposadr[this.model.actuator_trnid[i*2]]];
    engine.mj_forward(this.model,this.data);
    this.initialQ=Array.from(this.data.qpos);this.initialCtrl=Array.from(this.data.ctrl);
    this.lastClock=performance.now();
  }

  private assertOpen(){if(this.disposed)throw new Error('Browser physics has been disposed')}
  private qindex(name:string){const id=this.jointIds.get(name);if(id===undefined)throw new Error(`Unknown synthetic joint ${name}`);return this.model.jnt_qposadr[id] as number}
  private setTarget(name:string,value:number){const actuator=this.actuatorIds.get(`ctrl_${name}`);if(actuator===undefined)throw new Error(`Unknown actuator ${name}`);this.data.ctrl[actuator]=clamp(value,this.model.actuator_ctrlrange[actuator*2],this.model.actuator_ctrlrange[actuator*2+1])}
  private finite(data=this.data){return Array.from(data.qpos as ArrayLike<number>).every(Number.isFinite)&&Array.from(data.qvel as ArrayLike<number>).every(Number.isFinite)}
  private contacts(data=this.data):Contact[]{
    if(!data.ncon)return [];
    const found:Contact[]=[];const contacts=data.contact;
    try{
      for(let i=0;i<data.ncon;i++){
        const contact=contacts.get(i);if(!contact)continue;
        try{
          const a=contact.geom1,b=contact.geom2;
          const robotA=this.robotBodies.has(this.model.geom_bodyid[a]),robotB=this.robotBodies.has(this.model.geom_bodyid[b]);
          if((robotA||robotB)&&contact.dist<-.0001)found.push({geoms:[this.engine.mj_id2name(this.model,this.engine.mjtObj.mjOBJ_GEOM.value,a),this.engine.mj_id2name(this.model,this.engine.mjtObj.mjOBJ_GEOM.value,b)],distance_m:contact.dist,self_collision:robotA&&robotB});
        }finally{contact.delete()}
      }
    }finally{contacts.delete()}
    return found;
  }
  private hold(){for(let i=0;i<this.model.nu;i++)this.data.ctrl[i]=this.data.qpos[this.model.jnt_qposadr[this.model.actuator_trnid[i*2]]];this.data.qvel.fill(0)}

  private jointDemo(elapsed:number){
    const cycle=elapsed*.65;
    this.setTarget('base_x',.025*Math.sin(cycle*.65));this.setTarget('base_y',.014*Math.sin(cycle*.45));this.setTarget('base_yaw',.07*Math.sin(cycle*.55));
    this.setTarget('left_wheel_joint',.5*Math.sin(cycle*.65)+.18*Math.sin(cycle*.55));this.setTarget('right_wheel_joint',.5*Math.sin(cycle*.65)-.18*Math.sin(cycle*.55));
    for(const [side,sign,phase]of [['left',1,0],['right',-1,1.1]] as const){
      this.setTarget(`${side}_lift`,.055*Math.sin(cycle*.55+phase));
      INITIAL_ARM_Q.forEach((initial,index)=>{
        let value=initial+[.08,.18,.15,.20,.17,.15,.22][index]*Math.sin(cycle+phase+(index+1)*.25);
        if(index===0)value=sign*(.11+.07*Math.sin(cycle+phase));this.setTarget(`${side}_joint_${index+1}`,value);
      });
      for(const finger of [-1,1])this.setTarget(`${side}_gripper_${finger}`,-finger*(.16+.12*Math.sin(cycle*1.5+phase)));
    }
  }

  /** Computed WASM Jacobian IK and collision samples; never a replayed goal pose. */
  solveReach(target:Vec3,side:'left'|'right'='left',baseX=.18):ReachPlan{
    this.assertOpen();
    if(!Array.isArray(target)||target.length!==3||!target.every(Number.isFinite)||!['left','right'].includes(side)||!Number.isFinite(baseX)||baseX<-.1||baseX>.25)throw new Error('Invalid bounded synthetic reach request');
    const candidate=new this.engine.MjData(this.model);
    const sampled=new this.engine.MjData(this.model);
    const jacBuffer=new this.engine.DoubleBuffer(this.model.nv*3);
    try{
      candidate.qpos.set(this.data.qpos);candidate.qpos[this.qindex('base_x')]=baseX;
      const jointIndices=INITIAL_ARM_Q.map((_,i)=>this.jointIds.get(`${side}_joint_${i+1}`)!);
      const qindices=jointIndices.map(index=>this.model.jnt_qposadr[index] as number);
      const dofs=jointIndices.map(index=>this.model.jnt_dofadr[index] as number);
      const site=this.siteIds.get(side)!;
      let residual=Infinity;
      for(let iteration=0;iteration<240;iteration++){
        this.engine.mj_forward(this.model,candidate);
        const point=read3(candidate.site_xpos,site*3),error=target.map((value,index)=>value-point[index]);residual=norm(error);
        if(residual<.006)break;
        this.engine.mj_jacSite(this.model,candidate,jacBuffer,null,site);
        const view=jacBuffer.GetView() as Float64Array;
        const jac=[0,1,2].map(row=>dofs.map(column=>view[row*this.model.nv+column]));
        const system=[0,1,2].map(row=>[0,1,2].map(column=>jac[row].reduce((sum,value,k)=>sum+value*jac[column][k],row===column?.003:0)));
        const solved=solve3(system,error);
        qindices.forEach((index,k)=>{const delta=jac.reduce((sum,row,r)=>sum+row[k]*solved[r],0);candidate.qpos[index]=clamp(candidate.qpos[index]+clamp(delta,-.065,.065),-2.65,2.65)});
      }
      this.engine.mj_forward(this.model,candidate);residual=norm(target.map((value,index)=>value-candidate.site_xpos[site*3+index]));
      let collisions:Contact[]=[];let sampleCount=0;
      for(let i=0;i<60;i++){
        const ratio=i/59;for(let q=0;q<this.model.nq;q++)sampled.qpos[q]=(1-ratio)*this.data.qpos[q]+ratio*candidate.qpos[q];
        this.engine.mj_forward(this.model,sampled);sampleCount++;collisions=this.contacts(sampled);if(collisions.length)break;
      }
      return{target:[...target],side,residual_m:residual,reachable:residual<.015,collision_free_samples:collisions.length===0,sample_count:sampleCount,contacts:collisions,target_qpos:Array.from(candidate.qpos)};
    }finally{jacBuffer.delete();sampled.delete();candidate.delete()}
  }

  command(action:PhysicsCommand|string):BrowserPhysicsState{
    this.assertOpen();
    if(action==='reset'){
      this.engine.mj_resetData(this.model,this.data);this.data.qpos.set(this.initialQ);this.data.ctrl.set(this.initialCtrl);this.engine.mj_forward(this.model,this.data);
      this.mode='idle';this.paused=false;this.reachPlan=null;this.stopReason=null;this.lastContacts=[];this.stepCount=0;this.accumulator=0;
    }else if(action==='pause'){this.paused=!this.paused}
    else if(action==='joint_demo'){this.mode='joint_demo';this.paused=false;this.modeStarted=this.data.time;this.stopReason=null;this.reachPlan=null}
    else if(action==='reach_demo'){
      const plan=this.solveReach([.22,-.53,.96]);this.reachPlan=plan;
      if(!plan.reachable||!plan.collision_free_samples){this.stopReason='Reach rejected by endpoint IK or sampled collision gate';this.paused=true}
      else{this.reachPlan={...plan,start_qpos:Array.from(this.data.qpos),duration_s:4};this.data.mocap_pos.set(plan.target);this.mode='reach_demo';this.paused=false;this.modeStarted=this.data.time;this.stopReason=null}
    }else throw new Error('Allowed commands: joint_demo, reach_demo, pause, reset');
    this.lastClock=performance.now();return this.snapshot();
  }

  /** Explicit bounded stepping; browser calls state() to advance elapsed time. */
  advance(seconds:number):BrowserPhysicsState{
    this.assertOpen();if(!Number.isFinite(seconds)||seconds<0||seconds>2)throw new Error('Advance must be finite and between zero and two seconds');
    if(this.paused)return this.snapshot();
    this.accumulator+=seconds;const count=Math.min(1000,Math.floor((this.accumulator+1e-10)/this.timestep));this.accumulator-=count*this.timestep;
    for(let step=0;step<count;step++){
      const elapsed=this.data.time-this.modeStarted;
      if(this.mode==='joint_demo')this.jointDemo(elapsed);
      else if(this.mode==='reach_demo'&&this.reachPlan?.start_qpos){
        let ratio=clamp(elapsed/this.reachPlan.duration_s!,0,1);ratio=ratio*ratio*(3-2*ratio);
        for(let i=0;i<this.model.nu;i++){const q=this.model.jnt_qposadr[this.model.actuator_trnid[i*2]];this.data.ctrl[i]=(1-ratio)*this.reachPlan.start_qpos[q]+ratio*this.reachPlan.target_qpos[q]}
      }
      this.engine.mj_step(this.model,this.data);this.stepCount++;
      const contacts=this.contacts();
      if(contacts.length||!this.finite()){this.lastContacts=contacts;this.stopReason=contacts.length?'Synthetic contact stop':'Nonfinite physics state';this.hold();this.paused=true;break}
    }
    this.engine.mj_forward(this.model,this.data);return this.snapshot();
  }

  state():BrowserPhysicsState{
    this.assertOpen();const timestamp=performance.now(),elapsed=clamp((timestamp-this.lastClock)/1000,0,.05);this.lastClock=timestamp;return this.advance(elapsed);
  }
  private snapshot():BrowserPhysicsState{
    const bodies:BrowserPhysicsState['bodies']={};
    for(const [name,id]of this.bodyIds){const q=this.data.xquat;bodies[name]={position:read3(this.data.xpos,id*3),quaternion:[q[id*4],q[id*4+1],q[id*4+2],q[id*4+3]]}}
    const joints:Record<string,number>={};for(const name of this.jointNames)joints[name]=this.data.qpos[this.qindex(name)];
    const endEffectors:Record<string,Vec3>={};for(const [side,id]of this.siteIds)endEffectors[side]=read3(this.data.site_xpos,id*3);
    const metrics:BrowserPhysicsState['metrics']={physics_steps:this.stepCount,finite_dynamics:this.finite(),contacts:this.lastContacts,stop_reason:this.stopReason,grasp_success:null,object_attached:false};
    if(this.reachPlan){const distance=norm(endEffectors[this.reachPlan.side].map((value,i)=>value-this.reachPlan!.target[i]));metrics.reach={target:this.reachPlan.target,ik_residual_m:this.reachPlan.residual_m,actual_endpoint_error_m:distance,endpoint_reached:distance<.02,sampled_collision_gate_passed:this.reachPlan.collision_free_samples,samples:this.reachPlan.sample_count}}
    return{bodies,joints,mode:this.mode,paused:this.paused,simulation_time:this.data.time,target:{position:read3(this.data.mocap_pos,0)},end_effectors:endEffectors,metrics,model_hash:this.descriptors.model_hash,hardware_model_verified:false,authorizes_hardware:false,source:'Actual MuJoCo WebAssembly dynamics on reference-informed unverified surrogate',engine:'mujoco-wasm',engine_version:this.engine.mj_versionString()};
  }
  dispose(){if(this.disposed)return;this.disposed=true;this.data.delete();this.model.delete()}
}
