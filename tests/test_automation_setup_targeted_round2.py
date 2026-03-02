from __future__ import annotations

from src.modules.messages.setup import AutomationSetupService


def test_load_yaml_handles_non_dict_config_file(temp_dir) -> None:
    config_path = temp_dir / "config.yaml"
    config_path.write_text("- just\n- a\n- list\n", encoding="utf-8")

    service = AutomationSetupService(config_path=str(config_path))
    data, existed = service._load_yaml()
    assert existed is True
    assert data == {}


def test_load_yaml_uses_example_and_handles_non_dict(temp_dir) -> None:
    config_dir = temp_dir / "nested" / "cfg"
    config_path = config_dir / "config.yaml"
    example = config_dir / "config.example.yaml"
    example.parent.mkdir(parents=True, exist_ok=True)
    example.write_text("- demo\n", encoding="utf-8")

    service = AutomationSetupService(config_path=str(config_path))
    data, existed = service._load_yaml()
    assert existed is False
    assert data == {}


def test_load_yaml_returns_empty_when_no_files(temp_dir) -> None:
    config_path = temp_dir / "new" / "config.yaml"
    service = AutomationSetupService(config_path=str(config_path))
    data, existed = service._load_yaml()
    assert existed is False
    assert data == {}
