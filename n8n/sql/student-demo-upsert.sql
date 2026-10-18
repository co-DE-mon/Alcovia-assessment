-- Generated synthetic cohort statement.
WITH staff_write AS (
  INSERT INTO staff (staff_id, name, role)
  SELECT staff_id, name, role FROM json_populate_recordset(NULL::staff, ($1::json->'tables'->'staff'))
  ON CONFLICT (staff_id) DO UPDATE SET
    name = EXCLUDED.name,
    role = EXCLUDED.role
  RETURNING 1
),
students_write AS (
  INSERT INTO students (student_id, name, grade, board, advisor_id, career_counsellor_id, program_start_date, left_on, wearable, wearable_connected_on, wearable_disconnected_on, calendar_connected_on, calendar_disconnected_on, weekday_study_hours, weekend_study_hours)
  SELECT student_id, name, grade, board, advisor_id, career_counsellor_id, program_start_date, left_on, wearable, wearable_connected_on, wearable_disconnected_on, calendar_connected_on, calendar_disconnected_on, weekday_study_hours, weekend_study_hours FROM json_populate_recordset(NULL::students, ($1::json->'tables'->'students'))
  ON CONFLICT (student_id) DO UPDATE SET
    name = EXCLUDED.name,
    grade = EXCLUDED.grade,
    board = EXCLUDED.board,
    advisor_id = EXCLUDED.advisor_id,
    career_counsellor_id = EXCLUDED.career_counsellor_id,
    program_start_date = EXCLUDED.program_start_date,
    left_on = students.left_on,
    wearable = EXCLUDED.wearable,
    wearable_connected_on = COALESCE(students.wearable_connected_on, EXCLUDED.wearable_connected_on),
    wearable_disconnected_on = CASE WHEN EXCLUDED.wearable = 'none' THEN COALESCE(students.wearable_disconnected_on, EXCLUDED.wearable_disconnected_on) END,
    calendar_connected_on = students.calendar_connected_on,
    calendar_disconnected_on = students.calendar_disconnected_on,
    weekday_study_hours = COALESCE(EXCLUDED.weekday_study_hours, students.weekday_study_hours),
    weekend_study_hours = COALESCE(EXCLUDED.weekend_study_hours, students.weekend_study_hours)
  RETURNING 1
),
events_write AS (
  INSERT INTO events (event_id, kind, title, planned_for, status, group_id, owner_staff_id, posted_on, views, shares, source, nps_score)
  SELECT event_id, kind, title, planned_for, status, group_id, owner_staff_id, posted_on, views, shares, source, nps_score FROM json_populate_recordset(NULL::events, ($1::json->'tables'->'events'))
  ON CONFLICT (event_id) DO UPDATE SET
    kind = EXCLUDED.kind,
    title = EXCLUDED.title,
    planned_for = EXCLUDED.planned_for,
    status = CASE WHEN events.kind='quiz' AND events.status IN ('held','cancelled') AND EXCLUDED.status='planned' THEN events.status ELSE EXCLUDED.status END,
    group_id = EXCLUDED.group_id,
    owner_staff_id = EXCLUDED.owner_staff_id,
    posted_on = EXCLUDED.posted_on,
    views = EXCLUDED.views,
    shares = EXCLUDED.shares,
    source = EXCLUDED.source,
    nps_score = EXCLUDED.nps_score
  RETURNING 1
),
event_attendance_write AS (
  INSERT INTO event_attendance (event_id, student_id, invited, attended, outcome)
  SELECT event_id, student_id, invited, attended, outcome FROM json_populate_recordset(NULL::event_attendance, ($1::json->'tables'->'event_attendance'))
  ON CONFLICT (event_id, student_id) DO UPDATE SET
    invited = EXCLUDED.invited,
    attended = EXCLUDED.attended,
    outcome = EXCLUDED.outcome
  RETURNING 1
),
quiz_attempts_write AS (
  INSERT INTO quiz_attempts (event_id, student_id, started_at, completed_at, score, total_questions)
  SELECT event_id, student_id, started_at, completed_at, score, total_questions FROM json_populate_recordset(NULL::quiz_attempts, ($1::json->'tables'->'quiz_attempts'))
  ON CONFLICT (event_id, student_id) DO UPDATE SET
    started_at = EXCLUDED.started_at,
    completed_at = COALESCE(EXCLUDED.completed_at,quiz_attempts.completed_at),
    score = COALESCE(EXCLUDED.score,quiz_attempts.score),
    total_questions = COALESCE(EXCLUDED.total_questions,quiz_attempts.total_questions)
  WHERE quiz_attempts.started_at=EXCLUDED.started_at AND (quiz_attempts.completed_at IS NULL OR (quiz_attempts.completed_at=EXCLUDED.completed_at AND quiz_attempts.score IS NOT DISTINCT FROM EXCLUDED.score))
  RETURNING 1
),
feedback_write AS (
  INSERT INTO feedback (feedback_id, student_id, event_id, kind, q1_rating, q2_rating, q3_rating, composite, has_comment, submitted_at)
  SELECT feedback_id, student_id, event_id, kind, q1_rating, q2_rating, q3_rating, composite, has_comment, submitted_at FROM json_populate_recordset(NULL::feedback, ($1::json->'tables'->'feedback')) incoming
  WHERE NOT EXISTS (SELECT 1 FROM feedback old WHERE old.feedback_id<>incoming.feedback_id AND old.student_id=incoming.student_id AND ((incoming.event_id IS NOT NULL AND old.event_id=incoming.event_id) OR (incoming.event_id IS NULL AND old.event_id IS NULL AND old.kind=incoming.kind AND date_trunc('month',old.submitted_at)=date_trunc('month',incoming.submitted_at))))
  ON CONFLICT (feedback_id) DO UPDATE SET
    student_id = EXCLUDED.student_id,
    event_id = EXCLUDED.event_id,
    kind = EXCLUDED.kind,
    q1_rating = EXCLUDED.q1_rating,
    q2_rating = EXCLUDED.q2_rating,
    q3_rating = EXCLUDED.q3_rating,
    composite = EXCLUDED.composite,
    has_comment = EXCLUDED.has_comment,
    submitted_at = EXCLUDED.submitted_at
  WHERE feedback.student_id IS NOT DISTINCT FROM EXCLUDED.student_id AND feedback.event_id IS NOT DISTINCT FROM EXCLUDED.event_id AND feedback.kind IS NOT DISTINCT FROM EXCLUDED.kind AND feedback.q1_rating IS NOT DISTINCT FROM EXCLUDED.q1_rating AND feedback.q2_rating IS NOT DISTINCT FROM EXCLUDED.q2_rating AND feedback.q3_rating IS NOT DISTINCT FROM EXCLUDED.q3_rating AND feedback.composite IS NOT DISTINCT FROM EXCLUDED.composite AND feedback.has_comment IS NOT DISTINCT FROM EXCLUDED.has_comment AND feedback.submitted_at IS NOT DISTINCT FROM EXCLUDED.submitted_at
  RETURNING 1
),
focus_sessions_write AS (
  INSERT INTO focus_sessions (session_id, student_id, started_at, planned_minutes, actual_minutes, status, fail_reason)
  SELECT session_id, student_id, started_at, planned_minutes, actual_minutes, status, fail_reason FROM json_populate_recordset(NULL::focus_sessions, ($1::json->'tables'->'focus_sessions'))
  ON CONFLICT (session_id) DO UPDATE SET
    student_id = EXCLUDED.student_id,
    started_at = EXCLUDED.started_at,
    planned_minutes = EXCLUDED.planned_minutes,
    actual_minutes = EXCLUDED.actual_minutes,
    status = EXCLUDED.status,
    fail_reason = EXCLUDED.fail_reason
  RETURNING 1
),
wearable_daily_write AS (
  INSERT INTO wearable_daily (student_id, day, strain, recovery_pct, sleep_hours, data_source)
  SELECT student_id, day, strain, recovery_pct, sleep_hours, data_source FROM json_populate_recordset(NULL::wearable_daily, ($1::json->'tables'->'wearable_daily'))
  ON CONFLICT (student_id, day) DO UPDATE SET
    strain = CASE WHEN wearable_daily.data_source=EXCLUDED.data_source THEN COALESCE(EXCLUDED.strain,wearable_daily.strain) ELSE EXCLUDED.strain END,
    recovery_pct = CASE WHEN wearable_daily.data_source=EXCLUDED.data_source THEN COALESCE(EXCLUDED.recovery_pct,wearable_daily.recovery_pct) ELSE EXCLUDED.recovery_pct END,
    sleep_hours = CASE WHEN wearable_daily.data_source=EXCLUDED.data_source THEN COALESCE(EXCLUDED.sleep_hours,wearable_daily.sleep_hours) ELSE EXCLUDED.sleep_hours END,
    data_source = EXCLUDED.data_source
  WHERE CASE EXCLUDED.data_source WHEN 'whoop' THEN 0 WHEN 'manual' THEN 1 ELSE 2 END <= CASE wearable_daily.data_source WHEN 'whoop' THEN 0 WHEN 'manual' THEN 1 ELSE 2 END
  RETURNING 1
),
todos_write AS (
  INSERT INTO todos (todo_id, student_id, source, title, due_date, status, created_at, updated_at)
  SELECT todo_id, student_id, source, title, due_date, status, created_at, updated_at FROM json_populate_recordset(NULL::todos, ($1::json->'tables'->'todos'))
  ON CONFLICT (todo_id) DO UPDATE SET
    student_id = EXCLUDED.student_id,
    source = EXCLUDED.source,
    title = EXCLUDED.title,
    due_date = EXCLUDED.due_date,
    status = EXCLUDED.status,
    created_at = EXCLUDED.created_at,
    updated_at = EXCLUDED.updated_at
  RETURNING 1
),
roadmap_items_write AS (
  INSERT INTO roadmap_items (item_id, student_id, roadmap, level, title, created_at, due_date, done_at, source)
  SELECT item_id, student_id, roadmap, level, title, created_at, due_date, done_at, source FROM json_populate_recordset(NULL::roadmap_items, ($1::json->'tables'->'roadmap_items'))
  ON CONFLICT (item_id) DO UPDATE SET
    student_id = EXCLUDED.student_id,
    roadmap = EXCLUDED.roadmap,
    level = EXCLUDED.level,
    title = EXCLUDED.title,
    created_at = roadmap_items.created_at,
    due_date = EXCLUDED.due_date,
    done_at = CASE WHEN EXCLUDED.done_at IS NULL THEN NULL ELSE COALESCE(roadmap_items.done_at, EXCLUDED.done_at) END,
    source = EXCLUDED.source
  RETURNING 1
),
chapter_progress_write AS (
  INSERT INTO chapter_progress (student_id, chapter_id, subject, quarter, planned_month, stage_reached, updated_at)
  SELECT student_id, chapter_id, subject, quarter, planned_month, stage_reached, updated_at FROM json_populate_recordset(NULL::chapter_progress, ($1::json->'tables'->'chapter_progress'))
  ON CONFLICT (student_id, chapter_id) DO UPDATE SET
    subject = EXCLUDED.subject,
    quarter = EXCLUDED.quarter,
    planned_month = EXCLUDED.planned_month,
    stage_reached = EXCLUDED.stage_reached,
    updated_at = CASE WHEN chapter_progress.stage_reached IS DISTINCT FROM EXCLUDED.stage_reached THEN EXCLUDED.updated_at ELSE chapter_progress.updated_at END
  WHERE EXCLUDED.updated_at >= chapter_progress.updated_at
  RETURNING 1
),
study_hours_write AS (
  INSERT INTO study_hours (student_id, subject, quarter, as_of, estimated_hours, actual_hours)
  SELECT student_id, subject, quarter, as_of, estimated_hours, actual_hours FROM json_populate_recordset(NULL::study_hours, ($1::json->'tables'->'study_hours'))
  ON CONFLICT (student_id, subject, quarter, as_of) DO UPDATE SET
    estimated_hours = EXCLUDED.estimated_hours,
    actual_hours = EXCLUDED.actual_hours
  RETURNING 1
),
advisor_inputs_write AS (
  INSERT INTO advisor_inputs (student_id, month, input_kind, done, source)
  SELECT student_id, month, input_kind, done, source FROM json_populate_recordset(NULL::advisor_inputs, ($1::json->'tables'->'advisor_inputs'))
  ON CONFLICT (student_id, month, input_kind) DO UPDATE SET
    done = EXCLUDED.done,
    source = EXCLUDED.source
  RETURNING 1
),
exam_targets_write AS (
  INSERT INTO exam_targets (student_id, subject, exam_type, target_score, actual_score)
  SELECT student_id, subject, exam_type, target_score, actual_score FROM json_populate_recordset(NULL::exam_targets, ($1::json->'tables'->'exam_targets'))
  ON CONFLICT (student_id, subject, exam_type) DO UPDATE SET
    target_score = EXCLUDED.target_score,
    actual_score = EXCLUDED.actual_score
  RETURNING 1
),
syllabus_daily_write AS (
  INSERT INTO syllabus_daily (student_id, day, chapters_completed, total_chapters)
  SELECT student_id, day, chapters_completed, total_chapters FROM json_populate_recordset(NULL::syllabus_daily, ($1::json->'tables'->'syllabus_daily'))
  ON CONFLICT (student_id, day) DO UPDATE SET
    chapters_completed = EXCLUDED.chapters_completed,
    total_chapters = EXCLUDED.total_chapters
  RETURNING 1
)
SELECT (SELECT count(*)::int FROM staff_write) AS staff, (SELECT count(*)::int FROM students_write) AS students, (SELECT count(*)::int FROM events_write) AS events, (SELECT count(*)::int FROM event_attendance_write) AS event_attendance, (SELECT count(*)::int FROM quiz_attempts_write) AS quiz_attempts, (SELECT count(*)::int FROM feedback_write) AS feedback, (SELECT count(*)::int FROM focus_sessions_write) AS focus_sessions, (SELECT count(*)::int FROM wearable_daily_write) AS wearable_daily, (SELECT count(*)::int FROM todos_write) AS todos, (SELECT count(*)::int FROM roadmap_items_write) AS roadmap_items, (SELECT count(*)::int FROM chapter_progress_write) AS chapter_progress, (SELECT count(*)::int FROM study_hours_write) AS study_hours, (SELECT count(*)::int FROM advisor_inputs_write) AS advisor_inputs, (SELECT count(*)::int FROM exam_targets_write) AS exam_targets, (SELECT count(*)::int FROM syllabus_daily_write) AS syllabus_daily;
