"""按**数据能力**动态解析真库项目（取代 ``gold.py`` 里写死的 9 个项目 UUID）。

## 为什么不能再写死 UUID

2026-11-01 现算：`gold.py` 里 HS / HP / YB / LN / MD / WL / UA / UB / UP 共 **9 个 UUID 在
`projects` 表里全都查不到行**（不是软删，是不存在；以 UAT 命名的项目现库一个都没有）。
写死 UUID 的失效方式很隐蔽 —— 用例不会说"项目没了"，而是拿 403 / 空集去跟同样是空的金标准
互相印证，**看起来绿、其实什么都没验**。

## 为什么是「按能力」而不是「按项目」

本轮还查出一件事：**老的角色划分已经无解**。例如原 `HS`（华氏）同时被要求「有 AJE 调整分录」
「RJE 恰好 0 行」「有底稿」「有附注」「六类报表且既有过期又有未过期」，而现库里：
华氏 `a7fc75e5` 的 adjustments 是 0、底稿是 0；重药安徽 `0ec33ac9` 有 8 条 AJE 但 **RJE 有 2 条**
（原用例断言 RJE == 0）。没有任何一个活项目能同时满足。

所以这里不按"项目代号"解析，而是按**能力**解析：每条能力是一个显式的判据（SQL + 确定性排序），
谁满足就用谁。好处是判据恒定、数据随库变；坏处是同一条用例在不同时间可能落到不同项目上 ——
这是用户 2026-11-01 明确接受的取舍（替代方案「每次手工更新 9 个 UUID」等于把这次的失效模式
留在原地）。

## 三条实现纪律

1. **只用显式列的裸 SQL，禁 `db.get(Project, ...)`**：共享库缺任一与高级查询无关的新列时
   （现算缺 `projects.amount_unit`，远端迁移 V250 未落库），全列 ORM 投影会让整条链路 500 ——
   这正是本 spec 前十五节那 5 处 500 的同一机理。
2. **取不到就当场失败并打印判据与候选**，绝不 `skip`、绝不退化成"空集也算过"。
3. **确定性排序**：同样的库必须选出同一个项目，否则用例在"碰巧选了另一个"时表现不一致。

每条能力解析一次后按 ``(能力名)`` 缓存在 ``PickResolver`` 实例上（夹具按用例创建，不跨库复用）。
"""
from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Mapping
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

#: 四表的生效数据集子查询（与 ``dataset_query.get_active_filter`` 同口径）。
#: 这里写成「取该 (项目, 年度) 下 activated_at 最新（空值在后）、其次 created_at 最新的 active 数据集」。
_ACTIVE_DATASET = """
SELECT DISTINCT ON (project_id, year) project_id, year, id AS dataset_id
FROM ledger_datasets WHERE status = 'active'
ORDER BY project_id, year, activated_at DESC NULLS LAST, created_at DESC
"""

#: 未软删项目的显式列投影（**不要**用 ORM 全列加载，见模块说明纪律 1）
_LIVE_PROJECTS = (
    "SELECT id, name, audit_year, report_scope::text AS report_scope, "
    "template_type::text AS template_type FROM projects WHERE NOT is_deleted"
)


@dataclasses.dataclass(frozen=True)
class Pick:
    """一条能力解析出的项目。

    ``metric`` 是该能力的排序度量现算值，写进断言失败信息里便于复盘（例如"这个项目被选中是
    因为它的序时账有 2,532,279 行"）。
    """

    id: uuid.UUID
    name: str
    audit_year: int | None
    report_scope: str | None
    template_type: str | None
    capability: str
    metric: int

    def __str__(self) -> str:  # 断言失败信息里直接可读
        return f"{self.name}（{self.id}，年度 {self.audit_year}，{self.capability} 度量 {self.metric}）"


@dataclasses.dataclass(frozen=True)
class Capability:
    """一条能力判据。

    ``metric_sql`` 必须是一个以 ``l``（live projects 别名）为外层相关列的标量子查询，
    返回整数度量；``require`` 是该度量上的下限（严格大于）；``extra_sql`` 是附加的布尔条件。
    解析时按 ``度量 DESC, id ASC`` 取第一名 —— id 兜底保证同度量时选择唯一。
    """

    name: str
    description: str
    metric_sql: str
    require_gt: int = 0
    extra_sql: str = "TRUE"


#: 能力目录。新增能力请一并在 `test_aql_project_picks_pg.py` 里加一条解析断言，
#: 否则"能力存在但从没被解析过"这件事没有任何门禁看得见。
CAPABILITIES: dict[str, Capability] = {
    "tb_detail": Capability(
        name="tb_detail",
        description="试算表（trial_balance）在其审计年度有行：五列金额与 Σ审定 的对账需要真实分布",
        metric_sql=(
            "SELECT count(*) FROM trial_balance t "
            "WHERE t.project_id = l.id AND t.year = l.audit_year AND NOT t.is_deleted"
        ),
        extra_sql="l.audit_year IS NOT NULL",
    ),
    "balance_direction_columns": Capability(
        name="balance_direction_columns",
        description="余额表（tb_balance）的期末方向列有值：方向列分布判据需要真实取值集合",
        metric_sql=(
            "SELECT count(*) FROM tb_balance b "
            "WHERE b.project_id = l.id AND b.year = l.audit_year AND NOT b.is_deleted "
            "AND b.closing_direction IS NOT NULL"
        ),
        extra_sql="l.audit_year IS NOT NULL",
    ),
    "aux_balance_direction_columns": Capability(
        name="aux_balance_direction_columns",
        description="辅助余额（tb_aux_balance）的期末方向列有值",
        metric_sql=(
            "SELECT count(*) FROM tb_aux_balance a "
            "WHERE a.project_id = l.id AND a.year = l.audit_year AND NOT a.is_deleted "
            "AND a.closing_direction IS NOT NULL"
        ),
        extra_sql="l.audit_year IS NOT NULL",
    ),
    "ledger_over_fetch_cap": Capability(
        name="ledger_over_fetch_cap",
        description=(
            "生效数据集下的序时账行数远超内存硬上限（FETCH_HARD_CAP=5000）："
            "COUNT / 排序 / 分页是否真的下推数据库，只有在这种量级上才测得出"
        ),
        metric_sql=(
            f"SELECT count(*) FROM tb_ledger g JOIN ({_ACTIVE_DATASET}) act "
            "ON act.project_id = g.project_id AND act.year = g.year AND act.dataset_id = g.dataset_id "
            "WHERE g.project_id = l.id AND g.year = l.audit_year AND NOT g.is_deleted"
        ),
        require_gt=5_000,
        extra_sql="l.audit_year IS NOT NULL",
    ),
    "ledger_over_export_hard_limit": Capability(
        name="ledger_over_export_hard_limit",
        description="生效数据集下的序时账行数超过导出硬上限（1,000,000）：整表导出必须被拒而不是截断",
        metric_sql=(
            f"SELECT count(*) FROM tb_ledger g JOIN ({_ACTIVE_DATASET}) act "
            "ON act.project_id = g.project_id AND act.year = g.year AND act.dataset_id = g.dataset_id "
            "WHERE g.project_id = l.id AND g.year = l.audit_year AND NOT g.is_deleted"
        ),
        require_gt=1_000_000,
        extra_sql="l.audit_year IS NOT NULL",
    ),
    "aux_multi_dimension": Capability(
        name="aux_multi_dimension",
        description="辅助余额有多个辅助维度（aux_type）：跨维度告警与收窄到单一维度的判据需要 ≥ 2 个维度",
        metric_sql=(
            "SELECT count(DISTINCT a.aux_type) FROM tb_aux_balance a "
            "WHERE a.project_id = l.id AND a.year = l.audit_year AND NOT a.is_deleted"
        ),
        require_gt=1,
        extra_sql="l.audit_year IS NOT NULL",
    ),
    "report_full_with_stale_mix": Capability(
        name="report_full_with_stale_mix",
        description=(
            "六类报表齐全且**既有过期又有未过期**：过期告警与未生成告警要能分别落点，"
            "全过期或全不过期都测不出区分"
        ),
        metric_sql=(
            "SELECT count(*) FROM financial_report f "
            "WHERE f.project_id = l.id AND f.year = l.audit_year AND NOT f.is_deleted"
        ),
        extra_sql=(
            "l.audit_year IS NOT NULL AND EXISTS ("
            "  SELECT 1 FROM financial_report f2 WHERE f2.project_id = l.id AND f2.year = l.audit_year"
            "  AND NOT f2.is_deleted AND f2.is_stale) "
            "AND EXISTS ("
            "  SELECT 1 FROM financial_report f3 WHERE f3.project_id = l.id AND f3.year = l.audit_year"
            "  AND NOT f3.is_deleted AND NOT f3.is_stale)"
        ),
    ),
    "report_absent": Capability(
        name="report_absent",
        description=(
            "**没有**生成任何报表但有试算表数据：验「没生成报表时只返回结构、金额全空」。"
            "度量用试算表行数（越多越像个真实项目），报表行数必须为 0"
        ),
        metric_sql=(
            "SELECT count(*) FROM trial_balance t "
            "WHERE t.project_id = l.id AND t.year = l.audit_year AND NOT t.is_deleted"
        ),
        extra_sql=(
            "l.audit_year IS NOT NULL AND NOT EXISTS ("
            "  SELECT 1 FROM financial_report f WHERE f.project_id = l.id AND NOT f.is_deleted)"
        ),
    ),
    "workpapers": Capability(
        name="workpapers",
        description="有未删除底稿：底稿清单取数与 `wp_code` 排序判据",
        metric_sql=(
            "SELECT count(*) FROM working_paper w WHERE w.project_id = l.id AND NOT w.is_deleted"
        ),
    ),
    "disclosure_notes": Capability(
        name="disclosure_notes",
        description="有附注章节：附注目录与逐表取数判据",
        metric_sql="SELECT count(*) FROM disclosure_notes d WHERE d.project_id = l.id",
    ),
    "adjustments_aje": Capability(
        name="adjustments_aje",
        description="有 AJE 调整分录（小写枚举）：调整分录源的逐行对账",
        metric_sql=(
            "SELECT count(*) FROM adjustments j WHERE j.project_id = l.id AND NOT j.is_deleted "
            "AND j.adjustment_type::text = 'aje'"
        ),
    ),
    "balance_without_active_dataset": Capability(
        name="balance_without_active_dataset",
        description=(
            "有余额表行但该年度**没有 active 数据集**：生效数据集口径在"
            "「没有 active 数据集时只按未删过滤」这一分支上的判据"
        ),
        metric_sql=(
            "SELECT count(*) FROM tb_balance b WHERE b.project_id = l.id AND NOT b.is_deleted "
            f"AND NOT EXISTS (SELECT 1 FROM ({_ACTIVE_DATASET}) act "
            "WHERE act.project_id = b.project_id AND act.year = b.year)"
        ),
    ),
    "consolidated_with_notes": Capability(
        name="consolidated_with_notes",
        description="合并口径项目（report_scope='consolidated'）且有合并附注数据",
        metric_sql="SELECT count(*) FROM consol_note_data c WHERE c.project_id = l.id",
        extra_sql="l.report_scope = 'consolidated'",
    ),
}


class PickResolver:
    """按能力解析项目；每条能力只查一次库，结果缓存在实例上。"""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._cache: dict[str, Pick] = {}

    async def _rows(self, sql: str, params: Mapping[str, Any] | None = None) -> list[tuple]:
        async with self._engine.connect() as conn:
            await conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            try:
                return [tuple(r) for r in (await conn.execute(text(sql), dict(params or {}))).all()]
            finally:
                await conn.rollback()

    async def candidates(self, capability: str, limit: int = 5) -> list[tuple]:
        """该能力的前 N 名候选 ``(id, name, audit_year, report_scope, template_type, metric)``。"""
        cap = CAPABILITIES[capability]
        sql = (
            f"WITH live AS ({_LIVE_PROJECTS}) "
            "SELECT l.id::text, l.name, l.audit_year, l.report_scope, l.template_type, "
            f"({cap.metric_sql}) AS metric "
            "FROM live l "
            f"WHERE ({cap.extra_sql}) AND ({cap.metric_sql}) > :require "
            "ORDER BY metric DESC, l.id ASC "
            f"LIMIT {int(limit)}"
        )
        return await self._rows(sql, {"require": cap.require_gt})

    async def resolve(self, capability: str) -> Pick:
        """解析一条能力；取不到就当场失败并打印判据与实际分布（绝不 skip、绝不返回空）。"""
        if capability in self._cache:
            return self._cache[capability]
        if capability not in CAPABILITIES:
            pytest.fail(f"未登记的能力 {capability!r}；已登记：{sorted(CAPABILITIES)}")
        cap = CAPABILITIES[capability]
        rows = await self.candidates(capability, limit=5)
        if not rows:
            # 失败信息要能直接指向"库里现在到底有什么"，否则下一个人还得重新查一遍
            diag = await self._rows(
                f"WITH live AS ({_LIVE_PROJECTS}) "
                "SELECT l.name, l.audit_year, "
                f"({cap.metric_sql}) AS metric FROM live l "
                "ORDER BY metric DESC NULLS LAST, l.id ASC LIMIT 8"
            )
            listing = "；".join(f"{name}(年度 {year}) = {metric}" for name, year, metric in diag)
            pytest.fail(
                f"没有项目满足能力 {capability!r}（判据：{cap.description}；要求度量 > {cap.require_gt}，"
                f"附加条件 {cap.extra_sql}）。\n"
                f"库内度量前 8 名：{listing}\n"
                "这不是环境问题就是判据问题：要么共享库数据变了（请改判据或补数据），"
                "要么判据写错了（请核对 SQL）。**不要把这条用例改成跳过**。"
            )
        pid, name, audit_year, report_scope, template_type, metric = rows[0]
        pick = Pick(
            id=uuid.UUID(pid),
            name=name,
            audit_year=audit_year,
            report_scope=report_scope,
            template_type=template_type,
            capability=capability,
            metric=int(metric),
        )
        self._cache[capability] = pick
        return pick
