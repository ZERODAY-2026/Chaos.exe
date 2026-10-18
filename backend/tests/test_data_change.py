"""The data-change demo: answers follow the data, and only an isolated file is modified."""

import pytest

from app import database
from app.gemma import Generation, ModelStatus
from eval import data_change
from eval.data_change import (
    REFERENCE_SQL,
    UnsafeDemoTarget,
    apply_demo_change,
    diff_results,
    reset_demo_db,
    run_demo,
)


class FixedGemma:
    model = "fixed"

    def status(self):
        return ModelStatus("fixed", "test", True)

    def generate(self, question, schema_text, dialect, feedback=None):
        return Generation(model="fixed", duration_ms=1.0, sql=REFERENCE_SQL)


def test_answer_changes_after_controlled_change(tmp_path):
    report = run_demo(tmp_path / "demo.duckdb", generator=FixedGemma())
    before, after = report["before"], report["after"]
    assert before["status"] == after["status"] == "success"
    assert before["executed"] and after["executed"]
    assert before["rows"] == [["Electronics", 166000.0], ["Furniture", 36000.0]]
    assert after["rows"] == [["Electronics", 196000.0], ["Furniture", 36000.0]]
    assert report["differences"] == ["Electronics: 166000.0 -> 196000.0"]
    assert before["query_id"] != after["query_id"]


def test_demo_works_without_a_model(tmp_path):
    report = run_demo(tmp_path / "demo.duckdb", use_model=False)
    assert report["sent"] == REFERENCE_SQL
    assert report["differences"] == ["Electronics: 166000.0 -> 196000.0"]


def test_demo_resets_and_change_is_idempotent(tmp_path):
    path = reset_demo_db(tmp_path / "demo.duckdb")
    apply_demo_change(path)
    apply_demo_change(path)  # never duplicates the demo row
    from app.providers import DuckDBProvider

    assert DuckDBProvider(db_path=path).run_query("SELECT COUNT(*) FROM sales")["rows"] == [[7]]
    reset_demo_db(path)
    assert DuckDBProvider(db_path=path).run_query("SELECT COUNT(*) FROM sales")["rows"] == [[6]]


def test_demo_refuses_application_databases(tmp_path, monkeypatch):
    with pytest.raises(UnsafeDemoTarget):
        reset_demo_db(database.DEFAULT_DB_PATH)
    with pytest.raises(UnsafeDemoTarget):
        apply_demo_change(database.DEFAULT_DB_PATH)
    configured = tmp_path / "configured.duckdb"
    monkeypatch.setenv("DATAMIND_DUCKDB_PATH", str(configured))
    with pytest.raises(UnsafeDemoTarget):
        apply_demo_change(configured)
    with pytest.raises(UnsafeDemoTarget):
        reset_demo_db(tmp_path / "not-a-db.txt")


def test_diff_results():
    assert diff_results([["A", 1], ["B", 2]], [["A", 1], ["B", 3], ["C", 4]]) == ["B: 2 -> 3", "C: None -> 4"]
    assert diff_results([["A", 1]], [["A", 1]]) == []


def test_cli_cleanup(tmp_path, capsys):
    db = tmp_path / "cli.duckdb"
    assert data_change.main(["--db", str(db), "--direct-sql", "--cleanup"]) == 0
    out = capsys.readouterr().out
    assert "Electronics: 166000.0 -> 196000.0" in out and "Demo database deleted" in out
    assert not db.exists()
