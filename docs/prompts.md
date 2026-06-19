# Prompts & LLM Instructions

The prototype uses the LLM for **narrative only** — it never computes numbers. Every
figure shown in a deck is precomputed by the metric engine (`src/metrics`) and the deck
insight layer (`src/presentation/deck_schema.py`), then passed to the model as text. The
model returns structured JSON validated against a Pydantic schema.

## Where this lives in code
- System + user prompts: `src/llm/prompts.py`
- Structured output schema + call: `src/llm/narrative_generator.py` (`NarrativeBundle`)
- Model factory (provider-agnostic, default Claude): `src/llm/client.py`

## Call shape
One structured call per merchant:

```
model.with_structured_output(NarrativeBundle).invoke([SystemMessage(...), HumanMessage(...)])
```

`NarrativeBundle`:
- `executive_summary: list[str]` — 3–5 one-line bullets
- `kpi_analysis: dict[str, str]` — `metric_id` → 2–4 sentence paragraph

## System prompt

```
You are a Riskified Customer Success Manager writing a merchant performance review.
Write in clear, concise, professional business English for a merchant audience.

STRICT RULES:
- Use ONLY the numbers provided in the user message. NEVER invent, estimate, or
  recompute any figure. If a number isn't provided, don't state it.
- Explain what changed and why it matters. When an evidence event lines up in time with a
  movement, note that it COINCIDES with the change — do not assert it caused the change.
- Use measured, hedged language: prefer "coincides with", "is consistent with", "may
  indicate", "suggests". Do NOT use "directly attributable", "models appropriately tightened",
  "fraud environment normalized", or "demonstrates model robustness".
- Respect each KPI's direction: for Approval Rate higher is better; for Accepted
  Chargeback Rate and Effective Fraud Rate lower is better.
- This is a CUSTOMER-FACING document. Never mention internal data-quality, validation,
  mismatch, provided-vs-computed, reconciliation, or "data points" topics.
- Some merchants have a count-based (transaction volume) and an amount-weighted (submitted
  value) view. When both are provided for a KPI, discuss both perspectives.
- Keep each KPI analysis to 2-4 sentences; keep executive-summary bullets to one line.
```

A deterministic **language gate** (`src/llm/evaluation.py` `check_language`) enforces the
customer-safe rules above: the deck is **not** written if the narrative contains internal/QA
terms (mismatch, provided-vs-computed, data-quality, "N of M data points", …) or over-strong
causal claims (directly attributable, …).

## User message (rendered from the precomputed DeckModel)

Built by `build_user_message(deck)`. Example (ACME, abridged):

```
Merchant: ACME (Post authorization, Strategic)
Period: 2025-07 to 2026-06

KPIs (all figures precomputed — use exactly as given):
- Submission Volume (id=submission_volume, neutral):
    first 4,584 (2025-07) → latest <…> (2026-06); change <…>%; trend —
    best <…> (<…>); worst <…> (<…>)
- Approval Rate (id=approval_rate, higher is better):
    first 96.84% (2025-07) → latest <…> ...
- Accepted Chargeback Rate (id=accepted_chargeback_rate, lower is better): ...
- Effective Fraud Rate (id=effective_fraud_rate, lower is better): ...

    count-based: first 96.84% (2025-07) → latest <…> ...
    amount-weighted: first <…> → latest <…>; change <…>   # Strategic only

Evidence events:
- 2025-12: Peak Season
- 2026-01: High Fraud
- 2026-02: Low Volume

Write: (1) an executive_summary as 3-5 one-line bullets, and
(2) kpi_analysis: a 2-4 sentence paragraph per KPI keyed by its id.
```

Internal data-quality notes are **not** included in the prompt (they stay in
`quality_summary.json` and the write-up). For Strategic merchants each rate KPI also carries an
`amount-weighted` line so the model can discuss the submitted-value perspective.

## Why this design
- **No hallucinated math**: the model can't change a number it's only handed as text, and
  the schema constrains output shape. All arithmetic is unit-tested in `src/metrics`.
- **Provider-agnostic**: `init_chat_model` lets us swap Claude ↔ another provider via env.
- **Testable offline**: `generate_narrative(deck, model=...)` accepts an injected model, so
  tests use a fake that returns a canned `NarrativeBundle` (no network, no cost).
