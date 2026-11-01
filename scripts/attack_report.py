#!/usr/bin/env python3
"""Run the shared attacks against stock Atomic CRM and against the hardened schema,
and write docs/attack-report.md with the before and after.

  python scripts/attack_report.py [--dsn ADMIN_DSN]
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import sys

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))
from attacks import ATTACKS, run_attack  # noqa: E402
from build_db import build, run_file  # noqa: E402
from helpers import ADMIN_DSN  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=ADMIN_DSN)
    a = ap.parse_args()

    stock_dsn = build(a.dsn, "ea_report_stock", stock_atomic=True)
    with psycopg.connect(stock_dsn, autocommit=True) as c:
        run_file(c, ROOT / "db" / "seed" / "seed_stock_atomic.sql")
    hard_dsn = build(a.dsn, "ea_report_hardened", seed=True)

    results = []
    with psycopg.connect(stock_dsn) as s, psycopg.connect(hard_dsn) as h:
        for atk in ATTACKS:
            sb, sd = run_attack(s, atk)
            hb, hd = run_attack(h, atk)
            results.append((atk, sb, sd, hb, hd))

    pin = (ROOT / "vendor" / "atomic-crm" / "PINNED_COMMIT").read_text().split()[0][:10]
    lines = [
        "# Attack report",
        "",
        f"Generated {datetime.date.today().isoformat()} by `scripts/attack_report.py`. "
        f"Stock schema: Atomic CRM at commit `{pin}`. Hardened: the same schema plus `db/migrations`.",
        "",
        "Each row is one attempt by one signed-in user (or a signed-out visitor) against a record they should not "
        "reach. **Blocked** means the database refused it or it touched no target rows. "
        "Run on Postgres 16 with `db/test-shim/supabase_shim.sql` standing in for Supabase's auth layer.",
        "",
        "| Attempt | Actor | Stock Atomic | Hardened |",
        "| --- | --- | --- | --- |",
    ]
    for atk, sb, sd, hb, hd in results:
        lines.append(f"| {atk.name} | {atk.actor_label} | {'Blocked' if sb else '**Allowed**'} ({sd}) | "
                     f"{'Blocked' if hb else '**Allowed**'} ({hd}) |")
    stock_allowed = sum(1 for r in results if not r[1])
    hard_allowed = sum(1 for r in results if not r[3])
    lines += ["", f"Stock Atomic allowed {stock_allowed} of {len(results)} attempts. "
                  f"The hardened schema allowed {hard_allowed}.", "",
              "Stock Atomic is a good template that is honest about its scope: it is built for a small team "
              "where everyone may see and change everything. The point of this report is what changes when "
              "that assumption stops holding, and when AI agents connect as users.", ""]
    # Run the standalone audit tool on both databases and keep its reports next to this one.
    sys.path.insert(0, str(ROOT / "tools" / "rls-audit"))
    import json
    import rls_audit
    probe = json.loads((ROOT / "tools/rls-audit/probe.northwind.json").read_text())
    for label, dsn_ in (("stock-atomic", stock_dsn), ("hardened", hard_dsn)):
        args = ["--dsn", dsn_, "--probe", str(ROOT / "tools/rls-audit/probe.northwind.json"),
                "--out", str(ROOT / "docs" / f"rls-audit-{label}.md")]
        if label == "hardened":
            args += ["--accept", str(ROOT / "tools/rls-audit/accepted.northwind.json")]
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            rls_audit.main(args)
    lines += ["See also `docs/rls-audit-stock-atomic.md` and `docs/rls-audit-hardened.md`, produced by "
              "`tools/rls-audit` on the same two databases.", ""]
    out = ROOT / "docs" / "attack-report.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    return 0 if hard_allowed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
