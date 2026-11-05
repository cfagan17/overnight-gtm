"""integrations/slack: the digest and the button handler, end to end against the database."""
import hashlib
import hmac
import json
import sys
import urllib.parse

import psycopg

from helpers import ANA, CY, ROOT
from test_console import as_service, queued_decision, tx  # noqa: F401  (tx is a fixture)

sys.path.insert(0, str(ROOT))
from integrations.slack.core import build_digests, digest_blocks, handle_interaction, verify_signature  # noqa: E402

SECRET = "test-signing-secret"
NOW = 1_800_000_000


class TxTransport:
    """What RestTransport does, inside the test transaction: every call as the service role."""

    def __init__(self, conn):
        self.c = conn

    def rpc(self, fn, args):
        as_service(self.c)
        names = ", ".join(f"{k} => %({k})s" for k in args)
        try:
            with self.c.transaction():
                rows = self.c.execute(f"select to_jsonb(r) from public.{fn}({names}) r", args).fetchall()
        except psycopg.Error as e:
            raise PermissionError(e.diag.message_primary)
        finally:
            self.c.execute("reset role")
        return [r[0] for r in rows]

    def select(self, table, columns):
        as_service(self.c)
        rows = self.c.execute(f"select to_jsonb(t) from (select {columns} from public.{table}) t").fetchall()
        self.c.execute("reset role")
        return [r[0] for r in rows]


def signed(payload: dict, secret=SECRET, ts=NOW):
    body = urllib.parse.urlencode({"payload": json.dumps(payload)}).encode()
    sig = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    return {"X-Slack-Request-Timestamp": str(ts), "X-Slack-Signature": sig}, body


def click(user, action_id, did, blocks=None):
    return {"type": "block_actions", "user": {"id": user}, "response_url": "https://hooks.slack.com/actions/T/1/x",
            "actions": [{"action_id": action_id, "value": str(did), "block_id": f"decision:{did}"}],
            "message": {"blocks": blocks or []}}


def map_people(tx):
    tx.execute("reset role")
    tx.execute("insert into public.slack_user_map (slack_user_id, user_id) values ('U0ANA', %s), ('U0CY', %s)", (ANA, CY))


def test_digest_goes_to_each_person_with_only_what_they_may_review(tx):
    d = queued_decision(tx)
    map_people(tx)
    msgs = build_digests(TxTransport(tx), "https://console.example")
    by = {m["channel"]: m for m in msgs}
    assert "U0ANA" in by and "U0CY" not in by                     # Cy cannot review West, so gets nothing
    blocks = by["U0ANA"]["blocks"]
    ids = [b["block_id"] for b in blocks if b["type"] == "actions"]
    assert f"decision:{d}" in ids
    edit = next(e for b in blocks if b.get("block_id") == f"decision:{d}" for e in b["elements"] if e["action_id"] == "edit")
    assert edit["url"] == f"https://console.example/reviews?d={d}"


def test_digest_is_short():
    items = [{"decision_id": i, "loop": "deal_inspection", "action": "flag_risk", "subject_id": str(i), "subject_name": f"Deal {i}", "rationale": "x" * 900}
             for i in range(10)]
    blocks = digest_blocks("Maya", items, "https://c")
    assert sum(b["type"] == "actions" for b in blocks) == 6
    assert "4 more" in blocks[-1]["elements"][0]["text"]
    assert all(len(b["text"]["text"]) < 3000 for b in blocks if b["type"] == "section")    # Slack's limit


def test_click_accepts_as_the_mapped_person(tx):
    d = queued_decision(tx)
    map_people(tx)
    h, body = signed(click("U0ANA", "accept", d, [{"type": "actions", "block_id": f"decision:{d}"}]))
    status, update = handle_interaction(TxTransport(tx), SECRET, h, body, now=NOW)
    assert status == 200 and update["response_url"].startswith("https://hooks.slack.com/")
    assert "Accepted" in update["blocks"][0]["elements"][0]["text"]
    row = tx.execute("select review_outcome, reviewed_by::text from public.decisions where id = %s", (d,)).fetchone()
    assert row == ("accepted", ANA)


def test_click_from_someone_without_access_changes_nothing(tx):
    d = queued_decision(tx)
    map_people(tx)
    for user in ("U0CY", "U0NOBODY"):
        h, body = signed(click(user, "accept", d, [{"type": "actions", "block_id": f"decision:{d}"}]))
        status, update = handle_interaction(TxTransport(tx), SECRET, h, body, now=NOW)
        assert status == 200 and "Not done" in update["blocks"][0]["elements"][0]["text"]
    assert tx.execute("select review_outcome from public.decisions where id = %s", (d,)).fetchone()[0] is None


def test_forged_or_replayed_requests_are_refused(tx):
    d = queued_decision(tx)
    map_people(tx)
    h, body = signed(click("U0ANA", "accept", d), secret="wrong")
    assert handle_interaction(TxTransport(tx), SECRET, h, body, now=NOW) == (401, None)
    h, body = signed(click("U0ANA", "accept", d), ts=NOW - 600)
    assert handle_interaction(TxTransport(tx), SECRET, h, body, now=NOW) == (401, None)
    assert tx.execute("select review_outcome from public.decisions where id = %s", (d,)).fetchone()[0] is None
    assert not verify_signature(SECRET, "not-a-number", b"", "v0=x")
