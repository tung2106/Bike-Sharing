"""Đánh giá hồi quy trên các dự đoán theo giờ đã lưu của cùng thí nghiệm."""

from pathlib import Path

import numpy as np
import pandas as pd

TEST_CSV = (
    Path(__file__).resolve().parents[1]
    / 'experiments/hourly_comparison/runs/20261025_024202/test_predictions.csv'
)
# Mỗi phiên bản dùng đúng cột dự đoán của nó trong lần chạy trên.
RF85_MODEL = ('rf85', 'original_refit_85', 'Random Forest 85%', 'RF 85%')
HGB_MODEL = ('hgb85', 'selected_refit_85', 'HistGradientBoosting 85%', 'HGB 85%')
MODELS = (
    ('rf70', 'original_saved_70', 'Random Forest 70%', 'RF 70%'),
    RF85_MODEL,
    HGB_MODEL,
)
PREVIOUS_DAY_MODEL = (
    'rf85_previous_day',
    'rf85_previous_day',
    'RF 85% + lượt ngày trước',
    'RF 85% + ngày',
)


def read_test_hours(prediction_columns, archive=None):
    """Ghép dự đoán gốc với lượt thuê thực tế của cùng giờ."""
    rows = pd.read_csv(
        TEST_CSV if archive is None else archive,
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


def evaluation_report(previous_day_archive=None, *, archive=None, default_model=None):
    compared = MODELS
    rows = read_test_hours(
        {column: key for key, column, _, _ in MODELS}, archive or previous_day_archive
    )
    if previous_day_archive is not None:
        key, column, _, _ = PREVIOUS_DAY_MODEL
        previous = read_test_hours({column: key}, previous_day_archive)
        if not rows.actual.equals(previous.actual):
            raise ValueError('Model archives must cover the same test observations')
        rows[key] = previous[key]
        compared = (*MODELS, PREVIOUS_DAY_MODEL)
    if default_model is None:
        default_model = (
            RF85_MODEL[0] if previous_day_archive is None else PREVIOUS_DAY_MODEL[0]
        )
    actual = rows['actual']
    count = len(rows)
    actual_mean = float(actual.mean())
    baseline_squares = float(((actual - actual_mean) ** 2).sum())

    models = []
    for key, _, label, short_label in compared:
        error = rows[key] - actual
        absolute_sum = float(error.abs().sum())
        squared_sum = float((error**2).sum())
        models.append(
            {
                'key': key,
                'label': label,
                'short_label': short_label,
                'absolute_sum': absolute_sum,
                'squared_sum': squared_sum,
                'mae': absolute_sum / count,
                'rmse': (squared_sum / count) ** 0.5,
                'r2': (
                    1 - squared_sum / baseline_squares if baseline_squares > 0 else None
                ),
            }
        )

    return {
        'default_model': default_model,
        'count': count,
        'first': rows.index[0].isoformat(timespec='minutes'),
        'last': rows.index[-1].isoformat(timespec='minutes'),
        'actual_mean': actual_mean,
        'baseline_squares': baseline_squares,
        'models': models,
        'days': hours_by_day(rows),
    }
