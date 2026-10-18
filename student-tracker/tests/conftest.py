import sys
from datetime import date
from pathlib import Path

import duckdb
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AS_OF = date(2026, 10, 24)


@pytest.fixture(scope="session")
def cfg():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


@pytest.fixture(scope="session")
def db(tmp_path_factory):
    from seed.generate import build
    path = str(tmp_path_factory.mktemp("seed") / "student.duckdb")
    build(path)
    con = duckdb.connect(path, read_only=True)
    yield con
    con.close()


@pytest.fixture(scope="session")
def one(db):
    def run(sql, *args):
        return db.execute(sql, list(args)).fetchone()[0]
    return run
