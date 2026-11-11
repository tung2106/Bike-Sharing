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

    def test_slot_records_and_summary_match_filtered_heatmap(self):
        dates = pd.to_datetime(self.data.dteday)
        for start, end, kind, weekday, hour in [
            ('2011-01-01', '2012-12-31', 'all', 1, 17),
            ('2012-05-01', '2012-05-31', '1', 1, 17),
            ('2012-12-31', '2012-12-31', 'all', 0, 8),
        ]:
            with self.subTest(kind=kind, start=start):
                filters = dict(start=start, end=end, workingday=kind)
                expected = self.data.loc[
                    self.data.dteday.between(start, end)
                    & dates.dt.dayofweek.eq(weekday)
                    & self.data.hr.eq(hour)
                ].sort_values('dteday')
                if kind != 'all':
                    expected = expected.loc[expected.workingday.eq(int(kind))]
                response = self.client.get(
                    '/api/history/slot',
                    query_string={**filters, 'weekday': weekday, 'hour': hour},
                )
                self.assertEqual(response.status_code, 200)
                result = response.json
                self.assertEqual(result['filters'], filters)
                self.assertEqual(
                    [r['date'] for r in result['records']], expected.dteday.tolist()
                )
                self.assertEqual(
                    [r['rentals'] for r in result['records']], expected.cnt.tolist()
                )
                self.assertTrue(
                    all(
                        r['rentals'] == r['casual'] + r['registered']
                        for r in result['records']
                    )
                )
                summary = result['summary']
                self.assertEqual(summary['samples'], len(expected))
                self.assertEqual(summary['total'], int(expected.cnt.sum()))
                self.assertAlmostEqual(summary['mean'], expected.cnt.mean())
                self.assertAlmostEqual(summary['median'], expected.cnt.median())
                self.assertAlmostEqual(summary['q25'], expected.cnt.quantile(0.25))
                self.assertAlmostEqual(summary['q75'], expected.cnt.quantile(0.75))
                for label, value in [
                    ('minimum', expected.cnt.min()),
                    ('maximum', expected.cnt.max()),
                ]:
                    self.assertEqual(summary[label]['rentals'], value)
                    self.assertEqual(
                        summary[label]['date'],
                        expected.loc[expected.cnt.eq(value)].dteday.iloc[0],
                    )
                heatmap = self.client.get('/api/history', query_string=filters).json[
                    'heatmap'
                ]
                cell = next(
                    c for c in heatmap if c['day'] == weekday and c['hour'] == hour
                )
                self.assertAlmostEqual(summary['mean'], cell['mean'])
                self.assertEqual(summary['samples'], cell['samples'])

    def test_slot_missing_hour_does_not_become_zero(self):
        for day, rows in self.data.groupby('dteday'):
            missing = set(range(24)) - set(rows.hr)
            if missing:
                hour = min(missing)
                weekday = pd.Timestamp(day).dayofweek
                result = self.client.get(
                    '/api/history/slot',
                    query_string=dict(start=day, end=day, weekday=weekday, hour=hour),
                ).json
                self.assertEqual(result['records'], [])
                self.assertIsNone(result['summary'])
                self.assertEqual(result['missing_days'], 1)
                break
        else:
            self.fail('Expected at least one missing hour in the source dataset')

    def test_slot_empty_and_invalid_requests(self):
        response = self.client.get(
            '/api/history/slot',
            query_string=dict(
                start='2011-01-01', end='2011-01-01', workingday='1', weekday=5, hour=8
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['records'], [])
        self.assertIsNone(response.json['summary'])
        for args in [
            {},
            {'weekday': '1'},
            {'weekday': '1', 'hour': '17.5'},
            {'weekday': 'bad', 'hour': '8'},
            {'weekday': 7, 'hour': 8},
            {'weekday': 1, 'hour': 24},
            {'weekday': 1, 'hour': -1},
            {'weekday': 1, 'hour': 8, 'start': '2012-02-30'},
            {'weekday': 1, 'hour': 8, 'workingday': '3'},
        ]:
            with self.subTest(args=args):
                self.assertEqual(
                    self.client.get('/api/history/slot', query_string=args).status_code,
                    400,
                )

    def test_slot_when_history_source_is_unavailable(self):
        from unittest.mock import patch

        app = Flask(__name__)
        with patch('history.pd.read_csv', side_effect=OSError('missing source')):
            with self.assertLogs(app.logger, level='ERROR'):
                register_history(app)
        self.assertEqual(
            app.test_client().get('/api/history/slot?weekday=1&hour=17').status_code,
            503,
        )
