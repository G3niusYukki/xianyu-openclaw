from PIL import Image

from src.modules.media.utils import add_watermark, resize_image_for_xianyu


def test_resize_and_watermark_success(tmp_path):
    src = tmp_path / "src.png"
    out1 = tmp_path / "resized.jpg"
    out2 = tmp_path / "watermarked.jpg"

    Image.new("RGB", (100, 50), (0, 0, 0)).save(src)

    assert resize_image_for_xianyu(str(src), str(out1), target_size=(80, 80)) is True
    assert out1.exists()

    assert add_watermark(str(out1), str(out2), text="HELLO") is True
    assert out2.exists()


def test_resize_and_watermark_failures(tmp_path):
    missing = tmp_path / "missing.png"
    assert resize_image_for_xianyu(str(missing), str(tmp_path / "o.jpg")) is False
    assert add_watermark(str(missing), str(tmp_path / "w.jpg")) is False
