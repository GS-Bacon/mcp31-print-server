# tests/test_network_utils.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PIL import Image
import io

from WebService.common.network_utils import serialize_data, deserialize_data


class TestNetworkUtils:
    """network_utilsのテスト（シリアライズ/デシリアライズ）"""

    # ===== シリアライズ/デシリアライズ基本テスト =====

    def test_serialize_deserialize_text_only(self):
        """テキストのみの送受信"""
        original_body = "テスト本文です"

        serialized = serialize_data(body_text=original_body)
        header, body_text, body_images, footer = deserialize_data(serialized)

        assert body_text == original_body
        assert header is None
        assert footer is None
        assert body_images == []

    def test_serialize_deserialize_header_text(self):
        """テキストヘッダー"""
        header_data = {"type": "text", "content": "ヘッダーテキスト"}

        serialized = serialize_data(header=header_data)
        header, body_text, body_images, footer = deserialize_data(serialized)

        assert header["type"] == "text"
        assert header["content"] == "ヘッダーテキスト"

    def test_serialize_deserialize_footer_text(self):
        """テキストフッター"""
        footer_data = {"type": "text", "content": "フッターテキスト"}

        serialized = serialize_data(footer=footer_data)
        header, body_text, body_images, footer = deserialize_data(serialized)

        assert footer["type"] == "text"
        assert footer["content"] == "フッターテキスト"

    def test_serialize_deserialize_header_image(self):
        """画像ヘッダー"""
        img = Image.new('RGB', (50, 50), color='red')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_bytes = buffer.getvalue()

        header_data = {"type": "image", "content": img_bytes}

        serialized = serialize_data(header=header_data)
        header, body_text, body_images, footer = deserialize_data(serialized)

        assert header["type"] == "image"
        assert header["content"] == img_bytes

    def test_serialize_deserialize_body_images(self):
        """本文画像（複数）"""
        img1 = Image.new('RGB', (30, 30), color='blue')
        img2 = Image.new('RGB', (40, 40), color='green')

        buffer1 = io.BytesIO()
        img1.save(buffer1, format='PNG')
        bytes1 = buffer1.getvalue()

        buffer2 = io.BytesIO()
        img2.save(buffer2, format='JPEG')
        bytes2 = buffer2.getvalue()

        serialized = serialize_data(body_image_bytes_list=[bytes1, bytes2])
        header, body_text, body_images, footer = deserialize_data(serialized)

        assert len(body_images) == 2
        assert body_images[0] == bytes1
        assert body_images[1] == bytes2

    def test_serialize_deserialize_full(self):
        """全データの送受信"""
        header_data = {"type": "text", "content": "=== ヘッダー ==="}
        body = "本文テキスト\n改行も含む"

        img = Image.new('RGB', (100, 100), color='purple')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_bytes = buffer.getvalue()

        footer_data = {"type": "image", "content": img_bytes}

        serialized = serialize_data(
            header=header_data,
            body_text=body,
            body_image_bytes_list=[img_bytes],
            footer=footer_data
        )

        header, body_text, body_images, footer = deserialize_data(serialized)

        assert header["type"] == "text"
        assert header["content"] == "=== ヘッダー ==="
        assert body_text == body
        assert len(body_images) == 1
        assert body_images[0] == img_bytes
        assert footer["type"] == "image"
        assert footer["content"] == img_bytes

    # ===== エッジケース =====

    def test_serialize_deserialize_empty(self):
        """全て空/None"""
        serialized = serialize_data()
        header, body_text, body_images, footer = deserialize_data(serialized)

        assert header is None
        assert body_text == ""
        assert body_images == []
        assert footer is None

    def test_serialize_deserialize_empty_string(self):
        """空文字列"""
        serialized = serialize_data(body_text="")
        header, body_text, body_images, footer = deserialize_data(serialized)
        assert body_text == ""

    def test_serialize_deserialize_long_text(self):
        """長いテキスト"""
        long_text = "あ" * 10000

        serialized = serialize_data(body_text=long_text)
        header, body_text, body_images, footer = deserialize_data(serialized)

        assert body_text == long_text

    def test_serialize_deserialize_special_chars(self):
        """特殊文字・制御文字"""
        special = "Hello\tWorld\n\r特殊文字：！＠＃＄％"

        serialized = serialize_data(body_text=special)
        header, body_text, body_images, footer = deserialize_data(serialized)

        assert body_text == special

    def test_serialize_deserialize_unicode(self):
        """Unicode文字（絵文字など）"""
        unicode_text = "絵文字テスト 🎉🚀✨ 中文 한국어"

        serialized = serialize_data(body_text=unicode_text)
        header, body_text, body_images, footer = deserialize_data(serialized)

        assert body_text == unicode_text

    def test_serialize_deserialize_large_image(self):
        """大きい画像"""
        img = Image.new('RGB', (2000, 2000), color='white')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        large_bytes = buffer.getvalue()

        serialized = serialize_data(body_image_bytes_list=[large_bytes])
        header, body_text, body_images, footer = deserialize_data(serialized)

        assert len(body_images) == 1
        assert body_images[0] == large_bytes

    def test_serialize_deserialize_many_images(self):
        """多数の画像"""
        images = []
        for i in range(10):
            img = Image.new('RGB', (50, 50), color=(i * 25, 0, 0))
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            images.append(buffer.getvalue())

        serialized = serialize_data(body_image_bytes_list=images)
        header, body_text, body_images, footer = deserialize_data(serialized)

        assert len(body_images) == 10
        for i, img_bytes in enumerate(body_images):
            assert img_bytes == images[i]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
