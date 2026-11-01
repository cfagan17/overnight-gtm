#!/usr/bin/env python3
"""Fit assessment: should this company use earned-autonomy, and in which mode?

Read-only. Combines a short questionnaire with what it can read from your CRM's metadata.

  python tools/fit-assessment/assess.py --answers answers.json
  python tools/fit-assessment/assess.py --answers answers.json --salesforce-describe ./describe/
  python tools/fit-assessment/assess.py --answers answers.json --hubspot-properties ./properties/
  python tools/fit-assessment/assess.py --answers answers.json --postgres "$DATABASE_URL"

answers.json (see answers.example.json):
  {"company_stage": "seed|series_a|series_b|growth|public", "gtm_headcount": 12,
   "current_crm": "none|salesforce|hubspot|attio|other", "has_gtm_engineer": true,
   "target_accounts": 800, "compliance": ["soc2"], "partner_motion": true, "usage_based_pricing": false}

Salesforce describe: one JSON file per object from `sf sobject describe --sobject <Name> --json`
(Account, Opportunity, Contact, OpportunityLineItem, Contract, Territory2, OpportunityPartner).
HubSpot: JSON from GET /crm/v3/properties/<object> for deals, companies, contacts.
"""
from __future__ import annotations

import argparse
import json
import pathlib

LEDGER_NEEDS = [
    ("Accounts, contacts, deals", "core"),
    ("Territories with effective dates", "territories"),
    ("Deal lines (products, ARR per line)", "lines"),
    ("Contracts with start and end dates", "contracts"),
    ("Partner credit on deals", "partners"),
    ("Forecast category on deals", "forecast_category"),
    ("Weekly forecast snapshots", "snapshots"),
    ("Field history / audit trail", "audit"),
]


def from_salesforce(d: pathlib.Path) -> dict:
    objs = {}
    for f in d.glob("*.json"):
        body = json.loads(f.read_text())
        body = body.get("result", body)
        objs[body.get("name", f.stem)] = {fld["name"] for fld in body.get("fields", [])}
    opp = objs.get("Opportunity", set())
    return {
        "core": all(o in objs for o in ("Account", "Contact", "Opportunity")),
        "territories": "Territory2" in objs,
        "lines": "OpportunityLineItem" in objs,
        "contracts": "Contract" in objs,
        "partners": "OpportunityPartner" in objs or any(n.lower().startswith("partner") for n in opp),
        "forecast_category": "ForecastCategoryName" in opp,
        "snapshots": False,   # reporting snapshots are configured, not visible in describe
        "audit": True,        # Salesforce keeps field history on tracked fields
        "ea_fields_installed": "EA_Decision_Id__c" in opp,
    }


def from_hubspot(d: pathlib.Path) -> dict:
    props = {}
    for f in d.glob("*.json"):
        body = json.loads(f.read_text())
        props[f.stem] = {p["name"] for p in body.get("results", body if isinstance(body, list) else [])}
    deals = props.get("deals", set())
    return {
        "core": all(k in props for k in ("deals", "companies", "contacts")),
        "territories": False,
        "lines": True,            # HubSpot line items exist as an object
        "contracts": False,
        "partners": any("partner" in p for p in deals),
        "forecast_category": "hs_manual_forecast_category" in deals or "hs_forecast_category" in deals,
        "snapshots": False,
        "audit": True,            # property history
        "ea_fields_installed": "ea_decision_id" in deals,
    }


def from_postgres(dsn: str) -> dict:
    import psycopg
    with psycopg.connect(dsn) as c:
        tables = {r[0] for r in c.execute("select table_name from information_schema.tables where table_schema = 'public'")}
        accounts = c.execute("select count(*) from public.companies").fetchone()[0] if "companies" in tables else None
    return {
        "core": {"companies", "contacts", "deals"} <= tables,
        "territories": "territories" in tables, "lines": "deal_lines" in tables, "contracts": "contracts" in tables,
        "partners": "deal_partners" in tables, "forecast_category": "forecast_snapshots" in tables,
        "snapshots": "forecast_snapshots" in tables, "audit": "audit_log" in tables,
        "ea_fields_installed": "decisions" in tables, "accounts": accounts,
    }


def recommend(a: dict, crm: dict | None) -> tuple[str, list[str], list[str]]:
    reasons, cautions = [], []
    head = a.get("gtm_headcount", 0)
    current = a.get("current_crm", "none")
    eng = a.get("has_gtm_engineer", False)
    if current in ("none", "attio", "other") and head <= 15 and not eng:
        mode = "buy"
        reasons.append("A small team without a GTM engineer is better served by a maintained AI-native CRM "
                       "(Day AI, Attio, Lightfield). This repo's method (evidence, decisions, holdouts, promotion) "
                       "can still guide how you use it.")
    elif current in ("salesforce", "hubspot"):
        mode = f"sidecar ({current})"
        name = {"salesforce": "Salesforce", "hubspot": "HubSpot"}[current]
        reasons.append(f"Keep {name} as the system of record. Run the primitives and loops beside it; agent "
                       "changes go back through one integration user with a narrow permission set.")
    elif eng:
        mode = "greenfield (Atomic CRM fork)"
        reasons.append("You have someone to own the code, and no CRM to keep. Fork Atomic CRM and apply these migrations.")
    else:
        mode = "buy"
        reasons.append("Without a GTM engineer to own it, a self-hosted CRM becomes someone's second job.")
    accts = a.get("target_accounts") or (crm or {}).get("accounts") or 0
    per_arm = int(accts * 0.2)
    if accts and per_arm < 300:
        cautions.append(f"With about {accts} target accounts, a 20% holdout is about {per_arm} accounts. That detects only "
                        "large effects. Plan to test big changes, run tests longer, or rely more on review acceptance.")
    if "soc2" in [c.lower() for c in a.get("compliance", [])] and mode.startswith("greenfield"):
        cautions.append("Supabase's SOC 2 covers its infrastructure, not your application. You will need to produce "
                        "the evidence for this code yourself (access reviews, change management, the audit log).")
    if a.get("partner_motion"):
        reasons.append("You have a partner motion: the partner credit, partner-route policy and partner intelligence "
                       "loop apply directly.")
    if head > 200 and mode.startswith("greenfield"):
        cautions.append("At this size, replacing the CRM is a large migration. The sidecar mode gets most of the value "
                        "with far less risk.")
    return mode, reasons, cautions


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--salesforce-describe")
    ap.add_argument("--hubspot-properties")
    ap.add_argument("--postgres")
    a = ap.parse_args()
    answers = json.loads(pathlib.Path(a.answers).read_text())
    crm = None
    if a.salesforce_describe:
        crm = from_salesforce(pathlib.Path(a.salesforce_describe))
    elif a.hubspot_properties:
        crm = from_hubspot(pathlib.Path(a.hubspot_properties))
    elif a.postgres:
        crm = from_postgres(a.postgres)
    mode, reasons, cautions = recommend(answers, crm)
    out = ["# Fit assessment", "", f"**Recommended mode: {mode}**", ""]
    out += [f"- {r}" for r in reasons]
    if cautions:
        out += ["", "## Cautions", ""] + [f"- {c}" for c in cautions]
    if crm:
        out += ["", "## What your CRM already has", "", "| Need | Present |", "| --- | --- |"]
        out += [f"| {label} | {'yes' if crm.get(key) else 'no'} |" for label, key in LEDGER_NEEDS]
        out += [f"| earned-autonomy fields installed | {'yes' if crm.get('ea_fields_installed') else 'no'} |"]
        gaps = [label for label, key in LEDGER_NEEDS if not crm.get(key)]
        if gaps:
            out += ["", "Gaps the ledger tables or sidecar mirror would fill: " + ", ".join(gaps) + "."]
    out += ["", "This is a starting point for a conversation, not a verdict. See EVALUATE.md for when not to use this.", ""]
    print("\n".join(out))


if __name__ == "__main__":
    main()
