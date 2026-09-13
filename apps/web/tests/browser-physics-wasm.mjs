/** Run with `node --test tests/browser-physics-wasm.mjs` from apps/web.
 * Uses the real official WASM package and authoritative reference assets.
 */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import loadMujoco from '@mujoco/mujoco';

const source=readFileSync(new URL('../src/browserPhysicsCore.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {BrowserPhysics}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const engine=await loadMujoco();
const xml=readFileSync(new URL('../public/simulation/reference.xml',import.meta.url),'utf8');
const descriptors=JSON.parse(readFileSync(new URL('../public/simulation/reference-descriptors.json',import.meta.url),'utf8'));
const create=()=>new BrowserPhysics(engine,xml,descriptors);

test('native reference XML compiles in official WASM with matching body topology',()=>{
  const sim=create();
  try{
    const state=sim.advance(0);
    assert.equal(state.engine,'mujoco-wasm');assert.equal(state.engine_version,'3.13.0');
    assert.equal(Object.keys(state.bodies).length,27);assert.equal(Object.keys(state.joints).length,25);
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
    assert.ok(Math.abs(final.metrics.reach.actual_endpoint_error_m-.000317791668950957)<1e-9);
    assert.equal(final.metrics.physics_steps,3000);assert.deepEqual(final.metrics.contacts,[]);
    assert.equal(final.metrics.object_attached,false);assert.equal(final.metrics.grasp_success,null);
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
