// Demo contract only: the fixture is not a recorded Alcovia response.
'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const helpers=require('../code/normalise.js');
const {mapChapters}=require('../code/chapters.js');
const root=path.join(__dirname,'../..');
const cfg=JSON.parse(execFileSync('python3',['-B','-c',"import yaml,json,sys;print(json.dumps(yaml.safe_load(open(sys.argv[1]))))",path.join(root,'student-tracker/config.yaml')],{encoding:'utf8'}));
const fixture=()=>JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/demo/chapter-input.json'),'utf8'));
const run=(change=()=>{},config=cfg)=>{const x=fixture();change(x);return mapChapters(x,config,helpers);};
const stage=(change,config)=>run(change,config).rows[0]?.stage_reached;

test('explicit demo evidence produces a complete row with source time in IST',()=>{
 const r=run();assert.equal(r.status,'ok');assert.equal(r.rows.length,1);
 assert.equal(r.rows[0].stage_reached,5);assert.equal(r.rows[0].updated_at,'2026-10-10 15:30:00');
 assert.equal(r.rows[0].subject,'Mathematics');assert.equal(r.rows[0].planned_month,'2026-09-01');
});
test('strict configurable practice threshold',()=>{
 for(const [score,want] of [[69.99,2],[70,2],[70.01,5]])assert.equal(stage(x=>Object.assign(x.chapters[0].scores[0],{marksObtained:score,accuracyPercentage:score})),want);
 const c=structuredClone(cfg);c.syllabus.practice_accuracy_pct=90;assert.equal(stage(()=>{},c),2);
});
test('strict configurable readiness threshold',()=>{
 for(const [score,want] of [[79.99,4],[80,4],[80.01,5]])assert.equal(stage(x=>Object.assign(x.chapters[0].scores[1],{marksObtained:score,accuracyPercentage:score})),want);
});
test('stage order is contiguous; a later score cannot prove earlier work',()=>{
 assert.equal(stage(x=>x.chapters[0].tasks[0].taskStatus='NotStarted'),0);
 assert.equal(stage(x=>x.chapters[0].tasks[1].taskStatus='InProgress'),1);
 assert.equal(stage(x=>x.supplement[0].timedPaper.withinTime=false),3);
});
test('task keys and score types come from configuration',()=>{
 const c=structuredClone(cfg);c.chapter_loader.task_types.reading=['videos'];
 assert.equal(stage(x=>x.chapters[0].tasks[0].taskType='videos',c),5);
});
test('missing evidence is partial and unmeasured, not fabricated',()=>{
 for(const change of [x=>x.plans=[],x=>delete x.supplement[0].stageChangedAt,x=>delete x.supplement[0].timedPaper,x=>delete x.chapters[0].tasks,x=>delete x.chapters[0].scores,x=>x.chapters[0].tasks[0].taskStatus='NotRequired']){
  const r=run(change);assert.equal(r.status,'partial');assert.equal(r.rows.length,0);assert.equal(r.rejects.length,1);
 }
 assert.equal(stage(x=>x.chapters[0].scores=[]),2);
});
test('invalid rows do not discard a valid chapter',()=>{
 const r=run(x=>x.chapters.push(null));assert.equal(r.status,'partial');assert.equal(r.rows.length,1);assert.equal(r.rejects.length,1);
});
test('ambiguous identity, dates, scores and unsupported values are rejected',()=>{
 for(const change of [x=>x.subjects.push({...x.subjects[0]}),x=>x.plans[0].studentId='someone-else',x=>x.plans[0].plannedMonth='2026-08-01',x=>x.plans[0].plannedMonth='2026-09-02',x=>x.chapters[0].quarterId='unknown',x=>x.chapters[0].scores[0].maxMarks=0,x=>x.chapters[0].scores[0].accuracyPercentage=50,x=>x.chapters[0].scores[0].marksObtained='',x=>x.chapters[0].tasks[0].taskStatus='Magic',x=>x.chapters[0].tasks.push({...x.chapters[0].tasks[0]})]){
  const r=run(change);assert.equal(r.status,'partial');assert.equal(r.rows.length,0);
 }
});
test('latest score wins independent of response order; conflicting ties are rejected',()=>{
 const add=x=>x.chapters[0].scores.push({...x.chapters[0].scores[0],id:'DEMO-NEW',attemptNo:2,recordedOn:'2026-10-11T10:00:00Z',marksObtained:65,accuracyPercentage:65});
 assert.equal(stage(add),2);assert.equal(stage(x=>{add(x);x.chapters[0].scores.reverse();}),2);
 assert.equal(run(x=>x.chapters[0].scores.push({...x.chapters[0].scores[0],id:'DEMO-CONFLICT',marksObtained:65,accuracyPercentage:65})).status,'partial');
});
test('same input always produces same rows; no polling clock creates activity',()=>{assert.deepEqual(run(),run());});
test('demo mode must be explicit and missing configuration fails closed',()=>{
 assert.throws(()=>run(x=>x.demo=false),/demo/i);
 const c=structuredClone(cfg);delete c.syllabus.practice_accuracy_pct;assert.throws(()=>run(()=>{},c),/config/i);
});


test('ambiguous duplicate chapters are both unmeasured independent of order',()=>{
 const a=run(x=>x.chapters.push({...x.chapters[0]}));
 assert.equal(a.rows.length,0);assert.equal(a.rejects.length,2);
});
test('score type mapping is configurable',()=>{
 const c=structuredClone(cfg);c.chapter_loader.score_types.readiness='Exam';
 assert.equal(stage(x=>x.chapters[0].scores[1].scoreType='Exam',c),5);
});
