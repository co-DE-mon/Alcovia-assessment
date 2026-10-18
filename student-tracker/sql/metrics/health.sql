-- Data-health metrics (DuckDB): is the pipeline delivering? Reads ingest_log, which n8n writes once per run per source.
-- $now is the end of the as-of day (metrics.params), never the wall clock. Every query documents: definition, grain, source tables, edge cases.

-- name: source_freshness
-- Definition: per source, the last fully successful run, hours since it, the last run's status and error, and the failed and partial runs in the
--   7 days before $now. A source is stale when it has no successful run, or none within $data_freshness_stale_after_hours hours.
-- Grain: one row per source (app_api, clickup, whoop), including sources that have never run. Source: ingest_log.
-- Edge cases: only a run with status ok resets the clock; a partial run does not, because some rows were not loaded. Runs after $now are
--   ignored. A source with no runs at all has NULL times and is stale. hours_since_ok counts whole hours.
WITH sources AS (SELECT unnest(['app_api', 'clickup', 'whoop']) AS source),
runs AS (SELECT * FROM ingest_log WHERE started_at <= $now::TIMESTAMP),
ok AS (SELECT source, max(coalesce(finished_at, started_at)) AS last_ok_at FROM runs WHERE status = 'ok' GROUP BY source),
last AS (
    SELECT source, max(started_at) AS last_run_at, arg_max(status, started_at) AS last_status, arg_max_null(error, started_at) AS last_error
    FROM runs GROUP BY source
),
recent AS (
    SELECT source, count(*) FILTER (WHERE status = 'failed') AS failed_7d, count(*) FILTER (WHERE status = 'partial') AS partial_7d
    FROM runs WHERE started_at > $now::TIMESTAMP - INTERVAL 7 DAY GROUP BY source
)
SELECT s.source, ok.last_ok_at, date_diff('hour', ok.last_ok_at, $now::TIMESTAMP) AS hours_since_ok,
       l.last_run_at, l.last_status, l.last_error,
       coalesce(r.failed_7d, 0) AS failed_7d, coalesce(r.partial_7d, 0) AS partial_7d,
       ok.last_ok_at IS NULL OR date_diff('hour', ok.last_ok_at, $now::TIMESTAMP) > $data_freshness_stale_after_hours AS stale
FROM sources s LEFT JOIN ok USING (source) LEFT JOIN last l USING (source) LEFT JOIN recent r USING (source)
ORDER BY s.source;

-- name: recent_runs
-- Definition: every pipeline run in the 14 days up to $now, newest first, for the data-health page.
-- Grain: one row per run. Source: ingest_log.
-- Edge cases: runs after $now are ignored. error is NULL for a clean run.
SELECT run_id, source, started_at, finished_at, status, rows_upserted, error
FROM ingest_log
WHERE started_at <= $now::TIMESTAMP AND started_at > $now::TIMESTAMP - INTERVAL 14 DAY
ORDER BY started_at DESC, source;

-- name: whoop_reconnect
-- Definition: the active students whose Whoop needs attention at $end: they disconnected it, or no Whoop reading has arrived for more than
--   $data_freshness_wearable_silent_days days. This is the list behind a "N students need to reconnect Whoop" note in the run log.
-- Grain: one row per affected student. Source: students, wearable_daily.
-- Edge cases: a student who connected a Whoop and has never had a reading is listed (days without data is NULL). A student with no Whoop is never listed.
--   Manual sleep rows are ignored, because they say nothing about the device.
WITH last AS (
    SELECT student_id, max(day) AS last_reading FROM wearable_daily WHERE data_source = 'whoop' AND day <= $end::DATE GROUP BY student_id
)
SELECT s.name AS "Student", s.student_id AS "ID", s.advisor_id AS "Advisor", s.wearable_connected_on AS "Connected on",
       s.wearable_disconnected_on AS "Disconnected on", l.last_reading AS "Last reading", date_diff('day', l.last_reading, $end::DATE) AS "Days without data",
       CASE WHEN s.wearable_disconnected_on <= $end::DATE THEN 'Disconnected the Whoop' ELSE 'Stopped syncing' END AS "Why"
FROM students s LEFT JOIN last l USING (student_id)
WHERE s.wearable = 'whoop' AND s.wearable_connected_on <= $end::DATE AND is_active(s.program_start_date, s.left_on, $end::DATE)
  AND (s.wearable_disconnected_on <= $end::DATE OR l.last_reading IS NULL OR date_diff('day', l.last_reading, $end::DATE) > $data_freshness_wearable_silent_days)
ORDER BY "Days without data" DESC NULLS FIRST, s.name;

-- name: history_start
-- Definition: the first day the database has an event planned for. A comparison window that begins before it would read missing data as a drop.
-- Grain: one row. Source: events. Takes no parameters.
-- Edge cases: NULL when there are no events at all.
SELECT min(planned_for)::DATE AS first_day FROM events;
