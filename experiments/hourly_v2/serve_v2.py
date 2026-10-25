"""Chay thu model v2 o cong rieng; dung Ctrl+C de dung."""
import os
os.environ.setdefault('OMP_NUM_THREADS', '4')
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'website'))
from app import create_app
from waitress import serve

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True, type=Path, help='Thu muc ket qua chua model.joblib')
    parser.add_argument('--port', type=int, default=8001)
    args = parser.parse_args()
    model = args.run.resolve() / 'model.joblib'
    app = create_app(model_path=model)
    if app.config['MODEL_BUNDLE'] is None:
        raise RuntimeError('Khong tai duoc model: ' + str(model))
    print('MODEL:', model, flush=True)
    print(f'URL: http://127.0.0.1:{args.port}', flush=True)
    serve(app, host='127.0.0.1', port=args.port, threads=4)
