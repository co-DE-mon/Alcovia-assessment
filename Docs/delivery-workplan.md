# November 2026 delivery workplan

GitHub-readable copy of the [editable Excel workbook](delivery-workplan.xlsx). The task statuses and acceptance results are proposed starting values; update the workbook as delivery proceeds.

## Tasks and owners

One engineer implementation stream; engineer days count implementation allocation only. “—” means no engineer time.

| Area | Task | Subtask | Engineer days | Status | Owner | Target | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| All workstreams | T01 Set outcomes | T01.1 Agree the problem and scope | 0 | Not started | Pranav | 2 Nov 2026 | For app adoption, GTM and student tracking, name the user, decision, owner and review date. Record exclusions and dependencies. |
| All workstreams | T01 Set outcomes | T01.2 Define the measure and acceptance | 0 | Not started | Process designer | 2 Nov 2026 | Agree a baseline, target and sample records for each item. Keep useful app activity, GTM decisions and advisor review effort distinct. |
| All workstreams | T02 Audit existing assets | T02.1 Run both dashboards and n8n | 0.5 | Not started | Engineer | 2 Nov 2026 | Trace one record through each existing prototype. Mark live, simulated and missing connections. Reuse what works; revise estimates if gaps are larger. |
| App adoption | T02 Audit existing assets | T02.2 Confirm app and release access | 0.5 | Not started | Engineer | 2 Nov 2026 | Confirm build access and the existing TestFlight / Android APK routes. Pranav resolves access blockers. Do not assume remote updates are supported. |
| All workstreams | T03 Verify measurement | T03.1 Agree definitions and source mappings | 0 | Not started | Process designer | 3 Nov 2026 | After T01–T02. With Pranav, define app usage and outcome windows; GTM collections, unpaid invoices and campaign rules; student inputs and denominators. |
| All workstreams | T03 Verify measurement | T03.2 Reconcile samples to displayed metrics | 1 | Not started | Engineer | 3 Nov 2026 | After T01–T02. Verify collection and calculation. Separate focus, game and idle time where measurable. A Streak visit is not an achieved streak; missing feedback is not a negative rating. |
| App adoption | T04 Prepare user evidence | T04.1 Speak with five students | 0 | Not started | Pranav | 3 Nov 2026 | After T01. Ask about the first focus attempt, daily targets and recording progress. Check whether students already have work set up. Confirm post-Diwali study days and availability. |
| All workstreams | T04 Prepare user evidence | T04.2 Observe staff tasks and prepare fixtures | 0 | Not started | Process designer | 3 Nov 2026 | After T01. Ask sales and an advisor to demonstrate a real decision or weekly review. Prepare source examples and expected results with existing business stakeholders. |
| App adoption | T05 Build focus guidance | T05.1 Explain the commitment before Start | 1.5 | Not started | Engineer | 5 Nov 2026 | After T03–T04. Use verified behaviour to explain app switching, calls and screen locks before commitment. Keep duration, blocking and reward redesign outside this first slice. |
| App adoption | T05 Build focus guidance | T05.2 Add measurement and identify the build | 0.5 | Not started | Engineer | 6 Nov 2026 | After T05.1. Demonstrate the complete flow and identify the candidate version. These two build days exclude device QA, review wait, distribution and student installation. |
| App adoption | T06 Test and release | T06.1 Test the interruption paths separately | 0.5 | Not started | Engineer | 10 Nov 2026 | After T02, T05. Check app switching, calls and screen locks on supported devices. Record actual outcomes; fix misleading guidance before distribution. |
| App adoption | T06 Test and release | T06.2 Package, submit and track approval | 1 | Not started | Engineer | 11 Nov 2026 | After T06.1. Use the confirmed release route; record review status, version, install instructions and faulty-release response. 11 Nov is the preparation target, not promised approval. |
| App adoption | T06 Test and release | T06.3 Run the unaided student check | 0 | Not started | Process designer | 13 Nov 2026 | After T05. A new student can find Focus, understand the commitment and act unaided. If holiday availability prevents this, finish at T08 before the pilot. |
| GTM tracker | T07 Validate GTM | T07.1 Connect Meta, Razorpay and ClickUp | 1.5 | Not started | Engineer | 13 Nov 2026 | Sources: Meta Ads (campaign spend, CTR and frequency), Razorpay and ClickUp. Trace programme/workshop leads through invoice, collection and onboarding. After T02–T04; follows T06 in the engineer schedule. |
| App adoption | T08 Check pilot readiness | T08.1 Verify installation and reporting | 0.5 | Not started | Engineer | 16 Nov 2026 | After T04, T06. Approval must be complete where required. Record installed versions and verify one sample session/outcome appears once. Move the pilot if a gate is incomplete. |
| App adoption | T08 Check pilot readiness | T08.2 Confirm usability and participant dates | 0 | Not started | Process designer | 16 Nov 2026 | After T06 and alongside T08.1. Complete the unaided check. Pranav confirms availability; record each actual start and expected study days. No observation starts before readiness. |
| GTM tracker | T07 Validate GTM | T07.2 Reconcile figures and expose exceptions | 1 | Not started | Engineer | 17 Nov 2026 | After T07.1; follows T08.1. Check selected periods, unpaid invoices, trial renewals and agreed campaign rules. Surface missing/stale/rejected inputs; label unavailable creative or landing-page measures. |
| GTM tracker | T07 Validate GTM | T07.3 Accept the figures and staff decision | 0 | Not started | Process designer | 17 Nov 2026 | After T07.2. Repeated ₹3,999 payment counts once; unpaid invoice stays outstanding. A staff user can explain a figure and the action it supports unaided. Pranav accepts the result. |
| Student dashboard | T10 Complete student pilot | T10.1 Connect individual and cohort views | 1.5 | Not started | Engineer | 18 Nov 2026 | After T02–T04 and T07 implementation. Capture one weekly-review record once; show it in individual and cohort views for the correct period. Start from the existing dashboard. |
| Student dashboard | T10 Complete student pilot | T10.2 Check sources and automation | 1 | Not started | Engineer | 19 Nov 2026 | After T10.1. Validate delivery quantity, feedback quality and student performance with response counts and denominators. Confirm n8n uses the agreed identities and reporting periods. |
| App adoption | T09 Run focus pilot | T09.1 Observe use without coaching | 0 | Not started | Pranav | 20 Nov 2026 | After T08; target 16–20 Nov. Record completion, abandonment, help required and installed version. Separate new/existing users and absence. Stop further rollout for a material failure. |
| Student dashboard | T10 Complete student pilot | T10.3 Handle missing, late and corrected data | 1 | Not started | Engineer | 23 Nov 2026 | After T10.2. Missing wearable data remains missing. Late/corrected records reach the right week without duplicate entries or false zeroes. Complete these checks before accepting the pilot. |
| Student dashboard | T10 Complete student pilot | T10.4 Run an advisor weekly review | 0 | Not started | Process designer | 23 Nov 2026 | After T10.3. The advisor uses the view without recreating the same record elsewhere. Record preparation time, coverage and help required. Pranav reviews the outcome. |
| Operations | T12 Practise recovery | T12.1 Test duplicate, stale and replay paths | 1 | Not started | Engineer | 24 Nov 2026 | After T07, T08, T10. Run the Acceptance checks scenarios; reconcile before/after totals. A failed record has an owner and can recover without repeating completed work. |
| Operations | T12 Practise recovery | T12.2 Let the operator run a recovery | 0 | Not started | Process designer | 24 Nov 2026 | After T12.1. Follow the routine recovery instructions without editing code. Replaying input must not resend old renewal or task reminders. Keep evidence with the workflow export. |
| Operations | T13 Fix and hand over | T13.1 Fix priority defects and repeat checks | 1 | Not started | Engineer | 26 Nov 2026 | After T07, T10 and relevant T12 results. Fix the highest-impact issues, repeat affected checks and keep unresolved limitations visible. Pranav controls scope. |
| App adoption | T11 Review focus follow-up | T11.1 Review each full seven-day window | 0 | Not started | Pranav | 27 Nov 2026 | After T09. With the designer, report repeat-use counts, denominators and missing follow-up. Include holidays/absence and equivalent comparison windows. Small-sample findings are directional. |
| Operations | T13 Fix and hand over | T13.2 Package the operating handover | 1 | Not started | Engineer | 27 Nov 2026 | After T13.1. Name the operator, fallback and escalation route. Link working views, definitions, release evidence, SQL/schema, n8n export and recovery steps. |
| Operations | T13 Fix and hand over | T13.3 Check that a colleague can operate it | 0 | Not started | Process designer | 27 Nov 2026 | After T13.2. Use the flow and resolve a routine exception without code changes. Check access to the linked documents; record any remaining help required. |
| All workstreams | T14 Review outcomes | T14.1 Prepare evidence and maintenance costs | 1 | Not started | Engineer | 30 Nov 2026 | After T07, T10–T11, T13. Support Pranav with reconciled figures, missing-data limits, defects and ongoing operating effort. Do not label a late pilot successful before its window ends. |
| All workstreams | T14 Review outcomes | T14.2 Decide Keep, Improve or Stop | 0 | Not started | Pranav | 30 Nov 2026 | After T14.1. Consider user benefit, data quality and operator effort. If inconclusive, run one further week with a specific question; otherwise change the test or stop. Date the decision. |

## Weekly capacity

| Week start | Week end | Main delivery | Engineer days | Weekdays | Reserve days | Review / decision |
| --- | --- | --- | --- | --- | --- | --- |
| 2 Nov 2026 | 6 Nov 2026 | Access/reuse audit; verify metrics; narrow Focus guidance build. | 4 | 5 | 1 | Pranav: outcomes and five interviews. Designer: definitions, mappings and the first unaided flow check. |
| 9 Nov 2026 | 13 Nov 2026 | Focus device QA and release preparation; begin GTM connection. | 3 | 5 | 2 | Confirm approval status and post-Diwali availability. Use this week for internal work where staff are available. |
| 16 Nov 2026 | 20 Nov 2026 | Verify Focus installs; finish GTM; start student dashboard sources and views. | 4 | 5 | 1 | Target Focus pilot: 16 Nov, only after release, usability and install gates. Accept GTM figures and the staff decision. |
| 23 Nov 2026 | 27 Nov 2026 | Finish student-data checks; test recovery; priority fixes and operator handover. | 4 | 5 | 1 | Advisor weekly review; seven-day Focus follow-up. Respect actual participant start dates and missing follow-up. |
| 30 Nov 2026 | 30 Nov 2026 | Review evidence and operating effort. | 1 | 1 | 0 | Pranav: Keep, Improve or Stop. A late pilot may need a later outcome review. |

**Total:** 16 planned engineer days across 21 weekdays, leaving 5 reserve days. Approval or release wait adds elapsed time, not engineer effort.

## Acceptance and recovery checks

These are planned checks, not results claimed for the current prototypes. The Focus release, usability and installation checks must pass before its pilot starts.

| ID | Area | Check / linked task | Pass condition | Owner | Due | Result |
| --- | --- | --- | --- | --- | --- | --- |
| C01 | All workstreams | T03 · Definitions and sample reconciliation | Baselines, windows, identities and denominators are agreed; displayed sample figures reconcile. Streak visits and achieved streaks stay distinct. | Process designer | 3 Nov 2026 | Not run |
| C02 | App adoption | T06 · Interruption behaviour | App switching, calls and screen locks are tested separately; pre-start guidance describes verified behaviour. | Engineer | 10 Nov 2026 | Not run |
| C03 | App adoption | T06/T08 · Unaided first use | A new student can find Focus, understand the commitment and act without coaching. Finish before the pilot if unavailable during 9–13 Nov. | Process designer | 16 Nov 2026 | Not run |
| C04 | App adoption | T08 · Release and installation | Required approval is complete; candidate version and each pilot installation are recorded. One sample session and outcome reach reporting. | Engineer | 16 Nov 2026 | Not run |
| C05 | GTM tracker | T07 · Journey, totals and action | Meta campaign spend, CTR and frequency reconcile for the selected period. Programme/workshop lead → invoice → payment → onboarding reconciles; unpaid invoices, trial renewals and campaign rules work. Staff can explain the action unaided. | Process designer | 17 Nov 2026 | Not run |
| C06 | Student dashboard | T10 · Weekly-review journey | One captured record reaches individual/cohort views for the correct week. Quantity, feedback and performance show coverage and denominators. Advisor preparation and help required are recorded. | Process designer | 23 Nov 2026 | Not run |
| F01 | GTM tracker | Duplicate payment | Receive the same ₹3,999 workshop payment twice; the collection remains ₹3,999 and the payment identity is preserved. | Engineer | 17 Nov 2026 | Not run |
| F02 | App adoption | Duplicate session outcome | Repeat one focus-completion event; reporting still contains one completed session. | Engineer | 16 Nov 2026 | Not run |
| F03 | All workstreams | Late or unavailable source | Show the last successful update and mark stale data. An unavailable feed does not become zero revenue or zero activity. | Engineer | 24 Nov 2026 | Not run |
| F04 | Student dashboard | Missing feedback or wearable reading | Show the gap and available coverage. No feedback is not a negative rating; no device reading is not zero performance. | Process designer | 23 Nov 2026 | Not run |
| F05 | All workstreams | Invalid or corrected record | Expose the rejected record and responsible owner. Correct and replay into the intended period without duplicating the original. | Engineer | 24 Nov 2026 | Not run |
| F06 | Operations | Partial processing or replay | Stop a batch partway through, retry and reconcile before/after results. Completed work is not repeated. | Engineer | 24 Nov 2026 | Not run |
| F07 | Operations | Repeated reminder | Replay an input that previously sent a renewal/task reminder. A delivery record prevents the same reminder being sent again automatically. | Process designer | 24 Nov 2026 | Not run |
| F08 | App adoption | Faulty app release | Document how to stop further rollout and identify affected versions. Disable only if supported; otherwise prepare a corrected build and verify installation. | Engineer | 13 Nov 2026 | Not run |
| F09 | All workstreams | Confusing flow | The relevant teen, parent or staff user can find the flow, understand it and act unaided. Fix confusing steps before expanding use. | Process designer | 23 Nov 2026 | Not run |
| C07 | Operations | T13 · Operator handover | A colleague can use the flow and handle a routine exception without editing code. Owner, fallback, escalation and working document links are recorded. | Process designer | 27 Nov 2026 | Not run |
| C08 | All workstreams | T14 · Outcome window and decision | Use actual pilot starts and complete follow-up windows. Report denominators and missing data; record Keep, Improve or Stop and the next review date. | Pranav | 30 Nov 2026 | Not run |

The workbook also has editable evidence and issue-link cells for each check.
