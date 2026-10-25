"""QueryOrchestrator — 高级查询统一编排层（advanced-query-module Task 8.1）。

设计对应 design.md §Components 3「QueryOrchestrator（查询编排）」与 §Architecture
「分层与统一寻址路径」。

职责：把业务视图查询（``custom_query.py``，cell 级 ACNR 寻址）与白名单构建器
（``query_builder.py``，表级 DSL）两套入口统一收敛到同一条执行链：

    Ownership_Check → resolve → cache → (sql | cell-fetch) → group → pivot → serialize

关键约束：
- **两入口统一编排**：``entry="business"`` 走寻址 + cell-fetch；``entry="builder"``
  走白名单 DSL SQL。二者共享同一 Ownership_Check / cache / group / pivot / serialize
  管线（R1.6 / R9.5 / R11.1 / R11.2）。
- **service 只 flush 不 commit**：编排层不做事务提交，提交由 router / 上层负责
  （平台铁律）。本编排为只读查询链，不写库。
- **ACNR 引用不重写**：寻址统一经 ``AddressingService``（封装 ``full_resolve``），
  不自建命名/坐标表。

并行依赖（clearly-marked integration hooks）：
- ``GroupingEngine``（task 9.1，``grouping_engine.py``）与 ``PivotEngine``（task 10.x，
  ``pivot_engine.py``）正在并行开发。本编排以**防御式惰性导入**引用其计划模块路径：
  存在则接线调用，缺失则跳过该步并在 ``warnings`` 中标注为待接线的集成钩子，
  不使编排链崩溃。
- 实际取数步（sql | cell-fetch）依赖 ParamSQLBuilder（6.x）与业务 cell-fetch，
  经可注入的 ``row_fetcher`` 接线；未注入时返回空结果并在 ``warnings`` 标注钩子。

ColumnMeta 的 addr_id 挂载细节属 task 8.2；本任务定义**最小 ColumnMeta** 供 8.2 扩展。

_Requirements: 1.6, 9.5, 11.1, 11.2_
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.custom_query.addressing_service import (
    AddressingService,
    ResolvedTarget,
    addressing_service,
)
from app.services.custom_query.ownership_guard import OwnershipGuard, ownership_guard
from app.services.custom_query.pagination import (
    apply_pagination,
    collect_available_columns,
    resolve_sort,
    validate_pagination,
)
from app.services.custom_query.query_cache import QueryCache, query_cache

logger = logging.getLogger(__name__)

# ─── 入口类型 ────────────────────────────────────────────────────────────────
ENTRY_BUSINESS = "business"  # 业务视图查询（所有角色，cell 级 ACNR 寻址）
ENTRY_BUILDER = "builder"    # 白名单 DSL 构建器（admin/manager，表级 SQL）
_VALID_ENTRIES = (ENTRY_BUSINESS, ENTRY_BUILDER)

# 分页默认
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 100

#: 透视结果中承载「行维度组合标签」的列键（见 _grid_to_rows_columns）
PIVOT_ROW_LABEL_KEY = "row_label"


# ─── 结果列元数据（task 8.2：addr_id 挂载逻辑落地）────────────────────────────
@dataclass
class ColumnMeta:
    """快照结果列元数据（design §Components 3 / Data Models §3）。

    挂载规则（task 8.2，R4.1 / R4.5）：``addr_id`` 当且仅当该列的值由**单一可解析
    源格**产生时挂载，``drillable`` 随之为真（前端据此渲染 ``GtIndexChip``）；由多个
    源格聚合或无源格产生的列不挂 ``addr_id``、``drillable=False``，渲染为不可下钻的
    普通文本列。挂载决策由本模块的 :func:`resolve_single_source_addr_id` /
    :func:`build_column_meta` / :func:`mount_addr_id` 统一裁定，并在编排器 serialize
    步单点收敛（见 :meth:`QueryOrchestrator._finalize_columns`）。

    ``semantic_label``（task 13.1 引入）：可读名，导出时作数据来源标识列（R7.4）。
    """

    key: str
    title: str
    addr_id: Optional[str] = None
    drillable: bool = False
    dtype: str = "text"  # number/text/date
    semantic_label: Optional[str] = None  # 可读名（导出数据来源标识列用，R7.4）
    #: 列值来源元数据（advanced-query-hardening-wiring-closure R3.6），形如
    #: ``{"manual": bool, "provenance": [...], "trace": [...]}``：
    #: ``manual`` 标识该列是否含手工录入值、``provenance`` 记取数出处、
    #: ``trace`` 记跨表追溯路径。
    #: ``ExecuteCompatibilityAdapter.to_legacy_response`` 据此判定该列是否需要
    #: 以完整 dict 形态下发（而非退化为列名字符串），故必须参与 payload 往返。
    source: Optional[dict] = None

    def __post_init__(self) -> None:
        # 不变式：drillable ⇔ addr_id 非空（R4.1 单源可下钻 / R4.5 多源/无源不可下钻）
        self.drillable = self.addr_id is not None


# ─── task 8.2：单源 addr_id 挂载逻辑（纯函数，供 fetcher / serialize 复用）────────
def resolve_single_source_addr_id(
    source_addr_ids: Iterable[Optional[str]],
) -> Optional[str]:
    """裁定一列（或一格）是否由**单一可解析源格**产生并返回其 addr_id。

    规则（R4.1 / R4.5）：
      - 恰好存在一个去重后的非空源 addr_id → 返回该 addr_id（单源，可下钻）。
      - 零个源 addr_id（无源 / 计算列）或多个不同源 addr_id（多源聚合）→ 返回
        ``None``（不可下钻）。

    空串 / ``None`` 视为「无有效源」被忽略；因此若某列仅有空值源与单一有效源，
    仍判定为单源（以唯一的有效 addr_id 为准）。

    这是 addr_id 挂载的**单一裁定入口**：fetcher 构造列、透视/分组收敛列、
    serialize 步落列元数据均复用本函数，保证「单源⇔挂载」在全链一致。
    """
    distinct = {a for a in source_addr_ids if a}
    if len(distinct) == 1:
        return next(iter(distinct))
    return None


def build_column_meta(
    *,
    key: str,
    title: str,
    source_addr_ids: Iterable[Optional[str]] = (),
    dtype: str = "text",
    semantic_label: Optional[str] = None,
    source: Optional[dict] = None,
) -> ColumnMeta:
    """由列的**源 addr_id 集合**构造 :class:`ColumnMeta`，自动裁定单源挂载。

    供取数层（业务 cell-fetch / ParamSQLBuilder 集成钩子）构造结果列时直接调用：
    传入该列所有值对应的源 addr_id（单源 → 挂载并可下钻；多源/无源 → 普通文本列）。
    ``drillable`` 由 ``ColumnMeta.__post_init__`` 依 ``addr_id`` 派生，无需显式传入。

    _Requirements: 4.1, 4.5_
    """
    return ColumnMeta(
        key=key,
        title=title,
        addr_id=resolve_single_source_addr_id(source_addr_ids),
        dtype=dtype,
        semantic_label=semantic_label,
        source=source,
    )


def mount_addr_id(
    column: ColumnMeta,
    source_addr_ids: Iterable[Optional[str]],
) -> ColumnMeta:
    """依 ``source_addr_ids`` 重新裁定既有列的 addr_id 挂载，返回**新** ColumnMeta。

    纯函数（不修改入参）：以 :func:`resolve_single_source_addr_id` 裁定后经
    ``dataclasses.replace`` 生成新实例，``__post_init__`` 据新 ``addr_id`` 重算
    ``drillable``。用于在分组/透视后依实际源格数量收敛列的可下钻性（多源 → 剥离
    addr_id）。

    _Requirements: 4.1, 4.5_
    """
    return replace(column, addr_id=resolve_single_source_addr_id(source_addr_ids))


# ─── 聚合与透视配置（最小定义；GroupingEngine/PivotEngine 落地时对齐）───────────
@dataclass
class Agg:
    """聚合规格：{field, func in {sum,count,avg,max,min}, alias}。"""

    field: str
    func: str = "sum"
    alias: Optional[str] = None


@dataclass
class PivotConfig:
    """透视配置（design §Components 5）：行维度 / 列维度 / 值字段 / 聚合方式。"""

    row_dims: list[str] = field(default_factory=list)
    col_dims: list[str] = field(default_factory=list)
    value_field: Optional[str] = None
    agg: str = "sum"
    max_cols: int = 512


# ─── 请求 / 结果契约 ──────────────────────────────────────────────────────────
@dataclass
class QueryRequest:
    """统一查询请求（design §Components 3）。

    - ``entry``：``"business"`` | ``"builder"``。
    - ``targets``：业务视图寻址目标（addr_id / uri / report:/note:/tb: 语法糖）。
    - ``dsl``：白名单构建器 DSL（表 / JOIN / 条件 / 聚合）。
    - ``group_by`` / ``aggs``：多维度分组（task 9.1）。
    - ``pivot``：透视配置（task 10.x）。
    - ``project_id`` / ``page`` / ``page_size``。
    """

    entry: str
    project_id: str
    targets: list[str] = field(default_factory=list)
    dsl: Optional[dict] = None
    group_by: list[str] = field(default_factory=list)
    aggs: list[Agg] = field(default_factory=list)
    pivot: Optional[PivotConfig] = None
    page: int = DEFAULT_PAGE
    page_size: int = DEFAULT_PAGE_SIZE
    # ── 业务视图 legacy 请求体字段（R3.4）───────────────────────────────────
    # `custom_query.QueryRequest`（pydantic）与本 dataclass 经
    # `ExecuteCompatibilityAdapter.to_orchestrator_request` 一一对应；缺任一字段
    # 该 adapter 即 TypeError，故这些字段是「唯一执行路径」成立的前提而非可选增强。
    source: Optional[str] = None
    year: Optional[int] = None
    filters: dict = field(default_factory=dict)
    columns: list[str] = field(default_factory=list)
    #: 排序项 [{"field": str, "direction": "asc"|"desc"}]，由 StablePagination 消费
    sort: list[dict] = field(default_factory=list)
    limit: int = DEFAULT_PAGE_SIZE
    offset: int = 0

    def cache_def(self) -> dict:
        """稳定序列化的查询定义（用于缓存键，design Data Models §4）。

        分页与排序必须纳入键：否则第 1 页与第 2 页、升序与降序会命中同一缓存条目。
        """
        return {
            "entry": self.entry,
            "targets": list(self.targets),
            "dsl": self.dsl,
            "group_by": list(self.group_by),
            "aggs": [asdict(a) for a in self.aggs],
            "pivot": asdict(self.pivot) if self.pivot else None,
            "page": self.page,
            "page_size": self.page_size,
            "source": self.source,
            "year": self.year,
            "filters": self.filters,
            "columns": list(self.columns),
            "sort": [dict(s) for s in self.sort],
            "limit": self.limit,
            "offset": self.offset,
        }


@dataclass
class QueryResult:
    """统一查询结果（design §Components 3）。"""

    columns: list[ColumnMeta] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    total: int = 0
    cache_hit: bool = False
    warnings: list[str] = field(default_factory=list)
    #: 本次实际生效的分页窗口（R3.5）。`ExecuteCompatibilityAdapter.to_legacy_response`
    #: 直接读取这两个字段，缺失即 AttributeError —— 该 adapter 自交付起从未被
    #: router 调用，故此缺陷此前不可见。
    limit: int = 0
    offset: int = 0

    def to_payload(self) -> dict:
        """转为 JSON 可序列化 dict（供 QueryCache 存储）。"""
        return {
            "columns": [asdict(c) for c in self.columns],
            "rows": self.rows,
            "total": self.total,
            "warnings": self.warnings,
            "limit": self.limit,
            "offset": self.offset,
        }

    @classmethod
    def from_payload(cls, payload: dict, *, cache_hit: bool) -> "QueryResult":
        """从缓存 payload 重建（还原 ColumnMeta）。

        往返必须无损：``source`` 漏还原会让 adapter 把带 source 的列降级成列名
        字符串，缓存命中与未命中的响应形态就此分叉（R3.5 / R3.6）。
        """
        cols = [
            ColumnMeta(
                key=c.get("key", ""),
                title=c.get("title", ""),
                addr_id=c.get("addr_id"),
                dtype=c.get("dtype", "text"),
                semantic_label=c.get("semantic_label"),
                source=c.get("source"),
            )
            for c in payload.get("columns", [])
        ]
        return cls(
            columns=cols,
            rows=list(payload.get("rows", [])),
            total=int(payload.get("total", 0)),
            cache_hit=cache_hit,
            warnings=list(payload.get("warnings", [])),
            limit=int(payload.get("limit", 0)),
            offset=int(payload.get("offset", 0)),
        )


# 取数回调签名：给定 (req, resolved_targets, db) → (rows, columns)
RowFetcher = Callable[
    [QueryRequest, list[ResolvedTarget], AsyncSession],
    Awaitable[tuple[list[dict], list[ColumnMeta]]],
]


class QueryOrchestrator:
    """两入口统一查询编排器。

    执行链：Ownership_Check → resolve → cache → (sql | cell-fetch) → group →
    pivot → serialize。编排层只读、只 flush 不 commit（无写库）。
    """

    def __init__(
        self,
        *,
        addressing: AddressingService | None = None,
        guard: OwnershipGuard | None = None,
        cache: QueryCache | None = None,
        business_fetcher: RowFetcher | None = None,
        builder_fetcher: RowFetcher | None = None,
    ) -> None:
        self._addressing = addressing or addressing_service
        self._guard = guard or ownership_guard
        self._cache = cache or query_cache
        # 取数集成钩子（sql | cell-fetch）——由 router/上层接线（ParamSQLBuilder 6.x /
        # 业务 cell-fetch）；未注入时返回空结果并在 warnings 标注。
        self._business_fetcher = business_fetcher
        self._builder_fetcher = builder_fetcher

    # ── 主入口 ───────────────────────────────────────────────────────────
    async def execute(
        self,
        req: QueryRequest,
        *,
        user: Any,
        db: AsyncSession,
        ttl: int = 30,
    ) -> QueryResult:
        """执行统一查询编排链，返回 QueryResult。

        step1 Ownership_Check：任何数据读写前强制项目归属校验（R9.5）；
        step2 resolve：业务视图目标经 AddressingService 统一寻址（R1.6），
              任一不可解析 → TARGET_UNRESOLVABLE 全有或全无、不部分执行；
        step3 cache：以查询定义 + project_id + scope_sig 为键短 TTL 缓存；
        step4 (sql | cell-fetch)：按 entry 分派取数（集成钩子）；
        step5 group：多维度分组（GroupingEngine，惰性接线）；
        step6 pivot：转置/透视（PivotEngine，惰性接线）；
        step7 serialize：组装 QueryResult。
        """
        if req.entry not in _VALID_ENTRIES:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "INVALID_ENTRY",
                    "message": f"未知查询入口 '{req.entry}'，须为 {_VALID_ENTRIES}",
                },
            )

        # ── step1: Ownership_Check（数据读写前，单点强制 R9.5）──
        # 授权恒先于一切：分页越界校验也排在其后，避免向无权用户回传「参数不合法」
        # 这类可用于探测的信息差。
        await self._guard.assert_target_accessible(
            user=user, project_id=req.project_id, db=db
        )

        # ── step1.5: 分页边界校验（R4.6）──
        # router 的 pydantic 层已有 ge/le，这里是防绕过 router 直调编排器的第二道；
        # 归一后写回 req，使其参与后续缓存键计算（否则 limit 的字符串/整数两种形态
        # 会算出两个键）。
        req.limit, req.offset = validate_pagination(req.limit, req.offset)

        # ── step2: resolve（业务视图统一寻址 R1.6；全有或全无 R1.4）──
        resolved = await self._resolve_targets(req, db)

        # ── step3: cache（键隔离 project_id + scope_sig R12.5）──
        scope_sig = self._scope_signature(user, req)
        key = self._cache.cache_key(req.cache_def(), str(req.project_id), scope_sig)

        executed = {"ran": False}

        async def _compute() -> dict:
            executed["ran"] = True
            result = await self._run_pipeline(req, resolved, user=user, db=db)
            return result.to_payload()

        payload = await self._cache.get_or_compute(key, _compute, ttl=ttl)
        return QueryResult.from_payload(payload, cache_hit=not executed["ran"])

    # ── step2 内部：目标解析 ──────────────────────────────────────────────
    async def _resolve_targets(
        self, req: QueryRequest, db: AsyncSession
    ) -> list[ResolvedTarget]:
        """业务视图入口统一寻址；白名单构建器入口不走 cell 寻址。

        任一目标 ``found=False`` → 归集无法解析清单、整体不执行、不返回部分结果
        （R1.4 TARGET_UNRESOLVABLE）。
        """
        if req.entry != ENTRY_BUSINESS or not req.targets:
            return []

        resolved = await self._addressing.resolve_many(
            req.targets, project_id=req.project_id, db=db
        )
        unresolved = [t.raw for t in resolved if not t.found]
        if unresolved:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "TARGET_UNRESOLVABLE",
                    "message": "存在无法解析为有效 addr_id 的查询目标，已中止查询",
                    "unresolved": unresolved,
                },
            )
        return resolved

    # ── step4–7 内部：取数 → 分组 → 透视 → 序列化 ───────────────────────────
    async def _run_pipeline(
        self,
        req: QueryRequest,
        resolved: list[ResolvedTarget],
        *,
        user: Any,
        db: AsyncSession,
    ) -> QueryResult:
        warnings: list[str] = []

        # step4: (sql | cell-fetch) — 按 entry 分派取数（集成钩子）
        rows, columns = await self._fetch_rows(req, resolved, db, warnings)

        # 跨项目聚合仅保留可访问项目行（R9.6）——防御式，仅当行携带 project_id
        if rows and any("project_id" in r for r in rows):
            rows = await self._guard.filter_accessible_rows(rows, user=user, db=db)

        # step5: group（GroupingEngine，惰性接线 task 9.1）
        collapsed = False
        if req.group_by:
            rows, columns = self._apply_grouping(req, rows, columns, warnings)
            collapsed = True  # 分组聚合 → 值列由多源格产生（多源，不可下钻）

        # step6: pivot（PivotEngine，惰性接线 task 10.x）
        if req.pivot is not None:
            rows, columns = self._apply_pivot(req, rows, columns, warnings)
            collapsed = True  # 透视交叉列由列维度聚合产生（多源，不可下钻）

        # step7: paginate —— 排序 → total → 切片（R4.1~R4.5）
        # 顺序不可调换：total 必须反映 group/pivot **之后**的行数，且必须在切片
        # 之前计算，否则 total 退化为「当前页行数」，前端无从判断是否还有下一页。
        available = collect_available_columns(rows, [c.key for c in columns])
        sort_keys = resolve_sort(req.source, req.sort, available)
        paged = apply_pagination(
            rows, sort=sort_keys, limit=req.limit, offset=req.offset
        )

        # step8: serialize —— 单点收敛列的 addr_id 挂载（R4.1 单源可下钻 / R4.5 多源不可下钻）
        columns = self._finalize_columns(columns, collapsed=collapsed)

        return QueryResult(
            columns=columns,
            rows=paged.rows,
            total=paged.total,
            limit=paged.limit,
            offset=paged.offset,
            cache_hit=False,
            warnings=warnings,
        )

    def _finalize_columns(
        self,
        columns: list[ColumnMeta],
        *,
        collapsed: bool,
    ) -> list[ColumnMeta]:
        """serialize 步单点收敛结果列的 addr_id 挂载（task 8.2，R4.1 / R4.5）。

        规则：
        - ``collapsed=True``（发生分组或透视）：结果列的值由**多个源格**聚合产生，
          不满足「单一可解析源格」，故一律剥离 addr_id、渲染为不可下钻普通文本列
          （R4.5）。cell 级单源溯源在透视场景由 ``PivotEngine`` 于 ``Cell.addr_id``
          承载（见 pivot_engine.py），不在列元数据层。
        - ``collapsed=False``（明细结果集）：保留取数层（fetcher）经
          :func:`build_column_meta` 裁定的单源挂载，仅经 :func:`mount_addr_id`
          复核不变式（单源 → 可下钻，否则普通文本列，R4.1）。

        本方法保证「单源⇔挂载」在编排出口单点一致，不依赖各 fetcher 自行维持不变式。
        """
        finalized: list[ColumnMeta] = []
        for col in columns:
            # 明细：以列自身既有 addr_id 作单源证据复核；聚合：清空源集合 → 不可下钻
            source_ids: tuple[Optional[str], ...] = (
                () if collapsed else (col.addr_id,)
            )
            finalized.append(mount_addr_id(col, source_ids))
        return finalized

    async def _fetch_rows(
        self,
        req: QueryRequest,
        resolved: list[ResolvedTarget],
        db: AsyncSession,
        warnings: list[str],
    ) -> tuple[list[dict], list[ColumnMeta]]:
        """按 entry 分派取数。

        - ``business`` → cell-fetch（业务 cell 级取数集成钩子）。
        - ``builder`` → 白名单 DSL SQL（ParamSQLBuilder 集成钩子）。

        取数实现经可注入的 fetcher 接线（保持编排层解耦、可独立测试）；未注入时
        返回空结果并在 warnings 标注为待接线的集成钩子（不使链崩溃）。
        """
        fetcher = (
            self._business_fetcher
            if req.entry == ENTRY_BUSINESS
            else self._builder_fetcher
        )
        if fetcher is None:
            warnings.append(
                f"row_fetcher 未接线（entry={req.entry}）：取数为集成钩子，"
                "待 ParamSQLBuilder(6.x)/业务 cell-fetch 接线"
            )
            return [], []
        return await fetcher(req, resolved, db)

    def _apply_grouping(
        self,
        req: QueryRequest,
        rows: list[dict],
        columns: list[ColumnMeta],
        warnings: list[str],
    ) -> tuple[list[dict], list[ColumnMeta]]:
        """惰性接线 GroupingEngine（task 9.1）。缺失则跳过并标注 warning。"""
        try:
            from app.services.custom_query.grouping_engine import (  # type: ignore
                GroupingEngine,
            )
        except ImportError:
            warnings.append(
                "grouping_engine 尚未就绪（task 9.1）：已跳过分组步（集成钩子）"
            )
            return rows, columns

        try:
            engine = GroupingEngine()
            group_result = engine.group(
                rows,
                list(req.group_by),
                [asdict(a) for a in req.aggs],
            )
            # GroupResult 契约由 task 9.1 落地；防御式提取 rows/columns
            new_rows = getattr(group_result, "rows", rows)
            new_cols = getattr(group_result, "columns", None)
            if new_cols is None:
                new_cols = columns
            return list(new_rows), list(new_cols)
        except HTTPException:
            raise  # 分组校验类错误（INVALID_GROUP_DIM/AGG_TYPE_MISMATCH）上抛
        except Exception as exc:  # noqa: BLE001 — 集成钩子容错，不使编排崩溃
            logger.warning("grouping_engine 接线调用失败（集成钩子）: %s", exc)
            warnings.append("分组步接线异常，已跳过（集成钩子）")
            return rows, columns

    def _apply_pivot(
        self,
        req: QueryRequest,
        rows: list[dict],
        columns: list[ColumnMeta],
        warnings: list[str],
    ) -> tuple[list[dict], list[ColumnMeta]]:
        """惰性接线 PivotEngine（task 10.x）。缺失则跳过并标注 warning。"""
        try:
            from app.services.custom_query.pivot_engine import (  # type: ignore
                PivotEngine,
            )
        except ImportError:
            warnings.append(
                "pivot_engine 尚未就绪（task 10.x）：已跳过透视步（集成钩子）"
            )
            return rows, columns

        try:
            engine = PivotEngine()
            grid = engine.pivot(
                rows,
                req.pivot,
                max_cols=req.pivot.max_cols if req.pivot else 512,
            )
            # Grid（row_labels / col_labels / cells）→ rows / columns。
            # 改造前此处是 `getattr(grid, "rows", None)` 的防御式提取，而 Grid 从来
            # 没有 `rows` / `columns` 属性 ⇒ 恒回退原始行、透视静默不生效（total 仍是
            # 原始行数）。防御式回退在契约不匹配时掩盖了缺陷，故改为显式转换。
            return self._grid_to_rows_columns(grid, req.pivot)
        except HTTPException:
            raise  # 透视校验类错误（PIVOT_COL_LIMIT）上抛
        except Exception as exc:  # noqa: BLE001 — 集成钩子容错
            logger.warning("pivot_engine 接线调用失败（集成钩子）: %s", exc)
            warnings.append("透视步接线异常，已跳过（集成钩子）")
            return rows, columns

    # ── 辅助 ─────────────────────────────────────────────────────────────
    @staticmethod
    def _grid_to_rows_columns(
        grid: Any, pivot_cfg: Any
    ) -> tuple[list[dict], list[ColumnMeta]]:
        """透视网格 ``Grid`` → 统一 ``rows`` / ``columns`` 契约。

        行维度组合合成**一列**（多维度时列名为各维度以 " / " 连接，与
        ``PivotEngine._combo_label`` 的行标签构造保持一致）；列维度的每个唯一组合
        各成一列。交叉单元格取 ``Cell.value``；``Cell.addr_id`` 属 cell 级溯源，
        不上升为列级 ``addr_id``（透视值由多源聚合产生，列级恒不可下钻，R4.5）。
        """
        # 行维度组合合成的列固定命名为 `row_label`：行标签本身已是各维度值以
        # " / " 连接的组合串（PivotEngine._combo_label），用维度名作列名在多维度时
        # 会得到 "region / quarter" 这种既非列名也非值的混合物，且下游按固定键取值
        # 更稳定（契约 test_p5_pivot_happens_before_total_and_pagination 断言键集
        # 恰为 {"row_label", <列标签...>}）。
        row_key = PIVOT_ROW_LABEL_KEY

        col_labels = [str(c) for c in (getattr(grid, "col_labels", None) or [])]
        # 列名去重：行维度列与某个列维度标签同名时会在 dict 中互相覆盖，
        # 静默丢一列比报错更难排查，故显式加后缀区分。
        seen = {row_key}
        resolved_labels: list[str] = []
        for label in col_labels:
            candidate = label
            suffix = 2
            while candidate in seen:
                candidate = f"{label}_{suffix}"
                suffix += 1
            seen.add(candidate)
            resolved_labels.append(candidate)

        columns = [ColumnMeta(key=row_key, title=row_key)]
        columns.extend(
            ColumnMeta(key=label, title=label, dtype="number")
            for label in resolved_labels
        )

        cells = getattr(grid, "cells", None) or []
        rows: list[dict] = []
        for r_idx, r_label in enumerate(getattr(grid, "row_labels", None) or []):
            row: dict = {row_key: r_label}
            row_cells = cells[r_idx] if r_idx < len(cells) else []
            for c_idx, label in enumerate(resolved_labels):
                cell = row_cells[c_idx] if c_idx < len(row_cells) else None
                row[label] = getattr(cell, "value", None)
            rows.append(row)
        return rows, columns

    @staticmethod
    def _scope_signature(user: Any, req: QueryRequest) -> str:
        """当前用户可访问范围的稳定签名（缓存键隔离 R12.5）。

        最小实现：以 user.id + entry 组合作签名，保证不同用户/入口不复用缓存。
        更细粒度的可访问项目集合签名由 QueryCache 键中的 project_id 与本签名共同隔离。
        """
        user_id = getattr(user, "id", None)
        return f"{user_id}:{req.entry}"


# 模块级单例（与同包 addressing_service / ownership_guard / query_cache 一致）
query_orchestrator = QueryOrchestrator()
