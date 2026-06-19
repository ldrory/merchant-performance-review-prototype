from src.db.connection import get_connection
from src.ingestion.loaders import read_kpis, read_profiles, read_evidence
from src.metrics.registry import METRIC_REGISTRY
from src.pipeline import run_pipeline
from src.presentation.chart_generator import _has_amount_overlay, render_charts
from src.presentation.deck_schema import build_deck_model
from src.repositories.metrics_repository import MetricsRepository


def _model(merchant_id="acme"):
    con = get_connection(":memory:")
    run_pipeline(con, read_kpis(), read_profiles(), read_evidence())
    return build_deck_model(MetricsRepository(con), merchant_id)


def test_render_charts_creates_monthly_and_quarterly_pngs(tmp_path):
    charts = render_charts(_model(), tmp_path)
    assert set(charts) == {m.id for m in METRIC_REGISTRY}
    for metric_id, paths in charts.items():
        assert paths["monthly"].exists() and paths["monthly"].stat().st_size > 0
        assert paths["quarterly"].exists() and paths["quarterly"].stat().st_size > 0


def test_charts_written_into_given_dir(tmp_path):
    charts = render_charts(_model(), tmp_path)
    assert charts["approval_rate"]["monthly"].parent == tmp_path


def test_overlay_only_for_strategic_rate_kpis():
    acme = {k.metric_id: k for k in _model("acme").kpis}            # Strategic
    vandelay = {k.metric_id: k for k in _model("vandelay-industries").kpis}  # Enterprise
    # Strategic rate KPI overlays both series; volume ($ vs orders) and Enterprise do not.
    assert _has_amount_overlay(acme["approval_rate"]) is True
    assert _has_amount_overlay(acme["submission_volume"]) is False
    assert _has_amount_overlay(vandelay["approval_rate"]) is False


def test_render_charts_count_only_for_enterprise(tmp_path):
    charts = render_charts(_model("vandelay-industries"), tmp_path)
    for paths in charts.values():
        assert paths["monthly"].exists() and paths["quarterly"].exists()
