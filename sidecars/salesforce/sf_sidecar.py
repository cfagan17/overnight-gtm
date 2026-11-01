#!/usr/bin/env python3
"""Salesforce sidecar: mirror ids/owners for visibility, and write approved agent changes back.

  python sidecars/salesforce/sf_sidecar.py ingest --dsn "$DATABASE_URL" --since 2026-10-01T00:00:00Z
  python sidecars/salesforce/sf_sidecar.py writeback --dsn "$DATABASE_URL"

Salesforce auth: SF_INSTANCE_URL and SF_ACCESS_TOKEN for the integration user (for
example from `sf org display --target-org <alias>`). The integration user should hold
only the EA_Agent_Writer permission set in metadata/, so Salesforce's own sharing,
field-level security and field history still apply to every write.

STATUS: written against the Salesforce REST API (v61.0) and tested here with a fake
HTTP session only. It has not been run against a real org.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

import psycopg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from sidecars.common.mirror import upsert_subjects, writeback  # noqa: E402

API = "v61.0"
# territory_key comes from a field you choose; the default uses a custom Account field.
QUERIES = {
    "company": "SELECT Id, Name, OwnerId, {terr} FROM Account WHERE SystemModstamp > {since}",
    "deal": "SELECT Id, Name, OwnerId, Account.{terr} FROM Opportunity WHERE SystemModstamp > {since}",
    "contact": "SELECT Id, Name, OwnerId, Account.{terr} FROM Contact WHERE SystemModstamp > {since}",
}


class Salesforce:
    def __init__(self, instance_url: str, token: str, session=None):
        import requests
        self.base = instance_url.rstrip("/")
        self.s = session or requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})

    def query(self, soql: str):
        url = f"{self.base}/services/data/{API}/query"
        params = {"q": soql}
        while url:
            r = self.s.get(url, params=params, timeout=60)
            r.raise_for_status()
            body = r.json()
            yield from body["records"]
            url = f"{self.base}{body['nextRecordsUrl']}" if body.get("nextRecordsUrl") else None
            params = None

    def patch(self, obj: str, record_id: str, fields: dict):
        r = self.s.patch(f"{self.base}/services/data/{API}/sobjects/{obj}/{record_id}", json=fields, timeout=60)
        if r.status_code not in (200, 204):
            raise RuntimeError(f"Salesforce {r.status_code}: {r.text[:300]}")


def _terr(rec, field):
    """Territory key from the record itself (Account) or from its parent Account."""
    if field in rec:
        return rec[field]
    return (rec.get("Account") or {}).get(field)


def ingest(conn, sf: Salesforce, since: str, territory_field: str = "EA_Territory_Key__c") -> int:
    total = 0
    for subject_type, q in QUERIES.items():
        rows = [{"subject_type": subject_type, "subject_id": rec["Id"], "display_name": rec.get("Name"),
                 "owner_external_id": rec.get("OwnerId"), "territory_key": _terr(rec, territory_field)}
                for rec in sf.query(q.format(terr=territory_field, since=since))]
        total += upsert_subjects(conn, "salesforce", rows)
    return total


def send_change(sf: Salesforce):
    def send(c):
        sf.patch(c["object_name"], c["record_id"],
                 {c["field"]: c["value"], "EA_Decision_Id__c": str(c["decision_id"])})
    return send


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["ingest", "writeback"])
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--since", default="1970-01-01T00:00:00Z")
    ap.add_argument("--territory-field", default="EA_Territory_Key__c")
    a = ap.parse_args()
    sf = Salesforce(os.environ["SF_INSTANCE_URL"], os.environ["SF_ACCESS_TOKEN"])
    with psycopg.connect(a.dsn) as conn:
        if a.command == "ingest":
            print({"upserted": ingest(conn, sf, a.since, a.territory_field)})
        else:
            print(writeback(conn, "salesforce", send_change(sf)))


if __name__ == "__main__":
    main()
