/** Corruption tests; build receipts here are synthetic fixtures, not app builds. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {copyFileSync,mkdirSync,mkdtempSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {dirname,resolve,sep} from 'node:path';
import {checkSceneSync,checkBuild,defaultRoot,prebuild,recordBuild} from '../scripts/check-scene-sync.mjs';

const scratch=resolve(defaultRoot,'.cache/scene-sync-node-tests');mkdirSync(scratch,{recursive:true});
function fixture(t){
  const root=mkdtempSync(resolve(scratch,'case-'));
  t.after(()=>{assert(root.startsWith(scratch+sep));rmSync(root,{recursive:true,force:true})});
  const paths=['sim/reference_body_descriptors.xml','sim/reference_body_descriptors.json','sim/reference_demo_trajectories.json',
    'apps/web/public/simulation/reference.xml','apps/web/public/simulation/reference-descriptors.json',
    ...['room.glb','robot.glb','phone.glb','meal_box.glb'].map(name=>`assets/simulation/${name}`),
    'apps/web/index.html','apps/web/package.json','apps/web/package-lock.json','apps/web/tsconfig.json','apps/web/vite.config.ts',
    'apps/web/node_modules/@mujoco/mujoco/package.json',
    'apps/web/scripts/copy-public-assets.mjs','apps/web/scripts/check-scene-sync.mjs'];
  for(const path of paths){const target=resolve(root,path);mkdirSync(dirname(target),{recursive:true});copyFileSync(resolve(defaultRoot,path),target)}
  mkdirSync(resolve(root,'apps/web/src'),{recursive:true});writeFileSync(resolve(root,'apps/web/src/main.ts'),'export const fixture = 1;\n');
  return root;
}
function outputs(root){
  const target=resolve(root,'apps/web/dist');mkdirSync(resolve(target,'simulation'),{recursive:true});
  writeFileSync(resolve(target,'index.html'),'<script src="/bundle.js"></script>');writeFileSync(resolve(target,'bundle.js'),'console.log("synthetic receipt test")');
  for(const name of ['reference.xml','reference-descriptors.json'])copyFileSync(resolve(root,'apps/web/public/simulation',name),resolve(target,'simulation',name));
}

test('current checked-in model exports and all actual GLBs pass the lightweight guard',()=>{
  const result=checkSceneSync(defaultRoot);assert.equal(result.passed,true,JSON.stringify(result.checks));
  assert.equal(result.scene_revision.length,16);assert.equal(result.model_hash.length,64);
});
test('a stale public XML is rejected before build',t=>{
  const root=fixture(t);writeFileSync(resolve(root,'apps/web/public/simulation/reference.xml'),'<mujoco/>');
  assert.equal(checkSceneSync(root).passed,false);assert.throws(()=>prebuild(root,'local'),/reference.xml/);
});
test('a mismatched trajectory model token is rejected',t=>{
  const root=fixture(t),file=resolve(root,'sim/reference_demo_trajectories.json'),data=JSON.parse(readFileSync(file));
  data.model_hash='0'.repeat(64);writeFileSync(file,JSON.stringify(data));
  assert(checkSceneSync(root).checks.some(check=>check.name==='trajectory_model_hash'&&!check.passed));
});
test('a detached or displaced GLB body is rejected using actual descriptor poses',t=>{
  const root=fixture(t),path=resolve(root,'assets/simulation/phone.glb'),original=readFileSync(path),oldLength=original.readUInt32LE(12);
  const document=JSON.parse(original.toString('utf8',20,20+oldLength));document.nodes.find(node=>node.name==='phone').translation[2]+=.10;
  const text=Buffer.from(JSON.stringify(document)),padded=Buffer.concat([text,Buffer.alloc((4-text.length%4)%4,32)]),header=Buffer.from(original.subarray(0,20));
  const remainder=original.subarray(20+oldLength);header.writeUInt32LE(20+padded.length+remainder.length,8);header.writeUInt32LE(padded.length,12);
  writeFileSync(path,Buffer.concat([header,padded,remainder]));
  const result=checkSceneSync(root);assert(result.checks.some(check=>check.name==='phone.glb'&&!check.passed&&check.error.includes('pose')));
});
test('a build cannot record a fresh receipt if sources change during compilation',t=>{
  const root=fixture(t);prebuild(root,'local');outputs(root);writeFileSync(resolve(root,'apps/web/src/main.ts'),'export const fixture = 2;');
  assert.throws(()=>recordBuild(root,'local'),/changed during compilation/);
});
test('receipts distinguish local/public mode and detect changed compiled output',t=>{
  const root=fixture(t);prebuild(root,'local');outputs(root);recordBuild(root,'local');
  assert.equal(checkBuild(root,'local').passed,true);assert.equal(checkBuild(root,'public').passed,false);
  writeFileSync(resolve(root,'apps/web/dist/bundle.js'),'outdated or replaced bundle');
  assert.equal(checkBuild(root,'local').passed,false);
});
test('a source added after build invalidates the receipt even when all existing file hashes match',t=>{
  const root=fixture(t);prebuild(root,'local');outputs(root);recordBuild(root,'local');
  writeFileSync(resolve(root,'apps/web/src/new-control.ts'),'export const changed = true;');
  assert.equal(checkBuild(root,'local').passed,false);
});
test('a local launch cannot accept a build configured to force public mode',t=>{
  const root=fixture(t);writeFileSync(resolve(root,'apps/web/.env.local'),'VITE_PUBLIC_DEMO=1\n');
  assert.throws(()=>prebuild(root,'local'),/requests public demo mode/);
});
test('an installed browser engine different from its pinned dependency is rejected',t=>{
  const root=fixture(t),path=resolve(root,'apps/web/node_modules/@mujoco/mujoco/package.json');
  const packageData=JSON.parse(readFileSync(path));packageData.version='99.0.0';writeFileSync(path,JSON.stringify(packageData));
  assert(checkSceneSync(root).checks.some(check=>check.name==='browser_engine_version'&&!check.passed));
});
