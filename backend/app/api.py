"""FastAPI backend implementing the frontend contract (frontend/docs/API_CONTRACT.md).

Endpoints: ``GET /api/health``, ``GET /api/schema``, ``POST /api/query``.

Honesty rules from the contract are enforced here:
- ``executed`` is true only after the provider actually returned rows.
- A provider is ``connected`` only if a real ``SELECT 1`` succeeded.
- Natural-language questions go to Gemma (local Ollama, see ``app/gemma.py``),
  which only proposes SQL. The SQL is validated with ``validate_read_only_sql``
  and executed through the provider (read-only connection / read-only role).
  The answer is built from the returned rows, never from model prose. If Ollama
  is unreachable the response is a ``model_unavailable`` error, not an answer.
- Input that is itself a SELECT/WITH statement is run directly ("direct SQL
  mode") through the same validator, read-only connection and row limit.

Run locally (PowerShell, repo root)::

    .\\.venv\\Scripts\\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from collections.abc import Mapping
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import database
from .gemma import GemmaError, OllamaGemma
from .guardrails import (
    classify_db_error,
    detect_ambiguity,
    feedback_for_model,
    missing_concept,
    sanitize_error,
    screen_question,
)
from .schema_context import SchemaContext, build_context
from .sql_explain import explain_sql, summarize
from .providers import (
    MAX_ROWS,
    DataProvider,
    DuckDBProvider,
    SnowflakeConfigError,
    SnowflakeProvider,
    UnsafeQueryError,
    validate_read_only_sql,
)

log = logging.getLogger("datamind.api")

API_VERSION = "0.1.0"
MAX_QUESTION_LENGTH = 1000  # matches the frontend's MAX_QUESTION_LENGTH
DEFAULT_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")
HEALTH_CACHE_SECONDS = 30.0

PROVIDER_LABELS = {"duckdb": "DuckDB (local)", "snowflake": "Snowflake"}

MODEL_UNAVAILABLE_MESSAGE = (
    "Gemma is not connected to this backend yet, so natural-language questions "
    "cannot be answered. You can enter a read-only SQL query that starts with "
    "SELECT or WITH."
)
DIRECT_SQL_WARNING = (
    "Direct SQL mode: the input was run as SQL because it starts with SELECT or "
    "WITH. No language model was used."
)
GENERATED_SQL_WARNING = (
    "This SQL was written by {model}, a small language model. It was validated as "
    "read-only and actually executed; check the SQL to confirm it matches your question."
)
SCHEMA_CACHE_SECONDS = 300.0
DEFAULT_MAX_ATTEMPTS = 2  # first try + one corrected retry
EMPTY_RESULT_WARNING = (
    "No rows matched. The data may not contain matching records, or the filters may be too "
    "narrow; check the filters in the SQL."
)
RETRY_NOTE = (
    "Attempt {n} failed and was not used ({error}); Gemma corrected the SQL and the version "
    "shown was validated again before running."
)
DIALECTS = {"duckdb": "DuckDB", "snowflake": "Snowflake"}

_USE_DEFAULT = object()

_SQL_START = re.compile(r"^\s*(?:(?:--[^\n]*\n|/\*.*?\*/)\s*)*(SELECT|WITH)\b", re.I | re.S)
_SNOWFLAKE_HOST = re.compile(r"[\w.-]+\.snowflakecomputing\.com(?::\d+)?", re.I)


# --------------------------------------------------------------------------- #
# Request model
# --------------------------------------------------------------------------- #


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str = Field(max_length=MAX_QUESTION_LENGTH)
    provider: str | None = Field(default=None, max_length=64)

    @field_validator("question")
    @classmethod
    def _question_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be empty")
        return value

    @field_validator("provider")
    @classmethod
    def _provider_blank_is_default(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _public_error(exc: BaseException) -> str:
    """A short, user-facing error message with no hostnames or long traces."""
    text = " ".join(str(exc).split()) or type(exc).__name__
    text = _SNOWFLAKE_HOST.sub("<snowflake-host>", text)
    return text[:500]


def _is_database_error(exc: BaseException) -> bool:
    module = type(exc).__module__ or ""
    return module.startswith(("duckdb", "_duckdb", "snowflake"))


def _safe_location(provider: DataProvider) -> dict[str, str]:
    try:
        return dict(provider.location())
    except Exception:  # not configured: report nothing rather than guess
        return {}


def looks_like_sql(text: str) -> bool:
    return bool(_SQL_START.match(text))


def _new_query_id() -> str:
    return f"q_{uuid.uuid4().hex[:12]}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _row_summary(columns: list[str], rows: list[list[Any]], truncated: bool) -> str:
    """A factual answer built only from the returned rows (no model wording)."""
    if truncated:
        return f"The query returned more than {MAX_ROWS} rows; showing the first {MAX_ROWS}."
    if not rows:
        return "The query ran and returned no rows."
    count = f"The query returned {len(rows)} row{'s' if len(rows) != 1 else ''}."
    if len(columns) <= 4:
        values = ", ".join(f"{c} = {v}" for c, v in zip(columns, rows[0]))
        return f"{count} {'Result' if len(rows) == 1 else 'First row'}: {values}."
    return count


class _HealthCache:
    """Caches provider connectivity checks so health polling stays cheap."""

    def __init__(self, ttl: float) -> None:
        self.ttl = ttl
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, bool, str | None]] = {}

    def check(self, provider_id: str, provider: DataProvider) -> tuple[bool, str | None]:
        now = time.monotonic()
        with self._lock:
            hit = self._entries.get(provider_id)
            if hit and self.ttl > 0 and now - hit[0] < self.ttl:
                return hit[1], hit[2]
        try:
            provider.run_query("SELECT 1")
            outcome: tuple[bool, str | None] = (True, None)
        except SnowflakeConfigError as exc:
            outcome = (False, f"Not configured. {_public_error(exc)}")
        except Exception as exc:
            outcome = (False, _public_error(exc))
        with self._lock:
            self._entries[provider_id] = (now, *outcome)
        return outcome


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #


def _cors_origins(env: Mapping[str, str]) -> list[str]:
    raw = env.get("DATAMIND_CORS_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    return origins or list(DEFAULT_CORS_ORIGINS)


def create_app(
    providers: Mapping[str, DataProvider] | None = None,
    default_provider: str | None = None,
    *,
    allow_direct_sql: bool | None = None,
    initialize_duckdb: bool = True,
    health_cache_seconds: float = HEALTH_CACHE_SECONDS,
    env: Mapping[str, str] | None = None,
    generator: Any = _USE_DEFAULT,
) -> FastAPI:
    """Build the API. ``generator`` is the question-to-SQL model client
    (default: Ollama Gemma from env; ``None`` disables natural-language questions)."""
    env = os.environ if env is None else env
    sql_generator = OllamaGemma.from_env(env) if generator is _USE_DEFAULT else generator
    registry: dict[str, DataProvider] = dict(
        providers
        if providers is not None
        else {"duckdb": DuckDBProvider(), "snowflake": SnowflakeProvider()}
    )
    default_id = (default_provider or env.get("DATAMIND_PROVIDER", "duckdb")).strip().lower()
    if default_id not in registry:
        raise ValueError(f"Default provider {default_id!r} is not registered.")
    if allow_direct_sql is None:
        allow_direct_sql = env.get("DATAMIND_ALLOW_DIRECT_SQL", "true").strip().lower() != "false"
    health_cache = _HealthCache(health_cache_seconds)
    try:
        max_attempts = int(env.get("DATAMIND_GEMMA_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS))
    except ValueError:
        max_attempts = DEFAULT_MAX_ATTEMPTS
    max_attempts = min(max(max_attempts, 1), 3)  # strict bound

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if initialize_duckdb and isinstance(registry.get("duckdb"), DuckDBProvider):
            database.initialize_database()  # idempotent dev seed
        yield

    app = FastAPI(title="DataMind API", version=API_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(env),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
        allow_credentials=False,
    )

    model_cache: dict[str, Any] = {"at": None, "value": None}
    schema_cache: dict[str, tuple[float, SchemaContext]] = {}
    include_values = env.get("DATAMIND_SCHEMA_VALUES", "true").strip().lower() != "false"

    def model_status() -> dict[str, Any]:
        if sql_generator is None:
            return {"name": "Gemma", "runtime": None, "available": False,
                    "detail": "No Gemma runtime is configured."}
        now = time.monotonic()
        if model_cache["at"] is None or health_cache_seconds <= 0 or now - model_cache["at"] >= health_cache_seconds:
            status = sql_generator.status()
            model_cache["value"] = {"name": status.name, "runtime": status.runtime,
                                    "available": status.available, "detail": status.detail}
            model_cache["at"] = now
        return dict(model_cache["value"])

    def schema_context_for(pid: str, provider: DataProvider) -> SchemaContext:
        """Schema + declared/inferred relationships + example values + measure hints (cached)."""
        now = time.monotonic()
        hit = schema_cache.get(pid)
        if hit and now - hit[0] < SCHEMA_CACHE_SECONDS:
            return hit[1]
        context = build_context(provider, provider.get_schema(), include_values=include_values)
        schema_cache[pid] = (now, context)
        return context

    # ---- /api/health ------------------------------------------------------ #

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        statuses = []
        for pid, provider in registry.items():
            connected, detail = health_cache.check(pid, provider)
            status: dict[str, Any] = {
                "id": pid,
                "label": PROVIDER_LABELS.get(pid, pid),
                "connected": connected,
                "is_default": pid == default_id,
                **_safe_location(provider),
            }
            if detail:
                status["detail"] = detail
            statuses.append(status)
        model = model_status()
        default_ok = any(s["connected"] for s in statuses if s["is_default"])
        if default_ok and model["available"]:
            overall = "ok"
        elif any(s["connected"] for s in statuses):
            overall = "degraded"
        else:
            overall = "down"
        return {
            "status": overall,
            "version": API_VERSION,
            "row_limit": MAX_ROWS,
            "providers": statuses,
            "model": model,
        }

    # ---- /api/schema ------------------------------------------------------ #

    @app.get("/api/schema")
    def schema(provider: str | None = Query(default=None, max_length=64)) -> dict[str, Any]:
        pid = (provider or default_id).strip().lower()
        if pid not in registry:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {pid}")
        source = registry[pid]
        try:
            tables = source.get_schema()
        except SnowflakeConfigError as exc:
            raise HTTPException(503, detail=f"{pid} is not configured. {_public_error(exc)}")
        except Exception as exc:
            log.exception("Schema discovery failed for %s", pid)
            message = _public_error(exc) if _is_database_error(exc) else "Schema discovery failed."
            raise HTTPException(503, detail=message)
        location = _safe_location(source)
        return {
            "provider": pid,
            "database": location.get("database"),
            "schemas": [
                {
                    "name": location.get("schema") or "default",
                    "tables": [
                        {
                            "name": table,
                            "columns": [
                                {"name": c["name"], "data_type": c["type"], "nullable": c["nullable"]}
                                for c in columns
                            ],
                        }
                        for table, columns in tables.items()
                    ],
                }
            ],
        }

    # ---- /api/query ------------------------------------------------------- #

    def execute(provider: DataProvider, sql: str) -> tuple[str, Any]:
        """Run validated SQL. Returns ("ok", (result, ms, started_at)) or
        ("config", exc) / ("db", exc) / ("internal", exc)."""
        started_at = _utc_now_iso()
        t0 = time.perf_counter()
        try:
            result = provider.run_query(sql)
        except SnowflakeConfigError as exc:
            return "config", exc
        except Exception as exc:
            if not _is_database_error(exc):
                log.exception("Unexpected failure running query")
                return "internal", exc
            return "db", exc
        return "ok", (result, round((time.perf_counter() - t0) * 1000, 1), started_at)

    @app.post("/api/query")
    def query(body: QueryRequest) -> JSONResponse:
        pid = (body.provider or default_id).lower()
        base: dict[str, Any] = {
            "query_id": _new_query_id(),
            "question": body.question,
            "provider": pid,
            "executed": False,
        }

        def respond(payload: dict[str, Any], status_code: int = 200) -> JSONResponse:
            return JSONResponse({**base, **payload}, status_code=status_code)

        def error(stage: str, code: str, message: str, **extra: Any) -> JSONResponse:
            return respond(
                {"status": "error", "error": {"stage": stage, "code": code, "message": message}, **extra}
            )

        if pid not in registry:
            return error("validation", "unknown_provider", f"Unknown provider: {pid}")
        provider = registry[pid]
        label = PROVIDER_LABELS.get(pid, pid)
        passed = {"passed": True, "read_only": True, "limit_applied": MAX_ROWS, "messages": []}

        def failed_validation(exc: UnsafeQueryError) -> dict[str, Any]:
            return {"passed": False, "read_only": False, "messages": [str(exc)]}

        def refused_sql(sql: str, exc: UnsafeQueryError, warnings: list[str]) -> JSONResponse:
            return respond(
                {
                    "status": "refused",
                    "answer": (
                        f"This query was not run: {exc} DataMind only runs a single "
                        "read-only SELECT or WITH statement."
                    ),
                    "sql": sql,
                    "validation": failed_validation(exc),
                    "warnings": warnings,
                }
            )

        def db_error(sql: str, exc: BaseException, warnings: list[str]) -> JSONResponse:
            message = _public_error(exc)
            info = classify_db_error(message)
            if info.code == "unknown_object":
                message = f"The query refers to a table or column that does not exist: {message}"
            return error("execution", info.code, message, sql=sql, validation=passed, warnings=warnings)

        def success(sql: str, outcome: Any, warnings: list[str], origin: str) -> JSONResponse:
            result, duration_ms, started_at = outcome
            rows, truncated = result["rows"], result["truncated"]
            execution: dict[str, Any] = {
                "duration_ms": duration_ms, "started_at": started_at, **_safe_location(provider)
            }
            if result.get("provider_query_id"):
                execution["provider_query_id"] = result["provider_query_id"]
            explained = explain_sql(sql, pid, MAX_ROWS)
            fields = explained.as_contract()
            if explained.parsed and not fields["filters"]:
                fields["filters"] = ["None (all rows considered)"]
            explanation = {"summary": f"{origin} {summarize(explained, len(rows), truncated)}", **fields}
            if not rows:
                warnings = warnings + [EMPTY_RESULT_WARNING]
            payload: dict[str, Any] = {
                "status": "success",
                "executed": True,
                "answer": _row_summary(result["columns"], rows, truncated),
                "explanation": explanation,
                "sql": sql,
                "validation": passed,
                "columns": [{"name": c} for c in result["columns"]],
                "rows": rows,
                "truncated": truncated,
                "execution": execution,
                "warnings": warnings,
            }
            if not truncated:
                payload["row_count"] = len(rows)  # total is unknown when truncated
            return respond(payload)

        def run(sql: str, warnings: list[str]) -> tuple[str, Any]:
            kind, value = execute(provider, sql)
            if kind == "config":
                return "done", error(
                    "execution", "provider_not_configured", f"{pid} is not configured. {_public_error(value)}",
                    sql=sql, validation=passed, warnings=warnings,
                )
            if kind == "internal":
                return "done", respond(
                    {
                        "status": "error",
                        "error": {"stage": "internal", "code": "internal_error", "message": "Internal server error."},
                        "sql": sql,
                    },
                    status_code=500,
                )
            return kind, value

        # ---- direct SQL mode -------------------------------------------- #
        if allow_direct_sql and looks_like_sql(body.question):
            sql, warnings = body.question, [DIRECT_SQL_WARNING]
            try:
                validate_read_only_sql(sql)
            except UnsafeQueryError as exc:
                if exc.is_refusal:
                    return refused_sql(sql, exc, warnings)
                return error("validation", exc.code, str(exc), sql=sql,
                             validation=failed_validation(exc), warnings=warnings)
            kind, value = run(sql, warnings)
            if kind == "done":
                return value
            if kind == "db":
                return db_error(sql, value, warnings)
            return success(sql, value, warnings, f"Ran the SQL exactly as entered on {label}; no language model was used.")

        # ---- natural-language question ------------------------------------ #
        screening = screen_question(body.question)
        if not screening.allowed:
            return respond(
                {
                    "status": "refused",
                    "answer": screening.message,
                    "validation": {"passed": False, "read_only": True,
                                   "messages": [f"Blocked before SQL generation ({screening.kind} request)."]},
                }
            )
        if sql_generator is None:
            return error("generation", "model_unavailable", MODEL_UNAVAILABLE_MESSAGE)
        try:
            context = schema_context_for(pid, provider)
        except SnowflakeConfigError as exc:
            return error("execution", "provider_not_configured", f"{pid} is not configured. {_public_error(exc)}")
        except Exception as exc:
            log.exception("Schema discovery failed for %s", pid)
            message = _public_error(exc) if _is_database_error(exc) else "Schema discovery failed."
            return error("generation", "schema_unavailable", f"Could not read the schema: {message}")
        schema_text = context.text

        # Schema-aware checks that do not need the model.
        missing = missing_concept(body.question, context.schema)
        if missing:
            return respond(
                {
                    "status": "refused",
                    "answer": missing,
                    "validation": {"passed": False, "read_only": True,
                                   "messages": ["Blocked before SQL generation (missing data)."]},
                }
            )
        ambiguity = detect_ambiguity(body.question, context.measure_options)
        if ambiguity:
            clarifying_question, options = ambiguity
            return respond(
                {
                    "status": "clarification_needed",
                    "answer": clarifying_question,
                    "clarification": {"question": clarifying_question, "options": options},
                }
            )

        dialect = DIALECTS.get(pid, "ANSI")
        feedback: str | None = None
        failures: list[str] = []
        model_ms = 0.0
        for attempt in range(1, max_attempts + 1):
            base["generation_attempts"] = attempt
            try:
                if feedback is None:
                    generation = sql_generator.generate(body.question, schema_text, dialect)
                else:
                    generation = sql_generator.generate(body.question, schema_text, dialect, feedback=feedback)
            except GemmaError as exc:
                return error("generation", exc.code, str(exc))
            model_ms += generation.duration_ms
            base["model"] = {"name": generation.model, "duration_ms": round(model_ms, 1)}

            if generation.clarification is not None:
                c = generation.clarification
                return respond(
                    {
                        "status": "clarification_needed",
                        "answer": c.question,
                        "clarification": {"question": c.question, "options": list(c.options)},
                    }
                )
            if generation.refusal or not generation.sql:
                return respond(
                    {
                        "status": "refused",
                        "answer": (
                            "This question cannot be answered from the available data: "
                            f"{generation.refusal or 'no query was produced.'}"
                        ),
                    }
                )

            sql = generation.sql
            warnings = [GENERATED_SQL_WARNING.format(model=generation.model)] + failures
            last = attempt == max_attempts
            try:
                validate_read_only_sql(sql)
            except UnsafeQueryError as exc:
                if exc.is_refusal:  # unsafe SQL is never retried or executed
                    return refused_sql(sql, exc, warnings)
                if last:
                    return error("validation", exc.code, str(exc), sql=sql,
                                 validation=failed_validation(exc), warnings=warnings)
                failures.append(RETRY_NOTE.format(n=attempt, error=sanitize_error(str(exc))))
                feedback = feedback_for_model(sql, f"The SQL could not be validated: {exc}")
                continue

            kind, value = run(sql, warnings)
            if kind == "done":
                return value
            if kind == "db":
                message = _public_error(value)
                if classify_db_error(message).retryable and not last:
                    failures.append(RETRY_NOTE.format(n=attempt, error=sanitize_error(message)))
                    feedback = feedback_for_model(sql, message)
                    continue
                return db_error(sql, value, warnings)
            origin = (
                f"Gemma ({generation.model}) wrote this SQL from your question using the {label} "
                f"schema; it passed the read-only check and ran on {label}."
            )
            return success(sql, value, warnings, origin)
        return error("internal", "internal_error", "Internal server error.")  # pragma: no cover

    return app


app = create_app()
