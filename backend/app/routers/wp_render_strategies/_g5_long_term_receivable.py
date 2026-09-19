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
from app.services.four_table.g_cycle_specs import G5_SPEC
from app.services.four_table import (
    resolve_semantic_accounts,
    select_leaves,
    filter_by_prefixes,
    to_leaf_rows,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

_G5_ACCOUNT_PREFIX = "1531"  # 兜底常量，仅 fallback
_ADJUDICATED_ITEM_ID = "G5-1-adjudicated-amount"

#: 科目定位改走**语义驱动**（单一真源 `four_table/g_cycle_specs.G5_SPEC`）。
G5_ACCOUNT_SPEC = G5_SPEC


# ─── Pure functions ───────────────────────────────────────────────────────────


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


# ─── Data fetch ───────────────────────────────────────────────────────────────


async def _load_leaves(ctx: RenderContext, codes: list[str]) -> list[dict]:
    """获取叶子科目行 — 改用共享件 `select_leaves` + `filter_by_prefixes`。

    🔴 旧实现用自造 `_is_leaf` + 无点号边界 `LIKE '{code}%'`，前者会在参差树丢叶子
    （`_row_depth` 只取最深，`1531.01` 无子科目时被 `1531.02.01` 深度挤掉），
    后者会让 `1531` 误命中 `15310` 这类不同科目。改用共享件消除两类缺陷。
    """
    leaves: list[dict] = []
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        # 构建 OR 条件：code == prefix OR code LIKE 'prefix.%'（点号边界）
        conditions = []
        for code in codes:
            conditions.append(TbBalance.account_code == code)
            conditions.append(TbBalance.account_code.like(f"{code}.%"))

        if not conditions:
            return []

        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.dataset_id,
            ).where(sa.and_(active_filter, sa.or_(*conditions)))
        )
        all_rows = to_leaf_rows(result.fetchall())
        # 共享件叶子判定 + 前缀过滤
        filtered = filter_by_prefixes(select_leaves(all_rows), codes)

        for row in filtered:
            leaves.append({
                "account_code": row.account_code,
                "account_name": row.account_name,
                "opening_balance": row.opening,
                "closing_balance": row.closing,
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

    # ─── 四表取数（语义驱动科目定位） ────────────────────────────────────────
    accounts = await resolve_semantic_accounts(ctx, G5_ACCOUNT_SPEC)
    resolved_codes = accounts.codes_of("gross") or [_G5_ACCOUNT_PREFIX]
    tb_source_codes = accounts.as_dict()

    # 获取叶子
    leaves = await _load_leaves(ctx, resolved_codes)

    # 构建输出
    tb_values = build_g5_tb_values(leaves)
    leaf_categories = build_g5_leaf_categories(leaves)
    adjudication_prefill = build_g5_adjudication_prefill(leaf_categories)

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
