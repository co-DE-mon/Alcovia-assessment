# Alcovia student tracker

I built this for the weekly student review described in Problem 4. It brings cohort progress and individual student records into one view, so you can see where the programme is falling behind and open the records behind each number.

I’ve used **synthetic data throughout**, with `DEMO-` IDs and a default reporting date of **24 October 2026**. The [dashboard](https://alcovia-assessment-wr3mxh9irsdkorfvkdxvrf.streamlit.app/) and connected data-flow demo work on this data. I haven’t connected them to live Alcovia/ClickUp data.

To inspect a number, open its records from the overview or cadence page, then select a row. Student rows open the student profile and its source tables; event rows open attendance and feedback, and group rows open their events. The daily trend opens that day's events and focus sessions. The Students and Data health tables use the same row selection. All detail views keep the selected reporting date.

## What it covers

I’ve organised the dashboard around the brief’s three questions: **Conducted** — did Alcovia deliver it? **Liked** — did students value it? **Performed** — how did the student do?

| Cadence | Activities covered | What the three lenses measure |
|---|---|---|
| Daily | Timetable, 8pm quiz, focus time, active minutes and recovery | Coverage and participation; completion/connection proxies; on-time quiz starts, completed focus time, to-do adherence, strain and sleep. |
| Weekly | Academic roadmap, advisor inputs and academic sessions | Study plans and session delivery; roadmap/session ratings; task completion, deadlines, study-hour accuracy, syllabus pace and chapter readiness. |
| Monthly | Workshops, pods, peer sessions, mentor calls and personal branding | Held vs expected/scheduled; feedback and workshop NPS, with clip reach as a branding proxy; attendance and shoots published. |
| Quarterly | Podcast, competition prep, parent-child bonding, out-of-city trip, social work, entrepreneurship and summer program closure | Delivery, group formation and startup-plan coverage; activity/theme ratings; attendance, publication, competition entry, milestones and applications submitted. |
| Roadmaps | Career, personal, academic, syllabus completion and rigour | Plans set and advisor reviews completed; roadmap check-in ratings or chapter-activity proxy; completion, deadlines, syllabus pace, exam targets and chapters taken through all five stages. |

Start with **Overview** to see which students need attention, where engagement drops, the biggest gaps and whether the data is fresh. From there, you can open a cadence page to separate delivery, feedback and performance for each activity. **See the records** shows what contributed to a KPI. **Students** lets you filter by advisor and open a student’s profile. **Data health** shows failed or partial runs and whose Whoop data has stopped arriving.

You can move the as-of date through the last **60 days** of demo history. I’ve used a rolling **30-day** window for daily, weekly and monthly activities, and the quarter so far for quarterly activities and roadmaps. The page names group the activities; they don’t mean each page has a different reporting window. Academic quarters start in March, June, September and December. All calculations use the selected date and IST timestamps.

## Approach and metric choices

I’ve used Streamlit and DuckDB, so you can run the prototype without setting up a separate backend or database service. On first use, the app generates a temporary database from a fixed seed. The calculations are in SQL; [scorecard.py](scorecard.py) selects the **88 displayed KPIs** and applies the status rules. I’ve kept targets in [config.yaml](config.yaml), so they can be changed in one place.

I’ve kept the student list alongside the cohort view because an average can hide the child who needs the weekly conversation. For this demo, I flag a student under **Needs attention** when at least two of these warning signs apply:

- No quiz started in the last seven days, **only if a quiz was held in that window while the student was enrolled**.
- No completed focus minutes in the last seven days.
- Syllabus completion below 80% of the expected cumulative pace.
- Fewer than 80% of roadmap items due **this quarter** completed by their deadline, counting late completions as misses. This spans all roadmap categories and levels.
- Fewer than half of to-dos due in the last 30 days completed.

I don’t flag a missing syllabus record as poor progress, or a student with nothing due as having missed a deadline. Students enrolled for fewer than 30 days are marked new, although they can still be flagged. When I show “Last active”, I mean their latest quiz start, focus-session start (including failed sessions), or completed to-do update—not an app open. I’d use these flags to guide the review; they aren’t a validated risk score.

| Success metric from the brief | Current calculation |
|---|---|
| Task completion rate | Completed to-dos / to-dos due in the selected period. |
| Deadline adherence | To-dos completed by their due date / completed to-dos due in the period. `updated_at` stands in for completion time because a dedicated completion timestamp is unavailable. |
| Time estimation accuracy | `max(0, 1 − abs(actual − expected) / expected)`, averaged across measured student-subjects. Expected hours = the quarter's estimate × the share of the quarter elapsed at the latest snapshot. Zero actual or expected hours is treated as unmeasured. |
| Chapter readiness | Average stage reached / 5 across chapters planned up to the selected month. The five stages represent reading, notes, practice, a timed paper and exam readiness. |
| Monthly rigour adherence | Chapters reaching stage 5 / chapters planned for the selected month. The roadmap page separately shows closed months so unfinished current-month work does not dominate that view. |

For the demo, I’ve marked a KPI **on track at 80% or above**, **watch from 50% to below 80%**, and **off track below 50%**. I divide ratings by 5, so a 4/5 rating meets the on-track line. For workshop NPS, I average the value supplied on each event and divide by 10. I’m not calculating a fresh Net Promoter Score from promoter/detractor responses.

I cap displayed KPI shares at 0–100%, while keeping the raw counts visible when delivery exceeds a target. Each scorecard cell averages its available KPIs with equal weight. An activity card uses its weakest eligible KPI instead. The overview’s on-track count is therefore a count of measurements, not a single student-progress score. I’ve left current-month rigour adherence visible but excluded it from biggest-gap rankings because the month is still unfinished.

I show **no data** when a measurement or denominator is missing. A genuine zero still stays zero—for example, an enrolled student with no completed focus sessions. These thresholds and status rules are assumptions for the demo; I’d confirm them with Alcovia before using them operationally.

## Assumptions and limits

### Targets I’ve used in the demo

| Setting | Current value and basis |
|---|---|
| Focus | 60 completed minutes per student-day. Provisional; separate from Problem 1's 30-minute app-usage objective. Failed minutes do not count toward the target. |
| Quiz | One per day; 8pm from the brief, with an inclusive 15-minute entry window from the event's scheduled time. “Regular” means starting at least 4 of the last 7 **held quizzes**, excluding students enrolled for fewer than 7 days. The 4-of-7 rule is provisional. |
| Wellness | Strain band 8–16 inclusive; sleep target 8 hours; low recovery below 33%. Illustrative values, not individualized health targets. |
| Syllabus | 25% of the year's chapters per quarter, distributed evenly through the quarter. The brief suggests this fallback when exam syllabi are unclear; the prototype applies it throughout. On track means at least 80% of that cumulative pace. |
| Sessions | 2 academic, 4 career and 2 personal sessions per student per month in the demo configuration. Targets by grade and the mapping of personal to Mindset/DeepWork need confirmation. |
| Monthly activities | 2 workshops per cohort, 1 mentor call per student, 1 peer session per student in pairs, and 1 pod per group of 5. The peer target is provisional. These student workshops are separate from the paid GTM workshops. |
| Branding | A posted clip meets the reach proxy at 1,500 views. Provisional, and not evidence that the student liked the activity. |
| Connections and freshness | Calendar/wearable retention is measured at day 30 after connection. Whoop is considered syncing with a reading no more than 2 days old and no disconnection. A source is stale after more than 36 whole hours without a fully successful run; partial runs do not reset that clock. |

### Who is counted

When I say “active student”, I mean enrolled on that date, up to but excluding their leaving date. I don’t mean they opened the app. For daily reach, I count student-days, so joining or leaving changes that day’s denominator. Most other cohort metrics use students enrolled at the selected end date. Event attendance follows the invitation list, while academic-session attendance uses known attendance at held sessions. You’ll see different rates where those populations differ.

I estimate months as `days / 30.4375` and use end-date enrollment for student/group delivery targets. That is an approximation: it doesn’t fully account for mid-period joins, departures or holidays. For held-versus-scheduled delivery, I count held and cancelled events; events still marked planned stay outside that denominator. I pool tasks and chapters for cohort rates, so a student with more records carries more weight. Wearable performance only uses days with a reading, so I’d read it alongside coverage before drawing a conclusion.

### Approximations that affect interpretation

- **Timetable and advisor inputs:** I use a to-do due that day as a stand-in for a logged timetable. Same-day adherence requires completion on the due date, while deadline adherence also allows early completion. Both use `updated_at`, which later edits can change. For “Students filling inputs”, I count a manual to-do created or a completed task updated in seven days. That doesn’t tell me who made the update. The weekly advisor metric tracks assigned to-dos. The separate monthly advisor checklist tracks targets, guardrails, input cadence, deadline messages, tutor escalation, catch-up sprints and roadmap/syllabus/rigour reviews; those duties need explicit done and not-done records.
- **Feedback:** I use behaviour proxies for daily “Liked” values. For focus, I use the share of sessions **not given up** and keep app-switch failures separate; a product rule causing a session to fail doesn’t tell me the student disliked it. I haven’t implemented phone lockdown or verified the brief’s whitelisted-call behavior through this tracker. Calendar/wearable retention means still connected **at day 30**, not necessarily today; reconnect cycles are not modeled. Academic-session feedback currently pools session forms across several session types. Career, personal and syllabus ratings reuse different questions from the same roadmap check-in, rather than separate surveys. Theme ratings for social work, entrepreneurship and summer support are proposed; parent feedback and students' own LinkedIn posts are not captured.
- **Wellness:** I’ve used Whoop strain under “Active minutes”, so this isn’t a measurement of exercise minutes. I haven’t established Apple, Samsung or Garmin support. Manual sleep contributes to sleep metrics but never becomes measured strain or recovery. A missing wearable reading is unknown, not zero physical activity.
- **Roadmaps:** I count coverage when there is at least one goal of that type created by the end date, without requiring a current-quarter plan. The “monthly milestones” coverage KPI does not filter to monthly goals. For career performance, I currently show completed items / items created. This still differs from the brief’s binary done/not-done outcome per student. Undated goals are excluded from due/late calculations; the poll assigns annual goals a 31 December deadline. First-observed goal creation/completion dates are approximations, not recovered historical timestamps.
- **Chapter rigour:** I require five consecutive stages in the demo loader: `Done` tasks for reading and notes, practice with a latest Worksheet score **above 70%**, explicit completed/within-time paper evidence, then a latest Mocktest score **above 80%**. `SignificantlyDone` is incomplete; `NotRequired` is unresolved, not automatically passed. Planned month and stage-change timestamps need explicit evidence. I haven’t assumed that a Mocktest proves a paper was timed, or that a partially completed task has passed a stage.
- **Outcomes:** I can show attendance, publication and application submission, but I wouldn’t use those alone to claim learning or soft-skill gains. Competition entry is entries / records with known attendance, so repeated entries can count more than once. Summer applications use distinct invitees to non-cancelled support sessions; an invitee without a recorded submitted/accepted outcome counts as not submitted. Family attendance and parent satisfaction are not independently modeled. Exam targets need manual input, an agreed score scale and exam/year identity; the headline currently selects formative exams only.

### Historical views

I compare each KPI with its value 30 days earlier and show the difference in percentage points. I hide the comparison if the earlier window starts before recorded event history, or if a quarterly KPI would cross a quarter boundary. Even within the same quarter, quarter-to-date comparisons cover different elapsed lengths.

There’s a limit to how far you can treat the date picker as a historical view. Tasks, chapter stages, advisor duties, student details and exam scores can still reflect their latest stored state. The exam table has no exam date/year, and clip views/shares come from the latest sync. Some profile sections show all roadmap items and exam scores, including records beyond the selected date. Event ratings follow the held event’s date and can include later submissions; roadmap and entrepreneurship ratings use submission dates. I haven’t built a fully versioned audit trail.

## Data capture with minimal manual entry

For data capture, I’ve structured the imports around tasks, focus, study hours, goals and syllabus history. Session records include attendance and optional ClickUp links. Advisor duties, score targets, additional activities and outcomes still need actual ClickUp field/student mappings. The remaining manual work would be recording those duties and outcomes where there is no verified source, rather than re-entering each student’s app activity.

The demo validates the mapping and calculations on sample data. Before live use, I’d confirm the production input contracts, cohort access and join/leave roster with the team. I’d also agree which records should come from ClickUp and which should come from the product, so the same activity isn’t imported twice.

The connected demo runs through this path:

```text
Synthetic source responses → manual n8n workflow → Postgres
                          → validated DuckDB snapshot → Streamlit
```

In [student-tracker-demo.json](../n8n/student-tracker-demo.json), I’ve connected the source mappers using a shared two-student cohort, with explicit manual samples for advisor duties and exam targets. The writes are atomic, and replay is checked. The exporter validates the full snapshot before replacing the previous file; you can then use **Refresh data** to reload it. I leave `ingest_log` empty for this synthetic import, so Data health shows stale sources. The dashboard still runs its queries in DuckDB; it doesn’t query Postgres directly.

I’ve kept the separate daily poll inactive because its source coverage is still partial. The [source audit](../n8n/audit/source-coverage.json) marks 6 of the 88 KPI input mappings loaded, 26 partial and 56 missing. Those numbers describe that poll, not the full synthetic demo or live readiness. Its proposed run time is 23:55 IST, with a seven-day syllabus-history reread. The current focus loader can’t recover session rows after that capture time or on a missed day; the known history response only gives daily totals. Calendar retention also needs a status loader, and connection retention needs a full observation window.

Before I’d use this on live data, I’d need to resolve cohort permissions, populated source responses, submitted-feedback access, corrections/deletions and missed-run recovery. Upserts prevent duplicate imports, but don’t give us a complete history by themselves. Snapshot validation checks roster/event links and schema constraints; other Postgres writers and concurrent imports still need safeguards. Alerts and production scheduling also need configuration. The [n8n README](../n8n/README.md) has the integrated-demo instructions.

## Run locally

To run it, use **Python 3.12 or newer** and start from `student-tracker/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

I’ve seeded **90 days** of daily history with seed **42** and 20 synthetic student records; 19 are enrolled at the default end date. The advisor assignments, targets and examples are illustrative. Try **DEMO-S17** for prolonged inactivity, **DEMO-S01** for poor recent recovery, and Data health for a stale Whoop feed. I’ve included all three quarterly themes together so you can review their coverage; this isn’t an agreed programme calendar.

You don’t need credentials or external connections for the default demo. **Refresh data** clears cached results/configuration and reopens a configured snapshot, or rebuilds the same seeded database when no snapshot is configured. It doesn’t run n8n or fetch fresh source data. If you change configuration or fixtures used by a workflow, regenerate and re-import it—the imported workflow doesn’t read the repository. To run the checks:

```bash
python -m pytest tests -q
```

To run the connected synthetic demo, from the repository root, with Podman and the n8n/Postgres images available:

```bash
python3 -B n8n/tests/integration.py --only 13 --snapshot-output /tmp/alcovia-student-tracker-demo/student.duckdb
ALCOVIA_STUDENT_SNAPSHOT=/tmp/alcovia-student-tracker-demo/student.duckdb student-tracker/.venv/bin/streamlit run student-tracker/app.py --server.address 127.0.0.1
```

For a disposable Postgres container that already holds demo data, publish a fresh snapshot with:

```bash
student-tracker/.venv/bin/python student-tracker/snapshot.py --container YOUR_DEMO_CONTAINER --database student --user postgres --as-of 2026-10-24 --output /tmp/alcovia-student-tracker-demo/student.duckdb
```

I’ve limited the exporter to an explicit synthetic `DEMO-` cohort. It reads all 16 tables in one repeatable-read transaction and keeps the previous snapshot if validation fails. The snapshot supplies its own as-of date. If a configured snapshot is missing or invalid, the app raises an error instead of switching to generated data. The tests cover metric calculations, date boundaries, seeded examples, drill-down reconciliation, snapshots and page rendering. Browser layout and public hosting still need separate verification.

## Code and remaining work

- [Database schema](sql/schema/student.sql) and [metric queries](sql/metrics/): definitions, grain, source tables and edge cases alongside each query.
- [Demo generator](seed/generate.py), [dashboard pages](views/) and [tests](tests/).
- I’ve kept the Definitions page tied to the KPI catalogue and assumptions below, so this README is also the dashboard’s reference. The SQL and current loader/configuration rules define the implemented behavior.

The entry point for Streamlit Community Cloud is `student-tracker/app.py`. The working synthetic prototype doesn’t establish live ingestion. I’ve kept team allocation, delivery dates from 1 November and the advisor’s scope for non-tuition subjects outside this README; those need to be covered in the overall executive writeup.

## KPI catalogue

Here’s the full list of the **88 headline KPIs** I’ve included, grouped by activity and the three lenses. You can trace each one through the `file`/`query` fields in [scorecard.py](scorecard.py) to its [SQL definition](sql/metrics/). Supporting queries also show quiz scores, recovery percentages, competition stages and application acceptances; those aren’t all separate headline KPIs.

| Cadence / activity | Conducted | Liked | Performed |
|---|---|---|---|
| Daily / 8pm quiz | Quizzes held / days | Quizzes finished / started (proxy)<br>Regular quiz takers (proxy) | Started inside the entry window |
| Daily / Focus time | Student-days with a session | Sessions not given up (proxy) | Student-days at the focus target |
| Daily / Timetable | Student-days with a to-do due | Calendar still connected (proxy) | To-dos done on their due date |
| Daily / Active minutes | Student-days with wearable strain | Wearable still connected (proxy) | Strain inside the target band |
| Daily / Recovery | Student-days with a recovery reading | Whoop students still syncing (proxy) | Sleep at or above target |
| Weekly / Academic roadmap | Study-hour plan set | Roadmap check-in: pace of progress (average / 5) | Students on the syllabus pace<br>Task completion rate<br>Deadline adherence<br>Time estimation accuracy<br>Chapter readiness score<br>Monthly rigour adherence |
| Weekly / Advisor input | Advisor-assigned to-dos done | Academic session rating (average / 5) | Advisor-assigned to-dos done on time<br>Students filling in their inputs |
| Weekly / Academic sessions | Academic sessions held vs policy | Session feedback (average rating / 5) | Academic sessions attended |
| Monthly / Workshops | Workshops held vs expected | Workshop rating (average / 5)<br>Workshop NPS (/ 10) | Workshop attendance |
| Monthly / Pod session | Pods held vs expected | Pod rating (average / 5) | Pod attendance |
| Monthly / Peer session | Peer sessions held vs expected | Peer session rating (average / 5) | Peer session attendance |
| Monthly / Mentor call | Mentor calls held vs expected | Mentor call rating (average / 5) | Mentor call attendance |
| Monthly / Personal branding | Shoots held / scheduled | Posted clips reaching the view target (proxy) | Shoots posted |
| Quarterly / Podcast | Podcasts held / scheduled | Podcast rating (average / 5) | Episodes posted |
| Quarterly / Competition prep | Students assigned a competition | Competition rating (average / 5) | Assigned students who entered |
| Quarterly / Parent-child bonding | Parent workshop held | Parent workshop rating (average / 5) | Parent workshop attendance |
| Quarterly / Out-of-city trip | Trip held | Trip rating (average / 5) | Trip attendance |
| Quarterly / Social work | Social work activities held / scheduled<br>Groups formed | Social work rating (average / 5) | Social work attendance<br>Theme milestones done by deadline |
| Quarterly / Summer program closure | Application support sessions held / scheduled | Summer support rating (average / 5) | Students who submitted an application |
| Quarterly / Entrepreneurship | Students with a startup plan | Entrepreneurship rating (average / 5) | Theme milestones done by deadline |
| Roadmaps / Career | Students with a career roadmap | Check-in: confidence the roadmap leads to the goals (average / 5) | Career roadmap items done |
| Roadmaps / Personal | Students with monthly milestones | Check-in: how invested students feel (average / 5) | Milestones done by deadline |
| Roadmaps / Syllabus completion | Monthly syllabus reviews done | Roadmap check-in: pace of progress (average / 5) | Chapters covered against the syllabus pace |
| Roadmaps / Rigour of completion | Rigour checks done by the advisor<br>Sprints made when a timeline was missed | Students still working through their chapters (proxy) | Chapters from past months fully complete |
| Roadmaps / Academic | Students with an academic roadmap<br>Advisor inputs done | Roadmap check-in rating (average / 5) | Academic items done by deadline<br>Exam scores at or above target |

## Source and schema reference

This is the data contract behind the tracker: what each table needs, how the demo uses it and what I’d confirm before a live connection. The synthetic examples exercise the imports and KPI calculations; production mappings still need validation with the team.

| Destination | Required inputs and mapping | Remaining limit |
|---|---|---|
| `students` | Stable student ID, name, grade/board, advisor/counsellor links and enrollment dates. | A reliable leaving date is needed; a missing roster row is not proof of departure. Email is not retained. |
| `staff` | Stable staff ID, name and advisor/career-counsellor role. | Assignments and roster completeness need confirmation. |
| `students` connection dates | Connection state and dated connect/disconnect transitions. | Dates recorded when first seen are approximations. Calendar status is not loaded. |
| `focus_sessions` | Session ID, student ID, start time, actual minutes, outcome and failure reason. | Planned duration is nullable and unused by the metrics. Current capture is limited to the reporting day. |
| Focus history | Daily date, total minutes, focus score and session count. | Daily totals cannot reconstruct individual sessions or their failure reasons. Session-level backfill remains unresolved. |
| `todos` | Task ID, student ID, source, title, due date, status, creation and update time. | Update time is only an approximation of completion time. |
| `events` + `event_attendance` (sessions) | Session identity/type/start, cancellation, optional ClickUp link, invited students and attendance. | The poll infers held from a past start time unless cancelled. Present/Absent/Upcoming map to true/false/NULL. A single-student import does not establish the cohort invitation list. |
| `events.nps_score` | Event-level workshop score on a 0–10 scale; policy, scheduled and attended totals for reconciliation. | The score's meaning and session policy by grade need confirmation. |
| Quiz events and `quiz_attempts` | Separate delivery records plus student attempts: quiz ID, topic, scheduled time, status, start/completion time, score and question count. | Taken-only history cannot distinguish skipped quizzes from quizzes that were never held. The demo explicitly supplies delivery evidence. |
| `feedback` | Submitted ratings linked to the student/event, with question ratings and supplied composite. | Pending requests are not submitted ratings. Social work, entrepreneurship and summer program have no form wired into this integration; their collection is proposed. |
| `roadmap_items` | Annual, quarterly and monthly goals with stable IDs, category, creation/due/completion dates. Venture maps to entrepreneurship. | `social_work` has no category mapping in the current goal importer. First-seen dates and the meaning of a startup plan need agreement. |
| `chapter_progress` | Chapter/student/subject/quarter identity, planned month, stage evidence and stage-change time. | Timed-paper proof and activity timestamps must be explicit. The demo uses a supplied plan and evidence rather than inferring them from unrelated fields. |
| `study_hours` | Estimated and actual hours by student, subject and quarter, plus weekday/weekend plans and snapshot date. | Running totals need snapshots. Subject names need normalization; fractional-hour rounding needs review. |
| `syllabus_daily` | Student/date, chapters completed and total chapters. | Confirm stable denominators and exam-specific syllabus before replacing the fallback pace. |
| `exam_targets` | Student, subject, exam type, target and actual score on an agreed scale. | Targets currently use explicit manual inputs; repeated exams and exam/year identity need a schema extension. |
| `wearable_daily` | Student/date/source, strain, recovery and sleep, with explicit units. | Current automated coverage is Whoop. Other-vendor demos supply sleep only. Manual sleep must not become measured strain or recovery; populated production inputs need validation. |
| `advisor_inputs`, additional events/outcomes | Checklist duties, group memberships, publishing, milestones and application outcomes. | Quarterly items (podcast, competition, parent workshop, trip, themes, summer program) need explicit source mappings. Real ClickUp list/field IDs and ownership remain unresolved. |
| `ingest_log` | Run/source, timestamps, status, rows and classified error, written by ingestion. | Synthetic cohort imports leave it empty; default-demo runs are illustrative. |

I’ve used **16 data tables**. Activities share an `events` table, with attendance keyed by event and student. Quizzes, feedback, focus, wearables and roadmaps have their own record structures. Study-hour snapshots and syllabus history are dated, while chapter progress and to-dos hold mutable state. The [schema](sql/schema/student.sql) gives the columns and keys.

In the mapping layer, I convert zoned UTC timestamps to IST before deriving dates, while keeping source calendar dates as dates. I handle both `data` wrappers and bare lists, keep source IDs and map statuses explicitly. Invalid rows or failed reads shouldn’t become an empty successful load. I retain source metadata where origins differ and omit credentials, email and free-text feedback comments from the demo data.

Before rollout, I’d agree the input contract for each source: date boundaries, academic-year/quarter context, pagination, statuses, correction rules and cohort permissions. Reading data, requesting feedback and triggering a backend sync are separate operations; a submission or sync action is not a substitute for a readable history.

## Assumption reference index

I’ve kept the **A1–A66** references used in the code comments so you can trace an assumption without opening another document. This index points to the current rules above, including where an earlier approximation has been superseded. Targets and mappings need agreement before being applied to the whole cohort.

| References | Assumption or current disposition |
|---|---|
| A1, A3, A40 | To-dos approximate a timetable; update time approximates completion. No calendar-block adherence measurement. |
| A2, A5, A32 | Daily quality uses behavior proxies; give-up differs from app-switch failure; quiz participation is emphasized over score. |
| A4, A42, A51 | Daily quiz/entry-window and regular-taker rules; exclude newly enrolled students from regularity; delivery requires evidence independent of attempts. |
| A6, A18, A62 | Focus/wellness targets, peer-session frequency and branding view target are provisional. |
| A7, A8, A36, A37 | Current automated wellness coverage is Whoop; missing readings remain unknown. Summer feedback and phone-lockdown/call behavior are not established by this integration. |
| A9, A44, A59 | The poll imports one student per run; cohort authorization and departure source remain unresolved. A missing roster row is not an inferred exit. |
| A10, A11, A14 | Cohort/staff counts are synthetic; advisor planned-workload assumption is unused. |
| A12, A27, A30, A58 | Goals approximate roadmaps; coverage and deadline rules above apply; career headline is item-based; missing due dates stay undated except the annual year-end approximation. |
| A13, A38, A55, A64 | Academic quarters start Mar/Jun/Sep/Dec; cumulative 25%-per-quarter pace, 80% tolerance, and pooled chapter pace. Old seed-quarter notes are superseded. |
| A15, A41 | Study-hour estimates are taken from the source; who set them is unknown. Accuracy is elapsed-quarter pace-based, not final estimate accuracy. |
| A16, A48, A65 | Current consecutive-stage demo contract governs chapter reduction; explicit planning/time evidence is required. Chapter activity proxies engagement; closed-month rigour complements current-month adherence. |
| A17, A33, A35, A56 | Brief/policy activity counts, five-student pods and fractional-month delivery assumptions. Per-grade policy and family attendance remain unresolved. |
| A19, A20, A34 | Branding-source mapping is inferred; own LinkedIn posts and workshop simulation/soft-skill performance are not captured. |
| A21, A22, A49, A52, A63 | Existing/proposed feedback kinds, session-source/attendance mapping, unconfirmed personal-session semantics, and shared roadmap check-in questions. |
| A23, A24, A25, A39, A61, A66 | Competition/application outcomes and theme milestones need owned records. Simultaneous themes, three startup milestones and four summer-support sessions are demo examples, not an agreed calendar. |
| A26, A29 | Recorded ownership: Alcovia organizes social-work groups; entrepreneurship is student-led. Academic advisor owns academic/personal plans; career counsellor owns career plans. Confirm operational ownership with Alcovia. |
| A28, A31 | Separate rigour review and monthly advisor checklist are proposed operating records, with duties explicitly marked done/not done. |
| A43, A45, A46, A47, A50, A53, A54, A60 | Explicit status mappings; first-observed dates; nullable planned focus time; capture/backfill limits; goals/targets/input proxies and daily-poll timing. See source reference and capture section. |
| A57 | Score scaling, averaging, status thresholds and two-warning attention rule are configurable demo choices. |
