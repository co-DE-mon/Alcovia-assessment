-- Campaign performance metrics (DuckDB). Period = $start..$end inclusive.
-- CTR = clicks / impressions. Frequency = average impressions per person reached, as Meta reports it (not additive across days).
-- Every query documents: definition, grain, source tables, edge cases. A zero denominator gives NULL, never 0.

-- name: campaign_summary
-- Definition: per campaign, spend, impressions, clicks and CTR in the period, for workshop and program campaigns alike.
-- Grain: one row per campaign with ad activity in the period. Source: campaigns, ad_sets, ads, ad_daily.
-- Edge cases: a campaign with no ad rows in the period has no row; zero impressions gives a NULL CTR.
SELECT c.campaign_id, c.name, c.kind, sum(d.spend)::DOUBLE AS spend, sum(d.impressions)::BIGINT AS impressions, sum(d.clicks)::BIGINT AS clicks,
       sum(d.clicks) * 1.0 / nullif(sum(d.impressions), 0) AS ctr
FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets s USING (ad_set_id) JOIN campaigns c USING (campaign_id)
WHERE d.day BETWEEN $start::DATE AND $end::DATE
GROUP BY c.campaign_id, c.name, c.kind ORDER BY c.campaign_id

-- name: campaign_ads
-- Definition: the ads behind one row of campaign_summary ($campaign_id): spend, impressions, clicks and CTR per ad in the period, biggest spend first.
-- Grain: one row per ad with ad activity in the period. Source: ad_daily, ads, ad_sets.
-- Edge cases: the rows add up to that campaign's campaign_summary row; zero impressions gives a NULL CTR; an unknown campaign gives no rows.
SELECT s.ad_set_id, a.ad_id, a.asset_name, sum(d.spend)::DOUBLE AS spend, sum(d.impressions)::BIGINT AS impressions, sum(d.clicks)::BIGINT AS clicks,
       sum(d.clicks) * 1.0 / nullif(sum(d.impressions), 0) AS ctr
FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets s USING (ad_set_id)
WHERE s.campaign_id = $campaign_id AND d.day BETWEEN $start::DATE AND $end::DATE
GROUP BY s.ad_set_id, a.ad_id, a.asset_name ORDER BY spend DESC, a.ad_id

-- name: ad_daily_ctr
-- Definition: one ad's ($ad_id) spend, impressions, clicks and CTR for each day of the period.
-- Grain: one row per day the ad has activity. Source: ad_daily.
-- Edge cases: zero impressions gives a NULL CTR; an unknown ad gives no rows; the rows add up to the ad's campaign_ads row.
SELECT day, spend::DOUBLE AS spend, impressions, clicks, clicks * 1.0 / nullif(impressions, 0) AS ctr
FROM ad_daily WHERE ad_id = $ad_id AND day BETWEEN $start::DATE AND $end::DATE ORDER BY day

-- name: ad_leads
-- Definition: the leads created in the period that came from one ad ($ad_id), with whether each had qualified or signed by $end.
-- Grain: one row per lead, newest first. Source: leads, lead_stages.
-- Edge cases: stages reached after $end are not counted; an ad with no leads, or an unknown ad, gives no rows. Names are generated dummy values.
SELECT l.lead_id, l.student_name, l.city, l.created_at,
       coalesce(bool_or(s.stage = 'qualified'), false) AS qualified, coalesce(bool_or(s.stage = 'signed'), false) AS signed
FROM leads l LEFT JOIN lead_stages s ON s.lead_id = l.lead_id AND s.reached_at::DATE <= $end::DATE
WHERE l.ad_id = $ad_id AND l.created_at::DATE BETWEEN $start::DATE AND $end::DATE
GROUP BY l.lead_id, l.student_name, l.city, l.created_at ORDER BY l.created_at DESC, l.lead_id DESC

-- name: campaign_day_ads
-- Definition: the ads behind one row of ctr_daily ($campaign_id on $day): spend, impressions, clicks and CTR per ad that day, biggest spend first.
-- Grain: one row per ad with activity that day. Source: ad_daily, ads, ad_sets.
-- Edge cases: the rows add up to that ctr_daily row; zero impressions gives a NULL CTR; a day with no activity or an unknown campaign gives no rows.
SELECT s.ad_set_id, a.ad_id, a.asset_name, d.spend::DOUBLE AS spend, d.impressions::BIGINT AS impressions, d.clicks::BIGINT AS clicks,
       d.clicks * 1.0 / nullif(d.impressions, 0) AS ctr
FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets s USING (ad_set_id)
WHERE s.campaign_id = $campaign_id AND d.day = $day::DATE
ORDER BY d.spend DESC, a.ad_id

-- name: adset_ads
-- Definition: the ads inside one ad set ($ad_set_id): spend, impressions, clicks and CTR per ad in the period, biggest spend first.
-- Grain: one row per ad with activity in the period. Source: ad_daily, ads.
-- Edge cases: zero impressions gives a NULL CTR; an unknown ad set gives no rows.
SELECT a.ad_set_id, a.ad_id, a.asset_name, sum(d.spend)::DOUBLE AS spend, sum(d.impressions)::BIGINT AS impressions, sum(d.clicks)::BIGINT AS clicks,
       sum(d.clicks) * 1.0 / nullif(sum(d.impressions), 0) AS ctr
FROM ad_daily d JOIN ads a USING (ad_id)
WHERE a.ad_set_id = $ad_set_id AND d.day BETWEEN $start::DATE AND $end::DATE
GROUP BY a.ad_set_id, a.ad_id, a.asset_name ORDER BY spend DESC, a.ad_id

-- name: adset_daily_frequency
-- Definition: one ad set's ($ad_set_id) reach and frequency for each day of the period, behind the frequency in adset_frequency.
-- Grain: one row per day with data. Source: ad_set_daily.
-- Edge cases: frequency is a per-day figure as Meta reports it, never summed; an unknown ad set gives no rows.
SELECT day, reach, frequency FROM ad_set_daily WHERE ad_set_id = $ad_set_id AND day BETWEEN $start::DATE AND $end::DATE ORDER BY day

-- name: asset_ctr
-- Definition: per ad (asset), impressions, clicks and CTR in the period.
-- Grain: one row per ad with ad activity in the period. Source: ad_daily, ads, ad_sets.
-- Edge cases: an ad with zero impressions has a NULL CTR (it is unmeasured, not the worst).
SELECT s.campaign_id, s.ad_set_id, a.ad_id, a.asset_name, sum(d.impressions)::BIGINT AS impressions, sum(d.clicks)::BIGINT AS clicks,
       sum(d.clicks) * 1.0 / nullif(sum(d.impressions), 0) AS ctr
FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets s USING (ad_set_id)
WHERE d.day BETWEEN $start::DATE AND $end::DATE GROUP BY s.campaign_id, s.ad_set_id, a.ad_id, a.asset_name ORDER BY s.campaign_id, a.ad_id

-- name: adset_frequency
-- Definition: per ad set, frequency on the last day with data in the period, the highest frequency in the period, and whether it needs a change
--   (frequency at or above campaign.frequency_change_at in config.yaml; the brief says 3+).
-- Grain: one row per ad set with data in the period. Source: ad_set_daily, ad_sets.
-- Edge cases: frequency cannot be summed across days, so the last day stands for "now" and the flag depends on the period's last day only
--   (peak_frequency is the part that follows the whole period); an ad set with no rows in the period has no row.
SELECT s.campaign_id, f.ad_set_id, arg_max(f.frequency, f.day) AS frequency, max(f.frequency) AS peak_frequency,
       arg_max(f.frequency, f.day) >= $campaign_frequency_change_at AS needs_change
FROM ad_set_daily f JOIN ad_sets s USING (ad_set_id)
WHERE f.day BETWEEN $start::DATE AND $end::DATE
GROUP BY s.campaign_id, f.ad_set_id ORDER BY f.ad_set_id

-- name: landing_health
-- Definition: per campaign landing page, sessions, drop-off rate (bounces / sessions) and session-weighted average load time in seconds.
-- Grain: one row per campaign with sessions in the period. Source: landing_page_daily.
-- Edge cases: zero sessions gives NULL rates; load time is weighted by sessions so a quiet slow day does not dominate.
SELECT campaign_id, sum(sessions)::BIGINT AS sessions, sum(bounces)::BIGINT AS bounces, sum(bounces) * 1.0 / nullif(sum(sessions), 0) AS drop_off_rate,
       sum(avg_load_seconds * sessions) / nullif(sum(sessions), 0) AS avg_load_seconds
FROM landing_page_daily WHERE day BETWEEN $start::DATE AND $end::DATE
GROUP BY campaign_id ORDER BY campaign_id

-- name: ctr_daily
-- Definition: CTR per campaign per day, for the trend chart.
-- Grain: one row per campaign per day with ad activity. Source: ad_daily, ads, ad_sets.
-- Edge cases: zero impressions gives a NULL CTR (a gap in the line, not a drop to 0).
SELECT s.campaign_id, d.day, sum(d.spend)::DOUBLE AS spend, sum(d.clicks) * 1.0 / nullif(sum(d.impressions), 0) AS ctr
FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets s USING (ad_set_id)
WHERE d.day BETWEEN $start::DATE AND $end::DATE
GROUP BY s.campaign_id, d.day ORDER BY s.campaign_id, d.day
