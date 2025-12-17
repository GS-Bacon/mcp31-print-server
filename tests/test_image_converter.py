# tests/test_image_converter.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PIL import Image
import io

from MCP31PRINT.image_converter import ImageConverter


class TestImageConverter:
    """ImageConverterのテスト"""

    @pytest.fixture
    def converter(self):
        """デフォルトのImageConverterインスタンス"""
        return ImageConverter(font_path=None, font_size=24, default_width=384)

    # ===== text_to_bitmap テスト =====

    def test_text_to_bitmap_normal(self, converter):
        """通常のテキスト変換"""
        result = converter.text_to_bitmap("こんにちは")
        assert result is not None
        assert isinstance(result, Image.Image)
        assert result.mode == 'RGB'
        assert result.width > 0
        assert result.height > 0

    def test_text_to_bitmap_empty(self, converter):
        """空文字列"""
        result = converter.text_to_bitmap("")
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_text_to_bitmap_whitespace_only(self, converter):
        """空白のみ"""
        result = converter.text_to_bitmap("   ")
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_text_to_bitmap_newlines(self, converter):
        """改行を含むテキスト"""
        result = converter.text_to_bitmap("1行目\n2行目\n3行目")
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_text_to_bitmap_long_text(self, converter):
        """長いテキスト"""
        long_text = "あ" * 1000
        result = converter.text_to_bitmap(long_text)
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_text_to_bitmap_special_chars(self, converter):
        """特殊文字"""
        result = converter.text_to_bitmap("!@#$%^&*()_+-=[]{}|;':\",./<>?")
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_text_to_bitmap_mixed_content(self, converter):
        """日本語・英語・数字・記号の混合"""
        result = converter.text_to_bitmap("Hello世界123!テスト@#$")
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_text_to_bitmap_empty_lines(self, converter):
        """空行を含むテキスト"""
        result = converter.text_to_bitmap("1行目\n\n\n4行目")
        assert result is not None
        assert isinstance(result, Image.Image)

    # ===== image_from_bytes テスト =====

    def test_image_from_bytes_png(self, converter):
        """PNG画像のバイト変換"""
        # テスト用PNG画像を生成
        img = Image.new('RGB', (100, 100), color='red')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        png_bytes = buffer.getvalue()

        result = converter.image_from_bytes(png_bytes)
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_image_from_bytes_jpeg(self, converter):
        """JPEG画像のバイト変換"""
        img = Image.new('RGB', (100, 100), color='blue')
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        jpeg_bytes = buffer.getvalue()

        result = converter.image_from_bytes(jpeg_bytes)
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_image_from_bytes_rgba(self, converter):
        """RGBA（透過）画像のバイト変換"""
        img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        rgba_bytes = buffer.getvalue()

        result = converter.image_from_bytes(rgba_bytes)
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_image_from_bytes_large_image(self, converter):
        """大きい画像（プリンター幅より大きい）"""
        img = Image.new('RGB', (1000, 1000), color='green')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        large_bytes = buffer.getvalue()

        result = converter.image_from_bytes(large_bytes)
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_image_from_bytes_small_image(self, converter):
        """小さい画像"""
        img = Image.new('RGB', (10, 10), color='yellow')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        small_bytes = buffer.getvalue()

        result = converter.image_from_bytes(small_bytes)
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_image_from_bytes_invalid(self, converter):
        """無効なバイトデータ"""
        result = converter.image_from_bytes(b"invalid image data")
        assert result is None

    def test_image_from_bytes_empty(self, converter):
        """空のバイトデータ"""
        result = converter.image_from_bytes(b"")
        assert result is None

    # ===== combine_images_vertically テスト =====

    def test_combine_images_single(self, converter):
        """1枚の画像結合"""
        img = Image.new('RGB', (100, 50), color='red')
        result = converter.combine_images_vertically([img])
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_combine_images_multiple(self, converter):
        """複数画像の結合"""
        img1 = Image.new('RGB', (100, 50), color='red')
        img2 = Image.new('RGB', (100, 50), color='blue')
        img3 = Image.new('RGB', (100, 50), color='green')

        result = converter.combine_images_vertically([img1, img2, img3])
        assert result is not None
        assert isinstance(result, Image.Image)
        # 結合後の高さは3枚分 + パディング
        assert result.height >= 150

    def test_combine_images_different_sizes(self, converter):
        """異なるサイズの画像結合"""
        img1 = Image.new('RGB', (50, 30), color='red')
        img2 = Image.new('RGB', (200, 100), color='blue')
        img3 = Image.new('RGB', (500, 50), color='green')  # 幅がdefault_widthより大きい

        result = converter.combine_images_vertically([img1, img2, img3])
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_combine_images_empty_list(self, converter):
        """空のリスト"""
        result = converter.combine_images_vertically([])
        assert result is None

    def test_combine_images_with_text(self, converter):
        """テキスト画像と通常画像の結合"""
        text_img = converter.text_to_bitmap("ヘッダーテキスト")
        color_img = Image.new('RGB', (100, 100), color='purple')

        result = converter.combine_images_vertically([text_img, color_img])
        assert result is not None
        assert isinstance(result, Image.Image)

    # ===== 統合テスト =====

    def test_full_workflow(self, converter):
        """ヘッダー + 本文テキスト + 画像 + フッターの完全ワークフロー"""
        header = converter.text_to_bitmap("=== ヘッダー ===")
        body_text = converter.text_to_bitmap("本文のテキストです。\n改行も含みます。")
        body_image = Image.new('RGB', (200, 150), color='cyan')
        footer = converter.text_to_bitmap("--- フッター ---")

        result = converter.combine_images_vertically([header, body_text, body_image, footer])
        assert result is not None
        assert isinstance(result, Image.Image)
        assert result.width == converter.default_width


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
