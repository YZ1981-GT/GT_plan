"""公式 reference 来源解析 + 源变更失效链（Formula Management Library · Req 25.5/25.7）。

本模块补齐"公式三来源"中 ``reference`` 来源的**解引用**与**源变更失效传播**：

- **reference 来源解析（Req 25.5）**：当公式 ``formula_source='reference'`` 且带
  ``reference_formula_id`` 时，解析取**被参照源公式**的 ``expression``——**复用而非
  重录**（扩展 Req 9 的公式复用能力）。引用方不再各自重录表达式，而以源公式为单一
  真源，源公式变更即被引用方感知。

- **源变更失效传播（Req 25.7）**：被参照源公式发生变更（更新/删除）时，经 **ACNR
  失效链**（``acnr.events.invalidate``）使所有引用方标失效并可重算——**复用**既有
  canonical 失效链（L3→L2→FormulaReverseIndex→legacy WP 域），**不自建**失效逻辑。

- **悬空 reference（fail-open）**：``reference_formula_id`` 指向**已删除/不存在**的源
  公式时，按 **fail-open** 记 Issue_List / 告警，**不静默产错值**——绝不返回一个
  凭空/错误的表达式冒充解析成功。

三层一致铁律：``formula_source`` / ``reference_formula_id`` 列已在 **V100** 落地
（``wp_formula`` 扩 7 列）并已在 ``workpaper_models.py:WpFormula`` ORM 同步 —— 本模块
**不重复建列**，仅补 reference 解析与失效传播逻辑。

工程铁律：
- **service 只 flush 不 commit**（本模块只读查询 + 触发失效链，不 commit）。
- 引用解析经 ACNR 全链（间接经 ``engine.resolve_ref`` / ``acnr.events.invalidate``）。
- 失效链复用 ``acnr.events.invalidate``，不自建。

Requirements: 25.5, 25.7
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpFormula
from app.services.formula_management.engine import IssueItem

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 结果结构
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class ReferenceResolution:
    """``reference`` 来源解引用结果。

    - ``resolved``：True 表示成功取到被参照源公式的表达式。
    - ``expression``：源公式表达式（复用而非重录）；``resolved=False`` 时为 ``None``。
    - ``source_formula_id``：被参照源公式 id（字符串形式，供溯源）。
    - ``dangling``：True 表示 ``reference_formula_id`` 悬空（源公式不存在/已删除）。
    - ``issue``：悬空 / 缺参 / 非法 id 时的 fail-open 问题项（不产错值）。
    """

    resolved: bool
    expression: str | None = None
    source_formula_id: str | None = None
    dangling: bool = False
    issue: IssueItem | None = None


def _as_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    """把 str / UUID 统一为 UUID；非法/空返回 None（供 fail-open 判定）。"""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# reference 来源解析（Req 25.5）
# ═══════════════════════════════════════════════════════════════════════════════
async def resolve_reference_expression(
    db: AsyncSession,
    *,
    reference_formula_id: uuid.UUID | str | None,
    requester_formula_id: str | None = None,
    requester_addr_id: str | None = None,
) -> ReferenceResolution:
    """解析 ``reference`` 来源公式：取被参照源公式的 ``expression``（复用而非重录）。

    悬空处理（fail-open，Req 25.7 末句）：
    - ``reference_formula_id`` 为空 → 记 Issue（缺参），``resolved=False``。
    - id 非法（无法解析为 UUID）→ 记 Issue，``resolved=False``。
    - 源公式不存在/已删除 → ``dangling=True`` + 记 Issue，``resolved=False``。

    上述任一情况**均不返回表达式**（``expression=None``），从而**不静默产错值**：
    调用方应将 ``issue`` 追加到 Issue_List 并跳过该引用，而非用一个错误/凭空的
    表达式继续求值。

    Args:
        db: AsyncSession（只读查询）。
        reference_formula_id: 被参照源公式 id。
        requester_formula_id: 发起引用的公式 id（供 Issue 溯源，可空）。
        requester_addr_id: 发起引用的公式承载单元 addr_id（供 Issue 溯源，可空）。

    Returns:
        ReferenceResolution。

    Requirements: 25.5
    """
    if reference_formula_id is None:
        return ReferenceResolution(
            resolved=False,
            issue=IssueItem(
                formula_id=requester_formula_id or "",
                addr_id=requester_addr_id,
                description="reference 来源公式缺少 reference_formula_id，已跳过引用不产错值",
            ),
        )

    src_uuid = _as_uuid(reference_formula_id)
    if src_uuid is None:
        return ReferenceResolution(
            resolved=False,
            source_formula_id=str(reference_formula_id),
            issue=IssueItem(
                formula_id=requester_formula_id or "",
                addr_id=requester_addr_id,
                description=(
                    f"reference_formula_id 非法（无法解析为 UUID）："
                    f"{reference_formula_id!r}，已跳过引用不产错值"
                ),
            ),
        )

    src = (
        await db.execute(sa.select(WpFormula).where(WpFormula.id == src_uuid))
    ).scalar_one_or_none()

    if src is None:
        # 悬空：指向已删除/不存在的源公式 → fail-open 记 Issue，不产错值（Req 25.7）。
        logger.warning(
            "reference 来源悬空：源公式 %s 不存在（可能已删除），跳过引用不产错值 "
            "(requester=%s)",
            src_uuid,
            requester_formula_id,
        )
        return ReferenceResolution(
            resolved=False,
            dangling=True,
            source_formula_id=str(src_uuid),
            issue=IssueItem(
                formula_id=requester_formula_id or "",
                addr_id=requester_addr_id,
                description=(
                    f"参照来源公式 {src_uuid} 不存在（可能已删除），"
                    f"已跳过引用不产错值"
                ),
            ),
        )

    # 复用源公式表达式（复用而非重录，Req 25.5）。
    return ReferenceResolution(
        resolved=True,
        expression=src.expression,
        source_formula_id=str(src.id),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 源变更失效传播（Req 25.7）
# ═══════════════════════════════════════════════════════════════════════════════
async def find_reference_dependents(
    db: AsyncSession, *, source_formula_id: uuid.UUID | str
) -> list[WpFormula]:
    """查找所有以 ``source_formula_id`` 为参照源的引用方公式。

    引用方判据：``formula_source='reference'`` 且 ``reference_formula_id`` 指向源公式。

    Returns:
        引用方 ``WpFormula`` 列表（可能为空）。
    """
    src_uuid = _as_uuid(source_formula_id)
    if src_uuid is None:
        return []
    rows = (
        await db.execute(
            sa.select(WpFormula).where(
                WpFormula.reference_formula_id == src_uuid,
                WpFormula.formula_source == "reference",
            )
        )
    ).scalars().all()
    return list(rows)


async def invalidate_reference_dependents(
    db: AsyncSession,
    *,
    source_formula_id: uuid.UUID | str,
    project_id: uuid.UUID | str,
    trigger: str = "formula_reference_source_change",
) -> int:
    """被参照源公式变更时，经 **ACNR 失效链**使引用方标失效并可重算（Req 25.7）。

    **复用** ``acnr.events.invalidate``（canonical 失效链：L3→L2→FormulaReverseIndex→
    legacy WP 域），**不自建**失效逻辑。仅当存在引用方时才触发失效链，避免无谓开销。
    invalidate 本身不抛异常（失效失败仅 warning，不阻断主流程）。

    Args:
        db: AsyncSession。
        source_formula_id: 发生变更的被参照源公式 id。
        project_id: 项目 id（失效链按 project 维度清理）。
        trigger: 失效触发来源标识（供日志/审计）。

    Returns:
        受影响（被标失效）的引用方数量。

    Requirements: 25.7
    """
    dependents = await find_reference_dependents(
        db, source_formula_id=source_formula_id
    )
    if not dependents:
        return 0

    try:
        # 复用既有 canonical 失效链，不自建。
        from app.services.acnr.events import invalidate

        await invalidate(str(project_id), trigger=trigger)
    except Exception as exc:  # noqa: BLE001 — 失效不阻断主流程
        logger.warning(
            "reference 源变更后 ACNR 失效链触发失败（不阻断）: "
            "source=%s project=%s deps=%d: %s",
            source_formula_id,
            project_id,
            len(dependents),
            exc,
        )

    logger.info(
        "reference 源变更失效传播: source=%s project=%s 引用方=%d trigger=%s",
        source_formula_id,
        project_id,
        len(dependents),
        trigger,
    )
    return len(dependents)


def _normalize_ref_id(value: Any) -> uuid.UUID | None:
    """对外暴露的 id 归一化助手（供 service 层复用，避免各处重复实现）。"""
    return _as_uuid(value)
