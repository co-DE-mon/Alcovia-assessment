// Synthetic demo contract; no populated real quiz API response is claimed.
'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {execFileSync}=require('node:child_process');
const {mapQuizzes}=require('../code/quizzes.js');
const helpers=require('../code/normalise.js');
const cfg=JSON.parse(execFileSync('python3',['-B','-c',"import yaml,json,sys;print(json.dumps(yaml.safe_load(open(sys.argv[1]))))",path.join(__dirname,'../../student-tracker/config.yaml')],{encoding:'utf8'}));
const fixture=()=>JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/demo/quiz-input.json'),'utf8'));
const run=(change=()=>{},config=cfg)=>{const pack=fixture();change(pack);return mapQuizzes(pack,config,helpers);};
test('delivery remains separate from completed and unfinished attempts',()=>{
 const r=run();assert.equal(r.status,'ok');assert.equal(r.events.length,9);assert.equal(r.attempts.length,4);
 assert.equal(r.events.filter(e=>e.status==='held').length,7);assert.equal(r.events.filter(e=>e.status==='cancelled').length,1);
 assert.equal(r.attempts.filter(a=>a.completed_at).length,3);assert.equal(r.attempts.find(a=>!a.completed_at).score,null);
 assert.equal(r.events[0].planned_for,'2026-10-01 20:00:00');
});
test('empty or failed attempt history never removes held-but-skipped quizzes',()=>{
 let r=run(x=>{x.history.data.history=[];x.history.meta.total=0;});assert.equal(r.events.filter(e=>e.status==='held').length,7);assert.equal(r.attempts.length,1);
 r=run(x=>x.history={error:'upstream unavailable'});assert.equal(r.status,'partial');assert.equal(r.events.length,9);assert.equal(r.attempts.length,1);
});
test('incomplete history is rejected instead of treated as an empty successful read',()=>{
 const r=run(x=>x.history.meta.total=10);assert.equal(r.status,'partial');assert.equal(r.events.length,9);assert.equal(r.attempts.length,1);
 assert.match(r.rejects[0].reason,/truncated/);
});
test('unknown delivery, malformed rows, impossible scores and times are reported',()=>{
 for(const change of [x=>x.history.data.history[0].score=11,x=>x.history.data.history[0].totalQuestions=0,x=>x.history.data.history[0].completedAt='2026-09-01T10:00:00Z',x=>x.history.data.history[0].startedAt=null,x=>x.history.data.history[0].startedAt='2026-10-01T14:20:00Z',x=>x.history.data.history.push(null),x=>x.delivery[0].status='mystery']){
  const r=run(change);assert.equal(r.status,'partial');assert.ok(r.rejects.length);
 }
});
test('unknown status does not become held from a past schedule time',()=>{
 const r=run(x=>{x.scheduledSnapshots[0].quiz.status='mystery';x.delivery=x.delivery.slice(1);});
 assert.equal(r.status,'partial');assert.ok(!r.events.some(e=>e.event_id.endsWith('DEMO-QUIZ-1')));
});
test('IDs and status mappings come from configuration',()=>{
 const c=structuredClone(cfg);c.quiz_loader.event_id_prefix='test-prefix/';
 const r=run(()=>{},c);assert.ok(r.events.every(e=>e.event_id.startsWith('test-prefix/')));
});
test('identical rows deduplicate; contradictory attempts are unmeasured',()=>{
 let r=run(x=>x.history.data.history.push({...x.history.data.history[0]}));assert.equal(r.attempts.length,4);
 r=run(x=>x.history.data.history.push({...x.history.data.history[0],score:5}));assert.equal(r.status,'partial');assert.equal(r.attempts.length,3);
});
test('scheduled unfinished and completed history merge without response-order dependence',()=>{
 const change=x=>{x.scheduledSnapshots[0].quiz.participation={id:'p',startedAt:x.history.data.history[0].startedAt,completedAt:null,score:0};};
 assert.equal(run(change).attempts.filter(a=>a.completed_at).length,3);
 const a=run(),b=run(x=>{x.scheduledSnapshots.reverse();x.history.data.history.reverse();x.delivery.reverse();});
 assert.deepEqual(a,b);
});
test('no attempt is invented for skipped, cancelled or future quizzes',()=>{
 const r=run();assert.equal(r.attempts.length,4);
 const bad=run(x=>x.scheduledSnapshots[7].quiz.participation={id:'p',startedAt:'2026-10-08T14:31:00Z',completedAt:null,score:0});
 assert.equal(bad.status,'partial');assert.equal(bad.attempts.length,4);
});
test('time-only rescheduling is not delivery proof; demo mode/config must be explicit',()=>{
 assert.throws(()=>run(x=>x.demo=false),/demo/i);
 const c=structuredClone(cfg);delete c.quiz_loader.event_id_prefix;assert.throws(()=>run(()=>{},c),/config/i);
 const r=run(x=>{x.delivery=[];x.history.data.history=[];x.history.meta.total=0;x.scheduledSnapshots.forEach(s=>{s.quiz.status='SCHEDULED';s.quiz.participation=null;});});
 assert.ok(r.events.every(e=>e.status==='planned'));assert.equal(r.attempts.length,0);
});

test('millisecond precision and unsupported same-day deliveries remain explicit',()=>{
 const r=run(x=>x.history.data.history[0].startedAt='2026-10-01T14:30:00.125Z');
 assert.equal(r.attempts[0].started_at,'2026-10-01 20:00:00.125');
 const bad=run(x=>{const q=structuredClone(x.scheduledSnapshots[0]);q.quiz.id='second-same-day';x.scheduledSnapshots.push(q);});
 assert.equal(bad.status,'partial');assert.ok(!bad.events.some(e=>e.planned_for.startsWith('2026-10-01')));
});
test('history can recover delivery only with valid actual start evidence',()=>{
 const r=run(x=>{x.scheduledSnapshots=x.scheduledSnapshots.slice(1);x.delivery=x.delivery.slice(1);});
 assert.equal(r.events.length,9);assert.equal(r.events[0].source,'app_api');
 const bad=run(x=>{x.scheduledSnapshots=x.scheduledSnapshots.slice(1);x.delivery=x.delivery.slice(1);x.history.data.history[0].startedAt=null;});
 assert.equal(bad.status,'partial');assert.equal(bad.events.length,8);
});
