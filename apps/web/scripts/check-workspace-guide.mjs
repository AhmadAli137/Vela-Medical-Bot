import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium,expect} from '@playwright/test';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../..');
const target=process.env.VELA_CHECK_URL||'http://127.0.0.1:8000/#simulation';
const publicDemo=process.env.VELA_CHECK_PUBLIC==='1';
const name=publicDemo?'public-workspace-guide':'local-workspace-guide';
const report={url:target,publicDemo,started:new Date().toISOString(),errors:[],failedResponses:[],passed:false};
await mkdir(resolve(root,'apps/web/artifacts'),{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  page.on('pageerror',error=>report.errors.push(String(error)));
  page.on('response',response=>{if(response.status()>=400)report.failedResponses.push({status:response.status(),url:response.url()})});
  await page.goto(target,{waitUntil:'domcontentloaded'});
  await expect(page.getByRole('button',{name:'Joint movement',exact:true})).toBeEnabled({timeout:60000});
  await page.getByRole('button',{name:'App guide',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Which app should I use?'});
  await expect(dialog).toBeVisible();
  for(const label of ['Simulation studio','Native MuJoCo window','Room operations','Patient experience','Robot & fleet','Research studio'])assert((await dialog.innerText()).includes(label));
  await expect(dialog.getByRole('button',{name:'Open native MuJoCo',exact:true})).toHaveCount(publicDemo?0:1);
  await page.screenshot({path:resolve(root,`apps/web/artifacts/${name}-desktop.png`)});
  await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button',{name:'App guide',exact:true})).toBeFocused();
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'App guide',exact:true}).click();await expect(dialog).toBeVisible();
  await dialog.getByRole('button',{name:'Back to the simulation',exact:true}).scrollIntoViewIfNeeded();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile guide overflows viewport');
  await page.screenshot({path:resolve(root,`apps/web/artifacts/${name}-mobile.png`)});
  await dialog.getByRole('button',{name:'Back to the simulation',exact:true}).click();
  if(!publicDemo){
    await page.setViewportSize({width:1440,height:1000});
    await page.getByRole('button',{name:'App guide',exact:true}).click();
    await dialog.getByRole('link',{name:'Room operations',exact:true}).click();
    await expect(page.getByRole('navigation',{name:'Main navigation'})).toBeVisible({timeout:15000});
    report.localRoles=[];
    for(const [label,role] of [['Patient experience','patient'],['Robot & fleet','operator'],['Research studio','researcher'],['Room operations','staff']]){
      await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:label,exact:true}).click();
      await expect(page.getByRole('navigation',{name:'Main navigation'})).toBeVisible({timeout:15000});
      await expect.poll(async()=>{
        const response=await page.request.get(new URL('/api/bootstrap',target).href);
        return (await response.json()).role;
      }).toBe(role);
      report.localRoles.push({label,role,passed:true});
    }
    await page.getByRole('button',{name:'App guide',exact:true}).click();
    await expect(page.getByRole('dialog',{name:'Which app should I use?'})).toBeVisible();
    await page.getByRole('dialog').getByRole('link',{name:'Open simulation',exact:true}).click();
    await expect(page.getByRole('button',{name:'Joint movement',exact:true})).toBeEnabled({timeout:30000});
  }
  assert.deepEqual(report.errors,[]);assert.deepEqual(report.failedResponses,[]);
  report.passed=true;
}catch(error){report.failure=String(error.stack||error);throw error}
finally{
  report.finished=new Date().toISOString();await writeFile(resolve(root,`artifacts/${name}.json`),JSON.stringify(report,null,2));
  await browser.close();console.log(JSON.stringify(report));
}
