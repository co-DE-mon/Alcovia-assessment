-- Roadmap metrics (DuckDB). Period = $start..$end inclusive. For "items due by today" pass the quarter's first day as $start.
-- Definitions: student-tracker/README.md#kpi-catalogue (Roadmaps). Tags like [A30] point to README.md#assumption-reference-index.
-- Every query documents: definition, grain, source tables, edge cases. A zero denominator gives NULL, never 0.
-- A roadmap item is done by its deadline when done_at falls on or before due_date and on or before $end.

-- name: roadmap_status
-- Definition (Performed): per roadmap and level, items due in the period and the share done by their deadline [A30].
--   roadmap is career, personal, academic, social_work or entrepreneurship; level is annual, quarterly or monthly.
-- Grain: one row per roadmap and level with an item due in the period. Source: roadmap_items, students.
-- Edge cases: an item done after $end is still open at $end. An item done after its deadline is done_late, not done_by_deadline.
--   Only students active on $end count.
SELECT r.roadmap, r.level,
       count(*) AS items_due,
       count(*) FILTER (WHERE r.done_at IS NOT NULL AND r.done_at::DATE <= r.due_date AND r.done_at::DATE <= $end::DATE) AS done_by_deadline,
       count(*) FILTER (WHERE r.done_at IS NOT NULL AND r.done_at::DATE > r.due_date AND r.done_at::DATE <= $end::DATE) AS done_late,
       count(*) FILTER (WHERE r.done_at IS NULL OR r.done_at::DATE > $end::DATE) AS open_items,
       count(*) FILTER (WHERE r.done_at IS NOT NULL AND r.done_at::DATE <= r.due_date AND r.done_at::DATE <= $end::DATE)::DOUBLE / count(*) AS done_by_deadline_rate
FROM roadmap_items r JOIN students s USING (student_id)
WHERE r.due_date BETWEEN $start AND $end AND is_active(s.program_start_date, s.left_on, $end::DATE)
GROUP BY r.roadmap, r.level
ORDER BY r.roadmap, r.level;

-- name: roadmap_on_track_by_student
-- Definition (Performed): per student, items due in the period done by their deadline / items due. On track when the share is at least
--   $roadmap_on_track_pct percent [A30].
-- Grain: one row per active student with at least one item due in the period. Source: roadmap_items, students.
-- Edge cases: a student with nothing due is absent, not on track and not off track. Late completions do not count as done by deadline.
SELECT r.student_id,
       count(*) AS items_due,
       count(*) FILTER (WHERE r.done_at IS NOT NULL AND r.done_at::DATE <= r.due_date AND r.done_at::DATE <= $end::DATE) AS done_by_deadline,
       100.0 * count(*) FILTER (WHERE r.done_at IS NOT NULL AND r.done_at::DATE <= r.due_date AND r.done_at::DATE <= $end::DATE) / count(*) AS pct,
       100.0 * count(*) FILTER (WHERE r.done_at IS NOT NULL AND r.done_at::DATE <= r.due_date AND r.done_at::DATE <= $end::DATE) / count(*)
           >= $roadmap_on_track_pct AS on_track
FROM roadmap_items r JOIN students s USING (student_id)
WHERE r.due_date BETWEEN $start AND $end AND is_active(s.program_start_date, s.left_on, $end::DATE)
GROUP BY r.student_id
ORDER BY r.student_id;

-- name: roadmap_coverage
-- Definition (Conducted): per roadmap, active students with at least one item created on or before $end / active students.
-- Grain: one row per roadmap that has any item. Source: roadmap_items, students.
-- Edge cases: a roadmap nobody has is absent from the result, which the dashboard reads as 0% covered. Counts students once however many
--   items they have.
WITH active AS (SELECT student_id FROM students WHERE is_active(program_start_date, left_on, $end::DATE)),
n AS (SELECT count(*) AS students FROM active)
SELECT r.roadmap,
       (SELECT students FROM n) AS active_students,
       count(DISTINCT r.student_id) AS students_with_roadmap,
       count(DISTINCT r.student_id)::DOUBLE / nullif((SELECT students FROM n), 0) AS coverage_rate
FROM roadmap_items r JOIN active USING (student_id)
WHERE r.created_at::DATE <= $end::DATE
GROUP BY r.roadmap
ORDER BY r.roadmap;

-- name: advisor_inputs_by_kind
-- Definition (Conducted): the same inputs grouped by kind (targets aligned, guardrails set, inputs at cadence, deadline messages sent, tutor
--   input set, sprint made, syllabus review, rigour check, career roadmap reviewed, personal milestones set), done / due [A31].
-- Grain: one row per input kind. Source: advisor_inputs, students.
-- Edge cases: whole calendar months from the month of $start to the month of $end, so the current month is unfinished and reads low.
SELECT i.input_kind,
       count(*) AS inputs_due,
       count(*) FILTER (WHERE i.done) AS inputs_done,
       count(*) FILTER (WHERE i.done)::DOUBLE / count(*) AS done_rate
FROM advisor_inputs i JOIN students s USING (student_id)
WHERE i.month BETWEEN date_trunc('month', $start::DATE) AND $end::DATE AND is_active(s.program_start_date, s.left_on, $end::DATE)
GROUP BY i.input_kind
ORDER BY i.input_kind;

-- name: exam_score_vs_target
-- Definition (Performed, academic): per exam type, the average score target, the average actual score and the share of scored
--   student-subjects at or above target [A53].
-- Grain: one row per exam type. Source: exam_targets, students.
-- Edge cases: an exam not yet taken has no actual score and is left out of the averages and the share, so those are NULL, not 0 (n_scored
--   shows how many were scored). Only students active on $end.
SELECT t.exam_type,
       count(*) AS student_subjects,
       count(t.actual_score) AS n_scored,
       avg(t.target_score) AS avg_target,
       avg(t.actual_score) AS avg_actual,
       avg(t.actual_score - t.target_score) AS avg_gap,
       count(*) FILTER (WHERE t.actual_score >= t.target_score)::DOUBLE / nullif(count(t.actual_score), 0) AS met_target_rate
FROM exam_targets t JOIN students s USING (student_id)
WHERE is_active(s.program_start_date, s.left_on, $end::DATE)
GROUP BY t.exam_type
ORDER BY t.exam_type;

-- name: roadmap_feedback
-- Definition (Liked): the monthly roadmap check-in form (pace of progress, how invested, confidence the month leads to the quarterly
--   goals): average of its three ratings, and the share of active students who answered in the period [A21].
-- Grain: one row (cohort). Source: feedback, students.
-- Edge cases: feedback of students no longer active is ignored. NULL averages when no one answered.
WITH f AS (
    SELECT f.student_id, f.composite, f.q1_rating, f.q2_rating, f.q3_rating
    FROM feedback f JOIN students s USING (student_id)
    WHERE f.kind = 'roadmap' AND f.submitted_at::DATE BETWEEN $start AND $end AND is_active(s.program_start_date, s.left_on, $end::DATE)
),
n AS (SELECT count(*) AS students FROM students WHERE is_active(program_start_date, left_on, $end::DATE))
SELECT (SELECT students FROM n) AS active_students,
       count(DISTINCT student_id) AS students_responded,
       count(DISTINCT student_id)::DOUBLE / nullif((SELECT students FROM n), 0) AS response_rate,
       count(*) AS responses, avg(composite) AS avg_composite, avg(q1_rating) AS avg_pace, avg(q2_rating) AS avg_invested, avg(q3_rating) AS avg_confidence
FROM f;

-- name: roadmap_completion
-- Definition (Performed, career roadmap): per roadmap, items created by $end that are done by $end / those items, and the students whose
--   items are all done. The brief treats the career roadmap as binary, done or not done, so this ignores due dates.
-- Grain: one row per roadmap that has any item. Source: roadmap_items, students.
-- Edge cases: done_at after $end counts as not done at $end. A student with no item for a roadmap is absent from it, not counted as done
--   or not done. Only students active on $end.
WITH r AS (
    SELECT r.roadmap, r.student_id, (r.done_at IS NOT NULL AND r.done_at::DATE <= $end::DATE) AS done
    FROM roadmap_items r JOIN students s USING (student_id)
    WHERE r.created_at::DATE <= $end::DATE AND is_active(s.program_start_date, s.left_on, $end::DATE)
),
per_student AS (SELECT roadmap, student_id, bool_and(done) AS all_done FROM r GROUP BY roadmap, student_id)
SELECT r.roadmap, count(*) AS items, count(*) FILTER (WHERE r.done) AS items_done,
       count(*) FILTER (WHERE r.done)::DOUBLE / count(*) AS completion_rate,
       (SELECT count(*) FROM per_student p WHERE p.roadmap = r.roadmap) AS students,
       (SELECT count(*) FROM per_student p WHERE p.roadmap = r.roadmap AND p.all_done) AS students_all_done
FROM r
GROUP BY r.roadmap
ORDER BY r.roadmap;
