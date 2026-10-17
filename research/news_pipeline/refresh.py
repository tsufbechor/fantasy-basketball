#!/usr/bin/env python3
"""Manually refresh minimal NBA player-news metadata from RotoWire's public RSS feed.

The feed descriptions/headlines are parsed in memory only. Persistent records contain a
stable item ID, source/profile link, timestamps, player identity, category tags, and a
short rule-based paraphrase. No page scraping, login, or hidden endpoint is used.
"""
from __future__ import annotations

import argparse
import csv
import email.utils
import hashlib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_FEED = "https://www.rotowire.com/rss/news.php?sport=NBA"
ROSTER = ROOT / "research/rosters_injuries/rosters_2026-27.csv"
ALIAS_PATH = HERE / "player_aliases.json"
STORE = HERE / "data/news.json"
SAMPLE = HERE / "data/sample_records.json"
USER_AGENT = "FantasyBasketballPersonalRSSReader/0.1 (manual refresh)"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_pub_date(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            # RotoWire's feed uses RFC-style dates with US abbreviations plus AM/PM,
            # which Python's email parser may leave naive. Resolve common US zones.
            match = re.match(r"^(.*?\s(?:AM|PM))\s+([A-Z]{2,5})$", value.strip(), re.I)
            zones = {"PST": -8, "PDT": -7, "MST": -7, "MDT": -6,
                     "CST": -6, "CDT": -5, "EST": -5, "EDT": -4,
                     "UTC": 0, "GMT": 0}
            if not match or match.group(2).upper() not in zones:
                return None, value
            naive = datetime.strptime(match.group(1), "%a, %d %b %Y %I:%M:%S %p")
            from datetime import timedelta
            parsed = naive.replace(tzinfo=timezone(timedelta(hours=zones[match.group(2).upper()])))
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"), value
    except (TypeError, ValueError, OverflowError):
        return None, value


def normalized_name(value: str) -> str:
    value = value.casefold().replace("’", "'")
    value = re.sub(r"[^a-z0-9 ]", "", value)
    return " ".join(value.split())


def roster_lookup() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    if not ROSTER.exists():
        return result
    with ROSTER.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = normalized_name(row.get("player_name", ""))
            if key:
                result[key] = {"player_id": row.get("player_id", ""),
                               "team_abbreviation": row.get("team_abbreviation", ""),
                               "season_id": row.get("season_id", "")}
    return result


def alias_lookup() -> dict[str, str]:
    if not ALIAS_PATH.exists():
        return {}
    with ALIAS_PATH.open(encoding="utf-8") as f:
        aliases = json.load(f)
    return {normalized_name(alias): canonical for alias, canonical in aliases.items()}


def classify_and_paraphrase(player: str, title: str) -> tuple[list[str], str]:
    detail = title.partition(":")[2].strip().casefold()
    tags: list[str] = []
    injury_terms = ("injur", "illness", "sick", "concussion", "sprain", "fracture",
                    "surgery", "hamstring", "ankle", "knee", "foot", "back", "hip",
                    "shoulder", "wrist", "elbow", "rest", "health")
    if any(term in detail for term in injury_terms):
        tags.append("injury")
    if any(term in detail for term in ("return", "expected to play", "will play", "available", "cleared")):
        tags.append("return")
    if any(term in detail for term in ("out", "sitting out", "unavailable", "will miss")):
        tags.append("availability")
    if any(term in detail for term in ("minute", "workload", "restriction", "rotation")):
        tags.append("minutes")
    if any(term in detail for term in ("start", "starting", "starter", "lineup")):
        tags.append("starting_role")
    if any(term in detail for term in ("signed", "waived", "trade", "traded", "contract", "released")):
        tags.append("transaction")
    if not tags:
        tags.append("general")

    # Short, rule-based paraphrases avoid retaining or reproducing the feed's prose.
    if "return" in tags and "expected to play" in detail and "preseason" in detail:
        summary = f"{player} is expected to return during preseason."
    elif "availability" in tags and "out" in detail:
        count = re.search(r"\b(one|two|three|four|five|\d+)\s+(?:more\s+)?games?\b", detail)
        if "season" in detail:
            summary = f"{player} is reported unavailable for the season."
        elif count:
            summary = f"{player} is reported unavailable for the next {count.group(1)} games."
        else:
            summary = f"{player} is reported unavailable for an upcoming game."
    elif "availability" in tags and "sitting out" in detail:
        summary = f"{player} is reported to miss a listed upcoming game."
    elif "injury" in tags and "illness" in detail:
        summary = f"An illness is reported to be affecting {player}."
    elif "transaction" in tags:
        summary = f"A roster or contract move involving {player} was reported."
    elif "starting_role" in tags:
        summary = f"A starting-role or lineup update for {player} was reported."
    elif "minutes" in tags:
        summary = f"A playing-time or workload update for {player} was reported."
    elif "return" in tags and "injury" in tags:
        summary = f"An injury-related availability or return update for {player} was reported."
    elif "return" in tags:
        summary = f"An availability or return update for {player} was reported."
    elif "injury" in tags:
        summary = f"An injury or health update for {player} was reported."
    else:
        summary = f"A player-related update for {player} was reported."
    return tags, summary


def publisher_player_id(profile_url: str) -> str | None:
    # RotoWire profile URL suffix is its own profile key, not an NBA/ESPN ID.
    match = re.search(r"-(\d+)(?:[/?#]|$)", urlparse(profile_url).path)
    return match.group(1) if match else None


def parse_feed(xml_bytes: bytes, fetched_at: str, roster: dict[str, dict[str, str]], aliases: dict[str, str]) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    parsed: list[dict] = []
    for item in root.findall("./channel/item"):
        guid = (item.findtext("guid") or "").strip()
        title = (item.findtext("title") or "").strip()
        profile_url = (item.findtext("link") or "").strip()
        if profile_url:
            parsed_url = urlparse(profile_url)
            normalized_path = "/" + "/".join(part for part in parsed_url.path.split("/") if part)
            profile_url = parsed_url._replace(path=normalized_path).geturl()
        published, published_raw = parse_pub_date(item.findtext("pubDate"))
        if not guid or not title:
            continue
        player_raw = title.partition(":")[0].strip()
        canonical = aliases.get(normalized_name(player_raw), player_raw)
        roster_entry = roster.get(normalized_name(canonical))
        tags, summary = classify_and_paraphrase(canonical, title)
        # Hash the source's minimal mutable metadata without persisting the original headline.
        description_for_digest_only = (item.findtext("description") or "").strip()
        digest = hashlib.sha256("\n".join((title, description_for_digest_only, profile_url, published_raw or "")).encode()).hexdigest()
        parsed.append({
            "event_id": f"rotowire:{guid}",
            "source": "RotoWire",
            "source_item_id": guid,
            "source_url": profile_url,
            "publisher_player_id": publisher_player_id(profile_url),
            "published_at": published,
            "published_at_source_tz": published_raw,
            "fetched_at": fetched_at,
            "player_name": canonical,
            "player_name_as_reported": player_raw,
            "player_match": ({"status": "matched", **roster_entry} if roster_entry else {"status": "unmatched", "player_id": None, "team_abbreviation": None}),
            "summary": summary,
            "tags": tags,
            "report_kind": "historical_news_event",
            "current_status": "not_inferred; verify against a current roster/injury source",
            "source_metadata_sha256": digest,
        })
    return parsed


def fetch(url: str) -> tuple[bytes, dict[str, str | None]]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"Feed returned HTTP {response.status}")
        headers = response.headers
        return response.read(), {"http_date": headers.get("Date"),
            "http_last_modified": headers.get("Last-Modified"),
            "cache_control": headers.get("Cache-Control"),
            "etag": headers.get("ETag")}


def read_store(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "source": "RotoWire", "records": []}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def merge(existing: dict, incoming: list[dict], fetched_at: str) -> tuple[dict, dict]:
    by_id = {record["event_id"]: record for record in existing.get("records", [])}
    counts = {"fetched": len(incoming), "new": 0, "revised": 0, "unchanged": 0, "unmatched": 0}
    for item in incoming:
        counts["unmatched"] += item["player_match"]["status"] == "unmatched"
        old = by_id.get(item["event_id"])
        if old is None:
            item["first_seen_at"] = fetched_at
            item["last_seen_at"] = fetched_at
            item["revision_count"] = 0
            item["revisions"] = []
            by_id[item["event_id"]] = item
            counts["new"] += 1
            continue
        # Keep a revision attached to the same event ID. A corrected headline is not a new injury event.
        comparable = ("source_metadata_sha256", "summary", "tags", "published_at", "player_name", "source_url")
        if any(old.get(field) != item.get(field) for field in comparable):
            old.setdefault("revisions", []).append({"observed_at": fetched_at,
                "previous_metadata_sha256": old.get("source_metadata_sha256"),
                "metadata_sha256": item.get("source_metadata_sha256"),
                "previous_summary": old.get("summary"), "summary": item.get("summary"),
                "previous_tags": old.get("tags"), "tags": item.get("tags")})
            old["revision_count"] = old.get("revision_count", 0) + 1
            counts["revised"] += 1
        else:
            counts["unchanged"] += 1
        # Preserve first-seen and revision history. Refresh only current normalized fields.
        for key, value in item.items():
            if key not in ("first_seen_at", "revisions", "revision_count", "last_seen_at"):
                old[key] = value
        old["last_seen_at"] = fetched_at
    existing["records"] = sorted(by_id.values(), key=lambda record: (record.get("published_at") or "", record["event_id"]), reverse=True)
    existing["last_fetch_at"] = fetched_at
    existing["source_url"] = DEFAULT_FEED
    return existing, counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed-file", type=Path, help="Use an already retrieved XML fixture for offline processing")
    parser.add_argument("--feed-url", default=DEFAULT_FEED)
    parser.add_argument("--store", type=Path, default=STORE)
    parser.add_argument("--sample", type=Path, default=SAMPLE)
    args = parser.parse_args()

    try:
        if args.feed_file:
            xml_bytes = args.feed_file.read_bytes()
            source_http = {"http_date": None, "http_last_modified": None,
                           "cache_control": None, "etag": None,
                           "retrieval_method": "local_fixture"}
        else:
            xml_bytes, source_http = fetch(args.feed_url)
            source_http["retrieval_method"] = "publisher_provided_rss"
        fetched_at = now_utc()
        incoming = parse_feed(xml_bytes, fetched_at, roster_lookup(), alias_lookup())
        existing = read_store(args.store)
        merged, counts = merge(existing, incoming, fetched_at)
        merged["source_http"] = source_http
        args.store.parent.mkdir(parents=True, exist_ok=True)
        args.store.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Separate sample is a compact projection; no original headline/description/body is stored.
        args.sample.write_text(json.dumps({"generated_at": fetched_at, "count": min(8, len(merged["records"])),
            "records": [{k: r.get(k) for k in ("event_id", "source", "source_item_id", "source_url", "published_at", "published_at_source_tz", "fetched_at", "player_name", "player_match", "summary", "tags", "report_kind", "current_status", "revision_count")} for r in merged["records"][:8]]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"counts": counts, "total_stored_events": len(merged["records"]), "store": str(args.store), "sample": str(args.sample)}, indent=2))
        return 0
    except Exception as exc:
        print(f"refresh failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
