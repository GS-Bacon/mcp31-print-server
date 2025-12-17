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

## ディレクトリ構成

```
mcp31-print-server/
├── MCP31PRINT/           # プリンタドライバライブラリ
│   ├── printer_driver.py # プリンタ制御
│   ├── image_converter.py # 画像変換
│   └── local_config.py   # ローカル設定
├── AdminWebService/      # 管理Webコンソール
│   ├── admin_server.py   # Flask APIサーバー
│   ├── database.py       # SQLite DB
│   ├── templates/        # HTMLテンプレート
│   └── static/           # CSS/JS
├── google_forms_printer/ # Google Forms連携
└── requirements.txt      # 依存パッケージ
```

## ライセンス

MIT License
