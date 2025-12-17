import socket
import threading
import os
import sys
import queue # queueモジュールをインポート

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..')
sys.path.append(project_root)

from datetime import datetime
from common.network_utils import deserialize_data
from .config import BaseServerConfig

from MCP31PRINT.printer_driver import PrinterDriver
from MCP31PRINT.image_converter import ImageConverter
FONT_PATH='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'

try:
    from .MyActualServerConfig import MyActualServerConfig as ActualServerConfig
except ImportError:
    print("Error: MyActualServerConfig.py not found or incorrectly configured.")
    print("Please copy ServerConfig.py.template to MyActualServerConfig.py and set actual values.")
    exit(1)

class FileReceiverServer:
    def __init__(self):
        self.host = ActualServerConfig().SERVER_IP
        self.port = ActualServerConfig().SERVER_PORT
        self.output_dir = os.path.join(current_dir, "received_files") # output_dir は相対パスのままでOK
                                                                        # os.path.join は絶対パスと結合すると絶対パスになる
        os.makedirs(self.output_dir, exist_ok=True)

        # ★追加: プリントジョブキューを初期化
        self.print_queue = queue.Queue()
        # ★追加: ワーカースレッドを起動
        self.printer_worker_thread = threading.Thread(target=self._printer_worker, daemon=True)
        self.printer_worker_thread.start()
        print("Printer worker thread started.")

    def _printer_worker(self):
        """
        プリントキューからジョブを取り出し、順次プリンターに送信するワーカースレッド。
        """
        driver = PrinterDriver()
        converter = ImageConverter(
            font_path=FONT_PATH,
            font_size=30,
            default_width=driver.paper_width_dots
        )
        
        while True:
            # キューからジョブを取得。キューが空の場合は、ジョブが来るまでここで待機する。
            job_data = self.print_queue.get() 
            print(f"Processing print job from queue. Queue size: {self.print_queue.qsize()}")

            try:
                # job_data は deserialize_data の返り値（header_data, body_text, body_image_bytes_list, footer_data）
                header_data, body_text, body_image_bytes_list, footer_data = job_data

                imglist = []
                
                # ヘッダー処理
                if header_data:
                    if isinstance(header_data, dict) and header_data.get("type") == "text" and header_data.get("content"):
                        imglist.append(converter.text_to_bitmap(text=header_data["content"]))
                    elif isinstance(header_data, dict) and header_data.get("type") == "image" and header_data.get("content"):
                        imglist.append(converter.image_from_bytes(header_data["content"]))
                    elif isinstance(header_data, str):
                        imglist.append(converter.text_to_bitmap(text=header_data))
                    else:
                        print(f"Warning: Unexpected header_data format in worker: {type(header_data)} - {header_data}")

                # 本文テキスト処理
                if body_text:
                    imglist.append(converter.text_to_bitmap(text=body_text))
                    print(f"Converting body text to image in worker: {body_text[:50]}...")

                # 本文画像処理
                if body_image_bytes_list:
                    for i, image_bytes in enumerate(body_image_bytes_list):
                        imglist.append(converter.image_from_bytes(image_bytes=image_bytes))
                        print(f"Converting body image {i+1} to image in worker.")

                # フッター処理
                if footer_data:
                    if isinstance(footer_data, dict) and footer_data.get("type") == "image" and footer_data.get("content"):
                        imglist.append(converter.image_from_bytes(footer_data["content"]))
                        print("Converting footer QR image to image in worker.")
                    elif isinstance(footer_data, dict) and footer_data.get("type") == "text" and footer_data.get("content"):
                        imglist.append(converter.text_to_bitmap(text=footer_data["content"]))
                        print("Converting footer text to image in worker.")
                    elif isinstance(footer_data, bytes):
                        imglist.append(converter.image_from_bytes(footer_data))
                        print("Converting raw footer image bytes to image in worker.")
                    else:
                        print(f"Warning: Unexpected footer_data format in worker: {type(footer_data)} - {footer_data}")

                # すべての画像を結合して印刷
                if imglist:
                    printimg = converter.combine_images_vertically(images=imglist)
                    if printimg:
                        driver.print_image(printimg)
                        driver.print_empty_lines(5)
                        print("\n--- 紙をカット ---")
                        driver.cut_paper(mode='full')
                        print(f"Job completed successfully. Remaining in queue: {self.print_queue.qsize()}")
                    else:
                        print("Worker: No combined image to print.")
                else:
                    print("Worker: No content to print for this job.")

            except Exception as e:
                print(f"Error processing print job in worker: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # ジョブ処理が完了したことをキューに通知
                self.print_queue.task_done()
                print(f"Job finished. Remaining in queue: {self.print_queue.qsize()}")


    def _handle_client(self, conn, addr):
        print(f"Connected by {addr}")
        try:
            data_buffer = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data_buffer += chunk
                if b"<END_OF_TRANSMISSION>" in data_buffer:
                    data_buffer = data_buffer.replace(b"<END_OF_TRANSMISSION>", b"")
                    break

            # 受信したデータをキューに追加するだけに変更
            header_data, body_text, body_image_bytes_list, footer_data = deserialize_data(data_buffer)
            
            # 受信時刻と送信元IPは、ファイル保存などのデバッグ用途で残しておく
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            sender_ip = addr[0].replace('.', '_')

            # ジョブデータをタプルとしてキューに入れる
            job_tuple = (header_data, body_text, body_image_bytes_list, footer_data)
            self.print_queue.put(job_tuple)
            print(f"Received data from {addr} and added to print queue. Current queue size: {self.print_queue.qsize()}")

        except Exception as e:
            print(f"Error handling client {addr}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            conn.close()
            print(f"Connection with {addr} closed.")

    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen()
            print(f"Server listening on {self.host}:{self.port}")
            while True:
                conn, addr = s.accept()
                thread = threading.Thread(target=self._handle_client, args=(conn, addr))
                thread.start()

if __name__ == "__main__":
    server = FileReceiverServer()
    server.start()