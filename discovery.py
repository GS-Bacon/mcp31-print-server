# discovery.py
"""
MCP31プリントサーバー自動発見ユーティリティ

ローカルネットワーク内のMCP31プリントサーバーをmDNS経由で自動発見します。

使用例:
    from discovery import discover_print_server, discover_print_servers

    # 最初に見つかったサーバーを取得
    server = discover_print_server()
    if server:
        print(f"Found: {server['ip']}:{server['port']}")

    # 全てのサーバーを取得
    servers = discover_print_servers(timeout=5)
    for s in servers:
        print(f"Server: {s['name']} at {s['ip']}:{s['port']}")
"""

import socket
import time
from typing import Optional

try:
    from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False

SERVICE_TYPE = "_mcp31print._tcp.local."


class PrintServerListener(ServiceListener):
    """mDNSサービス発見用リスナー"""

    def __init__(self):
        self.servers = []

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            addresses = info.parsed_addresses()
            if addresses:
                server_info = {
                    "name": name.replace(f".{SERVICE_TYPE}", ""),
                    "ip": addresses[0],
                    "port": info.port,
                    "properties": {
                        k.decode() if isinstance(k, bytes) else k:
                        v.decode() if isinstance(v, bytes) else v
                        for k, v in info.properties.items()
                    },
                    "hostname": info.server
                }
                self.servers.append(server_info)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass


def discover_print_servers(timeout: float = 3.0) -> list:
    """
    ローカルネットワーク内の全MCP31プリントサーバーを発見

    Args:
        timeout: 検索タイムアウト（秒）

    Returns:
        見つかったサーバーのリスト
        [{"name": str, "ip": str, "port": int, "properties": dict, "hostname": str}, ...]
    """
    if not ZEROCONF_AVAILABLE:
        raise ImportError(
            "zeroconf is not installed. Install with: pip install zeroconf"
        )

    zeroconf = Zeroconf()
    listener = PrintServerListener()

    try:
        browser = ServiceBrowser(zeroconf, SERVICE_TYPE, listener)
        time.sleep(timeout)
        return listener.servers
    finally:
        zeroconf.close()


def discover_print_server(timeout: float = 3.0) -> Optional[dict]:
    """
    ローカルネットワーク内の最初に見つかったMCP31プリントサーバーを返す

    Args:
        timeout: 検索タイムアウト（秒）

    Returns:
        サーバー情報 {"name": str, "ip": str, "port": int, ...} または None
    """
    servers = discover_print_servers(timeout)
    return servers[0] if servers else None


def get_print_server_url(timeout: float = 3.0) -> Optional[str]:
    """
    プリントサーバーのベースURLを取得

    Args:
        timeout: 検索タイムアウト（秒）

    Returns:
        サーバーURL (例: "http://192.168.1.100:5000") または None
    """
    server = discover_print_server(timeout)
    if server:
        return f"http://{server['ip']}:{server['port']}"
    return None


def get_printers_api_url(timeout: float = 3.0) -> Optional[str]:
    """
    プリンター一覧APIのURLを取得

    Args:
        timeout: 検索タイムアウト（秒）

    Returns:
        API URL (例: "http://192.168.1.100:5000/api/printers") または None
    """
    server = discover_print_server(timeout)
    if server:
        path = server.get("properties", {}).get("path", "/api/printers")
        return f"http://{server['ip']}:{server['port']}{path}"
    return None


# === CLI ===

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="MCP31プリントサーバーをローカルネットワークから自動発見"
    )
    parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=3.0,
        help="検索タイムアウト秒数 (デフォルト: 3.0)"
    )
    parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="全てのサーバーを表示"
    )
    parser.add_argument(
        "-j", "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    print(f"MCP31プリントサーバーを検索中... (タイムアウト: {args.timeout}秒)")

    try:
        servers = discover_print_servers(timeout=args.timeout)

        if not servers:
            print("サーバーが見つかりませんでした")
            exit(1)

        if args.json:
            import json
            if args.all:
                print(json.dumps(servers, indent=2, ensure_ascii=False))
            else:
                print(json.dumps(servers[0], indent=2, ensure_ascii=False))
        else:
            display_servers = servers if args.all else [servers[0]]
            for i, server in enumerate(display_servers):
                if i > 0:
                    print("-" * 40)
                print(f"サーバー名: {server['name']}")
                print(f"IPアドレス: {server['ip']}")
                print(f"ポート: {server['port']}")
                print(f"ホスト名: {server['hostname']}")
                print(f"API URL: http://{server['ip']}:{server['port']}/api/printers")
                if server.get('properties'):
                    print(f"プロパティ: {server['properties']}")

    except ImportError as e:
        print(f"エラー: {e}")
        exit(1)
