"""Cached data access for the dashboard. The dummy database is built once per server start from seed/generate.py; no database file is stored in the repo."""
import tempfile
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

import metrics
import rca
import timeline
from seed.generate import build


_DEMO_DIR = tempfile.TemporaryDirectory(prefix="alcovia-gtm-")   # removed when the server exits; a rebuild reuses the same file


@st.cache_resource(show_spinner="Building the dummy data…")
def _database():
    path = Path(_DEMO_DIR.name) / "gtm.duckdb"
    build(path)
    return duckdb.connect(str(path), read_only=True)


def cursor():
    """A cursor of its own, so concurrent sessions never share one connection object."""
    return _database().cursor()


@st.cache_data
def config():
    return metrics.load_config()


@st.cache_data
def as_of():
    return cursor().execute("SELECT as_of FROM snapshot_meta").fetchone()[0]


def period():
    """The (start, end) chosen in the shared selector; the choice lives in session state under tl_choice / tl_custom."""
    return timeline.resolve(st.session_state.get("tl_choice", timeline.DEFAULT_CHOICE), as_of(), st.session_state.get("tl_custom"))


@st.cache_data(show_spinner=False)
def query(file, name, start, end, **extra):
    """One named metric as a DataFrame. `extra` carries the query's own parameters ($lead_id, $ad_id, $stream ...). Queries that only look at the period's
    last day (the single-lead and single-enrollment ones) get start == end."""
    return pd.DataFrame(metrics.run(cursor(), file, name, {**metrics.params(config(), start, end), **extra}))


@st.cache_data(show_spinner=False)
def assess(start, end):
    """The RCA verdicts and the inputs behind them (see rca.py). Program verdicts look back rca.lookback_days from `end`; workshops use start..end."""
    return rca.assess(cursor(), config(), start, end)
