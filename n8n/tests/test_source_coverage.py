"""Validate source coverage and independently check the shared-query exceptions.
Run: student-tracker/.venv/bin/python -B -m unittest discover -s n8n/tests -p test_source_coverage.py -v
"""
import importlib.util
from pathlib import Path
import sys
import re
import unittest
from datetime import date

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('source_coverage', ROOT / 'n8n/audit/source_coverage.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
sys.path.insert(0, str(ROOT / 'student-tracker'))
import duckdb
import metrics


class CoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = audit.collect()

    def test_all_kpis_have_reviewed_contracts_and_query_references(self):
        self.assertEqual(self.data['summary']['kpis'], 88)
        self.assertEqual(self.data['summary']['named_queries'], 95)
        for k in self.data['kpis']:
            self.assertIn(k['query'], self.data['queries'])
            self.assertTrue(k['capabilities'])
            for capability in k['capabilities']:
                self.assertIn(capability, self.data['capabilities'])
        self.assertEqual(self.data['summary']['query_missing_table_kpis'], 32)
        self.assertEqual(self.data['summary']['selected_input_missing_table_kpis'], 30)

    def test_populated_tables_do_not_imply_supported_fields_or_event_kinds(self):
        def find(name):
            return next(k for k in self.data['kpis'] if k['name'] == name)
        self.assertEqual(find('Calendar still connected (proxy)')['status'], 'missing')
        self.assertEqual(find('Peer sessions held vs expected')['status'], 'missing')
        self.assertIn('publishing', find('Shoots posted')['capabilities'])
        social = next(k for k in self.data['kpis'] if k['activity'] == 'Social work' and k['query'] == 'roadmaps.roadmap_status')
        self.assertEqual(social['capabilities'], ['social_goals'])

    def test_shared_query_exceptions_are_mapped_by_selected_output(self):
        nps = next(k for k in self.data['kpis'] if k['name'] == 'Workshop NPS (/ 10)')
        self.assertIn('feedback', nps['query_unloaded_tables'])
        self.assertNotIn('session_feedback', nps['capabilities'])
        held = next(k for k in self.data['kpis'] if k['name'] == 'Quizzes held / days')
        self.assertIn('quiz_attempts', held['query_unloaded_tables'])
        self.assertEqual(held['capabilities'], ['quiz_events'])

    def test_missing_evidence_or_unreviewed_query_fails_closed(self):
        with self.assertRaises(ValueError):
            audit.evidence('n8n/code/normalise.js', 'nonexistent evidence sentinel')
        import ast
        with self.assertRaises(ValueError):
            audit.query_capabilities('daily', 'new_unreviewed_kpi', ast.parse("field('value')", mode='eval').body)


class QueryExceptionsTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect(':memory:')
        self.con.execute((ROOT / 'student-tracker/sql/schema/student.sql').read_text())
        self.con.execute((ROOT / 'student-tracker/sql/schema/macros.sql').read_text())
        self.prm = metrics.params(metrics.load_config(), date(2026, 10, 1), date(2026, 10, 24))
        self.con.execute("INSERT INTO students (student_id,name,grade,advisor_id,program_start_date,wearable) VALUES ('DEMO-A','Demo',10,'DEMO-ADV','2026-01-01','none')")

    def tearDown(self):
        self.con.close()

    def test_every_named_query_executes_and_every_kpi_selects_real_columns(self):
        self.prm.update(student_id='DEMO-A', kind='workshop', roadmap='academic', input_kind='syllabus_review', exam_type='formative')
        data = audit.collect()
        columns = {}
        for file in sorted((ROOT / 'student-tracker/sql/metrics').glob('*.sql')):
            for name, sql in metrics.load(file.stem).items():
                with self.subTest(query=f'{file.stem}.{name}'):
                    needed = set(re.findall(r'\$(\w+)', re.sub(r'--[^\n]*', '', sql)))
                    cur = self.con.execute(sql, {k: self.prm[k] for k in needed})
                    columns[f'{file.stem}.{name}'] = {c[0] for c in cur.description}
                    cur.fetchall()
        self.assertEqual(len(columns), 95)
        for kpi in data['kpis']:
            with self.subTest(kpi=kpi['name']):
                self.assertTrue(set(kpi['output_fields']) <= columns[kpi['query']])

    def test_workshop_nps_survives_empty_feedback_and_attendance(self):
        self.con.execute("INSERT INTO events (event_id,kind,planned_for,status,source,nps_score) VALUES ('DEMO-W','workshop','2026-10-05 10:00:00','held','app_api',7.6)")
        rows = metrics.run(self.con, 'events', 'event_feedback', self.prm)
        self.assertAlmostEqual(rows[0]['avg_nps'], 7.6)
        self.assertIsNone(rows[0]['avg_composite'])

    def test_quiz_held_rate_survives_empty_attempts(self):
        self.con.execute("INSERT INTO events (event_id,kind,planned_for,status,source) VALUES ('DEMO-Q','quiz','2026-10-05 20:00:00','held','app_api')")
        row = metrics.run(self.con, 'daily', 'quiz_summary', self.prm)[0]
        self.assertAlmostEqual(row['held_rate'], 1 / 24)
        self.assertIsNone(row['completion_rate'])


if __name__ == '__main__':
    unittest.main()
