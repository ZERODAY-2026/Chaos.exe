"""Static safety checks for scripts/snowflake_setup.sql (it is never executed by tests)."""

import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "snowflake_setup.sql"


@pytest.fixture(scope="module")
def sql():
    return SCRIPT.read_text(encoding="utf-8")


def _active(sql_text):
    """Statements that would actually run (comment lines removed)."""
    return "\n".join(line for line in sql_text.splitlines() if not line.strip().startswith("--"))


def test_no_secrets_or_real_identifiers(sql):
    assert "BEGIN" not in sql or "BEGIN/END" in sql  # no PEM blocks
    assert not re.search(r"-----BEGIN [A-Z ]*KEY-----", sql)
    assert not re.search(r"MII[A-Za-z0-9+/]{40,}", sql)  # no pasted key material
    assert not re.search(r"\b[A-Z0-9]{7}-[A-Z0-9]{5,}\b", sql)  # no ORG-ACCOUNT identifiers
    assert "snowflakecomputing.com" not in sql
    assert "PASSWORD" not in _active(sql).upper()


def test_app_role_gets_only_usage_and_select(sql):
    grants = re.findall(r"GRANT\s+(.+?)\s+ON\s+.+?\s+TO\s+ROLE\s+DATAMIND_READONLY", _active(sql), re.I | re.S)
    assert grants and {g.strip().upper() for g in grants} <= {"USAGE", "SELECT"}
    assert "IMPORTED PRIVILEGES" not in _active(sql)  # optional grant stays commented out
    assert not re.search(r"GRANT\s+(ALL|OWNERSHIP|INSERT|UPDATE|DELETE)", _active(sql), re.I)


def test_idempotent_and_cost_controlled(sql):
    active = _active(sql)
    for obj in ("WAREHOUSE", "DATABASE", "SCHEMA", "TABLE", "ROLE", "USER"):
        assert re.search(rf"CREATE {obj} IF NOT EXISTS", active), obj
    assert "MERGE INTO DATAMIND.PUBLIC.SALES" in active and "WHEN NOT MATCHED THEN INSERT" in active
    assert "INSERT INTO" not in active  # only the guarded MERGE inserts rows
    assert "AUTO_SUSPEND = 60" in active and "WAREHOUSE_SIZE = 'XSMALL'" in active


def test_service_user_is_key_pair_only(sql):
    assert "TYPE = SERVICE" in _active(sql)
    assert "<PASTE_PUBLIC_KEY_BASE64_HERE>" in sql
    assert "ALTER USER" not in _active(sql)  # key registration is a manual, commented step


def test_sample_rows_match_the_local_dev_data(sql):
    from app.database import SAMPLE_SALES

    for order_id, product, category, qty, price, year in SAMPLE_SALES:
        assert re.search(
            rf"\({order_id},\s*'{product}',\s*'{category}',\s*{qty},\s*{price:.1f},\s*{year}\)", sql
        ), product
