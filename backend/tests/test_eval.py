"""Tests for the evaluation suite: fixtures, ground truth, comparison and runner."""

import duckdb
import pytest

from app.gemma import Clarification, Generation, ModelStatus
from eval.compare import first_row_matches, rows_match, values_equal
from eval.datasets import build_dataset
from eval.run_eval import judge, load_cases, plan_request, run

CASES = load_cases()
BEHAVIORS = {"rows", "top", "empty", "refused", "clarification", "not_answered"}


# --- the case file ---------------------------------------------------------- #


def test_cases_are_well_formed():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)) and len(ids) >= 20
    for c in CASES:
        for key in ("id", "dataset", "category", "difficulty", "question", "tables", "assumptions", "expected"):
            assert key in c, (c["id"], key)
        assert c["dataset"] in ("sales", "retail", "tpch")
        assert c["difficulty"] in ("easy", "medium", "hard")
        assert c["expected"]["behavior"] in BEHAVIORS
        if c["expected"]["behavior"] in ("rows", "top", "empty"):
            assert c["reference_sql"], c["id"]
        if c["expected"]["behavior"] in ("rows", "top"):
            # Literal expected rows, or (TPC-H only, no copies allowed) computed live.
            assert ("rows" in c["expected"]) != bool(c["expected"].get("from_reference_sql")), c["id"]
            if c["expected"].get("from_reference_sql"):
                assert c["dataset"] == "tpch"


def test_case_set_covers_required_categories():
    categories = {c["category"] for c in CASES}
    for needed in ("aggregation", "filtering", "grouping", "ranking", "multi_step", "join", "phrasing",
                   "date_filter", "empty_result", "ambiguous", "missing_data", "modify_request",
                   "prompt_injection", "unsupported"):
        assert needed in categories, needed


@pytest.fixture(scope="module")
def fixture_dbs(tmp_path_factory):
    d = tmp_path_factory.mktemp("eval")
    return {name: build_dataset(name, d) for name in ("sales", "retail")}


@pytest.mark.parametrize("case", [c for c in CASES if c["reference_sql"] and c["dataset"] != "tpch"],
                         ids=lambda c: c["id"])
def test_reference_sql_reproduces_expected_answer(case, fixture_dbs):
    """Ground truth is independent of Gemma: hand-written SQL on deterministic fixtures."""
    with duckdb.connect(str(fixture_dbs[case["dataset"]]), read_only=True) as con:
        rows = [list(r) for r in con.execute(case["reference_sql"]).fetchall()]
    exp = case["expected"]
    if exp["behavior"] == "empty":
        assert rows == []
    elif exp["behavior"] == "top":
        assert first_row_matches(exp["rows"][0], rows)
    else:
        assert rows_match(exp["rows"], rows)


def test_retail_fixture_has_foreign_keys(fixture_dbs):
    with duckdb.connect(str(fixture_dbs["retail"]), read_only=True) as con:
        fks = con.execute(
            "SELECT COUNT(*) FROM duckdb_constraints() WHERE constraint_type = 'FOREIGN KEY'"
        ).fetchone()[0]
    assert fks == 3


def test_build_dataset_is_fresh_each_time(tmp_path):
    first = build_dataset("retail", tmp_path)
    with duckdb.connect(str(first)) as con:
        con.execute("DELETE FROM order_items")
    second = build_dataset("retail", tmp_path)
    with duckdb.connect(str(second), read_only=True) as con:
        assert con.execute("SELECT COUNT(*) FROM order_items").fetchone()[0] == 13
    with pytest.raises(ValueError):
        build_dataset("nope", tmp_path)


# --- comparison --------------------------------------------------------------- #


def test_values_equal_tolerance_and_case():
    assert values_equal(166000, 166000.0)
    assert values_equal(5166.6667, 5166.666666666667)
    assert not values_equal(100, 101)
    assert values_equal("Electronics", " electronics ")
    assert values_equal(0.8217821782, 82.17821782, scale=100.0)
    assert values_equal(None, None) and not values_equal(None, 0)
    assert values_equal(12, "12") and not values_equal(12, "twelve")


def test_rows_match_ignores_column_order_aliases_and_extra_columns():
    expected = [["Electronics", 166000], ["Furniture", 36000]]
    assert rows_match(expected, [[36000.0, "Furniture"], [166000.0, "Electronics"]])
    assert rows_match(expected, [["Electronics", 9, 166000.0], ["Furniture", 8, 36000.0]])
    assert not rows_match(expected, [["Electronics", 166000.0]])
    assert not rows_match(expected, [["Electronics", 166000.0], ["Furniture", 35000.0]])
    assert rows_match([[0.82178]], [[82.178]], accept_percent=True)
    assert not rows_match([[0.82178]], [[82.178]])
    assert rows_match([], []) and not rows_match([], [[1]])


def test_first_row_matches():
    assert first_row_matches(["Laptop", 100000], [["Laptop", 100000.0], ["Phone", 60000.0]])
    assert not first_row_matches(["Laptop", 100000], [["Phone", 60000.0], ["Laptop", 100000.0]])
    assert not first_row_matches(["Laptop", 100000], [])


# --- judging --------------------------------------------------------------------- #


CASE = {"id": "X", "expected": {"behavior": "rows", "rows": [[3]]}}


def test_judge_success_and_failures():
    assert judge(CASE, {"status": "success", "executed": True, "rows": [[3]]})[0]
    assert not judge(CASE, {"status": "success", "executed": True, "rows": [[4]]})[0]
    ok, reason = judge(CASE, {"status": "error", "error": {"code": "unknown_object"}})
    assert not ok and "unknown_object" in reason


def test_judge_behaviors():
    refused = {"id": "R", "expected": {"behavior": "refused"}}
    assert judge(refused, {"status": "refused", "executed": False})[0]
    assert not judge(refused, {"status": "success", "executed": True, "rows": [[1]]})[0]
    clar = {"id": "C", "expected": {"behavior": "clarification"}}
    assert judge(clar, {"status": "clarification_needed", "executed": False})[0]
    na = {"id": "N", "expected": {"behavior": "not_answered"}}
    assert judge(na, {"status": "error", "executed": False})[0]
    assert not judge(na, {"status": "success", "executed": True, "rows": [[0.3]]})[0]
    empty = {"id": "E", "expected": {"behavior": "empty"}}
    assert judge(empty, {"status": "success", "executed": True, "rows": []})[0]
    assert not judge(empty, {"status": "success", "executed": True, "rows": [[1]]})[0]


def test_plan_request():
    by_id = {c["id"]: c for c in CASES}
    assert plan_request(by_id["S01"], "reference") == by_id["S01"]["reference_sql"]
    assert plan_request(by_id["S13"], "reference") == by_id["S13"]["question"]  # screened refusal
    assert plan_request(by_id["S11"], "reference") is None  # needs the model
    assert plan_request(by_id["S11"], "gemma") == by_id["S11"]["question"]


# --- runner ------------------------------------------------------------------------ #


def test_reference_run_passes_every_executed_case(tmp_path):
    report = run(mode="reference", workdir=tmp_path, env={})
    assert report["failed"] == 0, [r for r in report["results"] if r["outcome"] == "failed"]
    assert report["executed"] >= 20 and report["accuracy"] == 1.0
    skipped = {r["id"] for r in report["results"] if r["outcome"] == "skipped"}
    assert skipped == {"S11", "S12", "R11"}  # cases that need the model are never counted as passes


class ScriptedGemma:
    """Answers from a lookup table so the gemma-mode runner can be tested offline."""

    model = "scripted"

    def __init__(self, answers):
        self.answers = answers

    def status(self):
        return ModelStatus("scripted", "test", True)

    def generate(self, question, schema_text, dialect, feedback=None):
        answer = self.answers.get(question)
        if isinstance(answer, Clarification):
            return Generation(model="scripted", duration_ms=1.0, clarification=answer)
        if answer is None:
            return Generation(model="scripted", duration_ms=1.0, refusal="no data for that")
        return Generation(model="scripted", duration_ms=1.0, sql=answer)


def test_gemma_mode_scores_correct_and_wrong_answers(tmp_path):
    by_id = {c["id"]: c for c in CASES}
    answers = {c["question"]: c["reference_sql"] for c in CASES if c["reference_sql"]}
    answers[by_id["S11"]["question"]] = Clarification("Revenue or units?", ("a", "b"))
    answers[by_id["R11"]["question"]] = Clarification("Revenue or orders?", ())
    answers[by_id["S02"]["question"]] = "SELECT category, SUM(quantity) FROM sales GROUP BY category"  # wrong
    report = run(mode="gemma", generator=ScriptedGemma(answers), workdir=tmp_path, env={})
    failed = {r["id"] for r in report["results"] if r["outcome"] == "failed"}
    assert failed == {"S02"}
    assert report["skipped"] == 0
    assert report["passed"] == report["total_cases"] - 1


def test_local_runs_never_include_live_only_tpch_cases(tmp_path):
    report = run(mode="reference", workdir=tmp_path, env={}, datasets=("sales", "retail", "tpch"))
    assert not any(r["dataset"] == "tpch" for r in report["results"])


def test_expected_rows_can_be_computed_live_from_reference_sql(tmp_path):
    """The TPC-H mechanism, exercised offline on the retail fixture."""
    live_case = {
        "id": "L01", "dataset": "retail", "category": "join", "difficulty": "medium",
        "question": "How many orders are there per status?", "tables": ["orders"], "assumptions": [],
        "reference_sql": "SELECT status, COUNT(*) AS n FROM orders GROUP BY status",
        "expected": {"behavior": "rows", "from_reference_sql": True},
    }
    good = ScriptedGemma({live_case["question"]: "SELECT status, COUNT(*) FROM orders GROUP BY status"})
    report = run(mode="gemma", generator=good, workdir=tmp_path, env={}, cases=[live_case])
    [r] = report["results"]
    assert r["outcome"] == "passed"
    assert sorted(r["expected_rows_computed_live"]) == [["cancelled", 1], ["completed", 7]]

    wrong = ScriptedGemma({live_case["question"]: "SELECT status, COUNT(*) FROM orders WHERE order_id > 104 GROUP BY status"})
    report = run(mode="gemma", generator=wrong, workdir=tmp_path, env={}, cases=[live_case])
    assert report["results"][0]["outcome"] == "failed"

    broken = {**live_case, "reference_sql": "SELECT nope FROM orders"}
    report = run(mode="gemma", generator=good, workdir=tmp_path, env={}, cases=[broken])
    assert report["results"][0]["outcome"] == "failed"
    assert report["results"][0]["reason"].startswith("reference query failed")
