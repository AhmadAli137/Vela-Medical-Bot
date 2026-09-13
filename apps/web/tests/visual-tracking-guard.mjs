import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const source=readFileSync(new URL('../src/visualTrackingGuard.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {VisualTrackingGuard}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const fresh=(nowMs,extra={})=>({enabled:true,moving:true,nowMs,frameAtMs:nowMs,status:'tracking',hasPose:true,...extra});

test('fresh tracking and relocalization keep actual motion enabled',()=>{
  const guard=new VisualTrackingGuard();
  for(const now of [0,1000,5000])assert.equal(guard.evaluate(fresh(now)),false);
  assert.equal(guard.evaluate(fresh(6000,{status:'relocalized'})),false);
});
test('continuous loss or failure to initialize pauses only after the 1.5 second grace',()=>{
  for(const status of ['lost','initializing']){
    const guard=new VisualTrackingGuard(),blind=now=>fresh(now,{hasPose:false,status,frameAtMs:null});
    assert.equal(guard.evaluate(blind(10)),false);
    assert.equal(guard.evaluate(blind(1509)),false);
    assert.equal(guard.evaluate(blind(1510)),true);
    assert.equal(guard.latched,true);
  }
});
test('a frozen camera becomes stale above 750 ms and then gets a full loss grace',()=>{
  const guard=new VisualTrackingGuard(),frozen=now=>fresh(now,{frameAtMs:0});
  assert.equal(guard.evaluate(frozen(750)),false);
  assert.equal(guard.evaluate(frozen(751)),false);
  assert.equal(guard.evaluate(frozen(2250)),false);
  assert.equal(guard.evaluate(frozen(2251)),true);
});
test('healthy frames clear the loss timer instead of accumulating separate outages',()=>{
  const guard=new VisualTrackingGuard(),blind=now=>fresh(now,{status:'lost',hasPose:false});
  guard.evaluate(blind(0));assert.equal(guard.evaluate(blind(1000)),false);
  assert.equal(guard.evaluate(fresh(1100)),false);
  assert.equal(guard.evaluate(blind(1200)),false);
  assert.equal(guard.evaluate(blind(2699)),false);
  assert.equal(guard.evaluate(blind(2700)),true);
});
test('disabled guarding or paused/idle motion does not accumulate an outage',()=>{
  for(const extra of [{enabled:false},{moving:false}]){
    const guard=new VisualTrackingGuard();
    guard.evaluate(fresh(0,{status:'lost',hasPose:false}));
    assert.equal(guard.evaluate(fresh(3000,{status:'lost',hasPose:false,...extra})),false);
    assert.equal(guard.evaluate(fresh(4000,{status:'lost',hasPose:false})),false);
    assert.equal(guard.evaluate(fresh(5499,{status:'lost',hasPose:false})),false);
    assert.equal(guard.evaluate(fresh(5500,{status:'lost',hasPose:false})),true);
  }
});
test('a pause latch never auto-resumes; explicit reset/manual-resume starts a new interval',()=>{
  const guard=new VisualTrackingGuard();guard.evaluate(fresh(0,{hasPose:false}));
  assert.equal(guard.evaluate(fresh(1500,{hasPose:false})),true);
  assert.equal(guard.evaluate(fresh(1600,{moving:false})),true);
  assert.equal(guard.evaluate(fresh(1700)),true);
  assert.equal(guard.evaluate(fresh(1800,{enabled:false})),true);
  guard.reset();assert.equal(guard.latched,false);assert.equal(guard.evaluate(fresh(0)),false);
  assert.equal(guard.evaluate(fresh(100,{hasPose:false})),false);
  assert.equal(guard.evaluate(fresh(1599,{hasPose:false})),false);
  assert.equal(guard.evaluate(fresh(1600,{hasPose:false})),true);
});
test('future/missing frame timestamps and invalid clocks cannot claim healthy observation',()=>{
  for(const frameAtMs of [null,NaN,5000]){
    const guard=new VisualTrackingGuard();assert.equal(guard.evaluate(fresh(0,{frameAtMs})),false);
    assert.equal(guard.evaluate(fresh(1500,{frameAtMs})),true);
  }
  for(const nowMs of [NaN,Infinity,-1])assert.equal(new VisualTrackingGuard().evaluate(fresh(nowMs)),true);
  const guard=new VisualTrackingGuard();guard.evaluate(fresh(100));assert.equal(guard.evaluate(fresh(99)),true);
});
test('transport consumes a pause latch once and never sends an automatic resume',()=>{
  const guard=new VisualTrackingGuard(),commands=[];let sent=false;
  const controller=input=>{if(guard.evaluate(input)&&input.moving&&!sent){sent=true;commands.push('pause_for_tracking')}};
  controller(fresh(0,{hasPose:false}));controller(fresh(1500,{hasPose:false}));
  controller(fresh(1600,{hasPose:false}));controller(fresh(1700,{moving:false}));controller(fresh(1800));
  assert.deepEqual(commands,['pause_for_tracking']);
  // Explicit user action is the only reset/resume path.
  guard.reset();sent=false;controller(fresh(0));controller(fresh(100,{hasPose:false}));controller(fresh(1600,{hasPose:false}));
  assert.deepEqual(commands,['pause_for_tracking','pause_for_tracking']);
});
