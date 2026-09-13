import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import ts from 'typescript';

const source=readFileSync(new URL('../src/roleSessionQueue.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {RoleSessionQueue}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return{promise,resolve,reject}};
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('a delayed patient login cannot overwrite a subsequent return to staff',async()=>{
  const patient=deferred(),calls=[];let cookieRole='staff';
  const sessions=new RoleSessionQueue(async({role})=>{calls.push(role);if(role==='patient')await patient.promise;cookieRole=role},async()=>({role:cookieRole}));
  const old=sessions.request({role:'patient'});await tick();const current=sessions.request({role:'staff'});
  assert.deepEqual(calls,['patient'],'New login must wait for the cookie-changing old response');
  patient.resolve();assert.equal(await old.promise,null);
  const result=await current.promise;assert.equal(result.role,'staff');assert.equal(result.data.role,'staff');assert.equal(cookieRole,'staff');
  assert.deepEqual(calls,['patient','staff']);assert.equal(sessions.pending,false);
});

test('navigation during initial bootstrap discards the old data and logs into the newest route',async()=>{
  const initial=deferred();let cookieRole='staff',loads=0;
  const sessions=new RoleSessionQueue(async({role})=>{cookieRole=role},async()=>++loads===1?initial.promise:{role:cookieRole});
  const old=sessions.request({role:'staff'});await tick();const latest=sessions.request({role:'researcher'});
  initial.resolve({role:'staff'});assert.equal(await old.promise,null);
  const result=await latest.promise;assert.equal(result.data.role,'researcher');assert.equal(cookieRole,'researcher');
});

test('superseded queued routes are skipped and explicit manual role choice remains the latest request',async()=>{
  const first=deferred(),calls=[];let role='staff';
  const sessions=new RoleSessionQueue(async(credentials)=>{calls.push(credentials.role);if(calls.length===1)await first.promise;role=credentials.role},async()=>({role}));
  const a=sessions.request({role:'staff'});await tick();const b=sessions.request({role:'patient'});const manual=sessions.request({role:'operator'});
  first.resolve();assert.equal(await a.promise,null);assert.equal(await b.promise,null);
  assert.equal((await manual.promise).data.role,'operator');await tick();assert.deepEqual(calls,['staff','operator']);
});

test('a failed login does not poison a later authorized connection',async()=>{
  let cookieRole='staff';const sessions=new RoleSessionQueue(async({role,token})=>{if(!token)throw Error('Token required');cookieRole=role},async()=>({role:cookieRole}));
  await assert.rejects(sessions.request({role:'researcher'}).promise,/Token required/);
  const result=await sessions.request({role:'researcher',token:'synthetic-test-token'}).promise;
  assert.equal(result.data.role,'researcher');assert.equal(sessions.pending,false);
});

test('obsolete login errors cannot replace the latest route outcome',async()=>{
  const oldLogin=deferred();let role='staff';
  const sessions=new RoleSessionQueue(async(credentials)=>{if(credentials.role==='patient')await oldLogin.promise;role=credentials.role},async()=>({role}));
  const old=sessions.request({role:'patient'});await tick();const latest=sessions.request({role:'staff'});oldLogin.reject(Error('Old request failed'));
  assert.equal(await old.promise,null);assert.equal((await latest.promise).role,'staff');
});

test('disposing an unmounted workspace aborts requests and never commits delayed bootstrap data',async()=>{
  const delayed=deferred();let signal;
  const sessions=new RoleSessionQueue(async(_,abortSignal)=>{signal=abortSignal},async()=>delayed.promise);
  const request=sessions.request({role:'staff'});await tick();sessions.dispose();assert.equal(signal.aborted,true);
  delayed.resolve({role:'staff'});assert.equal(await request.promise,null);assert.equal(sessions.isCurrent(request.revision),false);
  assert.equal(await sessions.request({role:'patient'}).promise,null);
});
