"""The Slack side of Overnight: the morning digest and the button handler.

Both talk to the database only through functions that the service role may call:
slack_review_queue() and slack_review_decision(). Each one acts as the person the Slack
user is mapped to, so every permission check is the same one the console runs.
Nothing here decides anything. It formats, verifies Slack's signature, and passes clicks on.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Callable, Protocol

ACTION_LABEL = {     # the same labels as console/src/lib/meta.ts
    "propose_strategy": "Account plan", "flag_risk": "Deal risk", "update_field": "Field update", "schedule_touch": "Outreach step",
    "flag_churn_risk": "Churn risk", "flag_expansion": "Expansion", "propose_icp_change": "ICP change", "propose_partner": "New partner",
    "product_theme": "Product theme", "propose_credit": "Comp credit", "propose_carve": "Territory carve", "propose_skill_version": "Skill change",
}
MAX_ITEMS = 6           # Slack messages stay short. Everything else is in the console.


class Transport(Protocol):
    def rpc(self, fn: str, args: dict) -> list | dict | str | None: ...
    def select(self, table: str, columns: str) -> list[dict]: ...


class RestTransport:
    """Supabase's REST API with the service role key. Keep that key on the server only."""

    def __init__(self, url: str, service_key: str):
        import requests
        self.s = requests.Session()
        self.url = url.rstrip("/")
        self.s.headers.update({"apikey": service_key, "Authorization": f"Bearer {service_key}"})

    def rpc(self, fn, args):
        r = self.s.post(f"{self.url}/rest/v1/rpc/{fn}", json=args, timeout=20)
        if r.status_code >= 400:
            raise PermissionError(r.json().get("message", r.text))
        return r.json() if r.content else None

    def select(self, table, columns):
        r = self.s.get(f"{self.url}/rest/v1/{table}", params={"select": columns}, timeout=20)
        r.raise_for_status()
        return r.json()


# --- The digest ----------------------------------------------------------------------------

def digest_blocks(first_name: str, items: list[dict], console_url: str) -> list[dict]:
    """Block Kit for one person's morning message. Pure: same input, same message."""
    n = len(items)
    head = (f"Good morning {first_name}. The loops ran overnight. *{n} {'thing needs' if n == 1 else 'things need'} you.*"
            if n else f"Good morning {first_name}. The loops ran overnight. Nothing needs you today.")
    blocks: list[dict] = [{"type": "section", "text": {"type": "mrkdwn", "text": head}}]
    for d in items[:MAX_ITEMS]:
        did = str(d["decision_id"])
        label = ACTION_LABEL.get(d["action"], d["action"].replace("_", " ").capitalize())
        loop = d["loop"].replace("_", " ").capitalize()
        rationale = (d.get("rationale") or "")[:600]
        blocks += [
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{label}: {d.get('subject_name') or d['subject_id']}*\n_{loop}_\n{rationale}"}},
            {"type": "actions", "block_id": f"decision:{did}", "elements": [
                {"type": "button", "action_id": "accept", "value": did, "style": "primary", "text": {"type": "plain_text", "text": "Accept"}},
                {"type": "button", "action_id": "edit", "url": f"{console_url.rstrip('/')}/reviews?d={did}", "text": {"type": "plain_text", "text": "Edit in console"}},
                {"type": "button", "action_id": "reject", "value": did, "style": "danger", "text": {"type": "plain_text", "text": "Reject"},
                 "confirm": {"title": {"type": "plain_text", "text": "Reject this?"}, "text": {"type": "plain_text", "text": "The loop is graded on your answer."},
                             "confirm": {"type": "plain_text", "text": "Reject"}, "deny": {"type": "plain_text", "text": "Cancel"}}},
            ]},
        ]
    if n > MAX_ITEMS:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"{n - MAX_ITEMS} more in the <{console_url.rstrip('/')}/reviews|review inbox>."}]})
    return blocks


def build_digests(t: Transport, console_url: str) -> list[dict]:
    """One message per mapped person who has something waiting. Returns {channel, text, blocks}."""
    people = t.select("slack_user_map", "slack_user_id,user_id")
    names = {s["user_id"]: s["first_name"] for s in t.select("sales", "user_id,first_name")}
    out = []
    for p in people:
        items = t.rpc("slack_review_queue", {"p_slack_user": p["slack_user_id"]}) or []
        if not items:
            continue
        first = names.get(p["user_id"], "there")
        out.append({"channel": p["slack_user_id"], "text": f"{len(items)} things from the loops need you.",
                    "blocks": digest_blocks(first, items, console_url)})
    return out


# --- The button handler --------------------------------------------------------------------

def verify_signature(signing_secret: str, timestamp: str, body: bytes, signature: str, now: float | None = None) -> bool:
    """Slack's v0 request signature, with a five minute replay window."""
    try:
        if abs((now or time.time()) - int(timestamp)) > 300:
            return False
    except (TypeError, ValueError):
        return False
    base = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def handle_interaction(t: Transport, signing_secret: str, headers: dict, body: bytes,
                       now: float | None = None) -> tuple[int, dict | None]:
    """Handle one Slack interactivity request.

    Returns (http status, update). Slack ignores the body of the reply to a button click, so the
    caller acknowledges with an empty 200 and posts the update to update["response_url"].
    """
    h = {k.lower(): v for k, v in headers.items()}
    if not verify_signature(signing_secret, h.get("x-slack-request-timestamp", ""), body, h.get("x-slack-signature", ""), now):
        return 401, None
    form = urllib.parse.parse_qs(body.decode())
    payload = json.loads(form.get("payload", ["{}"])[0])
    action = (payload.get("actions") or [{}])[0]
    user = (payload.get("user") or {}).get("id", "")
    if action.get("action_id") not in ("accept", "reject"):
        return 200, None                                      # "Edit in console" is a link; nothing to do
    outcome = "accepted" if action["action_id"] == "accept" else "rejected"
    try:
        did = int(action.get("value", ""))
        t.rpc("slack_review_decision", {"p_slack_user": user, "p_decision_id": did, "p_outcome": outcome,
                                        "p_note": "Rejected from the digest" if outcome == "rejected" else None})
        text = f":white_check_mark: {outcome.capitalize()} by <@{user}>."
    except (PermissionError, ValueError) as e:
        text = f":no_entry: Not done: {e}"
    return 200, {"response_url": payload.get("response_url"), **replace_action_block(payload, action.get("block_id", ""), text)}


def replace_action_block(payload: dict, block_id: str, text: str) -> dict:
    """The original message, with the clicked row's buttons swapped for the result."""
    blocks = (payload.get("message") or {}).get("blocks") or []
    new = [{"type": "context", "elements": [{"type": "mrkdwn", "text": text}]} if b.get("block_id") == block_id else b for b in blocks]
    return {"replace_original": True, "blocks": new}
