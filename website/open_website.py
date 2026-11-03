"""Open the local website with one double-click, reusing an existing server."""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPERIMENTS = ROOT.parent / 'experiments'
DEMO_RUN = EXPERIMENTS / 'rf85_previous_day' / 'runs' / '20261102T154526002202Z'
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def website_ready(base_url, model_hash):
    try:
        with HTTP.open(base_url + '/api/model', timeout=2) as response:
            info = json.load(response)
        return (
            info.get('ready') is True
            and info.get('dataset') == 'hour'
            and info.get('model_sha256') == model_hash
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def port_in_use(port):
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(('127.0.0.1', port)) == 0


def open_browser(base_url):
    if not webbrowser.open(base_url, new=2):
        raise RuntimeError(
            'Khong mo duoc trinh duyet mac dinh. Hay kiem tra cai dat trinh duyet tren Windows.'
        )


def main(demo=False):
    if demo:
        port = 8002
        model = DEMO_RUN / 'model.joblib'
        server_script = EXPERIMENTS / 'hourly_comparison' / 'serve_v2.py'
        command = [sys.executable, '-B', str(server_script), '--run', str(DEMO_RUN), '--port', str(port)]
    else:
        port = 8001
        model = ROOT / os.environ.get('BIKE_MODEL_PATH', 'models/model.joblib')
        command = [sys.executable, '-B', str(ROOT / 'app.py')]

    if not model.is_file():
        raise RuntimeError(f'Khong tim thay mo hinh: {model}')
    model_hash = hashlib.sha256(model.read_bytes()).hexdigest()
    base_url = f'http://127.0.0.1:{port}'
    if website_ready(base_url, model_hash):
        print('Website da chay. Dang mo giao dien...', flush=True)
        open_browser(base_url)
        return
    if port_in_use(port):
        raise RuntimeError(
            f'Cong {port} dang duoc su dung nhung khong tra ve dung mo hinh. '
            'Kiem tra cua so may chu dang chay; khong khoi dong them mot ban.'
        )
    print(
        'Dang khoi dong Bike Rental. Trinh duyet se tu mo khi mo hinh san sang.',
        flush=True,
    )
    server = subprocess.Popen(command, cwd=ROOT)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError('May chu da dung. Xem thong bao loi phia tren.')
            if website_ready(base_url, model_hash):
                open_browser(base_url)
                print(
                    'Da mo giao dien. Giu cua so nay khi su dung. Nhan Ctrl+C de dung website.',
                    flush=True,
                )
                exit_code = server.wait()
                if exit_code:
                    raise RuntimeError(f'May chu da dung voi ma loi {exit_code}.')
                return
            time.sleep(0.5)
        raise RuntimeError(
            'Mo hinh chua san sang sau 60 giay. Kiem tra file model va thu vien.'
        )
    finally:
        # Only stop a process started by this invocation, never another app.
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', help='Open RF with previous-day rentals on port 8002.')
    try:
        main(demo=parser.parse_args().demo)
    except KeyboardInterrupt:
        print('\nDa dung website.')
    except Exception as error:
        print(f'Loi: {error}', file=sys.stderr)
        sys.exit(1)
