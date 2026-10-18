/* Pure synthetic mapper for Apple, Samsung and Garmin daily sleep. No network, clock, credentials or connection inference.
 * These vendors expose no strain or recovery score comparable to Whoop's, so only sleep_hours is filled; the other two stay NULL (unknown, never zero). */
'use strict';
function mapWearables(input, config, helpers) {
  const check=(ok,message)=>{if(!ok)throw new Error(message);};
  const record=x=>x!==null && typeof x==='object' && !Array.isArray(x);
  const policy=config?.wearable_loader;
  check(input?.demo===true,'wearable demo mode must be explicit');
  check(policy && record(policy.vendors) && Object.keys(policy.vendors).length>0 && Array.isArray(policy.sleep_hours_range) &&
    policy.sleep_hours_range.length===2 && policy.sleep_hours_range.every(Number.isFinite) && policy.sleep_hours_range[0]>=0 && policy.sleep_hours_range[0]<policy.sleep_hours_range[1] &&
    Object.values(policy.vendors).every(v=>record(v) && typeof v.date_field==='string' && typeof v.sleep_field==='string' && Number.isFinite(v.per_hour) && v.per_hour>0),'invalid wearable loader configuration');
  const capture=helpers.toIst(input.asOf);
  check(capture && new Date(input.asOf.slice(0,10)+'T00:00:00Z').toISOString().slice(0,10)===input.asOf.slice(0,10),'explicit valid zoned capture timestamp required');
  check(Array.isArray(input.devices),'invalid wearable inputs');
  const day=value=>{
    check(typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value+'T00:00:00Z')) &&
      new Date(value+'T00:00:00Z').toISOString().slice(0,10)===value,'invalid calendar day');
    check(value<=capture.slice(0,10),'reading day is after capture');return value;
  };
  const rejects=[],groups=new Map();
  const fail=(source,date,error)=>rejects.push({source,day:typeof date==='string'?date:null,reason:error.message});
  for(const device of input.devices)try{
    check(record(device) && typeof device.studentId==='string' && device.studentId.trim() && Array.isArray(device.readings),'malformed wearable device');
    const vendor=policy.vendors[device.vendor];check(vendor,'unsupported wearable vendor');
    for(const reading of device.readings)try{
      check(record(reading),'malformed wearable reading');
      const date=day(reading[vendor.date_field]);
      const raw=reading[vendor.sleep_field];
      if(raw==null)continue;                                   // no sleep recorded that day: no row, never zero
      check(typeof raw==='number' && Number.isFinite(raw),'invalid sleep duration');
      const hours=raw/vendor.per_hour;
      check(hours>=policy.sleep_hours_range[0] && hours<=policy.sleep_hours_range[1],'invalid sleep hours');
      const key=device.studentId+'|'+date;
      if(!groups.has(key))groups.set(key,[]);
      groups.get(key).push({student_id:device.studentId,day:date,strain:null,recovery_pct:null,sleep_hours:hours,data_source:device.vendor});
    }catch(e){fail(device.vendor,reading?.[vendor.date_field],e);}
  }catch(e){fail(device?.vendor,null,e);}
  const rows=[];
  for(const [key,candidates] of groups){
    const first=candidates[0];
    // One device per student-day: a second vendor or a different value for the same day is a conflict, so the day is skipped and named.
    if(candidates.some(c=>c.data_source!==first.data_source || c.sleep_hours!==first.sleep_hours)){fail('merge',first.day,new Error('conflicting wearable readings'));continue;}
    rows.push(first);
  }
  rows.sort((a,b)=>a.student_id.localeCompare(b.student_id) || a.day.localeCompare(b.day));
  return {demo:true,status:rejects.length?'partial':'ok',rows,rejects};
}
if(typeof module!=='undefined' && module.exports)module.exports={mapWearables};
