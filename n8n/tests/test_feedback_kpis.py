"""Synthetic submitted feedback -> every affected scorecard output and its detail queries."""
from datetime import date
import json
from pathlib import Path
import subprocess,sys,unittest
import yaml
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'student-tracker'))
import duckdb,metrics

class FeedbackKpis(unittest.TestCase):
    def setUp(self):
        self.pack=json.loads((ROOT/'n8n/tests/fixtures/demo/feedback-input.json').read_text())
        cfg=yaml.safe_load((ROOT/'student-tracker/config.yaml').read_text())
        script="const fs=require('fs'),x=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(require('./n8n/code/feedback.js').mapFeedback(x.pack,x.cfg,require('./n8n/code/normalise.js'))));"
        self.rows=json.loads(subprocess.check_output(['node','-e',script],input=json.dumps(dict(pack=self.pack,cfg=cfg)),text=True,cwd=ROOT))['rows']
        self.con=duckdb.connect(':memory:')
        self.con.execute((ROOT/'student-tracker/sql/schema/student.sql').read_text());self.con.execute((ROOT/'student-tracker/sql/schema/macros.sql').read_text())
        for sid in self.pack['studentIds']:self.con.execute("INSERT INTO students(student_id,name,grade,advisor_id,program_start_date,wearable) VALUES (?,?,10,'DEMO-ADV','2026-01-01','none')",[sid,sid])
        for event in self.pack['eventLinks']:
            self.con.execute("INSERT INTO events(event_id,kind,title,planned_for,status,source,nps_score) VALUES (?,?,?,?,'held','manual',?)",[event['eventId'],event['kind'],event['eventId'],event['plannedFor'],8 if event['kind']=='workshop' else None])
            for sid in self.pack['studentIds']:self.con.execute('INSERT INTO event_attendance(event_id,student_id,invited,attended) VALUES (?,?,true,true)',[event['eventId'],sid])
        for row in self.rows:self.con.execute('INSERT INTO feedback ('+', '.join(row)+') VALUES ('+', '.join('?' for _ in row)+')',list(row.values()))
        self.prm=metrics.params(cfg,date(2026,10,1),date(2026,10,8));self.prm['student_id']=self.pack['studentIds'][0]
    def tearDown(self):self.con.close()
    def query(self,file,name,**extra):return metrics.run(self.con,file,name,{**self.prm,**extra})
    def test_all_eighteen_selected_feedback_kpi_values(self):
        audit=json.loads((ROOT/'n8n/audit/source-coverage.json').read_text())
        affected=[k for k in audit['kpis'] if set(k['capabilities']) & {'session_feedback','roadmap_feedback','proposed_feedback'}]
        self.assertEqual(len(affected),18)
        for k in affected:
            with self.subTest(kpi=k['name'],activity=k['activity']):
                file,name=k['query'].split('.');result=self.query(file,name)
                for field,value in k['filters'].items():result=[row for row in result if row[field]==value]
                self.assertEqual(len(result),1)
                output=k['output_fields'][0]
                expected={'avg_pace':4,'avg_invested':3,'avg_confidence':5}.get(output)
                if expected is None:
                    if file=='quarterly':expected=4
                    elif file=='roadmaps':expected=4.2
                    elif file=='weekly':expected=(5*4.15+4.2)/6
                    else:expected=4.15 if k['filters'].get('kind') in {'academic_session','workshop','pod','mentor_call'} else 4.2
                self.assertAlmostEqual(result[0][output],expected)
    def test_response_denominators_and_nps_are_independent_of_missing_feedback(self):
        event=next(x for x in self.query('events','event_feedback') if x['kind']=='workshop')
        self.assertEqual(event['response_rate'],0.5);self.assertEqual(event['avg_nps'],8)
        self.assertEqual(self.query('roadmaps','roadmap_feedback')[0]['response_rate'],0.5)
        self.con.execute('DELETE FROM feedback')
        event=next(x for x in self.query('events','event_feedback') if x['kind']=='workshop')
        self.assertIsNone(event['avg_composite']);self.assertEqual(event['avg_nps'],8)
        self.assertIsNone(self.query('roadmaps','roadmap_feedback')[0]['avg_composite'])
        self.assertIsNone(self.query('quarterly','entrepreneurship_rating')[0]['avg_composite'])
    def test_drill_profile_and_roadmap_question_meanings(self):
        self.assertEqual(len(self.query('profile','profile_feedback')),18)
        self.assertEqual(len(self.query('drill','session_feedback_rows')),6)
        self.assertEqual(len(self.query('drill','event_feedback_rows',kind='podcast')),2)
        r=self.query('drill','roadmap_feedback_rows')[0]
        self.assertEqual(r['Pace of progress'],4);self.assertEqual(r['How invested'],3);self.assertEqual(r['Confidence in the quarterly goals'],5)
        self.assertEqual(self.query('drill','entrepreneurship_rating_rows')[0]['Rating'],4)
    def test_null_ratings_are_excluded_from_averages_without_inventing_scores(self):
        self.con.execute("UPDATE feedback SET composite=NULL,q1_rating=NULL WHERE kind='roadmap'")
        r=self.query('roadmaps','roadmap_feedback')[0];self.assertEqual(r['responses'],1)
        self.assertIsNone(r['avg_composite']);self.assertIsNone(r['avg_pace']);self.assertEqual(r['avg_invested'],3)

if __name__=='__main__':unittest.main()
