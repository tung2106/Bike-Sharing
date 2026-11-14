"""Train the saved RF configuration on 70%, evaluate validation/test separately.

The historical train.py refits on 85%; this script deliberately does not.
Outputs are versioned in runs/, without changing the deployed website model.
"""

import hashlib
import json
import os
import platform
import sys
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
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'training'))
from model_utils import regression_metrics, save_json


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    config_path = HERE / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    if [config[k] for k in ('train_percent', 'validation_percent', 'test_percent')] != [
        70,
        15,
        15,
    ]:
        raise ValueError('This experiment requires chronological 70/15/15 splits')
    source = ROOT / 'data/raw/hour.csv'
    deployed = ROOT / 'website/models/model.joblib'
    deployed_hash = digest(deployed)
    template = joblib.load(deployed)
    features = template['features']
    frame = pd.read_csv(source)
    frame['timestamp'] = pd.to_datetime(frame.dteday) + pd.to_timedelta(
        frame.hr, unit='h'
    )
    frame = frame.sort_values('timestamp', kind='stable').reset_index(drop=True)
    assert not frame.timestamp.duplicated().any()
    assert np.isfinite(frame[features + ['cnt']].to_numpy()).all()
    assert set(features).isdisjoint({'cnt', 'casual', 'registered', 'instant'})
    first = len(frame) * 70 // 100
    second = first + len(frame) * 15 // 100
    parts = {
        'train': frame.iloc[:first],
        'validation': frame.iloc[first:second],
        'test': frame.iloc[second:],
    }
    assert parts['train'].timestamp.max() < parts['validation'].timestamp.min()
    assert parts['validation'].timestamp.max() < parts['test'].timestamp.min()
    estimator_params = {k: v for k, v in config.items() if not k.endswith('_percent')}
    model = clone(template['pipeline']).set_params(
        **{'model__' + key: value for key, value in estimator_params.items()}
    )
    # All learned preprocessing state and trees are reset by clone.
    model.fit(parts['train'][features], parts['train'].cnt)
    metrics = {}
    predictions = {}
    for name, part in parts.items():
        predictions[name] = model.predict(part[features])
        metrics[name] = regression_metrics(part.cnt, predictions[name])

    # An unlimited forest is freshly fitted on the SAME 70%, for a fair control.
    control = clone(model).set_params(model__max_depth=None)
    control.fit(parts['train'][features], parts['train'].cnt)
    control_metrics = {
        name: regression_metrics(part.cnt, control.predict(part[features]))
        for name, part in parts.items()
    }
    now = datetime.now(timezone.utc)
    out = HERE / 'runs' / now.strftime('%Y%m%d_%H%M%S_depth20_70_15_15')
    out.mkdir(parents=True, exist_ok=False)
    split = {
        name: {
            'rows': len(part),
            'start': str(part.timestamp.iloc[0]),
            'end': str(part.timestamp.iloc[-1]),
        }
        for name, part in parts.items()
    }
    report = {
        **metrics,
        'baseline_test': control_metrics['test'],
        'control_unlimited_same_train': control_metrics,
        'split': split,
        'evaluated_at_utc': now.isoformat(),
        'selection': {
            'best_params': model.named_steps['model'].get_params(),
            'policy': 'User chose depth 20 after validation comparison; fit only on first 70%. No test-based selection or refit on validation.',
        },
        'evaluation_note': 'Historical test previously viewed in this project; not a new independent holdout. Unlimited control uses the identical 70% training split.',
    }
    versions = {
        'python': platform.python_version(),
        'numpy': np.__version__,
        'pandas': pd.__version__,
        'joblib': joblib.__version__,
        'scikit-learn': sklearn.__version__,
    }
    bundle = {
        'pipeline': model,
        'features': features,
        'dataset': 'hour',
        'target': 'cnt',
        'name': 'Random Forest depth 20 - train 70%',
        'versions': versions,
        'report': report,
    }
    joblib.dump(bundle, out / 'model.joblib', compress=3)
    restored = joblib.load(out / 'model.joblib')
    for name, part in parts.items():
        np.testing.assert_allclose(
            restored['pipeline'].predict(part[features]), predictions[name]
        )
        part[['instant', 'timestamp', 'cnt']].assign(
            prediction=predictions[name]
        ).to_csv(out / f'{name}_predictions.csv', index=False)
    pd.concat(
        [
            part[['instant', 'timestamp']].assign(split=name)
            for name, part in parts.items()
        ]
    ).to_csv(out / 'split_manifest.csv', index=False)
    comparison = [
        {'model': label, 'split': name, **values}
        for label, scores in [('depth20', metrics), ('unlimited', control_metrics)]
        for name, values in scores.items()
    ]
    pd.DataFrame(comparison).to_csv(out / 'comparison.csv', index=False)
    save_json(out / 'metrics.json', report)
    save_json(out / 'environment.json', versions)
    save_json(out / 'config.json', config)
    save_json(
        out / 'provenance.json',
        {
            'source_sha256': digest(source),
            'template_model_sha256': deployed_hash,
            'model_sha256': digest(out / 'model.joblib'),
            'script_sha256': digest(Path(__file__)),
            'config_sha256': digest(config_path),
            'deployed_model_updated': False,
        },
    )
    assert digest(deployed) == deployed_hash
    print('OUTPUT:', out.relative_to(ROOT), flush=True)
    print(pd.DataFrame(comparison).to_string(index=False), flush=True)
    print('SPLIT:', json.dumps(split), flush=True)
    print('Saved model reload verified; website model unchanged.', flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=4):
        main()
