"""The demo data loads on top of the seed, and leaves a sensible morning for each person."""
import datetime as dt
import json
import pathlib
import subprocess
import sys

import psycopg
import pytest

from helpers import ADMIN_DSN, ANA, CY, FIN, OWNER, PAT, VP, build

ROOT = pathlib.Path(__file__).resolve().parents[1]
PERSONAS = {"Maya": ANA, "Sam": OWNER, "Vic": VP, "Cy": CY, "Pat": PAT, "Morgan": FIN}   # the six on the demo sign-in page
# "Last night" is the window the console's Today page counts: the last 36 hours.
NIGHT = "interval '36 hours'"


@pytest.fixture(scope="module")
def demo():
    dsn = build(ADMIN_DSN, "ea_test_demo", seed=True)
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute((ROOT / "examples/demo/acme_signals.sql").read_text())
    subprocess.run([sys.executable, str(ROOT / "scripts/demo_history.py"), "--dsn", dsn], check=True, capture_output=True)
    with psycopg.connect(dsn) as c:
        yield c


def as_person(c, uid):
    c.execute("set local role authenticated")
    c.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": uid, "role": "authenticated"}),))


def test_demo_history_loads_and_each_person_has_a_queue(demo):
    c = demo
    assert c.execute("select count(*) from public.runs").fetchone()[0] > 200
    assert c.execute("select count(*) from public.loop_prompts where status = 'approved'").fetchone()[0] == 12
    for who in (ANA, CY, OWNER):
        with c.transaction(force_rollback=True):
            as_person(c, who)
            assert c.execute("select count(*) from public.review_queue()").fetchone()[0] > 0, who


def test_fresh_demo_has_last_night_for_every_persona(demo):
    """Fails if a fresh demo has no runs, evidence or decisions in the last night for anyone."""
    c = demo
    total = c.execute("select count(*) from public.evidence").fetchone()[0]
    for name, who in PERSONAS.items():
        with c.transaction(force_rollback=True):
            as_person(c, who)
            runs, loops = c.execute("select coalesce(sum(runs_36h), 0), count(*) filter (where runs_36h > 0) from public.loop_activity()").fetchone()
            assert runs > 0, f"{name}: no runs last night"
            assert loops == 12, f"{name}: {loops} of 12 loops ran last night"
            new = c.execute(f"select count(*) from public.evidence where created_at >= now() - {NIGHT}").fetchone()[0]
            assert new > 0, f"{name}: no evidence recorded last night"
            # Evidence is dated when the run recorded it, not when the demo was loaded.
            assert new < total / 4, f"{name}: {new} of {total} evidence rows look new"
            made = c.execute(f"select count(*) from public.decisions where made_at >= now() - {NIGHT}").fetchone()[0]
            assert made > 0, f"{name}: no decisions made last night"


def test_fresh_demo_queue_and_forecast_calls_are_from_last_night(demo):
    c = demo
    for name, who in PERSONAS.items():
        with c.transaction(force_rollback=True):
            as_person(c, who)
            old = c.execute(f"select count(*) from public.review_queue() where made_at < now() - {NIGHT}").fetchone()[0]
            assert old == 0, f"{name}: {old} queue items are older than last night"
            calls = c.execute("select subject_id, max(observed_at) >= now() - " + NIGHT + " from public.evidence "
                              "where subject_type = 'territory' and kind = 'inferred' and claim like 'Agent forecast call%%' group by 1").fetchall()
            assert len(calls) == 4 and all(fresh for _, fresh in calls), f"{name}: forecast calls {calls}"


def test_fresh_demo_promises_are_not_piled_up_overdue(demo):
    c = demo
    opened, overdue, worst = c.execute("select count(*), count(*) filter (where due_on < current_date), "
                                       "coalesce(max(current_date - due_on), 0) from public.commitments where status = 'open'").fetchone()
    assert opened >= 3
    assert overdue <= 1 and worst <= 2, f"{overdue} overdue, the worst by {worst} days"
    for rep in (ANA, CY):   # each rep on the sign-in page has at least one promise still ahead
        assert c.execute("select count(*) from public.commitments where status = 'open' and owner_user_id = %s and due_on >= current_date", (rep,)).fetchone()[0] > 0


def test_fresh_demo_shifts_the_saved_acme_run_to_today(demo):
    c = demo
    close = c.execute("select expected_closing_date from public.deals where company_id = 1").fetchone()[0]
    assert 7 <= (close - dt.datetime.now(dt.timezone.utc).date()).days <= 9
    plan, rationale = c.execute("select s.plan, d.rationale from public.strategies s join public.decisions d on d.id = s.decision_id "
                                "where s.subject_type = 'company' and s.subject_id = '1' and s.version = 2").fetchone()
    assert close.isoformat() in plan["risks"][0]
    assert f"closes {close:%m-%d}" in rationale
    # Only the dates move. The rest of what Claude wrote is as saved.
    saved = json.loads((ROOT / "examples/live-run/output.json").read_text())["strategy_v2"]
    assert plan["risks"][0] == saved["risks"][0].replace("2026-11-12", close.isoformat())
    assert {k: v for k, v in plan.items() if k != "risks"} == {k: v for k, v in saved.items() if k != "risks"}
    assert plan["risks"][1:] == saved["risks"][1:]
    # The Acme signals are recent, and the dates inside their links match.
    for uri, seen in c.execute("select source_uri, observed_at from public.evidence where recorded_by in "
                               "('00000000-0000-0000-0000-0000000000aa', %s) and source_uri ~ '[0-9]{4}-[0-9]{2}-[0-9]{2}'", (ANA,)).fetchall():
        assert f"{seen.astimezone(dt.timezone.utc):%Y-%m-%d}" in uri or f"{seen:%Y-%m-%d}" in uri
        assert seen > dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)


def test_forecast_calls_view_follows_row_level_security(demo):
    """0010: the latest call per territory with its numbers, and only for evidence the person may see."""
    c = demo
    with c.transaction(force_rollback=True):
        as_person(c, VP)
        rows = c.execute("select territory, claim, agent_call_usd, human_call_usd, gap_usd, observed_at from public.forecast_calls").fetchall()
        assert len(rows) == 4
        for territory, claim, agent, human, gap, seen in rows:
            assert agent > 0 and human > 0 and gap == agent - human, territory
            assert f"${agent / 1000000:.2f}M" in claim and f"${human / 1000000:.2f}M" in claim
            assert seen > dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=36)
        visible = c.execute("select count(distinct subject_id) from public.evidence where subject_type = 'territory' and claim like 'Agent forecast call:%%'").fetchone()[0]
        assert visible == 4
    for who in (CY, PAT):   # the view never shows more than the evidence table does for the same person
        with c.transaction(force_rollback=True):
            as_person(c, who)
            through_view = c.execute("select count(*) from public.forecast_calls").fetchone()[0]
            direct = c.execute("select count(distinct subject_id) from public.evidence where subject_type = 'territory' and claim like 'Agent forecast call:%%'").fetchone()[0]
            assert through_view == direct
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with c.transaction(force_rollback=True):
            c.execute("set local role anon")
            c.execute("select count(*) from public.forecast_calls")
    with c.transaction(force_rollback=True):   # a claim in other words still shows, without numbers
        c.execute("insert into public.evidence (subject_type, subject_id, kind, claim, source_uri, observed_at, strength, recorded_by) "
                  "values ('territory', '2', 'inferred', 'Agent forecast call: about the same as last week.', 'run://x', now(), 'weak', %s)", (OWNER,))
        assert c.execute("select agent_call_usd, gap_usd from public.forecast_calls where territory_id = 2").fetchone() == (None, None)


def test_vp_sees_flagged_deals_with_reason_and_evidence(demo):
    c = demo
    with c.transaction(force_rollback=True):
        as_person(c, VP)
        rows = c.execute("select d.id, d.payload->>'risk', dl.stage, (select count(*) from public.decision_evidence de join public.evidence e on e.id = de.evidence_id where de.decision_id = d.id) "
                         "from public.decisions d join public.deals dl on dl.id::text = d.subject_id "
                         "where d.\"loop\" = 'deal_inspection' and d.action = 'flag_risk' and d.review_outcome is null").fetchall()
        assert len(rows) >= 3
        for did, risk, stage, cited in rows:
            assert risk and cited >= 1 and stage not in ("won", "lost"), did


def test_demo_only_proposes_what_fits_the_deal_stage(demo):
    """No close-date move, risk flag or outreach step on a deal that is already won or lost."""
    c = demo
    bad = c.execute("select d.id, d.action, dl.name, dl.stage from public.decisions d join public.deals dl on dl.id::text = d.subject_id "
                    "where d.subject_type = 'deal' and ((d.action in ('update_field', 'flag_risk') and dl.stage in ('won', 'lost')) "
                    "or (d.action = 'propose_credit' and dl.stage <> 'won'))").fetchall()
    assert bad == []
    bad = c.execute("select d.id, co.name, dl.stage from public.decisions d join public.contacts ct on ct.id::text = d.subject_id "
                    "join public.companies co on co.id = ct.company_id join public.deals dl on dl.company_id = co.id "
                    "where d.action = 'schedule_touch' and d.subject_type = 'contact' and dl.stage in ('won', 'lost')").fetchall()
    assert bad == []
    assert c.execute("select count(*) from public.decisions where action = 'update_field' and review_outcome is null").fetchone()[0] >= 3
