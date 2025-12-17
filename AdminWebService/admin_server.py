# AdminWebService/admin_server.py
"""MCP31プリンタ管理コンソール - バックエンドAPIサーバー"""

import os
import sys
import uuid
import subprocess
import threading
import queue
from datetime import datetime
from flask import Flask, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename

# プロジェクトルートをパスに追加
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from AdminWebService import database as db

app = Flask(__name__, static_folder='static', template_folder='templates')

# 設定
UPLOAD_FOLDER = os.path.join(current_dir, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ジョブキュー
job_queue = queue.Queue()


def allowed_file(filename):
    """許可されたファイル拡張子かチェック"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# === プリンタ設定 API (/admin/config) ===

@app.route('/admin/config/printers', methods=['GET'])
def get_printers():
    """登録済みプリンタリストの取得"""
    try:
        printers = db.get_all_printers()
        return jsonify(printers)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/admin/config/printers', methods=['POST'])
def add_printer():
    """新しいプリンタの登録"""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "リクエストボディが空です"}), 400

        name = data.get('name', '').strip()
        ip_address = data.get('ip_address', '').strip()

        if not name:
            return jsonify({"status": "error", "message": "プリンタ名が必要です"}), 400
        if not ip_address:
            return jsonify({"status": "error", "message": "IPアドレスが必要です"}), 400

        # 既存チェック
        if db.get_printer(ip_address):
            return jsonify({"status": "error", "message": f"IP {ip_address} は既に登録されています"}), 400

        db.add_printer(name, ip_address)
        return jsonify({"status": "success", "message": f"プリンタ '{name}' を登録しました"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/admin/config/printers/<ip>', methods=['DELETE'])
def delete_printer(ip):
    """指定したIPアドレスのプリンタを削除"""
    try:
        if db.delete_printer(ip):
            return jsonify({"status": "success", "message": f"プリンタ {ip} を削除しました"})
        else:
            return jsonify({"status": "error", "message": f"プリンタ {ip} が見つかりません"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/admin/config/default', methods=['POST'])
def set_default():
    """指定したIPアドレスのプリンタをデフォルトに設定"""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "リクエストボディが空です"}), 400

        ip_address = data.get('ip_address', '').strip()
        if not ip_address:
            return jsonify({"status": "error", "message": "IPアドレスが必要です"}), 400

        if db.set_default_printer(ip_address):
            return jsonify({"status": "success", "message": f"プリンタ {ip_address} をデフォルトに設定しました"})
        else:
            return jsonify({"status": "error", "message": f"プリンタ {ip_address} が見つかりません"}), 404

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# === プリンタアクション API (/admin/action) ===

def ping_host(ip_address: str) -> tuple:
    """
    ホストにPingを実行
    Returns: (success: bool, ping_ms: str)
    """
    try:
        # Windows用pingコマンド
        if sys.platform == 'win32':
            result = subprocess.run(
                ['ping', '-n', '1', '-w', '3000', ip_address],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # 応答時間を抽出 (例: "時間=XXms" or "time=XXms")
                output = result.stdout
                import re
                match = re.search(r'[時間|time][=<](\d+)ms', output)
                if match:
                    return True, match.group(1)
                return True, "1"
            return False, "N/A"
        else:
            # Linux/Mac用
            result = subprocess.run(
                ['ping', '-c', '1', '-W', '3', ip_address],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                import re
                match = re.search(r'time=(\d+\.?\d*)', result.stdout)
                if match:
                    return True, str(int(float(match.group(1))))
                return True, "1"
            return False, "N/A"

    except subprocess.TimeoutExpired:
        return False, "N/A"
    except Exception:
        return False, "N/A"


@app.route('/admin/action/ping', methods=['POST'])
def ping_printer():
    """単一プリンタの疎通チェックを実行"""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "リクエストボディが空です"}), 400

        ip_address = data.get('ip_address', '').strip()
        if not ip_address:
            return jsonify({"status": "error", "message": "IPアドレスが必要です"}), 400

        success, ping_ms = ping_host(ip_address)
        status = "OK" if success else "Failure"

        # DBを更新
        db.update_printer_status(ip_address, status, ping_ms)

        return jsonify({
            "status": "success" if success else "error",
            "ping_ms": int(ping_ms) if ping_ms != "N/A" else ping_ms,
            "message": f"Ping {'成功' if success else '失敗'}: {ip_address}"
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/admin/action/ping_all', methods=['POST'])
def ping_all_printers():
    """全プリンタの疎通チェックを非同期で実行"""
    try:
        printers = db.get_all_printers()
        if not printers:
            return jsonify({"status": "success", "message": "登録されたプリンタがありません"})

        def ping_all_async():
            for printer in printers:
                ip = printer['ip_address']
                success, ping_ms = ping_host(ip)
                status = "OK" if success else "Failure"
                db.update_printer_status(ip, status, ping_ms)

        thread = threading.Thread(target=ping_all_async)
        thread.start()

        return jsonify({
            "status": "success",
            "message": f"{len(printers)}台のプリンタに対してPing実行を開始しました"
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/admin/action/testprint', methods=['POST'])
def test_print():
    """テスト印刷ジョブのキュー登録"""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "リクエストボディが空です"}), 400

        ip_address = data.get('ip_address', '').strip()
        file_name = data.get('file_name', '').strip()

        if not ip_address:
            return jsonify({"status": "error", "message": "IPアドレスが必要です"}), 400
        if not file_name:
            return jsonify({"status": "error", "message": "ファイル名が必要です"}), 400

        # ファイル存在チェック
        file_path = os.path.join(UPLOAD_FOLDER, file_name)
        if not os.path.exists(file_path):
            return jsonify({"status": "error", "message": f"ファイル '{file_name}' が見つかりません"}), 404

        # ジョブ作成
        job_id = str(uuid.uuid4())
        thumbnail_path = file_path  # サムネイルは元ファイルを使用

        db.add_job(job_id, file_name, ip_address, thumbnail_path)

        # ジョブをキューに追加
        job_queue.put({
            "job_id": job_id,
            "file_path": file_path,
            "printer_ip": ip_address
        })

        return jsonify({
            "status": "success",
            "job_id": job_id,
            "message": f"印刷ジョブをキューに追加しました"
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/admin/action/upload_test_image', methods=['POST'])
def upload_test_image():
    """PNGテスト画像のアップロード"""
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "ファイルが選択されていません"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "ファイル名が空です"}), 400

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # 同名ファイルがある場合はタイムスタンプを付与
            base, ext = os.path.splitext(filename)
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.exists(save_path):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{base}_{timestamp}{ext}"
                save_path = os.path.join(UPLOAD_FOLDER, filename)

            file.save(save_path)
            return jsonify({
                "status": "success",
                "message": f"ファイル '{filename}' をアップロードしました"
            })
        else:
            return jsonify({
                "status": "error",
                "message": f"許可されていないファイル形式です。許可: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/admin/action/delete_job', methods=['POST'])
def delete_job():
    """ジョブの削除/キャンセル処理"""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "リクエストボディが空です"}), 400

        job_id = data.get('job_id', '').strip()
        if not job_id:
            return jsonify({"status": "error", "message": "ジョブIDが必要です"}), 400

        job = db.get_job(job_id)
        if not job:
            return jsonify({"status": "error", "message": f"ジョブ {job_id} が見つかりません"}), 404

        # ステータスに応じて更新
        if job['status'] in ('QUEUED', 'PROCESSING'):
            db.update_job_status(job_id, 'DELETED')
            message = "ジョブをキャンセルしました"
        else:
            db.update_job_status(job_id, 'DELETED')
            message = "ジョブを削除済みに設定しました"

        return jsonify({"status": "success", "message": message})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/admin/action/retry_job', methods=['POST'])
def retry_job():
    """失敗したジョブの再実行"""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "リクエストボディが空です"}), 400

        job_id = data.get('job_id', '').strip()
        if not job_id:
            return jsonify({"status": "error", "message": "ジョブIDが必要です"}), 400

        job = db.get_job(job_id)
        if not job:
            return jsonify({"status": "error", "message": f"ジョブ {job_id} が見つかりません"}), 404

        if job['status'] != 'FAILED':
            return jsonify({"status": "error", "message": "FAILEDステータスのジョブのみ再実行できます"}), 400

        # ファイル存在チェック
        file_path = os.path.join(UPLOAD_FOLDER, job['file_name'])
        if not os.path.exists(file_path):
            return jsonify({"status": "error", "message": f"ファイル '{job['file_name']}' が見つかりません"}), 404

        # ステータスをQUEUEDに戻す
        db.update_job_status(job_id, 'QUEUED')

        # ジョブをキューに再追加
        job_queue.put({
            "job_id": job_id,
            "file_path": file_path,
            "printer_ip": job['printer_ip']
        })

        return jsonify({
            "status": "success",
            "message": "ジョブを再実行キューに追加しました"
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# === データ取得 API (/admin/data) ===

@app.route('/admin/data/test_files', methods=['GET'])
def get_test_files():
    """アップロード済みテストファイル名リストを取得"""
    try:
        files = []
        if os.path.exists(UPLOAD_FOLDER):
            for f in os.listdir(UPLOAD_FOLDER):
                if allowed_file(f):
                    files.append(f)
        files.sort()
        return jsonify(files)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/admin/data/queue', methods=['GET'])
def get_queue():
    """全ジョブのキュー/ログ履歴を取得"""
    try:
        jobs = db.get_all_jobs()
        pending_count = db.get_pending_jobs_count()
        return jsonify({
            "jobs": jobs,
            "pending_count": pending_count
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/admin/data/thumbnail', methods=['GET'])
def get_thumbnail():
    """印刷ジョブのサムネイル画像を取得"""
    try:
        job_id = request.args.get('job_id', '').strip()
        if not job_id:
            return jsonify({"status": "error", "message": "job_idが必要です"}), 400

        job = db.get_job(job_id)
        if not job:
            return jsonify({"status": "error", "message": "ジョブが見つかりません"}), 404

        thumbnail_path = job.get('thumbnail_path')
        if thumbnail_path and os.path.exists(thumbnail_path):
            return send_file(thumbnail_path, mimetype='image/png')
        else:
            # 代替の透明SVG
            svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
                <rect width="100" height="100" fill="#f0f0f0"/>
                <text x="50" y="55" text-anchor="middle" fill="#999" font-size="12">No Image</text>
            </svg>'''
            return svg, 200, {'Content-Type': 'image/svg+xml'}

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# === 静的ファイル & フロントエンド ===

@app.route('/')
def index():
    """管理画面トップページ"""
    return send_from_directory('templates', 'index.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    """静的ファイル配信"""
    return send_from_directory('static', filename)


# === ジョブワーカー ===

def job_worker():
    """バックグラウンドでジョブを処理するワーカー"""
    while True:
        try:
            job_data = job_queue.get(timeout=1)
        except queue.Empty:
            continue

        job_id = job_data['job_id']
        file_path = job_data['file_path']
        printer_ip = job_data['printer_ip']

        # ジョブが削除されていないか確認
        job = db.get_job(job_id)
        if not job or job['status'] == 'DELETED':
            job_queue.task_done()
            continue

        # 処理中に更新
        db.update_job_status(job_id, 'PROCESSING')

        try:
            # プリンタドライバを使って印刷
            from MCP31PRINT.printer_driver import PrinterDriver
            from MCP31PRINT.image_converter import ImageConverter

            # IPアドレスを指定してドライバを初期化
            driver = PrinterDriver(printer_ip=printer_ip)
            print(f"Job {job_id}: Printing to {printer_ip}")

            # 画像を読み込んで印刷
            from PIL import Image
            img = Image.open(file_path)

            converter = ImageConverter(default_width=driver.paper_width_dots)
            # 画像をそのまま印刷
            driver.print_image(img)
            driver.print_empty_lines(3)
            driver.cut_paper()

            db.update_job_status(job_id, 'SUCCESS')
            print(f"Job {job_id} completed successfully")

        except Exception as e:
            db.update_job_status(job_id, 'FAILED')
            print(f"Job {job_id} failed: {e}")
            import traceback
            traceback.print_exc()

        finally:
            job_queue.task_done()


def start_worker():
    """ワーカースレッドを起動"""
    worker_thread = threading.Thread(target=job_worker, daemon=True)
    worker_thread.start()
    print("Job worker started")


# === メイン ===

if __name__ == '__main__':
    # DB初期化
    db.init_db()
    print("Database initialized")

    # ワーカー起動
    start_worker()

    # サーバー起動（debugモード無効でワーカーが正しく動作する）
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
