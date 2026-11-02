import shutil
from pathlib import Path

import pytest

from pgi.config import ROOT, load_config
from pgi.pipeline import run
from pgi.warehouse import connect

LANDING = ROOT / "data" / "landing"


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture(scope="session")
def _base(tmp_path_factory, cfg):
    """Landing copy + warehouse after one full run. Built once; copied per test."""
    base = tmp_path_factory.mktemp("base")
    shutil.copytree(LANDING, base / "landing")
    run(cfg, base / "landing", base / "warehouse")
    return base


@pytest.fixture
def ws(_base, tmp_path):
    """A private workspace (landing + already-loaded warehouse) for one test."""
    shutil.copytree(_base, tmp_path / "ws")
    return tmp_path / "ws"


def query(warehouse: Path, sql: str, params=None):
    con = connect(warehouse)
    try:
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()
