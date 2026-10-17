#!/usr/bin/env python3
"""Reproducible, descriptive NBA GP availability diagnostics from local LeagueDash caches.

Reads data/career/raw/league_dash_*_base.json without modifying it. Outputs only
to research/durability/. Results are historical diagnostics, not player forecasts.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "career" / "raw"
OUT = Path(__file__).resolve().parent


def load() -> dict[tuple[int, int], dict[str, float | str]]:
    rows: dict[tuple[int, int], dict[str, float | str]] = {}
    for path in sorted(RAW.glob("league_dash_*_base.json")):
        m = re.fullmatch(r"league_dash_(\d{4})-(\d{2})_base\.json", path.name)
        if not m:
            continue
        start, end2 = int(m.group(1)), int(m.group(2))
        season = start if end2 == (start + 1) % 100 else None
        if season is None:
            continue
        doc = json.loads(path.read_text())
        ix = {name: i for i, name in enumerate(doc["columns"])}
        needed = {"PLAYER_ID", "PLAYER_NAME", "GP", "AGE"}
        if not needed.issubset(ix):
            print(f"Skipping {path.name}: missing columns {needed - set(ix)}")
            continue
        # LeagueDash may return one row per team stint; GP adds across stints.
        grouped: dict[int, dict] = {}
        for record in doc["data"]:
            pid = int(record[ix["PLAYER_ID"]])
            item = grouped.setdefault(pid, {"name": str(record[ix["PLAYER_NAME"]]), "gp": 0, "ages": []})
            item["gp"] += int(record[ix["GP"]] or 0)
            if record[ix["AGE"]] is not None:
                item["ages"].append(float(record[ix["AGE"]]))
        for pid, item in grouped.items():
            rows[(pid, season)] = {
                "name": item["name"], "gp": float(item["gp"]),
                "age": mean(item["ages"]) if item["ages"] else float("nan"),
            }
    return rows


def metrics(actual: list[float], pred: list[float]) -> dict[str, float]:
    errors = [p - a for a, p in zip(actual, pred)]
    return {
        "n": len(errors),
        # Standardize availability error to an 82-game season for comparison.
        "mae_gp_equiv": 82 * mean(abs(e) for e in errors),
        "rmse_gp_equiv": 82 * (mean(e * e for e in errors)) ** 0.5,
        "bias_gp_equiv": 82 * mean(errors),
    }


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def main() -> None:
    rows = load()
    seasons = sorted({s for _, s in rows})
    by_player: dict[int, dict[int, dict]] = defaultdict(dict)
    for (pid, season), value in rows.items():
        by_player[pid][season] = value

    # NBA team schedule maxima for shortened seasons; other years used 82.
    # In 2019-20, 75 is the highest team schedule after the season stoppage.
    schedule = {season: {1998: 50, 2011: 66, 2019: 75, 2020: 72}.get(season, 82)
                for season in seasons}
    league_rate = {
        season: mean(min(v["gp"], schedule[season]) / schedule[season]
                     for (pid, s), v in rows.items() if s == season)
        for season in seasons
    }

    # Use team games available rather than observed player GP (some records
    # exceed 82; others miss at least one game).
    with (OUT / "season_coverage.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["season_start", "player_seasons", "team_schedule_max"])
        w.writeheader()
        for season in seasons:
            w.writerow({"season_start": season,
                        "player_seasons": sum(1 for _, s in rows if s == season),
                        "team_schedule_max": schedule[season]})

    # One-season-ahead, player-season forecasts. Require contiguous seasons to
    # avoid treating absence/retirement as zero availability.
    actual = {"league_mean": [], "lag1": [], "prior3_mean": []}
    predicted = {k: [] for k in actual}
    examples = []
    for pid, hist in by_player.items():
        for target in seasons:
            prior = target - 1
            if prior not in hist or target not in hist or target not in schedule or prior not in schedule:
                continue
            outcome = min(hist[target]["gp"], schedule[target]) / schedule[target]
            lag1 = min(hist[prior]["gp"], schedule[prior]) / schedule[prior]
            baseline = league_rate[prior]
            historical = [min(hist[p]["gp"], schedule[p]) / schedule[p]
                          for p in range(prior - 2, prior + 1) if p in hist and p in schedule]
            # Use a single paired sample so the candidate errors are comparable.
            if len(historical) != 3:
                continue
            for key, pred in (("league_mean", baseline), ("lag1", lag1)):
                actual[key].append(outcome)
                predicted[key].append(pred)
            actual["prior3_mean"].append(outcome)
            predicted["prior3_mean"].append(mean(historical))
            age = hist[target]["age"]
            examples.append({"target_season": target, "gp_fraction": outcome,
                             "prior_gp_fraction": lag1, "age": age})

    model_rows = []
    for name in actual:
        if actual[name]:
            row = {"forecast": name, **metrics(actual[name], predicted[name])}
            model_rows.append(row)
    with (OUT / "backtest_summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["forecast", "n", "mae_gp_equiv", "rmse_gp_equiv", "bias_gp_equiv"])
        w.writeheader()
        for row in model_rows:
            w.writerow(row)

    # Age and lagged availability slices are reported as conditional means,
    # not fitted coefficients; exclude newly entering players (no lag).
    groups: dict[str, list[float]] = defaultdict(list)
    for x in examples:
        age = x["age"]
        if age == age:
            lo = int(age // 5) * 5
            groups[f"age_{lo}_{lo + 4}"].append(x["gp_fraction"])
        lag = x["prior_gp_fraction"]
        bucket = "0_19" if lag < .20 else "20_39" if lag < .40 else "40_59" if lag < .60 else "60_79" if lag < .80 else "80_100"
        groups[f"prior_gp_fraction_{bucket}"].append(x["gp_fraction"])
    with (OUT / "conditional_summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["slice", "n", "mean_next_gp_fraction", "p10", "p50", "p90"])
        w.writeheader()
        for key, vals in sorted(groups.items()):
            w.writerow({"slice": key, "n": len(vals), "mean_next_gp_fraction": mean(vals),
                        "p10": quantile(vals, .10), "p50": quantile(vals, .50),
                        "p90": quantile(vals, .90)})

    print(f"cached seasons: {len(seasons)} ({seasons[0] if seasons else 'n/a'}–{seasons[-1] if seasons else 'n/a'}); player-seasons: {len(rows)}")
    print(f"schedule denominators: {schedule}")
    for row in model_rows:
        print(row)


if __name__ == "__main__":
    main()
