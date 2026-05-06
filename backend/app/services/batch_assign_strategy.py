"""批量委派策略 — BatchAssignStrategy 纯函数

三种策略：
  - manual: 所有底稿分给同一人（candidates[0]）
  - round_robin: 按候选人列表均匀轮询分配
  - by_level: helper/senior 分初级底稿，manager 分复杂底稿
    阈值从 WpIndex.complexity 读取，无该字段时按 audit_cycle 映射表走

纯函数设计，便于单元测试，不依赖数据库。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


# ── 数据结构 ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class WorkpaperInfo:
    """底稿信息（用于策略计算）"""
    wp_id: UUID
    audit_cycle: str | None = None
    complexity: int | None = None  # 1=简单, 2=中等, 3=复杂


@dataclass(frozen=True)
class CandidateInfo:
    """候选人信息"""
    user_id: UUID
    role: str  # 'auditor' | 'senior_auditor' | 'manager'


@dataclass(frozen=True)
class AssignmentResult:
    """分配结果"""
    wp_id: UUID
    user_id: UUID


# ── audit_cycle → complexity 映射表 ──────────────────────────────
# D/F 循环通常是初级底稿（银行/应收/应付等），K/N 循环较复杂（长期资产/权益等）
CYCLE_COMPLEXITY_MAP: dict[str, int] = {
    "D": 1,  # 货币资金循环 — 初级
    "F": 1,  # 销售与收款循环 — 初级
    "K": 3,  # 投资与筹资循环 — 复杂
    "N": 3,  # 权益循环 — 复杂
}
# 未在映射表中的循环默认为中等复杂度
DEFAULT_COMPLEXITY = 2

# ── 角色 → 可处理复杂度阈值 ──────────────────────────────────────
# role 对应可处理的最大复杂度
ROLE_MAX_COMPLEXITY: dict[str, int] = {
    "auditor": 1,        # 审计助理 — 只分初级
    "senior_auditor": 2, # 高级审计员 — 初级+中等
    "manager": 3,        # 经理 — 所有复杂度
}


def _get_complexity(wp: WorkpaperInfo) -> int:
    """获取底稿复杂度：优先用 complexity 字段，否则按 audit_cycle 映射"""
    if wp.complexity is not None:
        return wp.complexity
    if wp.audit_cycle:
        return CYCLE_COMPLEXITY_MAP.get(wp.audit_cycle.upper(), DEFAULT_COMPLEXITY)
    return DEFAULT_COMPLEXITY


# ── 策略实现 ──────────────────────────────────────────────────────

def assign_manual(
    workpapers: list[WorkpaperInfo],
    candidates: list[UUID],
) -> list[AssignmentResult]:
    """手动策略：所有底稿分给 candidates[0]

    Args:
        workpapers: 待分配底稿列表
        candidates: 候选人 ID 列表（取第一个）

    Returns:
        分配结果列表

    Raises:
        ValueError: candidates 为空
    """
    if not candidates:
        raise ValueError("manual 策略至少需要一个候选人")
    target = candidates[0]
    return [AssignmentResult(wp_id=wp.wp_id, user_id=target) for wp in workpapers]


def assign_round_robin(
    workpapers: list[WorkpaperInfo],
    candidates: list[UUID],
) -> list[AssignmentResult]:
    """轮询策略：按候选人列表均匀分配

    Args:
        workpapers: 待分配底稿列表
        candidates: 候选人 ID 列表

    Returns:
        分配结果列表

    Raises:
        ValueError: candidates 为空
    """
    if not candidates:
        raise ValueError("round_robin 策略至少需要一个候选人")
    results = []
    for i, wp in enumerate(workpapers):
        target = candidates[i % len(candidates)]
        results.append(AssignmentResult(wp_id=wp.wp_id, user_id=target))
    return results


def assign_by_level(
    workpapers: list[WorkpaperInfo],
    candidates: list[CandidateInfo],
) -> list[AssignmentResult]:
    """按职级策略：根据底稿复杂度匹配候选人职级

    规则：
    - complexity=1 (初级) → 优先分给 auditor/senior_auditor
    - complexity=2 (中等) → 优先分给 senior_auditor
    - complexity=3 (复杂) → 优先分给 manager

    当某级别候选人不足时，向上级别溢出（初级溢出到 senior，senior 溢出到 manager）。
    同级别内按轮询均匀分配。

    Args:
        workpapers: 待分配底稿列表
        candidates: 候选人信息列表（含角色）

    Returns:
        分配结果列表

    Raises:
        ValueError: candidates 为空
    """
    if not candidates:
        raise ValueError("by_level 策略至少需要一个候选人")

    # 按角色分组
    junior_candidates = [c for c in candidates if c.role in ("auditor", "senior_auditor")]
    manager_candidates = [c for c in candidates if c.role == "manager"]

    # 如果某组为空，所有人都可以接任何底稿
    all_user_ids = [c.user_id for c in candidates]

    # 按复杂度分组底稿
    simple_wps = []   # complexity <= 1
    medium_wps = []   # complexity == 2
    complex_wps = []  # complexity >= 3

    for wp in workpapers:
        c = _get_complexity(wp)
        if c <= 1:
            simple_wps.append(wp)
        elif c == 2:
            medium_wps.append(wp)
        else:
            complex_wps.append(wp)

    results = []

    # 分配简单底稿 → 优先 junior
    target_pool = [c.user_id for c in junior_candidates] if junior_candidates else all_user_ids
    for i, wp in enumerate(simple_wps):
        target = target_pool[i % len(target_pool)]
        results.append(AssignmentResult(wp_id=wp.wp_id, user_id=target))

    # 分配中等底稿 → 优先 senior_auditor，无则 junior 全体
    senior_candidates = [c for c in candidates if c.role == "senior_auditor"]
    target_pool = (
        [c.user_id for c in senior_candidates]
        if senior_candidates
        else ([c.user_id for c in junior_candidates] if junior_candidates else all_user_ids)
    )
    for i, wp in enumerate(medium_wps):
        target = target_pool[i % len(target_pool)]
        results.append(AssignmentResult(wp_id=wp.wp_id, user_id=target))

    # 分配复杂底稿 → 优先 manager
    target_pool = [c.user_id for c in manager_candidates] if manager_candidates else all_user_ids
    for i, wp in enumerate(complex_wps):
        target = target_pool[i % len(target_pool)]
        results.append(AssignmentResult(wp_id=wp.wp_id, user_id=target))

    return results


# ── 统一入口 ──────────────────────────────────────────────────────

Strategy = Literal["manual", "round_robin", "by_level"]


def compute_assignments(
    strategy: Strategy,
    workpapers: list[WorkpaperInfo],
    candidates: list[UUID] | list[CandidateInfo],
    override_assignments: list[AssignmentResult] | None = None,
) -> list[AssignmentResult]:
    """统一入口：根据策略计算分配结果，再应用 override 微调

    Args:
        strategy: 分配策略
        workpapers: 待分配底稿
        candidates: 候选人列表（by_level 需要 CandidateInfo，其他只需 UUID）
        override_assignments: 手动微调覆盖

    Returns:
        最终分配结果列表
    """
    if strategy == "manual":
        user_ids = [
            c.user_id if isinstance(c, CandidateInfo) else c
            for c in candidates
        ]
        results = assign_manual(workpapers, user_ids)
    elif strategy == "round_robin":
        user_ids = [
            c.user_id if isinstance(c, CandidateInfo) else c
            for c in candidates
        ]
        results = assign_round_robin(workpapers, user_ids)
    elif strategy == "by_level":
        # by_level 需要 CandidateInfo
        candidate_infos = []
        for c in candidates:
            if isinstance(c, CandidateInfo):
                candidate_infos.append(c)
            else:
                # 如果只传了 UUID，默认当 auditor
                candidate_infos.append(CandidateInfo(user_id=c, role="auditor"))
        results = assign_by_level(workpapers, candidate_infos)
    else:
        raise ValueError(f"未知策略: {strategy}")

    # 应用 override 微调
    if override_assignments:
        override_map = {o.wp_id: o.user_id for o in override_assignments}
        results = [
            AssignmentResult(wp_id=r.wp_id, user_id=override_map.get(r.wp_id, r.user_id))
            for r in results
        ]

    return results
