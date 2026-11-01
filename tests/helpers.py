"""Shared test helpers: build databases, and run SQL as a given principal.

Acting as someone mirrors what Supabase's API does for a signed-in request:
`set local role authenticated` plus the JWT claims in request.jwt.claims.
"""
from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sys

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_db import build  # noqa: E402

ADMIN_DSN = os.environ.get("EA_TEST_DSN", "postgresql://postgres@/postgres?host=/tmp&port=54329")

# Seeded principals (db/seed/seed.sql)
OWNER = "00000000-0000-0000-0000-000000000001"       # Riley, RevOps, owner role
VP = "00000000-0000-0000-0000-000000000002"          # Vic, manages both regional managers
WEST_MGR = "00000000-0000-0000-0000-000000000003"    # Wen, manages Ana and Ben
EAST_MGR = "00000000-0000-0000-0000-000000000004"    # Ezra, manages Cy
ANA = "00000000-0000-0000-0000-000000000005"         # West Enterprise AE
BEN = "00000000-0000-0000-0000-000000000006"         # West Commercial AE
CY = "00000000-0000-0000-0000-000000000007"          # East AE
PAT = "00000000-0000-0000-0000-000000000008"         # Partner manager
FIN = "00000000-0000-0000-0000-000000000009"         # Read-only finance
ANON = None


def agent_uid(agent_definition_id: int) -> str:
    return f"00000000-0000-0000-0000-0000000001{agent_definition_id:02d}"


class Denied(Exception):
    """Raised when the database refused the action (permission or policy)."""


@contextlib.contextmanager
def acting_as(conn: psycopg.Connection, uid: str | None):
    """Run statements as a principal inside a transaction that is always rolled back."""
    with conn.transaction(force_rollback=True):
        if uid is None:
            conn.execute("set local role anon")
            conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": "anon"}),))
        else:
            conn.execute("set local role authenticated")
            conn.execute("select set_config('request.jwt.claims', %s, true)",
                         (json.dumps({"sub": uid, "role": "authenticated"}),))
        yield conn


def attempt(conn: psycopg.Connection, sql: str, params=None):
    """Execute inside a savepoint. Returns ('ok', rows, rowcount) or ('denied', message, 0)."""
    try:
        with conn.transaction():
            cur = conn.execute(sql, params)
            rows = cur.fetchall() if cur.description else []
            return "ok", rows, cur.rowcount
    except (psycopg.errors.InsufficientPrivilege, psycopg.errors.RaiseException) as exc:
        return "denied", str(exc).splitlines()[0], 0


def scalar(conn: psycopg.Connection, sql: str, params=None):
    return conn.execute(sql, params).fetchone()[0]


def agent_id(conn: psycopg.Connection, name: str) -> int:
    with conn.transaction():
        conn.execute("reset role")
        return scalar(conn, "select id from public.agent_definitions where name = %s", (name,))
