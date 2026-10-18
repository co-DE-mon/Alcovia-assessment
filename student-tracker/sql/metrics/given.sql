-- Given success metrics (DuckDB): the five metrics Alcovia named in the brief. Period = $start..$end inclusive, $end on or before the as-of day.
-- Definitions: student-tracker/README.md#kpi-catalogue (Given success metrics). Tags like [A3] point to README.md#assumption-reference-index.
-- Every query documents: definition, grain, source tables, edge cases. A zero denominator gives NULL, never 0.
-- Only students active on $end are counted, so a student who has left does not drag the cohort number.

-- name: task_metrics
-- Definition: task completion rate = to-dos done / to-dos due in the period. Deadline adherence = to-dos done on or before their due date /
--   to-dos done. A to-do is due when its due_date falls inside the period.
-- Grain: one row (cohort). Source: todos, students.
-- Edge cases: the API has no completion timestamp, so updated_at stands in for it [A3]. Pending and in-progress to-dos past their due date count
--   as not done. Rates are NULL when nothing was due (completion) or nothing was done (adherence). Ratio of sums, so a student with many
--   to-dos weighs more; task_metrics_by_student gives the per-student view.
WITH t AS (
    SELECT t.student_id, t.status, t.due_date, t.updated_at
    FROM todos t JOIN students s USING (student_id)
    WHERE t.due_date BETWEEN $start AND $end AND is_active(s.program_start_date, s.left_on, $end::DATE)
),
agg AS (
    SELECT count(*) AS todos_due,
           count(*) FILTER (WHERE status = 'done') AS todos_done,
           count(*) FILTER (WHERE status = 'done' AND updated_at::DATE <= due_date) AS done_on_time,
           count(DISTINCT student_id) AS students
    FROM t
)
SELECT students, todos_due, todos_done, done_on_time,
       todos_done::DOUBLE / nullif(todos_due, 0) AS task_completion_rate,
       done_on_time::DOUBLE / nullif(todos_done, 0) AS deadline_adherence
FROM agg;

-- name: task_metrics_by_student
-- Definition: the same two rates for each student, for the cohort's off-track list.
-- Grain: one row per student active on $end that has at least one to-do due in the period. Source: todos, students.
-- Edge cases: a student with no to-do due is absent (no data), not 0%. Same completion-time stand-in as task_metrics [A3].
SELECT t.student_id,
       count(*) AS todos_due,
       count(*) FILTER (WHERE t.status = 'done') AS todos_done,
       count(*) FILTER (WHERE t.status = 'done' AND t.updated_at::DATE <= t.due_date) AS done_on_time,
       count(*) FILTER (WHERE t.status = 'done')::DOUBLE / count(*) AS task_completion_rate,
       count(*) FILTER (WHERE t.status = 'done' AND t.updated_at::DATE <= t.due_date)::DOUBLE
           / nullif(count(*) FILTER (WHERE t.status = 'done'), 0) AS deadline_adherence
FROM todos t JOIN students s USING (student_id)
WHERE t.due_date BETWEEN $start AND $end AND is_active(s.program_start_date, s.left_on, $end::DATE)
GROUP BY t.student_id
ORDER BY t.student_id;

-- name: time_estimation
-- Definition: the average pace accuracy over every measured student-subject (latest snapshot per student and subject; see the formula in the edge cases).
-- Grain: one row (cohort). Source: study_hours, students.
-- Edge cases: unmeasured student-subjects are counted in not_measured and left out of the average, so the average is NULL, not 0, when none
--   is measured.
WITH latest AS (
    SELECT h.student_id, h.subject, h.as_of, h.estimated_hours, h.actual_hours,
           row_number() OVER (PARTITION BY h.student_id, h.subject ORDER BY h.as_of DESC) AS rn
    FROM study_hours h JOIN students s USING (student_id)
    WHERE h.quarter = $quarter AND h.as_of <= $end AND is_active(s.program_start_date, s.left_on, $end::DATE)
),
acc AS (
    SELECT student_id,
           estimated_hours * least(1.0, greatest(0.0, (date_diff('day', $quarter_start, as_of) + 1)::DOUBLE
                                                      / (date_diff('day', $quarter_start, $quarter_end) + 1))) AS expected_hours,
           actual_hours
    FROM latest WHERE rn = 1
),
scored AS (
    SELECT student_id,
           CASE WHEN actual_hours = 0 OR expected_hours = 0 THEN NULL
                ELSE greatest(0.0, 1 - abs(actual_hours - expected_hours) / expected_hours) END AS accuracy
    FROM acc
)
SELECT count(*) AS student_subjects,
       count(accuracy) AS measured,
       count(*) - count(accuracy) AS not_measured,
       count(DISTINCT student_id) FILTER (WHERE accuracy IS NOT NULL) AS students_measured,
       avg(accuracy) AS avg_accuracy
FROM scored;

-- name: chapter_readiness_by_student
-- Definition: chapter readiness score = average over a student's chapters of stage_reached / $syllabus_stages_total, for chapters planned
--   up to the month containing $end. Stages: read, notes, practice above 70%, timed past paper, exam accuracy above 80% [A16].
-- Grain: one row per student active on $end. Source: chapter_progress, students.
-- Edge cases: a student with no planned chapter is absent. A chapter at stage 0 counts as 0, because it is planned and not started.
SELECT c.student_id, count(*) AS chapters,
       avg(c.stage_reached)::DOUBLE / $syllabus_stages_total AS readiness_score
FROM chapter_progress c JOIN students s USING (student_id)
WHERE c.planned_month <= date_trunc('month', $end::DATE) AND is_active(s.program_start_date, s.left_on, $end::DATE)
GROUP BY c.student_id
ORDER BY c.student_id;

-- name: chapter_readiness
-- Definition: the average readiness score over all planned chapters of the cohort (see chapter_readiness_by_student).
-- Grain: one row (cohort). Source: chapter_progress, students.
-- Edge cases: NULL when no chapter is planned.
SELECT count(DISTINCT c.student_id) AS students, count(*) AS chapters,
       avg(c.stage_reached)::DOUBLE / $syllabus_stages_total AS readiness_score
FROM chapter_progress c JOIN students s USING (student_id)
WHERE c.planned_month <= date_trunc('month', $end::DATE) AND is_active(s.program_start_date, s.left_on, $end::DATE);

-- name: rigour_adherence
-- Definition: monthly rigour adherence = chapters planned for the month containing $end that reached the last stage / chapters planned
--   for that month, over the whole cohort.
-- Grain: one row (cohort). Source: chapter_progress, students.
-- Edge cases: NULL when no chapter is planned that month.
SELECT count(DISTINCT c.student_id) AS students, count(*) AS chapters_planned,
       count(*) FILTER (WHERE c.stage_reached = $syllabus_stages_total) AS chapters_complete,
       count(*) FILTER (WHERE c.stage_reached = $syllabus_stages_total)::DOUBLE / nullif(count(*), 0) AS adherence
FROM chapter_progress c JOIN students s USING (student_id)
WHERE c.planned_month = date_trunc('month', $end::DATE) AND is_active(s.program_start_date, s.left_on, $end::DATE);

-- name: rigour_closed_months
-- Definition (Performed, rigour of completion [A65]): chapters planned in months that have already ended that reached the last stage ($syllabus_stages_total) /
--   those chapters. rigour_adherence reads the current month, which is unfinished and so low by construction; this one reads only closed months.
-- Grain: one row (cohort). Source: chapter_progress, students.
-- Edge cases: chapters of students not active on $end are left out. NULL rate when no chapter was planned in a closed month.
SELECT count(DISTINCT c.student_id) AS students, count(*) AS chapters_planned,
       count(*) FILTER (WHERE c.stage_reached = $syllabus_stages_total) AS chapters_complete,
       count(*) FILTER (WHERE c.stage_reached = $syllabus_stages_total)::DOUBLE / nullif(count(*), 0) AS closed_month_rate
FROM chapter_progress c JOIN students s USING (student_id)
WHERE c.planned_month < date_trunc('month', $end::DATE) AND is_active(s.program_start_date, s.left_on, $end::DATE);

-- name: chapter_activity
-- Definition (Liked, proxy, rigour of completion [A2][A65]): active students who updated any chapter's stage in the last $scorecard_window_days days ending $end /
--   active students. A student who keeps moving chapters forward is still choosing to do the work; a silent one has stopped.
-- Grain: one row (cohort). Source: chapter_progress, students.
-- Edge cases: a student with no chapters counts as not working. updated_at is the time the stage last changed.
WITH s AS (
    SELECT s.student_id,
           coalesce(bool_or(c.updated_at::DATE BETWEEN $end::DATE - ($scorecard_window_days::INTEGER - 1) AND $end::DATE), false) AS recent
    FROM students s LEFT JOIN chapter_progress c USING (student_id)
    WHERE is_active(s.program_start_date, s.left_on, $end::DATE) GROUP BY s.student_id
)
SELECT count(*) AS active_students, count(*) FILTER (WHERE recent) AS working,
       count(*) FILTER (WHERE recent)::DOUBLE / nullif(count(*), 0) AS working_rate
FROM s;
