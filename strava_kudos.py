#!/usr/bin/env python3
"""
Strava kudos analyzer.

Two modes:

  1. Kudos RECEIVED (API) — who likes your activities most.
     Paginates all your activities and fetches each activity's kudos list.
     Can be slow; uses a local cache (strava_kudos_cache.json) to resume.

  2. Kudos GIVEN (data export) — whose activities you liked most.
     Strava's API doesn't expose kudos you've given. Use your GDPR data export:
       Settings → My Account → Download or Delete Your Account → Request Archive
     Then run with the path to the extracted folder:
       python3 strava_kudos.py --export-dir ~/Downloads/strava_export

Usage:
  python3 strava_kudos.py                          # kudos received via API
  python3 strava_kudos.py --export-dir <path>      # kudos given from data export
  python3 strava_kudos.py --top 20                 # show top N (default 15)
"""

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict

import requests

TOKENS_FILE = "strava_tokens.json"
CACHE_FILE = "strava_kudos_cache.json"
TOKEN_URL = "https://www.strava.com/oauth/token"
API_BASE = "https://www.strava.com/api/v3"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE) as f:
            return json.load(f)
    return None


def save_tokens(tokens):
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def get_valid_token():
    tokens = load_tokens()
    if not tokens:
        sys.exit(
            f"No tokens found. Run strava_social.py first to authenticate, "
            f"or ensure {TOKENS_FILE} exists."
        )

    if tokens["expires_at"] < time.time() + 60:
        print("Refreshing access token...")
        client_id = tokens.get("client_id") or input("client_id: ").strip()
        client_secret = tokens.get("client_secret") or input("client_secret: ").strip()
        resp = requests.post(TOKEN_URL, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
        })
        resp.raise_for_status()
        tokens.update(resp.json())
        save_tokens(tokens)

    return tokens["access_token"]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(token, path, params=None):
    while True:
        resp = requests.get(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
        )
        if resp.status_code == 429:
            reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 900))
            wait = max(reset - int(time.time()), 60)
            print(f"\n  Rate limit hit. Waiting {wait}s...", end="", flush=True)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()


def fetch_paged(token, path, page_size=100, label=""):
    results = []
    page = 1
    while True:
        data = api_get(token, path, {"per_page": page_size, "page": page})
        if not data:
            break
        results.extend(data)
        if label:
            print(f"\r  {label}: {len(results)}", end="", flush=True)
        if len(data) < page_size:
            break
        page += 1
    if label:
        print()
    return results


# ---------------------------------------------------------------------------
# Cache helpers (for resumable activity kudos crawl)
# ---------------------------------------------------------------------------

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {"processed_ids": [], "kudos_by_athlete": {}}


def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)


# ---------------------------------------------------------------------------
# Kudos RECEIVED via API
# ---------------------------------------------------------------------------

def analyze_kudos_received(token, top_n):
    print("\n=== Kudos RECEIVED (who likes your activities most) ===")
    print("Fetching your activities... (this uses a cache; Ctrl-C to stop and see partial results)\n")

    cache = load_cache()
    processed = set(cache["processed_ids"])
    kudos_tally = defaultdict(lambda: {"count": 0, "name": ""})
    kudos_tally.update({k: v for k, v in cache["kudos_by_athlete"].items()})

    activities = fetch_paged(token, "/athlete/activities", label="activities fetched")
    new_activities = [a for a in activities if str(a["id"]) not in processed]

    if not new_activities:
        print("  All activities already cached.")
    else:
        print(f"  Fetching kudos for {len(new_activities)} activities "
              f"({len(processed)} already cached)...\n")

    try:
        for i, activity in enumerate(new_activities, 1):
            aid = activity["id"]
            name = activity.get("name", "Untitled")
            kudosers = api_get(token, f"/activities/{aid}/kudos", {"per_page": 200})

            for athlete in kudosers:
                athlete_id = str(athlete["id"])
                full_name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
                kudos_tally[athlete_id]["count"] += 1
                kudos_tally[athlete_id]["name"] = full_name

            processed.add(str(aid))
            print(f"\r  [{i}/{len(new_activities)}] {name[:50]:<50}", end="", flush=True)

            # Save cache every 20 activities
            if i % 20 == 0:
                cache["processed_ids"] = list(processed)
                cache["kudos_by_athlete"] = dict(kudos_tally)
                save_cache(cache)

    except KeyboardInterrupt:
        print("\n  Interrupted — saving cache and showing partial results.")
    finally:
        cache["processed_ids"] = list(processed)
        cache["kudos_by_athlete"] = dict(kudos_tally)
        save_cache(cache)

    print(f"\n\n  Cache saved to {CACHE_FILE} (re-run to continue from here)\n")
    print_table(
        kudos_tally,
        title=f"Top {top_n} athletes who kudosed your activities",
        top_n=top_n,
    )


# ---------------------------------------------------------------------------
# Kudos GIVEN via data export
# ---------------------------------------------------------------------------

def analyze_kudos_given(export_dir, top_n):
    print("\n=== Kudos GIVEN (whose activities you liked most) ===")

    # Strava export typically has kudos data in kudos.csv
    # The file lists activity_id, activity_name, athlete_name (and sometimes athlete_id)
    kudos_csv = os.path.join(export_dir, "kudos.csv")

    if not os.path.exists(kudos_csv):
        # Some exports use a different structure; look around
        candidates = []
        for root, dirs, files in os.walk(export_dir):
            for fname in files:
                if "kudo" in fname.lower() and fname.endswith(".csv"):
                    candidates.append(os.path.join(root, fname))
        if candidates:
            kudos_csv = candidates[0]
            print(f"  Found: {kudos_csv}")
        else:
            sys.exit(
                f"  No kudos.csv found in {export_dir}.\n"
                f"  Make sure you've extracted the full Strava data export archive.\n"
                f"  Expected file: {kudos_csv}"
            )

    tally = Counter()
    rows_seen = 0
    with open(kudos_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        print(f"  Columns: {headers}\n")

        # Strava export column names vary; try common patterns
        name_col = next(
            (c for c in headers if "athlete" in c.lower() or "name" in c.lower()),
            headers[0] if headers else None,
        )
        if not name_col:
            sys.exit("  Could not identify athlete name column in kudos.csv.")

        for row in reader:
            rows_seen += 1
            athlete_name = row.get(name_col, "").strip()
            if athlete_name:
                tally[athlete_name] += 1

    if rows_seen == 0:
        print("  kudos.csv is empty — you may not have given any kudos, or the file format is unexpected.")
        return

    print(f"  Total kudos given: {rows_seen}\n")
    print_table_counter(tally, title=f"Top {top_n} athletes whose activities you liked", top_n=top_n)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_table(kudos_tally, title, top_n):
    sorted_athletes = sorted(
        kudos_tally.values(),
        key=lambda x: x["count"],
        reverse=True,
    )[:top_n]

    if not sorted_athletes:
        print("  No kudos data found.")
        return

    print(f"  {title}")
    print(f"  {'Rank':<6}{'Kudos':>6}  {'Name'}")
    print("  " + "-" * 50)
    for rank, entry in enumerate(sorted_athletes, 1):
        print(f"  {rank:<6}{entry['count']:>6}  {entry['name']}")


def print_table_counter(counter, title, top_n):
    top = counter.most_common(top_n)
    if not top:
        print("  No data.")
        return

    print(f"  {title}")
    print(f"  {'Rank':<6}{'Kudos':>6}  {'Athlete'}")
    print("  " + "-" * 50)
    for rank, (name, count) in enumerate(top, 1):
        print(f"  {rank:<6}{count:>6}  {name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Analyze Strava kudos.")
    parser.add_argument("--export-dir", metavar="PATH",
                        help="Path to extracted Strava data export (for kudos given)")
    parser.add_argument("--top", type=int, default=15, metavar="N",
                        help="Show top N athletes (default: 15)")
    parser.add_argument("--clear-cache", action="store_true",
                        help="Delete cached kudos data and start fresh")
    args = parser.parse_args()

    if args.clear_cache and os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
        print(f"Cache cleared: {CACHE_FILE}")

    if args.export_dir:
        analyze_kudos_given(args.export_dir, args.top)
    else:
        token = get_valid_token()
        analyze_kudos_received(token, args.top)


if __name__ == "__main__":
    main()
