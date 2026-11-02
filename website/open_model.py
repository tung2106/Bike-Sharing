"""Open the local website with one double-click, reusing an existing server."""
import argparse
import json
import hashlib
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

PORT = 8000
BASE_URL = 'http://127.0.0.1:8000'
MODEL_PATH = None
VARIANT = None
ROOT = Path(__file__).resolve().parent
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def website_ready():
    try:
        with HTTP.open(BASE_URL + '/api/model', timeout=2) as response:
            info = json.load(response)
        return (info.get('ready') is True and info.get('dataset') == 'hour'
                and info.get('model_sha256') == hashlib.sha256(
                    MODEL_PATH.read_bytes()).hexdigest())
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def port_in_use():
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(('127.0.0.1', PORT)) == 0


def open_browser():
    if not webbrowser.open(BASE_URL, new=2):
        raise RuntimeError('Khong mo duoc trinh duyet mac dinh. Hay kiem tra cai dat trinh duyet tren Windows.')


def main():
    if website_ready():
        print('Website da chay. Dang mo giao dien...', flush=True)
        open_browser()
        return
    if port_in_use():
        raise RuntimeError(f'Cong {PORT} dang duoc su dung boi may chu khac hoac chua san sang. '
                           'Kiem tra cua so may chu dang chay; khong khoi dong them mot ban.')
    print('Dang khoi dong Bike Rental. Trinh duyet se tu mo khi mo hinh san sang.', flush=True)
    server = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), VARIANT, '--serve'], cwd=ROOT)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError('May chu da dung. Xem thong bao loi phia tren.')
            if website_ready():
                open_browser()
                print('Da mo giao dien. Giu cua so nay khi su dung. Nhan Ctrl+C de dung website.', flush=True)
                exit_code = server.wait()
                if exit_code:
                    raise RuntimeError(f'May chu da dung voi ma loi {exit_code}.')
                return
            time.sleep(0.5)
        raise RuntimeError('Mo hinh chua san sang sau 60 giay. Kiem tra file model va thu vien.')
    finally:
        # Only stop a process started by this invocation, never another app.
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


def configure(variant):
    global PORT, BASE_URL, MODEL_PATH, VARIANT
    VARIANT = variant
    PORT = 8000 if variant == 'rf' else 8001
    BASE_URL = f'http://127.0.0.1:{PORT}'
    if variant == 'rf':
        MODEL_PATH = ROOT.parent / 'experiments/rf85/model.joblib'
    else:
        MODEL_PATH = ROOT.parent / 'experiments/hourly_v2/runs/20261025_024202/model.joblib'
    if not MODEL_PATH.is_file():
        raise RuntimeError(f'Khong tim thay model: {MODEL_PATH}. Hay dung nhanh phien-ban-2 de mo ca hai.')
    # Validate the algorithm, not just the file name or inherited environment.
    from app import load_model
    from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
    bundle = load_model(MODEL_PATH)
    expected = RandomForestRegressor if variant == 'rf' else HistGradientBoostingRegressor
    if not isinstance(bundle['pipeline'].named_steps['model'], expected):
        raise RuntimeError('File model khong dung thuat toan da chon.')
    print(f'Model: {expected.__name__} | {BASE_URL}', flush=True)


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('variant', choices=['rf', 'hgb'])
        parser.add_argument('--serve', action='store_true')
        parser.add_argument('--check', action='store_true', help='Validate model and report server status without opening browser')
        args = parser.parse_args()
        os.environ.setdefault('OMP_NUM_THREADS', '4')
        configure(args.variant)
        if args.serve:
            from app import create_app
            from waitress import serve
            serve(create_app(model_path=MODEL_PATH), host='127.0.0.1', port=PORT, threads=4)
        elif args.check:
            print('Matching server ready:', website_ready())
            print('Port in use:', port_in_use())
        else:
            main()
    except KeyboardInterrupt:
        print('\nDa dung website.')
    except Exception as error:
        print(f'Loi: {error}', file=sys.stderr)
        sys.exit(1)
