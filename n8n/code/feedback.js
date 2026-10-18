/* Submitted feedback DEMO. Pure mapper; no clock, API calls or retained comment text. */
'use strict';
function mapFeedback(input, config, helpers) {
  const check=(ok,message)=>{if(!ok)throw new Error(message);};
  const record=x=>x!==null && typeof x==='object' && !Array.isArray(x);
  const id=x=>typeof x==='string' && x.trim().length>0;
  check(input?.demo===true,'feedback demo mode must be explicit');
  const policy=config?.feedback_loader;
  check(policy && id(policy.id_prefix) && Array.isArray(policy.rating_range) && policy.rating_range.length===2 &&
    policy.rating_range.every(Number.isFinite) && policy.rating_range[0]>=1 && policy.rating_range[1]<=5 && policy.rating_range[0]<policy.rating_range[1] &&
    record(policy.session_type_map) && record(policy.kind_event_map) &&
    Object.values(policy.kind_event_map).every(x=>Array.isArray(x) && x.every(id)) &&
    Array.isArray(policy.monthly_kinds) && policy.monthly_kinds.every(k=>Array.isArray(policy.kind_event_map[k]) && policy.kind_event_map[k].length===0), 'invalid feedback configuration');
  const timestamp=value=>{
    const converted=helpers.toIst(value);
    check(converted && new Date(value.slice(0,10)+'T00:00:00Z').toISOString().slice(0,10)===value.slice(0,10),'invalid zoned timestamp');
    const ms=new Date(value).getUTCMilliseconds();return converted+(ms?'.'+String(ms).padStart(3,'0'):'');
  };
  timestamp(input.asOf);
  check(Array.isArray(input.studentIds) && input.studentIds.every(id) && Array.isArray(input.eventLinks),'invalid feedback roster or links');
  const students=new Set(input.studentIds),events=new Map(),sourceLinks=new Map(),blockedEvents=new Set(),rejects=[];
  const fail=(source,key,error)=>rejects.push({source,feedback_id:id(key)?key:null,reason:error.message});
  for(const link of input.eventLinks)try{
    check(record(link) && id(link.eventId) && id(link.sourceId) && id(link.kind),'invalid event link');timestamp(link.plannedFor);
    const old=events.get(link.eventId),mapped=sourceLinks.get(link.sourceId);
    check((!old || JSON.stringify(old)===JSON.stringify(link)) && (!mapped || mapped===link.eventId),'contradictory event links');
    events.set(link.eventId,link);sourceLinks.set(link.sourceId,link.eventId);
  }catch(e){if(link?.eventId)blockedEvents.add(link.eventId);if(link?.sourceId && sourceLinks.has(link.sourceId))blockedEvents.add(sourceLinks.get(link.sourceId));fail('links',null,e);}
  const unwrap=response=>{
    check(record(response) && response.success!==false && !response.error,'submitted feedback read failed');
    const body=response.data??response;check(record(body),'malformed feedback response');return body;
  };
  let admin=[];
  try{
    check(Array.isArray(input.adminPages),'missing submitted admin pages');let total=null;
    for(const response of input.adminPages){
      const body=unwrap(response);check(Array.isArray(body.rows) && Number.isInteger(body.total) && body.total>=0,'malformed submitted feedback page');
      check(total===null || total===body.total,'inconsistent feedback totals');total=body.total;admin.push(...body.rows);
    }
    check(total===null || new Set(admin.map(x=>x?.id)).size===total,'incomplete submitted feedback pages');
  }catch(e){admin=[];fail('admin',null,e);}
  let exported=[];
  try{const body=unwrap(input.exportResponse);check(Array.isArray(body.rows),'missing submitted export rows');exported=body.rows;}
  catch(e){fail('export',null,e);}
  const candidates=[];
  const rating=(value,integer)=>{
    if(value==null)return null;
    check(typeof value==='number' && Number.isFinite(value) && (!integer || Number.isInteger(value)) &&
      value>=policy.rating_range[0] && value<=policy.rating_range[1],'invalid feedback rating');return value;
  };
  for(const [source,rows] of [['admin',admin],['export',exported]])for(const raw of rows)try{
    check(record(raw) && id(raw.id) && students.has(raw.studentId),'unknown feedback or student identity');
    const kind=source==='admin'?policy.session_type_map[typeof raw.sessionType==='string'?raw.sessionType.toLowerCase().replace(/[^a-z0-9]/g,''):'']:raw.kind;
    check(Object.hasOwn(policy.kind_event_map,kind),'unknown feedback kind');
    const eventId=source==='admin'?sourceLinks.get(raw.sessionId):raw.eventId;
    const submitted=timestamp(raw.submittedAt);check(Date.parse(raw.submittedAt)<=Date.parse(input.asOf),'feedback is after capture');
    if(policy.monthly_kinds.includes(kind))check(eventId===null,'monthly feedback must not invent an event link');
    else{
      const event=events.get(eventId);
      check(event && !blockedEvents.has(eventId) && event.status==='held' && policy.kind_event_map[kind].includes(event.kind),'feedback has no matching held event');
      check(Date.parse(raw.submittedAt)>=Date.parse(event.plannedFor),'feedback predates its event');
    }
    let comment;
    if(source==='admin'){
      check(raw.openComment===null || typeof raw.openComment==='string','unknown comment presence');comment=typeof raw.openComment==='string' && raw.openComment.trim().length>0;
    }else{check(typeof raw.hasComment==='boolean','unknown comment presence');comment=raw.hasComment;}
    candidates.push({feedback_id:policy.id_prefix+source+':'+raw.id,student_id:raw.studentId,event_id:eventId,kind,
      q1_rating:rating(raw.q1Rating,true),q2_rating:rating(raw.q2Rating,true),q3_rating:rating(raw.q3Rating,true),
      composite:rating(raw.compositeScore,false),has_comment:comment,submitted_at:submitted});
  }catch(e){fail(source,raw?.id,e);}
  const byId=new Map(),blocked=new Set();
  for(const row of candidates){
    const old=byId.get(row.feedback_id);
    if(old && JSON.stringify(old)!==JSON.stringify(row)){blocked.add(row.feedback_id);fail('identity',row.feedback_id,new Error('contradictory feedback ID'));}
    else byId.set(row.feedback_id,row);
  }
  const natural=new Map();
  for(const row of byId.values()){
    const key=JSON.stringify(row.event_id===null?[row.student_id,row.kind,row.submitted_at.slice(0,7)]:[row.student_id,row.event_id]);
    if(!natural.has(key))natural.set(key,[]);natural.get(key).push(row.feedback_id);
  }
  for(const ids of natural.values())if(ids.length>1)for(const key of ids){blocked.add(key);fail('identity',key,new Error('multiple submitted forms for the same event or monthly check-in'));}
  const rows=[...byId.values()].filter(r=>!blocked.has(r.feedback_id)).sort((a,b)=>a.feedback_id.localeCompare(b.feedback_id));
  return {demo:true,status:rejects.length?'partial':'ok',rows,rejects};
}
if(typeof module!=='undefined' && module.exports)module.exports={mapFeedback};
