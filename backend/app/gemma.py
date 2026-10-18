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
NUM_CTX = 8192

CANNOT_ANSWER = "CANNOT_ANSWER"
CLARIFY = "CLARIFY"


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
class Clarification:
    question: str
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Generation:
    """Result of one generation. Exactly one of ``sql`` / ``refusal`` /
    ``clarification`` is set."""

    model: str
    duration_ms: float
    sql: str | None = None
    refusal: str | None = None
    clarification: Clarification | None = None


# --------------------------------------------------------------------------- #
# Prompt and output parsing (pure functions, unit-tested without a model)
# --------------------------------------------------------------------------- #


_TABLE_PREFIX = re.compile(r"^[a-z]{1,3}_(.+)$")  # TPC-H style: C_CUSTKEY, PS_PARTKEY
_KEY_SUFFIX = re.compile(r"(_id|_key|key)$")


def _key_base(column: str) -> str | None:
    """``customer_id`` -> ``customer_id``; ``C_CUSTKEY`` -> ``custkey``; others -> None."""
    name = column.lower()
    if not _KEY_SUFFIX.search(name):
        return None
    prefixed = _TABLE_PREFIX.match(name)
    return prefixed.group(1) if prefixed and _KEY_SUFFIX.search(prefixed.group(1)) else name


def join_hints(schema: Schema) -> list[str]:
    """Likely join keys: key-like columns (``*_id``, ``*_key``, ``*key``) that appear
    in more than one table, ignoring short table prefixes (``O_CUSTKEY`` matches
    ``C_CUSTKEY``). Derived only from the discovered schema, so it works for any
    dataset without configuration. These are hints for the model, not constraints."""
    owners: dict[str, list[tuple[str, str]]] = {}
    for table, columns in schema.items():
        for c in columns:
            base = _key_base(c["name"])
            if base:
                owners.setdefault(base, []).append((table, c["name"]))
    hints = []
    for key, places in owners.items():
        if len(places) < 2:
            continue
        # Prefer the table the key "belongs to" (customer_id -> customers, custkey -> CUSTOMER).
        stem = _KEY_SUFFIX.sub("", key)
        places.sort(key=lambda p: (
            p[0].lower() not in (stem, f"{stem}s", f"{stem}es"),  # exact owner first (orders for order_id)
            not p[0].lower().startswith(stem),
            p[0].lower(),
        ))
        target_table, target_col = places[0]
        for table, col in places[1:]:
            hints.append(f"{table}.{col} = {target_table}.{target_col}")
    return hints


def format_schema(schema: Schema, schema_name: str | None = None) -> str:
    """Compact ``TABLE(col (type), ...)`` lines plus join-key hints, truncated to MAX_SCHEMA_CHARS.

    Types are lower-cased in parentheses so an upper-case name and type (Snowflake's
    ``QUANTITY NUMBER``) cannot be misread as one identifier (``QUANTITY_NUMBER``).
    """
    lines = []
    for table, columns in schema.items():
        cols = ", ".join(f"{c['name']} ({c['type'].lower()})" for c in columns)
        qualified = f"{schema_name}.{table}" if schema_name else table
        lines.append(f"{qualified}({cols})")
    hints = join_hints(schema)
    if hints:
        lines.append("Join keys: " + "; ".join(hints))
    text = "\n".join(lines)
    if len(text) > MAX_SCHEMA_CHARS:
        text = text[:MAX_SCHEMA_CHARS].rsplit("\n", 1)[0] + "\n-- (schema truncated)"
    return text


def build_prompt(
    question: str, schema_text: str, dialect: str, feedback: str | None = None
) -> tuple[str, str]:
    """Return ``(system, user)`` prompts. ``feedback`` describes a failed attempt."""
    system = (
        f"You translate questions into one {dialect} SQL query.\n"
        "Schema rules:\n"
        "- Use only the tables and columns listed, spelled exactly. A column belongs to the table it is "
        "listed under; to use a column from another table, JOIN that table.\n"
        "- Join on the declared foreign keys or the listed possible join keys only.\n"
        "- When a column lists values, filter with exactly one of those spellings. If the question names a "
        "value that is not listed, still filter on it in the column it belongs to (the answer may be empty).\n"
        "Measure rules:\n"
        "- Use the measure hints. Revenue, sales amount or money is quantity times unit price (or a stored "
        "amount column), never a sum of prices alone.\n"
        "- 'How many units/items sold' is SUM of the quantity column. 'How many <things>' is "
        "COUNT(DISTINCT <key>) of the things.\n"
        "- 'Which X has the most/highest Y': GROUP BY X (the entity named in the question), ORDER BY Y "
        "DESC, LIMIT 1.\n"
        "- Share or percentage of a total: the part divided by the overall total, e.g. "
        "SUM(CASE WHEN <condition> THEN <measure> ELSE 0 END) / SUM(<measure>); do not filter the total.\n"
        "- Change between periods: return the measure for each period (GROUP BY the period column).\n"
        "- Average per order or per customer: total per order/customer in a subquery, then AVG of those totals.\n"
        "Output rules:\n"
        "- Exactly one read-only SELECT (or WITH ... SELECT) statement. Never INSERT, UPDATE, DELETE, "
        "MERGE, CREATE, ALTER, DROP or any other change.\n"
        "- Give computed columns short aliases.\n"
        f"- Only if no listed column relates to the question, reply exactly: {CANNOT_ANSWER}: <short reason>. "
        "Questions that need joins are answerable.\n"
        "- If the question is ambiguous in a way that changes the answer (for example which "
        f"metric or which period), reply exactly: {CLARIFY}: <short question> || "
        "<full question option 1> || <full question option 2>\n"
        "- Otherwise reply with only the SQL inside one ```sql code block. No explanation."
        # No worked example: with gemma3:1b, examples were copied (column names, single-column
        # SUMs) into real queries and lowered measured accuracy (see backend/eval/README.md).
    )
    user = f"Schema:\n{schema_text}\n\nQuestion: {question}"
    if feedback:
        user += f"\n\n{feedback}"
    return system, user


_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.I | re.S)
_SQL_START = re.compile(r"\b(SELECT|WITH)\b", re.I)


def parse_clarification(text: str) -> Clarification | None:
    """Parse ``CLARIFY: question || option || option`` (only when no SQL block is present)."""
    match = re.search(rf"{CLARIFY}\s*:?\s*(.*)", text or "", re.I | re.S)
    if not match or _FENCE.search(text):
        return None
    parts = [" ".join(p.split()).strip(" -*") for p in match.group(1).split("||")]
    parts = [p for p in parts if p]
    if not parts:
        return None
    return Clarification(question=parts[0][:300], options=tuple(o[:300] for o in parts[1:4]))


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

    def generate(
        self, question: str, schema_text: str, dialect: str, feedback: str | None = None
    ) -> Generation:
        """One generation. ``feedback`` (already sanitized) describes the previous failed attempt."""
        system, user = build_prompt(question, schema_text, dialect, feedback)
        started = time.perf_counter()
        body = self._request(
            "/api/generate",
            {
                "model": self.model,
                "system": system,
                "prompt": user,
                "stream": False,
                # num_ctx is set explicitly so a larger schema context is never truncated
                # by a smaller runtime default (gemma3 supports up to 32k tokens).
                "options": {"temperature": 0, "num_predict": 400, "num_ctx": NUM_CTX},
            },
            self.timeout,
        )
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        if isinstance(body, dict) and body.get("error"):
            raise GemmaError(f"Ollama error: {str(body['error'])[:200]}")
        if not isinstance(body, dict) or not isinstance(body.get("response"), str):
            raise GemmaBadOutputError("Ollama response did not contain generated text.")
        clarification = parse_clarification(body["response"])
        if clarification is not None:
            return Generation(model=self.model, duration_ms=duration_ms, clarification=clarification)
        sql, refusal = parse_model_output(body["response"])
        return Generation(model=self.model, duration_ms=duration_ms, sql=sql, refusal=refusal)
