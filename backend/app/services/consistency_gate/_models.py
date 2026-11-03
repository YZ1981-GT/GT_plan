"""一致性门控 — 五态数据模型（唯一定义）

ADR-FHIC-14 第 1 点。外部通过 __init__ 导入，禁止在 _models 之外直接构造 CheckItem。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 五态状态
# ---------------------------------------------------------------------------

Status = Literal["passed", "failed", "not_executed", "not_applicable", "error"]

_BLOCKING_STATUSES: frozenset[Status] = frozenset({"failed", "not_executed", "error"})


# ---------------------------------------------------------------------------
# CheckItem
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CheckItem:
    """单项检查结果"""

    check_name: str
    status: Status
    passed: bool  # 由工厂按 status=="passed" 填写
    details: str = ""
    reason: str = ""
    branch_id: str = ""
    severity: str = "warning"  # blocking / warning

    # ---- 判定辅助 ----

    @property
    def would_block_when_enforced(self) -> bool:
        """enforce 模式下此项是否阻断（阻断级 ∧ status ∈ failed/not_executed/error）"""
        return self.severity == "blocking" and self.status in _BLOCKING_STATUSES

    @property
    def has_blocking_failures(self) -> bool:
        """阻断级 ∧ failed — 与 HEAD 逐项同义"""
        return self.severity == "blocking" and self.status == "failed"


# ---------------------------------------------------------------------------
# ConsistencyResult
# ---------------------------------------------------------------------------

@dataclass
class ConsistencyResult:
    """一致性检查总结果"""

    overall: str = "pass"  # pass / fail
    checks: list[CheckItem] = field(default_factory=list)

    @property
    def has_blocking_failures(self) -> bool:
        return any(c.has_blocking_failures for c in self.checks)

    @property
    def would_block_when_enforced(self) -> bool:
        return any(c.would_block_when_enforced for c in self.checks)

    def status_counts(self) -> dict[str, int]:
        """返回五态计数"""
        counts: dict[str, int] = {
            "passed": 0,
            "failed": 0,
            "not_executed": 0,
            "not_applicable": 0,
            "error": 0,
        }
        for c in self.checks:
            counts[c.status] = counts.get(c.status, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# 展示口径（需求 16.5：看板 / 热力图与 consistency-check 同一套五态读法）
# ---------------------------------------------------------------------------

FIVE_STATES: tuple[Status, ...] = ("passed", "failed", "not_executed", "not_applicable", "error")


def check_status(check: object) -> str:
    """检查项五态；没有 ``status`` 属性的旧对象按 ``passed`` 记 passed / failed（只有测试替身会这样）。"""
    status = getattr(check, "status", None)
    if status in FIVE_STATES:
        return str(status)
    return "passed" if getattr(check, "passed", False) else "failed"


def five_state_counts(checks: list) -> dict[str, int]:
    """五态计数（五个键都在，没有的计 0）。"""
    counts = {state: 0 for state in FIVE_STATES}
    for check in checks:
        counts[check_status(check)] += 1
    return counts


def not_passed_checks(checks: list) -> list[dict[str, str]]:
    """非通过项逐项的状态与原因（未执行 / 不适用 / 异常都带原因，不并成「未通过」）。"""
    return [
        {"check_name": check.check_name, "status": check_status(check),
         "reason": getattr(check, "reason", "") or "", "branch_id": getattr(check, "branch_id", "") or "",
         "severity": getattr(check, "severity", "") or ""}
        for check in checks if check_status(check) != "passed"
    ]


# ---------------------------------------------------------------------------
# 工厂函数 — 唯一的 CheckItem 构造入口
# ---------------------------------------------------------------------------

def _ok(
    check_name: str,
    *,
    details: str = "",
    severity: str = "warning",
) -> CheckItem:
    """通过"""
    return CheckItem(
        check_name=check_name,
        status="passed",
        passed=True,
        details=details,
        severity=severity,
    )


def _fail(
    check_name: str,
    *,
    reason: str = "",
    details: str = "",
    severity: str = "warning",
) -> CheckItem:
    """失败"""
    return CheckItem(
        check_name=check_name,
        status="failed",
        passed=False,
        reason=reason,
        details=details,
        severity=severity,
    )


def _not_executed(
    check_name: str,
    *,
    branch_id: str,
    reason: str = "",
    severity: str = "warning",
) -> CheckItem:
    """未执行（数据缺失 / 未保存 / 部分数据）"""
    return CheckItem(
        check_name=check_name,
        status="not_executed",
        passed=False,
        reason=reason,
        branch_id=branch_id,
        severity=severity,
    )


def _not_applicable(
    check_name: str,
    *,
    branch_id: str,
    reason: str = "",
    severity: str = "warning",
) -> CheckItem:
    """不适用（在线表单 / 已裁剪 / 结构性不可用）"""
    return CheckItem(
        check_name=check_name,
        status="not_applicable",
        passed=False,
        reason=reason,
        branch_id=branch_id,
        severity=severity,
    )


def _error(
    check_name: str,
    *,
    branch_id: str,
    reason: str = "",
    severity: str = "warning",
) -> CheckItem:
    """检查异常"""
    return CheckItem(
        check_name=check_name,
        status="error",
        passed=False,
        reason=reason,
        branch_id=branch_id,
        severity=severity,
    )
