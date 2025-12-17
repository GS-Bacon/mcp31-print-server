# mcp31-print-server

Star MCP31レシートプリンタ向けの印刷サーバーシステムです。Raspberry Pi等で動作し、ネットワーク経由でプリンタを制御できます。

## 機能

- **プリンタドライバ (MCP31PRINT)**: Star MCP31プリンタのESC/POSコマンド制御
  - 画像印刷（自動リサイズ、ディザリング処理）
  - テキスト印刷
  - 用紙カット
- **管理Webコンソール (AdminWebService)**: ブラウザからプリンタを管理
  - プリンタの登録・削除
  - 疎通確認 (Ping)
  - テスト印刷
  - ジョブキュー管理
- **サービスディスカバリ (mDNS/Zeroconf)**: ローカルネットワーク内でサーバーを自動発見
  - 他のサービスからIPアドレス指定不要でサーバーに接続可能
- **Google Forms連携 (google_forms_printer)**: フォーム回答を自動印刷

## 必要環境

- Python 3.11以上
- Star MCP31プリンタ（ネットワーク接続）
- Raspberry Pi / Linux

## セットアップ

```bash
# リポジトリをクローン
git clone <repository-url>
cd mcp31-print-server

# 仮想環境を作成
python -m venv .venv
source .venv/bin/activate

# 依存関係をインストール
pip install -r requirements.txt
```

## プリンタ設定

`MCP31PRINT/local_config.py` を作成して設定:

```python
class LocalPrinterConfig:
    PRINTER_IP = "192.168.1.100"  # プリンタのIPアドレス
    PRINTER_PORT = 9100
    PAPER_WIDTH_DOTS = 576  # 用紙幅 (80mm = 576dots)
```

## 使い方

### 管理コンソールの起動

```bash
python AdminWebService/admin_server.py
```

ブラウザで `http://<サーバーIP>:5000` にアクセス

### Pythonからの利用

```python
from MCP31PRINT.printer_driver import PrinterDriver

driver = PrinterDriver(printer_ip="192.168.1.100")

# 画像を印刷
driver.print_image("image.png")
driver.print_empty_lines(3)
driver.cut_paper()
```

## API仕様

### 外部公開API - ポート5000

外部から接続可能なプリンタ情報を取得できます。

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| GET | `/api/printers` | 登録済みプリンタ一覧を取得 |
| GET | `/api/printers/<ip>` | 指定IPのプリンタ情報を取得 |

#### レスポンス例

```bash
# プリンタ一覧取得
curl http://localhost:5000/api/printers
```

```json
[
  {
    "name": "Reception",
    "ip_address": "192.168.1.100",
    "paper_width_dots": 576,
    "status": "OK",
    "is_default": true
  },
  {
    "name": "Kitchen",
    "ip_address": "192.168.1.101",
    "paper_width_dots": 384,
    "status": "OK",
    "is_default": false
  }
]
```

### 管理API (AdminWebService) - ポート5000

#### プリンタ設定

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| GET | `/admin/config/printers` | 登録済みプリンタ一覧を取得 |
| POST | `/admin/config/printers` | プリンタを登録 |
| PUT | `/admin/config/printers/<ip>` | プリンタ情報を更新 |
| DELETE | `/admin/config/printers/<ip>` | プリンタを削除 |
| POST | `/admin/config/default` | デフォルトプリンタを設定 |

#### アクション

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| POST | `/admin/action/ping` | 単一プリンタの疎通確認 |
| POST | `/admin/action/ping_all` | 全プリンタの疎通確認 |
| POST | `/admin/action/testprint` | テスト印刷ジョブを登録 |
| POST | `/admin/action/upload_test_image` | テスト画像をアップロード |
| POST | `/admin/action/delete_job` | ジョブを削除 |
| POST | `/admin/action/retry_job` | 失敗ジョブを再実行 |

#### データ取得

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| GET | `/admin/data/test_files` | アップロード済み画像一覧 |
| GET | `/admin/data/queue` | ジョブキュー・履歴を取得 |
| GET | `/admin/data/thumbnail?job_id=<id>` | ジョブのサムネイル画像 |

#### リクエスト例

```bash
# プリンタ登録 (paper_width_dotsはオプション、デフォルト576)
curl -X POST http://localhost:5000/admin/config/printers \
  -H "Content-Type: application/json" \
  -d '{"name": "Reception", "ip_address": "192.168.1.100", "paper_width_dots": 576}'

# プリンタ情報更新
curl -X PUT http://localhost:5000/admin/config/printers/192.168.1.100 \
  -H "Content-Type: application/json" \
  -d '{"name": "Front Desk", "paper_width_dots": 384}'

# 画像アップロード
curl -X POST http://localhost:5000/admin/action/upload_test_image \
  -F "file=@test.png"

# テスト印刷
curl -X POST http://localhost:5000/admin/action/testprint \
  -H "Content-Type: application/json" \
  -d '{"ip_address": "192.168.1.100", "file_name": "test.png"}'
```

### Socket API (WebService)

ヘッダー・本文・フッターを含む印刷データをSocket経由で送信できます。

```python
from WebService.client.client import FileSenderClient

client = FileSenderClient()
client.send_data(
    header_data={"type": "text", "content": "タイトル"},
    body_text_message="本文テキスト",
    body_image_bytes_list=[image_bytes],  # バイト列のリスト
    footer_data={"type": "text", "content": "フッター"}
)
```

設定ファイル `WebService/client/MyActualServerConfig.py` でサーバーIP/ポートを指定。

## サービスディスカバリ (mDNS)

サーバー起動時に自動的にmDNS (Zeroconf/Bonjour) でサービスをアドバタイズします。
ローカルネットワーク内の他のサービスは、IPアドレスを事前に知らなくてもサーバーを発見できます。

### サーバー側

管理コンソール起動時に自動でmDNSサービスが登録されます:

```
$ python AdminWebService/admin_server.py
Database initialized
Job worker started
mDNS service registered: MCP31 Print Server._mcp31print._tcp.local.
  - IP: 192.168.1.50
  - Port: 5000
  - Service Type: _mcp31print._tcp.local.
```

### クライアント側 (CLIツール)

```bash
# サーバーを検索
python discovery.py

# 全サーバーを表示
python discovery.py --all

# JSON形式で出力
python discovery.py --json

# タイムアウト指定 (秒)
python discovery.py --timeout 5
```

### クライアント側 (Pythonから利用)

```python
from discovery import discover_print_server, get_printers_api_url
import requests

# サーバーを自動発見
server = discover_print_server()
if server:
    print(f"Found server: {server['ip']}:{server['port']}")

# API URLを取得してプリンタ一覧を取得
api_url = get_printers_api_url()
if api_url:
    response = requests.get(api_url)
    printers = response.json()
    for p in printers:
        print(f"Printer: {p['name']} ({p['ip_address']}) - {p['paper_width_dots']} dots")
```

### 発見できる情報

| プロパティ | 説明 |
|-----------|------|
| `ip` | サーバーのIPアドレス |
| `port` | サーバーのポート番号 |
| `hostname` | サーバーのホスト名 |
| `properties.path` | プリンターAPI パス (`/api/printers`) |
| `properties.version` | APIバージョン |

## ディレクトリ構成

```
mcp31-print-server/
├── MCP31PRINT/           # プリンタドライバライブラリ
│   ├── printer_driver.py # プリンタ制御
│   ├── image_converter.py # 画像変換
│   └── local_config.py   # ローカル設定
├── AdminWebService/      # 管理Webコンソール
│   ├── admin_server.py   # Flask APIサーバー (mDNS対応)
│   ├── database.py       # SQLite DB
│   ├── templates/        # HTMLテンプレート
│   └── static/           # CSS/JS
├── google_forms_printer/ # Google Forms連携
├── discovery.py          # サーバー自動発見ユーティリティ
└── requirements.txt      # 依存パッケージ
```

## ライセンス

MIT License
