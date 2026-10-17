#!/usr/bin/env python3
"""Chronological GP model experiment; conditional on next-season NBA participation.

Read cached full-league seasons, tune on 2015-18, test on 2023-25.
Exclude windows touching 2019-20 (unequal team schedules) rather than assume 75.
This does not create calibrated injury-aware player forecasts or fantasy ranks.
"""
import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/scoring'
FEATURES = ['availability_lag1', 'availability_lag2', 'availability_lag3',
            'last_age', 'last_age_squared', 'last_mpg', 'availability_sd3']


def load_samples():
    panel = {}
    for path in sorted((ROOT / 'data/career/raw').glob('league_dash_*_base.json')):
        year = int(path.name.split('_')[2][:4])
        obj = json.loads(path.read_text())
        records = [dict(zip(obj['columns'], r)) for r in obj['data']]
        ids = [int(r['PLAYER_ID']) for r in records]
        assert len(ids) == len(set(ids)), 'Inspect duplicate source player rows before aggregating'
        for r in records:
            gp = float(r['GP'])
            denominator = {1998: 50, 2011: 66, 2020: 72}.get(year, 82)
            panel[int(r['PLAYER_ID']), year] = {
                'a': min(gp / denominator, 1), 'age': float(r['AGE']),
                'mpg': float(r['MIN']) / gp, 'name': r['PLAYER_NAME']}
    samples = []
    for (pid, year), target in panel.items():
        if 2019 in range(year - 3, year + 1):
            continue
        history = [panel.get((pid, year - lag)) for lag in (1, 2, 3)]
        if not all(history):
            continue
        a = [r['a'] for r in history]
        features = a + [history[0]['age'], history[0]['age'] ** 2,
                        history[0]['mpg'], float(np.std(a))]
        samples.append({'year': year, 'pid': pid, 'x': features,
                        'y': target['a'], 'lag1': a[0], 'mean3': float(np.mean(a))})
    return samples


def fit(train, alpha):
    x = np.array([r['x'] for r in train]); y = np.array([r['y'] for r in train])
    center = x.mean(axis=0); scale = x.std(axis=0); scale[scale == 0] = 1
    z = np.column_stack([np.ones(len(x)), (x - center) / scale])
    penalty = np.eye(z.shape[1]) * alpha; penalty[0, 0] = 0
    assert np.isfinite(z).all() and np.isfinite(y).all()
    gram = np.einsum('ni,nj->ij', z, z)
    rhs = np.einsum('ni,n->i', z, y)
    beta = np.linalg.solve(gram + penalty, rhs)
    assert np.isfinite(beta).all()
    return center, scale, beta


def predict(model, rows):
    center, scale, beta = model
    x = np.array([r['x'] for r in rows])
    z = np.column_stack([np.ones(len(x)), (x-center)/scale])
    values = np.einsum('ni,i->n', z, beta)
    assert np.isfinite(values).all()
    return np.clip(values, 0, 1)


def measure(actual, prediction):
    error = (np.array(prediction) - np.array(actual)) * 82
    return {'n': len(error), 'mae_gp_equivalent': float(np.mean(abs(error))),
            'rmse_gp_equivalent': float(np.sqrt(np.mean(error**2))),
            'bias_gp_equivalent': float(np.mean(error))}


def write_projection_comparison(model):
    path = ROOT / 'data/consolidated/baseline_scoring.csv'
    if not path.exists():
        return
    rows = list(csv.DictReader(path.open()))
    comparison = []
    center, scale, beta = model
    for row in rows:
        fields = ['gp_2025-26', 'gp_2024-25', 'gp_2023-24',
                  'latest_actual_age', 'latest_actual_mpg']
        record = {k: row[k] for k in ('hashtag_id', 'hashtag_name', 'nba_player_id', 'gp')}
        record['comparison_status'] = 'insufficient_three_season_history'
        record['experimental_conditional_gp'] = ''
        record['experimental_gp_minus_hashtag_gp'] = ''
        if all(row.get(k) for k in fields):
            a = [min(float(row[k])/82, 1) for k in fields[:3]]
            age = float(row['latest_actual_age'])
            x = np.array(a + [age, age**2, float(row['latest_actual_mpg']), float(np.std(a))])
            z = np.r_[1, (x-center)/scale]
            gp = float(np.clip(np.einsum('i,i->', z, beta), 0, 1)*82)
            record['comparison_status'] = 'experimental_conditional_on_nba_participation'
            record['experimental_conditional_gp'] = gp
            record['experimental_gp_minus_hashtag_gp'] = gp - float(row['gp'])
        record['used_in_fantasy_score'] = False
        record['limitations'] = 'No current injury/role/exit features or calibrated uncertainty; independent diagnostic, not a Hashtag correction.'
        comparison.append(record)
    with (OUT/'availability_projection_comparison.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(comparison[0]))
        writer.writeheader(); writer.writerows(comparison)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_samples()
    tuning = []
    for alpha in (1, 10, 100, 1000):
        errors = []
        for year in range(2015, 2019):
            train = [r for r in rows if r['year'] < year]
            test = [r for r in rows if r['year'] == year]
            errors.extend(abs(p-r['y']) for p, r in zip(predict(fit(train, alpha), test), test))
        tuning.append({'alpha': alpha, 'validation_mae_gp_equivalent': float(np.mean(errors)*82)})
    alpha = min(tuning, key=lambda r: r['validation_mae_gp_equivalent'])['alpha']
    result = []; pooled = {k: [] for k in ('lag1', 'mean3', 'ridge')}; actual = []
    for year in (2023, 2024, 2025):
        train = [r for r in rows if r['year'] < year]
        test = [r for r in rows if r['year'] == year]
        y = [r['y'] for r in test]; pred = predict(fit(train, alpha), test)
        for name, values in [('lag1', [r['lag1'] for r in test]),
                             ('mean3', [r['mean3'] for r in test]), ('ridge', pred)]:
            result.append({'season': f'{year}-{(year+1)%100:02}', 'model': name, **measure(y, values)})
            pooled[name].extend(values)
        actual.extend(y)
    for name, values in pooled.items():
        result.append({'season': 'pooled_heldout', 'model': name, **measure(actual, values)})
    with (OUT/'availability_backtest.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(result[0])); writer.writeheader(); writer.writerows(result)
    model = fit(rows, alpha)
    center, scale, beta = model
    write_projection_comparison(model)
    report = {'selected_ridge_alpha': alpha, 'tuning': tuning, 'sample_count': len(rows),
              'features': FEATURES, 'fit_on_all_observed_data_intercept': float(beta[0]),
              'standardized_feature_coefficients': dict(zip(FEATURES, beta[1:].tolist())),
              'feature_mean': center.tolist(), 'feature_sd': scale.tolist(),
              'pooled_holdout': {name: measure(actual, values) for name, values in pooled.items()},
              'limitations': ['Conditional on appearing in the target season and three preceding consecutive seasons.',
                              'No injury, rest, NBA-exit, rookie or current-roster features.',
                              'All windows touching 2019-20 excluded; shortened uniform schedules normalized.',
                              'GP capped at schedule denominator for traded players; not exact individual opportunity.',
                              'No calibrated uncertainty intervals; not a final injury-aware forecast.',
                              'Feature coefficients are predictive associations, not causal weights.']}
    (OUT/'availability_model_experiment.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report['pooled_holdout'], indent=2))


if __name__ == '__main__':
    main()
