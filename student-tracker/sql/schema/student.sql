-- Student tracker schema (DuckDB). Table plan: student-tracker/README.md#source-and-schema-reference. KPI definitions: student-tracker/README.md#kpi-catalogue
-- All timestamps are IST: the API returns UTC, and ingest converts to IST before storing timestamps or taking dates [student-tracker/README.md#source-and-schema-reference].
-- Dummy data only; every seeded id starts DEMO-. Missing data is NULL, never zero.
-- Every ingested table is keyed on the source system's id, so re-running an n8n import upserts instead of duplicating.
-- Thresholds and targets live in student-tracker/config.yaml, not here.

-- Advisors own the academic and personal roadmaps; career counsellors own the career roadmap [A29].
CREATE TABLE IF NOT EXISTS staff (
    staff_id  VARCHAR PRIMARY KEY,
    name      VARCHAR NOT NULL,
    role      VARCHAR NOT NULL CHECK (role IN ('advisor', 'career_counsellor'))
);

-- Active on a day = program_start_date <= day AND (left_on IS NULL OR left_on > day). Every "per active student" KPI uses this.
CREATE TABLE IF NOT EXISTS students (
    student_id                VARCHAR PRIMARY KEY,   -- app user id
    name                      VARCHAR NOT NULL,
    grade                     INTEGER NOT NULL CHECK (grade BETWEEN 8 AND 12),
    board                     VARCHAR,
    advisor_id                VARCHAR NOT NULL,
    career_counsellor_id      VARCHAR,               -- NULL when none assigned (as on the test account)
    program_start_date        DATE NOT NULL,
    left_on                   DATE,
    wearable                  VARCHAR NOT NULL CHECK (wearable IN ('none', 'whoop', 'apple', 'samsung', 'garmin')),
    wearable_connected_on     DATE,                  -- liked proxy: still connected after N days [A2]
    wearable_disconnected_on  DATE,
    calendar_connected_on     DATE,                  -- liked proxy for the timetable [A2]
    calendar_disconnected_on  DATE,
    weekday_study_hours       INTEGER,               -- the student's study-hour plan from /academics/time-budget; NULL until they set it [A54]
    weekend_study_hours       INTEGER
);

-- The app's session types map here: Academic, Career, Mentor, Workshop, PodSession and Quiz directly; Mindset and DeepWork have their own kinds [A49].
-- Anything Alcovia schedules: the 8pm quiz, workshops, pods, calls, sessions, shoots, competitions, trips, themes.
-- planned_for is the scheduled time. Attendance is in event_attendance. A quiz entry window is planned_for + config quiz.entry_window_minutes.
CREATE TABLE IF NOT EXISTS events (
    event_id        VARCHAR PRIMARY KEY,          -- ClickUp task id or app id
    kind            VARCHAR NOT NULL CHECK (kind IN (
                        'quiz', 'workshop', 'pod', 'mentor_call', 'peer_session',
                        'academic_session', 'career_session', 'personal_session', 'mindset_session', 'deep_work_session',
                        'branding_shoot', 'podcast', 'competition', 'parent_workshop', 'trip',
                        'social_work', 'entrepreneurship_checkin', 'summer_support')),
    title           VARCHAR,                      -- quiz topic, workshop profession, pod theme
    planned_for     TIMESTAMP NOT NULL,
    status          VARCHAR NOT NULL CHECK (status IN ('planned', 'held', 'cancelled')),
    group_id        VARCHAR,                      -- pod, peer pair, social work group
    owner_staff_id  VARCHAR,
    posted_on       DATE,                         -- branding clip or podcast episode launch date
    views           INTEGER,                      -- clip or episode views, shares: liked proxy where no form exists [A19]
    shares          INTEGER,
    source          VARCHAR NOT NULL CHECK (source IN ('clickup', 'app_api', 'manual')),
    nps_score       DOUBLE                        -- event-level workshop NPS, 0-10 (the app returns workshopNpsScore on workshop sessions)
);

-- One row per invited student. attended is NULL until the event is held. no-show = invited AND held AND NOT attended.
CREATE TABLE IF NOT EXISTS event_attendance (
    event_id    VARCHAR NOT NULL,
    student_id  VARCHAR NOT NULL,
    invited     BOOLEAN NOT NULL,
    attended    BOOLEAN,
    outcome     VARCHAR,                          -- competition stage reached, summer application result [A23]
    PRIMARY KEY (event_id, student_id)
);

-- One row per student who started a quiz. A student who never started has no row here, only an invited row in event_attendance.
CREATE TABLE IF NOT EXISTS quiz_attempts (
    event_id         VARCHAR NOT NULL,
    student_id       VARCHAR NOT NULL,
    started_at       TIMESTAMP NOT NULL,
    completed_at     TIMESTAMP,
    score            INTEGER,
    total_questions  INTEGER,
    PRIMARY KEY (event_id, student_id)
);

-- The app's own feedback forms (3 star ratings 1-5, optional comment). kinds social_work has no form today: proposed one-tap, q1 only [A21].
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id   VARCHAR PRIMARY KEY,
    student_id    VARCHAR NOT NULL,
    event_id      VARCHAR,                        -- NULL for the monthly roadmap check-in
    kind          VARCHAR NOT NULL CHECK (kind IN (
                      'session', 'workshop', 'pod', 'mentor', 'mindset', 'deep_work', 'roadmap',
                      'podcast_shoot', 'podcast_post', 'competition', 'social_work', 'entrepreneurship', 'summer_support')),
    q1_rating     INTEGER CHECK (q1_rating BETWEEN 1 AND 5),
    q2_rating     INTEGER CHECK (q2_rating BETWEEN 1 AND 5),
    q3_rating     INTEGER CHECK (q3_rating BETWEEN 1 AND 5),
    composite     DOUBLE,
    has_comment   BOOLEAN NOT NULL,
    submitted_at  TIMESTAMP NOT NULL
);

-- The app API returns status capitalised ('Failed'); the ingest step lowercases it to match the checks below [A43].
CREATE TABLE IF NOT EXISTS focus_sessions (
    session_id       VARCHAR PRIMARY KEY,
    student_id       VARCHAR NOT NULL,
    started_at       TIMESTAMP NOT NULL,
    planned_minutes  INTEGER,                      -- no source in the focus responses, so NULL in production and no metric reads it [A46]
    actual_minutes   DOUBLE,
    status           VARCHAR NOT NULL CHECK (status IN ('completed', 'failed')),
    fail_reason      VARCHAR CHECK (fail_reason IN ('give_up', 'app_switch', 'abandoned', 'interrupted'))
);

-- No row means no data that day (NULL), never zero [A8]. Manual rows carry sleep_hours only: strain and recovery are not measured.
CREATE TABLE IF NOT EXISTS wearable_daily (
    student_id    VARCHAR NOT NULL,
    day           DATE NOT NULL,
    strain        DOUBLE,
    recovery_pct  DOUBLE,
    sleep_hours   DOUBLE,
    data_source   VARCHAR NOT NULL CHECK (data_source IN ('whoop', 'apple', 'samsung', 'garmin', 'manual')),
    PRIMARY KEY (student_id, day)
);

-- App to-dos and daily goals. The API has no completion timestamp, so updated_at stands in for it [A3].
CREATE TABLE IF NOT EXISTS todos (
    todo_id     VARCHAR PRIMARY KEY,
    student_id  VARCHAR NOT NULL,
    source      VARCHAR NOT NULL CHECK (source IN ('manual', 'admin_assigned', 'coaching_report', 'session_action', 'n8n')),
    title       VARCHAR NOT NULL,
    due_date    DATE NOT NULL,
    status      VARCHAR NOT NULL CHECK (status IN ('pending', 'in_progress', 'done', 'missed')),
    created_at  TIMESTAMP NOT NULL,
    updated_at  TIMESTAMP NOT NULL
);

-- A roadmap item is done when done_at is set. social_work and entrepreneurship hold the theme milestones.
CREATE TABLE IF NOT EXISTS roadmap_items (
    item_id     VARCHAR PRIMARY KEY,
    student_id  VARCHAR NOT NULL,
    roadmap     VARCHAR NOT NULL CHECK (roadmap IN ('career', 'personal', 'academic', 'social_work', 'entrepreneurship')),
    level       VARCHAR NOT NULL CHECK (level IN ('annual', 'quarterly', 'monthly')),
    title       VARCHAR NOT NULL,
    created_at  TIMESTAMP NOT NULL,
    due_date    DATE,                             -- NULL for a goal the app gave no due date: it is never due or late [A58]
    done_at     TIMESTAMP,
    source      VARCHAR NOT NULL CHECK (source IN ('clickup', 'app_api', 'manual'))
);

-- stage_reached counts the brief's rigour stages passed: 0 none, 1 read, 2 notes, 3 practice above 70%, 4 timed past paper, 5 exam accuracy above 80% [A16].
CREATE TABLE IF NOT EXISTS chapter_progress (
    student_id     VARCHAR NOT NULL,
    chapter_id     VARCHAR NOT NULL,
    subject        VARCHAR NOT NULL,
    quarter        VARCHAR NOT NULL,
    planned_month  DATE NOT NULL,                 -- first day of the month the chapter is planned for
    stage_reached  INTEGER NOT NULL CHECK (stage_reached BETWEEN 0 AND 5),
    updated_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (student_id, chapter_id)
);

-- The API returns only the current estimated and actual hours, so n8n snapshots them. actual_hours = 0 gives a NULL accuracy, not 100%.
CREATE TABLE IF NOT EXISTS study_hours (
    student_id       VARCHAR NOT NULL,
    subject          VARCHAR NOT NULL,
    quarter          VARCHAR NOT NULL,
    as_of            DATE NOT NULL,
    estimated_hours  DOUBLE NOT NULL,
    actual_hours     DOUBLE NOT NULL,
    PRIMARY KEY (student_id, subject, quarter, as_of)
);

-- Staff duties from the brief, one done / not done row per student per month. input_kind values come from config.yaml advisor_input_kinds [A31].
CREATE TABLE IF NOT EXISTS advisor_inputs (
    student_id  VARCHAR NOT NULL,
    month       DATE NOT NULL,                    -- first day of the month
    input_kind  VARCHAR NOT NULL,
    done        BOOLEAN NOT NULL,
    source      VARCHAR NOT NULL CHECK (source IN ('clickup', 'manual')),
    PRIMARY KEY (student_id, month, input_kind)
);

CREATE TABLE IF NOT EXISTS exam_targets (
    student_id    VARCHAR NOT NULL,
    subject       VARCHAR NOT NULL,
    exam_type     VARCHAR NOT NULL CHECK (exam_type IN ('formative', 'unit_test', 'mid_term')),
    target_score  DOUBLE NOT NULL,
    actual_score  DOUBLE,                         -- NULL until the exam is taken
    PRIMARY KEY (student_id, subject, exam_type)
);

-- One row per n8n run per source. Feeds the data-freshness panel and failure alerts.
CREATE TABLE IF NOT EXISTS ingest_log (
    run_id         VARCHAR PRIMARY KEY,
    source         VARCHAR NOT NULL CHECK (source IN ('app_api', 'clickup', 'whoop')),
    started_at     TIMESTAMP NOT NULL,
    finished_at    TIMESTAMP,
    status         VARCHAR NOT NULL CHECK (status IN ('ok', 'partial', 'failed')),
    rows_upserted  INTEGER,
    error          VARCHAR
);

-- Syllabus completion over time, from /academics/my-syllabus-history (one row per student per day, a running total).
CREATE TABLE IF NOT EXISTS syllabus_daily (
    student_id          VARCHAR NOT NULL,
    day                 DATE NOT NULL,
    chapters_completed  INTEGER NOT NULL,
    total_chapters      INTEGER NOT NULL,
    PRIMARY KEY (student_id, day)
);
