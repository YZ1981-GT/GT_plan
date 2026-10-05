"""公式推送的公共取数上下文（与 rules.FORMULA_CONTEXTS 一一对应）。

spec: chain-closure-phase2-formula-push-engine · design §四 / ADR-PUSH-001 / ADR-PUSH-002

* ``tb:trial_balance_audited`` —— ``TB(code,'期末余额')`` = ``trial_balance.audited_amount``（试算表
  持久化审定数），``TB(code,'年初余额')`` = ``opening_balance``；均按标准码前缀汇总（科目及其子级），
  与报表引擎审定模式（``ReportFormulaParser``）逐值同口径
  （``test_tb_context_matches_report_engine_including_sub_level_codes`` 守卫）。
* ``adj:hall_approved_excluding_workpaper`` —— ``ADJ(code,'aje_net')`` = 调整分录大厅**已批准**、
  且 ``origin≠workpaper`` 的净额（底稿来源分录已由 E1-5 本地调整计入，排除以免重计）；同样按标准码前缀
  归入所给科目，与试算表审定数口径一致。

两者都**不吞异常**：取数失败抛给引擎，整次推送判失败，不拿「查询失败的 0」去覆盖真实值。
"""
from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa

from app.services.formula_engine import FormulaContext


@dataclass(frozen=True)
class TbAuditedSnapshot:
    """试算表审定口径取数结果。``available=False`` = 本项目该年度试算表尚无任何行。"""

    tb_data: Mapping[str, Mapping[str, Decimal]]
    available: bool
    company_codes: tuple[str, ...] = ()


async def load_tb_audited(db, project_id: UUID, year: int, codes: Collection[str]) -> TbAuditedSnapshot:
    """按标准科目码**前缀**汇总 ``audited_amount`` / ``opening_balance``（缺该科目 = 诚实的 0）。

    🔴 必须与报表引擎 ``ReportFormulaParser._get_tb_rows_prefix`` 同口径（``LIKE 'code%'`` = 科目及其全部子级标准码）：
    「试算平衡表数」核对的是报表货币资金行。精确匹配会整段漏掉映射到子级标准码的科目 —— 真库和平药房_2024
    的 1012 本行为 0、``101202`` / ``101203`` 合计 52,475,713.77（报表计入），审定表会凭空多出这么大的差异数。
    试算表行由叶子逐一映射到唯一标准码生成（``recalc_unadjusted``），前缀汇总不会重复计数。
    """
    from app.models.audit_platform_models import TrialBalance

    wanted = [str(c) for c in codes]
    base = sa.and_(
        TrialBalance.project_id == project_id,
        TrialBalance.year == year,
        TrialBalance.is_deleted == sa.false(),
    )
    company_rows = (await db.execute(
        sa.select(TrialBalance.company_code).where(base).distinct()
    )).scalars().all()
    rows = (await db.execute(
        sa.select(
            TrialBalance.standard_account_code,
            TrialBalance.audited_amount,
            TrialBalance.opening_balance,
        ).where(base, sa.or_(*[TrialBalance.standard_account_code.like(f"{c}%") for c in wanted]))
    )).all() if wanted else []
    audited: dict[str, Decimal] = {c: Decimal("0") for c in wanted}
    opening: dict[str, Decimal] = {c: Decimal("0") for c in wanted}
    for r in rows:
        for c in wanted:  # 每个科目各自按前缀取（与报表引擎逐个 TB() 求值一致）
            if (r.standard_account_code or "").startswith(c):
                audited[c] += r.audited_amount or Decimal("0")
                opening[c] += r.opening_balance or Decimal("0")
    tb_data = {c: {"期末余额": audited[c], "年初余额": opening[c],
                   "本期发生额": audited[c] - opening[c]} for c in wanted}
    return TbAuditedSnapshot(
        tb_data=tb_data,
        available=bool(company_rows),
        company_codes=tuple(sorted(str(c) for c in company_rows if c is not None)),
    )


async def load_hall_adjustments(db, project_id: UUID, year: int, codes: Collection[str]) -> dict[str, dict[str, Decimal]]:
    """大厅已批准、非底稿来源的调整净额，按标准码**前缀**归入所给科目（键名沿用 ``adj_net_batch``，禁转换）。

    与 :func:`load_tb_audited` 同口径：记到子级标准码（如 ``101202`` 银行本票存款）的 AJE 进试算表 ``101202``
    行、被报表 ``TB('1012')`` 前缀汇总计入 —— 这里若只取 ``1012`` 本码，E1 审定合计就会漏掉它，与试算平衡表数
    凭空差出该笔调整。过滤与符号归一全部仍由 ``adj_net_batch`` 负责（approved、排除 ``origin=workpaper``）。
    """
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry
    from app.services.adjustment_amount_source import adj_net_batch

    wanted = [str(c) for c in codes]
    if not wanted:
        return {}
    entry_codes = (await db.execute(
        sa.select(AdjustmentEntry.standard_account_code).distinct()
        .join(Adjustment, AdjustmentEntry.adjustment_id == Adjustment.id)
        .where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            sa.or_(*[AdjustmentEntry.standard_account_code.like(f"{c}%") for c in wanted]),
        )
    )).scalars().all()
    by_code = await adj_net_batch(
        db,
        project_id=project_id,
        year=year,
        account_codes=sorted({*wanted, *(c for c in entry_codes if c)}),
        include_statuses=None,  # None = DEFAULT_INCLUDE_STATUSES（仅 approved，ADR-ADJ-003）
        exclude_origins=frozenset({"workpaper"}),
    )
    out: dict[str, dict[str, Decimal]] = {}
    for code, values in by_code.items():
        for c in wanted:
            if code.startswith(c):
                bucket = out.setdefault(c, {k: Decimal("0") for k in values})
                for k, v in values.items():
                    bucket[k] = bucket.get(k, Decimal("0")) + v
    return out


@dataclass
class FormulaSources:
    """一次推送用到的公式上下文素材。"""

    #: context_for / unavailable_reason 共用的试算表口径名集合（新增口径只改这里）
    _TB_CONTEXTS: frozenset[str] = frozenset({"trial_balance_audited", "trial_balance_audited_occurrence"})

    tb: TbAuditedSnapshot | None = None
    hall_adj: dict[str, dict[str, Decimal]] = field(default_factory=dict)

    def context_for(self, context: Mapping[str, str]) -> FormulaContext:
        """按规则声明的 context 组装 FormulaContext（未声明的维度不给数据）。"""
        tb_data: dict[str, dict[str, Decimal]] = {}
        adj_data: dict[str, dict[str, Decimal]] = {}
        if context.get("tb") in self._TB_CONTEXTS:
            if self.tb is None:
                raise RuntimeError("试算表审定口径未加载")
            tb_data = {k: dict(v) for k, v in self.tb.tb_data.items()}
        if context.get("adj") == "hall_approved_excluding_workpaper":
            adj_data = {k: dict(v) for k, v in self.hall_adj.items()}
        return FormulaContext(tb_data=tb_data, adj_data=adj_data)

    def unavailable_reason(self, context: Mapping[str, str]) -> str | None:
        """规则所需上下文无从取数时的中文原因；None = 可求值。"""
        if context.get("tb") in self._TB_CONTEXTS and (self.tb is None or not self.tb.available):
            return "试算表尚未生成（四表导入并重算试算表后推送）"
        return None
