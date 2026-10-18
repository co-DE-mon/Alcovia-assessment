-- Event metrics (DuckDB) for the monthly and quarterly activities: workshop, pod, mentor call, peer session, branding shoot, podcast,
-- competition, parent workshop, trip, social work. Period = $start..$end inclusive; use a month for monthly KPIs and a quarter for quarterly ones.
-- Definitions: student-tracker/README.md#kpi-catalogue (Monthly, Quarterly). Tags like [A17] point to README.md#assumption-reference-index.
-- Every query documents: definition, grain, source tables, edge cases. A zero denominator gives NULL, never 0.
-- One row per event kind, so the dashboard picks the kinds each cadence needs. Quizzes and the one-to-one session kinds are in daily.sql and weekly.sql.

-- name: event_delivery
-- Definition (Conducted): events held / events scheduled (held + cancelled) in the period, and for workshops, mentor calls, peer sessions and
--   pods, held / the number expected from config events_per_month: workshops per cohort, mentor calls and peer sessions per student
--   (peer sessions are pairs, so half as many events), pods one per group of $events_per_month_pod_group_size students [A17][A18][A35].
-- Grain: one row per event kind present in the period. Source: events, students.
-- Edge cases: events still in the future are counted in still_planned, not as scheduled. Months are fractional (days / 30.4375). Kinds
--   without a cadence in config (branding, podcast, competition, parent workshop, trip, social work) have NULL expected. NULL rates on a
--   zero denominator.
WITH e AS (
    SELECT kind, status FROM events
    WHERE planned_for::DATE BETWEEN $start AND $end
      AND kind IN ('workshop', 'pod', 'mentor_call', 'peer_session', 'branding_shoot', 'podcast', 'competition', 'parent_workshop',
                   'trip', 'social_work', 'entrepreneurship_checkin', 'summer_support')
),
n AS (SELECT count(*) AS students FROM students WHERE is_active(program_start_date, left_on, $end::DATE)),
months AS (SELECT (date_diff('day', $start, $end) + 1) / 30.4375 AS m),
agg AS (
    SELECT kind,
           count(*) FILTER (WHERE status IN ('held', 'cancelled')) AS scheduled,
           count(*) FILTER (WHERE status = 'held') AS held,
           count(*) FILTER (WHERE status = 'cancelled') AS cancelled,
           count(*) FILTER (WHERE status = 'planned') AS still_planned
    FROM e GROUP BY kind
)
SELECT kind, scheduled, held, cancelled, still_planned,
       held::DOUBLE / nullif(scheduled, 0) AS held_rate,
       CASE kind WHEN 'workshop' THEN $events_per_month_workshop * (SELECT m FROM months)
                 WHEN 'mentor_call' THEN $events_per_month_mentor_call * (SELECT students FROM n) * (SELECT m FROM months)
                 WHEN 'peer_session' THEN $events_per_month_peer_session * (SELECT students FROM n) / 2.0 * (SELECT m FROM months)
                 WHEN 'pod' THEN ceil((SELECT students FROM n)::DOUBLE / $events_per_month_pod_group_size) * (SELECT m FROM months) END AS expected,
       held::DOUBLE / nullif(CASE kind WHEN 'workshop' THEN $events_per_month_workshop * (SELECT m FROM months)
                 WHEN 'mentor_call' THEN $events_per_month_mentor_call * (SELECT students FROM n) * (SELECT m FROM months)
                 WHEN 'peer_session' THEN $events_per_month_peer_session * (SELECT students FROM n) / 2.0 * (SELECT m FROM months)
                 WHEN 'pod' THEN ceil((SELECT students FROM n)::DOUBLE / $events_per_month_pod_group_size) * (SELECT m FROM months) END, 0) AS delivered_vs_expected
FROM agg
ORDER BY kind;

-- name: event_attendance_rates
-- Definition (Performed): students who attended / students invited, over held events in the period.
-- Grain: one row per event kind. Source: events, event_attendance.
-- Edge cases: only held events count (attendance is unknown before then). Invitees who were not active are not filtered, because
--   an invitation is a record of who the event was for. NULL rate when nobody was invited.
SELECT e.kind,
       count(DISTINCT e.event_id) AS events_held,
       count(*) FILTER (WHERE a.invited) AS invited,
       count(*) FILTER (WHERE a.attended) AS attended,
       count(*) FILTER (WHERE a.invited AND NOT a.attended) AS not_attended,
       count(*) FILTER (WHERE a.attended)::DOUBLE / nullif(count(*) FILTER (WHERE a.invited), 0) AS attended_rate
FROM events e JOIN event_attendance a USING (event_id)
WHERE e.status = 'held' AND e.planned_for::DATE BETWEEN $start AND $end AND e.kind NOT IN ('quiz')
GROUP BY e.kind
ORDER BY e.kind;

-- name: event_feedback
-- Definition (Liked): the average of the app's feedback form for events held in the period (three star ratings, 1-5, and their composite),
--   the share of attendees who responded, and for workshops the event-level NPS (0-10) [A21].
-- Grain: one row per event kind held in the period. Source: events, event_attendance, feedback.
-- Edge cases: kinds with no feedback form (branding, summer support) show NULL averages. response_rate is NULL when nobody attended.
--   avg_nps averages events, not responses, and is NULL for kinds without an NPS.
WITH ev AS (
    SELECT event_id, kind, nps_score FROM events
    WHERE status = 'held' AND planned_for::DATE BETWEEN $start AND $end AND kind NOT IN ('quiz')
),
att AS (SELECT ev.kind, count(*) FILTER (WHERE a.attended) AS attended FROM ev JOIN event_attendance a USING (event_id) GROUP BY ev.kind),
fb AS (
    SELECT ev.kind, count(*) AS responses, avg(f.composite) AS avg_composite,
           avg(f.q1_rating) AS avg_q1, avg(f.q2_rating) AS avg_q2, avg(f.q3_rating) AS avg_q3
    FROM ev JOIN feedback f USING (event_id) GROUP BY ev.kind
),
nps AS (SELECT kind, avg(nps_score) AS avg_nps, count(nps_score) AS nps_events FROM ev GROUP BY kind)
SELECT nps.kind, att.attended, coalesce(fb.responses, 0) AS responses,
       coalesce(fb.responses, 0)::DOUBLE / nullif(att.attended, 0) AS response_rate,
       fb.avg_composite, fb.avg_q1, fb.avg_q2, fb.avg_q3, nps.avg_nps, nps.nps_events
FROM nps LEFT JOIN att USING (kind) LEFT JOIN fb USING (kind)
ORDER BY nps.kind;

-- name: posted_clips
-- Definition (Conducted, Liked proxy): for branding shoots and podcast episodes held in the period: how many were posted by $end, the
--   average days from shoot to post, and the average views and shares of posted ones. Views and shares stand in for "liked" because no form
--   exists for the audience side [A2][A19].
-- Grain: one row per kind (branding_shoot, podcast). Source: events.
-- Edge cases: a clip not yet posted is in held but not in posted. Averages are NULL when nothing is posted. Views and shares are as of
--   the latest sync, not as of $end.
SELECT kind,
       count(*) AS held,
       count(*) FILTER (WHERE posted_on IS NOT NULL AND posted_on <= $end::DATE) AS posted,
       count(*) FILTER (WHERE posted_on IS NOT NULL AND posted_on <= $end::DATE)::DOUBLE / nullif(count(*), 0) AS posted_rate,
       avg(date_diff('day', planned_for::DATE, posted_on)) FILTER (WHERE posted_on IS NOT NULL AND posted_on <= $end::DATE) AS avg_days_to_post,
       avg(views) FILTER (WHERE posted_on IS NOT NULL AND posted_on <= $end::DATE) AS avg_views,
       avg(shares) FILTER (WHERE posted_on IS NOT NULL AND posted_on <= $end::DATE) AS avg_shares
FROM events
WHERE kind IN ('branding_shoot', 'podcast') AND status = 'held' AND planned_for::DATE BETWEEN $start AND $end
GROUP BY kind
ORDER BY kind;

-- name: clip_reach
-- Definition (Liked proxy, personal branding [A2][A19][A62]): posted clips with at least $branding_view_target views / posted clips. Views stand in for "liked"
--   because no form exists for the audience side. The target is our assumption.
-- Grain: one row per kind (branding_shoot, podcast). Source: events.
-- Edge cases: only clips posted by $end count. Views are as of the latest sync, not as of $end. NULL rate when nothing is posted.
SELECT kind,
       count(*) FILTER (WHERE posted_on IS NOT NULL AND posted_on <= $end::DATE) AS posted,
       count(*) FILTER (WHERE posted_on IS NOT NULL AND posted_on <= $end::DATE AND views >= $branding_view_target) AS reached,
       count(*) FILTER (WHERE posted_on IS NOT NULL AND posted_on <= $end::DATE AND views >= $branding_view_target)::DOUBLE
           / nullif(count(*) FILTER (WHERE posted_on IS NOT NULL AND posted_on <= $end::DATE), 0) AS reach_rate,
       $branding_view_target AS view_target
FROM events
WHERE kind IN ('branding_shoot', 'podcast') AND status = 'held' AND planned_for::DATE BETWEEN $start AND $end
GROUP BY kind
ORDER BY kind;
