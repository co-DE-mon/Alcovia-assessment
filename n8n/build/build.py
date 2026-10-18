#!/usr/bin/env python3
"""Generates every file in n8n/ that is derived from another source, so none of it is edited by hand:

  sql/postgres-schema.sql   student-tracker/sql/schema/student.sql with the one Postgres type difference applied
  sql/upserts.sql           the statement each table batch runs (a readable copy of what is embedded in the workflow)
  student-app-daily-poll.json, ingest-error-handler.json   the workflows, with no credentials attached and active = false

  python3 n8n/build/build.py                       write the shareable files
  python3 n8n/build/build.py --test OUTDIR URL     also write test copies in OUTDIR: credentials attached and the API address replaced
"""
import argparse
import json
import re
import subprocess
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCHEMA = ROOT.parent / "student-tracker" / "sql" / "schema" / "student.sql"
NS = uuid.UUID("a1c0b1a0-0000-4000-8000-00000000a1c0")

# Columns the poll must not overwrite with its own value on a conflict. Everything else is last-write-wins from EXCLUDED.
KEEP = {
    "students": {
        "left_on": "students.left_on",                                       # the poll never sets it [A44]
        "calendar_connected_on": "students.calendar_connected_on",           # no calendar status call yet
        "calendar_disconnected_on": "students.calendar_disconnected_on",
        "wearable_connected_on": "COALESCE(students.wearable_connected_on, EXCLUDED.wearable_connected_on)",   # first date seen [A45]
        "wearable_disconnected_on": "CASE WHEN EXCLUDED.wearable = 'none' THEN COALESCE(students.wearable_disconnected_on, EXCLUDED.wearable_disconnected_on) END",
        "weekday_study_hours": "COALESCE(EXCLUDED.weekday_study_hours, students.weekday_study_hours)",   # NULL = not reported this run
        "weekend_study_hours": "COALESCE(EXCLUDED.weekend_study_hours, students.weekend_study_hours)",
    },
    "wearable_daily": {    # a sparse reading keeps the values already known for that day, but never across a source change
        c: f"CASE WHEN wearable_daily.data_source = EXCLUDED.data_source THEN COALESCE(EXCLUDED.{c}, wearable_daily.{c}) ELSE EXCLUDED.{c} END"
        for c in ("strain", "recovery_pct", "sleep_hours")
    },
    "roadmap_items": {
        "created_at": "roadmap_items.created_at",                            # the first run that saw the goal [A50]
        "done_at": "CASE WHEN EXCLUDED.done_at IS NULL THEN NULL ELSE COALESCE(roadmap_items.done_at, EXCLUDED.done_at) END",   # first run that saw Achieved
    },
}
LOG_SQL = ("INSERT INTO ingest_log SELECT * FROM json_populate_record(NULL::ingest_log, $1::json)\n"
           "ON CONFLICT (run_id) DO UPDATE SET source = EXCLUDED.source, started_at = EXCLUDED.started_at, finished_at = EXCLUDED.finished_at,\n"
           "  status = EXCLUDED.status, rows_upserted = EXCLUDED.rows_upserted, error = EXCLUDED.error")


def parse_tables(sql):
    """{table: {'columns': [...], 'pk': [...]}} from the CREATE TABLE blocks of student.sql."""
    tables = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", sql, re.S):
        cols, pk = [], []
        for line in m.group(2).split("\n"):
            code = re.sub(r"--.*", "", line).rstrip()
            if not code.strip() or len(code) - len(code.lstrip()) != 4:        # blank, a comment, or the continuation of a multi-line CHECK
                continue
            body = code.strip()
            composite = re.match(r"PRIMARY KEY \((.*?)\)", body)
            if composite:
                pk = [c.strip() for c in composite.group(1).split(",")]
                continue
            name = body.split()[0]
            cols.append(name)
            if "PRIMARY KEY" in body:
                pk = [name]
        tables[m.group(1)] = {"columns": cols, "pk": pk}
    return tables


def js_keys():
    """The KEYS and TABLE_ORDER the normaliser uses, read from normalise.js itself."""
    out = subprocess.run(["node", "-e", "const m=require(process.argv[1]);console.log(JSON.stringify({keys:m.KEYS,order:m.TABLE_ORDER}))",
                          str(ROOT / "code" / "normalise.js")], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def upsert_sql(table, spec):
    keep = KEEP.get(table, {})
    sets = [f"{c} = {keep.get(c, f'EXCLUDED.{c}')}" for c in spec["columns"] if c not in spec["pk"]]
    cols = ", ".join(spec["columns"])
    return (f"WITH up AS (\n  INSERT INTO {table} ({cols})\n  SELECT {cols} FROM json_populate_recordset(NULL::{table}, $1::json)\n"
            f"  ON CONFLICT ({', '.join(spec['pk'])}) DO UPDATE SET\n    " + ",\n    ".join(sets) + "\n  RETURNING 1\n)\nSELECT count(*)::int AS upserted FROM up")


def uid(name):
    return str(uuid.uuid5(NS, name))


def node(name, type_, version, params, pos, **extra):
    extra = {k: v for k, v in extra.items() if not (k == "credentials" and not v)}      # a shareable export has no credential bindings at all
    return {"parameters": params, "id": uid(name), "name": name, "type": type_, "typeVersion": version, "position": list(pos), **extra}


def chain(*names):
    return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]} for a, b in zip(names, names[1:])}


def build_workflows(tables, keys, base_url, creds):
    module = (ROOT / "code" / "normalise.js").read_text()
    sqls = {t: upsert_sql(t, tables[t]) for t in keys["order"]}
    poll_js = module + (ROOT / "code" / "poll-glue.js").read_text().replace("/*__SQL__*/ {}", json.dumps(sqls, indent=2))
    sum_js = module + (ROOT / "code" / "summarise-glue.js").read_text()
    err_js = module + (ROOT / "code" / "error-glue.js").read_text()
    pg = {"postgres": {"id": creds["postgres"], "name": "Student tracker Postgres"}} if creds else {}
    http_auth = {"httpCustomAuth": {"id": creds["http"], "name": "Alcovia student app login"}} if creds else {}
    retry = {"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000}
    bearer = [{"name": "Authorization", "value": "={{ 'Bearer ' + $('Sign in').first().json.data.accessToken }}"}]   # read from the sign-in node at run time, never stored
    api = "={{ $('Settings').first().json.baseUrl }}"

    def get(name, path, pos, query=None, paged=False):
        p = {"method": "GET", "url": f"{api}{path}", "sendHeaders": True, "headerParameters": {"parameters": bearer}, "options": {"timeout": 30000}}
        if query:
            p["sendQuery"] = True
            p["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in query.items()]}
        if paged:
            p["options"]["pagination"] = {"pagination": {
                "paginationMode": "updateAParameterInEachRequest",
                "parameters": {"parameters": [{"type": "qs", "name": "page", "value": "={{ $pageCount + 1 }}"}]},
                "paginationCompleteWhen": "other",
                "completeExpression": "={{ !$response.body.meta || $response.body.meta.page * $response.body.meta.limit >= $response.body.meta.total }}",
                "limitPagesFetched": True, "maxRequests": 20}}
        # A failed read must not stop the run: it continues, the error is reported by the Normalise step, and the run is logged as partial.
        return node(name, "n8n-nodes-base.httpRequest", 4.2, p, pos, onError="continueRegularOutput", alwaysOutputData=True, executeOnce=True, **retry)

    fetches = [
        ("Fetch profile", "/users/me", None, False), ("Fetch wearable status", "/whoop/status", None, False),
        ("Fetch time budget", "/academics/time-budget", None, False), ("Fetch focus today", "/schedule/focus/score/today", None, False),
        ("Fetch todos", "/student/todos", None, False),
        ("Fetch sessions", "/schedule/sessions", {"limit": "={{ $('Settings').first().json.pageLimit }}", "page": "1"}, True),
        ("Fetch syllabus history", "/academics/my-syllabus-history", {"startDate": "={{ $('Settings').first().json.since }}", "endDate": "={{ $('Settings').first().json.today }}"}, False),
        ("Fetch wellness history", "/wellness/history", {"days": "7"}, False),
        ("Fetch annual goals", "/goals/annual", None, False),
        ("Fetch quarterly goals", "/goals/quarterly", {"limit": "={{ $('Settings').first().json.pageLimit }}", "page": "1"}, True),
    ]
    nodes = [
        node("Schedule (daily 23:55 IST)", "n8n-nodes-base.scheduleTrigger", 1.2, {"rule": {"interval": [{"field": "cronExpression", "expression": "55 23 * * *"}]}}, (0, 0)),
        node("Run now", "n8n-nodes-base.manualTrigger", 1, {}, (0, 160)),
        node("Settings", "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": [
            {"id": uid("a1"), "name": "baseUrl", "value": base_url, "type": "string"},
            {"id": uid("a2"), "name": "today", "value": "={{ $now.setZone('Asia/Kolkata').toFormat('yyyy-MM-dd') }}", "type": "string"},
            {"id": uid("a3"), "name": "since", "value": "={{ $now.setZone('Asia/Kolkata').minus({ days: 7 }).toFormat('yyyy-MM-dd') }}", "type": "string"},
            {"id": uid("a4"), "name": "pageLimit", "value": 100, "type": "number"}]}, "includeOtherFields": False, "options": {}}, (260, 80)),
        # A sign-in failure is fatal on purpose: the workflow stops and the error workflow records it and raises the alert.
        node("Sign in", "n8n-nodes-base.httpRequest", 4.2, {"method": "POST", "url": f"{api}/auth/signin", "authentication": "genericCredentialType",
             "genericAuthType": "httpCustomAuth", "options": {"timeout": 30000}}, (520, 80), credentials=http_auth, **retry),
    ]
    x = 780
    for name, path, query, paged in fetches:
        nodes.append(get(name, path, (x, 80), query, paged))
        x += 260
    nodes += [
        node("Normalise", "n8n-nodes-base.code", 2, {"mode": "runOnceForAllItems", "language": "javaScript", "jsCode": poll_js}, (x, 80)),
        node("Upsert table", "n8n-nodes-base.postgres", 2.6, {"operation": "executeQuery", "query": "={{ $json.sql }}",
             "options": {"queryReplacement": "={{ JSON.stringify($json.rows) }}", "queryBatching": "independently"}}, (x + 260, 80),
             credentials=pg, onError="continueRegularOutput", retryOnFail=True, maxTries=2, waitBetweenTries=2000),
        node("Summarise run", "n8n-nodes-base.code", 2, {"mode": "runOnceForAllItems", "language": "javaScript", "jsCode": sum_js}, (x + 520, 80)),
        node("Log run", "n8n-nodes-base.postgres", 2.6, {"operation": "executeQuery", "query": LOG_SQL, "options": {"queryReplacement": "={{ JSON.stringify($json.log) }}"}},
             (x + 780, 80), credentials=pg, **retry),
        node("About this workflow", "n8n-nodes-base.stickyNote", 1, {"width": 760, "height": 300, "content":
             "## Student app daily poll\n\nSigns in as one student, reads the app, maps the answers to the student-tracker tables and upserts them into Postgres. "
             "One `INSERT ... ON CONFLICT DO UPDATE` per table, keyed on the app's own ids, so a replay changes nothing.\n\n"
             "- **Sign-in fails**: the run stops; the error workflow logs it and raises the alert.\n"
             "- **A read fails**: the run continues and is logged `partial`.\n"
             "- **A row has an unknown value**: it is rejected and named in the log; the other rows load.\n"
             "- **A table write fails**: the other tables still load; the run is `partial`, or `failed` if every table failed.\n\n"
             "Attach the credentials named in n8n/README.md. Inactive until you switch it on."}, (0, -380)),
    ]
    names = ["Settings", "Sign in"] + [f[0] for f in fetches] + ["Normalise", "Upsert table", "Summarise run", "Log run"]
    conns = chain(*names)
    conns["Schedule (daily 23:55 IST)"] = {"main": [[{"node": "Settings", "type": "main", "index": 0}]]}
    conns["Run now"] = {"main": [[{"node": "Settings", "type": "main", "index": 0}]]}
    poll = {"name": "Student app daily poll", "id": "studentAppDailyPoll01", "nodes": nodes, "connections": conns, "active": False, "tags": [],
            "settings": {"executionOrder": "v1", "timezone": "Asia/Kolkata", "saveDataSuccessExecution": "none", "saveDataErrorExecution": "none",
                         "saveManualExecutions": False, "executionTimeout": 900,
                         "errorWorkflow": "ingestErrorHandler01"}, "meta": {"templateCredsSetupCompleted": False}}

    err_nodes = [
        node("Error Trigger", "n8n-nodes-base.errorTrigger", 1, {}, (0, 0)),
        node("Build failure row", "n8n-nodes-base.code", 2, {"mode": "runOnceForAllItems", "language": "javaScript", "jsCode": err_js}, (260, 0)),
        node("Log failure", "n8n-nodes-base.postgres", 2.6, {"operation": "executeQuery", "query": LOG_SQL, "options": {"queryReplacement": "={{ JSON.stringify($json.log) }}"}},
             (520, 0), credentials=pg, onError="continueRegularOutput", **retry),
        # Disabled until Alcovia picks a channel and attaches an SMTP credential (a disabled node passes its input through, so the log row is unaffected).
        node("Send alert email (enable after attaching SMTP)", "n8n-nodes-base.emailSend", 2.1, {"fromEmail": "alerts@example.invalid", "toEmail": "ops@example.invalid",
             "subject": "={{ 'Alcovia ingest FAILED: ' + $('Build failure row').first().json.log.source }}",
             "emailFormat": "text", "text": "={{ 'Run ' + $('Build failure row').first().json.log.run_id + ' failed: ' + $('Build failure row').first().json.log.error }}", "options": {}},
             (780, 0), disabled=True, onError="continueRegularOutput"),
        node("About this workflow", "n8n-nodes-base.stickyNote", 1, {"width": 700, "height": 220, "content":
             "## Ingest error handler\n\nThe poll already names this workflow as its **Error workflow** (fixed id `ingestErrorHandler01`); publish this one so n8n runs it. When that workflow stops, this writes a `failed` row to "
             "`ingest_log`, so the dashboard's Data health page shows it, and it ends in a disabled email node. To get alerts: set real from/to addresses, attach an SMTP credential and enable that node (or swap in Slack). "
             "If the database is down, the log write continues to the alert node. No notification is sent while it is disabled."}, (0, -300)),
    ]
    err = {"name": "Ingest error handler", "id": "ingestErrorHandler01", "nodes": err_nodes,
           "connections": chain("Error Trigger", "Build failure row", "Log failure", "Send alert email (enable after attaching SMTP)"),
           "active": False, "tags": [], "settings": {"executionOrder": "v1", "timezone": "Asia/Kolkata", "saveDataSuccessExecution": "none", "saveDataErrorExecution": "none", "saveManualExecutions": False}, "meta": {"templateCredsSetupCompleted": False}}
    return poll, err, sqls


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", nargs=2, metavar=("OUTDIR", "BASE_URL"))
    args = ap.parse_args()
    schema = SCHEMA.read_text()
    tables, keys = parse_tables(schema), js_keys()
    for t in keys["order"]:
        assert tables[t]["pk"] == keys["keys"][t], f"{t}: key in normalise.js {keys['keys'][t]} differs from the schema {tables[t]['pk']}"
    pg_schema = ("-- GENERATED by n8n/build/build.py from student-tracker/sql/schema/student.sql. Do not edit; change student.sql and rebuild.\n"
                 "-- The only change is DOUBLE -> DOUBLE PRECISION. The DuckDB macros (is_active, period_days) are not part of the Postgres side.\n"
                 + re.sub(r"\bDOUBLE\b(?! PRECISION)", "DOUBLE PRECISION", schema))
    (ROOT / "sql" / "postgres-schema.sql").write_text(pg_schema)
    poll, err, sqls = build_workflows(tables, keys, "https://api.alcovia.life/api/v1", None)
    (ROOT / "sql" / "upserts.sql").write_text("-- GENERATED by n8n/build/build.py. $1 is the table's rows as a JSON array; the workflow runs one statement per table.\n\n" +
                                              "\n\n".join(f"-- {t}\n{s};" for t, s in sqls.items()) + f"\n\n-- ingest_log (one row per run)\n{LOG_SQL};\n")
    dump(ROOT / "student-app-daily-poll.json", poll)
    dump(ROOT / "ingest-error-handler.json", err)
    print("wrote sql/postgres-schema.sql, sql/upserts.sql, student-app-daily-poll.json, ingest-error-handler.json")
    if args.test:
        out, base = Path(args.test[0]), args.test[1]
        out.mkdir(parents=True, exist_ok=True)
        tp, te, _ = build_workflows(tables, keys, base, {"postgres": "testPostgres01", "http": "testHttpAuth01"})
        # The CLI cannot start a workflow from an Error Trigger, and `n8n execute` exits before a dispatched error workflow finishes. So the test copy of the
        # handler gets a manual entry that feeds the same "Build failure row" node with a report shaped like n8n's own. The shareable file does not have it.
        sample = ("return [{ json: { execution: { id: '9001', lastNodeExecuted: 'Sign in', error: { message: 'Authorization failed - please check your credentials' } },\n"
                  "                  workflow: { id: 'studentAppDailyPoll01', name: 'Student app daily poll' } } }];")
        te["nodes"] += [node("Test entry", "n8n-nodes-base.manualTrigger", 1, {}, (0, 220)),
                        node("Sample failure report", "n8n-nodes-base.code", 2, {"mode": "runOnceForAllItems", "language": "javaScript", "jsCode": sample}, (260, 220))]
        te["connections"].pop("Error Trigger")        # the CLI starts from the Error Trigger if it is there, and runs nothing, so the test copy drops it
        te["nodes"] = [n for n in te["nodes"] if n["name"] != "Error Trigger"]
        te["connections"]["Test entry"] = {"main": [[{"node": "Sample failure report", "type": "main", "index": 0}]]}
        te["connections"]["Sample failure report"] = {"main": [[{"node": "Build failure row", "type": "main", "index": 0}]]}
        dump(out / "poll.test.json", tp)
        dump(out / "error.test.json", te)
        print(f"wrote test copies in {out}")


if __name__ == "__main__":
    main()
