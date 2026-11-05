#!/usr/bin/env python3
"""Install Overnight on a real Supabase project: Atomic CRM's schema, then db/migrations,
optionally the Northwind demo data.

  python scripts/install_hosted.py --dsn "$SUPABASE_DB_URL" [--seed] [--reset --yes-wipe-public-schema]

--dsn     The Session pooler connection string from the Supabase dashboard (Connect).
--seed    Load db/seed/seed.sql (fictional company "Northwind Data", with demo users that cannot sign in).
--reset   DESTRUCTIVE. Drops the public schema, the Overnight schemas, every auth user and the
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
DEMO = ROOT / "examples" / "demo" / "acme_signals.sql"

RESET = """
drop schema if exists public cascade;
drop schema if exists ea_private cascade;
create schema public;
grant usage on schema public to postgres, anon, authenticated, service_role;
grant all on schema public to postgres, service_role;
alter default privileges in schema public grant all on tables to postgres, anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to postgres, anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to postgres, anon, authenticated, service_role;
drop policy if exists "Attachments 1mt4rzk_0" on storage.objects;
drop policy if exists "Attachments 1mt4rzk_1" on storage.objects;
drop policy if exists "Attachments 1mt4rzk_3" on storage.objects;
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
    ap.add_argument("--drop-schema", action="append", default=[], help="with --reset: also drop this schema (repeatable)")
    ap.add_argument("--demo", action="store_true", help="also load the demo signals and two months of demo history (needs --seed)")
    ap.add_argument("--demo-logins", action="store_true", help="with --demo: let the demo people sign in (public demo console)")
    a = ap.parse_args()
    if a.reset and not a.yes_wipe_public_schema:
        sys.exit("--reset wipes the public schema and every auth user. Add --yes-wipe-public-schema to confirm.")
    with psycopg.connect(a.dsn, autocommit=True) as conn:
        print(conn.execute("select version()").fetchone()[0])
        if a.reset:
            for name in a.drop_schema:
                run(conn, f"drop schema {name}", f'drop schema if exists "{name}" cascade;')
            run(conn, "reset", RESET)
            # Keep any schema the API is configured to expose, or PostgREST cannot load its schema cache.
            exposed = conn.execute("select string_agg(c, ',') from pg_roles r, unnest(r.rolconfig) c "
                                   "where r.rolname = 'authenticator' and c like 'pgrst.db_schemas=%'").fetchone()[0] or ""
            for name in a.drop_schema:
                if name in [x.strip() for x in exposed.split("=", 1)[-1].split(",")]:
                    run(conn, f"recreate empty exposed schema {name}",
                        f'create schema if not exists "{name}"; grant usage on schema "{name}" to anon, authenticated, service_role;')
        for f in ATOMIC + MIGRATIONS:
            run(conn, str(f.relative_to(ROOT)), f.read_text())
        record(conn, ATOMIC + MIGRATIONS)
        if a.seed:
            run(conn, str(SEED.relative_to(ROOT)), SEED.read_text())
        if a.demo:
            run(conn, str(DEMO.relative_to(ROOT)), DEMO.read_text())
            sys.path.insert(0, str(ROOT / "scripts"))
            import demo_history
            demo_history.build(conn)
            print("ok  scripts/demo_history.py")
            if a.demo_logins:
                demo_history.set_passwords(conn)
                print(f"ok  demo sign-ins, password: {demo_history.DEMO_PASSWORD}")
        conn.execute("notify pgrst, 'reload schema'")
    print("done")


if __name__ == "__main__":
    main()
