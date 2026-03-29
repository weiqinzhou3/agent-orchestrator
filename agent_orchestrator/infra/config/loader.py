from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppConfig:
    auto_append_later_to_backlog: bool = False


def load_config() -> AppConfig:
    return AppConfig()
