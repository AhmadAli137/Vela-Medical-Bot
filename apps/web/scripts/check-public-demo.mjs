import {createServer} from 'node:http';
import {readFile, stat, mkdir, writeFile} from 'node:fs/promises';
import {dirname, extname, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {chromium, expect} from '@playwright/test';

// Test the published static files with the exact Vercel headers and no API proxy.
const webRoot=resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repository=resolve(webRoot,'../..');
const output=resolve(webRoot,'dist');
const deployment=JSON.parse(await readFile(resolve(repository,'vercel.json'),'utf8'));
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.json':'application/json','.xml':'application/xml','.wasm':'application/wasm','.glb':'model/gltf-binary','.woff':'font/woff','.woff2':'font/woff2','.svg':'image/svg+xml'};
const server=createServer(async(request,response)=>{
  const pathname=decodeURIComponent(new URL(request.url,'http://localhost').pathname);
  const filename=resolve(output, pathname==='/'?'index.html':`.${pathname}`);
  for(const header of deployment.headers[0].headers)response.setHeader(header.key,header.value);
  if(!filename.startsWith(output+sep)){response.writeHead(403).end();return}
  try{
    const information=await stat(filename);
    if(!information.isFile())throw new Error('Not a file');
    response.writeHead(200,{'Content-Type':mime[extname(filename)]||'application/octet-stream'});
    response.end(await readFile(filename));
  }catch{response.writeHead(404,{'Content-Type':'text/plain'}).end('Not found')}
});
await new Promise(resolveReady=>server.listen(4173,'127.0.0.1',resolveReady));
const started=Date.now();
const errors=[],failedRequests=[],apiRequests=[];
let browser,page;
try{
  browser=await chromium.launch({channel:'chrome',headless:true});
  const context=await browser.newContext({viewport:{width:1600,height:1000}});
  page=await context.newPage();
  page.on('pageerror',error=>errors.push(String(error)));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text())});
  page.on('requestfailed',request=>failedRequests.push({url:request.url(),error:request.failure()?.errorText}));
  page.on('request',request=>{if(new URL(request.url()).pathname.startsWith('/api/'))apiRequests.push(request.url())});
  await page.goto('http://127.0.0.1:4173/',{waitUntil:'networkidle'});
  await expect.poll(async()=>{
    const alerts=await page.getByRole('alert').allTextContents();
    if(alerts.length)throw new Error(alerts.join('; '));
    return page.getByRole('button',{name:'Joint movement',exact:true}).isEnabled();
  },{timeout:60000}).toBe(true);
  await expect(page.getByText('MuJoCo · in browser',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Model & physics',exact:true}).click();
  await expect(page.getByText('27 synchronized',{exact:true})).toBeVisible();
  await page.getByText('25 joint positions',{exact:true}).click();
  const jointPositions=()=>page.locator('.immersive-joints code').allTextContents();
  const clock=async()=>parseFloat(await page.locator('.immersive-clock strong').innerText());
  const initial=await jointPositions();
  await page.getByRole('button',{name:'Joint movement',exact:true}).click();
  await page.waitForTimeout(3500);
  const moved=await jointPositions();
  const movingJoints=moved.filter((value,index)=>value!==initial[index]).length;
  assert(movingJoints>=20,`Only ${movingJoints} joints changed`);
  const movingTime=await clock();
  await page.getByRole('button',{name:'Pause simulation',exact:true}).click();
  await page.waitForTimeout(400);
  const pausedTime=await clock();
  await page.waitForTimeout(700);
  assert.equal(await clock(),pausedTime,'Simulation continued while paused');
  await page.getByRole('button',{name:'Reset simulation',exact:true}).click();
  await page.getByRole('button',{name:'Table reach demo',exact:true}).click();
  await page.waitForTimeout(6500);
  const reachErrorText=await page.locator('dl div').filter({has:page.getByText('Reach endpoint error',{exact:true})}).locator('dd').innerText();
  assert(parseFloat(reachErrorText)<.6,`Reach did not settle: ${reachErrorText}`);
  const physicsSteps=await page.locator('dl div').filter({has:page.getByText('Physics steps',{exact:true})}).locator('dd').innerText();
  await page.getByRole('button',{name:'About this demo',exact:true}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByRole('button',{name:'About this demo',exact:true})).toBeFocused();
  await page.evaluate(()=>{location.hash='#staff'});
  await expect(page.getByRole('heading',{name:'Patient room 417.'})).toBeVisible();
  await page.getByRole('button',{name:'Model & physics',exact:true}).click();
  await mkdir(resolve(webRoot,'artifacts'),{recursive:true});
  await page.screenshot({path:resolve(webRoot,'artifacts/public-simulation.png')});
  assert.deepEqual(errors,[],'Browser errors');
  assert.deepEqual(failedRequests,[],'Failed network requests');
  assert.deepEqual(apiRequests,[],'Public demo called the local API');
  const result={checked_at:new Date().toISOString(),elapsed_seconds:(Date.now()-started)/1000,origin:'http://127.0.0.1:4173',server:'Static files with Vercel response headers; no API proxy',engine:'MuJoCo WebAssembly',viewport:{width:1600,height:1000},synchronized_bodies:27,joint_positions:initial.length,moving_joints:movingJoints,moving_simulation_time_seconds:movingTime,paused_simulation_time_seconds:pausedTime,reach_endpoint_error_display:reachErrorText,physics_steps_display:physicsSteps,default_route_3d:true,legacy_hash_stays_in_public_demo:true,about_dialog_escape_and_focus_restoration:true,errors,failed_requests:failedRequests,api_requests:apiRequests,screenshot:'apps/web/artifacts/public-simulation.png'};
  await writeFile(resolve(repository,'artifacts/public-browser-check.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result,null,2));
}catch(error){
  console.error(JSON.stringify({errors,failedRequests,apiRequests,alerts:await page?.getByRole('alert').allTextContents()},null,2));
  throw error;
}finally{
  await browser?.close();
  await new Promise(resolveClosed=>server.close(resolveClosed));
}
