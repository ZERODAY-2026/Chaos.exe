# Chaos.exe: DataMind — Talk to Your Data

Team Chaos.exe's project for ZeroDay OSS Hacktoberfest 2026, problem statement PS1.

DataMind lets a user ask questions about their data in plain language. A
Google Gemma model is meant to turn the question into read-only SQL, which
runs on **Snowflake**, and show the answer.

> **Project status: work in progress, not yet checkpoint-complete.**
> Only the database layer exists in this repository so far. The Gemma agent,
> API and frontend are not here yet, and Snowflake has not yet been tested
> against a real account.

## Status

| Component | Owner | Status |
| --- | --- | --- |
| DuckDB dev database (`backend/app/database.py`) | Member 1 | Implemented, locally tested |
| Provider interface + read-only SQL validator (`backend/app/providers.py`) | Member 1 | Implemented, locally tested |
| `SnowflakeProvider` (Snowflake is **mandatory** for PS1) | Member 1 | Implemented, **mock-tested only**; live tests written but not yet run |
| Gemma agent (natural language to SQL; **mandatory** for PS1) | Teammate | Not yet implemented in this repo |
| Backend API | Teammate | Not yet implemented |
| Frontend | Teammate | Not yet implemented in this repo |

"Locally tested" means unit tests pass on a developer machine. "Mock-tested"
means Snowflake was replaced by test fakes. Only the opt-in live tests in
`backend/tests/test_snowflake_live.py` can verify a real Snowflake connection.

## Architecture (planned)

```
User ──▶ Frontend ──▶ Backend API ──▶ Gemma agent (question → SQL)
                           │
                           ▼
                validate_read_only_sql()
                           │
                           ▼
            DataProvider (get_schema, run_query)
             ├── SnowflakeProvider  ← final submission
             └── DuckDBProvider     ← local development only
```

DuckDB is a free local stand-in for development and tests. It does **not**
replace Snowflake in the final project. The active provider is chosen with
`DATAMIND_PROVIDER` (`duckdb` or `snowflake`).

## Setup (Windows PowerShell)

Requires Python 3.12.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pytest backend\tests -v
```

The live Snowflake tests are skipped unless `DATAMIND_SNOWFLAKE_LIVE=1` and
Snowflake credentials are configured.

## Snowflake

See [backend/README.md](backend/README.md) for the full setup:
- setup SQL for the warehouse, read-only role, service user and sample table
- key-pair (preferred) or password authentication
- loading `backend/.env`
- running the live tests
- cost control: an XSMALL warehouse with `AUTO_SUSPEND = 60`, and `ALTER WAREHOUSE ... SUSPEND`

Credentials go only in `backend/.env`, which Git ignores. Never commit
`.env` files or private keys.

## Data

The sample `sales` table has 6 synthetic rows written by the team for
development and testing (see `SAMPLE_SALES` in `backend/app/database.py`).
It contains no real or third-party data. Any external dataset added later
must be listed here with its source and licence.

## Known limitations

- Snowflake integration has not been verified against a real account.
- No Gemma, API or frontend code exists in this repository yet.
- The SQL validator is a keyword filter, not a security boundary. A
  dedicated read-only Snowflake role is required. The filter may also reject
  some valid queries (for example, a column named `set`).
- Snowflake `NUMBER` values are returned as Python `Decimal`, so an API layer
  must convert them to JSON.
- `backend/.env` is not loaded automatically yet.

## License

Not yet chosen. An open-source licence file still needs to be added.
