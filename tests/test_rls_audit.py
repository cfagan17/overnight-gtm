"""The standalone audit tool finds the stock gaps and passes the hardened schema."""
import json
import pathlib
import sys

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "rls-audit"))
import rls_audit  # noqa: E402
from helpers import ADMIN_DSN, build  # noqa: E402
from build_db import run_file  # noqa: E402

PROBE = json.loads((ROOT / "tools/rls-audit/probe.northwind.json").read_text())
ACCEPT = json.loads((ROOT / "tools/rls-audit/accepted.northwind.json").read_text())


def severities(findings, accept=()):
    keep = [f for f in findings if not any(a["check"] == f.check and a["object"] == f.object for a in accept)]
    return {s: sum(1 for f in keep if f.severity == s) for s in ("HIGH", "MEDIUM", "LOW")}, keep


def test_stock_atomic_has_high_findings():
    dsn = build(ADMIN_DSN, "ea_audit_stock", stock_atomic=True)
    with psycopg.connect(dsn, autocommit=True) as c:
        run_file(c, ROOT / "db/seed/seed_stock_atomic.sql")
    counts, keep = severities(rls_audit.run(dsn, ["public"], PROBE))
    checks = {f.check for f in keep if f.severity == "HIGH"}
    assert {"write_policy_true", "probe_writes_others_rows"} <= checks
    assert counts["HIGH"] >= 20


def test_hardened_has_no_high_or_medium_after_review(dsn):
    counts, keep = severities(rls_audit.run(dsn, ["public"], PROBE), ACCEPT)
    assert counts["HIGH"] == 0 and counts["MEDIUM"] == 0, [f for f in keep if f.severity != "LOW"]
