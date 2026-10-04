"""Các hàm cho notebook Bike_Sharing_Colab.ipynb (Python >= 3.10)."""

# %% Thư viện và cấu hình
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import ParameterGrid
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

NUMERIC = ['temp', 'atemp', 'hum', 'windspeed']
BINARY = ['yr', 'holiday', 'workingday']
CATEGORICAL = ['season', 'mnth', 'weekday', 'weathersit']
TARGET = 'cnt'
SEED = 42
DEFAULT_GRID = {
    'n_estimators': [100, 200],
    'max_depth': [None, 16],
    'min_samples_leaf': [1, 3],
    'max_features': [1.0],
}


def save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False),
                          encoding='utf-8')


# %% Kết nối Google Drive
def connect_google_drive(project_name='TT_CSN', mount_point='/content/drive'):
    """Yêu cầu đăng nhập Drive trong Colab, trả về thư mục dự án."""
    from google.colab import drive
    drive.mount(mount_point)
    project = Path(mount_point) / 'MyDrive' / project_name
    (project / 'data').mkdir(parents=True, exist_ok=True)
    return project


# %% Đọc dữ liệu, chia 70/15/15 và xuất CSV gốc
def feature_columns(dataset):
    if dataset not in ('day', 'hour'):
        raise ValueError("dataset phải là 'day' hoặc 'hour'")
    categorical = CATEGORICAL + (['hr'] if dataset == 'hour' else [])
    return NUMERIC + BINARY + categorical, categorical


def normalize_features(frame, features):
    """Giữ đúng schema và xử lý các ký hiệu thiếu giống lúc dự đoán."""
    missing_columns = set(features) - set(frame.columns)
    if missing_columns:
        raise ValueError(f'Thiếu cột đầu vào: {sorted(missing_columns)}')
    result = frame.loc[:, features].replace(
        r'(?i)^\s*(?:na|n/a|nan|null|none|\?)?\s*$', np.nan, regex=True)
    for column in features:
        result[column] = pd.to_numeric(result[column], errors='raise')
    result = result.replace([np.inf, -np.inf], np.nan).astype(float)
    for column in set(features) - set(NUMERIC):
        present = result[column].dropna()
        if not (present % 1 == 0).all():
            raise ValueError(f'Cột {column} cần mã nguyên')
    for column in BINARY:
        if not result[column].dropna().isin([0, 1]).all():
            raise ValueError(f'Cột {column} cần giá trị 0/1')
    return result


def split_dataset(csv_path, output_dir, dataset):
    """Sắp theo thời gian, chia rồi xuất CSV; chưa học phép điền/mã hóa."""
    csv_path, output_dir = Path(csv_path), Path(output_dir)
    features, categorical = feature_columns(dataset)
    frame = pd.read_csv(csv_path, na_values=['?', 'null', 'None', 'none', 'NA', 'N/A'])
    required = set(features + ['instant', 'dteday', TARGET])
    if required - set(frame.columns):
        raise ValueError(f'{csv_path.name}: thiếu {sorted(required - set(frame.columns))}')
    original_rows = len(frame)
    original_missing = {c: int(v) for c, v in frame.isna().sum().items()}
    frame = frame.drop_duplicates().copy()
    duplicates = original_rows - len(frame)
    frame[TARGET] = pd.to_numeric(frame[TARGET], errors='raise').replace([np.inf, -np.inf], np.nan)
    missing_target = int(frame[TARGET].isna().sum())
    frame = frame.dropna(subset=[TARGET]).copy()
    if not ((frame[TARGET] >= 0) & (frame[TARGET] % 1 == 0)).all():
        raise ValueError('cnt phải là số nguyên không âm')
    frame[features] = normalize_features(frame, features)
    dates = pd.to_datetime(frame['dteday'], format='%Y-%m-%d', errors='raise')
    if dates.isna().any():
        raise ValueError('Thiếu ngày: không thể chia theo thời gian')
    if dataset == 'hour':
        if frame['hr'].isna().any() or not frame['hr'].between(0, 23).all():
            raise ValueError('Thiếu/sai giờ: không thể chia theo thời gian')
        dates = dates + pd.to_timedelta(frame['hr'], unit='h')
    frame['timestamp'] = dates
    if frame['timestamp'].duplicated().any() or frame['instant'].duplicated().any():
        raise ValueError('Trùng thời điểm hoặc mã bản ghi; cần kiểm tra dữ liệu')
    frame = frame.sort_values('timestamp', kind='stable').reset_index(drop=True)
    n = len(frame)
    a, b = n * 70 // 100, n * 70 // 100 + n * 15 // 100
    partitions = {'train': frame.iloc[:a].copy(),
                  'validation': frame.iloc[a:b].copy(), 'test': frame.iloc[b:].copy()}
    if any(len(part) < 2 for part in partitions.values()):
        raise ValueError('Mỗi tập cần ít nhất 2 dòng để đánh giá R²')
    if partitions['train'][features].isna().all().any():
        raise ValueError('Có cột hoàn toàn thiếu trên train, cần kiểm tra nguồn')
    raw_dir = output_dir / 'splits' / 'raw'
    raw_dir.mkdir(parents=True, exist_ok=True)
    report = {'dataset': dataset, 'target': TARGET, 'source_sha256': hashlib.sha256(csv_path.read_bytes()).hexdigest(),
              'original_rows': original_rows, 'missing_original': original_missing,
              'duplicates_removed': duplicates, 'missing_target_removed': missing_target,
              'features': features, 'categorical': categorical,
              'split_method': 'chronological: floor(70% N), floor(15% N), remainder',
              'splits': {}}
    manifest = []
    for name, part in partitions.items():
        part[features + [TARGET]].to_csv(raw_dir / f'{name}.csv', index=False)
        manifest.append(part[['instant', 'dteday', 'timestamp']].assign(split=name))
        report['splits'][name] = {'rows': len(part), 'percentage': 100 * len(part) / n,
                                 'start': str(part['timestamp'].iloc[0]),
                                 'end': str(part['timestamp'].iloc[-1])}
    pd.concat(manifest).to_csv(output_dir / 'splits' / 'split_manifest.csv', index=False)
    assert partitions['train']['timestamp'].max() < partitions['validation']['timestamp'].min()
    assert partitions['validation']['timestamp'].max() < partitions['test']['timestamp'].min()
    save_json(output_dir / 'split_report.json', report)
    return report


# %% Tiền xử lý và train, chọn siêu tham số chỉ bằng validation
def make_preprocessor(dataset):
    _, categorical = feature_columns(dataset)
    return ColumnTransformer([
        ('numeric', SimpleImputer(strategy='median'), NUMERIC),
        ('binary', SimpleImputer(strategy='most_frequent'), BINARY),
        ('category', Pipeline([
            ('imputer', SimpleImputer(strategy='most_frequent')),
            ('encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
        ]), categorical),
    ], remainder='drop', verbose_feature_names_out=False)


def regression_metrics(actual, predicted):
    return {'RMSE': float(np.sqrt(mean_squared_error(actual, predicted))),
            'MAE': float(mean_absolute_error(actual, predicted)),
            'R2': float(r2_score(actual, predicted))}


def train_and_select(train, validation, dataset, output_dir, param_grid=None, n_jobs=-1):
    """Không nhận test. Chọn RMSE validation thấp nhất, không refit trên 85%."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    features, _ = feature_columns(dataset)
    X_train, X_val = normalize_features(train, features), normalize_features(validation, features)
    y_train, y_val = train[TARGET], validation[TARGET]
    processor = make_preprocessor(dataset)
    train_encoded = processor.fit_transform(X_train)
    val_encoded = processor.transform(X_val)
    assert np.isfinite(train_encoded).all() and np.isfinite(val_encoded).all()
    candidates = list(ParameterGrid(DEFAULT_GRID if param_grid is None else param_grid))
    if not candidates:
        raise ValueError('Lưới tham số rỗng')
    history, best_model, best_score, best_params = [], None, np.inf, None
    for index, params in enumerate(candidates, start=1):
        model = RandomForestRegressor(random_state=SEED, n_jobs=n_jobs, **params)
        model.fit(train_encoded, y_train)
        metrics = regression_metrics(y_val, model.predict(val_encoded))
        history.append({'candidate': index, 'parameters': json.dumps(params), **metrics})
        print(f"{dataset}: cấu hình {index}/{len(candidates)}, validation RMSE={metrics['RMSE']:.3f}", flush=True)
        if metrics['RMSE'] < best_score:
            best_model, best_score, best_params = model, metrics['RMSE'], params
    # Hai thành phần đều đã fit; ghép pipeline không huấn luyện lại.
    pipeline = Pipeline([('preprocessor', processor), ('model', best_model)])
    table = pd.DataFrame(history).sort_values(['RMSE', 'candidate'], kind='stable')
    table.to_csv(output_dir / 'validation_results.csv', index=False)
    selection = {'algorithm': 'RandomForestRegressor', 'selection_metric': 'validation RMSE',
                 'best_params': best_params, 'best_validation_RMSE': float(best_score),
                 'fit_partition': 'train only (70%)', 'random_state': SEED,
                 'candidate_count': len(candidates),
                 'baseline_validation': regression_metrics(y_val, np.full(len(y_val), y_train.mean()))}
    save_json(output_dir / 'selection.json', selection)
    return pipeline, selection


# %% Đánh giá cuối, xuất dữ liệu đã mã hóa, lưu và tải lại mô hình
def export_encoded_splits(pipeline, output_dir, features):
    output_dir = Path(output_dir)
    processor = pipeline.named_steps['preprocessor']
    names = processor.get_feature_names_out()
    for split in ['train', 'validation', 'test']:
        raw = pd.read_csv(output_dir / 'splits' / 'raw' / f'{split}.csv')
        values = processor.transform(normalize_features(raw, features))
        if not np.isfinite(values).all():
            raise ValueError(f'{split}: dữ liệu mã hóa còn giá trị thiếu/vô hạn')
        encoded = pd.DataFrame(values, columns=names)
        encoded[TARGET] = raw[TARGET].to_numpy()
        encoded.to_csv(output_dir / 'splits' / f'{split}.csv', index=False)
    joblib.dump(processor, output_dir / 'preprocessor.joblib')


def evaluate_and_save(pipeline, selection, train, test, dataset, output_dir):
    """Đánh giá cấu hình đã chốt, lưu đúng mô hình được đánh giá."""
    output_dir = Path(output_dir)
    features, _ = feature_columns(dataset)
    X_test = normalize_features(test, features)
    predicted = pipeline.predict(X_test)
    test_metrics = regression_metrics(test[TARGET], predicted)
    baseline = regression_metrics(test[TARGET], np.full(len(test), train[TARGET].mean()))
    report = {'dataset': dataset, 'test': test_metrics, 'baseline_test': baseline,
              'baseline': 'mean cnt from train', 'selection': selection,
              'evaluated_at_utc': datetime.now(timezone.utc).isoformat()}
    save_json(output_dir / 'metrics.json', report)
    pd.DataFrame({'actual_cnt': test[TARGET].to_numpy(), 'predicted_cnt': predicted,
                  'residual': test[TARGET].to_numpy() - predicted}).to_csv(
                      output_dir / 'test_predictions.csv', index=False)
    versions = {'python': platform.python_version(), 'numpy': np.__version__,
                'pandas': pd.__version__, 'scikit-learn': sklearn.__version__, 'joblib': joblib.__version__}
    bundle = {'pipeline': pipeline, 'features': features, 'target': TARGET,
              'dataset': dataset, 'versions': versions, 'report': report}
    path = output_dir / 'model.joblib'
    joblib.dump(bundle, path, compress=3)
    reloaded = joblib.load(path)
    np.testing.assert_allclose(reloaded['pipeline'].predict(X_test.iloc[:10]), predicted[:10])
    save_json(output_dir / 'environment.json', versions)
    (output_dir / 'requirements.txt').write_text('\n'.join(
        f'{name}=={version}' for name, version in versions.items() if name != 'python') + '\n', encoding='utf-8')
    return report


def predict_saved_model(model_path, new_data):
    """Đầu vào là DataFrame gốc hoặc đường dẫn CSV, không cần cnt."""
    bundle = joblib.load(model_path)
    frame = pd.read_csv(new_data) if isinstance(new_data, (str, Path)) else new_data.copy()
    X = normalize_features(frame, bundle['features'])
    return pd.DataFrame({'predicted_cnt': bundle['pipeline'].predict(X)}, index=frame.index)


# %% Hàm chạy trọn quy trình cho một dataset
def run_experiment(dataset, data_dir, run_dir, param_grid=None, n_jobs=-1):
    output_dir = Path(run_dir) / dataset
    if (output_dir / 'metrics.json').exists():
        raise FileExistsError('Lần chạy này đã có kết quả test. Tạo RUN_DIR mới để không ghi đè.')
    split_report = split_dataset(Path(data_dir) / f'{dataset}.csv', output_dir, dataset)
    raw_dir = output_dir / 'splits' / 'raw'
    train = pd.read_csv(raw_dir / 'train.csv')
    validation = pd.read_csv(raw_dir / 'validation.csv')
    pipeline, selection = train_and_select(train, validation, dataset, output_dir, param_grid, n_jobs)
    # Chỉ tải tập test vào bước đánh giá sau khi đã chọn xong cấu hình.
    test = pd.read_csv(raw_dir / 'test.csv')
    report = evaluate_and_save(pipeline, selection, train, test, dataset, output_dir)
    export_encoded_splits(pipeline, output_dir, split_report['features'])
    print(f'Đã lưu {dataset}: {output_dir}', flush=True)
    return report
