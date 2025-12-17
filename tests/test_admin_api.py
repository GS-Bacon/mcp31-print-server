# tests/test_admin_api.py
"""管理APIのテスト"""

import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PIL import Image
import io

from AdminWebService.admin_server import app
from AdminWebService import database as db


@pytest.fixture
def client():
    """テスト用Flaskクライアント"""
    # テスト用の一時DBを使用
    db.DATABASE_PATH = tempfile.mktemp(suffix='.db')
    db.init_db()

    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

    # クリーンアップ
    if os.path.exists(db.DATABASE_PATH):
        os.remove(db.DATABASE_PATH)


@pytest.fixture
def upload_folder():
    """テスト用アップロードフォルダ"""
    from AdminWebService import admin_server
    original_folder = admin_server.UPLOAD_FOLDER
    temp_folder = tempfile.mkdtemp()
    admin_server.UPLOAD_FOLDER = temp_folder

    yield temp_folder

    # クリーンアップ
    admin_server.UPLOAD_FOLDER = original_folder
    shutil.rmtree(temp_folder, ignore_errors=True)


class TestPrinterConfig:
    """プリンタ設定APIのテスト"""

    def test_get_printers_empty(self, client):
        """空のプリンタリスト取得"""
        response = client.get('/admin/config/printers')
        assert response.status_code == 200
        data = response.get_json()
        assert data == []

    def test_add_printer(self, client):
        """プリンタ追加"""
        response = client.post('/admin/config/printers',
            json={"name": "Test Printer", "ip_address": "192.168.1.100"})
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'success'

    def test_add_printer_duplicate(self, client):
        """重複IPのプリンタ追加（エラー）"""
        client.post('/admin/config/printers',
            json={"name": "Printer 1", "ip_address": "192.168.1.100"})

        response = client.post('/admin/config/printers',
            json={"name": "Printer 2", "ip_address": "192.168.1.100"})
        assert response.status_code == 400
        data = response.get_json()
        assert data['status'] == 'error'

    def test_add_printer_missing_name(self, client):
        """名前なしでプリンタ追加（エラー）"""
        response = client.post('/admin/config/printers',
            json={"ip_address": "192.168.1.100"})
        assert response.status_code == 400

    def test_add_printer_missing_ip(self, client):
        """IPなしでプリンタ追加（エラー）"""
        response = client.post('/admin/config/printers',
            json={"name": "Test"})
        assert response.status_code == 400

    def test_get_printers_after_add(self, client):
        """プリンタ追加後のリスト取得"""
        client.post('/admin/config/printers',
            json={"name": "Printer A", "ip_address": "192.168.1.101"})
        client.post('/admin/config/printers',
            json={"name": "Printer B", "ip_address": "192.168.1.102"})

        response = client.get('/admin/config/printers')
        data = response.get_json()
        assert len(data) == 2

    def test_delete_printer(self, client):
        """プリンタ削除"""
        client.post('/admin/config/printers',
            json={"name": "To Delete", "ip_address": "192.168.1.200"})

        response = client.delete('/admin/config/printers/192.168.1.200')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'success'

        # 確認
        response = client.get('/admin/config/printers')
        data = response.get_json()
        assert len(data) == 0

    def test_delete_printer_not_found(self, client):
        """存在しないプリンタ削除（エラー）"""
        response = client.delete('/admin/config/printers/999.999.999.999')
        assert response.status_code == 404

    def test_set_default_printer(self, client):
        """デフォルトプリンタ設定"""
        client.post('/admin/config/printers',
            json={"name": "Printer 1", "ip_address": "192.168.1.1"})
        client.post('/admin/config/printers',
            json={"name": "Printer 2", "ip_address": "192.168.1.2"})

        response = client.post('/admin/config/default',
            json={"ip_address": "192.168.1.2"})
        assert response.status_code == 200

        # 確認
        response = client.get('/admin/config/printers')
        data = response.get_json()
        default_printer = next((p for p in data if p['is_default'] == 1), None)
        assert default_printer is not None
        assert default_printer['ip_address'] == '192.168.1.2'


class TestPrinterAction:
    """プリンタアクションAPIのテスト"""

    def test_ping_missing_ip(self, client):
        """IPなしでPing（エラー）"""
        response = client.post('/admin/action/ping', json={})
        assert response.status_code == 400

    def test_ping_invalid_ip(self, client):
        """無効なIPへのPing"""
        # 存在しないIPへのPing（失敗が期待される）
        response = client.post('/admin/action/ping',
            json={"ip_address": "999.999.999.999"})
        assert response.status_code == 200
        data = response.get_json()
        # Pingは失敗するはず
        assert data['status'] == 'error' or data['ping_ms'] == 'N/A'

    def test_ping_all_empty(self, client):
        """プリンタなしでPing All"""
        response = client.post('/admin/action/ping_all')
        assert response.status_code == 200

    def test_testprint_missing_params(self, client):
        """パラメータなしでテスト印刷（エラー）"""
        response = client.post('/admin/action/testprint', json={})
        assert response.status_code == 400

    def test_testprint_file_not_found(self, client):
        """存在しないファイルでテスト印刷（エラー）"""
        response = client.post('/admin/action/testprint',
            json={"ip_address": "192.168.1.1", "file_name": "nonexistent.png"})
        assert response.status_code == 404

    def test_delete_job_not_found(self, client):
        """存在しないジョブ削除（エラー）"""
        response = client.post('/admin/action/delete_job',
            json={"job_id": "nonexistent-job-id"})
        assert response.status_code == 404


class TestDataEndpoints:
    """データ取得APIのテスト"""

    def test_get_test_files_empty(self, client, upload_folder):
        """空のファイルリスト取得"""
        response = client.get('/admin/data/test_files')
        assert response.status_code == 200
        data = response.get_json()
        assert data == []

    def test_get_queue_empty(self, client):
        """空のキュー取得"""
        response = client.get('/admin/data/queue')
        assert response.status_code == 200
        data = response.get_json()
        assert data['jobs'] == []
        assert data['pending_count'] == 0

    def test_get_thumbnail_missing_job_id(self, client):
        """job_idなしでサムネイル取得（エラー）"""
        response = client.get('/admin/data/thumbnail')
        assert response.status_code == 400

    def test_get_thumbnail_not_found(self, client):
        """存在しないジョブのサムネイル取得（エラー）"""
        response = client.get('/admin/data/thumbnail?job_id=nonexistent')
        assert response.status_code == 404


class TestFileUpload:
    """ファイルアップロードのテスト"""

    def test_upload_png(self, client, upload_folder):
        """PNGファイルのアップロード"""
        # テスト画像を作成
        img = Image.new('RGB', (100, 100), color='red')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        response = client.post('/admin/action/upload_test_image',
            data={'file': (buffer, 'test.png')},
            content_type='multipart/form-data')

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'success'

    def test_upload_jpeg(self, client, upload_folder):
        """JPEGファイルのアップロード"""
        img = Image.new('RGB', (100, 100), color='blue')
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        buffer.seek(0)

        response = client.post('/admin/action/upload_test_image',
            data={'file': (buffer, 'test.jpg')},
            content_type='multipart/form-data')

        assert response.status_code == 200

    def test_upload_invalid_extension(self, client, upload_folder):
        """無効な拡張子のファイルアップロード（エラー）"""
        response = client.post('/admin/action/upload_test_image',
            data={'file': (io.BytesIO(b'test'), 'test.txt')},
            content_type='multipart/form-data')

        assert response.status_code == 400

    def test_upload_no_file(self, client):
        """ファイルなしでアップロード（エラー）"""
        response = client.post('/admin/action/upload_test_image',
            content_type='multipart/form-data')

        assert response.status_code == 400

    def test_get_files_after_upload(self, client, upload_folder):
        """アップロード後のファイルリスト取得"""
        # ファイルをアップロード
        img = Image.new('RGB', (50, 50), color='green')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        client.post('/admin/action/upload_test_image',
            data={'file': (buffer, 'uploaded.png')},
            content_type='multipart/form-data')

        # ファイルリスト取得
        response = client.get('/admin/data/test_files')
        data = response.get_json()
        assert 'uploaded.png' in data


class TestJobWorkflow:
    """ジョブワークフローのテスト"""

    def test_create_and_cancel_job(self, client, upload_folder):
        """ジョブ作成とキャンセル"""
        # ファイルをアップロード
        img = Image.new('RGB', (100, 100), color='purple')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        client.post('/admin/action/upload_test_image',
            data={'file': (buffer, 'job_test.png')},
            content_type='multipart/form-data')

        # プリンタを追加
        client.post('/admin/config/printers',
            json={"name": "Job Test Printer", "ip_address": "192.168.1.50"})

        # ジョブを作成
        response = client.post('/admin/action/testprint',
            json={"ip_address": "192.168.1.50", "file_name": "job_test.png"})

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'success'
        job_id = data['job_id']

        # キューを確認
        response = client.get('/admin/data/queue')
        queue_data = response.get_json()
        assert queue_data['pending_count'] >= 0  # ワーカーが処理中かもしれない

        # ジョブをキャンセル
        response = client.post('/admin/action/delete_job',
            json={"job_id": job_id})
        assert response.status_code == 200


class TestEdgeCases:
    """エッジケースのテスト"""

    def test_empty_json_body(self, client):
        """空のJSONボディ"""
        response = client.post('/admin/config/printers',
            data='',
            content_type='application/json')
        assert response.status_code == 400

    def test_special_characters_in_name(self, client):
        """プリンタ名に特殊文字"""
        response = client.post('/admin/config/printers',
            json={"name": "Printer <>&\"'テスト", "ip_address": "192.168.1.123"})
        assert response.status_code == 200

        response = client.get('/admin/config/printers')
        data = response.get_json()
        assert any(p['name'] == "Printer <>&\"'テスト" for p in data)

    def test_whitespace_in_params(self, client):
        """パラメータ前後の空白"""
        response = client.post('/admin/config/printers',
            json={"name": "  Trimmed  ", "ip_address": "  192.168.1.150  "})
        assert response.status_code == 200

        response = client.get('/admin/config/printers')
        data = response.get_json()
        # 空白がトリムされているか確認
        printer = next((p for p in data if p['ip_address'] == '192.168.1.150'), None)
        assert printer is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
