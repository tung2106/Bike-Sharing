"""Open the local website with one double-click, reusing an existing server."""
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

BASE_URL = 'http://127.0.0.1:8000'
ROOT = Path(__file__).resolve().parent
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def website_ready():
    try:
        with HTTP.open(BASE_URL + '/api/model', timeout=2) as response:
            info = json.load(response)
        return (info.get('ready') is True and info.get('dataset') == 'hour'
                and info.get('model_sha256') == hashlib.sha256(
                    Path(os.environ.get('BIKE_MODEL_PATH', ROOT / 'models/model.joblib')).read_bytes()).hexdigest())
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def port_in_use():
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(('127.0.0.1', 8000)) == 0


def open_browser():
    if not webbrowser.open(BASE_URL, new=2):
        raise RuntimeError('Khong mo duoc trinh duyet mac dinh. Hay kiem tra cai dat trinh duyet tren Windows.')


def main():
    if website_ready():
        print('Website da chay. Dang mo giao dien...', flush=True)
        open_browser()
        return
    if port_in_use():
        raise RuntimeError('Cong 8000 dang duoc su dung nhung mo hinh Bike Rental chua san sang. '
                           'Kiem tra cua so may chu dang chay; khong khoi dong them mot ban.')
    print('Dang khoi dong Bike Rental. Trinh duyet se tu mo khi mo hinh san sang.', flush=True)
    server = subprocess.Popen([sys.executable, '-B', str(ROOT / 'app.py')], cwd=ROOT)
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


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nDa dung website.')
    except Exception as error:
        print(f'Loi: {error}', file=sys.stderr)
        sys.exit(1)
