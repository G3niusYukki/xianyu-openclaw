"""技能文档与 CLI 契约测试。"""

import argparse
import re
from pathlib import Path

from src.cli import build_parser

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _collect_cli_commands(parser: argparse.ArgumentParser) -> set[str]:
    sub_actions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not sub_actions:
        return set()
    return set(sub_actions[0].choices.keys())


def test_skill_markdown_files_exist() -> None:
    skill_docs = sorted(SKILLS_DIR.glob("xianyu-*/SKILL.md"))
    assert len(skill_docs) >= 4


def test_skill_markdown_has_required_frontmatter() -> None:
    for md_path in SKILLS_DIR.glob("xianyu-*/SKILL.md"):
        content = md_path.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "name:" in content
        assert "description:" in content


def test_skill_examples_match_cli_commands() -> None:
    parser = build_parser()
    cli_commands = _collect_cli_commands(parser)

    referenced_commands = set()
    pattern = re.compile(r"python\s+-m\s+src\.cli\s+([a-zA-Z0-9_-]+)")

    for md_path in SKILLS_DIR.glob("xianyu-*/SKILL.md"):
        content = md_path.read_text(encoding="utf-8")
        referenced_commands.update(pattern.findall(content))

    # xianyu-content 主要是纯文本生成，不强制命令示例
    referenced_commands.discard("")
    assert referenced_commands
    assert referenced_commands.issubset(cli_commands)


def test_legacy_python_skill_packages_are_deprecated() -> None:
    legacy_pkgs = sorted(SKILLS_DIR.glob("xianyu_*"))
    assert legacy_pkgs
    for pkg in legacy_pkgs:
        init_file = pkg / "__init__.py"
        assert init_file.exists()
        content = init_file.read_text(encoding="utf-8")
        assert "Deprecated legacy Python skill package" in content
