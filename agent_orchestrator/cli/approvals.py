from __future__ import annotations


def register(approval_subparsers) -> None:
    approve_parser = approval_subparsers.add_parser("approve", help="Approve a pending approval")
    approve_parser.add_argument("--project", required=True)
    approve_parser.add_argument("--id", required=True)
    approve_parser.add_argument("--actor", required=True)
    approve_parser.set_defaults(handler=_handle_approve)

    reject_parser = approval_subparsers.add_parser("reject", help="Reject a pending approval")
    reject_parser.add_argument("--project", required=True)
    reject_parser.add_argument("--id", required=True)
    reject_parser.add_argument("--actor", required=True)
    reject_parser.set_defaults(handler=_handle_reject)


def _handle_approve(args) -> int:
    return 0


def _handle_reject(args) -> int:
    return 0
