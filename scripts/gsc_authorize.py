"""One-off: turn the downloaded OAuth client into a GSC refresh token.

`radar/gsc.py` needs client_id + client_secret + refresh_token (an "authorized user"
credential). The file from the Cloud Console is only the client half. This script serves
one loopback redirect on http://localhost:<port>, exchanges the code, and writes
`gsc_token.json` at the repository root (gitignored). It then lists the Search Console
properties the account can read, so the `gsc.site` value can be copied from real output.

Run: .venv/bin/python scripts/gsc_authorize.py path/to/client_secret_*.json
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

CLIENT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("gsc_client.json")
OUT = Path("gsc_token.json")
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
REDIRECT = "http://localhost:{port}"


class Handler(BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        Handler.code = (query.get("code") or [None])[0]
        Handler.error = (query.get("error") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("授权完成，可以关闭这个页面。".encode("utf-8"))

    def log_message(self, *args) -> None:      # keep the job's output clean
        pass


def main() -> None:
    if not CLIENT.exists():
        raise SystemExit(f"client JSON not found: {CLIENT}\n"
                         "usage: python scripts/gsc_authorize.py <client_secret_*.json>")
    client = json.loads(CLIENT.read_text())["installed"]
    server = HTTPServer(("", 0), Handler)
    port = server.server_address[1]
    redirect = REDIRECT.format(port=port)
    auth = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent"})
    print("OPEN THIS URL:\n" + auth + "\n", flush=True)
    while Handler.code is None and Handler.error is None:
        server.handle_request()
    server.server_close()
    if Handler.error or not Handler.code:
        raise SystemExit(f"authorization failed: {Handler.error}")
    token_uri = client.get("token_uri") or "https://oauth2.googleapis.com/token"
    body = urllib.parse.urlencode({
        "client_id": client["client_id"], "client_secret": client["client_secret"],
        "code": Handler.code, "grant_type": "authorization_code", "redirect_uri": redirect}).encode()
    with urllib.request.urlopen(urllib.request.Request(token_uri, data=body), timeout=30) as res:
        token = json.load(res)
    if "refresh_token" not in token:
        raise SystemExit("no refresh_token in the answer (is the app in Testing and reused?): "
                         + ", ".join(k for k in token if k != "access_token"))
    OUT.write_text(json.dumps({
        "client_id": client["client_id"], "client_secret": client["client_secret"],
        "refresh_token": token["refresh_token"], "token_uri": token_uri}, indent=1))
    print(f"written: {OUT}", flush=True)
    req = urllib.request.Request("https://www.googleapis.com/webmasters/v3/sites",
                                 headers={"Authorization": f"Bearer {token['access_token']}"})
    with urllib.request.urlopen(req, timeout=30) as res:
        sites = json.load(res).get("siteEntry") or []
    print("properties this account can read:", flush=True)
    for site in sites:
        print(f"  {site['siteUrl']}  ({site['permissionLevel']})", flush=True)


if __name__ == "__main__":
    main()
