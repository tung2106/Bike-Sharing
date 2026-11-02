"""Read-only historical aggregates; no model predictions or training."""

from datetime import date
from pathlib import Path
import pandas as pd
from flask import jsonify, request


def register_history(app):
    source = Path(__file__).resolve().parents[1] / 'data/raw/hour.csv'
    try:
        data = pd.read_csv(
            source,
            usecols=['dteday', 'hr', 'workingday', 'cnt', 'casual', 'registered'],
        )
        data['dteday'] = pd.to_datetime(data['dteday']).dt.strftime('%Y-%m-%d')
        if (
            data.empty
            or data.isna().any().any()
            or data.duplicated(['dteday', 'hr']).any()
        ):
            raise ValueError('Invalid historical data')
        data['weekday'] = pd.to_datetime(data['dteday']).dt.dayofweek
        lower, upper = data.dteday.min(), data.dteday.max()
    except Exception:
        app.logger.exception('Historical CSV unavailable')
        data = None

    @app.get('/api/history')
    def history():
        if data is None:
            return jsonify(error='Không đọc được dữ liệu lịch sử hour.csv.'), 503
        start, end = request.args.get('start', lower), request.args.get('end', upper)
        kind = request.args.get('workingday', 'all')
        try:
            if (
                date.fromisoformat(start).isoformat() != start
                or date.fromisoformat(end).isoformat() != end
            ):
                raise ValueError()
            if not lower <= start <= end <= upper or kind not in ('all', '0', '1'):
                raise ValueError()
        except ValueError:
            return (
                jsonify(
                    error=f'Chọn khoảng ngày hợp lệ từ {lower} đến {upper} và loại ngày hợp lệ.'
                ),
                400,
            )
        selected = data.loc[data.dteday.between(start, end)]
        if kind != 'all':
            selected = selected.loc[selected.workingday.eq(int(kind))]
        # A missing hour is unknown, never a zero-rental observation.
        grouped = selected.groupby('hr')['cnt'].agg(['mean', 'count'])
        hourly = [
            dict(
                hour=h,
                mean=float(grouped.loc[h, 'mean']) if h in grouped.index else None,
                samples=int(grouped.loc[h, 'count']) if h in grouped.index else 0,
            )
            for h in range(24)
        ]
        peak = min(
            (row for row in hourly if row['samples']),
            key=lambda row: (-row['mean'], row['hour']),
            default=None,
        )
        weekly = selected.groupby(['weekday', 'hr']).cnt.agg(['mean', 'count'])
        heatmap = [
            dict(day=int(day), hour=int(hour), mean=float(mean), samples=int(count))
            for (day, hour), (mean, count) in weekly.iterrows()
        ]
        return jsonify(
            heatmap=heatmap,
            bounds=dict(start=lower, end=upper),
            filters=dict(start=start, end=end, workingday=kind),
            rows=len(selected),
            days=int(selected.dteday.nunique()),
            total=int(selected.cnt.sum()),
            casual=int(selected.casual.sum()),
            registered=int(selected.registered.sum()),
            average=float(selected.cnt.mean()) if len(selected) else None,
            peak=peak,
            hourly=hourly,
        )

    @app.get('/api/history/rf-test')
    def rf_test():
        predictions = (
            source.parents[2]
            / 'experiments/hourly_comparison/runs/20261025_024202/test_predictions.csv'
        )
        try:
            rows = pd.read_csv(
                predictions, usecols=['timestamp', 'cnt', 'original_refit_85']
            )
            times = pd.to_datetime(rows['timestamp'])
            if rows.empty or rows.isna().any().any() or times.duplicated().any():
                raise ValueError('Invalid test predictions')
            days = {}
            for stamp, actual, prediction in zip(
                times, rows['cnt'], rows['original_refit_85']
            ):
                key = stamp.date().isoformat()
                days.setdefault(key, []).append(
                    dict(
                        hour=stamp.hour,
                        actual=int(actual),
                        prediction=float(prediction),
                    )
                )
            return jsonify(days=days)
        except (OSError, ValueError):
            app.logger.exception('RF test predictions unavailable')
            return (
                jsonify(error='Không đọc được kết quả kiểm tra của Random Forest.'),
                503,
            )
