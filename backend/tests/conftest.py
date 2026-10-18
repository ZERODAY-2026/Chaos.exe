import sys
from pathlib import Path

import pytest

# Make ``app`` importable when running pytest from the repo root or backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import database  # noqa: E402


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the database module at a throwaway file and initialise it."""
    monkeypatch.setenv("DATAMIND_DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    database.initialize_database()
    return database
