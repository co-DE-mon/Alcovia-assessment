/* One synthetic cohort -> the existing app/demo mappers -> one atomic database payload. */
'use strict';
function mapStudentDemo(input,config,helpers) {
  const check=(ok,message)=>{if(!ok)throw new Error(message);};
  check(input?.demo===true && input.cohort?.demo===true,'integrated demo must be explicitly synthetic');
  check(helpers.toIst(input.cohort.asOf),'invalid cohort capture time');
  const base=helpers.normalise(input.base);
  const chapters=helpers.mapChapters(input.chapters,config,helpers);
  const quizzes=helpers.mapQuizzes(input.quizzes,config,helpers);
  const wellness=helpers.mapWellness(input.wellness,config,helpers);
  const feedback=helpers.mapFeedback(input.feedback,config,helpers);
  check([base,chapters,quizzes,wellness,feedback].every(result=>result.status==='ok'),'a source bundle is partial; inspect source evidence before importing');
  const tables={...base.rows,ingest_log:[]};
  const existing=new Map(tables.students.map(row=>[row.student_id,row]));
  tables.students=input.cohort.students.map(row=>({...existing.get(row.student_id),...row}));
  for(const row of tables.students)check(row.wearable!=='whoop' || row.wearable_connected_on && row.wearable_disconnected_on==null,'contradictory connected wearable state in roster');
  const students=new Set(tables.students.map(row=>row.student_id));
  check(students.size===tables.students.length && [...students].every(id=>typeof id==='string' && id.startsWith('DEMO-')),'invalid synthetic roster');
  tables.staff=[...new Map([...tables.staff,...input.cohort.staff].map(row=>[row.staff_id,row])).values()];
  tables.events.push(...quizzes.events,...input.feedback.eventLinks.map(link=>({event_id:link.eventId,kind:link.kind,title:link.eventId,planned_for:helpers.toIst(link.plannedFor),status:link.status,source:'manual'})));
  tables.quiz_attempts=quizzes.attempts;tables.chapter_progress=chapters.rows;tables.wearable_daily=wellness.rows;tables.feedback=feedback.rows;
  tables.advisor_inputs=input.cohort.advisor_inputs;tables.exam_targets=input.cohort.exam_targets;
  for(const row of tables.advisor_inputs)check(config.advisor_input_kinds.includes(row.input_kind) && typeof row.done==='boolean' && row.source==='manual' && /^\d{4}-\d{2}-01$/.test(row.month) && helpers.toIst(row.month+'T00:00:00Z'),'invalid explicit advisor input');
  const max=input.cohort.examScoreMax;
  check(Number.isFinite(max) && max>0,'explicit exam score scale required');
  for(const row of tables.exam_targets)check(['formative','unit_test','mid_term'].includes(row.exam_type) && row.subject && Number.isFinite(row.target_score) && row.target_score>=0 && row.target_score<=max && (row.actual_score===null || Number.isFinite(row.actual_score) && row.actual_score>=0 && row.actual_score<=max),'invalid single-cycle exam target');
  const events=new Set(tables.events.map(row=>row.event_id));
  check(events.size===tables.events.length,'duplicate event identity across demo sources');
  const staff=new Set(tables.staff.map(row=>row.staff_id));
  for(const row of tables.students)check(staff.has(row.advisor_id),'student has no advisor');
  for(const [table,rows] of Object.entries(tables))for(const row of rows){
    if('student_id' in row)check(students.has(row.student_id),'row has no student in the shared roster');
    if(table!=='events' && row.event_id!=null)check(events.has(row.event_id),'row has no event in the shared bundle');
  }
  return {demo:true,tables,asOf:input.cohort.asOf,counts:Object.fromEntries(Object.entries(tables).map(([name,rows])=>[name,rows.length]))};
}
if(typeof module!=='undefined' && module.exports)module.exports={mapStudentDemo};
