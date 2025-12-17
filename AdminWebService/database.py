# AdminWebService/database.py
"""データベース管理モジュール"""

import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'admin.db')


def get_db_connection():
    """データベース接続を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_connection():
    """コンテキストマネージャーでDB接続を管理"""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """データベースの初期化"""
    with db_connection() as conn:
        cursor = conn.cursor()

        # プリンタテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS printers (
                ip_address TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                is_default INTEGER DEFAULT 0,
                status TEXT DEFAULT 'Unknown',
                ping_ms TEXT DEFAULT 'N/A',
                last_check TEXT
            )
        ''')

        # ジョブテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'QUEUED',
                file_name TEXT,
                printer_ip TEXT,
                timestamp TEXT,
                thumbnail_path TEXT
            )
        ''')


# === プリンタ操作 ===

def get_all_printers():
    """全プリンタを取得"""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM printers ORDER BY is_default DESC, name ASC')
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_printer(ip_address: str):
    """指定IPのプリンタを取得"""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM printers WHERE ip_address = ?', (ip_address,))
        row = cursor.fetchone()
        return dict(row) if row else None


def add_printer(name: str, ip_address: str):
    """プリンタを追加"""
    with db_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO printers (ip_address, name, is_default, status, ping_ms, last_check)
            VALUES (?, ?, 0, 'Unknown', 'N/A', ?)
        ''', (ip_address, name, now))


def delete_printer(ip_address: str):
    """プリンタを削除"""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM printers WHERE ip_address = ?', (ip_address,))
        return cursor.rowcount > 0


def set_default_printer(ip_address: str):
    """デフォルトプリンタを設定"""
    with db_connection() as conn:
        cursor = conn.cursor()
        # 全てのis_defaultを0にリセット
        cursor.execute('UPDATE printers SET is_default = 0')
        # 指定したプリンタをデフォルトに
        cursor.execute('UPDATE printers SET is_default = 1 WHERE ip_address = ?', (ip_address,))
        return cursor.rowcount > 0


def update_printer_status(ip_address: str, status: str, ping_ms: str):
    """プリンタのステータスを更新"""
    with db_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            UPDATE printers
            SET status = ?, ping_ms = ?, last_check = ?
            WHERE ip_address = ?
        ''', (status, ping_ms, now, ip_address))


# === ジョブ操作 ===

def get_all_jobs():
    """全ジョブを取得"""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM jobs ORDER BY timestamp DESC')
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_pending_jobs_count():
    """待機中ジョブ数を取得"""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('QUEUED', 'PROCESSING')")
        return cursor.fetchone()[0]


def get_job(job_id: str):
    """指定IDのジョブを取得"""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def add_job(job_id: str, file_name: str, printer_ip: str, thumbnail_path: str = None):
    """ジョブを追加"""
    with db_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        cursor.execute('''
            INSERT INTO jobs (job_id, status, file_name, printer_ip, timestamp, thumbnail_path)
            VALUES (?, 'QUEUED', ?, ?, ?, ?)
        ''', (job_id, file_name, printer_ip, now, thumbnail_path))


def update_job_status(job_id: str, status: str):
    """ジョブステータスを更新"""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE jobs SET status = ? WHERE job_id = ?', (status, job_id))
        return cursor.rowcount > 0


def get_queued_jobs():
    """キュー中のジョブを取得"""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE status = 'QUEUED' ORDER BY timestamp ASC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


# 初期化
if __name__ == '__main__':
    init_db()
    print("Database initialized.")
