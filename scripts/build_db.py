#!/usr/bin/env python3
"""Build a test database: Supabase shim, Atomic CRM's real schema, then our migrations.

Usage:
  python scripts/build_db.py --dsn postgresql://postgres@localhost:54329/postgres --name ea_test [--stock-atomic] [--seed]

--stock-atomic stops after Atomic's own schema, which is how the attack suite measures
the "before" picture. Never point this at a real Supabase project: it drops and
recreates the named database.
"""
from __future__ import annotations

import argparse
import pathlib
import re

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHIM = ROOT / "db" / "test-shim" / "supabase_shim.sql"
ATOMIC = sorted((ROOT / "vendor" / "atomic-crm" / "schemas").glob("0*.sql"))
MIGRATIONS = sorted((ROOT / "db" / "migrations").glob("0*.sql"))
SEED = ROOT / "db" / "seed" / "seed.sql"

# The "http" extension exists on Supabase but not on plain Postgres. The shim provides
# stubs for the functions Atomic calls, so the extension line is skipped in tests only.
HTTP_EXT = re.compile(r'create extension if not exists "http"[^;]*;', re.I)


def run_file(conn: psycopg.Connection, path: pathlib.Path) -> None:
    sql = path.read_text()
    if path.parent.name == "schemas":
        sql = HTTP_EXT.sub("", sql)
    try:
        conn.execute(sql)
    except Exception as exc:  # re-raise with the file name so failures are readable
        raise RuntimeError(f"{path.relative_to(ROOT)}: {exc}") from exc


def build(admin_dsn: str, name: str, stock_atomic: bool = False, seed: bool = False) -> str:
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f'drop database if exists "{name}" with (force)')
        admin.execute(f'create database "{name}"')
    dsn = re.sub(r"/[^/?]*(\?|$)", f"/{name}\\1", admin_dsn, count=1) if "/" in admin_dsn.split("@")[-1] else f"{admin_dsn}/{name}"
    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in [SHIM, *ATOMIC] + ([] if stock_atomic else MIGRATIONS):
            run_file(conn, path)
        if seed and not stock_atomic:
            run_file(conn, SEED)
    return dsn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default="postgresql://postgres@localhost:54329/postgres")
    ap.add_argument("--name", default="ea_dev")
    ap.add_argument("--stock-atomic", action="store_true")
    ap.add_argument("--seed", action="store_true")
    a = ap.parse_args()
    print(build(a.dsn, a.name, a.stock_atomic, a.seed))


if __name__ == "__main__":
    main()
