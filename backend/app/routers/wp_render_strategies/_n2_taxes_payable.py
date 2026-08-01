"""N2 应交税费 — 专属渲染策略.

component_type = "n2-taxes-payable"

N2 前端组件 GtN2TaxesPayable 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/增值税测算/其他税费测算/房产税/土增税/出口退税等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 N2 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目2221应交税费（**贷方/负债类科目**）：期末=期初+贷方-借方
N税费循环最复杂底稿（18 sheet/~180+公式）。
多税种测算引擎：增值税/城建税及附加/房产税/土地增值税/出口退税。
数据持久化在 checklist_responses 表，item_id 前缀为 "N2-*"。

Requirements: 1.6
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

_N2_ACCOUNT_CODE = "2221"
_ADJUDICATED_ITEM_ID = "N2-1-adjudicated-amount"

N2_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税费审计程序表N2A", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税费审定表N2-1", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税费明细表N2-2", "component_type": "n2-taxes-payable"},
    {"sheet_name": "调整分录汇总N2-3", "component_type": "n2-taxes-payable"},
    {"sheet_name": "税收政策检查N2-4", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税金认定表N2-5", "component_type": "n2-taxes-payable"},
    {"sheet_name": "增值税测算表N2-6", "component_type": "n2-taxes-payable"},
    {"sheet_name": "出口退税核对表N2-7", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交其他税费测算表N2-8", "component_type": "n2-taxes-payable"},
    {"sheet_name": "房产税测算表N2-9", "component_type": "n2-taxes-payable"},
    {"sheet_name": "土地增值税测算表N2-10", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税费检查表N2-11", "component_type": "n2-taxes-payable"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "n2-taxes-payable"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "n2-taxes-payable"},
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


async def _fetch_tb_data(ctx: RenderContext, year: str | None = None) -> dict[str, Any]:
    """从 tb_balance 取科目2221应交税费余额数据（负债类贷方）."""
    result: dict[str, Any] = {
        "account_code": _N2_ACCOUNT_CODE,
        "account_name": "应交税费",
        "direction": "credit",
        "begin_balance": 0,
        "debit_amount": 0,
        "credit_amount": 0,
        "end_balance": 0,
    }
    try:
        active_filter = get_active_filter(ctx.project_id)
        stmt = (
            sa.select(
                TbBalance.opening_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_balance,
            )
            .where(
                TbBalance.project_id == str(ctx.project_id),
                TbBalance.account_code == _N2_ACCOUNT_CODE,
                active_filter,
            )
        )
        # year 列为 Integer，需转型；非数字则跳过 year 过滤（不崩）
        if year:
            try:
                stmt = stmt.where(TbBalance.year == int(year))
            except (ValueError, TypeError):
                pass
        stmt = stmt.limit(1)
        row = (await ctx.db.execute(stmt)).fetchone()
        if row:
            # 读取真实列 opening_balance/closing_balance，输出键保持 begin_balance/end_balance（前端兼容）
            result["begin_balance"] = _parse_num(row.opening_balance)
            result["debit_amount"] = _parse_num(row.debit_amount)
            result["credit_amount"] = _parse_num(row.credit_amount)
            result["end_balance"] = _parse_num(row.closing_balance)
    except Exception as e:  # noqa: BLE001
        logger.warning("N2 render: TB 取数失败: %s", e)
    return result


# ─── 审定表预填（从 tb_balance 2221% 叶子子科目按税种归类）────────────────────


def _classify_tax_type(account_name: str | None) -> str:
    """按科目名称归类税种。

    注意关键词包含关系导致的顺序敏感：
    「土地增值税」含「增值税」→ 必须先判 lvt；
    「城镇土地使用税」含「土地」→ 先判 land-use；
    「地方教育」需先于「教育费附加」判定。
    """
    name = account_name or ""
    if "土地增值税" in name:
        return "lvt"
    if "城镇土地使用税" in name or "土地使用" in name:
        return "land-use"
    if "城市维护建设" in name or "城建" in name:
        return "urban"
    if "增值税" in name:
        return "urban"
    if "地方教育" in name:
        return "local-education"
    if "教育费附加" in name or "教育" in name:
        return "education"
    if "消费税" in name:
        return "consumption"
    if "企业所得税" in name:
        return "cit"
    if "个人所得税" in name:
        return "iit"
    if "印花税" in name:
        return "stamp"
    if "房产税" in name:
        return "property"
    if "车船税" in name:
        return "vehicle"
    return "other"


async def _build_adjudication_prefill(
    ctx: RenderContext, year: str | None = None
) -> dict[str, float]:
    """从 tb_balance 科目2221%叶子子科目按税种预填审定表未审数（期初/期末）。

    - 查 2221% 全部子科目，优先取叶子（不是其他 code 前缀者），退而取全部；
      叶子检测天然选出最深层明细（三级退二级退一级）。
    - 按科目名称 `_classify_tax_type` 归类税种。
    - 负债类贷方，金额取 abs() 规避借正贷负符号。
    - 返回 {N2-1-{taxtype}-audited: 期末abs, N2-1-{taxtype}-opening: 期初abs}。
    """
    prefill: dict[str, float] = {}
    try:
        active_filter = get_active_filter(ctx.project_id)
        stmt = sa.select(
            TbBalance.account_code,
            TbBalance.account_name,
            TbBalance.opening_balance,
            TbBalance.closing_balance,
        ).where(
            TbBalance.project_id == str(ctx.project_id),
            TbBalance.account_code.like(f"{_N2_ACCOUNT_CODE}%"),
            active_filter,
        )
        if year:
            try:
                stmt = stmt.where(TbBalance.year == int(year))
            except (ValueError, TypeError):
                pass
        rows = (await ctx.db.execute(stmt)).fetchall()
        if not rows:
            return prefill
        codes = [r.account_code for r in rows]
        # 叶子 = 不是其他 code 前缀者（选出最深层明细）
        leaves = [
            r
            for r in rows
            if not any(other != r.account_code and other.startswith(r.account_code) for other in codes)
        ]
        if not leaves:
            leaves = list(rows)
        for r in leaves:
            tt = _classify_tax_type(r.account_name)
            opening = abs(_parse_num(r.opening_balance))
            closing = abs(_parse_num(r.closing_balance))
            ak = f"N2-1-{tt}-audited"
            ok = f"N2-1-{tt}-opening"
            prefill[ak] = round(prefill.get(ak, 0.0) + closing, 2)
            prefill[ok] = round(prefill.get(ok, 0.0) + opening, 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("N2 render: adjudication prefill 构建失败: %s", e)
    return prefill


# ─── 主渲染函数 ───────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict[str, Any]:
    """N2 应交税费专属渲染策略.

    轻量返回：project_context + responses_snapshot + TB数据。
    前端 GtN2TaxesPayable 为自加载组件（各子组件独立拉取 checklist_responses）。
    """
    # ─── 读取 checklist_responses 快照（列名对齐 schema: wp_id/conclusion/remark） ───
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
        logger.warning("N2 render: checklist_responses 查询失败: %s", e)

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
        logger.warning("N2 render: project context 查询失败: %s", e)

    # bs_date
    audit_year = project_context.get("audit_year")
    project_context["bs_date"] = f"{audit_year}-12-31" if audit_year else None  # type: ignore[assignment]

    # 关联方
    related_parties: list[str] = []
    try:
        rp_rows = (await ctx.db.execute(
            sa.text(
                "SELECT party_name FROM related_party_registry "
                "WHERE project_id = :pid AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )).fetchall()
        related_parties = [r.party_name for r in rp_rows]
    except Exception:  # noqa: BLE001
        pass
    project_context["related_parties"] = related_parties  # type: ignore[assignment]

    # ─── TB 取数（科目2221应交税费，贷方/负债类）────────────────────
    tb = await _fetch_tb_data(ctx, year=audit_year)

    # ─── 审定表预填（仅无持久化 N2-1-adjudication-rows 时，不覆盖用户编辑）───
    adjudication_prefill: dict[str, float] = {}
    if "N2-1-adjudication-rows" not in responses_snapshot:
        adjudication_prefill = await _build_adjudication_prefill(ctx, year=audit_year)

    return {
        "account_code": _N2_ACCOUNT_CODE,
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        # 审定表预填（按税种从 tb_balance 2221% 叶子子科目归类，仅无持久化时非空）
        "adjudication_prefill": adjudication_prefill,
        # TB 余额数据（科目2221，贷方/负债类）
        "trial_balance": tb,
        # 负债类公式方向元数据
        "formula_direction": {
            "account_code": "2221",
            "account_name": "应交税费",
            "direction": "credit",  # 贷方/负债类！
            "end_balance_formula": "begin + credit - debit",  # 期末=期初+贷方-借方
            "note": (
                "负债类贷方科目：应交税费增加在贷方（计提时贷记2221），"
                "缴纳时借方减少。N税费循环最复杂底稿，涵盖增值税/城建税/"
                "教育费附加/房产税/土地增值税/出口退税多个税种。"
            ),
        },
        # N2 特有元数据
        "n2_metadata": {
            "engine": "multi_tax",
            "vat_formula": "payable_vat = output_vat - (input_vat - input_transfer_out)",
            "surtax_formula": "surtax = (vat + consumption_tax) × rate",
            "property_tax_by_value": "original_value × (1 - deduct_rate) × 1.2%",
            "property_tax_by_rent": "rent_income × 12%",
            "lvt_formula": "appreciation × rate - deduct_items × quick_deduct_coef",
            "cross_wp_links": ["N4", "L8"],
        },
        # sheet 列表元数据
        "sheets": N2_SHEETS,
        "component_type": "n2-taxes-payable",
    }
