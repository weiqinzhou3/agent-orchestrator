from __future__ import annotations


def register(project_subparsers) -> None:
    status_parser = project_subparsers.add_parser("status", help="Show project status")
    status_parser.add_argument("--project", required=True)
    status_parser.set_defaults(handler=_handle_status)

    advance_parser = project_subparsers.add_parser("advance", help="Advance project to the next step")
    advance_parser.add_argument("--project", required=True)
    advance_parser.set_defaults(handler=_handle_advance)

    request_close_parser = project_subparsers.add_parser("request-close", help="Request project close approval")
    request_close_parser.add_argument("--project", required=True)
    request_close_parser.set_defaults(handler=_handle_request_close)


def _handle_status(args) -> int:
    return 0


def _handle_advance(args) -> int:
    return 0


def _handle_request_close(args) -> int:
    return 0
