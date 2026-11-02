"""Đánh giá hồi quy trên các dự đoán theo giờ đã lưu của cùng thí nghiệm."""

from pathlib import Path

import numpy as np
import pandas as pd


TEST_CSV = (
    Path(__file__).resolve().parents[1]
    / 'experiments/hourly_comparison/runs/20261025_024202/test_predictions.csv'
)
# Mỗi phiên bản dùng đúng cột dự đoán của nó trong lần chạy trên.
MODELS = (
    ('rf70', 'original_saved_70', 'Random Forest 70%', 'RF 70%'),
    ('rf85', 'original_refit_85', 'Random Forest 85%', 'RF 85%'),
    ('hgb85', 'selected_refit_85', 'HistGradientBoosting 85%', 'HGB 85%'),
)


def read_test_hours(prediction_columns):
    """Ghép dự đoán gốc với lượt thuê thực tế của cùng giờ."""
    rows = pd.read_csv(
        TEST_CSV,
        usecols=['timestamp', 'cnt', *prediction_columns],
        dtype={'cnt': 'int64', **{column: float for column in prediction_columns}},
    )
    times = pd.DatetimeIndex(pd.to_datetime(rows.pop('timestamp')))
    if (
        rows.empty
        or times.hasnans
        or not times.is_unique
        or not times.equals(times.floor('h'))
        or not np.isfinite(rows.to_numpy()).all()
        or rows['cnt'].lt(0).any()
    ):
        raise ValueError('Invalid hourly test observations')
    rows.index = times
    return rows.rename(columns={'cnt': 'actual', **prediction_columns}).sort_index()


def hours_by_day(rows):
    with_hour = rows.assign(hour=rows.index.hour)
    return {
        day: group.to_dict(orient='records')
        for day, group in with_hour.groupby(rows.index.strftime('%Y-%m-%d'))
    }


def evaluation_report():
    rows = read_test_hours({column: key for key, column, _, _ in MODELS})
    actual = rows['actual']
    count = len(rows)
    actual_mean = float(actual.mean())
    baseline_squares = float(((actual - actual_mean) ** 2).sum())

    models = []
    for key, _, label, short_label in MODELS:
        error = rows[key] - actual
        absolute_sum = float(error.abs().sum())
        squared_sum = float((error ** 2).sum())
        models.append({
            'key': key, 'label': label, 'short_label': short_label,
            'absolute_sum': absolute_sum, 'squared_sum': squared_sum,
            'mae': absolute_sum / count,
            'rmse': (squared_sum / count) ** 0.5,
            'r2': 1 - squared_sum / baseline_squares if baseline_squares > 0 else None,
        })

    return {
        'count': count,
        'first': rows.index[0].isoformat(timespec='minutes'),
        'last': rows.index[-1].isoformat(timespec='minutes'),
        'actual_mean': actual_mean,
        'baseline_squares': baseline_squares,
        'models': models,
        'days': hours_by_day(rows),
    }
