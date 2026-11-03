"""按**数据能力**动态解析真库项目（取代 ``gold.py`` 里写死的 9 个项目 UUID）。

## 为什么不能再写死 UUID

2026-11-01 现算：`gold.py` 里 HS / HP / YB / LN / MD / WL / UA / UB / UP 共 **9 个 UUID 在
`projects` 表里全都查不到行**（不是软删，是不存在；以 UAT 命名的项目现库一个都没有）。
写死 UUID 的失效方式很隐蔽 —— 用例不会说"项目没了"，而是拿 403 / 空集去跟同样是空的金标准
互相印证，**看起来绿、其实什么都没验**。

## 为什么是「按能力」而不是「按项目」

老的角色划分已经无解。例如原 `HS`（华氏）同时被要求「有 AJE 调整分录」「RJE 恰好 0 行」
「有底稿」「有附注」「六类报表且既有过期又有未过期」，而现库里华氏 `a7fc75e5` 的 adjustments
与底稿都是 0，重药安徽 `0ec33ac9` 有 8 条 AJE 但 **RJE 有 2 条** —— 没有任何一个活项目能同时满足。

所以这里不按"项目代号"解析，而是按**能力**解析：每条能力是一个显式判据（SQL + 确定性排序），
谁满足就用谁。判据恒定、数据随库变；同一条用例在不同时间可能落到不同项目上 —— 这是用户
2026-11-01 明确接受的取舍（替代方案「每次手工更新 9 个 UUID」等于把这次的失效模式留在原地）。

**写入类判据不在这里**：写入隔离、合成形态（多数据集、软删行、项目独有报表行等）在回滚事务里
自建（``writable_projects`` 与 conftest 的 ``writable_project`` / ``no_active_dataset_project``）。
口径类判据（Σ审定 = 金标准、百万行 COUNT 不截断、方向列分布）只在真实数据分布上才有意义，
合成夹具会把它们降级成「实现与实现自比」，所以留在真实项目上。

## 实现纪律

1. **只用显式列的裸 SQL，禁 `db.get(Project, ...)`**：ORM 声明的列可以领先于共享库
   （2026-11-01 现算缺 `projects.amount_unit`；2026-11-03 21:48 已由他人迁到 V251，但 V236 /
   V248 / V249 仍缺），全列 ORM 投影会让整条链路 500。
2. **取不到就当场失败并打印判据与库内度量分布**，绝不 `skip`、绝不退化成"空集也算过"。
3. **确定性排序**：``度量 DESC|ASC, id ASC``，同样的库必须选出同一个项目。
4. **四表度量只数生效数据集里的行**：接口读的就是这些行；按「只按未删」数会挑中
   「数据都在非生效数据集里」的项目，用例随后在前置上红。
5. ``prefer="min"``：判据只是「超过某个阈值」时取**刚好满足的最小项目**，COUNT 类用例因此快一个
   数量级（如「序时账 > 5,000 行」取 2 万行的项目而不是 250 万行的项目）；判据本身不变。

解析结果按 ``(数据库, 能力)`` 缓存在进程内：所有写入都在回滚事务里、从不提交，一次测试运行内
已提交数据不变，没必要每条用例重查一遍（序时账度量要扫数百万行）。``test_aql_project_picks_pg``
的确定性用例显式绕过缓存。
"""
from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Mapping
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

#: 四表的生效数据集子查询（与 ``dataset_query.get_active_filter`` 同口径）：取该 (项目, 年度) 下
#: ``activated_at`` 最新（空值在后）、其次 ``created_at`` 最新的 active 数据集。
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

_AUDIT_YEAR_SET = "l.audit_year IS NOT NULL"


def _active(table: str, alias: str, where: str = "TRUE", select: str = "count(*)") -> str:
    """审计年度、生效数据集、未删的四表行上的聚合（标量子查询，外层相关列为 ``l``）。"""
    return (
        f"SELECT {select} FROM {table} {alias} JOIN ({_ACTIVE_DATASET}) act "
        f"ON act.project_id = {alias}.project_id AND act.year = {alias}.year "
        f"AND act.dataset_id = {alias}.dataset_id "
        f"WHERE {alias}.project_id = l.id AND {alias}.year = l.audit_year AND NOT {alias}.is_deleted "
        f"AND ({where})"
    )


def _exists_active(table: str, alias: str, where: str) -> str:
    return f"EXISTS ({_active(table, alias, where, select='1')})"


def _trial_balance(where: str = "TRUE", select: str = "count(*)") -> str:
    return (
        f"SELECT {select} FROM trial_balance t "
        f"WHERE t.project_id = l.id AND t.year = l.audit_year AND NOT t.is_deleted AND ({where})"
    )


def _report(where: str = "TRUE", select: str = "count(*)") -> str:
    return (
        f"SELECT {select} FROM financial_report f "
        f"WHERE f.project_id = l.id AND f.year = l.audit_year AND NOT f.is_deleted AND ({where})"
    )


#: 判据片段（命名后再拼进能力，避免在 f-string 里嵌套引号）
_TB_HAS_1001 = _trial_balance("t.standard_account_code = '1001'", "1")
_BANK_AUX_BALANCE_WHERE = "a.account_code LIKE '1002%' AND a.aux_type = '银行账户'"
_AUX_LEDGER_HAS_1002 = _exists_active("tb_aux_ledger", "x", "x.account_code LIKE '1002%'")
_AUX_LEDGER_HAS_BANK = _exists_active("tb_aux_ledger", "y", "y.aux_type = '银行账户'")
_REPORT_TYPES = _report(select="count(DISTINCT f.report_type)")
_REPORT_STALE_TYPES = _report("f.is_stale", "count(DISTINCT f.report_type)")
_REPORT_HAS_STALE = _report("f.is_stale", "1")
_REPORT_BS002_HAS_AMOUNT = _report(
    "f.report_type::text = 'balance_sheet' AND f.row_code = 'BS-002' AND f.current_period_amount IS NOT NULL", "1"
)
_REPORT_BS_OVER_1E8 = _report("f.report_type::text = 'balance_sheet' AND f.current_period_amount > 100000000", "1")


@dataclasses.dataclass(frozen=True)
class Pick:
    """一条能力解析出的项目。

    ``metric`` 是该能力的排序度量现算值，写进断言失败信息里便于复盘（例如"这个项目被选中是
    因为它的序时账有 22,716 行"）。
    """

    id: uuid.UUID
    name: str
    audit_year: int | None
    report_scope: str | None
    template_type: str | None
    capability: str
    metric: int

    @property
    def standard_family(self) -> str:
        """接口 ``meta.ref_context.template_type`` 的口径：``listed`` 以外一律 ``soe``（见 ``entry_filters``）。"""
        return "listed" if self.template_type == "listed" else "soe"

    def __str__(self) -> str:  # 断言失败信息里直接可读
        return f"{self.name}（{self.id}，年度 {self.audit_year}，{self.capability} 度量 {self.metric}）"


@dataclasses.dataclass(frozen=True)
class Capability:
    """一条能力判据。

    ``metric_sql`` 是以 ``l``（live projects 别名）为外层相关列的标量子查询，返回整数度量；
    度量须 ``> require_gt``，给了 ``require_le`` 时还须 ``<= require_le``；``extra_sql`` 是附加布尔条件。
    ``prefer`` = ``max`` 取度量最大者，``min`` 取刚好满足的最小者；同度量按 id 升序兜底保证唯一。
    """

    name: str
    description: str
    metric_sql: str
    require_gt: int = 0
    require_le: int | None = None
    extra_sql: str = "TRUE"
    prefer: str = "max"

    def __post_init__(self) -> None:
        if self.prefer not in ("max", "min"):
            raise ValueError(f"{self.name}: prefer 只能是 max / min，得 {self.prefer!r}")


#: 能力目录。新增能力请一并在 `test_aql_project_picks_pg.py` 里被参数化覆盖（它直接取本目录），
#: 并至少有一条用例真正 `resolve` 它 —— 只声明不使用的能力由
#: `test_every_capability_is_used_by_some_test` 打红。
CAPABILITIES: dict[str, Capability] = {
    # ── 试算表 ──
    "tb_detail": Capability(
        name="tb_detail",
        description="审计年度的试算表有行：五列金额与 Σ审定 的对账需要真实分布",
        metric_sql=_trial_balance(),
        extra_sql=_AUDIT_YEAR_SET,
    ),
    "tb_account_categories": Capability(
        name="tb_account_categories",
        description="审计年度试算表的科目类别多于 2 个：分组后 total = 组数 的判据要有足够多的组",
        metric_sql=_trial_balance(select="count(DISTINCT t.account_category)"),
        require_gt=2,
        extra_sql=_AUDIT_YEAR_SET,
    ),
    "tb_with_cash_account": Capability(
        name="tb_with_cash_account",
        description="审计年度试算表有标准科目 1001：公式引用 TB('1001','审定数') 在地址库里必须真能校验通过",
        metric_sql=_trial_balance(),
        extra_sql=f"{_AUDIT_YEAR_SET} AND EXISTS ({_TB_HAS_1001})",
    ),
    "tb_and_notes_copy_source": Capability(
        name="tb_and_notes_copy_source",
        description=(
            "审计年度同时有试算表与附注章节：循环级可见性用例要把这两张表整体复制到"
            "回滚事务里新建的【测试】项目上（真实项目只读）"
        ),
        metric_sql=_trial_balance(),
        extra_sql=(
            f"{_AUDIT_YEAR_SET} AND EXISTS ("
            "  SELECT 1 FROM disclosure_notes d WHERE d.project_id = l.id AND d.year = l.audit_year"
            "  AND NOT d.is_deleted)"
        ),
    ),
    "account_chart_two_sources": Capability(
        name="account_chart_two_sources",
        description=(
            "科目表同一科目码有标准 / 客户两套行：只按科目码关联会把试算表放大，登记的 JOIN 只认标准科目；"
            "试算行 ≤ 1,000（用例一页取完）且确有标准科目匹配"
        ),
        metric_sql=_trial_balance(),
        require_le=1000,
        extra_sql=(
            f"{_AUDIT_YEAR_SET} AND ("
            "  SELECT count(*) FROM trial_balance t LEFT JOIN account_chart c"
            "  ON c.project_id = t.project_id AND c.account_code = t.standard_account_code"
            "  WHERE t.project_id = l.id AND t.year = l.audit_year AND NOT t.is_deleted"
            f") > ({_trial_balance()}) AND EXISTS ("
            "  SELECT 1 FROM trial_balance t JOIN account_chart c"
            "  ON c.project_id = t.project_id AND c.account_code = t.standard_account_code"
            "  AND c.source = 'standard' AND NOT c.is_deleted"
            "  WHERE t.project_id = l.id AND t.year = l.audit_year AND NOT t.is_deleted)"
        ),
    ),
    # ── 余额表 / 辅助余额 ──
    "balance_direction_columns": Capability(
        name="balance_direction_columns",
        description="生效数据集的余额表（tb_balance）期末方向列有值：方向列分布判据需要真实取值集合",
        metric_sql=_active("tb_balance", "b", "b.closing_direction IS NOT NULL"),
        extra_sql=_AUDIT_YEAR_SET,
    ),
    "aux_balance_direction_columns": Capability(
        name="aux_balance_direction_columns",
        description="生效数据集的辅助余额（tb_aux_balance）期末方向列有值",
        metric_sql=_active("tb_aux_balance", "a", "a.closing_direction IS NOT NULL"),
        extra_sql=_AUDIT_YEAR_SET,
        prefer="min",
    ),
    "balance_with_narrowing_active_dataset": Capability(
        name="balance_with_narrowing_active_dataset",
        description=(
            "审计年度**有** active 数据集，且生效口径**严格窄于**「只按未删」"
            "（该年度还存在属于非生效数据集的行）：AQ-02 口径差的正面样本 —— "
            "口径相等的项目证明不了「生效数据集过滤真的在起作用」"
        ),
        metric_sql=_active("tb_balance", "b"),
        extra_sql=(
            f"{_AUDIT_YEAR_SET} AND ({_active('tb_balance', 'b2')}) < ("
            "  SELECT count(*) FROM tb_balance b3"
            "  WHERE b3.project_id = l.id AND b3.year = l.audit_year AND NOT b3.is_deleted)"
        ),
    ),
    "aux_bank_account_1002": Capability(
        name="aux_bank_account_1002",
        description=(
            "生效数据集里银行存款（1002 前缀）有按「银行账户」的辅助余额，且辅助明细既有 1002 前缀行、"
            "也有「银行账户」行：辅助余额对账、辅助明细必须收窄与按类型收窄三条判据都要有真实行"
        ),
        metric_sql=_active("tb_aux_balance", "a", _BANK_AUX_BALANCE_WHERE),
        extra_sql=f"{_AUDIT_YEAR_SET} AND {_AUX_LEDGER_HAS_1002} AND {_AUX_LEDGER_HAS_BANK}",
        prefer="min",
    ),
    # ── 序时账 ──
    "ledger_over_fetch_cap": Capability(
        name="ledger_over_fetch_cap",
        description=(
            "生效数据集的序时账多于内存硬上限 FETCH_HARD_CAP = 5,000 行：COUNT / 排序 / 分页是否真的"
            "下推数据库，只有在这种量级上才测得出"
        ),
        metric_sql=_active("tb_ledger", "g"),
        require_gt=5_000,
        extra_sql=_AUDIT_YEAR_SET,
        prefer="min",
    ),
    "ledger_over_max_offset": Capability(
        name="ledger_over_max_offset",
        description="生效数据集的序时账多于 MAX_SQL_OFFSET + 50 = 100,050 行：offset 100,000 处仍能取满一页",
        metric_sql=_active("tb_ledger", "g"),
        require_gt=100_050,
        extra_sql=_AUDIT_YEAR_SET,
        prefer="min",
    ),
    "ledger_over_export_hard_limit": Capability(
        name="ledger_over_export_hard_limit",
        description="生效数据集的序时账超过导出硬上限 1,000,000 行：整表导出必须在取数前被拒而不是截断",
        metric_sql=_active("tb_ledger", "g"),
        require_gt=1_000_000,
        extra_sql=_AUDIT_YEAR_SET,
        prefer="min",
    ),
    "ledger_month_export": Capability(
        name="ledger_month_export",
        description="审计年度 1 月的序时账多于旧导出上限 1,000 行：按月完整导出的行数必须等于 COUNT",
        metric_sql=_active(
            "tb_ledger", "g",
            "g.voucher_date >= make_date(l.audit_year, 1, 1) AND g.voucher_date < make_date(l.audit_year, 2, 1)",
        ),
        require_gt=1_000,
        extra_sql=_AUDIT_YEAR_SET,
        prefer="min",
    ),
    "ledger_with_null_debit": Capability(
        name="ledger_with_null_debit",
        description="生效数据集的序时账有借方为空的行：降序排序时空值排在最后的判据需要真实的空值",
        metric_sql=_active("tb_ledger", "g", "g.debit_amount IS NULL"),
        extra_sql=_AUDIT_YEAR_SET,
        prefer="min",
    ),
    "ledger_debit_over_1e8_within_page": Capability(
        name="ledger_debit_over_1e8_within_page",
        description="生效数据集有借方 > 1 亿的序时账行且不超过 2,000 行：条件计数在库内完成、一页取完逐行核对",
        metric_sql=_active("tb_ledger", "g", "g.debit_amount > 100000000"),
        require_le=2_000,
        extra_sql=_AUDIT_YEAR_SET,
        prefer="min",
    ),
    "ledger_1002_over_fetch_cap": Capability(
        name="ledger_1002_over_fetch_cap",
        description="生效数据集里 1002 前缀的序时账多于 5,000 行：分组触顶必须 400 拒绝而不是截断",
        metric_sql=_active("tb_ledger", "g", "g.account_code LIKE '1002%'"),
        require_gt=5_000,
        extra_sql=_AUDIT_YEAR_SET,
        prefer="min",
    ),
    # ── 报表 ──
    "report_rich": Capability(
        name="report_rich",
        description=(
            "审计年度报表齐备且形态完整：有带过期行的报表类型、也有不带的；资产负债表货币资金（BS-002）"
            "本期有值；有本期金额 > 1 亿的资产负债表行。报表源对账、过期 / 未生成告警分别落点、"
            "条件在库内求值三类判据都要这些形态"
        ),
        metric_sql=_REPORT_TYPES,
        extra_sql=(
            f"{_AUDIT_YEAR_SET} AND EXISTS ({_REPORT_HAS_STALE}) AND ({_REPORT_TYPES}) > ({_REPORT_STALE_TYPES}) "
            f"AND EXISTS ({_REPORT_BS002_HAS_AMOUNT}) AND EXISTS ({_REPORT_BS_OVER_1E8})"
        ),
    ),
    "report_absent": Capability(
        name="report_absent",
        description=(
            "**没有**生成任何报表但有试算表数据：验「没生成报表时只返回结构、金额全空」。"
            "度量用试算表行数（越多越像个真实项目），报表行数必须为 0"
        ),
        metric_sql=_trial_balance(),
        extra_sql=(
            f"{_AUDIT_YEAR_SET} AND NOT EXISTS ("
            "  SELECT 1 FROM financial_report f WHERE f.project_id = l.id AND NOT f.is_deleted)"
        ),
    ),
    "financial_report_rows": Capability(
        name="financial_report_rows",
        description="审计年度有已生成的报表行：构建器 financial_report 表按项目作用域取数",
        metric_sql=_report(),
        extra_sql=_AUDIT_YEAR_SET,
        prefer="min",
    ),
    # ── 底稿 / 附注 / 调整分录 / 合并 ──
    "workpapers": Capability(
        name="workpapers",
        description="有未删除底稿且不超过 2,000 张：底稿清单取数与 wp_code 排序判据（用例一页取完）",
        metric_sql=(
            "SELECT count(*) FROM working_paper w JOIN wp_index i ON i.id = w.wp_index_id "
            "WHERE w.project_id = l.id AND NOT w.is_deleted"
        ),
        require_le=2_000,
    ),
    "notes_multi_table_total": Capability(
        name="notes_multi_table_total",
        description=(
            "审计年度附注多于 100 节，且有一节含 ≥ 2 张表、第二张表最后一行是「合计」：附注目录、"
            "逐表取数与切表判据（取表、行序、合计行位置）都要这种章节"
        ),
        metric_sql=(
            "SELECT count(*) FROM disclosure_notes d "
            "WHERE d.project_id = l.id AND d.year = l.audit_year AND NOT d.is_deleted"
        ),
        require_gt=100,
        extra_sql=(
            f"{_AUDIT_YEAR_SET} AND EXISTS ("
            "  SELECT 1 FROM disclosure_notes d WHERE d.project_id = l.id AND d.year = l.audit_year"
            "  AND NOT d.is_deleted"
            "  AND CASE WHEN jsonb_typeof(d.table_data->'_tables') = 'array'"
            "      THEN jsonb_array_length(d.table_data->'_tables') ELSE 0 END >= 2"
            "  AND d.table_data->'_tables'->1->'rows'->-1->>'label' = '合计')"
        ),
    ),
    "adjustments_aje": Capability(
        name="adjustments_aje",
        description="审计年度有 AJE 调整分录（小写枚举）：调整分录源对真实行逐行对账",
        metric_sql=(
            "SELECT count(*) FROM adjustments j WHERE j.project_id = l.id AND j.year = l.audit_year "
            "AND NOT j.is_deleted AND j.adjustment_type::text = 'aje'"
        ),
        extra_sql=_AUDIT_YEAR_SET,
    ),
    "consolidated_with_notes": Capability(
        name="consolidated_with_notes",
        description="合并口径项目（report_scope='consolidated'）且有合并附注数据",
        metric_sql="SELECT count(*) FROM consol_note_data c WHERE c.project_id = l.id",
        extra_sql="l.report_scope = 'consolidated'",
    ),
}

#: 进程内缓存：``(数据库 URL, 能力) -> Pick``（见模块说明）
_PROCESS_CACHE: dict[tuple[str, str], Pick] = {}


class PickResolver:
    """按能力解析项目。

    ``use_process_cache=False`` 时每次都重查（确定性用例用它证明排序可复现）。
    """

    def __init__(self, engine: AsyncEngine, *, use_process_cache: bool = True) -> None:
        self._engine = engine
        self._use_process_cache = use_process_cache
        self._cache: dict[str, Pick] = {}

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def _rows(self, sql: str, params: Mapping[str, Any] | None = None) -> list[tuple]:
        async with self._engine.connect() as conn:
            await conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            try:
                return [tuple(r) for r in (await conn.execute(text(sql), dict(params or {}))).all()]
            finally:
                await conn.rollback()

    @staticmethod
    def _scored_sql(cap: Capability) -> str:
        # 度量只算一次：内层逐项目算度量（附加条件在内层过滤），外层按阈值过滤与排序
        return (
            f"WITH live AS ({_LIVE_PROJECTS}), scored AS ("
            "  SELECT l.id::text AS id, l.name, l.audit_year, l.report_scope, l.template_type, "
            f"  ({cap.metric_sql}) AS metric FROM live l WHERE ({cap.extra_sql}))"
        )

    async def candidates(self, capability: str, limit: int = 5) -> list[tuple]:
        """该能力的前 N 名候选 ``(id, name, audit_year, report_scope, template_type, metric)``。"""
        cap = CAPABILITIES[capability]
        direction = "DESC" if cap.prefer == "max" else "ASC"
        upper = "" if cap.require_le is None else " AND metric <= :require_le"
        sql = (
            f"{self._scored_sql(cap)} "
            "SELECT id, name, audit_year, report_scope, template_type, metric FROM scored "
            f"WHERE metric > :require_gt{upper} ORDER BY metric {direction}, id ASC LIMIT {int(limit)}"
        )
        params: dict[str, Any] = {"require_gt": cap.require_gt}
        if cap.require_le is not None:
            params["require_le"] = cap.require_le
        return await self._rows(sql, params)

    async def resolve(self, capability: str) -> Pick:
        """解析一条能力；取不到就当场失败并打印判据与实际分布（绝不 skip、绝不返回空）。"""
        if capability in self._cache:
            return self._cache[capability]
        if capability not in CAPABILITIES:
            pytest.fail(f"未登记的能力 {capability!r}；已登记：{sorted(CAPABILITIES)}")
        key = (str(self._engine.url), capability)
        if self._use_process_cache and key in _PROCESS_CACHE:
            self._cache[capability] = _PROCESS_CACHE[key]
            return self._cache[capability]
        cap = CAPABILITIES[capability]
        rows = await self.candidates(capability, limit=1)
        if not rows:
            # 失败信息要能直接指向"库里现在到底有什么"，否则下一个人还得重新查一遍
            diag = await self._rows(
                f"WITH live AS ({_LIVE_PROJECTS}) "
                f"SELECT l.name, l.audit_year, ({cap.metric_sql}) AS metric, ({cap.extra_sql}) AS extra_ok "
                "FROM live l ORDER BY metric DESC NULLS LAST, l.id ASC LIMIT 8"
            )
            listing = "；".join(
                f"{name}(年度 {year}) = {metric}{'' if ok else '（附加条件不满足）'}"
                for name, year, metric, ok in diag
            )
            bound = f"> {cap.require_gt}" + ("" if cap.require_le is None else f" 且 ≤ {cap.require_le}")
            pytest.fail(
                f"没有项目满足能力 {capability!r}（判据：{cap.description}；要求度量 {bound}，"
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
        if self._use_process_cache:
            _PROCESS_CACHE[key] = pick
        return pick
