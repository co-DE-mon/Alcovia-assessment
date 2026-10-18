"""Is the pipeline delivering? One card per source and the run history."""
import pandas as pd
import streamlit as st

import data
import ui
from views.common import record_table, show, table_height

RUN_ICON = {"ok": "✓ ok", "partial": "! partial", "failed": "✕ failed"}


EFFECT = {"failed": "Nothing was loaded from {source} in this run, so its data stopped updating until the next good run.",
          "partial": "Some rows were not loaded."}


def affected(end):
    """What is behind a stale or partial source: the students who have to act, and every failed or partial run with its error."""
    people = data.reconnect(end)
    problems = [r for r in data.runs(end) if r["status"] != "ok"]
    if not people and not problems:
        st.success("Every run in the last 14 days loaded completely.")
        return
    if people:
        show(ui.h2("Students who need to reconnect Whoop", "Their wearable data has stopped, so every Whoop KPI is missing their days. Ask them to reconnect in the app."))
        record_table(people, "health-reconnect", end, cap=260)
    if problems:
        show(ui.h2("Runs that did not load completely", "Last 14 days, newest first."))
        rows = []
        for r in problems:
            effect = EFFECT[r["status"]].format(source=r["source"])
            if r["source"] == "whoop" and r["status"] == "partial" and people:
                effect = "Some students' rows were not loaded: the students listed above."
            rows.append({"Run ID": r["run_id"], "Started": f'{ui.fmt_short(r["started_at"])} · {r["started_at"]:%H:%M}', "Source": r["source"], "Result": RUN_ICON[r["status"]],
                         "Error": r["error"] or "", "What it means": effect})
        record_table(rows, "health-problems", end, cap=300)


def page():
    cfg, end = data.config(), data.as_of()
    out = data.front(end)
    hours = cfg["data_freshness"]["stale_after_hours"]
    show(ui.page_header("Data health", f"Does each source have a recent, complete load? As of the end of {ui.fmt_date(end)}."))
    show(f'<div class="sv-sub" style="margin:-.4rem 0 .9rem">A source is <b>stale</b> when it has no fully successful run in the last {hours} hours. '
         'A partial run, where some rows were not loaded, does not count as successful.</div>')
    show(ui.tile_row([ui.source_card(r) for r in out["freshness"]]))
    affected(end)

    runs = data.runs(end)
    show(ui.h2("Run history", "Every load in the last 14 days. n8n writes one row per run per source."))
    source = st.selectbox("Source", ["All sources"] + sorted({r["source"] for r in runs}))
    rows = [{"Run ID": r["run_id"], "Started": f'{ui.fmt_short(r["started_at"])} · {r["started_at"]:%H:%M}', "Source": r["source"], "Result": RUN_ICON[r["status"]],
                        "Rows loaded": r["rows_upserted"], "Note": r["error"] or ""} for r in runs if source in ("All sources", r["source"])]
    record_table(rows, f"health-runs-{source}", end)
