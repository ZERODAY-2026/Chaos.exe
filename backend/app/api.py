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
from .gemma import GemmaError, OllamaGemma, format_schema
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
    schema_cache: dict[str, tuple[float, str]] = {}

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

    def schema_text_for(pid: str, provider: DataProvider) -> str:
        now = time.monotonic()
        hit = schema_cache.get(pid)
        if hit and now - hit[0] < SCHEMA_CACHE_SECONDS:
            return hit[1]
        text = format_schema(provider.get_schema())
        schema_cache[pid] = (now, text)
        return text

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

        if allow_direct_sql and looks_like_sql(body.question):
            sql = body.question
            warnings = [DIRECT_SQL_WARNING]
            summary = f"Ran the SQL exactly as entered on {label}. No language model was used."
        else:
            # Natural-language question: Gemma proposes SQL; it is never trusted.
            if sql_generator is None:
                return error("generation", "model_unavailable", MODEL_UNAVAILABLE_MESSAGE)
            try:
                schema_text = schema_text_for(pid, provider)
            except SnowflakeConfigError as exc:
                return error("execution", "provider_not_configured", f"{pid} is not configured. {_public_error(exc)}")
            except Exception as exc:
                log.exception("Schema discovery failed for %s", pid)
                message = _public_error(exc) if _is_database_error(exc) else "Schema discovery failed."
                return error("generation", "schema_unavailable", f"Could not read the schema: {message}")
            try:
                generation = sql_generator.generate(body.question, schema_text, DIALECTS.get(pid, "ANSI"))
            except GemmaError as exc:
                return error("generation", exc.code, str(exc))
            base["model"] = {"name": generation.model, "duration_ms": generation.duration_ms}
            if generation.refusal or not generation.sql:
                return respond(
                    {
                        "status": "refused",
                        "answer": (
                            "Gemma could not answer this from the available data: "
                            f"{generation.refusal or 'no query was produced.'}"
                        ),
                    }
                )
            sql = generation.sql
            warnings = [GENERATED_SQL_WARNING.format(model=generation.model)]
            summary = (
                f"Gemma ({generation.model}) wrote this SQL from your question using the "
                f"{label} schema. It passed the read-only check and ran on {label}."
            )

        try:
            validate_read_only_sql(sql)
        except UnsafeQueryError as exc:
            validation = {"passed": False, "read_only": False, "messages": [str(exc)]}
            if exc.is_refusal:
                return respond(
                    {
                        "status": "refused",
                        "answer": (
                            f"This query was not run: {exc} DataMind only runs a single "
                            "read-only SELECT or WITH statement."
                        ),
                        "sql": sql,
                        "validation": validation,
                        "warnings": warnings,
                    }
                )
            return error("validation", exc.code, str(exc), sql=sql, validation=validation, warnings=warnings)

        validation = {"passed": True, "read_only": True, "limit_applied": MAX_ROWS, "messages": []}
        started_at = _utc_now_iso()
        t0 = time.perf_counter()
        try:
            result = provider.run_query(sql)
        except SnowflakeConfigError as exc:
            return error(
                "execution", "provider_not_configured", f"{pid} is not configured. {_public_error(exc)}",
                sql=sql, validation=validation, warnings=warnings,
            )
        except Exception as exc:
            if not _is_database_error(exc):
                log.exception("Unexpected failure running query on %s", pid)
                return respond(
                    {
                        "status": "error",
                        "error": {"stage": "internal", "code": "internal_error", "message": "Internal server error."},
                        "sql": sql,
                    },
                    status_code=500,
                )
            return error(
                "execution", "execution_failed", _public_error(exc),
                sql=sql, validation=validation, warnings=warnings,
            )
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)

        rows, truncated = result["rows"], result["truncated"]
        execution: dict[str, Any] = {"duration_ms": duration_ms, "started_at": started_at, **_safe_location(provider)}
        if result.get("provider_query_id"):
            execution["provider_query_id"] = result["provider_query_id"]
        payload: dict[str, Any] = {
            "status": "success",
            "executed": True,
            "answer": _row_summary(result["columns"], rows, truncated),
            "explanation": {"summary": summary},
            "sql": sql,
            "validation": validation,
            "columns": [{"name": c} for c in result["columns"]],
            "rows": rows,
            "truncated": truncated,
            "execution": execution,
            "warnings": warnings,
        }
        if not truncated:
            payload["row_count"] = len(rows)  # total is unknown when truncated
        return respond(payload)

    return app


app = create_app()
