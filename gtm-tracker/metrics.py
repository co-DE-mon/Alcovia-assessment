"""Run the named queries in sql/metrics/*.sql with parameters taken from config.yaml.

A query starts with a `-- name: <query_name>` line; the comment block under it documents the metric.
Every $name in a query comes from params(): the period you pass in, plus every config.yaml value flattened to
section_key (a list becomes section_key_0, section_key_1).
"""
import re
from datetime import datetime, time
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
    """{'campaign': {'frequency_change_at': 3}} -> {'campaign_frequency_change_at': 3}"""
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


def params(cfg, start, end):
    """Query parameters for the period start..end (inclusive). now is the end of that day, never the wall clock, so a result can be reproduced."""
    return {**flatten(cfg), "start": start, "end": end, "now": datetime.combine(end, time(23, 59, 59))}


@lru_cache(maxsize=None)
def load(file):
    """{query_name: sql} for one file."""
    parts = _NAME.split((SQL_DIR / f"{file}.sql").read_text())  # [preamble, name, body, name, body, ...]
    return {name: body.strip().rstrip(";") for name, body in zip(parts[1::2], parts[2::2])}


def describe(file):
    """{query_name: the comment block under its `-- name:` line, with the leading `-- ` removed}. This is what the Definitions page shows."""
    parts = _NAME.split((SQL_DIR / f"{file}.sql").read_text())
    out = {}
    for name, body in zip(parts[1::2], parts[2::2]):
        lines = []
        for line in body.lstrip("\n").splitlines():
            if not line.startswith("--"):
                break
            lines.append(line[3:] if line.startswith("-- ") else line[2:])
        out[name] = "\n".join(l.rstrip() for l in lines)
    return out


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
