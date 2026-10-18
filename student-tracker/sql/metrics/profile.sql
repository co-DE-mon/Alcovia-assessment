-- Student profile queries (DuckDB): everything the tracker holds about one student, one query per section of the student dialog.
-- All take $student_id. Activity logs (quizzes, focus, to-dos, wearable) cover the scorecard period $start..$end; events, feedback and advisor inputs
-- cover the quarter so far ($quarter_start..$end); roadmaps, chapters and exams are shown in full. Aliases are plain words because they are the table headings.
-- Grain is stated per query. A student with nothing in a section gets no rows, which the dialog shows as "No records".

-- name: profile_identity
-- Grain: one row. Source: students, staff.
SELECT s.name AS "Name", s.student_id AS "ID", s.grade AS "Grade", s.board AS "Board", s.advisor_id AS "Advisor",
       coalesce(s.career_counsellor_id, 'None assigned') AS "Career counsellor", s.program_start_date AS "Joined",
       s.left_on AS "Left on", s.wearable AS "Wearable", s.wearable_connected_on AS "Wearable connected on", s.wearable_disconnected_on AS "Wearable disconnected on",
       s.calendar_connected_on AS "Calendar connected on", s.calendar_disconnected_on AS "Calendar disconnected on",
       s.weekday_study_hours AS "Weekday study hours", s.weekend_study_hours AS "Weekend study hours"
FROM students s WHERE s.student_id = $student_id;

-- name: profile_quizzes
-- Grain: one row per held 8pm quiz in the period while the student was active. Source: events, quiz_attempts, students.
SELECT e.event_id AS "Event ID", e.planned_for::DATE AS "Day", e.title AS "Topic",
       CASE WHEN a.started_at IS NULL THEN 'Not started'
            WHEN a.started_at < e.planned_for THEN 'Started before window'
            WHEN a.started_at BETWEEN e.planned_for AND e.planned_for + to_minutes($quiz_entry_window_minutes::INTEGER) THEN 'Started on time' ELSE 'Started late' END AS "Start",
       CASE WHEN a.completed_at IS NOT NULL THEN 'Finished' WHEN a.started_at IS NOT NULL THEN 'Not finished' END AS "Finish",
       CASE WHEN a.completed_at IS NOT NULL THEN a.score || ' / ' || a.total_questions END AS "Score"
FROM events e
JOIN students s ON s.student_id = $student_id AND is_active(s.program_start_date, s.left_on, e.planned_for::DATE)
LEFT JOIN quiz_attempts a ON a.event_id = e.event_id AND a.student_id = $student_id
WHERE e.kind = 'quiz' AND e.status = 'held' AND e.planned_for::DATE BETWEEN $start AND $end
ORDER BY e.planned_for DESC;

-- name: profile_focus
-- Grain: one row per focus session in the period. Source: focus_sessions.
SELECT session_id AS "Session ID", started_at AS "Started", planned_minutes AS "Planned minutes", round(actual_minutes) AS "Minutes", status AS "Result", fail_reason AS "Why it ended"
FROM focus_sessions WHERE student_id = $student_id AND started_at::DATE BETWEEN $start AND $end ORDER BY started_at DESC;

-- name: profile_todos
-- Grain: one row per to-do due in the period. Source: todos.
SELECT todo_id AS "To-do ID", due_date AS "Due", title AS "To-do", source AS "Created by", status AS "Status", created_at AS "Created", updated_at AS "Last updated"
FROM todos WHERE student_id = $student_id AND due_date BETWEEN $start AND $end ORDER BY due_date DESC;

-- name: profile_events
-- Grain: one row per event or session the student was invited to this quarter (quizzes are in profile_quizzes). Source: events, event_attendance.
SELECT e.event_id AS "Event ID", e.group_id AS "Group", e.planned_for::DATE AS "Date", e.kind AS "Type", e.title AS "Title", e.status AS "Status",
       CASE WHEN a.invited THEN 'Yes' ELSE 'No' END AS "Invited",
       CASE WHEN a.attended IS NULL THEN '–' WHEN a.attended THEN 'Yes' ELSE 'No' END AS "Attended", a.outcome AS "Outcome"
FROM event_attendance a JOIN events e USING (event_id)
WHERE a.student_id = $student_id AND e.kind <> 'quiz' AND e.planned_for::DATE BETWEEN $quarter_start AND $end
ORDER BY e.planned_for DESC;

-- name: profile_feedback
-- Grain: one row per feedback form the student submitted this quarter. Source: feedback, events.
SELECT f.feedback_id AS "Feedback ID", f.event_id AS "Event ID", f.submitted_at::DATE AS "Submitted", f.kind AS "Form", e.title AS "About", f.q1_rating AS "Rating 1", f.q2_rating AS "Rating 2", f.q3_rating AS "Rating 3",
       round(f.composite, 2) AS "Average rating", CASE WHEN f.has_comment THEN 'Yes' ELSE 'No' END AS "Left a comment"
FROM feedback f LEFT JOIN events e USING (event_id)
WHERE f.student_id = $student_id AND f.submitted_at::DATE BETWEEN $quarter_start AND $end ORDER BY f.submitted_at DESC;

-- name: profile_roadmap
-- Grain: one row per roadmap item, all time. Source: roadmap_items.
SELECT item_id AS "Item ID", roadmap AS "Roadmap", level AS "Level", title AS "Item", created_at AS "Created", due_date AS "Due", done_at AS "Done on",
       CASE WHEN done_at IS NOT NULL AND due_date IS NOT NULL AND done_at::DATE > due_date THEN 'Done late'
            WHEN done_at IS NOT NULL THEN 'Done'
            WHEN due_date IS NULL THEN 'Open, no due date' WHEN due_date < $end::DATE THEN 'Overdue' ELSE 'Open' END AS "Status"
FROM roadmap_items WHERE student_id = $student_id ORDER BY roadmap, due_date NULLS LAST;

-- name: profile_advisor_inputs
-- Grain: one row per advisor duty and month this quarter. Source: advisor_inputs.
SELECT month AS "Month", input_kind AS "Input", CASE WHEN done THEN 'Done' ELSE 'Not done' END AS "Status"
FROM advisor_inputs WHERE student_id = $student_id AND month BETWEEN date_trunc('month', $quarter_start::DATE) AND $end::DATE ORDER BY month DESC, input_kind;

-- name: profile_chapters
-- Grain: one row per chapter planned up to this month. Source: chapter_progress. Stage 0-5: read, notes, practice, timed paper, exam accuracy.
SELECT subject AS "Subject", chapter_id AS "Chapter", quarter AS "Quarter", planned_month AS "Planned for", updated_at AS "Updated", stage_reached AS "Stage reached (of 5)"
FROM chapter_progress WHERE student_id = $student_id AND planned_month <= date_trunc('month', $end::DATE) ORDER BY subject, planned_month, chapter_id;

-- name: profile_study_hours
-- Grain: one row per subject, latest snapshot in the quarter. Source: study_hours.
SELECT subject AS "Subject", as_of AS "As of", estimated_hours AS "Hours planned for the quarter", actual_hours AS "Hours studied so far"
FROM study_hours WHERE student_id = $student_id AND quarter = $quarter AND as_of <= $end
QUALIFY row_number() OVER (PARTITION BY subject ORDER BY as_of DESC) = 1 ORDER BY subject;

-- name: profile_exams
-- Grain: one row per subject and exam type. Source: exam_targets.
SELECT subject AS "Subject", exam_type AS "Exam", target_score AS "Target", actual_score AS "Score",
       CASE WHEN actual_score IS NULL THEN 'Not taken yet' WHEN actual_score >= target_score THEN 'Met the target' ELSE 'Below target' END AS "Result"
FROM exam_targets WHERE student_id = $student_id ORDER BY subject, exam_type;

-- name: profile_wearable
-- Grain: one row per day with wearable or manual data in the period. Source: wearable_daily.
SELECT day AS "Day", strain AS "Strain", recovery_pct AS "Recovery %", sleep_hours AS "Sleep hours", data_source AS "Source"
FROM wearable_daily WHERE student_id = $student_id AND day BETWEEN $start AND $end ORDER BY day DESC;

-- name: event_detail
-- Grain: one event. Source: events. The selected row is identified by event_id, never title/date, so repeated titles stay distinct.
SELECT event_id AS "Event ID", kind AS "Type", title AS "Title", planned_for AS "Scheduled", status AS "Status",
       group_id AS "Group", owner_staff_id AS "Owner", posted_on AS "Posted on", views AS "Views", shares AS "Shares",
       source AS "Source", nps_score AS "NPS (out of 10)"
FROM events WHERE event_id = $event_id AND planned_for::DATE <= $end::DATE;

-- name: event_people
-- Grain: one invited student. Source: event_attendance, students, quiz_attempts. Null attendance/quiz attempt stays unknown.
SELECT a.student_id AS "ID", coalesce(s.name, a.student_id) AS "Student", a.invited AS "Invited", a.attended AS "Attended",
       a.outcome AS "Outcome", q.started_at AS "Quiz started", q.completed_at AS "Quiz finished", q.score AS "Quiz score", q.total_questions AS "Questions"
FROM event_attendance a LEFT JOIN students s USING (student_id)
LEFT JOIN quiz_attempts q ON q.student_id = a.student_id AND q.event_id = a.event_id
WHERE a.event_id = $event_id ORDER BY "Student";

-- name: event_feedback
-- Grain: one feedback form. Source: feedback, students. Comments are never exported into this dashboard.
SELECT f.feedback_id AS "Feedback ID", f.student_id AS "ID", coalesce(s.name, f.student_id) AS "Student", f.kind AS "Form",
       f.q1_rating AS "Rating 1", f.q2_rating AS "Rating 2", f.q3_rating AS "Rating 3", f.composite AS "Average rating", f.submitted_at AS "Submitted"
FROM feedback f LEFT JOIN students s USING (student_id) WHERE f.event_id = $event_id ORDER BY f.submitted_at DESC;

-- name: group_events
-- Grain: one event in a selected group, through the selected reporting date. Source: events.
SELECT event_id AS "Event ID", group_id AS "Group", planned_for::DATE AS "Date", kind AS "Type", title AS "Title", status AS "Status"
FROM events WHERE group_id = $group_id AND planned_for::DATE <= $end::DATE ORDER BY planned_for DESC;

-- name: day_events
-- Grain: one event on the selected day. Source: events. A daily trend can lead to the actual quiz or other scheduled activity.
SELECT event_id AS "Event ID", planned_for AS "Scheduled", kind AS "Type", title AS "Title", status AS "Status"
FROM events WHERE planned_for::DATE = $day::DATE AND planned_for::DATE <= $end::DATE ORDER BY planned_for;

-- name: day_focus
-- Grain: one focus session on the selected day. Source: focus_sessions, students.
SELECT f.session_id AS "Session ID", f.student_id AS "ID", s.name AS "Student", f.started_at AS "Started",
       f.actual_minutes AS "Minutes", f.status AS "Result", f.fail_reason AS "Why it ended"
FROM focus_sessions f LEFT JOIN students s USING (student_id)
WHERE f.started_at::DATE = $day::DATE AND f.started_at::DATE <= $end::DATE ORDER BY f.started_at;
