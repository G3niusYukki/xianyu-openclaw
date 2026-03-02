import io
import sqlite3
from unittest.mock import Mock

import pytest

import src.dashboard_server as ds
from src.dashboard_server import DashboardHandler


def _handler(path: str = "/") -> DashboardHandler:
    h = DashboardHandler.__new__(DashboardHandler)
    h.path = path
    h.headers = {}
    h.rfile = io.BytesIO()
    h.wfile = io.BytesIO()
    h.repo = Mock()
    h.module_console = Mock()
    h.mimic_ops = Mock()
    h.send_response = Mock()
    h.send_header = Mock()
    h.end_headers = Mock()
    h._send_json = Mock()
    h._send_html = Mock()
    h._send_bytes = Mock()
    return h


def test_read_json_body_handles_invalid_length_and_invalid_json() -> None:
    h = _handler()
    h._read_json_body = DashboardHandler._read_json_body.__get__(h, DashboardHandler)

    h.headers = {"Content-Length": "abc"}
    assert h._read_json_body() == {}

    payload = b"[1,2,3]"
    h.headers = {"Content-Length": str(len(payload))}
    h.rfile = io.BytesIO(payload)
    assert h._read_json_body() == {}

    payload2 = b'{"ok": true}'
    h.headers = {"Content-Length": str(len(payload2))}
    h.rfile = io.BytesIO(payload2)
    assert h._read_json_body() == {"ok": True}


def test_do_get_api_statuses_and_error_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    h = _handler("/api/module/status?window=5&limit=2")
    h.module_console.status.return_value = {"error": "boom"}
    h.do_GET()
    assert h._send_json.call_args.kwargs["status"] == 500

    h2 = _handler("/api/module/check?skip_gateway=yes")
    h2.module_console.check.return_value = {"ok": True}
    h2.do_GET()
    h2.module_console.check.assert_called_once_with(skip_gateway=True)
    assert h2._send_json.call_args.kwargs["status"] == 200

    h3 = _handler("/api/module/logs?target=presales&tail=50")
    h3.module_console.logs.return_value = {"error": "bad target"}
    h3.do_GET()
    assert h3._send_json.call_args.kwargs["status"] == 500

    h4 = _handler("/api/download-cookie-plugin")
    h4.mimic_ops.export_cookie_plugin_bundle.side_effect = FileNotFoundError("missing bundle")
    h4.do_GET()
    assert h4._send_json.call_args.kwargs["status"] == 404

    h5 = _handler("/api/logs/content?file=app/x.log&page=2&size=33&search=err")
    h5.mimic_ops.read_log_content.return_value = {"success": False, "error": "not found"}
    h5.do_GET()
    kwargs = h5.mimic_ops.read_log_content.call_args.kwargs
    assert kwargs["page"] == 2
    assert kwargs["size"] == 33
    assert kwargs["search"] == "err"
    assert h5._send_json.call_args.kwargs["status"] == 404

    h6 = _handler("/api/logs/realtime/stream?file=presales&tail=1")
    h6._send_json = DashboardHandler._send_json.__get__(h6, DashboardHandler)
    h6.mimic_ops.read_log_content.return_value = {"success": True, "lines": ["L1"]}

    def _sleep_raise(_sec: int) -> None:
        raise BrokenPipeError

    monkeypatch.setattr(ds.time, "sleep", _sleep_raise)
    h6.do_GET()
    assert h6.send_response.called


def test_do_get_sqlite_and_generic_exception_handlers() -> None:
    h = _handler("/api/summary")
    h.repo.get_summary.side_effect = sqlite3.Error("db fail")
    h.do_GET()
    assert "Database error" in h._send_json.call_args.args[0]["error"]
    assert h._send_json.call_args.kwargs["status"] == 500

    h2 = _handler("/api/summary")
    h2.repo.get_summary.side_effect = RuntimeError("unknown fail")
    h2.do_GET()
    assert "unknown fail" in h2._send_json.call_args.args[0]["error"]
    assert h2._send_json.call_args.kwargs["status"] == 500


def test_do_post_routes_and_status_codes() -> None:
    h = _handler("/api/module/control")
    h._read_json_body = Mock(return_value={"action": "bad", "target": "all"})
    h.module_console.control.return_value = {"error": "unsupported"}
    h.do_POST()
    h.module_console.control.assert_called_once_with(action="bad", target="all")
    assert h._send_json.call_args.kwargs["status"] == 400

    h2 = _handler("/api/service/control")
    h2._read_json_body = Mock(return_value={"action": "suspend"})
    h2.mimic_ops.service_control.return_value = {"success": True, "status": "suspended"}
    h2.do_POST()
    h2.mimic_ops.service_control.assert_called_once_with(action="suspend")
    assert h2._send_json.call_args.kwargs["status"] == 200

    h3 = _handler("/api/parse-cookie")
    h3._read_json_body = Mock(return_value={"text": ""})
    h3.mimic_ops.parse_cookie_text.return_value = {"success": False, "error": "empty"}
    h3.do_POST()
    assert h3._send_json.call_args.kwargs["status"] == 400

    h4 = _handler("/api/reset-database")
    h4._read_json_body = Mock(return_value={"type": "all"})
    h4.mimic_ops.reset_database.return_value = {"success": True, "results": {}}
    h4.do_POST()
    h4.mimic_ops.reset_database.assert_called_once_with(db_type="all")
    assert h4._send_json.call_args.kwargs["status"] == 200

    h5 = _handler("/api/save-template")
    h5._read_json_body = Mock(return_value={"weight_template": "A", "volume_template": "B"})
    h5.mimic_ops.save_template.return_value = {"success": True}
    h5.do_POST()
    h5.mimic_ops.save_template.assert_called_once_with(weight_template="A", volume_template="B")

    h6 = _handler("/api/save-markup-rules")
    h6._read_json_body = Mock(return_value={"markup_rules": {"a": 1}})
    h6.mimic_ops.save_markup_rules.return_value = {"success": False, "error": "bad"}
    h6.do_POST()
    assert h6._send_json.call_args.kwargs["status"] == 400

    h7 = _handler("/api/test-reply")
    h7._read_json_body = Mock(return_value={"message": "hi"})
    h7.mimic_ops.test_reply.return_value = {"success": True, "reply": "ok"}
    h7.do_POST()
    h7.mimic_ops.test_reply.assert_called_once_with({"message": "hi"})


def test_do_post_not_found_and_exception_path() -> None:
    h = _handler("/api/not-found")
    h.do_POST()
    assert h._send_json.call_args.kwargs["status"] == 404

    h2 = _handler("/api/service/recover")
    h2._read_json_body = Mock(side_effect=RuntimeError("boom"))
    h2.do_POST()
    assert h2._send_json.call_args.kwargs["status"] == 500
    assert "boom" in h2._send_json.call_args.args[0]["error"]
