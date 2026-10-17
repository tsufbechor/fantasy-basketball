#!/usr/bin/env python3
"""Join Hashtag snapshots, ESPN rosters, and NBA career actuals for 8-cat review.

Inputs are read-only. All generated files are written under data/consolidated/.
The scoring below is a transparent diagnostic and does not reproduce Hashtag.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "consolidated"
CAREER = ROOT / "data" / "career"
ROSTER = ROOT / "research" / "rosters_injuries" / "rosters_2026-27.csv"
INJURY_EVENTS = ROOT / "research" / "rosters_injuries" / "injuries_2026-27.csv"
NEWS = ROOT / "research" / "news_pipeline" / "data" / "news.json"
SLEEPER_MENTIONS = ROOT / "research" / "sleepers_2025_26" / "player_mentions.csv"
LEAGUE = ROOT / "data" / "espn" / "league_9490871_2026_27.json"
SNAPSHOTS = {
    "2024-25": ROOT / "Fantasy Basketball Rankings 2022-25 _ Hashtag Basketball.html",
    "2025-26": ROOT / "Fantasy Basketball Rankings 2025-26 _ Hashtag Basketball.html",
    "2026-27": ROOT / "hashtag_2026_27_no_to.html",
}
HISTORICAL_SEASONS = ("2024-25", "2025-26")
PROJECTION_SEASON = "2026-27"
MAX_GP = 82.0
COUNT_CATS = ("three_pm", "points", "rebounds", "assists", "steals", "blocks")
SCORING_CATS = ("fg_impact", "ft_impact", *COUNT_CATS)
CAT_LABELS = {
    "three_pm": "3PM", "points": "PTS", "rebounds": "REB", "assists": "AST",
    "steals": "STL", "blocks": "BLK", "fg_impact": "FG impact", "ft_impact": "FT impact",
}


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", value)


def team_key(value: str) -> str:
    aliases = {"GSW": "GS", "SAS": "SA", "NOP": "NO", "PHX": "PHO",
               "NYK": "NY", "BKN": "BK", "UTA": "UTAH", "WSH": "WAS"}
    return aliases.get(value.strip().upper(), value.strip().upper())


def number(value: Any) -> float | None:
    if value is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(m.group()) if m else None


def option_values(soup: BeautifulSoup, field_suffix: str) -> list[str]:
    select = soup.find("select", id=re.compile(field_suffix + r"$"))
    return [o.get_text(" ", strip=True) for o in select.select("option[selected]")] if select else []


def parse_hashtag_page(path: Path, season: str) -> tuple[dict[str, dict], dict]:
    soup = BeautifulSoup(path.read_text(errors="replace"), "html.parser")
    table = soup.select_one("#ContentPlaceHolder1_GridView1")
    if table is None:
        raise ValueError(f"Missing rankings table in {path.name}")
    header = [c.get_text(" ", strip=True).upper() for c in table.select("tr")[0].find_all(["th", "td"], recursive=False)]
    column = {name: i for i, name in enumerate(header)}
    if "TREB" in column:
        column["REB"] = column["TREB"]
    required = {"R#", "PLAYER", "POS", "TEAM", "GP", "MPG", "FG%", "FT%", "3PM", "PTS", "REB", "AST", "STL", "BLK", "TOTAL"}
    if not required.issubset(column):
        raise ValueError(f"Missing Hashtag columns in {path.name}: {sorted(required - set(column))}")
    selected = {
        "source_file": path.name,
        "season_label": season,
        "dataset": option_values(soup, "DDDURATION")[0] if option_values(soup, "DDDURATION") else "",
        "based_on": option_values(soup, "DDRANK")[0] if option_values(soup, "DDRANK") else "",
        "type": option_values(soup, "DDTYPE")[0] if option_values(soup, "DDTYPE") else "",
        "gp_penalty": option_values(soup, "DDPEN")[0] if option_values(soup, "DDPEN") else "not exposed in snapshot",
        "position_adp_source": option_values(soup, "DDPOSFROM")[0] if option_values(soup, "DDPOSFROM") else "",
        "min_gp": option_values(soup, "DDGAMES")[0] if option_values(soup, "DDGAMES") else "",
        "selected_categories": [
            inp.get("id", "").removeprefix("ContentPlaceHolder1_CB")
            for inp in soup.select('input[type="checkbox"][id^="ContentPlaceHolder1_CB"]')
            if inp.has_attr("checked")
        ],
    }
    rows: dict[str, dict] = {}
    duplicate_rows = []
    raw_player_rows = 0
    for tr in table.select("tr")[1:]:
        link = tr.select_one('a[id*="GridView1_HyperLink1_"]')
        if not link:
            continue
        raw_player_rows += 1
        id_match = re.search(r"/(\d+)/player", link.get("href", ""))
        if not id_match:
            raise ValueError(f"Hashtag player link lacks ID: {link.get('href')}")
        hid = id_match.group(1)
        cells = tr.find_all(["th", "td"], recursive=False)
        if len(cells) != len(header):
            raise ValueError(f"Unexpected row with {len(cells)} cells in {path.name}: {hid}")
        def cell_text(i: int) -> str:
            return cells[i].get_text(" ", strip=True)

        def display_stat(header_name: str) -> tuple[float | None, float | None, float | None]:
            i = column[header_name]
            td = cells[i]
            value_el = td.find("span", id=re.compile(r"GridView1_L"))
            value = number(value_el.get_text(" ", strip=True) if value_el else cell_text(i))
            attempts_el = td.select_one("span.float-end")
            pair = re.search(r"\((\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)\)",
                             attempts_el.get_text(" ", strip=True) if attempts_el else "")
            return value, float(pair.group(1)) if pair else None, float(pair.group(2)) if pair else None

        fg_pct, fgm_pg, fga_pg = display_stat("FG%")
        ft_pct, ftm_pg, fta_pg = display_stat("FT%")
        notes = {"positive": [], "caution": []}
        for span in cells[1].select("span[data-bs-original-title]"):
            cls = " ".join(span.get("class", []))
            note = span.get("data-bs-original-title", "").strip()
            if note:
                bucket = "positive" if "text-success" in cls else "caution" if "text-danger" in cls else "other"
                notes.setdefault(bucket, []).append(note)
        row = {
            "hashtag_id": hid,
            "hashtag_name": link.get_text(" ", strip=True),
            "season": season,
            "rank": int(number(cell_text(column["R#"])) or 0),
            "adp": number(cell_text(column["ADP"])) if "ADP" in column else None,
            "position": cell_text(column["POS"]),
            "hashtag_team": cell_text(column["TEAM"]),
            "gp": number(cell_text(column["GP"])),
            "mpg": number(cell_text(column["MPG"])),
            "fg_pct": fg_pct,
            "fgm_pg_display": fgm_pg,
            "fga_pg_display": fga_pg,
            "ft_pct": ft_pct,
            "ftm_pg_display": ftm_pg,
            "fta_pg_display": fta_pg,
            "three_pm": display_stat("3PM")[0],
            "points": display_stat("PTS")[0],
            "rebounds": display_stat("REB")[0],
            "assists": display_stat("AST")[0],
            "steals": display_stat("STL")[0],
            "blocks": display_stat("BLK")[0],
            "hashtag_total": number(cell_text(column["TOTAL"])),
            "hashtag_positive_notes_json": json.dumps(notes["positive"], ensure_ascii=False),
            "hashtag_caution_notes_json": json.dumps(notes["caution"], ensure_ascii=False),
        }
        if hid in rows:
            duplicate_rows.append(hid)
            previous = rows[hid]
            comparable = {k: v for k, v in row.items() if k not in ("rank", "adp")}
            prior_comparable = {k: v for k, v in previous.items() if k not in ("rank", "adp")}
            if comparable != prior_comparable:
                raise ValueError(f"Duplicate Hashtag ID {hid} has conflicting stats in {path.name}")
            if row["rank"] < previous["rank"]:
                rows[hid] = row
        else:
            rows[hid] = row
    selected["raw_player_rows"] = raw_player_rows
    selected["parsed_player_rows"] = len(rows)
    selected["duplicate_source_rows_collapsed"] = len(duplicate_rows)
    selected["duplicate_hashtag_ids"] = sorted(set(duplicate_rows), key=int)
    return rows, selected


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def maybe_float(x: Any) -> float | None:
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def mean_sd(values: list[float]) -> tuple[float, float]:
    mu = statistics.mean(values)
    sd = statistics.pstdev(values)
    return mu, sd


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mapping = read_csv(CAREER / "player_mapping.csv")
    career = read_csv(CAREER / "player_seasons.csv")
    roster = read_csv(ROSTER)
    injury_events = read_csv(INJURY_EVENTS)
    news_doc = json.loads(NEWS.read_text())
    news_records = news_doc.get("records", [])
    mention_rows = read_csv(SLEEPER_MENTIONS)
    league = json.loads(LEAGUE.read_text())
    snapshots: dict[str, dict[str, dict]] = {}
    page_meta = {}
    for season, path in SNAPSHOTS.items():
        snapshots[season], page_meta[season] = parse_hashtag_page(path, season)
    for season in HISTORICAL_SEASONS:
        if "Regular Season" not in page_meta[season]["dataset"]:
            raise AssertionError(f"Historical HTML does not identify actual regular-season data: {season}")
    if page_meta[PROJECTION_SEASON]["gp_penalty"] != "20%":
        raise AssertionError("Current Hashtag snapshot no longer has the expected 20% GP penalty selected")
    expected_categories = {"FGP", "FTP", "3PM", "PTS", "REB", "AST", "STL", "BLK"}
    for season, meta in page_meta.items():
        if set(meta["selected_categories"]) != expected_categories:
            raise AssertionError(f"Unexpected category selection for {season}: {meta['selected_categories']}")

    mapping_by_id = {r["hashtag_id"]: r for r in mapping}
    if len(mapping_by_id) != len(mapping):
        raise AssertionError("Duplicate Hashtag IDs in source mapping")
    all_ids = sorted(set(mapping_by_id) | set().union(*(set(d) for d in snapshots.values())), key=int)
    if len(all_ids) != 366:
        raise AssertionError(f"Expected 366 union Hashtag IDs from the saved snapshots; found {len(all_ids)}")

    # Use exact normalized Hashtag name first; reviewed NBA mapping aliases may
    # offer a second exact canonical-name key. Never fuzzy-match ESPN IDs.
    roster_by_name: dict[str, list[dict]] = defaultdict(list)
    for r in roster:
        roster_by_name[norm(r["player_name"])].append(r)
    mentions_by_id: dict[str, list[dict]] = defaultdict(list)
    for r in mention_rows:
        if r.get("hashtag_player_id"):
            mentions_by_id[r["hashtag_player_id"]].append(r)
    canonical = []
    espn_conflicts = []
    for hid in all_ids:
        m = mapping_by_id.get(hid, {})
        hname = m.get("hashtag_name") or next((d[hid]["hashtag_name"] for d in snapshots.values() if hid in d), "")
        nba_name = m.get("nba_full_name", "")
        candidate_keys = list(dict.fromkeys(k for k in (norm(hname), norm(nba_name)) if k))
        candidates = [r for k in candidate_keys for r in roster_by_name.get(k, [])]
        unique_candidates = {(r["player_id"], r["team_abbreviation"], r["player_name"]): r for r in candidates}
        candidates = list(unique_candidates.values())
        player_ids = {r["player_id"] for r in candidates}
        roster_teams = {r["team_abbreviation"] for r in candidates}
        espn_status, espn_id, espn_name, espn_team = "no_exact_roster_match", "", "", ""
        if len(candidates) == 1 and len(player_ids) == 1:
            r = candidates[0]
            espn_status, espn_id, espn_name, espn_team = "exact_normalized_name", r["player_id"], r["player_name"], r["team_abbreviation"]
        elif len(player_ids) > 1 or len(roster_teams) > 1:
            espn_status = "ambiguous_roster_name_or_team"
            espn_conflicts.append({"hashtag_id": hid, "hashtag_name": hname,
                                  "candidates_json": json.dumps(candidates, ensure_ascii=False)})
        current = snapshots[PROJECTION_SEASON].get(hid, {})
        latest = next((r for r in career if r["player_id"] == m.get("nba_player_id") and r["season"] == "2025-26"), {})
        conf_team = bool(current.get("hashtag_team") and espn_team and team_key(current["hashtag_team"]) != team_key(espn_team))
        canonical.append({
            "hashtag_id": hid, "hashtag_name": hname,
            "nba_player_id": m.get("nba_player_id", ""), "nba_full_name": nba_name,
            "nba_mapping_status": m.get("mapping_status", "unmatched"),
            "mapping_snapshots": m.get("snapshots", ""),
            "espn_player_id": espn_id, "espn_roster_name": espn_name,
            "espn_roster_team": espn_team, "espn_join_status": espn_status,
            "hashtag_team_2026_27": current.get("hashtag_team", ""),
            "team_conflict_hashtag_vs_espn": conf_team,
            "latest_actual_season": latest.get("season", ""),
            "latest_actual_team_or_teams": latest.get("team_or_teams", ""),
            "latest_actual_gp": latest.get("games_played", ""),
            "sleepers_2025_26_historical_mention_count": len(mentions_by_id.get(hid, [])),
            "sleepers_2025_26_articles_json": json.dumps(sorted({r["article_id"] for r in mentions_by_id.get(hid, [])}), ensure_ascii=False),
            "sleepers_2025_26_classifications_json": json.dumps(sorted({r["classification"] for r in mentions_by_id.get(hid, [])}), ensure_ascii=False),
        })

    # Join actual HTML snapshots and NBA Stats actuals into one row per tracked
    # player-season. Missing HTML rows are explicit; unobserved NBA seasons stay blank.
    season_rows = {(r["player_id"], r["season"]): r for r in career}
    actuals = []
    for p in canonical:
        for season in HISTORICAL_SEASONS:
            html = snapshots[season].get(p["hashtag_id"], {})
            nba = season_rows.get((p["nba_player_id"], season), {}) if p["nba_player_id"] else {}
            actual = {"hashtag_id": p["hashtag_id"], "hashtag_name": p["hashtag_name"],
                      "nba_player_id": p["nba_player_id"], "season": season,
                      "html_snapshot_included": bool(html),
                      "historical_hashtag_rank": html.get("rank", ""),
                      "historical_hashtag_total": html.get("hashtag_total", ""),
                      "historical_hashtag_gp": html.get("gp", ""),
                      "historical_hashtag_mpg": html.get("mpg", ""),
                      "historical_hashtag_fg_pct": html.get("fg_pct", ""),
                      "historical_hashtag_fgm_pg_display": html.get("fgm_pg_display", ""),
                      "historical_hashtag_fga_pg_display": html.get("fga_pg_display", ""),
                      "historical_hashtag_ft_pct": html.get("ft_pct", ""),
                      "historical_hashtag_ftm_pg_display": html.get("ftm_pg_display", ""),
                      "historical_hashtag_fta_pg_display": html.get("fta_pg_display", ""),
                      "historical_hashtag_3pm": html.get("three_pm", ""),
                      "historical_hashtag_pts": html.get("points", ""),
                      "historical_hashtag_reb": html.get("rebounds", ""),
                      "historical_hashtag_ast": html.get("assists", ""),
                      "historical_hashtag_stl": html.get("steals", ""),
                      "historical_hashtag_blk": html.get("blocks", ""),
                      "nba_actual_available": bool(nba),
                      "nba_team_or_teams": nba.get("team_or_teams", ""),
                      "nba_gp": nba.get("games_played", ""), "nba_age": nba.get("age", ""),
                      "nba_mpg": nba.get("minutes_per_game", ""),
                      "nba_fgm_total": nba.get("fgm_total", ""), "nba_fga_total": nba.get("fga_total", ""),
                      "nba_fg_pct": nba.get("fg_pct", ""), "nba_ftm_total": nba.get("ftm_total", ""),
                      "nba_fta_total": nba.get("fta_total", ""), "nba_ft_pct": nba.get("ft_pct", ""),
                      "nba_3pm_total": nba.get("fg3m_total", ""), "nba_pts_total": nba.get("points_total", ""),
                      "nba_reb_total": nba.get("rebounds_total", ""), "nba_ast_total": nba.get("assists_total", ""),
                      "nba_stl_total": nba.get("steals_total", ""), "nba_blk_total": nba.get("blocks_total", ""),
                      "nba_usage_pct": nba.get("usage_pct", "")}
            gp = maybe_float(nba.get("games_played"))
            for field, total in (("3pm", "fg3m_total"), ("pts", "points_total"),
                                 ("reb", "rebounds_total"), ("ast", "assists_total"),
                                 ("stl", "steals_total"), ("blk", "blocks_total")):
                value = maybe_float(nba.get(total))
                actual[f"nba_{field}_per_game"] = value / gp if gp and value is not None else ""
            actuals.append(actual)

    # Last-three-season career facts (raw NBA age, usage, GP, and per-game role).
    trends_by_player: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in career:
        if r["season"] in ("2023-24", "2024-25", "2025-26"):
            trends_by_player[r["player_id"]][r["season"]] = r

    projection_rows = list(snapshots[PROJECTION_SEASON].values())
    if len(projection_rows) != 300:
        raise AssertionError(f"Expected 300 2026–27 projection rows, got {len(projection_rows)}")
    # Weighted percentage references and category z-score moments are frozen on
    # this entire 300-player projection universe.
    # Displayed makes are rounded to 0.1 and may disagree slightly with the
    # displayed percentage. Use pct × attempts for impact math; retain makes.
    for r in projection_rows:
        r["fgm_pg_used_for_impact"] = r["fg_pct"] * r["fga_pg_display"]
        r["ftm_pg_used_for_impact"] = r["ft_pct"] * r["fta_pg_display"]
    fg_makes = [r["fgm_pg_used_for_impact"] for r in projection_rows]
    fg_atts = [r["fga_pg_display"] for r in projection_rows if r["fga_pg_display"] is not None]
    ft_makes = [r["ftm_pg_used_for_impact"] for r in projection_rows]
    ft_atts = [r["fta_pg_display"] for r in projection_rows if r["fta_pg_display"] is not None]
    if len(fg_makes) != len(projection_rows) or len(ft_makes) != len(projection_rows):
        raise AssertionError("Missing embedded FGM/FGA or FTM/FTA pair in a 2026–27 row")
    p_ref_fg = sum(fg_makes) / sum(fg_atts)
    p_ref_ft = sum(ft_makes) / sum(ft_atts)
    for r in projection_rows:
        r["fg_impact"] = r["fgm_pg_used_for_impact"] - p_ref_fg * r["fga_pg_display"]
        r["ft_impact"] = r["ftm_pg_used_for_impact"] - p_ref_ft * r["fta_pg_display"]
    cat_stats = {cat: mean_sd([r[cat] for r in projection_rows]) for cat in SCORING_CATS}

    canonical_by_id = {p["hashtag_id"]: p for p in canonical}
    canonical_by_espn_id = {p["espn_player_id"]: p for p in canonical if p["espn_player_id"]}
    actual_by_id = defaultdict(dict)
    for r in actuals:
        actual_by_id[r["hashtag_id"]][r["season"]] = r
    base_total_means: dict[str, float] = {}
    base_total_sds: dict[str, float] = {}
    for cat in SCORING_CATS:
        totals = []
        for r in projection_rows:
            gp = r["gp"] or 0.0
            totals.append(r[cat] * gp)
        base_total_means[cat], base_total_sds[cat] = mean_sd(totals)
        if base_total_sds[cat] == 0:
            raise AssertionError(f"Zero baseline SD for {cat}")

    scored = []
    gp_scenarios = []
    for source in projection_rows:
        r = dict(source)
        p = canonical_by_id[source["hashtag_id"]]
        history = trends_by_player.get(p["nba_player_id"], {}) if p["nba_player_id"] else {}
        latest = history.get("2025-26", {})
        latest_html = actual_by_id[source["hashtag_id"]].get("2025-26", {})
        r.update({
            "nba_player_id": p["nba_player_id"], "nba_mapping_status": p["nba_mapping_status"],
            "espn_player_id": p["espn_player_id"], "espn_roster_team": p["espn_roster_team"],
            "espn_join_status": p["espn_join_status"],
            "team_conflict_hashtag_vs_espn": p["team_conflict_hashtag_vs_espn"],
            "latest_actual_gp": latest.get("games_played", ""),
            "latest_actual_mpg": latest.get("minutes_per_game", ""),
            "latest_actual_age": latest.get("age", ""),
            "latest_actual_usage_pct": latest.get("usage_pct", ""),
            "latest_actual_team_or_teams": latest.get("team_or_teams", ""),
            "hashtag_actuals_2025_26_present": bool(latest_html.get("nba_actual_available", False)),
            "sleepers_2025_26_historical_mention_count": len(mentions_by_id.get(source["hashtag_id"], [])),
            "sleepers_2025_26_articles_json": json.dumps(sorted({x["article_id"] for x in mentions_by_id.get(source["hashtag_id"], [])}), ensure_ascii=False),
            "sleepers_2025_26_classifications_json": json.dumps(sorted({x["classification"] for x in mentions_by_id.get(source["hashtag_id"], [])}), ensure_ascii=False),
        })
        for season in ("2023-24", "2024-25", "2025-26"):
            hist = history.get(season, {})
            r[f"age_{season}"] = hist.get("age", "")
            r[f"usage_pct_{season}"] = hist.get("usage_pct", "")
            r[f"mpg_{season}"] = hist.get("minutes_per_game", "")
            r[f"gp_{season}"] = hist.get("games_played", "")
        first_usage = maybe_float(history.get("2023-24", {}).get("usage_pct"))
        last_usage = maybe_float(history.get("2025-26", {}).get("usage_pct"))
        r["usage_change_2023_24_to_2025_26_pp"] = last_usage - first_usage if first_usage is not None and last_usage is not None else ""
        latest_stats = history.get("2025-26", {})
        latest_gp = maybe_float(latest_stats.get("games_played"))
        latest_mpg_value = maybe_float(latest_stats.get("minutes_per_game"))
        r["mpg_actual_2025_26"] = latest_mpg_value if latest_mpg_value is not None else ""
        r["mpg_projection_minus_actual"] = source["mpg"] - latest_mpg_value if latest_mpg_value is not None else ""
        source_totals = {
            "three_pm": "fg3m_total", "points": "points_total", "rebounds": "rebounds_total",
            "assists": "assists_total", "steals": "steals_total", "blocks": "blocks_total",
        }
        for cat, field in source_totals.items():
            value = maybe_float(latest_stats.get(field))
            pg = value / latest_gp if latest_gp and value is not None else None
            projection = source[cat]
            r[f"{cat}_pg_actual_2025_26"] = pg if pg is not None else ""
            r[f"{cat}_pg_projection_minus_actual"] = projection - pg if pg is not None else ""
        # FG/FT projected pct and volume deltas are explicit, not folded into age/usage.
        for label, actual_pct_field, projected_pct_field in (
            ("fg", "fg_pct", "fg_pct"), ("ft", "ft_pct", "ft_pct")):
            pct = maybe_float(latest_stats.get(actual_pct_field))
            r[f"{label}_pct_actual_2025_26"] = pct if pct is not None else ""
            r[f"{label}_pct_projection_minus_actual"] = source[projected_pct_field] - pct if pct is not None else ""
        r["hashtag_gp_penalty_selected_pct"] = page_meta[PROJECTION_SEASON]["gp_penalty"]
        for cat in SCORING_CATS:
            mu, sd = cat_stats[cat]
            z = (source[cat] - mu) / sd
            r[f"z_{cat}"] = z
        r["our_raw8cat_zsum"] = sum(r[f"z_{cat}"] for cat in SCORING_CATS)
        r["scoring_reference_players"] = len(projection_rows)
        r["fg_reference_weighted_pct"] = p_ref_fg
        r["ft_reference_weighted_pct"] = p_ref_ft
        r["projection_to_actual_delta_note"] = "Per-game Hashtag projection minus NBA Stats 2025-26 per-game actual; no adjustment applied"
        scored.append(r)

        base_gp = float(source["gp"] or 0)
        for scenario, gp in (("hashtag_projected_gp", base_gp),
                             ("hashtag_projected_gp_minus_5", max(0.0, base_gp - 5.0)),
                             ("hashtag_projected_gp_plus_5", min(MAX_GP, base_gp + 5.0))):
            row = {"hashtag_id": source["hashtag_id"], "player": source["hashtag_name"],
                   "scenario": scenario, "expected_gp_assumption": gp,
                   "gp_delta_vs_hashtag_projection": gp - base_gp,
                   "reference_universe": "2026-27 Hashtag Top 300, baseline Hashtag projected GP",
                   "reference_gp_penalty_pct_selected": page_meta[PROJECTION_SEASON]["gp_penalty"]}
            total_z = 0.0
            for cat in SCORING_CATS:
                raw_total = source[cat] * gp
                # Frozen baseline mean/SD: scenario comparisons do not refit scaling.
                z = (raw_total - base_total_means[cat]) / base_total_sds[cat]
                row[f"{cat}_season_total"] = raw_total
                row[f"z_{cat}_frozen_total_reference"] = z
                total_z += z
            row["raw_total_8cat_zsum_frozen_reference"] = total_z
            row["is_model_forecast"] = False
            row["scenario_definition"] = "Mechanical +/-5 game stress around Hashtag GP; not a probability or learned adjustment"
            gp_scenarios.append(row)

    # All key integrity and bounds checks run before outputs are accepted.
    assert len(canonical) == 366 and len({r["hashtag_id"] for r in canonical}) == 366
    assert len(actuals) == 366 * 2 and len({(r["hashtag_id"], r["season"]) for r in actuals}) == len(actuals)
    assert len(scored) == 300 and len({r["hashtag_id"] for r in scored}) == 300
    assert len(gp_scenarios) == 900 and len({(r["hashtag_id"], r["scenario"]) for r in gp_scenarios}) == 900
    assert 0 <= p_ref_fg <= 1 and 0 <= p_ref_ft <= 1
    for r in projection_rows:
        assert 0 <= r["gp"] <= MAX_GP, (r["hashtag_name"], r["gp"])
        for pct in (r["fg_pct"], r["ft_pct"]):
            assert 0 <= pct <= 1, (r["hashtag_name"], pct)
        assert r["fgm_pg_display"] <= r["fga_pg_display"] + .11, r["hashtag_name"]
        assert r["ftm_pg_display"] <= r["fta_pg_display"] + .11, r["hashtag_name"]
        for cat in COUNT_CATS:
            assert r[cat] >= 0, (r["hashtag_name"], cat, r[cat])
    collisions = Counter(r["espn_player_id"] for r in canonical if r["espn_player_id"])
    collision_ids = [pid for pid, n in collisions.items() if n > 1]
    if collision_ids:
        raise AssertionError(f"ESPN ID joined to multiple Hashtag IDs: {collision_ids}")
    for rank, row in enumerate(sorted(scored, key=lambda z: z["our_raw8cat_zsum"], reverse=True), start=1):
        row["our_raw8cat_rank"] = rank

    # Persist in stable, review-friendly order.
    write_csv(OUT / "tracked_players.csv", canonical)
    write_csv(OUT / "hashtag_actuals.csv", actuals)
    score_fields = ["hashtag_id", "hashtag_name", "rank", "adp", "position", "hashtag_team", "gp", "mpg",
                    "fg_pct", "fgm_pg_display", "fga_pg_display", "ft_pct", "ftm_pg_display", "fta_pg_display",
                    "three_pm", "points", "rebounds", "assists", "steals", "blocks", "hashtag_total",
                    "hashtag_gp_penalty_selected_pct", "hashtag_positive_notes_json", "hashtag_caution_notes_json",
                    "nba_player_id", "nba_mapping_status", "espn_player_id", "espn_roster_team", "espn_join_status",
                    "team_conflict_hashtag_vs_espn", "latest_actual_gp", "latest_actual_mpg", "latest_actual_age",
                    "latest_actual_usage_pct", "latest_actual_team_or_teams", "mpg_actual_2025_26",
                    "mpg_projection_minus_actual",
                    "sleepers_2025_26_historical_mention_count", "sleepers_2025_26_articles_json",
                    "sleepers_2025_26_classifications_json", "age_2023-24", "age_2024-25", "age_2025-26",
                    "usage_pct_2023-24", "usage_pct_2024-25", "usage_pct_2025-26", "usage_change_2023_24_to_2025_26_pp",
                    "mpg_2023-24", "mpg_2024-25", "mpg_2025-26", "gp_2023-24", "gp_2024-25", "gp_2025-26"]
    for cat in COUNT_CATS:
        score_fields.extend([f"{cat}_pg_actual_2025_26", f"{cat}_pg_projection_minus_actual"])
    for label in ("fg", "ft"):
        score_fields.extend([f"{label}_pct_actual_2025_26", f"{label}_pct_projection_minus_actual"])
    score_fields.extend(["fgm_pg_used_for_impact", "ftm_pg_used_for_impact", "fg_impact", "ft_impact",
                         *[f"z_{cat}" for cat in SCORING_CATS],
                         "our_raw8cat_zsum", "our_raw8cat_rank", "scoring_reference_players", "fg_reference_weighted_pct",
                         "ft_reference_weighted_pct", "projection_to_actual_delta_note"])
    write_csv(OUT / "hashtag_projections_2026_27.csv", scored, score_fields)
    write_csv(OUT / "baseline_scoring.csv", scored, score_fields)
    write_csv(OUT / "gp_sensitivity.csv", gp_scenarios)
    write_csv(OUT / "espn_join_conflicts.csv", espn_conflicts)

    # Preserve current reports as source metadata only. In particular, the
    # rule-based news summaries are not verified injury claims and these rows
    # never enter the scoring calculation above.
    evidence_events = []
    for item in news_records:
        match = item.get("player_match") or {}
        espn_id = str(match.get("player_id") or "")
        player = canonical_by_espn_id.get(espn_id, {})
        evidence_events.append({
            "event_id": item.get("event_id", ""), "source_type": "news_summary",
            "source": item.get("source", ""), "source_item_id": item.get("source_item_id", ""),
            "source_url": item.get("source_url", ""), "source_player_id": item.get("publisher_player_id", ""),
            "espn_player_id": espn_id, "hashtag_id": player.get("hashtag_id", ""),
            "hashtag_name": player.get("hashtag_name", ""),
            "player_name_as_reported": item.get("player_name_as_reported", item.get("player_name", "")),
            "reported_team": match.get("team_abbreviation", ""),
            "reported_status": "", "current_status": "not_inferred",
            "current_status_source_text": item.get("current_status", ""),
            "join_status": "exact_espn_id" if player else ("unmatched_espn_id" if espn_id else "no_espn_id"),
            "published_at": item.get("published_at", ""),
            "published_at_source_tz": item.get("published_at_source_tz", ""),
            "fetched_at": item.get("fetched_at", ""),
            "first_seen_at": item.get("first_seen_at", ""), "last_seen_at": item.get("last_seen_at", ""),
            "event_date_utc": "", "feed_source_timestamp": "", "season_id": match.get("season_id", ""),
            "summary": item.get("summary", ""),
            "summary_verification": "unverified_machine_summary",
            "tags_json": json.dumps(item.get("tags", []), ensure_ascii=False),
            "report_kind": item.get("report_kind", ""), "injury_type": "", "injury_location": "",
            "injury_detail": "", "return_date": "", "fantasy_status": "",
            "revision_count": item.get("revision_count", ""),
        })
    for item in injury_events:
        espn_id = str(item.get("player_id", ""))
        player = canonical_by_espn_id.get(espn_id, {})
        evidence_events.append({
            "event_id": f"espn-injury:{item.get('season_id','')}:{espn_id}:{item.get('event_date_utc','')}:{item.get('status','')}",
            "source_type": "espn_injury_event", "source": item.get("news_source", ""),
            "source_item_id": "", "source_url": "", "source_player_id": "",
            "espn_player_id": espn_id, "hashtag_id": player.get("hashtag_id", ""),
            "hashtag_name": player.get("hashtag_name", ""),
            "player_name_as_reported": item.get("player_name", ""),
            "reported_team": item.get("team_abbreviation", ""),
            "reported_status": item.get("status", ""), "current_status": "not_inferred",
            "current_status_source_text": "", "join_status": "exact_espn_id" if player else "unmatched_espn_id",
            "published_at": "", "published_at_source_tz": "", "fetched_at": "",
            "first_seen_at": "", "last_seen_at": "", "event_date_utc": item.get("event_date_utc", ""),
            "feed_source_timestamp": item.get("feed_source_timestamp", ""), "season_id": item.get("season_id", ""),
            "summary": "", "summary_verification": "reported_event_metadata",
            "tags_json": "[]", "report_kind": "", "injury_type": item.get("injury_type", ""),
            "injury_location": item.get("injury_location", ""), "injury_detail": item.get("injury_detail", ""),
            "return_date": item.get("return_date", ""), "fantasy_status": item.get("fantasy_status", ""),
            "revision_count": "",
        })
    event_fields = ["event_id", "source_type", "source", "source_item_id", "source_url", "source_player_id",
                    "espn_player_id", "hashtag_id", "hashtag_name", "player_name_as_reported", "reported_team",
                    "reported_status", "current_status", "current_status_source_text", "join_status", "published_at",
                    "published_at_source_tz", "fetched_at", "first_seen_at", "last_seen_at", "event_date_utc",
                    "feed_source_timestamp", "season_id", "summary", "summary_verification", "tags_json", "report_kind",
                    "injury_type", "injury_location", "injury_detail", "return_date", "fantasy_status", "revision_count"]
    assert len(evidence_events) == len(news_records) + len(injury_events)
    assert len({r["event_id"] for r in evidence_events}) == len(evidence_events)
    assert all(r["current_status"] == "not_inferred" for r in evidence_events)
    assert all(r["summary_verification"] == "unverified_machine_summary" for r in evidence_events if r["source_type"] == "news_summary")
    write_csv(OUT / "evidence_events.csv", evidence_events, event_fields)

    missing_nba = [r["hashtag_name"] for r in canonical if not r["nba_player_id"]]
    missing_espn = [r["hashtag_name"] for r in canonical if not r["espn_player_id"]]
    team_conflicts = [r for r in canonical if r["team_conflict_hashtag_vs_espn"]]
    latest_actuals = [r for r in career if r["season"] in HISTORICAL_SEASONS]
    multi_team_actuals = [r for r in latest_actuals if "/" in r["team_or_teams"]]
    league_settings = league.get("settings", {})
    selected_counts = {s: page_meta[s]["parsed_player_rows"] for s in page_meta}
    quality = {
        "source_counts": {
            "hashtag_ids_union": len(canonical), "nba_mapped": sum(bool(r["nba_player_id"]) for r in canonical),
            "nba_unmatched": len(missing_nba), "espn_exact_roster_join": sum(bool(r["espn_player_id"]) for r in canonical),
            "espn_unjoined_or_ambiguous": len(missing_espn), "current_projection_rows": len(scored),
            "historical_actual_rows": len(actuals), "historical_nba_player_season_rows_2024_25_2025_26": len(latest_actuals),
            "historical_multiteam_player_season_rows": len(multi_team_actuals),
            "espn_hashtag_team_conflicts": len(team_conflicts),
            "hashtag_rows_by_snapshot": selected_counts,
            "historical_snapshot_duplicate_rows_collapsed": {
                season: page_meta[season]["duplicate_source_rows_collapsed"] for season in HISTORICAL_SEASONS
            },
            "historical_sleeper_mention_rows": len(mention_rows),
            "unique_historical_sleeper_players": len(mentions_by_id),
            "evidence_event_rows": len(evidence_events),
            "news_summary_event_rows": len(news_records),
            "espn_injury_event_rows": len(injury_events),
            "evidence_events_exact_espn_id_join": sum(bool(r["hashtag_id"]) for r in evidence_events),
            "evidence_events_unmatched": sum(not bool(r["hashtag_id"]) for r in evidence_events),
        },
        "mapping_status_counts": dict(Counter(r["nba_mapping_status"] for r in canonical)),
        "espn_join_status_counts": dict(Counter(r["espn_join_status"] for r in canonical)),
        "unmatched_nba_names": missing_nba,
        "unmatched_espn_names": missing_espn,
        "team_conflicts": [{"hashtag_id": r["hashtag_id"], "name": r["hashtag_name"],
                            "hashtag_team": r["hashtag_team_2026_27"], "espn_team": r["espn_roster_team"]}
                           for r in team_conflicts],
        "page_settings": page_meta,
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in [*SNAPSHOTS.values(), CAREER / "player_mapping.csv",
                                       CAREER / "player_seasons.csv", ROSTER, LEAGUE, SLEEPER_MENTIONS,
                                       INJURY_EVENTS, NEWS]},
        "scoring": {
            "method": "raw 8-category per-game z-score sum over the 2026-27 Top 300 projected universe",
            "categories": list(SCORING_CATS), "category_order": [CAT_LABELS[c] for c in SCORING_CATS],
            "count_categories": [CAT_LABELS[c] for c in COUNT_CATS],
            "fg_reference_weighted_pct": p_ref_fg, "ft_reference_weighted_pct": p_ref_ft,
            "category_mean_and_population_sd": {cat: {"mean": cat_stats[cat][0], "population_sd": cat_stats[cat][1]}
                                                for cat in SCORING_CATS},
            "universe_size": len(projection_rows), "rounding": "Uses displayed Hashtag values (mostly 1 decimal); not hidden Hashtag category z inputs.",
            "shooting_impact_makes_policy": "Displayed percentage × displayed attempts defines derived makes for impact; rounded displayed makes remain separately preserved.",
            "hashtag_total_preserved": True, "hashtag_gp_penalty_preserved": page_meta[PROJECTION_SEASON]["gp_penalty"],
            "h2h_floor_applied_to_our_score": False,
        },
        "gp_sensitivity": {
            "scenarios": ["Hashtag projected GP", "Hashtag GP - 5", "Hashtag GP + 5 capped at 82"],
            "status": "mechanical stress test only; no probabilities, learned coefficients, replacement adjustment, or signed-z-score-times-GP shortcut",
            "fixed_reference": "2026-27 Top 300 baseline projected total-category means and population SDs are frozen for all scenarios.",
            "replacement_value_computed": False,
            "replacement_reason": "waiver pool, scoring-week schedule/lineup limits and roster/IR slot semantics are not joined to a certified fantasy replacement set",
        },
        "team_count": len(league.get("teams", [])),
        "league_scoring_type": league_settings.get("scoringSettings", {}).get("scoringType"),
        "league_settings_snapshot": {
            "league_name": league_settings.get("name"), "team_count": league_settings.get("size"),
            "scoring_type": league_settings.get("scoringSettings", {}).get("scoringType"),
            "scoring_item_ids_and_values": league_settings.get("scoringSettings", {}).get("scoringItems", []),
            "roster_slot_counts_raw": league_settings.get("rosterSettings", {}).get("lineupSlotCounts", {}),
            "bench_unlimited_flag": league_settings.get("rosterSettings", {}).get("isBenchUnlimited"),
            "matchup_period_count": league_settings.get("scheduleSettings", {}).get("matchupPeriodCount"),
            "matchup_period_length": league_settings.get("scheduleSettings", {}).get("matchupPeriodLength"),
            "acquisition_settings": league_settings.get("acquisitionSettings", {}),
        },
        "stale_injury_data_used_in_score": False,
        "evidence_events_used_in_score": False,
        "evidence_events": {
            "news_source_last_fetch_at": news_doc.get("last_fetch_at", ""),
            "news_source_record_count": len(news_records),
            "injury_event_count": len(injury_events),
            "join_counts_by_source_type": {
                source_type: dict(Counter(r["join_status"] for r in evidence_events if r["source_type"] == source_type))
                for source_type in ("news_summary", "espn_injury_event")
            },
            "unmatched_events": [{"event_id": r["event_id"], "player_name": r["player_name_as_reported"],
                                  "espn_player_id": r["espn_player_id"]}
                                 for r in evidence_events if not r["hashtag_id"]],
            "join_key": "exact ESPN player ID only; unmatched source rows retained",
            "current_status_policy": "always not_inferred; reported_status retained separately for ESPN injury events",
            "news_summary_policy": "preserved as unverified_machine_summary, not treated as verified claims",
            "scoring_effect": False,
        },
        "qualitative_hashtag_notes_used_in_score": False,
        "sleeper_2025_26_mentions_used_in_score": False,
        "sleeper_mentions_source": "research/sleepers_2025_26/player_mentions.csv; joined by Hashtag ID, counts and labels are historical annotations only",
        "outputs_are_deterministic": True,
        "integrity_checks": [
            "366 unique tracked Hashtag IDs; source snapshot rows checked for duplicate IDs",
            "732 unique tracked-player by historical-season rows",
            "300 unique 2026-27 Hashtag projection rows",
            "900 unique player by GP sensitivity scenario rows",
            "projected GP in [0,82], shooting percentages in [0,1], nonnegative counts, makes <= attempts within display rounding tolerance",
            "ESPN player IDs are unique across tracked Hashtag IDs; ambiguous name/team collisions are left unjoined and listed",
        ],
    }
    (OUT / "quality_report.json").write_text(json.dumps(quality, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps({"tracked": len(canonical), "nba_mapped": quality["source_counts"]["nba_mapped"],
                      "nba_unmatched": missing_nba, "espn_exact_join": quality["source_counts"]["espn_exact_roster_join"],
                      "team_conflicts": quality["source_counts"]["espn_hashtag_team_conflicts"],
                      "projected": len(scored), "actual_rows": len(actuals),
                      "evidence_events": len(evidence_events),
                      "evidence_event_joins": sum(bool(r["hashtag_id"]) for r in evidence_events),
                      "reference_p_fg": p_ref_fg, "reference_p_ft": p_ref_ft,
                      "top10_raw8cat": [{"name": x["hashtag_name"], "hashtag_rank": x["rank"],
                                         "hashtag_total": x["hashtag_total"], "our_raw8cat_zsum": x["our_raw8cat_zsum"]}
                                        for x in sorted(scored, key=lambda z: z["our_raw8cat_zsum"], reverse=True)[:10]]},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
