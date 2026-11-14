"""Kiểm tra một lần chạy đã lưu, hai API dự đoán và kết quả hiển thị trên web."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'website'))
from app import FEATURES, create_app
from daily_context import PREVIOUS_DAY, previous_day_rentals


def request_for(row):
    return dict(
        date=row.dteday.strftime('%Y-%m-%d'),
        hour=int(row.hr),
        holiday=bool(row.holiday),
        weather=int(row.weathersit),
        temperature=row.temp * 47 - 8,
        feels_like=row.atemp * 66 - 16,
        humidity=row.hum * 100,
        wind_speed=row.windspeed * 67,
    )


def check_calendar_gaps():
    totals = pd.Series([100, 999], index=pd.to_datetime(['2012-02-28', '2012-03-01']))
    dates = ['2012-02-29 17:00', '2012-03-01 07:00', '2012-03-02 00:00']
    np.testing.assert_allclose(previous_day_rentals(dates, totals), [100, np.nan, 999])


def top_hours(rows, field):
    ranked = sorted(rows, key=lambda row: (-row[field], row['hour']))
    return {row['hour'] for row in ranked[:3]}


def verify(directory):
    check_calendar_gaps()
    raw = pd.read_csv(ROOT / 'data/raw/hour.csv', parse_dates=['dteday'])
    raw.index = raw.dteday + pd.to_timedelta(raw.hr, unit='h')
    raw.sort_index(inplace=True)
    daily = (
        pd.read_csv(ROOT / 'data/raw/day.csv', parse_dates=['dteday'])
        .set_index('dteday')
        .cnt
    )
    # Independent lookup: shift the keys forward one calendar day, not the rows.
    past = daily.copy()
    past.index += pd.DateOffset(days=1)
    raw[PREVIOUS_DAY] = raw.dteday.map(past)
    saved = pd.read_csv(
        directory / 'test_predictions.csv', parse_dates=['timestamp']
    ).set_index('timestamp')
    metrics = json.loads((directory / 'metrics.json').read_text(encoding='utf-8'))
    # Git may convert line endings on checkout. Verify the same text in either convention.
    csv_text = (directory / 'test_predictions.csv').read_text(encoding='utf-8')
    assert metrics['source_sha256']['test_predictions'] in {
        hashlib.sha256(csv_text.replace('\n', ending).encode('utf-8')).hexdigest()
        for ending in ('\n', '\r\n')
    }
    cut = len(raw) * 70 // 100 + len(raw) * 15 // 100
    test = raw.iloc[cut:]
    assert saved.index.equals(test.index)
    np.testing.assert_array_equal(saved.cnt, test.cnt)
    np.testing.assert_array_equal(saved[PREVIOUS_DAY], test[PREVIOUS_DAY])
    control_path = ROOT / 'website/models/model.joblib'
    candidate_path = directory / 'model.joblib'
    for path, column, key in [
        (control_path, 'original_refit_85', 'rf85'),
        (candidate_path, 'rf85_previous_day', 'rf85_previous_day'),
    ]:
        candidate = path == candidate_path
        app = create_app(model_path=path)
        client = app.test_client()
        bundle = app.config['MODEL_BUNDLE']
        expected_features = [*FEATURES, PREVIOUS_DAY] if candidate else FEATURES
        assert bundle['features'] == expected_features
        info = client.get('/api/model').json
        assert info['ready'] and info['uses_previous_day'] == candidate
        assert info['model_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
        predicted = bundle['pipeline'].predict(test[expected_features])
        np.testing.assert_allclose(predicted, saved[column], rtol=0, atol=1e-9)
        calculated = dict(
            MAE=mean_absolute_error(test.cnt, predicted),
            RMSE=root_mean_squared_error(test.cnt, predicted),
            R2=r2_score(test.cnt, predicted),
        )
        evaluation = client.get('/api/evaluation').json
        assert evaluation['count'] == len(test) and evaluation['default_model'] == key
        assert len(evaluation['models']) == (4 if candidate else 3)
        online_scores = next(m for m in evaluation['models'] if m['key'] == key)
        for name, value in calculated.items():
            np.testing.assert_allclose(
                [info['test'][name], online_scores[name.lower()]], value, rtol=1e-10
            )
        history = client.get('/api/history/rf-test').json['days']
        online_predictions = [
            r['prediction'] for day in sorted(history) for r in history[day]
        ]
        np.testing.assert_allclose(online_predictions, predicted, rtol=0, atol=1e-9)
        matches = []
        for hours in history.values():
            if {r['hour'] for r in hours} == set(range(24)):
                matches.append(
                    len(top_hours(hours, 'actual') & top_hours(hours, 'prediction'))
                )
        published = next(m for m in metrics['test_comparison'] if m['model'] == key)
        assert (len(matches), sum(matches), matches.count(3)) == (
            published['complete_days'],
            published['matched_hours'],
            published['perfect_days'],
        )
        if candidate:
            imputer = (
                bundle['pipeline']
                .named_steps['preprocessor']
                .named_transformers_['numeric']
            )
            np.testing.assert_equal(
                imputer.statistics_[-1], raw.iloc[:cut][PREVIOUS_DAY].median()
            )
        # First day has no yesterday, leap day has a real one, and the last test day has both peaks.
        for timestamp in [
            '2011-01-01 08:00',
            '2012-02-29 17:00',
            '2012-09-12 16:00',
            '2012-12-31 08:00',
        ]:
            row = raw.loc[timestamp]
            response = client.post('/api/predict', json=request_for(row))
            assert response.status_code == 200, response.json
            result = response.json
            frames = pd.concat(
                [raw.loc[[timestamp], expected_features]] * 24, ignore_index=True
            )
            frames['hr'] = range(24)
            expected = bundle['pipeline'].predict(frames)
            assert [point['hour'] for point in result['hourly']] == list(range(24))
            np.testing.assert_allclose(
                [point['prediction'] for point in result['hourly']],
                expected,
                rtol=0,
                atol=1e-9,
            )
            np.testing.assert_allclose(
                result['prediction'], expected[int(row.hr)], rtol=0, atol=1e-9
            )
            if candidate:
                wanted = row[PREVIOUS_DAY]
                assert result['features'][PREVIOUS_DAY] == (
                    None if pd.isna(wanted) else wanted
                )
                assert (PREVIOUS_DAY in result['imputed_features']) == pd.isna(wanted)
        print(
            f'PASS {key}: {len(test)} saved test hours, scores, history, 24-hour API and date boundaries'
        )


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    verify(parser.parse_args().run.resolve())
