import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "fit-assessment"))
import assess  # noqa: E402


def test_small_team_is_told_to_buy():
    mode, reasons, _ = assess.recommend({"gtm_headcount": 4, "current_crm": "none", "has_gtm_engineer": False}, None)
    assert mode == "buy" and "Day AI" in reasons[0]


def test_salesforce_company_gets_sidecar_and_holdout_caution():
    mode, _, cautions = assess.recommend({"gtm_headcount": 45, "current_crm": "salesforce", "target_accounts": 900}, None)
    assert mode == "sidecar (salesforce)" and any("holdout" in c for c in cautions)


def test_greenfield_with_engineer_and_soc2_caution():
    mode, _, cautions = assess.recommend({"gtm_headcount": 20, "current_crm": "none", "has_gtm_engineer": True,
                                          "compliance": ["SOC2"], "target_accounts": 5000}, None)
    assert mode.startswith("greenfield") and any("SOC 2" in c for c in cautions)


def test_salesforce_describe_reading():
    crm = assess.from_salesforce(ROOT / "tools/fit-assessment/examples/salesforce-describe")
    assert crm["core"] and crm["lines"] and crm["forecast_category"] and not crm["territories"]


def test_postgres_reading(dsn):
    crm = assess.from_postgres(dsn)
    assert all(crm[k] for k in ("core", "territories", "lines", "contracts", "partners", "snapshots", "audit")) and crm["accounts"] == 24
