"""Thu nghiem hour v2: chronological validation, unchanged web inputs.

Run with website/.venv/Scripts/python.exe experiments/hourly_v2/train_experiment.py
The original model remains unchanged. Outputs are placed in runs/<UTC timestamp>/.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS', '4')
import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'colab'))
from colab_train import feature_columns, make_preprocessor, regression_metrics, save_json

FEATURES, CATEGORIES = feature_columns('hour')
NUMERIC = ['temp', 'atemp', 'hum', 'windspeed']
SEED = 42


def candidates(original):
    # Fresh copies: never evaluate an already-trained model on its training rows.
    rf = clone(original['pipeline'])
    rf.set_params(model__n_jobs=4)
    regular = clone(rf).set_params(model__n_estimators=200, model__max_depth=18,
                                  model__min_samples_leaf=3, model__max_features=0.9)
    extra = Pipeline([('preprocessor', make_preprocessor('hour')),
                      ('model', ExtraTreesRegressor(n_estimators=200, min_samples_leaf=2,
                                                   random_state=SEED, n_jobs=4))])
    # Preserve ordered hour/month values for threshold splits; no target-derived features.
    processor = ColumnTransformer([
        ('numeric', SimpleImputer(strategy='median'), NUMERIC),
        ('codes', SimpleImputer(strategy='most_frequent'), [c for c in FEATURES if c not in NUMERIC]),
    ])
    boosting = Pipeline([('preprocessor', processor), ('model', HistGradientBoostingRegressor(
        loss='poisson', learning_rate=0.06, max_iter=400, max_leaf_nodes=31,
        min_samples_leaf=20, l2_regularization=5, early_stopping=False,
        categorical_features=None, random_state=SEED))])
    return {'rf_original': rf, 'rf_regularized': regular,
            'extra_trees': extra, 'hist_boost_poisson': boosting}


def predict_checked(pipeline, frame):
    values = pipeline.predict(frame[FEATURES])
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('Invalid predictions')
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    out = args.output or Path(__file__).parent / 'runs' / datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    out.mkdir(parents=True, exist_ok=False)
    csv_path = ROOT / 'du_lieu/goc/hour.csv'
    model_path = ROOT / 'experiments/hourly_v2/baseline/model.joblib'
    frame = pd.read_csv(csv_path)
    frame['timestamp'] = pd.to_datetime(frame['dteday']) + pd.to_timedelta(frame['hr'], unit='h')
    frame = frame.sort_values('timestamp').reset_index(drop=True)
    assert not frame['timestamp'].duplicated().any()
    assert frame[FEATURES + ['cnt']].notna().all().all()
    assert np.isfinite(frame[FEATURES + ['cnt']].to_numpy()).all()
    assert ((frame['cnt'] >= 0) & (frame['cnt'] % 1 == 0)).all()
    original = joblib.load(model_path)
    assert original['features'] == FEATURES and original['dataset'] == 'hour'
    n = len(frame)
    cut70 = n * 70 // 100
    cut85 = cut70 + n * 15 // 100
    folds = [(n * 50 // 100, n * 60 // 100),
             (n * 60 // 100, cut70), (cut70, cut85)]
    models = candidates(original)
    plan = {
        'seed': SEED, 'features': FEATURES, 'selection_metric': 'pooled validation MAE',
        'refit_policy': 'Winner chosen before test; export after refit on first 85%.',
        'test_caveat': 'Previously viewed historical test; exploratory, not independent final evidence.',
        'input_caveat': 'Observed historical weather; not a backtest using archived weather forecasts.',
        'source_sha256': hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        'original_model_sha256': hashlib.sha256(model_path.read_bytes()).hexdigest(),
        'missing_hour_count': len(pd.date_range(frame.timestamp.min(), frame.timestamp.max(), freq='h').difference(frame.timestamp)),
        'candidates': {name: model.named_steps['model'].get_params() for name, model in models.items()},
        'folds': [{'train_rows': a, 'validation_rows': b-a,
                   'train_end': str(frame.timestamp.iloc[a-1]),
                   'validation_start': str(frame.timestamp.iloc[a]),
                   'validation_end': str(frame.timestamp.iloc[b-1])} for a, b in folds],
        'test': {'rows': n-cut85, 'start': str(frame.timestamp.iloc[cut85]), 'end': str(frame.timestamp.iloc[-1])},
    }
    # Persist the full experiment plan before any scores are computed.
    save_json(out / 'plan.json', plan)
    rows, summary = [], []
    for name, template in models.items():
        all_actual, all_predicted = [], []
        for fold, (a, b) in enumerate(folds, 1):
            fitted = clone(template).fit(frame.iloc[:a][FEATURES], frame.iloc[:a]['cnt'])
            valid = frame.iloc[a:b]
            prediction = predict_checked(fitted, valid)
            metrics = regression_metrics(valid['cnt'], prediction)
            rows.append({'candidate': name, 'fold': fold, 'rows': len(valid), **metrics})
            all_actual.extend(valid['cnt'].tolist())
            all_predicted.extend(prediction.tolist())
            print(f'{name} fold {fold}: MAE={metrics["MAE"]:.3f}, RMSE={metrics["RMSE"]:.3f}', flush=True)
            pd.DataFrame(rows).to_csv(out / 'validation_folds.csv', index=False)
        summary.append({'candidate': name, **regression_metrics(all_actual, all_predicted)})
    ranking = pd.DataFrame(summary).sort_values(['MAE', 'RMSE', 'candidate'])
    ranking.to_csv(out / 'validation_summary.csv', index=False)
    winner = ranking.iloc[0]['candidate']
    selection = {'candidate': winner, 'algorithm': type(models[winner].named_steps['model']).__name__,
                 'best_params': models[winner].named_steps['model'].get_params(),
                 'selection_metric': 'pooled validation MAE across 3 chronological folds',
                 'fit_partition': 'first 85%; selected before test evaluation',
                 'validation': ranking.iloc[0].to_dict()}
    save_json(out / 'selection.json', selection)
    print('SELECTED BEFORE TEST:', winner, flush=True)
    # Test is used only after the candidate and refit policy are fixed.
    chosen70 = clone(models[winner]).fit(frame.iloc[:cut70][FEATURES], frame.iloc[:cut70]['cnt'])
    chosen85 = clone(models[winner]).fit(frame.iloc[:cut85][FEATURES], frame.iloc[:cut85]['cnt'])
    baseline85 = clone(models['rf_original']).fit(frame.iloc[:cut85][FEATURES], frame.iloc[:cut85]['cnt'])
    test = frame.iloc[cut85:]
    evaluation = {'original_saved_70': original['pipeline'], 'selected_70': chosen70,
                  'original_refit_85': baseline85, 'selected_refit_85': chosen85}
    test_rows, group_rows = [], []
    predictions = test[['instant', 'timestamp', 'hr', 'workingday', 'cnt']].copy()
    for name, model in evaluation.items():
        predicted = predict_checked(model, test)
        predictions[name] = predicted
        metrics = regression_metrics(test['cnt'], predicted)
        test_rows.append({'model': name, **metrics})
        for group, mask in {
            'peak_hours': test.hr.isin([7, 8, 9, 16, 17, 18, 19]),
            'workingday': test.workingday.eq(1), 'non_workingday': test.workingday.eq(0),
        }.items():
            group_rows.append({'model': name, 'group': group, 'rows': int(mask.sum()),
                               **regression_metrics(test.loc[mask, 'cnt'], predicted[mask.to_numpy()])})
    by_name = {row['model']: row for row in test_rows}
    for metric in ('MAE', 'RMSE', 'R2'):
        np.testing.assert_allclose(by_name['original_saved_70'][metric], original['report']['test'][metric], rtol=1e-8)
    pd.DataFrame(test_rows).to_csv(out / 'test_comparison.csv', index=False)
    pd.DataFrame(group_rows).to_csv(out / 'test_groups.csv', index=False)
    predictions.to_csv(out / 'test_predictions.csv', index=False)
    versions = {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__,
                'scikit-learn': sklearn.__version__, 'joblib': joblib.__version__}
    metrics = {k: by_name['selected_refit_85'][k] for k in ('MAE', 'RMSE', 'R2')}
    report = {'test': metrics, 'baseline_test': {k: by_name['original_saved_70'][k] for k in metrics},
              'baseline': 'Original deployed Random Forest trained on 70%',
              'selection': selection, 'evaluated_at_utc': datetime.now(timezone.utc).isoformat(),
              'evaluation_note': plan['test_caveat'], 'comparison': test_rows}
    bundle = {'pipeline': chosen85, 'features': FEATURES, 'target': 'cnt', 'dataset': 'hour',
              'name': selection['algorithm'] + ' · thử nghiệm v2', 'versions': versions, 'report': report}
    joblib.dump(bundle, out / 'model.joblib', compress=3)
    loaded = joblib.load(out / 'model.joblib')
    np.testing.assert_allclose(predict_checked(loaded['pipeline'], test), predictions['selected_refit_85'])
    save_json(out / 'metrics.json', report)
    save_json(out / 'environment.json', versions)
    (out / 'requirements.txt').write_text('\n'.join(f'{k}=={v}' for k,v in versions.items() if k != 'python')+'\n', encoding='utf-8')
    save_json(out / 'provenance.json', {'source_sha256': plan['source_sha256'],
              'model_sha256': hashlib.sha256((out / 'model.joblib').read_bytes()).hexdigest(),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'selection': selection})
    print(pd.DataFrame(test_rows).to_string(index=False), flush=True)
    print('OUTPUT:', out, flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=4):
        main()
