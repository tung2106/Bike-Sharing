"""Đối chiếu RF85 với cùng mô hình có thêm tổng lượt của ngày D−1."""

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'website'))
sys.path.insert(0, str(ROOT / 'training'))
from model_utils import regression_metrics
from daily_context import DAY_CSV, PREVIOUS_DAY, daily_totals, previous_day_rentals
from evaluation import TEST_CSV

HOUR_CSV = ROOT / 'data/raw/hour.csv'
BASE_MODEL = ROOT / 'website/models/model.joblib'
RUNS = Path(__file__).resolve().parent / 'runs'
CANDIDATE = 'rf85_previous_day'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frame():
    totals = daily_totals()
    frame = pd.read_csv(HOUR_CSV, parse_dates=['dteday'])
    pd.testing.assert_series_equal(frame.groupby('dteday').cnt.sum(), totals)
    if (
        frame.hr.isna().any()
        or not frame.hr.between(0, 23).all()
        or frame.hr.mod(1).ne(0).any()
    ):
        raise ValueError('Giờ không hợp lệ trong hour.csv')
    frame['timestamp'] = frame.dteday + pd.to_timedelta(frame.hr, unit='h')
    frame[PREVIOUS_DAY] = previous_day_rentals(frame.dteday, totals)
    return frame.set_index('timestamp', verify_integrity=True).sort_index()


def fit_model(bundle, train, with_day):
    pipeline = clone(bundle['pipeline'])
    features = list(bundle['features'])
    if with_day:
        features.append(PREVIOUS_DAY)
        pre = pipeline.named_steps['preprocessor']
        pre.set_params(
            transformers=[
                (name, step, [*columns, PREVIOUS_DAY] if name == 'numeric' else columns)
                for name, step, columns in pre.transformers
            ]
        )
    pipeline.fit(train[features], train.cnt)
    return pipeline


def measure(rows, predictions):
    scores = regression_metrics(rows.cnt, predictions)
    correct = []
    for _, day in rows.assign(prediction=predictions).groupby('dteday'):
        if len(day) != 24:
            continue
        # Bản ghi đã xếp theo thời gian. Nếu bằng lượt, ưu tiên giờ sớm hơn như trên web.
        predicted_hours = day.nlargest(3, 'prediction', keep='first').hr
        observed_hours = day.nlargest(3, 'cnt', keep='first').hr
        correct.append(len(set(predicted_hours) & set(observed_hours)))
    return dict(
        **scores,
        complete_days=len(correct),
        matched_hours=sum(correct),
        perfect_days=correct.count(3),
    )


def evaluate_folds(frame, cutoff, bundle):
    # Tiến dần theo mốc 50/60/70/85 của dự án, tách vào đầu ngày cho từng đợt.
    bounds = [
        frame.index[i].normalize()
        for i in (
            len(frame) // 2,
            len(frame) * 60 // 100,
            len(frame) * 70 // 100,
            cutoff,
        )
    ]
    results = []
    for fold, (start, end) in enumerate(zip(bounds, bounds[1:]), 1):
        train = frame.loc[frame.index < start]
        valid = frame.loc[(frame.index >= start) & (frame.index < end)]
        for key, with_day in [('rf85', False), (CANDIDATE, True)]:
            pipeline = fit_model(bundle, train, with_day)
            pred = pipeline.predict(valid[pipeline.feature_names_in_])
            results.append(
                dict(
                    fold=fold,
                    model=key,
                    train_rows=len(train),
                    train_end=str(train.index[-1]),
                    validation_rows=len(valid),
                    start=str(valid.index[0]),
                    end=str(valid.index[-1]),
                    **measure(valid, pred),
                )
            )
        print(
            f'Validation {fold}: {start.date()} -> {end.date()} (exclusive)', flush=True
        )
    return pd.DataFrame(results)


def run():
    frame = load_frame()
    baseline = joblib.load(BASE_MODEL)
    cut = len(frame) * 70 // 100 + len(frame) * 15 // 100
    train, test = frame.iloc[:cut], frame.iloc[cut:]
    split = baseline['report']['split']
    assert (len(train), len(test)) == (split['train_rows'], split['test_rows'])
    assert train.index[-1] == pd.Timestamp(split['train_end'])
    assert test.index[0] == pd.Timestamp(split['test_start'])
    assert test.index[-1] == pd.Timestamp(split['test_end'])
    assert baseline['versions']['scikit-learn'] == sklearn.__version__
    folds = evaluate_folds(frame, cut, baseline)
    candidate = fit_model(baseline, train, True)
    base_pred = baseline['pipeline'].predict(test[baseline['features']])
    new_pred = candidate.predict(test[candidate.feature_names_in_])
    reference = measure(test, base_pred)
    revised = measure(test, new_pred)
    for key, value in baseline['report']['test'].items():
        np.testing.assert_allclose(reference[key], value, rtol=1e-9)

    # Preserve the three published series and align the fourth by exact timestamp.
    archive = pd.read_csv(TEST_CSV, parse_dates=['timestamp']).set_index(
        'timestamp', verify_integrity=True
    )
    pd.testing.assert_index_equal(archive.index, test.index)
    np.testing.assert_array_equal(archive.cnt, test.cnt)
    np.testing.assert_allclose(archive.original_refit_85, base_pred, rtol=0, atol=1e-9)
    archive[PREVIOUS_DAY] = test[PREVIOUS_DAY]
    archive[CANDIDATE] = new_pred
    comparison = pd.DataFrame(
        [dict(model='rf85', **reference), dict(model=CANDIDATE, **revised)]
    )
    utc = datetime.now(timezone.utc)
    report = dict(
        test={k: revised[k] for k in ('MAE', 'RMSE', 'R2')},
        baseline_test=baseline['report']['test'],
        split=split,
        test_comparison=comparison.to_dict(orient='records'),
        validation=folds.to_dict(orient='records'),
        selection=dict(
            best_params=candidate.named_steps['model'].get_params(),
            policy='Same RF parameters in every fit. Only previous_day_rentals is added.',
        ),
        feature=PREVIOUS_DAY,
        missing_train_rows=int(train[PREVIOUS_DAY].isna().sum()),
        missing_test_rows=int(test[PREVIOUS_DAY].isna().sum()),
        training_lag_median=float(train[PREVIOUS_DAY].median()),
        evaluation_note='Previously viewed historical test; observed hourly weather. Daily totals are available only after the preceding day closes.',
        evaluated_at_utc=utc.isoformat(timespec='seconds'),
        source_sha256={
            'hour.csv': sha256(HOUR_CSV),
            'day.csv': sha256(DAY_CSV),
            'baseline_model': sha256(BASE_MODEL),
        },
    )
    versions = dict(
        python=platform.python_version(),
        numpy=np.__version__,
        pandas=pd.__version__,
        joblib=joblib.__version__,
        **{'scikit-learn': sklearn.__version__},
    )
    bundle = dict(
        name='Random Forest 85% + lượt ngày trước',
        dataset='hour',
        target='cnt',
        pipeline=candidate,
        features=list(candidate.feature_names_in_),
        versions=versions,
        report=report,
    )
    RUNS.mkdir(exist_ok=True)
    destination = RUNS / utc.strftime('%Y%m%dT%H%M%S%fZ')
    with TemporaryDirectory(dir=RUNS) as temporary:
        out = Path(temporary) / 'ready'
        out.mkdir()
        frame.to_csv(out / 'hour_with_previous_day.csv')
        folds.to_csv(out / 'validation_folds.csv', index=False)
        comparison.to_csv(out / 'comparison.csv', index=False)
        archive.to_csv(out / 'test_predictions.csv')
        report['source_sha256']['test_predictions'] = sha256(
            out / 'test_predictions.csv'
        )
        (out / 'metrics.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        joblib.dump(bundle, out / 'model.joblib', compress=3)
        reloaded = joblib.load(out / 'model.joblib')
        np.testing.assert_allclose(
            reloaded['pipeline'].predict(test[reloaded['features']]),
            new_pred,
            rtol=0,
            atol=1e-9,
        )
        out.rename(destination)
    print(comparison.to_string(index=False), flush=True)
    print('RUN=' + str(destination), flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=4):
        run()
