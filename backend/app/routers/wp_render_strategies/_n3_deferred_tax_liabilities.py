"""N3 递延所得税负债 — 专属渲染策略.

component_type = "n3-deferred-tax-liabilities"

N3 前端组件 GtN3DeferredTaxLiabilities 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/调整/附注等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 N3 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目2901递延所得税负债（**贷方/负债类科目**）：期末=期初+贷方-借方
N税费循环中的负债类科目。应纳税暂时性差异×适用税率=递延所得税负债。
数据持久化在 checklist_responses 表，item_id 前缀为 "N3-*"。

Requirements: 1.6
"""

from __future__ import annotations

import json
import logging
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.deferred_tax_shared import (
    aggregate_by_slot,
    classify_liability_subaccount,
    code_predicate,
    leaf_rows,
)
from app.services.report_account_mapping import resolve_report_line_account_codes

from ._context import RenderContext

logger = logging.getLogger(__name__)

_N3_ACCOUNT_CODE = "2901"
# 报表行编码（**DB 只读实证**：`report_config` 四套准则一致
# `BS-067 递延所得税负债 = TB('2901','期末余额')`）。
_N3_ROW_CODE = "BS-067"
_ADJUDICATED_ITEM_ID = "N3-1-adjudicated-amount"
_ADJ_ROWS_ITEM_ID = "N3-1-adjudication-rows"
_TB_PREFILL_ITEM_ID = "N3-1-tb-prefill"

# 🔴 **不含任何披露 sheet**：N3 源模板（`backend/wp_templates/N/N3 递延所得税负债.xlsx`）
# 只有 底稿目录 / N3A / N3-1 / N3-2 / N3-3 / GT_Custom，`workpaper_sheet_classification`
# 里 wp_code=N3 亦 0 条附注 sheet。递延所得税负债的附注披露与 **N1 共节**
# （五、30 / 八、31，N1 表(1) 已含负债段）。原先这里列着「附注披露信息」条目 +
# 宿主 `isHtmlSheet` 认「附注」→ 该 sheet 一旦出现即渲染空白 Tab（inert 残留，已清）。
# 守卫：`test_n3_four_table_extraction.py` + 前端 `disclosureAutoSyncCoverage.spec.ts`
# 的 `CYCLES_WITHOUT_DISCLOSURE.N3`。
N3_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "n3-deferred-tax-liabilities"},
    {"sheet_name": "递延所得税负债审计程序表的N3A", "component_type": "n3-deferred-tax-liabilities"},
    {"sheet_name": "递延所得税负债审定表N3-1", "component_type": "n3-deferred-tax-liabilities"},
    {"sheet_name": "递延所得税负债明细表N3-2", "component_type": "n3-deferred-tax-liabilities"},
    {"sheet_name": "调整分录汇总N3-3", "component_type": "n3-deferred-tax-liabilities"},
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


# ─── TB 取数（负债类！期末余额）──────────────────────────────────────────────


async def _resolve_account_codes(ctx: RenderContext) -> list[str]:
    """按报表行 `BS-067` 规则映射解析取数科目集（fail-open 回退 `['2901']`）。"""
    try:
        codes = await resolve_report_line_account_codes(
            ctx.db, ctx.project_id, _N3_ROW_CODE, fallback=[_N3_ACCOUNT_CODE]
        )
        return [c for c in codes if str(c).strip()] or [_N3_ACCOUNT_CODE]
    except Exception as e:  # noqa: BLE001 — 映射解析失败按 fallback 处理
        logger.warning("N3 render: 报表行 %s 科目映射解析失败: %s", _N3_ROW_CODE, e)
        return [_N3_ACCOUNT_CODE]


async def _fetch_tb_data(
    ctx: RenderContext, codes: list[str] | None = None
) -> dict[str, Any]:
    """从 tb_balance 取递延所得税负债余额（负债类贷方，`abs()` 归一）。

    🔴 原实现只查 `account_code == '2901'` 精确单行 + `.limit(1)`：
    客户按子科目挂账（活体实测 `2901.01/.02/.03` 普遍存在）时**恒返回 0**。
    改为「科目级精确行优先 → 无则叶子子科目聚合」，与 N1 同款。
    """

    codes = [c for c in (codes or [_N3_ACCOUNT_CODE]) if str(c).strip()] or [
        _N3_ACCOUNT_CODE
    ]
    result: dict[str, Any] = {
        "account_code": _N3_ACCOUNT_CODE,
        "account_codes": list(codes),
        "account_name": "递延所得税负债",
        "direction": "credit",
        "begin_balance": 0,
        "debit_amount": 0,
        "credit_amount": 0,
        "end_balance": 0,
    }
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
        )
        all_rows = (
            await ctx.db.execute(
                sa.select(
                    TbBalance.account_code,
                    TbBalance.opening_balance,
                    TbBalance.debit_amount,
                    TbBalance.credit_amount,
                    TbBalance.closing_balance,
                ).where(
                    active_filter,
                    sa.or_(*[code_predicate(TbBalance.account_code, c) for c in codes]),
                )
            )
        ).fetchall()

        roots = {str(c).strip() for c in codes if "~" not in str(c)}
        # ① 科目级精确行（父级即总额，不与子科目双算）
        rows = [r for r in all_rows if (r.account_code or "").strip() in roots]
        # ② 无科目级行（客户按子科目挂账）→ 叶子聚合
        if not rows:
            rows = leaf_rows(list(all_rows))

        for row in rows:
            # 负债类：两种符号约定并存（活体实测 2901 期末既有 -233512.19 也有 200530.32）
            result["begin_balance"] += abs(_parse_num(row.opening_balance))
            result["debit_amount"] += abs(_parse_num(row.debit_amount))
            result["credit_amount"] += abs(_parse_num(row.credit_amount))
            result["end_balance"] += abs(_parse_num(row.closing_balance))
        for k in ("begin_balance", "debit_amount", "credit_amount", "end_balance"):
            result[k] = round(result[k], 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("N3 render: TB 取数失败: %s", e)
    return result


async def _build_adjudication_prefill(
    ctx: RenderContext, codes: list[str] | None = None
) -> dict[str, dict[str, float]]:
    """从 tb_balance 递延所得税负债 **叶子**子科目按语义槽预填审定表期初/期末。

    复用 N1 已实测的 2901 五语义槽分类（共享模块 `deferred_tax_shared`），
    **不新造第 3 套**。原实现把 TB 数据全塞进「其他」一行，分类信息全丢。

    只有父级科目（无子科目）→ 返回 ``{}``（不虚构分类，`trial_balance` 给总额做反向校验）。
    """
    codes = [c for c in (codes or [_N3_ACCOUNT_CODE]) if str(c).strip()] or [
        _N3_ACCOUNT_CODE
    ]
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
        )
        rows = (
            await ctx.db.execute(
                sa.select(
                    TbBalance.account_code,
                    TbBalance.account_name,
                    TbBalance.opening_balance,
                    TbBalance.closing_balance,
                ).where(
                    active_filter,
                    sa.or_(*[code_predicate(TbBalance.account_code, c) for c in codes]),
                )
            )
        ).fetchall()
    except Exception as e:  # noqa: BLE001 — 预填失败按空处理，不阻塞渲染
        logger.warning("N3 render: 审定表预填 tb_balance 查询失败: %s", e)
        return {}

    roots = {str(c).strip() for c in codes if "~" not in str(c)}
    subs = leaf_rows([r for r in rows if (r.account_code or "").strip() not in roots])
    return aggregate_by_slot(subs, classify_liability_subaccount, absolute=True)


# ─── 主渲染函数 ───────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict[str, Any]:
    """N3 递延所得税负债专属渲染策略.

    轻量返回：project_context + responses_snapshot + TB数据。
    前端 GtN3DeferredTaxLiabilities 为自加载组件（各子组件独立拉取 checklist_responses）。
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
        logger.warning("N3 render: checklist_responses 查询失败: %s", e)

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
        logger.warning("N3 render: project context 查询失败: %s", e)

    # ─── 科目映射（report_config 单一真源，fail-open 回退硬编码科目）──────────
    codes = await _resolve_account_codes(ctx)

    # ─── TB 取数（科目2901递延所得税负债，贷方/负债类）────────────────────
    tb = await _fetch_tb_data(ctx, codes)

    # ─── 审定表分类预填（2901 叶子 → 五语义槽，复用 N1 已实测分类）──────────
    adjudication_prefill = await _build_adjudication_prefill(ctx, codes)

    # ─── 审定表 TB 预填种子（仅当无持久化审定表行时注入）──────────────────
    # 保留既有形态（前端 `useN3Adjudication` 读 `N3-1-tb-prefill`）以零回归；
    # 分类信息由新增的 `adjudication_prefill` 顶层键承载。
    if _ADJ_ROWS_ITEM_ID not in responses_snapshot:
        responses_snapshot[_TB_PREFILL_ITEM_ID] = {
            "item_id": _TB_PREFILL_ITEM_ID,
            "conclusion": json.dumps(
                {
                    "beginning": tb.get("begin_balance", 0) or 0,
                    "creditAmount": tb.get("credit_amount", 0) or 0,
                    "debitAmount": tb.get("debit_amount", 0) or 0,
                    "unadjusted": tb.get("end_balance", 0) or 0,
                }
            ),
            "remark": None,
        }

    return {
        "account_code": _N3_ACCOUNT_CODE,
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        # TB 余额数据（科目2901，贷方/负债类，已 abs() 归一）
        "trial_balance": tb,
        # 审定表按语义槽预填（`{槽: {opening, closing}}`；空 dict = 无子科目）
        "adjudication_prefill": adjudication_prefill,
        # 取数溯源：报表行规则映射解析出的科目集（供前端展示「取数来源」）
        "tb_source_codes": {
            "row_code": _N3_ROW_CODE,
            "codes": codes,
            "basis": "balance",  # 余额类 → 期末余额
        },
        # 负债类公式方向元数据
        "formula_direction": {
            "account_code": "2901",
            "account_name": "递延所得税负债",
            "direction": "credit",  # 贷方/负债类！
            "end_balance_formula": "begin + credit - debit",  # 期末=期初+贷方-借方
            "note": (
                "负债类贷方科目：递延所得税负债增加在贷方（确认时贷记2901），"
                "转回时借方减少。核心引擎：递延所得税负债=应纳税暂时性差异×适用税率。"
                "与N1递延所得税资产对应（同源暂时性差异分列）。"
            ),
        },
        # N3 特有元数据
        "n3_metadata": {
            "engine": "deferred_tax_liability",
            "formula": "deferred_tax_liability = taxable_temporary_difference × tax_rate",
            "cross_wp_links": ["N1", "N5-8"],
        },
        # sheet 列表元数据
        "sheets": N3_SHEETS,
        "component_type": "n3-deferred-tax-liabilities",
    }
