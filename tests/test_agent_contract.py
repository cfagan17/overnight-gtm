"""The agent contract: every check is enforced by the database, not by the prompt."""
import json

import pytest

from helpers import ANA, CY, OWNER, WEST_MGR, acting_as, agent_uid, attempt, scalar


def agent(conn, name):
    row = conn.execute("select id from public.agent_definitions where name = %s", (name,)).fetchone()
    return row[0], agent_uid(row[0])


def set_level(conn, name, level):
    """Test-only shortcut: change autonomy without the promotion review (superuser)."""
    conn.execute("select set_config('ea.promotion_in_progress', 'on', true)")
    conn.execute("update public.agent_definitions set autonomy_level = %s where name = %s", (level, name))
    conn.execute("select set_config('ea.promotion_in_progress', '', true)")


def as_superuser(conn):
    conn.execute("reset role")
    conn.execute("select set_config('request.jwt.claims', '', true)")


def act(conn, uid):
    conn.execute("set local role authenticated")
    conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": uid, "role": "authenticated"}),))


def start_run(conn):
    return scalar(conn, "select public.start_run('test-model', 'v1', '{}'::jsonb, 'test')")


def company(conn, name):
    return conn.execute("select id from public.companies where name = %s", (name,)).fetchone()[0]


@pytest.fixture()
def tx(conn):
    with conn.transaction(force_rollback=True):
        yield conn


def test_runs_belong_to_agents(tx):
    _, ap = agent(tx, "account-program")
    _, cap = agent(tx, "conversation-capture")
    act(tx, ANA)
    assert attempt(tx, "select public.start_run('m','v1')")[0] == "denied"            # humans do not start runs
    act(tx, ap)
    run = start_run(tx)
    act(tx, cap)
    assert attempt(tx, "select public.record_evidence(%s,'company','1','web_page','x claim','https://x',now())", (run,))[0] == "denied"


def test_scope_limits_what_an_agent_can_read(tx):
    _, ap = agent(tx, "account-program")          # scoped to West Enterprise only
    west, east = company(tx, "Acme Orchards"), company(tx, "Maple Ledger")
    act(tx, ap)
    run = start_run(tx)
    ctx = scalar(tx, "select public.get_account_context(%s, %s)", (west, run))
    assert ctx["company"]["name"] == "Acme Orchards" and len(ctx["contacts"]) == 3
    assert attempt(tx, "select public.get_account_context(%s, %s)", (east, run))[0] == "denied"
    assert scalar(tx, "select count(*) from public.deals") == scalar(tx, "select count(*) from public.deals where territory_id = 2")
    assert attempt(tx, "select public.record_evidence(%s,'company',%s,'web_page','A claim','https://x',now())", (run, str(east)))[0] == "denied"


def test_evidence_strength_comes_from_kind_and_is_append_only(tx):
    _, ap = agent(tx, "account-program")
    west = company(tx, "Acme Orchards")
    act(tx, ap)
    run = start_run(tx)
    weak = scalar(tx, "select public.record_evidence(%s,'company',%s,'web_page','Hiring 12 data engineers','https://acme.example/jobs',now())", (run, str(west)))
    strong = scalar(tx, "select public.record_evidence(%s,'company',%s,'product_usage','Projects doubled in 6 weeks','telemetry://acme/projects',now())", (run, str(west)))
    assert scalar(tx, "select strength from public.evidence where id = %s", (weak,)) == "weak"
    assert scalar(tx, "select strength from public.evidence where id = %s", (strong,)) == "strong"
    assert attempt(tx, "update public.evidence set claim = 'changed' where id = %s", (weak,))[0] == "denied"
    as_superuser(tx)
    assert attempt(tx, "update public.evidence set claim = 'changed' where id = %s", (weak,))[0] == "denied"   # even superusers


def test_decisions_need_visible_evidence(tx):
    _, ap = agent(tx, "account-program")
    west = company(tx, "Acme Orchards")
    act(tx, ap)
    run = start_run(tx)
    assert attempt(tx, "select public.propose_decision(%s,'propose_strategy','company',%s,'Usage is growing fast', array[]::bigint[])", (run, str(west)))[0] == "denied"
    as_superuser(tx)
    east_ev = scalar(tx, "insert into public.evidence (subject_type, subject_id, kind, claim, source_uri, observed_at, strength, recorded_by) "
                         "values ('company', %s, 'rep_observation', 'East fact', 'note://1', now(), 'x', %s) returning id",
                     (str(company(tx, 'Maple Ledger')), CY))
    act(tx, ap)
    assert attempt(tx, "select public.propose_decision(%s,'propose_strategy','company',%s,'Usage is growing fast', array[%s]::bigint[])", (run, str(west), east_ev))[0] == "denied"


def test_strategy_lifecycle_and_no_id_no_claim(tx):
    _, ap = agent(tx, "account-program")
    west = str(company(tx, "Acme Orchards"))
    act(tx, ap)
    run = start_run(tx)
    e1 = scalar(tx, "select public.record_evidence(%s,'company',%s,'product_usage','Projects doubled','telemetry://1',now())", (run, west))
    e2 = scalar(tx, "select public.record_evidence(%s,'company',%s,'web_page','New CTO hired','https://x',now())", (run, west))
    d = scalar(tx, "select public.propose_decision(%s,'propose_strategy','company',%s,'Usage doubled, time to engage', array[%s]::bigint[])", (run, west, e1))
    bad_plan = json.dumps({"why_now": [{"claim": "new CTO", "evidence": [e2]}]})
    assert attempt(tx, "select public.propose_strategy(%s,%s,'company',%s,%s::jsonb)", (run, d, west, bad_plan))[0] == "denied"
    plan = json.dumps({"why_now": [{"claim": "Projects doubled", "evidence": [e1]}], "sender": {"type": "rep"}})
    sid = scalar(tx, "select public.propose_strategy(%s,%s,'company',%s,%s::jsonb)", (run, d, west, plan))
    assert attempt(tx, "select public.review_decision(%s,'accepted')", (d,))[0] == "denied"   # agents do not review
    act(tx, CY)
    assert attempt(tx, "select public.review_decision(%s,'accepted')", (d,))[0] == "denied"   # cannot see the account
    act(tx, ANA)
    assert scalar(tx, "select public.review_decision(%s,'edited','Rep should send this',%s::jsonb)",
                  (d, json.dumps({"plan": {"why_now": [{"claim": "Projects doubled", "evidence": [e1]}], "sender": {"type": "executive"}}}))) == "approved"
    tx.execute("select public.activate_strategy(%s)", (sid,))
    assert scalar(tx, "select status || ':' || (plan->'sender'->>'type') from public.strategies where id = %s", (sid,)) == "active:executive"
    assert scalar(tx, "select review_outcome from public.decisions where id = %s", (d,)) == "edited"


def test_holdout_accounts_are_recorded_but_never_activated(tx):
    _, ap = agent(tx, "account-program")
    west_ids = [str(r[0]) for r in tx.execute("select id from public.companies where territory_id = 2 order by id").fetchall()]
    act(tx, OWNER)
    exp = scalar(tx, "insert into public.experiments (name, hypothesis, loop, metric, subject_type, holdout_pct) "
                     "values ('t','h','account_program','m','company',50) returning id")
    arms = scalar(tx, "select public.assign_experiment(%s, %s)", (exp, west_ids))
    assert arms["holdout"] >= 1 and arms["treatment"] >= 1
    tx.execute("select public.start_experiment(%s)", (exp,))
    assert attempt(tx, "select public.assign_experiment(%s, array['999'])", (exp,))[0] == "denied"   # fixed once started
    holdout = scalar(tx, "select subject_id from public.experiment_assignments where experiment_id = %s and arm = 'holdout' limit 1", (exp,))
    act(tx, ap)
    run = start_run(tx)
    e = scalar(tx, "select public.record_evidence(%s,'company',%s,'product_usage','Usage up','telemetry://h',now())", (run, holdout))
    d = scalar(tx, "select public.propose_decision(%s,'propose_strategy','company',%s,'Usage up, engage', array[%s]::bigint[])", (run, holdout, e))
    sid = scalar(tx, "select public.propose_strategy(%s,%s,'company',%s,'{}'::jsonb)", (run, d, holdout))
    assert scalar(tx, "select status from public.strategies where id = %s", (sid,)) == "holdout"
    act(tx, OWNER)
    assert attempt(tx, "select public.activate_strategy(%s)", (sid,))[0] == "denied"


def field_update_setup(tx, level, kind="call_quote"):
    as_superuser(tx)
    set_level(tx, "conversation-capture", level)
    _, cap = agent(tx, "conversation-capture")
    deal = scalar(tx, "select d.id from public.deals d join public.sales s on s.id = d.sales_id where s.user_id = %s order by d.id limit 1", (ANA,))
    act(tx, cap)
    run = start_run(tx)
    e = scalar(tx, "select public.record_evidence(%s,'deal',%s,%s,'Buyer said legal review is done','gong://call/1#12:30',now())", (run, str(deal), kind))
    payload = json.dumps({"table": "deals", "field": "stage", "row_id": deal, "value": "in-negociation"})
    d = scalar(tx, "select public.propose_decision(%s,'update_field','deal',%s,'Legal review complete per call', array[%s]::bigint[], %s::jsonb)", (run, str(deal), e, payload))
    return run, deal, d


def test_field_update_level_1_is_refused(tx):
    as_superuser(tx)
    set_level(tx, "conversation-capture", 1)
    _, cap = agent(tx, "conversation-capture")
    act(tx, cap)
    run = start_run(tx)
    assert attempt(tx, "select public.apply_field_update(%s, 1, 'deals', 1, 'stage', '\"won\"')", (run,))[0] == "denied"


def test_field_update_level_2_waits_for_human(tx):
    run, deal, d = field_update_setup(tx, 2)
    assert scalar(tx, "select public.apply_field_update(%s,%s,'deals',%s,'stage','\"in-negociation\"')", (run, d, deal)) == "queued"
    assert scalar(tx, "select stage from public.deals where id = %s", (deal,)) != "in-negociation"
    act(tx, ANA)
    assert scalar(tx, "select public.review_decision(%s,'accepted')", (d,)) == "applied"
    assert scalar(tx, "select stage from public.deals where id = %s", (deal,)) == "in-negociation"
    as_superuser(tx)
    row = tx.execute("select decision_id, principal_id::text from public.audit_log where table_name='deals' and row_id=%s "
                     "order by id desc limit 1", (str(deal),)).fetchone()
    assert row == (d, ANA)            # attributed to the decision and the human who approved it


def test_field_update_level_3_applies_and_is_attributed(tx):
    run, deal, d = field_update_setup(tx, 3)
    assert scalar(tx, "select public.apply_field_update(%s,%s,'deals',%s,'stage','\"in-negociation\"')", (run, d, deal)) == "applied"
    as_superuser(tx)
    row = tx.execute("select decision_id, run_id, principal_kind from public.audit_log where table_name='deals' and row_id=%s "
                     "order by id desc limit 1", (str(deal),)).fetchone()
    assert row == (d, run, "agent")


def test_field_update_refusals(tx):
    run, deal, d = field_update_setup(tx, 3, kind="enrichment_vendor")        # weak evidence only
    assert attempt(tx, "select public.apply_field_update(%s,%s,'deals',%s,'stage','\"in-negociation\"')", (run, d, deal))[0] == "denied"
    run, deal, d = field_update_setup(tx, 3)
    assert attempt(tx, "select public.apply_field_update(%s,%s,'deals',%s,'stage','\"won\"')", (run, d, deal))[0] == "denied"     # payload mismatch
    assert attempt(tx, "select public.apply_field_update(%s,%s,'deals',%s,'amount','1')", (run, d, deal))[0] == "denied"          # not allowlisted
    assert scalar(tx, "select public.apply_field_update(%s,%s,'deals',%s,'stage','\"in-negociation\"')", (run, d, deal)) == "applied"
    assert attempt(tx, "select public.apply_field_update(%s,%s,'deals',%s,'stage','\"in-negociation\"')", (run, d, deal))[0] == "denied"  # decision used once


def touch(tx, run, contact, channel="email", sender="agent"):
    e = scalar(tx, "select public.record_evidence(%s,'contact',%s,'email_from_contact','Asked for a follow-up','mail://1',now())", (run, str(contact)))
    d = scalar(tx, "select public.propose_decision(%s,'schedule_touch','contact',%s,'Contact asked for follow-up', array[%s]::bigint[])", (run, str(contact), e))
    return scalar(tx, "select public.schedule_touch(%s,%s,%s,%s,%s,'Follow up')", (run, d, contact, channel, sender))


def test_touch_policies(tx):
    _, out = agent(tx, "outreach")
    non_partner = scalar(tx, "select ct.id from public.contacts ct where not exists (select 1 from public.deals d join public.deal_partners dp on dp.deal_id = d.id where d.company_id = ct.company_id) order by ct.id limit 1")
    partner_contact = scalar(tx, "select ct.id from public.contacts ct join public.deals d on d.company_id = ct.company_id join public.deal_partners dp on dp.deal_id = d.id where dp.credit = 'sourced' limit 1")
    dnc = scalar(tx, "select ct.id from public.contacts ct where ct.id <> %s order by ct.id desc limit 1", (non_partner,))
    tx.execute("insert into public.do_not_contact (contact_id, reason, added_by) values (%s, 'asked us to stop', %s)", (dnc, OWNER))
    act(tx, out)
    run = start_run(tx)
    assert touch(tx, run, non_partner)["status"] == "pending_approval"            # level 2: a human approves each one
    assert touch(tx, run, non_partner)["status"] == "pending_approval"
    assert touch(tx, run, non_partner)["status"] == "pending_approval"
    assert touch(tx, run, non_partner)["blocked_reason"].startswith('policy "Max 3')
    assert touch(tx, run, dnc)["blocked_reason"] == "contact is on the do-not-contact list"
    assert touch(tx, run, partner_contact)["blocked_reason"].startswith('policy "Partner-sourced')
    assert touch(tx, run, partner_contact, channel="partner_intro", sender="partner")["status"] == "pending_approval"
    other = scalar(tx, "select ct.id from public.contacts ct where ct.id not in (%s, %s, %s) and not exists (select 1 from public.deals d join public.deal_partners dp on dp.deal_id = d.id where d.company_id = ct.company_id) order by ct.id limit 1", (non_partner, dnc, partner_contact))
    assert touch(tx, run, other, channel="sms")["blocked_reason"].startswith('policy "No agent-sent SMS')


def test_tool_grants(tx):
    _, ap = agent(tx, "account-program")
    act(tx, ap)
    run = start_run(tx)
    assert attempt(tx, "select public.schedule_touch(%s, 1, 1, 'email', 'agent', 'x')", (run,))[0] == "denied"
    assert attempt(tx, "select public.apply_field_update(%s, 1, 'deals', 1, 'stage', '\"won\"')", (run,))[0] == "denied"


def test_autonomy_cannot_be_self_granted(tx):
    _, ap = agent(tx, "account-program")
    act(tx, ap)
    assert attempt(tx, "update public.agent_definitions set autonomy_level = 4 where name = 'account-program'")[2] == 0
    assert attempt(tx, "update public.agent_grants set scope = '{\"all\": true}'")[2] == 0
    act(tx, OWNER)
    assert attempt(tx, "update public.agent_definitions set autonomy_level = 3 where name = 'account-program'")[0] == "denied"
    aid = scalar(tx, "select id from public.agent_definitions where name = 'account-program'")
    check = scalar(tx, "select public.promotion_check(%s, 2::smallint)", (aid,))
    assert check["eligible"] is False
    assert attempt(tx, "select public.decide_promotion(%s, 2::smallint, 'feels good')", (aid,))[0] == "denied"
    tx.execute("select public.decide_promotion(%s, 0::smallint, 'pausing for review')", (aid,))           # demotion always allowed
    assert scalar(tx, "select autonomy_level from public.agent_definitions where id = %s", (aid,)) == 0
    tc = scalar(tx, "select id from public.agent_definitions where name = 'territory-capacity'")
    assert scalar(tx, "select public.promotion_check(%s, 3::smallint)", (tc,))["checks"][0]["pass"] is False   # capped at 2


def test_promotion_when_the_record_earns_it(tx):
    as_superuser(tx)
    aid, ap = agent(tx, "account-program")
    west = str(company(tx, "Acme Orchards"))
    act(tx, ap)
    run = start_run(tx)
    e = scalar(tx, "select public.record_evidence(%s,'company',%s,'product_usage','Usage up','telemetry://p',now())", (run, west))
    ids = [scalar(tx, "select public.propose_decision(%s,'note','company',%s,'Routine proposal', array[%s]::bigint[])", (run, west, e)) for _ in range(100)]
    act(tx, ANA)
    for i, d in enumerate(ids):
        outcome = "accepted" if i < 90 else "edited" if i < 97 else "rejected"
        tx.execute("select public.review_decision(%s, %s, null, %s::jsonb)", (d, outcome, '{"note": "tightened"}' if outcome == "edited" else None))
    act(tx, OWNER)
    tx.execute("select public.record_replay_result(%s,'account_program_v1','m','v2','{}'::jsonb,40,0.82,0.78)", (aid,))
    check = scalar(tx, "select public.promotion_check(%s, 2::smallint)", (aid,))
    assert check["eligible"] is True, check
    tx.execute("select public.decide_promotion(%s, 2::smallint, 'cleared the level 2 bar')", (aid,))
    assert scalar(tx, "select autonomy_level from public.agent_definitions where id = %s", (aid,)) == 2
    # one confirmed violation drops it back
    assert scalar(tx, "select public.flag_policy_violation(%s, 'contacted a customer in a quiet period')", (ids[0],)) == 1


def test_skills_are_proposed_by_agents_and_approved_by_owners(tx):
    _, od = agent(tx, "operating-design")
    west = str(company(tx, "Acme Orchards"))
    act(tx, od)
    run = start_run(tx)
    e = scalar(tx, "select public.record_evidence(%s,'company',%s,'crm_record','Stage 3 to 4 conversion fell','crm://report/1',now())", (run, west))
    d = scalar(tx, "select public.propose_decision(%s,'propose_skill_version','skill','stages','Add an exit criterion', array[%s]::bigint[])", (run, e))
    v = scalar(tx, "select public.propose_skill_version(%s,%s,'stages','# Stages v2')", (run, d))
    act(tx, ANA)
    assert attempt(tx, "select public.approve_skill('stages', %s)", (v,))[0] == "denied"
    act(tx, OWNER)
    tx.execute("select public.approve_skill('stages', %s)", (v,))
    assert scalar(tx, "select status from public.skills where name = 'stages' and version = %s", (v,)) == "approved"


def test_experiment_result_matches_the_worked_example(tx):
    """48 of 320 vs 8 of 80: a 5 point gap the test cannot yet call (design doc, section 9)."""
    act(tx, OWNER)
    exp = scalar(tx, "insert into public.experiments (name, hypothesis, loop, metric, subject_type, holdout_pct) "
                     "values ('w','h','account_program','meeting','company',20) returning id")
    as_superuser(tx)
    tx.execute("insert into public.experiment_assignments (experiment_id, subject_id, arm) "
               "select %s, 't' || g, 'treatment' from generate_series(1,320) g union all "
               "select %s, 'h' || g, 'holdout' from generate_series(1,80) g", (exp, exp))
    tx.execute("insert into public.experiment_outcomes (experiment_id, subject_id, metric_value) "
               "select %s, 't' || g, 1 from generate_series(1,48) g union all "
               "select %s, 'h' || g, 1 from generate_series(1,8) g", (exp, exp))
    act(tx, OWNER)
    r = scalar(tx, "select public.experiment_result(%s)", (exp,))
    assert float(r["difference"]) == pytest.approx(0.05, abs=1e-6)
    low, high = (float(x) for x in r["range_95"])
    assert low == pytest.approx(-0.027, abs=0.003) and high == pytest.approx(0.127, abs=0.003)
    assert r["conclusive"] is False
    assert 600 <= float(r["subjects_per_arm_needed_for_this_difference"]) <= 760


def test_escalations_go_to_humans(tx):
    _, ap = agent(tx, "account-program")
    _, other = agent(tx, "outreach")
    act(tx, ap)
    run = start_run(tx)
    assert scalar(tx, "select public.escalate(%s,'company','1',%s,'Conflicting evidence on who decides')", (run, ANA)) > 0
    assert attempt(tx, "select public.escalate(%s,'company','1',%s,'x')", (run, other))[0] == "denied"


def test_run_events_capture(tx):
    _, ap = agent(tx, "account-program")
    act(tx, ap)
    run = start_run(tx)
    assert scalar(tx, "select public.record_run_event(%s,'tool_call','get_account_context','{\"company_id\": 1}')", (run,)) == 1
    assert scalar(tx, "select public.record_run_event(%s,'tool_result','get_account_context','{}')", (run,)) == 2
    tx.execute("select public.end_run(%s,'completed','file://transcript.json',1200,300)", (run,))
    assert attempt(tx, "select public.record_run_event(%s,'tool_call','x','{}')", (run,))[0] == "denied"   # closed runs take no events
