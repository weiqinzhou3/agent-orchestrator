from __future__ import annotations

from .entities import GateDecision
from .enums import GateDecisionType


def parse_review_payload(payload: dict) -> GateDecision:
    if not isinstance(payload, dict):
        return GateDecision(decision=GateDecisionType.INVALID_FORMAT)

    try:
        decision = GateDecisionType(payload["decision"])
    except (KeyError, TypeError, ValueError):
        decision = GateDecisionType.INVALID_FORMAT

    blockers = list(payload.get("blockers") or [])
    important_items = list(payload.get("important_items") or [])
    later_items = list(payload.get("later_items") or [])

    return GateDecision(
        decision=decision,
        blocker_count=int(payload.get("blocker_count", len(blockers))),
        important_count=int(payload.get("important_count", len(important_items))),
        later_count=int(payload.get("later_count", len(later_items))),
        blockers=blockers,
        important_items=important_items,
        later_items=later_items,
    )
