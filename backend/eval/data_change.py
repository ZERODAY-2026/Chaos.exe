r"""Demonstrate that answers change when the data changes (PS1 submission extra).

Everything happens in an ISOLATED, throwaway DuckDB file (default
``data/demo/data_change_demo.duckdb``, git-ignored). It never writes to the dev
database, and it never touches Snowflake: the production app role is read-only
and must stay that way.

Steps
  1. Create a fresh demo database with the 6 sample sales rows.
  2. Ask a question through the real API pipeline and record SQL + rows.
  3. Controlled change: insert ONE clearly labeled row into the demo database.
  4. Ask the same question again.
  5. Print both results and exactly why they differ.
  6. Delete the demo database only if --cleanup is given.

PowerShell (repo root):
  .\.venv\Scripts\python.exe backend\eval\data_change.py              # uses Gemma via Ollama
  .\.venv\Scripts\python.exe backend\eval\data_change.py --direct-sql # no model needed
  .\.venv\Scripts\python.exe backend\eval\data_change.py --cleanup
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import duckdb  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import database  # noqa: E402
from app.api import create_app  # noqa: E402
from app.gemma import OllamaGemma  # noqa: E402
from app.providers import DuckDBProvider  # noqa: E402

DEFAULT_DEMO_DB = database.PROJECT_ROOT / "data" / "demo" / "data_change_demo.duckdb"
QUESTION = "What is the total revenue for each category?"
REFERENCE_SQL = (
    "SELECT category, SUM(quantity * unit_price) AS revenue FROM sales "
    "GROUP BY category ORDER BY category"
)
# The single controlled change. order_id 7 does not exist in the sample data.
DEMO_ROW = (7, "Monitor", "Electronics", 2, 15000.0, 2025)


class UnsafeDemoTarget(RuntimeError):
    """Raised when the demo is pointed at anything other than an isolated demo file."""


def _check_isolated(path: Path) -> Path:
    path = path.resolve()
    protected = {database.DEFAULT_DB_PATH.resolve()}
    if os.environ.get("DATAMIND_DUCKDB_PATH"):
        protected.add(Path(os.environ["DATAMIND_DUCKDB_PATH"]).resolve())
    if path in protected:
        raise UnsafeDemoTarget(f"Refusing to modify {path}: it is a configured application database.")
    if path.suffix != ".duckdb":
        raise UnsafeDemoTarget("The demo database must be a .duckdb file.")
    return path


def reset_demo_db(path: Path) -> Path:
    path = _check_isolated(path)
    for leftover in (path, Path(str(path) + ".wal")):
        if leftover.exists():
            leftover.unlink()
    database.initialize_database(path)
    return path


def apply_demo_change(path: Path) -> tuple:
    """The explicit, controlled setup step: add one labeled row to the DEMO file only."""
    path = _check_isolated(path)
    with duckdb.connect(str(path)) as con:  # write connection to the demo file, never the app
        exists = con.execute("SELECT COUNT(*) FROM sales WHERE order_id = ?", [DEMO_ROW[0]]).fetchone()[0]
        if not exists:
            con.execute("INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?)", list(DEMO_ROW))
    return DEMO_ROW


def ask(client: TestClient, text: str) -> dict[str, Any]:
    return client.post("/api/query", json={"question": text}).json()


def diff_results(before: list[list[Any]], after: list[list[Any]]) -> list[str]:
    """Describe per-group changes between two (label, value) result sets."""
    b = {str(r[0]): r[-1] for r in before}
    a = {str(r[0]): r[-1] for r in after}
    lines = []
    for key in sorted(set(a) | set(b)):
        if b.get(key) != a.get(key):
            lines.append(f"{key}: {b.get(key)} -> {a.get(key)}")
    return lines


def run_demo(path: Path, generator: Any = None, use_model: bool = True) -> dict[str, Any]:
    path = reset_demo_db(path)
    app = create_app(
        providers={"duckdb": DuckDBProvider(db_path=path)},
        default_provider="duckdb",
        initialize_duckdb=False,
        health_cache_seconds=0,
        env={},
        generator=generator if use_model else None,
    )
    text = QUESTION if use_model else REFERENCE_SQL
    with TestClient(app) as client:
        before = ask(client, text)
        change = apply_demo_change(path)
        after = ask(client, text)
    return {
        "question": QUESTION,
        "sent": text,
        "db": str(path),
        "before": before,
        "change": change,
        "after": after,
        "differences": diff_results(before.get("rows") or [], after.get("rows") or []),
    }


def _print_step(title: str, body: dict[str, Any]) -> None:
    print(f"\n== {title} ==")
    print(f"status: {body.get('status')}  executed: {body.get('executed')}")
    if body.get("sql"):
        print(f"SQL:    {' '.join(body['sql'].split())}")
    if body.get("rows") is not None:
        print(f"rows:   {body.get('rows')}")
    if body.get("answer"):
        print(f"answer: {body['answer']}")
    if body.get("error"):
        print(f"error:  {body['error']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show an answer changing when the data changes.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DEMO_DB, help="isolated demo .duckdb file")
    parser.add_argument("--direct-sql", action="store_true", help="send fixed SQL instead of asking Gemma")
    parser.add_argument("--cleanup", action="store_true", help="delete the demo database afterwards")
    args = parser.parse_args(argv)

    generator = None if args.direct_sql else OllamaGemma.from_env(os.environ)
    report = run_demo(args.db, generator=generator, use_model=not args.direct_sql)
    print(f"Isolated demo database: {report['db']}")
    print(f"Question: {report['question']}")
    _print_step("1. Before the change", report["before"])
    print(f"\n== 2. Controlled change (demo database only) ==\nINSERT INTO sales VALUES {report['change']}")
    _print_step("3. Same question after the change", report["after"])
    print("\n== 4. Why the answer changed ==")
    if report["differences"]:
        for line in report["differences"]:
            print(f"  {line}")
        same_sql = report["before"].get("sql") == report["after"].get("sql")
        print(f"  The inserted row {report['change']} is in category {DEMO_ROW[2]!r}. The query reads the table")
        print("  at question time, so its result now includes that row"
              + (" (same SQL both times)." if same_sql else " (note: the SQL differed between the two runs)."))
        print("  The size of the change depends on what the SQL computes; check the SQL above.")
    else:
        print("  No difference detected: the generated SQL may not cover the changed rows. Check the SQL above.")
    if args.cleanup:
        Path(report["db"]).unlink(missing_ok=True)
        print("\nDemo database deleted (--cleanup).")
    else:
        print(f"\nDemo database kept at {report['db']} (run with --cleanup to delete it).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
