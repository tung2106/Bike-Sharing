"""Một đặc trưng dùng chung khi huấn luyện và khi dự đoán trên web."""

from pathlib import Path

import numpy as np
import pandas as pd

PREVIOUS_DAY = 'previous_day_rentals'
DAY_CSV = Path(__file__).resolve().parents[1] / 'data/raw/day.csv'


def daily_totals(path=DAY_CSV):
    rows = pd.read_csv(path, usecols=['dteday', 'cnt'])
    dates = pd.DatetimeIndex(pd.to_datetime(rows['dteday'], format='%Y-%m-%d'))
    counts = rows['cnt']
    if (
        rows.empty
        or dates.hasnans
        or not dates.is_unique
        or not np.isfinite(counts).all()
        or counts.lt(0).any()
        or counts.mod(1).ne(0).any()
    ):
        raise ValueError('day.csv phải có một tổng lượt hợp lệ cho mỗi ngày.')
    return pd.Series(counts.to_numpy(), index=dates, name='cnt').sort_index()


def previous_day_rentals(dates, totals):
    # Tra đúng ngày D−1. Nếu ngày đó thiếu, pipeline dùng trung vị của tập train.
    yesterday = pd.DatetimeIndex(dates).normalize() - pd.Timedelta(days=1)
    return totals.reindex(yesterday).to_numpy(dtype=float)
