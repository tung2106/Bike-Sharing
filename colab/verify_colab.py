"""Run notebook logic locally with a small grid; Google auth is mocked only."""
import json
import sys
import types
from pathlib import Path
from uuid import uuid4

import joblib
import nbformat
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
RAW_DIR = PROJECT_ROOT / 'du_lieu' / 'goc'
notebook = nbformat.read(ROOT / 'Bike_Sharing_Colab.ipynb', as_version=4)
nbformat.validate(notebook)
namespace = {'__name__': '__notebook_check__'}
for cell in notebook.cells:
    if cell.cell_type == 'code' and not cell.source.startswith('%'):
        compile(cell.source, '<notebook>', 'exec')
    if cell.cell_type == 'code' and ('def ' in cell.source or cell.source.startswith('import hashlib')):
        exec(cell.source, namespace)

# Test the actual mount wrapper without a Google login.
check_root = PROJECT_ROOT / 'rac' / 'kiem_thu' / 'colab' / uuid4().hex
mount_calls = []
fake_colab = types.ModuleType('google.colab')
fake_colab.drive = types.SimpleNamespace(mount=lambda path: mount_calls.append(path))
sys.modules['google.colab'] = fake_colab
project = namespace['connect_google_drive']('TT_CSN', str(check_root / 'drive'))
assert mount_calls == [str(check_root / 'drive')]
assert (project / 'data').is_dir()

# Execute the real action cells, substituting local data and a smaller grid.
namespace['display'] = lambda obj: None
for cell in notebook.cells:
    if cell.cell_type != 'code':
        continue
    source = cell.source
    if source.startswith('from IPython.display import display'):
        source = source.replace('from IPython.display import display', '')
        source = source.replace("PROJECT_DIR = connect_google_drive(PROJECT_NAME)",
                                'PROJECT_DIR = Path(' + repr(str(project)) + ')')
        source = source.replace("DATA_DIR = PROJECT_DIR / 'data'", 'DATA_DIR = Path(' + repr(str(RAW_DIR)) + ')')
        exec(source, namespace)
    elif source.startswith(('split_reports =', 'PARAM_GRID =', 'final_results =', 'DATASET_TO_PREDICT =')):
        source = source.replace("'n_estimators': [100, 200]", "'n_estimators': [10]")
        source = source.replace("'min_samples_leaf': [1, 3]", "'min_samples_leaf': [1]")
        exec(source, namespace)

for name, counts in {'day': [511, 109, 111], 'hour': [12165, 2606, 2608]}.items():
    folder = namespace['RUN_DIR'] / name
    bundle = joblib.load(folder / 'model.joblib')
    processor = bundle['pipeline'].named_steps['preprocessor']
    headers = []
    for split, size in zip(['train', 'validation', 'test'], counts):
        raw = pd.read_csv(folder / 'splits/raw' / f'{split}.csv')
        encoded = pd.read_csv(folder / 'splits' / f'{split}.csv')
        assert len(raw) == len(encoded) == size
        assert np.isfinite(encoded.to_numpy()).all()
        np.testing.assert_array_equal(raw['cnt'], encoded['cnt'])
        headers.append(list(encoded.columns))
    assert headers[0] == headers[1] == headers[2]
    train = pd.read_csv(folder / 'splits/raw/train.csv')
    np.testing.assert_allclose(processor.named_transformers_['numeric'].statistics_, train[namespace['NUMERIC']].median())
    # Exercise missing values, unknown categories, and prediction without target.
    sample = train.iloc[:3].drop(columns='cnt').copy()
    sample.loc[0, 'temp'] = np.nan
    sample.loc[1, 'season'] = 99
    sample.loc[2, 'holiday'] = np.nan
    predictions = namespace['predict_saved_model'](folder / 'model.joblib', sample)
    assert len(predictions) == 3 and np.isfinite(predictions.to_numpy()).all()
    validation_table = pd.read_csv(folder / 'validation_results.csv')
    selection = json.loads((folder / 'selection.json').read_text(encoding='utf-8'))
    assert np.isclose(selection['best_validation_RMSE'], validation_table['RMSE'].min())
    test = pd.read_csv(folder / 'splits/raw/test.csv')
    metrics = namespace['regression_metrics'](test['cnt'], bundle['pipeline'].predict(test.drop(columns='cnt')))
    saved = json.loads((folder / 'metrics.json').read_text(encoding='utf-8'))['test']
    assert metrics == saved
    assert set(bundle['features']).isdisjoint({'cnt', 'instant', 'casual', 'registered', 'dteday'})
    print(f'{name}: split, train-only imputation, validation selection, metrics and model round-trip PASS')

# Changing validation observations must not change training imputation statistics.
train = pd.read_csv(namespace['RUN_DIR'] / 'day/splits/raw/train.csv')
validation = pd.read_csv(namespace['RUN_DIR'] / 'day/splits/raw/validation.csv')
train.loc[0, 'temp'] = np.nan
validation['temp'] = 999999
pipeline, _ = namespace['train_and_select'](train, validation, 'day', check_root / 'leakage_check',
                                          {'n_estimators': [2], 'max_depth': [2]}, n_jobs=1)
assert pipeline.named_steps['preprocessor'].named_transformers_['numeric'].statistics_[0] == train['temp'].median()
print('Notebook schema, all Python cells, simulated Drive connection, train-only fit: PASS')
print('Verification outputs (small grid, not final Colab results):', namespace['RUN_DIR'])
