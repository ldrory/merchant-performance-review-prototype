# Architecture

A prototype that turns merchant KPI CSVs into per-merchant PowerPoint performance reviews
(charts + LLM narrative), built on a table-first DuckDB pipeline, with a clearly classified
quality model. (Phase 3, a per-merchant conversational agent, reuses the same data layer.)

## Data flow (table-first / ELT-shaped)

```
CSVs ─[load]→ tidy frames ─[INPUT VALIDATION gate]→ exclude bad merchants / abort
                                   │
                                   ▼  persist source-of-truth tables (valid merchants only)
        DuckDB:  merchants · kpi_measures · evidence            (+ lineage)
                                   │
                                   ▼  engine reads kpi_measures + merchants BACK from DuckDB
        compute_monthly_facts → kpi_facts_monthly
        compute_quarterly_facts → kpi_facts_quarterly           (+ lineage)
                                   │
                MetricsRepository (merchant-scoped reads = isolation boundary)
                                   │
        ┌──────────────────────────┴───────────────────────────┐
        ▼                                                        ▼
  Phase 2 deck generation                               Phase 3 agent (reuses repo)
  deck_schema → charts → narrative(Claude)
  → NARRATIVE EVAL gate → .pptx + .eval.json
```

The database is the source of truth: the engine computes *on top of* the persisted
`kpi_measures` table, not from in-memory state. Two invariants hold everywhere:
- **The LLM never does arithmetic** — every number is computed in Python (unit-tested) and
  handed to the model as text; the model only narrates.
- **Merchant isolation** — all merchant reads go through `MetricsRepository`, filtered by
  `merchant_id` (a deterministic slug). Phase 3 tools inherit this.

## Curated tables (5, no `raw_*`)

| Table | Grain | Notes |
|---|---|---|
| `merchants` | merchant | `merchant_id` slug PK, Pre/Post, Strategic/Enterprise |
| `kpi_measures` | merchant×month×raw-KPI | normalized long KPI **source of truth** |
| `evidence` | event | re-keyed to `merchant_id` |
| `kpi_facts_monthly` | merchant×month×metric×variant | `FACT_COLUMNS` |
| `kpi_facts_quarterly` | merchant×quarter×metric×variant | volume-weighted rollup |

Every table carries **lineage**: `source_file`, `source_sha256`, `loaded_at` (one shared
timestamp per run). `FACT_COLUMNS` is defined once in `metrics/engine.py`; `db/schema.sql`
mirrors it and a test guards against drift.

## Metric model

Registry-driven (`metrics/registry.py`). 4 KPIs × {cnt, sum} variants (sum is Strategic-only):
Submission Volume (additive), Approval Rate, Accepted Chargeback Rate, Effective Fraud Rate.

**Value resolution** (`metrics/engine.py`):
- additive → `value` = the raw measure.
- ratio with a provided rate (Approval, Accepted CHBG) → `value` = **provided** rate; the
  formula `numerator/denominator` is computed in parallel for validation only.
- ratio without one (Effective Fraud) → `value` = computed `numerator/denominator`.

Rationale: in the dummy data the provided Accepted-Chargeback-Rate diverges from components by
up to 86%; the provided rate is the merchant's "official" number, so it stays the display
source of truth and the divergence is surfaced as a warning (not changed, not blocked).

**Quarterly** (`metrics/quarterly.py`) is **volume-weighted** by denominator, never a naive
average of monthly rates.

## Quality model — 4 layers, clearly classified

The guiding rule is **classification, not more reports**: input errors block, metric
**computation** errors block, metric **mismatch** warnings do not block, narrative eval errors
block. No modes/flags.

### 1. Input Validation Gate — blocks bad source data
`ingestion/validation.py` → `ValidationReport(issues)`. Raw structural/data-sanity checks:
required columns, enum values, `YYYY-MM` periods, duplicate rows, referential consistency,
rate range [0,1], non-negative values. A merchant with an `error` is **excluded before
persistence**; a global error (missing columns) or zero valid merchants **aborts the run**.

### 2. Metric Computation Integrity Gate — blocks if required facts can't be computed
Ensures every required fact can actually be produced. Enforced **pre-persist at input time**
(so a merchant that can't compute is never persisted — no delete-after-persist):
- **missing required component** (numerator/denominator/provided/source) → `missing_kpi`
  (the 16-KPI completeness check).
- **zero denominator** for a computed ratio → `zero_denominator`.
Plus a **post-compute safety net** (`metrics/quality.find_broken_metric_merchants`): if any
fact still has a null `value` or `missing_components`, the run fails loudly (defense-in-depth;
unreachable once the input checks pass for this data shape).

### 3. Metric Quality Summary — non-blocking warnings only
`metrics/quality.summarize_metric_quality(facts)` → one aggregated, neutral line per metric
whose **provided rate differs from the computed value**. This is a warning, *never* a blocker
(provided rate is the display source of truth). Single definition, two consumers: the deck
"Notes & Methodology" slide (via `deck_schema`) and the ingest console summary. No row-level
spam, no merchant-facing alarms.

### 4. Narrative Evaluation Gate — blocks the final deck
`llm/evaluation.py`, deterministic, after LLM generation:
- **structure** — exec summary present and every KPI has a non-empty analysis;
- **faithfulness** — coarse: flags only *material* invented numbers (counts/volumes not within
  ~1% of a figure the model was given), tolerating years, rates, small counts, rounding.
If `evaluate_narrative(...).ok` is false → `NarrativeEvalError`: **no pptx, no `LATEST`
update**, that merchant fails, and `generate_decks` exits non-zero with the reason. A passing
deck writes a `<deck>.eval.json` audit sidecar.

> Summary: `input errors block · computation errors block · mismatch warnings don't block ·
> narrative errors block`.

### Quality artifacts — per-process ownership
Each process emits the quality for the layers it actually runs (`src/quality_summary.py`).
Every layer uses the **same schema** — `layer`, `name`, `type` (gate/note), `blocking`,
`status` (PASS/WARN/FAIL), `summary`, `details` — and each file has a stage `overall_status`
(FAIL if any blocking layer fails, else WARN if any warns, else PASS).

- **ingest** owns Layers 1–3 → `data/output/quality/ingest_quality.json`, written **even when
  ingest fails** (only the layers that ran are included — later layers are never faked).
- **generate_decks** owns Layer 4 → `…/quality/<version>/deck_quality.json`, and writes a
  **consolidated** `…/quality/<version>/quality_summary.json` that *merges* the latest ingest
  summary (Layers 1–3) with Layer 4. The deck process does **not** re-run input validation —
  the source of truth for Layers 1–3 is the ingest artifact.
- The per-deck `<deck>.eval.json` is the Layer-4 per-merchant subset.

No DB table, no modes, no audit/event system. `generate_decks` exits non-zero when the
consolidated `overall_status == FAIL`.

## Conversational agent (Phase 3) — tenant isolation by construction
`src/agent/` + `scripts/chat.py` + `src/app/streamlit_app.py`. A per-merchant Q&A agent over the
same curated facts. The LLM is **not** a security boundary; isolation is structural:
- `merchant_id` comes only from the session (CLI `--merchant` / Streamlit picker) — never parsed
  from the question, never chosen by the LLM.
- `build_merchant_tools(repo, merchant_id)` returns tools that **close over `merchant_id`** and
  expose no such parameter (`get_merchant_facts`, `get_calculation_details`,
  `explain_reconciliation`, `get_evidence`, `get_profile`), using only the merchant-scoped
  repository reads. `get_merchant_facts` hands the
  LLM the merchant's *full* scoped time series (every month/quarter, both variants) so it can
  answer arbitrary questions by reading — deliberately **not** an LLM-to-SQL agent, which would
  move the security boundary into the model. `get_calculation_details(metric_id, period)` returns
  one KPI's methodology + supporting components (reported value, numerator, denominator, source
  field names), profile-selected (Pre vs Post; count + amount-weighted for Strategic).
- The agent is **merchant-facing**: its tool responses use business language only. Internal
  reconciliation fields (`value_source`, provided/computed values, `validation_status`, mismatch
  counts) stay in the fact table + `quality_summary.json` + the write-up — never in the chat.
- **Locked metric-explanation policy.** When the source dataset reports an explicit rate
  (Approval Rate, Accepted Chargeback Rate), that reported value is the customer-facing source of
  truth; `get_calculation_details` shows it plus supporting numerator/denominator components, and
  never prints `numerator / denominator = reported value` (it does not reconcile exactly).
  Computed-only metrics (Effective Fraud Rate) do show the real `numerator ÷ denominator = value`
  equation. Additive metrics (Submission Volume) show the raw source field. If a merchant asks why
  components don't reconcile, `explain_reconciliation` returns a fixed, transparent, customer-safe
  statement.
- The system prompt is built only from the selected merchant; the agent never loads any other
  tenant's data, so it cannot answer about another merchant — there is **no output guard**, and
  none is needed. `MerchantAgent.ask` runs a small manual tool loop (no LangGraph); the chat
  model is injectable so tests use a fake.
- Proven in `tests/test_tenant_isolation.py`: no tool exposes `merchant_id`, the prompt + tool
  outputs are single-merchant, and the agent feeds only the selected merchant's context even when
  the question names another merchant.

**Production note:** this app-layer scoping would be backed by **database-level Row-Level
Security / tenant policies** in production; the prototype demonstrates the model via strict
scoped reads + session-bound `merchant_id` + no cross-tenant context.

## Outputs & versioning
Per-company, then version: `data/output/decks/<merchant>/<merchant>_<version>.pptx` and
`charts/<merchant>/<version>/`, with a per-merchant `LATEST`. One UTC version per
`generate_decks` run; runs never overwrite each other.

## Testing
Logic is unit-tested with small synthetic fixtures (engine, quarterly, validation, metric
quality, evaluation); a real-data smoke test runs the whole pipeline into in-memory DuckDB and
asserts structural properties (not brittle floats). The LLM is dependency-injected so the deck
path is tested with a fake model — `pytest` needs no network/key.

## Production extensions (out of scope for the prototype)
- LLM-as-judge + human-approval workflow for subjective narrative quality (Layer 4 is
  deterministic-only here).
- DataFrame-schema validation via Pandera/Great Expectations (custom pandas checks here).
- Postgres + Row-Level Security for true multi-tenant isolation (app-layer scoping here).
- Concurrency/caching for the 200–300-merchant batch (sequential here).
