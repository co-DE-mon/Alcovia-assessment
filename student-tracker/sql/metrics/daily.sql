-- Daily metrics (DuckDB). Period = $start..$end inclusive; the caller keeps $end on or before the data's as-of day.
-- Definitions: student-tracker/README.md#kpi-catalogue (Daily). Tags like [A4] point to README.md#assumption-reference-index.
-- Every query documents: definition, grain, source tables, edge cases. A zero denominator gives NULL, never 0.
-- "Student-day" = one active student on one day (is_active in schema/macros.sql). Counts always sit beside a rate.

-- name: quiz_daily
-- Definition: per day, whether the 8pm quiz was held and how many active students started it, started inside the entry window,
--   and finished it. Entry window = $quiz_entry_window_minutes after the planned time [A4].
-- Grain: one row per day. Source: events (kind quiz), quiz_attempts, students.
-- Edge cases: a day with no quiz event, or a cancelled one, has held = false and NULL counts (not 0): nothing could be started.
--   One quiz a day is assumed; a second quiz on the same day would duplicate that day's row.
WITH roster AS (
    SELECT d.day, count(s.student_id) AS active_students
    FROM period_days($start, $end) d
    LEFT JOIN students s ON is_active(s.program_start_date, s.left_on, d.day)
    GROUP BY d.day
),
quiz AS (
    SELECT planned_for::DATE AS day, event_id, planned_for, status = 'held' AS held FROM events WHERE kind = 'quiz'
),
tries AS (
    SELECT a.event_id,
           count(*) AS started,
           count(*) FILTER (WHERE a.started_at BETWEEN q.planned_for AND q.planned_for + to_minutes($quiz_entry_window_minutes::INTEGER)) AS started_in_window,
           count(a.completed_at) AS completed
    FROM quiz_attempts a JOIN quiz q USING (event_id)
    GROUP BY a.event_id
)
SELECT r.day,
       coalesce(q.held, false) AS held,
       r.active_students,
       CASE WHEN q.held THEN coalesce(t.started, 0) END AS started,
       CASE WHEN q.held THEN coalesce(t.started_in_window, 0) END AS started_in_window,
       CASE WHEN q.held THEN coalesce(t.completed, 0) END AS completed
FROM roster r
LEFT JOIN quiz q ON q.day = r.day
LEFT JOIN tries t ON t.event_id = q.event_id
ORDER BY r.day;

-- name: quiz_summary
-- Definition (Conducted): quizzes held / days in the period [A4].
--   (Performed): student-quizzes started inside the window / student-quizzes due (active students on held days).
--   (Liked, proxy): finished / started [A2]. avg_score_pct is secondary: the quiz aims at awareness, not marks [A32].
-- Grain: one row. Source: events, quiz_attempts, students.
-- Edge cases: cancelled days count in days_in_period but not in quizzes_held; completion_rate is NULL when nobody started;
--   avg_score_pct covers finished attempts only and is NULL when none finished.
WITH held AS (
    SELECT event_id, planned_for, planned_for::DATE AS day
    FROM events
    WHERE kind = 'quiz' AND status = 'held' AND planned_for::DATE BETWEEN $start AND $end
),
due AS (
    SELECT h.event_id, h.planned_for, s.student_id
    FROM held h JOIN students s ON is_active(s.program_start_date, s.left_on, h.day)
),
joined AS (
    SELECT d.planned_for, a.started_at, a.completed_at, a.score, a.total_questions
    FROM due d LEFT JOIN quiz_attempts a ON a.event_id = d.event_id AND a.student_id = d.student_id
),
agg AS (
    SELECT count(*) AS student_quizzes_due,
           count(started_at) AS started,
           count(*) FILTER (WHERE started_at BETWEEN planned_for AND planned_for + to_minutes($quiz_entry_window_minutes::INTEGER)) AS started_in_window,
           count(completed_at) AS completed,
           avg(score::DOUBLE / total_questions) FILTER (WHERE completed_at IS NOT NULL) AS avg_score_pct
    FROM joined
)
SELECT date_diff('day', $start, $end) + 1 AS days_in_period,
       (SELECT count(*) FROM held) AS quizzes_held,
       (SELECT count(*) FROM held)::DOUBLE / (date_diff('day', $start, $end) + 1) AS held_rate,
       student_quizzes_due, started, started_in_window,
       started_in_window::DOUBLE / nullif(student_quizzes_due, 0) AS in_window_rate,
       completed,
       completed::DOUBLE / nullif(started, 0) AS completion_rate,
       avg_score_pct
FROM agg;

-- name: quiz_regular_takers
-- Definition (Liked, proxy [A2][A32]): active students who took at least $quiz_regular_taker_days_0 of the last $quiz_regular_taker_days_1
--   held quizzes up to $end / active students.
-- Grain: one row, measured at $end. Source: events, quiz_attempts, students.
-- Edge cases: students enrolled for fewer than $quiz_regular_taker_days_1 days are left out of both counts, because they could not have
--   had the full window [A42]. NULL when no student qualifies.
WITH recent AS (
    SELECT event_id FROM events
    WHERE kind = 'quiz' AND status = 'held' AND planned_for::DATE <= $end
    QUALIFY row_number() OVER (ORDER BY planned_for DESC) <= $quiz_regular_taker_days_1
),
eligible AS (
    SELECT student_id FROM students
    WHERE is_active(program_start_date, left_on, $end::DATE)
      AND program_start_date <= $end::DATE - $quiz_regular_taker_days_1::INTEGER
),
took AS (
    SELECT a.student_id, count(*) AS n FROM quiz_attempts a JOIN recent USING (event_id) GROUP BY a.student_id
)
SELECT count(*) AS eligible_students,
       count(*) FILTER (WHERE coalesce(t.n, 0) >= $quiz_regular_taker_days_0) AS regular_takers,
       count(*) FILTER (WHERE coalesce(t.n, 0) >= $quiz_regular_taker_days_0)::DOUBLE / nullif(count(*), 0) AS regular_taker_rate
FROM eligible e LEFT JOIN took t USING (student_id);

-- name: focus_daily
-- Definition: per day, active students, students who started a session, sessions, and completed vs failed minutes.
-- Grain: one row per day. Source: focus_sessions, students.
-- Edge cases: minutes are the session's actual_minutes. A student-day with no session is a real zero (the student was active but did not focus).
--   Sessions by a student on a day they were not active are ignored.
WITH sd AS (
    SELECT d.day, s.student_id
    FROM period_days($start, $end) d JOIN students s ON is_active(s.program_start_date, s.left_on, d.day)
),
f AS (
    SELECT student_id, started_at::DATE AS day, count(*) AS sessions,
           coalesce(sum(actual_minutes) FILTER (WHERE status = 'completed'), 0) AS completed_minutes,
           coalesce(sum(actual_minutes) FILTER (WHERE status = 'failed'), 0) AS failed_minutes
    FROM focus_sessions GROUP BY 1, 2
)
SELECT sd.day, count(*) AS active_students, count(f.sessions) AS students_with_session,
       coalesce(sum(f.sessions), 0) AS sessions,
       coalesce(sum(f.completed_minutes), 0) AS completed_minutes,
       coalesce(sum(f.failed_minutes), 0) AS failed_minutes
FROM sd LEFT JOIN f USING (student_id, day)
GROUP BY sd.day
ORDER BY sd.day;

-- name: focus_summary
-- Definition (Conducted): student-days with at least one started session / student-days.
--   (Liked, proxy [A2][A5]): sessions ended by give-up / sessions, and app-switch failures / sessions, reported separately because the app
--   fails a session on any app switch.
--   (Performed): completed minutes per student-day against $focus_daily_target_minutes [A6], with failed minutes beside it [A37],
--   and the share of student-days at or above the target.
-- Grain: one row. Source: focus_sessions, students.
-- Edge cases: only completed sessions count as valid focus minutes. give_up_rate and app_switch_rate are NULL when there were no sessions.
WITH sd AS (
    SELECT d.day, s.student_id
    FROM period_days($start, $end) d JOIN students s ON is_active(s.program_start_date, s.left_on, d.day)
),
f AS (
    SELECT student_id, started_at::DATE AS day, count(*) AS sessions,
           count(*) FILTER (WHERE status = 'completed') AS completed,
           count(*) FILTER (WHERE fail_reason = 'give_up') AS give_up,
           count(*) FILTER (WHERE fail_reason = 'app_switch') AS app_switch,
           coalesce(sum(actual_minutes) FILTER (WHERE status = 'completed'), 0) AS completed_minutes,
           coalesce(sum(actual_minutes) FILTER (WHERE status = 'failed'), 0) AS failed_minutes
    FROM focus_sessions GROUP BY 1, 2
),
j AS (
    SELECT coalesce(f.sessions, 0) AS sessions, coalesce(f.completed, 0) AS completed,
           coalesce(f.give_up, 0) AS give_up, coalesce(f.app_switch, 0) AS app_switch,
           coalesce(f.completed_minutes, 0) AS completed_minutes, coalesce(f.failed_minutes, 0) AS failed_minutes
    FROM sd LEFT JOIN f USING (student_id, day)
)
SELECT count(*) AS student_days,
       count(*) FILTER (WHERE sessions > 0) AS student_days_with_session,
       count(*) FILTER (WHERE sessions > 0)::DOUBLE / nullif(count(*), 0) AS reach_rate,
       sum(sessions) AS sessions, sum(completed) AS completed_sessions,
       sum(give_up)::DOUBLE / nullif(sum(sessions), 0) AS give_up_rate,
       sum(app_switch)::DOUBLE / nullif(sum(sessions), 0) AS app_switch_rate,
       sum(completed_minutes)::DOUBLE / nullif(count(*), 0) AS completed_minutes_per_student_day,
       sum(failed_minutes)::DOUBLE / nullif(count(*), 0) AS failed_minutes_per_student_day,
       $focus_daily_target_minutes AS target_minutes,
       count(*) FILTER (WHERE completed_minutes >= $focus_daily_target_minutes)::DOUBLE / nullif(count(*), 0) AS share_meeting_target
FROM j;

-- name: timetable_summary
-- Definition (Conducted): student-days with at least one to-do due / student-days. The schema holds no calendar events, so a to-do
--   due that day stands in for a logged timetable [A1][A40].
--   (Performed): to-dos due in the period that were done on their due date / to-dos due [A3]. Done on the due date means updated_at,
--   which stands in for the completion time because the API has none.
-- Grain: one row. Source: todos, students.
-- Edge cases: to-dos belonging to a student on a day they were not active are ignored; a pending or in-progress to-do past its due date
--   counts as not done; done_same_day_rate is NULL when nothing was due.
WITH sd AS (
    SELECT d.day, s.student_id
    FROM period_days($start, $end) d JOIN students s ON is_active(s.program_start_date, s.left_on, d.day)
),
due AS (
    SELECT t.student_id, t.due_date AS day, count(*) AS due,
           count(*) FILTER (WHERE t.status = 'done' AND t.updated_at::DATE = t.due_date) AS done_same_day
    FROM todos t GROUP BY 1, 2
),
j AS (
    SELECT coalesce(due.due, 0) AS due, coalesce(due.done_same_day, 0) AS done_same_day
    FROM sd LEFT JOIN due USING (student_id, day)
)
SELECT count(*) AS student_days,
       count(*) FILTER (WHERE due > 0) AS student_days_with_todo,
       count(*) FILTER (WHERE due > 0)::DOUBLE / nullif(count(*), 0) AS logged_rate,
       sum(due) AS todos_due,
       sum(done_same_day) AS done_same_day,
       sum(done_same_day)::DOUBLE / nullif(sum(due), 0) AS done_same_day_rate
FROM j;

-- name: connection_retention
-- Definition (Liked, proxy [A2]): of students who connected a calendar (or wearable) at least $wellness_connected_after_days days before $end, the share
--   still connected that many days after connecting. connected_now is the share connected on $end. never_connected counts active students who never connected.
-- Grain: one row per kind (calendar, wearable). Source: students.
-- Edge cases: students connected less than $wellness_connected_after_days days before $end are not eligible yet. Reconnections are not modelled: the first
--   connect and last disconnect dates are all the table holds. Rates are NULL when no student is eligible.
WITH s AS (
    SELECT 'calendar' AS kind, calendar_connected_on AS connected_on, calendar_disconnected_on AS disconnected_on,
           is_active(program_start_date, left_on, $end::DATE) AS active
    FROM students
    UNION ALL
    SELECT 'wearable', wearable_connected_on, wearable_disconnected_on, is_active(program_start_date, left_on, $end::DATE)
    FROM students
)
SELECT kind, $wellness_connected_after_days AS after_days,
       count(*) FILTER (WHERE active) AS active_students,
       count(*) FILTER (WHERE active AND connected_on IS NULL) AS never_connected,
       count(*) FILTER (WHERE active AND connected_on + $wellness_connected_after_days::INTEGER <= $end::DATE) AS eligible,
       count(*) FILTER (WHERE active AND connected_on + $wellness_connected_after_days::INTEGER <= $end::DATE
                          AND (disconnected_on IS NULL OR disconnected_on > connected_on + $wellness_connected_after_days::INTEGER)) AS retained,
       count(*) FILTER (WHERE active AND connected_on + $wellness_connected_after_days::INTEGER <= $end::DATE
                          AND (disconnected_on IS NULL OR disconnected_on > connected_on + $wellness_connected_after_days::INTEGER))::DOUBLE
           / nullif(count(*) FILTER (WHERE active AND connected_on + $wellness_connected_after_days::INTEGER <= $end::DATE), 0) AS retention_rate,
       count(*) FILTER (WHERE active AND connected_on <= $end::DATE AND (disconnected_on IS NULL OR disconnected_on > $end::DATE)) AS connected_now
FROM s
GROUP BY kind
ORDER BY kind;

-- name: wearable_summary
-- Definition (Conducted, active minutes and recovery share one number [A7]): student-days with Whoop strain / student-days.
--   (Performed, active minutes): days with strain inside [$wellness_strain_band_0, $wellness_strain_band_1] / days with strain [A6].
--   (Performed, recovery): average recovery %, share of sleep-logged days at or above $wellness_sleep_target_hours, and days with recovery
--   below $wellness_low_recovery_pct [A6].
-- Grain: one row. Source: wearable_daily, students.
-- Edge cases: a student-day with no row has no data and is NULL for every measure, never 0 [A8]. Manual rows carry sleep hours only, so they
--   add to sleep_days but not to strain or recovery coverage. Every average and rate is NULL when it has no data to average.
WITH sd AS (
    SELECT d.day, s.student_id
    FROM period_days($start, $end) d JOIN students s ON is_active(s.program_start_date, s.left_on, d.day)
),
w AS (
    SELECT sd.student_id, w.strain, w.recovery_pct, w.sleep_hours
    FROM sd LEFT JOIN wearable_daily w ON w.student_id = sd.student_id AND w.day = sd.day
)
SELECT count(*) AS student_days,
       count(strain) AS strain_days,
       count(strain)::DOUBLE / nullif(count(*), 0) AS strain_coverage,
       count(DISTINCT student_id) FILTER (WHERE strain IS NOT NULL) AS students_with_strain,
       count(*) FILTER (WHERE strain BETWEEN $wellness_strain_band_0 AND $wellness_strain_band_1)::DOUBLE
           / nullif(count(strain), 0) AS strain_in_band_rate,
       count(recovery_pct) AS recovery_days,
       avg(recovery_pct) AS avg_recovery_pct,
       count(*) FILTER (WHERE recovery_pct < $wellness_low_recovery_pct) AS low_recovery_days,
       count(sleep_hours) AS sleep_days,
       avg(sleep_hours) AS avg_sleep_hours,
       count(*) FILTER (WHERE sleep_hours >= $wellness_sleep_target_hours)::DOUBLE / nullif(count(sleep_hours), 0) AS sleep_target_rate
FROM w;

-- name: whoop_syncing
-- Definition (Liked, proxy, Recovery [A2][A7]): of the active students who had connected a Whoop by $end, the share still syncing: not disconnected, and a
--   Whoop reading within the last $data_freshness_wearable_silent_days days. The complement is the list in health.sql whoop_reconnect, and a test keeps the two equal.
-- Grain: one row (cohort), measured at $end. Source: students, wearable_daily.
-- Edge cases: students with no Whoop are not in either count. Manual sleep rows are ignored, because they say nothing about the device. NULL rate when no student
--   has a Whoop.
WITH last AS (
    SELECT student_id, max(day) AS last_reading FROM wearable_daily WHERE data_source = 'whoop' AND day <= $end::DATE GROUP BY student_id
),
w AS (
    SELECT (s.wearable_disconnected_on IS NULL OR s.wearable_disconnected_on > $end::DATE)
           AND l.last_reading IS NOT NULL AND date_diff('day', l.last_reading, $end::DATE) <= $data_freshness_wearable_silent_days AS syncing
    FROM students s LEFT JOIN last l USING (student_id)
    WHERE s.wearable = 'whoop' AND s.wearable_connected_on <= $end::DATE AND is_active(s.program_start_date, s.left_on, $end::DATE)
)
SELECT count(*) AS connected_students, count(*) FILTER (WHERE syncing) AS syncing,
       count(*) FILTER (WHERE syncing)::DOUBLE / nullif(count(*), 0) AS sync_rate
FROM w;
