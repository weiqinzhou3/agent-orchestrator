from __future__ import annotations

import argparse
from typing import Sequence

from agent_orchestrator.cli import approvals, bootstrap, phase, project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    project_parser = subparsers.add_parser("project", help="Project operations")
    project_subparsers = project_parser.add_subparsers(dest="project_command", required=True)
    project.register(project_subparsers)

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Bootstrap operations")
    bootstrap_subparsers = bootstrap_parser.add_subparsers(dest="bootstrap_command", required=True)
    bootstrap.register(bootstrap_subparsers)

    phase_parser = subparsers.add_parser("phase", help="Phase operations")
    phase_subparsers = phase_parser.add_subparsers(dest="phase_command", required=True)
    phase.register(phase_subparsers)

    approvals_parser = subparsers.add_parser("approvals", help="Approval operations")
    approvals_subparsers = approvals_parser.add_subparsers(dest="approval_command", required=True)
    approvals.register(approvals_subparsers)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
