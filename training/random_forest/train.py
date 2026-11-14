import os

os.environ.setdefault('OMP_NUM_THREADS', '4')
from pathlib import Path
import sys, json, hashlib, platform
import joblib, numpy as np, pandas as pd, sklearn
from sklearn.base import clone
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'training'))
from model_utils import regression_metrics


def main():
    out = Path(__file__).parent
    original_path = ROOT / 'experiments/hourly_comparison/baseline/model.joblib'
    source = ROOT / 'data/raw/hour.csv'
    original = joblib.load(original_path)
    features = original['features']
    df = pd.read_csv(source)
    df['timestamp'] = pd.to_datetime(df.dteday) + pd.to_timedelta(df.hr, unit='h')
    df = df.sort_values('timestamp').reset_index(drop=True)
    assert not df.timestamp.duplicated().any()
    assert np.isfinite(df[features + ['cnt']].to_numpy()).all()
    cut = len(df) * 70 // 100 + len(df) * 15 // 100
    train, test = df.iloc[:cut], df.iloc[cut:]
    # Clone resets learned trees but preserves the original RF hyperparameters.
    model = clone(original['pipeline']).set_params(model__n_jobs=4)
    model.fit(train[features], train.cnt)
    pred = model.predict(test[features])
    metrics = regression_metrics(test.cnt, pred)
    hgb = joblib.load(
        ROOT / 'experiments/hourly_comparison/runs/20261025_024202/model.joblib'
    )
    hp = hgb['pipeline'].predict(test[features])
    hmetrics = regression_metrics(test.cnt, hp)
    for key in hmetrics:
        np.testing.assert_allclose(hmetrics[key], hgb['report']['test'][key], rtol=1e-8)
    comparison = [
        dict(model='Random Forest 85%', **metrics),
        dict(model='HistGradientBoosting 85%', **hmetrics),
    ]
    report = dict(
        test=metrics,
        baseline_test=original['report']['test'],
        comparison=comparison,
        evaluation_note='Previously viewed historical test; not independent confirmation or regional deployment validation.',
        split=dict(
            train_rows=len(train),
            test_rows=len(test),
            train_end=str(train.timestamp.iloc[-1]),
            test_start=str(test.timestamp.iloc[0]),
            test_end=str(test.timestamp.iloc[-1]),
        ),
        selection=dict(
            best_params=model.named_steps['model'].get_params(),
            policy='Original RF hyperparameters; only refit on first 85%, no new tuning.',
        ),
    )
    versions = dict(
        python=platform.python_version(),
        numpy=np.__version__,
        pandas=pd.__version__,
        joblib=joblib.__version__,
        **{'scikit-learn': sklearn.__version__}
    )
    bundle = dict(
        pipeline=model,
        features=features,
        dataset='hour',
        target='cnt',
        name='Random Forest · huấn luyện 85%',
        versions=versions,
        report=report,
    )
    joblib.dump(bundle, out / 'model.joblib', compress=3)
    np.testing.assert_allclose(
        joblib.load(out / 'model.joblib')['pipeline'].predict(test[features]), pred
    )
    for name, value in [
        ('metrics', report),
        ('environment', versions),
        (
            'provenance',
            dict(
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                original_model_sha256=hashlib.sha256(
                    original_path.read_bytes()
                ).hexdigest(),
                model_sha256=hashlib.sha256(
                    (out / 'model.joblib').read_bytes()
                ).hexdigest(),
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            ),
        ),
    ]:
        (out / (name + '.json')).write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8'
        )
    pd.DataFrame(comparison).to_csv(out / 'comparison.csv', index=False)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=4):
        main()
