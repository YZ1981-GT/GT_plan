"""F53 / Sprint 8.39: 留档合规保留期策略。

三档分类（requirements §2.K F53 / design D13.4）：
- ``transient``：90 天过期，purge 任务物理删（默认，未被绑定的普通导入）
- ``archived``：10 年过期，元数据永久保留（有 final/eqcr_approved 报表绑定）
- ``legal_hold``：法定保留（诉讼中），永不删除

决策优先级：``legal_hold > archived > transient``。

``compute_retention_class`` 在 activate 阶段调用（见 DatasetService.activate 内
的 F53 hook），根据 dataset 当前的下游绑定关系自动判定类别。

LedgerDataset 当前 **没有** ``legal_hold_flag`` 字段——legal_hold 的触发来自
运维手动设置（如通过 DBA 直接 UPDATE ledger_datasets.source_summary.legal_hold
为 true，或未来的专用 ``PATCH /datasets/{id}/hold`` 端点）。当前实现从
``source_summary.legal_hold`` 字典键中读取该标记，既向后兼容也支持未来扩展。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset_models import LedgerDataset


RetentionClass = Literal["transient", "archived", "legal_hold"]


# 90 天 transient / 10 年 archived；legal_hold 无过期。
# 统一在此声明，purge_old_datasets 与 tests 都以此为单一真源。
TRANSIENT_RETENTION = timedelta(days=90)
ARCHIVED_RETENTION = timedelta(days=365 * 10)


def _dataset_has_legal_hold(dataset: LedgerDataset) -> bool:
    """判断 dataset 是否被标记 legal_hold。

    当前没有独立字段，约定从 ``source_summary.legal_hold`` 读取。
    """
    src = dataset.source_summary or {}
    if not isinstance(src, dict):
        return False
    raw = src.get("legal_hold")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


async def compute_retention_class(
    db: AsyncSession,
    dataset: LedgerDataset,
) -> RetentionClass:
    """为一个 dataset 计算应得的 retention_class。

    顺序：
    1. dataset 被标记 legal_hold → ``"legal_hold"``
    2. dataset 被 ``final`` / ``eqcr_approved`` 审计报表绑定 → ``"archived"``
    3. 否则 → ``"transient"``

    Args:
        db: 异步 session
        dataset: 已加载的 LedgerDataset ORM 对象

    Returns:
        三档之一的字符串字面量
    """
    if _dataset_has_legal_hold(dataset):
        return "legal_hold"

    # 检查是否有 final / eqcr_approved 报表绑定
    # 延迟 import 避免循环依赖（dataset_models → report_models → ...）
    from app.models.report_models import AuditReport, ReportStatus

    count_result = await db.execute(
        sa.select(sa.func.count())
        .select_from(AuditReport)
        .where(
            AuditReport.bound_dataset_id == dataset.id,
            AuditReport.is_deleted == sa.false(),
            AuditReport.status.in_((ReportStatus.final, ReportStatus.eqcr_approved)),
        )
    )
    bound_finals = int(count_result.scalar_one() or 0)
    if bound_finals > 0:
        return "archived"
    return "transient"


def compute_expires_at(retention_class: RetentionClass, now: datetime | None = None) -> datetime | None:
    """给定 retention_class，返回对应的过期时间（``None`` 表示永不过期）。

    Args:
        retention_class: 三档之一
        now: 注入当前时间（测试方便），默认为 ``datetime.now(tz=UTC)``

    Returns:
        - transient → now + 90 天
        - archived  → now + 10 年
        - legal_hold → None（永不过期）
    """
    current = now or datetime.now(timezone.utc)
    if retention_class == "transient":
        return current + TRANSIENT_RETENTION
    if retention_class == "archived":
        return current + ARCHIVED_RETENTION
    # legal_hold
    return None


async def apply_retention_to_artifact(
    db: AsyncSession,
    dataset: LedgerDataset,
    *,
    now: datetime | None = None,
) -> tuple[RetentionClass, datetime | None, UUID | None]:
    """F53 / Sprint 8.40: 在 activate 时同步把 retention 写回 ImportArtifact。

    - dataset 没有关联 artifact（job_id=NULL 或 job.artifact_id=NULL）时静默跳过。
    - 失败不回滚 dataset activate（retention 属于治理信息，不应阻断激活主路径）。

    Returns:
        ``(retention_class, retention_expires_at, artifact_id)``
        三元组；artifact_id=None 表示未找到关联 artifact。
    """
    from app.models.dataset_models import ImportArtifact, ImportJob

    retention_class = await compute_retention_class(db, dataset)
    expires_at = compute_expires_at(retention_class, now=now)

    if dataset.job_id is None:
        return retention_class, expires_at, None

    job_result = await db.execute(
        sa.select(ImportJob.artifact_id).where(ImportJob.id == dataset.job_id)
    )
    artifact_id = job_result.scalar_one_or_none()
    if artifact_id is None:
        return retention_class, expires_at, None

    await db.execute(
        sa.update(ImportArtifact)
        .where(ImportArtifact.id == artifact_id)
        .values(
            retention_class=retention_class,
            retention_expires_at=expires_at,
        )
    )
    return retention_class, expires_at, artifact_id


__all__ = [
    "RetentionClass",
    "TRANSIENT_RETENTION",
    "ARCHIVED_RETENTION",
    "compute_retention_class",
    "compute_expires_at",
    "apply_retention_to_artifact",
]
