"""Read-only historical aggregates; no model predictions or training."""

from datetime import date
from pathlib import Path
import pandas as pd
from flask import jsonify, request
from evaluation import (
    PREVIOUS_DAY_MODEL,
    RF85_MODEL,
    evaluation_report,
    hours_by_day,
    read_test_hours,
)


def register_history(
    app, previous_day_archive=None, *, active_model=None, archive=None
):
    rf_model = RF85_MODEL if previous_day_archive is None else PREVIOUS_DAY_MODEL
    active_model = active_model or rf_model
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

    def select_history():
        start, end = request.args.get('start', lower), request.args.get('end', upper)
        kind = request.args.get('workingday', 'all')
        try:
            if (
                date.fromisoformat(start).isoformat() != start
                or date.fromisoformat(end).isoformat() != end
                or not lower <= start <= end <= upper
                or kind not in ('all', '0', '1')
            ):
                raise ValueError()
        except ValueError:
            raise ValueError(
                f'Chọn khoảng ngày hợp lệ từ {lower} đến {upper} và loại ngày hợp lệ.'
            ) from None
        selected = data.loc[data.dteday.between(start, end)]
        if kind != 'all':
            selected = selected.loc[selected.workingday.eq(int(kind))]
        return selected, dict(start=start, end=end, workingday=kind)

    @app.get('/api/history')
    def history():
        if data is None:
            return jsonify(error='Không đọc được dữ liệu lịch sử hour.csv.'), 503
        try:
            selected, filters = select_history()
        except ValueError as error:
            return jsonify(error=str(error)), 400
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
            filters=filters,
            rows=len(selected),
            days=int(selected.dteday.nunique()),
            total=int(selected.cnt.sum()),
            casual=int(selected.casual.sum()),
            registered=int(selected.registered.sum()),
            average=float(selected.cnt.mean()) if len(selected) else None,
            peak=peak,
            hourly=hourly,
        )

    @app.get('/api/history/slot')
    def history_slot():
        if data is None:
            return jsonify(error='Không đọc được dữ liệu lịch sử hour.csv.'), 503
        try:
            selected, filters = select_history()
            weekday = int(request.args.get('weekday', ''))
            hour = int(request.args.get('hour', ''))
            if not 0 <= weekday <= 6 or not 0 <= hour <= 23:
                raise ValueError('Chọn thứ từ 0 đến 6 và giờ từ 0 đến 23.')
        except ValueError as error:
            return jsonify(error='Bộ lọc chi tiết không hợp lệ. ' + str(error)), 400

        # The weekday uses Monday=0, as in the heatmap.
        days = selected.loc[selected.weekday.eq(weekday)]
        observations = days.loc[days.hr.eq(hour)].sort_values('dteday')
        records = [
            dict(
                date=row.dteday,
                rentals=int(row.cnt),
                casual=int(row.casual),
                registered=int(row.registered),
            )
            for row in observations.itertuples()
        ]
        summary = None
        if records:
            counts = observations.cnt
            summary = dict(
                samples=len(records),
                total=int(counts.sum()),
                mean=float(counts.mean()),
                median=float(counts.median()),
                q25=float(counts.quantile(0.25)),
                q75=float(counts.quantile(0.75)),
                minimum=min(records, key=lambda row: row['rentals']),
                maximum=max(records, key=lambda row: row['rentals']),
            )
        return jsonify(
            filters=filters,
            weekday=weekday,
            hour=hour,
            records=records,
            summary=summary,
            missing_days=int(days.dteday.nunique()) - len(records),
        )

    def test_comparison(model, model_archive):
        try:
            rows = read_test_hours({model[1]: 'prediction'}, model_archive)
            return jsonify(days=hours_by_day(rows))
        except (OSError, ValueError):
            app.logger.exception('Saved test predictions unavailable for %s', model[0])
            return (
                jsonify(error='Không đọc được kết quả đối chiếu của mô hình.'),
                503,
            )

    @app.get('/api/history/rf-test')
    def rf_test():
        return test_comparison(rf_model, previous_day_archive)

    @app.get('/api/history/model-test')
    def model_test():
        model_archive = (
            previous_day_archive if active_model == PREVIOUS_DAY_MODEL else archive
        )
        return test_comparison(active_model, model_archive)

    @app.get('/api/evaluation')
    def evaluation():
        try:
            return jsonify(
                evaluation_report(
                    previous_day_archive, archive=archive, default_model=active_model[0]
                )
            )
        except (OSError, ValueError):
            app.logger.exception('Saved evaluation data unavailable')
            return (
                jsonify(error='Chưa đọc được các dự đoán đã lưu của thí nghiệm.'),
                503,
            )
