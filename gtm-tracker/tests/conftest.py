import sys
from pathlib import Path

import duckdb
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def cfg():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


@pytest.fixture(scope="session")
def db(tmp_path_factory):
    from seed.generate import build
    path = str(tmp_path_factory.mktemp("seed") / "gtm.duckdb")
    build(path)
    con = duckdb.connect(path, read_only=True)
    yield con
    con.close()


@pytest.fixture
def empty():
    """An in-memory database with the schema and no rows, for hand-built edge cases."""
    con = duckdb.connect()
    con.execute((ROOT / "sql" / "schema" / "gtm.sql").read_text())
    yield con
    con.close()


@pytest.fixture(scope="module")
def db_module(tmp_path_factory):
    """The seeded database for a whole test module (a module-scoped fixture cannot use the session one's tmp_path)."""
    from seed.generate import build
    path = str(tmp_path_factory.mktemp("seedm") / "gtm.duckdb")
    build(path)
    con = duckdb.connect(path, read_only=True)
    yield con
    con.close()


@pytest.fixture(scope="module")
def cfg_module():
    return yaml.safe_load((ROOT / "config.yaml").read_text())
