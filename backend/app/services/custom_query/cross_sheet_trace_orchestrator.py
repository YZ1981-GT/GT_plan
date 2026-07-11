"""CrossSheetTraceOrchestrator — 跨 sheet 溯源异步编排层

处理 design.md §Architecture「异步陷阱处理」：`CrossSheetResolver.resolve` 是
**同步纯函数**（仅公式字符串 BFS，读 `parsed_data.univer_snapshot`，不触碰 ACNR、
无 IO），若在其内部直接 `await`/`asyncio.run(full_resolve(...))` 会在已运行的事件
循环中抛错（memory 记录的 async pitfall）。

本编排层把异步 IO **全部上浮**到 orchestrator（由 router 层 `await`）：

  async def trace(...):
    chain = resolver.resolve(parsed_data, sheet, cell)     # 同步 BFS，无 IO
    resolved = await addressing.resolve_many(acnr_inputs)  # async 并发解析 addr_id
    # 合并 addr_id + jump_route 回链，返回

设计约束（不得违反）：
  - 保持 `cross_sheet_resolver.py` 的同步纯 BFS **不动**（可 PBT 的纯逻辑）。
  - **禁止**在同步 BFS 内部 `run_in_executor` 反向调用异步 resolve。
  - 异步 IO 只存在于本 orchestrator 的 `await` 中（经统一寻址入口
    `AddressingService` 封装 ACNR `full_resolve`，不重写 ACNR 核心）。
  - 无法解析的链节点优雅降级：`addr_id=None`、`resolved=False`，不中断整条链。

Requirements: 1.6, 4.2, 4.4
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.custom_query.addressing_service import (
    AddressingService,
    ResolvedTarget,
    addressing_service,
    DEFAULT_RESOLVE_TIMEOUT_S,
)
from app.services.custom_query.cross_sheet_resolver import (
    CrossSheetResolver,
    RefChainNode,
    RefChainResponse,
    cross_sheet_resolver,
)

logger = logging.getLogger(__name__)


# ─── Models ──────────────────────────────────────────────────────────────────


class TracedRefNode(BaseModel):
    """溯源链节点 + ACNR addr_id 增强。

    继承同步 BFS 节点（`RefChainNode`）的全部字段，并叠加经 ACNR 统一寻址
    解析出的 canonical 身份（addr_id / wp_id / jump_route）。无法解析的节点
    `resolved=False` 且 `addr_id=None`（优雅降级，见 R4.5）。
    """

    # ── 同步 BFS 原始字段（来自 RefChainNode）──
    depth: int
    uri: str
    value: Any = None
    formula: str | None = None
    truncated: bool = False
    cycle: bool = False
    missing: bool = False

    # ── ACNR 统一寻址增强字段 ──
    addr_id: str | None = None
    wp_id: str | None = None
    jump_route: str | None = None
    resolved: bool = False


class CrossSheetTraceResponse(BaseModel):
    """跨 sheet 溯源编排响应（同步 BFS 结构 + 每节点 addr_id）。"""

    chain: list[TracedRefNode]
    has_cycle: bool
    truncated_at_depth: int | None = None


# ─── ACNR 输入转换 ───────────────────────────────────────────────────────────


def _uri_to_acnr_input(uri: str) -> str:
    """将链节点的 `{sheet}!{cell}` uri 转为 ACNR 统一寻址输入形态。

    同步 BFS 的节点 uri 形如 `审定表D2-1!A2`（sheet 名 + '!' + cell）。ACNR
    的 `cell:` 索引命名空间正是 `cell:{sheet_code}!{cell}` 形态
    （见 `acnr.catalog._index_ref_to_addr_id`），故加 `cell:` 前缀归一为
    `index_ref`，由 `AddressingService` 路由到 `full_resolve(index_ref=...)`。

    若 uri 不含 '!'（非预期形态），原样返回，交由寻址层归类（多半解析失败 →
    优雅降级 addr_id=None）。
    """
    if "!" in uri:
        return f"cell:{uri}"
    return uri


def _merge_node(node: RefChainNode, resolved: ResolvedTarget) -> TracedRefNode:
    """把 ACNR 解析结果合并回单个 BFS 链节点。"""
    return TracedRefNode(
        depth=node.depth,
        uri=node.uri,
        value=node.value,
        formula=node.formula,
        truncated=node.truncated,
        cycle=node.cycle,
        missing=node.missing,
        addr_id=resolved.addr_id if resolved.found else None,
        wp_id=resolved.wp_id if resolved.found else None,
        jump_route=resolved.jump_route if resolved.found else None,
        resolved=resolved.found,
    )


# ─── Orchestrator ────────────────────────────────────────────────────────────


class CrossSheetTraceOrchestrator:
    """跨 sheet 溯源编排器 — 同步 BFS + async addr_id 解析。

    组合（非继承）同步 `CrossSheetResolver` 与统一寻址 `AddressingService`：
    先同步跑纯 BFS 得到引用链（无 IO），再一次性并发为每个链节点解析 addr_id +
    jump_route（唯一的 async IO 段），最后合并回链。
    """

    def __init__(
        self,
        resolver: CrossSheetResolver | None = None,
        addressing: AddressingService | None = None,
    ) -> None:
        self._resolver = resolver or cross_sheet_resolver
        self._addressing = addressing or addressing_service

    async def trace(
        self,
        parsed_data: dict | None,
        sheet_name: str,
        cell_ref: str,
        *,
        project_id: str | None = None,
        db: AsyncSession | None = None,
        max_depth: int = 3,
        timeout_s: float = DEFAULT_RESOLVE_TIMEOUT_S,
    ) -> CrossSheetTraceResponse:
        """溯源 `{sheet_name}!{cell_ref}` 引用链并为每节点挂 addr_id。

        步骤：
          1. `chain = resolver.resolve(...)` —— 同步纯 BFS，无任何 IO。
          2. `await addressing.resolve_many(...)` —— 并发解析每个链节点的
             addr_id + jump_route（唯一 async IO 段，经 ACNR full_resolve）。
          3. 合并 addr_id 回链，返回携带溯源身份的响应。

        无法解析的节点优雅降级（`addr_id=None`、`resolved=False`），不影响
        其余节点与整条链的返回。
        """
        # ── Step 1: 同步 BFS（纯函数，无 IO）──
        bfs: RefChainResponse = self._resolver.resolve(
            parsed_data, sheet_name, cell_ref, max_depth=max_depth
        )
        nodes = bfs.chain

        if not nodes:
            return CrossSheetTraceResponse(
                chain=[],
                has_cycle=bfs.has_cycle,
                truncated_at_depth=bfs.truncated_at_depth,
            )

        # ── Step 2: 并发解析 addr_id（唯一 async IO 段，上浮到 orchestrator）──
        acnr_inputs = [_uri_to_acnr_input(n.uri) for n in nodes]
        resolved: list[ResolvedTarget] = await self._addressing.resolve_many(
            acnr_inputs,
            project_id=project_id,
            db=db,
            timeout_s=timeout_s,
        )

        # ── Step 3: 合并回链 ──
        traced = [_merge_node(node, r) for node, r in zip(nodes, resolved)]

        return CrossSheetTraceResponse(
            chain=traced,
            has_cycle=bfs.has_cycle,
            truncated_at_depth=bfs.truncated_at_depth,
        )


# 模块级单例（与 cross_sheet_resolver / addressing_service 一致的使用范式）
cross_sheet_trace_orchestrator = CrossSheetTraceOrchestrator()
