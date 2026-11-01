#!/usr/bin/env python3
"""rls-audit: check a Supabase (or any Postgres) project for row-level security gaps
that matter once AI agents connect as users.

Static checks read the catalog only and change nothing:

  python rls_audit.py --dsn "$DATABASE_URL"

Probes act as real users inside transactions that are always rolled back. They still
fire triggers (which may call webhooks), so run them on a Supabase branch or a copy:

  python rls_audit.py --dsn "$BRANCH_DATABASE_URL" --probe probe.json

probe.json:
  {
    "actors": [{"label": "Rep A", "sub": "<auth user uuid>"}, {"label": "Agent", "sub": "<uuid>"}],
    "owner_columns": ["sales_id", "owner_id", "user_id"],
    "owner_value_sql": "select id from public.sales where user_id = %(sub)s"
  }

owner_value_sql returns the value an actor's own rows carry in the owner column (for
Atomic CRM that is the sales id; for tables keyed by auth user it is the uuid itself,
so use "select %(sub)s::uuid"). Exit code 2 when any HIGH finding is present.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass

import psycopg

EXPOSED_DEFAULT = ["public"]
API_ROLES = ("anon", "authenticated")


@dataclass
class Finding:
    severity: str      # HIGH, MEDIUM, LOW
    check: str
    object: str
    detail: str
    fix: str


def q(conn, sql, params=None):
    return conn.execute(sql, params).fetchall()


def check_rls_disabled(conn, schemas):
    rows = q(conn, """
      select n.nspname || '.' || c.relname
      from pg_class c join pg_namespace n on n.oid = c.relnamespace
      where c.relkind in ('r','p') and n.nspname = any(%s) and not c.relrowsecurity
        and (has_table_privilege('anon', c.oid, 'select') or has_table_privilege('authenticated', c.oid, 'select'))
      order by 1""", (schemas,))
    return [Finding("HIGH", "rls_disabled", r[0], "Row-level security is off and API roles can read the table.",
                    "alter table ... enable row level security; then add policies.") for r in rows]


def check_true_policies(conn, schemas):
    out = []
    rows = q(conn, """
      select schemaname || '.' || tablename, policyname, cmd, roles::text[], coalesce(qual, ''), coalesce(with_check, '')
      from pg_policies where schemaname = any(%s) order by 1, 2""", (schemas,))
    owner_cols = {r[0] for r in q(conn, """
      select table_schema || '.' || table_name from information_schema.columns
      where table_schema = any(%s) and column_name in ('sales_id','owner_id','user_id','created_by','account_owner_id')""", (schemas,))}
    for table, name, cmd, roles, qual, check in rows:
        applies = any(r in ("public", "anon", "authenticated") for r in roles)
        if not applies:
            continue
        is_true = lambda s: s.strip().lower() in ("true", "(true)")  # noqa: E731
        if cmd in ("INSERT", "UPDATE", "DELETE", "ALL") and (is_true(qual) or is_true(check)):
            out.append(Finding("HIGH", "write_policy_true", f"{table} / {name}",
                               f"{cmd} policy is unconditional for {', '.join(roles)}: any signed-in user (or agent) can change any row.",
                               "Scope the policy to the row owner, the owner's managers, or a role; keep agents off direct writes."))
        elif cmd == "SELECT" and is_true(qual) and table in owner_cols:
            out.append(Finding("MEDIUM", "read_policy_true_on_owned_table", f"{table} / {name}",
                               "Table has an owner column but every signed-in user can read every row.",
                               "Decide whether visibility should follow ownership, team or territory."))
        if "public" in roles:
            out.append(Finding("LOW", "policy_applies_to_public", f"{table} / {name}",
                               "Policy applies to every role, including anon.", "Name the roles: to authenticated."))
    return out


def check_anon_grants(conn, schemas):
    rows = q(conn, """
      select n.nspname || '.' || c.relname,
             string_agg(distinct p.privilege_type, ',' order by p.privilege_type)
      from pg_class c join pg_namespace n on n.oid = c.relnamespace
      join information_schema.role_table_grants p on p.table_schema = n.nspname and p.table_name = c.relname
      where c.relkind in ('r','p') and n.nspname = any(%s) and p.grantee = 'anon'
      group by 1 order by 1""", (schemas,))
    return [Finding("MEDIUM", "anon_table_grants", r[0], f"anon holds {r[1]}. Only RLS stands between signed-out callers and the data.",
                    "revoke all on ... from anon; grant back only what a signed-out page needs.") for r in rows]


def check_definer_functions(conn, schemas):
    out = []
    rows = q(conn, """
      select p.oid::regprocedure::text, coalesce(array_to_string(p.proconfig, ','), ''),
             has_function_privilege('anon', p.oid, 'execute'),
             has_function_privilege('authenticated', p.oid, 'execute')
      from pg_proc p join pg_namespace n on n.oid = p.pronamespace
      where p.prosecdef and n.nspname = any(%s)
        and p.prorettype <> 'trigger'::regtype   -- trigger functions cannot be called through the API
      order by 1""", (schemas,))
    for sig, config, anon_exec, auth_exec in rows:
        if "search_path" not in config:
            out.append(Finding("HIGH", "definer_without_search_path", sig,
                               "SECURITY DEFINER function without a fixed search_path can be hijacked by objects in another schema.",
                               "alter function ... set search_path = '';  and schema-qualify every name inside."))
        if anon_exec:
            out.append(Finding("MEDIUM", "definer_callable_by_anon", sig,
                               "Signed-out callers can run this function with its owner's rights.",
                               "revoke execute on function ... from anon, public; unless the login flow needs it."))
        elif auth_exec:
            out.append(Finding("LOW", "definer_callable_by_authenticated", sig,
                               "Runs with its owner's rights for any signed-in user. Check that it verifies the caller itself.",
                               "Confirm the function checks auth.uid() and the caller's role before acting."))
    return out


def check_views(conn, schemas):
    rows = q(conn, """
      select n.nspname || '.' || c.relname, coalesce(array_to_string(c.reloptions, ','), '')
      from pg_class c join pg_namespace n on n.oid = c.relnamespace
      where c.relkind = 'v' and n.nspname = any(%s)
        and (has_table_privilege('anon', c.oid, 'select') or has_table_privilege('authenticated', c.oid, 'select'))
      order by 1""", (schemas,))
    return [Finding("HIGH", "view_bypasses_rls", r[0],
                    "View runs with its owner's rights, so row-level security on the underlying tables does not apply.",
                    "create or replace view ... with (security_invoker = on) ...  (Postgres 15+), or confirm it exposes nothing private.")
            for r in rows if "security_invoker=on" not in r[1].replace(" ", "").lower()
            and "security_invoker=true" not in r[1].replace(" ", "").lower()]


def probe(conn, schemas, cfg):
    out = []
    owner_cols = cfg.get("owner_columns", ["sales_id", "owner_id", "user_id"])
    tables = q(conn, """
      select table_schema, table_name, column_name from information_schema.columns c
      join pg_class k on k.relname = c.table_name
      join pg_namespace n on n.oid = k.relnamespace and n.nspname = c.table_schema
      where c.table_schema = any(%s) and c.column_name = any(%s) and k.relkind in ('r','p')
      order by 1, 2""", (schemas, owner_cols))
    for actor in cfg["actors"]:
        sub = actor["sub"]
        mine = q(conn, cfg.get("owner_value_sql", "select %(sub)s::uuid"), {"sub": sub})
        my_value = mine[0][0] if mine else None
        for schema, table, col in tables:
            fq = f'"{schema}"."{table}"'
            with conn.transaction(force_rollback=True):
                conn.execute("set local role authenticated")
                conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": sub, "role": "authenticated"}),))
                try:
                    with conn.transaction():
                        others = conn.execute(f'select count(*) from {fq} where "{col}" is distinct from %s', (my_value,)).fetchone()[0]
                except psycopg.Error:
                    continue
                if others:
                    out.append(Finding("MEDIUM", "probe_reads_others_rows", f"{schema}.{table}",
                                       f"{actor['label']} can read {others} rows owned by someone else (by {col}).",
                                       "Confirm this visibility is intended for this role."))
                try:
                    with conn.transaction():
                        cur = conn.execute(f'update {fq} set "{col}" = "{col}" where ctid = (select ctid from {fq} '
                                           f'where "{col}" is distinct from %s limit 1)', (my_value,))
                        changed = cur.rowcount
                except psycopg.Error:
                    changed = 0
                if changed:
                    out.append(Finding("HIGH", "probe_writes_others_rows", f"{schema}.{table}",
                                       f"{actor['label']} can update a row owned by someone else (by {col}). Tested with a no-op update, rolled back.",
                                       "Restrict update policies to the owner, their managers, or specific roles."))
    return out


def render(findings, dsn_label):
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    findings = sorted(findings, key=lambda f: (order[f.severity], f.check, f.object))
    counts = {s: sum(1 for f in findings if f.severity == s) for s in order}
    lines = [f"# rls-audit report", "", f"Target: `{dsn_label}`", "",
             f"**{counts['HIGH']} high, {counts['MEDIUM']} medium, {counts['LOW']} low.**", ""]
    if not findings:
        lines.append("No findings.")
    else:
        lines += ["| Severity | Check | Object | What it means | Fix |", "| --- | --- | --- | --- | --- |"]
        for f in findings:
            lines.append(f"| {f.severity} | {f.check} | `{f.object}` | {f.detail} | {f.fix} |")
    lines += ["", "Static checks read the catalog only. Probe results, when present, came from rolled-back transactions.", ""]
    return "\n".join(lines), counts


def run(dsn, schemas, probe_cfg=None):
    with psycopg.connect(dsn) as conn:
        findings = (check_rls_disabled(conn, schemas) + check_true_policies(conn, schemas) + check_anon_grants(conn, schemas)
                    + check_definer_functions(conn, schemas) + check_views(conn, schemas))
        if probe_cfg:
            findings += probe(conn, schemas, probe_cfg)
        conn.rollback()
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", required=True, help="Postgres connection string (Supabase: Project Settings > Database)")
    ap.add_argument("--schemas", default=",".join(EXPOSED_DEFAULT), help="comma-separated schemas exposed through the API")
    ap.add_argument("--probe", help="probe config JSON (runs as users in rolled-back transactions)")
    ap.add_argument("--accept", help="JSON list of {check, object, reason} findings you have reviewed and accept")
    ap.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    ap.add_argument("--out", help="write the report to a file")
    a = ap.parse_args(argv)
    cfg = json.load(open(a.probe)) if a.probe else None
    if cfg:
        print("rls-audit: probes fire triggers inside rolled-back transactions; use a branch or a copy.", file=sys.stderr)
    findings = run(a.dsn, a.schemas.split(","), cfg)
    accepted = []
    if a.accept:
        rules = json.load(open(a.accept))
        keep = []
        for f in findings:
            rule = next((r for r in rules if r["check"] == f.check and r["object"] == f.object), None)
            (accepted if rule else keep).append((f, rule["reason"]) if rule else f)
        findings = keep
    label = a.dsn.split("@")[-1]
    if a.json:
        text = json.dumps([asdict(f) for f in findings], indent=2)
        counts = {s: sum(1 for f in findings if f.severity == s) for s in ("HIGH", "MEDIUM", "LOW")}
    else:
        text, counts = render(findings, label)
        if accepted:
            text += "\n## Accepted after review\n\n| Check | Object | Reason |\n| --- | --- | --- |\n"
            text += "\n".join(f"| {f.check} | `{f.object}` | {why} |" for f, why in accepted) + "\n"
    if a.out:
        open(a.out, "w").write(text)
    print(text)
    return 2 if counts["HIGH"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
