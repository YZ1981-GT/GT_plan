"""CrossSheetTraceOrchestrator — 跨 sheet 溯源异步编排层

处理 design.md §Architecture「异步陷阱处理」：`CrossSheetResolver.resolve` 是
**同步纯函数**（仅公式字符串 BFS，读 `parsed_data.univer_snapshot`，无 IO），若在其内部
直接 `await`/`asyncio.run(full_resolve(...))` 会在已运行的事件循环中抛错。

本编排层把身份判定与 IO **全部上浮**到 orchestrator（由 router 层 `await`）：

  async def trace(...):
    chain = resolver.resolve(parsed_data, sheet, cell)       # 同步 BFS，无 IO、不取身份
    index = await effective_catalog(db, project_id)          # 锁定项目用锁定目录
    identity = exact_identity.cell_of(父底稿, sheet, A1)      # 每个节点的规范身份
    wp_id / jump_route = await resolve_instance(...)         # 按 sheet 记忆

节点身份（acnr-foundation-defect-closure T20，design §9.2 R2-F8）：只要 sheet 在父底稿下识别出、
A1 合法即 `resolved=True` 并返回规范 addr_id，另标 `in_catalog`（是否为目录登记的 cell）；
sheet 未识别 / 多义 / 命中禁止别名 / A1 非法才 `resolved=False` 并给中文 `unresolved_reason`。
不再把节点拼成 `cell:{sheet 名}!{A1}` 交给寻址层（`cell:` 只认 sheet_code，真实 sheet 名恒解析不到）。

设计约束（不得违反）：
  - 保持 `cross_sheet_resolver.py` 的同步纯 BFS（可 PBT 的纯逻辑）；生产构造一律
    `resolve_identity=False`，BFS 不调同步桥接 `_sync_resolve`。
  - 身份只经 `exact_identity`（与目录写法解析、单元格取值同一判定）。
  - 无法解析的节点优雅降级：`addr_id=None`、`resolved=False`、带原因，不中断整条链。

Requirements: 1.6, 4.2, 4.4；acnr-foundation-defect-closure 需求 8.1~8.3
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.acnr import exact_identity
from app.services.acnr.resolver import resolve_instance
from app.services.acnr.wp_cell_target import effective_catalog
from app.services.custom_query.cross_sheet_resolver import (
    CrossSheetResolver,
    RefChainNode,
    RefChainResponse,
    cross_sheet_resolver,
)

logger = logging.getLogger(__name__)

#: 调用方没给父底稿编码时的原因（端点总会传；只在直接调用编排器时出现）
NO_PARENT_REASON = "缺少父底稿编码，无法确定单元格身份"


# ─── Models ──────────────────────────────────────────────────────────────────


class TracedRefNode(BaseModel):
    """溯源链节点 + ACNR 规范身份。

    继承同步 BFS 节点（`RefChainNode`）的原始字段，并叠加规范身份（addr_id / wp_id / jump_route）。
    `in_catalog`：addr_id 是否为目录登记的 cell；`unresolved_reason`：`resolved=False` 时的中文原因。
    """

    # ── 同步 BFS 原始字段（来自 RefChainNode）──
    depth: int
    uri: str
    value: Any = None
    formula: str | None = None
    truncated: bool = False
    cycle: bool = False
    missing: bool = False

    # ── ACNR 规范身份 ──
    addr_id: str | None = None
    wp_id: str | None = None
    jump_route: str | None = None
    resolved: bool = False
    in_catalog: bool = False
    unresolved_reason: str | None = None


class CrossSheetTraceResponse(BaseModel):
    """跨 sheet 溯源编排响应（同步 BFS 结构 + 每节点规范身份）。"""

    chain: list[TracedRefNode]
    has_cycle: bool
    truncated_at_depth: int | None = None


# ─── 节点身份 ────────────────────────────────────────────────────────────────


def _identity(parent_wp_code: str | None, node: RefChainNode, index) -> exact_identity.CellMatch:
    if not parent_wp_code:
        return exact_identity.CellMatch(state="no_parent", reason=NO_PARENT_REASON)
    return exact_identity.cell_of(parent_wp_code, node.sheet or "", node.cell or "", index=index)


async def _instance_route(db: AsyncSession, project_id: str, sheet: dict) -> tuple[str | None, str | None]:
    """sheet 级底稿 ⇒ `resolve_instance` 的 wp_id / jump_route；项目只有父底稿 ⇒ 父底稿 + `sheet=` 定位。

    与单元格取值的绑定口径一致（`wp_cell_target.bind_wp_code`：只在 sheet 级底稿不存在时回落父底稿）。
    """
    pid = UUID(str(project_id))
    parent, code = sheet.get("parent_wp_code", ""), sheet.get("sheet_code", "")
    hit = await resolve_instance(db, pid, parent, code)
    if hit.found and hit.wp_id is not None:
        return str(hit.wp_id), hit.jump_route
    if hit.error == "not_found" and code != parent:
        owner = await resolve_instance(db, pid, parent, parent)
        if owner.found and owner.wp_id is not None:
            # 显式 wp_id：校验归属本项目，并按本 sheet 的跳转模板生成路由（带 sheet=）
            fallback = await resolve_instance(db, pid, parent, code, explicit_wp_id=owner.wp_id)
            if fallback.found and fallback.wp_id is not None:
                return str(fallback.wp_id), fallback.jump_route
    return None, None


def _traced(node: RefChainNode, match: exact_identity.CellMatch, route: tuple[str | None, str | None]) -> TracedRefNode:
    return TracedRefNode(
        depth=node.depth,
        uri=node.uri,
        value=node.value,
        formula=node.formula,
        truncated=node.truncated,
        cycle=node.cycle,
        missing=node.missing,
        addr_id=match.addr_id if match.ok else None,
        wp_id=route[0],
        jump_route=route[1],
        resolved=match.ok,
        in_catalog=match.in_catalog if match.ok else False,
        unresolved_reason=None if match.ok else (match.reason or "无法确定单元格身份"),
    )


# ─── Orchestrator ────────────────────────────────────────────────────────────


class CrossSheetTraceOrchestrator:
    """跨 sheet 溯源编排器 — 同步 BFS + 规范身份 + 按 sheet 记忆的底稿实例。"""

    def __init__(self, resolver: CrossSheetResolver | None = None) -> None:
        self._resolver = resolver or cross_sheet_resolver

    async def trace(
        self,
        parsed_data: dict | None,
        sheet_name: str,
        cell_ref: str,
        *,
        parent_wp_code: str | None = None,
        project_id: str | None = None,
        db: AsyncSession | None = None,
        max_depth: int = 3,
    ) -> CrossSheetTraceResponse:
        """溯源 `{sheet_name}!{cell_ref}` 引用链并为每节点挂规范身份。

        `parent_wp_code`：端点的底稿编码（节点身份按「父底稿 + sheet + A1」判定）。
        有 `project_id` 与 `db` 时按 sheet 记忆取 wp_id / jump_route；查库异常上抛，不伪装成未解析。
        """
        bfs: RefChainResponse = self._resolver.resolve(
            parsed_data, sheet_name, cell_ref, max_depth=max_depth
        )
        index = await effective_catalog(db, project_id)
        routes: dict[str, tuple[str | None, str | None]] = {}
        traced: list[TracedRefNode] = []
        for node in bfs.chain:
            match = _identity(parent_wp_code, node, index)
            route: tuple[str | None, str | None] = (None, None)
            if match.ok and match.addr_id and project_id and db is not None:
                sheet_addr = match.addr_id.rsplit("/", 1)[0]
                if sheet_addr not in routes:
                    routes[sheet_addr] = await _instance_route(db, project_id, index.sheets_by_addr_id[sheet_addr])
                route = routes[sheet_addr]
            traced.append(_traced(node, match, route))

        return CrossSheetTraceResponse(
            chain=traced,
            has_cycle=bfs.has_cycle,
            truncated_at_depth=bfs.truncated_at_depth,
        )


# 模块级单例（与 cross_sheet_resolver 一致的使用范式）
cross_sheet_trace_orchestrator = CrossSheetTraceOrchestrator()
