"""底稿列表查询服务（Task 8 / 组件 C13 List/Views）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 11.1：先应用可见性过滤与业务过滤。
  - 11.2：过滤后、排序/分页/total/stats 计算前按 ``wp_index_id`` 去重。
  - 11.3：total 使用过滤且去重后的完整集合。
  - 11.4：stats 使用过滤且去重后的分页前完整集合。
  - 11.5：过滤且去重后为空集 → ``stats={"by_index_status":{},"by_file_status":{}}``。
  - 11.6：返回且仅返回顶层字段 ``{items,total,stats,page,page_size}``。
  - 11.7：非法 ``page`` / ``page_size`` / ``sort`` 在执行底稿数据查询前返回 HTTP 422。
  - 11.8：对请求排序字段使用 NULLS LAST。
  - 11.9：追加 ``wp_index_id`` 升序作为最终排序键（Stable_Sort）。
  - 11.12/11.13：MyLeadWorkpapers 仅当前用户作为 Workpaper_Lead 的底稿，复用分页/过滤/去重/
    Stable_Sort/stats 契约（独立身份边界）。
  - 12.1/12.2/12.3：``visibility_mode``、客户端角色/身份不改变授权（仅服务端分类 + scope + grants）。
  - 12.4/12.5/12.6：分别返回 ``index_status`` 与 ``file_status`` 替代含义不明确的 ``status``；
    记录 legacy 字段映射（见 ``LEGACY_STATUS_MAPPING``）。
Design: 组件 C13（List/Views）/ "Lists, editor, coverage and frontend"（固定列表 SQL 顺序；
  响应只 {items,total,stats,page,page_size}；拆 index_status/file_status；MyLeadWorkpapers 独立）
  / Property 14（filter→dedupe→total/stats→stable sort→page；两个"我的"视图各自身份边界）
  / Property 15（visibility_mode / client identity 从不授权）。

**固定 SQL 顺序（禁止全量到 Python/前端再过滤）**：
  1. 参数校验（page/page_size/sort/sort_dir）→ 非法立即 ``InvalidListParams`` → 路由 422，
     **在任何底稿数据查询之前**。
  2. classification/scope/grants → 由 ``VisibilityQueryService`` 产出可见 ``wp_index_id`` 集合
     （单次 UNION ALL；MyLeadWorkpapers 用 authoritative ``WorkingPaper.assigned_to`` 独立边界）。
  3. 业务过滤（audit_cycle / index_status / file_status / assigned_to）——SQL WHERE。
  4. ``wp_index`` 去重——``DISTINCT ON (wi.id)``（一个 wp_index 至多一行，nullable wp 亦计入）。
  5. 分页前 total / stats——SQL ``COUNT`` / ``GROUP BY`` over 去重后集合。
  6. NULLS LAST + ``wp_index_id`` ASC——SQL ``ORDER BY``（Stable_Sort）。
  7. 分页——SQL ``LIMIT/OFFSET``。
  8. 仅 hydrate 当前页可见项（不把全量底稿拉到 Python）。

约定：service 纯读，不 flush/commit。asyncpg 用 ``= ANY(CAST(:ids AS uuid[]))``（禁止 IN tuple）；
UUID 参数传字符串并 ``CAST(... AS uuid)``；枚举列一律 ``::text`` 比较，规避枚举绑定歧义。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wp_visibility.contracts import VisibilityContext
from app.services.wp_visibility.visibility_query import VisibilityQueryService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 分页 / 排序契约（Req 11.6/11.7/11.8/11.9）
# ---------------------------------------------------------------------------

MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20
DEFAULT_SORT = "wp_code"
DEFAULT_SORT_DIR = "asc"

# 已登记排序字段 → 去重集合内的列名（Req 11.7 未登记 sort → 422）。
_SORT_COLUMN: dict[str, str] = {
    "wp_code": "wp_code",
    "audit_cycle": "audit_cycle",
    "index_status": "index_status",
    "file_status": "file_status",
    "created_at": "created_at",
    "updated_at": "updated_at",
}
REGISTERED_SORTS: frozenset[str] = frozenset(_SORT_COLUMN)
REGISTERED_SORT_DIRS: frozenset[str] = frozenset({"asc", "desc"})

# nullable wp（无 WorkingPaper）在 by_file_status 下的稳定 sentinel key（Property 14："nullable wp counted"）。
# 使其在 total / by_index_status / by_file_status 三处均可见且计数一致（非真实 WpFileStatus 枚举值）。
FILE_STATUS_NOT_GENERATED = "not_generated"

# Legacy 状态字段映射（Req 12.6：明确记录每个 legacy source → target 字段）。
#
# 旧 `list_workpapers` 返回一个含义不明确的顶层 `status` 字段（``WorkingPaper.status`` 优先，
# 回退 ``WpIndex.status``），且 `status` 查询参数过滤 ``WpIndex.status``。本服务拆分为两个明确字段：
LEGACY_STATUS_MAPPING: Mapping[str, str] = {
    # legacy 响应字段 → 新字段
    "status(response, WorkingPaper.status||WpIndex.status)": "file_status + index_status",
    # legacy WpIndex.status → index_status
    "WpIndex.status": "index_status",
    # legacy WorkingPaper.status → file_status
    "WorkingPaper.status": "file_status",
    # legacy `status` 查询参数（旧过滤 WpIndex.status）→ index_status 过滤参数
    "query_param.status": "query_param.index_status",
}

__all__ = [
    "InvalidListParams",
    "ListParams",
    "WorkpaperListFilters",
    "WorkpaperListQueryService",
    "REGISTERED_SORTS",
    "REGISTERED_SORT_DIRS",
    "MIN_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "DEFAULT_PAGE_SIZE",
    "FILE_STATUS_NOT_GENERATED",
    "LEGACY_STATUS_MAPPING",
]


class InvalidListParams(ValueError):
    """非法分页/排序参数（Req 11.7）。路由层捕获后返回 HTTP 422，**在任何底稿查询之前**。"""


@dataclass(frozen=True)
class ListParams:
    """校验后的分页/排序参数。"""

    page: int
    page_size: int
    sort: str
    sort_dir: str

    @classmethod
    def parse(
        cls,
        page: Any,
        page_size: Any,
        sort: Any = DEFAULT_SORT,
        sort_dir: Any = DEFAULT_SORT_DIR,
    ) -> "ListParams":
        """校验并规范化；任一非法 → ``InvalidListParams``（Req 11.7，先于底稿查询）。

        - ``page``：正整数。
        - ``page_size``：``[MIN_PAGE_SIZE, MAX_PAGE_SIZE]`` 内的正整数。
        - ``sort``：已登记字段（``REGISTERED_SORTS``）。
        - ``sort_dir``：asc / desc。
        """
        if isinstance(page, bool) or not isinstance(page, int):
            raise InvalidListParams("page 必须为正整数")
        if page < 1:
            raise InvalidListParams("page 必须为正整数")
        if isinstance(page_size, bool) or not isinstance(page_size, int):
            raise InvalidListParams("page_size 必须为正整数")
        if page_size < MIN_PAGE_SIZE or page_size > MAX_PAGE_SIZE:
            raise InvalidListParams(
                f"page_size 必须在 [{MIN_PAGE_SIZE}, {MAX_PAGE_SIZE}] 范围内"
            )
        sort_val = sort or DEFAULT_SORT
        if sort_val not in REGISTERED_SORTS:
            raise InvalidListParams(f"未登记的 sort 字段: {sort_val!r}")
        dir_val = (sort_dir or DEFAULT_SORT_DIR).lower()
        if dir_val not in REGISTERED_SORT_DIRS:
            raise InvalidListParams(f"未登记的 sort_dir: {sort_dir!r}")
        return cls(page=page, page_size=page_size, sort=sort_val, sort_dir=dir_val)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass(frozen=True)
class WorkpaperListFilters:
    """业务过滤（全部可选）。"""

    audit_cycle: str | None = None
    index_status: str | None = None
    file_status: str | None = None
    assigned_to: UUID | None = None


# ---------------------------------------------------------------------------
# 去重底稿 CTE（DISTINCT ON 每 wp_index 取一行；nullable wp LEFT JOIN 保留）
# ---------------------------------------------------------------------------

_DEDUPED_CTE = """
WITH deduped AS (
    SELECT DISTINCT ON (wi.id)
        wi.id            AS wp_index_id,
        wi.project_id    AS project_id,
        wi.wp_code       AS wp_code,
        wi.wp_name       AS wp_name,
        wi.audit_cycle   AS audit_cycle,
        wi.status::text  AS index_status,
        wp.id            AS wp_id,
        wp.status::text  AS file_status,
        wp.review_status::text AS review_status,
        wp.assigned_to   AS assigned_to,
        wp.reviewer      AS reviewer,
        wp.file_version  AS file_version,
        wp.file_path     AS file_path,
        wp.source_type::text AS source_type,
        wp.prefill_stale AS prefill_stale,
        wp.created_at    AS created_at,
        wp.updated_at    AS updated_at
    FROM wp_index wi
    LEFT JOIN working_paper wp
        ON wp.wp_index_id = wi.id AND wp.is_deleted = false
    WHERE wi.id = ANY(CAST(:ids AS uuid[]))
      AND wi.is_deleted = false
      {filters}
    ORDER BY wi.id, wp.file_version DESC NULLS LAST, wp.created_at DESC NULLS LAST
)
"""


class WorkpaperListQueryService:
    """服务端正式分页 / 状态拆分 / 独立主编视图（组件 C13，纯读，全在 SQL）。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.visibility = VisibilityQueryService(db)

    # ------------------------------------------------------------------
    # 主底稿列表（角色化可见集 → 分页 / stats）
    # ------------------------------------------------------------------
    async def list_workpapers(
        self,
        context: VisibilityContext,
        *,
        page: Any = 1,
        page_size: Any = DEFAULT_PAGE_SIZE,
        sort: Any = DEFAULT_SORT,
        sort_dir: Any = DEFAULT_SORT_DIR,
        filters: WorkpaperListFilters | None = None,
    ) -> dict:
        """底稿列表：可见性(role/scope/grants)过滤 + 业务过滤 + 去重 + total/stats + 稳定排序 + 分页。

        返回 ``{items,total,stats,page,page_size}``（Req 11.6）。``visibility_mode``/客户端身份
        不参与——授权只来自服务端 ``context``（Req 12.1–12.3 / Property 15）。
        """
        # ① 参数校验（先于任何底稿查询，Req 11.7）
        params = ListParams.parse(page, page_size, sort, sort_dir)
        # ② classification/scope/grants → 可见 wp_index 集合（单次 UNION ALL）
        visible_ids = await self.visibility.visible_wp_index_ids(context)
        return await self._paginate(visible_ids, params, filters or WorkpaperListFilters())

    # ------------------------------------------------------------------
    # MyLeadWorkpapers（独立主编身份边界，复用分页/stats 契约；Req 11.12/11.13）
    # ------------------------------------------------------------------
    async def list_lead_workpapers(
        self,
        context: VisibilityContext,
        *,
        page: Any = 1,
        page_size: Any = DEFAULT_PAGE_SIZE,
        sort: Any = DEFAULT_SORT,
        sort_dir: Any = DEFAULT_SORT_DIR,
        filters: WorkpaperListFilters | None = None,
    ) -> dict:
        """我的主编底稿：仅当前用户作为 Workpaper_Lead（authoritative ``WorkingPaper.assigned_to``）
        的底稿，独立于程序行任务视图；复用同一分页/过滤/去重/Stable_Sort/stats 管线。
        """
        # ① 参数校验（先于任何底稿查询）
        params = ListParams.parse(page, page_size, sort, sort_dir)
        # ② 独立身份边界：lead = WorkingPaper.assigned_to == 当前 user（Req 2.2 权威字段）
        lead_ids = await self._lead_wp_index_ids(context)
        return await self._paginate(lead_ids, params, filters or WorkpaperListFilters())

    async def _lead_wp_index_ids(self, context: VisibilityContext) -> frozenset[UUID]:
        """当前用户作为 Workpaper_Lead 的去重 ``wp_index_id`` 集合（纯身份，不依赖 role/grants）。"""
        sql = sa.text(
            """
            SELECT DISTINCT wp.wp_index_id
            FROM working_paper wp
            JOIN wp_index wi ON wi.id = wp.wp_index_id
            WHERE wp.project_id = CAST(:pid AS uuid)
              AND wp.assigned_to = CAST(:uid AS uuid)
              AND wp.is_deleted = false
              AND wi.is_deleted = false
            """
        )
        try:
            rows = (
                await self.db.execute(
                    sql,
                    {"pid": str(context.project_id), "uid": str(context.user_id)},
                )
            ).scalars().all()
        except Exception as exc:  # noqa: BLE001 — fail-closed 空集，不 500
            logger.warning(
                "MyLeadWorkpapers 可见集查询异常 user=%s project=%s: %s",
                context.user_id,
                context.project_id,
                exc,
            )
            return frozenset()
        return frozenset(rows)

    # ------------------------------------------------------------------
    # 去重 + total/stats + stable sort + 分页（全部 SQL；仅 hydrate 当前页）
    # ------------------------------------------------------------------
    async def _paginate(
        self,
        wp_index_ids: frozenset[UUID],
        params: ListParams,
        filters: WorkpaperListFilters,
    ) -> dict:
        empty_stats = {"by_index_status": {}, "by_file_status": {}}
        # 空可见集：直接空页 + 两空字典（Req 11.5），不发起底稿查询。
        if not wp_index_ids:
            return {
                "items": [],
                "total": 0,
                "stats": empty_stats,
                "page": params.page,
                "page_size": params.page_size,
            }

        base_params: dict[str, Any] = {"ids": [str(x) for x in wp_index_ids]}
        filter_sql = self._build_filters(filters, base_params)
        cte = _DEDUPED_CTE.format(filters=filter_sql)

        try:
            # ⑤ 分页前 total（去重后完整集合，Req 11.3）
            total = int(
                (
                    await self.db.execute(
                        sa.text(cte + "SELECT COUNT(*) FROM deduped"), base_params
                    )
                ).scalar()
                or 0
            )
            # ⑤ 分页前 stats（去重后完整集合，Req 11.4）
            stats = await self._compute_stats(cte, base_params)
            # ⑥⑦⑧ 稳定排序 + 分页 + 仅 hydrate 当前页
            items = await self._fetch_page(cte, base_params, params)
        except Exception as exc:  # noqa: BLE001 — fail-closed：空页而非 500 泄露
            logger.warning("底稿列表查询异常: %s", exc)
            return {
                "items": [],
                "total": 0,
                "stats": empty_stats,
                "page": params.page,
                "page_size": params.page_size,
            }

        return {
            "items": items,
            "total": total,
            "stats": stats,
            "page": params.page,
            "page_size": params.page_size,
        }

    @staticmethod
    def _build_filters(
        filters: WorkpaperListFilters, params: dict[str, Any]
    ) -> str:
        """业务过滤 SQL 片段（枚举列 ``::text`` 比较；参数写入 ``params``）。"""
        frags: list[str] = []
        if filters.audit_cycle:
            frags.append("AND wi.audit_cycle = :f_audit_cycle")
            params["f_audit_cycle"] = filters.audit_cycle
        if filters.index_status:
            frags.append("AND wi.status::text = :f_index_status")
            params["f_index_status"] = filters.index_status
        if filters.file_status:
            frags.append("AND wp.status::text = :f_file_status")
            params["f_file_status"] = filters.file_status
        if filters.assigned_to:
            frags.append("AND wp.assigned_to = CAST(:f_assigned_to AS uuid)")
            params["f_assigned_to"] = str(filters.assigned_to)
        return "\n      ".join(frags)

    async def _compute_stats(self, cte: str, base_params: dict[str, Any]) -> dict:
        """by_index_status / by_file_status 计数（去重后集合；nullable wp → not_generated）。"""
        sql = sa.text(
            cte
            + """
            SELECT dim, k, c FROM (
                SELECT 'index'::text AS dim, index_status AS k, COUNT(*) AS c
                FROM deduped GROUP BY index_status
                UNION ALL
                SELECT 'file'::text AS dim,
                       COALESCE(file_status, :not_generated) AS k,
                       COUNT(*) AS c
                FROM deduped GROUP BY COALESCE(file_status, :not_generated)
            ) x
            """
        )
        p = dict(base_params)
        p["not_generated"] = FILE_STATUS_NOT_GENERATED
        rows = (await self.db.execute(sql, p)).all()
        by_index: dict[str, int] = {}
        by_file: dict[str, int] = {}
        for dim, k, c in rows:
            if k is None:
                continue
            if dim == "index":
                by_index[str(k)] = int(c)
            else:
                by_file[str(k)] = int(c)
        return {"by_index_status": by_index, "by_file_status": by_file}

    async def _fetch_page(
        self, cte: str, base_params: dict[str, Any], params: ListParams
    ) -> list[dict]:
        """稳定排序 + 分页 + 当前页 hydrate（Req 11.8/11.9）。"""
        sort_col = _SORT_COLUMN[params.sort]
        direction = "ASC" if params.sort_dir == "asc" else "DESC"
        # NULLS LAST（Req 11.8）+ wp_index_id 升序最终键（Req 11.9）。
        order_by = f"{sort_col} {direction} NULLS LAST, wp_index_id ASC"
        sql = sa.text(
            cte
            + f"""
            SELECT * FROM deduped
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
            """
        )
        p = dict(base_params)
        p["limit"] = params.page_size
        p["offset"] = params.offset
        rows = (await self.db.execute(sql, p)).mappings().all()
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _hydrate(r: Mapping[str, Any]) -> dict:
        """行 → 列表项（拆 index_status/file_status；nullable wp → wp_id=None 供前端禁用文件动作）。"""
        wp_id = r["wp_id"]
        return {
            "wp_index_id": str(r["wp_index_id"]),
            "project_id": str(r["project_id"]),
            "wp_id": str(wp_id) if wp_id else None,
            "wp_code": r["wp_code"],
            "wp_name": r["wp_name"],
            "audit_cycle": r["audit_cycle"],
            # 状态拆分（Req 12.4/12.5）：index_status = 索引层，file_status = 文件/编制层。
            "index_status": r["index_status"],
            "file_status": r["file_status"],
            "review_status": r["review_status"] or "not_submitted",
            "assigned_to": str(r["assigned_to"]) if r["assigned_to"] else None,
            "reviewer": str(r["reviewer"]) if r["reviewer"] else None,
            "file_version": r["file_version"],
            "file_path": r["file_path"],
            "source_type": r["source_type"],
            "prefill_stale": bool(r["prefill_stale"]) if r["prefill_stale"] is not None else False,
            # nullable wp（底稿尚未生成）→ 前端禁用文件动作（Req 12.8/12.9；后端 gate 另行强制）。
            "wp_generated": wp_id is not None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
