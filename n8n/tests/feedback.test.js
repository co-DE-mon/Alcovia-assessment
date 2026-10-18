// Submitted feedback demonstration; no API calls.
'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{execFileSync}=require('node:child_process');
const {mapFeedback}=require('../code/feedback.js'),helpers=require('../code/normalise.js');
const cfg=JSON.parse(execFileSync('python3',['-B','-c',"import yaml,json,sys;print(json.dumps(yaml.safe_load(open(sys.argv[1]))))",path.join(__dirname,'../../student-tracker/config.yaml')],{encoding:'utf8'}));
const fixture=()=>JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/demo/feedback-input.json'),'utf8'));
const run=(change=()=>{},config=cfg)=>{const x=fixture();change(x);return mapFeedback(x,config,helpers);};
test('paged submitted forms and proposed exports map with original composites',()=>{
 const r=run();assert.equal(r.status,'ok');assert.equal(r.rows.length,18);const row=r.rows.find(r=>r.feedback_id.endsWith('DEMO-ADMIN-FB-1'));
 assert.equal(row.composite,4.15);assert.equal(row.submitted_at,'2026-10-01 16:30:00');assert.equal(r.rows.find(r=>r.kind==='roadmap').submitted_at,'2026-10-03 00:15:00');
});
test('comment text is reduced to a flag and never enters rows or rejection details',()=>{
 const marker='PRIVATE_COMMENT_SENTINEL';let r=run(x=>x.adminPages[0].rows[0].openComment=marker);
 assert.equal(r.rows.find(r=>r.feedback_id.endsWith('DEMO-ADMIN-FB-1')).has_comment,true);assert.ok(!JSON.stringify(r).includes(marker));
 r=run(x=>{x.adminPages[0].rows[0].openComment=marker;x.adminPages[0].rows[0].q1Rating=0;});assert.ok(!JSON.stringify(r).includes(marker));
});
test('unknown ratings stay null and missing composite is never recomputed',()=>{
 const r=run(x=>{const row=x.adminPages[0].rows[0];row.q2Rating=null;row.compositeScore=null;});
 const row=r.rows.find(r=>r.feedback_id.endsWith('DEMO-ADMIN-FB-1'));assert.equal(row.q2_rating,null);assert.equal(row.composite,null);
});
test('failed or truncated admin pages preserve independent valid exports',()=>{
 for(const change of [x=>x.adminPages.pop(),x=>x.adminPages[1]={success:false},x=>x.adminPages[1].total=9,x=>x.adminPages[0].rows=null]){const r=run(change);assert.equal(r.status,'partial');assert.equal(r.rows.length,10);}
});
test('invalid ratings, times, sources and student identities are rejected',()=>{
 for(const change of [x=>x.adminPages[0].rows[0].q1Rating=0,x=>x.adminPages[0].rows[0].q1Rating=2.5,x=>x.adminPages[0].rows[0].compositeScore=6,x=>x.adminPages[0].rows[0].q1Rating='5',x=>x.adminPages[0].rows[0].submittedAt='2026-09-30T10:00:00Z',x=>x.adminPages[0].rows[0].submittedAt='2026-10-09T10:00:00Z',x=>x.adminPages[0].rows[0].sessionType='unknown',x=>x.adminPages[0].rows[0].studentId='unknown',x=>x.exportResponse.rows[0].kind='unknown'])assert.equal(run(change).status,'partial');
});
test('event identity, held state and kind must agree with explicit links',()=>{
 for(const change of [x=>x.adminPages[0].rows[0].sessionId='missing',x=>x.eventLinks[0].status='cancelled',x=>x.eventLinks[0].kind='pod',x=>x.exportResponse.rows[0].eventId=null,x=>x.exportResponse.rows.at(-1).eventId=x.eventLinks[0].eventId])assert.equal(run(change).status,'partial');
});
test('exact duplicates collapse; contradictory IDs and duplicate submissions reject both',()=>{
 assert.equal(run(x=>x.adminPages[0].rows.push({...x.adminPages[0].rows[0]})).rows.length,18);
 let r=run(x=>x.adminPages[0].rows.push({...x.adminPages[0].rows[0],q1Rating:4}));assert.equal(r.rows.length,17);assert.equal(r.status,'partial');
 r=run(x=>{x.adminPages[0].rows.push({...x.adminPages[0].rows[0],id:'another-id'});x.adminPages.forEach(p=>p.total=9);});assert.equal(r.rows.length,17);assert.equal(r.status,'partial');
});
test('missing sources are failures and explicit empty responses are harmless',()=>{
 const r=run(x=>{x.adminPages=[];x.exportResponse={rows:[]};});assert.equal(r.rows.length,0);assert.equal(r.status,'ok');
 assert.equal(run(x=>x.exportResponse={error:'unavailable'}).rows.length,8);
 assert.equal(run(x=>delete x.adminPages).status,'partial');
});
test('configuration supplies prefixes and validation bounds, demo is explicit',()=>{
 const c=structuredClone(cfg);c.feedback_loader.id_prefix='test-feedback/';assert.ok(run(()=>{},c).rows.every(r=>r.feedback_id.startsWith('test-feedback/')));
 assert.throws(()=>run(x=>x.demo=false),/demo/);assert.throws(()=>run(x=>x.asOf='2026-02-30T12:00:00Z'),/timestamp/);
});
test('pending lists and submission receipts cannot impersonate submitted exports',()=>{
 assert.equal(run(x=>x.exportResponse={pending:[{id:'p'}]}).status,'partial');
 assert.equal(run(x=>x.exportResponse={message:'submitted'}).status,'partial');
});

test('monthly duplicate check-ins and cross-source duplicates are not double counted',()=>{
 const r=run(x=>x.exportResponse.rows.push({...x.exportResponse.rows.find(r=>r.kind==='roadmap'),id:'second-roadmap'}));
 assert.equal(r.status,'partial');assert.ok(!r.rows.some(r=>r.kind==='roadmap'));
 const dup=run(x=>x.exportResponse.rows.push({id:'export-duplicate',studentId:x.studentIds[0],eventId:x.eventLinks[0].eventId,kind:'session',q1Rating:5,q2Rating:3,q3Rating:4,compositeScore:4.15,hasComment:false,submittedAt:'2026-10-01T11:00:00Z'}));
 assert.equal(dup.status,'partial');assert.equal(dup.rows.length,17);
});
test('row order cannot change accepted data and no extra source fields leak',()=>{
 const r=run(),reversed=run(x=>{x.adminPages.reverse();x.adminPages.forEach(p=>p.rows.reverse());x.exportResponse.rows.reverse();});assert.deepEqual(r,reversed);
 assert.deepEqual(Object.keys(r.rows[0]).sort(),['feedback_id','student_id','event_id','kind','q1_rating','q2_rating','q3_rating','composite','has_comment','submitted_at'].sort());
});
