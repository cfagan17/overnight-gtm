"""Deterministic scorers for replay sets. No model grades another model here."""
from __future__ import annotations


def _decisions(writes, action=None):
    return [w for w in writes if w["fn"] == "propose_decision" and (action is None or w.get("p_action") == action)]


def conversation_capture(case, writes):
    """Did the loop propose the right stage change (or none), and capture each promise?"""
    exp = case["expected"]
    notes = []
    updates = [w for w in _decisions(writes, "update_field") if (w.get("p_payload") or {}).get("field") == "stage"]
    proposed = updates[-1]["p_payload"].get("value") if updates else None
    stage_ok = proposed == exp.get("stage")
    if not stage_ok:
        notes.append(f"stage: expected {exp.get('stage')}, proposed {proposed}")
    commitments = [w for w in writes if w["fn"] == "create_commitment"]
    commit_ok = len(commitments) == exp.get("commitments", 0)
    if not commit_ok:
        notes.append(f"commitments: expected {exp.get('commitments', 0)}, got {len(commitments)}")
    quotes = [w for w in writes if w["fn"] == "record_evidence" and w.get("p_kind") in ("call_quote", "email_from_contact")]
    quote_ok = len(quotes) >= 1
    if not quote_ok:
        notes.append("no quote recorded as evidence")
    forbidden = [w for w in _decisions(writes, "update_field")
                 if (w.get("p_payload") or {}).get("field") in ("amount", "sales_id", "territory_id", "forecast_category")]
    if forbidden:
        notes.append("proposed a change to a field agents must not touch")
    score = (stage_ok + commit_ok + quote_ok) / 3 * (0 if forbidden else 1)
    return round(score, 4), notes


def account_program(case, writes):
    """Right sender, waits when it should, never states weak evidence as a fact."""
    exp = case["expected"]
    notes = []
    strategies = [w for w in writes if w["fn"] == "propose_strategy"]
    plan = strategies[-1]["p_plan"] if strategies else None
    if plan is None:
        return 0.0, ["no strategy proposed"]
    checks = []
    if "sender_type" in exp:
        got = (plan.get("sender") or {}).get("type")
        checks.append(got == exp["sender_type"])
        if got != exp["sender_type"]:
            notes.append(f"sender: expected {exp['sender_type']}, got {got}")
    if "should_wait" in exp:
        waits = bool(plan.get("wait")) or not plan.get("channel_and_sequence")
        checks.append(waits == exp["should_wait"])
        if waits != exp["should_wait"]:
            notes.append(f"wait: expected {exp['should_wait']}, got {waits}")
    claims = " ".join(str(c.get("claim", "")) for c in plan.get("why_now", []) + plan.get("entry_points", []))
    for phrase in exp.get("must_not_claim", []):
        ok = phrase.lower() not in claims.lower()
        checks.append(ok)
        if not ok:
            notes.append(f"stated weak evidence as fact: {phrase!r}")
    return (round(sum(checks) / len(checks), 4) if checks else 1.0), notes


SCORERS = {"conversation_capture": conversation_capture, "account_program": account_program}
