"""Attacks that run against BOTH a stock Atomic CRM database and the hardened one.

Each attack names an actor, the target rows (looked up as a superuser first), and the
SQL the actor tries. An attack is "blocked" when the database refuses it, or when it
touches none of the target rows.

These only use Atomic's own tables, so the same attack is meaningful on both schemas.
Hardened-only checks (agent contract, autonomy, field masking) live in test_*.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from helpers import ANA, ANON, FIN, acting_as, attempt

AGENT = "00000000-0000-0000-0000-000000000102"  # account-program agent (seed and stock seed)


@dataclass
class Attack:
    name: str
    actor_label: str
    actor: str | None
    target: str          # superuser SQL returning the target id
    sql: str             # attacker SQL; %(id)s is the target id
    kind: str            # 'read' or 'write'


ATTACKS = [
    Attack("Rep reads another territory's deal", "West AE", ANA,
           "select id from public.deals where name = 'Maple Ledger - Platform'",
           "select id, amount from public.deals where id = %(id)s", "read"),
    Attack("Rep reads another territory's contacts", "West AE", ANA,
           "select id from public.contacts where company_id = (select id from public.companies where name = 'Maple Ledger') limit 1",
           "select id, first_name, title from public.contacts where id = %(id)s", "read"),
    Attack("Rep reads another rep's call notes", "West AE", ANA,
           "select n.id from public.contact_notes n join public.contacts c on c.id = n.contact_id "
           "where c.company_id = (select id from public.companies where name = 'Maple Ledger') limit 1",
           "select id, text from public.contact_notes where id = %(id)s", "read"),
    Attack("Rep changes another rep's deal amount", "West AE", ANA,
           "select id from public.deals where name = 'Maple Ledger - Platform'",
           "update public.deals set amount = 1 where id = %(id)s", "write"),
    Attack("Rep reassigns another rep's deal to herself", "West AE", ANA,
           "select id from public.deals where name = 'Maple Ledger - Platform'",
           "update public.deals set sales_id = (select id from public.sales where user_id = auth.uid()) where id = %(id)s", "write"),
    Attack("Rep deletes another rep's deal", "West AE", ANA,
           "select id from public.deals where name = 'Maple Ledger - Platform'",
           "delete from public.deals where id = %(id)s", "write"),
    Attack("Rep deletes another rep's account (cascades to contacts and deals)", "West AE", ANA,
           "select id from public.companies where name = 'Maple Ledger'",
           "delete from public.companies where id = %(id)s", "write"),
    Attack("Rep rewrites another rep's call note", "West AE", ANA,
           "select n.id from public.contact_notes n join public.contacts c on c.id = n.contact_id "
           "where c.company_id = (select id from public.companies where name = 'Maple Ledger') limit 1",
           "update public.contact_notes set text = 'edited' where id = %(id)s", "write"),
    Attack("Rep deletes another rep's tasks", "West AE", ANA,
           "select t.id from public.tasks t join public.contacts c on c.id = t.contact_id "
           "where c.company_id = (select id from public.companies where name = 'Maple Ledger') limit 1",
           "delete from public.tasks where id = %(id)s", "write"),
    Attack("Rep adds a deal to another rep's account (inflating that territory's pipeline)", "West AE", ANA,
           "select id from public.companies where name = 'Maple Ledger'",
           "insert into public.deals (name, company_id, stage, amount, index) values ('injected', %(id)s, 'opportunity', 9999999, 0)", "write"),
    Attack("Read-only finance user changes a deal", "Read-only user", FIN,
           "select id from public.deals where name = 'Acme Orchards - Platform'",
           "update public.deals set amount = 1 where id = %(id)s", "write"),
    Attack("Agent account edits a deal stage directly, with no decision or evidence", "Agent", AGENT,
           "select id from public.deals where name = 'Acme Orchards - Platform'",
           "update public.deals set stage = 'won' where id = %(id)s", "write"),
    Attack("Agent account deletes a deal directly", "Agent", AGENT,
           "select id from public.deals where name = 'Acme Orchards - Platform'",
           "delete from public.deals where id = %(id)s", "write"),
    Attack("Agent account reads a deal outside its scope", "Agent", AGENT,
           "select id from public.deals where name = 'Maple Ledger - Platform'",
           "select id, amount from public.deals where id = %(id)s", "read"),
    Attack("Signed-out visitor reads accounts", "Signed out", ANON,
           "select id from public.companies where name = 'Acme Orchards'",
           "select id, name from public.companies where id = %(id)s", "read"),
]


def run_attack(conn, attack: Attack) -> tuple[bool, str]:
    """Returns (blocked, detail)."""
    target = conn.execute(attack.target).fetchone()
    if target is None:
        raise RuntimeError(f"no target for {attack.name}")
    params = {"id": target[0]}
    with acting_as(conn, attack.actor):
        status, rows, rowcount = attempt(conn, attack.sql, params)
    if status == "denied":
        return True, f"refused: {rows}"
    if attack.kind == "read":
        return (len(rows) == 0), ("no rows returned" if not rows else f"returned {len(rows)} row(s)")
    return (rowcount == 0), ("0 rows changed" if rowcount == 0 else f"{rowcount} row(s) changed")
