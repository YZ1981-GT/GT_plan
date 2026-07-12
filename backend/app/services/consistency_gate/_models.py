"""一致性门控 — 数据模型"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CheckItem:
    """单项检查结果"""

    check_name: str
    passed: bool
    details: str = ""
    severity: str = "warning"  # blocking / warning


@dataclass
class ConsistencyResult:
    """一致性检查总结果"""

    overall: str = "pass"  # pass / fail
    checks: list[CheckItem] = field(default_factory=list)

    @property
    def has_blocking_failures(self) -> bool:
        return any(not c.passed and c.severity == "blocking" for c in self.checks)
