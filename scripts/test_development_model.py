#!/usr/bin/env python3
"""Chronological age-feature probe, conditional on three-year NBA survivors.

Rates use per-minute units; MPG is modeled separately. This does not estimate
rookie experience, causal development, Hashtag residuals, or final fantasy ranks.
"""
import csv
import json
from pathlib import Path

import numpy as np

from test_availability_model import fit

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/scoring'
TARGETS = {'mpg': None, 'pts_per_min': 'PTS', 'reb_per_min': 'REB',
           'ast_per_min': 'AST', 'stl_per_min': 'STL', 'blk_per_min': 'BLK',
           'three_pm_per_min': 'FG3M', 'fga_per_min': 'FGA', 'fta_per_min': 'FTA'}


def load_panel():
    panel = {}
    for path in sorted((ROOT / 'data/career/raw').glob('league_dash_*_base.json')):
        year = int(path.name.split('_')[2][:4])
        obj = json.loads(path.read_text())
        records = [dict(zip(obj['columns'], row)) for row in obj['data']]
        assert len(records) == len({r['PLAYER_ID'] for r in records})
        for row in records:
            if row['GP'] <= 0 or row['MIN'] <= 0:
                continue
            values = {key: float(row[col]) / row['MIN'] if col else row['MIN'] / row['GP']
                      for key, col in TARGETS.items()}
            values['age'] = float(row['AGE'])
            panel[int(row['PLAYER_ID']), year] = values
    return panel


def predict_nonnegative(model, rows):
    # Availability helper clips at 1; use its fitted coefficients without that
    # upper bound for MPG and category rates.
    center, scale, beta = model
    x = np.array([r['x'] for r in rows])
    z = np.column_stack([np.ones(len(x)), (x-center)/scale])
    result = np.einsum('ni,i->n', z, beta)
    assert np.isfinite(result).all()
    return np.maximum(result, 0)


def samples(panel, target, age):
    rows = []
    for (pid, year), current in panel.items():
        if 2019 in range(year - 3, year + 1):
            continue
        history = [panel.get((pid, year-lag)) for lag in (1, 2, 3)]
        if not all(history):
            continue
        x = [h[target] for h in history] + [history[0]['mpg']]
        if age:
            x += [history[0]['age'], history[0]['age'] ** 2]
        rows.append({'year': year, 'x': x, 'y': current[target], 'lag1': history[0][target]})
    return rows


def main():
    panel = load_panel()
    results = []
    tuning = []
    for target in TARGETS:
        baseline_errors = []
        for with_age in (False, True):
            rows = samples(panel, target, with_age)
            candidates = []
            for alpha in (1, 10, 100, 1000):
                errors = []
                for year in range(2015, 2019):
                    train = [r for r in rows if r['year'] < year]
                    test = [r for r in rows if r['year'] == year]
                    errors.extend(abs(p-r['y']) for p, r in zip(predict_nonnegative(fit(train, alpha), test), test))
                candidates.append((float(np.mean(errors)), alpha))
            _, alpha = min(candidates)
            tuning.append({'target': target, 'with_age': with_age, 'alpha': alpha,
                           'validation_mae': min(candidates)[0]})
            errors = []
            for year in (2023, 2024, 2025):
                train = [r for r in rows if r['year'] < year]
                test = [r for r in rows if r['year'] == year]
                errors.extend(p-r['y'] for p, r in zip(predict_nonnegative(fit(train, alpha), test), test))
                if not with_age:
                    baseline_errors.extend(r['lag1']-r['y'] for r in test)
            results.append({'target': target, 'model': 'history_plus_age' if with_age else 'history',
                            'n': len(errors), 'mae': float(np.mean(np.abs(errors))),
                            'bias': float(np.mean(errors)), 'rmse': float(np.sqrt(np.mean(np.square(errors))))})
        results.append({'target': target, 'model': 'last_season', 'n': len(baseline_errors),
                        'mae': float(np.mean(np.abs(baseline_errors))), 'bias': float(np.mean(baseline_errors)),
                        'rmse': float(np.sqrt(np.mean(np.square(baseline_errors))))})
    with (OUT/'development_backtest.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0])); writer.writeheader(); writer.writerows(results)
    (OUT/'development_experiment.json').write_text(json.dumps({
        'validation_season_starts': list(range(2015, 2019)), 'test_season_starts': [2023, 2024, 2025],
        'tuning': tuning, 'results': results,
        'limitations': ['Conditional on target participation and three preceding consecutive seasons; excludes rookies and exits.',
                        'Per-minute rates are not pace-adjusted; historical season trends and role changes are not modeled.',
                        'No injury, teammate, true experience, uncertainty or Hashtag-residual features.',
                        'Age-feature comparison is an exploratory model-family test, not a calibrated scoring adjustment.']
    }, indent=2)+'\n')
    for target in TARGETS:
        values = {r['model']: r['mae'] for r in results if r['target'] == target}
        print(target, {k: round(v, 5) for k, v in values.items()},
              'age_incremental_improvement_pct', round(100*(1-values['history_plus_age']/values['history']), 2))


if __name__ == '__main__':
    main()
