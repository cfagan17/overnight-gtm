"""The runner drives the agent contract end to end (scripted tool calls, no model)."""
import json
import pathlib
import sys

import psycopg
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents" / "runtime"))
from runner import DbTransport, ScriptedClient, load_loop, run_loop  # noqa: E402
from tools import TOOLS, anthropic_tools  # noqa: E402
from helpers import ADMIN_DSN, agent_uid, build  # noqa: E402


@pytest.fixture(scope="module")
def rdsn():
    return build(ADMIN_DSN, "ea_test_runtime", seed=True)


def ids(dsn, sql):
    with psycopg.connect(dsn) as c:
        return c.execute(sql).fetchone()


def test_every_loop_definition_loads_and_uses_known_tools():
    loops = [p.name for p in (ROOT / "agents/loops").iterdir() if p.is_dir()]
    assert len(loops) == 12
    for name in loops:
        spec = load_loop(name)
        assert set(spec["tools"]) <= set(TOOLS), name
        assert anthropic_tools(spec["tools"])
        assert spec["starting_level"] <= spec["max_level"]


def test_scripted_account_program(rdsn, tmp_path):
    company, def_id = ids(rdsn, "select c.id, (select id from public.agent_definitions where name='account-program') "
                                "from public.companies c where c.name = 'Acme Orchards'")
    script = json.loads((ROOT / "examples/scripts/account_program.json").read_text())
    out = run_loop("account_program", DbTransport(rdsn, agent_uid(def_id)), ScriptedClient(script),
                   {"company_id": company}, transcripts=tmp_path)
    assert out["status"] == "completed"
    errors = [e for e in out["events"] if e["type"] == "tool_result" and e["payload"]["is_error"]]
    assert errors == []
    with psycopg.connect(rdsn) as c:
        st = c.execute("select status, plan->'sender'->>'type' from public.strategies where subject_id = %s order by id desc limit 1",
                       (str(company),)).fetchone()
        assert st == ("proposed", "rep")
        run = c.execute("select status, model, transcript_uri is not null, (select count(*) from public.run_events e where e.run_id = r.id) "
                        "from public.runs r where id = %s", (out["run_id"],)).fetchone()
        assert run[0] == "completed" and run[1] == "scripted" and run[2] and run[3] >= 10


def test_scripted_capture_is_refused_at_level_1(rdsn, tmp_path):
    company, deal, def_id = ids(rdsn, "select c.id, d.id, (select id from public.agent_definitions where name='conversation-capture') "
                                      "from public.companies c join public.deals d on d.company_id = c.id where d.stage = 'proposal-sent' order by c.id limit 1")
    script = json.loads((ROOT / "examples/scripts/conversation_capture.json").read_text())
    out = run_loop("conversation_capture", DbTransport(rdsn, agent_uid(def_id)), ScriptedClient(script),
                   {"company_id": company, "deal_id": deal, "source_uri": "gong://call/123#17:20"}, transcripts=tmp_path)
    last = [e for e in out["events"] if e["type"] == "tool_result"][-1]
    assert last["name"] == "apply_field_update" and last["payload"]["is_error"]
    assert "needs autonomy level 2" in last["payload"]["content"]
    with psycopg.connect(rdsn) as c:
        assert c.execute("select count(*) from public.commitments where subject_id = %s", (str(company),)).fetchone()[0] == 1
        assert c.execute("select stage from public.deals where id = %s", (deal,)).fetchone()[0] != "in-negociation"


def test_runner_uses_the_approved_prompt_from_the_database(rdsn, tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    from load_prompts import load
    from helpers import OWNER
    with psycopg.connect(rdsn) as c:
        load(c, OWNER)
        c.execute("set local role authenticated")
        c.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": OWNER, "role": "authenticated"}),))
        v = c.execute("select public.propose_prompt_version('account_program', %s, 'test')",
                      ((ROOT / "agents/loops/account_program/prompt.md").read_text() + "\nMARKER-V2",)).fetchone()[0]
        c.execute("select public.approve_prompt('account_program', %s)", (v,))
    company, def_id = ids(rdsn, "select c.id, (select id from public.agent_definitions where name='account-program') "
                                "from public.companies c where c.name = 'Acme Orchards'")
    script = json.loads((ROOT / "examples/scripts/account_program.json").read_text())
    out = run_loop("account_program", DbTransport(rdsn, agent_uid(def_id)), ScriptedClient(script),
                   {"company_id": company}, transcripts=tmp_path)
    with psycopg.connect(rdsn) as c:
        assert c.execute("select prompt_version from public.runs where id = %s", (out["run_id"],)).fetchone()[0] == f"db:v{v}"
    transcript = json.loads(next(tmp_path.glob(f"run-{out['run_id']}-*.json")).read_text())
    assert "MARKER-V2" in transcript["system"]
