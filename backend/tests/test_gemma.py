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
    assert format_schema(SCHEMA) == "SALES(CATEGORY (text), UNIT_PRICE (float))"
    assert "QUANTITY_NUMBER" not in format_schema({"SALES": [{"name": "QUANTITY", "type": "NUMBER", "nullable": True}]})
    assert format_schema(SCHEMA, "PUBLIC").startswith("PUBLIC.SALES(")


def test_join_hints_from_shared_key_columns():
    from app.gemma import join_hints

    schema = {
        "customers": [{"name": "customer_id", "type": "INTEGER", "nullable": False},
                      {"name": "city", "type": "VARCHAR", "nullable": False}],
        "orders": [{"name": "order_id", "type": "INTEGER", "nullable": False},
                   {"name": "customer_id", "type": "INTEGER", "nullable": False}],
        "order_items": [{"name": "order_id", "type": "INTEGER", "nullable": False},
                        {"name": "product_id", "type": "INTEGER", "nullable": False}],
        "products": [{"name": "product_id", "type": "INTEGER", "nullable": False}],
    }
    assert sorted(join_hints(schema)) == [
        "order_items.order_id = orders.order_id",
        "order_items.product_id = products.product_id",
        "orders.customer_id = customers.customer_id",
    ]
    text = format_schema(schema)
    assert text.splitlines()[-1].startswith("Join keys: ")
    assert join_hints(SCHEMA) == [] and "Join keys" not in format_schema(SCHEMA)


def test_join_hints_for_prefixed_key_columns_like_tpch():
    from app.gemma import join_hints

    def cols(*names):
        return [{"name": n, "type": "NUMBER", "nullable": False} for n in names]

    schema = {
        "CUSTOMER": cols("C_CUSTKEY", "C_NATIONKEY", "C_ACCTBAL"),
        "ORDERS": cols("O_ORDERKEY", "O_CUSTKEY", "O_TOTALPRICE"),
        "LINEITEM": cols("L_ORDERKEY", "L_PARTKEY", "L_SUPPKEY"),
        "PART": cols("P_PARTKEY"),
        "PARTSUPP": cols("PS_PARTKEY", "PS_SUPPKEY"),
        "SUPPLIER": cols("S_SUPPKEY", "S_NATIONKEY"),
        "NATION": cols("N_NATIONKEY", "N_REGIONKEY"),
        "REGION": cols("R_REGIONKEY"),
    }
    hints = set(join_hints(schema))
    assert {
        "ORDERS.O_CUSTKEY = CUSTOMER.C_CUSTKEY",
        "LINEITEM.L_ORDERKEY = ORDERS.O_ORDERKEY",
        "LINEITEM.L_PARTKEY = PART.P_PARTKEY",
        "PARTSUPP.PS_PARTKEY = PART.P_PARTKEY",
        "LINEITEM.L_SUPPKEY = SUPPLIER.S_SUPPKEY",
        "PARTSUPP.PS_SUPPKEY = SUPPLIER.S_SUPPKEY",
        "CUSTOMER.C_NATIONKEY = NATION.N_NATIONKEY",
        "SUPPLIER.S_NATIONKEY = NATION.N_NATIONKEY",
        "NATION.N_REGIONKEY = REGION.R_REGIONKEY",
    } == hints
    assert not any("ACCTBAL" in h or "TOTALPRICE" in h for h in hints)


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


# --- clarification and retry feedback ---------------------------------------- #

from app.gemma import Clarification, parse_clarification  # noqa: E402


def test_parse_clarification_with_options():
    c = parse_clarification(
        "CLARIFY: Do you mean revenue or units? || What is the total revenue per product? "
        "|| How many units were sold per product?"
    )
    assert c == Clarification(
        "Do you mean revenue or units?",
        ("What is the total revenue per product?", "How many units were sold per product?"),
    )


def test_parse_clarification_without_options_and_noise():
    assert parse_clarification("clarify: Which year?") == Clarification("Which year?", ())
    assert parse_clarification("SELECT 1") is None
    assert parse_clarification("```sql\nSELECT 1\n```\nCLARIFY: x") is None  # SQL wins
    assert parse_clarification("CLARIFY:   ") is None


def test_generate_returns_clarification(monkeypatch):
    fake_urlopen(monkeypatch, lambda url, body: {"response": "CLARIFY: Which metric? || Total revenue? || Units?"})
    g = OllamaGemma().generate("best product", "SALES(X TEXT)", "DuckDB")
    assert g.sql is None and g.refusal is None
    assert g.clarification.question == "Which metric?" and len(g.clarification.options) == 2


def test_prompt_has_clarify_rule_example_and_feedback():
    system, user = build_prompt("q", "S(X INT)", "DuckDB", feedback="Your previous SQL failed.\nError: bad")
    assert "CLARIFY:" in system
    # No worked example: gemma3:1b copied example patterns into real queries (measured).
    assert "Example" not in system and "TRIPS" not in system
    assert user.endswith("Your previous SQL failed.\nError: bad")
    assert "previous SQL" not in build_prompt("q", "S(X INT)", "DuckDB")[1]


def test_prompt_rules_target_measured_failures():
    system, _ = build_prompt("q", "TABLE S\n  - X (integer)", "Snowflake")
    for rule in ("never a sum of prices alone",          # S01/S02: SUM(unit_price) as revenue
                 "SUM of the quantity column",            # S04: COUNT(quantity) as units
                 "GROUP BY X (the entity named",          # S05: ranked category instead of product
                 "do not filter the total",               # S07: share computed inside a filter
                 "GROUP BY the period column",            # S09: one year only
                 "AVG of those totals",                   # R09: AVG(quantity) as order value
                 "Questions that need joins are answerable",  # T01/T03: joins refused
                 "exactly one of those spellings"):       # S08/S10: invented filter values
        assert rule in system, rule
    assert "Example" not in system  # still no worked example to copy


def test_generate_sets_context_window(monkeypatch):
    calls = fake_urlopen(monkeypatch, lambda url, body: {"response": "SELECT 1"})
    OllamaGemma().generate("q", "S(X INT)", "DuckDB")
    assert calls[0]["body"]["options"]["num_ctx"] == gemma.NUM_CTX == 8192


def test_generate_sends_feedback(monkeypatch):
    calls = fake_urlopen(monkeypatch, lambda url, body: {"response": "SELECT 1"})
    OllamaGemma().generate("q", "S(X INT)", "DuckDB", feedback="Error: invalid identifier 'PROFIT'")
    assert "invalid identifier 'PROFIT'" in calls[0]["body"]["prompt"]
