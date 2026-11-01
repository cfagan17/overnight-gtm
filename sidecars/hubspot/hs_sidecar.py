#!/usr/bin/env python3
"""HubSpot sidecar: mirror ids/owners for visibility, and write approved agent changes back.

  python sidecars/hubspot/hs_sidecar.py ingest --dsn "$DATABASE_URL" --since 2026-10-01T00:00:00Z
  python sidecars/hubspot/hs_sidecar.py writeback --dsn "$DATABASE_URL"

HubSpot auth: HUBSPOT_TOKEN from a private app with read on companies, contacts and
deals, and write on the allowlisted deal and contact properties only. Create the custom
property `ea_decision_id` (single-line text) on deals and contacts first (properties.json).

STATUS: written against the HubSpot CRM v3 API and tested here with a fake HTTP session
only. It has not been run against a real portal.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

import psycopg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from sidecars.common.mirror import upsert_subjects, writeback  # noqa: E402

BASE = "https://api.hubapi.com"
OBJECTS = {"companies": "company", "deals": "deal", "contacts": "contact"}
NAME_PROP = {"companies": "name", "deals": "dealname", "contacts": "lastname"}


class HubSpot:
    def __init__(self, token: str, session=None, base: str = BASE):
        import requests
        self.base = base
        self.s = session or requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})

    def search_modified(self, obj: str, since_ms: int, props: list[str]):
        after = None
        while True:
            body = {"filterGroups": [{"filters": [{"propertyName": "hs_lastmodifieddate", "operator": "GT", "value": since_ms}]}],
                    "properties": props, "limit": 100}
            if after:
                body["after"] = after
            r = self.s.post(f"{self.base}/crm/v3/objects/{obj}/search", json=body, timeout=60)
            r.raise_for_status()
            data = r.json()
            yield from data.get("results", [])
            after = (data.get("paging") or {}).get("next", {}).get("after")
            if not after:
                break

    def patch(self, obj: str, record_id: str, props: dict):
        r = self.s.patch(f"{self.base}/crm/v3/objects/{obj}/{record_id}", json={"properties": props}, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"HubSpot {r.status_code}: {r.text[:300]}")


def ingest(conn, hs: HubSpot, since_ms: int, territory_prop: str = "ea_territory_key") -> int:
    total = 0
    for obj, subject_type in OBJECTS.items():
        rows = [{"subject_type": subject_type, "subject_id": rec["id"],
                 "display_name": rec["properties"].get(NAME_PROP[obj]),
                 "owner_external_id": rec["properties"].get("hubspot_owner_id"),
                 "territory_key": rec["properties"].get(territory_prop)}
                for rec in hs.search_modified(obj, since_ms, [NAME_PROP[obj], "hubspot_owner_id", territory_prop])]
        total += upsert_subjects(conn, "hubspot", rows)
    return total


def send_change(hs: HubSpot):
    def send(c):
        hs.patch(c["object_name"], c["record_id"], {c["field"]: c["value"], "ea_decision_id": str(c["decision_id"])})
    return send


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["ingest", "writeback"])
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--since-ms", type=int, default=0)
    a = ap.parse_args()
    hs = HubSpot(os.environ["HUBSPOT_TOKEN"])
    with psycopg.connect(a.dsn) as conn:
        if a.command == "ingest":
            print({"upserted": ingest(conn, hs, a.since_ms)})
        else:
            print(writeback(conn, "hubspot", send_change(hs)))


if __name__ == "__main__":
    main()
