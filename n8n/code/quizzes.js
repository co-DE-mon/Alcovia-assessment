/* Pure, explicitly synthetic quiz contract. No clock, requests, or credentials.
 * App-shaped snapshots and history are separate from the supplemental delivery ledger.
 */
'use strict';
function mapQuizzes(input, config, helpers) {
  if (input?.demo !== true) throw new Error('quiz demo mode must be explicit');
  const policy = config?.quiz_loader;
  if (!policy || typeof policy.event_id_prefix !== 'string' || !policy.event_id_prefix ||
      !policy.status_map || !Object.values(policy.status_map).every(v => ['ignore','planned','held','cancelled'].includes(v)) ||
      !['held','planned'].includes(policy.history_event_status) || typeof policy.preserve_final_status !== 'boolean') throw new Error('invalid quiz loader configuration');
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  const record = x => x !== null && typeof x === 'object' && !Array.isArray(x);
  const id = x => typeof x === 'string' && x.trim().length > 0;
  const timestamp = x => {
    const base = helpers.toIst(x);
    check(base && new Date(x.slice(0,10)+'T00:00:00Z').toISOString().slice(0,10) === x.slice(0,10), 'invalid zoned timestamp');
    const fraction = new Date(x).getUTCMilliseconds();
    return base + (fraction ? '.'+String(fraction).padStart(3,'0') : '');
  };
  timestamp(input.asOf);
  check(id(input.studentId) && Array.isArray(input.scheduledSnapshots) && Array.isArray(input.delivery), 'invalid quiz demo inputs');
  const events = new Map(), blocked = new Set(), groups = new Map(), rejects = [];
  const fail = (source, key, error) => rejects.push({source, quiz_id:key ?? null, reason:error.message});
  const deliveries = new Map();
  for (const d of input.delivery) {
    try {
      check(record(d) && id(d.quizId) && ['held','cancelled','planned'].includes(d.status), 'invalid explicit delivery evidence');
      check(!deliveries.has(d.quizId) || deliveries.get(d.quizId) === d.status, 'contradictory delivery evidence');
      deliveries.set(d.quizId,d.status);
    } catch (e) { if(d?.quizId) blocked.add(d.quizId); fail('delivery',d?.quizId,e); }
  }
  const addEvent = (quizId, title, scheduledAt, fallback) => {
    check(id(quizId) && !blocked.has(quizId), 'unknown or contradictory quiz identity/status');
    const status = deliveries.get(quizId) || fallback;
    check(['ignore','planned','held','cancelled'].includes(status), 'unknown quiz status');
    if(status === 'ignore') return null;
    const planned = timestamp(scheduledAt);
    check(status !== 'held' || Date.parse(scheduledAt) <= Date.parse(input.asOf), 'held quiz is in the future');
    const row = {event_id:policy.event_id_prefix+quizId,kind:'quiz',title:typeof title==='string' ? title : null,planned_for:planned,status,
                 group_id:null,owner_staff_id:null,posted_on:null,views:null,shares:null,source:deliveries.has(quizId)?'manual':'app_api',nps_score:null};
    const existing=events.get(quizId);
    check(!existing || JSON.stringify(existing)===JSON.stringify(row),'contradictory quiz metadata');
    events.set(quizId,row);return row;
  };
  const addAttempt = (quizId, startedAt, completedAt, score, totalQuestions) => {
    const event=events.get(quizId);
    check(event && !blocked.has(quizId) && event.status==='held','attempt has no confirmed held quiz');
    const started=timestamp(startedAt), completed=completedAt==null?null:timestamp(completedAt);
    check(started>=event.planned_for && Date.parse(startedAt)<=Date.parse(input.asOf),'attempt starts before quiz or after capture');
    check(!completed || completed>=started && Date.parse(completedAt)<=Date.parse(input.asOf),'invalid completion chronology');
    check(totalQuestions==null || Number.isInteger(totalQuestions) && totalQuestions>0,'invalid question count');
    if(completed) check(Number.isInteger(score) && totalQuestions>0 && score>=0 && score<=totalQuestions,'invalid completed score');
    const row={event_id:event.event_id,student_id:input.studentId,started_at:started,completed_at:completed,score:completed?score:null,total_questions:totalQuestions??null};
    if(!groups.has(quizId))groups.set(quizId,[]);groups.get(quizId).push(row);
  };
  const snapshots=[];
  for(const response of input.scheduledSnapshots) {
    const q=response?.data?.quiz ?? response?.quiz;
    if(q===null || response?.quiz===null || response?.data?.quiz===null)continue;
    try {
      check(record(q),'malformed scheduled quiz response');
      const event=addEvent(q.id,q.title,q.scheduledAt,policy.status_map[q.status]);
      if(event && q.participation!=null)snapshots.push(q);
    } catch(e) {if(q?.id)blocked.add(q.id);fail('scheduled',q?.id,e);}
  }
  let history=[];
  try {
    const h=input.history;
    check(record(h) && !h.error && h.success!==false,'history read failed');
    history=h.data?.history ?? h.history;
    check(Array.isArray(history),'malformed quiz history response');
    const total=h.meta?.total;
    if(total!==undefined)check(Number.isInteger(total) && total>=0 && new Set(history.filter(record).map(x=>x.quizId)).size>=total,'truncated quiz history');
  } catch(e) {history=[];fail('history',null,e);}
  for(const h of history) {
    try {
      check(record(h) && id(h.quizId),'invalid history row');
      if(!events.has(h.quizId)) {
        timestamp(h.startedAt);timestamp(h.scheduledAt);
        check(Date.parse(h.startedAt)>=Date.parse(h.scheduledAt) && Date.parse(h.startedAt)<=Date.parse(input.asOf),'invalid history delivery proof');
        addEvent(h.quizId,h.quizTitle,h.scheduledAt,policy.history_event_status);
      } else check(events.get(h.quizId).planned_for===timestamp(h.scheduledAt),'history schedule conflicts with captured quiz');
      addAttempt(h.quizId,h.startedAt,h.completedAt,h.score,h.totalQuestions);
    } catch(e) {fail('history',h?.quizId,e);}
  }
  for(const q of snapshots) {
    try {addAttempt(q.id,q.participation.startedAt,q.participation.completedAt,q.participation.score,q.questionCount);}
    catch(e) {fail('participation',q.id,e);}
  }
  // Current dashboard assumes one quiz per day. Ambiguous days are not arbitrarily selected.
  const days=new Map();
  for(const [key,event] of events) {
    const day=event.planned_for.slice(0,10);
    if(!days.has(day))days.set(day,[]);days.get(day).push(key);
  }
  for(const keys of days.values())if(keys.length>1)for(const key of keys){blocked.add(key);fail('scheduled',key,new Error('multiple quizzes on one day unsupported by dashboard'));}
  const attempts=[];
  for(const [key,rows] of groups) {
    if(blocked.has(key))continue;
    try {
      const started=new Set(rows.map(r=>r.started_at));check(started.size===1,'conflicting attempt start times');
      const totals=new Set(rows.map(r=>r.total_questions).filter(v=>v!==null));check(totals.size<=1,'conflicting question counts');
      const complete=rows.filter(r=>r.completed_at);
      const variants=new Set(complete.map(r=>JSON.stringify(r)));check(variants.size<=1,'contradictory completed attempts');
      const selected={...(complete[0]||rows[0])};selected.total_questions=[...totals][0]??null;attempts.push(selected);
    }catch(e){fail('attempt',key,e);}
  }
  const byId=(a,b)=>a.event_id.localeCompare(b.event_id);
  return {demo:true,status:rejects.length?'partial':'ok',events:[...events].filter(([key])=>!blocked.has(key)).map(([,e])=>e).sort(byId),attempts:attempts.sort(byId),rejects};
}
if(typeof module!=='undefined' && module.exports)module.exports={mapQuizzes};
