# common/network_utils.py

import json
import base64
import os # _process_content でのパス存在チェックに使用

def _process_content(content_type, content_data):
    """ヘッダー/フッターのコンテンツを処理し、JSONに含める形式に変換するヘルパー関数"""
    if content_type == "text":
        return content_data
    elif content_type == "image":
        # content_data が既にバイトデータであることを想定
        if isinstance(content_data, bytes):
            return base64.b64encode(content_data).decode('utf-8')
        # もしパスが渡された場合のために、互換性を持たせる（ただし、本来は呼び出し元でバイト化すべき）
        elif isinstance(content_data, str) and os.path.exists(content_data):
            try:
                with open(content_data, "rb") as f:
                    image_bytes = f.read()
                    return base64.b64encode(image_bytes).decode('utf-8')
            except IOError as e:
                print(f"Error reading image file '{content_data}': {e}")
                return None
        else:
            print(f"Warning: Invalid image content data for type '{content_type}': {type(content_data)}")
            return None
    return None

def _deprocess_content(content_type, encoded_content):
    """JSONからデコードされたコンテンツを元の形式に戻すヘルパー関数"""
    if content_type == "text":
        return encoded_content
    elif content_type == "image":
        if encoded_content:
            return base64.b64decode(encoded_content.encode('utf-8'))
    return None

# serialize_data 関数の引数を変更: body_image_paths -> body_image_bytes_list
def serialize_data(header=None, body_text=None, body_image_bytes_list=None, footer=None):
    """
    ヘッダー、本文（テキストと画像バイトリスト）、フッターをJSON形式でシリアライズします。
    header/footer: {"type": "text" or "image", "content": "文字列" or "画像ファイルパス"}
    body_image_bytes_list: [画像バイトデータ1, 画像バイトデータ2, ...]
    """
    
    data = {
        "header": None,
        "body_text": body_text,
        "body_images": [], # ここにはBase64エンコードされた文字列が入る
        "footer": None
    }

    # ヘッダーの処理
    if header and "type" in header and "content" in header:
        processed_header_content = _process_content(header["type"], header["content"])
        if processed_header_content is not None:
            data["header"] = {
                "type": header["type"],
                "content": processed_header_content
            }

    # 本文画像の処理: ここでファイル読み込みは行わず、既にバイト列が渡されていることを想定
    if body_image_bytes_list:
        for img_bytes in body_image_bytes_list:
            if isinstance(img_bytes, bytes): # バイト列であることを確認
                data["body_images"].append(base64.b64encode(img_bytes).decode('utf-8'))
            else:
                print(f"Warning: Expected bytes for body image, but got {type(img_bytes)}. Skipping.")


    # フッターの処理
    if footer and "type" in footer and "content" in footer:
        processed_footer_content = _process_content(footer["type"], footer["content"])
        if processed_footer_content is not None:
            data["footer"] = {
                "type": footer["type"],
                "content": processed_footer_content
            }
            
    return json.dumps(data).encode('utf-8')

# deserialize_data は変更なし
def deserialize_data(json_data_bytes):
    """
    JSON形式のバイト文字列をデシリアライズして、ヘッダー、本文（テキストと画像リスト）、フッターを取得します。
    返り値: header_data, body_text, body_image_bytes_list, footer_data
    header_data/footer_data: {"type": "text" or "image", "content": "文字列" or バイトデータ}
    body_image_bytes_list: [画像バイト1, 画像バイト2, ...]
    """
    data = json.loads(json_data_bytes.decode('utf-8'))
    
    header_data = None
    if data.get("header"):
        header_data = {
            "type": data["header"].get("type"),
            "content": _deprocess_content(data["header"].get("type"), data["header"].get("content"))
        }
    
    body_text = data.get("body_text") or ""
    
    body_image_bytes_list = []
    if "body_images" in data and isinstance(data["body_images"], list):
        for img_base64 in data["body_images"]:
            body_image_bytes_list.append(base64.b64decode(img_base64.encode('utf-8')))
            
    footer_data = None
    if data.get("footer"):
        footer_data = {
            "type": data["footer"].get("type"),
            "content": _deprocess_content(data["footer"].get("type"), data["footer"].get("content"))
        }
            
    return header_data, body_text, body_image_bytes_list, footer_data