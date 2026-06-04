#!/usr/bin/env python3
"""
Strava social graph explorer — followers & following.

Setup:
  1. Register an app at https://www.strava.com/settings/api
     - Set "Authorization Callback Domain" to: localhost
  2. Run this script; it will open your browser for OAuth consent
  3. Tokens are saved to strava_tokens.json for reuse

Usage:
  python3 strava_social.py
"""

import json
import os
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests

TOKENS_FILE = "strava_tokens.json"
AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API_BASE = "https://www.strava.com/api/v3"
REDIRECT_PORT = 8000
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"

# Scopes needed: read (profile) + profile:read_all (private profile data)
SCOPE = "read,profile:read_all,activity:read"


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE) as f:
            return json.load(f)
    return None


def save_tokens(tokens):
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def refresh_access_token(client_id, client_secret, refresh_token):
    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    })
    resp.raise_for_status()
    return resp.json()


def get_authorization_code(client_id):
    """Opens the browser for OAuth consent and captures the code via a local server."""
    auth_params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": SCOPE,
    }
    auth_url = f"{AUTH_URL}?{urlencode(auth_params)}"
    print(f"\nOpening browser for Strava authorization...")
    webbrowser.open(auth_url)

    code_holder = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if "code" in params:
                code_holder["code"] = params["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<h2>Authorization successful! You can close this tab.</h2>")
            else:
                self.send_response(400)
                self.end_headers()
                error = params.get("error", ["unknown"])[0]
                self.wfile.write(f"<h2>Authorization failed: {error}</h2>".encode())

        def log_message(self, *args):
            pass  # suppress server logs

    server = HTTPServer(("localhost", REDIRECT_PORT), Handler)
    server.handle_request()
    return code_holder.get("code")


def exchange_code_for_tokens(client_id, client_secret, code):
    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    return resp.json()


def get_valid_token(client_id, client_secret):
    tokens = load_tokens()

    if tokens:
        if tokens["expires_at"] < time.time() + 60:
            print("Access token expired, refreshing...")
            new_tokens = refresh_access_token(client_id, client_secret, tokens["refresh_token"])
            tokens.update(new_tokens)
            save_tokens(tokens)
        return tokens["access_token"]

    # First-time auth
    code = get_authorization_code(client_id)
    if not code:
        print("Failed to get authorization code.")
        sys.exit(1)

    tokens = exchange_code_for_tokens(client_id, client_secret, code)
    save_tokens(tokens)
    print("Tokens saved to", TOKENS_FILE)
    return tokens["access_token"]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(token, path, params=None):
    resp = requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
    )
    if resp.status_code == 429:
        print("Rate limit hit. Waiting 15 minutes...")
        time.sleep(900)
        return api_get(token, path, params)
    resp.raise_for_status()
    return resp.json()


def fetch_paged(token, path, page_size=200):
    """Fetch all pages from a paginated endpoint."""
    results = []
    page = 1
    while True:
        page_data = api_get(token, path, {"per_page": page_size, "page": page})
        if not page_data:
            break
        results.extend(page_data)
        if len(page_data) < page_size:
            break
        page += 1
    return results


def format_athlete(a):
    name = f"{a.get('firstname', '')} {a.get('lastname', '')}".strip()
    city = a.get("city") or ""
    country = a.get("country") or ""
    location = ", ".join(filter(None, [city, country]))
    profile = a.get("profile_medium") or a.get("profile") or ""
    return f"  {a['id']:>10}  {name:<30}  {location:<25}  {profile}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== Strava Social Graph Explorer ===\n")

    client_id = os.environ.get("STRAVA_CLIENT_ID") or input("Enter your Strava client_id: ").strip()
    client_secret = os.environ.get("STRAVA_CLIENT_SECRET") or input("Enter your Strava client_secret: ").strip()

    token = get_valid_token(client_id, client_secret)
    print("\nAuthenticated successfully.\n")

    # Authenticated athlete profile
    athlete = api_get(token, "/athlete")
    print(f"Athlete: {athlete['firstname']} {athlete['lastname']} (@{athlete.get('username', 'n/a')})")
    print(f"  Followers : {athlete.get('follower_count', 'n/a')}")
    print(f"  Following : {athlete.get('friend_count', 'n/a')}")
    print()

    header = f"  {'ID':>10}  {'Name':<30}  {'Location':<25}  Profile URL"
    divider = "  " + "-" * 100

    # Strava's API returns athletes you follow who also follow you ("friends")
    # and athletes who follow you ("followers") — both as athlete summary objects.
    #
    # Note: Since the 2018 API restrictions, Strava only returns athletes
    # in your mutual-friend graph (not strangers). Full public follower lists
    # are no longer exposed via the API for privacy reasons.

    print("--- Athletes you FOLLOW (friends who follow back) ---")
    print(header)
    print(divider)
    try:
        following = fetch_paged(token, "/athlete/following")
        if following:
            for a in following:
                print(format_athlete(a))
            print(f"\n  Total: {len(following)}")
        else:
            print("  (none returned)")
    except requests.HTTPError as e:
        print(f"  Could not fetch following list: {e}")

    print()
    print("--- Athletes who FOLLOW YOU ---")
    print(header)
    print(divider)
    try:
        followers = fetch_paged(token, "/athlete/followers")
        if followers:
            for a in followers:
                print(format_athlete(a))
            print(f"\n  Total: {len(followers)}")
        else:
            print("  (none returned)")
    except requests.HTTPError as e:
        print(f"  Could not fetch followers list: {e}")

    # Summary: who follows you but you don't follow back, and vice versa
    if following and followers:
        following_ids = {a["id"] for a in following}
        follower_ids = {a["id"] for a in followers}
        follower_map = {a["id"]: a for a in followers}
        following_map = {a["id"]: a for a in following}

        not_following_back = follower_ids - following_ids
        not_followed_back = following_ids - follower_ids

        if not_following_back:
            print(f"\n--- Followers you DON'T follow back ({len(not_following_back)}) ---")
            print(header)
            print(divider)
            for aid in not_following_back:
                print(format_athlete(follower_map[aid]))

        if not_followed_back:
            print(f"\n--- People you follow who DON'T follow back ({len(not_followed_back)}) ---")
            print(header)
            print(divider)
            for aid in not_followed_back:
                print(format_athlete(following_map[aid]))


if __name__ == "__main__":
    main()
