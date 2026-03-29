from __future__ import annotations

from agent_orchestrator.cli.main import build_parser


def test_main_parser_exposes_expected_commands() -> None:
    parser = build_parser()

    namespace = parser.parse_args(["project", "status", "--project", "demo-project"])

    assert namespace.command == "project"
    assert namespace.project_command == "status"
    assert namespace.project == "demo-project"
