/** Run with `node --test tests/browser-physics-wasm.mjs` from apps/web.
 * Uses the real official WASM package and authoritative reference assets.
 */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import test,{after} from 'node:test';
import ts from 'typescript';
import loadMujoco from '@mujoco/mujoco';

const source=readFileSync(new URL('../src/browserPhysicsCore.ts',import.meta.url),'utf8');
const driveSource=ts.transpileModule(readFileSync(new URL('../src/browserDrive.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const driveUrl=`data:text/javascript;base64,${Buffer.from(driveSource).toString('base64')}`;
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText.replace("'./browserDrive'",JSON.stringify(driveUrl));
const {BrowserPhysics}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const engine=await loadMujoco();
const xml=readFileSync(new URL('../public/simulation/reference.xml',import.meta.url),'utf8');
const descriptors=JSON.parse(readFileSync(new URL('../public/simulation/reference-descriptors.json',import.meta.url),'utf8'));
const trajectories=JSON.parse(readFileSync(new URL('../../../sim/reference_demo_trajectories.json',import.meta.url),'utf8'));
const create=(library=trajectories)=>new BrowserPhysics(engine,xml,descriptors,library);
const advanceUntil=(sim,predicate,limit=200)=>{let state=sim.advance(0);for(let elapsed=0;!predicate(state)&&elapsed<limit;elapsed+=.5){state=sim.advance(.5);assert.equal(state.paused,false,`${state.metrics.stop_reason}: ${JSON.stringify(state.metrics.demo??state.metrics.pickup)}`)}assert.ok(predicate(state),'Measured condition did not occur within bounded simulation time');return state};
const evidence={engine:'MuJoCo 3.13.0 WebAssembly',model_hash:descriptors.model_hash};
const assertNoObjectAttachments=sim=>{
  for(let i=0;i<sim.model.neq;i++){
    assert.equal(sim.model.eq_type[i],engine.mjtEq.mjEQ_JOINT.value,'Only passive blinds joint couplings may be present');
    const name=id=>engine.mj_id2name(sim.model,engine.mjtObj.mjOBJ_JOINT.value,id);
    assert.match(name(sim.model.eq_obj1id[i]),/^blinds_tilt_\d{2}$/);assert.equal(name(sim.model.eq_obj2id[i]),'blinds_slide');
  }
};
after(()=>writeFileSync(new URL('../../../artifacts/browser-contact-physics.json',import.meta.url),JSON.stringify(evidence,null,2)+'\n'));

test('native reference XML compiles in official WASM with matching body topology',()=>{
  const sim=create();
  try{
    const state=sim.advance(0);
    assert.equal(state.engine,'mujoco-wasm');assert.equal(state.engine_version,'3.13.0');
    assert.equal(Object.keys(state.bodies).length,descriptors.body_specs.length);assert.equal(Object.keys(state.joints).length,26);
    assert.equal(state.hardware_model_verified,false);assert.equal(state.authorizes_hardware,false);
    for(const [name,pose]of Object.entries(state.bodies)){
      const expected=descriptors.initial_world_poses[name];
      assert.ok(pose.position.every((value,i)=>Math.abs(value-expected.position[i])<1e-12));
      assert.ok(pose.quaternion.every((value,i)=>Math.abs(value-expected.quaternion[i])<1e-12));
    }
  }finally{sim.dispose()}
});

test('modeled optical cameras stay aligned with moving head and wrist bodies',()=>{
  const sim=create();
  const rotate=([w,x,y,z],[a,b,c])=>[
    (1-2*y*y-2*z*z)*a+(2*x*y-2*z*w)*b+(2*x*z+2*y*w)*c,
    (2*x*y+2*z*w)*a+(1-2*x*x-2*z*z)*b+(2*y*z-2*x*w)*c,
    (2*x*z-2*y*w)*a+(2*y*z+2*x*w)*b+(1-2*x*x-2*y*y)*c,
  ];
  const check=state=>{
    assert.deepEqual(Object.keys(state.cameras).sort(),['head_rgb','head_stereo_right','left_wrist','right_wrist']);
    for(const [name,parent,offset,fovy]of [['head_rgb','head',[.067,.027,.008],90],['head_stereo_right','head',[.067,-.027,.008],90],['left_wrist','left_hand',[.046,0,-.008],75],['right_wrist','right_hand',[.046,0,-.008],75]]){
      const camera=state.cameras[name],body=state.bodies[parent],translated=rotate(body.quaternion,offset);
      assert.equal(camera.convention,'mujoco_opengl');assert.equal(camera.fovy_deg,fovy);assert.equal(camera.rotation.length,9);
      for(let axis=0;axis<3;axis++)assert.ok(Math.abs(camera.position[axis]-body.position[axis]-translated[axis])<1e-9,`${name} optical offset`);
      const columns=[0,1,2].map(column=>[0,1,2].map(row=>camera.rotation[row*3+column]));
      for(let a=0;a<3;a++)for(let b=0;b<3;b++)assert.ok(Math.abs(columns[a].reduce((sum,v,i)=>sum+v*columns[b][i],0)-(a===b?1:0))<1e-9);
    }
    const left=state.cameras.head_rgb,right=state.cameras.head_stereo_right;
    assert.ok(Math.abs(Math.hypot(...right.position.map((value,i)=>value-left.position[i]))-.054)<1e-9);
    for(let i=0;i<3;i++){assert.ok(Math.abs((right.position[i]-left.position[i])/.054-left.rotation[i*3])<1e-9);assert.ok(Math.abs(-left.rotation[i*3+2]-rotate(state.bodies.head.quaternion,[1,0,0])[i])<1e-9)}
    const focal=240/(2*Math.tan(left.fovy_deg*Math.PI/360));assert.ok(Math.abs(focal-120)<1e-10);
  };
  try{
    const initial=sim.advance(0);check(initial);sim.command('joint_demo');const moving=sim.advance(.5);check(moving);
    assert.ok(Math.hypot(...moving.cameras.left_wrist.position.map((value,i)=>value-initial.cameras.left_wrist.position[i]))>.001);
    const paused=sim.command('pause');assert.deepEqual(sim.advance(1).cameras,paused.cameras);
    evidence.cameras={initial:initial.cameras,after_motion:moving.cameras,stereo_baseline_m:.054,head_focal_length_px_at_320x240:120};
  }finally{sim.dispose()}
});

test('passive blinds coupling never adds an object or mechanism actuator',()=>{
  const sim=create();
  try{
    const state=sim.advance(0);assert.equal(sim.model.nu,22);assert.equal(sim.model.neq,16);assertNoObjectAttachments(sim);
    assert.equal(Object.keys(state.joints).length,26);assert.equal(Object.keys(state.object_joints).length,17);
    assert.ok(Object.keys(state.object_joints).every(name=>name==='blinds_slide'||/^blinds_tilt_\d{2}$/.test(name)));
    for(const name of ['phone','meal_box','blinds_handle'])assert.equal(sim.robotBodies.has(sim.bodyIds.get(name)),false);
  }finally{sim.dispose()}
});

test('actual forward dynamics drives all 22 actuators over a 16 second contact-free cycle',()=>{
  const sim=create();
  try{
    const original=sim.advance(0).joints;sim.command('joint_demo');let state;
    for(let i=0;i<8;i++){state=sim.advance(2);assert.equal(state.paused,false);assert.deepEqual(state.metrics.contacts,[])}
    assert.equal(state.metrics.physics_steps,8000);assert.ok(state.metrics.finite_dynamics);
    for(let actuator=0;actuator<sim.model.nu;actuator++){const name=engine.mj_id2name(sim.model,engine.mjtObj.mjOBJ_JOINT.value,sim.model.actuator_trnid[actuator*2]);assert.ok(Math.abs(state.joints[name]-original[name])>.0001,name)}assert.equal(state.metrics.drive.actuator_count,22);assert.ok(Math.abs(state.metrics.drive.lateral_velocity_m_s)<.003);
  }finally{sim.dispose()}
});

test('runtime WASM Jacobian IK and actual servo tracking match native endpoint evidence',()=>{
  const sim=create();
  try{
    const initial=sim.command('reach_demo');assert.equal(initial.metrics.reach.endpoint_reached,false);
    assert.equal(initial.metrics.reach.samples,60);assert.ok(initial.metrics.reach.sampled_collision_gate_passed);
    for(let i=0;i<3;i++)sim.advance(2);
    const final=sim.advance(0);assert.ok(final.metrics.reach.endpoint_reached);
    assert.ok(final.metrics.reach.actual_endpoint_error_m<.002);
    assert.equal(final.metrics.physics_steps,3000);assert.deepEqual(final.metrics.contacts,[]);
    assert.equal(final.metrics.object_attached,false);assert.equal(final.metrics.grasp_success,null);
    evidence.reach=final.metrics.reach;
  }finally{sim.dispose()}
});

test('unreachable and malformed goals are checked without changing live state',()=>{
  const sim=create();
  try{
    const original=sim.advance(0);const unreachable=sim.solveReach([8,8,8]);
    assert.equal(unreachable.reachable,false);assert.ok(unreachable.residual_m>5);
    assert.deepEqual(sim.advance(0).joints,original.joints);
    assert.throws(()=>sim.solveReach([NaN,0,0]),/Invalid/);
  }finally{sim.dispose()}
});

test('real WASM contact structs trigger a numerical stop when robot intersects table',()=>{
  const sim=create();
  try{
    // Deliberately corrupt the synthetic pose only inside this collision regression.
    sim.data.qpos[sim.qindex('base_x')]=1.15;engine.mj_forward(sim.model,sim.data);
    const state=sim.advance(.002);assert.equal(state.paused,true);
    assert.equal(state.metrics.stop_reason,'Synthetic contact stop');assert.ok(state.metrics.contacts.length>0);
  }finally{sim.dispose()}
});

test('pause, reset, bounded stepping and disposal prevent unintended mutation',()=>{
  const sim=create();
  const original=sim.advance(0);sim.command('joint_demo');sim.advance(.4);const paused=sim.command('pause');
  assert.deepEqual(sim.advance(1).joints,paused.joints);assert.equal(sim.command('pause').paused,false);
  const reset=sim.command('reset');assert.deepEqual(reset.joints,original.joints);assert.equal(reset.simulation_time,0);
  assert.throws(()=>sim.advance(3),/between/);assert.throws(()=>sim.advance(NaN),/finite/);
  assert.throws(()=>sim.command('hardware_execute'),/Allowed/);
  sim.dispose();sim.dispose();assert.throws(()=>sim.state(),/disposed/);
});

test('a slow browser frame advances at most 50 ms instead of replaying missed wall time',()=>{
  const sim=create();
  try{sim.lastClock-=10000;const state=sim.state();assert.ok(state.simulation_time<=.05000001);assert.ok(state.metrics.physics_steps<=25)}finally{sim.dispose()}
});

test('actual contact dynamics lift and hold the free phone, then release it under gravity',()=>{
  const sim=create();
  try{
    assertNoObjectAttachments(sim);
    const start=sim.command('pickup_demo');assert.equal(start.metrics.pickup.collision_samples,300);
    advanceUntil(sim,state=>state.metrics.pickup.bilateral_hold_s>10);
    const held=sim.advance(0);assert.equal(held.metrics.pickup.success,true);
    assert.equal(held.metrics.pickup.bilateral_contact,true);assert.ok(held.metrics.pickup.height_gain_m>.20);
    assert.ok(held.metrics.pickup.bilateral_hold_s>10);assert.equal(held.metrics.object_attached,false);
    assert.ok(held.metrics.pickup.normal_forces_n.left_finger_1>.01);
    assert.ok(held.metrics.pickup.normal_forces_n['left_finger_-1']>.01);
    assert.throws(()=>sim.command('joint_demo'),/Release the phone/);
    const releasing=sim.command('release_phone');assert.equal(releasing.metrics.pickup.success,false);assert.equal(releasing.metrics.grasp_success,false);assert.equal(releasing.metrics.pickup.bilateral_hold_s,0);for(let i=0;i<2;i++)sim.advance(2);
    const released=sim.advance(0);assert.equal(released.metrics.pickup.released,true);
    assert.equal(released.metrics.pickup.success,false);assert.equal(released.metrics.pickup.ever_succeeded,true);
    assert.ok(held.bodies.phone.position[2]-released.bodies.phone.position[2]>.20);
    assert.equal(released.metrics.grasp_success,false);assert.deepEqual(released.metrics.contacts,[]);
    evidence.pickup_held=held.metrics.pickup;evidence.released=released.metrics.pickup;
  }finally{sim.dispose()}
});

test('vertical carriages traverse 84 cm while hands reach low and high without collision',()=>{
  const sim=create();
  try{
    sim.command('lift_demo');for(let i=0;i<14;i++){const step=sim.advance(2);assert.equal(step.paused,false,step.metrics.stop_reason)}
    const final=sim.advance(0);assert.equal(final.metrics.lift.complete,true);
    for(const side of ['left','right']){
      assert.ok(final.metrics.lift.travel_m[side]>.83);
      assert.ok(final.metrics.lift.min_hand_height_m[side]<.15);
      assert.ok(final.metrics.lift.max_hand_height_m[side]>1.70);
      assert.ok(Math.abs(final.metrics.lift.positions_m[side])<.01);
    }
    assert.deepEqual(final.metrics.contacts,[]);
    evidence.vertical_travel=final.metrics.lift;
  }finally{sim.dispose()}
});

test('fixture checks reject moved starts and unconfirmed release without teleporting bodies',()=>{
  const sim=create();
  try{
    assert.throws(()=>sim.command('release_phone'),/confirmed bilateral/);
    sim.command('joint_demo');sim.advance(1);const before=sim.advance(0);
    assert.throws(()=>sim.command('pickup_demo'),/Reset the scene/);
    assert.deepEqual(sim.advance(0).bodies,before.bodies);
    sim.command('reset');const plan=sim.solvePose(Array.from(sim.data.qpos),[.63,-.72,.96]);
    assert.ok(plan.position_error_m<.0003);assert.ok(plan.orientation_error_rad<.003);
  }finally{sim.dispose()}
});

test('an actual collision during a held pickup clears success and latches the stop',()=>{
  const sim=create();
  try{
    sim.command('pickup_demo');advanceUntil(sim,state=>state.metrics.pickup.success);
    assert.equal(sim.advance(0).metrics.pickup.success,true);
    sim.data.qpos[sim.qindex('right_joint_1')]=-2;sim.data.qpos[sim.qindex('right_joint_2')]=1/3;
    engine.mj_forward(sim.model,sim.data);const stopped=sim.advance(.002);
    assert.equal(stopped.paused,true);assert.equal(stopped.metrics.stop_reason,'Synthetic contact stop');
    assert.equal(stopped.metrics.pickup.success,false);assert.equal(stopped.metrics.grasp_success,false);
    assert.equal(stopped.metrics.pickup.status,'stopped');assert.equal(stopped.metrics.pickup.ever_succeeded,true);
    assert.throws(()=>sim.command('pause'),/Reset the scene/);
    const reset=sim.command('reset');assert.equal(reset.metrics.stop_reason,null);assert.equal(reset.paused,false);
    evidence.contact_stop=stopped.metrics;
  }finally{sim.dispose()}
});

for(const command of ['bedside_demo','greeting_demo','phone_return_demo']){
  test(`${command} completes from actual WASM motion and measured outcomes`,()=>{
    const sim=create();
    try{
      const start=sim.command(command);assert.equal(start.mode,command);assert.equal(start.metrics.demo.complete,false);
      assert.equal(start.metrics.demo.stage_count,trajectories.commands[command].stages.length);
      assert.equal(start.metrics.demo.duration_s,trajectories.commands[command].duration_s);
      advanceUntil(sim,state=>state.metrics.demo.complete,start.metrics.demo.duration_s+3);
      const state=sim.advance(0),demo=state.metrics.demo,measured=demo.measurements;
      assert.equal(demo.complete,true,JSON.stringify(demo));assert.equal(demo.status,'complete');assert.equal(demo.progress,1);
      assert.equal(demo.stage_index,demo.stage_count-1);assert.ok(Object.values(demo.checks).every(Boolean));assert.ok(measured.settle_dwell_s>=.5);
      assert.ok(measured.rest_qpos_error<.01);assert.ok(measured.robot_speed<.01);
      assert.ok(state.metrics.physics_steps>=start.metrics.demo.duration_s*500);assert.equal(state.metrics.object_attached,false);
      if(command==='bedside_demo'){assert.ok(measured.max_base_excursion_m>.75);assert.equal(measured.visited_bedside,true);assert.ok(measured.base_home_error_m<.01)}
      if(command==='greeting_demo'){assert.ok(measured.max_hand_height_m>1.65);assert.ok(measured.wave_range_rad>.65)}
      if(command==='phone_return_demo'){
        assertNoObjectAttachments(sim);assert.equal(state.metrics.pickup.ever_succeeded,true);assert.equal(state.metrics.pickup.success,false);assert.equal(state.metrics.pickup.released,true);
        assert.equal(measured.gate_bilateral_contact_passed,true);assert.equal(measured.gate_grasp_confirmed_passed,true);assert.equal(measured.gate_phone_supported_passed,true);assert.equal(measured.gate_phone_settled_passed,true);
        assert.ok(measured.confirmed_grasp_height_m>.20);assert.ok(measured.confirmed_grasp_hold_s>=2);
        assert.ok(measured.supported_release_force_n>.05);assert.equal(measured.supported_release_bilateral,true);assert.ok(Math.abs(measured.supported_release_height_m-.8135)<.006);
        assert.ok(measured.phone_xy_error_m<.002);assert.ok(measured.phone_z_error_m<.0001);assert.ok(measured.phone_speed_m_s<.001);assert.ok(measured.hand_clearance_m>.7);
        assert.deepEqual(state.metrics.pickup.finger_contacts,[]);assert.equal(state.metrics.grasp_success,false);
      }
      evidence.more_demos??={};evidence.more_demos[command]=demo;
    }finally{sim.dispose()}
  });
}

test('incompatible or malformed demo libraries are rejected before live control mutation',()=>{
  const invalid=[
    library=>{library.model_hash='0'.repeat(64)},
    library=>{library.nq=31},
    library=>{library.actuated_q_indices.reverse()},
    library=>{library.commands.bedside_demo.stages[2].target_qpos[0]=NaN},
    library=>{library.commands.bedside_demo.stages[2].target_qpos[library.actuated_q_indices[library.position_actuator_indices[0]]]=999},
    library=>{library.position_actuator_indices.reverse()},
    library=>{library.commands.bedside_demo.stages.find(stage=>stage.navigation).navigation.kind='strafe'},
    library=>{library.commands.bedside_demo.stages[2].duration_s=0},
  ];
  for(const mutate of invalid){
    const library=structuredClone(trajectories);mutate(library);const sim=create(library);
    try{const before=sim.advance(0),ctrl=Array.from(sim.data.ctrl);assert.throws(()=>sim.command('bedside_demo'),/match|Invalid|limits/);assert.deepEqual(sim.advance(0),before);assert.deepEqual(Array.from(sim.data.ctrl),ctrl)}finally{sim.dispose()}
  }
});

test('new demos require the baseline fixture and pause freezes progress and physics',()=>{
  const sim=create();
  try{
    sim.command('joint_demo');sim.advance(1);const moved=sim.advance(0);
    for(const command of ['bedside_demo','greeting_demo','phone_return_demo'])assert.throws(()=>sim.command(command),/Reset the scene/);
    assert.deepEqual(sim.advance(0),moved);sim.command('reset');sim.command('bedside_demo');sim.advance(2);
    const paused=sim.command('pause');assert.deepEqual(sim.advance(2),paused);assert.throws(()=>sim.command('greeting_demo'),/Reset the scene/);
    sim.command('pause');advanceUntil(sim,state=>state.metrics.demo.complete);
    const reset=sim.command('reset');assert.equal(reset.metrics.demo,undefined);assert.equal(reset.mode,'idle');assert.equal(reset.simulation_time,0);
  }finally{sim.dispose()}
});

test('a lost physical grasp stops the return sequence before it can claim placement',()=>{
  const sim=create();
  try{
    sim.command('phone_return_demo');advanceUntil(sim,state=>state.metrics.pickup.success);
    const lifted=sim.advance(0);assert.equal(lifted.metrics.pickup.bilateral_contact,true);assert.ok(lifted.metrics.pickup.height_gain_m>.20);
    // Regression fault injection opens the fingers; production never edits qpos.
    for(const sign of [-1,1])sim.data.qpos[sim.qindex(`left_gripper_${sign}`)]=sign*.60;
    engine.mj_forward(sim.model,sim.data);const stopped=sim.advance(.002);
    assert.equal(stopped.paused,true);assert.match(stopped.metrics.stop_reason,/contact lost/);
    assert.equal(stopped.metrics.demo.complete,false);assert.equal(stopped.metrics.demo.status,'stopped');assert.equal(stopped.metrics.pickup.success,false);
    assert.throws(()=>sim.command('pause'),/Reset the scene/);assert.equal(stopped.metrics.demo.measurements.gate_phone_supported_passed,undefined);
  }finally{sim.dispose()}
});

test('elapsed trajectory time cannot fake an unmet measured greeting outcome',()=>{
  const library=structuredClone(trajectories);library.commands.greeting_demo.outcomes.minimum_wave_range_rad=2;
  const sim=create(library);
  try{
    sim.command('greeting_demo');for(let i=0;i<8;i++)sim.advance(2);
    const elapsed=sim.advance(0);assert.equal(elapsed.metrics.demo.progress,1);assert.equal(elapsed.metrics.demo.complete,false);assert.equal(elapsed.metrics.demo.checks.wrist_waved,false);
    sim.advance(2);const stopped=sim.advance(2);assert.equal(stopped.paused,true);assert.equal(stopped.metrics.demo.status,'stopped');assert.match(stopped.metrics.stop_reason,/grace period/);
  }finally{sim.dispose()}
});

test('a changed physical pose revokes a previously completed demo and latches reset',()=>{
  const sim=create();
  try{
    sim.command('bedside_demo');advanceUntil(sim,state=>state.metrics.demo.complete);
    sim.data.qpos[sim.qindex('right_joint_1')]=-2;sim.data.qpos[sim.qindex('right_joint_2')]=1/3;engine.mj_forward(sim.model,sim.data);
    const stopped=sim.advance(.002);assert.equal(stopped.paused,true);assert.equal(stopped.metrics.demo.complete,false);assert.equal(stopped.metrics.demo.status,'stopped');
    assert.ok(stopped.metrics.stop_reason);assert.throws(()=>sim.command('pause'),/Reset the scene/);const reset=sim.command('reset');assert.equal(reset.metrics.demo,undefined);assert.equal(reset.metrics.stop_reason,null);
  }finally{sim.dispose()}
});

for(const command of ['deliver_phone_demo','deliver_meal_demo','blinds_demo']){
  test(`${command} performs physical assistance and returns the robot to rest`,()=>{
    const sim=create();
    try{
      const definition=trajectories.commands[command],start=sim.command(command);
      assert.equal(start.metrics.demo.complete,false);assertNoObjectAttachments(sim);
      const stopIndex=definition.stages.findIndex(stage=>stage.name==='press_blinds_control');assert.equal(start.metrics.demo.measurements.collision_samples,(command==='blinds_demo'?stopIndex:definition.stages.length)*60);
      advanceUntil(sim,state=>state.metrics.demo.complete,start.metrics.demo.duration_s+3);
      const final=sim.advance(0),demo=final.metrics.demo,measured=demo.measurements;
      assert.equal(demo.complete,true,JSON.stringify(demo));assert.equal(demo.status,'complete');assert.equal(demo.progress,1);assert.ok(Object.values(demo.checks).every(Boolean));
      assert.ok(measured.rest_qpos_error<.01);assert.ok(measured.settle_dwell_s>=.5);assert.equal(final.metrics.object_attached,false);
      if(command==='blinds_demo'){
        assert.ok(measured.handle_travel_m>.15);assert.ok(measured.minimum_slat_angle_rad>1.10);assert.ok(measured.maximum_control_contact_force_n>.05);assert.equal(measured.gate_blinds_open_passed,true);
        assert.ok(final.object_joints.blinds_slide>.15);assert.ok(Object.entries(final.object_joints).filter(([name])=>name.startsWith('blinds_tilt_')).every(([,value])=>value>1.10));
      }else{
        const object=definition.object_name;
        assert.ok(measured.confirmed_grasp_height_m>.15);assert.ok(measured.confirmed_grasp_hold_s>=2);assert.equal(measured.supported_release_bilateral,true);assert.ok(measured.supported_release_force_n>.05);
        for(const gate of ['assist_bilateral','assist_grasped','assist_supported','assist_released'])assert.equal(measured[`gate_${gate}_passed`],true);
        assert.ok(measured.object_xy_error_m<.025);assert.ok(measured.object_z_error_m<.008);assert.ok(measured.object_speed_m_s<.04);assert.ok(measured.support_force_n>.05);assert.ok(measured.hand_clearance_m>.12);assert.ok(measured.patient_hand_distance_m<=.55);
        assert.equal(measured.fingers_clear,true);assert.ok(Math.hypot(...final.bodies[object].position.map((value,i)=>value-definition.source_position[i]))>1.5);
      }
      evidence.assistance??={};evidence.assistance[command]=demo;
    }finally{sim.dispose()}
  });
}

test('tracking-loss pause is idempotent and preserves physical grip actuator targets',()=>{
  const sim=create();
  try{
    sim.command('pickup_demo');advanceUntil(sim,state=>state.metrics.pickup.success);assert.equal(sim.advance(0).metrics.pickup.success,true);
    const controls=Array.from(sim.data.ctrl),paused=sim.command('pause_for_tracking');
    assert.equal(paused.paused,true);assert.equal(paused.metrics.visual_tracking_pause_reason,'Visual tracking lost');assert.deepEqual(Array.from(sim.data.ctrl),controls);
    assert.deepEqual(sim.command('pause_for_tracking'),paused);assert.deepEqual(sim.advance(2),paused);
    const resumed=sim.command('pause');assert.equal(resumed.paused,false);assert.equal(resumed.metrics.visual_tracking_pause_reason,null);assert.equal(sim.advance(1).metrics.pickup.success,true);
    assert.equal(sim.command('reset').metrics.visual_tracking_pause_reason,null);
  }finally{sim.dispose()}
});

test('assistance rejects moved meal, passive mechanism changes, and contact-allowlist tampering',()=>{
  for(const changed of ['meal','blinds']){
    const sim=create();
    try{
      if(changed==='meal'){const joint=engine.mj_name2id(sim.model,engine.mjtObj.mjOBJ_JOINT.value,'meal_box_free');sim.data.qpos[sim.model.jnt_qposadr[joint]]+=.04}else sim.data.qpos[sim.qindex('blinds_slide')]=.04;
      engine.mj_forward(sim.model,sim.data);const before=sim.advance(0),controls=Array.from(sim.data.ctrl);
      assert.throws(()=>sim.command('deliver_meal_demo'),/Reset the scene/);assert.deepEqual(sim.advance(0),before);assert.deepEqual(Array.from(sim.data.ctrl),controls);
    }finally{sim.dispose()}
  }
  const library=structuredClone(trajectories);library.commands.deliver_meal_demo.intentional_contacts.push(['meal_box_geom','patient_torso']);const sim=create(library);
  try{const before=sim.advance(0);assert.throws(()=>sim.command('deliver_meal_demo'),/intentional contact/);assert.deepEqual(sim.advance(0),before);assert.equal(sim.intentionalContacts.size,0)}finally{sim.dispose()}
});

test('a carried object striking an unapproved surface stops assistance',()=>{
  const sim=create();
  try{
    sim.command('deliver_phone_demo');advanceUntil(sim,state=>state.metrics.demo.measurements.ever_grasped);
    assert.equal(sim.advance(0).metrics.demo.measurements.ever_grasped,true);
    // Simulate an unexpected obstacle at the held object's current location.
    const position=sim.advance(0).bodies.phone.position,geom=engine.mj_name2id(sim.model,engine.mjtObj.mjOBJ_GEOM.value,'visitor_chair');
    sim.model.geom_pos.set(position,geom*3);engine.mj_forward(sim.model,sim.data);
    assert.ok(sim.contacts().some(contact=>contact.carried_object_collision),'Actual object contact must be recognized independently of robot contact');
    const stopped=sim.advance(.002);assert.equal(stopped.paused,true);assert.equal(stopped.metrics.demo.complete,false);assert.equal(stopped.metrics.demo.status,'stopped');assert.ok(stopped.metrics.stop_reason);
    assert.throws(()=>sim.command('pause_for_tracking'),/Reset the scene/);
  }finally{sim.dispose()}
});
