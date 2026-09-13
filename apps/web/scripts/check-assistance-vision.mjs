import {createServer} from 'node:http';
import {readFile,stat,mkdir,writeFile} from 'node:fs/promises';
import {dirname,extname,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {chromium,expect} from '@playwright/test';

const webRoot=resolve(dirname(fileURLToPath(import.meta.url)),'..'),root=resolve(webRoot,'../..'),dist=resolve(webRoot,'dist');
const remote=process.env.VELA_PUBLIC_URL,port=Number(process.env.VELA_DEMO_CHECK_PORT||4176);
const capture=process.env.VELA_CAPTURE_NAME||(remote?'vercel-assistance':'assistance');
assert(/^[a-z0-9-]+$/.test(capture));
const headers=JSON.parse(await readFile(resolve(root,'vercel.json'),'utf8')).headers[0].headers;
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.xml':'application/xml','.wasm':'application/wasm','.glb':'model/gltf-binary','.woff2':'font/woff2','.svg':'image/svg+xml'};
const server=createServer(async(req,res)=>{
  for(const h of headers)res.setHeader(h.key,h.value);
  try{const url=new URL(req.url,'http://localhost'),path=resolve(dist,url.pathname==='/'?'index.html':'.'+decodeURIComponent(url.pathname));if(!path.startsWith(dist+sep))throw Error('Invalid path');assert((await stat(path)).isFile());res.writeHead(200,{'Content-Type':mime[extname(path)]||'application/octet-stream'});res.end(await readFile(path))}catch{res.writeHead(404).end()}
});
if(!remote)await new Promise(ready=>server.listen(port,'127.0.0.1',ready));
const report={started:new Date().toISOString(),target:remote||`http://127.0.0.1:${port}/#simulation`,errors:[],requests:[],cameraStats:[],vision:[],demos:[],screenshots:[]};
await mkdir(resolve(webRoot,'artifacts'),{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-webgl','--ignore-gpu-blocklist']});
const page=await browser.newPage({viewport:process.env.VELA_MOBILE==='1'?{width:390,height:844}:{width:1440,height:1000},deviceScaleFactor:1});
page.on('pageerror',e=>report.errors.push(e.message));
page.on('response',r=>{if(r.status()>=400)report.requests.push({url:r.url(),status:r.status()})});
page.on('requestfailed',r=>report.requests.push({url:r.url(),failure:r.failure()?.errorText}));
const panel=page.getByTestId('robot-perception');
async function screenshot(name){const path=resolve(webRoot,`artifacts/${capture}-${name}.png`);await page.screenshot({path});report.screenshots.push(path)}
async function vision(){return await panel.evaluate(e=>({metrics:JSON.parse(e.dataset.slamMetrics),evaluation:JSON.parse(e.dataset.slamEvaluation),frames:Number(e.dataset.frames)}))}
async function healthy(){assert.deepEqual(report.errors,[]);assert.deepEqual(report.requests,[]);assert.deepEqual(await page.getByRole('alert').allTextContents(),[])}
try{
  await page.goto(report.target,{waitUntil:'networkidle'});
  await expect(page.locator('.immersive-loading')).toHaveCount(0,{timeout:120000});
  await expect.poll(async()=>Number(await panel.getAttribute('data-frames')),{timeout:30000}).toBeGreaterThan(5);
  report.cameraStats=await page.locator('canvas[data-camera]').evaluateAll(canvases=>canvases.map(c=>{const bytes=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let min=255,max=0,sum=0;for(let i=0;i<bytes.length;i+=4){const v=(bytes[i]+bytes[i+1]+bytes[i+2])/3;min=Math.min(min,v);max=Math.max(max,v);sum+=v}return {name:c.dataset.camera,width:c.width,height:c.height,frames:Number(c.dataset.frames),span:max-min,mean:sum/(bytes.length/4)}}));
  assert.equal(report.cameraStats.length,4);for(const c of report.cameraStats){assert(c.frames>5);assert(c.span>25,`Blank ${c.name} camera`)}
  for(const name of ['head_rgb','head_stereo_right','left_wrist','right_wrist']){
    const canvas=page.locator(`canvas[data-camera="${name}"]`);
    const data=await canvas.evaluate(c=>c.toDataURL('image/png').split(',')[1]);await writeFile(resolve(webRoot,`artifacts/${capture}-${name}.png`),Buffer.from(data,'base64'));
  }
  report.vision.push(await vision());await screenshot('camera-views');await healthy();
  if(process.env.VELA_MOBILE==='1'){
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile page overflow');
    await page.getByRole('button',{name:'More demos',exact:true}).click();
    for(const name of ['Deliver phone','Deliver meal','Open blinds','Start bedside approach','Start greeting','Start phone return']){const button=page.getByRole('button',{name,exact:true});await button.scrollIntoViewIfNeeded();await expect(button).toBeVisible()}
    await screenshot('mobile-demos');await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:'More demos',exact:true})).toBeFocused();
    const heading=page.getByRole('button',{name:/^Robot vision/});if(await heading.getAttribute('aria-expanded')==='false')await heading.click();await screenshot('mobile-cameras');
    await page.getByRole('button',{name:'Visual map',exact:true}).click();await screenshot('mobile-map');report.mobile={passed:true,viewport:[390,844],allSixDemosReachable:true,horizontalOverflow:false};
  }
  if(process.env.VELA_VISION_ONLY!=='1'){
    const commands=process.env.VELA_ASSISTANCE_COMMANDS?.split(',')||['deliver_phone_demo','deliver_meal_demo','blinds_demo'];
    const buttons={deliver_phone_demo:'Deliver phone',deliver_meal_demo:'Deliver meal',blinds_demo:'Open blinds',bedside_demo:'Start bedside approach'};
    for(const command of commands){
      await page.getByRole('button',{name:'More demos',exact:true}).click();await page.getByRole('button',{name:buttons[command],exact:true}).click();
      const demo=page.getByTestId('demo-metrics'),trace=[];const deadline=Date.now()+300000;let last,actionSaved=false;
      while(Date.now()<deadline){await healthy();last=JSON.parse(await demo.getAttribute('data-demo-metrics'));assert.equal(last.command,command);assert.notEqual(last.status,'stopped',JSON.stringify(last));trace.push(last);report.vision.push(await vision());if(!actionSaved&&last.progress>.58){await screenshot(command+'-action');actionSaved=true}if(last.complete)break;await page.waitForTimeout(750)}
      assert(last?.complete,`${command} did not complete`);assert(Object.values(last.checks).every(Boolean));report.demos.push({command,final:last,trace});await screenshot(command+'-complete');
    }
    await page.getByRole('button',{name:'Visual map',exact:true}).click();await screenshot('visual-map');
  }
  await healthy();report.passed=true;
  if(process.env.VELA_GUARD_CHECK==='1'){
    // Negative test: corrupt only rendered camera pixel readback. Physics
    // state, actuator controls, SLAM state and outcome flags remain untouched.
    await page.getByRole('button',{name:'Reset simulation',exact:true}).click();
    await expect.poll(async()=>(await vision()).metrics?.status,{timeout:20000}).toBe('tracking');
    await page.getByLabel('Pause motion if tracking is lost').check();
    await page.getByRole('button',{name:'Joint movement',exact:true}).click();
    await page.waitForTimeout(600);
    await page.evaluate(()=>{const prototype=WebGL2RenderingContext.prototype,original=prototype.readPixels;window.__restoreVisionPixels=()=>{prototype.readPixels=original};prototype.readPixels=function(...args){original.apply(this,args);if([320,640].includes(args[2])&&[240,480].includes(args[3])&&ArrayBuffer.isView(args[6]))args[6].fill(0)}});
    await expect(page.getByTestId('vision-pause')).toHaveCount(1,{timeout:15000});
    assert.equal((await vision()).metrics.status,'lost');
    const clock=()=>page.locator('.immersive-clock strong').innerText().then(parseFloat);
    const before=await clock();await page.waitForTimeout(800);assert(Math.abs(await clock()-before)<.01,'Motion did not pause on lost tracking');
    await page.evaluate(()=>window.__restoreVisionPixels());
    await expect.poll(async()=>(await vision()).metrics?.status,{timeout:15000}).toBe('tracking');
    await page.waitForTimeout(600);assert(Math.abs(await clock()-before)<.01,'Recovered visual tracking automatically resumed motion');
    await screenshot('tracking-loss-pause');
    await page.getByRole('button',{name:'Resume simulation',exact:true}).click();await page.waitForTimeout(600);assert(await clock()>before+.1,'Explicit resume did not resume motion');
    report.visualGuard={passed:true,corruption:'Camera RGBA readback only',pausedClock:before,automaticResume:false,manualResume:true};
    await page.getByRole('button',{name:'Reset simulation',exact:true}).click();await healthy();
  }
}catch(error){report.passed=false;report.failure=String(error.stack||error);await screenshot('failure').catch(()=>{});throw error}
finally{report.finished=new Date().toISOString();await writeFile(resolve(root,`artifacts/${capture}-check.json`),JSON.stringify(report,null,2));await browser.close();if(!remote)await new Promise(ready=>server.close(ready));console.log(JSON.stringify({passed:report.passed,cameraStats:report.cameraStats,vision:report.vision.at(-1),demos:report.demos.map(d=>({command:d.command,checks:d.final.checks})),failure:report.failure}))}
