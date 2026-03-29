from __future__ import annotations

from .entities import GateDecision


def parse_review_payload(payload: dict) -> GateDecision:
    raise NotImplementedError("review parsing is out of scope for phase-01")
