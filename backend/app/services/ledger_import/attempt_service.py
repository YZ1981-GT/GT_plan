"""账套导入 attempt 的生命周期与三次 base token CAS
（spec platform-global-display-settings-closure 任务 8 / AC-15~AC-17）。

设计要点（design §5、§13 第 7 条）：

1. **attempt 是恢复的唯一证据**：submit / seal / activation 三次都要在锁内
   校验「当前 active dataset UUID + unit contract digest」等于 detect 时拿到的
   base token；任一漂移即拒绝（否则会把「基于旧 active 算出的金额」激活成新 active）。
2. **`current_phase` 仅显示**：它记录进度用于 UI，**不参与任何判定**——
   把 phase 当状态机会让「phase 落后于实际」时做出错误决定。
3. **sealed + 全一致 ⇒ activation-only**：若合同 / bundle / row counts / post-hash /
   base token 全部一致，恢复时**不再重跑 converter/normalizer**，直接走激活。
   这是「重启后不重复换算一次」的核心（AC-17）。
4. **其他 retry 先清旧 stage 再建新 attempt**：半成品 stage 留着会被后续
   merge 读到，形成「混合两批数据」的静默错误。
5. **本模块只做判定与状态流转，不执行四表写入**：写入由 pipeline / activation
   在项目年度锁内完成（service 只 flush，router 统一 commit）。

🔴 本模块不在共享 PG 上做写入型验收：真库只跑只读 inspector。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset_models import LedgerImportAttempt, LedgerImportAttemptStatus

#: attempt 状态机的合法流转（只允许这些边；其他一律拒绝）。
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "building": frozenset({"sealed", "cleanup_pending"}),
    "sealed": frozenset({"activating", "cleanup_pending"}),
    "activating": frozenset({"activated", "cleanup_pending"}),
    "activated": frozenset({"cleanup_pending"}),
    "cleanup_pending": frozenset({"cleanup_done"}),
    "cleanup_done": frozenset(),
}

#: `current_phase` 的**显示用**取值（不参与判定，故不做闭集强校验，
#: 但登记在此便于前端展示与日志对齐）。
DISPLAY_PHASES = (
    "detect",
    "bundle_stored",
    "staged_writing",
    "staged_written",
    "sealed",
    "activating",
    "activated",
    "cleanup",
)


class AttemptStateError(Exception):
    """attempt 状态或 base token 不允许本次操作。"""


class BaseTokenDriftError(AttemptStateError):
    """base token（active dataset UUID + contract digest）已漂移。"""


@dataclass(frozen=True)
class BaseToken:
    """detect 时拿到的 base token：active dataset UUID + 单位合同 digest。

    🔴 **不含 dataset version**：design §13 第 7 条明确「base token 仅
    dataset UUID + unit contract digest，不新增 dataset version」。加 version
    会让「同一数据集重新计算合同」这类合法操作被误判为漂移。
    """

    dataset_id: UUID | None
    unit_contract_digest: str | None

    def matches(self, other: "BaseToken") -> bool:
        return (
            self.dataset_id == other.dataset_id
            and self.unit_contract_digest == other.unit_contract_digest
        )

    def describe(self) -> str:
        ds = str(self.dataset_id) if self.dataset_id else "<none>"
        digest = (self.unit_contract_digest or "<none>")[:12]
        return f"dataset={ds} contract={digest}…"


def assert_transition(current: str, target: str) -> None:
    """校验状态机边；非法流转抛 `AttemptStateError`。"""
    allowed = ALLOWED_TRANSITIONS.get(current)
    if allowed is None:
        raise AttemptStateError(f"未知的 attempt 状态 {current!r}")
    if target not in allowed:
        raise AttemptStateError(
            f"非法状态流转 {current} → {target}（允许：{sorted(allowed) or '无'}）"
        )


def assert_base_token(attempt: LedgerImportAttempt, current: BaseToken) -> None:
    """三次 CAS 共用：attempt 记录的 base token 必须等于**当前** base token。

    🔴 两个方向都要判：
    - attempt 记的 base 与当前不同 ⇒ 有人在这期间切了 active ⇒ 拒绝；
    - attempt 的 base 为 None 而当前有 active ⇒ 说明 attempt 是「首次无 active」
      时期建的，现在环境已变 ⇒ 同样拒绝（否则会基于空 base 激活）。
    """
    recorded = BaseToken(
        dataset_id=attempt.base_dataset_id,
        unit_contract_digest=attempt.base_unit_contract_digest,
    )
    if not recorded.matches(current):
        raise BaseTokenDriftError(
            "base token 已漂移："
            f"attempt 记录 {recorded.describe()}，当前 {current.describe()}"
        )


@dataclass(frozen=True)
class SealEvidence:
    """seal 时冻结的证据；activation-only 恢复要求全部逐项一致。"""

    unit_contract_digest: str | None
    bundle_digest: str | None
    row_counts: dict[str, int]
    post_hash: str | None

    def matches(self, other: "SealEvidence") -> bool:
        return (
            self.unit_contract_digest == other.unit_contract_digest
            and self.bundle_digest == other.bundle_digest
            and self.row_counts == other.row_counts
            and self.post_hash == other.post_hash
        )


def can_activation_only(
    attempt: LedgerImportAttempt,
    *,
    current: BaseToken,
    evidence: SealEvidence,
) -> bool:
    """判定能否「sealed 且全一致 ⇒ activation-only（不重跑 converter）」。

    五个条件**全部**满足才返回 True（缺一就要重跑，否则会激活半成品）：
    1. 状态是 `sealed`；
    2. base token 与当前一致；
    3. 单位合同 digest 一致；
    4. bundle digest 一致；
    5. row counts + post hash 一致。
    """
    if attempt.status != LedgerImportAttemptStatus.sealed.value:
        return False
    try:
        assert_base_token(attempt, current)
    except BaseTokenDriftError:
        return False
    sealed = SealEvidence(
        unit_contract_digest=attempt.unit_contract_digest,
        bundle_digest=attempt.bundle_digest,
        row_counts=(attempt.unit_confirmation or {}).get("row_counts") or {},
        post_hash=(attempt.unit_confirmation or {}).get("post_hash"),
    )
    return sealed.matches(evidence)


# ── 持久化入口（只 flush，不 commit）────────────────────────


async def create_attempt(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    upload_token: str,
    payload_style: Literal["account_chart", "ledger"],
    unit_confirmation: dict[str, Any],
    base: BaseToken,
    unit_contract_digest: str | None,
    bundle_digest: str | None,
    created_by: UUID | None = None,
) -> LedgerImportAttempt:
    """submit 时建 attempt（`building`）。

    🔴 **先清旧 stage 再建新 attempt**：调用方必须在本函数之前清掉同项目同年度
    的残留 stage 行（`clear_stale_stage`），否则新 attempt 会与旧 stage 混读。
    本函数只在 `payload_style` / `upload_token` 上做基本校验，不做清理——
    清理要按 dataset_id 逐表删，属调用方的事务边界。
    """
    if payload_style not in ("account_chart", "ledger"):
        raise AttemptStateError(f"非法 payload_style {payload_style!r}")
    if not upload_token:
        raise AttemptStateError("upload_token 不能为空")
    attempt = LedgerImportAttempt(
        project_id=project_id,
        year=year,
        dataset_id=None,
        base_dataset_id=base.dataset_id,
        base_unit_contract_digest=base.unit_contract_digest,
        upload_token=upload_token,
        status=LedgerImportAttemptStatus.building.value,
        current_phase="bundle_stored",
        payload_style=payload_style,
        unit_confirmation=unit_confirmation,
        unit_contract_digest=unit_contract_digest,
        bundle_digest=bundle_digest,
        created_by=created_by,
    )
    db.add(attempt)
    await db.flush()
    return attempt


async def seal_attempt(
    db: AsyncSession,
    attempt: LedgerImportAttempt,
    *,
    current: BaseToken,
    evidence: SealEvidence,
) -> LedgerImportAttempt:
    """seal：第二次 CAS，并把证据写进 `unit_confirmation` 供 activation-only 复用。"""
    assert_transition(attempt.status, LedgerImportAttemptStatus.sealed.value)
    assert_base_token(attempt, current)
    attempt.status = LedgerImportAttemptStatus.sealed.value
    attempt.current_phase = "sealed"
    attempt.unit_contract_digest = evidence.unit_contract_digest
    attempt.bundle_digest = evidence.bundle_digest
    # 证据写进 unit_confirmation（保留原键，只补 row_counts / post_hash）
    merged = dict(attempt.unit_confirmation or {})
    merged["row_counts"] = evidence.row_counts
    merged["post_hash"] = evidence.post_hash
    attempt.unit_confirmation = merged
    await db.flush()
    return attempt


async def begin_activation(
    db: AsyncSession,
    attempt: LedgerImportAttempt,
    *,
    current: BaseToken,
) -> LedgerImportAttempt:
    """进入 activating：第三次 CAS。

    🔴 这是**最后一次**能拦住「active 已被别人换掉」的机会。进入 activating 后
    写入方按 `attempt` 的 stage 数据合并，若此时 active 已变，合并结果会挂到错的
    数据集上。
    """
    assert_transition(attempt.status, LedgerImportAttemptStatus.activating.value)
    assert_base_token(attempt, current)
    attempt.status = LedgerImportAttemptStatus.activating.value
    attempt.current_phase = "activating"
    await db.flush()
    return attempt


async def finish_activation(
    db: AsyncSession,
    attempt: LedgerImportAttempt,
    *,
    dataset_id: UUID,
) -> LedgerImportAttempt:
    """激活完成：记下新 dataset_id 并转 `activated`。"""
    assert_transition(attempt.status, LedgerImportAttemptStatus.activated.value)
    attempt.dataset_id = dataset_id
    attempt.status = LedgerImportAttemptStatus.activated.value
    attempt.current_phase = "activated"
    await db.flush()
    return attempt


async def mark_cleanup(
    db: AsyncSession,
    attempt: LedgerImportAttempt,
    *,
    done: bool = False,
) -> LedgerImportAttempt:
    """进入/完成清理。失败时调用方应留下 `cleanup_pending` 供后续补偿。"""
    target = (
        LedgerImportAttemptStatus.cleanup_done.value
        if done
        else LedgerImportAttemptStatus.cleanup_pending.value
    )
    assert_transition(attempt.status, target)
    attempt.status = target
    attempt.current_phase = "cleanup"
    await db.flush()
    return attempt


async def load_latest_attempt(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
) -> LedgerImportAttempt | None:
    """取该项目年度最新一个 attempt（恢复入口用）。

    🔴 按 `created_at DESC, id DESC` 取：`created_at` 有 `server_default=now()`
    但同一事务里多行可能同刻，用 id 兜底保证确定性。
    """
    stmt = (
        sa.select(LedgerImportAttempt)
        .where(
            LedgerImportAttempt.project_id == project_id,
            LedgerImportAttempt.year == year,
        )
        .order_by(LedgerImportAttempt.created_at.desc(), LedgerImportAttempt.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()
