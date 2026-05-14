"""试算表计算引擎 — 增量更新 + 全量重算 + 事件处理器

Validates: Requirements 6.1-6.12, 10.1-10.6
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountMapping,
    AccountSource,
    Adjustment,
    AdjustmentType,
    TbBalance,
    TrialBalance,
)
from app.models.audit_platform_schemas import EventPayload
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)


class TrialBalanceService:
    """试算表计算引擎"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 未审数重算
    # ------------------------------------------------------------------
    async def recalc_unadjusted(
        self,
        project_id: UUID,
        year: int,
        company_code: str = "001",
        account_codes: list[str] | None = None,
    ) -> None:
        """
        通过 JOIN account_mapping 汇总 tb_balance.closing_balance 到标准科目。
        account_codes=None → 全量; 指定列表 → 增量。

        全量模式下，不在汇总结果中的已有试算表行会被清零（解决回滚后残留问题）。
        使用批量操作减少数据库往返。
        """
        bal = TbBalance.__table__
        mp = AccountMapping.__table__
        ac = AccountChart.__table__
        balance_filter = await get_active_filter(self.db, bal, project_id, year)

        # 1. 汇总查询：客户余额 → 映射 → 标准科目
        agg_q = (
            sa.select(
                mp.c.standard_account_code,
                sa.func.coalesce(sa.func.sum(bal.c.closing_balance), 0).label("total_closing"),
                sa.func.coalesce(sa.func.sum(bal.c.opening_balance), 0).label("total_opening"),
            )
            .select_from(
                bal.join(
                    mp,
                    sa.and_(
                        mp.c.project_id == bal.c.project_id,
                        mp.c.original_account_code == bal.c.account_code,
                        mp.c.is_deleted == sa.false(),
                    ),
                )
            )
            .where(balance_filter)
            .group_by(mp.c.standard_account_code)
        )

        if account_codes:
            agg_q = agg_q.where(mp.c.standard_account_code.in_(account_codes))

        result = await self.db.execute(agg_q)
        agg_rows = {r.standard_account_code: r for r in result.fetchall()}

        # 1b. 损益类科目额外汇总本期发生额（debit_amount - credit_amount）
        # 损益类期末余额通常为 0（已结转），审计需要看本期发生额
        period_agg_q = (
            sa.select(
                mp.c.standard_account_code,
                sa.func.coalesce(sa.func.sum(bal.c.debit_amount), 0).label("total_debit"),
                sa.func.coalesce(sa.func.sum(bal.c.credit_amount), 0).label("total_credit"),
            )
            .select_from(
                bal.join(
                    mp,
                    sa.and_(
                        mp.c.project_id == bal.c.project_id,
                        mp.c.original_account_code == bal.c.account_code,
                        mp.c.is_deleted == sa.false(),
                    ),
                )
            )
            .where(balance_filter)
            .group_by(mp.c.standard_account_code)
        )
        if account_codes:
            period_agg_q = period_agg_q.where(mp.c.standard_account_code.in_(account_codes))

        period_result = await self.db.execute(period_agg_q)
        period_rows = {r.standard_account_code: r for r in period_result.fetchall()}

        # 2. 获取一级科目名称
        # 注意：此时 existing_rows 还未加载，用 agg_rows.keys() 即可（有余额的科目一定在里面）
        level1_names: dict[str, str] = {}
        if agg_rows:
            # 从 tb_balance 取所有相关行的名称（含明细行）
            name_q = (
                sa.select(bal.c.account_code, bal.c.account_name)
                .where(balance_filter)
                .distinct()
            )
            name_result = await self.db.execute(name_q)
            all_names: dict[str, str] = {}
            for r in name_result.fetchall():
                if r.account_code and r.account_name:
                    all_names[r.account_code] = r.account_name

            # 对每个标准科目编码，优先精确匹配，否则从明细行取下划线前的部分
            for code in agg_rows.keys():
                if code in all_names:
                    raw_name = all_names[code]
                    level1_names[code] = raw_name.split('_')[0] if '_' in raw_name else raw_name
                else:
                    for _ac_code, _ac_name in all_names.items():
                        if _ac_code.startswith(code + '.') or (_ac_code.startswith(code) and len(_ac_code) > len(code)):
                            level1_names[code] = _ac_name.split('_')[0] if '_' in _ac_name else _ac_name
                            break

        # 2b. 兜底：从 AccountChart 标准科目表取名称（余额表没有的情况）
        std_q = (
            sa.select(ac.c.account_code, ac.c.account_name, ac.c.category)
            .where(
                ac.c.project_id == project_id,
                ac.c.source == AccountSource.standard.value,
                ac.c.is_deleted == sa.false(),
            )
        )
        if account_codes:
            std_q = std_q.where(ac.c.account_code.in_(account_codes))

        std_result = await self.db.execute(std_q)
        std_map: dict[str, any] = {}
        for r in std_result.fetchall():
            existing = std_map.get(r.account_code)
            if existing is None:
                std_map[r.account_code] = r
            elif len(r.account_name or '') < len(existing.account_name or ''):
                std_map[r.account_code] = r

        # 3. 获取已有试算表行（批量加载）
        tb_q = sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.company_code == company_code,
            TrialBalance.is_deleted == sa.false(),
        )
        if account_codes:
            tb_q = tb_q.where(TrialBalance.standard_account_code.in_(account_codes))

        tb_result = await self.db.execute(tb_q)
        existing_rows = {r.standard_account_code: r for r in tb_result.scalars().all()}

        # 4. 合并所有需要处理的科目（含已有但不在汇总中的——已清零）
        all_codes = set(agg_rows.keys()) | set(std_map.keys()) | set(existing_rows.keys())
        if account_codes:
            all_codes = all_codes & set(account_codes)

        new_rows = []
        for code in all_codes:
            agg = agg_rows.get(code)
            std = std_map.get(code)
            closing = Decimal(str(agg.total_closing)) if agg else Decimal("0")
            opening = Decimal(str(agg.total_opening)) if agg else Decimal("0")
            # 优先用 tb_balance level=1 的一级科目名称（最准确）
            name = level1_names.get(code) or (std.account_name if std else None)
            cat = std.category if std else AccountCategory.asset.value

            # 损益类科目（5xxx/6xxx）：取单边发生额（不做借-贷，因为结转后两边相等）
            # 收入类：取 credit_amount（贷方发生额），存为负数保持"贷方=负"语义
            # 费用/成本类：取 debit_amount（借方发生额），存为正数保持"借方=正"语义
            is_income_expense = code and code[0] in ('5', '6')
            if is_income_expense:
                period = period_rows.get(code)
                if period:
                    total_dr = Decimal(str(period.total_debit))
                    total_cr = Decimal(str(period.total_credit))
                    # 判断是收入类还是费用类：
                    # 收入类编码：5001/5051/5101/6001/6051/6101/6111/6117/6301
                    # 费用类编码：5401+/6401+/6403+/6601+/6602+/6603+/6701+/6702+/6711+/6801+
                    is_revenue = code in ('5001', '5051', '5101') or (
                        code.startswith('6') and code[:4] in ('6001', '6051', '6101', '6111', '6115', '6117', '6301')
                    )
                    if is_revenue:
                        # 收入类：取贷方发生额，存为负数（贷方语义）
                        closing = -total_cr
                    else:
                        # 费用/成本类：取借方发生额，存为正数（借方语义）
                        closing = total_dr
                else:
                    closing = Decimal("0")
                opening = Decimal("0")  # 损益类无期初余额

            row = existing_rows.get(code)
            if row:
                row.unadjusted_amount = closing
                row.opening_balance = opening
                if name:
                    row.account_name = name
                row.audited_amount = closing + row.rje_adjustment + row.aje_adjustment
            else:
                new_rows.append(TrialBalance(
                    project_id=project_id,
                    year=year,
                    company_code=company_code,
                    standard_account_code=code,
                    account_name=name,
                    account_category=cat if isinstance(cat, AccountCategory) else AccountCategory(cat),
                    unadjusted_amount=closing,
                    opening_balance=opening,
                    rje_adjustment=Decimal("0"),
                    aje_adjustment=Decimal("0"),
                    audited_amount=closing,
                ))

        if new_rows:
            self.db.add_all(new_rows)

        await self.db.flush()

    # ------------------------------------------------------------------
    # 调整列重算
    # ------------------------------------------------------------------
    async def recalc_adjustments(
        self,
        project_id: UUID,
        year: int,
        company_code: str = "001",
        account_codes: list[str] | None = None,
    ) -> None:
        """按 adjustment_type 分组汇总 adjustments 表到 rje/aje 列（批量操作）"""
        adj = Adjustment.__table__

        agg_q = (
            sa.select(
                adj.c.account_code,
                adj.c.adjustment_type,
                (sa.func.coalesce(sa.func.sum(adj.c.debit_amount), 0)
                 - sa.func.coalesce(sa.func.sum(adj.c.credit_amount), 0)).label("net"),
            )
            .where(
                adj.c.project_id == project_id,
                adj.c.year == year,
                adj.c.is_deleted == sa.false(),
            )
            .group_by(adj.c.account_code, adj.c.adjustment_type)
        )

        if account_codes:
            agg_q = agg_q.where(adj.c.account_code.in_(account_codes))

        result = await self.db.execute(agg_q)

        # 按科目汇总 rje/aje
        adj_map: dict[str, dict[str, Decimal]] = {}
        for r in result.fetchall():
            code = r.account_code
            if code not in adj_map:
                adj_map[code] = {"rje": Decimal("0"), "aje": Decimal("0")}
            adj_map[code][r.adjustment_type] = Decimal(str(r.net))

        # 批量加载需要更新的试算表行
        codes_to_update = set(adj_map.keys())
        if account_codes:
            codes_to_update = codes_to_update | set(account_codes)

        if not codes_to_update:
            return

        tb_q = sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.company_code == company_code,
            TrialBalance.standard_account_code.in_(codes_to_update),
            TrialBalance.is_deleted == sa.false(),
        )
        tb_result = await self.db.execute(tb_q)
        existing_rows = {r.standard_account_code: r for r in tb_result.scalars().all()}

        for code in codes_to_update:
            vals = adj_map.get(code, {"rje": Decimal("0"), "aje": Decimal("0")})
            row = existing_rows.get(code)
            if row:
                row.rje_adjustment = vals["rje"]
                row.aje_adjustment = vals["aje"]

        await self.db.flush()

    # ------------------------------------------------------------------
    # 审定数重算
    # ------------------------------------------------------------------
    async def recalc_audited(
        self,
        project_id: UUID,
        year: int,
        company_code: str = "001",
        account_codes: list[str] | None = None,
    ) -> None:
        """audited = unadjusted + rje + aje"""
        q = sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.company_code == company_code,
            TrialBalance.is_deleted == sa.false(),
        )
        if account_codes:
            q = q.where(TrialBalance.standard_account_code.in_(account_codes))

        result = await self.db.execute(q)
        for row in result.scalars().all():
            unadj = row.unadjusted_amount or Decimal("0")
            row.audited_amount = unadj + row.rje_adjustment + row.aje_adjustment

        await self.db.flush()

    # ------------------------------------------------------------------
    # 全量重算
    # ------------------------------------------------------------------
    async def full_recalc(
        self,
        project_id: UUID,
        year: int,
        company_code: str = "001",
    ) -> None:
        """全量重算：未审数 → 调整列 → 审定数"""
        await self.recalc_unadjusted(project_id, year, company_code)
        await self.recalc_adjustments(project_id, year, company_code)
        await self.recalc_audited(project_id, year, company_code)

    # ------------------------------------------------------------------
    # 一致性校验
    # ------------------------------------------------------------------
    async def check_consistency(
        self,
        project_id: UUID,
        year: int,
        company_code: str = "001",
    ) -> list[dict]:
        """校验：未审数=映射汇总、调整列=分录汇总、审定数公式正确"""
        issues = []

        # 获取当前试算表
        q = sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.company_code == company_code,
            TrialBalance.is_deleted == sa.false(),
        )
        result = await self.db.execute(q)
        rows = result.scalars().all()

        for row in rows:
            unadj = row.unadjusted_amount or Decimal("0")
            expected_audited = unadj + row.rje_adjustment + row.aje_adjustment
            if row.audited_amount != expected_audited:
                issues.append({
                    "type": "audited_formula",
                    "account_code": row.standard_account_code,
                    "expected": str(expected_audited),
                    "actual": str(row.audited_amount),
                })

        return issues

    # ------------------------------------------------------------------
    # 获取试算表数据
    # ------------------------------------------------------------------
    async def get_trial_balance(
        self,
        project_id: UUID,
        year: int,
        company_code: str = "001",
    ) -> list[TrialBalance]:
        """获取试算表所有行"""
        q = (
            sa.select(TrialBalance)
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.company_code == company_code,
                TrialBalance.is_deleted == sa.false(),
            )
            .order_by(TrialBalance.standard_account_code)
        )
        result = await self.db.execute(q)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # 试算平衡表汇总（按报表行次，AJE/RJE 从 adjustments 自动汇总）
    # ------------------------------------------------------------------
    async def get_summary_with_adjustments(
        self,
        project_id: UUID,
        year: int,
        report_type: str = "balance_sheet",
        company_code: str = "001",
    ) -> list[dict]:
        """
        按报表行次汇总试算平衡表。

        行次结构来自标准库（report_config），所有企业共用同一套模板。
        数据填充根据每个企业的 ReportLineMapping 映射关系。
        """
        from app.models.audit_platform_models import (
            Adjustment,
            AdjustmentType,
            ReportLineMapping,
        )
        from app.models.report_models import ReportConfig

        rlm = ReportLineMapping.__table__
        adj = Adjustment.__table__
        tb = TrialBalance.__table__
        rc = ReportConfig.__table__

        # 1. 从 report_config 加载标准行次模板（所有企业共用）
        # 确定 applicable_standard（从项目配置推断）
        from app.models.core import Project
        proj_result = await self.db.execute(
            sa.select(Project).where(Project.id == project_id)
        )
        proj = proj_result.scalar_one_or_none()
        template_type = 'soe'
        report_scope = 'standalone'
        if proj and proj.wizard_state:
            basic = (proj.wizard_state or {}).get('basic_info', {}).get('data', {})
            template_type = basic.get('template_type', 'soe')
            report_scope = basic.get('report_scope', 'standalone')
        applicable_standard = f"{template_type}_{report_scope}"

        rc_q = (
            sa.select(rc.c.row_code, rc.c.row_name, rc.c.indent_level, rc.c.is_total_row, rc.c.formula)
            .where(
                rc.c.report_type == report_type,
                rc.c.applicable_standard == applicable_standard,
                rc.c.is_deleted == sa.false(),
            )
            .order_by(rc.c.row_number)
        )
        rc_result = await self.db.execute(rc_q)
        rc_rows = rc_result.fetchall()

        # 如果标准库没有数据，fallback 到旧逻辑（从映射表取行次）
        if not rc_rows:
            return await self._get_summary_from_mapping(project_id, year, report_type, company_code)

        # 2. 获取该项目的映射关系（标准科目 → 报表行次名称）
        mapping_q = (
            sa.select(rlm.c.standard_account_code, rlm.c.report_line_code, rlm.c.report_line_name)
            .where(
                rlm.c.project_id == project_id,
                rlm.c.report_type == report_type,
                rlm.c.is_deleted == sa.false(),
                rlm.c.is_confirmed == sa.true(),
            )
        )
        mapping_result = await self.db.execute(mapping_q)

        # 建立 report_config 行次名称 → row_code 的索引（用于名称匹配）
        rc_name_to_code: dict[str, str] = {}
        for rc_row in rc_rows:
            name = (rc_row.row_name or '').strip().replace('：', '').replace(':', '').replace(' ', '')
            if name:
                rc_name_to_code[name] = rc_row.row_code

        # 行次编码（report_config 的 row_code）→ 标准科目列表
        line_accounts: dict[str, list[str]] = {}
        all_account_codes: set[str] = set()
        for r in mapping_result.fetchall():
            # 通过映射表的 report_line_name 匹配 report_config 的 row_name
            mapping_name = (r.report_line_name or '').strip().replace('：', '').replace(':', '').replace(' ', '')
            matched_rc_code = rc_name_to_code.get(mapping_name)

            if not matched_rc_code:
                # 名称匹配不上，尝试模糊匹配（包含关系）
                for rc_name, rc_code in rc_name_to_code.items():
                    if mapping_name in rc_name or rc_name in mapping_name:
                        matched_rc_code = rc_code
                        break

            if matched_rc_code:
                if matched_rc_code not in line_accounts:
                    line_accounts[matched_rc_code] = []
                line_accounts[matched_rc_code].append(r.standard_account_code)
                all_account_codes.add(r.standard_account_code)

        # 3. 从 trial_balance 汇总未审数
        unadj_map: dict[str, Decimal] = {}
        if all_account_codes:
            tb_q = (
                sa.select(
                    tb.c.standard_account_code,
                    sa.func.coalesce(sa.func.sum(tb.c.unadjusted_amount), 0).label("unadj"),
                )
                .where(
                    tb.c.project_id == project_id,
                    tb.c.year == year,
                    tb.c.company_code == company_code,
                    tb.c.standard_account_code.in_(list(all_account_codes)),
                    tb.c.is_deleted == sa.false(),
                )
                .group_by(tb.c.standard_account_code)
            )
            tb_result = await self.db.execute(tb_q)
            for r in tb_result.fetchall():
                unadj_map[r.standard_account_code] = Decimal(str(r.unadj))

        # 4. 从 adjustments 汇总 AJE/RJE
        aje_dr_map: dict[str, Decimal] = {}
        aje_cr_map: dict[str, Decimal] = {}
        rcl_dr_map: dict[str, Decimal] = {}
        rcl_cr_map: dict[str, Decimal] = {}

        if all_account_codes:
            adj_q = (
                sa.select(
                    adj.c.account_code,
                    adj.c.adjustment_type,
                    sa.func.coalesce(sa.func.sum(adj.c.debit_amount), 0).label("total_dr"),
                    sa.func.coalesce(sa.func.sum(adj.c.credit_amount), 0).label("total_cr"),
                )
                .where(
                    adj.c.project_id == project_id,
                    adj.c.year == year,
                    adj.c.account_code.in_(list(all_account_codes)),
                    adj.c.is_deleted == sa.false(),
                )
                .group_by(adj.c.account_code, adj.c.adjustment_type)
            )
            adj_result = await self.db.execute(adj_q)
            for r in adj_result.fetchall():
                code = r.account_code
                dr = Decimal(str(r.total_dr))
                cr = Decimal(str(r.total_cr))
                adj_type = r.adjustment_type
                if adj_type in (AdjustmentType.aje.value, AdjustmentType.aje):
                    aje_dr_map[code] = aje_dr_map.get(code, Decimal("0")) + dr
                    aje_cr_map[code] = aje_cr_map.get(code, Decimal("0")) + cr
                else:
                    rcl_dr_map[code] = rcl_dr_map.get(code, Decimal("0")) + dr
                    rcl_cr_map[code] = rcl_cr_map.get(code, Decimal("0")) + cr

        # 5. 按标准行次模板构建结果
        # 使用统一公式引擎执行 report_config.formula
        from app.services.formula_engine import execute_formula, get_formula_account_codes, FormulaContext

        # 构建 trial_balance 科目→金额索引（供公式引擎用）
        all_tb_q = (
            sa.select(tb.c.standard_account_code, tb.c.unadjusted_amount)
            .where(
                tb.c.project_id == project_id,
                tb.c.year == year,
                tb.c.company_code == company_code,
                tb.c.is_deleted == sa.false(),
            )
        )
        all_tb_result = await self.db.execute(all_tb_q)
        tb_amount_map: dict[str, Decimal] = {}
        for r in all_tb_result.fetchall():
            if r.standard_account_code:
                tb_amount_map[r.standard_account_code] = (
                    tb_amount_map.get(r.standard_account_code, Decimal("0"))
                    + (r.unadjusted_amount or Decimal("0"))
                )

        result_rows = []
        row_values: dict[str, Decimal | float] = {}

        for rc_row in rc_rows:
            row_code = rc_row.row_code
            formula = rc_row.formula
            is_total = rc_row.is_total_row or False

            if formula:
                # 有公式：用统一公式引擎执行
                unadj = execute_formula(formula, tb_amount_map, row_values)
                # 公式涉及的科目的调整也要汇总
                aje_dr = Decimal("0")
                aje_cr = Decimal("0")
                rcl_dr = Decimal("0")
                rcl_cr = Decimal("0")
                formula_codes = get_formula_account_codes(formula)
                for code in formula_codes:
                    if code.startswith("__range__"):
                        # 范围编码：遍历匹配
                        range_str = code.replace("__range__", "")
                        parts = range_str.split("~")
                        if len(parts) == 2:
                            for ac in list(all_account_codes):
                                if parts[0] <= ac <= parts[1]:
                                    aje_dr += aje_dr_map.get(ac, Decimal("0"))
                                    aje_cr += aje_cr_map.get(ac, Decimal("0"))
                                    rcl_dr += rcl_dr_map.get(ac, Decimal("0"))
                                    rcl_cr += rcl_cr_map.get(ac, Decimal("0"))
                    else:
                        aje_dr += aje_dr_map.get(code, Decimal("0"))
                        aje_cr += aje_cr_map.get(code, Decimal("0"))
                        rcl_dr += rcl_dr_map.get(code, Decimal("0"))
                        rcl_cr += rcl_cr_map.get(code, Decimal("0"))
                audited = unadj + aje_dr - aje_cr + rcl_dr - rcl_cr
            elif is_total:
                # 合计行无公式：向前汇总子行（fallback）
                total_unadj = Decimal("0")
                total_aje_dr = Decimal("0")
                total_aje_cr = Decimal("0")
                total_rcl_dr = Decimal("0")
                total_rcl_cr = Decimal("0")
                total_audited = Decimal("0")
                for prev_row in result_rows[::-1]:
                    if prev_row.get("is_category") or prev_row.get("is_total"):
                        break
                    total_unadj += Decimal(str(prev_row.get("unadjusted") or 0))
                    total_aje_dr += Decimal(str(prev_row.get("aje_dr") or 0))
                    total_aje_cr += Decimal(str(prev_row.get("aje_cr") or 0))
                    total_rcl_dr += Decimal(str(prev_row.get("rcl_dr") or 0))
                    total_rcl_cr += Decimal(str(prev_row.get("rcl_cr") or 0))
                    total_audited += Decimal(str(prev_row.get("audited") or 0))
                unadj = total_unadj
                aje_dr = total_aje_dr
                aje_cr = total_aje_cr
                rcl_dr = total_rcl_dr
                rcl_cr = total_rcl_cr
                audited = total_audited
            else:
                # 无公式非合计：用映射关系填充
                accounts = line_accounts.get(row_code, [])
                unadj = sum(unadj_map.get(ac, Decimal("0")) for ac in accounts)
                aje_dr = sum(aje_dr_map.get(ac, Decimal("0")) for ac in accounts)
                aje_cr = sum(aje_cr_map.get(ac, Decimal("0")) for ac in accounts)
                rcl_dr = sum(rcl_dr_map.get(ac, Decimal("0")) for ac in accounts)
                rcl_cr = sum(rcl_cr_map.get(ac, Decimal("0")) for ac in accounts)
                audited = unadj + aje_dr - aje_cr + rcl_dr - rcl_cr

            row_values[row_code] = float(unadj)

            result_rows.append({
                "row_code": row_code,
                "row_name": rc_row.row_name,
                "indent": rc_row.indent_level or 0,
                "is_total": is_total,
                "is_category": ((rc_row.indent_level or 0) == 0 and not is_total),
                "unadjusted": float(unadj) if unadj != 0 else None,
                "aje_dr": float(aje_dr) if aje_dr != 0 else None,
                "aje_cr": float(aje_cr) if aje_cr != 0 else None,
                "rcl_dr": float(rcl_dr) if rcl_dr != 0 else None,
                "rcl_cr": float(rcl_cr) if rcl_cr != 0 else None,
                "audited": float(audited) if audited != 0 else None,
            })

        return result_rows

    async def _get_summary_from_mapping(
        self,
        project_id: UUID,
        year: int,
        report_type: str = "balance_sheet",
        company_code: str = "001",
    ) -> list[dict]:
        """Fallback：当 report_config 无数据时，从映射表取行次（旧逻辑）"""
        from app.models.audit_platform_models import (
            Adjustment,
            AdjustmentType,
            ReportLineMapping,
        )

        rlm = ReportLineMapping.__table__
        adj = Adjustment.__table__
        tb = TrialBalance.__table__

        report_lines_q = (
            sa.select(
                rlm.c.report_line_code,
                rlm.c.report_line_name,
                rlm.c.report_line_level,
                rlm.c.parent_line_code,
                rlm.c.standard_account_code,
            )
            .where(
                rlm.c.project_id == project_id,
                rlm.c.report_type == report_type,
                rlm.c.is_deleted == sa.false(),
                rlm.c.is_confirmed == sa.true(),
            )
            .order_by(rlm.c.report_line_code, rlm.c.standard_account_code)
        )
        rl_result = await self.db.execute(report_lines_q)
        rl_rows = rl_result.fetchall()

        if not rl_rows:
            return []

        all_account_codes = list({r.standard_account_code for r in rl_rows if r.standard_account_code})

        unadj_map: dict[str, Decimal] = {}
        if all_account_codes:
            tb_q = (
                sa.select(
                    tb.c.standard_account_code,
                    sa.func.coalesce(sa.func.sum(tb.c.unadjusted_amount), 0).label("unadj"),
                )
                .where(
                    tb.c.project_id == project_id,
                    tb.c.year == year,
                    tb.c.company_code == company_code,
                    tb.c.standard_account_code.in_(all_account_codes),
                    tb.c.is_deleted == sa.false(),
                )
                .group_by(tb.c.standard_account_code)
            )
            tb_result = await self.db.execute(tb_q)
            for r in tb_result.fetchall():
                unadj_map[r.standard_account_code] = Decimal(str(r.unadj))

        aje_dr_map: dict[str, Decimal] = {}
        aje_cr_map: dict[str, Decimal] = {}
        rcl_dr_map: dict[str, Decimal] = {}
        rcl_cr_map: dict[str, Decimal] = {}

        if all_account_codes:
            adj_q = (
                sa.select(
                    adj.c.account_code,
                    adj.c.adjustment_type,
                    sa.func.coalesce(sa.func.sum(adj.c.debit_amount), 0).label("total_dr"),
                    sa.func.coalesce(sa.func.sum(adj.c.credit_amount), 0).label("total_cr"),
                )
                .where(
                    adj.c.project_id == project_id,
                    adj.c.year == year,
                    adj.c.account_code.in_(all_account_codes),
                    adj.c.is_deleted == sa.false(),
                )
                .group_by(adj.c.account_code, adj.c.adjustment_type)
            )
            adj_result = await self.db.execute(adj_q)
            for r in adj_result.fetchall():
                code = r.account_code
                dr = Decimal(str(r.total_dr))
                cr = Decimal(str(r.total_cr))
                adj_type = r.adjustment_type
                if adj_type in (AdjustmentType.aje.value, AdjustmentType.aje):
                    aje_dr_map[code] = aje_dr_map.get(code, Decimal("0")) + dr
                    aje_cr_map[code] = aje_cr_map.get(code, Decimal("0")) + cr
                else:
                    rcl_dr_map[code] = rcl_dr_map.get(code, Decimal("0")) + dr
                    rcl_cr_map[code] = rcl_cr_map.get(code, Decimal("0")) + cr

        line_accounts: dict[str, list[str]] = {}
        line_meta: dict[str, dict] = {}
        for r in rl_rows:
            code = r.report_line_code
            if code not in line_accounts:
                line_accounts[code] = []
                line_meta[code] = {
                    "row_name": r.report_line_name,
                    "indent": max(0, (r.report_line_level or 1) - 1),
                    "is_total": False,
                    "parent_line_code": r.parent_line_code,
                }
            if r.standard_account_code:
                line_accounts[code].append(r.standard_account_code)

        seen_codes: set[str] = set()
        ordered_codes: list[str] = []
        for r in rl_rows:
            if r.report_line_code not in seen_codes:
                seen_codes.add(r.report_line_code)
                ordered_codes.append(r.report_line_code)

        result_rows = []
        for row_code in ordered_codes:
            accounts = line_accounts.get(row_code, [])
            meta = line_meta[row_code]

            unadj = sum(unadj_map.get(ac, Decimal("0")) for ac in accounts)
            aje_dr = sum(aje_dr_map.get(ac, Decimal("0")) for ac in accounts)
            aje_cr = sum(aje_cr_map.get(ac, Decimal("0")) for ac in accounts)
            rcl_dr = sum(rcl_dr_map.get(ac, Decimal("0")) for ac in accounts)
            rcl_cr = sum(rcl_cr_map.get(ac, Decimal("0")) for ac in accounts)
            audited = unadj + aje_dr - aje_cr + rcl_dr - rcl_cr

            result_rows.append({
                "row_code": row_code,
                "row_name": meta["row_name"],
                "indent": meta["indent"],
                "is_total": meta["is_total"],
                "is_category": (meta["indent"] == 0 and not meta["is_total"]),
                "unadjusted": float(unadj) if unadj != 0 else None,
                "aje_dr": float(aje_dr) if aje_dr != 0 else None,
                "aje_cr": float(aje_cr) if aje_cr != 0 else None,
                "rcl_dr": float(rcl_dr) if rcl_dr != 0 else None,
                "rcl_cr": float(rcl_cr) if rcl_cr != 0 else None,
                "audited": float(audited) if audited != 0 else None,
            })

        return result_rows

    # ------------------------------------------------------------------
    # 事件处理器（供 EventBus 调用）
    # ------------------------------------------------------------------
    async def on_adjustment_changed(self, payload: EventPayload) -> None:
        """调整分录 CRUD → 增量重算受影响科目的调整列+审定数

        Validates: Requirements 10.1, 10.2, 10.3
        """
        logger.info(
            "on_adjustment_changed: project=%s, accounts=%s",
            payload.project_id, payload.account_codes,
        )
        account_codes = payload.account_codes
        year = payload.year
        if not year:
            logger.warning("on_adjustment_changed: missing year, skipping")
            return

        await self.recalc_adjustments(
            payload.project_id, year, account_codes=account_codes,
        )
        await self.recalc_audited(
            payload.project_id, year, account_codes=account_codes,
        )
        await self.db.flush()

    async def on_mapping_changed(self, payload: EventPayload) -> None:
        """科目映射变更 → 重算旧+新标准科目的未审数

        Validates: Requirements 10.4
        """
        logger.info(
            "on_mapping_changed: project=%s, accounts=%s",
            payload.project_id, payload.account_codes,
        )
        account_codes = payload.account_codes
        year = payload.year
        if not year:
            logger.warning("on_mapping_changed: missing year, skipping")
            return

        await self.recalc_unadjusted(
            payload.project_id, year, account_codes=account_codes,
        )
        await self.recalc_audited(
            payload.project_id, year, account_codes=account_codes,
        )
        await self.db.flush()

    async def on_data_imported(self, payload: EventPayload) -> None:
        """数据导入完成 → 全量重算未审数

        Validates: Requirements 10.5
        """
        logger.info(
            "on_data_imported: project=%s",
            payload.project_id,
        )
        year = payload.year
        if not year:
            logger.warning("on_data_imported: missing year, skipping")
            return

        await self.full_recalc(payload.project_id, year)
        await self.db.flush()

    async def on_import_rolled_back(self, payload: EventPayload) -> None:
        """导入回滚 → 全量重算

        Validates: Requirements 10.5
        """
        logger.info(
            "on_import_rolled_back: project=%s",
            payload.project_id,
        )
        year = payload.year
        if not year:
            logger.warning("on_import_rolled_back: missing year, skipping")
            return

        await self.full_recalc(payload.project_id, year)
        await self.db.flush()
