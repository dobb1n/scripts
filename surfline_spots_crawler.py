#!/usr/bin/env python3
"""
Surfline Spots Crawler
Crawls the Surfline taxonomy API to extract surf spot names and locations
from all regions worldwide.

Usage:
    python3 surfline_spots_crawler.py
    python3 surfline_spots_crawler.py --output spots.csv
    python3 surfline_spots_crawler.py --output spots.json --format json
"""

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import requests

BASE_URL = "https://services.surfline.com/taxonomy"
ROOT_TAXONOMY_ID = "58f7ed51dadb30820bb38782"  # Earth / world root node

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.surfline.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Delay between API requests to avoid rate limiting (seconds)
REQUEST_DELAY = 0.5


@dataclass
class Spot:
    spot_id: str
    name: str
    region: str
    subregion: str
    latitude: Optional[float]
    longitude: Optional[float]
    breadcrumb: str


def fetch_taxonomy(node_id: str, session: requests.Session, retries: int = 3) -> dict:
    """Fetch a single taxonomy node (maxDepth=1 to get immediate children)."""
    params = {
        "type": "taxonomy",
        "id": node_id,
        "maxDepth": 1,
    }
    for attempt in range(retries):
        try:
            resp = session.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            print(f"  [HTTP {e.response.status_code}] node {node_id}: {e}", file=sys.stderr)
            if e.response.status_code in (429, 503):
                wait = 2 ** attempt * 5
                print(f"  Rate limited — waiting {wait}s before retry...", file=sys.stderr)
                time.sleep(wait)
            else:
                raise
        except requests.exceptions.RequestException as e:
            print(f"  [Network error] node {node_id}: {e}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
    return {}


def parse_coordinates(node: dict) -> tuple[Optional[float], Optional[float]]:
    """Extract lat/lon from a taxonomy node."""
    loc = node.get("location") or node.get("geolocations")
    if isinstance(loc, dict):
        coords = loc.get("coordinates")
        if coords and len(coords) >= 2:
            # GeoJSON is [longitude, latitude]
            return coords[1], coords[0]
    return None, None


def crawl(
    node_id: str,
    session: requests.Session,
    spots: list[Spot],
    region: str = "",
    subregion: str = "",
    breadcrumb_parts: list[str] = None,
    depth: int = 0,
) -> None:
    """
    Recursively walk the taxonomy tree.

    Node types:
      - 'geoname'    → continent/country level (skip, recurse)
      - 'region'     → named surf region (e.g. "Southern California")
      - 'subregion'  → finer area within a region
      - 'spot'       → individual surf spot (leaf node)
    """
    if breadcrumb_parts is None:
        breadcrumb_parts = []

    time.sleep(REQUEST_DELAY)
    try:
        data = fetch_taxonomy(node_id, session)
    except Exception:
        return  # already logged

    node_name = data.get("name", "")
    node_type = data.get("type", "")
    children = data.get("contains", [])

    indent = "  " * depth
    print(f"{indent}[{node_type}] {node_name} ({len(children)} children)")

    current_breadcrumb = breadcrumb_parts + ([node_name] if node_name else [])

    # Update region / subregion trackers
    current_region = region
    current_subregion = subregion
    if node_type == "region":
        current_region = node_name
    elif node_type == "subregion":
        current_subregion = node_name

    for child in children:
        child_type = child.get("type", "")
        child_id = child.get("_id") or child.get("id", "")
        child_name = child.get("name", "")

        if child_type == "spot":
            lat, lon = parse_coordinates(child)
            spot = Spot(
                spot_id=child_id,
                name=child_name,
                region=current_region,
                subregion=current_subregion,
                latitude=lat,
                longitude=lon,
                breadcrumb=" > ".join(current_breadcrumb + [child_name]),
            )
            spots.append(spot)
        else:
            # Recurse into regions, subregions, geoname nodes, etc.
            crawl(
                node_id=child_id,
                session=session,
                spots=spots,
                region=current_region,
                subregion=current_subregion,
                breadcrumb_parts=current_breadcrumb,
                depth=depth + 1,
            )


def save_csv(spots: list[Spot], path: str) -> None:
    fields = ["spot_id", "name", "region", "subregion", "latitude", "longitude", "breadcrumb"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for spot in spots:
            writer.writerow(asdict(spot))
    print(f"Saved {len(spots)} spots → {path}")


def save_json(spots: list[Spot], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(s) for s in spots], f, indent=2, ensure_ascii=False)
    print(f"Saved {len(spots)} spots → {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl Surfline spots and extract names/locations.")
    parser.add_argument("--output", default="surfline_spots.csv", help="Output file path (default: surfline_spots.csv)")
    parser.add_argument("--format", choices=["csv", "json"], default="csv", help="Output format (default: csv)")
    parser.add_argument("--root", default=ROOT_TAXONOMY_ID, help="Root taxonomy node ID to start crawl from")
    args = parser.parse_args()

    session = requests.Session()
    spots: list[Spot] = []

    print(f"Starting Surfline spots crawl from root node: {args.root}")
    print(f"Output: {args.output} ({args.format.upper()})\n")

    crawl(node_id=args.root, session=session, spots=spots)

    print(f"\nCrawl complete. Found {len(spots)} spots total.\n")

    if args.format == "json":
        save_json(spots, args.output)
    else:
        save_csv(spots, args.output)


if __name__ == "__main__":
    main()
