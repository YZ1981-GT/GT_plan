"""N4 税金及附加 — 专属渲染策略（损益类！取本期发生额）.

component_type = "n4-taxes-and-surcharges"
科目 6403 税金及附加 — 损益类借方科目，从 tb_ledger 取本期发生额（借方发生-贷方发生）。

**损益类取数逻辑**：从tb_ledger取发生额（debit_amount/credit_amount），NOT 期末余额！
净发生额 = 借方发生(费用增加) - 贷方发生(费用冲回/红冲)

6403税金及附加为借方科目：借方=费用增加（确认时借记6403）。
与H10资产处置损益、I6研发费用、N5所得税费用同款损益类借方取数逻辑（借-贷）。
与K10(6117贷方科目,贷-借)方向相反。

N税费循环损益类底稿（9 sheet/~110+公式，其中O2A原底稿标记skip）。
数据持久化在 checklist_responses 表，item_id 前缀为 "N4-*"。
O2A原底稿标记skip走OnlyOffice fallback。

Requirements: 1.6, 7.2
"""

from __future__ import annotations

import logging
import types
from typing import Any

import sqlalchemy as sa

from app.services.dataset_query import get_active_filter
from app.services.deferred_tax_shared import code_predicate, leaf_rows
from app.services.report_account_mapping import resolve_report_line_account_codes

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目：6403税金及附加（损益类/借方=费用增加，贷方=年末结转损益）
_N4_ACCOUNT_CODE = "6403"

# 报表行编码（**DB 只读实证**：`report_config` 四套准则一致
# `IS-003 税金及附加 = TB('6403','本期发生额')`）。
_N4_ROW_CODE = "IS-003"


async def _resolve_account_codes(ctx: RenderContext) -> list[str]:
    """按报表行 `IS-003` 规则映射解析取数科目集（fail-open 回退 `['6403']`）。"""
    try:
        codes = await resolve_report_line_account_codes(
            ctx.db, ctx.project_id, _N4_ROW_CODE, fallback=[_N4_ACCOUNT_CODE]
        )
        return [c for c in codes if str(c).strip()] or [_N4_ACCOUNT_CODE]
    except Exception as e:  # noqa: BLE001 — 映射解析失败按 fallback 处理
        logger.warning("N4 render: 报表行 %s 科目映射解析失败: %s", _N4_ROW_CODE, e)
        return [_N4_ACCOUNT_CODE]

N4_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "税金及附加审计程序表N4A", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "税金及附加审定表N4-1", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "税金及附加明细表N4-2", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "调整分录汇总N4-3", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "O2A原底稿", "component_type": "skip"},
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


async def _fetch_period_amount(
    ctx: RenderContext, codes: list[str]
) -> dict[str, Any]:
    """损益类本期发生额：`trial_balance` 优先 → `tb_balance.debit_amount` 叶子兜底。

    🔴 **不用 `tb_ledger` 的借−贷**：全年序时账含年末「结转损益」分录，该差恒为 0。
    """
    from app.models.audit_platform_models import TbBalance, TrialBalance

    # ① trial_balance（与报表 `TB('6403','本期发生额')` 同源，最权威）
    tb_filter = await get_active_filter(
        ctx.db, TrialBalance.__table__, ctx.project_id, ctx.year or 0
    )
    tb_rows = (
        await ctx.db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.unadjusted_amount,
            ).where(
                tb_filter,
                sa.or_(
                    *[code_predicate(TrialBalance.standard_account_code, c) for c in codes]
                ),
            )
        )
    ).fetchall()
    leaves = leaf_rows(
        [
            types.SimpleNamespace(
                account_code=r.standard_account_code,
                unadjusted_amount=r.unadjusted_amount,
            )
            for r in tb_rows
        ]
    )
    if leaves:
        amount = round(sum(_parse_num(r.unadjusted_amount) for r in leaves), 2)
        if amount:
            return {
                "unadjusted_debit": amount,
                "unadjusted_credit": 0.0,
                "audited_amount": amount,
                "source": "trial_balance",
            }

    # ② tb_balance 借方发生额（科目级优先 → 叶子聚合）
    bal_filter = await get_active_filter(
        ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
    )
    bal_rows = (
        await ctx.db.execute(
            sa.select(TbBalance.account_code, TbBalance.debit_amount).where(
                bal_filter,
                sa.or_(*[code_predicate(TbBalance.account_code, c) for c in codes]),
            )
        )
    ).fetchall()
    roots = {str(c).strip() for c in codes if "~" not in str(c)}
    exact = [r for r in bal_rows if (r.account_code or "").strip() in roots]
    picked = exact or leaf_rows(list(bal_rows))
    amount = round(sum(_parse_num(r.debit_amount) for r in picked), 2)
    return {
        "unadjusted_debit": amount,
        "unadjusted_credit": 0.0,
        "audited_amount": amount,
        "source": "tb_balance" if picked else "none",
    }


async def _fetch_tb_period_amount(
    ctx: RenderContext, codes: list[str] | None = None
) -> dict[str, Any]:
    """从 tb_ledger 取科目6403税金及附加本期发生额（损益类借方）.

    损益类科目取发生额（与N5/H10/I6/L8同款），不取期末余额。

    6403税金及附加为借方科目：
    - 借方发生 = 费用增加（确认时借记6403）
    - 贷方发生 = 费用冲回/红冲
    - 净发生额 = 借方 - 贷方（正数=净费用）
    - 审定数 = 净发生额（本期发生额）

    **关键区别**：N4用tb_ledger取数（非tb_balance），方向为借方科目(借-贷)。
    与N5(6801)、H10、I6方向一致（借-贷），与K10(6117贷方科目,贷-借)方向相反。
    """
    codes = [c for c in (codes or [_N4_ACCOUNT_CODE]) if str(c).strip()] or [
        _N4_ACCOUNT_CODE
    ]
    result: dict[str, Any] = {
        "account_code": _N4_ACCOUNT_CODE,
        "account_codes": list(codes),
        "account_name": "税金及附加",
        "direction": "debit",
        "unadjusted_debit": 0.0,
        "unadjusted_credit": 0.0,
        "audited_amount": 0.0,
        "prior_amount": 0.0,
        "source": "none",
    }

    # 🔴 取数口径修正（P0）：原实现 sum `tb_ledger` 的「Σ借 − Σ贷」——
    # 对损益类科目**结构性恒为 0**。活体实证（9 个项目的 6403 / 6801 全部如此）：
    # 全年序时账必然包含年末「结转损益」分录（贷记损益科目结转到本年利润），
    # 故借贷两侧金额恒相等，其差恒为 0。
    # 平台权威口径 = `trial_balance`（recalc 已按发生额写好，报表 `TB('6403','本期发生额')`
    # 读的也是它）：实测项目 a7fc75e5 的 trial_balance 6403 = 11,258,989.55
    # = tb_balance 6403 的 **debit_amount**（仅借方）。
    try:
        result.update(await _fetch_period_amount(ctx, codes))
    except Exception as e:  # noqa: BLE001
        logger.warning("N4 render: 损益类本期发生额取数失败: %s", e)

    # 补充：从 trial_balance 取上期数（如存在）
    try:
        prior_year = (ctx.year or 0) - 1
        if prior_year > 0:
            prior_result = await ctx.db.execute(
                sa.text("""
                    SELECT SUM(audited_amount) AS prior_audited
                    FROM trial_balance
                    WHERE project_id = :pid AND year = :year AND is_deleted = false
                      AND standard_account_code LIKE :code_prefix
                """),
                {
                    "pid": str(ctx.project_id),
                    "year": prior_year,
                    "code_prefix": f"{_N4_ACCOUNT_CODE}%",
                },
            )
            prior_row = prior_result.fetchone()
            if prior_row and prior_row.prior_audited is not None:
                result["prior_amount"] = _parse_num(prior_row.prior_audited)
    except Exception as e:  # noqa: BLE001
        logger.warning("N4 render: trial_balance 上期数查询失败: %s", e)

    return result


# ─── 审定表按税种预填（6403 子科目名 → 10 个税种行）────────────────────────────

# 🔴 必须与前端 `useN4Adjudication.DEFAULT_TAX_TYPES` **逐字同序**
# （前端注释明确：命名与顺序须与 useN4Detail / useN4CrossSheet(N2 勾稽按名匹配) / 附注
# 三处保持一致）→ 契约测试 `test_n4_four_table_extraction` 读前端源码交叉比对。
_N4_TAX_OTHER = "其他"
_N4_TAX_TYPES = [
    "消费税",
    "城市维护建设税",
    "教育费附加",
    "地方教育附加",
    "房产税",
    "城镇土地使用税",
    "车船税",
    "印花税",
    "资源税",
    _N4_TAX_OTHER,
]


def _classify_n4_subaccount(name: str | None) -> str:
    """6403 子科目名 → 税种行（无法识别 → 其他）。

    🔴 **按名称而非编码判据**：活体实测 `6403.xx` 的编码语义在客户间冲突
    （`6403.01` 在某客户是「印花税」；`6403.02` 既是「税金及附加_城市维护建设税」
    也是「车船税」）→ 编码不可作为税种判据，名称才可靠。

    判定顺序有意如此：`地方教育` 必须先于 `教育费附加`（后者是前者的子串）；
    `城市维护建设` 先于泛化匹配。
    """
    n = (name or "").strip()
    if not n:
        return _N4_TAX_OTHER
    if "消费税" in n:
        return "消费税"
    if any(k in n for k in ("城市维护建设", "城建税")):
        return "城市维护建设税"
    if "地方教育" in n:
        return "地方教育附加"
    if "教育费附加" in n or "教育附加" in n:
        return "教育费附加"
    if "房产税" in n:
        return "房产税"
    if "土地使用税" in n:
        return "城镇土地使用税"
    if "车船" in n:
        return "车船税"
    if "印花税" in n:
        return "印花税"
    if "资源税" in n:
        return "资源税"
    return _N4_TAX_OTHER


async def _build_adjudication_prefill(
    ctx: RenderContext, codes: list[str]
) -> dict[str, float]:
    """从 tb_balance 的 6403 **叶子**子科目按税种预填未审数（本期发生额）。

    只取 `debit_amount`（借方发生额）—— 损益类贷方是年末结转损益，借−贷恒为 0。
    只有父级科目（无子科目）→ 返回 ``{}``，由前端把总额落「其他」行并提示需人工分配。
    全零税种跳过；查询失败返回 ``{}`` 不阻塞渲染。
    """
    from app.models.audit_platform_models import TbBalance

    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
        )
        rows = (
            await ctx.db.execute(
                sa.select(
                    TbBalance.account_code,
                    TbBalance.account_name,
                    TbBalance.debit_amount,
                ).where(
                    active_filter,
                    sa.or_(*[code_predicate(TbBalance.account_code, c) for c in codes]),
                )
            )
        ).fetchall()
    except Exception as e:  # noqa: BLE001 — 预填失败按空处理，不阻塞渲染
        logger.warning("N4 render: 审定表预填 tb_balance 查询失败: %s", e)
        return {}

    roots = {str(c).strip() for c in codes if "~" not in str(c)}
    subs = leaf_rows([r for r in rows if (r.account_code or "").strip() not in roots])
    agg: dict[str, float] = {}
    for r in subs:
        tax = _classify_n4_subaccount(r.account_name)
        agg[tax] = agg.get(tax, 0.0) + _parse_num(r.debit_amount)
    return {k: round(v, 2) for k, v in agg.items() if abs(v) >= 0.005}


async def _load_checklist_responses(ctx: RenderContext) -> dict[str, dict]:
    """加载 checklist_responses 快照（N4- 前缀项）."""
    responses: dict[str, dict] = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark, wp_ref "
                "FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "N4-%"},
        )
        for row in result.fetchall():
            responses[row.item_id] = {
                "item_id": row.item_id,
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
                "wp_ref": row.wp_ref or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("N4 render: checklist_responses 查询失败 wp_id=%s: %s", ctx.wp_id, e)
    return responses


async def _load_project_context(ctx: RenderContext) -> dict[str, str]:
    """加载项目上下文."""
    project_ctx: dict[str, str] = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
            """),
            {"wp_id": str(ctx.wp_id)},
        )
        row = result.fetchone()
        if row:
            project_ctx["client_name"] = row.client_name or ""
            project_ctx["audit_year"] = str(row.audit_year) if row.audit_year else ""
            project_ctx["business_category"] = row.business_category or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("N4 render: project context 加载失败: %s", e)
    return project_ctx


# ─── 主渲染函数 ───────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict[str, Any] | None:
    """N4 税金及附加专属渲染策略：损益类取发生额（借方科目！借-贷）.

    核心特殊：
    1. **损益类取发生额**非余额（从tb_ledger取数！）
    2. **借方科目**：净发生额=借方-贷方（费用类！与N5/H10/I6同款）
    3. 各税种费用确认与N2应交税费计提对应（cross_wp_ref联动）
    4. N税费循环损益类底稿（8 sheets + 1 skip）

    返回轻量 html_data 给前端 GtN4TaxesAndSurcharges 组件 selfLoad 使用。
    实际数据拉取由前端子组件通过 checklist-responses API 完成。
    """
    # 0. 科目映射（report_config 单一真源，fail-open 回退硬编码科目）
    codes = await _resolve_account_codes(ctx)

    # 1. 获取TB数据（损益类！取本期发生额，trial_balance 优先）
    tb_values = await _fetch_tb_period_amount(ctx, codes)

    # 1b. 审定表按税种预填（6403 叶子子科目按**名称**归类；前端仅无持久化时套用）
    adjudication_prefill = await _build_adjudication_prefill(ctx, codes)

    # 2. 加载 checklist_responses 快照（N4- 前缀项）
    checklist_responses = await _load_checklist_responses(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "n4-taxes-and-surcharges",
        "account_code": _N4_ACCOUNT_CODE,
        "account_direction": "debit",
        "account_category": "expense",
        "data_source": "trial_balance_period_amount",
        "tb_values": tb_values,
        # 审定表按税种预填（`{税种: 本期发生额}`；空 dict = 无子科目，前端落「其他」行）
        "adjudication_prefill": adjudication_prefill,
        # 取数溯源：报表行规则映射解析出的科目集（供前端展示「取数来源」）
        "tb_source_codes": {
            "row_code": _N4_ROW_CODE,
            "codes": codes,
            "basis": "period",  # 损益类 → 本期发生额
        },
        "checklist_responses": checklist_responses,
        "project_context": project_context,
        "sheets": N4_SHEETS,
        "meta": {
            "sheet_count": 8,
            "wp_code": "N4",
            "special_rules": {
                "income_statement": True,
                "account_direction": "debit",
                "net_formula": "借方发生-贷方发生",
                "source_table": "tb_ledger",
                "n2_cross_verify": True,
                "a_income_statement_link": True,
            },
        },
    }
