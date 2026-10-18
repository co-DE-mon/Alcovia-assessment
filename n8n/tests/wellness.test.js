// Synthetic contract tests. No external service is called.
'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {execFileSync}=require('node:child_process');
const {mapWellness}=require('../code/wellness.js'),helpers=require('../code/normalise.js');
const cfg=JSON.parse(execFileSync('python3',['-B','-c',"import yaml,json,sys;print(json.dumps(yaml.safe_load(open(sys.argv[1]))))",path.join(__dirname,'../../student-tracker/config.yaml')],{encoding:'utf8'}));
const fixture=()=>JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/demo/wellness-input.json'),'utf8'));
const run=(change=()=>{},config=cfg)=>{const input=fixture();change(input);return mapWellness(input,config,helpers);};
test('history milliseconds and manual hours map to four distinct daily rows',()=>{
 const r=run();assert.equal(r.status,'ok');assert.equal(r.rows.length,4);assert.deepEqual(r.rows.map(x=>x.sleep_hours),[8,7,9,8]);
 assert.equal(r.rows[3].strain,null);assert.equal(r.rows[3].recovery_pct,null);assert.equal(r.rows[3].data_source,'manual');
 assert.equal(r.rows[2].strain,0);assert.equal(r.emptyReadings,2);
});
test('missing readings remain absent; incomplete stages never become a complete sleep total',()=>{
 const r=run(x=>{x.history.data.history[0].sleepStageDeepMs=null;});assert.equal(r.rows[0].sleep_hours,null);
 const empty=run(x=>{x.history.data.history=[];x.dailySnapshots=[];});assert.equal(empty.rows.length,0);assert.equal(empty.status,'ok');
});
test('failed and malformed history remain partial while valid snapshots still load',()=>{
 for(const bad of [{success:false},{error:'unavailable'},{history:null}]){const r=run(x=>x.history=bad);assert.equal(r.status,'partial');assert.equal(r.rows.length,1);}
});
test('unknown brands, invalid dates, future days and mixed identities are rejected',()=>{
 for(const change of [x=>x.history.data.history[0].dataSource='GARMIN',x=>x.history.data.history[0].date='2026-02-30',x=>x.history.data.history[0].date='2026-10-10',x=>x.history.data.history[0].date='2026-10-01T00:00:00Z',x=>x.dailySnapshots[0].response.data.studentId='someone-else',x=>x.dailySnapshots[0].requestedDay='2026-10-03'])assert.equal(run(change).status,'partial');
});
test('invalid numeric readings and duration strings are rejected without coercion',()=>{
 for(const change of [x=>x.history.data.history[0].dayStrain=22,x=>x.history.data.history[0].recoveryScore=-1,x=>x.history.data.history[0].sleepStageRemMs='',x=>x.history.data.history[0].sleepStageRemMs='1e7',x=>x.history.data.history[0].dayStrain='8',x=>x.dailySnapshots[0].response.data.manualSleepHours=25])assert.equal(run(change).status,'partial');
});
test('manual estimates and activity never populate measured metrics',()=>{
 const r=run(x=>{const h=x.history.data.history[0];h.dataSource='MANUAL';h.sleepStageLightMs='28800000';});
 assert.ok(!r.rows.some(x=>x.day==='2026-10-01'));
});
test('same-day Whoop evidence takes precedence without borrowing manual sleep',()=>{
 const r=run(x=>x.history.data.history.push({date:'2026-10-04',dataSource:'WHOOP',dayStrain:9,recoveryScore:50}));
 const row=r.rows.find(x=>x.day==='2026-10-04');assert.equal(row.data_source,'whoop');assert.equal(row.sleep_hours,null);
});
test('exact duplicates collapse, conflicting same-source values reject the day independent of order',()=>{
 assert.equal(run(x=>x.history.data.history.push({...x.history.data.history[0]})).rows.length,4);
 const change=x=>x.history.data.history.push({...x.history.data.history[0],dayStrain:10});
 const r=run(change);assert.equal(r.status,'partial');assert.ok(!r.rows.some(x=>x.day==='2026-10-01'));
 const reversed=run(x=>{change(x);x.history.data.history.reverse();});assert.deepEqual(r.rows,reversed.rows);
});
test('snapshot and history complement same-source readings',()=>{
 const r=run(x=>x.dailySnapshots.push({requestedDay:'2026-10-01',response:{date:'2026-10-01',studentId:x.studentId,dataSource:'WHOOP',dayStrain:8,recoveryScore:32}}));
 assert.equal(r.rows[0].sleep_hours,8);assert.equal(r.status,'ok');
});
test('source priority and validation bounds come from configuration',()=>{
 const c=structuredClone(cfg);c.wellness_loader.source_priority=['manual','whoop'];
 const r=run(x=>x.history.data.history.push({date:'2026-10-04',dataSource:'WHOOP',dayStrain:9}),c);assert.equal(r.rows[3].data_source,'manual');
 c.wellness_loader.strain_range=[0,10];assert.equal(run(()=>{},c).status,'partial');
});
test('explicit capture date uses IST at midnight; no machine clock or timestamp date guessing',()=>{
 const r=run(x=>x.history.data.history.push({date:'2026-10-09',dataSource:'WHOOP',dayStrain:1}));assert.equal(r.status,'ok');assert.equal(r.rows.at(-1).day,'2026-10-09');
 assert.throws(()=>run(x=>x.asOf='2026-10-08T18:45:00'),/capture/);
 assert.throws(()=>run(x=>x.demo=false),/demo/);
 const c=structuredClone(cfg);delete c.wellness_loader;assert.throws(()=>run(()=>{},c),/configuration/);
});

test('failed snapshots and truncated history are explicit partial reads',()=>{
 let r=run(x=>x.dailySnapshots[0].response={success:false});assert.equal(r.status,'partial');assert.equal(r.rows.length,3);
 r=run(x=>x.history.meta={total:20});assert.equal(r.status,'partial');assert.equal(r.rows.length,1);
 assert.throws(()=>run(x=>x.asOf='2026-02-30T12:00:00Z'),/capture/);
});
test('explicit zero measurements stay zero rather than disappearing as missing',()=>{
 const r=run(x=>{const h=x.history.data.history[0];h.dayStrain=0;h.recoveryScore=0;h.sleepStageLightMs='0';h.sleepStageDeepMs='0';h.sleepStageRemMs='0';});
 assert.equal(r.rows[0].strain,0);assert.equal(r.rows[0].recovery_pct,0);assert.equal(r.rows[0].sleep_hours,0);
});
