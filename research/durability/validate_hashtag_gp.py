#!/usr/bin/env python3
"""Check one archived Hashtag preseason GP projection against NBA actuals.

This is a small feasibility check on the archived Top 30 page, not a sufficient
model-training set. It reads local NBA LeagueDash caches and writes locally.
"""
from __future__ import annotations

import csv
import gzip
import json
import re
import unicodedata
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "career" / "raw"
OUT = Path(__file__).resolve().parent / "hashtag_2025_26_preseason_gp_validation.csv"
STAMP = "20251009174024"
PAGE = f"https://web.archive.org/web/{STAMP}id_/https://hashtagbasketball.com/fantasy-basketball-projections"
ACTUAL_SEASON_FILE = RAW / "league_dash_2025-26_base.json"
PRIOR_SEASON_FILE = RAW / "league_dash_2024-25_base.json"


def norm(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", ascii_name)


def actuals_by_name(path: Path) -> dict[str, tuple[str, int]]:
    doc = json.loads(path.read_text())
    ix = {name: i for i, name in enumerate(doc["columns"])}
    games: dict[str, int] = {}
    names: dict[str, str] = {}
    for rec in doc["data"]:
        key = norm(str(rec[ix["PLAYER_NAME"]]))
        names[key] = str(rec[ix["PLAYER_NAME"]])
        games[key] = games.get(key, 0) + int(rec[ix["GP"]] or 0)
    # NBA API data can expose multi-team stints. Hashtag-to-NBA exact full-name
    # matching is unambiguous for this sample; no fuzzy matching is attempted.
    return {name: (names[name], gp) for name, gp in games.items()}


def main() -> None:
    if not ACTUAL_SEASON_FILE.exists():
        raise SystemExit(f"Missing actuals cache: {ACTUAL_SEASON_FILE}")
    req = urllib.request.Request(PAGE, headers={"Accept-Encoding": "identity"})
    body = urllib.request.urlopen(req, timeout=45).read()
    if body.startswith(b"\x1f\x8b"):
        body = gzip.decompress(body)
    soup = BeautifulSoup(body, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    selected = []
    for sel in soup.select("select"):
        selected.extend(o.get_text(" ", strip=True) for o in sel.select("option[selected]"))
    if "2025-26" not in title or "2025-26 Rest of Season Projections" not in selected:
        raise SystemExit(f"Unexpected archived page title/season: {title}; {selected}")
    table = soup.select_one("#ContentPlaceHolder1_GridView1")
    if table is None:
        raise SystemExit("Archived rankings table not found")
    header = [c.get_text(" ", strip=True) for c in table.select("tr")[0].find_all(["th", "td"], recursive=False)]
    gp_col = header.index("GP")
    actuals = actuals_by_name(ACTUAL_SEASON_FILE)
    prior = actuals_by_name(PRIOR_SEASON_FILE) if PRIOR_SEASON_FILE.exists() else {}
    rows = []
    for tr in table.select("tr")[1:]:
        cells = tr.find_all(["th", "td"], recursive=False)
        link = tr.select_one('a[id*="GridView1_HyperLink1_"]')
        if not link:
            continue
        name = link.get_text(" ", strip=True)
        vals = [c.get_text(" ", strip=True) for c in cells]
        try:
            projected = float(vals[gp_col])
        except (IndexError, ValueError):
            continue
        key = norm(name)
        actual = actuals.get(key)
        id_match = re.search(r"/(\d+)/player", link.get("href", ""))
        prior_actual = prior.get(key)
        rows.append({"hashtag_player_id": id_match.group(1) if id_match else "",
                     "player": name, "projected_gp": projected,
                     "nba_api_match": actual[0] if actual else "",
                     "actual_gp_2025_26": actual[1] if actual else "",
                     "actual_gp_2024_25": prior_actual[1] if prior_actual else "",
                     "gp_error_projected_minus_actual": projected - actual[1] if actual else "",
                     "archive_timestamp_utc": STAMP})
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    matched = [r for r in rows if r["actual_gp_2025_26"] != ""]
    print(f"page={title}; selections={selected[:10]}; parsed={len(rows)}; matched={len(matched)}")
    if matched:
        actual = [r["actual_gp_2025_26"] for r in matched]
        forecasts = {"Hashtag GP": [r["projected_gp"] for r in matched],
                     "Fixed 80% of 82": [65.6] * len(matched)}
        with_prior = [r for r in matched if r["actual_gp_2024_25"] != ""]
        if with_prior:
            forecasts["Prior-season GP"] = [r["actual_gp_2024_25"] for r in with_prior]
        print("top-30 GP forecast check (common sample unless noted):")
        for name, pred in forecasts.items():
            target = actual if len(pred) == len(actual) else [r["actual_gp_2025_26"] for r in with_prior]
            err = [p - y for p, y in zip(pred, target)]
            print(f"{name}: n={len(err)}, mean bias={sum(err)/len(err):.1f} GP, MAE={sum(abs(e) for e in err)/len(err):.1f} GP")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
