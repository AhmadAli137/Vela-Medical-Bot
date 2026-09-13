import {test, expect, type Page} from '@playwright/test';

async function resetRoom(page: Page) {
  const session=await page.request.post('/api/session',{data:{role:'operator'}});
  expect(session.ok()).toBeTruthy();
  const reset=await page.request.post('/api/demo/scenario',{data:{scenario:'reset',seed:71}});
  expect(reset.ok()).toBeTruthy();
  await page.request.post('/api/robots/mock-bracketbot/estop',{data:{engaged:false}});
}

test('staff plans, validates, approves and verifies an actual mock room task',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await resetRoom(page);
  await page.goto('/#staff');
  await expect(page.getByRole('heading',{name:'A little more room for care.'})).toBeVisible();
  await page.getByRole('button',{name:'Create a task',exact:true}).click();
  await page.getByLabel('Requested outcome').fill('Bring my phone closer');
  await page.getByRole('button',{name:'Create a reviewable plan'}).click();
  const dialog=page.getByRole('dialog',{name:'Task review'});
  await expect(dialog.getByText('place in zone',{exact:true})).toBeVisible();
  await dialog.getByRole('button',{name:'Validate',exact:true}).click();
  await expect(dialog.getByRole('button',{name:'Approve',exact:true})).toBeEnabled();
  await dialog.getByRole('button',{name:'Approve',exact:true}).click();
  await expect(dialog.getByText('approved',{exact:true})).toBeVisible();
  await dialog.getByRole('button',{name:'Run in mock room',exact:true}).click();
  await expect(dialog.getByText('completed',{exact:true})).toBeVisible();
  const response=await page.request.get('/api/bootstrap');const data=await response.json();
  const phone=data.room.objects.find((o:any)=>o.id==='phone');
  expect(phone.reachable_by_patient).toBeTruthy();
  expect(data.tasks.some((task:any)=>task.goal==='Bring my phone closer'&&task.status==='completed')).toBeTruthy();
  await dialog.getByRole('button',{name:'Close dialog'}).click();
  const notification=page.getByRole('button',{name:'Dismiss notification'});if(await notification.isVisible())await notification.click();
  await page.screenshot({path:'artifacts/staff-desktop.png',fullPage:true});
  expect(errors).toEqual([]);
});

test('patient clinical request remains a truthful escalation and privacy preferences persist',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/#patient');
  await expect(page.getByRole('heading',{name:'How can we help you settle in?'})).toBeVisible();
  await page.getByLabel('Your request',{exact:true}).fill('My chest hurts and I cannot breathe');
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.getByRole('heading',{name:'This demo cannot contact staff. Use your hospital call button or speak to staff directly.'})).toBeVisible();
  const response=await page.request.get('/api/bootstrap');const data=await response.json();
  expect(data.requests[0].route).toBe('D');
  expect(data.requests[0].locked).toBeTruthy();
  await page.getByRole('button',{name:'Manage preferences'}).click();
  await page.getByRole('button',{name:'Pause nonessential observation'}).click();
  await expect(page.getByRole('switch',{name:'Room observation'})).toHaveAttribute('aria-checked','false');
  await expect(page.getByRole('switch',{name:'Microphone preference'})).toHaveAttribute('aria-checked','false');
  await page.getByRole('button',{name:'Close dialog'}).click();
  const notification=page.getByRole('button',{name:'Dismiss notification'});if(await notification.isVisible())await notification.click();
  await page.getByRole('button',{name:'Stop robot',exact:true}).click();
  await expect(page.getByText('Simulated robot stopped.',{exact:true})).toBeVisible();
  expect((await (await page.request.get('/api/bootstrap')).json()).robots[0].estop).toBeTruthy();
  const denied=await page.request.post('/api/robots/mock-bracketbot/estop',{data:{engaged:false}});
  expect(denied.status()).toBe(403);
  if(await notification.isVisible())await notification.click();
  await page.screenshot({path:'artifacts/patient-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'artifacts/patient-mobile.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});

test('four surfaces render, switch demo roles, and run a real surrogate benchmark',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/#staff');
  await expect(page.getByRole('heading',{name:'A little more room for care.'})).toBeVisible();
  await page.getByRole('link',{name:'Robot & fleet',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Capability, with boundaries.'})).toBeVisible();
  await expect.poll(async()=>{const r=await page.request.get('/api/bootstrap');return(await r.json()).role}).toBe('operator');
  await page.screenshot({path:'artifacts/fleet-desktop.png',fullPage:true});
  await page.getByRole('link',{name:'Research studio',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Learn what actually helps.'})).toBeVisible();
  await expect.poll(async()=>{const r=await page.request.get('/api/bootstrap');return(await r.json()).role}).toBe('researcher');
  await page.screenshot({path:'artifacts/research-desktop.png',fullPage:true});
  await page.getByRole('tab',{name:'Simulation',exact:true}).click();
  await page.getByLabel('Episodes',{exact:true}).fill('3');
  await page.getByRole('button',{name:'Run 3 episodes'}).click();
  await expect(page.getByText('Measured in surrogate simulation')).toBeVisible({timeout:45000});
  await expect(page.getByRole('button',{name:'Export',exact:true})).toBeVisible();
  await page.getByRole('tab',{name:'Learning loop'}).click();
  await expect(page.getByRole('heading',{name:'Registered skills'})).toBeVisible();
  await page.getByRole('tab',{name:'Image corpus'}).click();
  await expect(page.getByRole('heading',{name:'Provenance before pixels.'})).toBeVisible();
  expect(errors).toEqual([]);
});

test('staff mobile layout and keyboard dialog navigation remain usable',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/#staff');
  await expect(page.getByRole('heading',{name:'A little more room for care.'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.getByRole('button',{name:'Create a task',exact:true}).click();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button',{name:'Close dialog'})).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Create a task',exact:true})).toBeFocused();
  await page.screenshot({path:'artifacts/staff-mobile.png',fullPage:true});
});

test('operator records and completes a consented synthetic correction without changing session owner',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await resetRoom(page);
  await page.goto('/#staff');
  await expect(page.getByRole('heading',{name:'A little more room for care.'})).toBeVisible();
  await page.getByRole('button',{name:'Create a task',exact:true}).click();
  await page.getByLabel('Requested outcome').fill('Bring my phone closer');
  await page.getByRole('button',{name:'Create a reviewable plan'}).click();
  await page.getByRole('button',{name:'Record a correction',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Record a supervised correction'});
  await expect(dialog).toBeVisible();
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button',{name:'Start mock correction'}).click();
  await expect(page.getByRole('heading',{name:'Capability, with boundaries.'})).toBeVisible();
  const before=await(await page.request.get('/api/bootstrap')).json();
  const recording=before.sessions.find((session:any)=>session.status==='recording');
  expect(recording).toBeTruthy();
  await page.getByRole('button',{name:'Complete mock correction',exact:true}).click();
  await expect(page.getByText('Twelve synthetic correction frames saved. No real camera pixels or Quest data were recorded.')).toBeVisible();
  const after=await(await page.request.get('/api/bootstrap')).json();
  const completed=after.sessions.find((session:any)=>session.id===recording.id);
  expect(completed.frame_count).toBe(12);
  expect(completed.status).toBe('stopped');
  expect(completed.labels.success).toBe(true);
  expect(completed.hardware_connected).toBe(false);
  expect(errors).toEqual([]);
});
