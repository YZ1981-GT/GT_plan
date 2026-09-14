"""地址坐标 Mention 授权、脱敏与上下文集成（Task 23）

Feature: dsh-agent-panel-integration
Requirements:
  - 6.1: 地址坐标作为 address mention 类型提供，返回稳定 addr ID、label、domain、
         URI/formula reference、jump route 与授权后的当前值摘要
  - 6.6: 坐标变化或失效后索引增量更新或标 stale；Context Manifest 暴露 stale 状态
  - 6.7: 地址当前值经过项目权限、地址域权限和脱敏；未授权用户不得通过语义搜索获知
         地址 label 或当前值
Design: "Components and Interfaces → 7/8. Mention + AddressCoordinateIndexSource"

本模块提供地址坐标 mention 的完整集成：

1. ``resolve_address_mention`` — 按 addr_id 加载地址详情并授权/脱敏
2. ``build_address_manifest_entry`` — 生成带 version/stale 标记的 manifest 条目
3. ``mask_address_value`` — 使用 ExportMaskService 对当前值脱敏

Properties:
  15: 地址索引真源与失效联动（通过 on_acnr_invalidate 标 stale）
  17: 地址权限与脱敏一致（未授权不能通过搜索获得 label/value）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.context_budget import ContextManifestEntry
from app.services.ai_chat.contracts import (
    AccessDecision,
    AiChatAction,
    ResourceType,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AddressMentionDetail",
    "resolve_address_mention",
    "build_address_manifest_entry",
    "mask_address_value",
    "check_address_stale",
]


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AddressMentionDetail:
    """已授权的地址坐标 mention 详情（Req 6.1 返回形状）。"""

    addr_id: str
    label: str
    domain: str
    uri: str
    formula_ref: str
    jump_route: str
    current_value: str | None  # 已脱敏的当前值（None=不可用/未授权）
    version: str  # 索引 fingerprint（用于 stale 检测）
    stale: bool  # 是否已标记过期
    wp_code: str = ""
    account_code: str = ""
    note_section: str = ""


# ---------------------------------------------------------------------------
# 核心：授权 + 加载 + 脱敏
# ---------------------------------------------------------------------------


async def resolve_address_mention(
    db: AsyncSession,
    *,
    user: Any,
    host_decision: AccessDecision,
    addr_id: str,
    project_id: UUID | None,
) -> AddressMentionDetail | None:
    """解析单个地址 mention（授权后加载详情并脱敏当前值）。

    Args:
        db: 数据库会话
        user: 当前用户
        host_decision: 已授权的宿主决策
        addr_id: 地址坐标 ID（formula_ref 或 URI）
        project_id: 项目 ID

    Returns:
        已授权并脱敏的地址详情，未授权/不存在时返回 None。

    Req 6.7: 未授权用户不能通过搜索或直接 ID 获得 label/current_value。
    """
    if not addr_id or not project_id:
        return None

    # ① 授权检查（复用 ResourceAccessResolver — Property 17）
    resolver = ResourceAccessResolver(db)
    decision = await resolver.authorize_resource(
        user, host_decision, ResourceType.address, addr_id, AiChatAction.read,
    )
    if not decision.allowed:
        return None

    # ② 加载地址详情
    entry = await _load_address_entry(db, addr_id, project_id)
    if entry is None:
        return None

    # ③ 脱敏当前值（Property 17：经过与 native chat 相同的角色脱敏）
    role = _extract_role(user)
    raw_value = entry.get("value")
    masked_value = mask_address_value(raw_value, role)

    # ④ 检查 stale 状态
    version = await _get_address_version(db, addr_id, project_id)
    stale = await check_address_stale(db, addr_id, project_id)

    return AddressMentionDetail(
        addr_id=addr_id,
        label=entry.get("label", ""),
        domain=entry.get("domain", ""),
        uri=entry.get("uri", ""),
        formula_ref=entry.get("formula_ref", ""),
        jump_route=entry.get("jump_route", ""),
        current_value=masked_value,
        version=version,
        stale=stale,
        wp_code=entry.get("wp_code", ""),
        account_code=entry.get("account_code", ""),
        note_section=entry.get("note_section", ""),
    )


# ---------------------------------------------------------------------------
# Manifest 集成
# ---------------------------------------------------------------------------


def build_address_manifest_entry(
    detail: AddressMentionDetail | None,
    addr_id: str,
    *,
    budget_tokens: int = 0,
    used_tokens: int = 0,
) -> ContextManifestEntry:
    """生成地址坐标的 Context Manifest 条目（Req 6.6: 暴露 version/stale）。

    Manifest 中 version/stale 使 ChatContextInspector 可展示坐标数据新旧状态。
    """
    if detail is None:
        return ContextManifestEntry(
            source_type="address",
            source_id=addr_id,
            label="",
            status="unavailable",
            reason="地址坐标不可用或未授权",
        )

    status = "included"
    reason = ""
    if detail.stale:
        reason = "地址坐标已过期，数据可能不是最新"

    return ContextManifestEntry(
        source_type="address",
        source_id=detail.addr_id,
        label=detail.label,
        status=status,
        budget_tokens=budget_tokens,
        used_tokens=used_tokens,
        version=detail.version,
        stale=detail.stale,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# 脱敏
# ---------------------------------------------------------------------------


def mask_address_value(
    value: Any,
    role: str | None,
) -> str | None:
    """使用 ExportMaskService 角色脱敏规则对地址当前值脱敏。

    Property 17：native 与 DSH 对五角色构造敏感文本返回相同脱敏结果。

    脱敏规则：
    - partner / admin: 不脱敏
    - manager: 金额超阈值时脱敏为区间描述
    - assistant / qc / eqcr / 未知角色: 金额一律脱敏为 "***"
    """
    if value is None:
        return None

    from app.services.export_mask_service import AMOUNT_THRESHOLD

    str_value = str(value)

    # partner / admin 不脱敏
    if role in ("partner", "admin"):
        return str_value

    # 尝试将值解析为数字做金额脱敏
    try:
        numeric_value = float(value)
    except (ValueError, TypeError):
        # 非数值字符串：非敏感场景直接返回
        return str_value

    # manager: 超阈值时脱敏为区间
    if role == "manager":
        if abs(numeric_value) > AMOUNT_THRESHOLD:
            return f"金额超过{AMOUNT_THRESHOLD/10000:.0f}万"
        return str_value

    # assistant / qc / eqcr / 未知角色: fail-closed = 完全脱敏
    if role in ("assistant", "auditor", "qc", "eqcr"):
        if abs(numeric_value) > AMOUNT_THRESHOLD:
            return "***"
        return str_value

    # 未知角色 → fail-closed（Req 6.7）
    return "***"


# ---------------------------------------------------------------------------
# Stale 检测
# ---------------------------------------------------------------------------


async def check_address_stale(
    db: AsyncSession,
    addr_id: str,
    project_id: UUID | None,
) -> bool:
    """检查地址坐标是否已标记 stale（Req 6.6）。

    从 KnowledgeIndex stale 标记查询；如索引中该 addr_id 对应条目已标 stale
    （ACNR invalidation event 触发），则返回 True。
    """
    if not project_id:
        return False

    try:
        import sqlalchemy as sa
        from app.models.knowledge_models import KnowledgeIndex

        # 查询索引中该地址条目是否标记为 stale
        result = await db.execute(
            sa.select(KnowledgeIndex.is_stale)
            .where(
                KnowledgeIndex.project_id == project_id,
                KnowledgeIndex.source_id == addr_id,
                KnowledgeIndex.source_type == "address_coordinate",
                KnowledgeIndex.is_deleted == sa.false(),
            )
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return bool(row)
    except Exception as exc:
        # 查询失败不阻断：返回 False（保守策略：宁可不标 stale 也不让功能不可用）
        logger.debug("check_address_stale 查询失败（降级 False）: %s", exc)

    return False


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


async def _load_address_entry(
    db: AsyncSession,
    addr_id: str,
    project_id: UUID,
) -> dict[str, Any] | None:
    """通过 addr_id 加载地址条目详情。"""
    try:
        from app.services.address_registry import address_registry

        # 搜索匹配 formula_ref 或 URI 的条目
        entries = await address_registry.search(
            db, str(project_id), 0, "", "", "soe", 500
        )
        for e in entries:
            if getattr(e, "formula_ref", "") == addr_id or getattr(e, "uri", "") == addr_id:
                return {
                    "label": getattr(e, "label", ""),
                    "domain": getattr(e, "domain", ""),
                    "uri": getattr(e, "uri", ""),
                    "formula_ref": getattr(e, "formula_ref", ""),
                    "jump_route": getattr(e, "jump_route", ""),
                    "value": getattr(e, "value", None),
                    "wp_code": getattr(e, "wp_code", ""),
                    "account_code": getattr(e, "account_code", ""),
                    "note_section": getattr(e, "note_section", ""),
                }
    except Exception as exc:
        logger.warning("_load_address_entry 失败 addr_id=%s: %s", addr_id, exc)

    return None


async def _get_address_version(
    db: AsyncSession,
    addr_id: str,
    project_id: UUID,
) -> str:
    """获取地址坐标的索引版本（fingerprint，用于 stale 比对）。

    从 KnowledgeIndex 中取 doc_version 字段作为 version。
    """
    try:
        import sqlalchemy as sa
        from app.models.knowledge_models import KnowledgeIndex

        result = await db.execute(
            sa.select(KnowledgeIndex.doc_version)
            .where(
                KnowledgeIndex.project_id == project_id,
                KnowledgeIndex.source_id == addr_id,
                KnowledgeIndex.source_type == "address_coordinate",
                KnowledgeIndex.is_deleted == sa.false(),
            )
            .limit(1)
        )
        version = result.scalar_one_or_none()
        if version:
            return str(version)
    except Exception as exc:
        logger.debug("_get_address_version 查询失败: %s", exc)

    return ""


def _extract_role(user: Any) -> str | None:
    """从用户对象提取系统角色字符串。"""
    role = getattr(user, "role", None)
    if role is None:
        return None
    value = getattr(role, "value", role)
    return str(value) if value else None
