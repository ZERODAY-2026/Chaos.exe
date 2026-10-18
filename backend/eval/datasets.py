"""Build evaluation fixture databases in a throwaway directory.

Fixtures are deliberately separate from production configuration: they are
created fresh in a temporary folder for every run and never touch the dev
database (``data/datamind_dev.duckdb``) or Snowflake.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from app import database

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
DATASETS = ("sales", "retail")


def build_dataset(name: str, directory: Path | str) -> Path:
    """Create ``<directory>/<name>.duckdb`` from scratch and return its path."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"eval_{name}.duckdb"
    for leftover in (path, path.with_suffix(".duckdb.wal")):
        if leftover.exists():
            leftover.unlink()
    if name == "sales":
        database.initialize_database(path)  # same 6 rows as the dev database
    elif name == "retail":
        script = (FIXTURE_DIR / "retail.sql").read_text(encoding="utf-8")
        with duckdb.connect(str(path)) as con:
            con.execute(script)
    else:
        raise ValueError(f"Unknown evaluation dataset: {name!r}")
    return path
