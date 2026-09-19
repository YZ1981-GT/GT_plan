"""高风险部署 Health Gate + 回滚演练编排（可执行、纯逻辑，无 DB 副作用）。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 11.2 (Wave 10 — 可执行最终发布门)
Requirements: R11, R12, R13, R14, R15
Design: §8.3 高风险部署 Health Gate、§8.4 Rollback

本模块把 design §8.3 / §8.4 冻结为**可执行判定面**，供预生产 migration health gate 与
完整回滚演练调用。它**不重复**已有构件，而是组合：

  * ``migration_phases.evaluate_cutover_preconditions`` / ``CutoverPreconditions``
    —— 迁移成功 / 无 pending·failed / schema 契约 / alias·backfill 差异 / 无 failed checkpoint /
    备份可恢复 / 队列·配额 就绪。
  * ``migration_phases.production_rollback_plan`` / ``RollbackPlan`` / ``RETAINED_GOVERNANCE_OBJECTS``
    —— 非破坏性回滚（切 flag/adapter、停 enqueue、drain worker、暂停 backfill、兼容读回退），
    保留全部治理对象与 legacy 列。

在既有 cutover 前置校验之上，本模块补齐 design §8.3 明确要求、但 ``CutoverPreconditions``
未单列的两条阻断条件：

  1. **无锁降级 / 跳过约束**（``lockless_degraded``）：任一相关迁移因锁不可得而进入
     “无锁降级 / 跳过约束” 模式 → 不得切 flag / 启 worker / 设新真源（design §8.3）。
  2. **所需锁 / 约束未生效**（``locks_constraints_in_effect``）：immutable 触发器、deferrable
     约束触发器、复合 scope unique、command-root unique、hold 保护约束等未全部生效 → 阻断。

以及 design §8.3 的**备份失败自动响应**：备份失败时**禁止自动执行高风险数据库回滚**；自动响应
只能停止新写、关闭 flag、drain worker、保留现场并告警，由人工确认恢复策略。

单一真源：本模块。不在测试或其它服务内复制这些阻断条件 / 自动响应 / 演练步骤。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.evidence_governance.migration_phases import (
    RETAINED_GOVERNANCE_OBJECTS,
    CutoverPreconditions,
    RollbackPlan,
    evaluate_cutover_preconditions,
    production_rollback_plan,
)

# ─────────────────────────────────────────────────────────────────────────────
# 阻断原因码（低基数、稳定，供审计/指标关联 —— design §8.3 / R12）
# ─────────────────────────────────────────────────────────────────────────────

REASON_MIGRATION_FAILED = "migration_failed"                 # 任一相关迁移失败
REASON_LOCKLESS_DEGRADED = "lockless_degraded_or_skipped_constraint"  # 无锁降级/跳过约束
REASON_PENDING_OR_FAILED_MIGRATION = "pending_or_failed_migration"    # 存在 pending/failed
REASON_LOCKS_NOT_IN_EFFECT = "required_locks_constraints_not_in_effect"
REASON_SCHEMA_CONTRACT = "schema_contract_failed"
REASON_BACKFILL_DIFF = "alias_backfill_diff_over_threshold"
REASON_FAILED_CHECKPOINT = "failed_checkpoint_present"
REASON_BACKUP_NOT_VERIFIED = "backup_not_verified"
REASON_QUOTA_OVER_BUDGET = "pg_pgbouncer_or_queue_quota_over_budget"

#: cutover 前置校验的 failure token → health-gate 稳定原因码映射。
_CUTOVER_FAILURE_TO_REASON: dict[str, str] = {
    "migrations_applied": REASON_MIGRATION_FAILED,
    "pending_or_failed_migration": REASON_PENDING_OR_FAILED_MIGRATION,
    "schema_contract": REASON_SCHEMA_CONTRACT,
    "backfill_coverage": REASON_BACKFILL_DIFF,
    "failed_checkpoint": REASON_FAILED_CHECKPOINT,
    "backup_not_verified": REASON_BACKUP_NOT_VERIFIED,
    "queue_quota": REASON_QUOTA_OVER_BUDGET,
}


# ─────────────────────────────────────────────────────────────────────────────
# Health Gate 判定
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DeploymentHealthGateDecision:
    """预生产高风险部署 health-gate 判定（design §8.3）。

    ``allowed`` 为 True 时，才允许切 feature flag / 启治理 worker / 设新表为写真源。
    任一阻断条件命中 → 三者全部禁止（fail-closed），并携带稳定原因码。
    """

    #: 组合后的 cutover 前置校验（迁移/schema/backfill/checkpoint/backup/quota）。
    cutover: CutoverPreconditions
    #: 迁移是否进入无锁降级 / 跳过约束模式（design §8.3）。恒 False 才放行。
    lockless_degraded: bool
    #: 所需锁 / 约束是否已全部生效（immutable/deferrable trigger、复合 unique 等）。
    locks_constraints_in_effect: bool
    #: 稳定阻断原因码（按固定顺序去重）。
    blocking_reasons: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return not self.blocking_reasons

    # design §8.3：三个动作共用同一门禁（全绿才放行；任一阻断全禁）。
    @property
    def allow_flag_flip(self) -> bool:
        return self.allowed

    @property
    def allow_worker_start(self) -> bool:
        return self.allowed

    @property
    def allow_new_source_of_truth(self) -> bool:
        return self.allowed

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "allow_flag_flip": self.allow_flag_flip,
            "allow_worker_start": self.allow_worker_start,
            "allow_new_source_of_truth": self.allow_new_source_of_truth,
            "lockless_degraded": self.lockless_degraded,
            "locks_constraints_in_effect": self.locks_constraints_in_effect,
            "cutover_failures": self.cutover.failures(),
            "blocking_reasons": list(self.blocking_reasons),
        }


def evaluate_deployment_health_gate(
    *,
    migrations_applied: bool,
    pending_migration_count: int,
    failed_migration_count: int,
    schema_contract_ok: bool,
    backfill_coverage_ratio: float,
    failed_checkpoint_count: int,
    backup_verified: bool,
    queue_quota_ready: bool,
    lockless_degraded: bool,
    locks_constraints_in_effect: bool,
    min_coverage: float = 1.0,
) -> DeploymentHealthGateDecision:
    """评估切 flag / 启 worker 前的 health gate（design §8.3）。

    组合 ``evaluate_cutover_preconditions`` 的七项，再叠加：
      * ``lockless_degraded`` 为 True → 阻断（无锁降级 / 跳过约束）。
      * ``locks_constraints_in_effect`` 为 False → 阻断（所需锁/约束未生效）。

    原因码按 design §8.3 的顺序稳定排列并去重。
    """
    cutover = evaluate_cutover_preconditions(
        migrations_applied=migrations_applied,
        pending_migration_count=pending_migration_count,
        failed_migration_count=failed_migration_count,
        schema_contract_ok=schema_contract_ok,
        backfill_coverage_ratio=backfill_coverage_ratio,
        failed_checkpoint_count=failed_checkpoint_count,
        backup_verified=backup_verified,
        queue_quota_ready=queue_quota_ready,
        min_coverage=min_coverage,
    )

    reasons: list[str] = []
    # 1/3/5/6/7 + schema/checkpoint 来自 cutover 前置校验（映射为稳定原因码）。
    for token in cutover.failures():
        mapped = _CUTOVER_FAILURE_TO_REASON.get(token)
        if mapped and mapped not in reasons:
            reasons.append(mapped)
    # 2. 无锁降级 / 跳过约束（design §8.3 明确阻断）。
    if lockless_degraded and REASON_LOCKLESS_DEGRADED not in reasons:
        reasons.append(REASON_LOCKLESS_DEGRADED)
    # 4. 所需锁 / 约束未生效。
    if not locks_constraints_in_effect and REASON_LOCKS_NOT_IN_EFFECT not in reasons:
        reasons.append(REASON_LOCKS_NOT_IN_EFFECT)

    # 稳定顺序（design §8.3 列举次序）。
    _ORDER = (
        REASON_MIGRATION_FAILED,
        REASON_LOCKLESS_DEGRADED,
        REASON_PENDING_OR_FAILED_MIGRATION,
        REASON_LOCKS_NOT_IN_EFFECT,
        REASON_SCHEMA_CONTRACT,
        REASON_BACKFILL_DIFF,
        REASON_FAILED_CHECKPOINT,
        REASON_BACKUP_NOT_VERIFIED,
        REASON_QUOTA_OVER_BUDGET,
    )
    ordered = tuple(r for r in _ORDER if r in reasons)

    return DeploymentHealthGateDecision(
        cutover=cutover,
        lockless_degraded=bool(lockless_degraded),
        locks_constraints_in_effect=bool(locks_constraints_in_effect),
        blocking_reasons=ordered,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 备份失败自动响应（design §8.3：禁止自动高风险 DB 回滚）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BackupFailureResponse:
    """备份失败时的自动响应（design §8.3）。

    自动响应**只能**：停止新写、关闭 flag、drain worker、保留现场、告警；
    **禁止自动执行高风险数据库回滚**（``auto_executes_destructive_db_rollback`` 恒 False），
    由人工确认恢复策略。
    """

    stop_new_writes: bool
    close_feature_flag: bool
    drain_workers: bool
    preserve_state: bool
    alert: bool
    auto_executes_destructive_db_rollback: bool
    requires_human_confirmation: bool
    steps: tuple[str, ...]


def backup_failure_response() -> BackupFailureResponse:
    """返回备份失败时的固定非破坏性自动响应（design §8.3）。"""
    return BackupFailureResponse(
        stop_new_writes=True,
        close_feature_flag=True,
        drain_workers=True,
        preserve_state=True,
        alert=True,
        auto_executes_destructive_db_rollback=False,  # 恒 False：禁止自动高风险 DB 回滚
        requires_human_confirmation=True,
        steps=(
            "1. 立即停止新写（关闭治理写入口 / 退回 legacy 读）",
            "2. 关闭 feature flag（不切新真源）",
            "3. drain 治理 worker（停 enqueue，保留 outbox 未处理事件）",
            "4. 保留现场（不删表 / 不降 enum / 不删约束 / 不删治理对象）",
            "5. 告警并关联 migration command-root 与 trace，等待人工确认恢复策略",
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 回滚演练编排（design §8.4）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RollbackRehearsalScript:
    """完整回滚演练脚本（design §8.4）：复用 ``production_rollback_plan``，附演练验证清单。"""

    plan: RollbackPlan
    #: 演练必须验证的非破坏性动作（design §8.4）。
    stop_new_writes: bool
    drain_workers: bool
    pause_backfill: bool
    compat_read_fallback: bool
    #: 演练后必须核验“零删除/零覆盖”的治理对象类别。
    must_preserve_object_kinds: tuple[str, ...]

    @property
    def destructive(self) -> bool:
        return self.plan.destructive  # 恒 False

    @property
    def retains_legacy_columns(self) -> bool:
        return self.plan.retain_legacy_columns  # 恒 True


def build_rollback_rehearsal_script(*, from_phase: str | None = None) -> RollbackRehearsalScript:
    """构造完整回滚演练脚本（design §8.4）。

    以 ``production_rollback_plan`` 为唯一回滚计划真源；演练在其上叠加四项非破坏性动作
    的验证开关与“必须保留的治理对象”清单（``RETAINED_GOVERNANCE_OBJECTS``）。
    """
    from app.services.evidence_governance.migration_phases import PHASE_M3_CUTOVER

    plan = production_rollback_plan(from_phase=from_phase or PHASE_M3_CUTOVER)
    return RollbackRehearsalScript(
        plan=plan,
        stop_new_writes=True,
        drain_workers=True,
        pause_backfill=True,
        compat_read_fallback=True,
        must_preserve_object_kinds=RETAINED_GOVERNANCE_OBJECTS,
    )
