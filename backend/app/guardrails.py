"""Deterministic guardrails around the language model (PS1 M6).

1. ``screen_question`` runs BEFORE Gemma: requests to change data, attempts to
   bypass the safeguards, and requests DataMind cannot answer from stored data
   (forecasts) are refused in plain language without calling the model.
2. ``classify_db_error`` decides whether a database error is worth one bounded
   retry (wrong table/column name, syntax) or must be reported as-is
   (permissions, timeouts, anything unknown).
3. ``feedback_for_model`` turns an error into short, sanitized text for Gemma:
   no hostnames, request ids or query ids.

These are convenience filters. The real safety boundaries are unchanged:
``validate_read_only_sql`` before every execution, read-only DuckDB connections
and the read-only Snowflake role.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# --------------------------------------------------------------------------- #
# Question screening
# --------------------------------------------------------------------------- #

_MODIFY = re.compile(
    r"\b(delete|drop|truncate|wipe|erase|purge|destroy|insert|upsert|merge\s+into|grant|revoke)\b"
    r"|\balter\s+(the\s+)?(table|column|schema|database|role|user)\b"
    r"|\bupdate\s+(the\s+)?\w+(\s+\w+)?\s+(set|to)\b"
    r"|\b(remove|add|create|change|modify|rename|overwrite|reset|edit|replace)\b"
    r"(\s+\w+){0,4}\s+(rows?|records?|entries|entry|data|tables?|columns?|values?|prices?|orders?|sales)\b",
    re.I,
)
_INJECTION = re.compile(
    r"\b(ignore|disregard|forget)\b(\s+\w+){0,3}\s+(instructions?|rules?|prompts?|guidelines?)\b"
    r"|\b(bypass|disable|skip|turn\s+off|override|circumvent|get\s+around)\b(\s+\w+){0,3}\s+"
    r"(safety|safeguards?|validation|validator|checks?|read[-\s]?only|guard\w*|restrictions?|filters?)\b"
    r"|\bsystem\s+prompt\b|\bjailbreak\b|\bdeveloper\s+mode\b",
    re.I,
)
_FORECAST = re.compile(
    r"\b(forecast\w*|predict\w*|projection|extrapolat\w*)\b"
    r"|\bwill\b(\s+\w+){0,4}\s+(be|sell|earn|make|grow)\b(\s+\w+){0,4}\s+\b(next|in\s+20\d\d|future)\b"
    r"|\bnext\s+(year|month|quarter|week)'?s?\b",
    re.I,
)


@dataclass(frozen=True)
class Screening:
    kind: str  # "ok" | "modify" | "injection" | "unsupported"
    message: str | None = None

    @property
    def allowed(self) -> bool:
        return self.kind == "ok"


MODIFY_MESSAGE = (
    "DataMind is read-only: it can look up and summarise data, but it never deletes, "
    "inserts, updates or alters anything. Ask a question about the existing data instead."
)
INJECTION_MESSAGE = (
    "This request asks DataMind to ignore or bypass its safety rules, so it was not run. "
    "Every query is checked as read-only before it reaches the database."
)
FORECAST_MESSAGE = (
    "DataMind only reports what is in the stored data; it does not forecast or predict "
    "future values. You can ask about past results, e.g. totals by year."
)


def screen_question(question: str) -> Screening:
    if _INJECTION.search(question):
        return Screening("injection", INJECTION_MESSAGE)
    if _MODIFY.search(question):
        return Screening("modify", MODIFY_MESSAGE)
    if _FORECAST.search(question):
        return Screening("unsupported", FORECAST_MESSAGE)
    return Screening("ok")


# --------------------------------------------------------------------------- #
# Schema-aware checks (need the discovered schema; still run before the model)
# --------------------------------------------------------------------------- #

_VAGUE = re.compile(
    r"\b(best|top|worst|leading|biggest|strongest|weakest|favou?rite|most\s+popular|most\s+important)"
    r"\s+(?:\d+\s+)?([a-z]+)",
    re.I,
)
_MEASURE_WORDS = re.compile(
    r"\b(revenue|sales|sold|sell\w*|units?|quantit\w*|orders?|ordered|count|number|price\w*|amount|"
    r"spend\w*|spent|money|income|value|balance|profit|cost\w*|margin|earn\w*|bought|buy\w*|purchas\w*|by)\b",
    re.I,
)
_NOT_ENTITIES = {"of", "the", "a", "an", "in", "for", "our", "my", "and", "is", "are"}

# Business concepts that need a dedicated column. If no column/table name contains
# any of the keywords, the question cannot be answered from this data.
_CONCEPTS = {
    "profit": ("profit", "margin", "cost"),
    "margin": ("margin", "profit", "cost"),
    "discount": ("discount",),
    "tax": ("tax",),
    "rating": ("rating", "score", "stars", "review"),
    "salary": ("salary", "wage", "pay"),
    "inventory": ("inventory", "stock"),
    "weight": ("weight",),
}


def detect_ambiguity(question: str, measure_options: dict[str, bool]) -> tuple[str, list[str]] | None:
    """A vague superlative ("best product", "top customer") with no measure named,
    when the schema supports more than one measure. Returns (question, options)."""
    match = _VAGUE.search(question)
    if not match or _MEASURE_WORDS.search(question):
        return None
    entity = match.group(2).lower()
    if entity in _NOT_ENTITIES:
        entity = "item"
    if entity.endswith("s") and len(entity) > 3 and not entity.endswith("ss"):
        entity = entity[:-1]
    options = []
    if measure_options.get("revenue"):
        options.append(f"Which {entity} has the highest revenue?")
    if measure_options.get("units"):
        options.append(f"Which {entity} has the most units sold?")
    if measure_options.get("orders"):
        options.append(f"Which {entity} has the most orders?")
    if len(options) < 2:  # only one sensible measure: not materially ambiguous
        return None
    word = " ".join(match.group(1).split()).lower()
    return f'"{word.capitalize()}" can be measured in different ways here. Which one do you mean?', options


def missing_concept(question: str, schema: dict[str, list[dict[str, Any]]]) -> str | None:
    """Plain-language reason if the question needs a concept no column provides."""
    names = [t.lower() for t in schema] + [c["name"].lower() for cols in schema.values() for c in cols]
    for concept, needs in _CONCEPTS.items():
        if re.search(rf"\b{concept}\w*\b", question, re.I) and not any(n in name for name in names for n in needs):
            return (
                f"This data has no column for {concept} (no {', '.join(needs)} column), so it cannot be "
                "calculated without guessing. Ask about the columns shown in the schema explorer instead."
            )
    return None


# --------------------------------------------------------------------------- #
# Database errors
# --------------------------------------------------------------------------- #

_UNKNOWN_OBJECT = re.compile(
    r"does not exist|not found|invalid identifier|unknown (column|table|identifier)"
    r"|referenced column .* not found|catalog error|binder error|no such (table|column)",
    re.I,
)
_SYNTAX = re.compile(r"syntax error|parser error|parse error|unexpected '|compilation error", re.I)
_PERMISSION = re.compile(r"insufficient privileges|permission denied|access denied|not authorized to", re.I)
_TIMEOUT = re.compile(r"timeout|timed out|statement reached its statement", re.I)
_NOISE = re.compile(
    r"\(?\s*(request_id|sfqid|query id)\s*[=:]\s*[\w-]+\s*,?\s*\)?"
    r"|[\w.-]+\.snowflakecomputing\.com(:\d+)?"
    r"|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.I,
)


@dataclass(frozen=True)
class DbErrorInfo:
    code: str  # "unknown_object" | "sql_syntax" | "permission_denied" | "query_timeout" | "execution_failed"
    retryable: bool


def classify_db_error(message: str) -> DbErrorInfo:
    """Permission and timeout checks come first: they are never retried."""
    if _PERMISSION.search(message):
        return DbErrorInfo("permission_denied", False)
    if _TIMEOUT.search(message):
        return DbErrorInfo("query_timeout", False)
    if _UNKNOWN_OBJECT.search(message):
        return DbErrorInfo("unknown_object", True)
    if _SYNTAX.search(message):
        return DbErrorInfo("sql_syntax", True)
    return DbErrorInfo("execution_failed", False)


def sanitize_error(message: str, limit: int = 300) -> str:
    text = _NOISE.sub("", " ".join(message.split()))
    text = re.sub(r"\s{2,}", " ", text).strip(" ,;")
    return text[:limit]


def feedback_for_model(sql: str, error: str) -> str:
    """What Gemma sees after a failed attempt: its own SQL and the cleaned error."""
    return (
        "Your previous SQL failed.\n"
        f"Previous SQL: {sql}\n"
        f"Error: {sanitize_error(error)}\n"
        "Write a corrected query that uses only the tables and columns in the schema."
    )
