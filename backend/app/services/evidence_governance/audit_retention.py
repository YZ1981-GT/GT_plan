"""审计保留判定（Task 7.4, Wave 6）—— R12.4 保留期/Legal Hold 内不可修改删除。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R12, R13
Design: §7.1 审计保留（保留期或 Legal Hold 内禁止修改或删除审计记录）;
        §4.6 不可变墓碑; §5.5 Hold 解除 + retention 到期才可 purge
Properties: P25 (审计事件覆盖, 部分), P27 (保留期边界, 部分)

职责边界（避免与 Task 7.3 重复）：

- Task 7.3 ``retention_legal_hold_service`` 拥有 Legal Hold 闭包、purge 四条件
  （``PurgeConditions`` / ``evaluate_purge_conditions``）与**不可变墓碑创建**
  （``RetentionLegalHoldService.purge`` → ``evidence_tombstones``）。
- 本模块只补 Task 7.4 的 **审计保留判定（R12.4）**：给定 ``archived_at`` + 保留策略天数
  + 是否 Legal Hold，纯函数计算记录是否处于保留期/hold，从而**禁止修改或删除**。
  该判定与 7.3 的 purge 条件正交（7.3 的 ``retention_expired`` 是 purge 输入布尔，
  本模块负责从归档时间 + 策略**推算**该布尔）。

墓碑与审计 transition 的物理不可变由 DB 触发器兜底（V108/V111 append-only /
immutable trigger）；本模块提供 API/服务层的保留窗口判定，可复算（P30 语义）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services.evidence_governance.frozen_contracts import (
    EvidenceErrorCode,
    EvidenceGovernanceError,
)

#: 平台默认保留期（天）；实际以项目保留策略版本为准（R13.1）。
DEFAULT_RETENTION_DAYS = 3650  # 10 年


@dataclass(frozen=True)
class RetentionStatus:
    """审计/证据记录的保留判定结果（R12.4）。"""

    within_retention: bool
    under_legal_hold: bool

    @property
    def mutation_forbidden(self) -> bool:
        """保留期内或 Legal Hold 生效 → 禁止修改/删除（R12.4）。"""
        return self.within_retention or self.under_legal_hold

    @property
    def retention_expired(self) -> bool:
        """保留期已届满（供 Task 7.3 purge 四条件的 ``retention_expired`` 输入）。"""
        return not self.within_retention


def is_within_retention(
    *,
    archived_at: datetime | None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    now: datetime | None = None,
) -> bool:
    """记录是否仍在保留期内（纯函数，可复算）。

    - ``archived_at is None``：尚未归档 → 视为在保留期内（活动审计不得删改）。
    - ``retention_days <= 0``：永久保留 → 恒在保留期内。
    - 否则 ``now < archived_at + retention_days`` 即在保留期内。
    """
    if archived_at is None:
        return True
    if retention_days <= 0:
        return True
    current = now or datetime.now(timezone.utc)
    if archived_at.tzinfo is None:
        archived_at = archived_at.replace(tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current < archived_at + timedelta(days=retention_days)


def evaluate_retention(
    *,
    archived_at: datetime | None,
    under_legal_hold: bool,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    now: datetime | None = None,
) -> RetentionStatus:
    """综合保留期 + Legal Hold 的保留判定（R12.4）。"""
    return RetentionStatus(
        within_retention=is_within_retention(
            archived_at=archived_at, retention_days=retention_days, now=now
        ),
        under_legal_hold=bool(under_legal_hold),
    )


def assert_audit_mutable(status: RetentionStatus) -> None:
    """保留期内或 hold 内禁止修改/删除审计记录（R12.4）→ 抛脱敏错误。

    Legal Hold 优先映射为 ``LEGAL_HOLD_ACTIVE``（423）；仅保留期未届满映射为
    ``VERSION_CONFLICT``（409），语义均为 "目标零变化 / destructive delta=0"。
    """
    if not status.mutation_forbidden:
        return
    raise EvidenceGovernanceError(
        EvidenceErrorCode.LEGAL_HOLD_ACTIVE
        if status.under_legal_hold
        else EvidenceErrorCode.VERSION_CONFLICT,
        "审计记录处于保留期或 Legal Hold，禁止修改或删除",
    )


__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "RetentionStatus",
    "is_within_retention",
    "evaluate_retention",
    "assert_audit_mutable",
]
