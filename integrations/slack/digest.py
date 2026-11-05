"""Send each mapped person their morning digest.

    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... SLACK_BOT_TOKEN=xoxb-... \
    CONSOLE_URL=https://your-console python -m integrations.slack.digest [--dry-run]

Run it each morning after the nightly loops, from cron or any scheduler.
"""
from __future__ import annotations

import argparse
import json
import os

from integrations.slack.core import RestTransport, build_digests


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the messages instead of sending them")
    a = ap.parse_args()
    t = RestTransport(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    msgs = build_digests(t, os.environ.get("CONSOLE_URL", "http://localhost:5173"))
    if a.dry_run:
        print(json.dumps(msgs, indent=2))
        return
    import requests
    token = os.environ["SLACK_BOT_TOKEN"]
    for m in msgs:
        r = requests.post("https://slack.com/api/chat.postMessage", json=m, timeout=20,
                          headers={"Authorization": f"Bearer {token}"}).json()
        print(m["channel"], "ok" if r.get("ok") else r.get("error"))


if __name__ == "__main__":
    main()
