"""报价 CLI 契约测试。"""

from src.cli import build_parser


def test_quote_cli_actions_include_setup_and_doctor() -> None:
    parser = build_parser()
    args = parser.parse_args(["quote", "--action", "doctor"])
    assert args.command == "quote"
    assert args.action == "doctor"

    args = parser.parse_args(
        [
            "quote",
            "--action",
            "setup",
            "--mode",
            "cost_table_plus_markup",
            "--origin-city",
            "安徽",
            "--cost-table-dir",
            "data/quote_costs",
        ]
    )
    assert args.command == "quote"
    assert args.action == "setup"
    assert args.mode == "cost_table_plus_markup"
