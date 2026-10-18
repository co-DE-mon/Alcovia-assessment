"""Verify quiz demo rows against all four KPIs and their visible drill/profile outputs."""
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import unittest
import yaml
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'student-tracker'))
import duckdb
import metrics

class QuizKpis(unittest.TestCase):
    def setUp(self):
        self.pack=json.loads((ROOT/'n8n/tests/fixtures/demo/quiz-input.json').read_text())
        self.cfg=yaml.safe_load((ROOT/'student-tracker/config.yaml').read_text())
        script="const fs=require('fs'),x=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(require('./n8n/code/quizzes.js').mapQuizzes(x.pack,x.cfg,require('./n8n/code/normalise.js'))));"
        self.mapped=json.loads(subprocess.check_output(['node','-e',script],input=json.dumps(dict(pack=self.pack,cfg=self.cfg)),text=True,cwd=ROOT))
        self.con=duckdb.connect(':memory:')
        self.con.execute((ROOT/'student-tracker/sql/schema/student.sql').read_text())
        self.con.execute((ROOT/'student-tracker/sql/schema/macros.sql').read_text())
        self.con.execute("INSERT INTO students (student_id,name,grade,advisor_id,program_start_date,wearable) VALUES (?,'Quiz Demo',10,'DEMO-ADV','2026-01-01','none')",[self.pack['studentId']])
        for table,key in [('events','events'),('quiz_attempts','attempts')]:
            for row in self.mapped[key]:self.con.execute('INSERT INTO '+table+' ('+', '.join(row)+') VALUES ('+', '.join('?' for _ in row)+')',list(row.values()))
        self.prm=metrics.params(self.cfg,date(2026,10,1),date(2026,10,8))
        self.prm['student_id']=self.pack['studentId']
    def tearDown(self):self.con.close()
    def run_query(self,file,name):return metrics.run(self.con,file,name,self.prm)
    def test_all_four_quiz_kpis_include_delivery_without_attempts(self):
        r=self.run_query('daily','quiz_summary')[0]
        self.assertEqual(r['quizzes_held'],7);self.assertEqual(r['started'],4);self.assertEqual(r['completed'],3)
        self.assertEqual(r['held_rate'],7/8);self.assertEqual(r['completion_rate'],3/4)
        self.assertEqual(r['in_window_rate'],3/7)
        self.assertEqual(self.run_query('daily','quiz_regular_takers')[0]['regular_taker_rate'],1)
        by_day={str(x['day']):x for x in self.run_query('daily','quiz_daily')}
        self.assertEqual(by_day['2026-10-05']['started'],0)
        self.assertFalse(by_day['2026-10-08']['held']);self.assertIsNone(by_day['2026-10-08']['started'])
    def test_window_has_both_bounds_and_preserves_subsecond_precision(self):
        event=self.cfg['quiz_loader']['event_id_prefix']+'DEMO-QUIZ-1'
        for time,want in [('19:59:59.999',False),('20:00:00',True),('20:15:00',True),('20:15:00.001',False)]:
            with self.subTest(time=time):
                self.con.execute('UPDATE quiz_attempts SET started_at=? WHERE event_id=?',['2026-10-01 '+time,event])
                daily=next(x for x in self.run_query('daily','quiz_daily') if str(x['day'])=='2026-10-01')
                self.assertEqual(daily['started_in_window'],int(want))
                expected=2+int(want)
                self.assertEqual(self.run_query('daily','quiz_summary')[0]['started_in_window'],expected)
                self.assertEqual(self.run_query('drill','quiz_by_student')[0]['Started on time'],expected)
                profile=next(x for x in self.run_query('profile','profile_quizzes') if str(x['Day'])=='2026-10-01')
                self.assertEqual(profile['Start']=='Started on time',want)
    def test_window_threshold_comes_from_shared_configuration(self):
        self.cfg['quiz']['entry_window_minutes']=5
        self.prm=metrics.params(self.cfg,date(2026,10,1),date(2026,10,8))
        self.assertEqual(self.run_query('daily','quiz_summary')[0]['started_in_window'],2)

if __name__=='__main__':unittest.main()
