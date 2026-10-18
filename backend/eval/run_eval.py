r"""Run the DataMind NL-to-SQL evaluation set through the real API pipeline.

Modes
  reference  No model. Row/empty cases send their reference SQL (direct SQL
             mode) to check the fixtures, API and comparison; screened refusal
             cases send the question. Cases that need a model are SKIPPED.
  gemma      Every case sends the natural-language question; Gemma (Ollama)
             writes the SQL. This measures the real system.

Providers
  duckdb     (default) fresh local fixture databases; no account needed.
  snowflake  live Snowflake (needs backend/.env loaded into the shell; queries
             run with the read-only role). --dataset sales uses DATAMIND.PUBLIC.SALES;
             --dataset tpch uses SNOWFLAKE_SAMPLE_DATA.TPCH_SF1 through a
             process-only override (backend/.env is not changed). TPC-H expected
             rows are computed live from reference_sql, since the data may not be
             copied into the repository.

Examples (PowerShell, repo root)
  .\.venv\Scripts\python.exe backend\eval\run_eval.py --mode reference
  .\.venv\Scripts\python.exe backend\eval\run_eval.py --mode gemma
  .\.venv\Scripts\python.exe backend\eval\run_eval.py --mode gemma --provider snowflake
  .\.venv\Scripts\python.exe backend\eval\run_eval.py --mode gemma --provider snowflake --dataset tpch
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.api import create_app  # noqa: E402
from app.gemma import OllamaGemma  # noqa: E402
from app.guardrails import screen_question  # noqa: E402
from app.providers import DuckDBProvider, SnowflakeProvider, SnowflakeSettings  # noqa: E402
from eval.compare import first_row_matches, rows_match  # noqa: E402
from eval.datasets import build_dataset  # noqa: E402

TPCH_LOCATION = {"SNOWFLAKE_DATABASE": "SNOWFLAKE_SAMPLE_DATA", "SNOWFLAKE_SCHEMA": "TPCH_SF1"}
LIVE_ONLY_DATASETS = {"tpch"}
CASES_FILE = Path(__file__).resolve().parent / "cases.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_cases(path: Path = CASES_FILE) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def judge(case: dict[str, Any], body: dict[str, Any]) -> tuple[bool, str]:
    """Return (passed, reason) for one API response."""
    exp = case["expected"]
    behavior = exp["behavior"]
    status = body.get("status")
    executed = body.get("executed") is True
    rows = body.get("rows") or []
    if behavior in ("rows", "top", "empty") and status != "success":
        err = body.get("error") or {}
        detail = err.get("code") or body.get("answer") or ""
        return False, f"expected an answer, got status={status} {detail}".strip()
    if behavior == "rows":
        candidates = [exp["rows"]] + exp.get("alternatives", [])
        if any(rows_match(c, rows, accept_percent=exp.get("accept_percent", False)) for c in candidates):
            return True, "rows match"
        return False, f"rows differ: got {rows[:5]}"
    if behavior == "top":
        if first_row_matches(exp["rows"][0], rows):
            return True, "top row matches"
        return False, f"top row differs: got {rows[:3]}"
    if behavior == "empty":
        return (executed and not rows), ("empty result" if not rows else f"expected no rows, got {len(rows)}")
    if behavior == "refused":
        ok = status == "refused" and not executed
        return ok, "refused" if ok else f"expected refusal, got status={status}"
    if behavior == "clarification":
        ok = status == "clarification_needed" and not executed
        return ok, "asked to clarify" if ok else f"expected clarification, got status={status}"
    if behavior == "not_answered":
        ok = status in ("refused", "clarification_needed", "error") and not executed
        return ok, f"not answered ({status})" if ok else f"answered something that cannot be computed: {rows[:3]}"
    raise ValueError(f"Unknown behavior {behavior!r} in case {case['id']}")


def plan_request(case: dict[str, Any], mode: str) -> str | None:
    """Text to send, or None when the case must be skipped in this mode."""
    if mode == "gemma":
        return case["question"]
    behavior = case["expected"]["behavior"]
    if behavior in ("rows", "top", "empty"):
        return case["reference_sql"]
    if behavior == "refused" and not screen_question(case["question"]).allowed:
        return case["question"]
    return None  # clarification / missing-data judgement needs the model


def run(
    mode: str = "reference",
    provider: str = "duckdb",
    datasets: tuple[str, ...] = ("sales", "retail"),
    generator: Any = None,
    workdir: Path | None = None,
    cases: list[dict[str, Any]] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = dict(os.environ if env is None else env)
    cases = [c for c in (cases or load_cases()) if c["dataset"] in datasets]
    if provider == "snowflake":
        cases = [c for c in cases if c["dataset"] in ("sales", "tpch")]  # retail exists only locally
    else:
        cases = [c for c in cases if c["dataset"] not in LIVE_ONLY_DATASETS]
    if mode == "gemma" and generator is None:
        generator = OllamaGemma.from_env(env)
    if mode == "reference":
        generator = None

    tmp = None
    if workdir is None:
        tmp = tempfile.TemporaryDirectory(prefix="datamind-eval-")
        workdir = Path(tmp.name)

    clients: dict[str, TestClient] = {}

    def client_for(dataset: str) -> TestClient:
        if dataset not in clients:
            if provider == "snowflake":
                overrides = TPCH_LOCATION if dataset == "tpch" else {}
                registry = {"snowflake": SnowflakeProvider(SnowflakeSettings.from_env({**env, **overrides}))}
            else:
                registry = {"duckdb": DuckDBProvider(db_path=build_dataset(dataset, workdir))}
            app = create_app(
                providers=registry,
                default_provider=provider,
                initialize_duckdb=False,
                health_cache_seconds=0,
                env=env,
                generator=generator,
                allow_direct_sql=True,
            )
            clients[dataset] = TestClient(app)
        return clients[dataset]

    results = []
    try:
        for case in cases:
            text = plan_request(case, mode)
            record: dict[str, Any] = {
                "id": case["id"], "dataset": case["dataset"], "category": case["category"],
                "difficulty": case["difficulty"], "behavior": case["expected"]["behavior"],
                "question": case["question"],
            }
            if text is None:
                record.update(outcome="skipped", reason="needs the model (run with --mode gemma)")
                results.append(record)
                continue
            started = time.perf_counter()
            client = client_for(case["dataset"])
            judged_case = case
            if case["expected"].get("from_reference_sql"):
                # Live ground truth: the hand-written reference SQL, run through the same
                # validated read-only path. Never derived from Gemma's output.
                ref = client.post("/api/query", json={"question": case["reference_sql"]}).json()
                if ref.get("status") != "success":
                    record.update(outcome="failed", reason=f"reference query failed: {ref.get('error')}")
                    results.append(record)
                    continue
                judged_case = {**case, "expected": {**case["expected"], "rows": ref["rows"]}}
                record["expected_rows_computed_live"] = ref["rows"][:10]
                record["reference_query_id"] = (ref.get("execution") or {}).get("provider_query_id")
            res = client.post("/api/query", json={"question": text})
            body = res.json()
            passed, reason = judge(judged_case, body)
            record.update(
                outcome="passed" if passed else "failed",
                reason=reason,
                http_status=res.status_code,
                status=body.get("status"),
                executed=body.get("executed"),
                sql=body.get("sql"),
                rows=(body.get("rows") or [])[:10],
                error=body.get("error"),
                generation_attempts=body.get("generation_attempts"),
                model=body.get("model"),
                provider_query_id=(body.get("execution") or {}).get("provider_query_id"),
                seconds=round(time.perf_counter() - started, 2),
            )
            results.append(record)
    finally:
        for c in clients.values():
            c.close()
        if tmp is not None:
            tmp.cleanup()

    counts = Counter(r["outcome"] for r in results)
    executed = counts["passed"] + counts["failed"]
    by_category: dict[str, dict[str, int]] = {}
    for r in results:
        bucket = by_category.setdefault(r["category"], {"passed": 0, "failed": 0, "skipped": 0})
        bucket[r["outcome"]] += 1
    return {
        "mode": mode,
        "provider": provider,
        "model": getattr(generator, "model", None),
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_cases": len(results),
        "executed": executed,
        "passed": counts["passed"],
        "failed": counts["failed"],
        "skipped": counts["skipped"],
        "accuracy": round(counts["passed"] / executed, 4) if executed else None,
        "by_category": by_category,
        "results": results,
    }


def print_report(report: dict[str, Any]) -> None:
    print(f"\nDataMind evaluation | mode={report['mode']} provider={report['provider']} model={report['model']}")
    print("-" * 100)
    for r in report["results"]:
        mark = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[r["outcome"]]
        print(f"{mark}  {r['id']:<4} {r['category']:<16} {r['question'][:46]:<46}  {r['reason'][:60]}")
    print("-" * 100)
    acc = report["accuracy"]
    acc_text = f"{acc:.1%}" if acc is not None else "n/a"
    print(
        f"executed {report['executed']} | passed {report['passed']} | failed {report['failed']} | "
        f"skipped {report['skipped']} | accuracy {acc_text}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the DataMind evaluation set.")
    parser.add_argument("--mode", choices=("reference", "gemma"), default="reference")
    parser.add_argument("--provider", choices=("duckdb", "snowflake"), default="duckdb")
    parser.add_argument("--dataset", choices=("sales", "retail", "tpch", "all"), default="all",
                        help="'all' = sales + retail locally, or sales on Snowflake; tpch is Snowflake-only")
    parser.add_argument("--output", type=Path, help="JSON report path (default: backend/eval/results/...)")
    args = parser.parse_args(argv)

    if args.dataset == "tpch" and args.provider != "snowflake":
        parser.error("--dataset tpch needs --provider snowflake (TPC-H lives in Snowflake only)")
    datasets = ("sales", "retail") if args.dataset == "all" else (args.dataset,)
    report = run(mode=args.mode, provider=args.provider, datasets=datasets)
    print_report(report)
    out = args.output or RESULTS_DIR / f"{args.mode}-{args.provider}-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"report written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
