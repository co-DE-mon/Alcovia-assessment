/* Pure synthetic wellness mapper. No network, clock, credentials or connection inference. */
'use strict';
function mapWellness(input, config, helpers) {
  const check=(ok,message)=>{if(!ok)throw new Error(message);};
  const record=x=>x!==null && typeof x==='object' && !Array.isArray(x);
  const policy=config?.wellness_loader;
  const range=x=>Array.isArray(x) && x.length===2 && x.every(Number.isFinite) && x[0]>=0 && x[0]<x[1];
  check(input?.demo===true,'wellness demo mode must be explicit');
  check(policy && record(policy.source_map) && ['WHOOP','MANUAL'].every(k=>policy.source_map[k]===k.toLowerCase()) &&
    Object.values(policy.source_map).every(v=>['whoop','manual'].includes(v)) &&
    Array.isArray(policy.source_priority) && policy.source_priority.length===2 && new Set(policy.source_priority).size===2 &&
    policy.source_priority.every(v=>['whoop','manual'].includes(v)) &&
    [policy.strain_range,policy.recovery_pct_range,policy.sleep_hours_range].every(range),'invalid wellness loader configuration');
  const capture=helpers.toIst(input.asOf);
  check(capture && new Date(input.asOf.slice(0,10)+'T00:00:00Z').toISOString().slice(0,10)===input.asOf.slice(0,10),'explicit valid zoned capture timestamp required');
  check(typeof input.studentId==='string' && input.studentId.trim() && Array.isArray(input.dailySnapshots),'invalid wellness inputs');
  const day=value=>{
    check(typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
      Number.isFinite(Date.parse(value+'T00:00:00Z')) && new Date(value+'T00:00:00Z').toISOString().slice(0,10)===value,'invalid calendar day');
    check(value<=capture.slice(0,10),'reading day is after capture');return value;
  };
  const number=(value,bounds,label)=>{
    if(value==null)return null;
    check(typeof value==='number' && Number.isFinite(value) && value>=bounds[0] && value<=bounds[1],'invalid '+label);return value;
  };
  const duration=value=>{
    if(value==null)return null;
    check(typeof value==='string' && /^\d+$/.test(value),'invalid sleep duration milliseconds');
    const ms=Number(value);check(Number.isSafeInteger(ms),'invalid sleep duration milliseconds');return ms;
  };
  const unwrap=response=>{
    check(record(response) && response.success!==false && !response.error,'wellness read failed');
    const body=response.data??response;check(record(body),'malformed wellness response');return body;
  };
  const rejects=[],groups=new Map();let emptyReadings=0;
  const fail=(source,date,error)=>rejects.push({source,day:typeof date==='string'?date:null,reason:error.message});
  const add=(reading,source,requestedDay)=>{
    check(record(reading),'malformed wellness reading');
    const date=day(reading.date);
    check(requestedDay===undefined || date===day(requestedDay),'snapshot day differs from requested day');
    check(reading.studentId===undefined || reading.studentId===input.studentId,'snapshot belongs to another student');
    const kind=policy.source_map[reading.dataSource];check(['whoop','manual'].includes(kind),'unsupported wellness source');
    const row={student_id:input.studentId,day:date,strain:null,recovery_pct:null,sleep_hours:null,data_source:kind};
    if(kind==='manual') {
      // Activity and estimated recovery are not wearable measurements. Only explicit hours are usable.
      if(source==='snapshot')row.sleep_hours=number(reading.manualSleepHours,policy.sleep_hours_range,'manual sleep hours');
    } else {
      row.strain=number(reading.dayStrain,policy.strain_range,'strain');
      row.recovery_pct=number(reading.recoveryScore,policy.recovery_pct_range,'recovery percentage');
      if(source==='history') {
        const stages=['sleepStageLightMs','sleepStageDeepMs','sleepStageRemMs'].map(k=>duration(reading[k]));
        // A missing stage means an unknown total, never zero or a partial total presented as a full night.
        if(stages.every(v=>v!==null))row.sleep_hours=number(stages.reduce((a,b)=>a+b,0)/3600000,policy.sleep_hours_range,'sleep hours');
      }
    }
    if([row.strain,row.recovery_pct,row.sleep_hours].every(v=>v===null)){emptyReadings++;return;}
    if(!groups.has(date))groups.set(date,[]);groups.get(date).push(row);
  };
  let history=[];
  try {
    const body=unwrap(input.history);check(Array.isArray(body.history),'malformed wellness history');history=body.history;
    const total=input.history.meta?.total;
    check(total===undefined || Number.isInteger(total) && total>=0 && new Set(history.filter(record).map(x=>x.date)).size>=total,'truncated wellness history');
  }catch(e){history=[];fail('history',null,e);}
  for(const reading of history)try{add(reading,'history');}catch(e){fail('history',reading?.date,e);}
  for(const snapshot of input.dailySnapshots)try{
    check(record(snapshot),'malformed snapshot request');day(snapshot.requestedDay);
    add(unwrap(snapshot.response),'snapshot',snapshot.requestedDay);
  }catch(e){fail('snapshot',snapshot?.requestedDay,e);}
  const rows=[];
  for(const [date,candidates] of groups)try{
    const merged=[];
    for(const kind of policy.source_priority) {
      const matching=candidates.filter(r=>r.data_source===kind);if(!matching.length)continue;
      const row={...matching[0]};
      for(const field of ['strain','recovery_pct','sleep_hours']) {
        const values=new Set(matching.map(r=>r[field]).filter(v=>v!==null));
        check(values.size<=1,'conflicting '+kind+' '+field+' readings');row[field]=[...values][0]??null;
      }
      merged.push(row);
    }
    rows.push(merged[0]);
  }catch(e){fail('merge',date,e);}
  rows.sort((a,b)=>a.day.localeCompare(b.day));
  return {demo:true,status:rejects.length?'partial':'ok',rows,rejects,emptyReadings};
}
if(typeof module!=='undefined' && module.exports)module.exports={mapWellness};
