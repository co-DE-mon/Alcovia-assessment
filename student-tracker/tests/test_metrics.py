"""Metric queries. Hand-made rows pin each definition and its edge cases; the seeded data pins the planted stories."""
from datetime import date, timedelta

import duckdb
import pytest

import metrics
from tests.conftest import AS_OF, ROOT

CFG = metrics.load_config()


def make():
    con = duckdb.connect()
    con.execute((ROOT / "sql" / "schema" / "student.sql").read_text())
    con.execute((ROOT / "sql" / "schema" / "macros.sql").read_text())
    return con


def add(con, table, **row):
    con.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))


def student(con, sid, start="2026-01-01", **kw):
    row = dict(student_id=sid, name=sid, grade=10, advisor_id="A", program_start_date=start, wearable="none")
    add(con, "students", **{**row, **kw})


def q(con, file, name, start, end):
    return metrics.run(con, file, name, metrics.params(CFG, date.fromisoformat(start), date.fromisoformat(end)))


def one(con, file, name, start, end):
    rows = q(con, file, name, start, end)
    assert len(rows) == 1
    return rows[0]


def quiz(con, day, status="held"):
    add(con, "events", event_id=f"Q-{day}", kind="quiz", planned_for=f"{day} 20:00:00", status=status, source="app_api")
    return f"Q-{day}"


def attempt(con, event, sid, start, done=None, score=None):
    add(con, "quiz_attempts", event_id=event, student_id=sid, started_at=start, completed_at=done,
        score=score, total_questions=10 if score is not None else None)


# ---------- parameters and conventions ----------

def test_params_flatten_config_and_name_the_quarter():
    p = metrics.params(CFG, date(2026, 10, 1), date(2026, 10, 24))
    assert p["quiz_entry_window_minutes"] == 15 and p["wellness_strain_band_1"] == 16 and p["quiz_regular_taker_days_1"] == 7
    assert (p["quarter"], p["quarter_start"], p["quarter_end"]) == ("2026-27-Q3", date(2026, 9, 1), date(2026, 11, 30))
    assert metrics.quarter_for(date(2027, 1, 15), CFG)[2] == "2026-27-Q4" and metrics.quarter_for(date(2026, 3, 1), CFG)[2] == "2026-27-Q1"


def test_run_names_the_missing_parameter():
    with pytest.raises(KeyError, match="focus_daily_target_minutes"):
        metrics.run(make(), "daily", "focus_summary", {"start": date(2026, 10, 1), "end": date(2026, 10, 2)})


@pytest.mark.parametrize("file", ["daily", "given", "weekly", "events", "quarterly", "roadmaps"])
def test_every_query_documents_itself(file):
    for name, sql in metrics.load(file).items():
        for needle in ("-- Definition", "Grain:", "Source", "Edge cases:"):
            assert needle in sql, f"{file}.{name} is missing '{needle}'"


# ---------- quiz ----------

def quiz_world():
    con = make()
    for sid in ("a", "b"):
        student(con, sid)
    student(con, "gone", left_on="2026-10-01")          # left before the quiz: not due, not counted
    e = quiz(con, "2026-10-01")
    quiz(con, "2026-10-02", status="cancelled")
    attempt(con, e, "a", "2026-10-01 20:15:00", "2026-10-01 20:25:00", score=8)   # exactly on the window edge: inside
    attempt(con, e, "b", "2026-10-01 20:16:00")                                    # one minute late, never finished
    return con


def test_quiz_summary_counts_window_edge_completion_and_ignores_cancelled_and_left():
    r = one(quiz_world(), "daily", "quiz_summary", "2026-10-01", "2026-10-03")
    assert (r["days_in_period"], r["quizzes_held"]) == (3, 1)
    assert r["held_rate"] == pytest.approx(1 / 3)
    assert (r["student_quizzes_due"], r["started"], r["started_in_window"], r["completed"]) == (2, 2, 1, 1)
    assert r["in_window_rate"] == 0.5 and r["completion_rate"] == 0.5
    assert r["avg_score_pct"] == pytest.approx(0.8)


def test_quiz_summary_with_no_quiz_gives_null_rates_not_zero():
    con = make()
    student(con, "a")
    r = one(con, "daily", "quiz_summary", "2026-10-01", "2026-10-03")
    assert r["quizzes_held"] == 0 and r["held_rate"] == 0
    assert r["in_window_rate"] is None and r["completion_rate"] is None and r["avg_score_pct"] is None


def test_quiz_daily_marks_cancelled_and_missing_days_with_null_counts():
    rows = {r["day"]: r for r in q(quiz_world(), "daily", "quiz_daily", "2026-10-01", "2026-10-03")}
    assert rows[date(2026, 10, 1)]["held"] and rows[date(2026, 10, 1)]["started"] == 2
    assert rows[date(2026, 10, 1)]["active_students"] == 2
    for day in (date(2026, 10, 2), date(2026, 10, 3)):   # cancelled, and no quiz event at all
        assert not rows[day]["held"] and rows[day]["started"] is None and rows[day]["completed"] is None


def test_quiz_regular_takers_needs_four_of_the_last_seven_and_skips_new_students():
    con = make()
    end = date(2026, 10, 24)
    for sid in ("x", "y"):
        student(con, sid)
    student(con, "new", start=str(end - timedelta(days=3)))     # enrolled 3 days: not eligible yet [A42]
    for i in range(8):                                           # 8 held quizzes; only the latest 7 count
        e = quiz(con, str(end - timedelta(days=i)))
        who = {"x": i < 4 or i == 7, "y": i < 3, "new": True}   # x: 4 in the last 7 (plus 1 older one); y: only 3
        for sid, took in who.items():
            if took:
                attempt(con, e, sid, f"{end - timedelta(days=i)} 20:05:00")
    r = one(con, "daily", "quiz_regular_takers", "2026-10-01", str(end))
    assert (r["eligible_students"], r["regular_takers"]) == (2, 1) and r["regular_taker_rate"] == 0.5
    assert one(make(), "daily", "quiz_regular_takers", "2026-10-01", str(end))["regular_taker_rate"] is None


# ---------- focus ----------

def session(con, n, sid, day, status, minutes, reason=None):
    add(con, "focus_sessions", session_id=f"F{n}", student_id=sid, started_at=f"{day} 17:00:00",
        planned_minutes=60, actual_minutes=minutes, status=status, fail_reason=reason)


def test_focus_summary_counts_only_completed_minutes_and_separates_failure_reasons():
    con = make()
    student(con, "a")
    student(con, "b")
    student(con, "late", start="2026-10-02")                          # not active on day 1, so its day-1 session is ignored
    session(con, 1, "a", "2026-10-01", "completed", 60)
    session(con, 2, "a", "2026-10-01", "failed", 10, "give_up")
    session(con, 3, "b", "2026-10-01", "failed", 5, "app_switch")
    session(con, 4, "late", "2026-10-01", "completed", 90)
    r = one(con, "daily", "focus_summary", "2026-10-01", "2026-10-02")
    assert r["student_days"] == 5                                     # a, b on both days + late on day 2
    assert (r["student_days_with_session"], r["sessions"], r["completed_sessions"]) == (2, 3, 1)
    assert r["reach_rate"] == pytest.approx(2 / 5)
    assert r["give_up_rate"] == pytest.approx(1 / 3) and r["app_switch_rate"] == pytest.approx(1 / 3)
    assert r["completed_minutes_per_student_day"] == pytest.approx(60 / 5)
    assert r["failed_minutes_per_student_day"] == pytest.approx(15 / 5)
    assert r["target_minutes"] == 60 and r["share_meeting_target"] == pytest.approx(1 / 5)


def test_focus_summary_with_no_sessions_has_zero_reach_and_null_failure_rates():
    con = make()
    student(con, "a")
    r = one(con, "daily", "focus_summary", "2026-10-01", "2026-10-02")
    assert r["reach_rate"] == 0 and r["completed_minutes_per_student_day"] == 0   # a student-day without focus is a real zero
    assert r["give_up_rate"] is None and r["app_switch_rate"] is None


def test_focus_daily_has_one_row_per_day():
    con = make()
    student(con, "a")
    session(con, 1, "a", "2026-10-01", "completed", 25)
    rows = q(con, "daily", "focus_daily", "2026-10-01", "2026-10-03")
    assert [r["day"] for r in rows] == [date(2026, 10, d) for d in (1, 2, 3)]
    assert rows[0]["students_with_session"] == 1 and rows[0]["completed_minutes"] == 25 and rows[1]["students_with_session"] == 0


# ---------- timetable and connections ----------

def todo(con, n, sid, due, status, updated):
    add(con, "todos", todo_id=f"T{n}", student_id=sid, source="manual", title="t", due_date=due, status=status,
        created_at="2026-09-01 09:00:00", updated_at=updated)


def test_timetable_summary_counts_same_day_completion_only():
    con = make()
    student(con, "a")
    student(con, "b")
    todo(con, 1, "a", "2026-10-01", "done", "2026-10-01 18:00:00")      # same day
    todo(con, 2, "a", "2026-10-01", "done", "2026-10-02 09:00:00")      # done a day late
    todo(con, 3, "a", "2026-10-01", "pending", "2026-09-01 09:00:00")   # past due and not done
    todo(con, 4, "b", "2026-10-02", "done", "2026-10-02 11:00:00")
    r = one(con, "daily", "timetable_summary", "2026-10-01", "2026-10-02")
    assert (r["student_days"], r["student_days_with_todo"], r["todos_due"], r["done_same_day"]) == (4, 2, 4, 2)
    assert r["logged_rate"] == 0.5 and r["done_same_day_rate"] == 0.5


def test_timetable_summary_with_nothing_due_is_null():
    con = make()
    student(con, "a")
    r = one(con, "daily", "timetable_summary", "2026-10-01", "2026-10-02")
    assert r["logged_rate"] == 0 and r["done_same_day_rate"] is None


def test_connection_retention_needs_thirty_days_and_handles_never_connected():
    con = make()
    student(con, "keeps", calendar_connected_on="2026-08-01")
    student(con, "drops", calendar_connected_on="2026-08-01", calendar_disconnected_on="2026-08-20")   # gone before day 30
    student(con, "recent", calendar_connected_on="2026-10-10")                                          # not eligible yet
    student(con, "never")
    rows = {r["kind"]: r for r in q(con, "daily", "connection_retention", "2026-10-01", "2026-10-24")}
    cal = rows["calendar"]
    assert (cal["active_students"], cal["never_connected"], cal["eligible"], cal["retained"], cal["connected_now"]) == (4, 1, 2, 1, 2)
    assert cal["retention_rate"] == 0.5 and cal["after_days"] == 30
    assert rows["wearable"]["eligible"] == 0 and rows["wearable"]["retention_rate"] is None


# ---------- wearables ----------

def wear(con, sid, day, source, strain=None, recovery=None, sleep=None):
    add(con, "wearable_daily", student_id=sid, day=day, strain=strain, recovery_pct=recovery, sleep_hours=sleep, data_source=source)


def test_wearable_summary_keeps_missing_days_null_and_manual_rows_out_of_strain_and_recovery():
    con = make()
    student(con, "a", wearable="whoop")
    wear(con, "a", "2026-10-01", "whoop", 10, 80, 8)       # in band, good recovery, slept enough
    wear(con, "a", "2026-10-02", "whoop", 20, 20, 6)       # out of band, low recovery, short sleep
    wear(con, "a", "2026-10-03", "manual", sleep=7)        # manual: sleep only
    r = one(con, "daily", "wearable_summary", "2026-10-01", "2026-10-04")   # 2026-10-04 has no row at all
    assert (r["student_days"], r["strain_days"], r["recovery_days"], r["sleep_days"]) == (4, 2, 2, 3)
    assert r["strain_coverage"] == 0.5 and r["strain_in_band_rate"] == 0.5
    assert r["avg_recovery_pct"] == 50 and r["low_recovery_days"] == 1
    assert r["avg_sleep_hours"] == 7 and r["sleep_target_rate"] == pytest.approx(1 / 3)


def test_wearable_summary_without_data_is_null_not_zero():
    con = make()
    student(con, "a")
    r = one(con, "daily", "wearable_summary", "2026-10-01", "2026-10-04")
    assert r["strain_coverage"] == 0 and r["students_with_strain"] == 0       # coverage genuinely is zero
    assert r["strain_in_band_rate"] is None and r["avg_recovery_pct"] is None
    assert r["avg_sleep_hours"] is None and r["sleep_target_rate"] is None


# ---------- given metrics ----------

def test_task_metrics_completion_and_deadline_adherence():
    con = make()
    student(con, "a")
    student(con, "gone", left_on="2026-10-05")
    todo(con, 1, "a", "2026-10-02", "done", "2026-10-02 10:00:00")       # on time
    todo(con, 2, "a", "2026-10-03", "done", "2026-10-05 10:00:00")       # late
    todo(con, 3, "a", "2026-10-04", "pending", "2026-09-01 09:00:00")    # not done
    todo(con, 4, "a", "2026-10-20", "done", "2026-10-20 10:00:00")       # outside the period
    todo(con, 5, "gone", "2026-10-02", "done", "2026-10-02 10:00:00")    # student left: not in the cohort
    r = one(con, "given", "task_metrics", "2026-10-01", "2026-10-10")
    assert (r["students"], r["todos_due"], r["todos_done"], r["done_on_time"]) == (1, 3, 2, 1)
    assert r["task_completion_rate"] == pytest.approx(2 / 3) and r["deadline_adherence"] == 0.5
    by = q(con, "given", "task_metrics_by_student", "2026-10-01", "2026-10-10")
    assert [x["student_id"] for x in by] == ["a"] and by[0]["todos_due"] == 3


def test_task_metrics_with_no_todos_is_null():
    con = make()
    student(con, "a")
    r = one(con, "given", "task_metrics", "2026-10-01", "2026-10-10")
    assert r["todos_due"] == 0 and r["task_completion_rate"] is None and r["deadline_adherence"] is None
    assert q(con, "given", "task_metrics_by_student", "2026-10-01", "2026-10-10") == []


def hours(con, sid, subject, as_of, est, actual, quarter="2026-27-Q3"):
    add(con, "study_hours", student_id=sid, subject=subject, quarter=quarter, as_of=as_of, estimated_hours=est, actual_hours=actual)


def test_time_estimation_is_pace_based_uses_the_latest_snapshot_and_skips_zero_actual():
    con = make()
    student(con, "a")
    expected = 100 * 54 / 91                      # Q3 is 1 Sep..30 Nov, 91 days; 24 Oct is day 54
    hours(con, "a", "Maths", "2026-10-17", 100, 10)                       # older snapshot: ignored
    hours(con, "a", "Maths", "2026-10-24", 100, expected / 2)             # half the expected pace: accuracy 0.5
    hours(con, "a", "Hindi", "2026-10-24", 50, 0)                         # nothing logged: not measured
    hours(con, "a", "Maths", "2026-10-24", 100, 99, quarter="2026-27-Q2")    # another quarter: ignored
    c = one(con, "given", "time_estimation", "2026-10-01", "2026-10-24")
    assert (c["student_subjects"], c["measured"], c["not_measured"]) == (2, 1, 1) and c["avg_accuracy"] == pytest.approx(0.5)


def test_time_estimation_caps_accuracy_at_zero_for_a_huge_overrun_and_is_null_when_nothing_measured():
    con = make()
    student(con, "a")
    hours(con, "a", "Maths", "2026-10-24", 10, 500)
    assert one(con, "given", "time_estimation", "2026-10-01", "2026-10-24")["avg_accuracy"] == 0
    other = make()
    student(other, "a")
    hours(other, "a", "Maths", "2026-10-24", 10, 0)
    assert one(other, "given", "time_estimation", "2026-10-01", "2026-10-24")["avg_accuracy"] is None


def chapter(con, sid, n, month, stage):
    add(con, "chapter_progress", student_id=sid, chapter_id=f"C{n}", subject="Maths", quarter="2026-27-Q3",
        planned_month=month, stage_reached=stage, updated_at="2026-10-20 10:00:00")


def test_chapter_readiness_and_rigour_adherence():
    con = make()
    student(con, "a")
    for n, stage in enumerate((5, 3, 0)):
        chapter(con, "a", n, "2026-10-01", stage)           # this month's chapters
    chapter(con, "a", 9, "2026-09-01", 5)                    # last month: counts for readiness, not for this month's rigour
    chapter(con, "a", 10, "2026-11-01", 5)                   # planned for next month: counts for neither
    r = one(con, "given", "chapter_readiness", "2026-10-01", "2026-10-24")
    assert (r["students"], r["chapters"]) == (1, 4) and r["readiness_score"] == pytest.approx((5 + 3 + 0 + 5) / 4 / 5)
    g = one(con, "given", "rigour_adherence", "2026-10-01", "2026-10-24")
    assert (g["chapters_planned"], g["chapters_complete"]) == (3, 1) and g["adherence"] == pytest.approx(1 / 3)


def test_chapter_metrics_are_null_when_nothing_is_planned():
    con = make()
    student(con, "a")
    assert one(con, "given", "chapter_readiness", "2026-10-01", "2026-10-24")["readiness_score"] is None
    assert one(con, "given", "rigour_adherence", "2026-10-01", "2026-10-24")["adherence"] is None


# ---------- the planted stories show up in the metrics ----------

START = AS_OF - timedelta(days=29)


def seeded(db, file, name, start=START, end=AS_OF):
    return metrics.run(db, file, name, metrics.params(CFG, start, end))


def test_seed_quiz_one_cancelled_day_in_the_last_30(db):
    r = seeded(db, "daily", "quiz_summary")[0]
    assert (r["days_in_period"], r["quizzes_held"]) == (30, 29)
    assert 0.2 < r["in_window_rate"] < 0.6 and 0.85 < r["completion_rate"] <= 1
    assert seeded(db, "daily", "quiz_regular_takers")[0]["regular_taker_rate"] < 0.6


def test_seed_quiz_summary_agrees_with_the_daily_rows(db):
    rows = seeded(db, "daily", "quiz_daily")
    s = seeded(db, "daily", "quiz_summary")[0]
    assert s["student_quizzes_due"] == sum(r["active_students"] for r in rows if r["held"])
    assert s["started"] == sum(r["started"] for r in rows if r["held"])


def test_seed_focus_is_weak_and_failures_are_split(db):
    r = seeded(db, "daily", "focus_summary")[0]
    assert r["reach_rate"] < 0.5 and r["share_meeting_target"] < 0.25
    assert r["give_up_rate"] > 0 and r["app_switch_rate"] > 0 and r["give_up_rate"] + r["app_switch_rate"] < 1
    assert r["completed_minutes_per_student_day"] < r["target_minutes"]


def test_seed_wearable_coverage_is_low_and_one_student_has_low_recovery(db):
    r = seeded(db, "daily", "wearable_summary")[0]
    assert r["strain_coverage"] < 0.15 and r["students_with_strain"] == 2
    assert r["low_recovery_days"] >= 3 and r["avg_recovery_pct"] is not None


def test_seed_connection_retention_matches_the_planted_students(db):
    rows = {r["kind"]: r for r in seeded(db, "daily", "connection_retention")}
    cal, wear_ = rows["calendar"], rows["wearable"]
    assert cal["never_connected"] == 2 and cal["active_students"] == 19
    assert (wear_["eligible"], wear_["retained"], wear_["connected_now"]) == (2, 2, 1)   # S02's Whoop lapsed 21 days ago


def test_seed_task_metrics_cohort_matches_students_and_is_sensible(db):
    c = seeded(db, "given", "task_metrics")[0]
    by = seeded(db, "given", "task_metrics_by_student")
    assert c["students"] == len(by) == 19                    # the student who left is not counted
    assert sum(b["todos_due"] for b in by) == c["todos_due"]
    assert 0.3 < c["task_completion_rate"] < 0.9 and 0.5 < c["deadline_adherence"] <= 1


def test_seed_time_estimation_has_unmeasured_subjects(db):
    c = seeded(db, "given", "time_estimation")[0]
    assert c["not_measured"] >= 1 and c["students_measured"] >= 15 and 0 < c["avg_accuracy"] < 1


def test_seed_rigour_adherence_falls_for_later_months(db):
    def at(day):
        return seeded(db, "given", "rigour_adherence", day - timedelta(days=29), day)[0]["adherence"]
    aug, sep, oct_ = at(date(2026, 8, 31)), at(date(2026, 9, 30)), at(AS_OF)
    assert aug > sep > oct_ >= 0


def test_the_retention_window_comes_from_config_not_from_the_sql():
    con = make()
    student(con, "drops", calendar_connected_on="2026-09-01", calendar_disconnected_on="2026-09-20")   # lasted 19 days
    student(con, "keeps", calendar_connected_on="2026-09-01")
    base = metrics.params(CFG, date(2026, 10, 1), date(2026, 10, 24))
    by_days = {}
    for days in (10, 30):
        row = next(r for r in metrics.run(con, "daily", "connection_retention", {**base, "wellness_connected_after_days": days}) if r["kind"] == "calendar")
        by_days[days] = (row["after_days"], row["eligible"], row["retained"])
    assert by_days == {10: (10, 2, 2), 30: (30, 2, 1)}      # lasting 19 days passes a 10-day test and fails a 30-day one
