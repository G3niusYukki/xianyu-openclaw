from pathlib import Path

import pytest

import src.setup_wizard as sw


def test_prompt_and_choose(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert sw._prompt("x", default="d") == "d"

    vals = iter(["", "ok"])
    monkeypatch.setattr("builtins.input", lambda _: next(vals))
    assert sw._prompt("x", required=True) == "ok"

    monkeypatch.setattr("getpass.getpass", lambda _: "sec")
    assert sw._prompt("x", secret=True) == "sec"

    vals3 = iter(["0", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(vals3))
    cp = sw._choose_content_provider()
    assert cp.id == sw.CONTENT_PROVIDERS[0].id


def test_env_read_and_docker_checks(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\nB=\n", encoding="utf-8")
    out = sw._read_existing_env(env)
    assert out["A"] == "1"
    assert sw._read_existing_env(tmp_path / "none") == {}

    monkeypatch.setattr("shutil.which", lambda x: None)
    assert sw._ensure_docker_ready() is False

    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/docker")

    class R:
        def __init__(self, code):
            self.returncode = code

    monkeypatch.setattr("subprocess.run", lambda *a, **k: R(1))
    assert sw._ensure_docker_ready() is False

    monkeypatch.setattr("subprocess.run", lambda *a, **k: R(0))
    assert sw._ensure_docker_ready() is True


def test_post_start_checks(monkeypatch):
    called = []

    class R:
        def __init__(self, out="", err=""):
            self.stdout = out
            self.stderr = err
            self.returncode = 0

    def fake_run(args, **kwargs):
        called.append(args)
        if args[:3] == ["docker", "compose", "logs"]:
            return R("At least one AI provider API key env var is required")
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    sw._run_post_start_checks()
    assert called


def test_run_setup_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(sw, "_choose_content_provider", lambda: sw.CONTENT_PROVIDERS[0])

    def prompt_no_start(text, default=None, required=False, secret=False):
        if "DEEPSEEK_API_KEY" in text:
            return "ck"
        if "XGJ_APP_KEY" in text:
            return "appkey"
        if "XGJ_APP_SECRET" in text:
            return "appsecret"
        if "XGJ_BASE_URL" in text:
            return ""
        if "XIANYU_COOKIE_1" in text:
            return "c1"
        if "XIANYU_COOKIE_2" in text:
            return ""
        if "请选择" in text:
            return "3"
        return ""

    monkeypatch.setattr(sw, "_prompt", prompt_no_start)
    rc = sw.run_setup()
    assert rc == 0
    assert (tmp_path / ".env").exists()

    def prompt_docker(text, default=None, required=False, secret=False):
        if "请选择" in text:
            return "2"
        return prompt_no_start(text, default, required, secret)

    monkeypatch.setattr(sw, "_prompt", prompt_docker)
    monkeypatch.setattr(sw, "_ensure_docker_ready", lambda: False)
    assert sw.run_setup() == 1

    class R:
        def __init__(self, code):
            self.returncode = code

    monkeypatch.setattr(sw, "_ensure_docker_ready", lambda: True)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: R(2))
    assert sw.run_setup() == 2


def test_setup_main_exit(monkeypatch):
    monkeypatch.setattr(sw, "run_setup", lambda: 7)
    with pytest.raises(SystemExit) as e:
        sw.main()
    assert e.value.code == 7


def test_run_post_start_checks_success_prints_actions(monkeypatch, capsys):
    class R:
        def __init__(self, out="", err="", code=0):
            self.stdout = out
            self.stderr = err
            self.returncode = code

    def fake_run(args, **kwargs):
        if args[:3] == ["docker", "compose", "logs"]:
            return R("all good")
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    sw._run_post_start_checks()
    out = capsys.readouterr().out
    assert "启动完成" in out
