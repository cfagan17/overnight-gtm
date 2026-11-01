#!/usr/bin/env python3
"""Run one loop once, as its agent.

  # live model, over Supabase's REST API (production shape)
  python agents/runtime/runner.py --loop account_program --input '{"company_id": 1}' \
      --supabase-url "$SUPABASE_URL" --anon-key "$SUPABASE_ANON_KEY" --jwt "$AGENT_JWT" \
      --model claude-opus-4-1      # any Anthropic model id; needs ANTHROPIC_API_KEY

  # scripted tool calls, over a direct Postgres connection (tests, demos, CI)
  python agents/runtime/runner.py --loop account_program --input '{"company_id": 1}' \
      --dsn "$DATABASE_URL" --agent-uid <agent auth uuid> --scripted examples/scripts/account_program.json

Every model turn, tool call and tool result is written to run_events through
record_run_event (the capture hook), and the transcript is saved to --transcripts.
Refused tool calls are returned to the model as errors, so it can adjust or escalate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import time

import yaml

HERE = pathlib.Path(__file__).resolve().parent
AGENTS = HERE.parent
sys.path.insert(0, str(HERE))
from tools import CASTS, JSON_ARGS, TOOLS, anthropic_tools, rpc_args  # noqa: E402

SETOF = {"search_evidence"}


class ToolRefused(Exception):
    pass


# Transports ------------------------------------------------------------------------

class DbTransport:
    """Direct Postgres connection that acts as the agent the way Supabase's API does."""

    def __init__(self, dsn: str, agent_uid: str):
        import psycopg
        self.psycopg = psycopg
        self.conn = psycopg.connect(dsn)
        self.uid = agent_uid
        self._types: dict[str, dict] = {}

    def _arg_types(self, fn: str) -> dict:
        if fn not in self._types:
            with self.conn.transaction():
                rows = self.conn.execute(
                    "select x.n, format_type(x.t, null) from pg_proc p join pg_namespace s on s.oid = p.pronamespace, "
                    "unnest(p.proargnames, p.proargtypes::oid[]) as x(n, t) where s.nspname = 'public' and p.proname = %s",
                    (fn,)).fetchall()
            self._types[fn] = dict(rows)
        return self._types[fn]

    def _call(self, fn: str, args: dict, setof: bool = False):
        from psycopg.types.json import Jsonb
        parts, params = [], {}
        types = self._arg_types(fn)
        for k, v in args.items():
            cast = types.get(k) or CASTS.get(k)
            parts.append(f"{k} => %({k})s" + (f"::{cast}" if cast else ""))
            params[k] = Jsonb(v) if k in JSON_ARGS else v
        call = f"public.{fn}({', '.join(parts)})"
        sql = f"select coalesce(jsonb_agg(to_jsonb(r)), '[]') from {call} r" if setof else f"select to_jsonb({call})"
        try:
            with self.conn.transaction():
                self.conn.execute("set local role authenticated")
                self.conn.execute("select set_config('request.jwt.claims', %s, true)",
                                  (json.dumps({"sub": self.uid, "role": "authenticated"}),))
                return self.conn.execute(sql, params).fetchone()[0]
        except (self.psycopg.errors.InsufficientPrivilege, self.psycopg.errors.RaiseException) as exc:
            raise ToolRefused(str(exc).splitlines()[0]) from None

    def rpc(self, fn: str, args: dict, setof: bool = False):
        return self._call(fn, args, setof)

    def my_definition(self) -> dict:
        with self.conn.transaction():
            self.conn.execute("set local role authenticated")
            self.conn.execute("select set_config('request.jwt.claims', %s, true)",
                              (json.dumps({"sub": self.uid, "role": "authenticated"}),))
            row = self.conn.execute(
                "select to_jsonb(d) from public.agent_definitions d where d.id = ea_private.current_agent_definition_id()").fetchone()
            return row[0] if row else {}


class RestTransport:
    """Supabase REST (PostgREST) with the agent's own JWT."""

    def __init__(self, url: str, anon_key: str, jwt: str):
        import requests
        self.requests = requests
        self.url = url.rstrip("/")
        self.headers = {"apikey": anon_key, "Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}

    def rpc(self, fn: str, args: dict, setof: bool = False):
        r = self.requests.post(f"{self.url}/rest/v1/rpc/{fn}", headers=self.headers, data=json.dumps(args), timeout=60)
        if r.status_code in (401, 403) or (r.status_code >= 400 and "ea:" in r.text):
            raise ToolRefused(r.json().get("message", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text)
        r.raise_for_status()
        return r.json() if r.text else None

    def my_definition(self) -> dict:
        r = self.requests.get(f"{self.url}/rest/v1/agent_definitions?select=*", headers=self.headers, timeout=30)
        r.raise_for_status()
        rows = r.json()
        return rows[0] if len(rows) == 1 else {}


# Model clients ------------------------------------------------------------------------

class AnthropicClient:
    def __init__(self, model: str, api_key: str | None = None, max_tokens: int = 4096):
        import requests
        self.requests = requests
        self.model = model
        self.key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.key:
            raise SystemExit("ANTHROPIC_API_KEY is not set")
        self.max_tokens = max_tokens
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    def turn(self, system: str, messages: list, tools: list) -> list:
        r = self.requests.post("https://api.anthropic.com/v1/messages", timeout=300,
                               headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                               json={"model": self.model, "max_tokens": self.max_tokens, "system": system,
                                     "messages": messages, "tools": tools})
        r.raise_for_status()
        body = r.json()
        for k in self.usage:
            self.usage[k] += body.get("usage", {}).get(k, 0)
        return body["content"]


class ScriptedClient:
    """Plays a fixed sequence of tool calls, as if a model had chosen them.

    Script format: {"steps": [{"tool": "...", "input": {...}, "save_as": "name"}], "final": "summary"}
    Inputs may reference earlier results: "${name}" (whole result) or "${name.field}".
    Used to test the contract end to end. It says nothing about model quality.
    """

    model = "scripted"

    def __init__(self, script: dict):
        self.steps = list(script["steps"])
        self.final = script.get("final", "Scripted run complete.")
        self.saved: dict = {}
        self.i = 0
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    def _resolve(self, v):
        if isinstance(v, str):
            m = re.fullmatch(r"\$\{([a-zA-Z0-9_]+)(?:\.([a-zA-Z0-9_\.]+))?\}", v)
            if m:
                val = self.saved[m.group(1)]
                for part in (m.group(2) or "").split(".") if m.group(2) else []:
                    val = val[int(part)] if isinstance(val, list) else val[part]
                return val
            return re.sub(r"\$\{([a-zA-Z0-9_]+)\}", lambda mm: str(self.saved[mm.group(1)]), v)
        if isinstance(v, list):
            return [self._resolve(x) for x in v]
        if isinstance(v, dict):
            return {k: self._resolve(x) for k, x in v.items()}
        return v

    def turn(self, system, messages, tools):
        if self.i == 0:
            self.saved["input"] = json.loads(messages[0]["content"]).get("input", {})
        last = messages[-1]
        if last["role"] == "user" and isinstance(last["content"], list):
            for block in last["content"]:
                if block.get("type") == "tool_result" and self.i > 0:
                    name = self.steps[self.i - 1].get("save_as")
                    if name:
                        self.saved[name] = json.loads(block["content"]) if not block.get("is_error") else None
        if self.i >= len(self.steps):
            return [{"type": "text", "text": self.final}]
        step = self.steps[self.i]
        self.i += 1
        return [{"type": "tool_use", "id": f"step{self.i}", "name": step["tool"], "input": self._resolve(step["input"])}]


# The loop ------------------------------------------------------------------------------

def load_loop(name: str) -> dict:
    d = AGENTS / "loops" / name
    spec = yaml.safe_load((d / "loop.yaml").read_text())
    spec["prompt_text"] = (AGENTS / "loops" / "_shared.md").read_text() + "\n\n" + (d / spec["prompt"]).read_text()
    spec["skill_texts"] = {s: (AGENTS / "skills" / f"{s}.md").read_text() for s in spec["skills"]}
    return spec


def run_loop(loop_name: str, transport, client, loop_input: dict, max_turns: int = 30,
             transcripts: pathlib.Path | None = None, trigger: str | None = None, today: str | None = None) -> dict:
    spec = load_loop(loop_name)
    skill_versions = {s: "file:" + hashlib.sha256(t.encode()).hexdigest()[:8] for s, t in spec["skill_texts"].items()}
    definition = transport.my_definition()
    run_id = transport.rpc("start_run", {"p_model": client.model, "p_prompt_version": spec["prompt_version"],
                                         "p_skill_versions": skill_versions, "p_trigger": trigger or "manual"})
    system = spec["prompt_text"] + "\n\n# Skills\n\n" + "\n\n".join(spec["skill_texts"].values())
    context = {"run_context": {"loop": loop_name, "autonomy_level": definition.get("autonomy_level"),
                               "today": today or dt.date.today().isoformat()}, "input": loop_input}
    messages = [{"role": "user", "content": json.dumps(context, indent=2)}]
    tools = anthropic_tools(spec["tools"])
    events = []

    def event(kind, name, payload):
        events.append({"type": kind, "name": name, "payload": payload})
        try:
            transport.rpc("record_run_event", {"p_run_id": run_id, "p_event_type": kind, "p_name": name, "p_payload": payload})
        except ToolRefused:
            pass

    status, summary = "completed", ""
    try:
        for _ in range(max_turns):
            content = client.turn(system, messages, tools)
            messages.append({"role": "assistant", "content": content})
            event("model_turn", None, {"content": content})
            uses = [b for b in content if b.get("type") == "tool_use"]
            if not uses:
                summary = " ".join(b.get("text", "") for b in content if b.get("type") == "text")
                break
            results = []
            for u in uses:
                event("tool_call", u["name"], u["input"])
                if u["name"] not in spec["tools"]:
                    out, err = f"tool {u['name']} is not part of this loop", True
                else:
                    try:
                        args = rpc_args(u["name"], u["input"])
                        args[TOOLS[u["name"]]["run_arg"]] = run_id
                        out, err = json.dumps(transport.rpc(TOOLS[u["name"]]["rpc"], args, u["name"] in SETOF), default=str), False
                    except ToolRefused as exc:
                        out, err = f"refused: {exc}", True
                event("tool_result", u["name"], {"is_error": err, "content": out[:4000]})
                results.append({"type": "tool_result", "tool_use_id": u["id"], "content": out, "is_error": err})
            messages.append({"role": "user", "content": results})
        else:
            status, summary = "failed", "max turns reached"
    except Exception as exc:  # record the failure on the run, then re-raise
        status, summary = "failed", f"{type(exc).__name__}: {exc}"
        event("error", None, {"message": summary})
        raise
    finally:
        uri = None
        if transcripts:
            transcripts.mkdir(parents=True, exist_ok=True)
            path = transcripts / f"run-{run_id}-{int(time.time())}.json"
            path.write_text(json.dumps({"run_id": run_id, "loop": loop_name, "system": system, "messages": messages}, indent=2, default=str))
            uri = path.resolve().as_uri()
        transport.rpc("end_run", {"p_run_id": run_id, "p_status": status, "p_transcript_uri": uri,
                                  "p_tokens_in": client.usage["input_tokens"], "p_tokens_out": client.usage["output_tokens"]})
    return {"run_id": run_id, "status": status, "summary": summary, "events": events}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--loop", required=True)
    ap.add_argument("--input", default="{}")
    ap.add_argument("--dsn")
    ap.add_argument("--agent-uid")
    ap.add_argument("--supabase-url")
    ap.add_argument("--anon-key")
    ap.add_argument("--jwt")
    ap.add_argument("--model")
    ap.add_argument("--scripted")
    ap.add_argument("--transcripts", default="runs")
    a = ap.parse_args()
    if a.dsn:
        transport = DbTransport(a.dsn, a.agent_uid)
    else:
        transport = RestTransport(a.supabase_url, a.anon_key, a.jwt)
    client = ScriptedClient(json.loads(pathlib.Path(a.scripted).read_text())) if a.scripted else AnthropicClient(a.model)
    out = run_loop(a.loop, transport, client, json.loads(a.input), transcripts=pathlib.Path(a.transcripts))
    print(json.dumps({k: v for k, v in out.items() if k != "events"}, indent=2))


if __name__ == "__main__":
    main()
