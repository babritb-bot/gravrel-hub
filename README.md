# Gravrel Hub — one dashboard for every Gravrel app

A password-gated launcher that links to all your deployed apps, each with a
live status dot (green = online, yellow = waking from sleep, red = needs a
look) and a private note visible only once you're logged in.

## Why the status check runs server-side

Browsers block a page from health-checking a *different* website (cross-origin
security). So the dot can't be faked or done in the browser — this app probes
each URL from its own server (`/api/status`) and the page polls that. Any HTTP
response counts as "up" (the app answered); only a real connection failure or a
cold-start timeout shows as down/waking.

## Run locally

    pip install -r requirements.txt
    python app.py            # http://127.0.0.1:5000  (no auth locally)

## Deploy on Render

New Web Service -> Docker -> Free -> Singapore. Health Check Path `/healthz`.
Environment variables:

| Variable       | Purpose                                              |
|----------------|------------------------------------------------------|
| `APP_PASSWORD` | the passphrase to enter the hub (required in public) |
| `SECRET_KEY`   | signs the session cookie (any long random string)    |
| `HTTPS_ONLY`   | set to `1` on the public https deploy                |

## Editing the app list

Edit `DEFAULT_APPS` in `app.py` — each entry has `name`, `tag`, `desc`, `url`
(where "Open" goes), `health` (what gets probed), `note` (your private line),
and `accent` (the card's colour stripe). Or drop an `apps.json` next to app.py
with the same shape and it'll be used instead — no code edit needed.

The five apps are pre-filled:
Gravrel Studio, Gravrel Dispatch, Canary, Gravrel Toolkit, Voicebox Guide.
