"""The scorecard and off-track list: status thresholds, roll-up, per-student reasons, data freshness, and the planted stories."""
from datetime import date

import pytest

import metrics
import scorecard as sc
from tests.conftest import AS_OF
from tests.test_metrics import CFG, add, make, student
from tests.test_metrics_cadences import event, todo


# ---------- statuses and roll-up ----------

@pytest.mark.parametrize("value,expected", [(1.0, "on_track"), (0.8, "on_track"), (0.7999, "watch"), (0.5, "watch"),
                                            (0.4999, "off_track"), (0.0, "off_track"), (None, "no_data")])
def test_status_boundaries_are_inclusive_at_the_thresholds(value, expected):
    assert sc.status(value, CFG) == expected


def test_status_follows_the_config_not_a_hardcoded_cut_off():
    cfg = {**CFG, "scorecard": {**CFG["scorecard"], "on_track_min": 0.9, "watch_min": 0.6}}
    assert (sc.status(0.85, CFG), sc.status(0.85, cfg), sc.status(0.55, cfg)) == ("on_track", "watch", "off_track")


def row(cadence, lens, value, activity="x"):
    return {"cadence": cadence, "activity": activity, "lens": lens, "kpi": "k", "value": value, "status": sc.status(value, CFG), "source": "s", "window": "period"}


def test_a_cell_takes_the_status_of_the_average_and_keeps_the_counts():
    grid = sc.cells([row("daily", "conducted", 1.0), row("daily", "conducted", 0.9), row("daily", "conducted", 0.1),   # average 0.67: watch
                     row("daily", "liked", None), row("daily", "performed", 0.2)], CFG)
    c = grid["daily"]["conducted"]
    assert c["status"] == "watch" and c["value"] == pytest.approx(2 / 3) and c["counts"] == {"on_track": 2, "watch": 0, "off_track": 1, "no_data": 0}
    assert grid["daily"]["liked"]["status"] == "no_data" and grid["daily"]["liked"]["with_data"] == 0 and grid["daily"]["liked"]["kpis"] == 1
    assert grid["daily"]["performed"]["status"] == "off_track"
    assert grid["weekly"]["conducted"] == {"status": "no_data", "value": None, "kpis": 0, "with_data": 0,
                                           "counts": {"on_track": 0, "watch": 0, "off_track": 0, "no_data": 0}}


def test_a_kpi_with_no_data_is_not_counted_as_a_failure():
    grid = sc.cells([row("daily", "conducted", 0.9), row("daily", "conducted", None)], CFG)
    assert grid["daily"]["conducted"]["status"] == "on_track" and grid["daily"]["conducted"]["counts"]["no_data"] == 1


def test_the_kpi_table_is_well_formed():
    names = [(k.cadence, k.activity, k.lens, k.name) for k in sc.KPIS]
    assert len(names) == len(set(names))
    assert {k.cadence for k in sc.KPIS} == set(sc.CADENCES) and {k.lens for k in sc.KPIS} == set(sc.LENSES)
    for cadence in sc.CADENCES:                     # every cadence has something under each lens
        for lens in sc.LENSES:
            assert any(k.cadence == cadence and k.lens == lens for k in sc.KPIS), (cadence, lens)
    for k in sc.KPIS:
        assert k.query in metrics.load(k.file), (k.file, k.query)


def test_ratings_are_scaled_to_a_share_and_overshoots_are_capped(db):
    rows = {r["kpi"]: r for r in sc.kpi_rows(db, CFG, AS_OF)}
    assert all(r["value"] is None or 0 <= r["value"] <= 1 for r in rows.values())
    raw = metrics.run(db, "weekly", "session_feedback", metrics.params(CFG, date(2026, 9, 25), AS_OF))[0]["avg_composite"]
    assert rows["Session feedback (average rating / 5)"]["value"] == pytest.approx(raw / 5)
    pol = metrics.run(db, "weekly", "session_delivery", metrics.params(CFG, date(2026, 9, 25), AS_OF))
    over = next(r for r in pol if r["kind"] == "academic_session")["delivered_vs_policy"]
    assert over > 1 and rows["Academic sessions held vs policy"]["value"] == 1.0


# ---------- per-student reasons ----------

def quiz_held(con, day):
    event(con, f"Q-{day}", "quiz", day)
    return f"Q-{day}"


def started(con, eid, sid, day):
    add(con, "quiz_attempts", event_id=eid, student_id=sid, started_at=f"{day} 20:05:00")


def focus(con, n, sid, day, status="completed", minutes=30):
    add(con, "focus_sessions", session_id=f"F{n}", student_id=sid, started_at=f"{day} 17:00:00", actual_minutes=minutes, status=status,
        fail_reason=None if status == "completed" else "give_up")


def activity(con, end="2026-10-24"):
    return {r["student_id"]: r for r in metrics.run(con, "students", "student_activity", metrics.params(CFG, date(2026, 9, 25), date.fromisoformat(end)))}


def test_student_activity_counts_only_quizzes_due_valid_focus_and_the_latest_of_three_signals():
    con = make()
    student(con, "a", start="2026-01-01")
    student(con, "new", start="2026-10-22")             # joined after most of the window's quizzes
    student(con, "gone", start="2026-01-01", left_on="2026-10-01")
    for day in ("2026-10-18", "2026-10-20", "2026-10-23"):
        e = quiz_held(con, day)
        started(con, e, "a", day) if day != "2026-10-20" else None
    event(con, "Q-old", "quiz", "2026-10-10")           # before the 7-day window
    focus(con, 1, "a", "2026-10-22", "completed", 25)
    focus(con, 2, "a", "2026-10-23", "failed", 40)      # failed minutes are not valid focus
    todo(con, 1, "a", "manual", "2026-10-26", "done", "2026-10-01 09:00:00", "2026-10-24 12:00:00")
    a = activity(con)
    assert set(a) == {"a", "new"}                       # the student who left is absent
    assert (a["a"]["quizzes_due"], a["a"]["quizzes_started"], a["a"]["focus_minutes"]) == (3, 2, 25)
    assert a["a"]["last_quiz"] == date(2026, 10, 23) and a["a"]["last_focus"] == date(2026, 10, 23)
    assert a["a"]["last_activity"] == date(2026, 10, 24) and a["a"]["days_since_activity"] == 0     # the to-do is the latest signal
    assert (a["new"]["quizzes_due"], a["new"]["focus_minutes"], a["new"]["last_activity"], a["new"]["days_since_activity"]) == (1, 0, None, None)
    assert a["new"]["days_enrolled"] == 2


def listed(con, cfg=CFG, end=date(2026, 10, 24)):
    return {r["student_id"]: r for r in sc.off_track(con, cfg, end)}


def test_a_student_is_listed_only_with_two_reasons_and_the_threshold_is_configurable():
    con = make()
    student(con, "two")        # no quiz and no focus
    student(con, "one")        # no quiz only: focus fine
    student(con, "fine")
    e = quiz_held(con, "2026-10-23")
    started(con, e, "fine", "2026-10-23")
    focus(con, 1, "one", "2026-10-23")
    focus(con, 2, "fine", "2026-10-23")
    got = listed(con)
    assert set(got) == {"two"} and got["two"]["reasons"] == ["no_quiz", "no_focus"]
    assert got["two"]["explanations"] == ["no quiz started in the last 7 days", "no valid focus minutes in the last 7 days"]
    loose = {**CFG, "scorecard": {**CFG["scorecard"], "off_track_min_reasons": 1}}
    assert set(listed(con, loose)) == {"two", "one"}
    strict = {**CFG, "scorecard": {**CFG["scorecard"], "off_track_min_reasons": 3}}
    assert listed(con, strict) == {}


def test_no_quiz_held_in_the_window_is_not_a_miss_and_a_new_student_is_labelled():
    con = make()
    student(con, "a")
    student(con, "new", start="2026-10-10")
    assert listed(con) == {} or all("no_quiz" not in r["reasons"] for r in listed(con).values())   # only no_focus applies, one reason
    todo_rows = [("a", "2026-10-10", "pending"), ("a", "2026-10-11", "missed"), ("new", "2026-10-12", "pending"), ("new", "2026-10-13", "missed")]
    for n, (sid, due, st) in enumerate(todo_rows):
        todo(con, n, sid, "manual", due, st, "2026-10-01 09:00:00", "2026-10-01 09:00:00")
    got = listed(con)
    assert got["a"]["reasons"] == ["no_focus", "tasks_slipping"] and got["a"]["new_student"] is False
    assert got["new"]["new_student"] is True and got["new"]["days_enrolled"] == 14


def test_syllabus_and_roadmap_reasons_use_the_existing_on_track_rules():
    con = make()
    student(con, "behind")
    student(con, "ahead")
    for sid, done in (("behind", 10), ("ahead", 80)):
        add(con, "syllabus_daily", student_id=sid, day="2026-10-24", chapters_completed=done, total_chapters=100)
    for n in range(3):
        add(con, "roadmap_items", item_id=f"R{n}", student_id="behind", roadmap="personal", level="monthly", title="t",
            created_at="2026-09-01 09:00:00", due_date="2026-10-10", done_at=None, source="clickup")
    focus(con, 1, "ahead", "2026-10-23")
    e = quiz_held(con, "2026-10-23")
    started(con, e, "ahead", "2026-10-23")
    got = listed(con)
    assert set(got) == {"behind"} and {"syllabus_behind", "roadmap_off_track"} <= set(got["behind"]["reasons"])


# ---------- data freshness ----------

def run_log(con, rid, source, started, status, error=None):
    add(con, "ingest_log", run_id=rid, source=source, started_at=started, finished_at=started, status=status, rows_upserted=5, error=error)


def fresh(con):
    return {r["source"]: r for r in sc.freshness(con, CFG, date(2026, 10, 24))}


def test_freshness_stale_rule_partial_runs_missing_sources_and_future_runs():
    con = make()
    run_log(con, "1", "app_api", "2026-10-24 02:00:00", "ok")
    run_log(con, "2", "clickup", "2026-10-22 02:00:00", "ok")                       # 69 hours before the as-of end: stale
    run_log(con, "3", "clickup", "2026-10-23 02:00:00", "failed", "rate limit")
    run_log(con, "4", "whoop", "2026-10-24 02:00:00", "partial", "2 students need to reconnect")
    run_log(con, "5", "app_api", "2026-10-25 02:00:00", "failed", "after the as-of day")   # ignored
    f = fresh(con)
    assert set(f) == {"app_api", "clickup", "whoop"}
    assert not f["app_api"]["stale"] and f["app_api"]["last_status"] == "ok" and f["app_api"]["failed_7d"] == 0 and f["app_api"]["last_error"] is None
    assert f["clickup"]["stale"] and f["clickup"]["hours_since_ok"] == 69 and f["clickup"]["last_status"] == "failed" and f["clickup"]["failed_7d"] == 1
    assert f["clickup"]["last_error"] == "rate limit"
    assert f["whoop"]["stale"] and f["whoop"]["last_ok_at"] is None and f["whoop"]["partial_7d"] == 1       # partial never resets the clock
    assert all(r["stale"] for r in fresh(make()).values())                          # a source that never ran is stale


def test_freshness_threshold_comes_from_config():
    con = make()
    for s in ("app_api", "clickup", "whoop"):
        run_log(con, s, s, "2026-10-23 20:00:00", "ok")         # 27 hours before the end of the as-of day
    base = metrics.params(CFG, date(2026, 10, 24), date(2026, 10, 24))
    stale = {h: metrics.run(con, "health", "source_freshness", {**base, "data_freshness_stale_after_hours": h})[0]["stale"] for h in (24, 36)}
    assert stale == {24: True, 36: False}


# ---------- the planted stories ----------

@pytest.fixture(scope="module")
def front(db):
    return sc.build(db, CFG, AS_OF)


def test_seed_off_track_list_is_the_dormant_students_first(front):
    ids = [r["student_id"] for r in front["off_track"]]
    dormant = [f"DEMO-S{n}" for n in range(11, 18)]
    assert set(dormant) <= set(ids)
    assert ids[:2] == ["DEMO-S17", "DEMO-S16"]                        # longest silent first, with the most reasons
    assert not {f"DEMO-S0{n}" for n in range(1, 8)} & set(ids)      # the engaged students are not listed
    assert "DEMO-S20" not in ids                                     # the student who left is not listed
    new = next(r for r in front["off_track"] if r["student_id"] == "DEMO-S19")
    assert new["new_student"] and new["days_enrolled"] == 19


def test_seed_pipeline_health_shows_only_whoop_stale(front):
    stale = {r["source"]: r["stale"] for r in front["freshness"]}
    assert stale == {"app_api": False, "clickup": False, "whoop": True}
    whoop = next(r for r in front["freshness"] if r["source"] == "whoop")
    assert whoop["last_status"] == "partial" and whoop["hours_since_ok"] > 36 and "reconnect" in whoop["last_error"]


def test_seed_scorecard_separates_a_structural_gap_from_real_weakness(front):
    by = {(r["activity"], r["kpi"]): r for r in front["kpis"]}
    assert by[("Active minutes", "Student-days with wearable strain")]["status"] == "off_track"        # 6% coverage
    assert by[("Entrepreneurship", "Theme milestones done by deadline")]["status"] == "watch"        # seeded for the demo (A61)
    statuses = {c: front["cells"][c] for c in sc.CADENCES}
    assert all(front["cells"][c][l]["with_data"] > 0 for c in sc.CADENCES for l in sc.LENSES)
    mixed = [cell for row in statuses.values() for cell in row.values() if cell["counts"]["on_track"] and cell["counts"]["off_track"]]
    assert mixed                                                        # at least one cell has both a healthy and a failing KPI


def test_seed_scorecard_is_stable_for_an_as_of_day(db):
    """Averages of floats can differ in the 16th digit between runs (DuckDB sums in parallel); everything else must be identical."""
    one, two = sc.kpi_rows(db, CFG, AS_OF), sc.kpi_rows(db, CFG, AS_OF)
    assert [(r["cadence"], r["activity"], r["lens"], r["kpi"], r["status"]) for r in one] == [(r["cadence"], r["activity"], r["lens"], r["kpi"], r["status"]) for r in two]
    assert [r["value"] for r in one] == pytest.approx([r["value"] for r in two], nan_ok=True)
    assert sc.off_track(db, CFG, AS_OF) == sc.off_track(db, CFG, AS_OF)


# ---------- student table, timeline and run history (the dashboard's data) ----------

def test_student_table_lists_flagged_students_first_and_includes_everyone(db):
    rows = sc.student_table(db, CFG, AS_OF)
    assert len(rows) == 19 and [r["student_id"] for r in rows if r["listed"]] == [r["student_id"] for r in sc.off_track(db, CFG, AS_OF)]
    assert [r["listed"] for r in rows] == sorted((r["listed"] for r in rows), reverse=True)        # flagged first
    by = {r["student_id"]: r for r in rows}
    assert not by["DEMO-S01"]["listed"] and by["DEMO-S01"]["syllabus_on_track"] and by["DEMO-S01"]["focus_minutes"] > 0
    assert by["DEMO-S17"]["last_activity"] is not None and by["DEMO-S17"]["days_since_activity"] == 47
    assert all(0 <= r["task_completion_rate"] <= 1 for r in rows if r["task_completion_rate"] is not None)
    assert by["DEMO-S09"]["reasons"] is not None and by["DEMO-S09"]["advisor_id"] == "DEMO-ADV-2"


def test_a_student_with_no_data_has_none_not_zero_in_the_table():
    con = make()
    student(con, "fresh", start="2026-10-23")
    row = sc.student_table(con, CFG, date(2026, 10, 24))[0]
    assert row["syllabus_pct"] is None and row["roadmap_pct"] is None and row["task_completion_rate"] is None and row["readiness_score"] is None
    assert row["last_activity"] is None and row["days_since_activity"] is None and row["new_student"]


def test_student_timeline_marks_held_quizzes_misses_and_inactive_days():
    con = make()
    student(con, "a", start="2026-10-21")
    student(con, "b", start="2026-01-01")
    for day in ("2026-10-21", "2026-10-22"):
        event(con, f"Q{day}", "quiz", day)
    event(con, "Qc", "quiz", "2026-10-23", status="cancelled")
    started(con, "Q2026-10-22", "a", "2026-10-22")
    started(con, "Q2026-10-21", "b", "2026-10-21")                 # someone else's attempt must not leak in
    focus(con, 1, "a", "2026-10-22", "completed", 25)
    focus(con, 2, "a", "2026-10-22", "completed", 30)
    focus(con, 3, "a", "2026-10-23", "failed", 40)
    todo(con, 1, "a", "manual", "2026-10-24", "done", "2026-10-20 09:00:00", "2026-10-24 10:00:00")
    rows = sc.student_timeline(con, CFG, date(2026, 10, 24), "a", days=5)
    assert [r["day"] for r in rows] == [date(2026, 10, d) for d in (21, 22, 23, 24)]              # 20 Oct is before they joined
    assert [(r["quiz_held"], r["quiz_started"]) for r in rows] == [(True, False), (True, True), (False, False), (False, False)]
    assert [r["focus_minutes"] for r in rows] == [0, 55, 0, 0] and [r["todos_done"] for r in rows] == [0, 0, 0, 1]
    assert sc.student_timeline(con, CFG, date(2026, 10, 24), "nobody") == []


def test_recent_runs_are_newest_first_within_fourteen_days_and_not_after_the_as_of_day():
    con = make()
    run_log(con, "old", "app_api", "2026-10-01 02:00:00", "ok")                  # more than 14 days back
    run_log(con, "a", "app_api", "2026-10-22 02:00:00", "ok")
    run_log(con, "b", "clickup", "2026-10-23 02:00:00", "failed", "rate limit")
    run_log(con, "future", "app_api", "2026-10-25 02:00:00", "ok")
    rows = sc.recent_runs(con, CFG, date(2026, 10, 24))
    assert [r["run_id"] for r in rows] == ["b", "a"] and rows[0]["error"] == "rate limit"


def test_every_as_of_day_in_the_history_builds_without_error(db):
    from datetime import timedelta
    for back in range(0, 61, 4):
        out = sc.build(db, CFG, AS_OF - timedelta(days=back))
        assert len(out["kpis"]) == len(sc.KPIS) and all(0 <= r["value"] <= 1 for r in out["kpis"] if r["value"] is not None)
        sc.student_table(db, CFG, AS_OF - timedelta(days=back))


def test_every_kpi_has_a_plain_explanation_and_a_count_recipe():
    import ui
    missing = [k.name for k in sc.KPIS if k.name not in ui.KPI_PLAIN or (k.activity, k.name) not in sc.DETAIL]
    assert not missing, missing


def test_the_run_log_note_and_the_list_of_students_agree_on_how_many_need_to_reconnect(tmp_path):
    """The seeded run-log note is built from the same students the dashboard lists, so the two cannot disagree."""
    import duckdb

    from seed.generate import build
    path = build(tmp_path / "s.duckdb")
    con = duckdb.connect(str(path), read_only=True)
    listed = sc.whoop_reconnect(con, CFG, AS_OF)
    note = con.execute("SELECT error FROM ingest_log WHERE source = 'whoop' AND status = 'partial' LIMIT 1").fetchone()[0]
    assert note.startswith(f"{len(listed)} student") and [r["ID"] for r in listed] == ["DEMO-S02"]


def test_every_activity_has_a_kpi_for_each_of_the_three_lenses():
    """The brief asks for KPIs for every activity through all three lenses, so a missing one is a gap to fix, not a blank to show."""
    seen = {}
    for k in sc.KPIS:
        seen.setdefault((k.cadence, k.activity), set()).add(k.lens)
    assert {key: sorted(set(sc.LENSES) - lenses) for key, lenses in seen.items() if lenses != set(sc.LENSES)} == {}


def test_whoop_students_syncing_and_students_to_reconnect_add_up_to_the_connected(tmp_path):
    """The Recovery liked KPI and the data-health list read the same students: syncing + needing to reconnect = connected."""
    import duckdb

    from seed.generate import build
    con = duckdb.connect(str(build(tmp_path / "s.duckdb")), read_only=True)
    prm = metrics.params(CFG, AS_OF, AS_OF)
    row = metrics.run(con, "daily", "whoop_syncing", prm)[0]
    assert row["connected_students"] == row["syncing"] + len(sc.whoop_reconnect(con, CFG, AS_OF)) and row["connected_students"] == 2
