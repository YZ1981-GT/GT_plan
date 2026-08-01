"""G5 长期应收款 — 专属渲染策略.

componentType: g5-long-term-receivable
科目 1531 长期应收款（借方/资产类）。

科目映射真源：report_config `BS-023 长期应收款 = TB('1531','期末余额')` 四准则一致。
取数：共享件 `four_table/report_line_accounts` 解析 → `leaf_aggregation` 叶子聚合。
性质分类：`four_table/g5_nature_buckets` 按名称归类。
"""

from __future__ import annotations

import logging
from collections import defaultdict

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.g5_nature_buckets import (
    G5_NATURE_BUCKETS,
    bucket_defs_payload,
    classify_g5_leaf,
)
from app.services.four_table.report_line_accounts import (
    ReportLineAccountSpec,
)
from app.services.report_account_mapping import resolve_report_line_account_codes

from ._context import RenderContext

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

_G5_ACCOUNT_PREFIX = "1531"  # 兜底常量，仅 fallback
_ADJUDICATED_ITEM_ID = "G5-1-adjudicated-amount"

G5_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code="BS-023",
    fallback_gross=("1531",),
)


# ─── Pure functions ───────────────────────────────────────────────────────────


def _is_leaf(code: str, all_codes: set[str]) -> bool:
    """判断是否叶子（无更深层子科目）."""
    prefix = code + "."
    return not any(c.startswith(prefix) for c in all_codes if c != code)


def build_g5_tb_values(leaves: list[dict]) -> dict:
    """从叶子列表构建 TB 取值."""
    opening = 0.0
    closing = 0.0
    for leaf in leaves:
        opening += float(leaf.get("opening_balance", 0) or 0)
        closing += float(leaf.get("closing_balance", 0) or 0)
    if not leaves:
        return {}
    return {"opening": opening, "closing": closing}


def build_g5_leaf_categories(leaves: list[dict]) -> dict:
    """按性质桶归类叶子科目."""
    categories: dict[str, dict] = defaultdict(
        lambda: {"codes": [], "opening": 0.0, "closing": 0.0}
    )
    for leaf in leaves:
        name = leaf.get("account_name", "") or ""
        code = leaf.get("account_code", "") or ""
        bucket_key = classify_g5_leaf(name, code)
        cat = categories[bucket_key]
        cat["codes"].append(code)
        cat["opening"] += float(leaf.get("opening_balance", 0) or 0)
        cat["closing"] += float(leaf.get("closing_balance", 0) or 0)
    return dict(categories)


def build_g5_adjudication_prefill(categories: dict) -> list[dict]:
    """从性质分类构建审定表预填数据."""
    prefill = []
    for bucket in G5_NATURE_BUCKETS:
        cat = categories.get(bucket.key)
        if not cat:
            continue
        if cat["opening"] == 0 and cat["closing"] == 0:
            continue
        prefill.append({
            "bucket_key": bucket.key,
            "label": bucket.label,
            "opening": cat["opening"],
            "closing": cat["closing"],
        })
    return prefill


def build_g5_source_codes(
    resolved_codes: list[str],
    resolved_from: str,
    applicable_standard: str | None = None,
) -> dict:
    """构建 tb_source_codes 溯源字段."""
    return {
        "gross_standard": resolved_codes[0] if resolved_codes else _G5_ACCOUNT_PREFIX,
        "resolved_from": resolved_from,
        "applicable_standard": applicable_standard or "",
    }


# ─── Data fetch ───────────────────────────────────────────────────────────────


async def _load_leaves(ctx: RenderContext, codes: list[str]) -> list[dict]:
    """获取叶子科目行（select_leaves 逻辑内联以避免循环依赖）."""
    leaves: list[dict] = []
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        # 构建 LIKE 条件
        like_clauses = []
        for code in codes:
            like_clauses.append(TbBalance.account_code.like(f"{code}%"))

        if not like_clauses:
            return []

        combined_filter = sa.or_(*like_clauses) if len(like_clauses) > 1 else like_clauses[0]

        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
            ).where(sa.and_(active_filter, combined_filter))
        )
        rows = result.fetchall()

        # 收集所有 codes 来判定叶子
        all_codes = {r.account_code.strip() for r in rows if r.account_code}

        for row in rows:
            code = (row.account_code or "").strip()
            if not code:
                continue
            if not _is_leaf(code, all_codes):
                continue
            leaves.append({
                "account_code": code,
                "account_name": (row.account_name or "").strip(),
                "opening_balance": float(row.opening_balance or 0),
                "closing_balance": float(row.closing_balance or 0),
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("G5 leaf fetch failed: %s", e)
    return leaves


# ─── Render entry ─────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict | None:
    """G5 长期应收款渲染策略入口."""
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── checklist_responses 快照 ─────────────────────────────────────────
    responses_snapshot: dict = {}
    adjudicated_amount = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'G5-%' "
                "LIMIT 800"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
        adjudicated_amount = responses_snapshot.get(_ADJUDICATED_ITEM_ID, {}).get(
            "conclusion", ""
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("G5 render: checklist_responses 失败: %s", e)

    # ─── project context ──────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": _G5_ACCOUNT_PREFIX,
    }
    applicable_standard: str | None = None
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, "
                "applicable_standard_v2->>'entity_type' as entity_type, "
                "applicable_standard_v2->>'scope' as scope "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            entity = proj_row.entity_type or "soe"
            scope = proj_row.scope or "standalone"
            applicable_standard = f"{entity}_{scope}"
    except Exception as e:  # noqa: BLE001
        logger.warning("G5 render: project context 失败: %s", e)

    # ─── 四表取数（共享件路径） ────────────────────────────────────────────
    resolved_codes: list[str] = list(G5_ACCOUNT_SPEC.fallback_gross)
    resolved_from = "fallback"
    try:
        parsed = await resolve_report_line_account_codes(
            db,
            ctx.project_id,
            G5_ACCOUNT_SPEC.row_code,
            fallback=list(G5_ACCOUNT_SPEC.fallback_gross),
            applicable_standards=[applicable_standard] if applicable_standard else None,
        )
        if parsed:
            resolved_codes = parsed
            resolved_from = "report_config"
    except Exception as e:  # noqa: BLE001
        logger.warning("G5 resolve_report_line_account_codes 失败 (降级 fallback): %s", e)

    # 获取叶子
    leaves = await _load_leaves(ctx, resolved_codes)

    # 构建输出
    tb_values = build_g5_tb_values(leaves)
    leaf_categories = build_g5_leaf_categories(leaves)
    adjudication_prefill = build_g5_adjudication_prefill(leaf_categories)
    tb_source_codes = build_g5_source_codes(resolved_codes, resolved_from, applicable_standard)

    return {
        "component_type": "g5-long-term-receivable",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": _G5_ACCOUNT_PREFIX,
        "prefix": "G5",
        "tb_values": tb_values,
        "adjudicated_amount": adjudicated_amount,
        # 新增四表取数输出
        "tb_source_codes": tb_source_codes,
        "adjudication_prefill": adjudication_prefill,
        "leaf_categories": leaf_categories,
        "nature_buckets": bucket_defs_payload(),
    }
