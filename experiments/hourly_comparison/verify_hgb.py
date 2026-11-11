"""Reproduce the saved HGB run without changing the model or tuning on test."""

import argparse
import hashlib
import json
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.exceptions import InconsistentVersionWarning
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from threadpoolctl import threadpool_limits


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scores(actual, predicted):
    assert np.isfinite(predicted).all() and (predicted >= 0).all()
    return dict(
        MAE=mean_absolute_error(actual, predicted),
        RMSE=root_mean_squared_error(actual, predicted),
        R2=r2_score(actual, predicted),
    )


def check_scores(actual, expected):
    np.testing.assert_allclose(
        list(actual.values()), [expected[key] for key in actual], rtol=1e-9
    )


def verify(repo):
    run = repo / 'experiments/hourly_comparison/runs/20261025_024202'
    source = repo / 'data/raw/hour.csv'
    model_path = run / 'model.joblib'
    provenance = read_json(run / 'provenance.json')
    assert sha256(source) == provenance['source_sha256']
    assert sha256(model_path) == provenance['model_sha256']
    with warnings.catch_warnings():
        warnings.simplefilter('error', InconsistentVersionWarning)
        bundle = joblib.load(model_path)
    pipeline = bundle['pipeline']
    model = pipeline.named_steps['model']
    features = bundle['features']
    assert isinstance(model, HistGradientBoostingRegressor)
    assert bundle['versions']['scikit-learn'] == sklearn.__version__
    assert bundle['dataset'] == 'hour' and bundle['target'] == 'cnt'
    assert set(features) == {
        'temp',
        'atemp',
        'hum',
        'windspeed',
        'yr',
        'holiday',
        'workingday',
        'season',
        'mnth',
        'weekday',
        'weathersit',
        'hr',
    }
    assert list(pipeline.feature_names_in_) == features
    selection = read_json(run / 'selection.json')
    assert selection == provenance['selection'] == bundle['report']['selection']
    assert model.get_params() == selection['best_params']

    raw = pd.read_csv(source, parse_dates=['dteday'])
    raw['timestamp'] = raw.dteday + pd.to_timedelta(raw.hr, unit='h')
    raw = raw.sort_values('timestamp').reset_index(drop=True)
    assert raw.timestamp.is_unique and len(raw) == 17379
    cut70 = len(raw) * 70 // 100
    cut85 = cut70 + len(raw) * 15 // 100
    test = raw.iloc[cut85:]
    assert (cut85, len(test)) == (14771, 2608)

    folds = pd.read_csv(run / 'validation_folds.csv').set_index(['candidate', 'fold'])
    ranking = pd.read_csv(run / 'validation_summary.csv')
    winner = selection['candidate']
    assert ranking.loc[ranking.MAE.idxmin(), 'candidate'] == winner
    boundaries = [len(raw) // 2, len(raw) * 60 // 100, cut70, cut85]
    validation_pred = []
    for fold, (start, end) in enumerate(zip(boundaries, boundaries[1:]), 1):
        train, valid = raw.iloc[:start], raw.iloc[start:end]
        assert train.timestamp.max() < valid.timestamp.min() < test.timestamp.min()
        fitted = clone(pipeline).fit(train[features], train.cnt)
        predicted = fitted.predict(valid[features])
        measured = scores(valid.cnt, predicted)
        check_scores(measured, folds.loc[(winner, fold)])
        validation_pred.append(predicted)
        print(
            f'Validation {fold}: train={start}, validation={len(valid)}, MAE={measured["MAE"]:.4f}'
        )
    measured = scores(
        raw.iloc[boundaries[0] : cut85].cnt, np.concatenate(validation_pred)
    )
    check_scores(measured, selection['validation'])
    print(f'Pooled validation MAE: {measured["MAE"]:.4f}')

    archive = pd.read_csv(run / 'test_predictions.csv', parse_dates=['timestamp'])
    np.testing.assert_array_equal(archive.timestamp, test.timestamp)
    np.testing.assert_array_equal(archive.cnt, test.cnt)
    predicted = pipeline.predict(test[features])
    np.testing.assert_allclose(predicted, archive.selected_refit_85, rtol=0, atol=1e-8)
    train = raw.iloc[:cut85]
    refit = clone(pipeline).fit(train[features], train.cnt)
    np.testing.assert_allclose(
        refit.predict(test[features]), predicted, rtol=0, atol=1e-8
    )
    measured = scores(test.cnt, predicted)
    check_scores(measured, bundle['report']['test'])
    check_scores(measured, read_json(run / 'metrics.json')['test'])
    by_day = archive.groupby(archive.timestamp.dt.normalize())
    for column in ('original_refit_85', 'selected_refit_85'):
        matched = []
        for _, day in by_day:
            if len(day) != 24:
                continue
            actual = set(day.nlargest(3, 'cnt').hr)
            forecast = set(day.nlargest(3, column).hr)
            matched.append(len(actual & forecast))
        print(
            f'{column}: top 3 exact on {matched.count(3)}/{len(matched)} days, {sum(matched)} matched hours'
        )
    print(f'Test: {len(test)} hours, {measured}')
    print(
        'PASS: model and data hashes, chronological validation, refit, and saved test predictions'
    )
    verify_web(repo, model_path, test, pipeline, features, predicted, measured)


def verify_web(repo, model_path, test, pipeline, features, predicted, measured):
    sys.path.insert(0, str(repo / 'website'))
    from app import create_app

    with create_app(model_path=model_path).test_client() as client:
        status = client.get('/api/model').get_json()
        assert status['ready'] and status['model_key'] == 'hgb85'
        assert status['model_sha256'] == sha256(model_path)
        check_scores(measured, status['test'])
        evaluation = client.get('/api/evaluation').get_json()
        assert evaluation['default_model'] == 'hgb85' and evaluation['count'] == len(
            test
        )
        check_scores(
            {key.lower(): value for key, value in measured.items()},
            next(model for model in evaluation['models'] if model['key'] == 'hgb85'),
        )
        days = client.get('/api/history/model-test').get_json()['days']
        displayed = [row for day in sorted(days) for row in days[day]]
        np.testing.assert_array_equal([row['actual'] for row in displayed], test.cnt)
        np.testing.assert_allclose(
            [row['prediction'] for row in displayed], predicted, atol=1e-8, rtol=0
        )

        for index in (0, -1):
            row = test.iloc[index]
            response = client.post(
                '/api/predict',
                json=dict(
                    date=row.dteday.date().isoformat(),
                    hour=int(row.hr),
                    holiday=bool(row.holiday),
                    weather=int(row.weathersit),
                    temperature=row.temp * 47 - 8,
                    feels_like=row.atemp * 66 - 16,
                    humidity=row.hum * 100,
                    wind_speed=row.windspeed * 67,
                ),
            )
            assert response.status_code == 200, response.get_json()
            body = response.get_json()
            hourly = pd.concat([test.iloc[[index]][features]] * 24, ignore_index=True)
            hourly['hr'] = range(24)
            expected = pipeline.predict(hourly)
            assert [point['hour'] for point in body['hourly']] == list(range(24))
            np.testing.assert_allclose(
                [point['prediction'] for point in body['hourly']],
                expected,
                atol=1e-8,
                rtol=0,
            )
            np.testing.assert_allclose(
                body['prediction'], expected[int(row.hr)], atol=1e-8, rtol=0
            )
    print(
        'PASS: HGB served by API, all test hours aligned, and 24-hour forecasts match pipeline'
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--repo', type=Path, default=Path(__file__).resolve().parents[2]
    )
    with threadpool_limits(limits=4):
        verify(parser.parse_args().repo.resolve())
