"""
Gravrel Hub — one dashboard linking every Gravrel app.

A password-gated launcher with a live status dot per app. Because browsers
block cross-origin health checks, the status probe runs server-side here and
the page polls this app's own /api/status endpoint.

    pip install -r requirements.txt
    python app.py
"""

import concurrent.futures
import hmac
import json
import os
import secrets
import time
import urllib.request
from pathlib import Path

from flask import (Flask, jsonify, redirect, render_template,
                   render_template_string, request, session)

APP_DIR = Path(__file__).parent

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=bool(os.environ.get("HTTPS_ONLY")))

# The app registry. Edit here (or in apps.json if present) to add/rename apps.
# "note" is your private line, shown only once you're logged in.
DEFAULT_APPS = [
    {"id": "studio", "name": "Gravrel Studio", "tag": "AI Media",
     "desc": "Self-hosted image & video generation across 200+ models.",
     "url": "https://open-higgsfield-ai-70sq.onrender.com/",
     "health": "https://open-higgsfield-ai-70sq.onrender.com/",
     "note": "Needs a funded Muapi key to generate. CORS fixed.",
     "accent": "#F0A202"},
    {"id": "dispatch", "name": "Gravrel Dispatch", "tag": "Email",
     "desc": "Mail-merge sender — personalised bulk email from a spreadsheet.",
     "url": "https://gravrel-dispatch.onrender.com/",
     "health": "https://gravrel-dispatch.onrender.com/healthz",
     "note": "Proton SMTP. Move to Resend/SES for real volume.",
     "accent": "#5FB6C4"},
    {"id": "canary", "name": "Canary", "tag": "Security",
     "desc": "Honeytoken tripwire — know the instant an intruder touches a decoy.",
     "url": "https://canary-1yl8.onrender.com",
     "health": "https://canary-1yl8.onrender.com/healthz",
     "note": "Sellable product. Set BASE_URL to its own domain.",
     "accent": "#3FD08A"},
    {"id": "toolkit", "name": "Gravrel Toolkit", "tag": "Lead Magnet",
     "desc": "Curated AI-tools hub with an email gate that captures leads.",
     "url": "https://gravrel-toolkit.onrender.com",
     "health": "https://gravrel-toolkit.onrender.com/healthz",
     "note": "Wire LEAD_WEBHOOK so leads survive free-tier sleep.",
     "accent": "#9B8CFF"},
    {"id": "voicebox", "name": "Voicebox Guide", "tag": "Guide",
     "desc": "A polished install guide for the free local AI voice studio.",
     "url": "https://voicebox-guide.onrender.com",
     "health": "https://voicebox-guide.onrender.com/healthz",
     "note": "Static guide. The lightest of the lot.",
     "accent": "#F0603C"},
]


def load_apps():
    f = APP_DIR / "apps.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return DEFAULT_APPS


LOGIN_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Gravrel Hub</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0A1519;
font-family:system-ui,sans-serif;color:#EAF4F0}.box{width:330px}
h1{font-family:system-ui;font-size:25px;margin:0 0 4px}h1 em{font-style:normal;color:#F0A202}
p{color:#8AA5AC;font-size:12px;letter-spacing:.12em;text-transform:uppercase;margin:0 0 26px}
input{width:100%;padding:13px;border:1px solid #1E3A43;border-radius:6px;background:#07140D;color:#fff;font-size:15px}
input:focus{outline:none;border-color:#F0A202}
button{width:100%;margin-top:13px;padding:13px;border:0;border-radius:6px;background:#F0A202;color:#241703;font-weight:700;font-size:15px;cursor:pointer}
.err{background:#3A1512;border-left:3px solid #C4453A;padding:10px 13px;font-size:13px;margin-bottom:16px;border-radius:0 4px 4px 0}
</style></head><body><div class="box">
<h1><em>◆</em> Gravrel Hub</h1><p>all systems</p>
{% if error %}<div class="err">{{ error }}</div>{% endif %}
<form method="post"><input name="password" type="password" autofocus placeholder="Passphrase" autocomplete="current-password">
<button>Enter</button></form></div></body></html>"""

_attempts = {}


@app.before_request
def gate():
    if request.path in ("/login", "/healthz") or request.path.startswith("/static/"):
        return None
    if not APP_PASSWORD:
        return None
    if session.get("ok"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "auth"}), 401
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if not APP_PASSWORD:
        return redirect("/")
    err = None
    if request.method == "POST":
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0]
        hits = [t for t in _attempts.get(ip, []) if time.time() - t < 900]
        if len(hits) >= 8:
            err = "Too many attempts. Wait 15 minutes."
        elif hmac.compare_digest(request.form.get("password", ""), APP_PASSWORD):
            session.clear()
            session["ok"] = True
            _attempts.pop(ip, None)
            return redirect("/")
        else:
            hits.append(time.time())
            _attempts[ip] = hits
            err = "Wrong passphrase."
    return render_template_string(LOGIN_PAGE, error=err), (401 if err else 200)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True})


def probe(a):
    """Server-side reachability check for one app. Render free apps that are
    asleep may be slow or briefly fail — reported as 'waking', not dead.
    Any HTTP response (even a 4xx/5xx) means the app is running, so it's 'up';
    only a connection-level failure counts as down or waking."""
    url = a.get("health") or a.get("url")
    t0 = time.time()
    try:
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "GravrelHub/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            code = r.status
        ms = int((time.time() - t0) * 1000)
        return {"id": a["id"], "status": "up", "code": code, "ms": ms}
    except urllib.error.HTTPError as e:
        # The server answered — with an error code, but it's alive and reachable.
        ms = int((time.time() - t0) * 1000)
        return {"id": a["id"], "status": "up", "code": e.code, "ms": ms}
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        # Connection refused / timeout on free tier usually means a cold start.
        kind = "waking" if ms >= 7000 else "down"
        return {"id": a["id"], "status": kind, "code": 0, "ms": ms,
                "err": type(e).__name__}


@app.route("/api/status")
def api_status():
    apps = load_apps()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(apps)) as ex:
        results = list(ex.map(probe, apps))
    return jsonify({"checked_at": int(time.time()), "results": results})


@app.route("/")
def index():
    return render_template("index.html", apps=load_apps(),
                           authed=bool(session.get("ok")) or not APP_PASSWORD)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    if host != "127.0.0.1" and not APP_PASSWORD:
        raise SystemExit("Refusing to start public without APP_PASSWORD set.")
    print(f"\n  Gravrel Hub at http://{host}:{port}")
    print(f"  Auth: {'on' if APP_PASSWORD else 'off (local only)'}\n")
    app.run(host=host, port=port, threaded=True)
