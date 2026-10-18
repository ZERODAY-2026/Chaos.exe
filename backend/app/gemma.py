"""Gemma (via a local Ollama server) turns a question into one SQL query.

The model only *proposes* SQL. The API validates it with
``validate_read_only_sql`` and runs it through the existing provider (read-only
connection / read-only Snowflake role); the model never touches the database.

Configuration (environment variables, all optional):
    OLLAMA_BASE_URL          default http://127.0.0.1:11434
    DATAMIND_GEMMA_MODEL     default gemma3:1b
    DATAMIND_GEMMA_TIMEOUT   seconds per generation, default 120

Uses only the standard library, so no extra dependency is needed.
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .results import Schema

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "gemma3:1b"
DEFAULT_TIMEOUT_SECONDS = 120.0
STATUS_TIMEOUT_SECONDS = 2.0
MAX_SCHEMA_CHARS = 6000  # keep the prompt small for a 1B model on CPU

CANNOT_ANSWER = "CANNOT_ANSWER"


class GemmaError(RuntimeError):
    """Base class. ``code`` is sent to the frontend as ``error.code``."""

    code = "generation_failed"


class GemmaUnavailableError(GemmaError):
    """Ollama is not reachable or the model is not pulled."""

    code = "model_unavailable"


class GemmaTimeoutError(GemmaError):
    code = "model_timeout"


class GemmaBadOutputError(GemmaError):
    """The model answered, but not with usable SQL."""

    code = "model_bad_output"


@dataclass(frozen=True)
class ModelStatus:
    name: str
    runtime: str
    available: bool
    detail: str | None = None


@dataclass(frozen=True)
class Generation:
    """Result of one generation. Exactly one of ``sql`` / ``refusal`` is set."""

    model: str
    duration_ms: float
    sql: str | None = None
    refusal: str | None = None


# --------------------------------------------------------------------------- #
# Prompt and output parsing (pure functions, unit-tested without a model)
# --------------------------------------------------------------------------- #


def format_schema(schema: Schema, schema_name: str | None = None) -> str:
    """Compact ``TABLE(col TYPE, ...)`` lines, truncated to MAX_SCHEMA_CHARS."""
    lines = []
    for table, columns in schema.items():
        cols = ", ".join(f"{c['name']} {c['type']}" for c in columns)
        qualified = f"{schema_name}.{table}" if schema_name else table
        lines.append(f"{qualified}({cols})")
    text = "\n".join(lines)
    if len(text) > MAX_SCHEMA_CHARS:
        text = text[:MAX_SCHEMA_CHARS].rsplit("\n", 1)[0] + "\n-- (schema truncated)"
    return text


def build_prompt(question: str, schema_text: str, dialect: str) -> tuple[str, str]:
    """Return ``(system, user)`` prompts."""
    system = (
        f"You translate questions into one {dialect} SQL query.\n"
        "Rules:\n"
        "- Output exactly one read-only SELECT (or WITH ... SELECT) statement.\n"
        "- Use only the tables and columns listed in the schema. Do not invent any.\n"
        "- Never write INSERT, UPDATE, DELETE, MERGE, CREATE, ALTER, DROP or any other change.\n"
        "- Give computed columns short aliases. Add ORDER BY when ranking.\n"
        f"- If the question cannot be answered from this schema, or asks to change data, "
        f"reply with exactly: {CANNOT_ANSWER}: <short reason>\n"
        "- Reply with only the SQL inside one ```sql code block. No explanation."
    )
    user = f"Schema:\n{schema_text}\n\nQuestion: {question}"
    return system, user


_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.I | re.S)
_SQL_START = re.compile(r"\b(SELECT|WITH)\b", re.I)


def parse_model_output(text: str) -> tuple[str | None, str | None]:
    """Return ``(sql, refusal)`` from raw model text.

    Raises GemmaBadOutputError when neither SQL nor a refusal can be found.
    The SQL is NOT trusted here; the caller must validate it.
    """
    stripped = (text or "").strip()
    if not stripped:
        raise GemmaBadOutputError("The model returned an empty response.")
    refusal = re.search(rf"{CANNOT_ANSWER}\s*:?\s*(.*)", stripped, re.I | re.S)
    if refusal and not _FENCE.search(stripped):
        reason = " ".join(refusal.group(1).split())[:300]
        return None, reason or "The question cannot be answered from this data."
    fenced = _FENCE.search(stripped)
    candidate = fenced.group(1) if fenced else stripped
    start = _SQL_START.search(candidate)
    if not start:
        raise GemmaBadOutputError("The model did not return a SQL query.")
    sql = candidate[start.start():].strip()
    # Drop a trailing semicolon; anything after it is left for the validator
    # to reject as a second statement.
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()
    return sql, None


# --------------------------------------------------------------------------- #
# Ollama client
# --------------------------------------------------------------------------- #


class OllamaGemma:
    runtime = "Ollama"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> OllamaGemma:
        env = os.environ if env is None else env
        try:
            timeout = float(env.get("DATAMIND_GEMMA_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))
        except ValueError:
            timeout = DEFAULT_TIMEOUT_SECONDS
        return cls(
            base_url=env.get("OLLAMA_BASE_URL", "").strip() or DEFAULT_BASE_URL,
            model=env.get("DATAMIND_GEMMA_MODEL", "").strip() or DEFAULT_MODEL,
            timeout=timeout,
        )

    # -- HTTP ---------------------------------------------------------------- #

    def _request(self, path: str, payload: dict[str, Any] | None, timeout: float) -> Any:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method="POST" if data else "GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                body = res.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200]
            if exc.code == 404:
                raise GemmaUnavailableError(
                    f"Model {self.model} is not available in Ollama. Run: ollama pull {self.model}"
                ) from None
            raise GemmaError(f"Ollama returned HTTP {exc.code}: {detail}") from None
        except (TimeoutError, socket.timeout):
            raise GemmaTimeoutError(
                f"Gemma did not respond within {int(timeout)} seconds."
            ) from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise GemmaTimeoutError(
                    f"Gemma did not respond within {int(timeout)} seconds."
                ) from None
            raise GemmaUnavailableError(
                f"Ollama is not reachable at {self.base_url}. Start Ollama and try again."
            ) from None
        try:
            return json.loads(body)
        except ValueError:
            raise GemmaBadOutputError("Ollama returned a response that is not JSON.") from None

    # -- public -------------------------------------------------------------- #

    def status(self) -> ModelStatus:
        """Cheap check: is Ollama up and is the model pulled? (No generation.)"""
        try:
            tags = self._request("/api/tags", None, STATUS_TIMEOUT_SECONDS)
        except GemmaError as exc:
            return ModelStatus(self.model, self.runtime, False, str(exc))
        names = {m.get("name") for m in tags.get("models", []) if isinstance(m, dict)}
        wanted = {self.model, f"{self.model}:latest"}
        if names & wanted:
            return ModelStatus(self.model, self.runtime, True)
        return ModelStatus(
            self.model, self.runtime, False,
            f"Model {self.model} is not pulled. Run: ollama pull {self.model}",
        )

    def generate(self, question: str, schema_text: str, dialect: str) -> Generation:
        system, user = build_prompt(question, schema_text, dialect)
        started = time.perf_counter()
        body = self._request(
            "/api/generate",
            {
                "model": self.model,
                "system": system,
                "prompt": user,
                "stream": False,
                "options": {"temperature": 0, "num_predict": 400},
            },
            self.timeout,
        )
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        if isinstance(body, dict) and body.get("error"):
            raise GemmaError(f"Ollama error: {str(body['error'])[:200]}")
        if not isinstance(body, dict) or not isinstance(body.get("response"), str):
            raise GemmaBadOutputError("Ollama response did not contain generated text.")
        sql, refusal = parse_model_output(body["response"])
        return Generation(model=self.model, duration_ms=duration_ms, sql=sql, refusal=refusal)
