-- Revenue metrics (DuckDB). Period = $start..$end inclusive; the caller keeps $end on or before the data's as-of day.
-- "Revenue" means cash collected: an invoice counts on its paid_on day, a workshop seat on the day Razorpay recorded the payment.
-- Every query documents: definition, grain, source tables, edge cases. A zero or missing denominator gives NULL, never 0.

-- name: target_vs_actual
-- Definition: cash collected in the period against the period's share of the monthly targets. Each day carries its month's target divided by
--   the days in that month, so a whole calendar month gets exactly its target and a 7-day window gets about a quarter of one.
-- Grain: one row. Source: revenue_targets, invoices, workshop_payments.
-- Edge cases: days in a month with no target row add nothing, so a period with no target rows at all gives a NULL target;
--   a period with no cash gives actual 0.
WITH days AS (SELECT unnest(generate_series($start::DATE, $end::DATE, INTERVAL 1 DAY))::DATE AS day),
t AS (
    SELECT sum(rt.target * 1.0 / date_part('day', last_day(rt.month))) AS target
    FROM days d JOIN revenue_targets rt ON rt.month = date_trunc('month', d.day)::DATE
),
cash AS (
    SELECT coalesce(sum(amount), 0) AS amount FROM invoices WHERE paid_on BETWEEN $start::DATE AND $end::DATE
    UNION ALL
    SELECT coalesce(sum(amount), 0) FROM workshop_payments WHERE paid_at::DATE BETWEEN $start::DATE AND $end::DATE
)
SELECT t.target AS target, (SELECT sum(amount) FROM cash)::DOUBLE AS actual
FROM t

-- name: cash_breakdown
-- Definition: the cash collected in the period (the "Achieved" number) split into full-program students, 3-month-trial students and workshop seats,
--   with a bridge from the period's sign-ups to that cash for the two student rows:
--     students       = students who enrolled in the period
--     contract       = their total price (students x fee)
--     paid_new       = what those students have paid by $end
--     not_collected  = contract - paid_new (agreed, not paid yet)
--     earlier        = what students who enrolled BEFORE the period paid inside it
--     amount         = cash collected = paid_new + earlier (the three rows add up to target_vs_actual.actual)
--     payments       = number of payments behind amount
--   Cash is counted on the day it was paid, so sign-ups and cash differ by exactly not_collected and earlier.
-- Grain: three rows, always, in the order Full program, 3-month trial, Workshop seats. Source: enrollments, invoices, workshop_payments.
-- Edge cases: a student row with no activity shows zeros; the workshop row has NULL for students, contract, paid_new, not_collected and earlier
--   (a workshop seat has no sign-up behind it).
WITH k(stream, kind, ord) AS (VALUES ('Full program', 'program', 1), ('3-month trial', 'trial_3m', 2)),
paid AS (SELECT e.kind, i.amount, e.started_on FROM invoices i JOIN enrollments e USING (enrollment_id) WHERE i.paid_on BETWEEN $start::DATE AND $end::DATE),
students AS (
    SELECT k.ord, k.stream,
           (SELECT count(*) FROM enrollments e WHERE e.kind = k.kind AND e.started_on BETWEEN $start::DATE AND $end::DATE)::INTEGER AS students,
           (SELECT coalesce(sum(e.amount), 0) FROM enrollments e WHERE e.kind = k.kind AND e.started_on BETWEEN $start::DATE AND $end::DATE)::DOUBLE AS contract,
           (SELECT coalesce(sum(p.amount), 0) FROM paid p WHERE p.kind = k.kind AND p.started_on BETWEEN $start::DATE AND $end::DATE)::DOUBLE AS paid_new,
           (SELECT coalesce(sum(p.amount), 0) FROM paid p WHERE p.kind = k.kind AND p.started_on < $start::DATE)::DOUBLE AS earlier,
           (SELECT count(*) FROM paid p WHERE p.kind = k.kind)::INTEGER AS payments
    FROM k
),
rows AS (
    SELECT ord, stream, students, contract, paid_new, earlier, payments, paid_new + earlier AS amount FROM students
    UNION ALL
    SELECT 3, 'Workshop seats', NULL::INTEGER, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE, count(payment_id)::INTEGER, coalesce(sum(amount), 0)::DOUBLE
    FROM workshop_payments WHERE paid_at::DATE BETWEEN $start::DATE AND $end::DATE
)
SELECT stream, students, contract, paid_new, contract - paid_new AS not_collected, earlier, amount, payments FROM rows ORDER BY ord

-- name: cash_records
-- Definition: the individual payments behind one row of cash_breakdown ($stream is 'Full program', '3-month trial' or 'Workshop seats'), newest first.
--   reference is the invoice id or the Razorpay payment id; who is the student id (invoices) or the lead id (workshop seats);
--   enrolled_on is when that student enrolled, so a payment from a student who enrolled before the period is easy to see (NULL for workshop seats).
-- Grain: one row per payment. Source: invoices, enrollments, workshop_payments.
-- Edge cases: an unknown stream, or a period with no payments, gives no rows; a workshop payment with no lead shows a dash in who; enrollment_id is NULL for workshop seats.
SELECT paid_on, reference, who, enrolled_on, amount, enrollment_id FROM (
    SELECT i.paid_on, i.invoice_id AS reference, e.student_id AS who, e.started_on AS enrolled_on, i.amount::DOUBLE AS amount, e.enrollment_id
    FROM invoices i JOIN enrollments e USING (enrollment_id)
    WHERE i.paid_on BETWEEN $start::DATE AND $end::DATE
      AND e.kind = CASE $stream WHEN 'Full program' THEN 'program' WHEN '3-month trial' THEN 'trial_3m' END
    UNION ALL
    SELECT p.paid_at::DATE, p.payment_id, coalesce(p.lead_id, '-'), NULL::DATE, p.amount::DOUBLE, NULL::VARCHAR
    FROM workshop_payments p WHERE $stream = 'Workshop seats' AND p.paid_at::DATE BETWEEN $start::DATE AND $end::DATE
) ORDER BY paid_on DESC, reference

-- name: signup_split
-- Definition: students who enrolled in the period, split by construct (3-month trial or full program), with their contract value.
-- Grain: one row per kind present. Source: enrollments (started_on).
-- Edge cases: a kind with no sign-ups in the period has no row.
SELECT kind, count(*) AS students, sum(amount)::DOUBLE AS amount
FROM enrollments WHERE started_on BETWEEN $start::DATE AND $end::DATE
GROUP BY kind ORDER BY kind

-- name: onboarded_monthly
-- Definition: students onboarded (enrollment started) per calendar month, for months that have a sign-up inside the period.
-- Grain: one row per month. Source: enrollments.
-- Edge cases: a month partly inside the period counts only the days inside it; a month with none has no row.
SELECT date_trunc('month', started_on)::DATE AS month, count(*) AS students
FROM enrollments WHERE started_on BETWEEN $start::DATE AND $end::DATE
GROUP BY 1 ORDER BY 1

-- name: onboarded_students
-- Definition: the students behind one bar of onboarded_monthly: enrollments that started in calendar month $month (any day of it) and inside the period, newest first.
-- Grain: one row per enrollment. Source: enrollments.
-- Edge cases: a month partly inside the period lists only the days inside it, so the rows always add up to that month's onboarded_monthly count.
SELECT student_id, enrollment_id, kind, started_on, amount::DOUBLE AS amount
FROM enrollments
WHERE date_trunc('month', started_on) = date_trunc('month', $month::DATE) AND started_on BETWEEN $start::DATE AND $end::DATE
ORDER BY started_on DESC, enrollment_id

-- name: workshop_revenue
-- Definition: for each workshop held in the period, the seats sold and the Razorpay amount (seats x price per seat).
-- Grain: one row per workshop. Source: workshops, workshop_payments.
-- Edge cases: a workshop with no payments shows 0 seats and 0 amount, not a missing row. Seats paid after $end are not counted (not known on $end).
SELECT w.workshop_id, w.held_on, coalesce(sum(p.seats), 0)::INTEGER AS seats, coalesce(sum(p.amount), 0)::DOUBLE AS amount
FROM workshops w LEFT JOIN workshop_payments p ON p.workshop_id = w.workshop_id AND p.paid_at::DATE <= $end::DATE
WHERE w.held_on BETWEEN $start::DATE AND $end::DATE
GROUP BY w.workshop_id, w.held_on ORDER BY w.held_on

-- name: workshop_payments_for
-- Definition: the Razorpay payments behind one row of workshop_revenue ($workshop_id), newest first. who is the lead id, or '-' when the payment has no lead.
-- Grain: one row per payment. Source: workshop_payments.
-- Edge cases: payments after $end are not listed (not known on $end), so the rows add up to that workshop's workshop_revenue row; an unknown workshop gives no rows.
SELECT paid_at::DATE AS paid_on, payment_id AS reference, coalesce(lead_id, '-') AS who, seats, amount::DOUBLE AS amount
FROM workshop_payments WHERE workshop_id = $workshop_id AND paid_at::DATE <= $end::DATE
ORDER BY paid_at DESC, payment_id

-- name: program_vs_workshop
-- Definition: cash collected in the period from program invoices against workshop seats.
-- Grain: two rows (program, workshop). Source: invoices (paid_on), workshop_payments (paid_at).
-- Edge cases: a stream with no cash in the period shows 0.
SELECT 'program' AS stream, coalesce(sum(amount), 0)::DOUBLE AS amount FROM invoices WHERE paid_on BETWEEN $start::DATE AND $end::DATE
UNION ALL
SELECT 'workshop', coalesce(sum(amount), 0)::DOUBLE FROM workshop_payments WHERE paid_at::DATE BETWEEN $start::DATE AND $end::DATE

-- name: unpaid_invoices
-- Definition: invoices issued inside the period that were still unpaid on $end, with how many days past due they were on $end.
-- Grain: one row per invoice. Source: invoices.
-- Edge cases: an invoice paid after $end is still listed (it was unpaid as of $end); not yet due gives days_overdue 0;
--   an invoice issued before $start is not listed even if it is still unpaid, so a short period hides older debt: widen the period to see it.
SELECT invoice_id, enrollment_id, amount::DOUBLE AS amount, due_on, greatest(0, $end::DATE - due_on)::INTEGER AS days_overdue
FROM invoices WHERE issued_on BETWEEN $start::DATE AND $end::DATE AND (paid_on IS NULL OR paid_on > $end::DATE)
ORDER BY days_overdue DESC, invoice_id

-- name: enrollment_invoices
-- Definition: every invoice of one enrollment ($enrollment_id) as known on $end, with the enrollment, its student and the lead and campaign it came from, so an unpaid invoice can be chased.
-- Grain: one row per invoice (issued by $end). Source: invoices, enrollments, leads, campaigns.
-- Edge cases: paid_on is NULL when unpaid on $end (a payment after $end is hidden); lead_id, student_name and campaign_name are NULL for an enrollment with no lead
--   or an organic lead; an unknown enrollment gives no rows.
SELECT i.invoice_id, i.issued_on, i.due_on, i.amount::DOUBLE AS amount, CASE WHEN i.paid_on <= $end::DATE THEN i.paid_on END AS paid_on,
       e.enrollment_id, e.student_id, e.kind, e.started_on, e.renewal_on, e.amount::DOUBLE AS contract, e.lead_id, l.student_name, c.name AS campaign_name
FROM invoices i JOIN enrollments e USING (enrollment_id) LEFT JOIN leads l ON l.lead_id = e.lead_id LEFT JOIN campaigns c ON c.campaign_id = l.campaign_id
WHERE e.enrollment_id = $enrollment_id AND i.issued_on <= $end::DATE
ORDER BY i.issued_on, i.invoice_id

-- name: upcoming_renewals
-- Definition: 3-month trial students whose trial ends from $end up to $renewals_lookahead_days later and who therefore need a renewal conversation.
--   Forward-looking by nature: it depends on the period's last day only, so changing the start of the period does not change it.
-- Grain: one row per trial enrollment. Source: enrollments (kind trial_3m, renewal_on).
-- Edge cases: a trial that already ended before $end is not listed; the lookahead is in config.yaml.
SELECT enrollment_id, student_id, renewal_on, (renewal_on - $end::DATE)::INTEGER AS days_left, amount::DOUBLE AS amount
FROM enrollments
WHERE kind = 'trial_3m' AND renewal_on BETWEEN $end::DATE AND $end::DATE + to_days($renewals_lookahead_days::INTEGER)
ORDER BY renewal_on, enrollment_id
