"""The Slack interactivity endpoint, as a tiny WSGI app.

    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... SLACK_SIGNING_SECRET=... \
    python -m integrations.slack.server            # listens on :8787

Point the Slack app's Interactivity Request URL at it. Any WSGI host works (gunicorn, a
container, a serverless adapter). The work is in core.handle_interaction.
"""
from __future__ import annotations

import os
from wsgiref.simple_server import make_server

from integrations.slack.core import RestTransport, handle_interaction


def app(environ, start_response):
    if environ.get("REQUEST_METHOD") != "POST":
        start_response("405 Method Not Allowed", [("Content-Type", "text/plain")])
        return [b"POST only"]
    size = int(environ.get("CONTENT_LENGTH") or 0)
    body = environ["wsgi.input"].read(size)
    headers = {k[5:].replace("_", "-"): v for k, v in environ.items() if k.startswith("HTTP_")}
    t = RestTransport(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    status, update = handle_interaction(t, os.environ["SLACK_SIGNING_SECRET"], headers, body)
    if update and update.get("response_url"):
        import requests
        url = update.pop("response_url")
        if url.startswith("https://hooks.slack.com/"):          # only ever post back to Slack
            requests.post(url, json=update, timeout=10)
    start_response("200 OK" if status == 200 else "401 Unauthorized", [("Content-Type", "text/plain")])
    return [b""]


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8787"))
    print(f"Slack interactivity endpoint on :{port}")
    make_server("", port, app).serve_forever()
