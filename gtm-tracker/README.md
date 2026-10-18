# Alcovia GTM tracker

I built this tracker for Problem 2 to bring revenue, the lead journey and campaign performance into one view, with the numbers behind each budget recommendation available to inspect.

I’ve used **synthetic data throughout**: a year ending **18 October 2026**, with generated contacts and `DEMO-` IDs. The [dashboard](https://alcovia-assessment-kbzzwsknrq3jkznzvbpfzq.streamlit.app/) works on this data. I haven’t connected it to live ClickUp, Meta or Razorpay data.

## What it covers

| Brief objective | In the dashboard |
|---|---|
| Revenue accountability | Target vs cash collected, full-program vs 3-month-trial sign-ups, monthly onboarding, fortnightly workshops at ₹3,999 per seat, program vs workshop revenue, unpaid invoices and upcoming trial renewals. |
| Funnel journey | Leads → qualified → discovery scheduled → discovery attended → ambition interview → architect session → signed up. Includes show-up and drop-off rates, qualified-lead cost, conversion, organic leads and average journey length. |
| Campaign performance | Program and workshop campaigns, highest/lowest CTR assets, ad-set frequency with a warning at 3+, landing-page drop-off and load time. |
| Root cause analysis | Scale, Hold, Refresh, Pause or Too early, with the reasons, supporting flags and evidence shown separately. |

Start with **Overview** for the main numbers, then click through the revenue, campaign and lead tables to inspect payments, ads and individual journeys. I’ve kept the Definitions page tied to the SQL comments, so you can trace a metric back to its calculation.

You can select 7/30/90 days, this month, last month or a custom range. I include both boundary dates and anchor the presets to the snapshot’s end date, with timestamps treated as IST calendar days. Your selection carries across the data pages. Try **Last 90 days** on Root cause analysis to see all eight campaign examples.

## Approach and metric choices

I’ve used Streamlit and DuckDB so you can run the prototype without setting up a separate backend or database service. On first use, the generator builds a temporary database. SQL calculates the metrics and Python applies the campaign rules. Seed **7** reproduces the demo. If you change the config or seed settings, restart the server: the app caches configuration, data and query results, and I haven’t built a live refresh pipeline.

- **I measure achieved revenue as cash collected on the payment date.** Achieved = contract value of new enrollments − not collected yet + payments from earlier enrollments + workshop receipts. The chart shows each amount from zero, not a cumulative waterfall. “Program” in the program/workshop split includes full programs **and trials**.
- **I prorate targets by day**, including month-to-date views. For historical demo months, I generate targets above/below that month’s cash so both outcomes are visible. The current month’s target uses the prior three months’ average cash × 1.05. These are illustrative targets; I haven’t treated them as independently set business goals. Missing target months contribute nothing; if all are missing, target is unavailable.
- **For onboarding, I count enrollment starts.** This doesn’t measure payment or app activation, and I haven’t deduplicated students with multiple enrollments. A partial month's bar counts only selected days; months without enrollments are omitted.
- **I use different dates for workshop cash and workshop events.** Achieved revenue and the program/workshop split count payments inside the period. For the workshop chart, I select workshops held inside the period and include their payments up to the end date, including payments before the start. Those totals need not match. Seats can exceed payment or buyer counts.
- **For the funnel, I follow leads created in the period**, using outcomes known by its end. They include paid, organic and brochure leads, across program and workshop campaigns. CPQL uses **all period ad spend / qualified paid-ad leads created in the period**; organic and brochure leads do not lower it. Brochure is a separate source, not organic.
- **I calculate show-up as attended/scheduled, and ambition drop-off as 1 − architect/ambition.** That drop-off figure includes people still waiting for an architect session, so I wouldn’t read all of it as confirmed loss. For “Qualified”, I use the recorded ClickUp stage; I’m not calculating a qualification score here. Review and qualification-conveyed stages appear in histories; rejected and nurture exits are separate. The model assumes a complete, ordered path and records one timestamp per lead/stage, not repeat calls or re-entry cycles.
- **I show headline program conversion as paid program or trial buyers from the selected lead cohort / leads created in the selected period.** A buyer needs a linked enrollment and at least one invoice paid by the selected end date. Each lead counts once, even with multiple invoices. A recent cohort may still be progressing, so its rate can understate eventual conversion. Campaign and attribute breakdowns show ClickUp sign-up stages rather than paid enrollments; RCA checks paid invoices separately. Average journey is creation to the **last recorded stage**, including leads still progressing; it is not elapsed time to today or a completed-sales-cycle average.
- **For unpaid invoices**, I include invoices issued in the selected period, so a short range can hide older debt. **For renewals**, I include trial end dates from the selected end date through 30 days later, including both boundaries. Already expired trials aren’t included.
- I’ve used the supplied pricing notes for demo fees: **₹5,00,000 for the full program and ₹1,75,000 for the trial**. Targets and results remain illustrative.

I’ve kept the demo billing model simple: one invoice per enrollment for the full fee, due in seven days. Payments generally arrive within 0–3 days, with a small unpaid share and overdue examples included. I use **90 days** for trials. I haven’t modeled completed renewals, trial upgrades, partial payments, installments, taxes, fees, cancellations or refunds.

### Reading campaign and lead tables

I calculate campaign CTR as total clicks / total impressions, rather than averaging daily percentages. The highest/lowest asset tables show five ads across **all campaigns in the selected period**. I’d use that ranking to inspect the assets, not to infer conversion quality or profitability. The RCA weak-ad flag makes a different comparison: an ad against its own campaign over 90 days.

On the campaign page, I show frequency as the **latest daily observation within the selected period**, alongside a separate peak column. I don’t sum or average it into a period-wide reach/frequency estimate. RCA uses the latest observation within 14 days, so the two displays can differ when data is sparse.

I apply lead filters before displaying the **200 newest matching rows**. For unpaid invoices, the totals cover all matches, while the visible list shows the **10 most overdue**. Those display limits don’t reduce the metric totals. I’ve kept missing lead attributes as their own group; I’d be cautious about ranking small or recent groups by conversion.

## Campaign decisions

I’ve structured the RCA for weekly budget reviews, with daily checks and monthly strategy reviews also possible. Each campaign gets one recommendation, the reasons behind it, separate diagnostic flags and an evidence label. You can inspect the inputs before acting. The tracker doesn’t change ad spend, and a rule firing doesn’t establish what caused the result.

### Windows and evidence

For program recommendations, I use **90 calendar days ending on the selected end date**, regardless of the selected start date. I treat leads aged **28–89 days** as mature and **0–27 days** as recent, and split spend over those same calendar days. That keeps me from dividing all 90 days of spend by only the older customers. For a historical end date, I exclude later stages, enrollments and payments.

I’ve used **28 days** to allow time for conversion before judging a lead cohort. That setting comes from the synthetic timings; I’d re-measure it on real ClickUp history. Younger leads stay visible as “awaiting conversion”, which doesn’t mean I expect all of them to convert.

Before giving a program campaign a financial recommendation, I require it to be **at least 14 days old**, with **30 qualified leads in the lookback**. Scale and Pause also require **30 mature qualified leads**. I haven’t set a minimum-spend requirement. These are provisional operating rules, not statistical confidence thresholds. Refresh can still apply below them, and other warnings remain visible.

I count the first ad day as day one, including gaps since launch. The current rules can keep a program campaign listed after its activity stops; I haven’t added an active-campaign or recent-spend eligibility check. Historical stage/payment cutoffs also don’t reconstruct later edits to lead attributes or campaign mappings.

### Numbers behind program verdicts

| Measure | Calculation |
|---|---|
| Mature qualified-lead cost (CPQL) | All campaign spend on mature-window days / mature qualified leads. |
| Mature paid conversion | (Mature leads with a paid full-program enrollment + mature leads with a paid trial enrollment) / mature qualified leads. Both purchase types are displayed separately. |
| Full-program acquisition cost | Mature-window spend / mature leads with a paid full-program enrollment. Trial buyers do not reduce this cost. |
| Recent cost deterioration | Recent CPQL / mature CPQL, each using its own window's spend and qualified leads. Above **1.30** blocks Scale. |

When I say “paid” in the RCA, I mean an enrollment has at least one invoice paid by the end date; I’m not requiring full settlement. I attribute the purchase to the lead’s recorded campaign and allocate spend by date, rather than tracing individual ad spend to each buyer. The demo assumes buyers have qualified and each lead buys one construct. Before using the combined conversion rate on real data, I’d reconcile qualification history and trial-to-program upgrades.

For peer medians, I use program campaigns that pass the evidence floors and have conversion and CPQL available. I include the campaign being assessed and give each campaign equal weight. I require **at least two eligible campaigns** for Scale, keeping conversion quality and lead-cost efficiency as separate tests.

### Verdict priority

I apply the program rules in this order:

1. **Pause** if eligible full-program acquisition cost is **above ₹50,000**. I’ve used a provisional allowance of 10% of the ₹5L fee because actual margins are unavailable. Exceeding it does not prove unprofitability. Pause takes priority over Refresh to control spending while replacement creative is prepared.
2. **Refresh** if any ad set's frequency is **3 or more**, or its CTR falls **at least 15%**: latest 14 days versus the preceding 14. Either trigger suffices. CTR is total clicks / total impressions, and the fall is relative: 2% to 1.7% is a 15% decline. RCA uses the latest available frequency in the last 14 days. I’ve kept the 15% sensitivity provisional and shown clicks and impressions so you can assess the evidence.
3. **Too early** if sign-up evidence is insufficient and no Refresh applies.
4. **Scale** if mature conversion is **strictly above** its peer median, mature CPQL **strictly below** its median, full-program acquisition cost is available and **at most ₹50,000**, and recent cost has not worsened by **more than 30%**. Matching a median does not qualify. The cost ceiling prevents scaling solely for outperforming weak peers. At +30% CPQL, the same budget buys about 23% fewer qualified leads, hence the deterioration check.
5. Otherwise **Hold**, including when fewer than two peers qualify. With deterioration and no higher-priority action, the label is “Hold: recent acquisition cost worsening”.

### Flags and missing data

| Flag | Trigger and interpretation |
|---|---|
| Creative review | An ad's 90-day CTR is **at least 50% below** its own campaign's median ad CTR. Review that asset; it does not automatically Refresh the campaign. |
| Fix landing page | Drop-off **above 50%** or load time **above 4 seconds**. Drop-off is bounces/sessions; load time is weighted by sessions. Program page signals use 90 days; workshop page signals use the selected period. |
| Overspend | Program lifetime spend by the end date **above ₹50,000** with no attributed paid customer of any age, trials included; workshop period spend **above ₹3,999** with no paid seats. This alerts even below eligibility; it does not automatically Pause. |
| No mature full-program conversions | Once evidence floors are met, zero such customers prompts a budget review. Acquisition cost is unavailable, not ₹0; Scale is blocked, but Pause is not automatic. Refresh can still take priority. |
| Recent acquisition cost worsening | Recent/mature CPQL **above 1.30**. Blocks Scale; does not independently Pause. |

I show an unavailable comparison when its denominator is missing or zero. An unavailable prior CTR or campaign median can’t trigger that comparison rule. There is one important limit: an unavailable recent/mature CPQL ratio currently does **not** independently block Scale. I also haven’t added minimum-impression or minimum-session floors to CTR and page flags, so I’d review their counts before acting. Flags don’t veto Scale by themselves; only the stated recommendation rules do.

### Workshop decisions

For workshops, I use the selected period for spend, collected seat revenue, qualified leads and **days with ad activity**. I require **14 such days and 30 qualified leads** before giving a financial recommendation. I calculate cost per seat as spend / paid seats, and revenue per rupee of ads as collected seat revenue / spend.

Once a workshop campaign is eligible, I recommend **Pause** below a revenue/spend ratio of **1.0**. Next comes **Refresh** using the same creative triggers, then **Too early** below eligibility, otherwise **Hold**. I haven’t added a Scale rule for workshops. Exactly 1.0 passes this advertising test, but it doesn’t demonstrate profit: the demo assumes zero refunds and excludes delivery costs. With spend but no seats, revenue/spend is zero and cost per seat is unavailable.

I keep the creative windows unchanged for workshops: 14 days versus the previous 14 for ad-set CTR, and 90 days for weak-ad comparisons. They don’t shorten when you change the timeline’s start date.

When you click a campaign, ad set or ad from RCA, its detail opens for the **selected timeline**, which can differ from the recommendation window. Use the RCA input tables to reconcile the recommendation. On Overview, “campaigns with a verdict” counts every label except Too early, including Refresh with limited evidence. I wouldn’t read it as the number of campaigns with mature conversion evidence.

I track later program purchases separately over a **60-day follow-up**. I only include linked buyers whose full follow-up has elapsed, then check whether they enrolled after the workshop seat purchase and within 60 days. That doesn’t verify payment of the later enrollment. With no eligible buyers, I show an unavailable rate. These linked purchases are synthetic and counted once in company cash; I don’t use them to override a workshop’s financial recommendation.

### Reading the demo

For **Last 90 days ending 18 October 2026**:

| Campaign | Verdict | Explanation |
|---|---|---|
| SCALE | Scale | Meets both peer tests and the cost ceiling. Conversion only narrowly beats the median, so this is a candidate for review, not a robust statistical win. |
| DECLINE | Hold | Passes the peer tests but recent CPQL has worsened by about 35%. |
| ASSET | Hold + creative flag | One weak ad does not warrant refreshing the campaign; conversion fails the Scale test. |
| FATIGUE | Pause + refresh reason | Acquisition cost breaches the ceiling; frequency/CTR also signal creative work. Pause wins. |
| LP | Too early + page flag | Only 27 mature qualified leads, despite the visible page problem. |
| NEW | Too early | Insufficient qualified and mature leads. |
| WS-OK / WS-VOLUME | Pause | Seat revenue covers about 0.53 / 0.40 of ad spend respectively. Later program purchases remain separate. |

I’ve included these examples to demonstrate and test the rules; they aren’t findings about Alcovia’s campaigns. Frequency 3+ comes from the brief. The other thresholds in [config.yaml](config.yaml) are provisional. You can trace the inputs to the [SQL](sql/metrics/rca.sql) and the recommendations to [rca.py](rca.py). The [expected-verdict tests](tests/test_rca_expected.py) check these cases without retuning thresholds to get a particular label.

## Run locally

To run it, start from `gtm-tracker/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

To run the checks:

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

The tests cover calculations, payment reconciliation, date boundaries, historical views, campaign rules and page rendering. I still need to verify browser clicks and layout manually.

## Code and remaining work

- [Database schema](sql/schema/gtm.sql): leads and stage history, enrollments and invoices, workshop payments, ad activity and landing-page data.
- [Metric queries](sql/metrics/): definitions, calculation grain, sources and edge cases alongside each query.
- [Demo generator](seed/generate.py), [decision rules](rca.py), [dashboard pages](views/) and [tests](tests/).

Live ingestion and authentication remain open. Team allocation and delivery timelines are in the [executive writeup](../Docs/executive-writeup.md).
