// Synthetic contract tests. No external service is called.
'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {execFileSync}=require('node:child_process');
const {mapWearables}=require('../code/wearables.js'),helpers=require('../code/normalise.js');
const cfg=JSON.parse(execFileSync('python3',['-B','-c',"import yaml,json,sys;print(json.dumps(yaml.safe_load(open(sys.argv[1]))))",path.join(__dirname,'../../student-tracker/config.yaml')],{encoding:'utf8'}));
const fixture=()=>JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/demo/wearables-input.json'),'utf8'));
const run=(change=()=>{},config=cfg)=>{const input=fixture();change(input);return mapWearables(input,config,helpers);};
test('each vendor unit converts to hours; strain and recovery stay unknown',()=>{
 const r=run();assert.equal(r.status,'ok');assert.equal(r.rows.length,6);
 assert.deepEqual(r.rows.map(x=>[x.student_id,x.day,x.sleep_hours,x.data_source]),[
  ['DEMO-STUDENT-2','2026-10-01',7.5,'apple'],['DEMO-STUDENT-2','2026-10-02',6.5,'apple'],
  ['DEMO-STUDENT-3','2026-10-01',7,'samsung'],['DEMO-STUDENT-3','2026-10-02',8,'samsung'],
  ['DEMO-STUDENT-4','2026-10-01',8.5,'garmin'],['DEMO-STUDENT-4','2026-10-02',7.5,'garmin']]);
 assert.ok(r.rows.every(x=>x.strain===null && x.recovery_pct===null));
});
test('a day with no sleep recorded produces no row, never a zero',()=>{
 assert.ok(!run().rows.some(x=>x.student_id==='DEMO-STUDENT-2' && x.day==='2026-10-03'));
});
test('unknown vendors, bad dates, future days, strings and out-of-range sleep are rejected without dropping valid rows',()=>{
 const cases=[x=>x.devices[0].vendor='whoop',x=>x.devices[0].readings[0].date='2026-02-30',x=>x.devices[0].readings[0].date='2026-10-10',
  x=>x.devices[0].readings[0].asleepMinutes='450',x=>x.devices[0].readings[0].asleepMinutes=1500,x=>x.devices[0].readings[0].asleepMinutes=-1];
 for(const change of cases){const r=run(change);assert.equal(r.status,'partial',String(change));assert.ok(r.rejects.length>=1);assert.ok(r.rows.some(x=>x.data_source==='garmin'));}
});
test('two vendors or two values for one student-day are a conflict and neither is loaded',()=>{
 const r=run(x=>x.devices.push({studentId:'DEMO-STUDENT-2',vendor:'garmin',readings:[{calendarDate:'2026-10-01',sleepTimeSeconds:3600}]}));
 assert.equal(r.status,'partial');assert.ok(!r.rows.some(x=>x.student_id==='DEMO-STUDENT-2' && x.day==='2026-10-01'));assert.ok(r.rows.some(x=>x.student_id==='DEMO-STUDENT-2' && x.day==='2026-10-02'));
 const same=run(x=>x.devices.push({studentId:'DEMO-STUDENT-2',vendor:'apple',readings:[{date:'2026-10-01',asleepMinutes:450}]}));
 assert.equal(same.status,'ok');assert.equal(same.rows.length,6);
});
test('demo mode, capture time and configuration are required',()=>{
 assert.throws(()=>run(x=>x.demo=false),/explicit/);
 assert.throws(()=>run(x=>x.asOf='2026-02-30T00:00:00Z'),/capture/);
 assert.throws(()=>run(()=>{},{}),/configuration/);
 assert.throws(()=>run(x=>x.devices=null),/invalid wearable inputs/);
});
