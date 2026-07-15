"""分阶段部署、特性开关矩阵与非破坏回滚（Task 15）

Feature: procedure-delegation-notification
需求：13.1-13.9（expand→dual-read→backfill→cutover→contract 顺序 + 三开关行为矩阵 +
      cutover 前置校验 + 生产非破坏回滚）
Design：Deployment and Rollback（阶段矩阵）
Properties：P34（部署阶段单调与回滚保留）

纯逻辑（无 DB 副作用），便于 PBT：
- ``expected_flags(phase)`` / ``detect_phase(...)``：阶段 ↔ 三开关行为矩阵（Req 13.2/13.3）。
- ``can_advance(current, target, checks_passed)``：阶段推进必须单调（一次一步），且下一阶段
  guard 未满足则拒绝任何跳跃（Req 13.1 / P34）。
- ``evaluate_cutover_preconditions(...)``：cutover 前 coverage / 冲突阈值 / 投影一致性 /
  dispatcher backlog / 回滚演练校验（Req 13.6）。
- ``production_rollback_flags(...)``：停 task 新写 + 停 dispatcher + 保留 V105 表/列/outbox +
  读取退回 dual-read/legacy fallback；不产生任何 DDL/破坏性 down（Req 13.8 / P34）。

三开关（config.py）：``PROCEDURE_ROW_TASKS_ENABLED`` / ``PROCEDURE_ROW_TASK_WRITE_MODE`` /
``PROCEDURE_TASK_DISPATCHER_ENABLED``。
"""

from __future__ import annotations

from dataclasses import dataclass

# --- 阶段（严格有序） -------------------------------------------------------
PHASE_EXPAND = "expand"
PHASE_DUAL_READ = "dual-read"
PHASE_BACKFILL = "backfill"
PHASE_CUTOVER = "cutover"
PHASE_CONTRACT = "contract"

PHASES: tuple[str, ...] = (
    PHASE_EXPAND,
    PHASE_DUAL_READ,
    PHASE_BACKFILL,
    PHASE_CUTOVER,
    PHASE_CONTRACT,
)

# --- 写模式（config PROCEDURE_ROW_TASK_WRITE_MODE 值域） --------------------
WRITE_MODE_LEGACY = "legacy"          # 无 task 新写（legacy-safe 回退，rollback 目标）
WRITE_MODE_DUAL = "dual"              # 双写：legacy + task
WRITE_MODE_TASK_SOURCE = "task-source"  # task 为读写真源
WRITE_MODES: frozenset[str] = frozenset(
    {WRITE_MODE_LEGACY, WRITE_MODE_DUAL, WRITE_MODE_TASK_SOURCE}
)

# task 新写是否允许（rollback 后 legacy 模式禁止新 task 写，只读 dual-read/legacy fallback）。
_TASK_WRITE_MODES: frozenset[str] = frozenset({WRITE_MODE_DUAL, WRITE_MODE_TASK_SOURCE})

# 生产回滚固定退回的阶段（dual-read fallback；不做破坏性 down）。
ROLLBACK_TARGET_PHASE = PHASE_DUAL_READ

# V105 回滚必须保留的物理对象（rollback 只翻转开关，绝不 DDL 删除）。
RETAINED_V105_TABLES: tuple[str, ...] = (
    "procedure_row_definitions",
    "procedure_row_tasks",
    "procedure_row_task_history",
    "procedure_operation_previews",
)


@dataclass(frozen=True)
class PhaseFlags:
    """某阶段允许的三开关行为（write_modes 可能允许多个值）。"""

    tasks_enabled: bool
    write_modes: frozenset[str]
    dispatcher_enabled: bool


# 阶段 → 允许的三开关组合（Design Deployment and Rollback 矩阵，Req 13.2/13.3）。
_PHASE_MATRIX: dict[str, PhaseFlags] = {
    PHASE_EXPAND: PhaseFlags(False, frozenset({WRITE_MODE_LEGACY}), False),
    # dual-read：读比较、可选双写；write_mode 只能 legacy 或 dual（不能 task-source）。
    PHASE_DUAL_READ: PhaseFlags(True, frozenset({WRITE_MODE_LEGACY, WRITE_MODE_DUAL}), False),
    PHASE_BACKFILL: PhaseFlags(True, frozenset({WRITE_MODE_DUAL}), False),
    PHASE_CUTOVER: PhaseFlags(True, frozenset({WRITE_MODE_TASK_SOURCE}), True),
    PHASE_CONTRACT: PhaseFlags(True, frozenset({WRITE_MODE_TASK_SOURCE}), True),
}


def phase_index(phase: str) -> int:
    """阶段序号（未知阶段 → -1）。"""
    try:
        return PHASES.index(phase)
    except ValueError:
        return -1


def expected_flags(phase: str) -> PhaseFlags:
    """返回某阶段允许的三开关行为矩阵。未知阶段 → ValueError。"""
    if phase not in _PHASE_MATRIX:
        raise ValueError(f"未知部署阶段: {phase}")
    return _PHASE_MATRIX[phase]


def is_task_write_allowed(write_mode: str) -> bool:
    """当前写模式是否允许 task 新写（rollback 后 legacy 禁止）。"""
    return write_mode in _TASK_WRITE_MODES


def flags_match_phase(
    phase: str,
    *,
    tasks_enabled: bool,
    write_mode: str,
    dispatcher_enabled: bool,
) -> bool:
    """三开关组合是否符合该阶段允许的行为矩阵。"""
    if phase not in _PHASE_MATRIX:
        return False
    pf = _PHASE_MATRIX[phase]
    return (
        tasks_enabled == pf.tasks_enabled
        and write_mode in pf.write_modes
        and dispatcher_enabled == pf.dispatcher_enabled
    )


def detect_phase(
    *,
    tasks_enabled: bool,
    write_mode: str,
    dispatcher_enabled: bool,
) -> str | None:
    """由三开关反推当前阶段；不匹配任何阶段矩阵 → None（非法/中间态）。

    backfill 与 dual-read(dual) 的 (tasks=true, write=dual, dispatcher=false) 组合重叠，
    统一归到更靠后的 backfill（backfill ⊇ dual-read 的 dual 双写能力）。
    """
    matched: list[str] = [
        p
        for p in PHASES
        if flags_match_phase(
            p,
            tasks_enabled=tasks_enabled,
            write_mode=write_mode,
            dispatcher_enabled=dispatcher_enabled,
        )
    ]
    if not matched:
        return None
    # 组合重叠时取最靠后阶段（能力单调递增），保证 detect 稳定确定。
    return max(matched, key=phase_index)


def settings_phase(settings) -> str | None:
    """从 config settings 读取三开关并反推阶段。"""
    return detect_phase(
        tasks_enabled=bool(getattr(settings, "PROCEDURE_ROW_TASKS_ENABLED", False)),
        write_mode=str(getattr(settings, "PROCEDURE_ROW_TASK_WRITE_MODE", WRITE_MODE_LEGACY)),
        dispatcher_enabled=bool(getattr(settings, "PROCEDURE_TASK_DISPATCHER_ENABLED", False)),
    )


def can_advance(current: str, target: str, *, checks_passed: bool) -> tuple[bool, str]:
    """阶段推进 guard：只允许沿 PHASES 顺序 **一次一步** 前进，且下一阶段 guard 满足。

    - target == current → 允许（no-op，返回 True）。
    - target 比 current 靠后超过一步（跳阶段）→ 拒绝（Req 13.1 / P34）。
    - target 恰好下一步：checks_passed 为 True 才允许。
    - target 比 current 靠前（回退）→ 拒绝（回退走 production_rollback，不走 advance）。
    - 未知阶段 → 拒绝。

    返回 ``(allowed, reason)``。
    """
    ci, ti = phase_index(current), phase_index(target)
    if ci < 0 or ti < 0:
        return False, f"未知阶段: current={current} target={target}"
    if ti == ci:
        return True, "no-op（阶段未变化）"
    if ti < ci:
        return False, "不允许通过 advance 回退阶段（生产回滚请用 production_rollback）"
    if ti - ci > 1:
        return False, f"禁止跳阶段推进：{current} → {target}（必须逐阶段）"
    if not checks_passed:
        return False, f"阶段 guard 未满足，拒绝进入 {target}"
    return True, f"允许推进 {current} → {target}"


@dataclass(frozen=True)
class CutoverPreconditions:
    """cutover 前置校验结果（Req 13.6）。"""

    coverage_ok: bool
    conflict_ok: bool
    projection_consistent: bool
    dispatcher_backlog_ok: bool
    rollback_drill_ok: bool

    @property
    def passed(self) -> bool:
        return (
            self.coverage_ok
            and self.conflict_ok
            and self.projection_consistent
            and self.dispatcher_backlog_ok
            and self.rollback_drill_ok
        )

    def failures(self) -> list[str]:
        out: list[str] = []
        if not self.coverage_ok:
            out.append("coverage")
        if not self.conflict_ok:
            out.append("conflict_threshold")
        if not self.projection_consistent:
            out.append("projection_consistency")
        if not self.dispatcher_backlog_ok:
            out.append("dispatcher_backlog")
        if not self.rollback_drill_ok:
            out.append("rollback_drill")
        return out


def evaluate_cutover_preconditions(
    *,
    coverage_ratio: float,
    conflict_count: int,
    projection_mismatches: int,
    dispatcher_backlog: int,
    rollback_drill_passed: bool,
    min_coverage: float = 1.0,
    max_conflicts: int = 0,
    max_backlog: int = 0,
) -> CutoverPreconditions:
    """cutover 前置校验：coverage / 冲突阈值 / 投影一致性 / dispatcher backlog / 回滚演练。

    - coverage_ratio ≥ min_coverage（默认 100% 物化覆盖）。
    - conflict_count ≤ max_conflicts（默认 0：不允许未解决的迁移冲突进入 cutover）。
    - projection_mismatches == 0（task 真源与投影完全一致）。
    - dispatcher_backlog ≤ max_backlog（默认 0：cutover 前 backlog 清空）。
    - rollback_drill_passed：已完成回滚演练。
    """
    return CutoverPreconditions(
        coverage_ok=coverage_ratio >= min_coverage,
        conflict_ok=conflict_count <= max_conflicts,
        projection_consistent=projection_mismatches == 0,
        dispatcher_backlog_ok=dispatcher_backlog <= max_backlog,
        rollback_drill_ok=bool(rollback_drill_passed),
    )


@dataclass(frozen=True)
class RollbackPlan:
    """生产非破坏回滚计划（只翻转开关，保留全部物理对象）。"""

    tasks_enabled: bool
    write_mode: str
    dispatcher_enabled: bool
    retained_tables: tuple[str, ...]
    destructive: bool
    target_phase: str
    steps: tuple[str, ...]


def production_rollback_flags(
    *,
    tasks_enabled: bool = True,
    write_mode: str = WRITE_MODE_TASK_SOURCE,
    dispatcher_enabled: bool = True,
) -> RollbackPlan:
    """生产回滚：先停 task 新写（write_mode→legacy），再停 dispatcher，保留 V105 表/列/outbox，
    读取退回 dual-read/legacy fallback（tasks_enabled 保持 True 以便 dual-read 可读）。

    绝不执行破坏性 down migration（destructive=False，retained_tables 保留全部 V105 表）。
    恢复后 dispatcher 从未 processed event 继续。返回新的三开关取值与保留清单。
    """
    return RollbackPlan(
        # dual-read fallback 仍需读 task overlay，故 tasks_enabled 保持开启。
        tasks_enabled=True,
        # 停止 task 新写：退回 legacy-safe（无新 task 写，读走 dual-read/legacy fallback）。
        write_mode=WRITE_MODE_LEGACY,
        # 停 dispatcher（保留 outbox 事件，恢复后从未 processed event 继续）。
        dispatcher_enabled=False,
        retained_tables=RETAINED_V105_TABLES,
        destructive=False,
        target_phase=ROLLBACK_TARGET_PHASE,
        steps=(
            "1. PROCEDURE_ROW_TASK_WRITE_MODE = legacy（停止 task 新写，legacy-safe 回退）",
            "2. PROCEDURE_TASK_DISPATCHER_ENABLED = false（停止 dispatcher claim，保留 outbox 事件）",
            "3. 保留 V105 全部表/列/outbox/notifications，不执行任何破坏性 down migration",
            "4. 读取退回 dual-read/legacy projection fallback（PROCEDURE_ROW_TASKS_ENABLED 保持 true）",
            "5. 恢复后重新开启 dispatcher，从未 processed event 继续投递",
        ),
    )
