"""Compare tree depth and leaf size on chronological validation, without test tuning.

Run from the project root:
    website/.venv/Scripts/python.exe -B experiments/random_forest_tuning/tune_depth.py

Every candidate, including the deployed parameter baseline, is freshly trained
on the first 70%. The following 15% selects parameters; the final 15% is unused.
No deployed or historical model is overwritten.
"""

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault('OMP_NUM_THREADS', '4')

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'training'))
from model_utils import regression_metrics, save_json

DEPTHS = [4, 8, 10, 12, 16, 20, 24, 32, None]
LEAF_SIZES = [1, 2, 3, 5, 10]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')

    source = ROOT / 'data/raw/hour.csv'
    deployed = ROOT / 'website/models/model.joblib'
    deployed_hash = sha256(deployed)
    bundle = joblib.load(deployed)
    features = bundle['features']
    frame = pd.read_csv(source)
    frame['timestamp'] = pd.to_datetime(frame.dteday) + pd.to_timedelta(
        frame.hr, unit='h'
    )
    frame = frame.sort_values('timestamp', kind='stable').reset_index(drop=True)
    assert not frame.timestamp.duplicated().any()
    assert set(features).isdisjoint({'cnt', 'casual', 'registered', 'instant'})
    train_end = len(frame) * 70 // 100
    validation_end = train_end + len(frame) * 15 // 100
    train = frame.iloc[:train_end]
    validation = frame.iloc[train_end:validation_end]
    assert train.timestamp.max() < validation.timestamp.min()
    assert validation.timestamp.max() < frame.timestamp.iloc[validation_end]

    # Cloning removes all fitted state, including preprocessing learned on 85%.
    processor = clone(bundle['pipeline'].named_steps['preprocessor'])
    x_train = processor.fit_transform(train[features])
    x_validation = processor.transform(validation[features])
    assert np.isfinite(x_train).all() and np.isfinite(x_validation).all()
    template = clone(bundle['pipeline'].named_steps['model'])
    template.set_params(n_jobs=args.jobs)

    out = (
        Path(__file__).resolve().parent
        / 'runs'
        / datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    )
    out.mkdir(parents=True, exist_ok=False)
    plan = {
        'selection_metric': 'validation_RMSE (lower is better)',
        'tie_break': 'smaller depth, then larger min_samples_leaf',
        'depths': DEPTHS,
        'min_samples_leaf': LEAF_SIZES,
        'fixed_estimator_parameters': template.get_params(),
        'features': features,
        'source_sha256': sha256(source),
        'deployed_model_sha256': deployed_hash,
        'script_sha256': sha256(Path(__file__)),
        'test_evaluated': False,
        'split': {
            'train_rows': len(train),
            'validation_rows': len(validation),
            'reserved_test_rows': len(frame) - validation_end,
            'train_start': str(train.timestamp.iloc[0]),
            'train_end': str(train.timestamp.iloc[-1]),
            'validation_start': str(validation.timestamp.iloc[0]),
            'validation_end': str(validation.timestamp.iloc[-1]),
        },
        'versions': {
            'python': platform.python_version(),
            'scikit-learn': sklearn.__version__,
            'numpy': np.__version__,
            'pandas': pd.__version__,
        },
        'limitations': [
            'One chronological validation period and one random seed.',
            'Historical test was previously viewed in earlier project experiments.',
            'Validation winner is a candidate, not independent test confirmation.',
        ],
    }
    save_json(out / 'plan.json', plan)
    print('OUTPUT:', out.relative_to(ROOT), flush=True)
    results = []
    best_key, best_predictions = None, None
    for depth in DEPTHS:
        for leaf in LEAF_SIZES:
            started = time.perf_counter()
            model = clone(template).set_params(max_depth=depth, min_samples_leaf=leaf)
            model.fit(x_train, train.cnt)
            train_metrics = regression_metrics(train.cnt, model.predict(x_train))
            predictions = model.predict(x_validation)
            val_metrics = regression_metrics(validation.cnt, predictions)
            depths = [tree.get_depth() for tree in model.estimators_]
            row = {
                'max_depth': 'None' if depth is None else str(depth),
                'min_samples_leaf': leaf,
                **{f'train_{k}': v for k, v in train_metrics.items()},
                **{f'validation_{k}': v for k, v in val_metrics.items()},
                'RMSE_gap': val_metrics['RMSE'] - train_metrics['RMSE'],
                'R2_gap': train_metrics['R2'] - val_metrics['R2'],
                'mean_tree_depth': float(np.mean(depths)),
                'max_tree_depth': max(depths),
                'mean_leaf_count': float(
                    np.mean([tree.get_n_leaves() for tree in model.estimators_])
                ),
                'elapsed_seconds': time.perf_counter() - started,
            }
            results.append(row)
            key = (val_metrics['RMSE'], depth if depth is not None else np.inf, -leaf)
            if best_key is None or key < best_key:
                best_key = key
                best_predictions = predictions.copy()
            pd.DataFrame(results).to_csv(out / 'all_results.csv', index=False)
            print(
                f"[{len(results):02d}/45] depth={str(depth):>4}, leaf={leaf:>2}: "
                f"train RMSE={train_metrics['RMSE']:.3f}, "
                f"validation RMSE={val_metrics['RMSE']:.3f}, "
                f"MAE={val_metrics['MAE']:.3f}, R2={val_metrics['R2']:.4f}",
                flush=True,
            )

    ranked = sorted(
        results,
        key=lambda r: (
            r['validation_RMSE'],
            float('inf') if r['max_depth'] == 'None' else int(r['max_depth']),
            -r['min_samples_leaf'],
        ),
    )
    best = ranked[0]
    by_depth = [
        min(
            (r for r in results if r['max_depth'] == str(depth)),
            key=lambda r: (r['validation_RMSE'], -r['min_samples_leaf']),
        )
        for depth in DEPTHS
    ]
    baseline = next(
        r for r in results if r['max_depth'] == 'None' and r['min_samples_leaf'] == 1
    )
    pd.DataFrame(by_depth).to_csv(out / 'best_by_depth.csv', index=False)
    pd.DataFrame(ranked).to_csv(out / 'ranking.csv', index=False)
    validation[['timestamp', 'cnt']].assign(prediction=best_predictions).to_csv(
        out / 'best_validation_predictions.csv', index=False
    )
    improvement = (
        100
        * (baseline['validation_RMSE'] - best['validation_RMSE'])
        / baseline['validation_RMSE']
    )
    save_json(
        out / 'selection.json',
        {
            'best': best,
            'baseline_same_train_split': baseline,
            'validation_RMSE_improvement_percent': improvement,
            'test_evaluated': False,
            'deployed_model_updated': False,
        },
    )
    assert sha256(deployed) == deployed_hash, 'Deployed model changed during run'
    print('BEST:', json.dumps(best), flush=True)
    print(f'Validation RMSE improvement over baseline: {improvement:.3f}%', flush=True)
    print('Test unused; website model unchanged.', flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=4):
        main()
