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
from app.services.ledger_import.direction_resolver import resolve_account_direction

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

        # 叶子节点过滤：客户科目表是多级树（1122 父级 / 1122.01 子级），
        # 父级余额 = 子级之和。account_mapping 把每一级 original_account_code 都
        # 映射到标准科目，若汇总时父子全加会重复计算（父级被算两遍）→ 试算表翻倍、
        # 资产≠负债+权益。因此只汇总叶子节点（没有被映射子科目的最明细行），
        # 既消除父子双计，又保留二级明细（如坏账准备 1231-01/02/03）的备抵映射。
        child = bal.alias("tb_child")
        leaf_cond = ~sa.exists(
            sa.select(sa.literal(1))
            .select_from(child)
            .where(
                child.c.project_id == bal.c.project_id,
                child.c.year == bal.c.year,
                child.c.is_deleted == sa.false(),
                child.c.account_code != bal.c.account_code,
                child.c.account_code.like(bal.c.account_code.concat(".%")),
                # 子级须与父级同数据集才算其子科目（active dataset 已由 balance_filter 锁定 bal）
                sa.or_(
                    child.c.dataset_id == bal.c.dataset_id,
                    sa.and_(child.c.dataset_id.is_(None), bal.c.dataset_id.is_(None)),
                ),
            )
        )

        # 1. 汇总查询：客户余额 → 映射 → 标准科目（仅叶子节点）
        # 🔴 方向符号修复：tb_balance.closing_balance/opening_balance 在部分账套里存的是
        #    "无符号绝对值"(贷方也是正数)，方向在 closing_direction/opening_direction 里。
        #    若直接 SUM(closing_balance) 再对贷方类 abs()，同一父科目下"借方性质挂账"
        #    (如 其他应付款-应付利润，direction='debit') 会被同号累加而非冲减 → 负债/资产虚增、
        #    资产≠负债+权益。这里按方向归一到"借正贷负"有符号口径再求和：
        #      debit  → +ABS(balance)   credit → -ABS(balance)   方向缺失 → 原值(兼容已有符号存储)。
        #    下游 `if direction=='credit': closing=abs(closing)` 不变即自洽。
        signed_closing = sa.case(
            (bal.c.closing_direction == "credit", -sa.func.abs(bal.c.closing_balance)),
            (bal.c.closing_direction == "debit", sa.func.abs(bal.c.closing_balance)),
            else_=bal.c.closing_balance,
        )
        signed_opening = sa.case(
            (bal.c.opening_direction == "credit", -sa.func.abs(bal.c.opening_balance)),
            (bal.c.opening_direction == "debit", sa.func.abs(bal.c.opening_balance)),
            else_=bal.c.opening_balance,
        )

        # 🔴 映射口径根治（2026-07）：未映射叶子继承最近已映射父科目标准码。
        #    根因：account_mapping 由 auto_match 生成，常出现「父科目已映射、部分子科目漏映射」
        #    （如 1651 使用权资产→1641 已映射，但叶子 1651.02 使用权资产_房屋及建筑物 漏映射）。
        #    原实现用 INNER JOIN 精确匹配 original_account_code == account_code，漏映射叶子被
        #    静默丢弃 → 丢的资产≠丢的负债 → 报表资产≠负债+权益。
        #    修复：按「最长前缀匹配」解析每个叶子的标准码——叶子自身有映射用自身，否则回退到
        #    最近的已映射祖先（1651.02 → 祖先 1651 → 1641）。账户层级下子科目天然属于父科目
        #    同一标准科目，此继承会计正确；无任何已映射祖先的叶子仍返回 NULL（保持原丢弃行为）。
        mp_anc = AccountMapping.__table__.alias("mp_anc")

        def _resolved_std_subq():
            return (
                sa.select(mp_anc.c.standard_account_code)
                .where(
                    mp_anc.c.project_id == bal.c.project_id,
                    mp_anc.c.is_deleted == sa.false(),
                    sa.or_(
                        bal.c.account_code == mp_anc.c.original_account_code,
                        bal.c.account_code.like(mp_anc.c.original_account_code.concat(".%")),
                    ),
                )
                .order_by(sa.func.length(mp_anc.c.original_account_code).desc())
                .limit(1)
                .correlate(bal)
                .scalar_subquery()
            )

        agg_sub = (
            sa.select(
                _resolved_std_subq().label("std"),
                signed_closing.label("sc"),
                signed_opening.label("so"),
            )
            .select_from(bal)
            .where(balance_filter)
            .where(leaf_cond)
        ).subquery("agg_sub")

        agg_q = (
            sa.select(
                agg_sub.c.std.label("standard_account_code"),
                sa.func.coalesce(sa.func.sum(agg_sub.c.sc), 0).label("total_closing"),
                sa.func.coalesce(sa.func.sum(agg_sub.c.so), 0).label("total_opening"),
            )
            .where(agg_sub.c.std.isnot(None))
            .group_by(agg_sub.c.std)
        )

        if account_codes:
            agg_q = agg_q.where(agg_sub.c.std.in_(account_codes))

        result = await self.db.execute(agg_q)
        agg_rows = {r.standard_account_code: r for r in result.fetchall()}

        # 1b. 损益类科目额外汇总本期发生额（debit_amount - credit_amount）
        # 损益类期末余额通常为 0（已结转），审计需要看本期发生额
        # 同样只取叶子节点，避免父子科目发生额重复累加。
        period_sub = (
            sa.select(
                _resolved_std_subq().label("std"),
                bal.c.debit_amount.label("dr"),
                bal.c.credit_amount.label("cr"),
            )
            .select_from(bal)
            .where(balance_filter)
            .where(leaf_cond)
        ).subquery("period_sub")

        period_agg_q = (
            sa.select(
                period_sub.c.std.label("standard_account_code"),
                sa.func.coalesce(sa.func.sum(period_sub.c.dr), 0).label("total_debit"),
                sa.func.coalesce(sa.func.sum(period_sub.c.cr), 0).label("total_credit"),
            )
            .where(period_sub.c.std.isnot(None))
            .group_by(period_sub.c.std)
        )
        if account_codes:
            period_agg_q = period_agg_q.where(period_sub.c.std.in_(account_codes))

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

            # 损益类科目（5xxx/6xxx）：取单边发生额（不做借-贷，因为结转后两边相等）。
            # v2 约定（category_natural_positive）：按 direction_resolver 判方向后存自然正数。
            # v2 约定（category_natural_positive）：
            # - 资产负债权益类：从 tb_balance.closing_balance 取值(v1 借正贷负),贷方类取 abs 转正。
            # - 损益类(5xxx/6xxx)：closing_balance 通常=0(年末结转/原始余额表不含),
            #   须从 tb_ledger 取单边发生额(收入取贷方,费用取借方)。
            is_income_expense = code and code[0] in ('5', '6')
            if is_income_expense:
                period = period_rows.get(code)
                if period:
                    total_dr = Decimal(str(period.total_debit))
                    total_cr = Decimal(str(period.total_credit))
                    direction, _source = resolve_account_direction(code, name or "")
                    if direction == "credit":
                        # 收入类（贷方正常）：取贷方发生额，存自然正数
                        closing = total_cr
                    else:
                        # 费用/成本类（借方正常）：取借方发生额，存自然正数
                        closing = total_dr
                else:
                    # 无序时账发生额时 fallback 到 tb_balance.closing_balance abs
                    direction, _source = resolve_account_direction(code, name or "")
                    closing = abs(closing) if direction == "credit" else closing
                opening = Decimal("0")  # 损益类无期初余额
            else:
                # 资产负债权益类：tb_balance.closing_balance 是"借正贷负"原始口径，
                # 贷方类（负债/权益）需取绝对值转为 v2 自然正数。
                direction, _source = resolve_account_direction(code, name or "")
                if direction == "credit":
                    closing = abs(closing)
                    opening = abs(opening)

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
        """按 adjustment_type 分组汇总到 rje/aje 列（批量操作）。

        adj-formula-repair-and-approval-gate-wiring 任务 2.4:
        科目列改为 adjustment_entries.standard_account_code + JOIN adjustments
        （ADR-ADJ-001，与 adj_net / ADJ() / cross_check 同口径）。
        origin 排除保留 V124 防双计约定（exclude workpaper）。
        review_status 仅 approved（ADR-ADJ-003，与 adj_net DEFAULT_INCLUDE_STATUSES 同口径）。

        口径差异说明（ADR-ADJ-002）：
        - 本函数传 exclude_origins={"workpaper"}（TB 列参与审定数计算，排除防双计）
        - ADJ() / cross_check 传 exclude_origins=frozenset()（底稿呈现，不排除）
        两者差异是语义差异而非缺陷。
        """
        from app.models.audit_platform_models import AdjustmentEntry

        adj = Adjustment.__table__
        ae = AdjustmentEntry.__table__

        # ADR-ADJ-001: 统一走 adjustment_entries.standard_account_code + JOIN
        agg_q = (
            sa.select(
                ae.c.standard_account_code.label("account_code"),
                adj.c.adjustment_type,
                (sa.func.coalesce(sa.func.sum(ae.c.debit_amount), 0)
                 - sa.func.coalesce(sa.func.sum(ae.c.credit_amount), 0)).label("net"),
            )
            .select_from(ae.join(adj, ae.c.adjustment_id == adj.c.id))
            .where(
                adj.c.project_id == project_id,
                adj.c.year == year,
                adj.c.is_deleted == sa.false(),
                # ADR-ADJ-003: 只纳入已审批的分录（与 adj_net DEFAULT_INCLUDE_STATUSES 同口径）
                adj.c.review_status == "approved",
                # V124 / workpaper-adjustment-centralization Req4.2：
                # 排除 workpaper 来源——底稿调整已由审定表 writeback 体现于
                # audited_amount，若此处再计入 aje_adjustment 会双计（ADR-ADJ-002）。
                sa.or_(adj.c.origin.is_(None), adj.c.origin != "workpaper"),
            )
            .group_by(ae.c.standard_account_code, adj.c.adjustment_type)
        )

        if account_codes:
            agg_q = agg_q.where(ae.c.standard_account_code.in_(account_codes))

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
                # v2 约定（category_natural_positive）：调整净额 SUM(debit)-SUM(credit)
                # 是"借正贷负"，但 unadjusted_amount 已按科目自然方向存正数（Task 3.1）。
                # 对贷方正常类（负债/权益/收入），一笔贷记增加应使审定数增大，若直接相加
                # "借正贷负"净额会方向反掉（见 design 发现 5 / 风险 2）。因此把净额归一到
                # 科目自然方向：借方类用 (debit-credit)，贷方类取反 (credit-debit)，
                # 使 audited = unadjusted + rje + aje 在所有类别下加减方向都正确，
                # 且保持该不变式被下游（check_consistency / module_cell_resolver / qc_engine）复用。
                direction, _src = resolve_account_direction(code, row.account_name or "")
                sign = Decimal("-1") if direction == "credit" else Decimal("1")
                row.rje_adjustment = sign * vals["rje"]
                row.aje_adjustment = sign * vals["aje"]

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
        """audited = unadjusted + rje + aje

        v2 约定下 unadjusted/rje/aje 均已按科目自然方向归一为正数口径
        （rje/aje 在 recalc_adjustments 中已按方向归一），故直接相加即得审定数，
        无需在此再按方向取反。
        """
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
        # 调整额不再在本方法内查库（改委托 adj_net_batch），故不再需要
        # Adjustment / AdjustmentType —— 留着会让人以为这里还在自己聚合调整。
        from app.models.audit_platform_models import ReportLineMapping
        from app.models.report_models import ReportConfig

        rlm = ReportLineMapping.__table__
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

        # 2. 获取该项目的映射关系（标准科目 → 报表行次名称 + 聚合方向）
        mapping_q = (
            sa.select(
                rlm.c.standard_account_code,
                rlm.c.report_line_code,
                rlm.c.report_line_name,
                rlm.c.mapping_sign,
            )
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
        # 科目聚合符号：subtract（备抵科目）→ -1，否则 +1。供 line_accounts 分支按符号加减。
        account_sign: dict[str, Decimal] = {}
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
                account_sign[r.standard_account_code] = (
                    Decimal("-1") if (r.mapping_sign or "add") == "subtract" else Decimal("1")
                )

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
                # v2 约定（category_natural_positive）：trial_balance.unadjusted_amount
                # 已是按科目类别存储的自然正数（Task 3.1 改造），无需再按符号取反补偿。
                # 报表行次的方向由 ReportLineMapping 的归属（资产侧/负债侧）+ account_category 决定，
                # 而非靠金额符号判断 —— 移除旧约定下的"二次翻转"。
                unadj_map[r.standard_account_code] = Decimal(str(r.unadj))

        # 4. 从 adjustments 汇总 AJE/RJE
        #
        # spec tb-adjustment-column-formula-closure Phase 0：委托
        # adjustment_amount_source.adj_net_batch（口径矩阵第 4 行），**禁**在此自写聚合。
        #
        # 🔴 改造前本处自写 SQL 且三个过滤全缺，是产生错误数字的根因（B1/B2/B3）：
        #   B1 无 review_status 过滤 ⇒ draft 分录被计入，而 TB 持久化列只算 approved
        #   B2 无 origin 过滤       ⇒ workpaper 来源与审定表 writeback 双计（违 V124）
        #   B3 查主表 adjustments 的 account_code/debit_amount/credit_amount 遗留冗余列
        #      而非 adjustment_entries.standard_account_code（违 ADR-ADJ-001）；
        #      实测真库该三列全库 0 非零 ⇒ 取的是废弃列，科目错配
        # 同文件 recalc_adjustments 早已按三个 ADR 改造，本处是其未修的孪生体。
        #
        # 口径与 recalc_adjustments / trial_balance.aje_adjustment 列一致：
        # 仅 approved（ADR-ADJ-003）+ 排除 workpaper 防双计（ADR-ADJ-002 / V124）。
        from app.services.adjustment_amount_source import (
            DEFAULT_INCLUDE_STATUSES,
            adj_net_batch,
        )

        adj_data = await adj_net_batch(
            self.db,
            project_id=project_id,
            year=year,
            account_codes=all_account_codes,
            include_statuses=DEFAULT_INCLUDE_STATUSES,
            exclude_origins=frozenset({"workpaper"}),
        )

        def _adj(code: str, key: str) -> Decimal:
            """取某科目某项调整额；缺失按 0（adj_net_batch 只返回有数据的科目）。

            key ∈ {aje_net, aje_dr, aje_cr, rje_net, rje_dr, rje_cr}
            - `*_dr`/`*_cr` 是**原始**借贷合计（恒非负），供展示列
            - `*_net` 是按科目自然方向**归一后**净额，供审定数计算（ADR-ADJ-005）
            """
            return adj_data.get(code, {}).get(key, Decimal("0"))

        # 5. 按标准行次模板构建结果
        # 使用统一公式引擎执行 report_config.formula

        # 构建 trial_balance 科目→金额索引（供公式引擎用）
        # v2 约定（category_natural_positive）：trial_balance.unadjusted_amount 已是按科目类别
        # 存储的自然正数（Task 3.1 改造）。报表展示与公式取数统一为正数，
        # 无需再对贷方方向科目取反补偿 —— 移除中间环节的"二次翻转"。
        from app.services.formula_engine import (
            FormulaContext,
            execute as fe_execute,
            get_formula_account_codes,
        )

        # ── B7 修正：构造**完整**的 FormulaContext，而非 from_simple_map 的 3 键 ──
        #
        # 🔴 改造前用 `execute_formula(f, tb_amount_map, row_values)`，它内部走
        # `FormulaContext.from_simple_map`，只产 3 键（期末余额/审定数/未审数）。
        # 而 `COLUMN_ALIASES` 注册了 14 个列名 ⇒ 其余 11 个**恒 0**且只留 trace
        # 不报错。实测后果：利润表公式普遍写 `SUM_TB('6001~6099','本期发生额')`，
        # 于是 **income_statement 78 行未审数全空**。
        #
        # 预载逻辑收敛在伴生模块 `tb_formula_context`（9 键来源表、
        # 「审定数=未审数」的语义约束理由、借贷两键必须占位的原因都在那里）。
        # 本处**只负责传入取数范围与调整额查询**，禁在此另写一份预载。
        from app.services.tb_formula_context import build_tb_formula_data

        formula_ctx_base = await build_tb_formula_data(
            self.db,
            tb=tb,
            project_id=project_id,
            year=year,
            company_code=company_code,
            adj_lookup=_adj,
        )

        result_rows = []
        row_values: dict[str, Decimal | float] = {}

        for rc_row in rc_rows:
            row_code = rc_row.row_code
            formula = rc_row.formula
            is_total = rc_row.is_total_row or False

            if formula:
                # 有公式：用统一公式引擎执行（L1 内核，ctx 由上方 L2 预载）
                # row_cache 每行都在变（ROW/SUM_ROW 引用已算出的行），故每次新建
                # FormulaContext 但复用同一份 tb_data（只读，不拷贝）。
                _ctx = FormulaContext(
                    tb_data=formula_ctx_base,
                    row_cache={k: Decimal(str(v)) for k, v in row_values.items()},
                )
                unadj = fe_execute(formula, _ctx).value
                # 公式涉及的科目的调整也要汇总
                aje_dr = Decimal("0")
                aje_cr = Decimal("0")
                rcl_dr = Decimal("0")
                rcl_cr = Decimal("0")
                # 归一净额（供审定数）——与展示用的 dr/cr 是两个口径，见 ADR-ADJ-005
                aje_net = Decimal("0")
                rcl_net = Decimal("0")
                formula_codes = get_formula_account_codes(formula)
                for code in formula_codes:
                    if code.startswith("__range__"):
                        # 范围编码：遍历匹配
                        range_str = code.replace("__range__", "")
                        parts = range_str.split("~")
                        if len(parts) == 2:
                            for ac in list(all_account_codes):
                                if parts[0] <= ac <= parts[1]:
                                    aje_dr += _adj(ac, "aje_dr")
                                    aje_cr += _adj(ac, "aje_cr")
                                    rcl_dr += _adj(ac, "rje_dr")
                                    rcl_cr += _adj(ac, "rje_cr")
                                    aje_net += _adj(ac, "aje_net")
                                    rcl_net += _adj(ac, "rje_net")
                    else:
                        aje_dr += _adj(code, "aje_dr")
                        aje_cr += _adj(code, "aje_cr")
                        rcl_dr += _adj(code, "rje_dr")
                        rcl_cr += _adj(code, "rje_cr")
                        aje_net += _adj(code, "aje_net")
                        rcl_net += _adj(code, "rje_net")
                # 🔴 B4 修正：审定数用**归一后**净额相加，不用原始 dr-cr。
                # 改造前写的是 `unadj + aje_dr - aje_cr + rcl_dr - rcl_cr`，对贷方正常类
                # （负债/权益/收入）方向反掉 —— 同文件 recalc_adjustments L405-416 的注释
                # 明确警告过这一点并已据此归一，本处是其未修的孪生体。
                # Property 1 实测：等价性边界恰为科目方向（借方类等价、贷方类符号相反）。
                audited = unadj + aje_net + rcl_net

                # 合计行公式结果为 0 时 fallback 到向前汇总（seed 公式可能范围不完整）
                if is_total and unadj == 0:
                    fb_unadj = Decimal("0")
                    fb_audited = Decimal("0")
                    for prev_row in result_rows[::-1]:
                        if prev_row.get("is_category") or prev_row.get("is_total"):
                            break
                        fb_unadj += Decimal(str(prev_row.get("unadjusted") or 0))
                        fb_audited += Decimal(str(prev_row.get("audited") or 0))
                    if fb_unadj != 0:
                        unadj = fb_unadj
                        audited = fb_audited

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
                # 无公式非合计：用映射关系填充（按 account_sign 加减，备抵科目为减项）
                accounts = line_accounts.get(row_code, [])
                unadj = sum(
                    account_sign.get(ac, Decimal("1")) * unadj_map.get(ac, Decimal("0"))
                    for ac in accounts
                )
                # account_sign 是**映射维度**的加减号（备抵科目为减项），
                # 与 adj_net 内部的**科目方向**符号归一是两个正交维度，两者都要应用。
                aje_dr = sum(
                    (account_sign.get(ac, Decimal("1")) * _adj(ac, "aje_dr")
                     for ac in accounts),
                    Decimal("0"),
                )
                aje_cr = sum(
                    (account_sign.get(ac, Decimal("1")) * _adj(ac, "aje_cr")
                     for ac in accounts),
                    Decimal("0"),
                )
                rcl_dr = sum(
                    (account_sign.get(ac, Decimal("1")) * _adj(ac, "rje_dr")
                     for ac in accounts),
                    Decimal("0"),
                )
                rcl_cr = sum(
                    (account_sign.get(ac, Decimal("1")) * _adj(ac, "rje_cr")
                     for ac in accounts),
                    Decimal("0"),
                )
                aje_net = sum(
                    (account_sign.get(ac, Decimal("1")) * _adj(ac, "aje_net")
                     for ac in accounts),
                    Decimal("0"),
                )
                rcl_net = sum(
                    (account_sign.get(ac, Decimal("1")) * _adj(ac, "rje_net")
                     for ac in accounts),
                    Decimal("0"),
                )
                # 🔴 B4 修正：同上，审定数用归一净额
                audited = unadj + aje_net + rcl_net

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
        # 调整额改委托 adj_net_batch，不再需要 Adjustment / AdjustmentType
        from app.models.audit_platform_models import ReportLineMapping

        rlm = ReportLineMapping.__table__
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
                # v2 约定（category_natural_positive）：unadjusted_amount 已是自然正数，
                # 无需按符号取反补偿 —— 与主路径 get_summary_with_adjustments 保持一致。
                unadj_map[r.standard_account_code] = Decimal(str(r.unadj))

        # spec tb-adjustment-column-formula-closure Phase 0 Task 0.8：
        # 本 fallback 路径与主路径 get_summary_with_adjustments 是同型缺陷
        # （B1 无 status 过滤 / B2 无 origin 过滤 / B3 查主表遗留冗余列 /
        #  B4 审定数用未归一 dr-cr），必须一并收敛 —— 只修主路径会留下
        # 「report_config 有配置时数对、无配置降级后数错」的隐蔽不一致。
        from app.services.adjustment_amount_source import (
            DEFAULT_INCLUDE_STATUSES,
            adj_net_batch,
        )

        adj_data = await adj_net_batch(
            self.db,
            project_id=project_id,
            year=year,
            account_codes=all_account_codes,
            include_statuses=DEFAULT_INCLUDE_STATUSES,
            exclude_origins=frozenset({"workpaper"}),
        )

        def _adj(code: str, key: str) -> Decimal:
            """同主路径：`*_dr`/`*_cr` 原始借贷（展示），`*_net` 归一净额（计算）。"""
            return adj_data.get(code, {}).get(key, Decimal("0"))

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
            aje_dr = sum((_adj(ac, "aje_dr") for ac in accounts), Decimal("0"))
            aje_cr = sum((_adj(ac, "aje_cr") for ac in accounts), Decimal("0"))
            rcl_dr = sum((_adj(ac, "rje_dr") for ac in accounts), Decimal("0"))
            rcl_cr = sum((_adj(ac, "rje_cr") for ac in accounts), Decimal("0"))
            # 🔴 B4 修正：审定数用归一净额（同主路径），不用原始 dr-cr
            aje_net = sum((_adj(ac, "aje_net") for ac in accounts), Decimal("0"))
            rcl_net = sum((_adj(ac, "rje_net") for ac in accounts), Decimal("0"))
            audited = unadj + aje_net + rcl_net

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
