import {createServer} from 'node:http';
import {readFile,stat,mkdir,writeFile} from 'node:fs/promises';
import {dirname,extname,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {chromium,expect} from '@playwright/test';

// Exercise production Chrome and the public UI. No injected physics state,
// direct runtime commands, API proxy, or elapsed-time completion shortcuts.
const webRoot=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const repository=resolve(webRoot,'../..'),output=resolve(webRoot,'dist');
const remote=process.env.VELA_PUBLIC_URL;
const port=Number(process.env.VELA_DEMO_CHECK_PORT||4175);
assert(Number.isInteger(port)&&port>1023&&port<65536,'Invalid local checker port');
const target=remote||`http://127.0.0.1:${port}/#simulation`;
const capture=process.env.VELA_CAPTURE_NAME||(remote?'vercel-more-demos':'more-demos');
assert(/^[a-z0-9-]+$/.test(capture),'Invalid capture name');
const reportPath=resolve(repository,`artifacts/${capture}-check.json`);
const deployment=JSON.parse(await readFile(resolve(repository,'vercel.json'),'utf8'));
const trajectoryLibrary=JSON.parse(await readFile(resolve(repository,'sim/reference_demo_trajectories.json'),'utf8'));
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.json':'application/json','.xml':'application/xml','.wasm':'application/wasm','.glb':'model/gltf-binary','.woff':'font/woff','.woff2':'font/woff2','.svg':'image/svg+xml'};
const server=createServer(async(request,response)=>{
  for(const header of deployment.headers[0].headers)response.setHeader(header.key,header.value);
  try{
    const pathname=decodeURIComponent(new URL(request.url,'http://localhost').pathname);
    const filename=resolve(output,pathname==='/'?'index.html':`.${pathname}`);
    if(!filename.startsWith(output+sep)){response.writeHead(403).end();return}
    if(!(await stat(filename)).isFile())throw new Error('Not a file');
    response.writeHead(200,{'Content-Type':mime[extname(filename)]||'application/octet-stream'});
    response.end(await readFile(filename));
  }catch{response.writeHead(404,{'Content-Type':'text/plain'}).end('Not found')}
});
if(!remote)await new Promise((ready,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',ready)});
console.log(`More-demos checker ready at ${target}`);

const demonstrations=[
  {command:'bedside_demo',button:'Start bedside approach',timeoutMs:150000},
  {command:'greeting_demo',button:'Start greeting',timeoutMs:150000},
  {command:'phone_return_demo',button:'Start phone return',timeoutMs:240000},
];
const started=Date.now(),errors=[],failedRequests=[],httpFailures=[],apiRequests=[],screenshots=[],results=[];
const sceneRequests=new Map();
const pickupEvidence={confirmed_hold_observed:false,max_height_gain_m:0,max_bilateral_hold_s:0};
const actionCaptures=new Set();
let browser,page,context,contentSecurityPolicy,galleryKeyboardVerified=false,resetVerified=false;

function assertFiniteMeasurements(value,path='measurements'){
  if(typeof value==='number')assert(Number.isFinite(value),`Nonfinite ${path}`);
  else if(value&&typeof value==='object')for(const [key,item] of Object.entries(value))assertFiniteMeasurements(item,`${path}.${key}`);
}

async function healthy(){
  assert.deepEqual(errors,[],'Browser errors');
  assert.deepEqual(failedRequests,[],'Failed network requests');
  assert.deepEqual(httpFailures,[],'HTTP errors');
  assert.deepEqual(apiRequests,[],'Static demo requested an API');
  assert.deepEqual(await page.getByRole('alert').allTextContents(),[],'Simulation error alert');
}

async function clock(){
  const value=parseFloat(await page.locator('.immersive-clock strong').innerText());
  assert(Number.isFinite(value),'Simulation clock is not finite');
  return value;
}

async function readDemo(){
  const panel=page.getByTestId('demo-metrics');
  const observed=await panel.evaluate(element=>({command:element.dataset.command,status:element.dataset.status,
    complete:element.dataset.complete,progress:element.dataset.progress,json:element.dataset.demoMetrics,text:element.innerText,
    accessibleProgress:element.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')}));
  assert(observed.json,'Full runtime demo metrics are missing');
  const metrics=JSON.parse(observed.json);
  assert.equal(observed.command,metrics.command,'UI command differs from runtime metrics');
  assert.equal(observed.status,metrics.status,'UI status differs from runtime metrics');
  assert.equal(observed.complete,String(metrics.complete),'UI completion differs from runtime metrics');
  assert.equal(Number(observed.progress),metrics.progress,'UI progress differs from runtime metrics');
  assert(Number.isFinite(metrics.progress)&&metrics.progress>=0&&metrics.progress<=1,'Invalid demo progress');
  assert.equal(typeof metrics.complete,'boolean');
  assert(['running','complete','stopped'].includes(metrics.status),'Invalid demo status');
  assert.notEqual(metrics.status,'stopped',`Demo stopped: ${JSON.stringify(metrics)}`);
  assert(typeof metrics.stage==='string'&&metrics.stage.length>0,'Missing runtime stage');
  assert(metrics.measurements&&typeof metrics.measurements==='object','Missing measured outcomes');
  assertFiniteMeasurements(metrics.measurements);
  assert(observed.text.includes('Stage')&&observed.text.includes('Progress'),'Visible stage or progress is missing');
  assert(observed.accessibleProgress!==null&&observed.accessibleProgress!==undefined,'Accessible progress bar is missing');
  assert.equal(Number(observed.accessibleProgress),Math.round(metrics.progress*100),'Accessible progress differs from measured progress');
  return metrics;
}

async function waitForDemo(command,predicate,timeoutMs,trace){
  const deadline=Date.now()+timeoutMs;
  let previous=-1,last;
  while(Date.now()<deadline){
    await healthy();
    last=await readDemo();
    assert.equal(last.command,command,'Active demo changed unexpectedly');
    assert(last.progress+1e-8>=previous,'Progress went backwards without a reset');
    previous=last.progress;
    const sample={stage:last.stage,status:last.status,complete:last.complete,progress:last.progress,simulation_time_s:await clock(),
      measurements:last.measurements,checks:last.checks};
    if(trace&&!trace.some(old=>old.stage===sample.stage&&old.status===sample.status&&JSON.stringify(old.checks)===JSON.stringify(sample.checks)))trace.push(sample);
    if(command==='phone_return_demo'){
      const rawPickup=await page.getByTestId('demo-metrics').getAttribute('data-pickup-metrics');
      const pickup=rawPickup?JSON.parse(rawPickup):null;
      if(pickup){
        const held={success:pickup.success,height:pickup.height_gain_m,bilateral:pickup.bilateral_contact,duration:pickup.bilateral_hold_s};
        assert(Number.isFinite(held.height)&&Number.isFinite(held.duration),'Nonfinite pickup measurement');
        pickupEvidence.max_height_gain_m=Math.max(pickupEvidence.max_height_gain_m,held.height);
        pickupEvidence.max_bilateral_hold_s=Math.max(pickupEvidence.max_bilateral_hold_s,held.duration);
        const outcome=trajectoryLibrary.commands.phone_return_demo.outcomes;
        pickupEvidence.confirmed_hold_observed ||= held.success&&held.bilateral&&held.height>=outcome.minimum_grasp_height_m&&held.duration>=outcome.minimum_bilateral_hold_s;
      }
    }
    const actionVisible=(command==='bedside_demo'&&last.stage==='pause_beside_bed')
      ||(command==='greeting_demo'&&last.stage==='wave_2')
      ||(command==='phone_return_demo'&&last.stage==='hold'&&pickupEvidence.confirmed_hold_observed);
    if(actionVisible&&!actionCaptures.has(command)){
      await photograph(`${command}-action`);
      actionCaptures.add(command);
    }
    if(predicate(last))return last;
    await page.waitForTimeout(200);
  }
  assert.fail(`Timed out waiting for ${command}: ${JSON.stringify(last)}`);
}

function assertMeasuredCompletion(demo){
  const measured=demo.measurements,thresholds=trajectoryLibrary.commands[demo.command].outcomes;
  const number=name=>{const value=measured[name];assert(typeof value==='number'&&Number.isFinite(value),`Missing numeric outcome ${name}`);return value};
  assert(number('rest_qpos_error')<=thresholds.rest_qpos_tolerance,'Robot did not return to rest');
  assert(number('robot_speed')<=thresholds.robot_speed_tolerance,'Robot did not settle');
  assert(number('settle_dwell_s')>=thresholds.settle_dwell_s,'Settled outcome was not maintained');
  if(demo.command==='bedside_demo'){
    assert.equal(measured.visited_bedside,true,'Bedside target was not reached');
    assert(number('max_base_excursion_m')>=thresholds.minimum_base_excursion_m,'Insufficient measured base travel');
    assert(number('base_home_error_m')<=Math.SQRT2*thresholds.rest_qpos_tolerance,'Base did not return home');
  }else if(demo.command==='greeting_demo'){
    assert(number('max_hand_height_m')>=thresholds.minimum_hand_height_m,'Greeting hand was not raised');
    assert(number('wave_range_rad')>=thresholds.minimum_wave_range_rad,'Wrist gesture was not measured');
  }else{
    assert(pickupEvidence.confirmed_hold_observed,'No successful bilateral pickup was observed before return');
    for(const [measurement,limit] of [['phone_xy_error_m','phone_xy_tolerance_m'],['phone_z_error_m','phone_z_tolerance_m'],
      ['phone_speed_m_s','phone_speed_tolerance_m_s'],['phone_angular_speed_rad_s','phone_angular_speed_tolerance_rad_s']]){
      assert(number(measurement)<=thresholds[limit],`Phone return exceeded ${limit}`);
    }
    assert(number('riser_support_force_n')>thresholds.support_force_minimum_n,'Phone lacks measured support contact');
    assert(number('hand_clearance_m')>=thresholds.hand_clearance_m,'Hand did not withdraw');
  }
}

async function photograph(name){
  const canvas=page.locator('.immersive-canvas canvas');
  await expect(canvas).toHaveAttribute('data-camera-settled','true',{timeout:20000});
  const path=`apps/web/artifacts/${capture}-${name}.png`;
  await page.screenshot({path:resolve(repository,path)});
  screenshots.push({view:name,file:path});
  return path;
}

async function openGallery(){
  await page.getByRole('button',{name:'More demos',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'More to explore.',exact:true});
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute('aria-modal','true');
  for(const demo of demonstrations)await expect(dialog.getByRole('button',{name:demo.button,exact:true})).toBeEnabled();
  return dialog;
}

try{
  await mkdir(resolve(webRoot,'artifacts'),{recursive:true});
  await mkdir(resolve(repository,'artifacts'),{recursive:true});
  browser=await chromium.launch({channel:'chrome',headless:true});
  context=await browser.newContext({viewport:{width:1600,height:1000}});
  page=await context.newPage();
  page.on('pageerror',error=>errors.push(String(error)));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text())});
  page.on('requestfailed',request=>failedRequests.push({url:request.url(),error:request.failure()?.errorText}));
  page.on('response',response=>{if(response.status()>=400)httpFailures.push({url:response.url(),status:response.status()})});
  page.on('request',request=>{const url=new URL(request.url());if(url.pathname.startsWith('/api/'))apiRequests.push(request.url());if(url.pathname.startsWith('/simulation/'))sceneRequests.set(url.pathname,url.searchParams.get('v'))});
  const navigation=await page.goto(target,{waitUntil:'networkidle'});
  assert.equal(navigation.status(),200,'Public page was not accessible');
  contentSecurityPolicy=navigation.headers()['content-security-policy'];
  assert(contentSecurityPolicy?.includes("'wasm-unsafe-eval'")&&contentSecurityPolicy.includes("'unsafe-eval'"),'Missing official MuJoCo WASM/embind CSP');
  await expect(page.getByRole('button',{name:'Joint movement',exact:true})).toBeEnabled({timeout:60000});
  await expect(page.getByRole('button',{name:'More demos',exact:true})).toBeEnabled({timeout:60000});

  let gallery=await openGallery();
  await expect.poll(()=>gallery.evaluate(element=>element.contains(document.activeElement))).toBe(true);
  await expect(gallery.getByRole('button',{name:'Close demos',exact:true})).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(gallery.getByRole('button',{name:'Start phone return',exact:true})).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(gallery.getByRole('button',{name:'Close demos',exact:true})).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(gallery).not.toBeVisible();
  await expect(page.getByRole('button',{name:'More demos',exact:true})).toBeFocused();
  galleryKeyboardVerified=true;
  gallery=await openGallery();
  await photograph('gallery');

  let previousCompletionTime;
  for(const [index,demo] of demonstrations.entries()){
    if(index)gallery=await openGallery();
    await gallery.getByRole('button',{name:demo.button,exact:true}).click();
    await expect(gallery).not.toBeVisible();
    const panel=page.getByTestId('demo-metrics');
    await expect(panel).toHaveAttribute('data-command',demo.command,{timeout:20000});
    const initial=await readDemo(),initialTime=await clock(),trace=[];
    assert.equal(initial.complete,false,'New demo retained stale completion');
    assert.equal(initial.status,'running','Demo did not start');
    if(previousCompletionTime!==undefined)assert(initialTime<previousCompletionTime,'Starting another demo did not reset simulation time');
    await waitForDemo(demo.command,state=>state.progress>.01&&state.progress<.8,30000,trace);
    await page.getByRole('button',{name:'Pause simulation',exact:true}).click();
    await expect(page.getByRole('button',{name:'Resume simulation',exact:true})).toBeEnabled();
    await page.waitForTimeout(200);
    const paused=await readDemo(),pausedTime=await clock();
    assert.equal(paused.complete,false,'Demo completed before pause test');
    await page.waitForTimeout(650);
    const held=await readDemo();
    assert.equal(await clock(),pausedTime,'Physics time advanced while paused');
    assert.deepEqual(held,paused,'Demo measurements or progress changed while paused');
    await page.getByRole('button',{name:'Resume simulation',exact:true}).click();
    await waitForDemo(demo.command,state=>state.progress>paused.progress,30000,trace);
    const complete=await waitForDemo(demo.command,state=>state.complete,demo.timeoutMs,trace);
    assert.equal(complete.status,'complete');
    assert.equal(complete.progress,1);
    assert(Object.keys(complete.measurements).length>0,'Completion has no measured outcomes');
    assert(complete.checks&&Object.keys(complete.checks).length>0,'Completion has no outcome checks');
    for(const [name,passed] of Object.entries(complete.checks))assert.equal(passed,true,`${demo.command} failed measured check: ${name}`);
    assertMeasuredCompletion(complete);
    assert(actionCaptures.has(demo.command),'No actual action-stage screenshot captured');
    assert(trace.some(state=>!state.complete),'No running state observed');
    previousCompletionTime=await clock();
    const screenshot=await photograph(demo.command);
    results.push({command:demo.command,initial_simulation_time_s:initialTime,completed_simulation_time_s:previousCompletionTime,
      pause_resume_verified:true,paused_simulation_time_s:pausedTime,completion:complete,
      outcome_thresholds:trajectoryLibrary.commands[demo.command].outcomes,
      ...(demo.command==='phone_return_demo'?{pickup_evidence:{...pickupEvidence}}:{}),observed_stages:trace,screenshot});
    console.log(`${demo.command}: measured completion and pause/resume passed.`);
  }

  await page.getByRole('button',{name:'Reset simulation',exact:true}).click();
  await expect(page.getByTestId('demo-metrics')).toHaveCount(0,{timeout:10000});
  await expect(page.getByRole('button',{name:'Joint movement',exact:true})).toBeEnabled();
  assert(await clock()<previousCompletionTime,'Reset did not clear simulation time');
  resetVerified=true;
  await healthy();
  assert(sceneRequests.size>=5,'Scene assets did not load');
  const revisions=new Set(sceneRequests.values());
  assert.equal(revisions.size,1,'Scene assets have mismatched revisions');
  assert.match([...revisions][0],/^[a-f0-9]{16}$/);
  const report={checked_at:new Date().toISOString(),passed:true,elapsed_seconds:(Date.now()-started)/1000,
    origin:new URL(target).origin,engine:'MuJoCo WebAssembly',viewport:{width:1600,height:1000},
    server:remote?'Published site; anonymous Chrome context':'Static production files with Vercel headers; no API proxy',
    scene_revision:[...revisions][0],content_security_policy:contentSecurityPolicy,gallery_keyboard_verified:galleryKeyboardVerified,
    reset_clears_completion:resetVerified,demos:results,screenshots,errors,failed_requests:failedRequests,http_failures:httpFailures,api_requests:apiRequests};
  await writeFile(reportPath,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({passed:true,demos:results.length,report:reportPath,screenshots},null,2));
}catch(error){
  const failure={checked_at:new Date().toISOString(),passed:false,error:String(error),demos:results,screenshots,
    gallery_keyboard_verified:galleryKeyboardVerified,reset_clears_completion:resetVerified,errors,
    failed_requests:failedRequests,http_failures:httpFailures,api_requests:apiRequests,alerts:await page?.getByRole('alert').allTextContents()};
  await writeFile(reportPath,JSON.stringify(failure,null,2)+'\n');
  if(page)await page.screenshot({path:resolve(webRoot,`artifacts/${capture}-failure.png`)}).catch(()=>{});
  console.error(JSON.stringify(failure,null,2));
  throw error;
}finally{
  await context?.close();
  await browser?.close();
  if(!remote)await new Promise(done=>server.close(done));
}
