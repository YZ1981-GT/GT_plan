"""MCP 只读工具的**真实取数实现**（dsh-agent-panel-integration 补 Task 25/26 责任真空）

Feature: dsh-agent-panel-integration
Requirements:
  - 11.2~11.4：MCP server 零 DB，全部数据经平台受权 REST 获取 —— 取数实现必须在平台侧。
  - 11.5/11.9：每次取数在 token 校验之后**再次**经 ``ResourceAccessResolver``，
    返回值按角色脱敏。
  - 2.4：mention / HostContext / MCP callback 使用同一决策函数，不存在
    "搜索不可见但直接 ID 可读"的旁路。
  - 6.5/6.6：语义检索不可用时返回 ``semantic_unavailable``，禁止 BM25/ILIKE 伪降级。
Properties: 26（工具目录受控）· 28（跨用户隔离）· 30（五角色脱敏一致）· 16（不伪降级）

## 为什么单独一个模块

``routers/ai_chat_mcp.py`` 的 7 个 ``_tool_*`` 分发器原本是空占位
（``return {"items": []}`` / ``{"status": "placeholder"}``），注释写"实际在 Task 26 接通"，
而 Task 26 建的是**调用方**（stdio server），范围不含平台侧取数 —— 形成责任真空：
三层管道全通、207 个测试全绿，但 DSH Agent 拿不到任何底稿/试算表内容。
本模块补上这段取数，并把它放在 service 层以便被守卫直接调用（不必起 HTTP）。

## 复用而非另写一套

===============  ==========================================================
工具             复用的平台能力
===============  ==========================================================
``wp_list``      ``ResourceAccessResolver.filter_visible_resources``
                 （与 ``MentionSearchService._search_workpapers`` 同一可见集语义）
``wp_read``      ``working_paper JOIN wp_index``（``working_paper`` 无 ``wp_code``）
                 + ``parsed_data``（底稿内容真源）
``tb_query``     ``dataset_query.get_active_filter`` + ``four_table.tb_query``
                 + ``four_table.leaf_aggregation``（叶子口径 + 方向定符号）
``addr_lookup``  ``ai_chat.address_mention.resolve_address_mention``
                 （已含授权 + 脱敏 + stale 检测）
``kb_search``    ``KnowledgeIndexService.semantic_search_strict``
                 （embedding-only，失败即 typed error）
``note_read``    ``DisclosureNote``（附注行真源 = ``table_data.rows[].label/values``）
``review_prompt````ReviewPromptService.load_prompt``（三级降级）
===============  ==========================================================

## 只读

本模块只有 ``select``；不含 ``insert`` / ``update`` / ``delete`` / ``commit``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.contracts import (
    AccessDecision,
    AiChatAction,
    ResourceType,
    coerce_uuid,
)
from app.services.ai_chat.mcp_token import McpTokenPayload

logger = logging.getLogger(__name__)

__all__ = [
    "McpToolError",
    "McpToolContext",
    "MCP_TOOL_IMPLEMENTATIONS",
    "build_tool_context",
    "tool_wp_list",
    "tool_wp_read",
    "tool_tb_query",
    "tool_addr_lookup",
    "tool_kb_search",
    "tool_note_read",
    "tool_review_prompt",
]


# ---------------------------------------------------------------------------
# Typed errors（Req：资源不存在 / 无权限 / 服务不可用 各自 typed error）
# ---------------------------------------------------------------------------

#: 资源不存在（或该 ID 在本项目下不存在）
ERR_NOT_FOUND = "tool_resource_not_found"
#: 无权限（授权决策拒绝 / 跨项目 / 越出 cycle scope）
ERR_ACCESS_DENIED = "access_denied"
#: 参数非法（缺必填、ID 格式错）
ERR_INVALID_ARGUMENT = "tool_invalid_argument"
#: 语义检索服务不可用（🔴 与"空结果"不同码 —— 禁止用空 results 冒充）
ERR_SEMANTIC_UNAVAILABLE = "semantic_unavailable"
#: 依赖服务不可用（DB / 取数服务异常）
ERR_SERVICE_UNAVAILABLE = "tool_service_unavailable"


class McpToolError(Exception):
    """MCP 工具的 typed error。

    🔴 三类错误必须分离，**不得**都返回空 dict：
    ``tool_resource_not_found`` / ``access_denied`` / ``tool_service_unavailable``。
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# 行数 / 体积上限（Req：工具自身要有上限，别先构造 10 万行再被外层拒）
# ---------------------------------------------------------------------------

#: 各工具 ``limit`` 的服务端封顶（客户端传更大也按此截断）
MAX_WP_LIST = 200
MAX_TB_ROWS = 500
MAX_ADDR_ROWS = 50
MAX_KB_HITS = 20
MAX_NOTE_ROWS = 200

#: 单个文本字段的字符上限（外层还有 ``AI_MCP_MAX_BYTES_PER_CALL`` 兜底）
MAX_TEXT_CHARS = 4000
#: ``parsed_data`` 单 sheet 返回的单元格数上限
MAX_SHEET_CELLS = 200
#: 知识库片段的字符上限
MAX_KB_SNIPPET_CHARS = 1200


def _clamp(value: Any, default: int, hard_max: int) -> int:
    """把客户端 limit 归一到 ``[1, hard_max]``。"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    if n <= 0:
        n = default
    return min(n, hard_max)


def _truncate(text: Any, limit: int = MAX_TEXT_CHARS) -> str:
    s = "" if text is None else str(text)
    return s if len(s) <= limit else s[:limit] + "…（已截断）"


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# 调用上下文
# ---------------------------------------------------------------------------


@dataclass
class McpToolContext:
    """单次工具调用的授权上下文。

    ``principal`` 是从 DB 加载的真实 ``User``（角色真源 = ``users.role``，
    不用 token 里的 role 冒充），供 ``ResourceAccessResolver`` 走完整判定链。
    """

    db: AsyncSession
    token: McpTokenPayload
    host_decision: AccessDecision
    resolver: ResourceAccessResolver
    principal: Any
    #: 项目权威审计年度（``projects.audit_year``）；未设置时为 None
    year: int | None = None

    @property
    def project_id(self) -> UUID:
        return self.token.project_id

    @property
    def cycle_scope(self) -> frozenset[str]:
        return self.token.cycle_scope


async def build_tool_context(
    *,
    db: AsyncSession,
    token_payload: McpTokenPayload,
    host_decision: AccessDecision,
    resolver: ResourceAccessResolver,
) -> McpToolContext:
    """加载主体与项目年度，构造工具调用上下文。

    Raises:
        McpToolError: 主体不存在 / 已停用 ⇒ ``access_denied``（不返回空数据伪装无结果）。
    """
    from app.models.core import Project, User

    user = (
        await db.execute(
            sa.select(User).where(
                User.id == token_payload.user_id,
                User.is_active == sa.true(),
            )
        )
    ).scalar_one_or_none()
    if user is None:
        raise McpToolError(
            ERR_ACCESS_DENIED, "调用主体不存在或已停用，拒绝取数"
        )

    year = (
        await db.execute(
            sa.select(Project.audit_year).where(Project.id == token_payload.project_id)
        )
    ).scalar_one_or_none()

    return McpToolContext(
        db=db,
        token=token_payload,
        host_decision=host_decision,
        resolver=resolver,
        principal=user,
        year=year,
    )


async def _authorize_resource(
    ctx: McpToolContext,
    resource_type: ResourceType,
    resource_id: str,
    action: AiChatAction = AiChatAction.read,
) -> AccessDecision:
    """过 ``ResourceAccessResolver``；拒绝即抛 ``access_denied``。

    🔴 这是每个工具内部的**第二道**授权（第一道是 token 签名 + scope 校验）。
    """
    decision = await ctx.resolver.authorize_resource(
        ctx.principal, ctx.host_decision, resource_type, resource_id, action
    )
    if not decision.allowed:
        raise McpToolError(
            ERR_ACCESS_DENIED,
            f"无权访问该资源（{resource_type.value}）",
        )
    return decision


async def _authorize_project_scope(ctx: McpToolContext) -> AccessDecision:
    """项目级取数（试算表 / 知识库）的授权。

    试算表与项目知识库都是**项目级**数据，判定语义与报表宿主一致
    （``ResourceAccessResolver._authorize_project_resource``：角色动作上界 +
    active ``ProjectUser`` 成员关系 + ``scope_cycles`` 上界）。报表宿主的稳定 ID
    取值域真源 = ``contracts.REPORT_HOST_IDS``，此处取其中的资产负债表作探针，
    不新建第二套项目级判定。
    """
    from app.services.ai_chat.contracts import REPORT_HOST_IDS

    probe = "balance_sheet" if "balance_sheet" in REPORT_HOST_IDS else sorted(REPORT_HOST_IDS)[0]
    return await _authorize_resource(ctx, ResourceType.report, probe, AiChatAction.read)


def _assert_same_project(ctx: McpToolContext, project_id: Any) -> None:
    """资源所属项目必须等于 token 绑定项目（Property 28：交换 project 即拒绝）。"""
    if project_id is None or str(project_id) != str(ctx.project_id):
        raise McpToolError(
            ERR_ACCESS_DENIED, "资源不属于当前 token 绑定的项目，拒绝取数"
        )


def _in_token_cycle_scope(ctx: McpToolContext, cycle: Any) -> bool:
    """底稿循环是否在 token 授权范围内。

    ``cycle_scope`` 为空集时表示 token 未做循环收窄（沿用平台 scope 上界），
    不做额外裁剪；非空时**必须**逐条裁剪（Req 2.6：mention/RAG/MCP 共用同一上界）。
    """
    scope = ctx.cycle_scope
    if not scope:
        return True
    return str(cycle or "") in scope


# ---------------------------------------------------------------------------
# ① wp_list
# ---------------------------------------------------------------------------


async def tool_wp_list(ctx: McpToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """列出当前项目**有权访问**的底稿。

    复用 ``ResourceAccessResolver.filter_visible_resources``（底稿走平台既有
    ``make_bulk_visible_filter``，与批量导出同一可见集语义）；再按 token 的
    ``cycle_scope`` 收窄。不可见项静默剔除，不泄露存在性（Req 2.5）。
    """
    from app.models.workpaper_models import WorkingPaper, WpIndex

    cycle = str(arguments.get("cycle") or "").strip()
    status = str(arguments.get("status") or "").strip()
    limit = _clamp(arguments.get("limit"), 50, MAX_WP_LIST)

    conditions = [
        WorkingPaper.project_id == ctx.project_id,
        WorkingPaper.is_deleted == sa.false(),
        WpIndex.is_deleted == sa.false(),
    ]
    if cycle:
        conditions.append(WpIndex.audit_cycle == cycle)
    if status:
        conditions.append(sa.cast(WorkingPaper.status, sa.String) == status)
    # SQL 层就按 token cycle_scope 下推（避免先取全量再内存过滤）
    if ctx.cycle_scope:
        conditions.append(WpIndex.audit_cycle.in_(sorted(ctx.cycle_scope)))

    stmt = (
        sa.select(
            WorkingPaper.id,
            WorkingPaper.project_id,
            WorkingPaper.status,
            WorkingPaper.review_status,
            WorkingPaper.updated_at,
            WpIndex.wp_code,
            WpIndex.wp_name,
            WpIndex.audit_cycle,
        )
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(sa.and_(*conditions))
        .order_by(WpIndex.wp_code)
        .limit(limit)
    )
    rows = (await ctx.db.execute(stmt)).all()
    if not rows:
        return {
            "project_id": str(ctx.project_id),
            "scope": sorted(ctx.cycle_scope),
            "items": [],
            "total": 0,
        }

    visible = set(
        await ctx.resolver.filter_visible_resources(
            ctx.principal,
            ctx.host_decision,
            ResourceType.workpaper,
            [str(r.id) for r in rows],
            AiChatAction.search,
        )
    )

    items: list[dict[str, Any]] = []
    for r in rows:
        if str(r.id) not in visible:
            continue
        if not _in_token_cycle_scope(ctx, r.audit_cycle):
            continue
        items.append(
            {
                "wp_id": str(r.id),
                "wp_code": r.wp_code or "",
                "wp_name": r.wp_name or "",
                "cycle": r.audit_cycle or "",
                "status": _enum_value(r.status),
                "review_status": _enum_value(r.review_status),
                "updated_at": r.updated_at.isoformat() if r.updated_at else "",
            }
        )

    return {
        "project_id": str(ctx.project_id),
        "scope": sorted(ctx.cycle_scope),
        "items": items,
        "total": len(items),
    }


def _enum_value(raw: Any) -> str:
    value = getattr(raw, "value", raw)
    return str(value) if value is not None else ""


# ---------------------------------------------------------------------------
# ② wp_read
# ---------------------------------------------------------------------------


async def tool_wp_read(ctx: McpToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """读取指定底稿内容。

    🔴 ``working_paper`` 表**无** ``wp_code``（在 ``wp_index``，须 JOIN）；
    底稿内容真源是 ``working_paper.parsed_data``（无 ``content`` 列）。
    """
    from app.models.workpaper_models import WorkingPaper, WpIndex

    wp_id = str(arguments.get("wp_id") or "").strip()
    if not wp_id:
        raise McpToolError(ERR_INVALID_ARGUMENT, "缺少 wp_id 参数")
    if coerce_uuid(wp_id) is None:
        raise McpToolError(ERR_INVALID_ARGUMENT, "wp_id 不是合法 UUID")

    sheet_name = str(arguments.get("sheet_name") or "").strip()
    include_data = bool(arguments.get("include_data", True))

    # ── 授权先于任何正文读取（Req 2.5 / Property 1）──
    await _authorize_resource(ctx, ResourceType.workpaper, wp_id, AiChatAction.read)

    row = (
        await ctx.db.execute(
            sa.select(
                WorkingPaper.id,
                WorkingPaper.project_id,
                WorkingPaper.status,
                WorkingPaper.review_status,
                WorkingPaper.file_version,
                WorkingPaper.updated_at,
                WorkingPaper.parsed_data,
                WpIndex.wp_code,
                WpIndex.wp_name,
                WpIndex.audit_cycle,
            )
            .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
            .where(
                WorkingPaper.id == UUID(wp_id),
                WorkingPaper.is_deleted == sa.false(),
            )
        )
    ).first()
    if row is None:
        raise McpToolError(ERR_NOT_FOUND, "底稿不存在或已删除")

    _assert_same_project(ctx, row.project_id)
    if not _in_token_cycle_scope(ctx, row.audit_cycle):
        raise McpToolError(
            ERR_ACCESS_DENIED, "该底稿所属循环不在当前授权范围内"
        )

    parsed = row.parsed_data if isinstance(row.parsed_data, dict) else {}
    sheet_names = _collect_sheet_names(parsed)

    result: dict[str, Any] = {
        "wp_id": str(row.id),
        "wp_code": row.wp_code or "",
        "wp_name": row.wp_name or "",
        "cycle": row.audit_cycle or "",
        "status": _enum_value(row.status),
        "review_status": _enum_value(row.review_status),
        "file_version": int(row.file_version or 0),
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        "sheets": sheet_names,
        "content": {},
    }

    if not include_data:
        return result

    if sheet_name:
        if sheet_name not in sheet_names:
            raise McpToolError(
                ERR_NOT_FOUND, f"底稿中不存在 sheet「{sheet_name}」"
            )
        result["content"] = {
            "sheet_name": sheet_name,
            "cells": _extract_sheet_cells(parsed, sheet_name),
        }
    else:
        result["content"] = _extract_workpaper_summary(parsed, sheet_names)

    return result


def _collect_sheet_names(parsed: dict[str, Any]) -> list[str]:
    """从 ``parsed_data`` 汇总 sheet 名（``sheets`` 与 ``html_data`` 两种形态并存）。"""
    names: list[str] = []
    for key in ("sheets", "html_data"):
        block = parsed.get(key)
        if isinstance(block, dict):
            for name in block:
                if name not in names:
                    names.append(str(name))
    return names


def _extract_sheet_cells(parsed: dict[str, Any], sheet_name: str) -> dict[str, Any]:
    """取单个 sheet 的单元格（截断到 ``MAX_SHEET_CELLS``）。"""
    for key in ("html_data", "sheets"):
        block = parsed.get(key)
        if not isinstance(block, dict):
            continue
        sheet = block.get(sheet_name)
        if sheet is None:
            continue
        cells = sheet.get("cells") if isinstance(sheet, dict) else None
        if isinstance(cells, dict):
            trimmed = dict(list(cells.items())[:MAX_SHEET_CELLS])
            return {
                "cells": trimmed,
                "cell_count": len(cells),
                "truncated": len(cells) > MAX_SHEET_CELLS,
            }
        if isinstance(sheet, dict):
            return {"raw": _truncate(sheet)}
    return {}


def _extract_workpaper_summary(
    parsed: dict[str, Any], sheet_names: list[str]
) -> dict[str, Any]:
    """不指定 sheet 时返回结构概要（不倒出全部正文）。"""
    checklist = parsed.get("checklist_responses")
    return {
        "sheet_count": len(sheet_names),
        "has_html_data": isinstance(parsed.get("html_data"), dict),
        "has_cells": isinstance(parsed.get("cells"), dict),
        "checklist_item_count": len(checklist) if isinstance(checklist, (list, dict)) else 0,
        "top_level_keys": sorted(str(k) for k in parsed)[:50],
    }


# ---------------------------------------------------------------------------
# ③ tb_query
# ---------------------------------------------------------------------------


async def tool_tb_query(ctx: McpToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """查询试算表 / 科目余额。

    两种模式：

    ``leaf_aggregate``（传了 ``account_code``）
        走 ``four_table.tb_query.fetch_tb_subtree``（内部 ``get_active_filter``）取整棵
        子树 → ``select_leaves`` 只留叶子 → ``resolve_leaf_totals`` 按
        ``closing_direction`` / ``opening_direction`` 定符号求和，并与父科目额勾稽自检。

    ``top_level``（未传 ``account_code``）
        返回一级科目行（``account_code`` 不含 ``.``）—— 一级行本身就是科目族合计，
        不需要叶子聚合；``get_active_filter`` 锁定 active 数据集。

    🔴 ``tb_balance`` 是**无符号绝对值 + 方向列**，求和必按方向带符号；
    🔴 只汇总**叶子**科目（父子双算是历史事故的根源）。
    """
    from app.models.audit_platform_models import TbBalance
    from app.services.dataset_query import get_active_filter
    from app.services.four_table.leaf_aggregation import (
        resolve_leaf_totals,
        select_leaves,
    )
    from app.services.four_table.tb_query import fetch_tb_subtree

    await _authorize_project_scope(ctx)

    account_code = str(arguments.get("account_code") or "").strip()
    period = str(arguments.get("period") or "current").strip() or "current"
    limit = _clamp(arguments.get("limit"), 100, MAX_TB_ROWS)
    year = int(ctx.year or 0)

    base: dict[str, Any] = {
        "project_id": str(ctx.project_id),
        "year": year,
        "period": period,
        "account_code": account_code,
    }

    if account_code:
        subtree = await fetch_tb_subtree(ctx.db, ctx.project_id, year, [account_code])
        if not subtree:
            return {**base, "mode": "leaf_aggregate", "rows": [], "totals": {}, "total": 0}

        leaves = [r for r in select_leaves(subtree) if r.account_code != account_code]
        # 父科目本身就是叶子（无子科目）时，叶子集就是它自己
        if not leaves:
            leaves = [r for r in select_leaves(subtree)]
        totals = resolve_leaf_totals(subtree, account_code)
        rows = [_leaf_row_dict(r) for r in leaves[:limit]]
        return {
            **base,
            "mode": "leaf_aggregate",
            "rows": rows,
            "totals": totals.as_dict(),
            "total": len(leaves),
            "truncated": len(leaves) > limit,
        }

    # ── top_level 模式 ──
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_direction,
                TbBalance.opening_direction,
            )
            .where(
                sa.and_(
                    active_filter,
                    TbBalance.account_code.notlike("%.%"),
                )
            )
            .order_by(TbBalance.account_code)
            .limit(limit)
        )
        rows = result.all()
    except Exception as exc:  # noqa: BLE001 — 依赖服务异常必须 typed error，不静默取空
        logger.error("tb_query 取数失败 project=%s: %s", ctx.project_id, exc, exc_info=True)
        try:
            await ctx.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise McpToolError(
            ERR_SERVICE_UNAVAILABLE, "科目余额取数失败，请稍后重试"
        ) from exc

    return {
        **base,
        "mode": "top_level",
        "rows": [
            {
                "account_code": r.account_code,
                "account_name": r.account_name or "",
                "opening": _f(r.opening_balance),
                "closing": _f(r.closing_balance),
                "debit": _f(r.debit_amount),
                "credit": _f(r.credit_amount),
                "closing_direction": r.closing_direction or "",
                "opening_direction": r.opening_direction or "",
            }
            for r in rows
        ],
        "totals": {},
        "total": len(rows),
    }


def _leaf_row_dict(row: Any) -> dict[str, Any]:
    return {
        "account_code": row.account_code,
        "account_name": row.account_name or "",
        "opening": row.opening,
        "closing": row.closing,
        "debit": row.debit,
        "credit": row.credit,
        "closing_direction": row.direction or "",
        "opening_direction": row.opening_direction or "",
        "is_leaf": True,
    }


# ---------------------------------------------------------------------------
# ④ addr_lookup
# ---------------------------------------------------------------------------


async def tool_addr_lookup(
    ctx: McpToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """查询地址坐标。

    直接复用 ``ai_chat.address_mention.resolve_address_mention``（已含授权 +
    角色脱敏 + stale 检测），不重写第二套地址取值。
    """
    from app.services.ai_chat.address_mention import resolve_address_mention

    addr_id = str(arguments.get("addr_id") or "").strip()
    query = str(arguments.get("query") or "").strip()
    domain = str(arguments.get("domain") or "").strip()
    limit = _clamp(arguments.get("limit"), 10, MAX_ADDR_ROWS)

    if not addr_id and not query:
        raise McpToolError(ERR_INVALID_ARGUMENT, "addr_lookup 需要 addr_id 或 query")

    if addr_id:
        # 授权先行 —— 与"不存在"分码（resolve_address_mention 对两者都返 None）
        await _authorize_resource(ctx, ResourceType.address, addr_id, AiChatAction.read)
        detail = await resolve_address_mention(
            ctx.db,
            user=ctx.principal,
            host_decision=ctx.host_decision,
            addr_id=addr_id,
            project_id=ctx.project_id,
        )
        if detail is None:
            raise McpToolError(ERR_NOT_FOUND, "地址坐标不存在")
        return {
            "project_id": str(ctx.project_id),
            "mode": "exact",
            "items": [_address_detail_dict(detail)],
            "total": 1,
        }

    candidates = await _search_address_ids(ctx, query, domain, limit)
    items: list[dict[str, Any]] = []
    for cand in candidates:
        cand_decision = await ctx.resolver.authorize_resource(
            ctx.principal, ctx.host_decision, ResourceType.address, cand,
            AiChatAction.search,
        )
        if not cand_decision.allowed:
            continue  # 搜索场景静默剔除，不泄露存在性
        detail = await resolve_address_mention(
            ctx.db,
            user=ctx.principal,
            host_decision=ctx.host_decision,
            addr_id=cand,
            project_id=ctx.project_id,
        )
        if detail is not None:
            items.append(_address_detail_dict(detail))

    return {
        "project_id": str(ctx.project_id),
        "mode": "search",
        "query": query,
        "domain": domain,
        "items": items,
        "total": len(items),
    }


async def _search_address_ids(
    ctx: McpToolContext, query: str, domain: str, limit: int
) -> list[str]:
    """用平台既有 ``address_registry.search`` 取候选 addr_id（不含权限）。"""
    try:
        from app.services.address_registry import address_registry

        entries = await address_registry.search(
            ctx.db, str(ctx.project_id), 0, query, domain, "soe", limit
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("addr_lookup 候选检索失败: %s", exc)
        raise McpToolError(
            ERR_SERVICE_UNAVAILABLE, "地址坐标检索服务不可用"
        ) from exc

    out: list[str] = []
    for e in entries or []:
        addr_id = getattr(e, "formula_ref", "") or getattr(e, "uri", "")
        if addr_id and addr_id not in out:
            out.append(str(addr_id))
    return out[:limit]


def _address_detail_dict(detail: Any) -> dict[str, Any]:
    return {
        "addr_id": detail.addr_id,
        "label": detail.label,
        "domain": detail.domain,
        "uri": detail.uri,
        "formula_ref": detail.formula_ref,
        "jump_route": detail.jump_route,
        "current_value": detail.current_value,
        "version": detail.version,
        "stale": detail.stale,
        "wp_code": detail.wp_code,
        "account_code": detail.account_code,
        "note_section": detail.note_section,
    }


# ---------------------------------------------------------------------------
# ⑤ kb_search
# ---------------------------------------------------------------------------

#: MCP ``scope`` 参数 → ``KnowledgeIndexService`` 的 scope 取值
_KB_SCOPE_MAP = {
    "project": "all",
    "global": "knowledge_doc",
    "project_data": "project_data",
    "knowledge_doc": "knowledge_doc",
    "all": "all",
}


async def tool_kb_search(
    ctx: McpToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """搜索知识库（**只走 embedding 语义检索**）。

    🔴 Property 16：embedding 不可用时抛 ``semantic_unavailable``，
    **禁止** BM25/ILIKE 伪降级 —— 那会把"检索服务坏了"伪装成"没搜到"。
    平台 ``KnowledgeIndexService.semantic_search`` 自带 BM25/ILIKE 兜底，
    故此处调其严格版 ``semantic_search_strict``。
    """
    from app.services.ai_chat.address_index_source import EmbeddingUnavailableError
    from app.services.knowledge_index_service import KnowledgeIndexService

    query = str(arguments.get("query") or "").strip()
    if not query:
        raise McpToolError(ERR_INVALID_ARGUMENT, "kb_search 缺少 query 参数")

    scope_raw = str(arguments.get("scope") or "project").strip()
    scope = _KB_SCOPE_MAP.get(scope_raw)
    if scope is None:
        raise McpToolError(
            ERR_INVALID_ARGUMENT, f"不支持的 scope「{scope_raw}」"
        )
    limit = _clamp(arguments.get("limit"), 10, MAX_KB_HITS)

    await _authorize_project_scope(ctx)

    service = KnowledgeIndexService(ctx.db)
    try:
        hits = await service.semantic_search_strict(
            ctx.project_id, query, top_k=limit, scope=scope, user=ctx.principal
        )
    except EmbeddingUnavailableError as exc:
        raise McpToolError(
            ERR_SEMANTIC_UNAVAILABLE,
            "语义检索服务当前不可用，本次未使用语义匹配结果",
        ) from exc

    return {
        "project_id": str(ctx.project_id),
        "query": query,
        "scope": scope_raw,
        "results": [
            {
                "source_type": h.get("source_type", ""),
                "source_id": h.get("source_id", ""),
                "content": _truncate(h.get("content"), MAX_KB_SNIPPET_CHARS),
                "score": h.get("score", 0.0),
                "document_name": h.get("document_name"),
                "folder_path": h.get("folder_path"),
                "is_stale": bool(h.get("is_stale", False)),
            }
            for h in hits[:limit]
        ],
        "total": len(hits[:limit]),
    }


# ---------------------------------------------------------------------------
# ⑥ note_read
# ---------------------------------------------------------------------------


async def tool_note_read(
    ctx: McpToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """读取附注。

    🔴 附注行真源 = ``table_data.rows[].label`` + ``rows[].values``
    （离线导入的 ``cells`` 是中间结构，不是渲染真源）。
    """
    from app.models.report_models import DisclosureNote

    note_id = str(arguments.get("note_id") or "").strip()
    section_key = str(arguments.get("section_key") or "").strip()
    chapter = str(arguments.get("chapter") or "").strip()
    limit = _clamp(arguments.get("limit"), 20, MAX_NOTE_ROWS)

    if note_id:
        if coerce_uuid(note_id) is None:
            raise McpToolError(ERR_INVALID_ARGUMENT, "note_id 不是合法 UUID")
        await _authorize_resource(ctx, ResourceType.note, note_id, AiChatAction.read)
        row = (
            await ctx.db.execute(
                sa.select(DisclosureNote).where(
                    DisclosureNote.id == UUID(note_id),
                    DisclosureNote.is_deleted == sa.false(),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise McpToolError(ERR_NOT_FOUND, "附注不存在或已删除")
        _assert_same_project(ctx, row.project_id)
        return {
            "project_id": str(ctx.project_id),
            "mode": "exact",
            "items": [_note_dict(row, limit)],
            "total": 1,
        }

    conditions = [
        DisclosureNote.project_id == ctx.project_id,
        DisclosureNote.is_deleted == sa.false(),
    ]
    if ctx.year:
        conditions.append(DisclosureNote.year == int(ctx.year))
    if section_key:
        conditions.append(
            sa.or_(
                DisclosureNote.section_id == section_key,
                DisclosureNote.note_section.ilike(f"%{section_key}%"),
                DisclosureNote.section_title.ilike(f"%{section_key}%"),
            )
        )
    if chapter:
        conditions.append(DisclosureNote.note_section.ilike(f"{chapter}%"))

    rows = (
        (
            await ctx.db.execute(
                sa.select(DisclosureNote)
                .where(sa.and_(*conditions))
                .order_by(DisclosureNote.sort_index, DisclosureNote.note_section)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return {
            "project_id": str(ctx.project_id),
            "mode": "list",
            "items": [],
            "total": 0,
        }

    visible = set(
        await ctx.resolver.filter_visible_resources(
            ctx.principal,
            ctx.host_decision,
            ResourceType.note,
            [str(r.id) for r in rows],
            AiChatAction.search,
        )
    )
    items = [_note_dict(r, limit) for r in rows if str(r.id) in visible]
    return {
        "project_id": str(ctx.project_id),
        "mode": "list",
        "items": items,
        "total": len(items),
    }


def _note_dict(row: Any, row_limit: int) -> dict[str, Any]:
    table_data = row.table_data if isinstance(row.table_data, dict) else {}
    raw_rows = table_data.get("rows")
    note_rows: list[dict[str, Any]] = []
    if isinstance(raw_rows, list):
        for item in raw_rows[:row_limit]:
            if not isinstance(item, dict):
                continue
            note_rows.append(
                {
                    "label": _truncate(item.get("label"), 200),
                    "values": list(item.get("values") or []),
                }
            )
    return {
        "note_id": str(row.id),
        "note_section": row.note_section or "",
        "section_title": row.section_title or "",
        "section_id": row.section_id or "",
        "year": int(row.year or 0),
        "status": _enum_value(row.status),
        "content_type": _enum_value(row.content_type),
        "text_content": _truncate(row.text_content),
        "rows": note_rows,
        "row_count": len(raw_rows) if isinstance(raw_rows, list) else 0,
        "column_groups": table_data.get("_column_groups") or [],
        "is_stale": bool(row.is_stale),
    }


# ---------------------------------------------------------------------------
# ⑦ review_prompt
# ---------------------------------------------------------------------------


async def tool_review_prompt(
    ctx: McpToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """获取复核提示。

    复用 ``ReviewPromptService.load_prompt``（sheet → subject → base 三级降级）。
    🔴 只返回 ``source_level`` / ``tips`` / ``checklist`` / ``risk_areas`` / ``version``，
    **不返回提示词正文**（Req 9.2：正文只在服务端 SystemMessageAssembler 内消费）。
    """
    from app.models.workpaper_models import WorkingPaper, WpIndex

    wp_id = str(arguments.get("wp_id") or "").strip()
    wp_code = str(arguments.get("wp_code") or "").strip()
    sheet_name = str(arguments.get("sheet_name") or "").strip() or None

    if not wp_id and not wp_code:
        raise McpToolError(
            ERR_INVALID_ARGUMENT, "review_prompt 需要 wp_id 或 wp_code"
        )

    # 定位底稿实例：wp_code 也要落到具体底稿才能授权（Req 2.4 同一决策函数）
    if wp_id:
        if coerce_uuid(wp_id) is None:
            raise McpToolError(ERR_INVALID_ARGUMENT, "wp_id 不是合法 UUID")
        locator = sa.and_(
            WorkingPaper.id == UUID(wp_id),
            WorkingPaper.is_deleted == sa.false(),
        )
    else:
        locator = sa.and_(
            WorkingPaper.project_id == ctx.project_id,
            WpIndex.wp_code == wp_code,
            WorkingPaper.is_deleted == sa.false(),
        )

    row = (
        await ctx.db.execute(
            sa.select(
                WorkingPaper.id,
                WorkingPaper.project_id,
                WpIndex.wp_code,
                WpIndex.audit_cycle,
            )
            .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
            .where(locator)
            .limit(1)
        )
    ).first()
    if row is None:
        raise McpToolError(ERR_NOT_FOUND, "底稿不存在，无法加载复核提示")

    await _authorize_resource(
        ctx, ResourceType.workpaper, str(row.id), AiChatAction.review
    )
    _assert_same_project(ctx, row.project_id)
    if not _in_token_cycle_scope(ctx, row.audit_cycle):
        raise McpToolError(
            ERR_ACCESS_DENIED, "该底稿所属循环不在当前授权范围内"
        )

    resolved_code = row.wp_code or wp_code
    try:
        from app.services.review_prompt_service import ReviewPromptService

        prompt = ReviewPromptService().load_prompt(resolved_code, sheet_name)
    except Exception as exc:  # noqa: BLE001 — typed error，不静默返回空提示
        logger.error(
            "review_prompt 加载失败 wp_code=%s sheet=%s: %s",
            resolved_code, sheet_name, exc, exc_info=True,
        )
        raise McpToolError(
            ERR_SERVICE_UNAVAILABLE, "复核提示词加载失败"
        ) from exc

    return {
        "wp_id": str(row.id),
        "wp_code": resolved_code,
        "sheet_name": sheet_name or "",
        "source_level": prompt.source_level,
        "version": prompt.version or "",
        "tips": list(prompt.tips or []),
        "checklist": list(prompt.checklist or []),
        "risk_areas": [
            {"level": ra.level, "text": ra.text} for ra in (prompt.risk_areas or [])
        ],
        "prompts": list(prompt.tips or []),
    }


# ---------------------------------------------------------------------------
# 工具名 → 实现（单一真源；与 MCP_READONLY_TOOLS 等势由守卫断言）
# ---------------------------------------------------------------------------

MCP_TOOL_IMPLEMENTATIONS = {
    "wp_list": tool_wp_list,
    "wp_read": tool_wp_read,
    "tb_query": tool_tb_query,
    "addr_lookup": tool_addr_lookup,
    "kb_search": tool_kb_search,
    "note_read": tool_note_read,
    "review_prompt": tool_review_prompt,
}
