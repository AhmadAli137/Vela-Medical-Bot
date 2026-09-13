/** Run with `node --test tests/browser-physics-wasm.mjs` from apps/web.
 * Uses the real official WASM package and authoritative reference assets.
 */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import test,{after} from 'node:test';
import ts from 'typescript';
import loadMujoco from '@mujoco/mujoco';

const source=readFileSync(new URL('../src/browserPhysicsCore.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {BrowserPhysics}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const engine=await loadMujoco();
const xml=readFileSync(new URL('../public/simulation/reference.xml',import.meta.url),'utf8');
const descriptors=JSON.parse(readFileSync(new URL('../public/simulation/reference-descriptors.json',import.meta.url),'utf8'));
const trajectories=JSON.parse(readFileSync(new URL('../../../sim/reference_demo_trajectories.json',import.meta.url),'utf8'));
const create=(library=trajectories)=>new BrowserPhysics(engine,xml,descriptors,library);
const evidence={engine:'MuJoCo 3.13.0 WebAssembly',model_hash:descriptors.model_hash};
after(()=>writeFileSync(new URL('../../../artifacts/browser-contact-physics.json',import.meta.url),JSON.stringify(evidence,null,2)+'\n'));

test('native reference XML compiles in official WASM with matching body topology',()=>{
  const sim=create();
  try{
    const state=sim.advance(0);
    assert.equal(state.engine,'mujoco-wasm');assert.equal(state.engine_version,'3.13.0');
    assert.equal(Object.keys(state.bodies).length,28);assert.equal(Object.keys(state.joints).length,25);
    assert.equal(state.hardware_model_verified,false);assert.equal(state.authorizes_hardware,false);
    for(const [name,pose]of Object.entries(state.bodies)){
      const expected=descriptors.initial_world_poses[name];
      assert.ok(pose.position.every((value,i)=>Math.abs(value-expected.position[i])<1e-12));
      assert.ok(pose.quaternion.every((value,i)=>Math.abs(value-expected.quaternion[i])<1e-12));
    }
  }finally{sim.dispose()}
});

test('actual forward dynamics actuates all 25 DOFs over a 16 second contact-free cycle',()=>{
  const sim=create();
  try{
    const original=sim.advance(0).joints;sim.command('joint_demo');let state;
    for(let i=0;i<8;i++){state=sim.advance(2);assert.equal(state.paused,false);assert.deepEqual(state.metrics.contacts,[])}
    assert.equal(state.metrics.physics_steps,8000);assert.ok(state.metrics.finite_dynamics);
    for(const [name,value]of Object.entries(state.joints))assert.ok(Math.abs(value-original[name])>.0001,name);
  }finally{sim.dispose()}
});

test('runtime WASM Jacobian IK and actual servo tracking match native endpoint evidence',()=>{
  const sim=create();
  try{
    const initial=sim.command('reach_demo');assert.equal(initial.metrics.reach.endpoint_reached,false);
    assert.equal(initial.metrics.reach.samples,60);assert.ok(initial.metrics.reach.sampled_collision_gate_passed);
    for(let i=0;i<3;i++)sim.advance(2);
    const final=sim.advance(0);assert.ok(final.metrics.reach.endpoint_reached);
    assert.ok(Math.abs(final.metrics.reach.actual_endpoint_error_m-.00031753621456)<1e-9);
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
    assert.equal(sim.model.neq,0,'No attachment constraints may be present');
    const start=sim.command('pickup_demo');assert.equal(start.metrics.pickup.collision_samples,240);
    for(let i=0;i<16;i++){const step=sim.advance(2);assert.equal(step.paused,false,step.metrics.stop_reason)}
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
    sim.command('pickup_demo');for(let i=0;i<10;i++)sim.advance(2);
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

for(const [command,seconds]of [['bedside_demo',16],['greeting_demo',16],['phone_return_demo',38]]){
  test(`${command} completes from actual WASM motion and measured outcomes`,()=>{
    const sim=create();
    try{
      const start=sim.command(command);assert.equal(start.mode,command);assert.equal(start.metrics.demo.complete,false);
      assert.equal(start.metrics.demo.stage_count,trajectories.commands[command].stages.length);
      assert.equal(start.metrics.demo.duration_s,trajectories.commands[command].duration_s);
      for(let i=0;i<seconds/2;i++){const step=sim.advance(2);assert.equal(step.paused,false,`${step.metrics.stop_reason}: ${JSON.stringify(step.metrics.demo)}`);assert.deepEqual(step.metrics.contacts,[])}
      const state=sim.advance(0),demo=state.metrics.demo,measured=demo.measurements;
      assert.equal(demo.complete,true,JSON.stringify(demo));assert.equal(demo.status,'complete');assert.equal(demo.progress,1);
      assert.equal(demo.stage_index,demo.stage_count-1);assert.ok(Object.values(demo.checks).every(Boolean));assert.ok(measured.settle_dwell_s>=.5);
      assert.ok(measured.rest_qpos_error<.01);assert.ok(measured.robot_speed<.01);
      assert.equal(state.metrics.physics_steps,seconds*500);assert.equal(state.metrics.object_attached,false);
      if(command==='bedside_demo'){assert.ok(measured.max_base_excursion_m>.75);assert.equal(measured.visited_bedside,true);assert.ok(measured.base_home_error_m<.01)}
      if(command==='greeting_demo'){assert.ok(measured.max_hand_height_m>1.65);assert.ok(measured.wave_range_rad>.65)}
      if(command==='phone_return_demo'){
        assert.equal(sim.model.neq,0);assert.equal(state.metrics.pickup.ever_succeeded,true);assert.equal(state.metrics.pickup.success,false);assert.equal(state.metrics.pickup.released,true);
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
    library=>{library.commands.bedside_demo.stages[2].target_qpos[library.actuated_q_indices[0]]=999},
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
    sim.command('pause');for(let i=0;i<7;i++)sim.advance(2);assert.equal(sim.advance(0).metrics.demo.complete,true);
    const reset=sim.command('reset');assert.equal(reset.metrics.demo,undefined);assert.equal(reset.mode,'idle');assert.equal(reset.simulation_time,0);
  }finally{sim.dispose()}
});

test('a lost physical grasp stops the return sequence before it can claim placement',()=>{
  const sim=create();
  try{
    sim.command('phone_return_demo');for(let i=0;i<9;i++)sim.advance(2);
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
    sim.command('bedside_demo');for(let i=0;i<8;i++)sim.advance(2);assert.equal(sim.advance(0).metrics.demo.complete,true);
    sim.data.qpos[sim.qindex('right_joint_1')]=-2;sim.data.qpos[sim.qindex('right_joint_2')]=1/3;engine.mj_forward(sim.model,sim.data);
    const stopped=sim.advance(.002);assert.equal(stopped.paused,true);assert.equal(stopped.metrics.demo.complete,false);assert.equal(stopped.metrics.demo.status,'stopped');
    assert.ok(stopped.metrics.stop_reason);assert.throws(()=>sim.command('pause'),/Reset the scene/);const reset=sim.command('reset');assert.equal(reset.metrics.demo,undefined);assert.equal(reset.metrics.stop_reason,null);
  }finally{sim.dispose()}
});
