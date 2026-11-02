import unittest
import sys
from pathlib import Path
import pandas as pd
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from history import register_history


class HistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = Flask(__name__)
        register_history(app)
        cls.client = app.test_client()
        cls.data = pd.read_csv(
            Path(__file__).resolve().parents[2] / 'data/raw/hour.csv'
        )

    def test_full_dataset_totals(self):
        response = self.client.get('/api/history')
        self.assertEqual(response.status_code, 200)
        result = response.json
        self.assertEqual(result['rows'], len(self.data))
        self.assertEqual(result['total'], int(self.data.cnt.sum()))
        self.assertEqual(result['casual'] + result['registered'], result['total'])
        self.assertAlmostEqual(result['average'], self.data.cnt.mean())

    def test_filtered_means_and_missing_hours(self):
        for start, end, kind in [
            ('2012-05-01', '2012-05-31', '1'),
            ('2011-01-01', '2011-01-01', '0'),
        ]:
            selected = self.data.loc[
                self.data.dteday.between(start, end)
                & self.data.workingday.eq(int(kind))
            ]
            result = self.client.get(
                '/api/history', query_string=dict(start=start, end=end, workingday=kind)
            ).json
            self.assertEqual(result['rows'], len(selected))
            for row in result['hourly']:
                actual = selected.loc[selected.hr.eq(row['hour']), 'cnt']
                self.assertEqual(row['samples'], len(actual))
                if len(actual):
                    self.assertAlmostEqual(row['mean'], actual.mean())
                else:
                    self.assertIsNone(row['mean'])

    def test_empty_filter(self):
        response = self.client.get(
            '/api/history?start=2011-01-01&end=2011-01-01&workingday=1'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['rows'], 0)
        self.assertIsNone(response.json['average'])
        self.assertIsNone(response.json['peak'])

    def test_invalid_filters(self):
        for query in [
            'start=bad',
            'start=2012-02-30',
            'start=2010-01-01',
            'start=2012-05-02&end=2012-05-01',
            'workingday=3',
        ]:
            self.assertEqual(self.client.get('/api/history?' + query).status_code, 400)

    def test_rf_comparison_matches_saved_predictions(self):
        source = (
            Path(__file__).resolve().parents[2]
            / 'experiments/hourly_comparison/runs/20261025_024202/test_predictions.csv'
        )
        expected = pd.read_csv(source)
        response = self.client.get('/api/history/rf-test')
        self.assertEqual(response.status_code, 200)
        days = response.json['days']
        self.assertEqual(sum(len(rows) for rows in days.values()), len(expected))
        for row in expected.itertuples():
            stamp = pd.Timestamp(row.timestamp)
            actual = next(
                item
                for item in days[stamp.date().isoformat()]
                if item['hour'] == stamp.hour
            )
            self.assertEqual(actual['actual'], row.cnt)
            self.assertAlmostEqual(actual['prediction'], row.original_refit_85)
