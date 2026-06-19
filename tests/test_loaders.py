import pandas as pd

from src.ingestion.loaders import read_kpis, read_profiles, read_evidence


def _write(path, text):
    path.write_text(text)
    return path


def test_read_kpis_normalizes_columns(tmp_path):
    csv = _write(
        tmp_path / "kpis.csv",
        "Account Name,Date,KPI,Value\n"
        "ACME,2025-07,Submitted Cnt,4584\n"
        "ACME,2025-07,Submitted Sum,4061435.832\n",
    )
    df = read_kpis(csv)
    assert list(df.columns) == ["account_name", "period", "kpi_name", "value"]
    assert len(df) == 2
    assert df.loc[0, "account_name"] == "ACME"
    assert df.loc[0, "period"] == "2025-07"
    assert df.loc[0, "kpi_name"] == "Submitted Cnt"
    assert df.loc[0, "value"] == 4584.0


def test_read_kpis_value_is_numeric(tmp_path):
    csv = _write(
        tmp_path / "kpis.csv",
        "Account Name,Date,KPI,Value\nACME,2025-07,Submitted Sum,4061435.832\n",
    )
    df = read_kpis(csv)
    assert pd.api.types.is_float_dtype(df["value"])
    assert df.loc[0, "value"] == 4061435.832


def test_read_kpis_strips_whitespace(tmp_path):
    csv = _write(
        tmp_path / "kpis.csv",
        "Account Name,Date,KPI,Value\n  ACME ,2025-07, Submitted Cnt ,4584\n",
    )
    df = read_kpis(csv)
    assert df.loc[0, "account_name"] == "ACME"
    assert df.loc[0, "kpi_name"] == "Submitted Cnt"


def test_read_profiles_normalizes_columns(tmp_path):
    csv = _write(
        tmp_path / "profiles.csv",
        "Merchant Name,Pre or Post,Business structure\n"
        "ACME,Post,Strategic\n"
        "Vandelay Industries,Post,Enterprise\n",
    )
    df = read_profiles(csv)
    assert list(df.columns) == ["merchant_name", "pre_or_post", "business_structure"]
    assert df.loc[1, "merchant_name"] == "Vandelay Industries"
    assert df.loc[1, "business_structure"] == "Enterprise"


def test_read_evidence_normalizes_columns(tmp_path):
    csv = _write(
        tmp_path / "evidence.csv",
        "Merchant Name,Month,Event\nACME,2026-01,High Fraud\n",
    )
    df = read_evidence(csv)
    assert list(df.columns) == ["merchant_name", "period", "event"]
    assert df.loc[0, "period"] == "2026-01"
    assert df.loc[0, "event"] == "High Fraud"
