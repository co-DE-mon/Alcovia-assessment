"""The seed fills every table, is deterministic, respects the schema rules, and carries the planted stories."""
from datetime import date, timedelta

import duckdb

from seed.generate import build
from snapshot import TABLES
from tests.conftest import AS_OF

END = "timestamp '2026-10-24 23:59:59'"


def test_every_table_has_rows(one):
    for t in TABLES:
        assert one(f"SELECT count(*) FROM {t}") > 0, t


def test_same_seed_same_data_different_seed_differs(tmp_path):
    def fingerprint(seed):
        path = build(tmp_path / f"s{seed}.duckdb", seed=seed)
        con = duckdb.connect(str(path), read_only=True)
        out = tuple(con.execute(f"SELECT count(*), sum(hash(t)) FROM {t} t").fetchone() for t in TABLES)
        con.close()
        return out
    assert fingerprint(42) == fingerprint(42)
    assert fingerprint(42) != fingerprint(7)


def test_every_id_is_demo(db):
    for table, col in [("staff", "staff_id"), ("students", "student_id"), ("events", "event_id"), ("todos", "todo_id"),
                       ("feedback", "feedback_id"), ("focus_sessions", "session_id"), ("roadmap_items", "item_id"),
                       ("ingest_log", "run_id")]:
        assert db.execute(f"SELECT count(*) FROM {table} WHERE {col} NOT LIKE 'DEMO-%'").fetchone()[0] == 0, table


def test_nothing_is_dated_after_as_of_except_planned_work(db):
    for sql in [f"SELECT count(*) FROM quiz_attempts WHERE started_at > {END}",
                f"SELECT count(*) FROM feedback WHERE submitted_at > {END}",
                f"SELECT count(*) FROM focus_sessions WHERE started_at > {END}",
                f"SELECT count(*) FROM todos WHERE updated_at > {END}",
                f"SELECT count(*) FROM roadmap_items WHERE done_at > {END}",
                "SELECT count(*) FROM wearable_daily WHERE day > date '2026-10-24'",
                "SELECT count(*) FROM study_hours WHERE as_of > date '2026-10-24'",
                "SELECT count(*) FROM events WHERE posted_on > date '2026-10-24'",
                f"SELECT count(*) FROM events WHERE planned_for > {END} AND status <> 'planned'",
                f"SELECT count(*) FROM events WHERE planned_for <= {END} AND status = 'planned'"]:
        assert db.execute(sql).fetchone()[0] == 0, sql


def test_attendance_is_unknown_until_the_event_is_held(db):
    assert db.execute("SELECT count(*) FROM event_attendance a JOIN events e USING (event_id) "
                      "WHERE e.status <> 'held' AND a.attended IS NOT NULL").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM event_attendance a JOIN events e USING (event_id) "
                      "WHERE e.status = 'held' AND a.attended IS NULL").fetchone()[0] == 0


def test_quiz_attempt_matches_attendance(db):
    assert db.execute("SELECT count(*) FROM quiz_attempts q LEFT JOIN event_attendance a USING (event_id, student_id) "
                      "WHERE a.attended IS NOT TRUE").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM event_attendance a JOIN events e USING (event_id) LEFT JOIN quiz_attempts q "
                      "USING (event_id, student_id) WHERE e.kind = 'quiz' AND a.attended AND q.started_at IS NULL").fetchone()[0] == 0


def test_students_are_enrolled_only_on_active_days(db):
    # the left student has no quiz row after leaving; the new joiner has none before starting
    assert db.execute("SELECT count(*) FROM event_attendance a JOIN events e USING (event_id) "
                      "WHERE e.kind = 'quiz' AND a.student_id = 'DEMO-S20' AND e.planned_for::DATE >= date '2026-09-30'").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM event_attendance a JOIN events e USING (event_id) "
                      "WHERE e.kind = 'quiz' AND a.student_id = 'DEMO-S19' AND e.planned_for::DATE < date '2026-10-05'").fetchone()[0] == 0


def test_missing_wearable_data_is_a_missing_row_or_null_never_zero(db):
    assert db.execute("SELECT count(*) FROM wearable_daily WHERE strain = 0 OR recovery_pct = 0 OR sleep_hours = 0").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM wearable_daily WHERE data_source = 'manual' AND (strain IS NOT NULL OR recovery_pct IS NOT NULL)").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM wearable_daily WHERE data_source = 'manual' AND sleep_hours IS NULL").fetchone()[0] == 0


def test_wearable_coverage_is_low(one):
    assert one("SELECT count(DISTINCT student_id) FROM wearable_daily") == 5   # one Whoop, one lapsed Whoop, three manual
    assert one("SELECT count(*) FROM students WHERE wearable = 'whoop'") == 2
    assert one("SELECT max(day) FROM wearable_daily WHERE student_id = 'DEMO-S02'") == AS_OF - timedelta(days=21)
    assert one("SELECT max(day) FROM wearable_daily WHERE student_id = 'DEMO-S01'") >= AS_OF - timedelta(days=2)


def test_seven_students_stopped_using_the_app_over_a_week_ago(one):
    last_use = """SELECT student_id, max(d) AS last FROM (
                    SELECT student_id, started_at::DATE AS d FROM focus_sessions
                    UNION ALL SELECT student_id, started_at::DATE FROM quiz_attempts) GROUP BY 1"""
    assert one(f"SELECT count(*) FROM ({last_use}) JOIN students USING (student_id) "
               "WHERE last < date '2026-10-17' AND left_on IS NULL") == 7   # the student who left is not counted


def test_one_student_left_and_one_joined_recently(one):
    assert one("SELECT left_on FROM students WHERE student_id = 'DEMO-S20'") == date(2026, 9, 30)
    assert one("SELECT program_start_date FROM students WHERE student_id = 'DEMO-S19'") == AS_OF - timedelta(days=19)
    assert one("SELECT count(*) FROM students WHERE program_start_date <= date '2026-10-24' AND (left_on IS NULL OR left_on > date '2026-10-24')") == 19


def test_advisor_three_lags_on_inputs(db):
    rows = dict(db.execute("SELECT s.advisor_id, avg(done::INT) FROM advisor_inputs i JOIN students s USING (student_id) "
                           "WHERE input_kind <> 'career_roadmap_reviewed' GROUP BY 1").fetchall())
    assert rows["DEMO-ADV-3"] + 0.2 < min(rows["DEMO-ADV-1"], rows["DEMO-ADV-2"])   # the current month drags every advisor down


def test_student_without_counsellor_has_no_career_sessions(one):
    assert one("SELECT career_counsellor_id IS NULL FROM students WHERE student_id = 'DEMO-S09'")
    assert one("SELECT count(*) FROM event_attendance a JOIN events e USING (event_id) WHERE a.student_id = 'DEMO-S09' AND e.kind = 'career_session'") == 0
    assert one("SELECT count(*) FROM event_attendance a JOIN events e USING (event_id) WHERE a.student_id = 'DEMO-S09' AND e.kind = 'academic_session'") > 0
    assert one("SELECT count(*) FROM advisor_inputs WHERE student_id = 'DEMO-S09' AND input_kind = 'career_roadmap_reviewed' AND done") == 0


def test_sessions_follow_the_policy(one, cfg):
    per = cfg["sessions"]["policy_per_month"]
    assert one("SELECT count(*) FROM events WHERE kind = 'academic_session' AND event_id LIKE 'DEMO-SS-DEMO-S01-%202608-%'") == per["academic"]
    assert one("SELECT count(*) FROM events WHERE kind = 'career_session' AND event_id LIKE 'DEMO-SS-DEMO-S01-%202608-%'") == per["career"]


def test_workshop_cancelled_and_poorly_rated(one):
    assert one("SELECT status FROM events WHERE event_id = 'DEMO-WS-202609-2'") == "cancelled"
    assert one("SELECT count(*) FROM events WHERE kind = 'workshop' AND status = 'held'") == 5
    worst = one("SELECT event_id FROM (SELECT event_id, avg(composite) c FROM feedback WHERE kind = 'workshop' AND event_id LIKE 'DEMO-WS-%' GROUP BY 1) ORDER BY c LIMIT 1")
    assert worst == "DEMO-WS-202608-1"


def test_one_pod_has_four_students_and_is_rated_worst(db):
    per_month = {}
    for month, group, n in db.execute("SELECT strftime(planned_for, '%Y-%m'), group_id, count(*) FROM events e JOIN event_attendance a USING (event_id) "
                                      "WHERE kind = 'pod' GROUP BY 1, 2").fetchall():
        per_month.setdefault(month, {})[group] = n
    assert len(per_month) == 3
    for sizes in per_month.values():       # every month: three pods of five and the short one, D
        assert sorted(sizes.values()) == [4, 5, 5, 5] and sizes["DEMO-POD-D"] == 4
    rating = db.execute("SELECT split_part(event_id, '-', 3), avg(composite) FROM feedback WHERE kind = 'pod' GROUP BY 1 ORDER BY 2").fetchall()
    assert rating[0][0] == "D"


def test_quiz_cancelled_three_days_and_mostly_started_in_window(one, cfg):
    assert one("SELECT count(*) FROM events WHERE kind = 'quiz' AND status = 'cancelled'") == 3
    w = cfg["quiz"]["entry_window_minutes"]
    inside = one(f"SELECT avg((q.started_at <= e.planned_for + INTERVAL {w} MINUTE)::INT) FROM quiz_attempts q JOIN events e USING (event_id)")
    assert 0.75 < inside < 0.95


def test_most_focus_sessions_fail_and_app_switch_is_a_common_reason(db):
    failed, total = db.execute("SELECT count(*) FILTER (WHERE status = 'failed'), count(*) FROM focus_sessions").fetchone()
    assert 0.35 < failed / total < 0.8
    assert db.execute("SELECT count(*) FROM focus_sessions WHERE status = 'failed' AND fail_reason IS NULL").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM focus_sessions WHERE status = 'completed' AND (fail_reason IS NOT NULL OR actual_minutes <> planned_minutes)").fetchone()[0] == 0
    top = db.execute("SELECT fail_reason FROM focus_sessions WHERE status = 'failed' GROUP BY 1 ORDER BY count(*) DESC LIMIT 1").fetchone()[0]
    assert top in ("app_switch", "give_up")


def test_ingest_log_has_the_planted_failures(db):
    got = {(r[0], r[1]) for r in db.execute("SELECT source, status FROM ingest_log WHERE status <> 'ok'").fetchall()}
    assert got == {("clickup", "failed"), ("whoop", "partial"), ("app_api", "failed")}
    assert db.execute("SELECT count(*) FROM ingest_log WHERE status = 'failed' AND error IS NULL").fetchone()[0] == 0


def test_social_work_groups_of_five_organised_by_alcovia(db):
    sizes = {r[1] for r in db.execute("SELECT group_id, count(DISTINCT student_id) FROM events e JOIN event_attendance a USING (event_id) WHERE kind = 'social_work' GROUP BY 1").fetchall()}
    assert sizes <= {4, 5}
    assert db.execute("SELECT count(*) FROM feedback WHERE kind = 'social_work' AND (q2_rating IS NOT NULL OR q3_rating IS NOT NULL)").fetchone()[0] == 0


def test_career_roadmap_missing_for_three_students(one):
    assert one("SELECT count(DISTINCT student_id) FROM roadmap_items WHERE roadmap = 'career'") == 16   # 19 active minus S09, S15, S17


def test_advisor_input_kinds_come_from_config(db, cfg):
    kinds = {r[0] for r in db.execute("SELECT DISTINCT input_kind FROM advisor_inputs").fetchall()}
    assert kinds == set(cfg["advisor_input_kinds"])


def test_time_estimation_has_a_null_case_when_actual_hours_are_zero(one):
    assert one("SELECT count(*) FROM study_hours WHERE actual_hours = 0 AND as_of = date '2026-10-24'") >= 1
    assert one("SELECT count(*) FROM study_hours WHERE estimated_hours <= 0") == 0


def test_ratings_are_in_range_and_composite_is_their_mean(db):
    assert db.execute("SELECT count(*) FROM feedback WHERE composite NOT BETWEEN 1 AND 5").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM feedback WHERE q1_rating IS NULL").fetchone()[0] == 0
    bad = db.execute("SELECT count(*) FROM feedback WHERE abs(composite - (coalesce(q1_rating,0)+coalesce(q2_rating,0)+coalesce(q3_rating,0)) / "
                     "nullif((q1_rating IS NOT NULL)::INT+(q2_rating IS NOT NULL)::INT+(q3_rating IS NOT NULL)::INT,0)) > 0.01").fetchone()[0]
    assert bad == 0


def test_study_hours_latest_snapshot_is_the_as_of_day_and_weekly(db):
    # regression: snapshots were once anchored to a weekday, so as_of itself was missing and the dashboard read week-old hours
    missing = db.execute("SELECT count(*) FROM students s WHERE left_on IS NULL AND NOT EXISTS "
                         "(SELECT 1 FROM study_hours h WHERE h.student_id = s.student_id AND h.as_of = date '2026-10-24')").fetchone()[0]
    assert missing == 0
    gaps = db.execute("SELECT count(*) FROM (SELECT as_of, lead(as_of) OVER (PARTITION BY student_id, subject ORDER BY as_of) AS nxt "
                      "FROM study_hours) WHERE nxt IS NOT NULL AND nxt - as_of <> 7").fetchone()[0]
    assert gaps == 0


def test_active_whoop_student_has_a_rough_last_week(db):
    rough, before = (db.execute(
        "SELECT count(*) FILTER (WHERE recovery_pct < 33)::DOUBLE / count(*), avg(recovery_pct) FROM wearable_daily "
        f"WHERE student_id = 'DEMO-S01' AND day {cond} date '2026-10-17'").fetchone() for cond in (">", "<="))
    assert rough[0] >= 0.4 and rough[0] > 2 * before[0]        # low-recovery days are common in the last week, rare before it
    assert rough[1] < before[1] - 15


def test_closed_months_show_a_spread_of_rigour_stages(db):
    got = {r[0]: r[1] for r in db.execute("SELECT planned_month, avg((stage_reached = 5)::INT) FROM chapter_progress GROUP BY 1").fetchall()}
    assert 0.25 < got[date(2026, 8, 1)] < 0.7
    assert 0.05 < got[date(2026, 9, 1)] < 0.4
    assert got[date(2026, 10, 1)] < 0.05    # the current month has barely started
    assert got[date(2026, 11, 1)] == 0      # next month is planned, nothing is done


def test_seed_follows_the_apis_academic_quarters(db):
    assert {r[0] for r in db.execute("SELECT DISTINCT quarter FROM study_hours").fetchall()} == {"2026-27-Q3"}
    assert dict(db.execute("SELECT planned_month, any_value(quarter) FROM chapter_progress GROUP BY 1").fetchall()) == {
        date(2026, 8, 1): "2026-27-Q2", date(2026, 9, 1): "2026-27-Q3", date(2026, 10, 1): "2026-27-Q3", date(2026, 11, 1): "2026-27-Q3"}
