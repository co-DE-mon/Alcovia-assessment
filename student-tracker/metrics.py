"""Run the named queries in sql/metrics/*.sql with parameters taken from config.yaml.

A query starts with a `-- name: <query_name>` line; the comment block under it documents the metric.
Every $name in a query comes from params(): dates you pass in, plus every config.yaml value flattened to
section_key (a list becomes section_key_0, section_key_1; a nested mapping becomes section_key_subkey).
"""
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
SQL_DIR = ROOT / "sql" / "metrics"
_NAME = re.compile(r"^-- name: (\w+)\s*$", re.M)


def load_config():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def flatten(value, prefix=""):
    """{'quiz': {'regular_taker_days': [4, 7]}} -> {'quiz_regular_taker_days_0': 4, 'quiz_regular_taker_days_1': 7}"""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            out.update(flatten(item, f"{prefix}_{key}" if prefix else str(key)))
        return out
    if isinstance(value, list):
        out = {}
        for i, item in enumerate(value):
            out.update(flatten(item, f"{prefix}_{i}"))
        return out
    return {prefix: value}


def month_add(day, n):
    m = day.month - 1 + n
    return date(day.year + m // 12, m % 12 + 1, 1)


def quarter_for(day, cfg):
    """(first day, last day, label) of the academic quarter containing day, from config quarters. Label like 2026-27-Q3."""
    starts = cfg["quarters"]["first_month_of_each"]
    found = [(date(y, m, 1), i) for y in (day.year - 1, day.year) for i, m in enumerate(starts) if date(y, m, 1) <= day]
    first, index = max(found)
    year = first.year if first.month >= starts[0] else first.year - 1   # the academic year starts with the first quarter's month
    return first, month_add(first, 3) - timedelta(days=1), f"{year}-{str(year + 1)[-2:]}-Q{index + 1}"


def params(cfg, start, end):
    """Query parameters for the period start..end (inclusive). The caller keeps end on or before the data's as-of day.
    now is the end of that day, never the wall clock, so a result can be reproduced."""
    q_start, q_end, label = quarter_for(end, cfg)
    elapsed = ((end - q_start).days + 1) / ((q_end - q_start).days + 1)
    pace = cfg["syllabus"]["quarter_target_pct"] * (int(label[-1]) - 1 + elapsed)   # share of the year's syllabus due by $end [A13]
    return {**flatten(cfg), "start": start, "end": end, "quarter": label, "quarter_start": q_start, "quarter_end": q_end,
            "syllabus_pace_pct": pace, "now": datetime.combine(end, time(23, 59, 59))}


@lru_cache(maxsize=None)
def load(file):
    """{query_name: sql} for one file."""
    parts = _NAME.split((SQL_DIR / f"{file}.sql").read_text())  # [preamble, name, body, name, body, ...]
    return {name: body.strip() for name, body in zip(parts[1::2], parts[2::2])}


def run(con, file, name, prm):
    """Run one query. Rows come back as dicts, decimals as float. A missing parameter raises a KeyError that names it."""
    sql = load(file)[name]
    needed = set(re.findall(r"\$(\w+)", re.sub(r"--.*", "", sql)))
    missing = needed - set(prm)
    if missing:
        raise KeyError(f"{file}.{name} needs parameters {sorted(missing)}")
    cur = con.execute(sql, {k: prm[k] for k in needed})
    columns = [c[0] for c in cur.description]
    return [dict(zip(columns, (float(v) if isinstance(v, Decimal) else v for v in row))) for row in cur.fetchall()]
