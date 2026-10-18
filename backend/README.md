# DataMind backend: database layer

Owner: Member 1 (Database & Snowflake).

> **Snowflake is mandatory for PS1.** DuckDB is used only for free local
> development and must not replace Snowflake in the final submission.

## DuckDB (dev) vs Snowflake (real)

| | `DuckDBProvider` | `SnowflakeProvider` |
| --- | --- | --- |
| Purpose | Local development and unit tests | Final submission, real queries |
| Select with | `DATAMIND_PROVIDER=duckdb` (default) | `DATAMIND_PROVIDER=snowflake` |
| Needs account / network | No | Yes |
| Data | `data/datamind_dev.duckdb` (git-ignored) | Tables in your Snowflake database |
| Read-only enforced by | `read_only=True` connection | Dedicated read-only **role** |
| Identifier case | lower-case (`sales`) | upper-case (`SALES`) |

Both implement the same interface, so the agent/API layer should only call
`get_provider()` and the `DataProvider` methods.

## Layout

| File | Purpose |
| --- | --- |
| `app/database.py` | DuckDB dev database: `initialize_database()`, `get_schema()`, `get_category_revenue()` |
| `app/providers.py` | `DataProvider`, `validate_read_only_sql()`, `DuckDBProvider`, `SnowflakeSettings`, `SnowflakeProvider`, `get_provider()` |
| `scripts/generate_snowflake_keypair.py` | Creates a key pair outside the repo for key-pair auth |
| `tests/` | Unit tests (no credentials needed) + opt-in live Snowflake tests |
| `.env.example` | Template for `backend/.env` (git-ignored) |

## Setup (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pytest backend\tests -v
```

Unit tests use fakes for Snowflake: they need no credentials, network or
account, and the live tests are skipped by default.

## Provider interface

```python
class DataProvider(Protocol):
    name: str
    def get_schema(self) -> dict[str, list[dict[str, str]]]: ...
    def run_query(self, sql: str) -> dict[str, Any]:  # {"columns", "rows", "truncated"}
        ...
```

`run_query` validates SQL with `validate_read_only_sql()` (single
`SELECT`/`WITH` statement, no DDL/DML/`USE`/`SET`), returns at most `MAX_ROWS`
(1000) rows and sets `truncated` when more exist. Snowflake sessions also get
a 60 s statement timeout and `QUERY_TAG = 'datamind'`.

> **Security:** the validator is a convenience filter, **not** a security
> boundary. Keyword filtering can be bypassed. Real protection for Snowflake
> comes from connecting as a dedicated role that has only `USAGE` and
> `SELECT` grants. Never set `SNOWFLAKE_ROLE` to `ACCOUNTADMIN`, `SYSADMIN`
> or any role that can write.

## Snowflake setup

### 1. One-time objects (run in Snowsight as an admin, e.g. `ACCOUNTADMIN`)

```sql
-- Cost-controlled warehouse
CREATE WAREHOUSE IF NOT EXISTS DATAMIND_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE;

CREATE DATABASE IF NOT EXISTS DATAMIND;

-- Read-only role used by the app
CREATE ROLE IF NOT EXISTS DATAMIND_READONLY;
GRANT USAGE ON WAREHOUSE DATAMIND_WH TO ROLE DATAMIND_READONLY;
GRANT USAGE ON DATABASE DATAMIND TO ROLE DATAMIND_READONLY;
GRANT USAGE ON SCHEMA DATAMIND.PUBLIC TO ROLE DATAMIND_READONLY;
GRANT SELECT ON ALL TABLES IN SCHEMA DATAMIND.PUBLIC TO ROLE DATAMIND_READONLY;
GRANT SELECT ON FUTURE TABLES IN SCHEMA DATAMIND.PUBLIC TO ROLE DATAMIND_READONLY;

-- Service user for the app (key-pair auth)
CREATE USER IF NOT EXISTS DATAMIND_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = DATAMIND_READONLY
  DEFAULT_WAREHOUSE = DATAMIND_WH;
GRANT ROLE DATAMIND_READONLY TO USER DATAMIND_SVC;

-- Same sample data as the DuckDB dev database (load with an admin role)
CREATE TABLE IF NOT EXISTS DATAMIND.PUBLIC.SALES (
  ORDER_ID INTEGER PRIMARY KEY, PRODUCT VARCHAR NOT NULL, CATEGORY VARCHAR NOT NULL,
  QUANTITY INTEGER NOT NULL, UNIT_PRICE DOUBLE NOT NULL, YEAR INTEGER NOT NULL
);
INSERT INTO DATAMIND.PUBLIC.SALES
SELECT * FROM VALUES
  (1,'Laptop','Electronics',2,50000.0,2024), (2,'Smartphone','Electronics',3,20000.0,2025),
  (3,'Headphones','Electronics',4,1500.0,2025), (4,'Desk','Furniture',2,12000.0,2024),
  (5,'Chair','Furniture',4,2500.0,2025), (6,'Lamp','Furniture',2,1000.0,2024)
WHERE NOT EXISTS (SELECT 1 FROM DATAMIND.PUBLIC.SALES);
```

### 2. Authentication options

**Option A: key-pair (preferred).** Snowflake does not allow password login
for `TYPE = SERVICE` users, and human password users are subject to MFA,
which a backend cannot complete. Generate a key outside the repo:

```powershell
.\.venv\Scripts\python.exe backend\scripts\generate_snowflake_keypair.py
# add --passphrase to encrypt the key (you will be prompted)
```

The script writes the private key to `~\.snowflake\datamind_rsa_key.p8` and
prints an `ALTER USER DATAMIND_SVC SET RSA_PUBLIC_KEY = '...'` statement
containing only the public key. Run that in Snowsight, then set
`SNOWFLAKE_PRIVATE_KEY_PATH` (and `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` if used).

**Option B: password (fallback).** Set `SNOWFLAKE_PASSWORD`. This requires a
user type that still allows password login without interactive MFA. If
`SNOWFLAKE_PRIVATE_KEY_PATH` is set, it takes precedence.

### 3. Configure and run locally

```powershell
Copy-Item backend\.env.example backend\.env   # then edit backend\.env
```

The backend does not load `.env` automatically yet. To load it into the
current PowerShell session only (values are not printed):

```powershell
Get-Content backend\.env | Where-Object { $_ -match '^\s*[A-Za-z_][A-Za-z0-9_]*=' } | ForEach-Object { $k, $v = $_ -split '=', 2; [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), 'Process') }
```

Then verify real connectivity with the opt-in live tests:

```powershell
$env:DATAMIND_SNOWFLAKE_LIVE = '1'
.\.venv\Scripts\python.exe -m pytest backend\tests\test_snowflake_live.py -v
```

These check the session role and warehouse, the `SALES` schema, and the exact
category revenue. Only a passing live run shows that Snowflake integration works.

### Cost control

- Keep the warehouse `XSMALL` with `AUTO_SUSPEND = 60` and `AUTO_RESUME = TRUE`.
- Suspend it manually when you finish: `ALTER WAREHOUSE DATAMIND_WH SUSPEND;`
- Optionally add a resource monitor with a credit quota that suspends the warehouse.
