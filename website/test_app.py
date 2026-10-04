"""Integration checks using the actual downloaded hour model, no retraining."""
import json
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from app import FEATURES, create_app, make_input, season_for

SOURCE_CSV = Path(__file__).resolve().parent.parent / 'du_lieu' / 'goc' / 'hour.csv'


class WebsiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.bundle = cls.app.config['MODEL_BUNDLE']
        assert cls.bundle is not None, 'Real model must load successfully'

    def payload(self):
        return {'date': '2012-05-01', 'hour': 8, 'weather': 1, 'holiday': False,
                'temperature': 24, 'feels_like': 26, 'humidity': 65, 'wind_speed': 12}

    def test_page_and_status(self):
        page = self.client.get('/')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Dự đoán lượt thuê xe', page.get_data(as_text=True))
        for asset in ['/static/style.css', '/static/app.js', '/static/favicon.svg']:
            with self.client.get(asset) as response:
                self.assertEqual(response.status_code, 200)
        status = self.client.get('/api/model')
        self.assertTrue(status.json['ready'])
        self.assertEqual(status.json['test'], self.bundle['report']['test'])
        self.assertEqual(len(status.json['model_sha256']), 64)

    def test_prediction_matches_original_pipeline(self):
        payload = self.payload()
        frame, _ = make_input(payload)
        response = self.client.post('/api/predict', json=payload)
        self.assertEqual(response.status_code, 200)
        expected = self.bundle['pipeline'].predict(frame)[0]
        self.assertAlmostEqual(response.json['prediction'], expected, places=8)

    def test_missing_values_use_trained_imputer(self):
        payload = self.payload()
        for name in ['temperature', 'feels_like', 'humidity', 'wind_speed']:
            payload[name] = None
        response = self.client.post('/api/predict', json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['imputed_features'], ['temp', 'atemp', 'hum', 'windspeed'])
        self.assertTrue(np.isfinite(response.json['prediction']))

    def test_invalid_inputs(self):
        for key, bad in [('date', '2026-10-04'), ('date', '2012-02-30'),
                         ('hour', 24), ('hour', 1.5), ('hour', None),
                         ('weather', 0), ('holiday', 'false'),
                         ('humidity', 101), ('wind_speed', -1),
                         ('temperature', float('inf')), ('temperature', True),
                         ('feels_like', 'abc')]:
            with self.subTest(key=key, value=bad):
                payload = self.payload()
                payload[key] = bad
                self.assertEqual(self.client.post('/api/predict', json=payload).status_code, 400)
        self.assertEqual(self.client.post('/api/predict', json=[]).status_code, 400)
        self.assertEqual(self.client.post('/api/predict', data='not json').status_code, 400)

    def test_calendar(self):
        payload = self.payload()
        frame, _ = make_input(payload)
        self.assertEqual(frame.iloc[0]['weekday'], 2)
        self.assertEqual(frame.iloc[0]['workingday'], 1)
        payload['holiday'] = True
        self.assertEqual(make_input(payload)[0].iloc[0]['workingday'], 0)
        for month, day, expected in [(3, 20, 1), (3, 21, 2), (6, 20, 2), (6, 21, 3),
                                      (9, 22, 3), (9, 23, 4), (12, 20, 4), (12, 21, 1)]:
            self.assertEqual(season_for(date(2012, month, day)), expected)

    @unittest.skipUnless(SOURCE_CSV.is_file(), 'Requires du_lieu/goc/hour.csv')
    def test_real_csv_round_trip_and_saved_test_metrics(self):
        source = pd.read_csv(SOURCE_CSV)
        # Verify feature interpretation across every source date, including leap day and seasons.
        days = pd.to_datetime(source['dteday'])
        np.testing.assert_array_equal(days.map(lambda d: season_for(d.date())), source['season'])
        np.testing.assert_array_equal((days.dt.weekday + 1) % 7, source['weekday'])
        samples = source.iloc[[0, 500, 12164, 12165, 14770, 17378]]
        for _, original in samples.iterrows():
            payload = {'date': original['dteday'], 'hour': int(original['hr']),
                       'holiday': bool(original['holiday']), 'weather': int(original['weathersit']),
                       'temperature': original['temp'] * 47 - 8,
                       'feels_like': original['atemp'] * 66 - 16,
                       'humidity': original['hum'] * 100, 'wind_speed': original['windspeed'] * 67}
            frame, _ = make_input(payload)
            np.testing.assert_allclose(frame.iloc[0].to_numpy(), original[FEATURES].to_numpy(dtype=float), atol=1e-14)
            response = self.client.post('/api/predict', json=payload)
            expected = self.bundle['pipeline'].predict(pd.DataFrame([original[FEATURES].to_dict()]))[0]
            self.assertAlmostEqual(response.json['prediction'], expected, places=8)
        n = len(source)
        test = source.iloc[n * 70 // 100 + n * 15 // 100:]
        predictions = self.bundle['pipeline'].predict(test[FEATURES])
        actual = {'RMSE': np.sqrt(mean_squared_error(test['cnt'], predictions)),
                  'MAE': mean_absolute_error(test['cnt'], predictions), 'R2': r2_score(test['cnt'], predictions)}
        for metric, value in actual.items():
            self.assertAlmostEqual(value, self.bundle['report']['test'][metric], places=8)
        print('Original Colab test metrics reproduced:', json.dumps(actual))


if __name__ == '__main__':
    unittest.main(verbosity=2)
