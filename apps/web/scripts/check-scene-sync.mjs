/** Dependency-free export/build guard; callable in Vercel without Python. */
import {createHash} from 'node:crypto';
import {existsSync,mkdirSync,readFileSync,readdirSync,writeFileSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const here=dirname(fileURLToPath(import.meta.url));
export const defaultRoot=resolve(here,'../../..');
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const json=path=>JSON.parse(readFileSync(path,'utf8'));
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const requireThat=(condition,message)=>{if(!condition)throw Error(message)};
const glbNames=['room.glb','robot.glb','phone.glb','meal_box.glb'];
const revisionPaths=['../../assets/simulation/room.glb','../../assets/simulation/robot.glb','../../assets/simulation/phone.glb','../../assets/simulation/meal_box.glb','public/simulation/reference.xml','public/simulation/reference-descriptors.json'];

export function glbDocument(file){
  const bytes=readFileSync(file);
  requireThat(bytes.length>=20&&bytes.toString('ascii',0,4)==='glTF'&&bytes.readUInt32LE(4)===2&&bytes.readUInt32LE(8)===bytes.length,'Invalid GLB header');
  const size=bytes.readUInt32LE(12);
  requireThat(bytes.toString('ascii',16,20)==='JSON'&&size%4===0&&20+size<=bytes.length,'Invalid GLB JSON chunk');
  return JSON.parse(bytes.toString('utf8',20,20+size));
}

function validatePoses(document,specs,poses){
  const nodes=document.nodes??[],roots=new Set(document.scenes?.[document.scene??0]?.nodes??[]);
  const parents=new Set(nodes.flatMap(node=>node.children??[]));
  for(const spec of specs){
    const matches=nodes.flatMap((node,index)=>node.name===spec.name?[index]:[]);
    requireThat(matches.length===1,`Expected one active visual body: ${spec.name}`);
    const index=matches[0],node=nodes[index],expected=poses[spec.name];
    requireThat(expected&&roots.has(index)&&!parents.has(index)&&!node.matrix,`Invalid root pose binding: ${spec.name}`);
    const position=node.translation??[0,0,0],scale=node.scale??[1,1,1],q=node.rotation??[0,0,0,1];
    requireThat(position.length===3&&q.length===4&&scale.length===3&&[...position,...q,...scale].every(Number.isFinite),`Invalid pose components: ${spec.name}`);
    requireThat(scale.every(v=>Math.abs(v-1)<=2e-5),`Scaled physics body: ${spec.name}`);
    const wxyz=[q[3],q[0],q[1],q[2]],difference=(a,b,sign=1)=>Math.hypot(...a.map((v,i)=>v-sign*b[i]));
    requireThat(difference(position,expected.position)<=2e-5&&Math.min(difference(wxyz,expected.quaternion),difference(wxyz,expected.quaternion,-1))<=2e-5,`Stale visual body pose: ${spec.name}`);
    requireThat((node.children??[]).some(child=>nodes[child]?.mesh!==undefined),`Missing body visual meshes: ${spec.name}`);
  }
}

export function checkSceneSync(root=defaultRoot){
  const checks=[],inputHashes={};
  const check=(name,operation)=>{try{operation();checks.push({name,passed:true})}catch(error){checks.push({name,passed:false,error:String(error.message??error)})}};
  const read=path=>{const bytes=readFileSync(resolve(root,path));inputHashes[path]=digest(bytes);return bytes};
  let descriptors,library,xml;
  check('browser_engine_version',()=>{
    const declared=JSON.parse(read('apps/web/package.json')).dependencies['@mujoco/mujoco'];
    const locked=JSON.parse(read('apps/web/package-lock.json')).packages['node_modules/@mujoco/mujoco'].version;
    const installed=JSON.parse(read('apps/web/node_modules/@mujoco/mujoco/package.json')).version;
    requireThat(/^\d+\.\d+\.\d+$/.test(declared)&&declared===locked&&declared===installed,'Browser MuJoCo must use the same exact declared, locked and installed version');
  });
  check('native_export_hash',()=>{xml=read('sim/reference_body_descriptors.xml');descriptors=JSON.parse(read('sim/reference_body_descriptors.json'));requireThat(descriptors.model_hash===digest(xml),'Native descriptors do not match exported XML');requireThat(descriptors.hardware_model_verified===false&&descriptors.authorizes_hardware===false,'Unexpected hardware authority')});
  for(const [native,published] of [['reference_body_descriptors.xml','reference.xml'],['reference_body_descriptors.json','reference-descriptors.json']]){
    check(`public_${published}`,()=>requireThat(read(`sim/${native}`).equals(read(`apps/web/public/simulation/${published}`)),`Stale public ${published}; copy freshly exported native fixture`));
  }
  check('trajectory_model_hash',()=>{library=JSON.parse(read('sim/reference_demo_trajectories.json'));requireThat(library.model_hash===descriptors?.model_hash,'Trajectory/model hash mismatch');requireThat(Object.keys(library.commands??{}).length>=1,'Empty trajectory library')});
  for(const filename of glbNames){check(filename,()=>{
    const path=`assets/simulation/${filename}`;read(path);const document=glbDocument(resolve(root,path));
    requireThat((document.meshes??[]).length>0,`No meshes in ${filename}`);
    const specs=descriptors.body_specs;
    if(filename==='room.glb')requireThat(!(document.nodes??[]).some(node=>specs.some(spec=>spec.dynamic_object&&spec.name===node.name)),'Dynamic body duplicated in static room');
    else validatePoses(document,filename==='robot.glb'?specs.filter(spec=>!spec.dynamic_object):specs.filter(spec=>`${spec.name}.glb`===filename),descriptors.initial_world_poses);
  })}
  const sceneHash=createHash('sha256');
  for(const path of revisionPaths){sceneHash.update(path);const file=resolve(root,'apps/web',path);if(existsSync(file))sceneHash.update(readFileSync(file))}
  return {passed:checks.every(check=>check.passed),model_hash:descriptors?.model_hash??null,scene_revision:sceneHash.digest('hex').slice(0,16),input_hashes:inputHashes,checks,
    limitations:['Node compares cached native/public exports; python -m sim.sync_check independently regenerates model and trajectories.','Matching GLB bindings does not prove Blender source-script regeneration.']};
}

function filesUnder(root,directory){
  const base=resolve(root,directory),result=[];
  if(!existsSync(base))return result;
  for(const entry of readdirSync(base,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){
    const path=`${directory}/${entry.name}`;
    if(entry.isDirectory())result.push(...filesUnder(root,path));else if(entry.isFile())result.push(path);
  }
  return result;
}

export function buildInputs(root=defaultRoot){
  const paths=[...filesUnder(root,'apps/web/src'),...filesUnder(root,'apps/web/public'),
    'apps/web/index.html','apps/web/package.json','apps/web/package-lock.json','apps/web/tsconfig.json','apps/web/vite.config.ts',
    'apps/web/scripts/copy-public-assets.mjs','apps/web/scripts/check-scene-sync.mjs','sim/reference_demo_trajectories.json',
    'sim/reference_body_descriptors.json','sim/reference_body_descriptors.xml',...glbNames.map(name=>`assets/simulation/${name}`)];
  // Hash environment files without exposing their contents in the receipt.
  for(const name of ['.env','.env.local','.env.production','.env.production.local','.env.public','.env.public.local'])if(existsSync(resolve(root,'apps/web',name)))paths.push(`apps/web/${name}`);
  return Object.fromEntries([...new Set(paths)].sort().map(path=>[path,digest(readFileSync(resolve(root,path)))]));
}

function modeGuard(root,mode){
  requireThat(['local','public'].includes(mode),'Build mode must be local or public');
  if(mode==='local'){
    requireThat(process.env.VITE_PUBLIC_DEMO!=='1','VITE_PUBLIC_DEMO requests a public build; unset it for the local backend app');
    for(const name of ['.env','.env.local','.env.production','.env.production.local']){
      const file=resolve(root,'apps/web',name);
      if(existsSync(file))requireThat(!/^\s*VITE_PUBLIC_DEMO\s*=\s*["']?1["']?\s*(?:#.*)?$/m.test(readFileSync(file,'utf8')),`${name} requests public demo mode; local backend build refused`);
    }
  }
}

export function prebuild(root,mode){
  modeGuard(root,mode);const report=checkSceneSync(root);requireThat(report.passed,JSON.stringify(report.checks.filter(check=>!check.passed)));
  const file=resolve(root,'apps/web/.cache/scene-sync-inputs.json');mkdirSync(dirname(file),{recursive:true});
  writeFileSync(file,JSON.stringify({mode,inputs:buildInputs(root)},null,2)+'\n');return report;
}

export function recordBuild(root,mode){
  modeGuard(root,mode);const before=json(resolve(root,'apps/web/.cache/scene-sync-inputs.json')),inputs=buildInputs(root);
  requireThat(before.mode===mode&&same(before.inputs,inputs),'Build inputs changed during compilation; rebuild before recording output');
  const report=checkSceneSync(root);requireThat(report.passed,'Scene became stale during build');
  const required=['apps/web/dist/index.html','apps/web/dist/simulation/reference.xml','apps/web/dist/simulation/reference-descriptors.json'];
  if(mode==='public')required.push(...glbNames.map(name=>`apps/web/dist/simulation/${name}`));
  for(const file of required)requireThat(existsSync(resolve(root,file)),`Missing build output: ${file}`);
  const outputs=Object.fromEntries(filesUnder(root,'apps/web/dist').filter(path=>!path.endsWith('/scene-sync-build.json')).sort().map(path=>[path,digest(readFileSync(resolve(root,path)))]));
  const receipt={schema_version:1,mode,model_hash:report.model_hash,scene_revision:report.scene_revision,inputs,outputs};
  writeFileSync(resolve(root,'apps/web/dist/scene-sync-build.json'),JSON.stringify(receipt,null,2)+'\n');return receipt;
}

export function checkBuild(root=defaultRoot,mode='local'){
  const scene=checkSceneSync(root),checks=[...scene.checks];
  try{
    modeGuard(root,mode);const receipt=json(resolve(root,'apps/web/dist/scene-sync-build.json'));
    requireThat(receipt.schema_version===1&&receipt.mode===mode,`Built frontend mode is ${receipt.mode??'unknown'}, expected ${mode}`);
    requireThat(same(receipt.inputs,buildInputs(root)),'Built frontend inputs are stale; run the matching npm build');
    requireThat(receipt.model_hash===scene.model_hash&&receipt.scene_revision===scene.scene_revision,'Built model/scene revision is stale');
    requireThat(same(Object.keys(receipt.outputs??{}).sort(),filesUnder(root,'apps/web/dist').filter(path=>!path.endsWith('/scene-sync-build.json')).sort()),'Built output inventory differs from its receipt');
    for(const [path,expected] of Object.entries(receipt.outputs))requireThat(digest(readFileSync(resolve(root,path)))===expected,`Changed/missing build output: ${path}`);
    checks.push({name:'frontend_build_receipt',passed:true});
  }catch(error){checks.push({name:'frontend_build_receipt',passed:false,error:String(error.message??error)})}
  return {...scene,passed:checks.every(check=>check.passed),build_mode:mode,checks};
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const [action,mode]=process.argv.slice(2);
  try{
    const report=action==='--prebuild'?prebuild(defaultRoot,mode):action==='--record-build'?recordBuild(defaultRoot,mode):action==='--check-build'?checkBuild(defaultRoot,mode):checkSceneSync(defaultRoot);
    console.log(JSON.stringify(action==='--record-build'?{passed:true,mode:report.mode,model_hash:report.model_hash,scene_revision:report.scene_revision,input_count:Object.keys(report.inputs).length,output_count:Object.keys(report.outputs).length}:report));if(report.passed===false)process.exitCode=1;
  }catch(error){console.log(JSON.stringify({passed:false,error:String(error.message??error)}));process.exitCode=1}
}
