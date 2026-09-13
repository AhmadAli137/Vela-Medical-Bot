import loadMujoco from '@mujoco/mujoco';
import wasmUrl from '@mujoco/mujoco/mujoco.wasm?url';
import {BrowserPhysics,type ReferenceDescriptors,type DemoTrajectories} from './browserPhysicsCore';
import demoTrajectories from '../../../sim/reference_demo_trajectories.json';
import {physicsAsset} from './deployment';

export {BrowserPhysics};
export type {BrowserPhysicsState,PhysicsCommand,ReferenceDescriptors,DemoMetrics,DemoTrajectories,CameraPose} from './browserPhysicsCore';

/** Load same-origin MJCF + descriptors and the bundled official WASM engine. */
export async function createBrowserPhysics(options:{modelUrl?:string;descriptorsUrl?:string}={}):Promise<BrowserPhysics>{
  const responses=await Promise.all([
    fetch(options.modelUrl??physicsAsset('reference.xml')),
    fetch(options.descriptorsUrl??physicsAsset('reference-descriptors.json')),
  ]);
  if(responses.some(response=>!response.ok))throw new Error('Reference physics assets could not be loaded');
  const [xml,descriptors]=await Promise.all([responses[0].text(),responses[1].json() as Promise<ReferenceDescriptors>]);
  const engine=await loadMujoco({locateFile:(file:string)=>file.endsWith('.wasm')?wasmUrl:file});
  // Runtime compatibility/shape checks run before any shared command is applied.
  return new BrowserPhysics(engine,xml,descriptors,demoTrajectories as unknown as DemoTrajectories);
}
