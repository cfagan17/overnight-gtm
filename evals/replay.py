#!/usr/bin/env python3
"""Replay evals: run a loop's prompt on a fixed set of past cases, offline, and score it.

  python evals/replay.py --set conversation_capture_v1 --model <anthropic model id> [--record --dsn ... --owner-uid ...]

No database writes happen during a replay. Reads return each case's recorded context;
writes are captured and scored. Run this for every loop when a new model, prompt or
skill version is a candidate, then record the score with --record so promotion_check
can see it (section 10 of the design: model upgrades become a promotion review).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agents" / "runtime"))
sys.path.insert(0, str(HERE))
from runner import AnthropicClient, ScriptedClient, ToolRefused, run_loop  # noqa: E402
from scorers import SCORERS  # noqa: E402


class ReplayTransport:
    """Answers reads from a recorded case and captures writes. Mirrors the database's
    citation rules so a replay cannot score well by citing evidence that does not exist."""

    def __init__(self, case: dict, autonomy_level: int):
        self.case = case
        self.level = autonomy_level
        self.next_id = 900000
        self.known_evidence = {e["id"] for e in case.get("context", {}).get("evidence", [])}
        self.writes: list[dict] = []
        self.decisions: dict[int, dict] = {}

    def _id(self):
        self.next_id += 1
        return self.next_id

    def my_definition(self):
        return {"autonomy_level": self.level}

    def rpc(self, fn, args, setof=False):
        if fn in ("start_run",):
            return 1
        if fn in ("end_run", "record_run_event"):
            return None
        if fn == "get_account_context":
            return self.case["context"]
        if fn == "search_evidence":
            return [e for e in self.case["context"].get("evidence", [])
                    if e.get("subject_type", "company") == args.get("p_subject_type")] or self.case["context"].get("evidence", [])
        if fn == "get_policies":
            return self.case.get("policies", {"policies": []})
        if fn == "record_evidence":
            new = self._id()
            self.known_evidence.add(new)
            self.writes.append({"fn": fn, "id": new, **args})
            return new
        if fn == "propose_decision":
            cited = args.get("p_evidence_ids") or []
            if not cited or any(int(e) not in self.known_evidence for e in cited):
                raise ToolRefused("ea: a decision must cite existing evidence ids")
            new = self._id()
            self.decisions[new] = args
            self.writes.append({"fn": fn, "id": new, **args})
            return new
        if fn == "propose_strategy":
            d = self.decisions.get(int(args["p_decision_id"])) if args.get("p_decision_id") is not None else None
            if d is None:
                raise ToolRefused("ea: decision not from this run")
            plan_ids = _evidence_ids(args.get("p_plan"))
            if not plan_ids <= {int(x) for x in d.get("p_evidence_ids", [])}:
                raise ToolRefused("ea: plan cites evidence ids the decision does not")
            self.writes.append({"fn": fn, "id": self._id(), **args})
            return self.next_id
        if fn == "apply_field_update":
            if self.level < 2:
                raise ToolRefused("ea: apply_field_update needs autonomy level 2")
            self.writes.append({"fn": fn, **args})
            return "applied" if self.level >= 3 else "queued"
        self.writes.append({"fn": fn, **args})
        return self._id()


def _evidence_ids(obj) -> set[int]:
    out: set[int] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "evidence" and isinstance(v, list):
                out |= {int(x) for x in v}
            else:
                out |= _evidence_ids(v)
    elif isinstance(obj, list):
        for x in obj:
            out |= _evidence_ids(x)
    return out


def replay(set_name: str, client_factory, autonomy_level: int = 3) -> dict:
    d = HERE / "sets" / set_name
    meta = json.loads((d / "set.json").read_text())
    cases = [json.loads(line) for line in (d / "cases.jsonl").read_text().splitlines() if line.strip()]
    scorer = SCORERS[meta["scorer"]]
    results = []
    for case in cases:
        t = ReplayTransport(case, autonomy_level)
        run_loop(meta["loop"], t, client_factory(case), case["input"], transcripts=None, trigger="replay", today=case.get("today"))
        score, notes = scorer(case, t.writes)
        results.append({"case": case["id"], "score": score, "notes": notes})
    return {"set": set_name, "loop": meta["loop"], "cases": len(results),
            "score": round(sum(r["score"] for r in results) / len(results), 4), "results": results}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", required=True)
    ap.add_argument("--model")
    ap.add_argument("--scripted-dir", help="directory of <case id>.json scripts (for testing the harness)")
    ap.add_argument("--level", type=int, default=3, help="autonomy level to replay at (3 lets write paths be scored)")
    a = ap.parse_args()
    if a.scripted_dir:
        factory = lambda case: ScriptedClient(json.loads((pathlib.Path(a.scripted_dir) / f"{case['id']}.json").read_text()))  # noqa: E731
    else:
        factory = lambda case: AnthropicClient(a.model)  # noqa: E731
    print(json.dumps(replay(a.set, factory, a.level), indent=2))


if __name__ == "__main__":
    main()
