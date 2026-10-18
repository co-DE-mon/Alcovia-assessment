"""Synthetic wellness loader -> DuckDB KPI, drill, profile and reconnect checks."""
from datetime import date
import json
from pathlib import Path
import subprocess,sys,unittest
import yaml
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'student-tracker'))
import duckdb,metrics

class WellnessKpis(unittest.TestCase):
    def setUp(self):
        self.pack=json.loads((ROOT/'n8n/tests/fixtures/demo/wellness-input.json').read_text())
        self.cfg=yaml.safe_load((ROOT/'student-tracker/config.yaml').read_text())
        script="const fs=require('fs'),x=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(require('./n8n/code/wellness.js').mapWellness(x.pack,x.cfg,require('./n8n/code/normalise.js'))));"
        self.mapped=json.loads(subprocess.check_output(['node','-e',script],input=json.dumps(dict(pack=self.pack,cfg=self.cfg)),text=True,cwd=ROOT))
        self.con=duckdb.connect(':memory:')
        self.con.execute((ROOT/'student-tracker/sql/schema/student.sql').read_text())
        self.con.execute((ROOT/'student-tracker/sql/schema/macros.sql').read_text())
        self.con.execute("INSERT INTO students (student_id,name,grade,advisor_id,program_start_date,wearable,wearable_connected_on) VALUES (?,'Wellness Demo',10,'DEMO-ADV','2026-01-01','whoop','2026-09-01')",[self.pack['studentId']])
        for row in self.mapped['rows']:
            self.con.execute('INSERT INTO wearable_daily ('+', '.join(row)+') VALUES ('+', '.join('?' for _ in row)+')',list(row.values()))
        self.prm=metrics.params(self.cfg,date(2026,10,1),date(2026,10,7));self.prm['student_id']=self.pack['studentId']
    def tearDown(self):self.con.close()
    def query(self,file,name):return metrics.run(self.con,file,name,self.prm)
    def test_all_five_wellness_kpis_and_detail_consistency(self):
        r=self.query('daily','wearable_summary')[0]
        self.assertEqual(r['student_days'],7);self.assertEqual(r['strain_days'],3);self.assertEqual(r['strain_coverage'],3/7)
        self.assertEqual(r['recovery_days'],3);self.assertEqual(r['avg_recovery_pct'],55);self.assertEqual(r['low_recovery_days'],1)
        self.assertEqual(r['strain_in_band_rate'],2/3);self.assertEqual(r['sleep_days'],4);self.assertEqual(r['sleep_target_rate'],3/4)
        self.assertEqual(r['avg_sleep_hours'],8)
        drill=self.query('drill','wearable_by_student')[0]
        self.assertEqual(drill['Days with strain data'],3);self.assertEqual(drill['Nights at the sleep target'],3)
        profile=self.query('profile','profile_wearable');self.assertEqual(len(profile),4)
        manual=next(x for x in profile if x['Source']=='manual');self.assertIsNone(manual['Strain']);self.assertIsNone(manual['Recovery %'])
        self.assertEqual(self.query('daily','whoop_syncing')[0]['sync_rate'],0)
        self.assertEqual(len(self.query('health','whoop_reconnect')),1)
    def test_manual_reading_never_rescues_whoop_sync_status(self):
        self.con.execute("UPDATE wearable_daily SET day='2026-10-07' WHERE data_source='manual'")
        self.assertEqual(self.query('daily','whoop_syncing')[0]['sync_rate'],0)
        self.con.execute("INSERT INTO wearable_daily VALUES (?, '2026-10-05',0,NULL,NULL,'whoop')",[self.pack['studentId']])
        self.assertEqual(self.query('daily','whoop_syncing')[0]['sync_rate'],1)
        self.assertEqual(len(self.query('health','whoop_reconnect')),0)
    def test_empty_measurements_have_null_rates_and_configured_thresholds_apply(self):
        self.cfg['wellness']['strain_band']=[0,8];self.cfg['wellness']['sleep_target_hours']=9
        self.prm=metrics.params(self.cfg,date(2026,10,1),date(2026,10,7))
        r=self.query('daily','wearable_summary')[0]
        self.assertEqual(r['strain_in_band_rate'],2/3);self.assertEqual(r['sleep_target_rate'],1/4)
        self.con.execute('DELETE FROM wearable_daily')
        r=self.query('daily','wearable_summary')[0]
        self.assertEqual(r['strain_coverage'],0)
        for field in ['strain_in_band_rate','avg_recovery_pct','sleep_target_rate','avg_sleep_hours']:self.assertIsNone(r[field])

if __name__=='__main__':unittest.main()
