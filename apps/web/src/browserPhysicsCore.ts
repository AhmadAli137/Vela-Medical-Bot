/** Actual MuJoCo WebAssembly dynamics for the public static demonstration.
 * Same estimated model and bounded controllers as sim/reference_runtime.py.
 * No robot, hospital API, uploaded media, or replayed pose animation is involved.
 */
import type {MainModule, MjData, MjModel} from '@mujoco/mujoco';
import {DifferentialDrive,wrapAngle} from './browserDrive';
import type {DriveMetrics,NavigationStage} from './browserDrive';

export type Vec3=[number,number,number];
export type Quat=[number,number,number,number];
export type SharedDemoCommand='bedside_demo'|'greeting_demo'|'phone_return_demo'|'deliver_phone_demo'|'deliver_meal_demo'|'blinds_demo';
export type PhysicsCommand='joint_demo'|'reach_demo'|'pickup_demo'|'release_phone'|'lift_demo'|SharedDemoCommand|'pause'|'pause_for_tracking'|'reset';
export type ReferenceDescriptors={model_hash:string;body_specs:{name:string;joint?:string;joint_type?:string;dynamic_object?:boolean;robot_body?:boolean;initial_q?:number}[];hardware_model_verified:false};
/** Camera-local right/up/back to world, row-major rotation; optical forward is
 * local -Z and up is local +Y. Positions use the scene's Z-up metre coordinates.
 * fovy_deg is the modeled vertical field of view, not hardware calibration. */
export type CameraPose={position:Vec3;rotation:number[];fovy_deg:number;fovy?:number;convention:'mujoco_opengl'};
type Contact={geoms:[string,string];distance_m:number;self_collision:boolean;carried_object_collision?:boolean};
type ReachPlan={target:Vec3;side:'left'|'right';residual_m:number;reachable:boolean;collision_free_samples:boolean;sample_count:number;contacts:Contact[];target_qpos:number[];start_qpos?:number[];duration_s?:number};
type PosePlan={target_qpos:number[];position_error_m:number;orientation_error_rad:number};
type StageGate='bilateral_contact'|'grasp_confirmed'|'phone_supported'|'phone_settled'|'assist_bilateral'|'assist_grasped'|'assist_supported'|'assist_released'|'blinds_open';
type Stage=NavigationStage&{gate_after?:StageGate};
export type DemoDefinition={name:string;description:string;stages:Stage[];outcomes:Record<string,number|number[]>;ik_errors?:PickupMetrics['ik_errors'];object_name?:'phone'|'meal_box';source_position?:number[];support_geom?:string;intentional_contacts?:[string,string][]};
export type DemoTrajectories={schema_version:1;model_hash:string;nq:number;nu:number;actuated_q_indices:number[];position_actuator_indices:number[];base_q_indices:number[];commands:Partial<Record<SharedDemoCommand,DemoDefinition>>};
export type DemoMetrics={command:SharedDemoCommand;name:string;stage:string;stage_index:number;stage_count:number;progress:number;elapsed_s:number;duration_s:number;status:'running'|'complete'|'stopped';complete:boolean;measurements:Record<string,number|string|boolean|number[]|null>;checks:Record<string,boolean>};
type PhoneObservation={phone_position:Vec3;phone_xy_error_m:number;phone_z_error_m:number;phone_speed_m_s:number;phone_angular_speed_rad_s:number;riser_support_force_n:number;hand_clearance_m:number};
export type PickupMetrics={stage:string;status:string;success:boolean;ever_succeeded:boolean;released:boolean;initial_phone_height_m:number;phone_height_m:number;height_gain_m:number;bilateral_contact:boolean;finger_contacts:string[];normal_forces_n:Record<string,number>;bilateral_hold_s:number;ik_errors:Record<string,{position_error_m:number;orientation_error_rad:number}>;collision_samples:number;sampled_collision_gate_passed:boolean;attachment_constraints:0};
export type LiftMetrics={stage:string;complete:boolean;positions_m:Record<'left'|'right',number>;min_positions_m:Record<'left'|'right',number>;max_positions_m:Record<'left'|'right',number>;travel_m:Record<'left'|'right',number>;hand_height_m:Record<'left'|'right',number>;min_hand_height_m:Record<'left'|'right',number>;max_hand_height_m:Record<'left'|'right',number>;estimated_range_m:[number,number]};
export type BrowserPhysicsState={
  bodies:Record<string,{position:Vec3;quaternion:Quat}>;
  joints:Record<string,number>;
  object_joints:Record<string,number>;
  cameras:Record<string,CameraPose>;
  mode:'idle'|'joint_demo'|'reach_demo'|'pickup_demo'|'release_phone'|'lift_demo'|SharedDemoCommand;paused:boolean;simulation_time:number;
  target:{position:Vec3};end_effectors:Record<string,Vec3>;
  metrics:{drive:DriveMetrics;physics_steps:number;finite_dynamics:boolean;contacts:Contact[];stop_reason:string|null;visual_tracking_pause_reason?:string|null;grasp_success:null|boolean;object_attached:false;pickup?:PickupMetrics;lift?:LiftMetrics;demo?:DemoMetrics;reach?:{target:Vec3;ik_residual_m:number;actual_endpoint_error_m:number;endpoint_reached:boolean;sampled_collision_gate_passed:boolean;samples:number}};
  model_hash:string;hardware_model_verified:false;authorizes_hardware:false;source:string;engine:'mujoco-wasm';engine_version:string;
};

const INITIAL_ARM_Q=[0,-.30,0,-1.50,0,-.15,0];
const ASSISTANCE_DEMOS:SharedDemoCommand[]=['deliver_phone_demo','deliver_meal_demo','blinds_demo'];
const SHARED_DEMOS:SharedDemoCommand[]=['bedside_demo','greeting_demo','phone_return_demo',...ASSISTANCE_DEMOS];
const contactKey=(names:string[])=>[...names].sort().join('|');
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
  private readonly objectJointNames:string[]=[];
  private readonly cameraIds=new Map<string,number>();
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
  private readonly robotDofs:number[];
  private readonly drive:DifferentialDrive;
  private readonly controlledQ:number[];
  private stages:Stage[]=[];
  private stageIndex=0;
  private stageStarted=0;
  private stageStartCtrl:number[]=[];
  private pickup:PickupMetrics|null=null;
  private liftDemo:LiftMetrics|null=null;
  private demo:DemoMetrics|null=null;
  private demoDefinition:DemoDefinition|null=null;
  private intentionalContacts=new Set<string>();
  private visualTrackingPauseReason:string|null=null;

  constructor(private readonly engine:MainModule,xml:string,private readonly descriptors:ReferenceDescriptors,private readonly demoTrajectories?:DemoTrajectories){
    if(descriptors.hardware_model_verified!==false||!Array.isArray(descriptors.body_specs))throw new Error('Expected unverified reference descriptors');
    this.model=engine.MjModel.from_xml_string(xml);
    try{this.data=new engine.MjData(this.model)}catch(error){this.model.delete();throw error}
    const option=this.model.opt;this.timestep=option.timestep;option.delete();
    if(this.model.nq!==57||this.model.nu!==22){this.data.delete();this.model.delete();throw new Error('Expected 22 robot actuators, wheel-driven base and reference object dynamics')}
    this.drive=new DifferentialDrive(engine,this.model,this.data);
    this.controlledQ=[...this.drive.positionQ,...this.drive.baseQ];
    this.actuatedQ=Array.from({length:this.model.nu},(_,i)=>this.model.jnt_qposadr[this.model.actuator_trnid[i*2]]);
    this.robotDofs=[...Array.from({length:this.model.nu},(_,i)=>this.model.jnt_dofadr[this.model.actuator_trnid[i*2]]),...['base_x','base_y','base_yaw','base_z'].map(name=>this.model.jnt_dofadr[engine.mj_name2id(this.model,engine.mjtObj.mjOBJ_JOINT.value,name)])];
    const actuatedJoints=new Set(Array.from({length:this.model.nu},(_,i)=>this.model.actuator_trnid[i*2]));
    for(let i=0;i<this.model.njnt;i++){
      if(this.model.jnt_type[i]===engine.mjtJoint.mjJNT_FREE.value)continue;
      const name=engine.mj_id2name(this.model,engine.mjtObj.mjOBJ_JOINT.value,i);
      (actuatedJoints.has(i)||['base_x','base_y','base_yaw','base_z'].includes(name)?this.jointNames:this.objectJointNames).push(name);this.jointIds.set(name,i);
    }
    for(let i=0;i<this.model.nu;i++)this.actuatorIds.set(engine.mj_id2name(this.model,engine.mjtObj.mjOBJ_ACTUATOR.value,i),i);
    for(const body of descriptors.body_specs){
      const id=engine.mj_name2id(this.model,engine.mjtObj.mjOBJ_BODY.value,body.name);
      if(id<0){this.dispose();throw new Error(`Reference body missing: ${body.name}`)}
      this.bodyIds.set(body.name,id);if(body.robot_body??!body.dynamic_object)this.robotBodies.add(id);
      if(body.joint&&body.joint_type!=='free')this.data.qpos[this.qindex(body.joint)]=body.initial_q??0;
    }
    for(const side of ['left','right'])this.siteIds.set(side,engine.mj_name2id(this.model,engine.mjtObj.mjOBJ_SITE.value,`${side}_ee`));
    for(const name of ['head_rgb','head_stereo_right','left_wrist','right_wrist']){const id=engine.mj_name2id(this.model,engine.mjtObj.mjOBJ_CAMERA.value,name);if(id>=0)this.cameraIds.set(name,id)}
    for(const i of this.drive.positionActuators)this.data.ctrl[i]=this.data.qpos[this.actuatedQ[i]];
    engine.mj_forward(this.model,this.data);
    this.initialQ=Array.from(this.data.qpos);this.initialCtrl=Array.from(this.data.ctrl);
    this.lastClock=performance.now();
  }

  private assertOpen(){if(this.disposed)throw new Error('Browser physics has been disposed')}
  private qindex(name:string){const id=this.jointIds.get(name);if(id===undefined)throw new Error(`Unknown synthetic joint ${name}`);return this.model.jnt_qposadr[id] as number}
  private setTarget(name:string,value:number){const actuator=this.actuatorIds.get(`ctrl_${name}`);if(actuator===undefined)throw new Error(`Unknown actuator ${name}`);this.data.ctrl[actuator]=clamp(value,this.model.actuator_ctrlrange[actuator*2],this.model.actuator_ctrlrange[actuator*2+1])}
  private finite(data=this.data){return Array.from(data.qpos as ArrayLike<number>).every(Number.isFinite)&&Array.from(data.qvel as ArrayLike<number>).every(Number.isFinite)}
  private contacts(data=this.data,allowPhoneGrasp=this.mode==='pickup_demo'||this.mode==='release_phone'||this.mode==='phone_return_demo',intentionalContacts=this.intentionalContacts):Contact[]{
    if(!data.ncon)return [];
    const found:Contact[]=[];const contacts=data.contact;
    try{
      for(let i=0;i<data.ncon;i++){
        const contact=contacts.get(i);if(!contact)continue;
        try{
          const a=contact.geom1,b=contact.geom2;
          const names:[string,string]=[this.engine.mj_id2name(this.model,this.engine.mjtObj.mjOBJ_GEOM.value,a),this.engine.mj_id2name(this.model,this.engine.mjtObj.mjOBJ_GEOM.value,b)];
          if(names.includes('floor')&&names.some(name=>name==='left_wheel_geom'||name==='right_wheel_geom'))continue;
          if(intentionalContacts.has(contactKey(names)))continue;
          if(allowPhoneGrasp&&names.includes('phone_geom')&&names.some(name=>name==='left_finger_-1_geom'||name==='left_finger_1_geom'))continue;
          if(ASSISTANCE_DEMOS.includes(this.mode as SharedDemoCommand)&&this.demoDefinition?.object_name){
            const object=this.demoDefinition.object_name,allowedSupports=[this.demoDefinition.support_geom,object==='phone'?'phone_riser':'meal_riser','bedside_tray'];
            if(names.includes(`${object}_geom`)&&!names.some(name=>allowedSupports.includes(name))&&contact.dist<-.0001){found.push({geoms:names,distance_m:contact.dist,self_collision:false,carried_object_collision:true});continue}
          }
          const robotA=this.robotBodies.has(this.model.geom_bodyid[a]),robotB=this.robotBodies.has(this.model.geom_bodyid[b]);
          if((robotA||robotB)&&contact.dist<-.0001)found.push({geoms:names,distance_m:contact.dist,self_collision:robotA&&robotB});
        }finally{contact.delete()}
      }
    }finally{contacts.delete()}
    return found;
  }
  private hold(){for(const i of this.drive.wheelActuators)this.data.ctrl[i]=0;for(const i of this.drive.positionActuators)this.data.ctrl[i]=this.data.qpos[this.actuatedQ[i]]}
  private stop(reason:string,contacts:Contact[]=[]){
    this.stopReason=reason;this.lastContacts=contacts;this.paused=true;
    if(this.pickup){this.pickup.success=false;this.pickup.status='stopped';this.pickup.bilateral_hold_s=0}
    if(this.liftDemo)this.liftDemo.complete=false;
    if(this.demo){this.demo.complete=false;this.demo.status='stopped';this.demo.measurements.settle_dwell_s=0}
    this.hold();
  }

  private jointDemo(elapsed:number){
    const cycle=elapsed*.65;
    const goal=[...this.initialQ];goal[this.drive.baseQ[0]]=.025*Math.sin(cycle*.65);goal[this.drive.baseQ[2]]=.07*Math.sin(cycle*.55);this.drive.apply(goal);
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
    if(Math.max(...this.controlledQ.map(q=>Math.abs(this.data.qpos[q]-this.initialQ[q])))>.025||Math.hypot(phone[0]-.63,phone[1]+.72)>.01||Math.abs(phone[2]-.8135)>.015)throw new Error('Reset the scene before starting this fixture demonstration');
    for(const spec of this.descriptors.body_specs){
      if(!spec.dynamic_object)continue;
      const body=this.bodyIds.get(spec.name)!,joint=this.model.body_jntadr[body];
      if(joint<0||this.model.jnt_type[joint]!==this.engine.mjtJoint.mjJNT_FREE.value)continue;
      const q=this.model.jnt_qposadr[joint],position=read3(this.data.xpos,body*3);
      if(Math.hypot(...position.map((value,i)=>value-this.initialQ[q+i]))>.015)throw new Error('Reset the scene before starting this fixture demonstration');
    }
    if(this.objectJointNames.some(name=>Math.abs(this.data.qpos[this.qindex(name)]-this.initialQ[this.qindex(name)])>.01))throw new Error('Reset the scene before starting this fixture demonstration');
  }

  private sharedDefinition(command:SharedDemoCommand):DemoDefinition{
    const library=this.demoTrajectories;
    if(!library||library.schema_version!==1||library.model_hash!==this.descriptors.model_hash||library.nq!==this.model.nq||library.nu!==this.model.nu||!Array.isArray(library.actuated_q_indices)||library.actuated_q_indices.length!==this.actuatedQ.length||!library.actuated_q_indices.every((value,i)=>value===this.actuatedQ[i]))throw new Error('Demo trajectories do not match this reference physics model');
    for(const [supplied,expected]of [[library.position_actuator_indices,this.drive.positionActuators],[library.base_q_indices,this.drive.baseQ]])if(!Array.isArray(supplied)||supplied.length!==expected.length||!supplied.every((value,i)=>value===expected[i]))throw new Error('Demo trajectories do not match wheel-driven actuator mappings');
    const definition=library.commands?.[command];
    if(!definition||typeof definition.name!=='string'||!definition.name||!Array.isArray(definition.stages)||!definition.stages.length||definition.stages.length>100||!definition.outcomes)throw new Error('Invalid reference demo definition');
    if(command==='deliver_phone_demo'||command==='deliver_meal_demo'){
      const object=command==='deliver_phone_demo'?'phone':'meal_box';
      if(definition.object_name!==object||!Array.isArray(definition.source_position)||definition.source_position.length!==3||!definition.source_position.every(Number.isFinite)||definition.support_geom!==(object==='phone'?'phone_delivery_riser':'meal_delivery_riser'))throw new Error('Invalid assistance object or support definition');
    }
    for(const stage of definition.stages){
      if(typeof stage.name!=='string'||!stage.name||!Number.isFinite(stage.duration_s)||stage.duration_s<=0||stage.duration_s>60||!Array.isArray(stage.target_qpos)||stage.target_qpos.length!==this.model.nq||!stage.target_qpos.every(Number.isFinite)||(stage.gate_after!==undefined&&!['bilateral_contact','grasp_confirmed','phone_supported','phone_settled','assist_bilateral','assist_grasped','assist_supported','assist_released','blinds_open'].includes(stage.gate_after)))throw new Error('Invalid bounded reference demo stage');
      for(const actuator of this.drive.positionActuators){
        const value=stage.target_qpos[this.actuatedQ[actuator]],minimum=this.model.actuator_ctrlrange[actuator*2],maximum=this.model.actuator_ctrlrange[actuator*2+1];
        if(minimum<maximum&&(value<minimum||value>maximum))throw new Error('Reference demo target exceeds actuator limits');
      }
      for(const name of ['base_x','base_y','base_yaw']){const joint=this.jointIds.get(name)!,value=stage.target_qpos[this.model.jnt_qposadr[joint]];if(value<this.model.jnt_range[joint*2]||value>this.model.jnt_range[joint*2+1])throw new Error('Reference demo target exceeds base limits')}
      if(stage.navigation){const nav=stage.navigation;if(!['turn','drive','face'].includes(nav.kind)||typeof nav.reverse!=='boolean'||!Array.isArray(nav.goal)||nav.goal.length!==3||!nav.goal.every((value,i)=>Number.isFinite(value)&&Math.abs(value-stage.target_qpos[this.drive.baseQ[i]])<1e-9))throw new Error('Invalid wheel-driven navigation stage')}
    }
    if(Object.values(definition.ik_errors??{}).some(error=>!Number.isFinite(error.position_error_m)||!Number.isFinite(error.orientation_error_rad)||error.position_error_m>.003||error.orientation_error_rad>.01))throw new Error('Demo rejected by pose IK gate');
    return structuredClone(definition);
  }

  private permittedContacts(command:SharedDemoCommand,definition:DemoDefinition):Set<string>{
    const permitted=new Set<string>();
    const object=command==='deliver_phone_demo'?'phone_geom':command==='deliver_meal_demo'?'meal_box_geom':command==='blinds_demo'?'blinds_handle_geom':null;
    const robotGeoms=['left_finger_-1_geom','left_finger_1_geom',...(command==='blinds_demo'?['left_hand_geom']:[])];
    for(const pair of definition.intentional_contacts??[]){
      if(!Array.isArray(pair)||pair.length!==2||!object||!robotGeoms.some(robot=>contactKey(pair)===contactKey([object,robot])))throw new Error('Invalid intentional contact pair in assistance definition');
      permitted.add(contactKey(pair));
    }
    if(permitted.size!==(object?robotGeoms.length:0))throw new Error('Invalid intentional contact allowance');
    return permitted;
  }

  private startStages(stages:Stage[],loadedContactStages=false,intentionalContacts=this.intentionalContacts,allowPhoneGrasp=loadedContactStages):number{
    const sampled=new this.engine.MjData(this.model);let previous=Array.from(this.data.qpos as Float64Array),checked=0;
    try{
      for(const stage of stages){
        // Loaded finger targets compress against the phone; they are not a
        // prediction of the contact-constrained pose. Preflight free-space only.
        if(loadedContactStages&&['close','lift','hold','press_blinds_control'].includes(stage.name))break;
        for(let sample=0;sample<60;sample++){
          const ratio=sample/59;sampled.qpos.set(this.data.qpos);
          for(const q of this.controlledQ)sampled.qpos[q]=(1-ratio)*previous[q]+ratio*stage.target_qpos[q];
          if([...intentionalContacts].some(pair=>pair.includes('phone_geom')||pair.includes('meal_box_geom'))){
            // Loaded servo targets press through the object. Only the sampled
            // route uses open pads; actual contact dynamics remain authoritative.
            for(const finger of [-1,1]){const q=this.qindex(`left_gripper_${finger}`);sampled.qpos[q]=finger*Math.max(.10,finger*sampled.qpos[q])}
          }
          this.engine.mj_forward(this.model,sampled);checked++;
          const collisions=this.contacts(sampled,allowPhoneGrasp,intentionalContacts);
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
      if(stage.navigation){const error=this.drive.error(stage.target_qpos);if(error.position_m>.012||error.heading_rad>.025){this.stop(`Navigation stopped: wheel-driven goal not reached after ${stage.name} (${error.position_m.toFixed(4)}m, ${error.heading_rad.toFixed(4)}rad)`);return}}
      if(this.demo&&stage.gate_after){
        const passed=this.demoGate(stage.gate_after);this.demo.measurements[`gate_${stage.gate_after}_passed`]=passed;
        if(!passed){this.stop(`Demo stopped: ${stage.gate_after} gate failed after ${stage.name}`);return}
        if(stage.gate_after==='grasp_confirmed'&&this.pickup){this.demo.measurements.confirmed_grasp_height_m=this.pickup.height_gain_m;this.demo.measurements.confirmed_grasp_hold_s=this.pickup.bilateral_hold_s}
        if(stage.gate_after==='phone_supported'){const observation=this.phoneObservation();this.demo.measurements.supported_release_height_m=observation.phone_position[2];this.demo.measurements.supported_release_force_n=observation.riser_support_force_n;this.demo.measurements.supported_release_bilateral=this.fingerContacts().touching.length===2}
        if(stage.gate_after==='assist_grasped'){this.demo.measurements.confirmed_grasp_height_m=this.demo.measurements.object_height_gain_m;this.demo.measurements.confirmed_grasp_hold_s=this.demo.measurements.grasp_hold_s}
        if(stage.gate_after==='assist_supported'){this.demo.measurements.supported_release_force_n=this.demo.measurements.support_force_n;this.demo.measurements.supported_release_position=structuredClone(this.demo.measurements.object_position);this.demo.measurements.supported_release_bilateral=this.demo.measurements.bilateral_contact}
      }
      if(stage.name==='close'&&this.fingerContacts().touching.length!==2){this.stop('Pickup stopped: bilateral finger contact not established');return}
      this.stageIndex++;this.stageStarted=this.data.time;
      // Preserve commanded squeeze across stage boundaries; measured finger
      // qpos would remove the spring error and drop a frictional grasp.
      this.stageStartCtrl=Array.from(this.data.ctrl);stage=this.stages[this.stageIndex];elapsed=0;
    }
    let ratio=clamp((elapsed+this.timestep)/stage.duration_s,0,1);ratio=ratio*ratio*(3-2*ratio);
    for(const i of this.drive.positionActuators)this.data.ctrl[i]=(1-ratio)*this.stageStartCtrl[i]+ratio*stage.target_qpos[this.actuatedQ[i]];
    this.drive.apply(stage.target_qpos,stage.navigation);
  }

  private measureFixture(){
    if(this.pickup){
      const phoneZ=this.data.xpos[this.bodyIds.get('phone')!*3+2],{touching,forces}=this.fingerContacts();
      Object.assign(this.pickup,{stage:this.stages[this.stageIndex].name,phone_height_m:phoneZ,height_gain_m:phoneZ-this.pickup.initial_phone_height_m,finger_contacts:touching,normal_forces_n:forces,bilateral_contact:touching.length===2});
      if(this.mode==='pickup_demo'||this.mode==='phone_return_demo'){
        if(this.pickup.height_gain_m>.15&&touching.length===2){this.pickup.bilateral_hold_s+=this.timestep;if(this.pickup.bilateral_hold_s>=2){this.pickup.success=true;this.pickup.ever_succeeded=true;this.pickup.status='holding'}}
        else{this.pickup.bilateral_hold_s=0;if(this.pickup.success){this.pickup.success=false;this.pickup.status='lost_grasp'}}
      }else if(this.mode==='release_phone'){this.pickup.success=false;this.pickup.released=!touching.length&&this.pickup.height_gain_m<.03;this.pickup.status=this.pickup.released?'released':'releasing'}
      if(this.mode==='phone_return_demo'){
        const stage=this.stages[this.stageIndex].name;
        if(['lower_phone','open_fingers','retreat_hand','clear_return','return_base','rest_arms','settle'].includes(stage)){this.pickup.success=false;this.pickup.status=stage==='lower_phone'?'lowering':'returning'}
        if(['lift','hold','lower_phone'].includes(stage)&&touching.length!==2&&this.pickup.height_gain_m>.02)this.stop('Demo stopped: phone contact lost during supported manipulation');
      }
    }
    if(this.liftDemo&&this.mode==='lift_demo'){
      this.liftDemo.stage=this.stages[this.stageIndex].name;
      this.liftDemo.complete=this.stageIndex===this.stages.length-1&&this.data.time-this.stageStarted>=this.stages.at(-1)!.duration_s+.5;
      for(const side of ['left','right'] as const){const value=this.data.qpos[this.qindex(`${side}_lift`)];this.liftDemo.positions_m[side]=value;this.liftDemo.min_positions_m[side]=Math.min(value,this.liftDemo.min_positions_m[side]);this.liftDemo.max_positions_m[side]=Math.max(value,this.liftDemo.max_positions_m[side]);this.liftDemo.travel_m[side]=this.liftDemo.max_positions_m[side]-this.liftDemo.min_positions_m[side];const height=this.data.site_xpos[this.siteIds.get(side)!*3+2];this.liftDemo.hand_height_m[side]=height;this.liftDemo.min_hand_height_m[side]=Math.min(height,this.liftDemo.min_hand_height_m[side]);this.liftDemo.max_hand_height_m[side]=Math.max(height,this.liftDemo.max_hand_height_m[side])}
    }
  }

  private assistanceForces(object:string):{forces:Record<string,number>;support:number}{
    const forces:Record<string,number>={'left_finger_-1':0,'left_finger_1':0};if(object==='blinds_handle')forces.left_hand=0;
    let support=0;if(!this.data.ncon)return{forces,support};
    const contacts=this.data.contact,wrench=new this.engine.DoubleBuffer(6);
    try{
      for(let i=0;i<this.data.ncon;i++){
        const contact=contacts.get(i);if(!contact)continue;
        try{
          const names=[this.engine.mj_id2name(this.model,this.engine.mjtObj.mjOBJ_GEOM.value,contact.geom1),this.engine.mj_id2name(this.model,this.engine.mjtObj.mjOBJ_GEOM.value,contact.geom2)];
          if(!names.includes(`${object}_geom`))continue;
          this.engine.mj_contactForce(this.model,this.data,i,wrench);const force=Math.max(0,(wrench.GetView() as Float64Array)[0]);
          for(const finger of Object.keys(forces))if(names.includes(`${finger}_geom`))forces[finger]+=force;
          if(this.demoDefinition?.support_geom&&names.includes(this.demoDefinition.support_geom))support+=force;
        }finally{contact.delete()}
      }
      return{forces,support};
    }finally{wrench.delete();contacts.delete()}
  }

  private observeAssistance():Record<string,boolean>{
    const definition=this.demoDefinition!,demo=this.demo!,measured=demo.measurements,thresholds=definition.outcomes;
    const previous=(key:string,fallback=0):number=>typeof measured[key]==='number'?measured[key] as number:fallback;
    if(this.mode==='blinds_demo'){
      const travel=this.data.qpos[this.qindex('blinds_slide')],angles=Array.from({length:16},(_,i)=>this.data.qpos[this.qindex(`blinds_tilt_${String(i).padStart(2,'0')}`)]);
      const {forces}=this.assistanceForces('blinds_handle'),force=Object.values(forces).reduce((sum,value)=>sum+value,0);
      Object.assign(measured,{handle_travel_m:travel,minimum_slat_angle_rad:Math.min(...angles),maximum_slat_angle_rad:Math.max(...angles),control_contact_force_n:force,maximum_control_contact_force_n:Math.max(previous('maximum_control_contact_force_n'),force)});
      return{handle_moved:travel>=(thresholds.minimum_handle_travel_m as number),slats_open:Math.min(...angles)>=(thresholds.minimum_slat_angle_rad as number),physical_control_contact:previous('maximum_control_contact_force_n')>=(thresholds.minimum_control_contact_force_n as number)};
    }
    const body=definition.object_name!,position=read3(this.data.xpos,this.bodyIds.get(body)!*3),joint=this.engine.mj_name2id(this.model,this.engine.mjtObj.mjOBJ_JOINT.value,`${body}_free`),address=this.model.jnt_dofadr[joint];
    const {forces,support}=this.assistanceForces(body),bilateral=Object.values(forces).every(force=>force>.01),fingersClear=!Object.values(forces).some(force=>force>.01);
    const target=thresholds.object_target as number[],height=position[2]-definition.source_position![2],hand=this.engine.mj_name2id(this.model,this.engine.mjtObj.mjOBJ_SITE.value,'left_grasp_center');
    const handReference=thresholds.patient_hand_reference as number[];
    Object.assign(measured,{object_name:body,object_position:position,object_height_gain_m:height,object_xy_error_m:Math.hypot(position[0]-target[0],position[1]-target[1]),object_z_error_m:Math.abs(position[2]-target[2]),object_speed_m_s:norm(read3(this.data.qvel,address)),object_angular_speed_rad_s:norm(read3(this.data.qvel,address+3)),support_force_n:support,bilateral_contact:bilateral,fingers_clear:fingersClear,hand_clearance_m:norm(read3(this.data.site_xpos,hand*3).map((value,i)=>value-position[i])),patient_hand_distance_m:norm(position.map((value,i)=>value-handReference[i]))});
    measured.grasp_hold_s=bilateral&&height>=(thresholds.minimum_grasp_height_m as number)?previous('grasp_hold_s')+this.timestep:0;
    measured.ever_grasped=!!measured.ever_grasped||measured.grasp_hold_s>=(thresholds.minimum_bilateral_hold_s as number);
    const supported=previous('object_xy_error_m')<=(thresholds.object_xy_tolerance_m as number)&&previous('object_z_error_m')<=(thresholds.object_z_tolerance_m as number)&&previous('object_speed_m_s')<=(thresholds.object_speed_tolerance_m_s as number)&&previous('object_angular_speed_rad_s')<=(thresholds.object_angular_speed_tolerance_rad_s as number)&&support>(thresholds.support_force_minimum_n as number);
    measured.supported_on_tray=supported;
    if(['raise_object','confirm_grasp','clear_work_table','navigate_bedside','tray_hover','lower_to_tray'].includes(this.stages[this.stageIndex].action_phase??demo.stage)&&height>.02&&!bilateral)this.stop('Assistance stopped: bilateral object contact lost during transport');
    return{verified_grasp:!!measured.ever_grasped,placed_on_tray:supported,fingers_clear:fingersClear,hand_retracted:previous('hand_clearance_m')>=(thresholds.hand_clearance_m as number),within_modeled_patient_reach:previous('patient_hand_distance_m')<=(thresholds.maximum_patient_reach_m as number)};
  }

  private phoneObservation():PhoneObservation{
    const phone=read3(this.data.xpos,this.bodyIds.get('phone')!*3);
    const joint=this.engine.mj_name2id(this.model,this.engine.mjtObj.mjOBJ_JOINT.value,'phone_free'),address=this.model.jnt_dofadr[joint];
    let supportForce=0;
    if(this.data.ncon){
      const contacts=this.data.contact,wrench=new this.engine.DoubleBuffer(6);
      try{
        for(let i=0;i<this.data.ncon;i++){
          const contact=contacts.get(i);if(!contact)continue;
          try{
            const names=[this.engine.mj_id2name(this.model,this.engine.mjtObj.mjOBJ_GEOM.value,contact.geom1),this.engine.mj_id2name(this.model,this.engine.mjtObj.mjOBJ_GEOM.value,contact.geom2)];
            if(names.includes('phone_geom')&&names.includes('phone_riser')){this.engine.mj_contactForce(this.model,this.data,i,wrench);supportForce+=Math.max(0,(wrench.GetView() as Float64Array)[0])}
          }finally{contact.delete()}
        }
      }finally{wrench.delete();contacts.delete()}
    }
    const target=this.demoDefinition!.outcomes.phone_target as number[];
    const hand=this.engine.mj_name2id(this.model,this.engine.mjtObj.mjOBJ_SITE.value,'left_grasp_center');
    return{phone_position:phone,phone_xy_error_m:Math.hypot(phone[0]-target[0],phone[1]-target[1]),phone_z_error_m:Math.abs(phone[2]-target[2]),phone_speed_m_s:norm(read3(this.data.qvel,address)),phone_angular_speed_rad_s:norm(read3(this.data.qvel,address+3)),riser_support_force_n:supportForce,hand_clearance_m:norm(read3(this.data.site_xpos,hand*3).map((value,i)=>value-phone[i]))};
  }

  private phoneSettled(observation:PhoneObservation):boolean{
    const thresholds=this.demoDefinition!.outcomes;
    return observation.phone_xy_error_m<=(thresholds.phone_xy_tolerance_m as number)&&observation.phone_z_error_m<=(thresholds.phone_z_tolerance_m as number)&&observation.phone_speed_m_s<=(thresholds.phone_speed_tolerance_m_s as number)&&observation.phone_angular_speed_rad_s<=(thresholds.phone_angular_speed_tolerance_rad_s as number)&&observation.riser_support_force_n>(thresholds.support_force_minimum_n as number);
  }

  private demoGate(gate:StageGate):boolean{
    if(ASSISTANCE_DEMOS.includes(this.mode as SharedDemoCommand)){
      const measured=this.demo!.measurements;
      if(gate==='assist_bilateral')return !!measured.bilateral_contact;
      if(gate==='assist_grasped')return !!(measured.ever_grasped&&measured.bilateral_contact);
      if(gate==='assist_supported')return !!(measured.supported_on_tray&&measured.bilateral_contact);
      if(gate==='assist_released')return !!(measured.supported_on_tray&&measured.fingers_clear);
      if(gate==='blinds_open')return ['handle_moved','slats_open','physical_control_contact'].every(key=>this.demo!.checks[key]);
      throw new Error('Unknown assistance contact gate');
    }
    const {touching}=this.fingerContacts();
    if(gate==='bilateral_contact')return touching.length===2;
    if(gate==='grasp_confirmed')return !!(this.pickup?.success&&this.pickup.ever_succeeded);
    if(gate==='phone_supported')return touching.length===2&&this.phoneSettled(this.phoneObservation());
    return touching.length===0&&this.phoneSettled(this.phoneObservation());
  }

  private measureDemo(){
    if(!this.demo||!this.demoDefinition)return;
    const demo=this.demo,thresholds=this.demoDefinition.outcomes,measured=demo.measurements;
    const previousNumber=(key:string,fallback=0):number=>typeof measured[key]==='number'?measured[key] as number:fallback;
    const elapsed=Math.max(0,this.data.time-this.modeStarted);
    Object.assign(demo,{stage:this.stages[this.stageIndex].name,stage_index:this.stageIndex,elapsed_s:elapsed,progress:Math.min(1,elapsed/demo.duration_s)});
    measured.rest_qpos_error=Math.max(...this.drive.positionQ.map(q=>Math.abs(this.data.qpos[q]-this.initialQ[q])));
    measured.robot_speed=Math.max(...this.robotDofs.map(dof=>Math.abs(this.data.qvel[dof])));
    const home=this.drive.error(this.initialQ);measured.base_home_error_m=home.position_m;measured.base_home_yaw_error_rad=home.heading_rad;
    const checks:Record<string,boolean>={returned_to_rest:measured.rest_qpos_error<=(thresholds.rest_qpos_tolerance as number),robot_settled:measured.robot_speed<=(thresholds.robot_speed_tolerance as number),base_returned_home:home.position_m<=.012&&home.heading_rad<=.025};
    if(ASSISTANCE_DEMOS.includes(this.mode as SharedDemoCommand))Object.assign(checks,this.observeAssistance());
    else if(this.mode==='bedside_demo'){
      const base=['base_x','base_y','base_yaw'].map(name=>this.data.qpos[this.qindex(name)]),target=thresholds.base_goal_qpos as number[];
      Object.assign(measured,{base_position_qpos:base,base_goal_error_m:Math.hypot(base[0]-target[0],base[1]-target[1]),base_yaw_error_rad:Math.abs(wrapAngle(base[2]-target[2])),base_home_error_m:Math.hypot(base[0],base[1])});
      measured.max_base_excursion_m=Math.max(previousNumber('max_base_excursion_m'),previousNumber('base_home_error_m'));
      measured.visited_bedside=!!measured.visited_bedside||(previousNumber('base_goal_error_m')<=(thresholds.base_goal_tolerance_m as number)&&previousNumber('base_yaw_error_rad')<=(thresholds.yaw_tolerance_rad as number));
      checks.visited_bedside=measured.visited_bedside;checks.base_travel_observed=measured.max_base_excursion_m>=(thresholds.minimum_base_excursion_m as number);
    }else if(this.mode==='greeting_demo'){
      const height=this.data.site_xpos[this.siteIds.get('left')!*3+2];
      measured.hand_height_m=height;measured.max_hand_height_m=Math.max(previousNumber('max_hand_height_m',height),height);
      if(demo.stage.startsWith('wave_')){const wave=this.data.qpos[this.qindex('left_joint_6')];measured.wave_min_rad=Math.min(previousNumber('wave_min_rad',wave),wave);measured.wave_max_rad=Math.max(previousNumber('wave_max_rad',wave),wave)}
      measured.wave_range_rad=previousNumber('wave_max_rad')-previousNumber('wave_min_rad');
      checks.hand_raised=measured.max_hand_height_m>=(thresholds.minimum_hand_height_m as number);checks.wrist_waved=measured.wave_range_rad>=(thresholds.minimum_wave_range_rad as number);
    }else if(this.mode==='phone_return_demo'){
      const observation=this.phoneObservation(),{touching}=this.fingerContacts();Object.assign(measured,observation);
      Object.assign(checks,{confirmed_grasp:!!this.pickup?.ever_succeeded,phone_on_riser:this.phoneSettled(observation),fingers_clear:touching.length===0,hand_retracted:observation.hand_clearance_m>=(thresholds.hand_clearance_m as number)});
      if(this.pickup&&['retreat_hand','clear_return','return_base','rest_arms','settle'].includes(demo.stage)){this.pickup.released=checks.phone_on_riser&&checks.fingers_clear;this.pickup.status=this.pickup.released?'returned':'returning'}
    }
    demo.checks=checks;const allChecked=Object.values(checks).every(Boolean);
    if(this.paused&&this.stopReason){demo.complete=false;demo.status='stopped';return}
    measured.settle_dwell_s=this.stageIndex===this.stages.length-1&&allChecked?previousNumber('settle_dwell_s')+this.timestep:0;
    if(demo.complete&&!allChecked)this.stop('Demo stopped: a completed outcome no longer holds');
    else if(elapsed+1e-9>=demo.duration_s&&allChecked&&measured.settle_dwell_s>=(thresholds.settle_dwell_s as number)){demo.complete=true;demo.status='complete'}
    else if(elapsed>demo.duration_s+3&&!demo.complete)this.stop('Demo stopped: measured outcome checks did not settle within the bounded grace period');
  }

  command(action:PhysicsCommand|string):BrowserPhysicsState{
    this.assertOpen();
    if(this.stopReason&&action!=='reset')throw new Error('Reset the scene before continuing after a simulation stop');
    if(SHARED_DEMOS.includes(this.mode as SharedDemoCommand)&&!['reset','pause','pause_for_tracking'].includes(action))throw new Error('Reset the scene before starting another demonstration');
    if(['joint_demo','reach_demo','lift_demo','pickup_demo',...SHARED_DEMOS].includes(action)&&['pickup_demo','release_phone'].includes(this.mode))throw new Error('Release the phone and reset the scene before another demonstration');
    if(action==='reset'){
      this.engine.mj_resetData(this.model,this.data);this.data.qpos.set(this.initialQ);this.data.ctrl.set(this.initialCtrl);this.engine.mj_forward(this.model,this.data);
      this.mode='idle';this.paused=false;this.reachPlan=null;this.stopReason=null;this.lastContacts=[];this.stepCount=0;this.accumulator=0;
      this.stages=[];this.pickup=null;this.liftDemo=null;this.stageIndex=0;this.stageStarted=0;
      this.demo=null;this.demoDefinition=null;
      this.intentionalContacts.clear();this.visualTrackingPauseReason=null;
    }else if(action==='pause'){this.paused=!this.paused;this.visualTrackingPauseReason=null}
    else if(action==='pause_for_tracking'){this.paused=true;this.visualTrackingPauseReason='Visual tracking lost'}
    else if(action==='joint_demo'){this.mode='joint_demo';this.paused=false;this.modeStarted=this.data.time;this.stopReason=null;this.reachPlan=null;this.stages=[];this.liftDemo=null}
    else if(action==='pickup_demo'||action==='lift_demo'){
      this.requireFixtureStart();
      if(action==='pickup_demo'){
        const {stages,errors}=this.pickupStages();if(Object.values(errors).some(error=>error.position_error_m>.002||error.orientation_error_rad>.01))throw new Error('Pickup rejected by six-dimensional pose IK gate');
        const count=this.startStages(this.drive.expandStages(this.initialQ,stages),true),height=this.data.xpos[this.bodyIds.get('phone')!*3+2];
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
      const released=Array.from(this.data.qpos as Float64Array);for(const i of this.drive.positionActuators)released[this.actuatedQ[i]]=this.data.ctrl[i];
      for(const finger of [-1,1])released[this.qindex(`left_gripper_${finger}`)]=finger*.60;
      this.stages=[{name:'release',target_qpos:released,duration_s:1.5}];this.stageIndex=0;this.stageStarted=this.data.time;this.stageStartCtrl=Array.from(this.data.ctrl);this.mode='release_phone';this.paused=false;this.pickup.status='releasing';this.pickup.success=false;this.pickup.bilateral_hold_s=0;
    }
    else if(action==='reach_demo'){
      const plan=this.solveReach([.22,-.53,.96]);this.reachPlan=plan;
      if(!plan.reachable||!plan.collision_free_samples){this.stopReason='Reach rejected by endpoint IK or sampled collision gate';this.paused=true}
      else{this.reachPlan={...plan,start_qpos:Array.from(this.data.qpos),duration_s:4};this.data.mocap_pos.set(plan.target);this.mode='reach_demo';this.paused=false;this.modeStarted=this.data.time;this.stopReason=null}
    }else if(SHARED_DEMOS.includes(action as SharedDemoCommand)){
      this.requireFixtureStart();const command=action as SharedDemoCommand,definition=this.sharedDefinition(command);
      const allowed=this.permittedContacts(command,definition);
      const checked=this.startStages(definition.stages,command==='phone_return_demo'||ASSISTANCE_DEMOS.includes(command),allowed,command==='phone_return_demo');
      this.intentionalContacts=allowed;
      this.demoDefinition=definition;
      this.demo={command,name:definition.name,stage:definition.stages[0].name,stage_index:0,stage_count:definition.stages.length,progress:0,elapsed_s:0,duration_s:definition.stages.reduce((sum,stage)=>sum+stage.duration_s,0),status:'running',complete:false,measurements:{collision_samples:checked,settle_dwell_s:0},checks:{}};
      this.pickup=null;this.liftDemo=null;this.reachPlan=null;
      if(command==='phone_return_demo'){
        const height=this.data.xpos[this.bodyIds.get('phone')!*3+2];
        this.pickup={stage:definition.stages[0].name,status:'running',success:false,ever_succeeded:false,released:false,initial_phone_height_m:height,phone_height_m:height,height_gain_m:0,bilateral_contact:false,finger_contacts:[],normal_forces_n:{},bilateral_hold_s:0,ik_errors:definition.ik_errors??{},collision_samples:checked,sampled_collision_gate_passed:true,attachment_constraints:0};
      }
      this.mode=command;this.paused=false;this.modeStarted=this.data.time;this.stopReason=null;
    }else throw new Error('Allowed commands: joint_demo, reach_demo, pickup_demo, release_phone, lift_demo, bedside_demo, greeting_demo, phone_return_demo, deliver_phone_demo, deliver_meal_demo, blinds_demo, pause, pause_for_tracking, reset');
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
      else if(this.mode==='pickup_demo'||this.mode==='release_phone'||this.mode==='lift_demo'||SHARED_DEMOS.includes(this.mode as SharedDemoCommand)){this.stagedControl();if(this.paused)break}
      else if(this.mode==='reach_demo'&&this.reachPlan?.start_qpos){
        let ratio=clamp(elapsed/this.reachPlan.duration_s!,0,1);ratio=ratio*ratio*(3-2*ratio);
        for(const i of this.drive.positionActuators){const q=this.actuatedQ[i];this.data.ctrl[i]=(1-ratio)*this.reachPlan.start_qpos[q]+ratio*this.reachPlan.target_qpos[q]}
        this.drive.apply(this.reachPlan.target_qpos,{kind:'drive',reverse:false,goal:this.drive.baseQ.map(q=>this.reachPlan!.target_qpos[q]) as Vec3});
      }
      this.engine.mj_step(this.model,this.data);this.stepCount++;
      this.measureFixture();
      this.measureDemo();if(this.paused)break;
      const contacts=this.contacts();
      if(contacts.length||!this.finite()){this.stop(contacts.length?'Synthetic contact stop':'Nonfinite physics state',contacts);break}
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
    const objectJoints:Record<string,number>={};for(const name of this.objectJointNames)objectJoints[name]=this.data.qpos[this.qindex(name)];
    const cameras:Record<string,CameraPose>={};for(const [name,id]of this.cameraIds)cameras[name]={position:read3(this.data.cam_xpos,id*3),rotation:Array.from({length:9},(_,i)=>this.data.cam_xmat[id*9+i]),fovy_deg:this.model.cam_fovy[id],fovy:this.model.cam_fovy[id],convention:'mujoco_opengl'};
    const endEffectors:Record<string,Vec3>={};for(const [side,id]of this.siteIds)endEffectors[side]=read3(this.data.site_xpos,id*3);
    const metrics:BrowserPhysicsState['metrics']={drive:this.drive.observe(),physics_steps:this.stepCount,finite_dynamics:this.finite(),contacts:this.lastContacts,stop_reason:this.stopReason,grasp_success:null,object_attached:false};
    metrics.visual_tracking_pause_reason=this.visualTrackingPauseReason;
    if(this.pickup){metrics.pickup=structuredClone(this.pickup);metrics.grasp_success=this.pickup.success}
    if(this.liftDemo)metrics.lift=structuredClone(this.liftDemo);
    if(this.demo)metrics.demo=structuredClone(this.demo);
    if(this.reachPlan){const distance=norm(endEffectors[this.reachPlan.side].map((value,i)=>value-this.reachPlan!.target[i]));metrics.reach={target:this.reachPlan.target,ik_residual_m:this.reachPlan.residual_m,actual_endpoint_error_m:distance,endpoint_reached:distance<.02,sampled_collision_gate_passed:this.reachPlan.collision_free_samples,samples:this.reachPlan.sample_count}}
    return{bodies,joints,object_joints:objectJoints,cameras,mode:this.mode,paused:this.paused,simulation_time:this.data.time,target:{position:read3(this.data.mocap_pos,0)},end_effectors:endEffectors,metrics,model_hash:this.descriptors.model_hash,hardware_model_verified:false,authorizes_hardware:false,source:'Actual MuJoCo WebAssembly dynamics on reference-informed unverified surrogate',engine:'mujoco-wasm',engine_version:this.engine.mj_versionString()};
  }
  dispose(){if(this.disposed)return;this.disposed=true;this.data.delete();this.model.delete()}
}
