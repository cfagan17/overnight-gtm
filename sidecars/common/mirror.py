"""Shared sidecar plumbing: upsert the visibility mirror and run the writeback loop.

Both sidecars connect to Postgres as the service role (a direct connection string or
the service key). They never hold customer data beyond ids, names, owners and the
territory key needed for visibility.
"""
from __future__ import annotations

import json

import psycopg


def upsert_subjects(conn: psycopg.Connection, system: str, rows: list[dict]) -> int:
    """rows: {subject_type, subject_id, display_name, owner_external_id, territory_key}"""
    n = 0
    for r in rows:
        conn.execute("""
          insert into public.external_subjects (subject_type, subject_id, source_system, display_name, owner_sales_id, territory_id, synced_at)
          values (%(t)s, %(id)s, %(sys)s, %(name)s,
                  (select sales_id from public.sidecar_user_map where source_system = %(sys)s and external_user_id = %(owner)s),
                  (select territory_id from public.sidecar_territory_map where source_system = %(sys)s and external_key = %(terr)s),
                  now())
          on conflict (subject_type, subject_id) do update set display_name = excluded.display_name,
            owner_sales_id = excluded.owner_sales_id, territory_id = excluded.territory_id, synced_at = now()""",
                     {"t": r["subject_type"], "id": r["subject_id"], "sys": system, "name": r.get("display_name"),
                      "owner": r.get("owner_external_id"), "terr": r.get("territory_key")})
        n += 1
    return n


def writeback(conn: psycopg.Connection, system: str, send) -> dict:
    """Claim approved changes and send each with send(change) -> None (raise on failure)."""
    sent = failed = 0
    with conn.transaction():
        conn.execute("set local role service_role")
        conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": "service_role"}),))
        changes = conn.execute("select to_jsonb(c) from public.claim_outbound_changes(%s) c", (system,)).fetchall()
        for (c,) in changes:
            try:
                send(c)
                conn.execute("select public.report_outbound_change(%s, true)", (c["id"],))
                sent += 1
            except Exception as exc:  # report the failure on the change and keep going
                conn.execute("select public.report_outbound_change(%s, false, %s)", (c["id"], str(exc)[:500]))
                failed += 1
    return {"sent": sent, "failed": failed}
