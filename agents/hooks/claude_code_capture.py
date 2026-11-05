#!/usr/bin/env python3
"""Claude Code capture hook: record every tool call an agent session makes as run_events.

Use this when a loop runs inside Claude Code (or another harness with hooks) instead of
agents/runtime/runner.py. The session starts a run with start_run, exports its id, and
this hook sends each PreToolUse / PostToolUse event to record_run_event.

Environment:
  EA_SUPABASE_URL, EA_SUPABASE_ANON_KEY, EA_AGENT_JWT   the agent's own credentials
  EA_RUN_ID                                             the run this session belongs to

Hooks capture; they are not the security boundary. If this hook is misconfigured or
removed, the database functions still enforce every rule.
"""
import json
import os
import sys
import urllib.request


def main() -> int:
    event = json.load(sys.stdin)
    run_id = os.environ.get("EA_RUN_ID")
    if not run_id:
        return 0
    kind = {"PreToolUse": "tool_call", "PostToolUse": "tool_result"}.get(event.get("hook_event_name"), "hook")
    payload = {"tool_input": event.get("tool_input"), "tool_response": event.get("tool_response"),
               "session_id": event.get("session_id")}
    body = json.dumps({"p_run_id": int(run_id), "p_event_type": kind, "p_name": event.get("tool_name"),
                       "p_payload": payload}).encode()
    req = urllib.request.Request(f"{os.environ['EA_SUPABASE_URL'].rstrip('/')}/rest/v1/rpc/record_run_event", data=body,
                                 headers={"apikey": os.environ["EA_SUPABASE_ANON_KEY"],
                                          "Authorization": f"Bearer {os.environ['EA_AGENT_JWT']}",
                                          "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as exc:  # never block the agent because capture failed; say so on stderr
        print(f"overnight capture hook: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
