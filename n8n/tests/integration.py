#!/usr/bin/env python3
"""End-to-end test of the n8n workflows in disposable containers: real n8n, real Postgres, the mock API in mock_api.js. Standard library only.

  python3 n8n/tests/integration.py            run every scenario (about 5 minutes; needs podman and the two images, see n8n/README.md)
  python3 n8n/tests/integration.py --keep     leave the containers up afterwards to poke at them
Nothing here touches Alcovia's service or any real credential: the sign-in is a made-up login that only the mock accepts, and the database is a
container that is removed at the end. The workflow is imported into a throw-away n8n user folder, never into an existing n8n.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
N8N_IMAGE = "docker.io/n8nio/n8n:2.43.7"
PG_IMAGE = "docker.io/library/postgres:17-alpine"
POD, PG, MOCK, N8N = "ahtest", "ah-pg", "ah-mock", "ah-n8n"
MOCK_PORT = 18080
POLL_ID, ERR_ID = "studentAppDailyPoll01", "ingestErrorHandler01"


def sh(*cmd, check=True, input=None, timeout=300):
    r = subprocess.run(cmd, capture_output=True, text=True, input=input, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:6])} ... failed ({r.returncode}):\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r


class Stack:
    def __init__(self, work):
        self.work = Path(work)
        self.home = self.work / "n8n-home"
        self.wf = self.work / "wf"

    # ---- lifecycle ----
    def up(self):
        self.down()
        self.home.mkdir(parents=True, exist_ok=True)
        self.wf.mkdir(parents=True, exist_ok=True)
        for p in (self.work, self.home, self.wf):
            p.chmod(0o777)
        sh("python3", str(ROOT / "build" / "build.py"), "--test", str(self.wf), "http://127.0.0.1:8080/api/v1")
        sh("python3", str(ROOT / "build" / "chapter_demo.py"), "--test", str(self.wf / "chapter-demo.test.json"))
        sh("python3", str(ROOT / "build" / "quiz_demo.py"), "--test", str(self.wf / "quiz-demo.test.json"))
        sh("python3", str(ROOT / "build" / "wellness_demo.py"), "--test", str(self.wf / "wellness-demo.test.json"))
        sh("python3", str(ROOT / "build" / "feedback_demo.py"), "--test", str(self.wf / "feedback-demo.test.json"))
        sh("python3", str(ROOT / "build" / "student_demo.py"), "--test", str(self.wf / "student-demo.test.json"))
        sh("python3", str(ROOT / "build" / "wearables_demo.py"), "--test", str(self.wf / "wearables-demo.test.json"))
        sh("python3", str(ROOT / "build" / "snapshot_export.py"), "--test", str(self.wf / "snapshot-export.test.json"), "sh /wf/snapshot-stub.sh")
        # Stand-in for snapshot.py (python, psql and duckdb are not in the n8n image): records its arguments, and fails when the host creates snapshot-fail.
        (self.wf / "snapshot-stub.sh").write_text('echo "$@" > /home/node/.n8n/snapshot-args.txt\nif [ -f /home/node/.n8n/snapshot-fail ]; then echo boom >&2; exit 3; fi\n'
                                                  'echo "Published validated synthetic student snapshot."\n')
        sh("python3", str(ROOT / "build" / "clickup.py"), "--test", str(self.wf / "clickup.test.json"), "http://127.0.0.1:8080/api/v2")
        poll = json.load(open(self.wf / "poll.test.json"))
        poll["settings"]["errorWorkflow"] = ERR_ID          # the test copy only: the shareable file leaves this for the operator to set
        json.dump(poll, open(self.wf / "poll.test.json", "w"))
        json.dump([
            {"id": "testPostgres01", "name": "Student tracker Postgres", "type": "postgres",
             "data": {"host": "127.0.0.1", "port": 5432, "database": "student", "user": "postgres", "password": "test", "maxConnections": 5, "ssl": "disable", "allowUnauthorizedCerts": False}},
            {"id": "testClickUpAuth01", "name": "ClickUp API token", "type": "httpHeaderAuth", "data": {"name": "Authorization", "value": "TEST-CLICKUP-TOKEN"}},
            {"id": "testHttpAuth01", "name": "Alcovia student app login", "type": "httpCustomAuth",
             "data": {"json": json.dumps({"body": {"email": "student@example.test", "password": "test-only-password"}}), "allowedHttpRequestDomains": "all"}},
        ], open(self.wf / "credentials.json", "w"))
        for f in self.wf.iterdir():
            f.chmod(0o644)
        sh("podman", "pod", "create", "--name", POD, "-p", f"127.0.0.1:{MOCK_PORT}:8080")
        sh("podman", "run", "-d", "--pod", POD, "--name", PG, "-e", "POSTGRES_PASSWORD=test", "-e", "POSTGRES_DB=student", PG_IMAGE)
        sh("podman", "run", "-d", "--pod", POD, "--name", MOCK, "-e", "FIXTURES=/mock/fixtures",
           "-v", f"{HERE}/mock_api.js:/mock/mock_api.js:ro,Z", "-v", f"{HERE}/fixtures:/mock/fixtures:ro,Z", "--entrypoint", "node", N8N_IMAGE, "/mock/mock_api.js")
        sh("podman", "run", "-d", "--pod", POD, "--name", N8N,
           "-e", "N8N_ENCRYPTION_KEY=integration-test-key", "-e", "N8N_DIAGNOSTICS_ENABLED=false", "-e", "N8N_VERSION_NOTIFICATIONS_ENABLED=false",
           "-e", "N8N_PERSONALIZATION_ENABLED=false", "-e", "N8N_RUNNERS_ENABLED=true",
           "-e", "NODES_EXCLUDE=[]",        # n8n disables Execute Command by default; the snapshot-export scenario needs it
           "-e", "N8N_USE_WORKFLOW_PUBLICATION_SERVICE=false",   # the CLI publishes without a running server, so use the direct active-version lookup
           "-v", f"{self.home}:/home/node/.n8n:Z", "-v", f"{self.wf}:/wf:ro,Z", "--entrypoint", "sleep", N8N_IMAGE, "infinity")
        for _ in range(60):
            if sh("podman", "exec", PG, "pg_isready", "-U", "postgres", "-d", "student", check=False).returncode == 0:
                break
            time.sleep(1)
        time.sleep(2)
        self.psql(open(ROOT / "sql" / "postgres-schema.sql").read())
        roster=json.loads((HERE/'fixtures/demo/cohort.json').read_text())['students']
        self.psql("INSERT INTO students SELECT * FROM json_populate_recordset(NULL::students,'"+json.dumps(roster).replace("'","''")+"') ON CONFLICT(student_id) DO NOTHING")
        self.n8n("import:credentials", "--input=/wf/credentials.json")
        self.n8n("import:workflow", "--input=/wf/error.test.json")
        self.n8n("publish:workflow", f"--id={ERR_ID}")           # n8n only runs an error workflow that is active
        self.n8n("import:workflow", "--input=/wf/poll.test.json")
        self.n8n("import:workflow", "--input=/wf/chapter-demo.test.json")
        self.n8n("import:workflow", "--input=/wf/quiz-demo.test.json")
        self.n8n("import:workflow", "--input=/wf/wellness-demo.test.json")
        self.n8n("import:workflow", "--input=/wf/feedback-demo.test.json")
        self.n8n("import:workflow", "--input=/wf/student-demo.test.json")
        self.n8n("import:workflow", "--input=/wf/wearables-demo.test.json")
        self.n8n("import:workflow", "--input=/wf/snapshot-export.test.json")
        self.n8n("import:workflow", "--input=/wf/clickup.test.json")
        for _ in range(30):
            try:
                self.control({})
                break
            except Exception:
                time.sleep(1)

    def down(self):
        sh("podman", "pod", "rm", "-f", POD, check=False)

    # ---- helpers ----
    def n8n(self, *args, check=True):
        return sh("podman", "exec", N8N, "n8n", *args, check=check, timeout=240)

    def execute(self, workflow=POLL_ID, debug=False):
        cmd = ["podman", "exec", *(["-e", "N8N_LOG_LEVEL=debug"] if debug else []), N8N, "n8n", "execute", f"--id={workflow}"]
        r = sh(*cmd, check=False, timeout=240)
        return r.returncode, r.stdout + r.stderr

    def psql(self, sql, tuples=False):
        args = ["podman", "exec", "-i", PG, "psql", "-U", "postgres", "-d", "student", "-v", "ON_ERROR_STOP=1"]
        if tuples:
            args += ["-At", "-F", "|"]
        r = sh(*args, input=sql)
        return [line.split("|") for line in r.stdout.strip().split("\n") if line] if tuples else r.stdout

    def q(self, sql):
        return self.psql(sql, tuples=True)

    def scalar(self, sql):
        rows = self.q(sql)
        return rows[0][0] if rows else None

    def control(self, state):
        req = urllib.request.Request(f"http://127.0.0.1:{MOCK_PORT}/__control", data=json.dumps(state).encode(), method="POST")
        urllib.request.urlopen(req, timeout=5).read()

    def mock_log(self):
        return json.load(urllib.request.urlopen(f"http://127.0.0.1:{MOCK_PORT}/__log", timeout=5))


# ---------------------------------------------------------------------------------------------------------------------------------------------
TABLES = ["staff", "students", "study_hours", "focus_sessions", "todos", "events", "event_attendance", "syllabus_daily", "wearable_daily", "roadmap_items"]
FX = HERE / "fixtures"


def fx(name):
    return json.loads((FX / name).read_text())


def ist_today():
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")


class Results:
    def __init__(self):
        self.rows = []

    def check(self, name, ok, detail=""):
        self.rows.append((bool(ok), name, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if not ok and detail else ""))
        return bool(ok)


def counts(st):
    return {t: int(st.scalar(f"SELECT count(*) FROM {t}")) for t in TABLES}


def checksum(st):
    return {t: st.scalar(f"SELECT md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) FROM {t} x") for t in TABLES}


def last_run(st):
    r = st.q("SELECT run_id, status, rows_upserted, coalesce(error, '') FROM ingest_log ORDER BY started_at DESC, run_id DESC LIMIT 1")
    return r[0] if r else None


def reset(st, state=None):
    st.psql("TRUNCATE " + ", ".join(TABLES + ["ingest_log"]))
    st.control(state or {})


def expected_counts():
    """The row counts the normaliser gives for the default fixtures, computed by the same code under plain node (independent of n8n)."""
    js = r"""
    const {normalise}=require(process.argv[1]); const fs=require('fs'); const fx=n=>JSON.parse(fs.readFileSync(process.argv[2]+'/'+n));
    const r=normalise({runAt:new Date().toISOString(),sources:{signin:[fx('signin.json')],me:[fx('me.json')],whoop:[{success:true,data:{isConnected:false}}],timeBudget:[fx('time_budget.json')],
      focus:[fx('focus_today.json')],todos:[fx('todos.json')],sessions:[fx('sessions.json')],syllabus:[fx('syllabus_history.json')],wellness:[fx('wellness_history.json')],annual:[fx('annual_goals.json')],quarterly:[fx('quarterly_goals.json')]}});
    console.log(JSON.stringify(r.counts));"""
    return json.loads(sh("node", "-e", js, str(ROOT / "code" / "normalise.js"), str(FX)).stdout)


def s_first_run_and_replay(st, R):
    print("\n[1] first run, then an identical replay")
    reset(st)
    rc, out = st.execute()
    R.check("the first run exits 0", rc == 0, out[-300:])
    want = expected_counts()
    R.check("every table has exactly the rows the normaliser produces for these fixtures", counts(st) == want, f"{counts(st)} vs {want}")
    run = last_run(st)
    R.check("one ingest_log row, status ok, rows_upserted = rows loaded, no error", run and run[1] == "ok" and int(run[2]) == sum(want.values()) and run[3] == "", str(run))
    login = [e for e in st.mock_log() if e["path"] == "/auth/signin"]
    R.check("the sign-in body came from the credential (email and password), as JSON", login and login[0]["bodyKeys"] == ["email", "password"] and "json" in (login[0]["contentType"] or ""), str(login))
    reads = [e for e in st.mock_log() if e["path"] != "/auth/signin"]
    R.check("every read carried the bearer token from the sign-in response", reads and all(e["authorised"] for e in reads), str(reads[:2]))
    R.check("the syllabus request asked for the last 7 IST days",
            any(e["path"] == "/academics/my-syllabus-history" and e["query"].get("endDate") == ist_today() for e in reads))
    before = checksum(st)
    rc2, _ = st.execute()
    R.check("the replay exits 0", rc2 == 0)
    R.check("a replay changes no data table at all (same row counts and the same content checksum)", checksum(st) == before and counts(st) == want)
    ids = st.q("SELECT run_id, status FROM ingest_log ORDER BY run_id")
    R.check("the replay is its own log row: two distinct run ids, both ok", len(ids) == 2 and len({i[0] for i in ids}) == 2 and all(i[1] == "ok" for i in ids), str(ids))


def s_changes(st, R):
    print("\n[2] changed data updates in place; first-seen dates survive")
    reset(st)
    st.execute()
    todo0 = fx("todos.json")["data"][0]["id"]
    st.control({"todoPatch": {"0": {"status": "pending", "updatedAt": "2026-10-18T01:00:00.000Z"}}})
    st.execute()
    row = st.q(f"SELECT status, updated_at FROM todos WHERE todo_id = '{todo0}'")[0]
    R.check("a changed to-do is updated in place (still 30 rows, new status and IST time)", row == ["pending", "2026-10-18 06:30:00"] and counts(st)["todos"] == 30, str(row))
    # wearable: connected -> backdate -> disconnected -> reconnected
    st.control({"whoop": True})
    st.execute()
    R.check("a connected wearable stamps today as the first connected date", st.q("SELECT wearable, wearable_connected_on::text, wearable_disconnected_on::text FROM students")[0] == ["whoop", ist_today(), ""])
    st.psql("UPDATE students SET wearable_connected_on = '2026-09-01'")
    st.control({"whoop": False})
    st.execute()
    R.check("disconnecting keeps the first connected date and stamps the disconnect date",
            st.q("SELECT wearable, wearable_connected_on::text, wearable_disconnected_on::text FROM students")[0] == ["none", "2026-09-01", ist_today()])
    st.psql("UPDATE students SET wearable_disconnected_on = '2026-10-10'")
    st.execute()
    R.check("a repeated not-connected run does not move the disconnect date", st.scalar("SELECT wearable_disconnected_on::text FROM students") == "2026-10-10")
    st.control({"whoop": True})
    st.execute()
    R.check("reconnecting clears the disconnect date and still keeps the first connected date",
            st.q("SELECT wearable, wearable_connected_on::text, wearable_disconnected_on::text FROM students")[0] == ["whoop", "2026-09-01", ""])
    # goals: Achieved stamps done_at once
    goal = "quarterly:" + fx("quarterly_goals.json")["data"][0]["id"]
    st.control({"goalStatus": {"0": "Achieved"}})
    st.execute()
    got = st.q(f"SELECT done_at IS NOT NULL, created_at::text FROM roadmap_items WHERE item_id = '{goal}'")[0]
    R.check("the first run that sees a goal Achieved stamps done_at", got[0] == "t", str(got))
    st.psql(f"UPDATE roadmap_items SET done_at = '2026-10-01 10:00:00', created_at = '2026-08-01 09:00:00' WHERE item_id = '{goal}'")
    st.execute()
    R.check("later runs keep the first done_at and created_at", st.q(f"SELECT done_at::text, created_at::text FROM roadmap_items WHERE item_id = '{goal}'")[0] == ["2026-10-01 10:00:00", "2026-08-01 09:00:00"])
    st.control({"whoop": True})                       # the goal is no longer Achieved
    st.execute()
    R.check("a goal that is no longer Achieved loses its done_at", st.scalar(f"SELECT done_at IS NULL FROM roadmap_items WHERE item_id = '{goal}'") == "t")


def s_pagination(st, R):
    print("\n[3] pagination, and a truncated page set")
    reset(st, {"sessionsTotal": 120})
    rc, out = st.execute()
    pages = sorted(e["query"].get("page") for e in st.mock_log() if e["path"] == "/schedule/sessions")
    R.check("120 sessions are fetched in two pages of up to 100 and no more", rc == 0 and pages == ["1", "2"], f"{pages} {out[-200:]}")
    R.check("all 120 sessions are stored", counts(st)["events"] == 120 and last_run(st)[1] == "ok", str(counts(st)))
    after_sessions = [e for e in st.mock_log() if e["path"] in ("/academics/my-syllabus-history", "/goals/annual", "/goals/quarterly")]
    R.check("multiple session pages do not multiply later API reads", len(after_sessions) == 3, str([e["path"] for e in after_sessions]))
    st.control({"sessionsTotal": 120, "truncateSessions": True})
    st.execute()
    run = last_run(st)
    R.check("a short page set is logged partial with the reason, not accepted as complete", run[1] == "partial" and "truncated" in run[3] and "sessions" in run[3], str(run))
    R.check("and the sessions already stored are left alone", counts(st)["events"] == 120)


def s_invalid(st, R):
    print("\n[4] invalid input is rejected row by row, named in the log, and never fails the run")
    reset(st)
    todos, sess = fx("todos.json")["data"], fx("sessions.json")["data"]
    extra = [{**todos[2], "id": "bad-status", "status": "Snoozed"}, {**todos[3], "id": "bad-source", "source": "whatsapp"}, {**todos[4]}]   # the last one repeats a todo
    st.control({"todoExtra": extra, "sessionExtra": [{**sess[0], "id": "bad-type", "sessionType": "Gala"}], "focusPatch": {"0": {"failReason": "battery"}}})
    rc, out = st.execute()
    run = last_run(st)
    c = counts(st)
    R.check("the run still completes", rc == 0, out[-300:])
    R.check("it is logged partial; the note counts the rejects per table and gives the first few reasons",
            run[1] == "partial" and "4 rows rejected (focus_sessions 1, todos 2, events 1)" in run[3] and all(w in run[3] for w in ("Snoozed", "whatsapp", "battery")), str(run))
    R.check("rejected rows are not stored, the duplicate to-do is stored once, everything else loads",
            c["todos"] == 30 and c["events"] == 40 and c["focus_sessions"] == 12, str(c))
    R.check("no database error was raised by any batch", "database errors" not in run[3], run[3])


def s_failures(st, R):
    print("\n[5] a transient read failure is retried; a persistent one is logged and leaves the table alone")
    reset(st)
    st.control({"fail": {"/student/todos": 1}})
    rc, _ = st.execute()
    attempts = [e for e in st.mock_log() if e["path"] == "/student/todos"]
    R.check("one failed read is retried and the run is ok", rc == 0 and len(attempts) == 2 and attempts[0].get("failed") and last_run(st)[1] == "ok", f"{len(attempts)} {last_run(st)}")
    st.psql("UPDATE todos SET title = 'SENTINEL'")
    st.control({"fail": {"/student/todos": -1}})
    rc, _ = st.execute()
    attempts = [e for e in st.mock_log() if e["path"] == "/student/todos"]
    run = last_run(st)
    R.check("a persistent failure is tried three times then logged partial naming the source", len(attempts) == 3 and run[1] == "partial" and "failed sources: todos" in run[3], f"{len(attempts)} {run}")
    R.check("the failed source is not treated as empty: its table is untouched", st.scalar("SELECT count(*) FROM todos WHERE title = 'SENTINEL'") == "30")
    R.check("the other tables still loaded in that run", counts(st)["events"] == 40 and counts(st)["focus_sessions"] == 13)


def s_signin(st, R):
    print("\n[6] a sign-in failure stops the run and the error workflow records it")
    reset(st, {"signinFail": True})
    rc, out = st.execute(debug=True)
    R.check("the run fails (non-zero exit)", rc != 0, out[-200:])
    R.check("no data was written by the failed run", sum(counts(st).values()) == 0)
    R.check("the sign-in was retried three times and no reads were attempted",
            len([e for e in st.mock_log() if e["path"] == "/auth/signin"]) == 3 and not [e for e in st.mock_log() if e["method"] == "GET"])
    R.check("n8n handed the failure to the error workflow it is configured with",
            "Start external error workflow" in out and "ingestErrorHandler01" in out and "is not active" not in out and "Could not find workflow" not in out, out[-200:])
    # `n8n execute` is a one-shot CLI that exits before the dispatched error workflow finishes, so the handler is run on its own, fed a report in n8n's shape.
    rc2, out2 = st.execute(ERR_ID)
    run = last_run(st)
    R.check("the error handler turns a failure report into a failed ingest_log row naming the node",
            rc2 == 0 and run and run[1] == "failed" and run[0] == "n8n-9001" and "Sign in" in run[3] and "Student app daily poll" in run[3], f"{rc2} {run} {out2[-200:]}")
    R.check("and the logged text carries no credential", run and not any(w in run[3] for w in ("test-only-password", "TEST-ONLY", "student@example.test")))


def s_database(st, R):
    print("\n[7] a database failure on one table fails only that table, and the next run heals it")
    reset(st)
    st.execute()
    st.psql("ALTER TABLE events RENAME TO events_away; TRUNCATE todos")
    rc, _ = st.execute()
    run = last_run(st)
    R.check("the run completes and is logged partial naming the table, without the SQL or any row data",
            rc == 0 and run[1] == "partial" and "events: the database rejected the write" in run[3] and not any(w in run[3] for w in ("INSERT", "json_populate", "Demo Student")), str(run))
    R.check("the other tables were still written", counts_safe(st, "todos") == 30 and counts_safe(st, "focus_sessions") == 13)
    st.psql("ALTER TABLE events_away RENAME TO events")
    rc, _ = st.execute()
    R.check("once the table is back the next run loads it and is ok", rc == 0 and last_run(st)[1] == "ok" and counts(st)["events"] == 40)
    st.psql("ALTER TABLE ingest_log RENAME TO ingest_log_away")
    try:
        handler_rc, handler_out = st.execute(ERR_ID)
        R.check("the failure handler continues when its database log write fails", handler_rc == 0, handler_out[-300:])
    finally:
        st.psql("ALTER TABLE ingest_log_away RENAME TO ingest_log")


def counts_safe(st, table):
    return int(st.scalar(f"SELECT count(*) FROM {table}"))


def s_files(st, R):
    print("\n[8] the files that will be shared")
    for name in ("student-app-daily-poll.json", "ingest-error-handler.json"):
        wf = json.loads((ROOT / name).read_text())
        R.check(f"{name}: inactive, no credential bindings, no token or password text",
                wf["active"] is False and not any("credentials" in n for n in wf["nodes"]) and not any(w in json.dumps(wf) for w in ("TEST-ONLY", "test-only-password", "student@example.test")))
    err = json.loads((ROOT / "ingest-error-handler.json").read_text())
    R.check("the shareable poll and ClickUp workflows name the shared error handler by its fixed id",
            all(json.loads((ROOT / f).read_text())["settings"].get("errorWorkflow") == err["id"] == ERR_ID for f in ("student-app-daily-poll.json", "clickup-advisor-inputs.json")))
    R.check("the handler's alert is a real email node, disabled and credential-free until a channel is chosen",
            any(n["type"].endswith("emailSend") and n.get("disabled") is True and "credentials" not in n for n in err["nodes"]))


def seed_demo_roster(st):
    rows=json.loads((HERE/'fixtures/demo/cohort.json').read_text())['students']
    st.psql("INSERT INTO students SELECT * FROM json_populate_recordset(NULL::students,'"+json.dumps(rows).replace("'","''")+"') ON CONFLICT(student_id) DO NOTHING")


def s_chapter_demo(st, R):
    seed_demo_roster(st)
    print("\n[9] configurable manual chapter demonstration")
    st.psql("TRUNCATE chapter_progress")
    rc, out = st.execute("chapterProgressDemo01")
    R.check("the chapter workflow runs in n8n", rc == 0, out[-300:])
    row = st.q("SELECT student_id, chapter_id, stage_reached::text, updated_at::text FROM chapter_progress")
    R.check("explicit sample evidence stores stage 5 and source timestamp in IST", len(row) == 1 and row[0][2:] == ['5', '2026-10-10 15:30:00'], str(row))
    before = st.scalar("SELECT md5(string_agg(x::text, '|')) FROM chapter_progress x")
    st.execute("chapterProgressDemo01")
    R.check("chapter replay changes no data", st.scalar("SELECT md5(string_agg(x::text, '|')) FROM chapter_progress x") == before)
    st.psql("UPDATE chapter_progress SET updated_at='2026-09-15 12:00:00'")
    st.execute("chapterProgressDemo01")
    R.check("unchanged stage preserves its existing activity timestamp", st.scalar("SELECT updated_at::text FROM chapter_progress") == '2026-09-15 12:00:00')
    workflow_path = st.wf / 'chapter-demo.test.json'
    workflow = json.load(open(workflow_path))
    evidence = next(n for n in workflow['nodes'] if n['name'] == 'Demo inputs')['parameters']['assignments']['assignments'][0]['value']
    evidence['chapters'][0]['tasks'][0]['taskStatus'] = 'NotStarted'
    evidence['supplement'][0]['stageChangedAt'] = '2026-10-11T10:00:00Z'
    workflow_path.write_text(json.dumps(workflow))
    st.n8n('import:workflow', '--input=/wf/chapter-demo.test.json')
    rc, out = st.execute('chapterProgressDemo01')
    R.check("a corrected stage updates with its explicit change time", rc == 0 and st.q("SELECT stage_reached::text, updated_at::text FROM chapter_progress")[0] == ['0','2026-10-11 15:30:00'], out[-200:])
    evidence['supplement'][0]['stageChangedAt'] = '2026-10-01T10:00:00Z'
    evidence['chapters'][0]['tasks'][0]['taskStatus'] = 'Done'
    workflow_path.write_text(json.dumps(workflow))
    st.n8n('import:workflow', '--input=/wf/chapter-demo.test.json')
    st.execute('chapterProgressDemo01')
    R.check("older evidence cannot overwrite a newer stage", st.scalar("SELECT stage_reached FROM chapter_progress") == '0')



def s_quiz_demo(st, R):
    seed_demo_roster(st)
    print("\n[10] manual quiz delivery and attempts demonstration")
    st.psql("TRUNCATE quiz_attempts; DELETE FROM events WHERE kind='quiz'")
    rc, out = st.execute('quizProgressDemo01')
    R.check('quiz workflow executes in real n8n', rc == 0, out[-500:])
    R.check('nine deliveries include seven held, one cancelled and one planned', st.q("SELECT count(*), count(*) FILTER(WHERE status='held'),count(*) FILTER(WHERE status='cancelled'),count(*) FILTER(WHERE status='planned') FROM events WHERE kind='quiz'") == [['9','7','1','1']])
    R.check('four attempts include three completions and one unfinished', st.q("SELECT count(*),count(completed_at),count(*) FILTER(WHERE completed_at IS NULL AND score IS NULL) FROM quiz_attempts") == [['4','3','1']])
    def digest():
        return [st.scalar(f"SELECT md5(coalesce(string_agg(x::text,'|' ORDER BY x::text),'')) FROM {table} x") for table in ('events','quiz_attempts')]
    before = digest()
    rc, out = st.execute('quizProgressDemo01')
    R.check('identical quiz replay changes no data', rc == 0 and digest() == before, out[-200:])
    path = st.wf / 'quiz-demo.test.json'
    workflow = json.loads(path.read_text())
    evidence = next(n for n in workflow['nodes'] if n['name']=='Demo inputs')['parameters']['assignments']['assignments'][0]['value']
    evidence['history'] = {'error': 'synthetic unavailable history'}
    # Stale scheduled status cannot erase final delivery, nor unfinished erase completed.
    evidence['delivery'][0]['status'] = 'planned'
    evidence['scheduledSnapshots'][0]['quiz']['participation'] = {'startedAt':'2026-10-01T14:30:00Z','completedAt':None,'score':0}
    path.write_text(json.dumps(workflow))
    st.n8n('import:workflow','--input=/wf/quiz-demo.test.json')
    rc,out = st.execute('quizProgressDemo01')
    R.check('failed history is reported partial and preserves existing data',rc == 0 and 'partial' in out and digest()==before,out[-300:])
    evidence['delivery'][0]['status'] = 'held'
    evidence['scheduledSnapshots'][3]['quiz']['participation'].update(completedAt='2026-10-04T14:50:00Z',score=9)
    path.write_text(json.dumps(workflow))
    st.n8n('import:workflow','--input=/wf/quiz-demo.test.json')
    rc,out=st.execute('quizProgressDemo01')
    R.check('later explicit completion updates the unfinished attempt',rc==0 and st.scalar("SELECT score FROM quiz_attempts WHERE event_id='quiz:DEMO-QUIZ-4'")=='9',out[-200:])
    R.check('skips and cancellation never create attempts',st.scalar("SELECT count(*) FROM quiz_attempts WHERE event_id IN ('quiz:DEMO-QUIZ-5','quiz:DEMO-QUIZ-6','quiz:DEMO-QUIZ-7','quiz:DEMO-QUIZ-8')")=='0')
    # Execute the generated parameterized statement with a deliberately invalid attempt.
    # Postgres must roll back an otherwise valid event update in the same statement.
    sql=(ROOT/'sql/quiz-demo-upsert.sql').read_text()
    event=json.loads(st.scalar("SELECT row_to_json(e)::text FROM events e WHERE event_id='quiz:DEMO-QUIZ-1'"))
    attempt=json.loads(st.scalar("SELECT row_to_json(a)::text FROM quiz_attempts a WHERE event_id='quiz:DEMO-QUIZ-1'"))
    event['title']='must roll back';attempt['started_at']=None
    payload=json.dumps({'events':[event],'attempts':[attempt]}).replace("'","''")
    before=digest()
    try:
        st.psql("PREPARE quiz_write(json) AS " + sql + "\nEXECUTE quiz_write('" + payload + "');")
        failed=False
    except RuntimeError:
        failed=True
    R.check('invalid attempt rolls back the entire delivery and attempt write',failed and digest()==before)
    public=json.loads((ROOT/'quiz-progress-demo.json').read_text())
    R.check('public demo is inactive with no credential bindings',public['active'] is False and not any('credentials' in n for n in public['nodes']))


def s_wellness_demo(st, R):
    seed_demo_roster(st)
    print("\n[11] manual wellness demonstration with source separation")
    st.psql('TRUNCATE wearable_daily')
    logs_before=st.scalar('SELECT count(*) FROM ingest_log')
    rc,out=st.execute('wellnessDailyDemo01')
    R.check('wellness workflow runs in real n8n',rc==0,out[-500:])
    R.check('history and snapshots store three Whoop rows and one manual row',st.q("SELECT count(*),count(*) FILTER(WHERE data_source='whoop'),count(*) FILTER(WHERE data_source='manual') FROM wearable_daily")==[['4','3','1']])
    R.check('manual sleep stays separate from measured recovery and strain',st.q("SELECT strain IS NULL,recovery_pct IS NULL,sleep_hours FROM wearable_daily WHERE data_source='manual'")==[['t','t','8']])
    R.check('millisecond sleep durations become hours and real zero strain survives',st.q("SELECT day::text,strain,sleep_hours FROM wearable_daily ORDER BY day")[:3]==[['2026-10-01','8','8'],['2026-10-02','16','7'],['2026-10-03','0','9']])
    def digest():return st.scalar("SELECT md5(coalesce(string_agg(x::text,'|' ORDER BY x::text),'')) FROM wearable_daily x")
    before=digest()
    rc,out=st.execute('wellnessDailyDemo01')
    R.check('wellness replay changes no data',rc==0 and digest()==before,out[-200:])
    path=st.wf/'wellness-demo.test.json';workflow=json.loads(path.read_text())
    evidence=next(n for n in workflow['nodes'] if n['name']=='Demo inputs')['parameters']['assignments']['assignments'][0]['value']
    original=json.loads(json.dumps(evidence))
    def execute_evidence():
        path.write_text(json.dumps(workflow));st.n8n('import:workflow','--input=/wf/wellness-demo.test.json')
        return st.execute('wellnessDailyDemo01')
    evidence['history']={'success':False}
    evidence['dailySnapshots'].append({'requestedDay':'2026-10-01','response':{'date':'2026-10-01','studentId':evidence['studentId'],'dataSource':'MANUAL','manualSleepHours':6}})
    rc,out=execute_evidence()
    R.check('failed history cannot delete data or downgrade an existing Whoop row',rc==0 and 'partial' in out and digest()==before,out[-250:])
    evidence.clear();evidence.update(original)
    evidence['history']['data']['history'][0].update(recoveryScore=None,sleepStageDeepMs=None)
    evidence['history']['data']['history'].append({'date':'2026-10-04','dataSource':'WHOOP','dayStrain':9,'recoveryScore':50})
    rc,out=execute_evidence()
    R.check('a sparse same-source observation preserves known measurements',rc==0 and st.q("SELECT recovery_pct,sleep_hours FROM wearable_daily WHERE day='2026-10-01'")==[['32','8']],out[-200:])
    R.check('Whoop upgrade clears manual sleep instead of relabelling it measured',st.q("SELECT data_source,strain,recovery_pct,sleep_hours IS NULL FROM wearable_daily WHERE day='2026-10-04'")==[['whoop','9','50','t']])
    before=digest();evidence['history']={'history':[]};evidence['dailySnapshots']=[]
    rc,out=execute_evidence()
    R.check('empty successful responses are harmless and keep previous rows',rc==0 and digest()==before,out[-200:])
    R.check('demo writes do not claim a live ingestion freshness success',st.scalar('SELECT count(*) FROM ingest_log')==logs_before)
    public=json.loads((ROOT/'wellness-daily-demo.json').read_text())
    R.check('wellness export is manual, inactive and has no credential bindings',public['active'] is False and not any('credentials' in n for n in public['nodes']) and [n['type'] for n in public['nodes'] if n['type'].endswith('Trigger')]==['n8n-nodes-base.manualTrigger'])


def s_feedback_demo(st, R):
    print("\n[12] submitted-feedback demonstration")
    pack=json.loads((HERE/'fixtures/demo/feedback-input.json').read_text())
    def literal(value):return "'"+json.dumps(value).replace("'","''")+"'"
    roster=[dict(student_id=s,name=s,grade=10,advisor_id='DEMO-ADV',program_start_date='2026-01-01',wearable='none') for s in pack['studentIds']]
    events=[dict(event_id=e['eventId'],kind=e['kind'],title=e['eventId'],planned_for=(datetime.fromisoformat(e['plannedFor'].replace('Z','+00:00'))+timedelta(hours=5,minutes=30)).strftime('%Y-%m-%d %H:%M:%S'),status=e['status'],source='manual') for e in pack['eventLinks']]
    st.psql("TRUNCATE feedback; INSERT INTO students SELECT * FROM json_populate_recordset(NULL::students,"+literal(roster)+") ON CONFLICT(student_id) DO NOTHING; INSERT INTO events SELECT * FROM json_populate_recordset(NULL::events,"+literal(events)+") ON CONFLICT(event_id) DO NOTHING;")
    logs_before=st.scalar('SELECT count(*) FROM ingest_log')
    rc,out=st.execute('submittedFeedbackDemo01')
    R.check('submitted-feedback workflow runs in real n8n',rc==0,out[-500:])
    R.check('eighteen submitted forms write with stable source-qualified IDs',st.scalar('SELECT count(*) FROM feedback')=='18')
    R.check('source composite is preserved rather than recomputed',st.scalar("SELECT composite FROM feedback WHERE feedback_id='feedback:admin:DEMO-ADMIN-FB-1'")=='4.15')
    R.check('roadmap and theme records remain eventless with IST submission date',st.q("SELECT event_id IS NULL,submitted_at::text FROM feedback WHERE kind='roadmap'")==[['t','2026-10-03 00:15:00']])
    def digest():return st.scalar("SELECT md5(coalesce(string_agg(x::text,'|' ORDER BY x::text),'')) FROM feedback x")
    before=digest();rc,out=st.execute('submittedFeedbackDemo01')
    R.check('submitted-feedback replay changes no data',rc==0 and digest()==before,out[-200:])
    path=st.wf/'feedback-demo.test.json';workflow=json.loads(path.read_text())
    evidence=next(n for n in workflow['nodes'] if n['name']=='Demo inputs')['parameters']['assignments']['assignments'][0]['value']
    original=json.loads(json.dumps(evidence))
    def execute_evidence():
        path.write_text(json.dumps(workflow));st.n8n('import:workflow','--input=/wf/feedback-demo.test.json');return st.execute('submittedFeedbackDemo01')
    evidence['adminPages'].pop();rc,out=execute_evidence()
    R.check('truncated pages are partial and never remove existing feedback',rc==0 and 'partial' in out and digest()==before,out[-250:])
    evidence.clear();evidence.update(json.loads(json.dumps(original)))
    evidence['adminPages'][0]['rows'][0]['q1Rating']=4
    st.psql("UPDATE events SET status='cancelled' WHERE event_id='DEMO-FEEDBACK-EVENT-2'")
    rc,out=execute_evidence()
    R.check('conflicting submitted content and a cancelled database event are suppressed',rc==0 and 'partial' in out and digest()==before,out[-250:])
    st.psql("UPDATE events SET status='held' WHERE event_id='DEMO-FEEDBACK-EVENT-2'")
    event_duplicate={'id':'new-event-response','studentId':pack['studentIds'][0],'eventId':pack['eventLinks'][0]['eventId'],'kind':'session','q1Rating':5,'q2Rating':3,'q3Rating':4,'compositeScore':4.15,'hasComment':False,'submittedAt':'2026-10-01T11:00:00Z'}
    monthly_duplicate=dict(next(r for r in original['exportResponse']['rows'] if r['kind']=='roadmap'),id='new-monthly-response')
    orphan=dict(event_duplicate,id='unknown-db-student',studentId='DEMO-UNKNOWN-DB-STUDENT')
    evidence['studentIds'].append(orphan['studentId']);evidence['adminPages']=[];evidence['exportResponse']={'rows':[event_duplicate,monthly_duplicate,orphan]}
    rc,out=execute_evidence()
    R.check('database guards reject duplicate event/monthly responses and unknown students',rc==0 and 'partial' in out and digest()==before,out[-250:])
    evidence['exportResponse']={'rows':[]};rc,out=execute_evidence()
    R.check('empty submitted reads preserve all existing forms',rc==0 and digest()==before,out[-200:])
    R.check('demo feedback never marks live ingestion fresh',st.scalar('SELECT count(*) FROM ingest_log')==logs_before)
    public=json.loads((ROOT/'submitted-feedback-demo.json').read_text())
    R.check('feedback export is inactive, credential-free and disables execution payload history',public['active'] is False and not any('credentials' in n for n in public['nodes']) and public['settings']['saveDataSuccessExecution']=='none' and public['settings']['saveDataErrorExecution']=='none' and public['settings']['saveManualExecutions'] is False)


def s_integrated_demo(st, R):
    print("\n[13] shared cohort -> n8n -> Postgres -> snapshot -> dashboard")
    schema=(ROOT/'sql/postgres-schema.sql').read_text()
    import re
    names=re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)',schema)
    st.psql('TRUNCATE '+', '.join(names))
    rc,out=st.execute('studentTrackerCohortDemo01')
    R.check('integrated cohort executes in real n8n',rc==0 and '"status": "ok"' in out,out[-700:])
    R.check('the database contains the shared two-student roster and explicit advisor/exam inputs',st.scalar('SELECT count(*) FROM students')=='2' and st.scalar('SELECT count(*) FROM advisor_inputs')=='20' and st.scalar('SELECT count(*) FROM exam_targets')=='2')
    orphan_queries=[f"SELECT count(*) FROM {table} t LEFT JOIN students s USING(student_id) WHERE s.student_id IS NULL" for table in ('chapter_progress','quiz_attempts','wearable_daily','feedback','study_hours','todos','roadmap_items','advisor_inputs','exam_targets')]
    R.check('every student fact joins to the shared cohort',all(st.scalar(query)=='0' for query in orphan_queries))
    def digest():return [st.scalar(f"SELECT md5(coalesce(string_agg(x::text,'|' ORDER BY x::text),'')) FROM {table} x") for table in names]
    before=digest()
    initial={table:st.q(f'SELECT x::text FROM {table} x ORDER BY 1') for table in names}
    rc,out=st.execute('studentTrackerCohortDemo01')
    after=digest()
    differences={table:{'before':initial[table][:1],'after':st.q(f'SELECT x::text FROM {table} x ORDER BY 1')[:1]} for table,left,right in zip(names,before,after) if left!=right}
    R.check('replaying the full cohort changes no stored data',rc==0 and after==before,str(differences))
    python=os.environ.get('STUDENT_PYTHON',str(ROOT.parent/'student-tracker/.venv/bin/python'))
    snapshot_script=ROOT.parent/'student-tracker/snapshot.py'
    workflow_path=st.wf/'student-demo.test.json';workflow=json.loads(workflow_path.read_text())
    evidence=next(n for n in workflow['nodes'] if n['name']=='Demo inputs')['parameters']['assignments']['assignments'][0]['value']
    as_of=evidence['cohort']['asOf'][:10]
    def export(path):return sh(python,'-B',str(snapshot_script),'--container',PG,'--database','student','--user','postgres','--as-of',as_of,'--output',str(path))
    first=st.work/'before.duckdb';second=st.work/'after.duckdb';export(first)
    evidence['cohort']['exam_targets'][0]['actual_score']=90
    workflow_path.write_text(json.dumps(workflow));st.n8n('import:workflow','--input=/wf/student-demo.test.json')
    rc,out=st.execute('studentTrackerCohortDemo01')
    R.check('changed sample input updates the exam score through n8n',rc==0 and st.scalar("SELECT actual_score FROM exam_targets WHERE student_id='DEMO-STUDENT-1'")=='90',out[-250:])
    export(second)
    # Keep the user-selected final artifact before the UI check consumes its private copy.
    output=os.environ.get('STUDENT_SNAPSHOT_OUTPUT')
    if output:
        import shutil
        destination=Path(output).resolve();destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(second,destination)
    check=sh(python,'-B',str(HERE/'check_dashboard_snapshot.py'),'--before',str(first),'--after',str(second),check=False,timeout=300)
    R.check('all 95 queries, 88 KPIs and a visible score refresh work on n8n-produced data',check.returncode==0,check.stdout[-300:]+check.stderr[-1100:])
    before_failure=digest()
    evidence['cohort']['students'][0]['grade']=99
    evidence['cohort']['exam_targets'][0]['actual_score']=95
    workflow_path.write_text(json.dumps(workflow));st.n8n('import:workflow','--input=/wf/student-demo.test.json')
    failed_rc,failed_out=st.execute('studentTrackerCohortDemo01')
    R.check('a database constraint failure rolls back every cohort table',failed_rc!=0 and digest()==before_failure)
    R.check('synthetic import does not claim a live ingestion success',st.scalar('SELECT count(*) FROM ingest_log')=='0')


def s_roster_guards(st, R):
    print("\n[14] standalone loaders reject students outside the database roster")
    samples={
      'chapter':('chapter_progress',[dict(student_id='DEMO-UNKNOWN-GUARD',chapter_id='DEMO-GUARD',subject='Demo',quarter='2026-27-Q3',planned_month='2026-10-01',stage_reached=1,updated_at='2026-10-10 10:00:00')]),
      'wellness':('wearable_daily',[dict(student_id='DEMO-UNKNOWN-GUARD',day='2026-10-10',strain=None,recovery_pct=None,sleep_hours=8,data_source='manual')]),
      'quiz':('quiz_attempts',dict(events=[dict(event_id='DEMO-GUARD-QUIZ',kind='quiz',planned_for='2026-10-10 20:00:00',status='held',source='manual')],attempts=[dict(event_id='DEMO-GUARD-QUIZ',student_id='DEMO-UNKNOWN-GUARD',started_at='2026-10-10 20:01:00',completed_at=None,score=None,total_questions=10)]))}
    for source,(table,payload) in samples.items():
        before=st.scalar('SELECT count(*) FROM '+table)
        sql=(ROOT/'sql'/f'{source}-demo-upsert.sql').read_text()
        value=json.dumps(payload).replace("'","''")
        st.psql("PREPARE roster_guard(json) AS "+sql+"\nEXECUTE roster_guard('"+value+"'); DEALLOCATE roster_guard;")
        R.check(source+' SQL suppresses unknown-student writes',st.scalar('SELECT count(*) FROM '+table)==before)

def s_clickup(st, R):
    seed_demo_roster(st)
    print("\n[15] ClickUp advisor inputs and exam targets -> Postgres")
    CK = "clickupAdvisorInputs01"
    st.psql("TRUNCATE advisor_inputs, exam_targets")
    st.control({})
    def digest():
        return [st.scalar(f"SELECT md5(coalesce(string_agg(x::text,'|' ORDER BY x::text),'')) FROM {t} x") for t in ("advisor_inputs", "exam_targets")]
    def last_log():
        return st.q("SELECT status,rows_upserted,coalesce(error,'') FROM ingest_log WHERE source='clickup' ORDER BY finished_at DESC, run_id DESC LIMIT 1")[0]
    rc, out = st.execute(CK)
    R.check("the ClickUp workflow runs in real n8n", rc == 0, out[-400:])
    R.check("both lists were read to their last page with the token from the credential",
            [e["query"].get("page") for e in st.mock_log() if e["path"].endswith("/ADVISOR1/task")] == ["0", "1"]
            and all(e["authorised"] for e in st.mock_log() if e["path"].startswith("/api/v2")))
    R.check("30 advisor inputs and 3 exam targets are stored; source is clickup",
            st.q("SELECT count(*), count(*) FILTER (WHERE source='clickup') FROM advisor_inputs") == [["30", "30"]] and st.scalar("SELECT count(*) FROM exam_targets") == "3")
    R.check("one ingest_log row for source clickup, status ok, rows_upserted = rows loaded", last_log()[:2] == ["ok", "33"], str(last_log()))
    R.check("an unchecked box is stored as not done, an empty actual score as NULL",
            st.scalar("SELECT done FROM advisor_inputs WHERE student_id='DEMO-STUDENT-2' AND input_kind='rigour_check'") == "f"
            and st.scalar("SELECT actual_score IS NULL FROM exam_targets WHERE subject='Physics'") == "t")
    before = digest()
    rc, out = st.execute(CK)
    R.check("a replay changes no data (same content checksum)", rc == 0 and digest() == before, out[-200:])
    st.control({"clickupPatch": {"EXAMS1": {"0": {"actual_score": "91"}}, "ADVISOR1": {"1": {"rigour_check": "true"}}}})
    rc, out = st.execute(CK)
    R.check("a changed score and a ticked box are updated in place, no extra rows",
            rc == 0 and st.scalar("SELECT actual_score FROM exam_targets WHERE subject='Maths' AND student_id='DEMO-STUDENT-1'") == "91"
            and st.scalar("SELECT done FROM advisor_inputs WHERE student_id='DEMO-STUDENT-2' AND input_kind='rigour_check'") == "t"
            and st.scalar("SELECT count(*) FROM advisor_inputs") == "30", out[-200:])
    st.control({"clickupPatch": {"EXAMS1": {"1": {"exam_type": "pop quiz"}}}})
    before = digest()
    rc, out = st.execute(CK)
    R.check("a task with an unknown exam type is rejected and named; the run is partial and the other rows stay", rc == 0 and last_log()[0] == "partial" and "pop quiz" in last_log()[2] and st.scalar("SELECT count(*) FROM exam_targets") == "3", str(last_log()))
    st.control({"fail": {"/api/v2/list/EXAMS1/task": -1}})
    rc, out = st.execute(CK)
    R.check("a persistent ClickUp failure is retried, logged partial naming the source, and deletes nothing",
            rc == 0 and last_log()[0] == "partial" and "exam_list" in last_log()[2] and st.scalar("SELECT count(*) FROM exam_targets") == "3"
            and len([e for e in st.mock_log() if e["path"].endswith("/EXAMS1/task") and e.get("failed")]) >= 3, str(last_log()))
    st.control({})
    st.psql("DELETE FROM students WHERE student_id='DEMO-STUDENT-2'")
    rc, out = st.execute(CK)
    R.check("rows for a student missing from the database are skipped, counted and logged partial", rc == 0 and last_log()[0] == "partial" and "not in the database" in last_log()[2], str(last_log()))
    seed_demo_roster(st)
    public = json.loads((ROOT / "clickup-advisor-inputs.json").read_text())
    R.check("the export is inactive, credential-free, holds only placeholders and has a schedule plus a manual trigger",
            public["active"] is False and not any("credentials" in n for n in public["nodes"]) and "REPLACE_WITH" in json.dumps(public)
            and sorted(n["type"] for n in public["nodes"] if n["type"].endswith("Trigger")) == ["n8n-nodes-base.manualTrigger", "n8n-nodes-base.scheduleTrigger"])


def s_wearables_demo(st, R):
    print("\n[16] Apple, Samsung and Garmin sleep demonstration")
    seed_demo_roster(st)
    base = json.loads((HERE/'fixtures/demo/cohort.json').read_text())['students'][1]
    st.psql("INSERT INTO students SELECT * FROM json_populate_recordset(NULL::students,'"+json.dumps([{**base, 'student_id': f'DEMO-STUDENT-{n}'} for n in (3, 4)]).replace("'", "''")+"') ON CONFLICT(student_id) DO NOTHING")
    st.psql("TRUNCATE wearable_daily")
    st.psql("INSERT INTO wearable_daily VALUES ('DEMO-STUDENT-2','2026-10-02',NULL,NULL,9,'manual'),('DEMO-STUDENT-3','2026-10-01',10,80,6,'whoop')")
    rc, out = st.execute('wearablesDailyDemo01')
    R.check('the wearables workflow runs in real n8n', rc == 0, out[-500:])
    R.check('the schema accepts apple, samsung and garmin rows; the other device\'s Whoop day is left alone and one skipped write is reported',
            st.q("SELECT data_source,count(*) FROM wearable_daily GROUP BY 1 ORDER BY 1") == [['apple', '2'], ['garmin', '2'], ['samsung', '1'], ['whoop', '1']] and 'partial' in out, out[-300:])
    R.check('vendor units become hours; strain and recovery stay NULL; a day with no sleep stores no row',
            st.q("SELECT student_id,day::text,sleep_hours,strain IS NULL AND recovery_pct IS NULL FROM wearable_daily WHERE data_source<>'whoop' ORDER BY 1,2") ==
            [['DEMO-STUDENT-2', '2026-10-01', '7.5', 't'], ['DEMO-STUDENT-2', '2026-10-02', '6.5', 't'], ['DEMO-STUDENT-3', '2026-10-02', '8', 't'],
             ['DEMO-STUDENT-4', '2026-10-01', '8.5', 't'], ['DEMO-STUDENT-4', '2026-10-02', '7.5', 't']])
    R.check('a vendor reading replaces manual sleep but never overwrites a Whoop day',
            st.q("SELECT data_source,strain,recovery_pct,sleep_hours FROM wearable_daily WHERE student_id='DEMO-STUDENT-3' AND day='2026-10-01'") == [['whoop', '10', '80', '6']]
            and st.q("SELECT data_source,sleep_hours FROM wearable_daily WHERE student_id='DEMO-STUDENT-2' AND day='2026-10-02'") == [['apple', '6.5']])
    digest = lambda: st.scalar("SELECT md5(coalesce(string_agg(x::text,'|' ORDER BY x::text),'')) FROM wearable_daily x")
    before = digest()
    rc, out = st.execute('wearablesDailyDemo01')
    R.check('wearables replay changes no data', rc == 0 and digest() == before, out[-200:])
    path = st.wf/'wearables-demo.test.json'; workflow = json.loads(path.read_text())
    evidence = next(n for n in workflow['nodes'] if n['name'] == 'Demo inputs')['parameters']['assignments']['assignments'][0]['value']
    evidence['devices'] = [{'studentId': 'DEMO-GHOST', 'vendor': 'apple', 'readings': [{'date': '2026-10-01', 'asleepMinutes': 400}]}]
    path.write_text(json.dumps(workflow)); st.n8n('import:workflow', '--input=/wf/wearables-demo.test.json')
    rc, out = st.execute('wearablesDailyDemo01')
    R.check('a reading for a student missing from the database is skipped and nothing is deleted', rc == 0 and 'partial' in out and digest() == before, out[-250:])
    public = json.loads((ROOT/'wearables-daily-demo.json').read_text())
    R.check('wearables export is manual, inactive and has no credential bindings',
            public['active'] is False and not any('credentials' in n for n in public['nodes']) and [n['type'] for n in public['nodes'] if n['type'].endswith('Trigger')] == ['n8n-nodes-base.manualTrigger'])


def s_snapshot_export(st, R):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    print("\n[17] scheduled dashboard snapshot export (command stubbed: python, psql and duckdb are not in the n8n image)")
    args_file, fail_file = st.home/'snapshot-args.txt', st.home/'snapshot-fail'
    args_file.unlink(missing_ok=True); fail_file.unlink(missing_ok=True)
    # At 00:30 the poll's data runs to the end of the previous IST day, so that day is the snapshot's as-of.
    yesterday = lambda: (datetime.now(ZoneInfo('Asia/Kolkata')) - timedelta(days=1)).strftime('%Y-%m-%d')
    days = {yesterday()}
    rc, out = st.execute('snapshotExport01')
    days.add(yesterday())
    got = args_file.read_text().strip() if args_file.exists() else ''
    R.check('the export workflow runs in real n8n and calls the command', rc == 0 and got != '', out[-400:])
    R.check('the command carries database, user, output and yesterday\'s IST date as separate arguments',
            any(got.endswith(f'--database student --user postgres --output /var/lib/alcovia/student.duckdb --as-of {d}') for d in days), got)
    R.check('a run that confirms publication succeeds', 'ok' in out and 'did not confirm' not in out, out[-300:])
    args_file.unlink(); fail_file.write_text('x')
    rc, out = st.execute('snapshotExport01')
    R.check('a failing export fails the run loudly instead of passing quietly', rc != 0, out[-300:])
    fail_file.unlink(); args_file.unlink(missing_ok=True)
    path = st.wf/'snapshot-export.test.json'; workflow = json.loads(path.read_text())
    settings = next(n for n in workflow['nodes'] if n['name'] == 'Settings')['parameters']['assignments']['assignments']
    next(a for a in settings if a['name'] == 'database')['value'] = 'student; touch /home/node/.n8n/pwned'
    path.write_text(json.dumps(workflow)); st.n8n('import:workflow', '--input=/wf/snapshot-export.test.json')
    rc, out = st.execute('snapshotExport01')
    R.check('a setting with shell characters is refused before any command runs', rc != 0 and not args_file.exists() and not (st.home/'pwned').exists(), out[-300:])
    public = json.loads((ROOT/'snapshot-export.json').read_text())
    R.check('snapshot export is inactive, credential-free, scheduled with a manual trigger and keeps error executions',
            public['active'] is False and not any('credentials' in n for n in public['nodes']) and public['settings']['saveDataErrorExecution'] == 'all'
            and sorted(n['type'] for n in public['nodes'] if n['type'].endswith('Trigger')) == ['n8n-nodes-base.manualTrigger', 'n8n-nodes-base.scheduleTrigger'])


SCENARIOS = [s_first_run_and_replay, s_changes, s_pagination, s_invalid, s_failures, s_signin, s_database, s_files, s_chapter_demo, s_quiz_demo, s_wellness_demo, s_feedback_demo, s_integrated_demo, s_roster_guards, s_clickup, s_wearables_demo, s_snapshot_export]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--only", help="comma-separated scenario numbers to run, e.g. 6 or 1,3 (default: all)")
    ap.add_argument("--smoke", action="store_true", help="bring the stack up, run the workflow once, print what happened")
    ap.add_argument("--snapshot-output",help="Keep the final synthetic DuckDB snapshot from scenario 13")
    args = ap.parse_args()
    if args.snapshot_output:os.environ["STUDENT_SNAPSHOT_OUTPUT"]=args.snapshot_output
    work = tempfile.mkdtemp(prefix="n8n-it-", dir=os.environ.get("IT_TMP"))
    st = Stack(work)
    try:
        st.up()
        if args.smoke:
            rc, out = st.execute()
            print("exit", rc)
            print(out[-3000:])
            print(st.q("SELECT run_id, source, status, rows_upserted, left(error, 200) FROM ingest_log"))
            print(st.q("SELECT 'todos', count(*) FROM todos UNION ALL SELECT 'events', count(*) FROM events UNION ALL SELECT 'roadmap_items', count(*) FROM roadmap_items"))
            return 0
        R = Results()
        wanted = {int(n) for n in args.only.split(",")} if args.only else None
        for number, scenario in enumerate(SCENARIOS, start=1):
            if wanted is None or number in wanted:
                scenario(st, R)
        failed = [r for r in R.rows if not r[0]]
        print(f"\n{len(R.rows) - len(failed)} of {len(R.rows)} checks passed")
        return 1 if failed else 0
    finally:
        if not args.keep:
            st.down()
            sh("podman", "unshare", "rm", "-rf", work, check=False)   # files made inside the containers belong to a sub-uid


if __name__ == "__main__":
    sys.exit(main())
