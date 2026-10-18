-- Drill-down queries (DuckDB): the rows behind a KPI's percentage, one query per family of KPIs. The dashboard opens one when a KPI is clicked.
-- Period = $start..$end inclusive, exactly as the KPI's own query (the KPI's window decides whether that is the period or the quarter).
-- Contract: every column is shown to the viewer, so aliases are plain words. drill.py names which numeric columns are the KPI's numerator and
--   denominator, and tests/test_drill.py checks that they add up to the KPI's headline number, so a definition cannot drift from its drill-down.
-- Grain is stated per query: per student where "which student" is the useful question, per event or item where "which one" is.
-- Parameters beyond the shared ones: $kind (event or connection kind), $roadmap, $exam_type. Student-days follow is_active in schema/macros.sql.

-- name: quiz_by_day
-- Grain: one row per day of the period. Source: events. Feeds: Quizzes held / days.
-- Edge cases: one quiz a day is assumed, as in daily.sql. A day with no quiz event shows "No quiz scheduled".
SELECT d.day AS "Day", q.title AS "Topic",
       CASE q.status WHEN 'held' THEN 'Held' WHEN 'cancelled' THEN 'Cancelled' WHEN 'planned' THEN 'Planned' ELSE 'No quiz scheduled' END AS "Status",
       coalesce(q.status = 'held', false)::INTEGER AS "Held"
FROM period_days($start, $end) d
LEFT JOIN (SELECT planned_for::DATE AS day, title, status FROM events WHERE kind = 'quiz') q ON q.day = d.day
ORDER BY d.day;

-- name: quiz_by_student
-- Grain: one row per student active on at least one held quiz day. Source: events, quiz_attempts, students.
-- Feeds: Quizzes finished / started, Started inside the entry window.
WITH held AS (
    SELECT event_id, planned_for, planned_for::DATE AS day
    FROM events WHERE kind = 'quiz' AND status = 'held' AND planned_for::DATE BETWEEN $start AND $end
),
due AS (
    SELECT s.student_id, s.name, h.event_id, h.planned_for
    FROM held h JOIN students s ON is_active(s.program_start_date, s.left_on, h.day)
),
j AS (
    SELECT d.student_id, d.name, d.planned_for, a.started_at, a.completed_at
    FROM due d LEFT JOIN quiz_attempts a ON a.event_id = d.event_id AND a.student_id = d.student_id
)
SELECT name AS "Student", student_id AS "ID",
       count(*) AS "Quizzes held",
       count(started_at) AS "Started",
       count(*) FILTER (WHERE started_at BETWEEN planned_for AND planned_for + to_minutes($quiz_entry_window_minutes::INTEGER)) AS "Started on time",
       count(completed_at) AS "Finished"
FROM j GROUP BY student_id, name ORDER BY name;

-- name: quiz_regular_takers_by_student
-- Grain: one row per student enrolled long enough to have the full window. Source: events, quiz_attempts, students. Feeds: Regular takers.
WITH recent AS (
    SELECT event_id FROM events
    WHERE kind = 'quiz' AND status = 'held' AND planned_for::DATE <= $end
    QUALIFY row_number() OVER (ORDER BY planned_for DESC) <= $quiz_regular_taker_days_1
),
eligible AS (
    SELECT student_id, name FROM students
    WHERE is_active(program_start_date, left_on, $end::DATE) AND program_start_date <= $end::DATE - $quiz_regular_taker_days_1::INTEGER
),
took AS (SELECT a.student_id, count(*) AS n FROM quiz_attempts a JOIN recent USING (event_id) GROUP BY a.student_id)
SELECT e.name AS "Student", e.student_id AS "ID", coalesce(t.n, 0) AS "Quizzes taken (of the last 7)",
       (coalesce(t.n, 0) >= $quiz_regular_taker_days_0)::INTEGER AS "Regular taker"
FROM eligible e LEFT JOIN took t USING (student_id) ORDER BY e.name;

-- name: focus_by_student
-- Grain: one row per student active in the period. Source: focus_sessions, students.
-- Feeds: Student-days with a session, Sessions not given up, Student-days at the focus target.
WITH sd AS (
    SELECT d.day, s.student_id, s.name FROM period_days($start, $end) d JOIN students s ON is_active(s.program_start_date, s.left_on, d.day)
),
f AS (
    SELECT student_id, started_at::DATE AS day, count(*) AS sessions,
           count(*) FILTER (WHERE fail_reason = 'give_up') AS give_up,
           coalesce(sum(actual_minutes) FILTER (WHERE status = 'completed'), 0) AS minutes
    FROM focus_sessions GROUP BY 1, 2
),
j AS (
    SELECT sd.student_id, sd.name, coalesce(f.sessions, 0) AS sessions, coalesce(f.give_up, 0) AS give_up, coalesce(f.minutes, 0) AS minutes
    FROM sd LEFT JOIN f USING (student_id, day)
)
SELECT name AS "Student", student_id AS "ID",
       count(*) AS "Active days",
       count(*) FILTER (WHERE sessions > 0) AS "Days with a session",
       sum(sessions)::INTEGER AS "Sessions",
       (sum(sessions) - sum(give_up))::INTEGER AS "Sessions not given up",
       count(*) FILTER (WHERE minutes >= $focus_daily_target_minutes) AS "Days at the focus target",
       round(sum(minutes))::INTEGER AS "Valid focus minutes"
FROM j GROUP BY student_id, name ORDER BY name;

-- name: timetable_by_student
-- Grain: one row per student active in the period. Source: todos, students.
-- Feeds: Student-days with a to-do due, To-dos done on their due date.
WITH sd AS (
    SELECT d.day, s.student_id, s.name FROM period_days($start, $end) d JOIN students s ON is_active(s.program_start_date, s.left_on, d.day)
),
due AS (
    SELECT student_id, due_date AS day, count(*) AS due,
           count(*) FILTER (WHERE status = 'done' AND updated_at::DATE = due_date) AS done_same_day
    FROM todos GROUP BY 1, 2
),
j AS (SELECT sd.student_id, sd.name, coalesce(due.due, 0) AS due, coalesce(due.done_same_day, 0) AS done_same_day FROM sd LEFT JOIN due USING (student_id, day))
SELECT name AS "Student", student_id AS "ID",
       count(*) AS "Active days",
       count(*) FILTER (WHERE due > 0) AS "Days with a to-do due",
       sum(due)::INTEGER AS "To-dos due",
       sum(done_same_day)::INTEGER AS "Done on the due date"
FROM j GROUP BY student_id, name ORDER BY name;

-- name: connection_by_student
-- Grain: one row per student active on $end, for the connection $kind (calendar or wearable). Source: students.
-- Feeds: Calendar / Wearable still connected. A student connected less than $wellness_connected_after_days days ago cannot be judged yet.
WITH s AS (
    SELECT 'calendar' AS kind, student_id, name, calendar_connected_on AS c, calendar_disconnected_on AS d,
           is_active(program_start_date, left_on, $end::DATE) AS active FROM students
    UNION ALL
    SELECT 'wearable', student_id, name, wearable_connected_on, wearable_disconnected_on, is_active(program_start_date, left_on, $end::DATE) FROM students
)
SELECT name AS "Student", student_id AS "ID", c AS "Connected on", d AS "Disconnected on",
       coalesce(c + $wellness_connected_after_days::INTEGER <= $end::DATE, false)::INTEGER AS "Connected long enough to judge",
       (coalesce(c + $wellness_connected_after_days::INTEGER <= $end::DATE, false)
        AND (d IS NULL OR d > c + $wellness_connected_after_days::INTEGER))::INTEGER AS "Still connected"
FROM s WHERE kind = $kind AND active ORDER BY name;

-- name: wearable_by_student
-- Grain: one row per student active in the period. Source: wearable_daily, students.
-- Feeds: Student-days with wearable strain, Strain inside the target band, Sleep at or above target.
WITH sd AS (
    SELECT d.day, s.student_id, s.name FROM period_days($start, $end) d JOIN students s ON is_active(s.program_start_date, s.left_on, d.day)
),
w AS (
    SELECT sd.student_id, sd.name, w.strain, w.recovery_pct, w.sleep_hours
    FROM sd LEFT JOIN wearable_daily w ON w.student_id = sd.student_id AND w.day = sd.day
)
SELECT name AS "Student", student_id AS "ID",
       count(*) AS "Active days",
       count(strain) AS "Days with strain data",
       count(recovery_pct) AS "Days with recovery data",
       count(*) FILTER (WHERE strain BETWEEN $wellness_strain_band_0 AND $wellness_strain_band_1) AS "Days inside the strain band",
       count(sleep_hours) AS "Nights with sleep data",
       count(*) FILTER (WHERE sleep_hours >= $wellness_sleep_target_hours) AS "Nights at the sleep target"
FROM w GROUP BY student_id, name ORDER BY name;

-- name: study_plan_by_student
-- Grain: one row per student active on $end. Source: students. Feeds: Study-hour plan set.
SELECT name AS "Student", student_id AS "ID", weekday_study_hours AS "Weekday study hours", weekend_study_hours AS "Weekend study hours",
       (weekday_study_hours IS NOT NULL AND weekend_study_hours IS NOT NULL)::INTEGER AS "Plan set"
FROM students WHERE is_active(program_start_date, left_on, $end::DATE) ORDER BY name;

-- name: syllabus_by_student
-- Grain: one row per active student with any syllabus history. Source: syllabus_daily, students. Feeds: Students on the syllabus pace.
WITH latest AS (
    SELECT d.*, row_number() OVER (PARTITION BY d.student_id ORDER BY d.day DESC) AS rn FROM syllabus_daily d WHERE d.day <= $end::DATE
)
SELECT s.name AS "Student", s.student_id AS "ID", l.day AS "Latest reading", l.chapters_completed AS "Chapters done", l.total_chapters AS "Chapters in total",
       l.total_chapters * $syllabus_pace_pct / 100.0 AS "Chapters expected by now",
       round(100.0 * l.chapters_completed / nullif(l.total_chapters, 0), 1) AS "Completed %", round($syllabus_pace_pct, 1) AS "Pace target %",
       ((100.0 * l.chapters_completed / nullif(l.total_chapters, 0)) >= $syllabus_on_track_ratio * $syllabus_pace_pct)::INTEGER AS "On pace"
FROM latest l JOIN students s USING (student_id)
WHERE l.rn = 1 AND is_active(s.program_start_date, s.left_on, $end::DATE) ORDER BY s.name;

-- name: todos_by_student
-- Grain: one row per active student with a to-do due in the period. Source: todos, students. Feeds: Task completion rate, Deadline adherence.
SELECT s.name AS "Student", s.student_id AS "ID",
       count(*) AS "To-dos due",
       count(*) FILTER (WHERE t.status = 'done') AS "Done",
       count(*) FILTER (WHERE t.status = 'done' AND t.updated_at::DATE <= t.due_date) AS "Done on time"
FROM todos t JOIN students s USING (student_id)
WHERE t.due_date BETWEEN $start AND $end AND is_active(s.program_start_date, s.left_on, $end::DATE)
GROUP BY s.student_id, s.name ORDER BY s.name;

-- name: time_estimation_rows
-- Grain: one row per student and subject, latest snapshot in the quarter. Source: study_hours, students. Feeds: Time estimation accuracy.
-- Edge cases: Accuracy is empty when no hours were logged yet: not measured, and left out of the average.
WITH latest AS (
    SELECT h.*, row_number() OVER (PARTITION BY h.student_id, h.subject ORDER BY h.as_of DESC) AS rn
    FROM study_hours h JOIN students s USING (student_id)
    WHERE h.quarter = $quarter AND h.as_of <= $end AND is_active(s.program_start_date, s.left_on, $end::DATE)
),
x AS (
    SELECT student_id, subject, estimated_hours, actual_hours,
           estimated_hours * least(1.0, greatest(0.0, (date_diff('day', $quarter_start, as_of) + 1)::DOUBLE
                                                      / (date_diff('day', $quarter_start, $quarter_end) + 1))) AS expected_hours
    FROM latest WHERE rn = 1
)
SELECT s.name AS "Student", s.student_id AS "ID", x.subject AS "Subject", round(x.estimated_hours, 1) AS "Hours planned for the quarter",
       round(x.expected_hours, 1) AS "Hours expected by now", round(x.actual_hours, 1) AS "Hours actually studied",
       CASE WHEN x.actual_hours = 0 OR x.expected_hours = 0 THEN NULL
            ELSE greatest(0.0, 1 - abs(x.actual_hours - x.expected_hours) / x.expected_hours) END AS "Accuracy"
FROM x JOIN students s USING (student_id) ORDER BY s.name, x.subject;

-- name: readiness_by_student
-- Grain: one row per active student with chapters planned up to this month. Source: chapter_progress, students. Feeds: Chapter readiness score.
-- A chapter's stage is 0-5 (read, notes, practice, timed paper, exam accuracy); readiness = stage points reached / stage points possible.
SELECT s.name AS "Student", s.student_id AS "ID", count(*) AS "Chapters planned",
       round(avg(c.stage_reached), 2) AS "Average stage (of 5)",
       sum(c.stage_reached)::INTEGER AS "Stage points reached",
       (count(*) * $syllabus_stages_total)::INTEGER AS "Stage points possible"
FROM chapter_progress c JOIN students s USING (student_id)
WHERE c.planned_month <= date_trunc('month', $end::DATE) AND is_active(s.program_start_date, s.left_on, $end::DATE)
GROUP BY s.student_id, s.name ORDER BY s.name;

-- name: rigour_by_student
-- Grain: one row per active student with chapters planned this month. Source: chapter_progress, students. Feeds: Monthly rigour adherence.
SELECT s.name AS "Student", s.student_id AS "ID", count(*) AS "Chapters planned this month",
       count(*) FILTER (WHERE c.stage_reached = $syllabus_stages_total) AS "Reached the last stage"
FROM chapter_progress c JOIN students s USING (student_id)
WHERE c.planned_month = date_trunc('month', $end::DATE) AND is_active(s.program_start_date, s.left_on, $end::DATE)
GROUP BY s.student_id, s.name ORDER BY s.name;

-- name: advisor_todos_rows
-- Grain: one row per advisor-assigned to-do due in the period. Source: todos, students. Feeds: Advisor-assigned to-dos done (on time).
SELECT s.name AS "Student", s.student_id AS "ID", t.title AS "To-do", t.due_date AS "Due", t.status AS "Status", t.updated_at::DATE AS "Last updated",
       (t.status = 'done')::INTEGER AS "Done",
       (t.status = 'done' AND t.updated_at::DATE <= t.due_date)::INTEGER AS "Done on time"
FROM todos t JOIN students s USING (student_id)
WHERE t.source = 'admin_assigned' AND t.due_date BETWEEN $start AND $end AND is_active(s.program_start_date, s.left_on, $end::DATE)
ORDER BY s.name, t.due_date;

-- name: input_cadence_by_student
-- Grain: one row per student active on $end. Source: todos, students. Feeds: Students filling in their inputs.
-- A student counts when they made a to-do of their own or finished one inside the last $weekly_input_window_days days.
SELECT s.name AS "Student", s.student_id AS "ID",
       count(t.todo_id) FILTER (WHERE t.source = 'manual' AND t.created_at::DATE BETWEEN $end::DATE - ($weekly_input_window_days::INTEGER - 1) AND $end::DATE) AS "Own to-dos created",
       count(t.todo_id) FILTER (WHERE t.status = 'done' AND t.updated_at::DATE BETWEEN $end::DATE - ($weekly_input_window_days::INTEGER - 1) AND $end::DATE) AS "To-dos finished",
       (count(t.todo_id) FILTER (WHERE (t.source = 'manual' AND t.created_at::DATE BETWEEN $end::DATE - ($weekly_input_window_days::INTEGER - 1) AND $end::DATE)
                                   OR (t.status = 'done' AND t.updated_at::DATE BETWEEN $end::DATE - ($weekly_input_window_days::INTEGER - 1) AND $end::DATE)) > 0)::INTEGER AS "Filled in inputs"
FROM students s LEFT JOIN todos t USING (student_id)
WHERE is_active(s.program_start_date, s.left_on, $end::DATE) GROUP BY s.student_id, s.name ORDER BY s.name;

-- name: events_list
-- Grain: one row per event of $kind in the period. Source: events. Feeds: every "held" KPI (held / scheduled, and held vs expected).
-- Edge cases: an event still planned is shown but is neither scheduled nor held, as in events.sql.
SELECT planned_for::DATE AS "Date", title AS "Title", group_id AS "Group",
       CASE status WHEN 'held' THEN 'Held' WHEN 'cancelled' THEN 'Cancelled' ELSE 'Planned' END AS "Status",
       (status IN ('held', 'cancelled'))::INTEGER AS "Scheduled", (status = 'held')::INTEGER AS "Held"
FROM events WHERE kind = $kind AND planned_for::DATE BETWEEN $start AND $end ORDER BY planned_for;

-- name: attendance_rows
-- Grain: one row per student invited to a held event of $kind in the period. Source: events, event_attendance, students.
-- Feeds: every attendance KPI. Invitees are not filtered by active status: an invitation records who the event was for.
SELECT e.planned_for::DATE AS "Date", e.title AS "Event", coalesce(s.name, a.student_id) AS "Student", a.student_id AS "ID",
       a.invited::INTEGER AS "Invited", (a.attended IS NOT NULL)::INTEGER AS "Attendance recorded", coalesce(a.attended, false)::INTEGER AS "Attended"
FROM events e JOIN event_attendance a USING (event_id) LEFT JOIN students s ON s.student_id = a.student_id
WHERE e.status = 'held' AND e.kind = $kind AND e.planned_for::DATE BETWEEN $start AND $end
ORDER BY e.planned_for, s.name;

-- name: session_feedback_rows
-- Grain: one row per session feedback form for a held session in the period. Source: feedback, events, students. Feeds: Session feedback.
SELECT e.planned_for::DATE AS "Date", e.kind AS "Session type", coalesce(s.name, f.student_id) AS "Student", f.student_id AS "ID",
       f.q1_rating AS "Rating 1", f.q2_rating AS "Rating 2", f.q3_rating AS "Rating 3", round(f.composite, 2) AS "Average rating"
FROM feedback f JOIN events e USING (event_id) LEFT JOIN students s ON s.student_id = f.student_id
WHERE f.kind = 'session' AND e.status = 'held' AND e.planned_for::DATE BETWEEN $start AND $end
  AND e.kind IN ('academic_session', 'career_session', 'personal_session', 'mindset_session', 'deep_work_session', 'peer_session')
ORDER BY e.planned_for, s.name;

-- name: event_feedback_rows
-- Grain: one row per feedback form for a held event of $kind in the period. Source: feedback, events, students. Feeds: every "rating (average / 5)" KPI.
SELECT e.planned_for::DATE AS "Date", e.title AS "Event", coalesce(s.name, f.student_id) AS "Student", f.student_id AS "ID",
       f.q1_rating AS "Rating 1", f.q2_rating AS "Rating 2", f.q3_rating AS "Rating 3", round(f.composite, 2) AS "Average rating"
FROM feedback f JOIN events e USING (event_id) LEFT JOIN students s ON s.student_id = f.student_id
WHERE e.status = 'held' AND e.kind = $kind AND e.planned_for::DATE BETWEEN $start AND $end
ORDER BY e.planned_for, s.name;

-- name: event_nps_rows
-- Grain: one row per held event of $kind with an NPS score. Source: events. Feeds: Workshop NPS. The KPI averages events, not responses.
SELECT planned_for::DATE AS "Date", title AS "Event", nps_score AS "NPS (out of 10)"
FROM events WHERE status = 'held' AND kind = $kind AND nps_score IS NOT NULL AND planned_for::DATE BETWEEN $start AND $end ORDER BY planned_for;

-- name: posted_rows
-- Grain: one row per held event of $kind (branding shoot or podcast) in the period. Source: events. Feeds: Shoots posted, Episodes posted.
SELECT planned_for::DATE AS "Date", title AS "Title", posted_on AS "Posted on",
       CASE WHEN posted_on IS NOT NULL AND posted_on <= $end::DATE THEN date_diff('day', planned_for::DATE, posted_on) END AS "Days to post",
       views AS "Views", shares AS "Shares",
       (posted_on IS NOT NULL AND posted_on <= $end::DATE)::INTEGER AS "Posted"
FROM events WHERE kind = $kind AND status = 'held' AND planned_for::DATE BETWEEN $start AND $end ORDER BY planned_for;

-- name: competition_by_student
-- Grain: one row per student active on $end. Source: events, event_attendance, students. Feeds: Students assigned a competition, Assigned students who entered.
-- Edge cases: a competition not yet held has attendance unknown: the student is assigned but neither entered nor not entered.
WITH c AS (
    SELECT a.student_id, a.attended, a.outcome
    FROM events e JOIN event_attendance a USING (event_id)
    WHERE e.kind = 'competition' AND e.status <> 'cancelled' AND e.planned_for::DATE BETWEEN $start AND $end
)
SELECT s.name AS "Student", s.student_id AS "ID",
       (count(c.student_id) > 0)::INTEGER AS "Assigned a competition",
       count(*) FILTER (WHERE c.attended IS NOT NULL) AS "Result recorded",
       count(*) FILTER (WHERE c.attended) AS "Entered",
       max(c.outcome) AS "Stage reached"
FROM students s LEFT JOIN c ON c.student_id = s.student_id
WHERE is_active(s.program_start_date, s.left_on, $end::DATE) GROUP BY s.student_id, s.name ORDER BY s.name;

-- name: social_work_group_rows
-- Grain: one row per social-work group with an activity in the period. Source: events, event_attendance. Feeds: Groups formed.
SELECT e.group_id AS "Group", count(DISTINCT a.student_id) FILTER (WHERE a.invited) AS "Members",
       count(DISTINCT e.event_id) FILTER (WHERE e.status = 'held') AS "Activities held",
       count(DISTINCT e.event_id) FILTER (WHERE e.status = 'cancelled') AS "Activities cancelled",
       count(DISTINCT e.event_id) FILTER (WHERE e.status = 'planned') AS "Activities still planned"
FROM events e LEFT JOIN event_attendance a USING (event_id)
WHERE e.kind = 'social_work' AND e.planned_for::DATE BETWEEN $start AND $end GROUP BY e.group_id ORDER BY e.group_id;

-- name: roadmap_items_due
-- Grain: one row per $roadmap item due in the period. Source: roadmap_items, students.
-- Feeds: every "done by deadline" KPI. Done late is not done by deadline; an item done after $end is still open.
SELECT s.name AS "Student", s.student_id AS "ID", r.title AS "Item", r.level AS "Level", r.due_date AS "Due", r.done_at::DATE AS "Done on",
       CASE WHEN r.done_at IS NOT NULL AND r.done_at::DATE <= $end::DATE AND r.done_at::DATE <= r.due_date THEN 'Done by the deadline'
            WHEN r.done_at IS NOT NULL AND r.done_at::DATE <= $end::DATE THEN 'Done late' ELSE 'Open' END AS "Status",
       (r.done_at IS NOT NULL AND r.done_at::DATE <= r.due_date AND r.done_at::DATE <= $end::DATE)::INTEGER AS "Done by the deadline"
FROM roadmap_items r JOIN students s USING (student_id)
WHERE r.roadmap = $roadmap AND r.due_date BETWEEN $start AND $end AND is_active(s.program_start_date, s.left_on, $end::DATE)
ORDER BY s.name, r.due_date;

-- name: roadmap_coverage_by_student
-- Grain: one row per student active on $end, for $roadmap. Source: roadmap_items, students. Feeds: the "Students with a ... roadmap / milestones" KPIs.
SELECT s.name AS "Student", s.student_id AS "ID", count(r.item_id) AS "Items on the roadmap", (count(r.item_id) > 0)::INTEGER AS "Has a roadmap"
FROM students s LEFT JOIN roadmap_items r ON r.student_id = s.student_id AND r.roadmap = $roadmap AND r.created_at::DATE <= $end::DATE
WHERE is_active(s.program_start_date, s.left_on, $end::DATE) GROUP BY s.student_id, s.name ORDER BY s.name;

-- name: roadmap_completion_rows
-- Grain: one row per $roadmap item created by $end. Source: roadmap_items, students. Feeds: Career roadmap items done. Due dates are ignored.
SELECT s.name AS "Student", s.student_id AS "ID", r.title AS "Item", r.level AS "Level", r.due_date AS "Due", r.done_at::DATE AS "Done on",
       (r.done_at IS NOT NULL AND r.done_at::DATE <= $end::DATE)::INTEGER AS "Done"
FROM roadmap_items r JOIN students s USING (student_id)
WHERE r.roadmap = $roadmap AND r.created_at::DATE <= $end::DATE AND is_active(s.program_start_date, s.left_on, $end::DATE)
ORDER BY s.name, r.due_date;

-- name: advisor_input_rows
-- Grain: one row per student, month and advisor duty in the quarter so far. Source: advisor_inputs, students. Feeds: Advisor inputs done.
SELECT s.name AS "Student", s.student_id AS "ID", i.month AS "Month", i.input_kind AS "Input",
       CASE WHEN i.input_kind = 'career_roadmap_reviewed' THEN coalesce(s.career_counsellor_id, 'UNASSIGNED') ELSE s.advisor_id END AS "Owner",
       i.done::INTEGER AS "Done"
FROM advisor_inputs i JOIN students s USING (student_id)
WHERE i.month BETWEEN date_trunc('month', $start::DATE) AND $end::DATE AND is_active(s.program_start_date, s.left_on, $end::DATE)
ORDER BY s.name, i.month, i.input_kind;

-- name: exam_rows
-- Grain: one row per student and subject for the $exam_type exam. Source: exam_targets, students. Feeds: Exam scores at or above target.
-- Edge cases: an exam not yet taken has no score and is left out of the share.
SELECT s.name AS "Student", s.student_id AS "ID", t.subject AS "Subject", t.target_score AS "Target score", t.actual_score AS "Actual score",
       (t.actual_score IS NOT NULL)::INTEGER AS "Scored", (t.actual_score >= t.target_score)::INTEGER AS "Met the target"
FROM exam_targets t JOIN students s USING (student_id)
WHERE t.exam_type = $exam_type AND is_active(s.program_start_date, s.left_on, $end::DATE) ORDER BY s.name, t.subject;

-- name: roadmap_feedback_rows
-- Grain: one row per monthly roadmap check-in in the quarter so far. Source: feedback, students. Feeds: Roadmap check-in rating.
SELECT f.submitted_at::DATE AS "Submitted", s.name AS "Student", s.student_id AS "ID", f.q1_rating AS "Pace of progress", f.q2_rating AS "How invested",
       f.q3_rating AS "Confidence in the quarterly goals", round(f.composite, 2) AS "Average rating"
FROM feedback f JOIN students s USING (student_id)
WHERE f.kind = 'roadmap' AND f.submitted_at::DATE BETWEEN $start AND $end AND is_active(s.program_start_date, s.left_on, $end::DATE)
ORDER BY f.submitted_at, s.name;

-- name: whoop_sync_by_student
-- Grain: one row per active student who had connected a Whoop by $end. Source: students, wearable_daily. Feeds: Whoop students still syncing.
WITH last AS (
    SELECT student_id, max(day) AS last_reading FROM wearable_daily WHERE data_source = 'whoop' AND day <= $end::DATE GROUP BY student_id
)
SELECT s.name AS "Student", s.student_id AS "ID", s.advisor_id AS "Advisor", s.wearable_connected_on AS "Connected on", s.wearable_disconnected_on AS "Disconnected on",
       l.last_reading AS "Last reading", date_diff('day', l.last_reading, $end::DATE) AS "Days without data",
       ((s.wearable_disconnected_on IS NULL OR s.wearable_disconnected_on > $end::DATE) AND l.last_reading IS NOT NULL
        AND date_diff('day', l.last_reading, $end::DATE) <= $data_freshness_wearable_silent_days)::INTEGER AS "Still syncing"
FROM students s LEFT JOIN last l USING (student_id)
WHERE s.wearable = 'whoop' AND s.wearable_connected_on <= $end::DATE AND is_active(s.program_start_date, s.left_on, $end::DATE)
ORDER BY "Still syncing", s.name;

-- name: clip_reach_rows
-- Grain: one row per held clip of $kind in the period. Source: events. Feeds: Posted clips reaching the view target. A clip not yet posted has no audience to count.
SELECT planned_for::DATE AS "Date", title AS "Title", posted_on AS "Posted on", views AS "Views", shares AS "Shares",
       (posted_on IS NOT NULL AND posted_on <= $end::DATE)::INTEGER AS "Posted",
       (posted_on IS NOT NULL AND posted_on <= $end::DATE AND views >= $branding_view_target)::INTEGER AS "Reached the view target"
FROM events WHERE kind = $kind AND status = 'held' AND planned_for::DATE BETWEEN $start AND $end ORDER BY planned_for;

-- name: entrepreneurship_rating_rows
-- Grain: one row per one-tap entrepreneurship rating in the quarter so far. Source: feedback, students. Feeds: Entrepreneurship rating.
SELECT f.submitted_at::DATE AS "Submitted", s.name AS "Student", s.student_id AS "ID", f.composite AS "Rating"
FROM feedback f JOIN students s USING (student_id)
WHERE f.kind = 'entrepreneurship' AND f.submitted_at::DATE BETWEEN $start AND $end AND is_active(s.program_start_date, s.left_on, $end::DATE)
ORDER BY f.submitted_at, s.name;

-- name: advisor_input_kind_rows
-- Grain: one row per student and month for one advisor duty, $input_kind, in the quarter so far. Source: advisor_inputs, students.
-- Feeds: Monthly syllabus reviews done, Rigour checks done, Sprints made.
SELECT s.name AS "Student", s.student_id AS "ID", i.month AS "Month", s.advisor_id AS "Advisor", i.done::INTEGER AS "Done"
FROM advisor_inputs i JOIN students s USING (student_id)
WHERE i.input_kind = $input_kind AND i.month BETWEEN date_trunc('month', $start::DATE) AND $end::DATE AND is_active(s.program_start_date, s.left_on, $end::DATE)
ORDER BY s.name, i.month;

-- name: chapter_activity_by_student
-- Grain: one row per student active on $end. Source: chapter_progress, students. Feeds: Students still working through their chapters.
SELECT s.name AS "Student", s.student_id AS "ID", max(c.updated_at::DATE) AS "Last chapter update", count(c.chapter_id) AS "Chapters",
       coalesce(bool_or(c.updated_at::DATE BETWEEN $end::DATE - ($scorecard_window_days::INTEGER - 1) AND $end::DATE), false)::INTEGER AS "Updated a chapter recently"
FROM students s LEFT JOIN chapter_progress c USING (student_id)
WHERE is_active(s.program_start_date, s.left_on, $end::DATE) GROUP BY s.student_id, s.name ORDER BY "Updated a chapter recently", s.name;

-- name: rigour_closed_by_student
-- Grain: one row per active student with chapters planned in a closed month. Source: chapter_progress, students. Feeds: Chapters from past months fully complete.
SELECT s.name AS "Student", s.student_id AS "ID", count(*) AS "Chapters planned",
       count(*) FILTER (WHERE c.stage_reached = $syllabus_stages_total) AS "Fully complete"
FROM chapter_progress c JOIN students s USING (student_id)
WHERE c.planned_month < date_trunc('month', $end::DATE) AND is_active(s.program_start_date, s.left_on, $end::DATE)
GROUP BY s.student_id, s.name ORDER BY s.name;

-- name: summer_applications_by_student
-- Grain: one row per student invited to the support sessions this quarter. Source: events, event_attendance, students. Feeds: Students who submitted an application.
SELECT coalesce(s.name, a.student_id) AS "Student", a.student_id AS "ID", count(*) FILTER (WHERE a.attended) AS "Sessions attended",
       coalesce(bool_or(a.outcome IN ('submitted', 'accepted')), false)::INTEGER AS "Applied",
       coalesce(bool_or(a.outcome = 'accepted'), false)::INTEGER AS "Accepted"
FROM events e JOIN event_attendance a USING (event_id) LEFT JOIN students s ON s.student_id = a.student_id
WHERE e.kind = 'summer_support' AND e.status <> 'cancelled' AND e.planned_for::DATE BETWEEN $start AND $end AND a.invited
GROUP BY a.student_id, s.name ORDER BY "Applied", "Student";
