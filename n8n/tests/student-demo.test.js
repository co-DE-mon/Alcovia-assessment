'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const workflow=JSON.parse(fs.readFileSync(path.join(__dirname,'../student-tracker-demo.json'),'utf8'));
const evidence=()=>structuredClone(workflow.nodes.find(n=>n.name==='Demo inputs').parameters.assignments.assignments[0].value);
const code=workflow.nodes.find(n=>n.name==='Map shared cohort').parameters.jsCode;
const map=change=>{const x=evidence();if(change)change(x);return new Function('$',code)(()=>({first:()=>({json:{evidence:x}})}))[0].json;};
test('integrated workflow maps a complete two-student cohort using existing source mappers',()=>{
 const r=map();assert.equal(r.tables.students.length,2);assert.equal(Object.keys(r.tables).length,16);
 assert.equal(r.tables.chapter_progress.length,1);assert.equal(r.tables.quiz_attempts.length,4);assert.equal(r.tables.wearable_daily.length,4);assert.equal(r.tables.feedback.length,18);
 assert.equal(r.tables.advisor_inputs.length,20);assert.equal(r.tables.exam_targets.length,2);assert.equal(r.tables.ingest_log.length,0);
 const ids=new Set(r.tables.students.map(s=>s.student_id));for(const rows of Object.values(r.tables))for(const row of rows)if('student_id'in row)assert.ok(ids.has(row.student_id));
});
test('a partial source, missing roster student, invalid duty or exam score stops the bundle',()=>{
 for(const change of [x=>x.feedback.adminPages.pop(),x=>x.wellness.studentId='DEMO-ORPHAN',x=>x.cohort.advisor_inputs[0].done='yes',x=>x.cohort.exam_targets[0].actual_score=101,x=>delete x.cohort.students[0].wearable_disconnected_on])assert.throws(()=>map(change));
});
test('same evidence is deterministic; a changed input changes only its mapped target',()=>{
 assert.deepEqual(map(),map());
 assert.equal(map(x=>x.cohort.exam_targets[0].actual_score=90).tables.exam_targets[0].actual_score,90);
});
