import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const source=readFileSync(new URL('../src/serializeSimulationTransport.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {serializeSimulationTransport}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}};
const turn=()=>new Promise(resolve=>setImmediate(resolve));

test('a delayed read and tracking pause finish before reset/start and the next observation',async()=>{
  const read=deferred(),pause=deferred(),calls=[],observed=[];
  let current={mode:'joint_demo',paused:false},reads=0;
  const transport=serializeSimulationTransport({
    state:()=>{calls.push('state');return ++reads===1?read.promise:Promise.resolve({...current})},
    command:async action=>{
      calls.push(action);
      if(action==='pause_for_tracking'){await pause.promise;current={...current,paused:true}}
      else current={mode:action==='reset'?'idle':action,paused:false};
      return{...current};
    },dispose:()=>{},
  });
  const capture=promise=>promise.then(state=>{observed.push(`${state.mode}:${state.paused}`);return state});
  const first=capture(transport.state()),stopping=capture(transport.command('pause_for_tracking'));
  const reset=capture(transport.command('reset')),start=capture(transport.command('greeting_demo')),last=capture(transport.state());
  await turn();assert.deepEqual(calls,['state']);
  read.resolve({...current});await first;await turn();assert.deepEqual(calls,['state','pause_for_tracking']);
  assert.deepEqual(observed,['joint_demo:false']);
  pause.resolve();await Promise.all([stopping,reset,start,last]);
  assert.deepEqual(calls,['state','pause_for_tracking','reset','greeting_demo','state']);
  assert.deepEqual(observed,['joint_demo:false','joint_demo:true','idle:false','greeting_demo:false','greeting_demo:false']);
});

test('a failed queued operation preserves its exact error and permits recovery',async()=>{
  const failure=new Error('Contact stop requires reset'),calls=[];
  const transport=serializeSimulationTransport({state:async()=>({mode:'idle'}),command:action=>{calls.push(action);if(action==='pause')return Promise.reject(failure);return Promise.resolve({mode:'idle'})},dispose:()=>{}});
  const paused=transport.command('pause'),reset=transport.command('reset');
  await assert.rejects(paused,error=>error===failure);assert.deepEqual(await reset,{mode:'idle'});
  assert.deepEqual(calls,['pause','reset']);
});

test('synchronous runtime failures reject the caller without poisoning the queue',async()=>{
  const failure=new Error('Synchronous engine error');let reads=0;
  const transport=serializeSimulationTransport({state:()=>{if(!reads++)throw failure;return Promise.resolve({mode:'idle'})},command:async()=>({}),dispose:()=>{}});
  const first=transport.state(),second=transport.state();
  await assert.rejects(first,error=>error===failure);assert.equal((await second).mode,'idle');
});

test('dispose aborts the active transport once and never starts queued controls',async()=>{
  const read=deferred(),abort=new Error('Original API abort error'),calls=[];let disposals=0;
  const transport=serializeSimulationTransport({state:()=>{calls.push('state');return read.promise},command:async action=>{calls.push(action);return{}},dispose:()=>{disposals++;read.reject(abort)}});
  const active=transport.state(),queued=transport.command('reset');
  const rejectedActive=assert.rejects(active,error=>error===abort),rejectedQueue=assert.rejects(queued,{name:'AbortError'});
  await turn();transport.dispose();transport.dispose();
  await Promise.all([rejectedActive,rejectedQueue]);
  await assert.rejects(transport.state(),{name:'AbortError'});await assert.rejects(transport.command('pause'),{name:'AbortError'});
  assert.equal(disposals,1);assert.deepEqual(calls,['state']);
});

test('a read that ignores abort cannot publish a successful state after disposal',async()=>{
  const read=deferred();const transport=serializeSimulationTransport({state:()=>read.promise,command:async()=>({}),dispose:()=>{}});
  const active=transport.state(),rejected=assert.rejects(active,{name:'AbortError'});
  await turn();transport.dispose();read.resolve({mode:'joint_demo',paused:false});await rejected;
});
