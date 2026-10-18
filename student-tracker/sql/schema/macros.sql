-- Shared definitions, loaded right after student.sql. Every metric uses these, so "active student" and "days in period" mean one thing.

-- A student is active on a day from program_start_date up to, but not including, left_on.
CREATE OR REPLACE MACRO is_active(start_date, left_date, day) AS
    start_date <= day AND (left_date IS NULL OR left_date > day);

-- One row per calendar day, first_day..last_day inclusive.
CREATE OR REPLACE MACRO period_days(first_day, last_day) AS TABLE
    SELECT unnest(generate_series(first_day, last_day, INTERVAL 1 DAY))::DATE AS day;
