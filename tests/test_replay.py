"""The replay harness scores what a loop wrote, and enforces the citation rules offline."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "agents" / "runtime"))
from replay import replay  # noqa: E402
from runner import ScriptedClient  # noqa: E402


def plan_script(sender, claim, ev, wait=False):
    plan = {"why_now": [{"claim": claim, "evidence": [ev]}], "sender": {"type": sender}}
    plan["channel_and_sequence"] = [] if wait else [{"step": 1, "channel": "email", "purpose": "intro"}]
    if wait:
        plan["wait"] = True
    return {"steps": [
        {"tool": "get_account_context", "input": {"company_id": 101}, "save_as": "ctx"},
        {"tool": "propose_decision", "input": {"action": "propose_strategy", "subject_type": "company", "subject_id": "101",
                                               "rationale": "Plan for this account", "evidence_ids": [ev]}, "save_as": "d"},
        {"tool": "propose_strategy", "input": {"decision_id": "${d}", "subject_type": "company", "subject_id": "101", "plan": plan}},
    ]}


GOOD = {"ap-01": plan_script("rep", "Trial projects doubled", 1), "ap-02": plan_script("partner", "Attended partner webinar", 4),
        "ap-03": plan_script("rep", "No strong signal yet", 5, wait=True), "ap-04": plan_script("rep", "Asked for help", 7),
        "ap-05": plan_script("rep", "Nothing strong yet", 8, wait=True)}
BAD = dict(GOOD, **{"ap-01": plan_script("agent", "They hired a new CTO", 2), "ap-02": plan_script("rep", "Evaluating", 3)})


def test_good_plans_score_full_marks():
    r = replay("account_program_v1", lambda case: ScriptedClient(GOOD[case["id"]]))
    assert r["score"] == 1.0, r


def test_bad_plans_lose_points_for_the_right_reasons():
    r = replay("account_program_v1", lambda case: ScriptedClient(BAD[case["id"]]))
    notes = {x["case"]: x["notes"] for x in r["results"]}
    assert r["score"] < 1.0
    assert any("new CTO" in n for n in notes["ap-01"]) and any("sender" in n for n in notes["ap-02"])


def test_replay_refuses_uncited_evidence():
    script = plan_script("rep", "Made up", 424242)
    r = replay("account_program_v1", lambda case: ScriptedClient(script))
    assert r["score"] == 0.0       # the decision is refused, so no strategy is ever proposed
