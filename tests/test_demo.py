"""The demo data loads on top of the seed, and leaves a sensible review queue for each person."""
import json
import pathlib
import subprocess
import sys

import psycopg

from helpers import ADMIN_DSN, ANA, CY, OWNER, build

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_demo_history_loads_and_each_person_has_a_queue():
    dsn = build(ADMIN_DSN, "ea_test_demo", seed=True)
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute((ROOT / "examples/demo/acme_signals.sql").read_text())
    subprocess.run([sys.executable, str(ROOT / "scripts/demo_history.py"), "--dsn", dsn], check=True, capture_output=True)
    with psycopg.connect(dsn) as c:
        assert c.execute("select count(*) from public.runs").fetchone()[0] > 200
        assert c.execute("select count(*) from public.loop_prompts where status = 'approved'").fetchone()[0] == 12
        for who in (ANA, CY, OWNER):
            with c.transaction(force_rollback=True):
                c.execute("set local role authenticated")
                c.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": who, "role": "authenticated"}),))
                assert c.execute("select count(*) from public.review_queue()").fetchone()[0] > 0, who
