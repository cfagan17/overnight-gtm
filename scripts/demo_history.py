#!/usr/bin/env python3
"""Give the Northwind demo two months of history, so the console has something to show.

  python scripts/demo_history.py --dsn "$DSN" [--passwords]

Run after db/seed/seed.sql and examples/demo/acme_signals.sql (scripts/install_hosted.py
--seed --demo does both). Everything here is fictional and generated from a fixed random seed:
nightly and weekly runs of all twelve loops, the evidence they cited, their decisions, and how
people reviewed them; a model upgrade three weeks ago; one policy violation and the demotion
that followed; a running holdout experiment; replay scores; and a fresh review queue for this
morning.

--passwords gives each demo person a sign-in (Supabase only), for the public demo console.
The password is printed. It protects nothing but demo data, and the reset script restores it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import random
import re

import psycopg
from psycopg.types.json import Jsonb

R = random.Random(7)
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
DAY = dt.timedelta(days=1)
OLD_MODEL, NEW_MODEL, UPGRADE_DAYS_AGO = "claude-opus-5", "claude-opus-5-5", 21
DEMO_PASSWORD = "overnight-demo"
# The saved Claude run in examples/live-run was made when the Acme deal closed on this date.
# A demo install moves the deal to eight days out and shifts the dates in the saved plan to match.
LIVE_RUN_CLOSE = dt.date(2026, 11, 12)
CLOSE_IN_DAYS = 8
# Last night, each of these loops does one piece of work for every rep, so nobody's morning is empty.
EVERY_REP_LOOPS = ("deal_inspection", "conversation_capture", "outreach")

PEOPLE = {  # email -> display name
    "riley.ops@northwind.example": ("Sam", "Rivera"),
    "vic.vp@northwind.example": ("Vic", "Moreno"),
    "wen.west@northwind.example": ("Wen", "Park"),
    "ezra.east@northwind.example": ("Ezra", "Cole"),
    "ana.rep@northwind.example": ("Maya", "Chen"),
    "ben.rep@northwind.example": ("Ben", "Okafor"),
    "cy.rep@northwind.example": ("Cy", "Nakamura"),
    "pat.partners@northwind.example": ("Pat", "Quinn"),
    "fin.readonly@northwind.example": ("Morgan", "Lee"),
}
FIRST = ["Alex", "Jamie", "Taylor", "Morgan", "Riley", "Devon", "Quinn", "Avery", "Rowan", "Elena", "Marcus", "Hana",
         "Omar", "Lucia", "Theo", "Nina", "Sofia", "Kenji", "Isla", "Mateo", "Aisha", "Leo", "Zara", "Felix"]
LAST = ["Brooks", "Shah", "Lindqvist", "Okoye", "Romero", "Fischer", "Tanaka", "Haddad", "Novak", "Silva", "Ward",
        "Ibrahim", "Kowalski", "Duarte", "Byrne", "Mehta", "Larsen", "Costa", "Yilmaz", "Grant", "Moreau", "Lin"]

LOOPS = {  # loop -> (cadence in days, decisions per run, review mix accepted/edited/rejected)
    "account_program": (1, (1, 2), (0.74, 0.19, 0.07)),
    "conversation_capture": (1, (1, 3), (0.91, 0.07, 0.02)),
    "deal_inspection": (1, (1, 2), (0.68, 0.22, 0.10)),
    "outreach": (1, (1, 2), (0.84, 0.11, 0.05)),
    "post_sale_health": (2, (0, 1), (0.80, 0.12, 0.08)),
    "market_model": (3, (0, 1), (0.70, 0.20, 0.10)),
    "forecast": (7, (0, 0), (1, 0, 0)),
    "partner_intelligence": (7, (1, 1), (0.60, 0.25, 0.15)),
    "product_feedback": (7, (1, 2), (0.85, 0.10, 0.05)),
    "comp_ops": (14, (1, 2), (0.70, 0.30, 0.0)),
    "territory_capacity": (60, (1, 1), (0, 1, 0)),
    "operating_design": (30, (1, 1), (0.5, 0.5, 0)),
}
NOTES = {
    "account_program": ["Send it from me, I know their CFO.", "Too early, they just renewed.", "Lead with the security add-on, not the platform.",
                        "Right person, wrong angle. They care about cost, not speed.", "Good. Add the SE to step two."],
    "deal_inspection": ["Champion is fine, she was on PTO.", "Real risk. Booking a call with the EB.", "Close date is right, procurement is fast here.",
                        "Paper process is the risk, not the champion."],
    "conversation_capture": ["Close date is end of month, not end of quarter.", "Title is VP, not Director."],
    "outreach": ["Shorter. One ask.", "Not this week, they are in a board meeting.", "Use the case study from Cedar Health instead."],
    "post_sale_health": ["Usage dip is the holiday, not churn.", "Agree, setting up an exec sponsor call."],
    "market_model": ["Weight product telemetry higher than firmographics.", "Healthcare is not a fit yet, keep it out of the ICP."],
    "partner_intelligence": ["Harbor is already working this account.", "Good find. Intro me to their alliance lead."],
    "product_feedback": ["Merge this with the SSO theme.", "Send to the data platform PM."],
    "comp_ops": ["Split should be 70/30, the partner sourced it.", "Correct per the plan."],
    "territory_capacity": ["Keep Acme with Maya through Q1, then move it."],
    "operating_design": ["Approve, but measure for one quarter."],
}


def ago(days: float, hour: int = 2) -> dt.datetime:
    # Always draw the same three numbers, so the data does not depend on the time of day it is built.
    minute, second, back = R.randint(0, 59), R.randint(0, 59), R.uniform(1, 5)
    t = (NOW - dt.timedelta(days=days)).replace(hour=hour, minute=minute, second=second)
    return t if t < NOW - dt.timedelta(minutes=30) else NOW - dt.timedelta(hours=back)


def shift_dates(obj, delta: dt.timedelta, close: dt.date):
    """Move every date in the saved run's text by delta. Nothing else in the text changes."""
    if isinstance(obj, dict):
        return {k: shift_dates(v, delta, close) for k, v in obj.items()}
    if isinstance(obj, list):
        return [shift_dates(v, delta, close) for v in obj]
    if isinstance(obj, str):
        obj = re.sub(r"(?<!\d)20\d\d-\d\d-\d\d(?!\d)", lambda m: (dt.date.fromisoformat(m.group()) + delta).isoformat(), obj)
        return re.sub(r"(?<![\d-])%s(?![\d-])" % LIVE_RUN_CLOSE.strftime("%m-%d"), close.strftime("%m-%d"), obj)
    return obj


def pick_outcome(mix):
    x = R.random()
    return "accepted" if x < mix[0] else "edited" if x < mix[0] + mix[1] else "rejected"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--passwords", action="store_true")
    a = ap.parse_args()
    with psycopg.connect(a.dsn) as c:
        build(c)
        if a.passwords:
            set_passwords(c)
            print(f"demo sign-in password: {DEMO_PASSWORD}")
    print("demo history loaded")


def set_passwords(c: psycopg.Connection) -> None:
    c.execute("update auth.users set encrypted_password = extensions.crypt(%s, extensions.gen_salt('bf')), "
              "email_confirmed_at = coalesce(email_confirmed_at, now()), created_at = coalesce(created_at, now()), updated_at = coalesce(updated_at, now()), aud = 'authenticated', role = 'authenticated', "
              "instance_id = coalesce(instance_id, '00000000-0000-0000-0000-000000000000'), "
              "confirmation_token = coalesce(confirmation_token, ''), recovery_token = coalesce(recovery_token, ''), "
              "email_change_token_new = coalesce(email_change_token_new, ''), email_change = coalesce(email_change, ''), "
              "email_change_token_current = coalesce(email_change_token_current, ''), reauthentication_token = coalesce(reauthentication_token, ''), "
              "phone_change = coalesce(phone_change, ''), phone_change_token = coalesce(phone_change_token, '') "
              "where email like '%%@northwind.example'", (DEMO_PASSWORD,))
    # Supabase sign-in also needs an identity row per user.
    c.execute("insert into auth.identities (provider_id, user_id, identity_data, provider, last_sign_in_at, created_at, updated_at) "
              "select u.id::text, u.id, jsonb_build_object('sub', u.id::text, 'email', u.email, 'email_verified', true), 'email', now(), now(), now() "
              "from auth.users u where u.email like '%%@northwind.example' "
              "and not exists (select 1 from auth.identities i where i.user_id = u.id and i.provider = 'email')")



def demo_plan(cname, ct, sender, rep, evs):
    """A generated plan in the same shape as the real Claude run in examples/live-run."""
    e1 = evs[0]
    e2 = evs[1] if len(evs) > 1 else evs[0]
    who = ct[1] if ct else "the champion"
    title = ct[2] if ct else "their team"
    plan = {
        "why_now": [{"claim": f"{cname}'s weekly active users are climbing fast.", "evidence": [e1]}]
                   + ([{"claim": f"{who} ({title}) named a deadline on the last call.", "evidence": [e2]}] if ct else []),
        "entry_points": [{"contact_id": ct[0], "reason": f"{who} has the pain and said it on a call.", "evidence": [e2]}] if ct else [],
        "sender": {"type": sender, "reason": f"{rep} owns the relationship." if sender == "rep" else "Early stage and low risk: the agent can open, the rep takes over on reply."},
        "content": [{"step": 1, "carries": f"What their usage shows, and an offer to help {who}'s team move the rest over.", "evidence": [e1, e2] if ct else [e1]},
                    {"step": 2, "carries": "A short plan sized to their deadline, with what we will do and what they will do.", "evidence": [e2]}],
        "channel_and_sequence": [{"step": 1, "channel": "email", "purpose": f"{'%s to %s' % (rep.split()[0], who.split()[0]) if sender == 'rep' else 'Agent to ' + who.split()[0]}: open with the usage and offer help."},
                                 {"step": 2, "channel": "meeting", "purpose": "Walk through the plan and agree dates."}],
        "risks": [R.choice(["No economic buyer is named yet.", "The deadline is stated but not tied to a budget.", "Usage is concentrated in one team."])],
        "what_would_change_it": "Write a new version if usage drops, a new approver appears, or the deadline moves.",
    }
    return plan


def build(c: psycopg.Connection) -> None:
    with c.transaction():   # one transaction, also on an autocommit connection
        _build(c)


def _build(c: psycopg.Connection) -> None:
    q = lambda sql, *p: c.execute(sql, p).fetchall()
    one = lambda sql, *p: c.execute(sql, p).fetchone()[0]

    # People and contacts get real-looking names.
    for email, (fn, ln) in PEOPLE.items():
        # The name lives in auth metadata too: Atomic copies it to sales on every auth.users update.
        c.execute("update auth.users set raw_user_meta_data = coalesce(raw_user_meta_data, '{}'::jsonb) || jsonb_build_object('first_name', %s::text, 'last_name', %s::text) where email = %s", (fn, ln, email))
        c.execute("update public.sales set first_name = %s, last_name = %s where email = %s", (fn, ln, email))
    for cid, in q("select id from public.contacts where last_name like 'Contact %%' order by id"):
        c.execute("update public.contacts set first_name = %s, last_name = %s where id = %s", (R.choice(FIRST), R.choice(LAST), cid))

    uid_of_sales = dict(q("select id, user_id from public.sales"))
    owner_name = {i: f"{f} {l}" for i, f, l in q("select id, first_name, last_name from public.sales")}
    owner_uid = one("select user_id from public.sales where email = 'riley.ops@northwind.example'")
    wen_uid = one("select user_id from public.sales where email = 'wen.west@northwind.example'")
    agents = {loop: (did, uid) for did, loop, uid in q(
        "select d.id, d.\"loop\", p.user_id from public.agent_definitions d join public.principals p on p.agent_definition_id = d.id")}
    companies = q("select c.id, c.name, c.sales_id, c.territory_id from public.companies c order by c.id")
    # The Acme deal always closes about eight days out, as it did when Claude wrote the saved plan.
    acme = one("select id from public.companies where name = 'Acme Orchards'")
    acme_close = NOW.date() + DAY * CLOSE_IN_DAYS
    c.execute("update public.deals set expected_closing_date = %s where company_id = %s", (acme_close, acme))
    contacts = {}
    for ct_id, comp_id, name, title in q("select id, company_id, first_name || ' ' || last_name, title from public.contacts"):
        contacts.setdefault(comp_id, []).append((ct_id, name, title))
    deals = {comp: (did, name, stage, amount) for did, comp, name, stage, amount in q(
        "select id, company_id, name, stage, amount from public.deals")}
    partners = q("select id, name from public.partners")
    west_ent = [x for x in companies if x[3] == 2]
    by_rep = {}   # rep -> their accounts that have a deal and a contact
    for x in companies:
        if x[0] in deals and contacts.get(x[0]):
            by_rep.setdefault(x[2], []).append(x)
    rep_ids = sorted(by_rep)

    # Prompts in the database, plus a proposed edit from Sam waiting for approval.
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from load_prompts import load
    load(c, owner_uid)
    body = (pathlib.Path(__file__).resolve().parents[1] / "agents/loops/account_program/prompt.md").read_text()
    c.execute("insert into public.loop_prompts (\"loop\", version, body, note, status, proposed_by, created_at) values "
              "('account_program', 2, %s, %s, 'proposed', %s, %s) on conflict do nothing",
              (body.replace("6. If the rep edited", "6. For enterprise accounts, the rep is the sender unless the reviewer history says otherwise.\n7. If the rep edited"),
               "Reps keep changing the sender on enterprise accounts. Make the rep the default sender there.", owner_uid, ago(1, 16)))

    # Autonomy today, and how it got there.
    c.execute("select set_config('ea.promotion_in_progress', 'on', true)")
    for loop, lvl in {"market_model": 2, "conversation_capture": 2, "outreach": 2, "product_feedback": 2}.items():
        c.execute("update public.agent_definitions set autonomy_level = %s where \"loop\" = %s", (lvl, loop))
    c.execute("select set_config('ea.promotion_in_progress', '', true)")
    checks = lambda n, acc, rej: Jsonb({"reviewed": n, "accepted_as_is": acc, "rejected": rej, "replay_at_least_baseline": True, "violations_60d": 0})
    for loop, frm, to, days, why, ck in [
        ("market_model", 1, 2, 40, "Cleared the level 2 bar: 112 reviewed, 81% accepted as is.", checks(112, .81, .06)),
        ("outreach", 2, 3, 30, "Cleared the level 3 bar: 214 reviewed, 96% accepted as is.", checks(214, .96, .02)),
        ("conversation_capture", 1, 2, 19, "Cleared the level 2 bar: 168 reviewed, 92% accepted as is.", checks(168, .92, .02)),
        ("outreach", 3, 2, 12, "Demoted: a fourth touch in 14 days to a contact at Kestrel Bikes was flagged by Wen Park.", Jsonb({"violation": True})),
        ("product_feedback", 1, 2, 8, "Cleared the level 2 bar: 104 reviewed, 85% accepted as is.", checks(104, .85, .05))]:
        c.execute("insert into public.autonomy_changes (agent_definition_id, from_level, to_level, reason, checks, decided_by, decided_at) "
                  "values (%s,%s,%s,%s,%s,%s,%s)", (agents[loop][0], frm, to, why, ck, owner_uid, ago(days, 15)))

    def evidence(subject_type, subject_id, kind, claim, uri, when, by, recorded=None):
        # created_at is when the run wrote the row down, not when this script ran. The console counts
        # "new evidence" by created_at, so only last night's rows count as new.
        return one("insert into public.evidence (subject_type, subject_id, kind, claim, source_uri, observed_at, strength, recorded_by, created_at) "
                   "values (%s,%s,%s,%s,%s,%s,'weak',%s,%s) returning id", subject_type, str(subject_id), kind, claim, uri, when, by, recorded or when)

    def run(loop, when, model, prompt_version, steps):
        did, auid = agents[loop]
        lvl = one("select autonomy_level from public.agent_definitions where id = %s", did)
        rid = one("insert into public.runs (agent_definition_id, principal_id, \"loop\", model, prompt_version, skill_versions, autonomy_level, "
                  "trigger, status, tokens_in, tokens_out, started_at, ended_at) values (%s,%s,%s,%s,%s,'{}',%s,'nightly','completed',%s,%s,%s,%s) returning id",
                  did, auid, loop, model, prompt_version, lvl, R.randint(18000, 52000), R.randint(1500, 4200), when, when + dt.timedelta(seconds=R.randint(20, 95)))
        seq = 0
        for name, payload in [("model_turn", {"content": "Reading the account context."})] + steps:
            for et in (("tool_call", "tool_result") if name != "model_turn" else ("model_turn",)):
                seq += 1
                c.execute("insert into public.run_events (run_id, seq, event_type, name, payload, at) values (%s,%s,%s,%s,%s,%s)",
                          (rid, seq, et, None if et == "model_turn" else name, Jsonb(payload if et != "tool_result" else {"ok": True}),
                           when + dt.timedelta(seconds=seq * 3)))
        return rid, auid, lvl

    def decision(rid, auid, lvl, loop, action, stype, sid, rationale, payload, evs, when, reviewer, fresh):
        if fresh:
            status, outcome, note, edited, rby, rat = ("queued" if lvl >= 2 else "proposed"), None, None, None, None, None
        else:
            mix = LOOPS[loop][2]
            if when > NOW - DAY * UPGRADE_DAYS_AGO:          # the newer model is somewhat better, not magic
                a, e, r = mix
                mix = (a + 0.35 * (e + r), 0.65 * e, 0.65 * r)
            outcome = pick_outcome(mix)
            note = R.choice(NOTES[loop]) if outcome != "accepted" else None
            edited = {**payload, "edited": True} if outcome == "edited" else None
            status = "rejected" if outcome == "rejected" else ("applied" if action == "update_field" else "approved")
            rby, rat = reviewer, when + dt.timedelta(hours=R.randint(5, 30))
        d = one("insert into public.decisions (run_id, made_by, \"loop\", action, subject_type, subject_id, rationale, payload, autonomy_level, status, "
                "review_outcome, edited_payload, review_note, reviewed_by, reviewed_at, made_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                rid, auid, loop, action, stype, str(sid), rationale, Jsonb(payload), lvl, status, outcome,
                Jsonb(edited) if edited else None, note, rby, rat, when)
        for e in evs:
            c.execute("insert into public.decision_evidence (decision_id, evidence_id) values (%s,%s) on conflict do nothing", (d, e))
        return d, outcome

    # The real run from examples/live-run: Claude's actual plan for Acme Orchards, waiting for Maya.
    live = json.loads((pathlib.Path(__file__).resolve().parents[1] / "examples/live-run/output.json").read_text())
    live = shift_dates(live, acme_close - LIVE_RUN_CLOSE, acme_close)
    acme_ev = [r[0] for r in q("select e.id from public.evidence e where (e.subject_type = 'company' and e.subject_id = %s) "
                                "or (e.subject_type = 'contact' and e.subject_id in (select id::text from public.contacts where company_id = %s)) order by e.id", str(acme), acme)]
    did, auid = agents["account_program"]
    when = ago(0, 2)
    lrid = one("insert into public.runs (agent_definition_id, principal_id, \"loop\", model, prompt_version, skill_versions, autonomy_level, trigger, status, "
               "tokens_in, tokens_out, transcript_uri, started_at, ended_at) values (%s,%s,'account_program','claude-opus-5-5','v2','{}',1,'nightly','completed',34292,3110,"
               "'examples/live-run/transcript.json',%s,%s) returning id", did, auid, when, when + dt.timedelta(seconds=30))
    for i, (et, name) in enumerate([("model_turn", None), ("tool_call", "get_account_context"), ("tool_result", "get_account_context"),
                                    ("tool_call", "get_policies"), ("tool_result", "get_policies"), ("tool_call", "get_policies"), ("tool_result", "get_policies"),
                                    ("tool_call", "get_policies"), ("tool_result", "get_policies"), ("tool_call", "search_evidence"), ("tool_result", "search_evidence"),
                                    ("model_turn", None), ("tool_call", "propose_decision"), ("tool_result", "propose_decision"),
                                    ("tool_call", "propose_strategy"), ("tool_result", "propose_strategy"), ("model_turn", None)], start=1):
        c.execute("insert into public.run_events (run_id, seq, event_type, name, payload, at) values (%s,%s,%s,%s,%s,%s)",
                  (lrid, i, et, name, Jsonb({}), when + dt.timedelta(seconds=i * 2)))
    ld = one("insert into public.decisions (run_id, made_by, \"loop\", action, subject_type, subject_id, rationale, payload, autonomy_level, status, made_at) "
             "values (%s,%s,'account_program','propose_strategy','company',%s,%s,'{}',1,'proposed',%s) returning id",
             lrid, auid, str(acme), live["decision"]["rationale"], when)
    for e in acme_ev:
        c.execute("insert into public.decision_evidence (decision_id, evidence_id) values (%s,%s)", (ld, e))
    plan = live["strategy_v2"]
    c.execute("insert into public.strategies (subject_type, subject_id, version, plan, status, decision_id, proposed_by, created_at) "
              "values ('company',%s,2,%s,'proposed',%s,%s,%s)", (str(acme), Jsonb(plan), ld, auid, when))

    strategy_version = {}
    last_plan = {}

    # Nightly and weekly runs, oldest first. Day 0 is last night: those decisions are this morning's queue.
    for day in range(60, -1, -1):
        model = OLD_MODEL if day > UPGRADE_DAYS_AGO else NEW_MODEL
        fresh = day == 0
        for loop, (cadence, (lo, hi), mix) in LOOPS.items():
            if day % cadence:
                continue
            if loop == "territory_capacity" and day not in (0,):
                continue
            if loop == "operating_design" and day not in (30, 0):
                continue
            when = ago(day, R.randint(1, 4))
            pv = "db:v1" if day <= 20 else "v1"
            n = R.randint(lo, hi) if not fresh else max(1, hi)
            if fresh and loop in EVERY_REP_LOOPS:
                n = max(n, len(rep_ids))
            if loop == "forecast":
                rid, auid, lvl = run(loop, when, model, pv, [("search_evidence", {"q": "pipeline"}), ("record_evidence", {})])
                for terr, base in [(2, 1.42), (3, 0.61), (4, 1.18), (5, 0.44)]:
                    val = base * (1 + R.uniform(-.08, .08))
                    evidence("territory", terr, "inferred", f"Agent forecast call: ${val:.2f}M this quarter (range ${val * .88:.2f}M to ${val * 1.1:.2f}M). Human call: ${base * (1 + R.uniform(-.12, .05)):.2f}M.",
                             f"run://{rid}", when, auid)
                continue
            rid, auid, lvl = run(loop, when, model, pv, [("get_account_context", {}), ("search_evidence", {}), ("propose_decision", {})])
            for i in range(n):
                if loop == "account_program":
                    # A new plan version only when the last one is at least ten days old, as in real use.
                    pool = [x for x in west_ent if x[1] != "Acme Orchards" and last_plan.get(x[0], 999) - day >= 10]
                    if not pool:
                        continue
                    comp = R.choice(pool)
                    last_plan[comp[0]] = day
                elif fresh and loop in EVERY_REP_LOOPS and i < len(rep_ids):
                    comp = R.choice(by_rep[rep_ids[i]])
                else:
                    comp = R.choice(companies)
                cid, cname, sales_id, terr = comp
                reviewer = uid_of_sales.get(sales_id)
                cts = contacts.get(cid, [])
                ct = R.choice(cts) if cts else None
                deal = deals.get(cid)
                evs = []
                if loop == "account_program":
                    evs.append(evidence("company", cid, "product_usage", f"{cname}: weekly active users up {R.randint(20, 110)}% in {R.randint(3, 8)} weeks.", f"telemetry://{cid}/wau", when - DAY * 2, auid, when))
                    if ct: evs.append(evidence("contact", ct[0], "call_quote", f"{ct[1]} ({ct[2]}): \"{R.choice(['We need this before the board review.', 'Migration effort is my only worry.', 'Budget is approved for Q1.', 'Show me how it works with our warehouse.'])}\"", f"gong://calls/{cid}-{day}", when - DAY * 5, auid, when))
                    payload = demo_plan(cname, ct, R.choice(["rep", "rep", "agent"]), owner_name.get(sales_id, "the rep"), evs)
                    d, outcome = decision(rid, auid, lvl, loop, "propose_strategy", "company", cid,
                                          f"{cname}: usage is climbing and {ct[1] if ct else 'the champion'} named a deadline. Propose a plan with {('the rep' if payload['sender']['type'] == 'rep' else 'an agent')} as sender.",
                                          payload, evs, when, reviewer, fresh)
                    v = strategy_version.get(cid, one("select coalesce(max(version), 0) from public.strategies where subject_type = 'company' and subject_id = %s", str(cid))) + 1
                    strategy_version[cid] = v
                    c.execute("insert into public.strategies (subject_type, subject_id, version, plan, status, decision_id, proposed_by, approved_by, created_at) values "
                              "('company',%s,%s,%s,%s,%s,%s,%s,%s)", (str(cid), v, Jsonb(payload),
                                                                 "proposed" if fresh else ("rejected" if outcome == "rejected" else "approved"), d, auid,
                                                                 None if fresh or outcome == "rejected" else reviewer, when))
                elif loop == "deal_inspection" and deal:
                    risk = R.choice(["No economic buyer identified at proposal stage.", "Champion has not replied in 16 days.", "Close date is before the procurement review can finish.", "No mutual plan, and the deal skipped technical validation."])
                    evs.append(evidence("deal", deal[0], "crm_record", f"{deal[1]}: stage {deal[2]}, ${deal[3]:,.0f}.", f"crm://deals/{deal[0]}", when, auid))
                    if ct: evs.append(evidence("contact", ct[0], "email_from_contact", f"{ct[1]}: \"{R.choice(['Let us regroup after the holidays.', 'Looping in procurement.', 'Can you send pricing for three years?'])}\"", f"mail://{cid}/{ct[0]}", when - DAY * 3, auid, when))
                    decision(rid, auid, lvl, loop, "flag_risk", "deal", deal[0], f"{deal[1]}: {risk}", {"risk": risk, "next_step": "Book a call with the economic buyer this week."}, evs, when, reviewer, fresh)
                elif loop == "conversation_capture" and deal and ct:
                    evs.append(evidence("contact", ct[0], "call_quote", f"{ct[1]}: \"We are targeting the end of next month to sign.\"", f"gong://calls/{cid}-{day}#t={R.randint(3, 40)}:{R.randint(10, 59)}", when - dt.timedelta(hours=6), auid, when))
                    newdate = (NOW + DAY * R.randint(25, 45)).date().isoformat()
                    decision(rid, auid, lvl, loop, "update_field", "deal", deal[0], f"{deal[1]}: buyer said end of next month on the call. Move the close date to {newdate}.",
                             {"table": "deals", "field": "expected_closing_date", "row_id": deal[0], "value": newdate}, evs, when, reviewer, fresh)
                    if (fresh and i < len(rep_ids)) or R.random() < .3:   # last night, one promise per rep
                        c.execute("insert into public.commitments (subject_type, subject_id, promise, owner_user_id, due_on, status, source_evidence_id, created_at) values "
                                  "('company',%s,%s,%s,%s,%s,%s,%s)", (str(cid), R.choice(["Send the SOC 2 report.", "Share the migration plan.", "Intro to a reference customer."]),
                                                                     reviewer, (when + DAY * 5).date(), "open" if day < 6 else "fulfilled", evs[0], when))
                elif loop == "outreach" and ct:
                    evs.append(evidence("company", cid, "crm_record", f"Approved plan for {cname}, step {R.randint(1, 3)}.", f"crm://strategies/{cid}", when, auid))
                    d, outcome = decision(rid, auid, lvl, loop, "schedule_touch", "contact", ct[0], f"Next step of the approved plan for {cname}: email {ct[1]} with the usage review offer.",
                                          {"channel": "email", "sender_type": "rep"}, evs, when, reviewer, fresh)
                    c.execute("insert into public.touches (decision_id, run_id, contact_id, channel, sender_type, purpose, scheduled_for, status, created_at) values "
                              "(%s,%s,%s,'email','rep',%s,%s,%s,%s)", (d, rid, ct[0], "Offer a usage review", when + DAY,
                                                                      "pending_approval" if fresh else ("cancelled" if outcome == "rejected" else "sent"), when))
                elif loop == "post_sale_health":
                    flag = R.choice(["flag_churn_risk", "flag_expansion"])
                    evs.append(evidence("company", cid, "product_usage", f"{cname}: {'usage down 31% over 30 days' if flag == 'flag_churn_risk' else 'compute credits at 140% of contract'}.", f"telemetry://{cid}/usage", when, auid))
                    decision(rid, auid, lvl, loop, flag, "company", cid, f"{cname}: {'usage is falling ahead of renewal' if flag == 'flag_churn_risk' else 'they are over their commit, time for a new term'}.", {"next_step": "Exec sponsor call"}, evs, when, reviewer, fresh)
                elif loop == "market_model":
                    evs.append(evidence("company", cid, "inferred", f"{cname}: ICP score {R.randint(52, 94)} (telemetry, segment, tech stack).", f"run://{rid}", when, auid))
                    if R.random() < .25 or fresh:
                        decision(rid, auid, lvl, loop, "propose_icp_change", "loop", "market_model", "Won deals over the last 90 days skew to companies already running scheduled data pipelines. Weight that signal higher.",
                                 {"change": "weight pipeline telemetry 0.3 to 0.45"}, evs, when, owner_uid, fresh)
                elif loop == "partner_intelligence":
                    pid, pname = R.choice(partners)
                    evs.append(evidence("partner", pid, "partner_report", f"{pname} reported {R.randint(2, 5)} joint opportunities in Germany this month.", f"partner://{pid}/report", when, auid))
                    decision(rid, auid, lvl, loop, "propose_strategy", "partner", pid, f"{pname} is sourcing deals in a region we do not cover. Propose a joint play with their alliance lead.",
                             {"play": "joint pipeline review"}, evs, when, uid_of_sales[8], fresh)
                elif loop == "product_feedback":
                    theme = R.choice(["SSO for contractors", "Scheduler migration tooling", "Usage alerts by team", "EU data residency"])
                    if ct: evs.append(evidence("contact", ct[0], "call_quote", f"{ct[1]}: \"Without {theme.lower()} this is a hard sell internally.\"", f"gong://calls/{cid}-{day}", when, auid))
                    decision(rid, auid, lvl, loop, "product_theme", "loop", "product_feedback", f"Theme: {theme}. Raised on {R.randint(3, 9)} calls this week, ${R.randint(300, 900)}k ARR in open deals.",
                             {"theme": theme}, evs, when, owner_uid, fresh)
                elif loop == "comp_ops" and deal:
                    evs.append(evidence("deal", deal[0], "crm_record", f"{deal[1]} closed, ${deal[3]:,.0f}.", f"crm://deals/{deal[0]}", when, auid))
                    decision(rid, auid, lvl, loop, "propose_credit", "deal", deal[0], f"{deal[1]}: 100% credit to the account owner. No partner on the deal.",
                             {"splits": [{"sales_id": sales_id, "pct": 100}]}, evs, when, owner_uid, fresh)
                elif loop == "territory_capacity":
                    evs.append(evidence("territory", 2, "inferred", "West Enterprise potential is 38% above East Enterprise with the same headcount.", f"run://{rid}", when, auid))
                    decision(rid, auid, lvl, loop, "propose_carve", "loop", "territory_capacity", "Rebalance for 2027: move 3 accounts from West Enterprise to a new Mountain territory and hire one AE. Spread of potential drops from 38% to 9%.",
                             {"moves": 3, "new_territory": "Mountain Enterprise", "hires": 1}, evs, when, owner_uid, fresh)
                elif loop == "operating_design":
                    evs.append(evidence("territory", 1, "inferred", "Deals without a technical champion closed at 11% vs 34% with one, over 140 closed deals.", f"run://{rid}", when, auid))
                    decision(rid, auid, lvl, loop, "propose_skill_version", "skill", "deal-inspection", "Losses cluster where there is no technical champion. Add that check to the deal inspection skill.",
                             {"skill": "deal-inspection"}, evs, when, owner_uid, fresh)

    # Open promises are due relative to today: the oldest was due yesterday, the rest are still ahead.
    for i, (pid,) in enumerate(q("select id from public.commitments where status = 'open' order by created_at, id")):
        c.execute("update public.commitments set due_on = %s where id = %s", (NOW.date() + DAY * (-1 if i == 0 else 2 + i), pid))

    # One policy violation, the reason outreach was demoted.
    kd = one("select d.id from public.decisions d where d.\"loop\" = 'outreach' and d.made_at < now() - interval '12 days' order by d.made_at desc limit 1")
    c.execute("insert into public.policy_violations (decision_id, agent_definition_id, note, flagged_by, flagged_at) values (%s,%s,%s,%s,%s)",
              (kd, agents["outreach"][0], "Fourth touch to the same contact in 14 days. The touch count missed a reply sent from a personal address.", wen_uid, ago(12, 17)))

    # Escalations waiting on people.
    for comp in R.sample(companies, 3):
        c.execute("insert into public.escalations (subject_type, subject_id, to_user, reason, status, created_at) values ('company',%s,%s,%s,'open',%s)",
                  (str(comp[0]), uid_of_sales.get(comp[2]), f"{comp[1]}: evidence conflicts. The champion said yes on the call, procurement said no budget by email.", ago(1, 3)))

    # Replay scores per loop, before and after the model upgrade.
    for loop, (did, _) in agents.items():
        base = R.uniform(.68, .86)
        for model, score, when in [(OLD_MODEL, base, 40), (NEW_MODEL, min(.97, base + R.uniform(-.01, .07)), UPGRADE_DAYS_AGO)]:
            c.execute("insert into public.replay_results (agent_definition_id, eval_set, model, prompt_version, cases, score, baseline_score, recorded_by, run_at) "
                      "values (%s,%s,%s,'v1',%s,%s,%s,%s,%s)", (did, f"{loop}-replay", model, R.randint(40, 200), round(score, 3), round(base, 3), owner_uid, ago(when, 18)))

    # The holdout experiment: 400 accounts, 80 held out (demo subjects), 60 days in.
    exp = one("select id from public.experiments where \"loop\" = 'account_program' order by id limit 1")
    c.execute("update public.experiments set status = 'running', starts_at = %s where id = %s", ((NOW - DAY * 60).date(), exp))
    ids = [f"demo-{i:03d}" for i in range(400)]
    held = set(R.sample(ids, 80))
    booked_t = set(R.sample([i for i in ids if i not in held], 48))
    booked_h = set(R.sample(sorted(held), 8))
    for i in ids:
        c.execute("insert into public.experiment_assignments (experiment_id, subject_id, arm, assigned_at) values (%s,%s,%s,%s)",
                  (exp, i, "holdout" if i in held else "treatment", NOW - DAY * 60))
        c.execute("insert into public.experiment_outcomes (experiment_id, subject_id, metric_value, observed_at) values (%s,%s,%s,%s)",
                  (exp, i, 1 if i in booked_t or i in booked_h else 0, NOW - DAY))

    # Weekly forecast snapshots, so the pipeline has a trend.
    for w in range(8, -1, -1):
        week = (NOW - DAY * 7 * w).date()
        week = week - dt.timedelta(days=week.weekday())
        c.execute("insert into public.forecast_snapshots (snapshot_week, deal_id, stage, forecast_category, amount_usd, expected_closing_date, sales_id, territory_id) "
                  "select %s, d.id, d.stage, d.forecast_category, d.amount * (1 + (%s - 4) * 0.02), d.expected_closing_date, d.sales_id, d.territory_id "
                  "from public.deals d on conflict do nothing", (week, w))

    # Slack ids for the demo people, so the console can show each one's Slack digest.
    for email, sid in [("ana.rep@northwind.example", "U0MAYA"), ("ben.rep@northwind.example", "U0BEN"), ("cy.rep@northwind.example", "U0CY"),
                       ("riley.ops@northwind.example", "U0SAM"), ("pat.partners@northwind.example", "U0PAT")]:
        c.execute("insert into public.slack_user_map (slack_user_id, user_id) select %s, user_id from public.sales where email = %s on conflict do nothing", (sid, email))


if __name__ == "__main__":
    main()
