/** Closed-loop failure regression against the actual official MuJoCo WASM engine. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import loadMujoco from '@mujoco/mujoco';

const compile=path=>ts.transpileModule(readFileSync(new URL(path,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const asUrl=source=>`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
const core=compile('../src/browserPhysicsCore.ts').replace("'./browserDrive'",JSON.stringify(asUrl(compile('../src/browserDrive.ts'))));
const {BrowserPhysics}=await import(asUrl(core));
const engine=await loadMujoco();
const xml=readFileSync(new URL('../public/simulation/reference.xml',import.meta.url),'utf8');
const descriptors=JSON.parse(readFileSync(new URL('../public/simulation/reference-descriptors.json',import.meta.url),'utf8'));
const trajectories=JSON.parse(readFileSync(new URL('../../../sim/reference_demo_trajectories.json',import.meta.url),'utf8'));

test('loss of tire traction stops an unmet navigation waypoint without claiming the task completed',()=>{
  const sim=new BrowserPhysics(engine,xml,descriptors,trajectories);
  try{
    // Remove propulsion only as a fault injection; production never changes tire friction.
    for(const name of ['floor','left_wheel_geom','right_wheel_geom']){
      const geom=engine.mj_name2id(sim.model,engine.mjtObj.mjOBJ_GEOM.value,name);
      sim.model.geom_friction.set([0,0,0],geom*3);
    }
    const started=sim.command('bedside_demo');let state=started;
    for(let elapsed=0;!state.paused&&elapsed<20;elapsed+=.5)state=sim.advance(.5);
    assert.equal(state.paused,true);assert.match(state.metrics.stop_reason,/Navigation stopped: wheel-driven goal not reached/);
    assert.equal(state.metrics.demo.complete,false);assert.equal(state.metrics.demo.status,'stopped');
    assert.ok(Math.hypot(state.joints.base_x,state.joints.base_y)<.01,'No planar servo may move the chassis without traction');
    assert.ok(Math.abs(state.joints.left_wheel_joint)>.1||Math.abs(state.joints.right_wheel_joint)>.1,'Wheel motors actually attempted navigation');
    assert.ok(sim.drive.wheelActuators.every(index=>sim.data.ctrl[index]===0));
    assert.throws(()=>sim.command('pause'),/Reset the scene/);assert.deepEqual(sim.advance(2),state);
    const reset=sim.command('reset');assert.equal(reset.metrics.stop_reason,null);assert.equal(reset.metrics.demo,undefined);
    writeFileSync(new URL('../../../artifacts/browser-drive-fault.json',import.meta.url),JSON.stringify({engine:'MuJoCo 3.13.0 WASM',model_hash:descriptors.model_hash,actual_stopped_state:state,reset_clears_fault:true},null,2)+'\n');
  }finally{sim.dispose()}
});
