"""交付 readiness 共享结果类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReadinessBlocker:
    """一条硬闸门或软警告。"""

    code: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceStatus:
    """某一数据源的 readiness 摘要。"""

    available: bool = False
    count: int = 0
    stale_count: int = 0
    detail: dict[str, Any] = field(default_factory=dict)


__all__ = ["ReadinessBlocker", "SourceStatus"]
