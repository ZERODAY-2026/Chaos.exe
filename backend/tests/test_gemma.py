"""Gemma client tests with mocked Ollama HTTP responses (no model, no network)."""

import io
import json
import socket
import urllib.error

import pytest

from app import gemma
from app.gemma import (
    CANNOT_ANSWER,
    GemmaBadOutputError,
    GemmaError,
    GemmaTimeoutError,
    GemmaUnavailableError,
    OllamaGemma,
    build_prompt,
    format_schema,
    parse_model_output,
)

SCHEMA = {
    "SALES": [
        {"name": "CATEGORY", "type": "TEXT", "nullable": True},
        {"name": "UNIT_PRICE", "type": "FLOAT", "nullable": True},
    ]
}


# --- prompt and schema ------------------------------------------------------ #


def test_format_schema():
    assert format_schema(SCHEMA) == "SALES(CATEGORY TEXT, UNIT_PRICE FLOAT)"
    assert format_schema(SCHEMA, "PUBLIC").startswith("PUBLIC.SALES(")


def test_format_schema_truncates_large_schemas():
    big = {f"T{i}": [{"name": f"C{j}", "type": "TEXT", "nullable": True} for j in range(20)] for i in range(100)}
    text = format_schema(big)
    assert len(text) <= gemma.MAX_SCHEMA_CHARS + 30
    assert text.endswith("-- (schema truncated)")


def test_prompt_contains_schema_rules_and_dialect():
    system, user = build_prompt("Top category?", "SALES(CATEGORY TEXT)", "Snowflake")
    assert "Snowflake" in system and "read-only SELECT" in system
    assert CANNOT_ANSWER in system
    assert "SALES(CATEGORY TEXT)" in user and "Top category?" in user


# --- output parsing ---------------------------------------------------------- #


@pytest.mark.parametrize(
    "text, sql",
    [
        ("```sql\nSELECT category FROM sales;\n```", "SELECT category FROM sales"),
        ("```\nSELECT 1\n```", "SELECT 1"),
        ("Here you go:\n```sql\nWITH t AS (SELECT 1 AS x) SELECT x FROM t\n```\nHope it helps",
         "WITH t AS (SELECT 1 AS x) SELECT x FROM t"),
        ("SELECT category FROM sales", "SELECT category FROM sales"),
        ("Sure! SELECT category FROM sales", "SELECT category FROM sales"),
    ],
)
def test_parse_extracts_sql(text, sql):
    assert parse_model_output(text) == (sql, None)


def test_parse_keeps_second_statement_for_validator_to_reject():
    sql, _ = parse_model_output("```sql\nSELECT 1; DROP TABLE sales;\n```")
    assert "DROP TABLE" in sql  # not silently trimmed: the validator must refuse it


def test_parse_refusal():
    assert parse_model_output("CANNOT_ANSWER: no customer table") == (None, "no customer table")
    assert parse_model_output("cannot_answer") == (None, "The question cannot be answered from this data.")


@pytest.mark.parametrize("text", ["", "   ", "I don't know.", "```sql\n\n```"])
def test_parse_rejects_non_sql(text):
    with pytest.raises(GemmaBadOutputError):
        parse_model_output(text)


# --- Ollama HTTP client (urlopen mocked) ------------------------------------- #


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(monkeypatch, handler):
    calls = []

    def urlopen(req, timeout):
        body = json.loads(req.data) if req.data else None
        calls.append({"url": req.full_url, "method": req.get_method(), "body": body, "timeout": timeout})
        result = handler(req.full_url, body)
        if isinstance(result, BaseException):
            raise result
        return FakeResponse(json.dumps(result).encode() if not isinstance(result, bytes) else result)

    monkeypatch.setattr(gemma.urllib.request, "urlopen", urlopen)
    return calls


def test_from_env_defaults_and_overrides():
    default = OllamaGemma.from_env({})
    assert (default.base_url, default.model, default.timeout) == ("http://127.0.0.1:11434", "gemma3:1b", 120.0)
    custom = OllamaGemma.from_env(
        {"OLLAMA_BASE_URL": "http://host:1/", "DATAMIND_GEMMA_MODEL": "gemma3:4b", "DATAMIND_GEMMA_TIMEOUT": "9"}
    )
    assert (custom.base_url, custom.model, custom.timeout) == ("http://host:1", "gemma3:4b", 9.0)
    assert OllamaGemma.from_env({"DATAMIND_GEMMA_TIMEOUT": "abc"}).timeout == 120.0


def test_generate_sends_prompt_and_parses(monkeypatch):
    calls = fake_urlopen(monkeypatch, lambda url, body: {"response": "```sql\nSELECT category FROM sales\n```"})
    result = OllamaGemma().generate("Which categories?", "SALES(CATEGORY TEXT)", "Snowflake")
    assert result.sql == "SELECT category FROM sales" and result.refusal is None
    assert result.model == "gemma3:1b" and result.duration_ms >= 0
    [call] = calls
    assert call["url"].endswith("/api/generate") and call["method"] == "POST"
    assert call["body"]["model"] == "gemma3:1b" and call["body"]["stream"] is False
    assert call["body"]["options"]["temperature"] == 0
    assert "Which categories?" in call["body"]["prompt"]
    assert call["timeout"] == 120.0


def test_generate_refusal(monkeypatch):
    fake_urlopen(monkeypatch, lambda url, body: {"response": "CANNOT_ANSWER: asks to delete data"})
    result = OllamaGemma().generate("delete everything", "SALES(X TEXT)", "DuckDB")
    assert result.sql is None and result.refusal == "asks to delete data"


def test_ollama_not_running(monkeypatch):
    fake_urlopen(monkeypatch, lambda url, body: urllib.error.URLError(ConnectionRefusedError(10061, "refused")))
    with pytest.raises(GemmaUnavailableError, match="not reachable"):
        OllamaGemma().generate("q", "s", "DuckDB")


def test_model_not_pulled(monkeypatch):
    err = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b'{"error":"model not found"}'))
    fake_urlopen(monkeypatch, lambda url, body: err)
    with pytest.raises(GemmaUnavailableError, match="ollama pull gemma3:1b"):
        OllamaGemma().generate("q", "s", "DuckDB")


def test_ollama_server_error(monkeypatch):
    err = urllib.error.HTTPError("u", 500, "err", {}, io.BytesIO(b"out of memory"))
    fake_urlopen(monkeypatch, lambda url, body: err)
    with pytest.raises(GemmaError, match="HTTP 500") as info:
        OllamaGemma().generate("q", "s", "DuckDB")
    assert info.value.code == "generation_failed"


@pytest.mark.parametrize("exc", [socket.timeout("timed out"), TimeoutError(), urllib.error.URLError(socket.timeout())])
def test_timeout(monkeypatch, exc):
    fake_urlopen(monkeypatch, lambda url, body: exc)
    with pytest.raises(GemmaTimeoutError) as info:
        OllamaGemma(timeout=5).generate("q", "s", "DuckDB")
    assert info.value.code == "model_timeout" and "5 seconds" in str(info.value)


@pytest.mark.parametrize(
    "payload, error",
    [
        (b"not json", GemmaBadOutputError),
        ({"done": True}, GemmaBadOutputError),
        ({"error": "model runner crashed"}, GemmaError),
        ({"response": "I am not sure."}, GemmaBadOutputError),
    ],
)
def test_bad_ollama_payloads(monkeypatch, payload, error):
    fake_urlopen(monkeypatch, lambda url, body: payload)
    with pytest.raises(error):
        OllamaGemma().generate("q", "s", "DuckDB")


def test_status_available(monkeypatch):
    calls = fake_urlopen(monkeypatch, lambda url, body: {"models": [{"name": "gemma3:1b"}, {"name": "llama3:8b"}]})
    status = OllamaGemma().status()
    assert status.available is True and status.name == "gemma3:1b" and status.runtime == "Ollama"
    assert calls[0]["url"].endswith("/api/tags") and calls[0]["method"] == "GET"
    assert calls[0]["timeout"] == gemma.STATUS_TIMEOUT_SECONDS


def test_status_model_missing(monkeypatch):
    fake_urlopen(monkeypatch, lambda url, body: {"models": [{"name": "llama3:8b"}]})
    status = OllamaGemma().status()
    assert status.available is False and "ollama pull gemma3:1b" in status.detail


def test_status_ollama_down(monkeypatch):
    fake_urlopen(monkeypatch, lambda url, body: urllib.error.URLError(ConnectionRefusedError()))
    status = OllamaGemma().status()
    assert status.available is False and "not reachable" in status.detail
