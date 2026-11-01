#!/usr/bin/env python3
"""Partner intelligence on public data.

Loads a public snapshot of Supabase's integration listings as weak evidence (kind
web_page) on partner subjects, then runs the partner_intelligence loop in ecosystem-scan
mode with a live model.

  python examples/partner-intelligence-public/run.py --dsn "$DATABASE_URL" --model <anthropic model id>
  python examples/partner-intelligence-public/run.py --dsn "$DATABASE_URL" --load-only

Nothing here is Supabase's internal data, and the database used is the fictional
Northwind demo. The point is to show the loop working on real public inputs: listings
are weak evidence, so a good run proposes questions and candidates to investigate, not
conclusions. No output from this script is checked into the repo; run it yourself.
"""
import argparse
import json
import pathlib
import re
import sys

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agents" / "runtime"))
from runner import AnthropicClient, DbTransport, run_loop  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
SNAPSHOT = HERE / "supabase-integrations-2026-11-01.json"
OWNER = "00000000-0000-0000-0000-000000000001"


def slug(name: str) -> str:
    return "public:" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load(dsn: str) -> int:
    snap = json.loads(SNAPSHOT.read_text())
    n = 0
    with psycopg.connect(dsn) as c, c.transaction():
        c.execute("set local role authenticated")
        c.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": OWNER, "role": "authenticated"}),))
        for row in snap["listings"]:
            claim = f"{row['partner']} is listed as a {row['category']} integration" + (" (featured)" if row["featured"] else "")
            c.execute("select public.record_evidence(null, 'partner', %s, 'web_page', %s, %s, %s::timestamptz)",
                      (slug(row["partner"]), claim, snap["source"], snap["captured_on"] + "T00:00:00Z"))
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--model")
    ap.add_argument("--load-only", action="store_true")
    a = ap.parse_args()
    print({"evidence_rows": load(a.dsn)})
    if a.load_only:
        return
    snap = json.loads(SNAPSHOT.read_text())
    with psycopg.connect(a.dsn) as c:
        agent_id = c.execute("select id from public.agent_definitions where name = 'partner-intelligence'").fetchone()[0]
    uid = f"00000000-0000-0000-0000-0000000001{agent_id:02d}"
    loop_input = {"scan": "ecosystem", "ecosystem_snapshot": snap,
                  "subjects": sorted({slug(r["partner"]) for r in snap["listings"]}),
                  "note": "Evidence on each subject is already recorded; search it before proposing."}
    out = run_loop("partner_intelligence", DbTransport(a.dsn, uid), AnthropicClient(a.model), loop_input,
                   transcripts=ROOT / "runs")
    print(json.dumps({k: v for k, v in out.items() if k != "events"}, indent=2))


if __name__ == "__main__":
    main()
