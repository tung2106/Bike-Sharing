"""Website dự đoán lượt thuê xe theo giờ từ pipeline đã huấn luyện."""

import hashlib
import logging
import math
import os
import warnings
from datetime import date
from pathlib import Path

if __name__ == '__main__':
    os.environ.setdefault('OMP_NUM_THREADS', '4')

import joblib
import numpy as np
import pandas as pd
import sklearn
from flask import Flask, jsonify, render_template, request
from sklearn.exceptions import InconsistentVersionWarning
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from daily_context import PREVIOUS_DAY, daily_totals, previous_day_rentals
from evaluation import HGB_MODEL, PREVIOUS_DAY_MODEL, RF85_MODEL, TEST_CSV
from model_config import HGB_PORT, configured_model_path

ROOT = Path(__file__).resolve().parent
RF_PREVIOUS_DAY_CSV = (
    ROOT.parent
    / 'experiments/rf85_previous_day/runs/20261102T154526002202Z/test_predictions.csv'
)
FEATURES = [
    'temp',
    'atemp',
    'hum',
    'windspeed',
    'yr',
    'holiday',
    'workingday',
    'season',
    'mnth',
    'weekday',
    'weathersit',
    'hr',
]


def season_for(day):
    """Đúng mốc đổi mùa quan sát trong hour.csv 2011–2012."""
    md = (day.month, day.day)
    if (3, 21) <= md < (6, 21):
        return 2
    if (6, 21) <= md < (9, 23):
        return 3
    if (9, 23) <= md < (12, 21):
        return 4
    return 1


def read_number(payload, key, label, low, high, integer=False, optional=False):
    value = payload.get(key)
    if optional and (value is None or value == ''):
        return np.nan
    if value is None or value == '' or isinstance(value, bool):
        raise ValueError(f'Vui lòng nhập {label}.')
    try:
        value = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{label} phải là số.') from None
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{label} phải nằm trong khoảng {low} đến {high}.')
    if integer and value != int(value):
        raise ValueError(f'{label} phải là số nguyên.')
    return int(value) if integer else value


def make_input(payload):
    if not isinstance(payload, dict):
        raise ValueError('Dữ liệu gửi lên phải là một đối tượng JSON.')
    try:
        day = date.fromisoformat(payload.get('date', ''))
    except (ValueError, TypeError):
        raise ValueError('Vui lòng chọn ngày hợp lệ.') from None
    if day.year not in (2011, 2012):
        raise ValueError(
            'Mô hình hiện hỗ trợ bối cảnh năm 2011 hoặc 2012. Chọn ngày trong khoảng này.'
        )
    hour = read_number(payload, 'hour', 'giờ', 0, 23, integer=True)
    weather = read_number(payload, 'weather', 'mã thời tiết', 1, 4, integer=True)
    holiday = payload.get('holiday', False)
    if not isinstance(holiday, bool):
        raise ValueError('Ngày lễ phải là giá trị đúng/sai.')
    temp = read_number(payload, 'temperature', 'nhiệt độ (°C)', -8, 39, optional=True)
    atemp = read_number(
        payload, 'feels_like', 'nhiệt độ cảm nhận (°C)', -16, 50, optional=True
    )
    humidity = read_number(payload, 'humidity', 'độ ẩm (%)', 0, 100, optional=True)
    wind = read_number(payload, 'wind_speed', 'tốc độ gió', 0, 67, optional=True)
    # UCI mô tả riêng thang giờ: temp=(t+8)/47, atemp=(t+16)/66.
    # Không dùng công thức cũ chia 41 / 50 của Readme.txt cho giao diện giờ.
    row = {
        'temp': (temp + 8) / 47,
        'atemp': (atemp + 16) / 66,
        'hum': humidity / 100,
        'windspeed': wind / 67,
        'yr': day.year - 2011,
        'holiday': int(holiday),
        'workingday': int(day.weekday() < 5 and not holiday),
        'season': season_for(day),
        'mnth': day.month,
        'weekday': (day.weekday() + 1) % 7,
        'weathersit': weather,
        'hr': hour,
    }
    return pd.DataFrame([row], columns=FEATURES), day


def load_model(model_path):
    if not model_path.is_file():
        raise RuntimeError('Không tìm thấy tệp mô hình theo đường dẫn đã cấu hình.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', InconsistentVersionWarning)
        bundle = joblib.load(model_path)
    if not isinstance(bundle, dict) or bundle.get('dataset') != 'hour':
        raise RuntimeError(
            'File được chọn không phải mô hình hour đã xuất từ notebook.'
        )
    if (
        bundle.get('features') not in (FEATURES, [*FEATURES, PREVIOUS_DAY])
        or bundle.get('target') != 'cnt'
    ):
        raise RuntimeError('Các cột của mô hình không khớp dữ liệu theo giờ.')
    trained = bundle.get('versions', {}).get('scikit-learn')
    if trained and trained != sklearn.__version__:
        raise RuntimeError(
            f'Cần scikit-learn {trained}, hiện đang dùng {sklearn.__version__}.'
        )
    if not callable(getattr(bundle.get('pipeline'), 'predict', None)):
        raise RuntimeError('Bundle không có pipeline dự đoán hợp lệ.')
    model = bundle['pipeline'].named_steps.get('model')
    if not isinstance(model, (RandomForestRegressor, HistGradientBoostingRegressor)):
        raise RuntimeError(
            'Website hỗ trợ Random Forest và HistGradientBoosting theo giờ.'
        )
    if (
        isinstance(model, HistGradientBoostingRegressor)
        and bundle['features'] != FEATURES
    ):
        raise RuntimeError('HistGradientBoosting cần đúng 12 đặc trưng theo giờ.')
    return bundle


def create_app(model_path=None):
    app = Flask(__name__)
    from history import register_history

    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024
    path = Path(model_path) if model_path is not None else configured_model_path()
    bundle, load_error = None, None
    totals = None
    previous_day_archive = None
    archive = None
    active_model = RF85_MODEL
    try:
        bundle = load_model(path)
        if isinstance(
            bundle['pipeline'].named_steps['model'], HistGradientBoostingRegressor
        ):
            active_model = HGB_MODEL
            archive = path.with_name('test_predictions.csv')
            if bundle.get('report', {}).get('previous_day_comparison'):
                previous_day_archive = archive
            elif archive.resolve() == TEST_CSV and RF_PREVIOUS_DAY_CSV.is_file():
                previous_day_archive = RF_PREVIOUS_DAY_CSV
        elif PREVIOUS_DAY in bundle['features']:
            totals = daily_totals()
            active_model = PREVIOUS_DAY_MODEL
            previous_day_archive = path.with_name('test_predictions.csv')
    except Exception:
        logging.exception('Không tải được mô hình')
        bundle = None
        load_error = 'Chưa tải được mô hình. Kiểm tra đường dẫn và phiên bản thư viện theo hướng dẫn cài đặt.'
    app.config['MODEL_BUNDLE'] = bundle
    register_history(
        app, previous_day_archive, active_model=active_model, archive=archive
    )

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/')
    def index():
        return render_template(
            'index.html',
            show_model_comparison=bundle is not None,
            model_label=active_model[2],
        )

    @app.get('/api/model')
    def model_info():
        if bundle is None:
            return jsonify(ready=False, error=load_error), 503
        report = bundle.get('report', {})
        short_name = active_model[3]
        if active_model == HGB_MODEL:
            rounds = bundle['pipeline'].named_steps['model'].n_iter_
            short_name = f'{short_name} · {rounds} vòng'
        return jsonify(
            ready=True,
            name=bundle.get('name', active_model[2]),
            model_key=active_model[0],
            model_label=active_model[2],
            short_name=short_name,
            dataset='hour',
            uses_previous_day=totals is not None,
            evaluation_note=report.get('evaluation_note'),
            years=[2011, 2012],
            test=report.get('test', {}),
            baseline=report.get('baseline_test', {}),
            parameters=report.get('selection', {}).get('best_params', {}),
            evaluated_at=report.get('evaluated_at_utc'),
            model_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    @app.post('/api/predict')
    def predict():
        if bundle is None:
            return jsonify(error=load_error), 503
        try:
            payload = request.get_json(silent=True)
            frame, day = make_input(payload)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        try:
            if totals is not None:
                frame[PREVIOUS_DAY] = previous_day_rentals([day], totals)
            hourly_frame = pd.concat([frame] * 24, ignore_index=True)
            hourly_frame['hr'] = range(24)
            values = np.asarray(bundle['pipeline'].predict(hourly_frame), dtype=float)
            if (
                values.shape != (24,)
                or not np.isfinite(values).all()
                or (values < 0).any()
            ):
                raise ValueError('Giá trị dự đoán không hợp lệ')
            value = float(values[int(frame.iloc[0]['hr'])])
            hourly = [
                {
                    'hour': hour,
                    'prediction': float(count),
                    'rounded_prediction': int(math.floor(count + 0.5)),
                }
                for hour, count in enumerate(values)
            ]
            missing = [c for c in frame.columns if pd.isna(frame.iloc[0][c])]
            return jsonify(
                prediction=value,
                rounded_prediction=int(math.floor(value + 0.5)),
                date=day.isoformat(),
                hour=int(frame.iloc[0]['hr']),
                imputed_features=missing,
                hourly=hourly,
                features={
                    c: None if pd.isna(frame.iloc[0][c]) else float(frame.iloc[0][c])
                    for c in frame.columns
                },
            )
        except Exception:
            app.logger.exception('Prediction failed')
            return (
                jsonify(
                    error='Không thể dự đoán. Vui lòng kiểm tra mô hình và thử lại.'
                ),
                500,
            )

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error='Dữ liệu gửi lên quá lớn.'), 413

    return app


if __name__ == '__main__':
    import argparse

    from waitress import serve

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, help='Tệp model.joblib cần chạy.')
    parser.add_argument('--port', type=int, default=HGB_PORT)
    args = parser.parse_args()

    app = create_app(model_path=args.model)
    if app.config['MODEL_BUNDLE'] is None:
        parser.exit(1, 'Không tải được mô hình. Xem thông tin lỗi ở trên.\n')
    print(f'Mở website tại http://127.0.0.1:{args.port}', flush=True)
    serve(app, host='127.0.0.1', port=args.port, threads=4)
