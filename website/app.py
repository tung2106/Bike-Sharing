"""Website dự đoán Bike Sharing từ đúng bundle hour của Google Colab."""
import hashlib
import json
import logging
import math
import os
import warnings
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from flask import Flask, jsonify, render_template, request
from sklearn.exceptions import InconsistentVersionWarning

ROOT = Path(__file__).resolve().parent
FEATURES = ['temp', 'atemp', 'hum', 'windspeed', 'yr', 'holiday', 'workingday',
            'season', 'mnth', 'weekday', 'weathersit', 'hr']


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
        raise ValueError('Mô hình hiện hỗ trợ bối cảnh năm 2011 hoặc 2012. Chọn ngày trong khoảng này.')
    hour = read_number(payload, 'hour', 'giờ', 0, 23, integer=True)
    weather = read_number(payload, 'weather', 'mã thời tiết', 1, 4, integer=True)
    holiday = payload.get('holiday', False)
    if not isinstance(holiday, bool):
        raise ValueError('Ngày lễ phải là giá trị đúng/sai.')
    temp = read_number(payload, 'temperature', 'nhiệt độ (°C)', -8, 39, optional=True)
    atemp = read_number(payload, 'feels_like', 'nhiệt độ cảm nhận (°C)', -16, 50, optional=True)
    humidity = read_number(payload, 'humidity', 'độ ẩm (%)', 0, 100, optional=True)
    wind = read_number(payload, 'wind_speed', 'tốc độ gió', 0, 67, optional=True)
    # UCI mô tả riêng thang giờ: temp=(t+8)/47, atemp=(t+16)/66.
    # Không dùng công thức cũ chia 41 / 50 của Readme.txt cho giao diện giờ.
    row = {'temp': (temp + 8) / 47, 'atemp': (atemp + 16) / 66,
           'hum': humidity / 100, 'windspeed': wind / 67,
           'yr': day.year - 2011, 'holiday': int(holiday),
           'workingday': int(day.weekday() < 5 and not holiday),
           'season': season_for(day), 'mnth': day.month,
           'weekday': (day.weekday() + 1) % 7, 'weathersit': weather, 'hr': hour}
    return pd.DataFrame([row], columns=FEATURES), day


def load_model(model_path):
    if not model_path.is_file():
        raise RuntimeError('Chưa có file mô hình. Đặt model.joblib của hour vào thư mục models rồi khởi động lại.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', InconsistentVersionWarning)
        bundle = joblib.load(model_path)
    if not isinstance(bundle, dict) or bundle.get('dataset') != 'hour':
        raise RuntimeError('File được chọn không phải mô hình hour đã xuất từ notebook.')
    if bundle.get('features') != FEATURES or bundle.get('target') != 'cnt':
        raise RuntimeError('Các cột của mô hình không khớp dữ liệu theo giờ.')
    trained = bundle.get('versions', {}).get('scikit-learn')
    if trained and trained != sklearn.__version__:
        raise RuntimeError(f'Cần scikit-learn {trained}, hiện đang dùng {sklearn.__version__}.')
    if not callable(getattr(bundle.get('pipeline'), 'predict', None)):
        raise RuntimeError('Bundle không có pipeline dự đoán hợp lệ.')
    return bundle


def create_app(model_path=None):
    app = Flask(__name__)
    from history import register_history
    register_history(app)
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024
    path = Path(model_path or os.environ.get('BIKE_MODEL_PATH', ROOT / 'models' / 'model.joblib'))
    bundle, load_error = None, None
    try:
        bundle = load_model(path)
    except Exception:
        logging.exception('Không tải được mô hình')
        load_error = 'Chưa tải được mô hình. Kiểm tra file hour/model.joblib và phiên bản thư viện theo hướng dẫn cài đặt.'
    app.config['MODEL_BUNDLE'] = bundle

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/api/model')
    def model_info():
        if bundle is None:
            return jsonify(ready=False, error=load_error), 503
        report = bundle.get('report', {})
        return jsonify(ready=True, name=bundle.get('name', 'Random Forest · theo giờ'), dataset='hour',
                       evaluation_note=report.get('evaluation_note'),
                       years=[2011, 2012], test=report.get('test', {}),
                       baseline=report.get('baseline_test', {}),
                       parameters=report.get('selection', {}).get('best_params', {}),
                       evaluated_at=report.get('evaluated_at_utc'),
                       model_sha256=hashlib.sha256(path.read_bytes()).hexdigest())

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
            hourly_frame = pd.concat([frame] * 24, ignore_index=True)
            hourly_frame['hr'] = range(24)
            values = np.asarray(bundle['pipeline'].predict(hourly_frame), dtype=float)
            if values.shape != (24,) or not np.isfinite(values).all() or (values < 0).any():
                raise ValueError('Giá trị dự đoán không hợp lệ')
            value = float(values[int(frame.iloc[0]['hr'])])
            hourly = [{'hour': hour, 'prediction': float(count),
                       'rounded_prediction': int(math.floor(count + 0.5))}
                      for hour, count in enumerate(values)]
            missing = [c for c in FEATURES if pd.isna(frame.iloc[0][c])]
            return jsonify(prediction=value, rounded_prediction=int(math.floor(value + 0.5)),
                           date=day.isoformat(), hour=int(frame.iloc[0]['hr']),
                           imputed_features=missing, hourly=hourly,
                           features={c: None if pd.isna(frame.iloc[0][c]) else float(frame.iloc[0][c]) for c in FEATURES})
        except Exception:
            app.logger.exception('Prediction failed')
            return jsonify(error='Không thể dự đoán. Vui lòng kiểm tra mô hình và thử lại.'), 500

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error='Dữ liệu gửi lên quá lớn.'), 413

    return app


if __name__ == '__main__':
    from waitress import serve
    print('Mở website tại http://127.0.0.1:8000', flush=True)
    serve(create_app(), host='127.0.0.1', port=8000, threads=4)
