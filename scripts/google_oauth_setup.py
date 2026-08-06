#!/usr/bin/env python3
"""One-time setup: authorize the bot to read/write your Google Docs.

Steps:
    1. In Google Cloud Console: create a project, enable the "Google Docs API".
    2. Create an OAuth 2.0 Client ID of type "Desktop app". Note the client
       ID and client secret.
    3. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your .env (or export
       them in your shell) before running this script.
    4. Run: python scripts/google_oauth_setup.py
    5. Approve access in the browser window that opens.
    6. Copy the printed GOOGLE_REFRESH_TOKEN into your .env / Railway variables.

Run this once — the refresh token doesn't expire from normal use. This
script only depends on the standard library plus python-dotenv (already a
project dependency); it is not part of the deployed bot.
"""
import http.server
import json
import os
import secrets
import threading
import urllib.parse
import urllib.request

import webbrowser

import dotenv

dotenv.load_dotenv()

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/"
SCOPE = "https://www.googleapis.com/auth/documents"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

_expected_state = secrets.token_urlsafe(16)
_received_code: str | None = None


class _RedirectHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        global _received_code
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()

        if params.get("state", [None])[0] != _expected_state:
            self.wfile.write(b"State mismatch - aborting. You can close this tab.")
            return

        code = params.get("code", [None])[0]
        if code is None:
            self.wfile.write(b"No authorization code received - aborting. You can close this tab.")
            return

        _received_code = code
        self.wfile.write(b"Authorized - you can close this tab and return to the terminal.")

    def log_message(self, format, *args) -> None:  # silence default request logging
        pass


def main() -> None:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit(
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET (in .env or the shell "
            "environment) before running this script."
        )

    auth_params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",  # forces a refresh_token even on repeat runs for the same account
        "state": _expected_state,
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(auth_params)}"

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _RedirectHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    print(f"Opening your browser for Google authorization...\n\n{auth_url}\n")
    webbrowser.open(auth_url)

    server_thread.join(timeout=300)
    server.server_close()

    if _received_code is None:
        raise SystemExit("Timed out waiting for authorization (5 min). Run the script again.")

    token_data = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": _received_code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        }
    ).encode()

    request = urllib.request.Request(TOKEN_URL, data=token_data, method="POST")
    with urllib.request.urlopen(request) as response:
        tokens = json.loads(response.read())

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise SystemExit(
            "No refresh_token in the response — Google only issues one on the first "
            "consent for a given app+account combination. Revoke this app's access at "
            "https://myaccount.google.com/permissions and run this script again."
        )

    print("Success! Add this to your .env / Railway variables:\n")
    print(f"GOOGLE_REFRESH_TOKEN={refresh_token}")


if __name__ == "__main__":
    main()
