-- RCA inputs (DuckDB): the numbers behind each campaign's verdict. Verdict rules live in rca.py and config.yaml (rca); the decision summary is in README.md.
-- Everything is as known on $end: a stage reached, a payment made or an enrolment started after $end is not used, so a past snapshot never changes.
-- Program campaigns use a fixed lookback (rca.lookback_days, 90) ending on $end: "mature" leads were created at least rca.mature_after_days (28) before $end,
--   "recent" leads fewer than 28 days before. Workshops follow the selected period $start..$end.
-- Every query documents: definition, grain, source tables, edge cases. A zero denominator gives NULL, never 0.

-- name: program_inputs
-- Definition: per program campaign, as known on $end, over the lookback window:
--   leads, qualified                  : leads created in the lookback and how many reached 'qualified' by $end
--   mature_*                          : the same for leads created at least 28 days before $end; mature_paid_program / mature_paid_trial count those leads with a paid enrolment
--                                       (an invoice paid by $end), the author's "paid customers"
--   mature_spend, recent_spend        : ad spend on the days those leads were created (mature window), and on the last 28 days (recent window)
--   cpql_mature, cpql_recent          : cost per qualified lead = window spend / qualified leads of that window; cpql_ratio = recent / mature (above 1.30 = worsening)
--   cost_per_paid_program             : mature_spend / mature_paid_program
--   conv_rate                         : mature qualified-lead-to-paid conversion: paid leads / mature qualified leads
--   paid_any                          : leads of any age with a paid enrolment by $end (for the overspend alert)
--   days_running, first_day, spend_to_date : since the first ad day on or before $end
--   landing_drop_off, landing_load    : sessions-weighted over the lookback
-- Grain: one row per program campaign with ad activity on or before $end. Source: campaigns, ad_daily, ads, ad_sets, leads, lead_stages, enrollments, invoices, landing_page_daily.
-- Edge cases: no qualified leads, or no paid program customer, gives NULL cost (never 0); an enrolment whose invoice is paid after $end is not a paid customer on $end.
WITH win AS (SELECT $end::DATE - ($rca_lookback_days::INTEGER - 1) AS first_day, $end::DATE - $rca_mature_after_days::INTEGER AS mature_last,
                    $end::DATE - ($rca_mature_after_days::INTEGER - 1) AS recent_first),
ad AS (
    SELECT s.campaign_id, d.day, d.spend FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets s USING (ad_set_id) WHERE d.day <= $end::DATE
),
run AS (
    SELECT campaign_id, min(day) AS first_day, ($end::DATE - min(day) + 1)::INTEGER AS days_running, sum(spend) AS spend_to_date,
           sum(spend) FILTER (WHERE day BETWEEN (SELECT first_day FROM win) AND (SELECT mature_last FROM win)) AS mature_spend,
           sum(spend) FILTER (WHERE day >= (SELECT recent_first FROM win)) AS recent_spend
    FROM ad GROUP BY campaign_id
),
paid AS (
    SELECT e.lead_id, bool_or(e.kind = 'program') AS program, bool_or(e.kind = 'trial_3m') AS trial
    FROM enrollments e
    WHERE e.lead_id IS NOT NULL AND e.started_on <= $end::DATE AND EXISTS (SELECT 1 FROM invoices i WHERE i.enrollment_id = e.enrollment_id AND i.paid_on <= $end::DATE)
    GROUP BY e.lead_id
),
known AS (
    SELECT l.lead_id, l.campaign_id, l.created_at::DATE AS created, count(st.stage) > 0 AS qualified
    FROM leads l LEFT JOIN lead_stages st ON st.lead_id = l.lead_id AND st.stage = 'qualified' AND st.reached_at::DATE <= $end::DATE
    WHERE l.campaign_id IN (SELECT campaign_id FROM campaigns WHERE kind = 'program') AND l.created_at::DATE BETWEEN (SELECT first_day FROM win) AND $end::DATE
    GROUP BY l.lead_id, l.campaign_id, l.created_at
),
agg AS (
    SELECT k.campaign_id, count(*) AS leads, count(*) FILTER (WHERE k.qualified) AS qualified,
           count(*) FILTER (WHERE k.created <= w.mature_last) AS mature_leads,
           count(*) FILTER (WHERE k.created <= w.mature_last AND k.qualified) AS mature_qualified,
           count(*) FILTER (WHERE k.created <= w.mature_last AND p.program) AS mature_paid_program,
           count(*) FILTER (WHERE k.created <= w.mature_last AND p.trial) AS mature_paid_trial,
           count(*) FILTER (WHERE k.created >= w.recent_first AND k.qualified) AS recent_qualified
    FROM known k CROSS JOIN win w LEFT JOIN paid p USING (lead_id) GROUP BY k.campaign_id
),
ever AS (
    SELECT l.campaign_id, count(*) FILTER (WHERE p.lead_id IS NOT NULL) AS paid_any
    FROM leads l LEFT JOIN paid p USING (lead_id) WHERE l.campaign_id IS NOT NULL AND l.created_at::DATE <= $end::DATE GROUP BY l.campaign_id
),
lp AS (
    SELECT campaign_id, sum(bounces) * 1.0 / nullif(sum(sessions), 0) AS landing_drop_off, sum(avg_load_seconds * sessions) / nullif(sum(sessions), 0) AS landing_load
    FROM landing_page_daily WHERE day BETWEEN (SELECT first_day FROM win) AND $end::DATE GROUP BY campaign_id
)
SELECT c.campaign_id, c.name, run.first_day, run.days_running, run.spend_to_date::DOUBLE AS spend_to_date,
       coalesce(agg.leads, 0)::INTEGER AS leads, coalesce(agg.qualified, 0)::INTEGER AS qualified, coalesce(agg.mature_leads, 0)::INTEGER AS mature_leads,
       coalesce(agg.mature_qualified, 0)::INTEGER AS mature_qualified, coalesce(agg.mature_paid_program, 0)::INTEGER AS mature_paid_program,
       coalesce(agg.mature_paid_trial, 0)::INTEGER AS mature_paid_trial, coalesce(agg.recent_qualified, 0)::INTEGER AS recent_qualified,
       coalesce(run.mature_spend, 0)::DOUBLE AS mature_spend, coalesce(run.recent_spend, 0)::DOUBLE AS recent_spend,
       coalesce(run.mature_spend, 0) / nullif(agg.mature_qualified, 0) AS cpql_mature, coalesce(run.recent_spend, 0) / nullif(agg.recent_qualified, 0) AS cpql_recent,
       (coalesce(run.recent_spend, 0) / nullif(agg.recent_qualified, 0)) / nullif(coalesce(run.mature_spend, 0) / nullif(agg.mature_qualified, 0), 0) AS cpql_ratio,
       coalesce(run.mature_spend, 0) / nullif(agg.mature_paid_program, 0) AS cost_per_paid_program,
       (agg.mature_paid_program + agg.mature_paid_trial) * 1.0 / nullif(agg.mature_qualified, 0) AS conv_rate,
       coalesce(ever.paid_any, 0)::INTEGER AS paid_any, lp.landing_drop_off, lp.landing_load
FROM campaigns c JOIN run USING (campaign_id) LEFT JOIN agg USING (campaign_id) LEFT JOIN ever USING (campaign_id) LEFT JOIN lp USING (campaign_id)
WHERE c.kind = 'program' ORDER BY c.campaign_id

-- name: adset_signals
-- Definition: per ad set, as known on $end: the frequency on the last day with data in the last campaign.trend_window_days (14) days (Meta's average views per person),
--   and the click-through rate of those 14 days against the 14 before, with the clicks and impressions behind both.
--   ctr_change = ctr_recent / ctr_prior - 1 (a fall of 15% reads -0.15).
-- Grain: one row per ad set with ad activity in the last 28 days. Source: ad_daily, ads, ad_sets, ad_set_daily.
-- Edge cases: no impressions (or a zero CTR) in the earlier 14 days gives NULL ctr_change, never a division by zero; no frequency row in the last 14 days gives NULL frequency.
WITH w AS (SELECT $end::DATE AS e, $campaign_trend_window_days::INTEGER AS n),
clicks AS (
    SELECT s.ad_set_id, s.campaign_id,
           sum(d.clicks) FILTER (WHERE d.day > w.e - w.n AND d.day <= w.e) AS clicks_recent, sum(d.impressions) FILTER (WHERE d.day > w.e - w.n AND d.day <= w.e) AS impressions_recent,
           sum(d.clicks) FILTER (WHERE d.day > w.e - 2 * w.n AND d.day <= w.e - w.n) AS clicks_prior, sum(d.impressions) FILTER (WHERE d.day > w.e - 2 * w.n AND d.day <= w.e - w.n) AS impressions_prior
    FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets s USING (ad_set_id) CROSS JOIN w WHERE d.day > w.e - 2 * w.n AND d.day <= w.e GROUP BY s.ad_set_id, s.campaign_id
),
freq AS (
    SELECT f.ad_set_id, arg_max(f.frequency, f.day) AS frequency FROM ad_set_daily f CROSS JOIN w WHERE f.day > w.e - w.n AND f.day <= w.e GROUP BY f.ad_set_id
)
SELECT c.campaign_id, c.ad_set_id, freq.frequency, c.clicks_recent::BIGINT AS clicks_recent, c.impressions_recent::BIGINT AS impressions_recent,
       c.clicks_prior::BIGINT AS clicks_prior, c.impressions_prior::BIGINT AS impressions_prior,
       c.clicks_recent * 1.0 / nullif(c.impressions_recent, 0) AS ctr_recent, c.clicks_prior * 1.0 / nullif(c.impressions_prior, 0) AS ctr_prior,
       (c.clicks_recent * 1.0 / nullif(c.impressions_recent, 0)) / nullif(c.clicks_prior * 1.0 / nullif(c.impressions_prior, 0), 0) - 1 AS ctr_change
FROM clicks c LEFT JOIN freq USING (ad_set_id) ORDER BY c.campaign_id, c.ad_set_id

-- name: ad_signals
-- Definition: per ad, as known on $end, its click-through rate over the lookback (rca.lookback_days), the median CTR of the ads in its campaign,
--   and vs_median = ctr / median - 1 (an ad half as good as the median reads -0.5).
-- Grain: one row per ad with impressions in the lookback. Source: ad_daily, ads, ad_sets.
-- Edge cases: a campaign whose median CTR is 0 or missing gives NULL vs_median (the comparison is unavailable, not infinite); an ad with no impressions has no row.
WITH t AS (
    SELECT s.campaign_id, s.ad_set_id, a.ad_id, a.asset_name, sum(d.clicks)::BIGINT AS clicks, sum(d.impressions)::BIGINT AS impressions,
           sum(d.clicks) * 1.0 / nullif(sum(d.impressions), 0) AS ctr
    FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets s USING (ad_set_id)
    WHERE d.day BETWEEN $end::DATE - ($rca_lookback_days::INTEGER - 1) AND $end::DATE GROUP BY s.campaign_id, s.ad_set_id, a.ad_id, a.asset_name HAVING sum(d.impressions) > 0
)
SELECT campaign_id, ad_set_id, ad_id, asset_name, clicks, impressions, ctr, median(ctr) OVER (PARTITION BY campaign_id) AS median_ctr,
       ctr / nullif(median(ctr) OVER (PARTITION BY campaign_id), 0) - 1 AS vs_median
FROM t ORDER BY campaign_id, ad_id

-- name: workshop_inputs
-- Definition: per workshop campaign over the selected period $start..$end, as known on $end:
--   days_running, spend           : days with ad activity and ad spend in the period
--   qualified                     : leads created in the period that reached 'qualified' by $end
--   paid_seats, revenue           : seats and rupees collected in the period (Razorpay, seats x Rs 3,999); refunds are not modelled, so this is also net revenue
--   cost_per_seat, revenue_ratio  : spend / seats, and revenue / spend (below 1.0 the ads cost more than the seats brought in; delivery costs are not counted)
--   followup_*                    : of the seat buyers in the period whose 60-day follow-up is complete on $end (paid at least rca.followup_days days before $end),
--                                   how many enrolled in the program within that many days after their seat. A separate outcome; it is not part of revenue or the verdict.
--   landing_drop_off, landing_load: sessions-weighted over the period
-- Grain: one row per workshop campaign with ad activity in the period. Source: campaigns, ad_daily, ads, ad_sets, leads, lead_stages, workshops, workshop_payments, enrollments, landing_page_daily.
-- Edge cases: no seats gives NULL cost_per_seat and revenue_ratio 0 (not NULL: money collected is really zero); no buyers with a complete follow-up gives NULL followup_rate.
WITH ad AS (
    SELECT s.campaign_id, count(DISTINCT d.day)::INTEGER AS days_running, sum(d.spend) AS spend
    FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets s USING (ad_set_id) WHERE d.day BETWEEN $start::DATE AND $end::DATE GROUP BY s.campaign_id
),
q AS (
    SELECT l.campaign_id, count(*) AS qualified FROM leads l
    WHERE l.created_at::DATE BETWEEN $start::DATE AND $end::DATE AND EXISTS (SELECT 1 FROM lead_stages st WHERE st.lead_id = l.lead_id AND st.stage = 'qualified' AND st.reached_at::DATE <= $end::DATE)
    GROUP BY l.campaign_id
),
pay AS (
    SELECT w.campaign_id, p.lead_id, p.paid_at::DATE AS paid_on, p.seats, p.amount
    FROM workshop_payments p JOIN workshops w USING (workshop_id) WHERE p.paid_at::DATE BETWEEN $start::DATE AND $end::DATE
),
tot AS (SELECT campaign_id, sum(seats) AS paid_seats, sum(amount) AS revenue FROM pay GROUP BY campaign_id),
fu AS (
    SELECT campaign_id, count(DISTINCT lead_id) AS followup_buyers,
           count(DISTINCT lead_id) FILTER (WHERE EXISTS (SELECT 1 FROM enrollments e WHERE e.lead_id = pay.lead_id AND e.started_on > pay.paid_on
                                                         AND e.started_on <= pay.paid_on + $rca_followup_days::INTEGER)) AS followup_converted
    FROM pay WHERE lead_id IS NOT NULL AND paid_on <= $end::DATE - $rca_followup_days::INTEGER GROUP BY campaign_id
),
lp AS (
    SELECT campaign_id, sum(bounces) * 1.0 / nullif(sum(sessions), 0) AS landing_drop_off, sum(avg_load_seconds * sessions) / nullif(sum(sessions), 0) AS landing_load
    FROM landing_page_daily WHERE day BETWEEN $start::DATE AND $end::DATE GROUP BY campaign_id
)
SELECT c.campaign_id, c.name, ad.days_running, ad.spend::DOUBLE AS spend, coalesce(q.qualified, 0)::INTEGER AS qualified,
       coalesce(tot.paid_seats, 0)::INTEGER AS paid_seats, coalesce(tot.revenue, 0)::DOUBLE AS revenue,
       ad.spend / nullif(tot.paid_seats, 0) AS cost_per_seat, coalesce(tot.revenue, 0) / nullif(ad.spend, 0) AS revenue_ratio,
       coalesce(fu.followup_buyers, 0)::INTEGER AS followup_buyers, coalesce(fu.followup_converted, 0)::INTEGER AS followup_converted,
       coalesce(fu.followup_converted, 0) * 1.0 / nullif(fu.followup_buyers, 0) AS followup_rate, lp.landing_drop_off, lp.landing_load
FROM campaigns c JOIN ad USING (campaign_id) LEFT JOIN q USING (campaign_id) LEFT JOIN tot USING (campaign_id) LEFT JOIN fu USING (campaign_id) LEFT JOIN lp USING (campaign_id)
WHERE c.kind = 'workshop' ORDER BY c.campaign_id
