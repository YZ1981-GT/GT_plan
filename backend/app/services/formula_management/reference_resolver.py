"""公式 reference 运行时关系解析（formula-runtime-convergence · Req 5 / P8）。

本模块实现 **运行时递归解析** reference 公式链：

- **运行时递归解析**：reference 公式保存 ``reference_formula_id``，运行时递归
  解析当前源公式，沿链取最终有效表达式，不在保存时复制 expression 作为权威值。
- **visited 环检测**：用 visited set 防止循环引用链，发现环时返回包含引用路径
  的结构化错误。
- **source_version / source_hash**：返回源公式的版本信息（definition_version
  或 updated_at 兜底）与内容 hash，供固定版本参照校验。
- **outbox stale 标记**：源公式定义变化时，通过 outbox 标记引用方为 stale，
  不在保存时复制 expression。
- **悬空 / 跨项目**：悬空或跨项目源返回包含引用路径的结构化错误并保持领域
  业务值不变。

Requirements: 5.1–5.6
Property 8: 对任意无环 reference 链，执行结果使用源公式当前版本；源 definition
变化后引用方结果随之变化且被标 stale。
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpFormula

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 结果结构
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ReferenceResolution:
    """运行时 reference 链解析结果。

    Attributes:
        resolved: True 表示成功解析到最终源公式表达式。
        expression: 最终源公式表达式；resolved=False 时为 None。
        source_formula_id: 最终源公式 id（字符串）。
        source_version: 源公式版本标识（definition_version 或 updated_at ISO）。
        source_hash: 源公式 expression 的 SHA-256 hash。
        reference_mode: 参照模式 'live' | 'pinned'。
        chain: 解析链路径（formula_id 列表，含起始公式）。
        dangling: True 表示链中出现悬空（源不存在）。
        cycle: True 表示检测到环。
        cross_project: True 表示跨项目引用。
        issue: 结构化错误信息。
    """

    resolved: bool
    expression: str | None = None
    source_formula_id: str | None = None
    source_version: str | None = None
    source_hash: str | None = None
    reference_mode: str = "live"
    chain: list[str] = field(default_factory=list)
    dangling: bool = False
    cycle: bool = False
    cross_project: bool = False
    issue: dict | None = None


@dataclass
class OutboxStaleEvent:
    """Outbox stale 事件载体。"""

    event_type: str = "reference_source_changed"
    source_formula_id: str = ""
    dependent_formula_ids: list[str] = field(default_factory=list)
    project_id: str = ""
    trigger: str = "source_definition_change"


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════


def _as_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    """把 str / UUID 统一为 UUID；非法/空返回 None。"""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def compute_expression_hash(expression: str | None) -> str:
    """计算表达式的 SHA-256 hash（用于 source_hash）。"""
    if not expression:
        return hashlib.sha256(b"").hexdigest()
    return hashlib.sha256(expression.encode("utf-8")).hexdigest()


def get_formula_version(formula: WpFormula) -> str:
    """获取公式版本标识。

    优先使用 definition_version（Task 11 迁移后可用），
    回退到 updated_at ISO 字符串。
    """
    # definition_version 字段在 Task 11 迁移后可用
    version = getattr(formula, "definition_version", None)
    if version is not None:
        return str(version)
    # 回退到 updated_at
    if formula.updated_at:
        return formula.updated_at.isoformat()
    return "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# 运行时递归解析（Req 5.2 / 5.3 / 5.5）
# ═══════════════════════════════════════════════════════════════════════════════


async def resolve_reference_chain(
    db: AsyncSession,
    *,
    formula_id: uuid.UUID | str,
    project_id: uuid.UUID | str,
    reference_mode: str = "live",
    pinned_version: str | None = None,
    pinned_hash: str | None = None,
) -> ReferenceResolution:
    """运行时递归解析 reference 链，取最终源公式的当前有效表达式。

    对 reference 公式链进行递归解析：
    - 每次执行时从头解析（不缓存旧副本）。
    - visited set 检测环。
    - 悬空/跨项目/环 返回结构化错误，保持领域业务值不变。
    - 实时参照(live)使用当前版本；固定版本(pinned)验证 source_version/source_hash。

    Args:
        db: AsyncSession（只读查询）。
        formula_id: 起始公式 id。
        project_id: 请求方项目 id（用于跨项目校验）。
        reference_mode: 'live'（实时参照）或 'pinned'（固定版本参照）。
        pinned_version: 固定版本参照时绑定的源版本。
        pinned_hash: 固定版本参照时绑定的源 hash。

    Returns:
        ReferenceResolution 包含解析结果或结构化错误。

    Requirements: 5.2, 5.3, 5.5
    """
    start_uuid = _as_uuid(formula_id)
    proj_uuid = _as_uuid(project_id)

    if start_uuid is None:
        return ReferenceResolution(
            resolved=False,
            issue={
                "code": "INVALID_FORMULA_ID",
                "description": f"formula_id 非法: {formula_id!r}",
                "path": [],
            },
        )

    if proj_uuid is None:
        return ReferenceResolution(
            resolved=False,
            issue={
                "code": "INVALID_PROJECT_ID",
                "description": f"project_id 非法: {project_id!r}",
                "path": [],
            },
        )

    visited: set[uuid.UUID] = set()
    chain: list[str] = []
    current_id = start_uuid

    while True:
        # 环检测
        if current_id in visited:
            return ReferenceResolution(
                resolved=False,
                cycle=True,
                chain=chain,
                issue={
                    "code": "REFERENCE_CYCLE",
                    "description": (
                        f"reference 链出现环: "
                        f"{' → '.join(chain)} → {str(current_id)}"
                    ),
                    "path": chain + [str(current_id)],
                },
            )

        visited.add(current_id)
        chain.append(str(current_id))

        # 查询当前节点公式
        formula = (
            await db.execute(
                sa.select(WpFormula).where(WpFormula.id == current_id)
            )
        ).scalar_one_or_none()

        if formula is None:
            # 悬空
            return ReferenceResolution(
                resolved=False,
                dangling=True,
                chain=chain,
                issue={
                    "code": "DANGLING_REFERENCE",
                    "description": (
                        f"reference 链中公式 {current_id} 不存在（悬空）"
                    ),
                    "path": chain,
                },
            )

        # 跨项目校验
        if formula.project_id != proj_uuid:
            return ReferenceResolution(
                resolved=False,
                cross_project=True,
                chain=chain,
                issue={
                    "code": "CROSS_PROJECT_REFERENCE",
                    "description": (
                        f"reference 链中公式 {current_id} 属于项目 "
                        f"{formula.project_id}，请求项目为 {proj_uuid}"
                    ),
                    "path": chain,
                },
            )

        # 如果当前公式不是 reference 类型或没有 reference_formula_id，
        # 说明到达链末端（最终源公式）。
        ref_id = getattr(formula, "reference_formula_id", None)
        is_reference_source = (
            getattr(formula, "formula_source", "custom") == "reference"
            and ref_id is not None
        )

        if not is_reference_source:
            # 到达最终源公式 — 取其当前表达式
            current_version = get_formula_version(formula)
            current_hash = compute_expression_hash(formula.expression)

            # 固定版本参照验证（Req 5.3）
            if reference_mode == "pinned":
                version_mismatch = (
                    pinned_version is not None
                    and current_version != pinned_version
                )
                hash_mismatch = (
                    pinned_hash is not None
                    and current_hash != pinned_hash
                )
                if version_mismatch or hash_mismatch:
                    return ReferenceResolution(
                        resolved=False,
                        source_formula_id=str(formula.id),
                        source_version=current_version,
                        source_hash=current_hash,
                        reference_mode="pinned",
                        chain=chain,
                        issue={
                            "code": "PINNED_VERSION_MISMATCH",
                            "description": (
                                f"固定版本参照的源公式 {formula.id} "
                                f"版本或 hash 已变化 "
                                f"(expected version={pinned_version}, "
                                f"hash={pinned_hash}; "
                                f"current version={current_version}, "
                                f"hash={current_hash})"
                            ),
                            "path": chain,
                            "pinned_version": pinned_version,
                            "pinned_hash": pinned_hash,
                            "current_version": current_version,
                            "current_hash": current_hash,
                        },
                    )

            return ReferenceResolution(
                resolved=True,
                expression=formula.expression,
                source_formula_id=str(formula.id),
                source_version=current_version,
                source_hash=current_hash,
                reference_mode=reference_mode,
                chain=chain,
            )

        # 继续沿链递归
        next_uuid = _as_uuid(ref_id)
        if next_uuid is None:
            return ReferenceResolution(
                resolved=False,
                chain=chain,
                issue={
                    "code": "INVALID_REFERENCE_ID",
                    "description": (
                        f"公式 {current_id} 的 reference_formula_id "
                        f"非法: {ref_id!r}"
                    ),
                    "path": chain,
                },
            )

        current_id = next_uuid


# ═══════════════════════════════════════════════════════════════════════════════
# 单步解析（兼容旧接口）
# ═══════════════════════════════════════════════════════════════════════════════


async def resolve_reference_expression(
    db: AsyncSession,
    *,
    reference_formula_id: uuid.UUID | str | None,
    requester_formula_id: str | None = None,
    requester_addr_id: str | None = None,
    project_id: uuid.UUID | str | None = None,
) -> ReferenceResolution:
    """解析 reference 来源公式：运行时取源公式当前表达式。

    兼容旧接口签名，内部委托给 resolve_reference_chain。
    若 project_id 未提供，退化为单步查询（不做跨项目校验）。

    Args:
        db: AsyncSession。
        reference_formula_id: 被参照源公式 id。
        requester_formula_id: 发起引用的公式 id。
        requester_addr_id: 发起引用的公式 addr_id。
        project_id: 请求项目 id（可选）。

    Returns:
        ReferenceResolution。
    """
    if reference_formula_id is None:
        return ReferenceResolution(
            resolved=False,
            issue={
                "code": "MISSING_REFERENCE_ID",
                "description": (
                    "reference 来源公式缺少 reference_formula_id，"
                    "已跳过引用不产错值"
                ),
                "path": [],
                "requester": requester_formula_id or "",
                "addr_id": requester_addr_id,
            },
        )

    src_uuid = _as_uuid(reference_formula_id)
    if src_uuid is None:
        return ReferenceResolution(
            resolved=False,
            issue={
                "code": "INVALID_REFERENCE_ID",
                "description": (
                    f"reference_formula_id 非法（无法解析为 UUID）："
                    f"{reference_formula_id!r}"
                ),
                "path": [],
                "requester": requester_formula_id or "",
            },
        )

    # 如果没有 project_id，做简单的单步查询
    if project_id is None:
        formula = (
            await db.execute(
                sa.select(WpFormula).where(WpFormula.id == src_uuid)
            )
        ).scalar_one_or_none()

        if formula is None:
            return ReferenceResolution(
                resolved=False,
                dangling=True,
                source_formula_id=str(src_uuid),
                chain=[str(src_uuid)],
                issue={
                    "code": "DANGLING_REFERENCE",
                    "description": (
                        f"参照来源公式 {src_uuid} 不存在（可能已删除）"
                    ),
                    "path": [str(src_uuid)],
                },
            )

        return ReferenceResolution(
            resolved=True,
            expression=formula.expression,
            source_formula_id=str(formula.id),
            source_version=get_formula_version(formula),
            source_hash=compute_expression_hash(formula.expression),
            chain=[str(formula.id)],
        )

    # 有 project_id 时使用完整链解析
    return await resolve_reference_chain(
        db,
        formula_id=src_uuid,
        project_id=project_id,
        reference_mode="live",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 依赖方查询
# ═══════════════════════════════════════════════════════════════════════════════


async def find_reference_dependents(
    db: AsyncSession, *, source_formula_id: uuid.UUID | str
) -> list[WpFormula]:
    """查找所有以 source_formula_id 为参照源的引用方公式。"""
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


# ═══════════════════════════════════════════════════════════════════════════════
# 源变更 outbox stale 标记（Req 5.4 / 5.6）
# ═══════════════════════════════════════════════════════════════════════════════


async def mark_dependents_stale_via_outbox(
    db: AsyncSession,
    *,
    source_formula_id: uuid.UUID | str,
    project_id: uuid.UUID | str,
    trigger: str = "source_definition_change",
) -> OutboxStaleEvent | None:
    """源公式定义变化时，通过 outbox 标记引用方为 stale（Req 5.6）。

    在同一事务中写入使实时引用方和固定版本引用方可被标记 stale 的
    Outbox 事件。不直接修改引用方状态（由 outbox consumer 处理）。

    Args:
        db: AsyncSession（同一事务上下文）。
        source_formula_id: 发生变更的源公式 id。
        project_id: 项目 id。
        trigger: 触发来源标识。

    Returns:
        OutboxStaleEvent 或 None（无引用方时不写 outbox）。

    Requirements: 5.4, 5.6
    """
    dependents = await find_reference_dependents(
        db, source_formula_id=source_formula_id
    )
    if not dependents:
        return None

    src_str = str(_as_uuid(source_formula_id) or source_formula_id)
    proj_str = str(_as_uuid(project_id) or project_id)
    dep_ids = [str(d.id) for d in dependents]

    event = OutboxStaleEvent(
        event_type="reference_source_changed",
        source_formula_id=src_str,
        dependent_formula_ids=dep_ids,
        project_id=proj_str,
        trigger=trigger,
    )

    # 尝试写入 formula_runtime_outbox 表（Task 11 迁移后可用）
    # 如果表不存在（尚未迁移），降级为日志记录 + ACNR 失效链
    try:
        from app.services.formula_runtime.outbox import write_outbox_event

        await write_outbox_event(
            db,
            event_type=event.event_type,
            payload={
                "source_formula_id": event.source_formula_id,
                "dependent_formula_ids": event.dependent_formula_ids,
                "project_id": event.project_id,
                "trigger": event.trigger,
            },
            run_id=None,
        )
    except (ImportError, Exception) as exc:
        # outbox 模块尚未就绪（Task 11），降级走 ACNR 失效链
        logger.info(
            "outbox 模块不可用（降级走 ACNR 失效链）: %s", exc
        )
        try:
            from app.services.acnr.events import invalidate

            await invalidate(proj_str, trigger=trigger)
        except Exception as acnr_exc:  # noqa: BLE001
            logger.warning(
                "ACNR 失效链也触发失败: %s", acnr_exc
            )

    logger.info(
        "reference 源变更 outbox stale 标记: source=%s project=%s "
        "dependents=%d trigger=%s",
        src_str,
        proj_str,
        len(dep_ids),
        trigger,
    )
    return event


# ═══════════════════════════════════════════════════════════════════════════════
# 旧接口兼容（保留签名以免破坏下游调用）
# ═══════════════════════════════════════════════════════════════════════════════


async def invalidate_reference_dependents(
    db: AsyncSession,
    *,
    source_formula_id: uuid.UUID | str,
    project_id: uuid.UUID | str,
    trigger: str = "formula_reference_source_change",
) -> int:
    """兼容旧接口：源变更时标记引用方 stale。

    内部委托给 mark_dependents_stale_via_outbox。
    Returns:
        受影响引用方数量。
    """
    event = await mark_dependents_stale_via_outbox(
        db,
        source_formula_id=source_formula_id,
        project_id=project_id,
        trigger=trigger,
    )
    if event is None:
        return 0
    return len(event.dependent_formula_ids)


def _normalize_ref_id(value: Any) -> uuid.UUID | None:
    """对外暴露的 id 归一化助手。"""
    return _as_uuid(value)
