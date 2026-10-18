# DataMind evaluation suite

Measures the real natural-language-to-SQL pipeline (`POST /api/query`) against
answers computed **independently of Gemma**.

## Contents

| File | Purpose |
| --- | --- |
| `cases.json` | 30 cases: id, dataset, question, category, difficulty, tables, assumptions, reference SQL, expected behavior/result |
| `fixtures/retail.sql` | Synthetic 4-table dataset (customers, products, orders, order_items) with foreign keys |
| `datasets.py` | Builds fresh fixture databases in a temporary folder for every run |
| `compare.py` | Result comparison tolerant of column order, aliases, extra columns and small numeric differences |
| `run_eval.py` | Runner: per-case outcome, accuracy, per-category counts, JSON report |
| `data_change.py` | "Answer changes when data changes" demonstration on an isolated database |
| `results/` | JSON reports (git-ignored) |

## Ground truth

- **sales** (6 rows) and **retail** cases: expected rows were computed by
  hand-written `reference_sql` on the deterministic fixtures and are stored in
  `cases.json`. `backend/tests/test_eval.py` re-runs every reference query and
  fails if a stored answer no longer matches, so the expectations cannot drift.
- **tpch** cases (optional, live): Snowflake's sample data may not be copied
  into the repository, so expected rows are computed at run time by the
  reference SQL through the same validated read-only path.
- Expected answers live only in this folder; the production code never reads them.

## Behaviors judged

| Behavior | Pass condition |
| --- | --- |
| `rows` | success, and the rows match the expected rows (or an accepted alternative such as a percentage) |
| `top` | success, and the first row matches (for "which … the most" questions) |
| `empty` | success with zero rows |
| `refused` | `refused`, nothing executed |
| `clarification` | `clarification_needed`, nothing executed |
| `not_answered` | anything but success, with no fabricated answer |

Categories covered: aggregation, filtering, grouping, ranking, multi-step,
join, alternative phrasing, date filter, empty result, ambiguous, missing data,
data-modification request, prompt injection, unsupported (forecast).

## Run (PowerShell, repo root)

```powershell
.\.venv\Scripts\python.exe backend\eval\run_eval.py --mode reference                      # harness only, no model
.\.venv\Scripts\python.exe backend\eval\run_eval.py --mode gemma                          # local fixtures, real Gemma
.\.venv\Scripts\python.exe backend\eval\run_eval.py --mode gemma --provider snowflake     # live SALES (load backend\.env first)
.\.venv\Scripts\python.exe backend\eval\run_eval.py --mode gemma --provider snowflake --dataset tpch
```

`reference` mode sends the reference SQL (or a screened question) and skips
cases that need the model; skipped cases never count as passes.

## Results recorded on 18 Oct 2026 (`gemma3:1b`, Q4_K_M, CPU)

| Run (in order) | Local DuckDB (26) | Snowflake SALES (15) | Snowflake TPC-H (4) |
| --- | ---: | ---: | ---: |
| Reference mode (no model; harness check) | 23/23 executed, 3 skipped | – | – |
| A. Example prompt (`ORDERS(ID, AMOUNT, YEAR)`), types as `NAME TYPE` | 12/26 (46.2%) | – | – |
| B. Unrelated example (`TRIPS`) + join-key hints | 13/26 (50.0%) | 6/15 (40.0%) | 0/4 |
| C. B + types as `NAME (type)` | 13/26 (50.0%) | 5/15 (33.3%) | – |
| D. C with types as `NAME: type` | 12/26 (46.2%) | 5/15 (33.3%) | – |
| **E. Final: C without any worked example** | **12/26 (46.2%)** | **7/15 (46.7%)** | **1/4 (25%)** |

Why each change was made (all generic, none based on the expected answers):
in A the model copied the example's `AMOUNT`/`YEAR` columns into retail queries;
join-key hints tell it which columns relate tables; `NAME (type)` stopped
Snowflake's upper-case `QUANTITY NUMBER` from being read as `QUANTITY_NUMBER`;
in B–D the model imitated the example's single-column `SUM`, which broke
"revenue" on Snowflake. E is kept because Snowflake is the submission target.
Run-to-run differences of ±1 case are within the noise of a 1B model.

**Reliable:** single-table aggregations and filters; refusing data-change,
prompt-injection and forecast requests (always, before the model runs);
empty-result reporting when the SQL is right.

**Unreliable with the 1B model:** joins across 3–4 tables, multi-step
calculations (shares, averages of per-order totals), picking the measure
(`COUNT` vs `SUM`, revenue vs quantity), detecting ambiguity (0/2 clarification
cases), and declining questions the schema cannot answer (profit margin was
sometimes answered with an unrelated calculation). Every answer shows its SQL,
so these errors are visible to the user rather than hidden.

A larger Gemma variant (for example `gemma3:4b`) is the obvious next experiment;
it was **not** downloaded or tested here because only 1–2 GB of RAM was free.
