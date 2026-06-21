# Architecture

**Deterministic data first, AI second.** One curated fact layer feeds *both* the decks and the
agent — so they never disagree, and the LLM never does arithmetic.

![Architecture](images/architecture.png)

## Pipeline (table-first / ELT)

`CSVs → load → validate (gate) → DuckDB source tables → metric engine (monthly + quarterly
facts) → MetricsRepository (merchant-scoped) → decks + agent`

The DB is the source of truth: the engine computes *on top of* the persisted tables, not from
in-memory state.

## Curated tables (ERD)

Five tables, all keyed by **`merchant_id`** — the deterministic slug that is also the
tenant-isolation key. Three **source** tables hold the validated inputs; two **fact** tables hold
the computed KPIs (derived from `kpi_measures` + `merchants`).

```
merchants (1) ──< kpi_measures
          (1) ──< evidence
          (1) ──< kpi_facts_monthly ──rollup──> kpi_facts_quarterly
```

| Table | Grain | Key / identifying columns | Purpose |
|---|---|---|---|
| `merchants` | one row per merchant | `merchant_id` (PK), `merchant_name`, `pre_or_post`, `business_structure` | Profile dimension; drives metric shape (Pre/Post stage, Strategic vs Enterprise variants). |
| `kpi_measures` | merchant × month × KPI | `merchant_id`, `period` (YYYY-MM), `kpi_name`, `value` | Tidy raw measures — the metric engine's input, read back from DuckDB. |
| `evidence` | merchant × month × event | `merchant_id`, `period`, `event` | Notable events (e.g. *High Fraud*) annotated on charts and surfaced by the agent. |
| `kpi_facts_monthly` | merchant × month × metric × variant | `merchant_id`, `period`, `metric_id`, `variant` (cnt/sum) | Computed monthly KPI facts: the displayed `value` + the provided-vs-computed cross-check. |
| `kpi_facts_quarterly` | merchant × quarter × metric × variant | `merchant_id`, `quarter`, `metric_id`, `variant` | Volume-weighted quarterly rollups (same columns as the monthly fact table). |

**Relationships:** `merchants.merchant_id` is 1—* to every other table, and *every* read is filtered
by it (the isolation boundary). The fact tables additionally carry the reconciliation columns
`value_source` (additive | provided | computed), `provided_value`, `computed_value`, `numerator`,
`denominator`, `abs_diff`, `rel_diff_pct`, `validation_status` — kept for the quality layer and
**never shown to merchants**. Every table also carries lineage: `source_file`, `source_sha256`,
`loaded_at`.

## Metric rules (profile-driven)

| Profile | Effect |
|---|---|
| Pre / Post | which authorization measures are used |
| Strategic | count **and** amount-weighted (sum) views |
| Enterprise | count only |

**Value resolution:** additive → raw measure · provided-rate KPIs (Approval, Accepted
Chargeback) → the **provided rate is the source of truth** (components validate it) · Effective
Fraud → computed. **Quarterly = volume-weighted**, never a naive average of monthly rates.

## Quality — 4 layers

| # | Layer | Blocks? |
|---|---|---|
| 1 | Input validation (schema, ranges, duplicates, zero denominators, evidence) | ✅ bad merchant excluded; global error aborts |
| 2 | Computation integrity (every required fact is producible) | ✅ |
| 3 | Metric quality (provided vs computed divergence) | ⚠️ warning only |
| 4 | Narrative eval (structure · faithfulness · customer-safe language) | ✅ no deck if it fails |

One bad merchant never blocks a 200–300 batch. Artifacts: `data/output/quality/…` (per-process,
shared schema).

## Agent — isolation by construction 🔒

- `merchant_id` comes from the session only; tools **close over it** and expose no merchant
  parameter.
- Reads only merchant-scoped facts — **no LLM-generated SQL**.
- The prompt is built from one merchant, so the agent physically can't see another. Proven in
  `tests/test_tenant_isolation.py`.
- Production: back this with database **row-level security**.

## Scale (200–300 merchants/run)

Per-merchant work is independent → parallel workers + bounded LLM concurrency. Swap DuckDB →
Postgres/warehouse. Outputs are versioned per run.

## Tested

162 tests, no network (the LLM is injected/faked). Unit tests + one real-data smoke test.

---
More: [writeup.md](writeup.md) (approach, trade-offs, production) · [prompts.md](prompts.md)
(LLM prompts).
