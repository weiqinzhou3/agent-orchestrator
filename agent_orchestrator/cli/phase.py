from __future__ import annotations


def register(phase_subparsers) -> None:
    run_parser = phase_subparsers.add_parser("run", help="Run a phase")
    run_parser.add_argument("--project", required=True)
    run_parser.add_argument("--phase", required=True)
    run_parser.set_defaults(handler=_handle_run)


def _handle_run(args) -> int:
    return 0
