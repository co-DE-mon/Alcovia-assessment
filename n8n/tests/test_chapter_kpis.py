"""Check demo chapter rows against the four existing student-tracker KPIs."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from datetime import date
import yaml

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'student-tracker'))
import duckdb
import metrics


class ChapterKpis(unittest.TestCase):
    def test_mapped_rows_drive_all_four_chapter_metrics(self):
        pack=json.loads((ROOT/'n8n/tests/fixtures/demo/chapter-input.json').read_text())
        cfg=yaml.safe_load((ROOT/'student-tracker/config.yaml').read_text())
        js="const fs=require('fs'),x=JSON.parse(fs.readFileSync(0,'utf8')); const {mapChapters}=require('./n8n/code/chapters.js');console.log(JSON.stringify(mapChapters(x.pack,x.cfg,require('./n8n/code/normalise.js'))));"
        result=json.loads(subprocess.check_output(['node','-e',js],input=json.dumps({'pack':pack,'cfg':cfg}),text=True,cwd=ROOT))
        self.assertEqual(result['status'],'ok')
        with duckdb.connect(':memory:') as con:
            con.execute((ROOT/'student-tracker/sql/schema/student.sql').read_text())
            con.execute((ROOT/'student-tracker/sql/schema/macros.sql').read_text())
            con.execute("INSERT INTO students (student_id,name,grade,advisor_id,program_start_date,wearable) VALUES (?, 'Demo',10,'DEMO-ADV','2026-01-01','none')",[pack['studentId']])
            for row in result['rows']:
                con.execute('INSERT INTO chapter_progress ('+', '.join(row)+') VALUES ('+', '.join('?' for _ in row)+')',list(row.values()))
            prm=metrics.params(cfg,date(2026,10,1),date(2026,10,24))
            def value(query,field):return metrics.run(con,'given',query,prm)[0][field]
            self.assertEqual(value('chapter_readiness','readiness_score'),1)
            self.assertEqual(value('rigour_closed_months','closed_month_rate'),1)
            self.assertEqual(value('chapter_activity','working_rate'),1)
            self.assertIsNone(value('rigour_adherence','adherence'))
            con.execute("UPDATE chapter_progress SET planned_month='2026-10-01'")
            self.assertEqual(value('rigour_adherence','adherence'),1)
            con.execute("UPDATE chapter_progress SET stage_reached=2")
            self.assertEqual(value('chapter_readiness','readiness_score'),2/cfg['syllabus']['stages_total'])
            self.assertEqual(value('rigour_adherence','adherence'),0)
            con.execute("UPDATE chapter_progress SET updated_at='2026-08-01'")
            self.assertEqual(value('chapter_activity','working_rate'),0)


if __name__=='__main__':unittest.main()
