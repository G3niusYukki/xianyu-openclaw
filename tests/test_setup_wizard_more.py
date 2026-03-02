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

    vals2 = iter(["999", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(vals2))
    gp = sw._choose_gateway_provider()
    assert gp.id == sw.GATEWAY_PROVIDERS[0].id

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
    sw._run_post_start_checks("8080")
    assert called


def test_run_setup_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(sw, "_choose_gateway_provider", lambda: sw.GATEWAY_PROVIDERS[0])
    monkeypatch.setattr(sw, "_choose_content_provider", lambda: sw.CONTENT_PROVIDERS[0])

    def prompt_no_start(text, default=None, required=False, secret=False):
        mapping = {
            "请输入 ANTHROPIC_API_KEY": "gk",
            "请输入 DEEPSEEK_API_KEY": "ck",
            "设置 OPENCLAW_GATEWAY_TOKEN": "tok",
            "设置 AUTH_PASSWORD（后台登录密码）": "pass",
            "设置 AUTH_USERNAME": "admin",
            "设置 OPENCLAW_WEB_PORT": "8080",
            "粘贴 XIANYU_COOKIE_1": "c1",
            "粘贴 XIANYU_COOKIE_2（可留空）": "",
            "是否立即启动容器？[Y/n]": "n",
        }
        return mapping[text]

    monkeypatch.setattr(sw, "_prompt", prompt_no_start)
    rc = sw.run_setup()
    assert rc == 0
    assert (tmp_path / ".env").exists()

    def prompt_start(text, default=None, required=False, secret=False):
        val = prompt_no_start(text, default, required, secret)
        if text == "是否立即启动容器？[Y/n]":
            return "y"
        return val

    monkeypatch.setattr(sw, "_prompt", prompt_start)
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
    sw._run_post_start_checks("8090")
    out = capsys.readouterr().out
    assert "启动完成。打开: http://localhost:8090" in out
    assert "docker compose exec -it openclaw-gateway openclaw devices list" in out


def test_run_setup_same_provider_reuses_gateway_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    gateway = sw.GATEWAY_PROVIDERS[0]

    class SameKeyContent:
        id = "same-key"
        env_key = gateway.env_key
        base_url = "https://x"
        model = "m"

    monkeypatch.setattr(sw, "_choose_gateway_provider", lambda: gateway)
    monkeypatch.setattr(sw, "_choose_content_provider", lambda: SameKeyContent())

    answers = {
        f"请输入 {gateway.env_key}": "k-same",
        "设置 OPENCLAW_GATEWAY_TOKEN": "tok",
        "设置 AUTH_PASSWORD（后台登录密码）": "pass",
        "设置 AUTH_USERNAME": "admin",
        "设置 OPENCLAW_WEB_PORT": "8080",
        "粘贴 XIANYU_COOKIE_1": "c1",
        "粘贴 XIANYU_COOKIE_2（可留空）": "",
        "是否立即启动容器？[Y/n]": "n",
    }
    monkeypatch.setattr(sw, "_prompt", lambda text, **kwargs: answers[text])

    rc = sw.run_setup()
    assert rc == 0
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert f"{gateway.env_key}=k-same" in content
    assert "AI_API_KEY=k-same" in content
