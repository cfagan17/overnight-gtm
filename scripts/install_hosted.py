#!/usr/bin/env python3
"""Install earned-autonomy on a real Supabase project: Atomic CRM's schema, then db/migrations,
optionally the Northwind demo data.

  python scripts/install_hosted.py --dsn "$SUPABASE_DB_URL" [--seed] [--reset --yes-wipe-public-schema]

--dsn     The Session pooler connection string from the Supabase dashboard (Connect).
--seed    Load db/seed/seed.sql (fictional company "Northwind Data", with demo users that cannot sign in).
--reset   DESTRUCTIVE. Drops the public schema, the earned-autonomy schemas, every auth user and the
          migration history, then installs fresh. Only for a project you are happy to wipe.

Unlike scripts/build_db.py this never creates or drops databases and never loads the test shim:
Supabase already provides everything the shim fakes.
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import sys

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
ATOMIC = sorted((ROOT / "vendor" / "atomic-crm" / "schemas").glob("0*.sql"))
MIGRATIONS = sorted((ROOT / "db" / "migrations").glob("0*.sql"))
SEED = ROOT / "db" / "seed" / "seed.sql"

RESET = """
drop schema if exists public cascade;
drop schema if exists ea_private cascade;
create schema public;
grant usage on schema public to postgres, anon, authenticated, service_role;
grant all on schema public to postgres, service_role;
alter default privileges in schema public grant all on tables to postgres, anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to postgres, anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to postgres, anon, authenticated, service_role;
delete from auth.users;
delete from supabase_migrations.schema_migrations;
"""


def run(conn: psycopg.Connection, label: str, sql: str) -> None:
    try:
        conn.execute(sql)
    except Exception as exc:
        raise SystemExit(f"FAILED in {label}: {exc}")
    print(f"ok  {label}")


def record(conn: psycopg.Connection, files: list[pathlib.Path]) -> None:
    """Record what was applied in Supabase's migration history, so `supabase db push` lines up later."""
    base = datetime.datetime.now(datetime.timezone.utc)
    for i, f in enumerate(files):
        version = (base + datetime.timedelta(seconds=i)).strftime("%Y%m%d%H%M%S")
        conn.execute("insert into supabase_migrations.schema_migrations (version, name, statements) values (%s, %s, %s)",
                     (version, f.stem, [f.read_text()]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--yes-wipe-public-schema", action="store_true")
    a = ap.parse_args()
    if a.reset and not a.yes_wipe_public_schema:
        sys.exit("--reset wipes the public schema and every auth user. Add --yes-wipe-public-schema to confirm.")
    with psycopg.connect(a.dsn, autocommit=True) as conn:
        print(conn.execute("select version()").fetchone()[0])
        if a.reset:
            run(conn, "reset", RESET)
        for f in ATOMIC + MIGRATIONS:
            run(conn, str(f.relative_to(ROOT)), f.read_text())
        record(conn, ATOMIC + MIGRATIONS)
        if a.seed:
            run(conn, str(SEED.relative_to(ROOT)), SEED.read_text())
        conn.execute("notify pgrst, 'reload schema'")
    print("done")


if __name__ == "__main__":
    main()
