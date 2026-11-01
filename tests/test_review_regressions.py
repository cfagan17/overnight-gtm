"""Regression tests for every confirmed finding of the independent review (docs/review-2026-11-01.md).

Each test reproduces the reviewer's attack and asserts it is now refused.
"""
import json

import psycopg
import pytest

from helpers import ANA, FIN, OWNER, agent_uid, attempt, scalar


def act(c, uid):
    c.execute("set local role authenticated")
    c.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": uid, "role": "authenticated"}),))


def su(c):
    c.execute("reset role")
    c.execute("select set_config('request.jwt.claims', '', true)")


def level(c, name, n):
    su(c)
    c.execute("select set_config('ea.promotion_in_progress', 'on', true)")
    c.execute("update public.agent_definitions set autonomy_level = %s where name = %s", (n, name))
    c.execute("select set_config('ea.promotion_in_progress', '', true)")


def aid(c, name):
    su(c)
    return scalar(c, "select id from public.agent_definitions where name = %s", (name,))


@pytest.fixture()
def tx(conn):
    with conn.transaction(force_rollback=True):
        yield conn


def deal_of(c, company):
    su(c)
    return scalar(c, "select d.id from public.deals d join public.companies co on co.id = d.company_id where co.name = %s", (company,))


def test_1_execute_field_update_is_not_callable(tx):
    ap = agent_uid(aid(tx, "account-program"))
    for uid in (ap, ANA):
        act(tx, uid)
        st, msg, _ = attempt(tx, "select ea_private.execute_field_update(1, '\"lost\"')")
        assert st == "denied" and "permission denied" in msg


def test_2_payload_row_must_match_checked_row(tx):
    cap_id = aid(tx, "conversation-capture")
    level(tx, "conversation-capture", 3)
    mine, other = deal_of(tx, "Acme Orchards"), deal_of(tx, "Maple Ledger")
    act(tx, agent_uid(cap_id))
    run = scalar(tx, "select public.start_run('m','v1')")
    ev = scalar(tx, "select public.record_evidence(%s,'deal',%s,'call_quote','They said so','gong://x/1',now())", (run, str(mine)))
    d = scalar(tx, "select public.propose_decision(%s,'update_field','deal',%s,'rationale long enough', array[%s]::bigint[], %s::jsonb)",
               (run, str(mine), ev, json.dumps({"table": "deals", "field": "stage", "row_id": other, "value": "lost"})))
    assert attempt(tx, "select public.apply_field_update(%s,%s,'deals',%s,'stage','\"lost\"')", (run, d, mine))[0] == "denied"
    su(tx)
    assert scalar(tx, "select stage from public.deals where id = %s", (other,)) != "lost"


def test_3_agents_cannot_mint_strong_evidence_or_borrow_it(tx):
    cap_id = aid(tx, "conversation-capture")
    level(tx, "conversation-capture", 3)
    a, b = deal_of(tx, "Acme Orchards"), deal_of(tx, "Bluebird Freight")
    act(tx, agent_uid(cap_id))
    run = scalar(tx, "select public.start_run('m','v1')")
    fake = scalar(tx, "select public.record_evidence(%s,'deal',%s,'call_quote','Made up quote','https://anything',now())", (run, str(a)))
    assert tx.execute("select strength, downgraded from public.evidence where id = %s", (fake,)).fetchone() == ("weak", True)
    real_a = scalar(tx, "select public.record_evidence(%s,'deal',%s,'call_quote','Quote about A','gong://call/9',now())", (run, str(a)))
    d = scalar(tx, "select public.propose_decision(%s,'update_field','deal',%s,'Using evidence about another deal', array[%s]::bigint[], %s::jsonb)",
               (run, str(b), real_a, json.dumps({"table": "deals", "field": "stage", "row_id": b, "value": "lost"})))
    assert attempt(tx, "select public.apply_field_update(%s,%s,'deals',%s,'stage','\"lost\"')", (run, d, b))[0] == "denied"


def test_4_audit_log_does_not_leak_masked_fields(tx):
    act(tx, FIN)
    assert scalar(tx, "select count(*) from public.audit_log where table_name = 'deal_lines'") > 0
    assert scalar(tx, "select count(*) from public.audit_log where table_name in ('deal_lines','partners') "
                      "and (after ? 'discount_pct' or after ? 'margin_pct' or before ? 'discount_pct' or before ? 'margin_pct')") == 0


def test_5_supersede_rules(tx):
    ap = agent_uid(aid(tx, "account-program"))
    deal = deal_of(tx, "Acme Orchards")
    act(tx, ANA)
    human = scalar(tx, "select public.record_evidence(null,'deal',%s,'rep_observation','Buyer said budget is cut','note://1',now())", (str(deal),))
    act(tx, ap)
    run = scalar(tx, "select public.start_run('m','v1')")
    assert attempt(tx, "select public.supersede_evidence(%s,%s,%s)", (run, human, human))[0] == "denied"
    newer = scalar(tx, "select public.record_evidence(%s,'deal',%s,'web_page','Budget fine per blog','https://x',now())", (run, str(deal)))
    assert attempt(tx, "select public.supersede_evidence(%s,%s,%s)", (run, human, newer))[0] == "denied"


def test_6_reviews_need_edit_rights(tx):
    tc = agent_uid(aid(tx, "territory-capacity"))
    act(tx, tc)
    run = scalar(tx, "select public.start_run('m','v1')")
    ev = scalar(tx, "select public.record_evidence(%s,'territory','4','crm_record','East is under-covered','crm://report/2',now())", (run,))
    d = scalar(tx, "select public.propose_decision(%s,'propose_strategy','territory','4','Rebalance East coverage', array[%s]::bigint[])", (run, ev))
    s = scalar(tx, "select public.propose_strategy(%s,%s,'territory','4','{}'::jsonb)", (run, d))
    act(tx, ANA)
    assert attempt(tx, "select public.review_decision(%s,'accepted')", (d,))[0] == "denied"
    act(tx, OWNER)
    assert scalar(tx, "select public.review_decision(%s,'accepted')", (d,)) == "approved"
    act(tx, ANA)
    assert attempt(tx, "select public.activate_strategy(%s)", (s,))[0] == "denied"


def test_7_running_experiments_are_frozen(tx):
    act(tx, OWNER)
    ids = [r[0] for r in tx.execute("select id::text from public.companies").fetchall()]
    tx.execute("select public.assign_experiment(1, %s)", (ids,))
    tx.execute("select public.start_experiment(1)")
    assert attempt(tx, "update public.experiments set status = 'draft', holdout_pct = 99 where id = 1")[0] == "denied"
    assert attempt(tx, "update public.experiments set loop = 'nothing' where id = 1")[0] == "denied"
    assert attempt(tx, "update public.experiments set status = 'closed' where id = 1")[2] == 1
    tx.execute("select public.record_experiment_outcome(1, %s, 1)", (ids[0],))
    assert attempt(tx, "select public.record_experiment_outcome(1, %s, 0)", (ids[0],))[0] == "denied"


def test_8_rule_changes_are_audited_and_pay_loops_are_capped(tx):
    act(tx, OWNER)
    tx.execute("update public.promotion_rules set min_reviewed = 0 where to_level = 2")
    su(tx)
    assert scalar(tx, "select count(*) from public.audit_log where table_name = 'promotion_rules' and op = 'UPDATE'") == 1
    with pytest.raises(psycopg.errors.CheckViolation):
        with tx.transaction():
            tx.execute("update public.agent_definitions set max_autonomy = 4 where name = 'comp-ops'")


def test_9_agents_cannot_send_as_someone_else(tx):
    out_id = aid(tx, "outreach")
    level(tx, "outreach", 3)
    su(tx)
    contact = scalar(tx, "select ct.id from public.contacts ct where not exists (select 1 from public.deals d join public.deal_partners dp "
                         "on dp.deal_id = d.id where d.company_id = ct.company_id) order by ct.id limit 1")
    act(tx, agent_uid(out_id))
    run = scalar(tx, "select public.start_run('m','v1')")

    def touch(channel, sender):
        e = scalar(tx, "select public.record_evidence(%s,'contact',%s,'email_from_contact','Asked to talk','mail://9',now())", (run, str(contact)))
        d = scalar(tx, "select public.propose_decision(%s,'schedule_touch','contact',%s,'Contact asked to talk', array[%s]::bigint[])", (run, str(contact), e))
        return scalar(tx, "select public.schedule_touch(%s,%s,%s,%s,%s,'hi')", (run, d, contact, channel, sender))

    assert touch("email", "agent")["status"] == "scheduled"
    assert touch("sms", "rep")["status"] == "pending_approval"        # the rep sends it, or nobody does


def test_10_reps_stay_inside_their_accounts_and_territories(tx):
    su(tx)
    east = scalar(tx, "select id from public.companies where name = 'Maple Ledger'")
    own = scalar(tx, "select id from public.companies where name = 'Acme Orchards'")
    act(tx, ANA)
    assert attempt(tx, "insert into public.deals (name, company_id, stage, amount) values ('injected', %s, 'opportunity', 9999999)", (east,))[0] == "denied"
    assert attempt(tx, "insert into public.contacts (first_name, last_name, company_id) values ('Fake','Person', %s)", (east,))[0] == "denied"
    assert attempt(tx, "update public.companies set territory_id = 4 where id = %s", (own,))[0] == "denied"
    st, rows, _ = attempt(tx, "insert into public.companies (name, state_abbr, segment, territory_id) values ('New Co','CA','enterprise',4) returning territory_id")
    assert st == "ok" and rows[0][0] == 2          # the rules decide, not the rep


def test_11_deactivated_principals_lose_access(tx):
    su(tx)
    tx.execute("update public.principals set active = false where user_id = %s", (OWNER,))
    act(tx, OWNER)
    assert scalar(tx, "select ea_private.current_role_name()") == "none"
    assert scalar(tx, "select count(*) from public.deals") == 0


def test_second_pass_loop_is_immutable(tx):
    act(tx, OWNER)
    assert attempt(tx, "update public.agent_definitions set loop = 'comp_ops_x' where name = 'comp-ops'")[0] == "denied"


def test_second_pass_agents_cannot_bury_integration_evidence(tx):
    ap = agent_uid(aid(tx, "account-program"))
    deal = deal_of(tx, "Acme Orchards")
    su(tx)
    tx.execute("set local role service_role")
    sev = scalar(tx, "insert into public.evidence (subject_type, subject_id, kind, claim, source_uri, observed_at, strength, recorded_by) "
                     "values ('deal', %s, 'call_quote', 'Buyer: budget cut', 'gong://c/9', now(), 'x', gen_random_uuid()) returning id", (str(deal),))
    act(tx, ap)
    run = scalar(tx, "select public.start_run('m','v1')")
    aev = scalar(tx, "select public.record_evidence(%s,'deal',%s,'web_page','Budget fine','https://x',now())", (run, str(deal)))
    assert attempt(tx, "select public.supersede_evidence(%s,%s,%s)", (run, sev, aev))[0] == "denied"


def test_second_pass_contacts_cannot_move_to_others_accounts(tx):
    su(tx)
    east = scalar(tx, "select id from public.companies where name = 'Maple Ledger'")
    mine = scalar(tx, "select ct.id from public.contacts ct join public.sales s on s.id = ct.sales_id where s.user_id = %s limit 1", (ANA,))
    act(tx, ANA)
    assert attempt(tx, "update public.contacts set company_id = %s where id = %s", (east, mine))[0] == "denied"


def test_second_pass_service_role_can_maintain_the_ledger(tx):
    su(tx)
    tx.execute("set local role service_role")
    assert attempt(tx, "insert into public.companies (name, state_abbr) values ('Svc Co', 'NY') returning id")[0] == "ok"


def test_second_pass_sources_can_refuse_agent_writes(tx):
    su(tx)
    tx.execute("update public.evidence_sources set agents_may_write = false where uri_prefix = 'gong://'")
    ap = agent_uid(aid(tx, "account-program"))
    deal = deal_of(tx, "Acme Orchards")
    act(tx, ap)
    run = scalar(tx, "select public.start_run('m','v1')")
    e = scalar(tx, "select public.record_evidence(%s,'deal',%s,'call_quote','A quote','gong://call/1',now())", (run, str(deal)))
    assert scalar(tx, "select strength from public.evidence where id = %s", (e,)) == "weak"
