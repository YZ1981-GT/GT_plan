"""H2 在建工程 — 专属渲染策略.

科目定位（语义驱动）：
  在建工程 = 1604
  工程物资 = 1605（含于同报表行 BS-029）
  报表行 BS-029 = TB('1604')

返回 allResponses + projectContext + TB数据(两层) + tb_source_codes
三角勾稽含转固扣减：期末=期初+增加-减少-转固

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.h2_account_scope import H2_ACCOUNT_SPEC, H2_SLOT_KEY_PREFIX
from app.services.four_table.semantic_account_resolver import (
    SemanticAccountResult,
    resolve_semantic_accounts,
)
from app.services.four_table.leaf_aggregation import (
    aggregate_leaves,
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table.parent_check import build_parent_check

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 保留旧常量供 _alias_tb_keys 兼容，不再作取数路径真源
_H2_ACCOUNT_PREFIXES = {
    "1604": ("cip_unadjusted", "cip_audited"),
    "1605": ("eng_mat_unadjusted", "eng_mat_audited"),
}

H2_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "在建工程实质性程序表H2A", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "审定表H2-1", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "明细表H2-2", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "调整分录汇总H2-3", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "分析表H2-4", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "转固时点检查表H2-5", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "在建工程审核记录H2-6", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "工程造价比较表H2-7", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "增加检查表H2-8", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "减少检查表H2-9", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "利息资本化测算表（无专门借款）H2-10", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "利息资本化测算表（有专门借款）H2-11", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "监盘计划H2-12", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "盘点检查表H2-13", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "监盘小结H2-14", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "减值测算表H2-15", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "可收回金额测试表H2-16", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "关联交易检查表H2-17", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h2-construction-in-progress"},
]


def _alias_tb_keys(tb: dict[str, float]) -> dict[str, float]:
    """补充前端常用别名键，避免 cip_unadjusted vs cip_1604_unadjusted 不一致."""
    aliases = {
        "cip_1604_unadjusted": tb.get("cip_unadjusted", 0.0),
        "cip_1604_audited": tb.get("cip_audited", 0.0),
        "eng_mat_1605_unadjusted": tb.get("eng_mat_unadjusted", 0.0),
        "eng_mat_1605_audited": tb.get("eng_mat_audited", 0.0),
    }
    for k, v in aliases.items():
        tb.setdefault(k, v)
    return tb


def _is_leaf(code: str, all_codes: set[str]) -> bool:
    """判定该科目是否为叶子节点（不是任何其它科目的前缀）。防止父子双算。"""
    for other in all_codes:
        if other != code and other.startswith(code):
            return False
    return True


async def _fetch_tb_data(ctx: RenderContext) -> tuple[dict, SemanticAccountResult]:
    """按语义槽取在建工程两层数据（在建工程 + 工程物资）。"""
    accounts = await resolve_semantic_accounts(ctx, H2_ACCOUNT_SPEC)

    tb: dict[str, float] = {}
    tb_rows: list = []
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
                TbBalance.closing_direction,
                TbBalance.dataset_id,
            ).where(active_filter)
        )
        tb_rows = list(result.fetchall())
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 TB balance fetch failed: %s", e)

    leaves = select_leaves(to_leaf_rows(tb_rows))
    for slot_key, prefix in H2_SLOT_KEY_PREFIX.items():
        slot = accounts.slots.get(slot_key)
        if slot is None or not slot.found:
            continue
        agg = aggregate_leaves(leaves, slot.codes)
        tb[f"{prefix}_unadjusted_opening"] = agg["opening"]
        tb[f"{prefix}_unadjusted_closing"] = agg["closing"]
        tb[f"{prefix}_unadjusted_debit"] = agg["debit"]
        tb[f"{prefix}_unadjusted_credit"] = agg["credit"]

    # trial_balance 精确匹配
    trial_rows: list = []
    standard_codes = sorted(
        {c for slot in accounts.slots.values() for c in slot.standard_codes if c}
    )
    if standard_codes:
        try:
            result = await ctx.db.execute(
                sa.text(
                    "SELECT standard_account_code, unadjusted_amount, audited_amount "
                    "FROM trial_balance "
                    "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                    "  AND standard_account_code = ANY(:codes)"
                ),
                {"pid": str(ctx.project_id), "year": ctx.year, "codes": standard_codes},
            )
            trial_rows = list(result.fetchall())
            for row in trial_rows:
                code = str(row.standard_account_code or "").strip()
                for slot_key, prefix in H2_SLOT_KEY_PREFIX.items():
                    slot = accounts.slots.get(slot_key)
                    if slot and code in set(slot.standard_codes):
                        tb[f"{prefix}_unadjusted"] = tb.get(f"{prefix}_unadjusted", 0.0) + float(row.unadjusted_amount or 0)
                        tb[f"{prefix}_audited"] = tb.get(f"{prefix}_audited", 0.0) + float(row.audited_amount or 0)
                        break
        except Exception as e:  # noqa: BLE001
            logger.warning("H2 trial_balance fetch failed: %s", e)

    tb["_parent_check"] = build_parent_check(
        accounts, tb_rows, trial_rows, H2_SLOT_KEY_PREFIX.keys()
    )
    return _alias_tb_keys(tb), accounts


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/适用准则/资产负债表日/关联方清单）."""
    project_ctx: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
        "applicable_standards": "",
        # bs_date（资产负债表日）：供 H2-5 转固期后窗口/少计折旧 asOf、H2-13 盘点基准日等取数
        "bs_date": "",
        # 关联方清单：供 H2-17 关联交易检查自动识别
        "related_parties": [],
    }
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
            if row.audit_year:
                project_ctx["bs_date"] = f"{row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 project context load failed: %s", e)

    # 关联方清单：从关联方登记表（related_party_registry）取项目级名单
    try:
        rp_rows = (
            await ctx.db.execute(
                sa.text(
                    "SELECT name FROM related_party_registry "
                    "WHERE project_id = :pid AND is_deleted = false "
                    "AND name IS NOT NULL AND name <> ''"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchall()
        project_ctx["related_parties"] = [r.name for r in rp_rows if r.name]
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 render: related_parties 查询失败: %s", e)

    return project_ctx


async def _build_h2_detail_prefill(ctx: RenderContext) -> list[dict]:
    """从 tb_balance 1604% 叶子科目构建 H2-2 明细行种子（Persist_First 由前端控制）。"""
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
            ).where(active_filter)
        )
        all_rows = result.fetchall()
        codes_1604: set[str] = set()
        for row in all_rows:
            code = (row.account_code or "").strip()
            if code == "1604" or code.startswith("1604"):
                codes_1604.add(code)
        prefill: list[dict] = []
        for row in all_rows:
            code = (row.account_code or "").strip()
            if code not in codes_1604:
                continue
            if not _is_leaf(code, codes_1604):
                continue
            opening = abs(float(row.opening_balance or 0))
            closing = abs(float(row.closing_balance or 0))
            if opening < 0.005 and closing < 0.005:
                continue
            name = (row.account_name or "").strip() or (code[4:].lstrip(".") if len(code) > 4 else code)
            prefill.append({"name": name, "cipBegin": opening, "cipEnd": closing, "category": "自动种子"})
        return prefill
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 detail prefill failed: %s", e)
        return []


async def render(ctx: RenderContext) -> dict | None:
    """H2在建工程渲染策略：allResponses + projectContext + TB数据."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H2-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 render responses load failed: %s", e)

    tb_values, accounts = await _fetch_tb_data(ctx)
    project_context = await _load_project_context(ctx)

    # 灰度门控：H2_FOUR_TABLE_EXTRACTION_ENABLED 控制是否输出 detail_prefill
    from app.core.config import settings
    if settings.H2_FOUR_TABLE_EXTRACTION_ENABLED:
        detail_prefill = await _build_h2_detail_prefill(ctx)
    else:
        detail_prefill = []

    resolved_codes = sorted({c for slot in accounts.slots.values() if slot.found for c in slot.codes})

    return {
        "component_type": "h2-construction-in-progress",
        "account_codes": resolved_codes or ["1604", "1605"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": accounts.as_dict(),
        "project_context": project_context,
        "detail_prefill": detail_prefill,
        "prefix": "H2",
        "sheets": H2_SHEETS,
    }
