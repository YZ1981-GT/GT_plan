"""G1 交易性金融资产 — 专属渲染策略.

componentType: g1-trading-financial-assets
科目 1501 交易性金融资产（借方/资产类）。

除返回 checklist 快照外，为 G1-1 审定表自动取数：
- 1501 交易性金融资产 的期初/期末余额（tb_balance，get_active_filter）
供前端 G1-1 审定表试算表列（只读）seed。
并回读已持久化的审定数（EventBus substantive:adjudicated 落库的独立 item_id），
供 render 回填 seed，避免刷新后丢失。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# G1-1 审定表 TB 取数科目（前缀匹配，兼容明细科目如 150101）
_G1_ACCOUNT_PREFIX = "1501"

# EventBus 审定值持久化的独立 item_id（render 回读 seed）
_ADJUDICATED_ITEM_ID = "G1-1-adjudicated-amount"

G1_INVEST_TYPES = [
    {"rowKey": "stock", "label": "股票"},
    {"rowKey": "fund", "label": "基金"},
    {"rowKey": "bond", "label": "债券"},
    {"rowKey": "derivative", "label": "衍生工具"},
    {"rowKey": "other", "label": "其他"},
]

G1_MEASURE_TYPES = [
    {"rowKey": "cost", "label": "成本"},
    {"rowKey": "fv-change", "label": "公允价值变动"},
    {"rowKey": "disposal", "label": "处置损益"},
]


async def _fetch_tb_values(ctx: RenderContext) -> dict:
    """取 1501 交易性金融资产 期初/期末余额，按父科目前缀聚合。

    返回 {"opening": float, "closing": float, "by_category": [...]}，
    by_category 按子科目分类映射到投资品种（stock/fund/bond/derivative/other），
    供前端 G1-1 审定表分行预填 seed。
    取数失败降级为空 dict，前端允许手填。
    """
    tb: dict = {}
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
                TbBalance.level,
            ).where(active_filter)
        )
        opening = 0.0
        closing = 0.0
        matched = False
        by_category: list[dict] = []
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            if code == _G1_ACCOUNT_PREFIX or code.startswith(_G1_ACCOUNT_PREFIX):
                opening += float(row.opening_balance or 0)
                closing += float(row.closing_balance or 0)
                matched = True
                # 子科目分类映射（非汇总行）
                if code != _G1_ACCOUNT_PREFIX and (row.level or 0) >= 2:
                    name = (row.account_name or "").lower()
                    category = _classify_g1_sub_account(name, code)
                    by_category.append({
                        "account_code": code,
                        "account_name": row.account_name or "",
                        "category": category,
                        "opening": float(row.opening_balance or 0),
                        "closing": float(row.closing_balance or 0),
                    })
        if matched:
            tb = {"opening": opening, "closing": closing, "by_category": by_category}
    except Exception as e:  # noqa: BLE001 — 取数失败降级为空，前端允许手填
        logger.warning("G1 TB fetch failed: %s", e)
    return tb


def _classify_g1_sub_account(name: str, code: str) -> str:
    """根据科目名称/编码将子科目映射到G1投资品种分类。"""
    # 按名称关键词优先
    if any(kw in name for kw in ("股票", "股权", "股份")):
        return "stock"
    if any(kw in name for kw in ("基金", "理财", "信托")):
        return "fund"
    if any(kw in name for kw in ("债券", "债", "票据")):
        return "bond"
    if any(kw in name for kw in ("衍生", "期权", "期货", "远期", "互换", "掉期")):
        return "derivative"
    # 按科目编码后缀（致同惯例：01股票02基金03债券04衍生）
    suffix = code[len(_G1_ACCOUNT_PREFIX):]
    if suffix.startswith("01"):
        return "stock"
    if suffix.startswith("02"):
        return "fund"
    if suffix.startswith("03"):
        return "bond"
    if suffix.startswith("04"):
        return "derivative"
    return "other"


async def render(ctx: RenderContext) -> dict | None:
    wp_id = ctx.wp_id
    db = ctx.db

    responses_snapshot: dict = {}
    adjudicated_amount = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'G1-%' "
                "LIMIT 800"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
        # 审定值回读：EventBus substantive:adjudicated 落库的独立 item_id
        adjudicated_amount = responses_snapshot.get(_ADJUDICATED_ITEM_ID, {}).get(
            "conclusion", ""
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("G1 render: checklist_responses 失败: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": _G1_ACCOUNT_PREFIX,
        "bs_date": "",
        "related_parties": [],
        "applicable_standards": [],
    }
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, applicable_standard_v2 "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            audit_year = str(proj_row.audit_year or "")
            project_context["audit_year"] = audit_year
            if audit_year:
                project_context["bs_date"] = f"{audit_year}-12-31"
            # applicable_standards — 可能是 JSONB dict 或 string
            raw_std = proj_row.applicable_standard_v2
            if raw_std:
                if isinstance(raw_std, dict):
                    std_type = raw_std.get("type", "")
                    if std_type:
                        project_context["applicable_standards"] = [std_type]
                elif isinstance(raw_std, str):
                    project_context["applicable_standards"] = [raw_std]
    except Exception as e:  # noqa: BLE001
        logger.warning("G1 render: project context 失败: %s", e)

    # 关联方名单（供G1-13凭证检查识别关联方交易）
    try:
        rp_result = await db.execute(
            sa.text(
                "SELECT name FROM related_party_registry "
                "WHERE project_id = :pid AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )
        project_context["related_parties"] = [
            r.name for r in rp_result.fetchall() if r.name
        ]
    except Exception:  # noqa: BLE001 — 表可能不存在
        pass

    tb_values = await _fetch_tb_values(ctx)

    return {
        "component_type": "g1-trading-financial-assets",
        "invest_types": G1_INVEST_TYPES,
        "measure_types": G1_MEASURE_TYPES,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": _G1_ACCOUNT_PREFIX,
        "prefix": "G1",
        # G1-1 审定表试算表列只读 seed（真接线：render→html_data→FormData→组件 watch）
        "tb_values": tb_values,
        # 审定数回读 seed（EventBus 持久化后刷新不丢失）
        "adjudicated_amount": adjudicated_amount,
    }
