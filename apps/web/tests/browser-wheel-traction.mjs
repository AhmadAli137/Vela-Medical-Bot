/** Direct official-WASM traction checks, independent of the route controller.
 * VELA_DRIVE_XML can point at a provisional native MJCF while it is developed.
 */
import assert from 'node:assert/strict';
import test,{after} from 'node:test';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import loadMujoco from '@mujoco/mujoco';
import ts from 'typescript';

const engine=await loadMujoco();
const driveSource=readFileSync(new URL('../src/browserDrive.ts',import.meta.url),'utf8');
const driveCompiled=ts.transpileModule(driveSource,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {DifferentialDrive}=await import(`data:text/javascript;base64,${Buffer.from(driveCompiled).toString('base64')}`);
const xml=readFileSync(process.env.VELA_DRIVE_XML?resolve(process.env.VELA_DRIVE_XML):new URL('../public/simulation/reference.xml',import.meta.url),'utf8');
const descriptors=JSON.parse(readFileSync(new URL('../public/simulation/reference-descriptors.json',import.meta.url),'utf8'));
const evidence={engine:'MuJoCo 3.13.0 WebAssembly',model_hash:createHash('sha256').update(xml).digest('hex'),source:process.env.VELA_DRIVE_XML?'prototype_override':'public_reference',cases:{}};
after(()=>writeFileSync(new URL('../../../artifacts/browser-wheel-traction.json',import.meta.url),JSON.stringify(evidence,null,2)+'\n'));

function create(){
  const model=engine.MjModel.from_xml_string(xml),data=new engine.MjData(model);
  const id=(type,name)=>engine.mj_name2id(model,engine.mjtObj[type].value,name);
  const joint=name=>id('mjOBJ_JOINT',name),q=name=>model.jnt_qposadr[joint(name)],v=name=>model.jnt_dofadr[joint(name)];
  for(const spec of descriptors.body_specs)if(spec.joint&&spec.joint_type!=='free')data.qpos[q(spec.joint)]=spec.initial_q??0;
  for(let i=0;i<model.nu;i++){
    const name=engine.mj_id2name(model,engine.mjtObj.mjOBJ_ACTUATOR.value,i);
    data.ctrl[i]=name.includes('_wheel_joint')?0:data.qpos[model.jnt_qposadr[model.actuator_trnid[i*2]]];
  }
  engine.mj_forward(model,data);
  const wheels={left:id('mjOBJ_ACTUATOR','ctrl_left_wheel_joint'),right:id('mjOBJ_ACTUATOR','ctrl_right_wheel_joint')};
  function observe(){
    const yaw=data.qpos[q('base_yaw')],vx=data.qvel[v('base_x')],vy=data.qvel[v('base_y')],rate=data.qvel[v('base_yaw')];
    const forward=Math.cos(yaw)*vx+Math.sin(yaw)*vy,lateral=-Math.sin(yaw)*vx+Math.cos(yaw)*vy;
    const forces={left:0,right:0},wrench=new engine.DoubleBuffer(6),contacts=data.contact;
    try{
      for(let i=0;i<data.ncon;i++){
        const contact=contacts.get(i);if(!contact)continue;
        try{
          const names=[contact.geom1,contact.geom2].map(index=>engine.mj_id2name(model,engine.mjtObj.mjOBJ_GEOM.value,index));
          if(!names.includes('floor'))continue;
          for(const side of ['left','right'])if(names.includes(`${side}_wheel_geom`)){
            engine.mj_contactForce(model,data,i,wrench);forces[side]+=Math.max(0,wrench.GetView()[0]);
          }
        }finally{contact.delete()}
      }
    }finally{contacts.delete();wrench.delete()}
    return{time_s:data.time,x_m:data.qpos[q('base_x')],y_m:data.qpos[q('base_y')],yaw_rad:yaw,forward_velocity_m_s:forward,lateral_velocity_m_s:lateral,yaw_rate_rad_s:rate,wheel_force_n:forces,
      wheel_angular_velocity_rad_s:Object.fromEntries(['left','right'].map(side=>[side,data.qvel[v(`${side}_wheel_joint`)]])),
      rolling_error_m_s:{left:forward-.20*rate-.13*data.qvel[v('left_wheel_joint')],right:forward+.20*rate-.13*data.qvel[v('right_wheel_joint')]}};
  }
  return{model,data,id,wheels,observe,dispose:()=>{data.delete();model.delete()}};
}

function rollout(left,right,mutate){
  const sim=create();
  try{
    assert.equal(sim.model.nu,22);
    for(const name of ['ctrl_base_x','ctrl_base_y','ctrl_base_yaw','ctrl_base_z'])assert.equal(sim.id('mjOBJ_ACTUATOR',name),-1);
    mutate?.(sim);
    sim.data.ctrl[sim.wheels.left]=left;sim.data.ctrl[sim.wheels.right]=right;
    const frames=[];
    for(let step=1;step<=1500;step++){engine.mj_step(sim.model,sim.data);if(step%25===0)frames.push(sim.observe())}
    assert.ok(Array.from(sim.data.qpos).every(Number.isFinite));
    return{final:frames.at(-1),frames};
  }finally{sim.dispose()}
}

test('equal wheel velocities propel the chassis through actual tire-floor traction',()=>{
  const run=rollout(2,2),steady=run.frames.filter(frame=>frame.time_s>.5);
  assert.ok(run.final.x_m>.6,JSON.stringify(run.final));assert.ok(Math.abs(run.final.y_m)<.002);assert.ok(Math.abs(run.final.yaw_rad)<.01);
  for(const frame of steady){assert.ok(Math.abs(frame.lateral_velocity_m_s)<.002);assert.ok(Math.max(...Object.values(frame.rolling_error_m_s).map(Math.abs))<.006);assert.ok(frame.wheel_force_n.left>1&&frame.wheel_force_n.right>1)}
  evidence.cases.forward=run;
});

test('opposite wheel velocities turn the chassis without commanding lateral translation',()=>{
  const run=rollout(-2,2),steady=run.frames.filter(frame=>frame.time_s>.5);
  evidence.cases.turn=run;
  assert.ok(run.final.yaw_rad>2,JSON.stringify(run.final));assert.ok(Math.hypot(run.final.x_m,run.final.y_m)<.03);
  assert.ok(Math.max(...steady.map(frame=>Math.abs(frame.lateral_velocity_m_s)))<.003);
  for(const frame of steady)assert.ok(frame.wheel_force_n.left>1&&frame.wheel_force_n.right>1,JSON.stringify(frame));
});

test('removing wheel-floor friction removes driven base translation',()=>{
  const run=rollout(2,2,sim=>{
    for(const name of ['floor','left_wheel_geom','right_wheel_geom']){const geom=sim.id('mjOBJ_GEOM',name);for(let axis=0;axis<3;axis++)sim.model.geom_friction[geom*3+axis]=0}
  });
  assert.ok(Math.hypot(run.final.x_m,run.final.y_m)<.01,JSON.stringify(run.final));
  assert.ok(run.final.wheel_angular_velocity_rad_s.left>1.8&&run.final.wheel_angular_velocity_rad_s.right>1.8);
  evidence.cases.no_friction=run;
});

test('a sideways goal becomes physical turn-drive-turn motion using only wheel controls',()=>{
  const sim=create();
  try{
    const drive=new DifferentialDrive(engine,sim.model,sim.data),initial=Array.from(sim.data.qpos),target=[...initial];
    target[drive.baseQ[1]]=.35;
    const stages=drive.expandStages(initial,[{name:'side_goal',duration_s:2,target_qpos:target,gate_after:'test_gate'}]);
    assert.deepEqual(stages.map(stage=>stage.navigation?.kind??'hold'),['turn','drive','face','hold']);
    assert.ok(stages.slice(0,-1).every(stage=>stage.gate_after===undefined));assert.equal(stages.at(-1).gate_after,'test_gate');
    const originalCtrl=Array.from(sim.data.ctrl);
    drive.apply(stages[0].target_qpos,stages[0].navigation);
    assert.deepEqual(Array.from(sim.data.qpos),initial,'Drive control may not write kinematic coordinates');
    for(const actuator of drive.positionActuators)assert.equal(sim.data.ctrl[actuator],originalCtrl[actuator]);
    assert.ok(drive.wheelActuators.every(actuator=>Math.abs(sim.data.ctrl[actuator])<=.01600001));
    const frames=[];
    for(const stage of stages){
      for(let step=0;step<Math.ceil(stage.duration_s/.002);step++){
        drive.apply(stage.target_qpos,stage.navigation);engine.mj_step(sim.model,sim.data);
        if(step%25===0)frames.push({...drive.observe(),stage:stage.name,time_s:sim.data.time});
      }
      const error=drive.error(stage.target_qpos);assert.ok(error.position_m<.012&&error.heading_rad<.02,JSON.stringify({stage:stage.name,error}));
    }
    const error=drive.error(target),maximumLateral=Math.max(...frames.map(frame=>Math.abs(frame.lateral_velocity_m_s)));
    assert.ok(error.position_m<.012&&error.heading_rad<.02);assert.ok(maximumLateral<.004,`Unexpected sideways velocity ${maximumLateral}`);
    assert.ok(frames.some(frame=>Math.abs(frame.yaw_rate_rad_s)>.3));assert.ok(frames.some(frame=>frame.forward_velocity_m_s>.15));
    evidence.cases.controlled_side_goal={final:drive.observe(),error,maximum_lateral_velocity_m_s:maximumLateral,frames};
  }finally{sim.dispose()}
});
