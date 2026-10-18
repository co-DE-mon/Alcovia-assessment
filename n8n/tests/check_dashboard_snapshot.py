"""Check real exported snapshots through every SQL query and the dashboard refresh control."""
import argparse
from datetime import date
import json,os,re,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'student-tracker'))
import duckdb,metrics,scorecard
from streamlit.testing.v1 import AppTest


def verify(before,after):
    con=duckdb.connect(str(before),read_only=True);cfg=metrics.load_config();end=con.execute('SELECT as_of FROM snapshot_meta').fetchone()[0]
    student=con.execute('SELECT student_id FROM students ORDER BY student_id').fetchone()[0]
    prm=metrics.params(cfg,end.replace(day=1),end);prm.update(student_id=student,kind='workshop',roadmap='academic',input_kind='syllabus_review',exam_type='unit_test')
    queries=0
    for file in sorted((ROOT/'student-tracker/sql/metrics').glob('*.sql')):
        for name in metrics.load(file.stem):metrics.run(con,file.stem,name,prm);queries+=1
    assert queries==95
    assert len(scorecard.build(con,cfg,end)['kpis'])==88
    con.close()
    with tempfile.TemporaryDirectory(prefix='alcovia-visible-refresh-') as tmp:
        served=Path(tmp)/'student.duckdb';shutil.copy2(before,served);os.environ['ALCOVIA_STUDENT_SNAPSHOT']=str(served)
        import data
        data.refresh()
        try:
            app=AppTest.from_file(str(ROOT/'student-tracker/app.py'),default_timeout=90).run()
            assert not app.exception,[e.value for e in app.exception]
            assert any(button.key=='refresh-data' for button in app.button)
            profile=AppTest.from_string('import data\nfrom views.students import records\nrecords(data.profile(data.bounds()[1],'+repr(student)+'))',default_timeout=90).run()
            def score():
                assert not profile.exception,[e.value for e in profile.exception]
                frames=[frame.value for frame in profile.dataframe if {'Score','Exam','Target'}.issubset(frame.value.columns)]
                assert frames
                return float(frames[0]['Score'].iloc[0])
            assert score()==85
            replacement=Path(tmp)/'next.duckdb';shutil.copy2(after,replacement);os.replace(replacement,served)
            profile.run();assert score()==85  # Explicit refresh is required; prove we exercised the cache.
            next(button for button in app.button if button.key=='refresh-data').click();app.run()
            assert not app.exception,[e.value for e in app.exception]
            profile.run();assert score()==90
        finally:
            os.environ.pop('ALCOVIA_STUDENT_SNAPSHOT',None);data.refresh()
    print(json.dumps(dict(queries=95,kpis=88,visibleBefore=85,visibleAfter=90,refreshVerified=True)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--before',type=Path,required=True);parser.add_argument('--after',type=Path,required=True);args=parser.parse_args();verify(args.before,args.after)
