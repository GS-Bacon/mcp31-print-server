# printer_driver.py

from escpos.printer import Network
from PIL import Image, ImageOps
import io
import time
import socket
from struct import pack

# local_configから設定をインポート（存在しない場合はデフォルト値を使用）
try:
    from MCP31PRINT.local_config import LocalPrinterConfig
    DEFAULT_PRINTER_IP = LocalPrinterConfig.PRINTER_IP
    DEFAULT_PRINTER_PORT = LocalPrinterConfig.PRINTER_PORT
    DEFAULT_PAPER_WIDTH_DOTS = LocalPrinterConfig.PAPER_WIDTH_DOTS
except ImportError:
    DEFAULT_PRINTER_IP = "192.168.1.100"
    DEFAULT_PRINTER_PORT = 9100
    DEFAULT_PAPER_WIDTH_DOTS = 576


class PrinterDriver:
    def __init__(self, printer_ip: str = None, printer_port: int = None, paper_width_dots: int = None):
        """
        :param printer_ip: プリンタのIPアドレス（Noneの場合はデフォルト値を使用）
        :param printer_port: プリンタのポート番号（Noneの場合はデフォルト値を使用）
        :param paper_width_dots: 用紙幅のドット数（Noneの場合はデフォルト値を使用）
        """
        self.printer_ip = printer_ip or DEFAULT_PRINTER_IP
        self.printer_port = printer_port or DEFAULT_PRINTER_PORT
        self.paper_width_dots = paper_width_dots or DEFAULT_PAPER_WIDTH_DOTS
        self.printer = None
        self.connection_timeout = 5 # 接続試行時のタイムアウト (秒)

    def _connect(self) -> bool:
        """
        プリンターに接続する内部関数。
        接続済みであれば再接続しない。
        エラー時は詳細なメッセージを出力。
        :return: 接続に成功すればTrue、そうでなければFalse
        """
        if self.printer:
            return True # 既に接続済み

        try:
            print(f"DEBUG: Connecting to printer at {self.printer_ip}:{self.printer_port}...")
            self.printer = Network(self.printer_ip, self.printer_port)
            
            self.printer._raw(b'\x1B\x40') # プリンター初期化コマンド
            time.sleep(0.5) # プリンターがコマンドを処理するのを待つ

            print("DEBUG: Connection established and printer initialized.")
            return True
        except socket.timeout:
            print(f"ERROR: 接続タイムアウト - プリンター ({self.printer_ip}:{self.printer_port}) への接続がタイムアウトしました。")
            self.printer = None
            return False
        except socket.error as e:
            print(f"ERROR: ソケットエラー - プリンターへの接続中にエラーが発生しました: {e}")
            print(f"DEBUG: ホスト ({self.printer_ip}) が到達可能か、ポート ({self.printer_port}) が開いているか確認してください。")
            self.printer = None
            return False
        except Exception as e:
            print(f"ERROR: 予期せぬエラー - プリンター接続中にエラーが発生しました: {e}")
            self.printer = None
            return False

    def _disconnect(self):
        """
        プリンターとの接続を切断する内部関数。
        エラー時は詳細なメッセージを出力。
        """
        if self.printer:
            try:
                self.printer.close() 
            except Exception as e:
                print(f"ERROR: プリンター切断時にエラーが発生しました: {e}")
            finally:
                self.printer = None # 必ず None に設定

    def check_connection(self) -> bool:
        """
        プリンターとの接続をチェックする。
        :return: 接続可能であればTrue、そうでなければFalse
        """
        print(f"プリンター {self.printer_ip}:{self.printer_port} への接続をチェック中...")
        if self._connect():
            print("プリンターへの接続に成功しました。")
            self._disconnect() # 接続チェックのみなので、すぐに切断
            return True
        else:
            print("プリンターへの接続に失敗しました。")
            return False

    def read_printer_settings(self) -> dict:
        """
        プリンター設定を読み込む (StarPRNT固有のコマンドを考慮)。
        詳細なエラー情報を出力。
        """
        settings = {}
        if not self._connect():
            settings['status'] = "接続失敗。設定を読み込めません。"
            return settings

        try:
            self.printer._raw(b'\x1D\x49\x41') 
            time.sleep(0.5) 

            # _read()はNetworkクラスのプライベートメソッドなので、
            # publicなdevice.read()を使用するか、_read()が定義されていることを確認
            # escpos.printer.Networkの_read()は通常、内部で利用される
            # ここでは安全のため、device.read() を使用
            response = self.printer.device.read(4096, timeout=self.connection_timeout) 

            if response:
                try:
                    decoded_response = response.decode('shift_jis', errors='replace')
                    settings['raw_response'] = response.hex()
                    settings['decoded_response'] = decoded_response
                    print(f"DEBUG: プリンター応答 (生): {response.hex()}")
                    print(f"DEBUG: プリンター応答 (デコード): {decoded_response}")
                except UnicodeDecodeError:
                    settings['raw_response'] = response.hex()
                    settings['decoded_response'] = "デコード失敗 (Shift-JIS以外、またはバイナリデータ)"
                    print(f"WARNING: プリンター応答のShift-JISデコードに失敗しました。")
                    print(f"DEBUG: プリンター応答 (生): {response.hex()}")
            else:
                print("WARNING: プリンターからの応答がありませんでした。")
                settings['status'] = "応答なし"
            
            settings['status'] = "接続成功。一部設定を読み込みました。"
            
        except socket.timeout:
            print(f"ERROR: プリンター設定読み込みタイムアウト - プリンター ({self.printer_ip}:{self.printer_port}) からの応答がタイムアウトしました。")
            settings['status'] = "エラー: 読み込みタイムアウト"
        except socket.error as e:
            print(f"ERROR: ソケットエラー - プリンター設定読み込み中にエラーが発生しました: {e}")
            settings['status'] = f"エラー: ネットワークエラー: {e}"
        except Exception as e:
            print(f"ERROR: 予期せぬエラー - プリンター設定読み込み中にエラーが発生しました: {e}")
            settings['status'] = f"エラー: 予期せぬエラー: {e}"
        finally:
            self._disconnect()
        return settings

    def _send_raw_command(self, command: bytes) -> bool:
        """
        プリンターに直接バイナリコマンドを送信するヘルパー関数。
        詳細なエラー情報を出力。
        :return: コマンド送信に成功すればTrue、そうでなければFalse
        """
        if not self._connect(): # 各操作前に接続を試みる
            return False
        try:
            self.printer._raw(command)
            time.sleep(0.1) # コマンド送信後、少し待つ
            return True
        except socket.timeout:
            print(f"ERROR: コマンド送信タイムアウト - プリンター ({self.printer_ip}:{self.printer_port}) へのコマンド送信がタイムアウトしました。")
            return False
        except socket.error as e:
            print(f"ERROR: ソケットエラー - コマンド送信中にエラーが発生しました: {e}")
            return False
        except Exception as e:
            print(f"ERROR: 予期せぬエラー - コマンド送信中にエラーが発生しました: {e}")
            return False
        finally:
            self._disconnect() # 各操作後に切断

    def print_text_raw(self, text: str, encoding: str = 'shift_jis'):
        """
        文字列を直接コマンドとして印刷する。文字化け対策のため、エンコーディングを指定可能にする。
        詳細なエラー情報を出力。
        :param text: 印刷する文字列
        :param encoding: 文字列のエンコーディング (e.g., 'shift_jis', 'cp932')
        """
        if not self._connect():
            return

        try:
            encoded_text = text.encode(encoding)
            self.printer._raw(encoded_text)
            self.printer._raw(b'\x0A') # 改行コード (LF) を追加
            print(f"テキスト '{text}' を印刷しました。")
            time.sleep(1) # テキスト印刷後、少し待つ
        except UnicodeEncodeError as e:
            print(f"ERROR: 文字列のエンコードに失敗しました ({encoding}): {e}")
            print("DEBUG: 指定されたエンコーディングで文字列が表現できない可能性があります。")
            return 0
        except socket.timeout:
            print(f"ERROR: テキスト印刷タイムアウト - プリンター ({self.printer_ip}:{self.printer_port}) へのテキスト送信がタイムアウトしました。")
        except socket.error as e:
            print(f"ERROR: ソケットエラー - テキスト印刷中にエラーが発生しました: {e}")
        except Exception as e:
            print(f"ERROR: 予期せぬエラー - テキスト印刷中にエラーが発生しました: {e}")
        finally:
            self._disconnect()

    def print_image(self, image_input: str | io.BytesIO | Image.Image, alignment: int = 0): # alignmentは0:Left, 1:Center, 2:Right
        """
        画像データをStarPRNTプリンターのラスターコマンドで印刷する。
        RGB/RGBA画像も適切に処理し、高度なディザリングを適用。
        :param image_input: 画像ファイルのパス (str) または BytesIO オブジェクト、PIL.Image オブジェクト
        :param alignment: 画像の水平アライメント (0: 左寄せ, 1: 中央寄せ, 2: 右寄せ)
        :raises ConnectionError: プリンタへの接続に失敗した場合
        """
        if not self._connect():
            raise ConnectionError(f"プリンタ {self.printer_ip}:{self.printer_port} への接続に失敗しました")

        try:
            self.printer._raw(b'\x1B\x40') # プリンター初期化コマンド
            time.sleep(1) # 初期化コマンドが処理されるのを待つ
            
            # 1. 画像の読み込みと初期処理
            if isinstance(image_input, str) or isinstance(image_input, io.BytesIO):
                img = Image.open(image_input)
            elif isinstance(image_input, Image.Image):
                img = image_input
            else:
                raise TypeError("image_input must be a file path (str), BytesIO, or PIL.Image object.")
            
            img.save("debug_01_initial.png")
            width, height = img.size

            # 2. RGBA (透過) 画像の処理
            if img.mode == "RGBA":
                bg = Image.new("RGBA", (width, height), (255, 255, 255, 255))
                img = Image.alpha_composite(bg, img)
                img.save("debug_02_rgba_processed.png")
            # 3. リサイズ (プリンターの紙幅に合わせる)
            if width > self.paper_width_dots:
                img = img.resize((self.paper_width_dots, height * self.paper_width_dots // width), Image.Resampling.LANCZOS)
                width, height = img.size
                img.save("debug_03_resized.png")
            # 4. グレースケール変換 (BT.709 Luma + ガンマ補正)
            if img.mode == "RGB" or img.mode == "RGBA":
                new_img = Image.new("L", img.size)
                img_data = img.getdata()
                new_img.putdata([round((((0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]) / 255) ** (1 / 2.2)) ** 1.5 * 255) for pixel in img_data])
                img = new_img
                img.save("debug_04_grayscale_l.png")
            elif img.mode not in ("1", "L"):
                img = img.convert("L")
                img.save("debug_04_grayscale_l.png") 

            # 5. モノクロ1ビット変換 (PillowのDitheringに切り替え)
            if img.mode == "L":
                img = img.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
                img.save("debug_05_monochrome_1bit.png")
            img = ImageOps.invert(img)
            # 6. 幅を8の倍数にパディング (プリンター要件)
            if width % 8 != 0:
                padded_width = width + (8 - width % 8)
                padded_img = Image.new("1", (padded_width, height), 1) # 白でパディング
                padded_img.paste(img, (0, 0))
                img = padded_img
                width, height = img.size
                img.save("debug_06_padded.png")
            
            # 7. アライメント (余白を追加して位置調整)
            if alignment == 1: # Center
                padding_x = (self.paper_width_dots - width) // 2
                if padding_x > 0:
                    img = ImageOps.expand(img, (padding_x, 0, self.paper_width_dots - width - padding_x, 0), fill=1) # 白でパディング
                    width, height = img.size
                    img.save("debug_07_aligned.png")
            
            elif alignment == 2: # Right
                padding_x = self.paper_width_dots - width
                if padding_x > 0:
                    img = ImageOps.expand(img, (padding_x, 0, 0, 0), fill=1) # 白でパディング
                    width, height = img.size
                    img.save("debug_07_aligned.png")

            # 8. 画像データをバイト列に変換
            data = img.tobytes()
            
            # 9. StarPRNTラスターコマンドの組み立てと送信 (ESC GS S 1 コマンド形式)
            # Command: ESC GS S 1 xL xH yL yH [data]
            # xL, xH: image width in bytes (LSB first)
            # yL, yH: image height in dots (LSB first)
            
            x_bytes_val = width // 8
            y_dots_val = height

            # コマンドプレフィックスを ESC GS S 1 に変更
            command_prefix = b'\x1B\x1D\x53\x01' # ESC GS S 1
            
            # struct.pack を使用してリトルエンディアンでパック
            # ESC GS S 1 コマンドは p1-p4 (データ長) を持ちません
            x_bytes = pack("<H", x_bytes_val) # 2バイトのunsigned short (xL xH)
            y_bytes = pack("<H", y_dots_val) # 2バイトのunsigned short (yL yH)

            full_command = command_prefix + x_bytes + y_bytes + b"\x00" + data
            self.printer._raw(full_command)
            #self.printer._raw(b'\x0A')
            print("画像をラスターモードで印刷しました。")
            time.sleep(1) # 画像印刷後、十分な待ち時間を設ける

        except FileNotFoundError:
            print(f"ERROR: 画像ファイルが見つかりません。")
        except TypeError as e:
            print(f"ERROR: 画像入力の型が不正です: {e}")
        except Exception as e:
            print(f"ERROR: 画像印刷中に予期せぬエラーが発生しました: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._disconnect()
    def print_image_from_bytes(self, image_bytes: bytes, alignment: int = 0):
        """
        バイト列形式の画像データをStarPRNTプリンターのラスターコマンドで印刷する。
        内部でPIL.Imageに変換し、必要な画像処理（リサイズ、モノクロ化、パディングなど）を行う。
        :param image_bytes: 画像のバイト列データ (例: PNG, JPEGなどのファイルデータ)
        :param alignment: 画像の水平アライメント (0: 左寄せ, 1: 中央寄せ, 2: 右寄せ)
        :raises ConnectionError: プリンタへの接続に失敗した場合
        """
        if not self._connect():
            raise ConnectionError(f"プリンタ {self.printer_ip}:{self.printer_port} への接続に失敗しました")

        try:
            self.printer._raw(b'\x1B\x40') # プリンター初期化コマンド
            time.sleep(1) # 初期化コマンドが処理されるのを待つ
            print("DEBUG: Printer initialized before image printing from bytes.")
            
            # バイト列からPIL.Imageオブジェクトを作成
            img_io = io.BytesIO(image_bytes)
            img = Image.open(img_io)
            
            print(f"DEBUG: Image received from bytes. Initial mode: {img.mode}, size: {img.size}")
            # デバッグのためにPIL Imageオブジェクトを保存
            img.save("debug_bytes_initial.png")

            width, height = img.size

            # 以降の画像処理は print_image と同じ
            # 2. RGBA (透過) 画像の処理
            if img.mode == "RGBA":
                bg = Image.new("RGBA", (width, height), (255, 255, 255, 255))
                img = Image.alpha_composite(bg, img)
                print("DEBUG: RGBA image alpha-composited with white background from bytes.")
                img.save("debug_bytes_rgba_processed.png")
            # 3. リサイズ (プリンターの紙幅に合わせる)
            if width > self.paper_width_dots:
                img = img.resize((self.paper_width_dots, height * self.paper_width_dots // width), Image.Resampling.LANCZOS)
                width, height = img.size
                print(f"DEBUG: Image resized to fit paper width from bytes: {img.size}")
                img.save("debug_bytes_resized.png")
            # 4. グレースケール変換 (BT.709 Luma + ガンマ補正)
            if img.mode == "RGB" or img.mode == "RGBA":
                new_img = Image.new("L", img.size)
                img_data = img.getdata()
                new_img.putdata([round((((0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]) / 255) ** (1 / 2.2)) ** 1.5 * 255) for pixel in img_data])
                img = new_img
                print("DEBUG: RGB/RGBA image converted to L (Luma) with gamma correction from bytes.")
                img.save("debug_bytes_grayscale_l.png")
            elif img.mode not in ("1", "L"):
                img = img.convert("L")
                print(f"DEBUG: Image converted to L (Grayscale) from {img.mode} from bytes.")
                img.save("debug_bytes_grayscale_l.png") 

            # 5. モノクロ1ビット変換 (PillowのDitheringに切り替え)
            if img.mode == "L":
                img = img.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
                print("DEBUG: Image converted to 1-bit monochrome with Pillow's FLOYDSTEINBERG dithering from bytes.")
                img.save("debug_bytes_monochrome_1bit.png")
            
            img = ImageOps.invert(img)
            img.save("debug_bytes_monochrome_1bit_inverted.png") # 反転後のデバッグ画像を保存

            # 6. 幅を8の倍数にパディング (プリンター要件)
            if width % 8 != 0:
                padded_width = width + (8 - width % 8)
                padded_img = Image.new("1", (padded_width, height), 1) # 白でパディング
                padded_img.paste(img, (0, 0))
                img = padded_img
                width, height = img.size
                print(f"DEBUG: Image padded to width {width} (multiple of 8) from bytes.")
                img.save("debug_bytes_padded.png")
            
            # 7. アライメント (余白を追加して位置調整)
            if alignment == 1: # Center
                padding_x = (self.paper_width_dots - width) // 2
                if padding_x > 0:
                    img = ImageOps.expand(img, (padding_x, 0, self.paper_width_dots - width - padding_x, 0), fill=1) # 白でパディング
                    width, height = img.size
                    print(f"DEBUG: Image centered with padding {padding_x} from bytes.")
                    img.save("debug_bytes_aligned.png")
            
            elif alignment == 2: # Right
                padding_x = self.paper_width_dots - width
                if padding_x > 0:
                    img = ImageOps.expand(img, (padding_x, 0, 0, 0), fill=1) # 白でパディング
                    width, height = img.size
                    print(f"DEBUG: Image right-aligned with padding {padding_x} from bytes.")
                    img.save("debug_bytes_aligned.png")

            # 8. 画像データをバイト列に変換 (プリンター用)
            data = img.tobytes()
            print(f"DEBUG: Image data converted to bytes for printer. Length: {len(data)} bytes.")
            print(f"DEBUG: First 20 bytes of printer data: {data[:20].hex()}")
            
            # 9. StarPRNTラスターコマンドの組み立てと送信 (ESC GS S 1 コマンド形式)
            x_bytes_val = width // 8
            y_dots_val = height

            command_prefix = b'\x1B\x1D\x53\x01' # ESC GS S 1
            
            x_bytes = pack("<H", x_bytes_val) 
            y_bytes = pack("<H", y_dots_val) 

            full_command = command_prefix + x_bytes + y_bytes + b"\x00" + data
            self.printer._raw(full_command)
            self.printer._raw(b'\x0A') # 改行コード (LF) を追加
            print("バイト列から画像をラスターモードで印刷しました。")
            time.sleep(2) # 画像印刷後、十分な待ち時間を設ける

        except Exception as e:
            print(f"ERROR: バイト列からの画像印刷中に予期せぬエラーが発生しました: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._disconnect()
    def print_empty_lines(self, num_lines: int):
        """
        指定された行数だけ空白行を印刷して紙送りを行う。
        :param num_lines: 印刷する空白行の数
        :raises ConnectionError: プリンタへの接続に失敗した場合
        """
        if not self._connect():
            raise ConnectionError(f"プリンタ {self.printer_ip}:{self.printer_port} への接続に失敗しました")
        try:
            print(f"DEBUG: Printing {num_lines} empty lines for paper feed.")
            for _ in range(num_lines):
                self.printer._raw(b'\x0A') # LF (改行) を送信
            print(f"{num_lines}行の空白行を印刷しました。")
            time.sleep(num_lines * 0.1) # 各行の印刷に少し時間をかける
        except Exception as e:
            print(f"ERROR: 空白行印刷中にエラーが発生しました: {e}")
        finally:
            self._disconnect()
    def cut_paper(self, mode: str = 'full'):
        """
        紙をカットする (StarPRNTコマンド)。
        詳細なエラー情報を出力。
        :raises ConnectionError: プリンタへの接続に失敗した場合
        """
        if not self._connect():
            raise ConnectionError(f"プリンタ {self.printer_ip}:{self.printer_port} への接続に失敗しました")
        
        try:
            if mode == 'full':
                command = b'\x1B\x64\x02' # ESC d 2 (Full Cut)
            elif mode == 'partial':
                command = b'\x1B\x64\x00' # ESC d 0 (Partial Cut)
                print("DEBUG: Sending partial cut command (ESC d 0)...")
            else:
                print("ERROR: 無効なカットモードです。'full' または 'partial' を指定してください。")
                return

            self.printer._raw(command)
            print(f"用紙カットコマンド '{mode}' を送信しました。")
            time.sleep(0.5) # カット動作が完了するのを待つ
        except socket.timeout:
            print(f"ERROR: 用紙カットタイムアウト - プリンター ({self.printer_ip}:{self.printer_port}) へのコマンド送信がタイムアウトしました。")
        except socket.error as e:
            print(f"ERROR: ソケットエラー - 用紙カット中にエラーが発生しました: {e}")
        except Exception as e:
            print(f"ERROR: 予期せぬエラー - 用紙カット中にエラーが発生しました: {e}")
        finally:
            self._disconnect()
