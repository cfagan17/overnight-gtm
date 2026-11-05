"""0009: versioned loop prompts, insight views, and the Slack review path."""
import json

import pytest

from helpers import ANA, CY, OWNER, agent_uid, attempt, scalar


def act(conn, uid):
    conn.execute("set local role authenticated")
    conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": uid, "role": "authenticated"}),))


def as_service(conn):
    conn.execute("reset role")
    conn.execute("set local role service_role")
    conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": "service_role"}),))


def agent(conn, name):
    row = conn.execute("select id from public.agent_definitions where name = %s", (name,)).fetchone()
    return row[0], agent_uid(row[0])


@pytest.fixture()
def tx(conn):
    with conn.transaction(force_rollback=True):
        yield conn


def queued_decision(tx):
    """An account-program decision on Acme Orchards (Ana's account), waiting for review."""
    _, ap = agent(tx, "account-program")
    company = scalar(tx, "select id from public.companies where name = 'Acme Orchards'")
    act(tx, ap)
    run = scalar(tx, "select public.start_run('test-model', 'v1', '{}'::jsonb, 'test')")
    ev = scalar(tx, "select public.record_evidence(%s,'company',%s,'product_usage','Usage doubled','telemetry://acme/x',now())", (run, str(company)))
    return scalar(tx, "select public.propose_decision(%s,'propose_strategy','company',%s,'Usage doubled, propose a plan',array[%s]::bigint[],'{}'::jsonb)",
                  (run, str(company), ev))


def test_owner_proposes_and_approves_prompt_versions(tx):
    act(tx, OWNER)
    v1 = scalar(tx, "select public.propose_prompt_version('account_program', 'You write the approach plan for one account. Version one.', 'first')")
    tx.execute("select public.approve_prompt('account_program', %s)", (v1,))
    v2 = scalar(tx, "select public.propose_prompt_version('account_program', 'You write the approach plan for one account. Version two.', 'tighter')")
    assert v2 == v1 + 1
    assert scalar(tx, "select version from public.get_loop_prompt('account_program')") == v1
    tx.execute("select public.approve_prompt('account_program', %s)", (v2,))
    assert scalar(tx, "select version from public.get_loop_prompt('account_program')") == v2
    assert scalar(tx, "select status from public.loop_prompts where \"loop\" = 'account_program' and version = %s", (v1,)) == "retired"
    assert attempt(tx, "select public.approve_prompt('account_program', %s)", (v2,))[0] == "denied"   # already approved


def test_only_owners_change_prompts_and_agents_read_only_their_own(tx):
    act(tx, OWNER)
    tx.execute("select public.propose_prompt_version('account_program', 'Account program prompt body, approved.')")
    tx.execute("select public.approve_prompt('account_program', 1)")
    tx.execute("select public.propose_prompt_version('outreach', 'Outreach prompt body, approved for the test.')")
    tx.execute("select public.approve_prompt('outreach', 1)")
    act(tx, ANA)
    assert attempt(tx, "select public.propose_prompt_version('account_program', 'A rep tries to change the prompt.')")[0] == "denied"
    assert attempt(tx, "insert into public.loop_prompts (\"loop\", version, body, proposed_by) values ('outreach', 9, 'direct insert by a rep', %s)", (ANA,))[0] == "denied"
    assert scalar(tx, "select count(*) from public.loop_prompts") == 2          # people read every prompt
    _, ap = agent(tx, "account-program")
    act(tx, ap)
    assert scalar(tx, "select count(*) from public.loop_prompts") == 1          # an agent reads only its own loop
    assert scalar(tx, "select count(*) from public.get_loop_prompt('outreach')") == 0
    assert attempt(tx, "select public.propose_prompt_version('account_program', 'An agent rewrites its own prompt.')")[0] == "denied"


def test_insight_views_respect_visibility(tx):
    d = queued_decision(tx)
    act(tx, ANA)
    tx.execute("select public.review_decision(%s, 'edited', 'Send it from me', '{\"sender\": \"rep\"}'::jsonb)", (d,))
    assert scalar(tx, "select reviewed from public.insight_overrides where \"loop\" = 'account_program'") == 1
    assert scalar(tx, "select in_edited from public.insight_evidence_in_reviews where kind = 'product_usage'") == 1
    act(tx, CY)                                                                   # an East rep cannot see West decisions
    assert scalar(tx, "select count(*) from public.insight_overrides") == 0


def test_slack_review_acts_as_the_mapped_person(tx):
    d = queued_decision(tx)
    tx.execute("reset role")
    tx.execute("insert into public.slack_user_map (slack_user_id, user_id) values ('U0ANA', %s), ('U0CY', %s)", (ANA, CY))
    as_service(tx)
    queue = tx.execute("select decision_id from public.slack_review_queue('U0ANA')").fetchall()
    assert (d,) in queue
    assert tx.execute("select count(*) from public.slack_review_queue('U0CY')").fetchone()[0] == 0     # Cy cannot review West
    assert attempt(tx, "select public.slack_review_decision('U0CY', %s, 'accepted')", (d,))[0] == "denied"
    assert attempt(tx, "select public.slack_review_decision('U0NOBODY', %s, 'accepted')", (d,))[0] == "denied"
    assert attempt(tx, "select public.slack_review_decision('U0ANA', %s, 'edited')", (d,))[0] == "denied"
    assert scalar(tx, "select public.slack_review_decision('U0ANA', %s, 'accepted')", (d,)) is not None
    tx.execute("reset role")
    row = tx.execute("select review_outcome, reviewed_by::text, review_note from public.decisions where id = %s", (d,)).fetchone()
    assert row == ("accepted", ANA, "Reviewed in Slack")


def test_signed_in_users_cannot_use_the_slack_functions(tx):
    d = queued_decision(tx)
    act(tx, ANA)
    assert attempt(tx, "select * from public.slack_review_queue('U0ANA')")[0] == "denied"
    assert attempt(tx, "select public.slack_review_decision('U0ANA', %s, 'accepted')", (d,))[0] == "denied"
    assert attempt(tx, "insert into public.slack_user_map (slack_user_id, user_id) values ('U0EVIL', %s)", (OWNER,))[0] == "denied"


def test_review_queue_shows_what_each_person_may_review(tx):
    d = queued_decision(tx)
    act(tx, ANA)
    assert d in [r[0] for r in tx.execute("select decision_id from public.review_queue()").fetchall()]
    act(tx, CY)
    assert d not in [r[0] for r in tx.execute("select decision_id from public.review_queue()").fetchall()]
    _, ap = agent(tx, "account-program")
    act(tx, ap)
    assert attempt(tx, "select * from public.review_queue()")[0] == "denied"


def test_reps_cannot_sign_off_their_own_comp(tx):
    did, cuid = agent(tx, "comp-ops")
    deal = scalar(tx, "select d.id from public.deals d join public.companies c on c.id = d.company_id where c.name = 'Acme Orchards'")
    tx.execute("reset role")
    d = scalar(tx, "insert into public.decisions (made_by, \"loop\", action, subject_type, subject_id, rationale, autonomy_level, status) "
                   "values (%s, 'comp_ops', 'propose_credit', 'deal', %s, 'Full credit to the account owner.', 1, 'proposed') returning id", (cuid, str(deal)))
    act(tx, ANA)                                                                   # Ana owns the deal, and would be paid on it
    assert d not in [r[0] for r in tx.execute("select decision_id from public.review_queue()").fetchall()]
    assert attempt(tx, "select public.review_decision(%s, 'accepted')", (d,))[0] == "denied"
    act(tx, OWNER)
    assert d in [r[0] for r in tx.execute("select decision_id from public.review_queue()").fetchall()]
    assert scalar(tx, "select public.review_decision(%s, 'accepted')", (d,)) is not None


def test_everyone_can_see_that_loops_ran_without_seeing_runs(tx):
    did, auid = agent(tx, "account-program")
    tx.execute("reset role")
    tx.execute("insert into public.runs (agent_definition_id, principal_id, \"loop\", model, prompt_version, skill_versions, autonomy_level, "
               "trigger, status, started_at) values (%s, %s, 'account_program', 'claude-test', 'v1', '{}', 1, 'nightly', 'completed', now() - interval '2 hours')",
               (did, auid))
    act(tx, CY)                                                                    # a rep: run rows are not theirs to read
    assert scalar(tx, "select count(*) from public.runs") == 0
    row = tx.execute("select runs_36h, model from public.loop_activity() where \"loop\" = 'account_program'").fetchone()
    assert row[0] >= 1 and row[1] == "claude-test"
    act(tx, auid)
    assert attempt(tx, "select * from public.loop_activity()")[0] == "denied"
