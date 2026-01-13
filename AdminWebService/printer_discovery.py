"""
LAN内プリンタ自動検出モジュール

1. mDNS/Bonjourで素早く検出
2. 見つからなければポート9100スキャンにフォールバック
"""

import socket
import threading
import ipaddress
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

try:
    from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False

# プリンタ関連のmDNSサービスタイプ
PRINTER_SERVICE_TYPES = [
    "_pdl-datastream._tcp.local.",  # RAW印刷 (ポート9100)
    "_ipp._tcp.local.",              # IPP (Internet Printing Protocol)
    "_printer._tcp.local.",          # 一般的なプリンタ
]

DEFAULT_PRINTER_PORT = 9100
PORT_SCAN_TIMEOUT = 0.5  # 秒


class PrinterDiscoveryListener(ServiceListener):
    """mDNSプリンタ検出用リスナー"""

    def __init__(self):
        self.printers: List[Dict] = []
        self._lock = threading.Lock()

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            addresses = info.parsed_addresses()
            if addresses:
                with self._lock:
                    printer_info = {
                        "name": self._clean_name(name, type_),
                        "ip_address": addresses[0],
                        "port": info.port,
                        "service_type": type_,
                        "discovery_method": "mdns",
                        "hostname": info.server if info.server else ""
                    }
                    # 重複チェック（同じIPは追加しない）
                    if not any(p["ip_address"] == addresses[0] for p in self.printers):
                        self.printers.append(printer_info)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def _clean_name(self, name: str, type_: str) -> str:
        """サービス名からタイプ部分を除去してクリーンな名前を返す"""
        clean = name.replace(f".{type_}", "")
        # 末尾の._tcp.local.も除去
        for suffix in ["._pdl-datastream._tcp.local.", "._ipp._tcp.local.", "._printer._tcp.local."]:
            clean = clean.replace(suffix, "")
        return clean


def get_local_ip() -> Optional[str]:
    """ローカルIPアドレスを取得"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def get_local_network_range() -> Optional[str]:
    """ローカルネットワークのCIDR範囲を取得（/24を仮定）"""
    local_ip = get_local_ip()
    if not local_ip:
        return None
    try:
        network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
        return str(network)
    except Exception:
        return None


def check_port_9100(ip: str, timeout: float = PORT_SCAN_TIMEOUT) -> bool:
    """指定IPのポート9100が開いているか確認"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, DEFAULT_PRINTER_PORT))
        sock.close()
        return result == 0
    except Exception:
        return False


def discover_printers_mdns(timeout: float = 3.0) -> List[Dict]:
    """mDNSでプリンタを検出"""
    if not ZEROCONF_AVAILABLE:
        return []

    zeroconf = None
    try:
        zeroconf = Zeroconf()
        listener = PrinterDiscoveryListener()
        browsers = []

        for service_type in PRINTER_SERVICE_TYPES:
            try:
                browser = ServiceBrowser(zeroconf, service_type, listener)
                browsers.append(browser)
            except Exception:
                pass

        # タイムアウトまで待機
        time.sleep(timeout)
        return listener.printers
    except Exception:
        return []
    finally:
        if zeroconf:
            try:
                zeroconf.close()
            except Exception:
                pass


def discover_printers_port_scan(
    timeout_per_host: float = PORT_SCAN_TIMEOUT,
    max_workers: int = 50,
    progress_callback=None
) -> List[Dict]:
    """ポート9100スキャンでプリンタを検出"""
    network_range = get_local_network_range()
    if not network_range:
        return []

    printers = []
    network = ipaddress.IPv4Network(network_range)
    hosts = list(network.hosts())
    total_hosts = len(hosts)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ip = {
            executor.submit(check_port_9100, str(ip), timeout_per_host): str(ip)
            for ip in hosts
        }

        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            completed += 1

            if progress_callback:
                progress_callback(completed, total_hosts)

            try:
                if future.result():
                    printers.append({
                        "name": f"Printer ({ip})",
                        "ip_address": ip,
                        "port": DEFAULT_PRINTER_PORT,
                        "service_type": "raw",
                        "discovery_method": "port_scan"
                    })
            except Exception:
                pass

    return printers


def discover_printers(
    mdns_timeout: float = 3.0,
    fallback_to_scan: bool = True,
    progress_callback=None
) -> Dict:
    """
    プリンタ検出のメインエントリポイント

    1. まずmDNSで検出
    2. 見つからなければポートスキャンにフォールバック

    Args:
        mdns_timeout: mDNS検出のタイムアウト（秒）
        fallback_to_scan: mDNSで見つからない場合にポートスキャンを実行
        progress_callback: 進捗コールバック関数 (current, total) -> None

    Returns:
        {
            "printers": [...],
            "method_used": "mdns" | "port_scan" | None,
            "mdns_available": bool
        }
    """
    result = {
        "printers": [],
        "method_used": None,
        "mdns_available": ZEROCONF_AVAILABLE
    }

    # Phase 1: mDNS検出
    if progress_callback:
        progress_callback(10, 100)

    mdns_printers = discover_printers_mdns(timeout=mdns_timeout)

    if progress_callback:
        progress_callback(40, 100)

    if mdns_printers:
        result["printers"] = mdns_printers
        result["method_used"] = "mdns"
        if progress_callback:
            progress_callback(100, 100)
        return result

    # Phase 2: ポートスキャン（フォールバック）
    if fallback_to_scan:
        def scan_progress(current, total):
            # 40% ~ 100% の範囲でマッピング
            percent = 40 + int((current / total) * 60)
            if progress_callback:
                progress_callback(percent, 100)

        scan_printers = discover_printers_port_scan(progress_callback=scan_progress)
        result["printers"] = scan_printers
        result["method_used"] = "port_scan" if scan_printers else None

    if progress_callback:
        progress_callback(100, 100)

    return result


# CLIテスト用
if __name__ == "__main__":
    import json

    print("=== プリンタ検出テスト ===")
    print(f"zeroconf利用可能: {ZEROCONF_AVAILABLE}")
    print(f"ローカルIP: {get_local_ip()}")
    print(f"ネットワーク範囲: {get_local_network_range()}")
    print()

    def progress(current, total):
        print(f"\r進捗: {current}/{total} ({int(current/total*100)}%)", end="", flush=True)

    print("検出中...")
    result = discover_printers(progress_callback=progress)
    print()
    print()
    print(f"検出方法: {result['method_used']}")
    print(f"検出数: {len(result['printers'])}")
    print(json.dumps(result['printers'], indent=2, ensure_ascii=False))
