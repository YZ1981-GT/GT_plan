"""M0–M4 evidence-governance 迁移阶段状态机（纯逻辑，无 DB 副作用）。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 8.1 (Wave 7 — M0–M4、质量快照、真实 PG 与容量基础验证)
Requirements: R14, R16
Design: §8.2 M0–M4、§8.3 高风险部署 Health Gate、§8.4 Rollback
Properties: P28（迁移幂等守恒）、P29（降级安全）

设计 §8.2 五阶段（strangler additive 路径）：

- **M0 additive/dark-read**：新表、约束、alias、兼容列已就位；**不切写**。新真源和兼容
  镜像都不写，只 dark-read 观测。所有 gate 仅观测。
- **M1 backfill**：按 project/year/id 小批 checkpoint 回填可证明字段；仍不切写。
- **M2 dual-write**：旧入口委托 facade，**同时写新真源与兼容镜像**；P0 规则首日 hard-block，
  其余 gate 可先观测。legacy 仍是权威读源（compat mirror 保持可读）。
- **M3 source-of-truth cutover**：新表**唯一写真源**；worker / AI coverage / manifest / hold /
  stale gate 全部启用；compat mirror 仍写供兼容读。
- **M4 retirement**：无旧写遥测后停止**非必要** mirror 更新；**删除 legacy 列不在本 spec**
  （legacy 列永久保留）。

本模块只表达「阶段 ↔ 行为矩阵 / 单调推进 guard / cutover·retirement 前置校验 / 非破坏回滚」，
不执行任何迁移或 backfill（backfill 见 ``evidence_backfill_runner``）。与 ``procedure_rollout``
同构，但语义是 evidence-governance 的 M0–M4。
"""

from __future__ import annotations

from dataclasses import dataclass

# --- 阶段（严格有序，design §8.2） -----------------------------------------
PHASE_M0_DARK_READ = "M0"          # additive / dark-read
PHASE_M1_BACKFILL = "M1"           # checkpoint backfill（可证明字段）
PHASE_M2_DUAL_WRITE = "M2"         # 双写：新真源 + 兼容镜像；P0 首日 hard-block
PHASE_M3_CUTOVER = "M3"            # source-of-truth cutover；全 gate 启用
PHASE_M4_RETIREMENT = "M4"         # 停非必要 mirror；legacy 列保留（不删）

PHASES: tuple[str, ...] = (
    PHASE_M0_DARK_READ,
    PHASE_M1_BACKFILL,
    PHASE_M2_DUAL_WRITE,
    PHASE_M3_CUTOVER,
    PHASE_M4_RETIREMENT,
)

# 生产回滚固定退回阶段（dual-write，兼容 facade 可继续写，避免双主 / 破坏性 down）。
ROLLBACK_TARGET_PHASE = PHASE_M2_DUAL_WRITE


@dataclass(frozen=True)
class PhaseBehavior:
    """某阶段允许/要求的治理写行为矩阵（design §8.2）。"""

    #: 是否运行 checkpoint backfill（M1 起可回填；后续阶段仍可补跑增量）。
    backfill_active: bool
    #: 是否写兼容镜像（legacy 列/旧字段镜像）。M0 不写；M2/M3 写；M4 停非必要 mirror。
    write_compat_mirror: bool
    #: 新治理表是否为唯一写真源。仅 M3/M4 为 True（M2 仍 legacy 权威，双写观测）。
    new_source_of_truth: bool
    #: P0 门禁（scope/actor/未确认 OCR/AI/hold/hash）是否硬阻断。M2 起首日 hard-block。
    p0_hard_block: bool
    #: 全部 gate（worker / AI coverage / manifest / hold / stale）是否启用。仅 M3/M4。
    all_gates_enabled: bool


# 阶段 → 行为矩阵（design §8.2 逐条）。
_PHASE_MATRIX: dict[str, PhaseBehavior] = {
    # M0 dark-read：什么都不切写，只观测（backfill 未启、不写镜像、legacy 权威、gate 观测）。
    PHASE_M0_DARK_READ: PhaseBehavior(
        backfill_active=False,
        write_compat_mirror=False,
        new_source_of_truth=False,
        p0_hard_block=False,
        all_gates_enabled=False,
    ),
    # M1 backfill：checkpoint 回填运行；仍不切写、不双写。
    PHASE_M1_BACKFILL: PhaseBehavior(
        backfill_active=True,
        write_compat_mirror=False,
        new_source_of_truth=False,
        p0_hard_block=False,
        all_gates_enabled=False,
    ),
    # M2 dual-write：新真源 + 兼容镜像同写；P0 首日 hard-block，其余 gate 观测；legacy 仍权威读。
    PHASE_M2_DUAL_WRITE: PhaseBehavior(
        backfill_active=True,
        write_compat_mirror=True,
        new_source_of_truth=False,
        p0_hard_block=True,
        all_gates_enabled=False,
    ),
    # M3 cutover：新表唯一写真源；全 gate 启用；compat mirror 仍写供兼容读。
    PHASE_M3_CUTOVER: PhaseBehavior(
        backfill_active=True,
        write_compat_mirror=True,
        new_source_of_truth=True,
        p0_hard_block=True,
        all_gates_enabled=True,
    ),
    # M4 retirement：停非必要 mirror；新表唯一真源；全 gate 保持；legacy 列不删。
    PHASE_M4_RETIREMENT: PhaseBehavior(
        backfill_active=True,
        write_compat_mirror=False,
        new_source_of_truth=True,
        p0_hard_block=True,
        all_gates_enabled=True,
    ),
}


def phase_index(phase: str) -> int:
    """阶段序号（未知阶段 → -1）。"""
    try:
        return PHASES.index(phase)
    except ValueError:
        return -1


def phase_behavior(phase: str) -> PhaseBehavior:
    """返回某阶段行为矩阵。未知阶段 → ValueError。"""
    if phase not in _PHASE_MATRIX:
        raise ValueError(f"未知迁移阶段: {phase}")
    return _PHASE_MATRIX[phase]


def can_advance(current: str, target: str, *, checks_passed: bool) -> tuple[bool, str]:
    """阶段推进 guard：只允许沿 PHASES **一次一步** 前进，且下一阶段前置校验满足。

    - target == current → 允许（no-op）。
    - target 靠后超过一步（跳阶段）→ 拒绝（design §8.3 逐阶段）。
    - target 恰好下一步：``checks_passed`` 为 True 才允许。
    - target 靠前（回退）→ 拒绝（回退走 ``production_rollback_plan``）。
    - 未知阶段 → 拒绝。
    """
    ci, ti = phase_index(current), phase_index(target)
    if ci < 0 or ti < 0:
        return False, f"未知阶段: current={current} target={target}"
    if ti == ci:
        return True, "no-op（阶段未变化）"
    if ti < ci:
        return False, "不允许通过 advance 回退阶段（生产回滚请用 production_rollback_plan）"
    if ti - ci > 1:
        return False, f"禁止跳阶段推进：{current} → {target}（必须逐阶段）"
    if not checks_passed:
        return False, f"阶段 guard 未满足，拒绝进入 {target}"
    return True, f"允许推进 {current} → {target}"


@dataclass(frozen=True)
class CutoverPreconditions:
    """M2 → M3 cutover 前置校验（design §8.3 Health Gate）。"""

    migrations_applied: bool          # 相关迁移全部成功
    no_pending_or_failed_migration: bool  # 无 pending/failed migration
    schema_contract_ok: bool          # schema/ORM/约束契约通过
    backfill_coverage_ok: bool        # alias/backfill 差异在阈值内
    no_failed_checkpoint: bool        # 无 failed checkpoint
    backup_verified: bool             # 备份已验证可恢复
    queue_quota_ready: bool           # outbox/queue/PG/PgBouncer 配额就绪

    @property
    def passed(self) -> bool:
        return all(
            (
                self.migrations_applied,
                self.no_pending_or_failed_migration,
                self.schema_contract_ok,
                self.backfill_coverage_ok,
                self.no_failed_checkpoint,
                self.backup_verified,
                self.queue_quota_ready,
            )
        )

    def failures(self) -> list[str]:
        out: list[str] = []
        if not self.migrations_applied:
            out.append("migrations_applied")
        if not self.no_pending_or_failed_migration:
            out.append("pending_or_failed_migration")
        if not self.schema_contract_ok:
            out.append("schema_contract")
        if not self.backfill_coverage_ok:
            out.append("backfill_coverage")
        if not self.no_failed_checkpoint:
            out.append("failed_checkpoint")
        if not self.backup_verified:
            out.append("backup_not_verified")
        if not self.queue_quota_ready:
            out.append("queue_quota")
        return out


def evaluate_cutover_preconditions(
    *,
    migrations_applied: bool,
    pending_migration_count: int,
    failed_migration_count: int,
    schema_contract_ok: bool,
    backfill_coverage_ratio: float,
    failed_checkpoint_count: int,
    backup_verified: bool,
    queue_quota_ready: bool,
    min_coverage: float = 1.0,
) -> CutoverPreconditions:
    """M2 → M3 前置校验（design §8.3）。

    任一相关迁移失败、迁移因锁不可得而降级、备份不可恢复、配额超预算，均阻止切 flag。
    """
    return CutoverPreconditions(
        migrations_applied=bool(migrations_applied),
        no_pending_or_failed_migration=(pending_migration_count == 0 and failed_migration_count == 0),
        schema_contract_ok=bool(schema_contract_ok),
        backfill_coverage_ok=backfill_coverage_ratio >= min_coverage,
        no_failed_checkpoint=(failed_checkpoint_count == 0),
        backup_verified=bool(backup_verified),
        queue_quota_ready=bool(queue_quota_ready),
    )


@dataclass(frozen=True)
class RetirementPreconditions:
    """M3 → M4 retirement 前置校验（design §8.2：无旧写遥测后停非必要 mirror）。"""

    no_legacy_write_telemetry: bool   # 无旧写入口遥测（一段观察窗口内 legacy 直写=0）
    cutover_stable: bool              # cutover 已稳定运行（M3 已生效且无回滚）

    @property
    def passed(self) -> bool:
        return self.no_legacy_write_telemetry and self.cutover_stable

    def failures(self) -> list[str]:
        out: list[str] = []
        if not self.no_legacy_write_telemetry:
            out.append("legacy_write_telemetry_present")
        if not self.cutover_stable:
            out.append("cutover_not_stable")
        return out


def evaluate_retirement_preconditions(
    *,
    legacy_write_events_in_window: int,
    cutover_stable: bool,
) -> RetirementPreconditions:
    """M3 → M4 前置校验：观察窗口内 legacy 直写事件必须为 0 且 cutover 稳定。"""
    return RetirementPreconditions(
        no_legacy_write_telemetry=(legacy_write_events_in_window == 0),
        cutover_stable=bool(cutover_stable),
    )


@dataclass(frozen=True)
class RollbackPlan:
    """生产非破坏回滚计划（design §8.4：只切 flag/adapter，保留全部治理对象与 legacy 列）。"""

    target_phase: str
    destructive: bool                 # 恒 False：不删表/不降 enum/不删约束/不删 legacy 列
    retain_legacy_columns: bool       # 恒 True：legacy 列永久保留
    retained_object_kinds: tuple[str, ...]
    steps: tuple[str, ...]


#: 回滚必须保留的治理对象类别（design §8.4：一律保留，不因应用回滚删除或覆盖）。
RETAINED_GOVERNANCE_OBJECTS: tuple[str, ...] = (
    "attachment_versions",
    "evidence_refs",
    "evidence_dependencies",
    "ocr_jobs",
    "ocr_results",
    "ocr_confirmations",
    "ocr_writebacks",
    "evidence_audit_command_roots",
    "evidence_audit_transitions",
    "archive_manifests",
    "legal_holds",
    "evidence_migration_checkpoints",
    "legacy_attachment_alias",
)


def production_rollback_plan(*, from_phase: str = PHASE_M3_CUTOVER) -> RollbackPlan:
    """生产回滚：退回 dual-write（M2），停 enqueue / drain worker / 暂停 backfill / 兼容读回退。

    绝不执行破坏性 DDL（不删表/降 enum/删约束/删 legacy 列）；已产生的 AttachmentVersion /
    EvidenceRef / OCR 决策 / 依赖 / 审计 / Manifest / Hold / checkpoint 全部保留（design §8.4）。
    """
    return RollbackPlan(
        target_phase=ROLLBACK_TARGET_PHASE,
        destructive=False,
        retain_legacy_columns=True,
        retained_object_kinds=RETAINED_GOVERNANCE_OBJECTS,
        steps=(
            "1. 停止新写切换（new_source_of_truth 退回 legacy，走 dual-write/read adapter）",
            "2. 停止 enqueue 并 drain 治理 worker（保留 outbox 事件，恢复后从未处理事件继续）",
            "3. 暂停 checkpoint backfill（已完成 checkpoint 与已回填对象保留）",
            "4. 读取退回兼容 facade（旧应用只读或经兼容 facade 写，避免双主）",
            "5. 保留全部治理对象与 legacy 列，不执行任何破坏性 down migration",
        ),
    )
