"""G7 长期股权投资(main组) — 专属渲染策略.

componentType: g7-long-term-equity-main
科目 1511 长期股权投资（借方/资产类）。

覆盖 7 个 sheet（sheetName v-if dispatch 主入口 GtG7LongTermEquityMain.vue 分发）：
    G7A 实质性程序表 / G7-1 审定表(97行×12列，5组分组折叠) /
    G7-2 明细表(54列→5区段Tab) / G7-3 调整分录汇总 /
    附注披露信息（上市公司）(253行) / 附注披露信息（国企）(355行) / 底稿目录

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免被 onlyoffice-sheet 吞掉。
2. 返回 7 个 sheet 配置供前端 sheetName v-if 分发。
3. 为 G7-1 审定表自动取数：1511 长期股权投资期初/期末余额 seed。
4. 回读已持久化的审定数（EventBus substantive:adjudicated 落库）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# G7-1 审定表 TB 取数科目（前缀匹配，兼容明细科目如 151101）
_G7_ACCOUNT_PREFIX = "1511"

# 长期股权投资减值准备（备抵科目，前端「减值准备」列 TB 核对用）
_G7_IMPAIRMENT_PREFIX = "1512"

# EventBus 审定值持久化的独立 item_id（render 回读 seed）
_ADJUDICATED_ITEM_ID = "G7-1-adjudicated-amount"

# 7 个 sheet 配置：sheetName（与源 xlsx tab 名一致）/ code（前端正则提取分发键）
G7_MAIN_SHEETS = [
    {
        "code": "G7A",
        "sheetName": "长期股权投资实质性程序表G7A",
        "componentType": "a-program-console",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-1",
        "sheetName": "审定表G7-1",
        "componentType": "g7-long-term-equity-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-2",
        "sheetName": "明细表G7-2",
        "componentType": "g7-long-term-equity-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-3",
        "sheetName": "调整分录汇总G7-3",
        "componentType": "g7-long-term-equity-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "附注披露信息（上市公司）",
        "sheetName": "附注披露信息（上市公司）",
        "componentType": "g7-long-term-equity-main",
        "group": "disclosure",
        "columns": [],
        "rows": [],
    },
    {
        "code": "附注披露信息（国企）",
        "sheetName": "附注披露信息（国企）",
        "componentType": "g7-long-term-equity-main",
        "group": "disclosure",
        "columns": [],
        "rows": [],
    },
    {
        "code": "底稿目录",
        "sheetName": "底稿目录",
        "componentType": "g7-long-term-equity-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
]


def _is_leaf(code: str, all_codes: set[str]) -> bool:
    """叶子判定：该 code 不是任何其它 code 的前缀（防父子双算）。

    与平台其它循环（F1/H2/H4/D-cycle prefill）口径一致：对 ``all_codes`` 中任一
    ``other != code``，若 ``other.startswith(code)`` 则 ``code`` 不是叶子。
    """
    return not any(other != code and other.startswith(code) for other in all_codes)


def _sum_leaf_by_prefix(
    rows: list[tuple[str, float, float]], prefix: str
) -> tuple[float, float, list[str]]:
    """按科目前缀筛出候选，**只累加叶子科目**的期初/期末余额（纯同步函数，便于单测）。

    🔴 四表库铁律：tb_balance 同时存父级（1511）与多级子科目（1511.01 / 1511.04.01），
    父子同时累加会虚增 2~3 倍 → 必须先做叶子判定再汇总。

    Args:
        rows: ``(account_code, opening_balance, closing_balance)`` 三元组列表。
        prefix: 科目前缀（如 "1511" / "1512"）。

    Returns:
        ``(opening, closing, leaf_codes)``；无候选时返回 ``(0.0, 0.0, [])``。
    """
    candidates = [
        (code, opening, closing)
        for code, opening, closing in rows
        if code and (code == prefix or code.startswith(prefix))
    ]
    all_codes = {code for code, _, _ in candidates}
    opening_total = 0.0
    closing_total = 0.0
    leaf_codes: list[str] = []
    for code, opening, closing in candidates:
        if not _is_leaf(code, all_codes):
            continue
        opening_total += float(opening or 0)
        closing_total += float(closing or 0)
        leaf_codes.append(code)
    return opening_total, closing_total, sorted(leaf_codes)


async def _fetch_tb_values(ctx: RenderContext) -> dict:
    """取 1511 长期股权投资 + 1512 减值准备 的期初/期末余额（仅叶子科目汇总）。

    一次查询取回 active dataset 内 1511%/1512% 的 ``(account_code, opening_balance,
    closing_balance)``，再由纯函数 :func:`_sum_leaf_by_prefix` 分组只累加叶子科目。

    返回::

        {"opening": float, "closing": float, "impairment": float,
         "impairment_opening": float,
         "source_codes": {"gross": [...叶子码], "impairment": [...叶子码]}}

    无匹配返回 ``{}``；异常 fail-open（warning + ``{}``）不阻断 render，前端允许手填。
    """
    tb: dict = {}
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        # 科目过滤下推 SQL（tb_balance 单项目可达百万行，避免全表扫描）；
        # 仍是**一次查询**同时取回原值组与减值组。
        prefix_filter = sa.or_(
            TbBalance.account_code.like(f"{_G7_ACCOUNT_PREFIX}%"),
            TbBalance.account_code.like(f"{_G7_IMPAIRMENT_PREFIX}%"),
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
            ).where(sa.and_(active_filter, prefix_filter))
        )
        rows = [
            (
                (row.account_code or "").strip(),
                float(row.opening_balance or 0),
                float(row.closing_balance or 0),
            )
            for row in result.fetchall()
        ]
        gross_opening, gross_closing, gross_codes = _sum_leaf_by_prefix(
            rows, _G7_ACCOUNT_PREFIX
        )
        imp_opening, imp_closing, imp_codes = _sum_leaf_by_prefix(
            rows, _G7_IMPAIRMENT_PREFIX
        )
        if gross_codes or imp_codes:
            tb = {
                # 原有键名与含义不变（1511 期初/期末），仅修正为叶子汇总口径
                "opening": gross_opening,
                "closing": gross_closing,
                # 新增：1512 长期股权投资减值准备
                "impairment": imp_closing,
                "impairment_opening": imp_opening,
                "source_codes": {"gross": gross_codes, "impairment": imp_codes},
            }
    except Exception as e:  # noqa: BLE001 — 取数失败降级为空，前端允许手填
        logger.warning("G7 TB fetch failed: %s", e)
    return tb


# 子科目 → G7-2 列语义（postgres 实证的 1511/1512 叶子分类）
_G7_CATEGORY_MAP: dict[str, str] = {
    "1511.01": "cost",         # 对子公司的投资（成本法）
    "1511.02": "cost",         # 联营/合营投资成本
    "1511.03": "profit_loss",  # 损益调整
    "1511.04.01": "oci",       # 其他权益变动-其他综合收益
    "1511.04.02": "other_equity",
    "1512": "impairment",      # 长期股权投资减值准备
}


def _classify_leaf(code: str) -> str | None:
    """按最长前缀匹配 Category_Map（精确 / 点分子级）；无匹配返回 None。

    例：``1511.01`` → 精确命中 cost；``1511.04.01`` → 精确命中 oci；
    ``1512.01`` → 经 ``1512.`` 命中 impairment；``1511`` 自身（无子级时）无匹配 → None。
    """
    best: str | None = None
    best_len = -1
    for key, cat in _G7_CATEGORY_MAP.items():
        if (code == key or code.startswith(key + ".")) and len(key) > best_len:
            best = cat
            best_len = len(key)
    return best


async def _build_g7_leaf_categories(ctx: RenderContext) -> dict | None:
    """tb_balance 1511%/1512% 叶子科目 → 分类合计（cost/profit_loss/oci/other_equity/impairment）。

    - 叶子判定复用 :func:`_is_leaf`（防父子双算，Property 1）；
    - 分类走 Category_Map 最长前缀匹配，未落入者进 ``unmapped``（不并入任何分类）；
    - 灰度关闭返回 ``None``；查询异常 fail-open 返回 ``None``（不阻断 render）。
    """
    from app.core.config import settings

    if not settings.G7_FOUR_TABLE_EXTRACTION_ENABLED:
        return None
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        prefix_filter = sa.or_(
            TbBalance.account_code.like(f"{_G7_ACCOUNT_PREFIX}%"),
            TbBalance.account_code.like(f"{_G7_IMPAIRMENT_PREFIX}%"),
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.closing_balance,
            ).where(sa.and_(active_filter, prefix_filter))
        )
        rows = [
            ((r.account_code or "").strip(), (r.account_name or "").strip(), float(r.closing_balance or 0))
            for r in result.fetchall()
        ]
        if not rows:
            return None
        all_codes = {code for code, _, _ in rows}
        cats = {"cost": 0.0, "profit_loss": 0.0, "oci": 0.0, "other_equity": 0.0, "impairment": 0.0}
        unmapped: list[dict] = []
        for code, name, closing in rows:
            if not _is_leaf(code, all_codes):
                continue
            cat = _classify_leaf(code)
            if cat and cat in cats:
                cats[cat] += closing
            else:
                unmapped.append({"code": code, "name": name, "amount": round(closing, 2)})
        return {
            **{k: round(v, 2) for k, v in cats.items()},
            "unmapped": unmapped,
            "source": "tb_balance",
        }
    except Exception as e:  # noqa: BLE001 — fail-open 不阻断 render
        logger.warning("G7 leaf categories fetch failed: %s", e)
        return None


async def render(ctx: RenderContext) -> dict | None:
    """G7 长期股权投资(main组) 渲染策略：返回 7 sheet 配置 + TB seed + responses 回读。"""
    wp_id = ctx.wp_id
    db = ctx.db

    responses_snapshot: dict = {}
    adjudicated_amount = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'G7-%' "
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
        logger.warning("G7 render: checklist_responses 失败: %s", e)

    from app.core.config import settings

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": _G7_ACCOUNT_PREFIX,
        # 灰度开关透出前端（G7-2「从四表取数」按钮显隐 / R2.6）
        "g7_extraction_enabled": bool(settings.G7_FOUR_TABLE_EXTRACTION_ENABLED),
    }
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
    except Exception as e:  # noqa: BLE001
        logger.warning("G7 render: project context 失败: %s", e)

    tb_values = await _fetch_tb_values(ctx)
    # additive：TB 取数溯源（实际参与汇总的叶子科目码），供前端展示来源，缺失即 {}
    project_context["tb_source_codes"] = tb_values.get("source_codes", {})

    # 灰度：G7-1 分类核对数据（叶子分类合计），关闭/异常返回 None（前端隐藏核对卡片）
    tb_leaf_categories = await _build_g7_leaf_categories(ctx)

    return {
        "component_type": "g7-long-term-equity-main",
        # 7 个 sheet 配置（componentType / sheetName / columns / rows）
        "sheets": G7_MAIN_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": _G7_ACCOUNT_PREFIX,
        "prefix": "G7",
        # G7-1 审定表试算表列只读 seed（真接线：render→html_data→FormData→组件 watch）
        "tb_values": tb_values,
        # G7-1 分类核对（叶子分类合计）；灰度关闭为 None（additive，前端隐藏核对卡片）
        "tb_leaf_categories": tb_leaf_categories,
        # 审定数回读 seed（EventBus 持久化后刷新不丢失）
        "adjudicated_amount": adjudicated_amount,
    }
