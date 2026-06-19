# Write-up — Merchant Performance Review prototype

A prototype that turns three merchant KPI CSVs into (1) per-merchant PowerPoint
performance-review decks and (2) a tenant-isolated conversational agent. This document covers
the approach, assumptions, AI tooling, architecture, quality strategy, production
considerations, and the key trade-offs. Deep detail lives in
[`architecture.md`](architecture.md) and [`prompts.md`](prompts.md).

---

## 1. Approach & scope

- **Table-first / ELT shape.** CSVs are loaded into DuckDB *source* tables first
  (`merchants`, `kpi_measures`, `evidence`); the metric engine then reads them back and
  computes facts on top (`kpi_facts_monthly`, `kpi_facts_quarterly`). The DB is the source of
  truth, not a result sink — the same path scales to a warehouse.
- **Registry-driven metrics.** A declarative registry (`src/metrics/registry.py`) maps each
  business KPI to its raw measure names and variants. Adding a KPI = a registry entry, not new
  code paths.
- **The LLM never does arithmetic.** Every number is computed and unit-tested in Python; the
  LLM only *narrates* precomputed values (decks) or *reads* precomputed facts (agent). This is
  the single most important correctness decision — it removes the largest hallucination risk.
- **Two consumers, one curated layer.** Decks and the agent both read through one
  merchant-scoped repository, so they can never disagree on the numbers or widen data scope.
- **Built phase-by-phase, TDD throughout.** 142 tests, no network needed (the LLM is injected
  and faked in tests).

---

## 2. Assumptions

- **The provided rate is the customer-facing source of truth.** Where the dataset ships a
  precomputed rate (Approval Rate, Accepted Chargeback Rate) that value is displayed; the
  component ratio (`numerator/denominator`) is computed in parallel **for validation only**.
  Effective Fraud Rate has no provided rate, so it is computed.
- **The provided rate may not reconcile exactly to its components** (it diverges in ~95% of
  Accepted-Chargeback rows in the dummy data, by up to ~86%). This is treated as expected —
  the source likely reflects timing/attribution/business-rule differences the components don't
  capture — and surfaced as a *non-blocking* note, never as a blocker or a "data error".
- **Profile drives metric shape** (from the brief): `Pre`/`Post` selects the authorization
  stage; `Strategic` gets count **and** amount-weighted (`sum`) variants, non-Strategic gets
  count only. These are deterministic rules in the engine, not LLM judgment.
- **Quarterly rates are volume-weighted** (`Σ(value·denom)/Σ(denom)`), never naive averages.
- **`merchant_id` is a deterministic slug** of the merchant name — the canonical join/group key
  *and* the isolation key. No separate identity/session store is needed for the prototype.
- **Monthly granularity is sufficient**; the data has no finer grain, so quarters roll up from
  months.
- **The Streamlit merchant picker simulates authentication** — in production the session
  `merchant_id` comes from real auth, never from the user or the model.

---

## 3. AI tooling

- **Provider-agnostic via LangChain** `init_chat_model` (`src/llm/client.py`); default is
  Claude (`claude-sonnet-4-6`), switchable by env (`LLM_PROVIDER`, `LLM_MODEL`).
- **Decks:** one structured-output call (`with_structured_output`) returns an executive summary
  + per-KPI analysis from a strict prompt that contains *only* precomputed numbers and forbids
  invention. See [`prompts.md`](prompts.md).
- **Agent:** `bind_tools` + a small manual tool loop (no LangGraph). Tools return precomputed,
  merchant-scoped facts; the model composes the answer.
- **Testability:** the chat model is dependency-injected, so tests use a `FakeChatModel` — the
  full deck and agent paths run offline with no API key.
- **Claude Code** was used as the development agent to build the project (see the prompts/docs
  as the record of design decisions).

---

## 4. Architecture (overview)

```
data/raw/*.csv ─► load ─► validate ─► persist SOURCE tables ─► metric engine ─► persist FACTS
                                       merchants · kpi_measures    (reads tables   kpi_facts_monthly
                                       · evidence  (DuckDB)         back)          kpi_facts_quarterly
                                                          │
                                       MetricsRepository (merchant-scoped reads = isolation boundary)
                                          │                                  │
                              [Phase 2] deck generator        [Phase 3] CLI + Streamlit agent
```

- **Pipeline** (`src/pipeline.py`) is a small DAG: validate → ingest sources → compute facts →
  persist facts.
- **Repository** (`src/repositories/metrics_repository.py`) is the single read/write path; every
  scoped read filters by `merchant_id`.
- **Decks**: `deck_schema` (pure-Python insights) → `chart_generator` (matplotlib) →
  `narrative_generator` (LLM) → `evaluation` (gate) → `deck_generator` (python-pptx).
- **Agent**: `build_merchant_tools(repo, merchant_id)` (tools close over the merchant) →
  `MerchantAgent` (tool loop) → CLI / Streamlit.

Full detail: [`architecture.md`](architecture.md).

---

## 5. Quality evaluation (4 layers)

Two gates, two non-blocking; each check has one home and one consumer.

| # | Layer | Behaviour | Where |
|---|---|---|---|
| 1 | Input validation | **GATE** — bad merchant excluded; global error aborts | `ingestion/validation.py` |
| 2 | Metric computation integrity | **GATE** — uncomputable fact (missing component / zero denominator) blocks | `validation.py` + `metrics/quality.find_broken_metric_merchants` |
| 3 | Metric quality | **note** — provided-vs-computed divergence summary (provided = truth) | `metrics/quality.summarize_metric_quality` |
| 4 | Narrative faithfulness | **GATE** — LLM prose checked for structure + numbers within ±1% of provided; deck not written on failure | `llm/evaluation.py` |

Each process emits the layers it actually runs (consistent `LayerResult` schema), written to
`data/output/quality/`. Numbers are correct *by construction* (engine computes + is tested; the
LLM only narrates), and Layer 4 is the safety net that catches any narration drift.

---

## 6. Production: scalability & safety

**Scale (target 200–300 merchants/run).**
- Generation is sequential here; it parallelizes trivially (per-merchant decks are independent)
  with a worker pool + bounded LLM concurrency/retries.
- DuckDB is the embedded prototype store; the same table-first model maps directly onto a
  warehouse (Postgres/Snowflake/BigQuery). The repository is the only thing that changes.
- Charts/decks are versioned per run and never overwrite, so runs are reproducible and
  diff-able.

**Safety / multi-tenant isolation.**
- **The LLM is not a security boundary.** Isolation is *structural*: `merchant_id` comes only
  from the session; agent tools close over it and expose no `merchant_id` parameter; the system
  prompt is built from the selected merchant only. The agent never holds another tenant's data,
  so it cannot leak it — proven in `tests/test_tenant_isolation.py`, not policed by a guard.
- **No LLM-generated SQL.** The agent reads pre-scoped facts; it never composes queries, so a
  prompt injection cannot widen scope.
- **Production hardening:** back the app-layer scoping with **database Row-Level Security /
  tenant policies**, real auth for the session `merchant_id`, secrets via a manager (not env),
  and an LLM-as-judge + human-approval workflow for subjective narrative quality.
- **Merchant-facing language:** agent responses use business language only; internal QA fields
  (mismatch, validation status, provided-vs-computed) stay in the quality artifacts and this
  write-up.

---

## 7. Key decisions & trade-offs

| Decision | Why | Trade-off / alternative |
|---|---|---|
| **DuckDB** (embedded) | Zero-setup, fast analytical SQL, perfect for a prototype + tests | Single-writer; not multi-tenant. Prod → Postgres + RLS. |
| **Provided rate = truth**, components validate | The dataset ships official rates; recomputing would silently disagree | We surface the divergence as a note instead of "fixing" it. |
| **Scoped tools + full-dataset tool** for the agent | Tiny per-merchant data (~96 rows) → hand the model the whole *scoped* table; flexible answers, isolation intact | Not an LLM-to-SQL agent (more flexible, but moves the security boundary into the model). |
| **Deterministic narrative eval** | Cheap, reliable, no network in CI; catches hallucinated numbers | Doesn't judge subjective quality — LLM-as-judge + human approval is the prod step. |
| **LLM never does arithmetic** | Removes the biggest correctness risk | More plumbing (precompute everything) but numbers are trustworthy. |
| **No LangGraph / vector DB / SQL agent** | Scope is small and well-defined; a manual tool loop is simpler to reason about and test | Less "framework", but far less hidden behaviour. |
| **Pydantic for contracts only** | Validate definitions/reports/deck model, not every row | Row data stays as DataFrames (fast, pandas-native). |
| **Merchant-facing vs internal language split** | The agent is customer-facing per the brief | Two phrasings of the same facts; internal detail kept in artifacts. |

---

## 8. Anticipated questions

- **Why does the displayed rate not equal numerator/denominator?** The dataset provides the
  official rate; components are a validation cross-check. The prototype treats the provided
  value as the source of truth and does not claim `num/den = displayed value`.
- **How is tenant isolation guaranteed?** By construction: the session sets `merchant_id`,
  tools close over it (no `merchant_id` argument), the prompt is single-merchant, and the
  repository filters every read. The agent never has another tenant's data in context. Tests
  assert a tool set with no `merchant_id` param and single-merchant outputs even when the user
  asks about another merchant.
- **How do you stop the deck LLM from hallucinating numbers?** It only narrates precomputed
  values; the Layer-4 faithfulness gate re-checks material numbers (±1%) and blocks the deck if
  they don't match.
- **How would this scale to 200–300 merchants?** Per-merchant work is independent → parallel
  workers + bounded LLM concurrency; swap DuckDB for a warehouse; outputs already versioned.
- **What would you change for production?** Postgres + RLS, real auth, secrets manager,
  concurrency, LLM-as-judge + human review, and DataFrame-schema validation
  (Pandera/Great Expectations) in place of the custom pandas checks.
- **Why not let the agent write SQL?** It's more flexible but makes the LLM the security
  boundary; with such small per-merchant data, returning the pre-scoped table is simpler and
  safe.

---

## 9. Out of scope (future work)

Dependency lock file; CI; real auth; concurrency/caching; Postgres + RLS; LLM-as-judge + human
approval; Pandera/Great Expectations schema validation; richer chart types.
