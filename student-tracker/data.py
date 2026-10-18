"""Cached data access for the dashboard. The dummy database is built once per server start from seed/generate.py; no database file is stored in the repo.
Every function takes the as-of day, so the cache holds one result per day the viewer opens."""
import os
import tempfile
from datetime import timedelta
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

import drill as drill_mod
import metrics
import scorecard
import student_profile
from seed.generate import DEFAULT_AS_OF, build

PICKER_DAYS = 60            # how far back the as-of picker goes


_DEMO_DIR = tempfile.TemporaryDirectory(prefix="alcovia-student-")   # removed when the server exits; a refresh rebuilds the file inside it


@st.cache_resource(show_spinner="Building the dummy data…")
def _database(source=None):
    if source:
        path = Path(source).resolve()
        if not path.is_file():
            raise FileNotFoundError("Configured student snapshot does not exist")
        con = duckdb.connect(str(path), read_only=True)
        try:
            if con.execute("SELECT demo FROM snapshot_meta").fetchall() != [(True,)]:
                raise ValueError("Expected a labelled synthetic student snapshot")
        except Exception:
            con.close()
            raise
        return con
    path = Path(_DEMO_DIR.name) / "student.duckdb"
    build(path)
    return duckdb.connect(str(path), read_only=True)


def cursor():
    """A cursor of its own, so concurrent sessions never share one connection object."""
    return _database(os.environ.get("ALCOVIA_STUDENT_SNAPSHOT")).cursor()


@st.cache_data
def config():
    return metrics.load_config()


def bounds():
    high = cursor().execute("SELECT as_of FROM snapshot_meta").fetchone()[0] if os.environ.get("ALCOVIA_STUDENT_SNAPSHOT") else DEFAULT_AS_OF
    return high - timedelta(days=PICKER_DAYS), high


def as_of():
    return st.session_state.get("as_of", bounds()[1])


@st.cache_data(show_spinner=False)
def front(day):
    return scorecard.build(cursor(), config(), day)


@st.cache_data(show_spinner=False)
def drill(day, activity, kpi):
    return drill_mod.fetch(cursor(), config(), day, activity, kpi)


@st.cache_data(show_spinner=False)
def students(day):
    return scorecard.student_table(cursor(), config(), day)


@st.cache_data(show_spinner=False)
def profile(day, student_id):
    return student_profile.fetch(cursor(), config(), day, student_id)


@st.cache_data(show_spinner=False)
def timeline(day, student_id):
    return scorecard.student_timeline(cursor(), config(), day, student_id)


@st.cache_data(show_spinner=False)
def reconnect(day):
    return scorecard.whoop_reconnect(cursor(), config(), day)


@st.cache_data(show_spinner=False)
def runs(day):
    return scorecard.recent_runs(cursor(), config(), day)


@st.cache_data(show_spinner=False)
def daily_trends(day):
    """Two daily series over the scorecard window: share of active students who started the quiz, and valid focus minutes per active student."""
    cfg = config()
    start, _ = scorecard.windows(cfg, day)
    prm = metrics.params(cfg, start, day)
    quiz = pd.DataFrame(metrics.run(cursor(), "daily", "quiz_daily", prm))
    focus = pd.DataFrame(metrics.run(cursor(), "daily", "focus_daily", prm))
    quiz["Started the quiz (%)"] = (100 * quiz["started"] / quiz["active_students"]).where(quiz["held"])      # a day with no quiz is a gap, not 0
    focus["Valid focus minutes per student"] = focus["completed_minutes"] / focus["active_students"]
    return quiz.set_index("day")[["Started the quiz (%)"]], focus.set_index("day")[["Valid focus minutes per student"]]


def refresh():
    """An explicit refresh clears data results and reopens the atomically published snapshot."""
    for cached in (front, drill, students, profile, timeline, reconnect, runs, daily_trends, config, _database):
        cached.clear()
