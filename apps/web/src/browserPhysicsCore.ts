/** Actual MuJoCo WebAssembly dynamics for the public static demonstration.
 * Same estimated model and bounded controllers as sim/reference_runtime.py.
 * No robot, hospital API, uploaded media, or replayed pose animation is involved.
 */
import type {MainModule, MjData, MjModel} from '@mujoco/mujoco';

export type Vec3=[number,number,number];
export type Quat=[number,number,number,number];
export type PhysicsCommand='joint_demo'|'reach_demo'|'pickup_demo'|'release_phone'|'lift_demo'|'pause'|'reset';
export type ReferenceDescriptors={model_hash:string;body_specs:{name:string;joint?:string;joint_type?:string;dynamic_object?:boolean;initial_q?:number}[];hardware_model_verified:false};
type Contact={geoms:[string,string];distance_m:number;self_collision:boolean};
type ReachPlan={target:Vec3;side:'left'|'right';residual_m:number;reachable:boolean;collision_free_samples:boolean;sample_count:number;contacts:Contact[];target_qpos:number[];start_qpos?:number[];duration_s?:number};
type PosePlan={target_qpos:number[];position_error_m:number;orientation_error_rad:number};
type Stage={name:string;target_qpos:number[];duration_s:number};
export type PickupMetrics={stage:string;status:string;success:boolean;ever_succeeded:boolean;released:boolean;initial_phone_height_m:number;phone_height_m:number;height_gain_m:number;bilateral_contact:boolean;finger_contacts:string[];normal_forces_n:Record<string,number>;bilateral_hold_s:number;ik_errors:Record<string,{position_error_m:number;orientation_error_rad:number}>;collision_samples:number;sampled_collision_gate_passed:boolean;attachment_constraints:0};
export type LiftMetrics={stage:string;complete:boolean;positions_m:Record<'left'|'right',number>;min_positions_m:Record<'left'|'right',number>;max_positions_m:Record<'left'|'right',number>;travel_m:Record<'left'|'right',number>;hand_height_m:Record<'left'|'right',number>;min_hand_height_m:Record<'left'|'right',number>;max_hand_height_m:Record<'left'|'right',number>;estimated_range_m:[number,number]};
export type BrowserPhysicsState={
  bodies:Record<string,{position:Vec3;quaternion:Quat}>;
  joints:Record<string,number>;
  mode:'idle'|'joint_demo'|'reach_demo'|'pickup_demo'|'release_phone'|'lift_demo';paused:boolean;simulation_time:number;
  target:{position:Vec3};end_effectors:Record<string,Vec3>;
  metrics:{physics_steps:number;finite_dynamics:boolean;contacts:Contact[];stop_reason:string|null;grasp_success:null|boolean;object_attached:false;pickup?:PickupMetrics;lift?:LiftMetrics;reach?:{target:Vec3;ik_residual_m:number;actual_endpoint_error_m:number;endpoint_reached:boolean;sampled_collision_gate_passed:boolean;samples:number}};
  model_hash:string;hardware_model_verified:false;authorizes_hardware:false;source:string;engine:'mujoco-wasm';engine_version:string;
};

const INITIAL_ARM_Q=[0,-.30,0,-1.50,0,-.15,0];
const clamp=(value:number,minimum:number,maximum:number)=>Math.max(minimum,Math.min(maximum,value));
const norm=(values:number[])=>Math.sqrt(values.reduce((sum,value)=>sum+value*value,0));
const read3=(values:ArrayLike<number>,offset:number):Vec3=>[values[offset],values[offset+1],values[offset+2]];

/** Solve a small damped IK system, with finite pivot checks. */
function solveLinear(matrix:number[][],rhs:number[]):number[]{
  const work=matrix.map((row,i)=>[...row,rhs[i]]);
  const size=rhs.length;
  for(let column=0;column<size;column++){
    let pivot=column;
    for(let row=column+1;row<size;row++)if(Math.abs(work[row][column])>Math.abs(work[pivot][column]))pivot=row;
    [work[column],work[pivot]]=[work[pivot],work[column]];
    const diagonal=work[column][column];
    if(!Number.isFinite(diagonal)||Math.abs(diagonal)<1e-12)throw new Error('Singular synthetic IK system');
    for(let j=column;j<=size;j++)work[column][j]/=diagonal;
    for(let row=0;row<size;row++)if(row!==column){const scale=work[row][column];for(let j=column;j<=size;j++)work[row][j]-=scale*work[column][j]}
  }
  return work.map(row=>row[size]);
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
  private mode:BrowserPhysicsState['mode']='idle';
  private paused=false;
  private modeStarted=0;
  private lastClock=performance.now();
  private lastContacts:Contact[]=[];
  private stopReason:string|null=null;
  private reachPlan:ReachPlan|null=null;
  private stepCount=0;
  private accumulator=0;
  private disposed=false;
  private readonly actuatedQ:number[];
  private readonly actuatedDofs:number[];
  private stages:Stage[]=[];
  private stageIndex=0;
  private stageStarted=0;
  private stageStartCtrl:number[]=[];
  private pickup:PickupMetrics|null=null;
  private liftDemo:LiftMetrics|null=null;

  constructor(private readonly engine:MainModule,xml:string,private readonly descriptors:ReferenceDescriptors){
    if(descriptors.hardware_model_verified!==false||!Array.isArray(descriptors.body_specs))throw new Error('Expected unverified reference descriptors');
    this.model=engine.MjModel.from_xml_string(xml);
    try{this.data=new engine.MjData(this.model)}catch(error){this.model.delete();throw error}
    const option=this.model.opt;this.timestep=option.timestep;option.delete();
    if(this.model.nq!==32||this.model.nu!==25){this.data.delete();this.model.delete();throw new Error('Expected 25 robot actuators and one free phone body')}
    this.actuatedQ=Array.from({length:this.model.nu},(_,i)=>this.model.jnt_qposadr[this.model.actuator_trnid[i*2]]);
    this.actuatedDofs=Array.from({length:this.model.nu},(_,i)=>this.model.jnt_dofadr[this.model.actuator_trnid[i*2]]);
    for(let i=0;i<this.model.njnt;i++){
      if(this.model.jnt_type[i]===engine.mjtJoint.mjJNT_FREE.value)continue;
      const name=engine.mj_id2name(this.model,engine.mjtObj.mjOBJ_JOINT.value,i);
      this.jointNames.push(name);this.jointIds.set(name,i);
    }
    for(let i=0;i<this.model.nu;i++)this.actuatorIds.set(engine.mj_id2name(this.model,engine.mjtObj.mjOBJ_ACTUATOR.value,i),i);
    for(const body of descriptors.body_specs){
      const id=engine.mj_name2id(this.model,engine.mjtObj.mjOBJ_BODY.value,body.name);
      if(id<0){this.dispose();throw new Error(`Reference body missing: ${body.name}`)}
      this.bodyIds.set(body.name,id);if(!body.dynamic_object)this.robotBodies.add(id);
      if(body.joint&&body.joint_type!=='free')this.data.qpos[this.qindex(body.joint)]=body.initial_q??0;
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
  private contacts(data=this.data,allowPhoneGrasp=this.mode==='pickup_demo'||this.mode==='release_phone'):Contact[]{
    if(!data.ncon)return [];
    const found:Contact[]=[];const contacts=data.contact;
    try{
      for(let i=0;i<data.ncon;i++){
        const contact=contacts.get(i);if(!contact)continue;
        try{
          const a=contact.geom1,b=contact.geom2;
          const names:[string,string]=[this.engine.mj_id2name(this.model,this.engine.mjtObj.mjOBJ_GEOM.value,a),this.engine.mj_id2name(this.model,this.engine.mjtObj.mjOBJ_GEOM.value,b)];
          if(allowPhoneGrasp&&names.includes('phone_geom')&&names.some(name=>name==='left_finger_-1_geom'||name==='left_finger_1_geom'))continue;
          const robotA=this.robotBodies.has(this.model.geom_bodyid[a]),robotB=this.robotBodies.has(this.model.geom_bodyid[b]);
          if((robotA||robotB)&&contact.dist<-.0001)found.push({geoms:names,distance_m:contact.dist,self_collision:robotA&&robotB});
        }finally{contact.delete()}
      }
    }finally{contacts.delete()}
    return found;
  }
  private hold(){for(let i=0;i<this.model.nu;i++)this.data.ctrl[i]=this.data.qpos[this.actuatedQ[i]];for(const dof of this.actuatedDofs)this.data.qvel[dof]=0}

  private jointDemo(elapsed:number){
    const cycle=elapsed*.65;
    this.setTarget('base_x',.025*Math.sin(cycle*.65));this.setTarget('base_y',.014*Math.sin(cycle*.45));this.setTarget('base_yaw',.07*Math.sin(cycle*.55));
    const travel=.025*Math.sin(cycle*.65),yaw=.07*Math.sin(cycle*.55);
    this.setTarget('left_wheel_joint',(travel-.20*yaw)/.13);this.setTarget('right_wheel_joint',(travel+.20*yaw)/.13);
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
        const solved=solveLinear(system,error);
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

  private rotationError(target:number[][],current:number[][]):number[]{
    const relative=target.map(row=>current.map(column=>row.reduce((sum,value,i)=>sum+value*column[i],0)));
    const angle=Math.acos(clamp((relative[0][0]+relative[1][1]+relative[2][2]-1)/2,-1,1));
    const vector=[relative[2][1]-relative[1][2],relative[0][2]-relative[2][0],relative[1][0]-relative[0][1]];
    if(angle<1e-7)return vector.map(value=>value/2);
    if(Math.abs(Math.sin(angle))<1e-6){
      const quaternion=new this.engine.DoubleBuffer(4);
      try{this.engine.mju_mat2Quat(quaternion,relative.flat());const axis=Array.from(quaternion.GetView() as Float64Array).slice(1);return axis.map(value=>angle*value/Math.max(norm(axis),1e-9))}finally{quaternion.delete()}
    }
    return vector.map(value=>value*angle/(2*Math.sin(angle)));
  }

  /** Full six-dimensional grasp pose IK using live MuJoCo position/rotation Jacobians. */
  solvePose(initial:number[],target:Vec3,baseX=.78,baseY=0,lift=0,side:'left'|'right'='left'):PosePlan{
    this.assertOpen();
    const candidate=new this.engine.MjData(this.model);
    const jacp=new this.engine.DoubleBuffer(this.model.nv*3),jacr=new this.engine.DoubleBuffer(this.model.nv*3);
    const rotation=[[0,-1,0],[1,0,0],[0,0,1]];
    try{
      candidate.qpos.set(initial);candidate.qpos[this.qindex('base_x')]=baseX;candidate.qpos[this.qindex('base_y')]=baseY;candidate.qpos[this.qindex(`${side}_lift`)]=lift;
      const ids=INITIAL_ARM_Q.map((_,i)=>this.jointIds.get(`${side}_joint_${i+1}`)!);
      const qindices=ids.map(id=>this.model.jnt_qposadr[id] as number),dofs=ids.map(id=>this.model.jnt_dofadr[id] as number);
      const site=this.engine.mj_name2id(this.model,this.engine.mjtObj.mjOBJ_SITE.value,`${side}_grasp_center`);
      const error=()=>({position:target.map((value,i)=>value-candidate.site_xpos[site*3+i]),rotation:this.rotationError(rotation,[0,1,2].map(row=>[0,1,2].map(column=>candidate.site_xmat[site*9+row*3+column])))});
      for(let iteration=0;iteration<600;iteration++){
        this.engine.mj_forward(this.model,candidate);
        const residual=error();if(norm(residual.position)<.0003&&norm(residual.rotation)<.003)break;
        this.engine.mj_jacSite(this.model,candidate,jacp,jacr,site);
        const position=jacp.GetView() as Float64Array,angular=jacr.GetView() as Float64Array;
        const jac=[0,1,2,3,4,5].map(row=>dofs.map(column=>row<3?position[row*this.model.nv+column]:.25*angular[(row-3)*this.model.nv+column]));
        const rhs=[...residual.position,...residual.rotation.map(value=>value*.25)];
        const system=jac.map((row,i)=>jac.map((other,j)=>row.reduce((sum,value,k)=>sum+value*other[k],i===j?.0005:0)));
        const solved=solveLinear(system,rhs);
        qindices.forEach((q,k)=>{const delta=jac.reduce((sum,row,i)=>sum+row[k]*solved[i],0);candidate.qpos[q]=clamp(candidate.qpos[q]+clamp(delta,-.08,.08),-2.65,2.65)});
      }
      this.engine.mj_forward(this.model,candidate);const residual=error();
      return{target_qpos:Array.from(candidate.qpos),position_error_m:norm(residual.position),orientation_error_rad:norm(residual.rotation)};
    }finally{jacp.delete();jacr.delete();candidate.delete()}
  }

  private pickupStages():{stages:Stage[];errors:PickupMetrics['ik_errors']}{
    const park=[...this.initialQ];park[this.qindex('right_joint_1')]=-.70;
    for(const finger of [-1,1])park[this.qindex(`left_gripper_${finger}`)]=finger*.60;
    const drive=[...park];drive[this.qindex('base_x')]=.78;
    for(const side of ['left','right'])drive[this.qindex(`${side}_wheel_joint`)]=.78/.13;
    const hover=this.solvePose(drive,[.63,-.72,.96]);
    const grasp=this.solvePose(hover.target_qpos,[.63,-.72,.8135]);
    const closed=[...grasp.target_qpos];for(const finger of [-1,1])closed[this.qindex(`left_gripper_${finger}`)]=-finger*.25;
    const lifted=this.solvePose(closed,[.63,-.72,1.05]);
    const errors=Object.fromEntries(Object.entries({hover,grasp,lift:lifted}).map(([name,plan])=>[name,{position_error_m:plan.position_error_m,orientation_error_rad:plan.orientation_error_rad}]));
    return{stages:[{name:'park',target_qpos:park,duration_s:2},{name:'approach_base',target_qpos:drive,duration_s:4},{name:'hover',target_qpos:hover.target_qpos,duration_s:3},{name:'descend',target_qpos:grasp.target_qpos,duration_s:3},{name:'close',target_qpos:closed,duration_s:1.5},{name:'lift',target_qpos:lifted.target_qpos,duration_s:4},{name:'hold',target_qpos:lifted.target_qpos,duration_s:2}],errors};
  }

  private requireFixtureStart(){
    const phone=read3(this.data.xpos,this.bodyIds.get('phone')!*3);
    if(Math.max(...this.actuatedQ.map(q=>Math.abs(this.data.qpos[q]-this.initialQ[q])))>.025||Math.hypot(phone[0]-.63,phone[1]+.72)>.01||Math.abs(phone[2]-.8135)>.015)throw new Error('Reset the scene before starting this fixture demonstration');
  }

  private startStages(stages:Stage[],allowPhoneGrasp=false):number{
    const sampled=new this.engine.MjData(this.model);let previous=Array.from(this.data.qpos as Float64Array),checked=0;
    try{
      for(const stage of stages){
        // Loaded finger targets compress against the phone; they are not a
        // prediction of the contact-constrained pose. Preflight free-space only.
        if(allowPhoneGrasp&&['close','lift','hold'].includes(stage.name))break;
        for(let sample=0;sample<60;sample++){
          const ratio=sample/59;sampled.qpos.set(this.data.qpos);
          for(const q of this.actuatedQ)sampled.qpos[q]=(1-ratio)*previous[q]+ratio*stage.target_qpos[q];
          this.engine.mj_forward(this.model,sampled);checked++;
          const collisions=this.contacts(sampled,allowPhoneGrasp);
          if(collisions.length)throw new Error(`Fixture path rejected during ${stage.name}: ${JSON.stringify(collisions)}`);
        }
        previous=stage.target_qpos;
      }
      this.stages=stages;this.stageIndex=0;this.stageStarted=this.data.time;this.stageStartCtrl=Array.from(this.data.ctrl);return checked;
    }finally{sampled.delete()}
  }

  private fingerContacts():{touching:string[];forces:Record<string,number>}{
    const touching=new Set<string>(),forces:Record<string,number>={'left_finger_-1':0,'left_finger_1':0};
    if(!this.data.ncon)return{touching:[],forces};
    const contacts=this.data.contact,wrench=new this.engine.DoubleBuffer(6);
    try{
      for(let i=0;i<this.data.ncon;i++){
        const contact=contacts.get(i);if(!contact)continue;
        try{
          const names=[contact.geom1,contact.geom2].map(id=>this.engine.mj_id2name(this.model,this.engine.mjtObj.mjOBJ_GEOM.value,id));
          if(!names.includes('phone_geom'))continue;
          for(const finger of Object.keys(forces))if(names.includes(`${finger}_geom`)&&contact.dist<.0001){
            this.engine.mj_contactForce(this.model,this.data,i,wrench);const normal=(wrench.GetView() as Float64Array)[0];
            if(normal>.01)touching.add(finger);forces[finger]+=Math.max(0,normal);
          }
        }finally{contact.delete()}
      }
      return{touching:[...touching].sort(),forces};
    }finally{wrench.delete();contacts.delete()}
  }

  private stagedControl(){
    if(!this.stages.length)return;
    let stage=this.stages[this.stageIndex],elapsed=this.data.time-this.stageStarted;
    if(elapsed+1e-9>=stage.duration_s&&this.stageIndex+1<this.stages.length){
      if(stage.name==='close'&&this.fingerContacts().touching.length!==2){this.stopReason='Pickup stopped: bilateral finger contact not established';this.paused=true;if(this.pickup)this.pickup.status='failed';return}
      this.stageIndex++;this.stageStarted=this.data.time;
      // Preserve commanded squeeze across stage boundaries; measured finger
      // qpos would remove the spring error and drop a frictional grasp.
      this.stageStartCtrl=Array.from(this.data.ctrl);stage=this.stages[this.stageIndex];elapsed=0;
    }
    let ratio=clamp((elapsed+this.timestep)/stage.duration_s,0,1);ratio=ratio*ratio*(3-2*ratio);
    for(let i=0;i<this.model.nu;i++)this.data.ctrl[i]=(1-ratio)*this.stageStartCtrl[i]+ratio*stage.target_qpos[this.actuatedQ[i]];
  }

  private measureFixture(){
    if(this.pickup){
      const phoneZ=this.data.xpos[this.bodyIds.get('phone')!*3+2],{touching,forces}=this.fingerContacts();
      Object.assign(this.pickup,{stage:this.stages[this.stageIndex].name,phone_height_m:phoneZ,height_gain_m:phoneZ-this.pickup.initial_phone_height_m,finger_contacts:touching,normal_forces_n:forces,bilateral_contact:touching.length===2});
      if(this.mode==='pickup_demo'){
        if(this.pickup.height_gain_m>.15&&touching.length===2){this.pickup.bilateral_hold_s+=this.timestep;if(this.pickup.bilateral_hold_s>=2){this.pickup.success=true;this.pickup.ever_succeeded=true;this.pickup.status='holding'}}
        else{this.pickup.bilateral_hold_s=0;if(this.pickup.success){this.pickup.success=false;this.pickup.status='lost_grasp'}}
      }else if(this.mode==='release_phone'){this.pickup.success=false;this.pickup.released=!touching.length&&this.pickup.height_gain_m<.03;this.pickup.status=this.pickup.released?'released':'releasing'}
    }
    if(this.liftDemo&&this.mode==='lift_demo'){
      this.liftDemo.stage=this.stages[this.stageIndex].name;
      this.liftDemo.complete=this.stageIndex===this.stages.length-1&&this.data.time-this.stageStarted>=this.stages.at(-1)!.duration_s+.5;
      for(const side of ['left','right'] as const){const value=this.data.qpos[this.qindex(`${side}_lift`)];this.liftDemo.positions_m[side]=value;this.liftDemo.min_positions_m[side]=Math.min(value,this.liftDemo.min_positions_m[side]);this.liftDemo.max_positions_m[side]=Math.max(value,this.liftDemo.max_positions_m[side]);this.liftDemo.travel_m[side]=this.liftDemo.max_positions_m[side]-this.liftDemo.min_positions_m[side];const height=this.data.site_xpos[this.siteIds.get(side)!*3+2];this.liftDemo.hand_height_m[side]=height;this.liftDemo.min_hand_height_m[side]=Math.min(height,this.liftDemo.min_hand_height_m[side]);this.liftDemo.max_hand_height_m[side]=Math.max(height,this.liftDemo.max_hand_height_m[side])}
    }
  }

  command(action:PhysicsCommand|string):BrowserPhysicsState{
    this.assertOpen();
    if(this.stopReason&&action!=='reset')throw new Error('Reset the scene before continuing after a simulation stop');
    if(['joint_demo','reach_demo','lift_demo','pickup_demo'].includes(action)&&['pickup_demo','release_phone'].includes(this.mode))throw new Error('Release the phone and reset the scene before another demonstration');
    if(action==='reset'){
      this.engine.mj_resetData(this.model,this.data);this.data.qpos.set(this.initialQ);this.data.ctrl.set(this.initialCtrl);this.engine.mj_forward(this.model,this.data);
      this.mode='idle';this.paused=false;this.reachPlan=null;this.stopReason=null;this.lastContacts=[];this.stepCount=0;this.accumulator=0;
      this.stages=[];this.pickup=null;this.liftDemo=null;this.stageIndex=0;this.stageStarted=0;
    }else if(action==='pause'){this.paused=!this.paused}
    else if(action==='joint_demo'){this.mode='joint_demo';this.paused=false;this.modeStarted=this.data.time;this.stopReason=null;this.reachPlan=null;this.stages=[];this.liftDemo=null}
    else if(action==='pickup_demo'||action==='lift_demo'){
      this.requireFixtureStart();
      if(action==='pickup_demo'){
        const {stages,errors}=this.pickupStages();if(Object.values(errors).some(error=>error.position_error_m>.002||error.orientation_error_rad>.01))throw new Error('Pickup rejected by six-dimensional pose IK gate');
        const count=this.startStages(stages,true),height=this.data.xpos[this.bodyIds.get('phone')!*3+2];
        this.pickup={stage:'park',status:'running',success:false,ever_succeeded:false,released:false,initial_phone_height_m:height,phone_height_m:height,height_gain_m:0,bilateral_contact:false,finger_contacts:[],normal_forces_n:{},bilateral_hold_s:0,ik_errors:errors,collision_samples:count,sampled_collision_gate_passed:true,attachment_constraints:0};
        this.liftDemo=null;this.data.mocap_pos.set([.63,-.72,1.05]);
      }else{
        const folded=[...this.initialQ];for(const [side,sign]of [['left',1],['right',-1]] as const)for(const [joint,value]of [[1,sign*.25],[2,-.8],[4,-.5],[6,-.15]])folded[this.qindex(`${side}_joint_${joint}`)]=value;
        const stages:Stage[]=[{name:'clear_mast',target_qpos:[...folded],duration_s:2}];
        const values:[string,number,number][]=[['lower_stages',-.66,-.66],['raise_left',.18,-.66],['raise_right',.18,.18]];
        for(const [name,left,right]of values){const target=[...folded];target[this.qindex('left_lift')]=left;target[this.qindex('right_lift')]=right;stages.push({name,target_qpos:target,duration_s:5})}
        const high=[...stages[3].target_qpos];for(const side of ['left','right']){high[this.qindex(`${side}_joint_2`)]=-2.1;high[this.qindex(`${side}_joint_4`)]=-.3}
        stages.push({name:'reach_high',target_qpos:high,duration_s:3},{name:'fold_arms',target_qpos:[...stages[3].target_qpos],duration_s:3},{name:'return_stages',target_qpos:[...this.initialQ],duration_s:3});
        this.startStages(stages);const heights={left:this.data.site_xpos[this.siteIds.get('left')!*3+2],right:this.data.site_xpos[this.siteIds.get('right')!*3+2]};
        this.liftDemo={stage:'clear_mast',complete:false,positions_m:{left:0,right:0},min_positions_m:{left:0,right:0},max_positions_m:{left:0,right:0},travel_m:{left:0,right:0},hand_height_m:{...heights},min_hand_height_m:{...heights},max_hand_height_m:{...heights},estimated_range_m:[-.72,.20]};
      }
      this.mode=action;this.paused=false;this.modeStarted=this.data.time;this.reachPlan=null;this.stopReason=null;
    }else if(action==='release_phone'){
      if(this.mode!=='pickup_demo'||!this.pickup?.success)throw new Error('Release is available after a confirmed bilateral pickup');
      const released=Array.from(this.data.qpos as Float64Array);for(let i=0;i<this.model.nu;i++)released[this.actuatedQ[i]]=this.data.ctrl[i];
      for(const finger of [-1,1])released[this.qindex(`left_gripper_${finger}`)]=finger*.60;
      this.stages=[{name:'release',target_qpos:released,duration_s:1.5}];this.stageIndex=0;this.stageStarted=this.data.time;this.stageStartCtrl=Array.from(this.data.ctrl);this.mode='release_phone';this.paused=false;this.pickup.status='releasing';this.pickup.success=false;this.pickup.bilateral_hold_s=0;
    }
    else if(action==='reach_demo'){
      const plan=this.solveReach([.22,-.53,.96]);this.reachPlan=plan;
      if(!plan.reachable||!plan.collision_free_samples){this.stopReason='Reach rejected by endpoint IK or sampled collision gate';this.paused=true}
      else{this.reachPlan={...plan,start_qpos:Array.from(this.data.qpos),duration_s:4};this.data.mocap_pos.set(plan.target);this.mode='reach_demo';this.paused=false;this.modeStarted=this.data.time;this.stopReason=null}
    }else throw new Error('Allowed commands: joint_demo, reach_demo, pickup_demo, release_phone, lift_demo, pause, reset');
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
      else if(this.mode==='pickup_demo'||this.mode==='release_phone'||this.mode==='lift_demo'){this.stagedControl();if(this.paused)break}
      else if(this.mode==='reach_demo'&&this.reachPlan?.start_qpos){
        let ratio=clamp(elapsed/this.reachPlan.duration_s!,0,1);ratio=ratio*ratio*(3-2*ratio);
        for(let i=0;i<this.model.nu;i++){const q=this.model.jnt_qposadr[this.model.actuator_trnid[i*2]];this.data.ctrl[i]=(1-ratio)*this.reachPlan.start_qpos[q]+ratio*this.reachPlan.target_qpos[q]}
      }
      this.engine.mj_step(this.model,this.data);this.stepCount++;
      this.measureFixture();
      const contacts=this.contacts();
      if(contacts.length||!this.finite()){this.lastContacts=contacts;this.stopReason=contacts.length?'Synthetic contact stop':'Nonfinite physics state';if(this.pickup){this.pickup.success=false;this.pickup.status='stopped';this.pickup.bilateral_hold_s=0}this.hold();this.paused=true;break}
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
    if(this.pickup){metrics.pickup=structuredClone(this.pickup);metrics.grasp_success=this.pickup.success}
    if(this.liftDemo)metrics.lift=structuredClone(this.liftDemo);
    if(this.reachPlan){const distance=norm(endEffectors[this.reachPlan.side].map((value,i)=>value-this.reachPlan!.target[i]));metrics.reach={target:this.reachPlan.target,ik_residual_m:this.reachPlan.residual_m,actual_endpoint_error_m:distance,endpoint_reached:distance<.02,sampled_collision_gate_passed:this.reachPlan.collision_free_samples,samples:this.reachPlan.sample_count}}
    return{bodies,joints,mode:this.mode,paused:this.paused,simulation_time:this.data.time,target:{position:read3(this.data.mocap_pos,0)},end_effectors:endEffectors,metrics,model_hash:this.descriptors.model_hash,hardware_model_verified:false,authorizes_hardware:false,source:'Actual MuJoCo WebAssembly dynamics on reference-informed unverified surrogate',engine:'mujoco-wasm',engine_version:this.engine.mj_versionString()};
  }
  dispose(){if(this.disposed)return;this.disposed=true;this.data.delete();this.model.delete()}
}
