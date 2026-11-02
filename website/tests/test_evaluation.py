import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation import TEST_CSV
from history import register_history


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        register_history(cls.app)
        cls.client = cls.app.test_client()

    def test_models_match_the_published_run_on_identical_held_out_hours(self):
        response = self.client.get('/api/evaluation')
        self.assertEqual(response.status_code, 200)
        report = response.json
        raw = pd.read_csv(Path(__file__).resolve().parents[2] / 'data/raw/hour.csv')
        cut = len(raw) * 70 // 100 + len(raw) * 15 // 100
        test = raw.iloc[cut:]
        stamps = pd.to_datetime(test.dteday) + pd.to_timedelta(test.hr, unit='h')
        rows = pd.DataFrame([
            dict(stamp=pd.Timestamp(day) + pd.Timedelta(hours=row['hour']), **row)
            for day, hours in report['days'].items() for row in hours
        ])
        self.assertEqual(report['count'], len(test))
        self.assertEqual(rows.stamp.tolist(), stamps.tolist())
        np.testing.assert_array_equal(rows.actual, test.cnt)

        archive = pd.read_csv(TEST_CSV)
        published = json.loads(TEST_CSV.with_name('metrics.json').read_text(encoding='utf-8'))
        scores = {item['model']: item for item in published['comparison']}
        displayed = {item['key']: item for item in report['models']}
        columns = {
            'rf70': 'original_saved_70',
            'rf85': 'original_refit_85',
            'hgb85': 'selected_refit_85',
        }
        self.assertEqual(set(displayed), set(columns))
        for key, column in columns.items():
            with self.subTest(model=key):
                np.testing.assert_allclose(rows[key], archive[column], rtol=0, atol=1e-10)
                for metric in ['MAE', 'RMSE', 'R2']:
                    self.assertAlmostEqual(displayed[key][metric.lower()], scores[column][metric], places=9)

    def test_worked_example_keeps_fractions_and_uses_the_test_mean(self):
        # Mean actual = 12, baseline sum of squares = 8.
        # RF 85% makes errors +2.5 and -0.5 in these two observed hours.
        with tempfile.TemporaryDirectory() as folder:
            csv = Path(folder) / 'test.csv'
            csv.write_text(
                'timestamp,cnt,original_saved_70,original_refit_85,selected_refit_85\n'
                '2012-09-12 16:00:00,10,0,12.5,10\n'
                '2012-09-12 19:00:00,14,0,13.5,14\n', encoding='utf-8',
            )
            with patch('evaluation.TEST_CSV', csv):
                report = self.client.get('/api/evaluation').json
        models = {m['key']: m for m in report['models']}
        self.assertEqual([row['hour'] for row in report['days']['2012-09-12']], [16, 19])
        self.assertEqual((report['actual_mean'], report['baseline_squares']), (12, 8))
        self.assertEqual((models['rf85']['absolute_sum'], models['rf85']['squared_sum']), (3, 6.5))
        self.assertEqual(models['rf85']['mae'], 1.5)
        self.assertAlmostEqual(models['rf85']['rmse'], math.sqrt(3.25))
        self.assertEqual(models['rf85']['r2'], 0.1875)
        self.assertEqual(models['rf70']['r2'], -36)
        self.assertEqual(models['hgb85']['r2'], 1)

    def test_incomplete_archive_is_not_scored_or_needed_by_rf_comparison(self):
        with tempfile.TemporaryDirectory() as folder:
            csv = Path(folder) / 'test.csv'
            csv.write_text(
                'timestamp,cnt,original_refit_85\n2012-09-12 16:00:00,10,12.5\n',
                encoding='utf-8',
            )
            with patch('evaluation.TEST_CSV', csv):
                with self.assertLogs(self.app.logger, level='ERROR'):
                    self.assertEqual(self.client.get('/api/evaluation').status_code, 503)
                self.assertEqual(self.client.get('/api/history/rf-test').status_code, 200)
