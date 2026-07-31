"""N5 所得税费用 — 专属渲染策略.

component_type = "n5-income-tax-expense"

N5 前端组件 GtN5IncomeTaxExpense 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/当期计算/纳税调整/税收优惠/研发加计/递延核对等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot + TB数据），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 N5 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目6801所得税费用（**损益类科目**）：取本期发生额（从tb_ledger），而非期末余额
N税费循环最复杂底稿（15 sheet/~95+公式，含82行当期计算表+107行纳税调整大表）。
数据持久化在 checklist_responses 表，item_id 前缀为 "N5-*"。
N3A原底稿标记skip走OnlyOffice fallback。

Requirements: 1.1, 1.6, 1.7, 1.8, 1.9, 1.11
"""

from __future__ import annotations

import logging
import types
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbLedger  # noqa: F401 — 保留供 _code_predicate 绑定列
from app.services.dataset_query import get_active_filter
from app.services.deferred_tax_shared import code_predicate, leaf_rows
from app.services.report_account_mapping import resolve_report_line_account_codes

from ._context import RenderContext

logger = logging.getLogger(__name__)

_N5_ACCOUNT_CODE = "6801"
_ADJUDICATED_ITEM_ID = "N5-1-adjudicated-amount"

# 报表行编码（**DB 只读实证**：`report_config` 四套准则一致
# `IS-023 减：所得税费用 = TB('6801','本期发生额')`）。
# 🔴 损益类取**本期发生额**，不取期末余额（平台铁律）。
_N5_ROW_CODE = "IS-023"


def _code_predicate(code: str):
    """本模块查 `tb_ledger`，故绑定其 `account_code` 列。"""
    return code_predicate(TbLedger.account_code, code)


async def _resolve_account_codes(ctx: RenderContext) -> list[str]:
    """按报表行 `IS-023` 规则映射解析取数科目集（fail-open 回退 `['6801']`）。"""
    try:
        codes = await resolve_report_line_account_codes(
            ctx.db, ctx.project_id, _N5_ROW_CODE, fallback=[_N5_ACCOUNT_CODE]
        )
        return [c for c in codes if str(c).strip()] or [_N5_ACCOUNT_CODE]
    except Exception as e:  # noqa: BLE001 — 映射解析失败按 fallback 处理
        logger.warning("N5 render: 报表行 %s 科目映射解析失败: %s", _N5_ROW_CODE, e)
        return [_N5_ACCOUNT_CODE]

N5_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "所得税审计程序表N5A", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "所得税费用审定表N5-1", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "所得税费用明细表N5-2", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "调整分录汇总N5-3", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "当期所得税费用计算表N5-4", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "纳税调整明细表N5-5", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "税收优惠明细表N5-6", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "加计扣除研发费用情况明细表N5-6-1", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "高新技术企业认定条件检查表N5-6-2", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "财产损失明细表N5-7", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "递延所得税费用核对表N5-8", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "附注披露信息（上市）", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "N3A原底稿", "component_type": "n5-income-tax-expense"},
]


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────


def _parse_num(v: Any) -> float:
    """安全解析数值，None/空/NaN→0.0."""
    if v is None or v == "":
        return 0.0
    try:
        f = float(v)
        return 0.0 if f != f else f  # NaN→0.0
    except (ValueError, TypeError):
        return 0.0


# ─── TB 取数（损益类！本期发生额，从 tb_ledger）──────────────────────────────


async def _fetch_tb_data(
    ctx: RenderContext, codes: list[str] | None = None
) -> dict[str, Any]:
    """从 tb_ledger 取所得税费用本期发生额（损益类借方）.

    损益类科目取**发生额**（与 N4/H10/I6/L8 同款），不取期末余额 ——
    `report_config` 实证 `IS-023 减：所得税费用 = TB('6801','本期发生额')`。

    Args:
        codes: 科目集（来自报表行 `IS-023` 规则映射）；缺省回退 `['6801']`。
    """
    codes = [c for c in (codes or [_N5_ACCOUNT_CODE]) if str(c).strip()] or [
        _N5_ACCOUNT_CODE
    ]
    result: dict[str, Any] = {
        "account_code": _N5_ACCOUNT_CODE,
        "account_codes": list(codes),
        "account_name": "所得税费用",
        "direction": "debit",
        "debit_occur": 0,
        "credit_occur": 0,
        "period_amount": 0,
        "source": "none",
    }
    try:
        # 🔴 P0 修复：原写 `get_active_filter(ctx.project_id)` —— 真实签名是
        # `async def get_active_filter(db, table, project_id, year, *, ...)`
        # → 单参调用必然 TypeError，被下方 `except Exception` 吞成 warning
        # → 本函数**从上线起恒返回全 0**，而 28 个 N5 测试全绿（它们从不真实调用本函数）。
        #
        # 🔴 P0 之二（取数口径）：原实现 sum `tb_ledger` 的「Σ借 − Σ贷」——
        # 对损益类科目**结构性恒为 0**。活体实证（项目 a7fc75e5 / 6801.01）：
        #   凭证 0409「计提当期所得税」→ 借方 110,445.40
        #   凭证 0410「结转损益」      → 贷方 110,445.40
        # 全年序时账必然包含年末结转损益分录，故借贷两侧金额恒相等。
        # 平台权威口径 = `trial_balance`（recalc 已按发生额写好，`TB('6801','本期发生额')`
        # 也是读它）：实测 trial_balance 6801 = 21,151,383.26
        # = tb_balance 6801 的 **debit_amount**（仅借方）
        # = 叶子 6801.01 24,891,157.62 + 6801.02 (−3,739,774.36)，逐分相等。
        result.update(await _fetch_period_amount(ctx, codes))
    except Exception as e:  # noqa: BLE001
        logger.warning("N5 render: TB 取数失败: %s", e)
    return result


async def _fetch_period_amount(
    ctx: RenderContext, codes: list[str]
) -> dict[str, Any]:
    """损益类本期发生额：`trial_balance` 优先 → `tb_balance.debit_amount` 叶子兜底。

    🔴 **不用 `tb_ledger` 的借−贷**：全年序时账含年末「结转损益」分录，
    该差恒为 0（见调用方注释的活体实证）。
    """
    from app.models.audit_platform_models import TbBalance, TrialBalance

    # ① trial_balance（与报表 `TB('6801','本期发生额')` 同源，最权威）
    tb_filter = await get_active_filter(
        ctx.db, TrialBalance.__table__, ctx.project_id, ctx.year or 0
    )
    tb_rows = (
        await ctx.db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.unadjusted_amount,
                TrialBalance.audited_amount,
            ).where(
                tb_filter,
                sa.or_(
                    *[
                        code_predicate(TrialBalance.standard_account_code, c)
                        for c in codes
                    ]
                ),
            )
        )
    ).fetchall()
    leaves = leaf_rows(
        [
            types.SimpleNamespace(
                account_code=r.standard_account_code,
                unadjusted_amount=r.unadjusted_amount,
                audited_amount=r.audited_amount,
            )
            for r in tb_rows
        ]
    )
    if leaves:
        amount = sum(_parse_num(r.unadjusted_amount) for r in leaves)
        if amount:
            return {
                "debit_occur": round(amount, 2),
                "credit_occur": 0.0,
                "period_amount": round(amount, 2),
                "source": "trial_balance",
            }

    # ② tb_balance 借方发生额叶子聚合（trial_balance 未 recalc 时）
    bal_filter = await get_active_filter(
        ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
    )
    bal_rows = (
        await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.debit_amount,
            ).where(
                bal_filter,
                sa.or_(*[code_predicate(TbBalance.account_code, c) for c in codes]),
            )
        )
    ).fetchall()
    roots = {str(c).strip() for c in codes if "~" not in str(c)}
    exact = [r for r in bal_rows if (r.account_code or "").strip() in roots]
    picked = exact or leaf_rows(list(bal_rows))
    amount = sum(_parse_num(r.debit_amount) for r in picked)
    return {
        "debit_occur": round(amount, 2),
        "credit_occur": 0.0,
        "period_amount": round(amount, 2),
        "source": "tb_balance" if picked else "none",
    }


# ─── 主渲染函数 ───────────────────────────────────────────────────────────────


async def _build_adjudication_prefill(
    ctx: RenderContext, codes: list[str] | None = None
) -> dict[str, Any] | None:
    """从 tb_balance 子科目预填审定表 N5-1（当期 / 递延两行）.

    科目 6801 所得税费用为损益类借方科目 → 取**发生额**（借−贷）。
    活体实测子科目 `6801.01 当期所得税费用` / `6801.02 递延所得税费用` 语义清晰且稳定，
    故按「编码前缀 + 名称关键字」双判据归类。仅无持久化时由前端注入。
    """
    from app.models.audit_platform_models import TbBalance

    codes = [c for c in (codes or [_N5_ACCOUNT_CODE]) if str(c).strip()] or [
        _N5_ACCOUNT_CODE
    ]
    try:
        # 🔴 P0 修复：原写 `_get_af(ctx.project_id)` 单参调用 → TypeError 被 except 吞
        # → 本函数**从上线起恒返回 None**，前端 provide/inject 链路虽完整但永远拿不到数据。
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
        )
        stmt = (
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                sa.func.coalesce(TbBalance.debit_amount, 0).label("debit_amount"),
                sa.func.coalesce(TbBalance.credit_amount, 0).label("credit_amount"),
            )
            .where(
                active_filter,
                sa.or_(*[code_predicate(TbBalance.account_code, c) for c in codes]),
            )
            .order_by(TbBalance.account_code)
        )
        rows = (await ctx.db.execute(stmt)).fetchall()
        if not rows:
            return None

        current_period = 0.0
        deferred_period = 0.0
        total_period = 0.0

        roots = {str(c).strip() for c in codes if "~" not in str(c)}
        # 父级科目行单独留作总额；子科目只取**叶子**防与中间级双算
        parent_rows = [r for r in rows if (r.account_code or "").strip() in roots]
        sub_rows = leaf_rows([r for r in rows if (r.account_code or "").strip() not in roots])

        # 🔴 只取 `debit_amount`（借方发生额），**不做 借−贷**：
        # 损益类科目的贷方是年末「结转损益」，借−贷恒为 0（活体实证见 _fetch_tb_data 注释）。
        # 负数借方（如 6801.02 递延 −3,739,774.36）语义即"贷方性质"，直取可保留符号，
        # 且叶子之和 == 父级 == trial_balance，逐分可验。
        for r in parent_rows:
            total_period += _parse_num(r.debit_amount)

        for r in sub_rows:
            code = (r.account_code or "").strip()
            name = r.account_name or ""
            period = _parse_num(r.debit_amount)
            if (
                "递延" in name
                or code.startswith(f"{_N5_ACCOUNT_CODE}.02")
                or code.startswith(f"{_N5_ACCOUNT_CODE}02")
            ):
                deferred_period += period
            else:
                current_period += period

        if current_period == 0 and deferred_period == 0 and total_period != 0:
            current_period = total_period

        return {
            "current": {"key": "current", "category": "一、当期所得税费用", "periodAmount": round(current_period, 2), "unadjusted": round(current_period, 2), "aje": 0, "rje": 0, "audited": round(current_period, 2), "priorPeriod": 0, "isTotal": False},
            "deferred": {"key": "deferred", "category": "二、递延所得税费用", "periodAmount": round(deferred_period, 2), "unadjusted": round(deferred_period, 2), "aje": 0, "rje": 0, "audited": round(deferred_period, 2), "priorPeriod": 0, "isTotal": False},
            "total_period": round(total_period if total_period != 0 else current_period + deferred_period, 2),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("N5 render: adjudication prefill failed: %s", e)
        return None


async def render(ctx: RenderContext) -> dict[str, Any]:
    """N5 所得税费用专属渲染策略.

    轻量返回：project_context + responses_snapshot + TB数据。
    前端 GtN5IncomeTaxExpense 为自加载组件（各子组件独立拉取 checklist_responses）。
    """
    # ─── 读取 checklist_responses 快照 ─────────────────────────────────
    responses_snapshot: dict[str, Any] = {}
    adjudicated_amount: float | None = None
    try:
        rows = (
            await ctx.db.execute(
                sa.text(
                    "SELECT item_id, conclusion, remark "
                    "FROM checklist_responses "
                    "WHERE wp_id = :wid"
                ),
                {"wid": str(ctx.wp_id)},
            )
        ).fetchall()
        for r in rows:
            responses_snapshot[r.item_id] = {
                "item_id": r.item_id,
                "conclusion": r.conclusion,
                "remark": r.remark,
            }
        # 提取审定数
        if _ADJUDICATED_ITEM_ID in responses_snapshot:
            raw_adj = responses_snapshot[_ADJUDICATED_ITEM_ID].get("conclusion")
            if raw_adj is not None:
                adjudicated_amount = _parse_num(raw_adj)
    except Exception as e:  # noqa: BLE001
        logger.warning("N5 render: checklist_responses 查询失败: %s", e)

    # ─── 项目上下文 ────────────────────────────────────────────────────
    project_context: dict[str, str] = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
    }
    try:
        proj_row = (
            await ctx.db.execute(
                sa.text(
                    "SELECT client_name, audit_year, business_category "
                    "FROM projects WHERE id = :pid"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = (
                proj_row.business_category or ctx.business_category or ""
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("N5 render: project context 查询失败: %s", e)

    # ─── 科目映射（report_config 单一真源，fail-open 回退硬编码科目）──────────
    codes = await _resolve_account_codes(ctx)

    # ─── TB 取数（科目6801所得税费用，损益类，本期发生额！）────────────────
    tb = await _fetch_tb_data(ctx, codes)

    # ─── 审定表预填（仅无已保存数据时） ─────────────────────────────────
    adjudication_prefill: dict[str, Any] | None = None
    if "N5-1-current-row" not in responses_snapshot:
        adjudication_prefill = await _build_adjudication_prefill(ctx, codes)

    return {
        "account_code": _N5_ACCOUNT_CODE,
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        # TB 发生额数据（科目6801，借方/损益类）
        "trial_balance": tb,
        # 取数溯源：报表行规则映射解析出的科目集（供前端展示「取数来源」）
        "tb_source_codes": {
            "row_code": _N5_ROW_CODE,
            "codes": codes,
            "basis": "period",  # 损益类 → 本期发生额
        },
        # 损益类公式方向元数据
        "formula_direction": {
            "account_code": "6801",
            "account_name": "所得税费用",
            "direction": "debit",  # 借方/损益类！
            "period_amount_formula": "debit_occur - credit_occur",
            "note": (
                "损益类借方科目：所得税费用增加在借方（确认时借记6801），"
                "取本期发生额（从tb_ledger），而非期末余额。"
                "与N4税金及附加、H10资产处置损益、I6研发费用同款。"
                "所得税费用=当期所得税费用+递延所得税费用。"
            ),
        },
        # N5 特有元数据
        "n5_metadata": {
            "engine": "income_tax_expense",
            "formula": "income_tax_expense = current_tax + deferred_tax",
            "sub_formulas": {
                "taxable_income": "accounting_profit + add_back - deduction",
                "current_tax": "taxable_income × tax_rate",
                "deferred_tax": "liability_increase - asset_increase",
                "rd_super_deduction": "rd_expense × super_rate",
            },
            "cross_wp_links": ["N1", "N3", "N4", "I6", "I2", "A"],
            "skip_sheets": ["N3A"],
        },
        # sheet 列表元数据
        "sheets": N5_SHEETS,
        "component_type": "n5-income-tax-expense",
        "adjudication_prefill": adjudication_prefill,
    }
