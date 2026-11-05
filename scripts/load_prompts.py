#!/usr/bin/env python3
"""Load agents/loops/*/prompt.md into loop_prompts as approved version 1 (first install only).

  python scripts/load_prompts.py --dsn "$DATABASE_URL" --owner-uid <owner auth uuid>

After this, prompts change only through propose_prompt_version and approve_prompt (the console's
prompt editor calls these). The files stay as the starting versions for new installs.
"""
import argparse
import pathlib

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(conn, owner_uid: str) -> int:
    n = 0
    for d in sorted(p for p in (ROOT / "agents" / "loops").iterdir() if p.is_dir()):
        cur = conn.execute("insert into public.loop_prompts (\"loop\", version, body, note, status, proposed_by, approved_by, approved_at) "
                           "values (%s, 1, %s, 'Starting version from the repo', 'approved', %s, %s, now()) on conflict do nothing",
                           (d.name, (d / "prompt.md").read_text(), owner_uid, owner_uid))
        n += cur.rowcount
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--owner-uid", required=True)
    a = ap.parse_args()
    with psycopg.connect(a.dsn) as c:
        print("loaded", load(c, a.owner_uid), "prompts")
