"""Atomic snapshot publishing and dashboard refresh regressions."""
from datetime import date
import duckdb
import pytest
import snapshot


def sample():
    tables={name:[] for name in snapshot.TABLES}
    tables['students']=[dict(student_id='DEMO-SNAPSHOT',name='Demo snapshot',grade=10,advisor_id='DEMO-ADV',program_start_date='2026-01-01',wearable='none')]
    return tables


def test_atomic_publish_rejects_orphans_and_preserves_previous_snapshot(tmp_path):
    path=tmp_path/'student.duckdb';tables=sample();snapshot.publish(tables,path,'2026-10-24');before=path.read_bytes()
    tables['wearable_daily']=[dict(student_id='DEMO-UNKNOWN',day='2026-10-01',data_source='manual',sleep_hours=8)]
    with pytest.raises(ValueError,match='roster'):snapshot.publish(tables,path,'2026-10-24')
    assert path.read_bytes()==before
    del tables['advisor_inputs']
    with pytest.raises(ValueError,match='every'):snapshot.publish(tables,path,'2026-10-24')


def test_database_constraints_reject_invalid_snapshot_without_replacing_old_file(tmp_path):
    path=tmp_path/'student.duckdb';tables=sample();snapshot.publish(tables,path,'2026-10-24');before=path.read_bytes()
    tables['students'][0]['grade']=99
    with pytest.raises(duckdb.ConstraintException):snapshot.publish(tables,path,'2026-10-24')
    assert path.read_bytes()==before


def test_dashboard_reads_snapshot_and_refreshes_after_atomic_replacement(tmp_path,monkeypatch):
    import data
    path=tmp_path/'student.duckdb';tables=sample();snapshot.publish(tables,path,'2026-10-24')
    monkeypatch.setenv('ALCOVIA_STUDENT_SNAPSHOT',str(path))
    data.refresh()
    try:
        assert data.bounds()[1]==date(2026,10,24)
        assert data.cursor().execute('SELECT name FROM students').fetchone()[0]=='Demo snapshot'
        tables['students'][0]['name']='Demo refreshed'
        snapshot.publish(tables,path,'2026-10-24');data.refresh()
        assert data.cursor().execute('SELECT name FROM students').fetchone()[0]=='Demo refreshed'
    finally:
        monkeypatch.delenv('ALCOVIA_STUDENT_SNAPSHOT');data.refresh()
