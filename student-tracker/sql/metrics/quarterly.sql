-- Quarterly metrics (DuckDB) that need more than the shared event queries. Period = $start..$end inclusive; pass a quarter.
-- Definitions: student-tracker/README.md#kpi-catalogue (Quarterly). Tags like [A26] point to README.md#assumption-reference-index.
-- Every query documents: definition, grain, source tables, edge cases. A zero denominator gives NULL, never 0.
-- Held, attendance and rating KPIs for podcast, parent workshop, trip and social work are in events.sql; theme milestones are in
-- roadmaps.sql (roadmap = social_work or entrepreneurship).

-- name: competition_outcomes
-- Definition (Conducted, Performed): students assigned a competition in the period / active students; of those, students who entered
--   (attended) and the stage they reached [A23].
-- Grain: one row (cohort). Source: events, event_attendance, students.
-- Edge cases: a competition not yet held has attended = NULL, so its students are assigned but neither entered nor not entered. A student in
--   two competitions counts once for assigned and once for each entry. outcome counts only entrants and is NULL until staff record it.
WITH c AS (
    SELECT e.status, a.student_id, a.attended, a.outcome
    FROM events e JOIN event_attendance a USING (event_id)
    WHERE e.kind = 'competition' AND e.status <> 'cancelled' AND e.planned_for::DATE BETWEEN $start AND $end
),
n AS (SELECT count(*) AS students FROM students WHERE is_active(program_start_date, left_on, $end::DATE))
SELECT (SELECT students FROM n) AS active_students,
       count(DISTINCT student_id) AS assigned_students,
       count(DISTINCT student_id)::DOUBLE / nullif((SELECT students FROM n), 0) AS assigned_rate,
       count(*) FILTER (WHERE attended) AS entries,
       count(*) FILTER (WHERE outcome = 'shortlisted') AS shortlisted,
       count(*) FILTER (WHERE outcome = 'placed') AS placed,
       count(*) FILTER (WHERE attended)::DOUBLE / nullif(count(*) FILTER (WHERE attended IS NOT NULL), 0) AS entered_rate
FROM c;

-- name: social_work_groups
-- Definition (Conducted, Performed): groups formed / groups expected (active students / $events_per_month_pod_group_size, rounded up),
--   activities held / scheduled, and attendance (attended / invited) across held activities. Alcovia forms the groups and organises the
--   activities [A26].
-- Grain: one row (cohort). Source: events, event_attendance, students.
-- Edge cases: group size comes from the invited rows, so a short group shows in min_group_size. Future activities are counted in
--   still_planned only. NULL rates on a zero denominator.
WITH sw AS (SELECT event_id, group_id, status FROM events WHERE kind = 'social_work' AND planned_for::DATE BETWEEN $start AND $end),
sizes AS (SELECT sw.group_id, count(DISTINCT a.student_id) AS size FROM sw JOIN event_attendance a USING (event_id) WHERE a.invited GROUP BY sw.group_id),
att AS (
    SELECT count(*) FILTER (WHERE a.invited) AS invited, count(*) FILTER (WHERE a.attended) AS attended
    FROM sw JOIN event_attendance a USING (event_id) WHERE sw.status = 'held'
),
n AS (SELECT count(*) AS students FROM students WHERE is_active(program_start_date, left_on, $end::DATE))
SELECT (SELECT count(*) FROM sizes) AS groups_formed,
       ceil((SELECT students FROM n)::DOUBLE / $events_per_month_pod_group_size) AS groups_expected,
       (SELECT count(*) FROM sizes)::DOUBLE / nullif(ceil((SELECT students FROM n)::DOUBLE / $events_per_month_pod_group_size), 0) AS groups_formed_rate,
       (SELECT min(size) FROM sizes) AS min_group_size, (SELECT max(size) FROM sizes) AS max_group_size,
       count(*) FILTER (WHERE status = 'held') AS activities_held,
       count(*) FILTER (WHERE status IN ('held', 'cancelled')) AS activities_scheduled,
       count(*) FILTER (WHERE status = 'planned') AS still_planned,
       count(*) FILTER (WHERE status = 'held')::DOUBLE / nullif(count(*) FILTER (WHERE status IN ('held', 'cancelled')), 0) AS held_rate,
       (SELECT invited FROM att) AS invited, (SELECT attended FROM att) AS attended,
       (SELECT attended FROM att)::DOUBLE / nullif((SELECT invited FROM att), 0) AS attended_rate
FROM sw;

-- name: entrepreneurship_rating
-- Definition (Liked, entrepreneurship theme [A21][A61]): the average of the one-tap rating (1-5) students are sent when a theme month ends, and who answered.
--   The app has no form for this theme, so the rating is proposed: n8n sends it and writes feedback kind entrepreneurship.
-- Grain: one row (cohort). Source: feedback, students.
-- Edge cases: only active students count. The average is NULL when nobody has answered, which the dashboard reads as no data, not a failure.
SELECT count(*) AS responses, count(DISTINCT f.student_id) AS students_responded, avg(f.composite) AS avg_composite
FROM feedback f JOIN students s USING (student_id)
WHERE f.kind = 'entrepreneurship' AND f.submitted_at::DATE BETWEEN $start AND $end AND is_active(s.program_start_date, s.left_on, $end::DATE);

-- name: summer_applications
-- Definition (Performed, summer program closure [A25][A66]): students invited to the application-support sessions who have submitted an application, and how many
--   of those have been accepted (shown as a lagging number). The application result is the outcome noted on the attendance row.
-- Grain: one row (cohort). Source: events, event_attendance.
-- Edge cases: an application is only known for a student who came to a held session, so a student who never came is counted as not submitted. Cancelled sessions
--   are ignored. NULL rate when nobody was invited.
WITH a AS (
    SELECT a.student_id, bool_or(a.outcome IN ('submitted', 'accepted')) AS applied, bool_or(a.outcome = 'accepted') AS accepted
    FROM events e JOIN event_attendance a USING (event_id)
    WHERE e.kind = 'summer_support' AND e.status <> 'cancelled' AND e.planned_for::DATE BETWEEN $start AND $end AND a.invited
    GROUP BY a.student_id
)
SELECT count(*) AS invited_students, count(*) FILTER (WHERE coalesce(applied, false)) AS applied, count(*) FILTER (WHERE coalesce(accepted, false)) AS accepted,
       count(*) FILTER (WHERE coalesce(applied, false))::DOUBLE / nullif(count(*), 0) AS applied_rate
FROM a;
