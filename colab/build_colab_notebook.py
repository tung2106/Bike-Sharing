"""Build the self-contained Colab notebook and upload bundle."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
RAW_DIR = PROJECT_ROOT / 'du_lieu' / 'goc'
PACKAGE_DIR = PROJECT_ROOT / 'ban_dong_goi'
cells = []


def cell(kind, source):
    item = {'cell_type': kind, 'metadata': {}, 'source': source.strip() + '\n',
            'id': f'cell-{len(cells):02d}'}
    if kind == 'code':
        item.update(execution_count=None, outputs=[])
    cells.append(item)


cell('markdown', '''# Bike Sharing: train, chọn tham số và đánh giá cuối

Notebook độc lập dành cho **day.csv và hour.csv**, mục tiêu hồi quy **cnt**.

1. Tải notebook này lên Google Colab.
2. Tạo thư mục **MyDrive/TT_CSN/data** trên Google Drive, tải hai CSV **gốc** vào đó.
3. Chọn runtime Python 3 (CPU là đủ), chạy các ô từ trên xuống và cho phép kết nối Drive.
4. Mỗi lần chạy lưu vào thư mục mới trong **MyDrive/TT_CSN/runs**.

Chia theo thời gian: **70% train / 15% validation / 15% test**. Làm tròn xuống train và validation,
test nhận phần còn lại. Không dùng test để chọn tham số và không refit trên train + validation.
Hai dataset chạy riêng. `casual` và `registered` bị loại vì tổng của chúng chính là `cnt`.

Random Forest được chọn làm mô hình khởi đầu. Chọn trong 8 cấu hình bằng RMSE validation;
đánh giá cuối bằng RMSE, MAE và R², đối chiếu với dự đoán trung bình train.
Thời tiết phải có sẵn tại thời điểm dự đoán; dự báo tương lai cần đầu vào thời tiết tương ứng.
''')
cell('code', '%pip -q install "scikit-learn>=1.2,<2" "pandas>=1.5,<4" "numpy>=1.24,<3" "joblib>=1.2,<2"')

source = (ROOT / 'colab_train.py').read_text(encoding='utf-8')
for section in source.split('# %% ')[1:]:
    title, code = section.split('\n', 1)
    cell('markdown', '## ' + title)
    cell('code', code)

cell('markdown', '''## 1. Kết nối Drive và kiểm tra hai CSV gốc

Nếu dùng đường dẫn khác, sửa `PROJECT_NAME` hoặc `DATA_DIR`.
Không dùng các CSV đã chia và mã hóa làm dữ liệu gốc; hãy dùng `day.csv` và `hour.csv` gốc.
''')
cell('code', '''from IPython.display import display
from uuid import uuid4

PROJECT_NAME = 'TT_CSN'
PROJECT_DIR = connect_google_drive(PROJECT_NAME)
DATA_DIR = PROJECT_DIR / 'data'
DATASETS = ['day', 'hour']  # Có thể chọn ['day'] hoặc ['hour'].
RUN_ID = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:8]
RUN_DIR = PROJECT_DIR / 'runs' / RUN_ID

for dataset in DATASETS:
    path = DATA_DIR / f'{dataset}.csv'
    if not path.is_file():
        raise FileNotFoundError(f'Hãy tải CSV gốc lên: {path}')
RUN_DIR.mkdir(parents=True, exist_ok=False)
print('Dữ liệu:', DATA_DIR)
print('Kết quả sẽ lưu:', RUN_DIR)
''')
cell('markdown', '''## 2. Chia và xuất train / validation / test

Xuất bản chưa mã hóa tại `<dataset>/splits/raw/`. File CSV chứa các đặc trưng và cột nhãn `cnt`.
Ngày và mã bản ghi được lưu riêng trong `split_manifest.csv` để đối chiếu.
Không tự tạo nhãn thiếu; cột số điền trung vị, cột phân loại điền mode ở bước train.
''')
cell('code', '''split_reports = {}
split_summary = []
for dataset in DATASETS:
    report = split_dataset(DATA_DIR / f'{dataset}.csv', RUN_DIR / dataset, dataset)
    split_reports[dataset] = report
    for split, details in report['splits'].items():
        split_summary.append({'dataset': dataset, 'split': split, **details})
display(pd.DataFrame(split_summary))
''')
cell('markdown', '''## 3. Huấn luyện và chọn siêu tham số

Hàm `train_and_select()` chỉ nhận train và validation. Bộ điền thiếu và one-hot chỉ fit trên train.
Mã phân loại mới được xử lý bằng nhóm one-hot toàn 0 (`handle_unknown='ignore'`).
Giữ cột nhị phân 0/1; các biến thời tiết đã được chuẩn hóa trong nguồn, không scale lại.

Sửa lưới bên dưới **trước khi xem kết quả test**. RMSE validation càng thấp càng tốt.
''')
cell('code', '''PARAM_GRID = {
    'n_estimators': [100, 200],
    'max_depth': [None, 16],
    'min_samples_leaf': [1, 3],
    'max_features': [1.0],
}
selected = {}
for dataset in DATASETS:
    destination = RUN_DIR / dataset
    if (destination / 'metrics.json').exists():
        raise RuntimeError('Đã đánh giá test trong lần chạy này. Không chọn lại tham số dựa trên test.')
    train = pd.read_csv(destination / 'splits/raw/train.csv')
    validation = pd.read_csv(destination / 'splits/raw/validation.csv')
    pipeline, selection = train_and_select(train, validation, dataset, destination, PARAM_GRID)
    selected[dataset] = (pipeline, selection)
    print(dataset, 'tham số tốt nhất:', selection['best_params'])
    display(pd.read_csv(destination / 'validation_results.csv'))
''')
cell('markdown', '''## 4. Đánh giá cuối và lưu mô hình lên Drive

Chỉ chạy sau khi đã chốt mô hình. Lưu đúng mô hình đã học trên 70% và được đánh giá trên test.
`model.joblib` chứa pipeline tiền xử lý + Random Forest, thứ tự cột và thông tin phiên bản.
File `splits/train.csv`, `splits/validation.csv`, `splits/test.csv` là bản số đã mã hóa,
có thể tách `X = df.drop(columns='cnt')`, `y = df['cnt']` để dùng với thuật toán khác.
Pipeline đã lưu nhận **dữ liệu gốc**, không nhận các CSV đã one-hot.
''')
cell('code', '''final_results = []
for dataset in DATASETS:
    destination = RUN_DIR / dataset
    if (destination / 'metrics.json').exists():
        raise RuntimeError(f'{dataset}: đã đánh giá test; đọc metrics.json để xem lại.')
    pipeline, selection = selected[dataset]
    train = pd.read_csv(destination / 'splits/raw/train.csv')
    test = pd.read_csv(destination / 'splits/raw/test.csv')
    report = evaluate_and_save(pipeline, selection, train, test, dataset, destination)
    export_encoded_splits(pipeline, destination, split_reports[dataset]['features'])
    final_results.append({'dataset': dataset, **report['test'],
                          'baseline_RMSE': report['baseline_test']['RMSE']})
summary = pd.DataFrame(final_results)
summary.to_csv(RUN_DIR / 'summary.csv', index=False)
display(summary)
print('Đã lưu mô hình, dữ liệu và báo cáo:', RUN_DIR)
''')
cell('markdown', '''## 5. Tải lại mô hình và dự đoán

Ví dụ dùng 5 dòng train chỉ để minh họa hàm dự đoán, không phải một phép đánh giá mới.
Thay `sample` bằng DataFrame mới hoặc đường dẫn CSV mới để sử dụng thực tế.
Trong phiên Colab mới: chạy ô thư viện, các ô định nghĩa hàm, kết nối Drive rồi gán
`RUN_DIR = PROJECT_DIR / 'runs' / '<mã lần chạy đã lưu>'`; không cần huấn luyện lại.
Khi tải lại mô hình, dùng phiên bản thư viện ghi trong `requirements.txt` của lần chạy.
''')
cell('code', '''DATASET_TO_PREDICT = DATASETS[0]
MODEL_PATH = RUN_DIR / DATASET_TO_PREDICT / 'model.joblib'
sample = pd.read_csv(RUN_DIR / DATASET_TO_PREDICT / 'splits/raw/train.csv').head(5).drop(columns=TARGET)
display(predict_saved_model(MODEL_PATH, sample))
# Dự đoán file mới:
# predictions = predict_saved_model(MODEL_PATH, PROJECT_DIR / 'data/new_data.csv')
# predictions.to_csv(PROJECT_DIR / 'predictions.csv', index=False)
''')
cell('markdown', '''## Các file được lưu

```
MyDrive/TT_CSN/runs/<RUN_ID>/
  summary.csv
  day/ (hour/ có cùng cấu trúc)
    splits/raw/train.csv, validation.csv, test.csv
    splits/train.csv, validation.csv, test.csv
    splits/split_manifest.csv
    split_report.json
    validation_results.csv
    selection.json
    metrics.json
    test_predictions.csv
    preprocessor.joblib
    model.joblib
    environment.json
    requirements.txt
```

Hàm chạy trọn quy trình nếu dùng Python thay vì các ô từng bước:
`run_experiment('day', DATA_DIR, RUN_DIR)` và tương tự với `'hour'`.
Không chạy lại hàm này trong cùng thư mục đã đánh giá test.

Tài liệu: [Kết nối Google Drive trong Colab](https://colab.research.google.com/notebooks/io.ipynb),
[RandomForestRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html),
[OneHotEncoder](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OneHotEncoder.html),
[Lưu mô hình](https://scikit-learn.org/stable/model_persistence.html).
Nguồn dữ liệu và thông tin trích dẫn: `Readme.txt` đi kèm dataset.
''')

notebook = {'nbformat': 4, 'nbformat_minor': 5, 'cells': cells,
            'metadata': {'colab': {'name': 'Bike_Sharing_Colab.ipynb', 'provenance': []},
                         'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                         'language_info': {'name': 'python', 'version': '3.12'}}}
(ROOT / 'Bike_Sharing_Colab.ipynb').write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding='utf-8')
PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
with ZipFile(PACKAGE_DIR / 'Bike_Sharing_Colab.zip', 'w', ZIP_DEFLATED) as archive:
    for name in ['Bike_Sharing_Colab.ipynb', 'colab_train.py', 'HUONG_DAN_COLAB.txt']:
        archive.write(ROOT / name, name)
    archive.write(RAW_DIR / 'Readme.txt', 'Readme.txt')
    for name in ['day.csv', 'hour.csv']:
        archive.write(RAW_DIR / name, 'data/' + name)
print('Built colab/Bike_Sharing_Colab.ipynb and ban_dong_goi/Bike_Sharing_Colab.zip')
