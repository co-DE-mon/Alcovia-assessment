-- Weekly metrics (DuckDB). Period = $start..$end inclusive; the caller keeps $end on or before the data's as-of day.
-- Definitions: student-tracker/README.md#kpi-catalogue (Weekly). Tags like [A54] point to README.md#assumption-reference-index.
-- Every query documents: definition, grain, source tables, edge cases. A zero denominator gives NULL, never 0.
-- Only students active on $end are counted unless a query says otherwise. Task completion, deadline adherence and time estimation
-- accuracy are in given.sql.

-- name: study_plan_set
-- Definition (Conducted, academic roadmap): active students with both weekday and weekend study hours set / active students [A54].
-- Grain: one row (cohort), measured at $end. Source: students.
-- Edge cases: NULL rate when there are no active students. A student who set only one of the two counts as not set.
SELECT count(*) AS active_students,
       count(*) FILTER (WHERE weekday_study_hours IS NOT NULL AND weekend_study_hours IS NOT NULL) AS plan_set,
       count(*) FILTER (WHERE weekday_study_hours IS NOT NULL AND weekend_study_hours IS NOT NULL)::DOUBLE / nullif(count(*), 0) AS plan_set_rate
FROM students
WHERE is_active(program_start_date, left_on, $end::DATE);

-- name: session_delivery
-- Definition (Conducted, Performed): for each session kind, sessions held / sessions scheduled (held + cancelled) and, for career, academic
--   and personal sessions, held / the monthly policy x active students x months in the period [A33]. Attended = students marked present /
--   students whose attendance is known.
-- Grain: one row per session kind present in the period. Source: events, event_attendance, students.
-- Edge cases: sessions still in the future are not counted as scheduled; cancelled sessions count against delivery. Months are fractional
--   (days / 30.4375) so a 30-day period is about one month. Kinds without a policy have a NULL policy_expected and delivered_vs_policy.
WITH s AS (
    SELECT event_id, kind, status FROM events
    WHERE kind IN ('academic_session', 'career_session', 'personal_session', 'mindset_session', 'deep_work_session')
      AND planned_for::DATE BETWEEN $start AND $end
),
att AS (
    SELECT s.kind, count(*) FILTER (WHERE a.attended) AS attended, count(*) FILTER (WHERE a.attended IS NOT NULL) AS attendance_known
    FROM s JOIN event_attendance a USING (event_id)
    WHERE s.status = 'held'
    GROUP BY s.kind
),
n AS (SELECT count(*) AS students FROM students WHERE is_active(program_start_date, left_on, $end::DATE)),
months AS (SELECT (date_diff('day', $start, $end) + 1) / 30.4375 AS m)
SELECT s.kind,
       count(*) FILTER (WHERE s.status IN ('held', 'cancelled')) AS scheduled,
       count(*) FILTER (WHERE s.status = 'held') AS held,
       count(*) FILTER (WHERE s.status = 'cancelled') AS cancelled,
       count(*) FILTER (WHERE s.status = 'held')::DOUBLE / nullif(count(*) FILTER (WHERE s.status IN ('held', 'cancelled')), 0) AS held_rate,
       CASE s.kind WHEN 'academic_session' THEN $sessions_policy_per_month_academic
                   WHEN 'career_session' THEN $sessions_policy_per_month_career
                   WHEN 'personal_session' THEN $sessions_policy_per_month_personal END * (SELECT students FROM n) * (SELECT m FROM months) AS policy_expected,
       count(*) FILTER (WHERE s.status = 'held')::DOUBLE / nullif(
           CASE s.kind WHEN 'academic_session' THEN $sessions_policy_per_month_academic
                       WHEN 'career_session' THEN $sessions_policy_per_month_career
                       WHEN 'personal_session' THEN $sessions_policy_per_month_personal END * (SELECT students FROM n) * (SELECT m FROM months), 0) AS delivered_vs_policy,
       max(att.attended) AS attended,
       max(att.attended)::DOUBLE / nullif(max(att.attendance_known), 0) AS attended_rate
FROM s LEFT JOIN att USING (kind)
GROUP BY s.kind
ORDER BY s.kind;

-- name: session_feedback
-- Definition (Liked): the average of the app's session feedback form (three star ratings, 1-5) for sessions held in the period, and the
--   share of attended sessions that got a response [A21]. Covers academic, career, personal, mindset, deep-work and peer sessions.
-- Grain: one row. Source: events, event_attendance, feedback.
-- Edge cases: only feedback tied to a held session in the period counts. NULL averages and response rate when there is no response or
--   no attended session; response_rate can exceed 1 only if a student rates twice, which the form does not allow.
WITH sess AS (
    SELECT event_id FROM events
    WHERE kind IN ('academic_session', 'career_session', 'personal_session', 'mindset_session', 'deep_work_session', 'peer_session')
      AND status = 'held' AND planned_for::DATE BETWEEN $start AND $end
),
attended AS (SELECT count(*) AS n FROM sess JOIN event_attendance a USING (event_id) WHERE a.attended),
fb AS (SELECT f.* FROM feedback f JOIN sess USING (event_id) WHERE f.kind = 'session')
SELECT (SELECT n FROM attended) AS attended_sessions,
       count(*) AS responses,
       count(*)::DOUBLE / nullif((SELECT n FROM attended), 0) AS response_rate,
       avg(composite) AS avg_composite, avg(q1_rating) AS avg_q1, avg(q2_rating) AS avg_q2, avg(q3_rating) AS avg_q3
FROM fb;

-- name: syllabus_pace_by_student
-- Definition: each student's latest syllabus completion % (chapters completed / total chapters) on or before $end, against the pace
--   target: 25% of the year's syllabus per quarter, so $syllabus_pace_pct by $end [A13]. On track when completion is at least
--   $syllabus_on_track_ratio of the pace [A55].
-- Grain: one row per active student with any syllabus history. Source: syllabus_daily, students.
-- Edge cases: days_stale shows how old the latest reading is (a student who stopped using the app freezes). A student with no history is
--   absent, not 0%. pace_ratio is NULL when the pace is 0.
WITH latest AS (
    SELECT d.*, row_number() OVER (PARTITION BY d.student_id ORDER BY d.day DESC) AS rn
    FROM syllabus_daily d WHERE d.day <= $end::DATE
)
SELECT l.student_id, l.day AS as_of, date_diff('day', l.day, $end::DATE) AS days_stale,
       l.chapters_completed, l.total_chapters,
       100.0 * l.chapters_completed / nullif(l.total_chapters, 0) AS completion_pct,
       $syllabus_pace_pct AS pace_pct,
       (100.0 * l.chapters_completed / nullif(l.total_chapters, 0)) / nullif($syllabus_pace_pct, 0) AS pace_ratio,
       (100.0 * l.chapters_completed / nullif(l.total_chapters, 0)) >= $syllabus_on_track_ratio * $syllabus_pace_pct AS on_track
FROM latest l JOIN students s USING (student_id)
WHERE l.rn = 1 AND is_active(s.program_start_date, s.left_on, $end::DATE)
ORDER BY l.student_id;

-- name: syllabus_pace
-- Definition (Performed): the share of active students on track against the syllabus pace (see syllabus_pace_by_student), and the
--   average completion %.
-- Grain: one row (cohort). Source: syllabus_daily, students.
-- Edge cases: NULL rate when no student has history.
WITH latest AS (
    SELECT d.*, row_number() OVER (PARTITION BY d.student_id ORDER BY d.day DESC) AS rn
    FROM syllabus_daily d WHERE d.day <= $end::DATE
),
cur AS (
    SELECT 100.0 * l.chapters_completed / nullif(l.total_chapters, 0) AS completion_pct
    FROM latest l JOIN students s USING (student_id)
    WHERE l.rn = 1 AND is_active(s.program_start_date, s.left_on, $end::DATE)
)
SELECT count(*) AS students, $syllabus_pace_pct AS pace_pct, avg(completion_pct) AS avg_completion_pct,
       count(*) FILTER (WHERE completion_pct >= $syllabus_on_track_ratio * $syllabus_pace_pct) AS on_track,
       count(*) FILTER (WHERE completion_pct >= $syllabus_on_track_ratio * $syllabus_pace_pct)::DOUBLE / nullif(count(*), 0) AS on_track_rate
FROM cur;

-- name: advisor_todos
-- Definition (Performed, advisor input): to-dos the advisor or the Alcovia team assigned (source admin_assigned) that fall due in the period,
--   and the share done on or before their due date.
-- Grain: one row (cohort). Source: todos, students.
-- Edge cases: updated_at stands in for the completion time [A3]. NULL rates when nothing was assigned or nothing was done.
WITH t AS (
    SELECT t.status, t.due_date, t.updated_at
    FROM todos t JOIN students s USING (student_id)
    WHERE t.source = 'admin_assigned' AND t.due_date BETWEEN $start AND $end AND is_active(s.program_start_date, s.left_on, $end::DATE)
)
SELECT count(*) AS assigned,
       count(*) FILTER (WHERE status = 'done') AS done,
       count(*) FILTER (WHERE status = 'done' AND updated_at::DATE <= due_date) AS done_on_time,
       count(*) FILTER (WHERE status = 'done')::DOUBLE / nullif(count(*), 0) AS done_rate,
       count(*) FILTER (WHERE status = 'done' AND updated_at::DATE <= due_date)::DOUBLE / nullif(count(*), 0) AS on_time_rate
FROM t;

-- name: student_input_cadence
-- Definition (Performed, advisor input): active students who created a to-do of their own (source manual) or marked one done in the last $weekly_input_window_days days
--   ending $end / active students. A proxy for "students fill in their inputs at the agreed cadence" [A54].
-- Grain: one row (cohort), measured at $end. Source: todos, students.
-- Edge cases: the window is $weekly_input_window_days days (config), not the period. To-dos assigned by advisors or the system do not count, because the student
--   did not create them. NULL rate when there are no active students. updated_at stands in for the completion time [A3].
WITH active AS (SELECT student_id FROM students WHERE is_active(program_start_date, left_on, $end::DATE)),
touched AS (
    SELECT DISTINCT student_id FROM todos
    WHERE (source = 'manual' AND created_at::DATE BETWEEN $end::DATE - ($weekly_input_window_days::INTEGER - 1) AND $end::DATE)
       OR (status = 'done' AND updated_at::DATE BETWEEN $end::DATE - ($weekly_input_window_days::INTEGER - 1) AND $end::DATE)
)
SELECT count(*) AS active_students,
       count(*) FILTER (WHERE t.student_id IS NOT NULL) AS filled_inputs,
       count(*) FILTER (WHERE t.student_id IS NOT NULL)::DOUBLE / nullif(count(*), 0) AS filled_rate
FROM active a LEFT JOIN touched t USING (student_id);

-- name: syllabus_progress
-- Definition (Performed, syllabus completion [A13][A64]): chapters completed / chapters expected by now, summed over the active students' latest syllabus readings.
--   Expected = each student's total chapters x the pace target ($syllabus_pace_pct, 25% of the year's syllabus per quarter). Above 1 means ahead of pace.
--   It complements syllabus_pace, which counts students as on track or not: this one shows how far behind or ahead the cohort is in chapters.
-- Grain: one row (cohort). Source: syllabus_daily, students.
-- Edge cases: a student with no syllabus history is left out of both sums. NULL rate when nothing is expected. The dashboard caps the value at 100%.
WITH latest AS (
    SELECT d.*, row_number() OVER (PARTITION BY d.student_id ORDER BY d.day DESC) AS rn FROM syllabus_daily d WHERE d.day <= $end::DATE
),
cur AS (
    SELECT l.chapters_completed, l.total_chapters FROM latest l JOIN students s USING (student_id)
    WHERE l.rn = 1 AND is_active(s.program_start_date, s.left_on, $end::DATE)
)
SELECT count(*) AS students, sum(chapters_completed) AS chapters_done, sum(total_chapters * $syllabus_pace_pct / 100.0) AS chapters_expected,
       sum(chapters_completed)::DOUBLE / nullif(sum(total_chapters * $syllabus_pace_pct / 100.0), 0) AS pace_ratio
FROM cur;
