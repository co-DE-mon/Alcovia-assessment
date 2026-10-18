-- Per-student metrics (DuckDB) for the off-track list. Measured at $end. Every query documents: definition, grain, source tables, edge cases.

-- name: student_activity
-- Definition: for each active student, over the last $scorecard_lookback_days days ending $end: quizzes held that they could have taken, quizzes they
--   started, valid focus minutes (completed sessions only), and the date of their latest quiz, focus session or completed to-do.
-- Grain: one row per student active on $end. Source: students, events, quiz_attempts, focus_sessions, todos.
-- Edge cases: quizzes held before the student joined are not due to them. A student with no quiz held in the window has quizzes_due = 0, which
--   is not a miss. focus_minutes is 0 when the student has no completed session, because that is a real zero; last_activity is NULL when the
--   student has never done any of the three. days_enrolled counts from program_start_date to $end. updated_at stands in for the completion time of a to-do [A3].
WITH s AS (
    SELECT student_id, name, advisor_id, program_start_date FROM students WHERE is_active(program_start_date, left_on, $end::DATE)
),
win AS (SELECT $end::DATE - ($scorecard_lookback_days::INTEGER - 1) AS lo),
quiz AS (
    SELECT s.student_id,
           (SELECT count(*) FROM events e
            WHERE e.kind = 'quiz' AND e.status = 'held' AND e.planned_for::DATE BETWEEN (SELECT lo FROM win) AND $end::DATE
              AND e.planned_for::DATE >= s.program_start_date) AS quizzes_due,
           count(a.student_id) FILTER (WHERE a.started_at::DATE BETWEEN (SELECT lo FROM win) AND $end::DATE) AS quizzes_started,
           max(a.started_at::DATE) FILTER (WHERE a.started_at::DATE <= $end::DATE) AS last_quiz
    FROM s LEFT JOIN quiz_attempts a USING (student_id) GROUP BY s.student_id, s.program_start_date
),
focus AS (
    SELECT s.student_id,
           coalesce(sum(f.actual_minutes) FILTER (WHERE f.status = 'completed' AND f.started_at::DATE BETWEEN (SELECT lo FROM win) AND $end::DATE), 0) AS focus_minutes,
           max(f.started_at::DATE) FILTER (WHERE f.started_at::DATE <= $end::DATE) AS last_focus
    FROM s LEFT JOIN focus_sessions f USING (student_id) GROUP BY s.student_id
),
todo AS (
    SELECT s.student_id, max(t.updated_at::DATE) FILTER (WHERE t.status = 'done' AND t.updated_at::DATE <= $end::DATE) AS last_todo
    FROM s LEFT JOIN todos t USING (student_id) GROUP BY s.student_id
)
SELECT s.student_id, s.name, s.advisor_id, quiz.quizzes_due, quiz.quizzes_started, focus.focus_minutes,
       quiz.last_quiz, focus.last_focus, todo.last_todo,
       greatest(quiz.last_quiz, focus.last_focus, todo.last_todo) AS last_activity,
       date_diff('day', greatest(quiz.last_quiz, focus.last_focus, todo.last_todo), $end::DATE) AS days_since_activity,
       date_diff('day', s.program_start_date, $end::DATE) AS days_enrolled
FROM s JOIN quiz USING (student_id) JOIN focus USING (student_id) JOIN todo USING (student_id)
ORDER BY s.student_id;

-- name: student_timeline
-- Definition: one student's day-by-day record over the period: whether a quiz was held, whether they started it, valid focus minutes, and
--   to-dos marked done. Feeds the student page.
-- Grain: one row per day the student was active, for the student in $student_id. Source: students, events, quiz_attempts, focus_sessions, todos.
-- Edge cases: days before the student joined or after they left are omitted. quiz_held is false on days with no quiz or a cancelled one, so a
--   student who did not start a quiz is a miss only on days it was held. Focus minutes count completed sessions only; updated_at stands in for a
--   to-do's completion time [A3]. An unknown student gives no rows.
WITH st AS (SELECT program_start_date, left_on FROM students WHERE student_id = $student_id)
SELECT d.day,
       coalesce((SELECT bool_or(e.status = 'held') FROM events e WHERE e.kind = 'quiz' AND e.planned_for::DATE = d.day), false) AS quiz_held,
       EXISTS (SELECT 1 FROM quiz_attempts a WHERE a.student_id = $student_id AND a.started_at::DATE = d.day) AS quiz_started,
       coalesce((SELECT sum(f.actual_minutes) FROM focus_sessions f
                 WHERE f.student_id = $student_id AND f.status = 'completed' AND f.started_at::DATE = d.day), 0) AS focus_minutes,
       (SELECT count(*) FROM todos t WHERE t.student_id = $student_id AND t.status = 'done' AND t.updated_at::DATE = d.day) AS todos_done
FROM period_days($start, $end) d, st
WHERE is_active(st.program_start_date, st.left_on, d.day)
ORDER BY d.day;
