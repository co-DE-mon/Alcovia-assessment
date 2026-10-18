"""Cross-check: recompute metrics in plain Python straight from the seed rows and compare with the SQL.
The Python below shares no SQL with the queries, so a logic error in one would show up as a disagreement."""
from collections import defaultdict
from datetime import date, timedelta

import pytest

import metrics
from tests.conftest import AS_OF
from tests.test_metrics import CFG

START = AS_OF - timedelta(days=29)
P = metrics.params(CFG, START, AS_OF)


def rows(db, sql):
    cur = db.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def sql(db, file, name, prm=P):
    return metrics.run(db, file, name, prm)


@pytest.fixture(scope="module")
def students(db):
    return {r["student_id"]: r for r in rows(db, "SELECT * FROM students")}


def active(s, day):
    return s["program_start_date"] <= day and (s["left_on"] is None or s["left_on"] > day)


def days(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def test_quiz_summary_matches_a_python_recount(db, students):
    ev = {r["event_id"]: r for r in rows(db, "SELECT * FROM events WHERE kind = 'quiz'")}
    att = {(r["event_id"], r["student_id"]): r for r in rows(db, "SELECT * FROM quiz_attempts")}
    held = [e for e in ev.values() if e["status"] == "held" and START <= e["planned_for"].date() <= AS_OF]
    due = started = in_window = completed = 0
    scores = []
    for e in held:
        for sid, s in students.items():
            if not active(s, e["planned_for"].date()):
                continue
            due += 1
            a = att.get((e["event_id"], sid))
            if a:
                started += 1
                in_window += a["started_at"] <= e["planned_for"] + timedelta(minutes=15)
                if a["completed_at"]:
                    completed += 1
                    scores.append(a["score"] / a["total_questions"])
    r = sql(db, "daily", "quiz_summary")[0]
    assert (r["quizzes_held"], r["student_quizzes_due"], r["started"], r["started_in_window"], r["completed"]) == (len(held), due, started, in_window, completed)
    assert r["avg_score_pct"] == pytest.approx(sum(scores) / len(scores))


def test_focus_summary_matches_a_python_recount(db, students):
    by = defaultdict(list)
    for f in rows(db, "SELECT * FROM focus_sessions"):
        by[(f["student_id"], f["started_at"].date())].append(f)
    sd = [(sid, d) for d in days(START, AS_OF) for sid, s in students.items() if active(s, d)]
    reach = sum(1 for k in sd if by.get(k))
    sessions = [f for k in sd for f in by.get(k, [])]
    done_min = sum(f["actual_minutes"] for f in sessions if f["status"] == "completed")
    meeting = sum(1 for k in sd if sum(f["actual_minutes"] for f in by.get(k, []) if f["status"] == "completed") >= 60)
    r = sql(db, "daily", "focus_summary")[0]
    assert (r["student_days"], r["student_days_with_session"], r["sessions"]) == (len(sd), reach, len(sessions))
    assert r["completed_minutes_per_student_day"] == pytest.approx(done_min / len(sd))
    assert r["share_meeting_target"] == pytest.approx(meeting / len(sd))
    assert r["give_up_rate"] == pytest.approx(sum(f["fail_reason"] == "give_up" for f in sessions) / len(sessions))


def test_task_metrics_match_a_python_recount(db, students):
    t = [x for x in rows(db, "SELECT * FROM todos") if START <= x["due_date"] <= AS_OF and active(students[x["student_id"]], AS_OF)]
    done = [x for x in t if x["status"] == "done"]
    on_time = [x for x in done if x["updated_at"].date() <= x["due_date"]]
    r = sql(db, "given", "task_metrics")[0]
    assert (r["todos_due"], r["todos_done"], r["done_on_time"]) == (len(t), len(done), len(on_time))
    assert r["task_completion_rate"] == pytest.approx(len(done) / len(t)) and r["deadline_adherence"] == pytest.approx(len(on_time) / len(done))


def test_wearable_summary_matches_a_python_recount(db, students):
    w = {(x["student_id"], x["day"]): x for x in rows(db, "SELECT * FROM wearable_daily")}
    sd = [(sid, d) for d in days(START, AS_OF) for sid, s in students.items() if active(s, d)]
    got = [w[k] for k in sd if k in w]
    strain = [x["strain"] for x in got if x["strain"] is not None]
    rec = [x["recovery_pct"] for x in got if x["recovery_pct"] is not None]
    sleep = [x["sleep_hours"] for x in got if x["sleep_hours"] is not None]
    r = sql(db, "daily", "wearable_summary")[0]
    assert (r["student_days"], r["strain_days"], r["recovery_days"], r["sleep_days"]) == (len(sd), len(strain), len(rec), len(sleep))
    assert r["strain_in_band_rate"] == pytest.approx(sum(8 <= x <= 16 for x in strain) / len(strain))
    assert r["avg_recovery_pct"] == pytest.approx(sum(rec) / len(rec)) and r["low_recovery_days"] == sum(x < 33 for x in rec)
    assert r["sleep_target_rate"] == pytest.approx(sum(x >= 8 for x in sleep) / len(sleep))


def test_syllabus_pace_matches_a_python_recount(db, students):
    latest = {}
    for x in sorted(rows(db, "SELECT * FROM syllabus_daily"), key=lambda r: r["day"]):
        if x["day"] <= AS_OF:
            latest[x["student_id"]] = x
    cur = {sid: 100 * x["chapters_completed"] / x["total_chapters"] for sid, x in latest.items() if active(students[sid], AS_OF)}
    pace = 25 * (2 + 54 / 91)                    # two quarters done, day 54 of 91 in the third
    got = {r["student_id"]: r for r in sql(db, "weekly", "syllabus_pace_by_student")}
    assert set(got) == set(cur)
    assert {sid for sid, r in got.items() if r["on_track"]} == {sid for sid, c in cur.items() if c >= 0.8 * pace}
    assert all(got[sid]["completion_pct"] == pytest.approx(c) for sid, c in cur.items())


def test_session_delivery_matches_a_python_recount(db):
    ev = [e for e in rows(db, "SELECT * FROM events") if e["kind"].endswith("_session") and e["kind"] != "peer_session" and START <= e["planned_for"].date() <= AS_OF]
    got = {r["kind"]: r for r in sql(db, "weekly", "session_delivery")}
    for kind in {e["kind"] for e in ev}:
        mine = [e for e in ev if e["kind"] == kind]
        assert got[kind]["held"] == sum(e["status"] == "held" for e in mine) and got[kind]["cancelled"] == sum(e["status"] == "cancelled" for e in mine)
    att = rows(db, "SELECT a.* FROM event_attendance a JOIN events e USING (event_id) WHERE e.kind = 'academic_session' AND e.status = 'held' "
                   "AND e.planned_for::DATE BETWEEN date '2026-09-25' AND date '2026-10-24'")
    assert got["academic_session"]["attended"] == sum(bool(a["attended"]) for a in att)


def test_event_feedback_and_nps_match_a_python_recount(db):
    ev = [e for e in rows(db, "SELECT * FROM events WHERE kind = 'workshop'") if e["status"] == "held" and date(2026, 8, 1) <= e["planned_for"].date() <= date(2026, 10, 24)]
    ids = {e["event_id"] for e in ev}
    fb = [f for f in rows(db, "SELECT * FROM feedback") if f["event_id"] in ids]
    attended = sum(bool(a["attended"]) for a in rows(db, "SELECT * FROM event_attendance") if a["event_id"] in ids)
    r = next(x for x in sql(db, "events", "event_feedback", metrics.params(CFG, date(2026, 8, 1), AS_OF)) if x["kind"] == "workshop")
    assert (r["attended"], r["responses"]) == (attended, len(fb))
    assert r["avg_composite"] == pytest.approx(sum(f["composite"] for f in fb) / len(fb))
    assert r["avg_nps"] == pytest.approx(sum(e["nps_score"] for e in ev) / len(ev))


def test_roadmap_on_track_and_advisor_inputs_match_a_python_recount(db, students):
    q3 = date(2026, 9, 1)
    by = defaultdict(list)
    for x in rows(db, "SELECT * FROM roadmap_items"):
        if q3 <= x["due_date"] <= AS_OF and active(students[x["student_id"]], AS_OF):
            by[x["student_id"]].append(x)
    pct = {sid: 100 * sum(1 for x in xs if x["done_at"] and x["done_at"].date() <= x["due_date"] and x["done_at"].date() <= AS_OF) / len(xs) for sid, xs in by.items()}
    got = {r["student_id"]: r for r in sql(db, "roadmaps", "roadmap_on_track_by_student", metrics.params(CFG, q3, AS_OF))}
    assert set(got) == set(pct) and all(got[s]["pct"] == pytest.approx(p) and got[s]["on_track"] == (p >= 80) for s, p in pct.items())


def test_time_estimation_matches_a_python_recount(db, students):
    latest = {}
    for x in sorted(rows(db, "SELECT * FROM study_hours WHERE quarter = '2026-27-Q3'"), key=lambda r: r["as_of"]):
        if x["as_of"] <= AS_OF and active(students[x["student_id"]], AS_OF):
            latest[(x["student_id"], x["subject"])] = x
    q_start, q_end = date(2026, 9, 1), date(2026, 11, 30)
    acc = {}
    for k, x in latest.items():
        expected = x["estimated_hours"] * min(1.0, max(0.0, ((x["as_of"] - q_start).days + 1) / ((q_end - q_start).days + 1)))
        acc[k] = None if x["actual_hours"] == 0 or expected == 0 else max(0.0, 1 - abs(x["actual_hours"] - expected) / expected)
    measured = [v for v in acc.values() if v is not None]
    assert sql(db, "given", "time_estimation")[0]["avg_accuracy"] == pytest.approx(sum(measured) / len(measured))


def test_every_query_runs_on_an_empty_database_and_on_a_one_day_period():
    from tests.test_metrics import make
    empty = make()
    for end_start in [(START, AS_OF), (AS_OF, AS_OF)]:
        prm = metrics.params(CFG, *end_start)
        for file in ("daily", "given", "weekly", "events", "quarterly", "roadmaps"):
            for name in metrics.load(file):
                metrics.run(empty, file, name, prm)       # must not raise; empty results or NULLs are fine


def test_every_query_runs_on_the_seed_for_a_one_day_period_and_a_quarter(db):
    for start, end in [(AS_OF, AS_OF), (date(2026, 9, 1), AS_OF)]:
        prm = metrics.params(CFG, start, end)
        for file in ("daily", "given", "weekly", "events", "quarterly", "roadmaps"):
            for name in metrics.load(file):
                metrics.run(db, file, name, prm)
