"""Narrative generation with a FakeChatModel (no network)."""
from src.db.connection import get_connection
from src.ingestion.loaders import read_kpis, read_profiles, read_evidence
from src.llm.narrative_generator import NarrativeBundle, generate_narrative
from src.llm.prompts import build_user_message
from src.metrics.registry import METRIC_REGISTRY
from src.pipeline import run_pipeline
from src.presentation.deck_schema import build_deck_model
from src.repositories.metrics_repository import MetricsRepository


class _FakeStructured:
    def __init__(self, result, recorder):
        self.result, self.recorder = result, recorder

    def invoke(self, messages):
        self.recorder.append(messages)
        return self.result


class FakeChatModel:
    """Mimics the slice of the LangChain chat-model API the generator uses."""
    def __init__(self, result):
        self.result = result
        self.messages_seen: list = []

    def with_structured_output(self, schema):
        return _FakeStructured(self.result, self.messages_seen)


def _model():
    con = get_connection(":memory:")
    run_pipeline(con, read_kpis(), read_profiles(), read_evidence())
    return build_deck_model(MetricsRepository(con), "acme")


def test_build_user_message_includes_precomputed_numbers():
    deck = _model()
    msg = build_user_message(deck)
    assert "ACME" in msg
    # Submission Volume latest = Jun'26 submitted count, formatted with a thousands sep.
    sv = next(k for k in deck.kpis if k.metric_id == "submission_volume")
    assert f"{sv.latest_value:,.0f}" in msg
    # evidence context is passed to the model
    assert "High Fraud" in msg


def test_build_user_message_excludes_internal_data_quality():
    # Customer-facing: internal QA wording must not reach the prompt/model.
    msg = build_user_message(_model()).lower()
    assert "data-quality" not in msg and "data quality" not in msg
    assert "mismatch" not in msg


def test_build_user_message_includes_amount_for_strategic():
    msg = build_user_message(_model())  # ACME is Strategic
    assert "amount-weighted" in msg


def test_generate_narrative_returns_bundle_for_each_kpi():
    deck = _model()
    canned = NarrativeBundle(
        executive_summary=["Strong approval rate.", "Volume steady."],
        kpi_analysis={m.id: f"analysis for {m.id}" for m in METRIC_REGISTRY},
    )
    fake = FakeChatModel(canned)
    result = generate_narrative(deck, model=fake)
    assert result.executive_summary
    assert set(result.kpi_analysis) == {m.id for m in METRIC_REGISTRY}
    assert fake.messages_seen  # the model was actually invoked
