import io
from types import SimpleNamespace

import pytest
from PIL import Image

from src.core import startup_checks as sc
from src.dashboard_server import DashboardHandler, parse_args
from src.modules.media.service import MediaService


def _handler_for_multipart(raw: bytes, content_type: str, content_length: int) -> DashboardHandler:
    h = DashboardHandler.__new__(DashboardHandler)
    h.headers = {"Content-Type": content_type, "Content-Length": str(content_length)}
    h.rfile = io.BytesIO(raw)
    return h


def test_dashboard_multipart_reader_guards_and_payload_conversions(monkeypatch: pytest.MonkeyPatch) -> None:
    h = _handler_for_multipart(b"", "multipart/form-data; boundary=x", 0)
    assert h._read_multipart_files() == []

    h = _handler_for_multipart(b"", "multipart/form-data; boundary=x", 10)
    assert h._read_multipart_files() == []

    class _FakePart:
        def __init__(self, filename, payload, disposition="form-data", multipart=False):
            self._filename = filename
            self._payload = payload
            self._disposition = disposition
            self._multipart = multipart

        def is_multipart(self):
            return self._multipart

        def get_content_disposition(self):
            return self._disposition

        def get_filename(self):
            return self._filename

        def get_payload(self, decode=True):
            assert decode is True
            return self._payload

    class _FakeMsg:
        def walk(self):
            return [
                _FakePart("", b"x"),
                _FakePart("none.bin", None),
                _FakePart("str.bin", "abc"),
                _FakePart("ba.bin", bytearray(b"xyz")),
                _FakePart("obj.bin", object()),
            ]

    class _FakeParser:
        def __init__(self, *args, **kwargs):
            pass

        def parsebytes(self, _data: bytes):
            return _FakeMsg()

    monkeypatch.setattr("email.parser.BytesParser", _FakeParser)
    h = _handler_for_multipart(b"raw", "multipart/form-data; boundary=x", 3)
    files = h._read_multipart_files()
    assert files == [("none.bin", b""), ("str.bin", b"abc"), ("ba.bin", b"xyz")]


def test_dashboard_parse_args_reads_cli_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "--host", "0.0.0.0", "--port", "19091", "--db-path", "tmp.db"])
    args = parse_args()
    assert args.host == "0.0.0.0"
    assert args.port == 19091
    assert args.db_path == "tmp.db"


def test_startup_checks_runtime_python_and_auto_gateway_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCLAW_RUNTIME", "")
    monkeypatch.setattr("src.core.config.get_config", lambda: SimpleNamespace(get=lambda key, default=None: "lite"))
    assert sc.resolve_runtime_mode() == "lite"

    monkeypatch.setattr(sc.sys, "version_info", SimpleNamespace(major=3, minor=9, micro=1))
    py = sc.check_python_version()
    assert py.passed is False
    assert "需要 3.10+" in py.message

    monkeypatch.setattr(sc, "resolve_runtime_mode", lambda: "auto")
    monkeypatch.setattr(sc, "check_gateway_reachable", lambda: sc.StartupCheckResult("Legacy Browser Gateway", True, "ok", True))
    results = sc.run_all_checks(skip_browser=False)
    assert results[-1].name == "Legacy Browser Gateway"
    assert results[-1].passed is True
    assert results[-1].message == "ok"


def test_media_service_targeted_branches(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    svc = MediaService(config={"watermark": {"enabled": False}, "supported_formats": ["jpg", "jpeg", "png"], "max_image_size": 10})

    img = Image.new("RGB", (20, 20), (255, 0, 0))
    same = svc._smart_resize(img)
    assert same is img

    src = tmp_path / "src.jpg"
    img.save(src)

    no_mark = svc.add_watermark(str(src), text="X")
    assert no_mark == str(src)

    out = svc.compress_image(str(src), output_path=None, quality=70)
    assert out == str(src)
    assert src.exists()

    too_big = tmp_path / "too_big.jpg"
    too_big.write_bytes(b"a" * 20)
    ok, msg = svc.validate_image(str(too_big))
    assert ok is False
    assert "图片过大" in msg

    cmyk = tmp_path / "cmyk.jpg"
    Image.new("CMYK", (10, 10)).save(cmyk)
    svc2 = MediaService(config={"supported_formats": ["jpg"], "max_image_size": 10_000_000, "watermark": {"enabled": False}})
    ok2, msg2 = svc2.validate_image(str(cmyk))
    assert ok2 is False
    assert msg2 == "不支持CMYK色彩模式"

    svc3 = MediaService(config={"watermark": {"enabled": False}, "supported_formats": ["jpg"]})
    monkeypatch.setattr(svc3, "resize_image_for_xianyu", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    result = svc3.batch_process_images([str(src)], output_dir=str(tmp_path / "out"), add_watermark=False)
    assert result == [str(src)]
