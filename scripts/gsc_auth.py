"""Create gsc_token.json for the optional Search Console signal. Run once, on your own machine.

  pip install google-auth-oauthlib
  python scripts/gsc_auth.py gsc_client.json

gsc_client.json is an OAuth client of type "Desktop app" from Google Cloud Console
(APIs & Services > Credentials), in a project with the Search Console API enabled. A
browser opens for consent (read-only access); the refresh token is written to
gsc_token.json next to config.json. Both files are in .gitignore: keep them out of git.
For CI, put the content of gsc_token.json in a secret named GSC_TOKEN_JSON.
"""
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

if __name__ == "__main__":
    client = sys.argv[1] if len(sys.argv) > 1 else "gsc_client.json"
    creds = InstalledAppFlow.from_client_secrets_file(client, SCOPES).run_local_server(port=0)
    Path("gsc_token.json").write_text(creds.to_json())
    print("wrote gsc_token.json")
