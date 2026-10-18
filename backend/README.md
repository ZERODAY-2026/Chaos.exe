# DataMind backend

FastAPI service that turns questions into validated, read-only SQL and runs it
on Snowflake (submission target) or DuckDB (local development, evaluation and
demos). Start with the [root README](../README.md) for setup and running;
this page is the backend reference.

> **Snowflake is mandatory for PS1.** DuckDB is a local stand-in for
> development, tests and the isolated demo; it never replaces Snowflake.

## Modules

| File | Purpose |
| --- | --- |
| `app/api.py` | Endpoints, request validation, CORS, query pipeline and bounded retry |
| `app/gemma.py` | Ollama/Gemma client: prompt, `format_schema()` + `join_hints()`, output parsing, `status()` |
| `app/guardrails.py` | `screen_question()`, `classify_db_error()`, `sanitize_error()`, `feedback_for_model()` |
| `app/providers.py` | `DataProvider`, `validate_read_only_sql()`, `DuckDBProvider(db_path=None)`, `SnowflakeProvider`, `SnowflakeSettings` |
| `app/sql_explain.py` | `explain_sql()` / `summarize()`: tables, filters and calculations parsed from executed SQL (SQLGlot) |
| `app/results.py` | `MAX_ROWS` (1000), `format_result()`, `to_json_value()`, `build_schema()` |
| `app/database.py` | DuckDB dev database (`data/datamind_dev.duckdb`, git-ignored) and the 6 synthetic `SALES` rows |
| `eval/` | Evaluation fixtures, cases, comparison, runner and data-change demo ([eval/README.md](eval/README.md)) |
| `scripts/generate_snowflake_keypair.py` | Key pair generation; refuses to write inside the repo |
| `tests/` | Unit tests (no credentials) and opt-in live Snowflake tests |

## Query pipeline (`POST /api/query`)

1. **Direct SQL** (input starts with `SELECT`/`WITH`): validate, then execute. No model.
2. **Natural language:**
   1. `screen_question()` refuses data-modification, safety-bypass and forecast requests **before** the model is called.
   2. The provider schema is discovered (cached 5 min) and formatted with join-key hints.
   3. Gemma returns SQL, `CLARIFY: …` (→ `clarification_needed`) or `CANNOT_ANSWER: …` (→ `refused`).
   4. `validate_read_only_sql()` runs on the generated SQL. Unsafe SQL is refused and never retried.
   5. The provider executes it (read-only connection / role, ≤ 1,000 rows).
   6. On a *fixable* error (`unknown_object`, `sql_syntax`, or malformed SQL) Gemma gets its own SQL plus
      the sanitized error (no hostnames, request or query ids) and tries again. That attempt is validated again.
      The limit is `DATAMIND_GEMMA_MAX_ATTEMPTS` (default 2, hard maximum 3). Permission errors, timeouts
      and unknown errors are **never** retried.
3. **Response:** `answer` built from the rows, `explanation` from `explain_sql()` on the SQL that actually ran,
   `execution.provider_query_id` (Snowflake), warnings (including any failed attempt that was not used).

## Provider interface

```python
class DataProvider(Protocol):
    name: str
    def get_schema(self) -> Schema: ...        # {table: [{"name", "type", "nullable"}]}
    def run_query(self, sql: str) -> QueryResult: ...  # {"columns", "rows", "truncated", "provider_query_id"?}
    def location(self) -> dict[str, str]: ...  # {"database", "schema", "warehouse"?} (non-secret)
```

Both providers share `run_query()`: validation first, then a read-only cursor,
`MAX_ROWS` + 1 fetched to detect truncation, values converted to JSON. Snowflake
sessions also set `STATEMENT_TIMEOUT_IN_SECONDS = 60`, `MULTI_STATEMENT_COUNT = 1`
and `QUERY_TAG = 'datamind'`.

> **Security:** the validator is a guardrail, not the security boundary. The
> boundary is the database permission: read-only DuckDB connections (external
> file/URL access disabled and locked) and a Snowflake role with only `USAGE`
> and `SELECT`. Never configure `ACCOUNTADMIN`, `SYSADMIN` or any write-capable role.

## Configuration (`backend/.env`, git-ignored)

Copy `backend/.env.example`. The backend reads **process environment variables**;
`.env` is not loaded automatically, so load it with the PowerShell line in the root README.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATAMIND_PROVIDER` | `duckdb` | Default provider: `duckdb` or `snowflake` |
| `DATAMIND_DUCKDB_PATH` | `data/datamind_dev.duckdb` | Local DuckDB file |
| `DATAMIND_ALLOW_DIRECT_SQL` | `true` | Allow typed `SELECT`/`WITH` input |
| `DATAMIND_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed frontend origins |
| `SNOWFLAKE_ACCOUNT` | – | `ORGNAME-ACCOUNTNAME` |
| `SNOWFLAKE_USER` / `SNOWFLAKE_ROLE` / `SNOWFLAKE_WAREHOUSE` | – | `DATAMIND_SVC` / `DATAMIND_READONLY` / `DATAMIND_WH` |
| `SNOWFLAKE_DATABASE` / `SNOWFLAKE_SCHEMA` | – | `DATAMIND` / `PUBLIC` (or another dataset, e.g. `SNOWFLAKE_SAMPLE_DATA` / `TPCH_SF1`) |
| `SNOWFLAKE_PRIVATE_KEY_PATH` | – | Key-pair auth (preferred); file outside the repo |
| `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | – | Only if the key is encrypted |
| `SNOWFLAKE_PASSWORD` | – | Fallback only; ignored when a key path is set |
| `DATAMIND_SNOWFLAKE_LIVE` | – | `1` enables `tests/test_snowflake_live.py` |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama server |
| `DATAMIND_GEMMA_MODEL` | `gemma3:1b` | Any pulled Gemma tag |
| `DATAMIND_GEMMA_TIMEOUT` | `120` | Seconds per generation |
| `DATAMIND_GEMMA_MAX_ATTEMPTS` | `2` | 1–3 attempts per question |

## Snowflake setup

Run [`scripts/snowflake_setup.sql`](../scripts/snowflake_setup.sql) in Snowsight.
It creates the X-Small auto-suspending warehouse, `DATAMIND.PUBLIC.SALES` (guarded
`MERGE`, no duplicates), the read-only role, and the `TYPE = SERVICE` user, and
ends with read-only verification queries. Administrator-only sections are marked.

**Key-pair authentication** (preferred: service users cannot use passwords, and
password users face MFA a backend cannot complete):

```powershell
.\.venv\Scripts\python.exe backend\scripts\generate_snowflake_keypair.py      # add --passphrase to encrypt
```

The private key goes to `~\.snowflake\datamind_rsa_key.p8`. The script prints an
`ALTER USER DATAMIND_SVC SET RSA_PUBLIC_KEY = '…'` line containing only the
public key; run it in Snowsight and set `SNOWFLAKE_PRIVATE_KEY_PATH`.

**Verify** (after loading `backend\.env`):

```powershell
$env:DATAMIND_SNOWFLAKE_LIVE = '1'
.\.venv\Scripts\python.exe -m pytest backend\tests\test_snowflake_live.py -v
```

These check the session role and warehouse, the `SALES` schema and the exact
category revenue. Only a passing live run proves the Snowflake integration.

**Second dataset (optional):** in the team account the read-only role could
already read `SNOWFLAKE_SAMPLE_DATA.TPCH_SF1` (checked 18 Oct 2026, no grant
change made). If yours cannot, the narrowest change, which needs the account owner's
approval, is `GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE_SAMPLE_DATA TO ROLE DATAMIND_READONLY;`.

**Cost control:** X-Small, `AUTO_SUSPEND = 60`, `AUTO_RESUME = TRUE`; run
`ALTER WAREHOUSE DATAMIND_WH SUSPEND;` when finished; optional resource monitor in the setup script.
