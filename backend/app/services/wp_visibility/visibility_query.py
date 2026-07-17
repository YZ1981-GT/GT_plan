"""AccessGrant 查询服务（Task 5 / 组件 C5 VisibilityQueryService）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 5.1/5.2：按 ``wp_index_id`` 计算 Delegated_Set 与 History_Set。
  - 5.3：Restricted 可见集唯一公式 ``(Delegated_Set ∪ History_Set) ∩ scope_cycles``。
  - 5.4：合并 Delegated/History 时按 ``wp_index_id`` 去重（保留独立 grant/access_kind）。
  - 5.5：Admin 显式产生 ``admin`` grant（忽略 scope，覆盖项目内全部底稿全页面）。
  - 5.6：Supervisor 对 scope 内 wp 显式产生 ``supervisor_scope`` grant（全页面）。
  - 5.7：Restricted 对 Delegated_Set 内 wp 产生 lead/assignee/reviewer grant。
  - 5.8/5.9：Row_Assignee/Operation_Reviewer 仅程序行身份 → 页面限定为对应 ProcedureRowTask
    的 sheet_key；未映射页面由 gate 转 External_Not_Found。
  - 5.10/5.17：Workpaper_Lead / lead_history → 整张底稿全部当前页面（ALL_PAGES）。
  - 5.11：多身份并集（同一 wp_index 上多个独立 grant，各自完整命中矩阵后并集）。
  - 5.12–5.14：仅因 History_Set 可见 → 只读 Current_Version（history grant ``readonly=True``）；
    历史版本 / 写动作由 gate 依据 readonly + matrix 统一转 404。
  - 5.15/5.16：每个独立身份产出且仅产出一个已登记 access_kind 的 grant；未登记 kind 丢弃。
  - 5.18：row_history 页面来源 = 不可变委派历史快照 sheet_key（Task 2 workpaper_delegation_history）。
  - 11.1–11.5：列表可见性过滤先于排序/分页；按 wp_index 去重；空集不回退循环级。
  - 16.5–16.13：无按底稿 N+1（单次 UNION ALL）；history 只读不可变快照，staff/task 重绑不改归属。
Design: 组件 C5（VisibilityQuery）/ "AccessGrant query" / Property 5/6/7/8。

**单次 UNION ALL（无 per-workpaper N+1）**：一条 SQL 语句 UNION ALL 产生 lead / assignee /
reviewer / lead_history / row_history（Non_Admin），并按角色显式追加 admin / supervisor_scope。
无论可见底稿多少，构建可见集只需常量次查询（Restricted：单次 UNION；Admin：单次 SELECT）。

**scope 相交 & 空集不回退（Req 5.3/5.4）**：全部 Non_Admin 分支都
``wi.audit_cycle = ANY(scope)``；scope 为空集时 Non_Admin 直接返回空可见集，绝不回退到
"整个循环级"可见。Admin 忽略 scope（Req 1.8）。

**历史稳定归属（Property 6 / Req 5.18 / 16.5-16.13）**：history grants 只读 Task 2 不可变快照
``workpaper_delegation_history``，按事件时冻结的 ``new_user_id/old_user_id`` 匹配当前自然人
（**不** JOIN 当前 StaffMember / ProcedureRowTask / sheet），并取冻结 ``sheet_key`` 作页面来源。
因此 staff↔user 重绑或 task 重派/软删后，历史归属与页面快照都不变。

**history 与当前委派并存（Req 5.11/5.12）**：history grant 与当前 lead/assignee/reviewer grant
在同一 wp_index 上作为**独立 grant 共存**；只读语义由 history grant 的 ``readonly=True`` 承载，
当写权限由并存的当前 grant 在 gate 处并集提供。"仅因 History 可见"（无当前 grant）时只有
readonly history grant → 只能读 Current_Version（Req 5.12）。查询层不做 History_Only 减法，
保证历史归属稳定且不误伤并存的当前委派。

约定：service 纯读，不 flush/commit 写。asyncpg 用 ``= ANY(CAST(:scope AS varchar[]))``（禁止 IN
tuple）；UUID 参数传字符串并 ``CAST(... AS uuid)``。查询异常 fail-closed 返回空可见集，绝不 500。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wp_visibility.contracts import (
    ALL_PAGES,
    READONLY_ACCESS_KINDS,
    REGISTERED_ACCESS_KINDS,
    AccessGrant,
    VisibilityContext,
    VisibilityRole,
    build_access_grant,
)

logger = logging.getLogger(__name__)

# 已登记 access_kind（与 contracts.REGISTERED_ACCESS_KINDS 一致；此处提供命名常量供调用方/测试引用）。
ACCESS_KIND_ADMIN = "admin"
ACCESS_KIND_SUPERVISOR_SCOPE = "supervisor_scope"
ACCESS_KIND_LEAD = "lead"
ACCESS_KIND_ASSIGNEE = "assignee"
ACCESS_KIND_REVIEWER = "reviewer"
ACCESS_KIND_LEAD_HISTORY = "lead_history"
ACCESS_KIND_ROW_HISTORY = "row_history"

# 每个 access_kind 的固定来源身份标签（Access_Grant.identity；保证同 kind 的多来源聚合为一个 grant）。
_IDENTITY_BY_KIND: dict[str, str] = {
    ACCESS_KIND_ADMIN: "admin",
    ACCESS_KIND_SUPERVISOR_SCOPE: "supervisor_scope",
    ACCESS_KIND_LEAD: "workpaper_lead",
    ACCESS_KIND_ASSIGNEE: "row_assignee",
    ACCESS_KIND_REVIEWER: "row_reviewer",
    ACCESS_KIND_LEAD_HISTORY: "lead_history",
    ACCESS_KIND_ROW_HISTORY: "row_history",
}

# ProcedureRowTask 终态 cancelled 不计入 active 委派（Delegated_Set："active、非取消、非软删"）。
# reviewed 仍属 active 委派（该自然人确实是执行/复核人，只是流程已完成）。
_CANCELLED_WORKFLOW = "cancelled"

__all__ = [
    "ACCESS_KIND_ADMIN",
    "ACCESS_KIND_SUPERVISOR_SCOPE",
    "ACCESS_KIND_LEAD",
    "ACCESS_KIND_ASSIGNEE",
    "ACCESS_KIND_REVIEWER",
    "ACCESS_KIND_LEAD_HISTORY",
    "ACCESS_KIND_ROW_HISTORY",
    "ALL_PAGES",
    "REGISTERED_ACCESS_KINDS",
    "AccessGrant",
    "VisibilityGrantSet",
    "VisibilityQueryService",
]


@dataclass(frozen=True)
class VisibilityGrantSet:
    """当前用户在某项目内的可见底稿 → 独立 AccessGrant 列表（按 ``wp_index_id`` 去重）。

    ``by_wp_index`` 只包含 **可见** 的 wp_index（至少一个 grant）；空可见集为空 dict。
    ``audit_cycle_by_wp_index`` 供列表 stats / 审计使用（Task 8）。
    """

    by_wp_index: Mapping[UUID, list[AccessGrant]]
    audit_cycle_by_wp_index: Mapping[UUID, str | None] = field(default_factory=dict)

    def grants_for(self, wp_index_id: UUID) -> list[AccessGrant]:
        return list(self.by_wp_index.get(wp_index_id, ()))

    def is_visible(self, wp_index_id: UUID) -> bool:
        return wp_index_id in self.by_wp_index

    def wp_index_ids(self) -> frozenset[UUID]:
        return frozenset(self.by_wp_index)


# ---------------------------------------------------------------------------
# 单次 UNION ALL SQL 分支
#
# 每个分支统一投影 6 列：
#   wp_index_id (uuid), audit_cycle (text), access_kind (text),
#   identity (text), sheet_key (text|null), readonly (bool)
# sheet_key = NULL 表示"全页面"（聚合为 ALL_PAGES）。
# 可选 ``{wpx_*}`` 收窄到单一 wp_index（供 gate 单资源判定复用）。
# ---------------------------------------------------------------------------

_BRANCH_LEAD = """
SELECT wi.id AS wp_index_id, wi.audit_cycle AS audit_cycle,
       'lead'::text AS access_kind, 'workpaper_lead'::text AS identity,
       CAST(NULL AS varchar) AS sheet_key, false AS readonly
FROM working_paper wp
JOIN wp_index wi ON wi.id = wp.wp_index_id
WHERE wp.project_id = CAST(:pid AS uuid)
  AND wp.assigned_to = CAST(:uid AS uuid)
  AND wp.is_deleted = false
  AND wi.is_deleted = false
  AND wi.audit_cycle = ANY(CAST(:scope AS varchar[]))
  {wpx_filter_wi}
"""

_BRANCH_ASSIGNEE = """
SELECT prt.wp_index_id AS wp_index_id, wi.audit_cycle AS audit_cycle,
       'assignee'::text AS access_kind, 'row_assignee'::text AS identity,
       prt.sheet_key AS sheet_key, false AS readonly
FROM procedure_row_tasks prt
JOIN staff_members sm ON sm.id = prt.assignee_staff_id
JOIN wp_index wi ON wi.id = prt.wp_index_id
WHERE prt.project_id = CAST(:pid AS uuid)
  AND sm.user_id = CAST(:uid AS uuid)
  AND sm.is_deleted = false
  AND prt.is_deleted = false
  AND prt.workflow_status <> :cancelled
  AND wi.is_deleted = false
  AND wi.audit_cycle = ANY(CAST(:scope AS varchar[]))
  {wpx_filter_prt}
"""

_BRANCH_REVIEWER = """
SELECT prt.wp_index_id AS wp_index_id, wi.audit_cycle AS audit_cycle,
       'reviewer'::text AS access_kind, 'row_reviewer'::text AS identity,
       prt.sheet_key AS sheet_key, false AS readonly
FROM procedure_row_tasks prt
JOIN staff_members sm ON sm.id = prt.reviewer_staff_id
JOIN wp_index wi ON wi.id = prt.wp_index_id
WHERE prt.project_id = CAST(:pid AS uuid)
  AND sm.user_id = CAST(:uid AS uuid)
  AND sm.is_deleted = false
  AND prt.is_deleted = false
  AND prt.workflow_status <> :cancelled
  AND wi.is_deleted = false
  AND wi.audit_cycle = ANY(CAST(:scope AS varchar[]))
  {wpx_filter_prt}
"""

# lead_history：整张底稿全部当前页面（sheet_key NULL → ALL_PAGES），只读；
# 按事件时冻结 user 匹配（Property 6：不回查当前 staff/task）。
_BRANCH_LEAD_HISTORY = """
SELECT DISTINCT wdh.wp_index_id AS wp_index_id, wi.audit_cycle AS audit_cycle,
       'lead_history'::text AS access_kind, 'lead_history'::text AS identity,
       CAST(NULL AS varchar) AS sheet_key, true AS readonly
FROM workpaper_delegation_history wdh
JOIN wp_index wi ON wi.id = wdh.wp_index_id
WHERE wdh.project_id = CAST(:pid AS uuid)
  AND wdh.target_role = 'lead'
  AND (wdh.old_user_id = CAST(:uid AS uuid) OR wdh.new_user_id = CAST(:uid AS uuid))
  AND wi.is_deleted = false
  AND wi.audit_cycle = ANY(CAST(:scope AS varchar[]))
  {wpx_filter_wdh}
"""

# row_history：页面来源 = 不可变快照 sheet_key（Req 5.18），只读；同样按冻结 user 匹配。
_BRANCH_ROW_HISTORY = """
SELECT DISTINCT wdh.wp_index_id AS wp_index_id, wi.audit_cycle AS audit_cycle,
       'row_history'::text AS access_kind, 'row_history'::text AS identity,
       wdh.sheet_key AS sheet_key, true AS readonly
FROM workpaper_delegation_history wdh
JOIN wp_index wi ON wi.id = wdh.wp_index_id
WHERE wdh.project_id = CAST(:pid AS uuid)
  AND wdh.target_role IN ('assignee', 'reviewer')
  AND (wdh.old_user_id = CAST(:uid AS uuid) OR wdh.new_user_id = CAST(:uid AS uuid))
  AND wi.is_deleted = false
  AND wi.audit_cycle = ANY(CAST(:scope AS varchar[]))
  {wpx_filter_wdh}
"""

# admin：项目内全部底稿全页面，忽略 scope（Req 1.8/5.5）。
_BRANCH_ADMIN = """
SELECT wi.id AS wp_index_id, wi.audit_cycle AS audit_cycle,
       'admin'::text AS access_kind, 'admin'::text AS identity,
       CAST(NULL AS varchar) AS sheet_key, false AS readonly
FROM wp_index wi
WHERE wi.project_id = CAST(:pid AS uuid)
  AND wi.is_deleted = false
  {wpx_filter_wi_id}
"""

# supervisor_scope：scope 内全部底稿全页面（Req 5.6）。
_BRANCH_SUPERVISOR = """
SELECT wi.id AS wp_index_id, wi.audit_cycle AS audit_cycle,
       'supervisor_scope'::text AS access_kind, 'supervisor_scope'::text AS identity,
       CAST(NULL AS varchar) AS sheet_key, false AS readonly
FROM wp_index wi
WHERE wi.project_id = CAST(:pid AS uuid)
  AND wi.is_deleted = false
  AND wi.audit_cycle = ANY(CAST(:scope AS varchar[]))
  {wpx_filter_wi_id}
"""


class VisibilityQueryService:
    """带 access_kind 的底稿 / 页面 / 历史 grants 查询（单次 UNION ALL，纯读，fail-closed）。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    async def grants_for_project(
        self, context: VisibilityContext
    ) -> VisibilityGrantSet:
        """当前用户在项目内的全部可见底稿及其独立 grant（列表视图 / 可见性过滤用）。

        - Admin：仅 ``admin`` grant（覆盖项目全部底稿，忽略 scope）。
        - Non_Admin：lead/assignee/reviewer/lead_history/row_history +（Supervisor）
          supervisor_scope，全部与 scope 相交；scope 为空 → 空可见集（不回退循环级）。
        """
        grants = await self._collect(context, wp_index_id=None)
        by_wp_index: dict[UUID, list[AccessGrant]] = defaultdict(list)
        cycles: dict[UUID, str | None] = {}
        for wp_index_id, audit_cycle, grant in grants:
            by_wp_index[wp_index_id].append(grant)
            cycles.setdefault(wp_index_id, audit_cycle)
        return VisibilityGrantSet(
            by_wp_index=dict(by_wp_index),
            audit_cycle_by_wp_index=cycles,
        )

    async def grants_for_wp_index(
        self, context: VisibilityContext, wp_index_id: UUID
    ) -> list[AccessGrant]:
        """单一底稿的全部独立 AccessGrant（gate 消费；多 grant 逐个匹配矩阵后并集）。"""
        grants = await self._collect(context, wp_index_id=wp_index_id)
        return [grant for _wpx, _cycle, grant in grants]

    async def visible_wp_index_ids(
        self, context: VisibilityContext
    ) -> frozenset[UUID]:
        """当前用户可见的去重 ``wp_index_id`` 集合（Req 5.4；列表可见性过滤 / stats 去重）。"""
        gs = await self.grants_for_project(context)
        return gs.wp_index_ids()

    # ------------------------------------------------------------------
    # SQL 组装、执行与聚合
    # ------------------------------------------------------------------
    async def _collect(
        self, context: VisibilityContext, wp_index_id: UUID | None
    ) -> list[tuple[UUID, str | None, AccessGrant]]:
        try:
            rows = await self._run_union_query(context, wp_index_id)
        except Exception as exc:  # noqa: BLE001 — fail-closed，不 500 泄露
            logger.warning(
                "AccessGrant 查询异常 user=%s project=%s: %s",
                context.user_id,
                context.project_id,
                exc,
            )
            return []
        return self._aggregate(rows)

    async def _run_union_query(
        self, context: VisibilityContext, wp_index_id: UUID | None
    ) -> list[sa.Row]:
        params: dict = {
            "pid": str(context.project_id),
            "uid": str(context.user_id),
            "cancelled": _CANCELLED_WORKFLOW,
        }
        if wp_index_id is not None:
            params["wpx"] = str(wp_index_id)
            f_wi = "AND wi.id = CAST(:wpx AS uuid)"
            f_wi_id = "AND wi.id = CAST(:wpx AS uuid)"
            f_prt = "AND prt.wp_index_id = CAST(:wpx AS uuid)"
            f_wdh = "AND wdh.wp_index_id = CAST(:wpx AS uuid)"
        else:
            f_wi = f_wi_id = f_prt = f_wdh = ""

        # ── Admin：单分支 SELECT，忽略 scope（Req 1.8/5.5）──
        if context.role is VisibilityRole.admin:
            sql = _BRANCH_ADMIN.format(wpx_filter_wi_id=f_wi_id)
            return list((await self.db.execute(sa.text(sql), params)).all())

        # ── Non_Admin：scope 相交；空 scope 直接空集（不回退循环级，Req 5.3/5.4）──
        scope = sorted(context.scope_cycles)
        if not scope:
            return []
        params["scope"] = scope

        branches: list[str] = [
            _BRANCH_LEAD.format(wpx_filter_wi=f_wi),
            _BRANCH_ASSIGNEE.format(wpx_filter_prt=f_prt),
            _BRANCH_REVIEWER.format(wpx_filter_prt=f_prt),
            _BRANCH_LEAD_HISTORY.format(wpx_filter_wdh=f_wdh),
            _BRANCH_ROW_HISTORY.format(wpx_filter_wdh=f_wdh),
        ]
        if context.role is VisibilityRole.supervisor:
            branches.append(_BRANCH_SUPERVISOR.format(wpx_filter_wi_id=f_wi_id))

        sql = "\nUNION ALL\n".join(f"({b.strip()})" for b in branches)
        return list((await self.db.execute(sa.text(sql), params)).all())

    @staticmethod
    def _aggregate(
        rows: list[sa.Row],
    ) -> list[tuple[UUID, str | None, AccessGrant]]:
        """把原始行按 (wp_index_id, access_kind) 聚合为独立 grant。

        - sheet_key NULL → 全页面（ALL_PAGES）；同组任一 NULL 即全页面。
        - 同组多个 sheet_key → 页面并集（frozenset）。
        - 未登记 access_kind → ``build_access_grant`` 返回 None → 丢弃（Req 5.16 / Property 8）。
        - 保留独立 grant/access_kind（Req 5.4/5.15）：不同 kind 不合并。
        """
        buckets: dict[tuple[UUID, str], dict] = defaultdict(
            lambda: {"audit_cycle": None, "all_pages": False, "sheets": set()}
        )
        for r in rows:
            wp_index_id = r[0]
            audit_cycle = r[1]
            access_kind = r[2]
            sheet_key = r[4]
            key = (wp_index_id, access_kind)
            b = buckets[key]
            b["audit_cycle"] = audit_cycle
            if sheet_key is None:
                b["all_pages"] = True
            else:
                b["sheets"].add(sheet_key)

        out: list[tuple[UUID, str | None, AccessGrant]] = []
        for (wp_index_id, access_kind), b in buckets.items():
            if b["all_pages"]:
                allowed: frozenset[str] | str = ALL_PAGES
            elif b["sheets"]:
                allowed = frozenset(b["sheets"])
            else:
                # 无任何页面且非全页面（如 row_history 快照缺 sheet）→ 丢弃（fail-closed）。
                continue
            # 防御性强制：History_Only kind 恒 readonly（Req 5.12–5.14），不依赖 SQL 列。
            readonly = access_kind in READONLY_ACCESS_KINDS
            grant = build_access_grant(
                access_kind=access_kind,
                identity=_IDENTITY_BY_KIND.get(access_kind, access_kind),
                allowed_sheet_keys=allowed,
                readonly=readonly,
            )
            if grant is None:  # 未登记 kind → 丢弃（Req 5.16）
                continue
            out.append((wp_index_id, b["audit_cycle"], grant))
        return out
