-- Funnel metrics (DuckDB) for the Meta-ads journey. Period = $start..$end inclusive.
-- A "lead" is created on a day; the cohort of a period is the leads created in it, and stage counts follow that cohort forward.
-- Stages in order: lead, qualified, discovery_set, discovery_attended, ambition_interview, architect_session, signed (the brief's journey).
-- ClickUp also records review and conveyed in between, and two exits, rejected and nurture; see schema/gtm.sql for the mapping.
-- Every query documents: definition, grain, source tables, edge cases. A zero denominator gives NULL, never 0.

-- name: stage_counts
-- Definition: how many of the leads created in the period reached each stage (or any later one: stages are a prefix of the order).
-- Grain: one row per stage, always all seven in order. Source: leads, lead_stages.
-- Edge cases: an empty period gives seven rows of 0. Only stages reached by $end count (a stage reached later is not known on $end), so a past period never changes when its leads progress later.
--   Leads created late in the period may not have had time to progress; recent cohorts understate later stages.
WITH s(stage, ord) AS (VALUES ('lead', 1), ('qualified', 2), ('discovery_set', 3), ('discovery_attended', 4), ('ambition_interview', 5), ('architect_session', 6), ('signed', 7)),
cohort AS (SELECT lead_id FROM leads WHERE created_at::DATE BETWEEN $start::DATE AND $end::DATE)
SELECT s.stage, count(ls.lead_id)::INTEGER AS leads
FROM s LEFT JOIN lead_stages ls ON ls.stage = s.stage AND ls.lead_id IN (SELECT lead_id FROM cohort) AND ls.reached_at::DATE <= $end::DATE
GROUP BY s.stage, s.ord ORDER BY s.ord

-- name: stage_leads
-- Definition: the leads behind one row of stage_counts: leads created in the period that reached $stage (one of the stage_counts stages) by $end, newest first.
-- Grain: one row per lead. Source: leads, lead_stages.
-- Edge cases: the rows add up to that stage's stage_counts number; an unknown stage or an empty period gives no rows; reached_at is when the lead first got there.
SELECT l.lead_id, l.student_name, l.parent_name, l.city, l.source_lead, l.created_at, min(ls.reached_at) AS reached_at
FROM leads l JOIN lead_stages ls ON ls.lead_id = l.lead_id AND ls.stage = $stage AND ls.reached_at::DATE <= $end::DATE
WHERE l.created_at::DATE BETWEEN $start::DATE AND $end::DATE
GROUP BY l.lead_id, l.student_name, l.parent_name, l.city, l.source_lead, l.created_at
ORDER BY l.created_at DESC, l.lead_id DESC

-- name: exits
-- Definition: of the leads created in the period, how many ClickUp moved to Rejected (did not meet the criteria at review)
--   and how many to Move to Nurture Database (attended the discovery call but were not taken further).
-- Grain: one row. Source: leads, lead_stages.
-- Edge cases: an empty period gives 0 and 0. A lead is in at most one exit. Leads still in progress are in neither.
WITH cohort AS (SELECT lead_id FROM leads WHERE created_at::DATE BETWEEN $start::DATE AND $end::DATE)
SELECT count(*) FILTER (WHERE stage = 'rejected')::INTEGER AS rejected, count(*) FILTER (WHERE stage = 'nurture')::INTEGER AS nurture
FROM lead_stages WHERE lead_id IN (SELECT lead_id FROM cohort) AND reached_at::DATE <= $end::DATE

-- name: show_up_and_drop
-- Definition: discovery-call show-up rate = attended / set; ambition-interview drop-off rate = 1 - (reached the architect session / held the ambition interview).
-- Grain: one row. Source: leads, lead_stages (cohort of the period).
-- Edge cases: no calls set, or no interviews held, gives a NULL rate.
WITH cohort AS (SELECT lead_id FROM leads WHERE created_at::DATE BETWEEN $start::DATE AND $end::DATE),
c AS (
    SELECT count(*) FILTER (WHERE stage = 'discovery_set') AS discovery_set,
           count(*) FILTER (WHERE stage = 'discovery_attended') AS discovery_attended,
           count(*) FILTER (WHERE stage = 'ambition_interview') AS ambition_interview,
           count(*) FILTER (WHERE stage = 'architect_session') AS architect_session
    FROM lead_stages WHERE lead_id IN (SELECT lead_id FROM cohort) AND reached_at::DATE <= $end::DATE
)
SELECT discovery_set::INTEGER AS discovery_set, discovery_attended::INTEGER AS discovery_attended,
       ambition_interview::INTEGER AS ambition_interview, architect_session::INTEGER AS architect_session,
       discovery_attended * 1.0 / nullif(discovery_set, 0) AS discovery_show_up_rate,
       1 - architect_session * 1.0 / nullif(ambition_interview, 0) AS ambition_drop_off_rate
FROM c

-- name: headline
-- Definition: the four top metrics.
--   cost_per_qualified_lead = all paid spend in the period / paid leads created in the period that reached 'qualified'.
--   program_conversion_rate = leads that reached 'signed' inside the period / leads created in the period [A: brief says "those who pay and sign up in the period reviewed"; read as a flow ratio].
--   organic_leads = leads whose ClickUp source lead is Organic, created in the period. Brochure leads are neither organic nor paid.
--   cost_per_qualified_lead divides by paid-ads leads only, so a brochure lead never lowers it.
--   avg_journey_days = mean days from creation to the last stage reached, for leads created in the period, whether they signed or dropped off.
-- Grain: one row. Source: leads, lead_stages, ad_daily.
-- Edge cases: no qualified paid leads gives a NULL cost; no leads gives NULL conversion and journey; spend with no leads still shows in by_campaign.
WITH cohort AS (SELECT * FROM leads WHERE created_at::DATE BETWEEN $start::DATE AND $end::DATE),
q AS (SELECT count(*) AS n FROM cohort c JOIN lead_stages s USING (lead_id) WHERE s.stage = 'qualified' AND c.source_lead = 'paid_ads' AND s.reached_at::DATE <= $end::DATE),
sp AS (SELECT coalesce(sum(spend), 0) AS amount FROM ad_daily WHERE day BETWEEN $start::DATE AND $end::DATE),
sg AS (SELECT count(*) AS n FROM lead_stages WHERE stage = 'signed' AND reached_at::DATE BETWEEN $start::DATE AND $end::DATE),
j AS (SELECT avg((epoch(m.last_at) - epoch(c.created_at)) / 86400.0) AS days
      FROM cohort c JOIN (SELECT lead_id, max(reached_at) AS last_at FROM lead_stages WHERE reached_at::DATE <= $end::DATE GROUP BY lead_id) m USING (lead_id))
SELECT sp.amount / nullif(q.n, 0) AS cost_per_qualified_lead,
       sg.n * 1.0 / nullif((SELECT count(*) FROM cohort), 0) AS program_conversion_rate,
       (SELECT count(*) FROM cohort WHERE source_lead = 'organic')::INTEGER AS organic_leads,
       j.days AS avg_journey_days
FROM q, sp, sg, j

-- name: by_campaign
-- Definition: per campaign, leads created in the period, how many qualified and signed, spend in the period, and cost per qualified lead.
-- Grain: one row per campaign that has spend or leads in the period. Source: campaigns, leads, lead_stages, ad_daily.
-- Edge cases: zero qualified leads gives a NULL cost per qualified lead; spend is summed apart from leads so a join cannot multiply it.
WITH cohort AS (SELECT * FROM leads WHERE created_at::DATE BETWEEN $start::DATE AND $end::DATE AND campaign_id IS NOT NULL),
l AS (
    SELECT c.campaign_id, count(DISTINCT c.lead_id) AS leads,
           count(*) FILTER (WHERE s.stage = 'qualified') AS qualified,
           count(*) FILTER (WHERE s.stage = 'signed') AS signed
    FROM cohort c JOIN lead_stages s ON s.lead_id = c.lead_id AND s.reached_at::DATE <= $end::DATE GROUP BY c.campaign_id
),
sp AS (
    SELECT a_s.campaign_id, sum(d.spend) AS spend
    FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets a_s USING (ad_set_id)
    WHERE d.day BETWEEN $start::DATE AND $end::DATE GROUP BY a_s.campaign_id
)
SELECT c.campaign_id, c.kind, coalesce(l.leads, 0)::INTEGER AS leads, coalesce(l.qualified, 0)::INTEGER AS qualified, coalesce(l.signed, 0)::INTEGER AS signed,
       coalesce(sp.spend, 0)::DOUBLE AS spend, coalesce(sp.spend, 0) / nullif(l.qualified, 0) AS cost_per_qualified_lead
FROM campaigns c LEFT JOIN l USING (campaign_id) LEFT JOIN sp USING (campaign_id)
WHERE l.campaign_id IS NOT NULL OR sp.campaign_id IS NOT NULL
ORDER BY c.campaign_id


-- name: by_dimension
-- Definition: leads created in the period, grouped by one ClickUp attribute at a time (city, grade, school, traffic_source, source_lead, utm_source):
--   leads, how many reached 'qualified', how many reached 'signed', and each as a share of the group's leads.
-- Grain: one row per (dimension, value). Every dimension's leads add up to the same total. Source: leads, lead_stages.
-- Edge cases: a missing value is its own group, labelled Unknown (utm_source: Not from an ad), never dropped. Small groups give noisy rates, so read leads first;
--   leads created late in the period may not have had time to qualify or sign, which understates both rates for recent cohorts.
WITH cohort AS (SELECT * FROM leads WHERE created_at::DATE BETWEEN $start::DATE AND $end::DATE),
f AS (
    SELECT c.lead_id, c.city, c.grade::VARCHAR AS grade, c.school, c.traffic_source, c.source_lead, c.utm_source,
           coalesce(bool_or(s.stage = 'qualified'), false) AS qualified, coalesce(bool_or(s.stage = 'signed'), false) AS signed
    FROM cohort c LEFT JOIN lead_stages s ON s.lead_id = c.lead_id AND s.reached_at::DATE <= $end::DATE GROUP BY ALL
),
long AS (
    SELECT 'city' AS dimension, coalesce(city, 'Unknown') AS value, qualified, signed FROM f
    UNION ALL SELECT 'grade', coalesce(grade, 'Unknown'), qualified, signed FROM f
    UNION ALL SELECT 'school', coalesce(school, 'Unknown'), qualified, signed FROM f
    UNION ALL SELECT 'traffic_source', coalesce(traffic_source, 'Unknown'), qualified, signed FROM f
    UNION ALL SELECT 'source_lead', coalesce(source_lead, 'Unknown'), qualified, signed FROM f
    UNION ALL SELECT 'utm_source', coalesce(utm_source, 'Not from an ad'), qualified, signed FROM f
)
SELECT dimension, value, count(*)::INTEGER AS leads, count(*) FILTER (WHERE qualified)::INTEGER AS qualified, count(*) FILTER (WHERE signed)::INTEGER AS signed,
       count(*) FILTER (WHERE qualified) * 1.0 / nullif(count(*), 0) AS qualified_rate, count(*) FILTER (WHERE signed) * 1.0 / nullif(count(*), 0) AS signed_rate
FROM long GROUP BY dimension, value ORDER BY dimension, leads DESC, value

-- name: lead_list
-- Definition: one row per lead created in the period, newest first, with the ClickUp fields, the furthest stage on the main path
--   (lead, review, qualified, conveyed, discovery_set, discovery_attended, ambition_interview, architect_session, signed) and a status:
--   Signed up, Rejected, Nurture or In progress. An exit stage (rejected, nurture) does not move the furthest stage.
-- Grain: one row per lead. Source: leads, lead_stages. Names and phone numbers are generated dummy values.
-- Edge cases: a lead with no stage rows has a NULL furthest stage and status In progress; an empty period gives no rows.
--   The furthest stage and status are as known on $end: a stage reached later is not counted.
WITH path(stage, ord) AS (VALUES ('lead', 1), ('review', 2), ('qualified', 3), ('conveyed', 4), ('discovery_set', 5), ('discovery_attended', 6),
                                 ('ambition_interview', 7), ('architect_session', 8), ('signed', 9)),
prog AS (SELECT s.lead_id, arg_max(s.stage, p.ord) AS furthest_stage FROM lead_stages s JOIN path p USING (stage) WHERE s.reached_at::DATE <= $end::DATE GROUP BY s.lead_id),
ex AS (SELECT lead_id, bool_or(stage = 'signed') AS signed, bool_or(stage = 'rejected') AS rejected, bool_or(stage = 'nurture') AS nurture FROM lead_stages WHERE reached_at::DATE <= $end::DATE GROUP BY lead_id)
SELECT l.lead_id, l.student_name, l.parent_name, l.phone, l.grade, l.school, l.city, l.source_lead, l.campaign_id, l.utm_source, l.traffic_source, l.created_at, prog.furthest_stage,
       CASE WHEN ex.signed THEN 'Signed up' WHEN ex.rejected THEN 'Rejected' WHEN ex.nurture THEN 'Nurture' ELSE 'In progress' END AS status
FROM leads l LEFT JOIN prog USING (lead_id) LEFT JOIN ex USING (lead_id)
WHERE l.created_at::DATE BETWEEN $start::DATE AND $end::DATE
ORDER BY l.created_at DESC, l.lead_id DESC

-- name: lead_detail
-- Definition: everything the leads table shows for one lead ($lead_id), plus the campaign, ad set and asset it came from.
-- Grain: one row, or none for an unknown id. Source: leads, campaigns, ad_sets, ads, lead_stages. Generated names and phone numbers.
-- Edge cases: an organic or brochure lead has no campaign, ad set or asset (NULLs); the status and furthest stage follow lead_list.
WITH path(stage, ord) AS (VALUES ('lead', 1), ('review', 2), ('qualified', 3), ('conveyed', 4), ('discovery_set', 5), ('discovery_attended', 6),
                                 ('ambition_interview', 7), ('architect_session', 8), ('signed', 9)),
prog AS (SELECT s.lead_id, arg_max(s.stage, p.ord) AS furthest_stage FROM lead_stages s JOIN path p USING (stage) WHERE s.lead_id = $lead_id AND s.reached_at::DATE <= $end::DATE GROUP BY s.lead_id),
ex AS (SELECT lead_id, bool_or(stage = 'signed') AS signed, bool_or(stage = 'rejected') AS rejected, bool_or(stage = 'nurture') AS nurture FROM lead_stages WHERE lead_id = $lead_id AND reached_at::DATE <= $end::DATE GROUP BY lead_id)
SELECT l.lead_id, l.student_name, l.parent_name, l.phone, l.grade, l.school, l.city, l.source_lead, l.utm_source, l.traffic_source, l.created_at,
       c.name AS campaign_name, s.name AS ad_set_name, a.asset_name, prog.furthest_stage,
       CASE WHEN ex.signed THEN 'Signed up' WHEN ex.rejected THEN 'Rejected' WHEN ex.nurture THEN 'Nurture' ELSE 'In progress' END AS status
FROM leads l LEFT JOIN campaigns c USING (campaign_id) LEFT JOIN ad_sets s ON s.ad_set_id = l.ad_set_id LEFT JOIN ads a ON a.ad_id = l.ad_id
LEFT JOIN prog ON prog.lead_id = l.lead_id LEFT JOIN ex ON ex.lead_id = l.lead_id
WHERE l.lead_id = $lead_id

-- name: lead_timeline
-- Definition: every stage one lead ($lead_id) reached, in time order, with the days since the stage before it. Exits (rejected, nurture) are included.
-- Grain: one row per stage reached. Source: lead_stages.
-- Edge cases: the first stage has NULL days_since_previous; an unknown id gives no rows. Only stages reached by $end are listed.
SELECT stage, reached_at, (epoch(reached_at) - epoch(lag(reached_at) OVER (ORDER BY reached_at))) / 86400.0 AS days_since_previous
FROM lead_stages WHERE lead_id = $lead_id AND reached_at::DATE <= $end::DATE ORDER BY reached_at

-- name: lead_money
-- Definition: the money tied to one lead ($lead_id): workshop seats bought, the program or trial enrollment, and each invoice with its payment state.
-- Grain: one row per workshop payment, enrollment or invoice, in date order (workshop, enrollment, invoice on the same day). Source: workshop_payments, enrollments, invoices.
-- Edge cases: a lead that never paid or enrolled has no rows; an unpaid invoice shows its due date, a paid one the payment date. Everything is as known on $end:
--   a payment, enrollment or invoice dated after $end is not shown, and an invoice paid after $end still reads unpaid.
SELECT item, reference, amount, on_date, state FROM (
    SELECT 1 AS ord, 'Workshop seats (' || p.seats::VARCHAR || ')' AS item, p.payment_id AS reference, p.amount::DOUBLE AS amount, p.paid_at::DATE AS on_date, 'Paid' AS state
    FROM workshop_payments p WHERE p.lead_id = $lead_id AND p.paid_at::DATE <= $end::DATE
    UNION ALL
    SELECT 2, CASE e.kind WHEN 'program' THEN 'Program enrollment' ELSE 'Trial enrollment' END, e.enrollment_id, e.amount::DOUBLE, e.started_on, 'Started'
    FROM enrollments e WHERE e.lead_id = $lead_id AND e.started_on <= $end::DATE
    UNION ALL
    SELECT 3, 'Invoice', i.invoice_id, i.amount::DOUBLE, i.issued_on,
           CASE WHEN i.paid_on IS NULL OR i.paid_on > $end::DATE THEN 'Unpaid, due ' || strftime(i.due_on, '%d %b %Y') ELSE 'Paid on ' || strftime(i.paid_on, '%d %b %Y') END
    FROM invoices i JOIN enrollments e USING (enrollment_id) WHERE e.lead_id = $lead_id AND i.issued_on <= $end::DATE
) ORDER BY on_date, ord, reference
