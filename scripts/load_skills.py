#!/usr/bin/env python3
"""Load agents/skills/*.md into the skills table as approved version 1 (first install only).

  python scripts/load_skills.py --dsn "$DATABASE_URL" --owner-uid <owner auth uuid>

After this, skills change only through propose_skill_version and approve_skill.
"""
import argparse
import pathlib

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
ap.add_argument("--owner-uid", required=True)
a = ap.parse_args()
with psycopg.connect(a.dsn) as c:
    for f in sorted((ROOT / "agents" / "skills").glob("*.md")):
        c.execute("insert into public.skills (name, version, body, status, proposed_by, approved_by, approved_at) "
                  "values (%s, 1, %s, 'approved', %s, %s, now()) on conflict do nothing",
                  (f.stem, f.read_text(), a.owner_uid, a.owner_uid))
        print("loaded", f.stem)
