# Alcovia n8n pipeline

Problem 4 of the Product, Systems & Analytics Lead assessment. The brief asks how the student dashboard will record data with minimal human intervention, and asks for systems that don't break. This folder is my answer to that part.

**All demo data is synthetic**, with `DEMO-` IDs. I've exported all 10 workflows **inactive**, with no credentials attached and the workflow timezone set to IST. Live Alcovia/ClickUp runs, alerts and hosting are still pending.

## What it covers

| Brief objective | What I built |
|---|---|
| Record data with minimal human intervention | A daily poll of the student app and a daily read of two ClickUp lists, both writing into one Postgres database. 12 of the 15 data tables load without anyone touching them. |
| Where the dashboard reads it | A nightly export that publishes a validated DuckDB snapshot, which the [student tracker](../student-tracker/README.md) opens. |
| Systems that don't break | Idempotent upserts, retries, rejected rows named in a run log, one `ingest_log` row per run, an error workflow and an atomic snapshot swap. |
| Sources outside the scheduled import | Manual demos for quizzes, chapter progress, wellness, other wearables and submitted feedback, plus one integrated demo that runs all of them together. |

```text
student app API (23:55 IST) --\
                               >-- n8n: map + check --> Postgres (upsert) --> ingest_log
ClickUp lists   (03:00 IST) --/                              |
                                                             v
                                   snapshot export (00:30 IST) --> DuckDB file --> student dashboard

any unhandled failure --> error workflow --> 'failed' row in ingest_log (+ email, off for now)
```

| Workflow | Trigger | What it does |
|---|---|---|
| [student-app-daily-poll.json](student-app-daily-poll.json) | 23:55 IST + Run now | Signs in as one student, makes 10 reads, maps them and upserts 10 tables. |
| [clickup-advisor-inputs.json](clickup-advisor-inputs.json) | 03:00 IST + Run now | Reads two ClickUp lists: advisor monthly duties and exam targets. |
| [ingest-error-handler.json](ingest-error-handler.json) | Error trigger | Error workflow for the two above (fixed id `ingestErrorHandler01`). Logs the failure; the alert email node is built but disabled. |
| [snapshot-export.json](snapshot-export.json) | 00:30 IST + Run now | Runs [snapshot.py](../student-tracker/snapshot.py) to publish the dashboard's DuckDB file, dated the previous IST day (the last full day the poll collected). |
| [student-tracker-demo.json](student-tracker-demo.json) | Manual | **Start here.** Loads a two-student sample cohort from every source in one atomic write. |
| `quiz-progress-demo.json`, `chapter-progress-demo.json`, `wellness-daily-demo.json`, `wearables-daily-demo.json`, `submitted-feedback-demo.json` | Manual | Separate demos for inputs not covered by the scheduled import. |

| Data | Tables | How it gets in |
|---|---|---|
| Profile, advisor link, Whoop connection, study-hour plan | `students`, `staff`, `study_hours` | Automatic, daily poll. |
| Focus sessions | `focus_sessions` | Automatic, but limited to the reporting-day records available at 23:55. |
| To-dos, goals / roadmap | `todos`, `roadmap_items` | Automatic, daily poll. |
| Workshops, pods, mentor calls and attendance | `events`, `event_attendance` | Scheduled session import, with optional ClickUp references. Someone still schedules the activity and records attendance. |
| Syllabus progress | `syllabus_daily` | Automatic. It re-reads 7 days, so a missed run heals itself. |
| Whoop strain, recovery, sleep | `wearable_daily` | Automatic, if the student has connected a Whoop. |
| Advisor inputs, exam targets | `advisor_inputs`, `exam_targets` | Automatic from ClickUp. Advisors still tick the boxes and enter targets. |
| Quizzes | `events`, `quiz_attempts` | Demo only. Delivery status needs a separate record, including held, cancelled and skipped quizzes. |
| Chapter progress | `chapter_progress` | Demo only. Monthly plans, stage evidence and stage-change dates need an agreed input contract. |
| Submitted feedback | `feedback` | Demo only. Needs a readable export of submitted ratings, with student/event linkage. |
| Apple, Samsung, Garmin | `wearable_daily` | Demo only, sleep only. Current scheduled wellness coverage is Whoop. |

`ingest_log` is the 16th table. The three demo-only tables have working mappers and tests; they're waiting on a real source. A person is still needed to keep ClickUp current, supply one login per student, attach an alert channel and switch the schedules on.

## Approach and design choices

You already use n8n, so I built on it rather than adding a new tool. Postgres holds the data, and the dashboard reads a DuckDB snapshot of it, so it never depends on a live database. Neither service has to stay running for the demo: start them for a load and stop them after.

- **I capture focus at 23:55 IST.** The current import uses reporting-day records, so moving capture past midnight could miss the previous day.
- **I poll ClickUp instead of using its trigger node.** The n8n ClickUp trigger has open reliability issues (n8n #14277, #20296, #20297), and advisor duties change monthly, so a daily read is enough.
- **I reject rather than guess.** Unknown values, missing readings and unproven chapter stages stay unknown. A KPI with no data shows "no data", never zero.
- **I publish a snapshot instead of letting the dashboard query Postgres.** The dashboard only reads, and a validated, atomic file means a bad load can't reach it.
- **The logic lives in one place.** It's plain JS in [code/](code/), unit-tested outside n8n, and the workflow JSON is generated from it, so the export and the tests can't drift apart. If you change anything, edit [code/](code/), [sql/](sql/) or [config.yaml](../student-tracker/config.yaml), run the matching script in [build/](build/) and re-import. Imported workflows don't read the repo, so a YAML change does nothing until you rebuild.
- **I’ve shipped everything inactive.** Production credentials, input contracts and a validation run need to be agreed before enabling the schedules.

### What makes it safe to leave running

- **Re-running is safe.** Every write is `INSERT ... ON CONFLICT DO UPDATE` on the app's own ids. The end-to-end test runs it twice and compares a checksum.
- **A failed read is never treated as "no data".** Each read retries 3 times (2 s apart), then the run carries on and is logged `partial`, naming the source. It can't wipe a table.
- **Short answers are caught.** A paged answer with fewer unique ids than the app's own `total` (a missing or repeated page) makes that source `partial`.
- **Bad rows aren't guessed.** An unknown status word, an impossible date (e.g. 30 Feb) or an out-of-range value is rejected and named in the log; the rest of the batch still loads. Duplicates in one answer collapse.
- **One bad table doesn't stop the others.** The poll writes each table separately; the run is `partial`, or `failed` only if every table failed, and the next run heals it. ClickUp writes both its tables in one statement, so they land together or not at all.
- **Runs can't hang.** Timeouts are 30 s per request, 15 min for the poll and 5 min for ClickUp and the snapshot export. Paging stops at 20 pages of 100 (sessions, goals) or 50 ClickUp pages; anything past that shows up as a truncated, `partial` source.
- **A sign-in failure stops the run** and goes to the error workflow. If the log write itself fails, the handler still continues to the alert node.
- **Every run leaves a trace.** One `ingest_log` row per run (`ok` / `partial` / `failed`), shown on the dashboard's Data health page. The demos never write a fake `ok` row, so they can't make the live feed look fresh.
- **The dashboard never sees half a load.** [snapshot.py](../student-tracker/snapshot.py) reads all tables in one transaction, rejects rows that point at unknown students or events, and swaps the file only on success; a failed export leaves yesterday's file in place. Its *Settings* values are checked against a safe-character list before they go into the shell command.
- **The integrated demo is all or nothing.** If any source bundle comes back `partial`, or a row points at a student or event outside the roster, nothing is written.
- **No secrets in the repo or the logs.** Logins live in n8n credentials. Saved execution data is off for all workflows (the snapshot export keeps failed runs only), so sign-in responses aren't stored. The poll and the error handler write errors as fixed categories, not raw upstream text. The student's email is never stored.

## Assumptions and limits

KPI-level assumptions (targets, proxies, thresholds) belong to the dashboard, and I've covered them in the [student tracker README](../student-tracker/README.md#assumptions-and-limits) (A1 to A66). Below are the ones the pipeline itself depends on.

### Access and timing

- The current poll imports one student per credential/run (A9, A59). A full cohort needs an agreed access model and roster.
- The schema stores IST. I convert zoned UTC inputs in one place and test the 18:30 UTC boundary. The production source’s reporting-day boundary still needs confirmation.
- Sessions after 23:55, or on a missed run, are not recovered by the current session loader. Daily aggregates cannot replace session-level backfill (A47, A60).
- The 00:30 snapshot is dated the previous IST day, because that's the last full day the 23:55 poll collected. The dashboard opens on that date.
- Syllabus and wellness re-read 7 days. After an outage longer than that, widen the window in the poll's *Settings* node.

### What the data means

- App status words map to lowercase schema values (`Failed` to `failed`, `Present` to attended, `Absent` to not attended, `Upcoming` to unknown). The mapper accepts explicit configured values; anything else is rejected (A43, A52).
- Missing is `NULL`, never zero (A8). Whoop sleep is loaded only when all three sleep stages are present.
- Some dates are "first seen by n8n", not the real event time: goal completion (the first run that sees `Achieved`; cleared if the goal goes back), the created date of quarterly and monthly goals, and Whoop connect/disconnect dates. The 30-day Whoop retention KPI only becomes real 30 days after launch (A45, A50).
- A session counts as **held** once its start time has passed, unless the app marks it cancelled. The current mapping doesn’t require a separate delivery-confirmed flag, so a session that quietly didn’t take place can still look held. Sessions carrying a ClickUp task id are tagged `source = clickup`. Workshop NPS is the app's event-level score (0 to 10), not a per-student rating.
- The single-student import maps Present, Absent or Upcoming (unknown); it doesn’t establish the full invitation roster.
- A focus session still running at capture time is skipped. Without session-level backfill, it may never be loaded.
- The student row needs a name, an advisor, a program start date and a grade from 8 to 12, or it's rejected. If the Whoop status read fails, the student row is skipped for that run; the other tables still load.
- Study hours are taken only for the quarter that contains today. Subject names are free text, and there’s no normalization map yet, so labels such as `Math` and `Mathematics` can split one subject into two.
- Goals load at annual, quarterly and monthly level. Daily goals (nested under monthly ones) aren't loaded. `Venture` maps to entrepreneurship; the current importer has no social-work category mapping.
- To-dos have no completion time, so `updated_at` stands in for it (A3).
- A goal with no due date is never counted as due or late; an annual goal is due 31 Dec (A58).
- Wellness keeps one source per student per day. Whoop beats manual, and manual sleep is never relabelled as Whoop. The poll skips manual days; the separate wellness demo supplies manual sleep through dated inputs. Valid ranges: strain 0 to 21, recovery 0 to 100, sleep 0 to 24 h.
- Upserts don't delete. A record removed in the app stays in Postgres until we agree a deletion rule. Current-state tables (to-dos, goals, chapters) can't rebuild a past day.

### ClickUp

I’ve assumed the following ClickUp structure. The list IDs and field mappings need to be matched to your workspace in [code/clickup.js](code/clickup.js) and *Settings*.

- Advisor duties: one task per student per month, with `student_id`, `month` and one checkbox per duty (`targets_aligned`, `guardrails_set`, `syllabus_review` and so on, from `advisor_input_kinds` in [config.yaml](../student-tracker/config.yaml)). Exam targets: one task per student, subject and exam type (`formative`, `unit_test`, `mid_term`), with `target_score` and `actual_score`.
- No task for a student-month means unknown, not "not done". An unticked box on an existing task means not done.
- `student_id` in ClickUp must be the app's own student id, and that student must already be in the database (the poll puts them there). Rows for unknown students are skipped, counted and make the run `partial`. That's also why ClickUp runs after the poll.
- A task with any bad field is rejected whole, never half-loaded.
- Scores are out of 100 (`scoreMax` in *Settings*). If two tasks share a key, the most recently edited one wins.
- Actual exam scores come from ClickUp too. A separate academic-results import would need an agreed exam identity, type and score scale.
- The exam target table has no exam year, so it holds one cycle, not a year of history.

### Demo sources

The inputs are synthetic and labelled as such; the full rules are in each mapper in [code/](code/).

- **Quizzes:** one quiz a day. "Held", "cancelled" and "planned" come from a separate delivery ledger, because the history only lists quizzes the student took. A held quiz with no attempt counts as skipped, never as not held. A quiz that appears in a student's history counts as held. Two quizzes on the same day are both rejected, because the dashboard assumes one a day.
- **Chapters:** I represent the brief’s five stages using tasks and scores: `read_textbook` done, `notes` done, a practice task done with the latest Worksheet score **above** 70, a timed past paper with explicit demo evidence, and a Mocktest **above** 80. Stages must be in order; a late test can't prove earlier work. If any stage's evidence is unknown (for example `NotRequired`), the chapter is rejected rather than scored 0. The latest score counts, not the best. The monthly plan and stage-change dates are demo inputs too.
- **Feedback:** one response per student per event. The supplied weighted composite is kept, not recomputed, and comments are stored only as "has comment" (no text). Roadmap and theme forms use an export I've proposed that doesn't exist yet.
- **Apple, Samsung, Garmin:** I've assumed the vendor field names and units (`wearable_loader` in [config.yaml](../student-tracker/config.yaml)). Only sleep is filled; they have no strain or recovery comparable to Whoop.

The test harness runs against synthetic fixtures and a mock source service. This verifies mapping, replay and failure handling; it does not establish production compatibility. The ClickUp fixtures use its documented API format. The remaining source contracts need validation before scheduling live imports.

### Not built or not proven

- **One student per run.** A full cohort needs one login per student or an admin token. That's your call.
- **Production compatibility is still pending**, and the ClickUp structure is assumed. Both need an agreed validation run before the schedules go on.
- **Only 6 of the 88 dashboard KPI input mappings are classified as loaded for the scheduled poll** (26 partial, 56 waiting on a source). The demos cover the rest on sample data. The per-KPI breakdown is in [audit/source-coverage.json](audit/source-coverage.json).
- **The dashboard's 95 queries are tested on DuckDB, not Postgres.** That's fine while it reads the snapshot; it matters if it ever reads Postgres directly.
- **ClickUp changes reach the dashboard a day late**, because the snapshot (00:30) runs before the ClickUp read (03:00).
- **A failed snapshot export is only visible inside n8n.** It doesn't use the error workflow or write to `ingest_log`, so the Data health page and the alert won't see it; the dashboard just keeps showing the old file.
- **The snapshot rebuilds the whole database every night**, row by row. That's fine for 20 students; a much larger cohort needs a bulk or incremental copy.
- **Leavers aren't detected.** My plan (A44) was to set `left_on` on the first day a student stops appearing, but the poll only sees one student, so nothing sets it yet. Leavers stay in the denominators.
- **Calendar connection isn’t imported.** Its retention KPI needs a connection-status feed and sufficient observation history.
- **ClickUp's log still keeps some raw error text** (up to 200 characters of a failed read or database error), unlike the poll. It should go through the same error categories before it handles real data.
- **Not in the scheduled import:** aggregate attendance/policy reconciliation, chapter progress and quizzes. These need explicit integration contracts.
- **No scheduled flow for quarterly themes, podcasts, competitions or trips.** These need mapped ClickUp records or an agreed product export.
- **Error dispatch is tested in two halves** (n8n hands the failure to the handler; the handler writes the right row), because the n8n CLI exits before the handler finishes. On a running server it's one step.
- **I imported and ran the workflows through the n8n CLI and never opened them in the editor**, so the canvas layout is unchecked.
- **Alerts are off**, and I haven't built **deadline-missed messages to stakeholders** (from the brief's advisor inputs). The data they'd need is now in one place.

## Run locally

You only need n8n and Postgres running while a load runs.

1. Create a Postgres database and run [sql/postgres-schema.sql](sql/postgres-schema.sql).
2. `npx n8n`, then import the workflow JSON files (Workflows > Import from file).
3. Add credentials:
   - **Postgres**, on every Postgres node.
   - Poll: **Custom Auth** with body `{"body": {"email": "...", "password": "..."}}`. It's only sent to the *Sign in* node.
   - ClickUp: **Header Auth** (`Authorization` = your API token) on both fetch nodes, and replace the two `REPLACE_WITH_..._LIST_ID` values in *Settings*.
4. Publish the error handler (n8n only runs an active error workflow) and check the poll and ClickUp workflows still name it after import. For alerts, set real addresses, attach SMTP (or swap in Slack) and enable the email node.
5. Snapshot export: enable the Execute Command node on the n8n host (remove it from `NODES_EXCLUDE`), install python with duckdb and psql there, and set the paths in *Settings* (the defaults are `/opt/alcovia/...`, database `student`, user `postgres`). The database password comes from `PGPASSWORD` or `~/.pgpass` on the host, not the workflow. [snapshot.py](../student-tracker/snapshot.py) refuses any cohort that isn't `DEMO-` data, and the dashboard refuses a snapshot not marked as demo. I did both on purpose, and both have to be removed deliberately before real students go in.
6. Press **Run now** once and read `ingest_log` before switching any schedule on.

To see the whole path on sample data, import [student-tracker-demo.json](student-tracker-demo.json), run it, run `snapshot.py` against the database, and open the dashboard with `ALCOVIA_STUDENT_SNAPSHOT=<file>` (see the [student tracker README](../student-tracker/README.md)). Its **Refresh data** button picks up a new snapshot.

To run the checks, from the repository root:

```bash
node --test n8n/tests/*.test.js                      # mappers and workflow glue
python3 n8n/tests/integration.py                     # all 17 scenarios, ~8 min, needs podman
python3 n8n/tests/integration.py --only 13 \
  --snapshot-output /tmp/alcovia-demo/student.duckdb # just the integrated demo, keeps the snapshot
```

The integration test runs real n8n 2.43.7 and Postgres 17 in throwaway containers against a mock API. It covers first load and replay, changes, pagination, bad rows, retries, sign-in failure, database outage, each demo, ClickUp and the snapshot export, then removes everything. It never calls Alcovia or uses a real login. The Python KPI checks for each demo source are in `tests/test_*_kpis.py` (run with `student-tracker/.venv/bin/python -m unittest`).

## Code and remaining work

- [Mappers](code/): `normalise.js` is shared by the poll and every demo; each source has its own mapper. No network or clock.
- [SQL](sql/): the Postgres schema (16 tables, generated from [student.sql](../student-tracker/sql/schema/student.sql)) and the upserts each workflow runs.
- [Generators](build/): build the workflow JSON from `code/`, `sql/` and [config.yaml](../student-tracker/config.yaml); `--check` detects stale exports.
- [Tests](tests/): Node unit tests, a mock of the app API, fixtures, Python KPI checks and the container end-to-end test.
- [Source audit](audit/): maps the 88 dashboard KPIs to required inputs and records coverage, gaps and next steps in [source-coverage.json](audit/source-coverage.json). Run `python3 -B n8n/audit/source_coverage.py --check` to check for drift.

Before switching anything on, I'd want three things: one real run of the poll with a student login to confirm the focus day boundary, the ClickUp list ids and field names matched to your real workspace, and an alert channel attached. Cohort access (one login per student or an admin token) is your decision. Team allocation and delivery timelines are in the executive writeup.
