"""账套导入恢复判定：`activation_only` vs 全量重建
（spec platform-global-display-settings-closure 任务 8 / design §5 恢复段）。

恢复入口（`recover_jobs` / `resume_from_checkpoint`）**只读 attempt**，不读
`ImportJob.current_phase`（后者仅作进度显示，不能授权复用 staged 行）。

本模块把「该走哪条恢复路径」收敛成**纯判定**，三条结论：

| 结论 | 条件 |
|---|---|
| `activation_only` | attempt 是 `sealed` **且** base token / contract digest / bundle digest / row_counts / post_hash **全部**与当前一致 ⇒ 不再跑 converter/normalizer，直接激活 |
| `resume_finish` | attempt 是 `activated` ⇒ 只补 job/queue 收尾，不碰数据 |
| `rebuild` | 其他一切情况（building / activating 中途 / cleanup_pending / 证据不一致）⇒ 先完成清理，再造新 attempt 全量重建 |

🔴 **为什么 `activating` 不算可续**：它意味着「已经动过 active 数据集」。
此时再判「能否 activation-only」会重复激活；正确处置是清理后重建
（`begin_activation` 已做过第三次 CAS，但激活本身的原子性由
`activate_dataset` 在一个事务里保证，中途失败即整单回滚）。

🔴 本模块只判定，不执行清理/重建（那是调用方在项目年度锁内的事）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset_models import LedgerImportAttempt
from app.services.ledger_import.attempt_service import (
    SealEvidence,
    can_activation_only,
)

RecoveryAction = Literal["activation_only", "resume_finish", "rebuild"]


@dataclass(frozen=True)
class RecoveryDecision:
    """恢复判定结果（供调用方直接分支）。"""

    action: RecoveryAction
    attempt_id: UUID | None
    reason: str
    #: 只有 `activation_only` 时非空：可直接激活的目标 dataset（staged）
    staged_dataset_id: UUID | None = None


async def decide_recovery(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    job_options: dict[str, Any] | None = None,
) -> RecoveryDecision:
    """判定该 job 的恢复路径。

    `job_options` 是 `ImportJob.options`：优先用其中的 `attempt_id` 精确定位
    attempt（并发提交时按 project+year 反查会取到别人的 attempt）。
    取不到时才回退到「该项目年度最新 attempt」——并在 reason 里写明来源。
    """
    from app.services.ledger_import.base_token_resolver import resolve_base_token

    attempt: LedgerImportAttempt | None = None
    source = ""
    raw_attempt_id = (job_options or {}).get("attempt_id")
    if raw_attempt_id:
        try:
            attempt_uuid = UUID(str(raw_attempt_id))
        except (ValueError, TypeError):
            attempt_uuid = None
        if attempt_uuid is not None:
            attempt = (
                await db.execute(
                    sa.select(LedgerImportAttempt).where(
                        LedgerImportAttempt.id == attempt_uuid
                    )
                )
            ).scalars().first()
            source = "job.options.attempt_id"

    if attempt is None:
        attempt = (
            await db.execute(
                sa.select(LedgerImportAttempt)
                .where(
                    LedgerImportAttempt.project_id == project_id,
                    LedgerImportAttempt.year == year,
                )
                .order_by(
                    LedgerImportAttempt.created_at.desc(),
                    LedgerImportAttempt.id.desc(),
                )
                .limit(1)
            )
        ).scalars().first()
        source = "latest_by_project_year"

    if attempt is None:
        return RecoveryDecision(
            action="rebuild",
            attempt_id=None,
            reason="没有 attempt（旧 job / attempt 从未创建）⇒ 全量重建",
        )

    status = str(getattr(attempt, "status", "") or "")

    # `activated`：只补 job/queue 收尾
    if status == "activated":
        return RecoveryDecision(
            action="resume_finish",
            attempt_id=attempt.id,
            reason=f"attempt 已 activated（{source}）⇒ 只补收尾",
        )

    # 其他状态：判能否 activation-only
    if status == "sealed":
        current = await resolve_base_token(db, project_id=project_id, year=year)
        evidence = SealEvidence(
            unit_contract_digest=attempt.unit_contract_digest,
            bundle_digest=attempt.bundle_digest,
            row_counts=(attempt.unit_confirmation or {}).get("row_counts") or {},
            post_hash=(attempt.unit_confirmation or {}).get("post_hash"),
        )
        if can_activation_only(attempt, current=current, evidence=evidence):
            staged = getattr(attempt, "dataset_id", None)
            return RecoveryDecision(
                action="activation_only",
                attempt_id=attempt.id,
                reason=(
                    f"attempt sealed 且五项证据全一致（{source}）⇒ "
                    "不重跑 converter，直接激活"
                ),
                staged_dataset_id=staged,
            )
        return RecoveryDecision(
            action="rebuild",
            attempt_id=attempt.id,
            reason=(
                f"attempt sealed 但证据不一致（{source}）⇒ "
                "先清理再全量重建"
            ),
        )

    # building / activating / cleanup_pending / cleanup_done
    return RecoveryDecision(
        action="rebuild",
        attempt_id=attempt.id,
        reason=(
            f"attempt 状态 {status}（{source}）不可续用"
            "（activating 意味着动过 active，重复激活不安全）⇒ 清理后全量重建"
        ),
    )


async def assert_rebuild_cleanup_needed(
    db: AsyncSession,
    *,
    attempt_id: UUID | None,
) -> bool:
    """判 `rebuild` 前是否需要先清理。返回 True 表示有残留 stage 需清。

    🔴 只读判定，不执行清理：清理要按 dataset_id 逐表删，属调用方事务边界。
    重复调用幂等（无 attempt / 无 dataset 一律 False）。
    """
    if attempt_id is None:
        return False
    attempt = (
        await db.execute(
            sa.select(LedgerImportAttempt).where(LedgerImportAttempt.id == attempt_id)
        )
    ).scalars().first()
    if attempt is None:
        return False
    if str(getattr(attempt, "status", "") or "") in ("cleanup_done",):
        return False
    return getattr(attempt, "dataset_id", None) is not None or str(
        getattr(attempt, "status", "") or ""
    ) in ("building", "activating", "cleanup_pending")
