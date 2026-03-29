from __future__ import annotations


def register(bootstrap_subparsers) -> None:
    run_parser = bootstrap_subparsers.add_parser("run", help="Run bootstrap")
    run_parser.add_argument("--project", required=True)
    run_parser.add_argument("--force-full", action="store_true")
    run_parser.set_defaults(handler=_handle_run)


def _handle_run(args) -> int:
    return 0
