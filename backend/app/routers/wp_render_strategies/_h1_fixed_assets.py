"""H1 固定资产 — 专属渲染策略.

科目1601固定资产 + 1602累计折旧 + 1603减值准备
返回 allResponses + projectContext + TB汇总 + 按分类预填(adjudication_category_prefill)
"""
from __future__ import annotations

import logging
import re

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1601原值 / 1602累计折旧 / 1603减值准备
_H1_ACCOUNT_PREFIXES = {
    "1601": ("cost_unadjusted", "cost_audited"),
    "1602": ("dep_unadjusted", "dep_audited"),
    "1603": ("impair_unadjusted", "impair_audited"),
}

_H1_FA_CATEGORIES = (
    "房屋及建筑物",
    "机器设备",
    "运输设备",
    "办公设备",
    "其他设备",
)

H1_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h1-fixed-assets"},
    {"sheet_name": "固定资产审计程序表H1A", "component_type": "h1-fixed-assets"},
    {"sheet_name": "审定表H1-1", "component_type": "h1-fixed-assets"},
    {"sheet_name": "明细表H1-2", "component_type": "h1-fixed-assets"},
    {"sheet_name": "调整分录汇总H1-3", "component_type": "h1-fixed-assets"},
    {"sheet_name": "闲置检查表H1-4", "component_type": "h1-fixed-assets"},
    {"sheet_name": "会计政策估计检查表H1-5", "component_type": "h1-fixed-assets"},
    {"sheet_name": "分析表H1-6", "component_type": "h1-fixed-assets"},
    {"sheet_name": "增加检查表H1-7", "component_type": "h1-fixed-assets"},
    {"sheet_name": "减少检查表H1-8", "component_type": "h1-fixed-assets"},
    {"sheet_name": "监盘计划H1-9", "component_type": "h1-fixed-assets"},
    {"sheet_name": "盘点检查表H1-10", "component_type": "h1-fixed-assets"},
    {"sheet_name": "监盘小结H1-11", "component_type": "h1-fixed-assets"},
    {"sheet_name": "折旧测算表H1-12", "component_type": "h1-fixed-assets"},
    {"sheet_name": "折旧分配分析表H1-13", "component_type": "h1-fixed-assets"},
    {"sheet_name": "减值测算表H1-14", "component_type": "h1-fixed-assets"},
    {"sheet_name": "可收回金额测试表H1-15", "component_type": "h1-fixed-assets"},
    {"sheet_name": "房屋建筑物权属检查表H1-16", "component_type": "h1-fixed-assets"},
    {"sheet_name": "运输设备权属检查表H1-17", "component_type": "h1-fixed-assets"},
    {"sheet_name": "关联交易检查表H1-18", "component_type": "h1-fixed-assets"},
    {"sheet_name": "经营租出固定资产检查表H1-19", "component_type": "h1-fixed-assets"},
    {"sheet_name": "融资租出固定资产检查表H1-20", "component_type": "h1-fixed-assets"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h1-fixed-assets"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h1-fixed-assets"},
]


def _classify_fa_block(code: str) -> str | None:
    c = (code or "").strip()
    if c.startswith("1601"):
        return "cost"
    if c.startswith("1602"):
        return "dep"
    if c.startswith("1603"):
        return "impair"
    return None


def _classify_fa_category(code: str, name: str) -> str:
    """科目名称优先；其次二级码 01~05 启发式；再退化为「机器设备/其他设备」。

    关键词按特异性排序：房屋 → 运输 → 办公/电子 → 机器 → 显式其他。
    办公在机器之前判断，避免「办公设备」被 `设备` 误归机器。
    无任何名称信号且无二级码时，兜底为「其他设备」（由审计师在 H1-1 复核）。
    """
    s = re.sub(r"\s+", "", name or "")
    if re.search(r"房屋|建筑|厂房|仓库|构筑物|不动产|房产|土地", s):
        return "房屋及建筑物"
    if re.search(r"运输|车辆|汽车|客车|货车|专用车|挂车|叉车|拖拉机|船舶|飞机|机动车", s):
        return "运输设备"
    if re.search(r"办公|电子设备|电脑|计算机|打印|复印|服务器|网络|监控|摄像|空调|家具|器具", s):
        return "办公设备"
    if re.search(r"机器|机械|生产|生产线|流水线|机组|专用设备|通用设备|锅炉|电机|装置|仪器|仪表", s):
        return "机器设备"
    if re.search(r"其他|未分类|低值", s):
        return "其他设备"
    # 名称含泛化「设备/机床/工具」但无更具体信号 → 机器设备（较其他设备更贴切）
    if re.search(r"设备|机床|工具", s):
        return "机器设备"

    m = re.match(r"^160[123][.\-]?0?([1-5])", (code or "").strip())
    if m:
        return {
            "1": "房屋及建筑物",
            "2": "机器设备",
            "3": "运输设备",
            "4": "办公设备",
            "5": "其他设备",
        }.get(m.group(1), "其他设备")
    return "其他设备"


def _empty_amt() -> dict:
    return {"begin": 0.0, "debit": 0.0, "credit": 0.0, "end": 0.0, "unadjusted": 0.0}


async def _build_category_prefill(ctx: RenderContext) -> dict:
    """从 tb_balance 的 1601/1602/1603 子科目按分类聚合，供 H1-1 预填未审数。"""
    buckets: dict[str, dict] = {
        cat: {"category": cat, "cost": _empty_amt(), "dep": _empty_amt(), "impair": _empty_amt(), "needs_review": False}
        for cat in _H1_FA_CATEGORIES
    }
    # 记录纯兜底项（名称无特征信号且无二级码匹配）
    _fallback_codes: set[str] = set()

    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(active_filter)
        )
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            block = _classify_fa_block(code)
            if not block:
                continue
            name = (row.account_name or "").strip()
            cat = _classify_fa_category(code, name)
            # 检测是否为纯兜底分类（即名称无任何关键词命中且无二级码匹配）
            if cat == "其他设备":
                s = re.sub(r"\s+", "", name)
                has_keyword = bool(re.search(r"其他|未分类|低值|设备|机床|工具", s))
                has_code = bool(re.match(r"^160[123][.\-]?0?[1-5]", code))
                if not has_keyword and not has_code:
                    _fallback_codes.add(code)
            target = buckets[cat][block]
            begin = float(row.opening_balance or 0)
            end = float(row.closing_balance or 0)
            debit = float(row.debit_amount or 0)
            credit = float(row.credit_amount or 0)
            begin_v = begin if block == "cost" else abs(begin)
            end_v = end if block == "cost" else abs(end)
            target["begin"] += begin_v
            target["debit"] += debit
            target["credit"] += credit
            target["end"] += end_v
            target["unadjusted"] += end_v
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 category prefill tb_balance fetch failed: %s", e)

    # 标记含纯兜底科目的分类需要复核
    if _fallback_codes:
        buckets["其他设备"]["needs_review"] = True

    categories = [buckets[c] for c in _H1_FA_CATEGORIES]

    def _sum(block: str) -> float:
        return sum(float(r[block]["unadjusted"]) for r in categories)

    return {
        "categories": categories,
        "totals": {
            "cost1601": _sum("cost"),
            "dep1602": _sum("dep"),
            "impair1603": _sum("impair"),
        },
    }


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1601+1602+1603的期初/期末余额及未审数."""
    tb: dict[str, float] = {}
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(active_filter)
        )
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            for prefix, (unadj_key, _audited_key) in _H1_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 TB balance fetch failed: %s", e)

    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND (
                    standard_account_code LIKE '1601%'
                    OR standard_account_code LIKE '1602%'
                    OR standard_account_code LIKE '1603%'
                  )
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _H1_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 trial_balance fetch failed: %s", e)

    # 兼容前端旧键名
    if "cost_unadjusted" in tb:
        tb["cost_1601_unadjusted"] = tb["cost_unadjusted"]
    if "dep_unadjusted" in tb:
        tb["dep_1602_unadjusted"] = tb["dep_unadjusted"]
    if "impair_unadjusted" in tb:
        tb["impair_1603_unadjusted"] = tb["impair_unadjusted"]

    return tb


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/适用准则）."""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category, p.applicable_standard_v2 AS applicable_standards
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
            project_ctx["applicable_standards"] = row.applicable_standards or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """H1固定资产渲染策略：allResponses + projectContext + TB + 分类预填."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H1%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 render responses load failed: %s", e)

    tb_values = await _fetch_tb_data(ctx)
    category_prefill = await _build_category_prefill(ctx)
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "h1-fixed-assets",
        "account_codes": ["1601", "1602", "1603"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "adjudication_category_prefill": category_prefill,
        "project_context": project_context,
        "prefix": "H1",
        "sheets": H1_SHEETS,
    }
