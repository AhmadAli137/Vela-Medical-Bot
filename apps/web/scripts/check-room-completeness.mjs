import {createServer} from 'node:http';
import {readFile,stat,mkdir,writeFile} from 'node:fs/promises';
import {dirname,extname,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {chromium,expect} from '@playwright/test';

// Inspect the real production WebGL scene using only its public camera controls.
const webRoot=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const repository=resolve(webRoot,'../..'),output=resolve(webRoot,'dist');
const remote=process.env.VELA_PUBLIC_URL,target=remote||'http://127.0.0.1:4173/';
const capture=process.env.VELA_CAPTURE_NAME||(remote?'vercel-room':'room');
assert(/^[a-z0-9-]+$/.test(capture),'Invalid capture name');
const deployment=JSON.parse(await readFile(resolve(repository,'vercel.json'),'utf8'));
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.json':'application/json','.xml':'application/xml','.wasm':'application/wasm','.glb':'model/gltf-binary','.woff':'font/woff','.woff2':'font/woff2','.svg':'image/svg+xml'};
const server=createServer(async(request,response)=>{
  const pathname=decodeURIComponent(new URL(request.url,'http://localhost').pathname);
  const filename=resolve(output,pathname==='/'?'index.html':`.${pathname}`);
  for(const header of deployment.headers[0].headers)response.setHeader(header.key,header.value);
  if(!filename.startsWith(output+sep)){response.writeHead(403).end();return}
  try{const information=await stat(filename);if(!information.isFile())throw new Error('Not a file');response.writeHead(200,{'Content-Type':mime[extname(filename)]||'application/octet-stream'});response.end(await readFile(filename))}
  catch{response.writeHead(404,{'Content-Type':'text/plain'}).end('Not found')}
});
if(!remote)await new Promise(done=>server.listen(4173,'127.0.0.1',done));
const started=Date.now(),errors=[],failedRequests=[],apiRequests=[],screenshots=[];
const sceneRequests=new Map();
let browser,page;
try{
  await mkdir(resolve(webRoot,'artifacts'),{recursive:true});
  browser=await chromium.launch({channel:'chrome',headless:true});
  const context=await browser.newContext({viewport:{width:1600,height:1000}});
  page=await context.newPage();
  page.on('pageerror',error=>errors.push(String(error)));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text())});
  page.on('requestfailed',request=>failedRequests.push({url:request.url(),error:request.failure()?.errorText}));
  page.on('request',request=>{const url=new URL(request.url());if(url.pathname.startsWith('/api/'))apiRequests.push(request.url());if(url.pathname.startsWith('/simulation/'))sceneRequests.set(url.pathname,url.searchParams.get('v'))});
  const navigation=await page.goto(target,{waitUntil:'networkidle'});
  assert.equal(navigation.status(),200);
  const contentSecurityPolicy=navigation.headers()['content-security-policy'];
  assert(contentSecurityPolicy?.includes("'unsafe-eval'"),'Official MuJoCo bindings require the approved public CSP');
  await expect.poll(async()=>{
    const alerts=await page.getByRole('alert').allTextContents();if(alerts.length)throw new Error(alerts.join('; '));
    return page.getByRole('button',{name:'Joint movement',exact:true}).isEnabled();
  },{timeout:60000}).toBe(true);
  const canvas=page.locator('.immersive-canvas canvas');
  await expect(canvas).toHaveAttribute('data-room-assemblies',/patient/);
  const assemblies=JSON.parse(await canvas.getAttribute('data-room-assemblies'));
  const expected=['patient','hospital_bed','visitor_chair','bedside_table','bedside_storage','wardrobe','visitor_table','room_plant'];
  for(const name of expected){
    const assembly=assemblies[name];assert(assembly,`Missing rendered assembly: ${name}`);
    assert(assembly.mesh_count>0&&assembly.triangle_count>0,`Assembly has no geometry: ${name}`);
    assert([...assembly.bounds.min,...assembly.bounds.max].every(Number.isFinite),`Nonfinite bounds: ${name}`);
    assert(assembly.bounds.max.every((value,i)=>value>assembly.bounds.min[i]),`Empty bounds: ${name}`);
  }
  const patient=assemblies.patient.bounds,bed=assemblies.hospital_bed.bounds;
  assert(patient.max[1]-patient.min[1]>1,'Patient model does not have a full body footprint');
  assert(patient.min[2]>.6,'Patient is below the expected bed surface');
  for(const axis of [0,1]){const center=(patient.min[axis]+patient.max[axis])/2;assert(center>bed.min[axis]&&center<bed.max[axis],'Patient is outside the bed footprint')}
  let manifestComparison;
  try{
    const manifest=JSON.parse(await readFile(resolve(repository,'assets/simulation/room-geometry-manifest.json'),'utf8'));
    manifestComparison={units:manifest.units,assemblies:{}};
    for(const name of expected){
      const records=manifest.objects.filter(item=>item.assembly===name);if(!records.length)continue;
      const minimum=[0,1,2].map(axis=>Math.min(...records.map(item=>item.min[axis])));
      const maximum=[0,1,2].map(axis=>Math.max(...records.map(item=>item.max[axis])));
      const difference=Math.max(...minimum.map((value,i)=>Math.abs(value-assemblies[name].bounds.min[i])),...maximum.map((value,i)=>Math.abs(value-assemblies[name].bounds.max[i])));
      if(name==='room_plant'){
        // Source bounds enclose each rotated leaf's box, so they conservatively
        // overestimate the joined foliage. Compare actual vertices to that envelope.
        const bounds=assemblies[name].bounds;
        const contained=minimum.every((value,i)=>bounds.min[i]>=value-.025)&&maximum.every((value,i)=>bounds.max[i]<=value+.025);
        const relativeExtent=minimum.map((value,i)=>(bounds.max[i]-bounds.min[i])/(maximum[i]-value));
        manifestComparison.assemblies[name]={method:'source_envelope_containment',source_object_count:records.length,max_bounds_difference_m:difference,contained,relative_extent:relativeExtent};
        assert(contained&&relativeExtent.every(value=>value>.65&&value<1.1),'Rendered planter does not fit its conservative source envelope');
      }else{
        manifestComparison.assemblies[name]={method:'bounds_agreement',source_object_count:records.length,max_bounds_difference_m:difference};
        assert(difference<.025,`Rendered ${name} differs from source geometry bounds by ${difference}m`);
      }
    }
  }catch(error){if(error.code!=='ENOENT')throw error}
  await expect(page.getByText('Synthetic patient model',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Model & physics',exact:true}).click();
  await expect(page.getByText('28 synchronized',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Model & physics',exact:true}).click();
  const photograph=async(name)=>{
    await expect(canvas).toHaveAttribute('data-camera-view',name);
    await expect(canvas).toHaveAttribute('data-camera-settled','true',{timeout:20000});
    await page.waitForTimeout(150);
    const file=`apps/web/artifacts/${capture}-${name}.png`;
    await page.screenshot({path:resolve(repository,file)});screenshots.push({view:name,file});
  };
  await photograph('bedside');
  await page.getByRole('button',{name:'Room overview',exact:true}).click();await photograph('overview');
  await page.getByRole('button',{name:'Patient bedside',exact:true}).click();await photograph('patient');
  for(const view of ['patient_face','bed_foot','bed_rear','chair','storage','wardrobe']){
    await page.getByRole('button',{name:'Model & physics',exact:true}).click();
    await page.getByRole('combobox',{name:'Inspect room furnishings',exact:true}).selectOption(view);
    await page.getByRole('button',{name:'Model & physics',exact:true}).click();
    await photograph(view);
  }
  await page.getByRole('button',{name:'Patient bedside',exact:true}).click();
  await expect(canvas).toHaveAttribute('data-camera-settled','true',{timeout:20000});
  await expect(page.getByRole('button',{name:'Pick up phone',exact:true})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Vertical travel',exact:true})).toBeEnabled();
  assert.equal(sceneRequests.size,5);const revisions=new Set(sceneRequests.values());assert.equal(revisions.size,1);assert.match([...revisions][0],/^[a-f0-9]{16}$/);
  assert.deepEqual(errors,[]);assert.deepEqual(failedRequests,[]);assert.deepEqual(apiRequests,[]);
  const result={checked_at:new Date().toISOString(),elapsed_seconds:(Date.now()-started)/1000,origin:new URL(target).origin,viewport:{width:1600,height:1000},scene_revision:[...revisions][0],content_security_policy:contentSecurityPolicy,assemblies,manifest_comparison:manifestComparison,patient_within_bed_footprint:true,synthetic_patient_label:true,physics_controls_available:true,screenshots,errors,failed_requests:failedRequests,api_requests:apiRequests};
  await writeFile(resolve(repository,`artifacts/${capture}-completeness-check.json`),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result,null,2));
}catch(error){console.error(JSON.stringify({errors,failedRequests,apiRequests,alerts:await page?.getByRole('alert').allTextContents()},null,2));throw error}
finally{await browser?.close();if(!remote)await new Promise(done=>server.close(done))}
