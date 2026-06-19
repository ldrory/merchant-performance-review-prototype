import re

from src.config import settings
from src.presentation.versioning import merchant_paths, new_version, write_latest


def test_new_version_format():
    v = new_version()
    assert re.fullmatch(r"\d{8}T\d{6}Z", v)


def test_merchant_paths_compose_company_then_version(tmp_path):
    deck, charts = merchant_paths("acme", "20260616T101500Z", base=tmp_path)
    assert deck == tmp_path / "decks" / "acme" / "acme_20260616T101500Z.pptx"
    assert charts == tmp_path / "charts" / "acme" / "20260616T101500Z"


def test_merchant_paths_default_base_is_output_dir():
    deck, charts = merchant_paths("acme", "v1")
    assert deck == settings.OUTPUT_DIR / "decks" / "acme" / "acme_v1.pptx"
    assert charts == settings.OUTPUT_DIR / "charts" / "acme" / "v1"


def test_write_latest_records_version(tmp_path):
    merchant_dir = tmp_path / "decks" / "acme"
    path = write_latest(merchant_dir, "20260616T101500Z")
    assert path == merchant_dir / "LATEST"
    assert path.read_text().strip() == "20260616T101500Z"
