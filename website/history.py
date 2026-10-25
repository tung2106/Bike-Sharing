"""Read-only historical aggregates; no model predictions or training."""
from datetime import date
from pathlib import Path
import pandas as pd
from flask import jsonify, request


def register_history(app):
    source = Path(__file__).resolve().parents[1] / 'du_lieu/goc/hour.csv'
    try:
        data = pd.read_csv(source, usecols=['dteday', 'hr', 'workingday', 'cnt', 'casual', 'registered'])
        data['dteday'] = pd.to_datetime(data['dteday']).dt.strftime('%Y-%m-%d')
        if data.empty or data.isna().any().any() or data.duplicated(['dteday', 'hr']).any():
            raise ValueError('Invalid historical data')
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
            if date.fromisoformat(start).isoformat() != start or date.fromisoformat(end).isoformat() != end:
                raise ValueError()
            if not lower <= start <= end <= upper or kind not in ('all', '0', '1'):
                raise ValueError()
        except ValueError:
            return jsonify(error=f'Chọn khoảng ngày hợp lệ từ {lower} đến {upper} và loại ngày hợp lệ.'), 400
        selected = data.loc[data.dteday.between(start, end)]
        if kind != 'all':
            selected = selected.loc[selected.workingday.eq(int(kind))]
        # A missing hour is unknown, never a zero-rental observation.
        grouped = selected.groupby('hr')['cnt'].agg(['mean', 'count'])
        hourly = [dict(hour=h, mean=float(grouped.loc[h, 'mean']) if h in grouped.index else None,
                       samples=int(grouped.loc[h, 'count']) if h in grouped.index else 0) for h in range(24)]
        peak = min((row for row in hourly if row['samples']),
                   key=lambda row: (-row['mean'], row['hour']), default=None)
        return jsonify(bounds=dict(start=lower, end=upper), filters=dict(start=start,end=end,workingday=kind),
            rows=len(selected), days=int(selected.dteday.nunique()),
            total=int(selected.cnt.sum()), casual=int(selected.casual.sum()), registered=int(selected.registered.sum()),
            average=float(selected.cnt.mean()) if len(selected) else None,
            peak=peak, hourly=hourly)
