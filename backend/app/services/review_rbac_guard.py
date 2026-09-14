"""Review RBAC Guard — 五级复核表角色权限校验服务.

提供 A21~A25 复核表的:
- RBAC 角色映射 (REVIEW_ROLE_MAP)
- 逐级依赖链 (REVIEW_DEPENDENCY)
- Guard 返回结构 (ReviewGuardResult)
- 统一校验入口 (evaluate_guard)
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.staff_models import ProjectAssignment, StaffMember

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 静态常量
# ---------------------------------------------------------------------------

REVIEW_ROLE_MAP: dict[str, list[str]] = {
    "A21": ["senior", "auditor"],
    "A22": ["manager"],
    "A23": ["signing_partner"],
    "A24": ["qc"],
    "A25": ["eqcr"],
}
"""wp_code 基础级别 → 允许的 project_assignments.role 列表."""

REVIEW_DEPENDENCY: dict[str, str] = {
    "A22": "A21",
    "A23": "A22",
    "A24": "A23",
    "A25": "A24",
}
"""逐级前置依赖: key 级别需要 value 级别已签字 (A21 无前置)."""


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class ReviewGuardResult:
    """evaluate_guard 统一返回结构."""

    readonly: bool = False
    locked: bool = False
    signed_by: str | None = None
    signed_at: str | None = None
    gate_reason: str | None = None
    unresolved_count: int = 0
    rbac_denied: bool = False


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

_BASE_LEVEL_RE = re.compile(r"^(A2[1-5])")
_VARIANT_SUFFIX_RE = re.compile(r"^A2[1-5](-\d+)?$")


def extract_base_level(wp_code: str) -> str | None:
    """从 wp_code 提取基础级别 (A21~A25).

    Examples:
        "A21-1" → "A21"
        "A22"   → "A22"
        "A25-2" → "A25"
        "B50"   → None (非复核表)
    """
    m = _BASE_LEVEL_RE.match(wp_code)
    return m.group(1) if m else None


def extract_variant_suffix(wp_code: str) -> str:
    """从 wp_code 提取变体后缀 (如 "-1", "-2")，无变体时返回空字符串.

    Examples:
        "A21-1" → "-1"
        "A22-2" → "-2"
        "A21"   → ""
    """
    m = _VARIANT_SUFFIX_RE.match(wp_code)
    if m and m.group(1):
        return m.group(1)
    return ""


# ---------------------------------------------------------------------------
# RBAC 校验
# ---------------------------------------------------------------------------


async def check_rbac(
    db: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    wp_code: str,
) -> bool:
    """检查当前用户是否被 RBAC 拒绝访问指定复核表.

    Returns:
        True  — rbac_denied，用户无权限（安全降级）
        False — 用户有权限，或 wp_code 非复核表（不受管辖）
    """
    # 1. 提取基础级别，非复核表直接放行
    base_level = extract_base_level(wp_code)
    if base_level is None or base_level not in REVIEW_ROLE_MAP:
        return False  # 非复核表不受管辖

    allowed_roles = REVIEW_ROLE_MAP[base_level]

    # 2. 通过 user_id 查找 staff_id
    staff_stmt = (
        sa.select(StaffMember.id)
        .where(StaffMember.user_id == user_id)
        .where(StaffMember.is_deleted == sa.false())
        .limit(1)
    )
    staff_result = await db.execute(staff_stmt)
    staff_row = staff_result.scalar_one_or_none()

    if staff_row is None:
        # 无 staff 映射 → 安全降级，视为无权限
        logger.warning(
            "[RBAC] user_id=%s 无对应 staff_members 记录，安全降级拒绝",
            user_id,
        )
        return True  # rbac_denied

    staff_id = staff_row

    # 3. 查询 project_assignments 匹配 project_id + staff_id + role in allowed_roles
    assign_stmt = (
        sa.select(sa.func.count())
        .select_from(ProjectAssignment.__table__)
        .where(ProjectAssignment.project_id == project_id)
        .where(ProjectAssignment.staff_id == staff_id)
        .where(ProjectAssignment.role.in_(allowed_roles))
        .where(ProjectAssignment.is_deleted == sa.false())
    )
    assign_result = await db.execute(assign_stmt)
    count = assign_result.scalar() or 0

    if count == 0:
        return True  # rbac_denied: 无匹配角色

    return False  # 有权限


# ---------------------------------------------------------------------------
# Sequential Gate 逐级校验
# ---------------------------------------------------------------------------


async def check_sequential_gate(
    db: AsyncSession,
    project_id: uuid.UUID,
    wp_code: str,
) -> tuple[bool, str | None]:
    """检查逐级前置依赖是否满足.

    Returns:
        (blocked, gate_reason):
          - (False, None) — 不阻止（无前置依赖或前置已签字）
          - (True, reason) — 阻止，reason 描述需先完成哪个级别
    """
    # 1. 提取基础级别
    base_level = extract_base_level(wp_code)
    if base_level is None:
        return (False, None)  # 非复核表不受管辖

    # 2. 查 REVIEW_DEPENDENCY 获取前置级别
    prerequisite_level = REVIEW_DEPENDENCY.get(base_level)
    if prerequisite_level is None:
        # A21 无前置依赖，直接放行
        return (False, None)

    # 3. 提取变体后缀
    suffix = extract_variant_suffix(wp_code)

    # 4. 构造前置 sign item_id: {prerequisite_level}{suffix}-sign
    prerequisite_code = f"{prerequisite_level}{suffix}"
    prerequisite_sign_item_id = f"{prerequisite_code}-sign"

    # 5. 查询 checklist_responses 中该 sign 记录是否 conclusion='pass'
    result = await db.execute(
        sa.text(
            """
            SELECT 1 FROM checklist_responses
            WHERE project_id = :project_id
              AND item_id = :item_id
              AND conclusion = 'pass'
            LIMIT 1
            """
        ),
        {
            "project_id": str(project_id),
            "item_id": prerequisite_sign_item_id,
        },
    )
    row = result.scalar_one_or_none()

    if row is not None:
        # 前置已签字，放行
        return (False, None)

    # 前置未签字，阻止
    gate_reason = f"需先完成 {prerequisite_code} 复核并签字"
    return (True, gate_reason)


# ---------------------------------------------------------------------------
# Sign-Lock 锁定检查
# ---------------------------------------------------------------------------


async def calc_unresolved_count(
    db: AsyncSession,
    wp_id: uuid.UUID,
) -> int:
    """计算指定底稿中未清复核意见数量.

    统计 checklist_responses 中 conclusion='N' 的记录，
    排除 item_id 以 -sign / -record / -unlock-log 结尾的系统项。

    Returns:
        未清意见条数（int）
    """
    result = await db.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM checklist_responses
            WHERE wp_id = :wp_id
              AND conclusion = 'N'
              AND item_id NOT LIKE '%-sign'
              AND item_id NOT LIKE '%-record'
              AND item_id NOT LIKE '%-unlock-log'
            """
        ),
        {"wp_id": str(wp_id)},
    )
    count = result.scalar() or 0
    return int(count)


# ---------------------------------------------------------------------------
# Sign-Lock 锁定检查
# ---------------------------------------------------------------------------


async def check_sign_lock(
    db: AsyncSession,
    project_id: uuid.UUID,
    wp_code: str,
) -> tuple[bool, str | None, str | None]:
    """检查指定复核表是否已签字锁定.

    Returns:
        (locked, signed_by, signed_at):
          - (False, None, None) — 未锁定
          - (True, signer_name|None, iso_timestamp|None) — 已锁定
    """
    import json

    # 1. 构造 sign item_id
    sign_item_id = f"{wp_code}-sign"

    # 2. 查询 checklist_responses 中 conclusion='pass' 的签字记录
    result = await db.execute(
        sa.text(
            """
            SELECT remark, updated_at FROM checklist_responses
            WHERE project_id = :project_id
              AND item_id = :item_id
              AND conclusion = 'pass'
            LIMIT 1
            """
        ),
        {
            "project_id": str(project_id),
            "item_id": sign_item_id,
        },
    )
    row = result.first()

    if row is None:
        return (False, None, None)

    # 3. 已锁定 — 尝试从 remark JSON 提取 signer_id
    remark_raw = row[0]  # remark
    updated_at_raw = row[1]  # updated_at

    # signed_at: 取 updated_at 作为签字时间
    signed_at: str | None = None
    if updated_at_raw is not None:
        signed_at = str(updated_at_raw)

    # 4. 解析 remark 获取 signer_id
    signed_by: str | None = None
    signer_id: str | None = None

    if remark_raw:
        try:
            remark_data = json.loads(remark_raw)
            signer_id = remark_data.get("signer_id") if isinstance(remark_data, dict) else None
        except (json.JSONDecodeError, TypeError):
            # remark 非有效 JSON — 仍返回 locked=True 但 signed_by=None
            pass

    # 5. 从 staff_members 查询签字人姓名
    if signer_id:
        try:
            signer_uuid = uuid.UUID(signer_id)
            staff_stmt = (
                sa.select(StaffMember.name)
                .where(StaffMember.id == signer_uuid)
                .where(StaffMember.is_deleted == sa.false())
                .limit(1)
            )
            staff_result = await db.execute(staff_stmt)
            name = staff_result.scalar_one_or_none()
            if name:
                signed_by = name
        except (ValueError, Exception):
            # signer_id 非有效 UUID 或查询异常不影响 locked 状态
            logger.warning(
                "[SignLock] signer_id=%s 查询 staff_members 异常",
                signer_id,
            )

    return (True, signed_by, signed_at)


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------


async def evaluate_guard(
    db: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    wp_code: str,
    wp_id: uuid.UUID,
) -> ReviewGuardResult:
    """统一评估 review guard，按顺序执行各项检查.

    执行顺序:
      1. sign_lock → 若 locked 则直接返回 readonly=True（无需再查 rbac/gate）
      2. rbac → 角色权限检查
      3. sequential_gate → 逐级前置依赖检查
      4. unresolved_count → 未清复核意见计数

    异常安全: 任何异常均安全降级为 readonly=True。
    """
    try:
        # 1. Sign-Lock 检查（最高优先级）
        locked, signed_by, signed_at = await check_sign_lock(db, project_id, wp_code)

        if locked:
            # 锁定时仍需计算 unresolved_count 供前端显示
            unresolved = await calc_unresolved_count(db, wp_id)
            return ReviewGuardResult(
                readonly=True,
                locked=True,
                signed_by=signed_by,
                signed_at=signed_at,
                unresolved_count=unresolved,
            )

        # 2. RBAC 检查
        rbac_denied = await check_rbac(db, user_id, project_id, wp_code)

        # 3. Sequential Gate 检查
        gate_blocked, gate_reason = await check_sequential_gate(db, project_id, wp_code)

        # 4. Unresolved Count
        unresolved = await calc_unresolved_count(db, wp_id)

        # 5. 综合判定 readonly
        readonly = rbac_denied or gate_blocked

        return ReviewGuardResult(
            readonly=readonly,
            locked=False,
            signed_by=None,
            signed_at=None,
            gate_reason=gate_reason,
            unresolved_count=unresolved,
            rbac_denied=rbac_denied,
        )

    except Exception:
        logger.exception("[evaluate_guard] 异常，安全降级为 readonly=True")
        return ReviewGuardResult(readonly=True)
