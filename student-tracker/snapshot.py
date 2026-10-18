"""Publish a validated, atomic DuckDB snapshot of a synthetic n8n Postgres database.
Uses psql (or psql in a disposable Podman container); no new Python dependency.
"""
import argparse
import json
import os
import re
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
SCHEMA = (ROOT / "sql" / "schema" / "student.sql").read_text()
TABLES = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA)


def publish(tables, destination, as_of):
    """Validate the entire cohort before replacing the prior snapshot. Missing tables fail closed."""
    if set(tables) != set(TABLES):
        raise ValueError("snapshot must contain every student-tracker table")
    day = date.fromisoformat(str(as_of))
    if str(as_of) != day.isoformat():
        raise ValueError("as-of date must be YYYY-MM-DD")
    students = {r["student_id"] for r in tables["students"]}
    events = {r["event_id"] for r in tables["events"]}
    if not students or not all(s.startswith("DEMO-") for s in students):
        raise ValueError("only an explicit synthetic cohort may be published")
    for table, rows in tables.items():
        for row in rows:
            if "student_id" in row and row["student_id"] not in students:
                raise ValueError("snapshot contains a student outside its roster")
            if table != "events" and row.get("event_id") is not None and row["event_id"] not in events:
                raise ValueError("snapshot contains an unknown event link")
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".student-snapshot-", suffix=".duckdb", dir=destination.parent)
    os.close(fd)
    os.unlink(temporary)
    try:
        con = duckdb.connect(temporary)
        try:
            con.execute(SCHEMA)
            con.execute((ROOT / "sql" / "schema" / "macros.sql").read_text())
            for table in TABLES:
                columns = [x[0] for x in con.execute("DESCRIBE " + table).fetchall()]
                for row in tables[table]:
                    if set(row) - set(columns):
                        raise ValueError("snapshot contains unknown columns")
                    con.execute("INSERT INTO " + table + " (" + ", ".join(row) + ") VALUES (" + ", ".join("?" for _ in row) + ")", list(row.values()))
            con.execute("CREATE TABLE snapshot_meta(as_of DATE, demo BOOLEAN, source VARCHAR)")
            con.execute("INSERT INTO snapshot_meta VALUES (?,true,'n8n Postgres demonstration')", [day])
        finally:
            con.close()
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def export(command, destination, as_of):
    # One repeatable-read snapshot across all tables, using fixed schema-owned identifiers.
    fields = ", ".join("'" + table + "', (SELECT coalesce(json_agg(t),'[]'::json) FROM " + table + " t)" for table in TABLES)
    sql = "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SELECT json_build_object(" + fields + "); COMMIT;"
    result = subprocess.run([*command, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql], check=True, capture_output=True, text=True)
    return publish(json.loads(result.stdout), destination, as_of)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", help="Disposable Postgres container; omit to use local psql/PG* environment")
    parser.add_argument("--database", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args()
    command = ["podman", "exec", args.container, "psql"] if args.container else ["psql"]
    command += ["-U", args.user, "-d", args.database]
    export(command, args.output, args.as_of)
    print("Published validated synthetic student snapshot.")


if __name__ == "__main__":
    main()
