"""G1 交易性金融资产 — 专属渲染策略.

componentType: g1-trading-financial-assets

科目映射链路（report_config DB 实证，四准则完全一致）：
  BS-003 交易性金融资产 = TB('1101','期末余额')
  BS-004 衍生金融资产   = TB('1102','期末余额')

G1-1 审定表三大部分：
  （一）投资成本：按金融资产分类 × 品种(债务/权益/衍生/理财/结构性存款/基金/其他)
  （二）累计公允价值变动：同维度
  （三）账面余额（公允价值）：= (一) + (二)

四表取数逻辑：
  1. 从 report_config 解析 BS-003 → 标准码 1101
  2. account_mapping 反解 → 原始码前缀集
  3. tb_balance 按前缀取叶子科目（select_leaves + filter_by_prefixes）
  4. 叶子按名称分类到 stock/fund/bond/derivative/other（classify_g1_leaf），供 by_category
  5. 输出 tb_source_codes 供溯源面板
  6. 输出 adjudication_prefill 供 G1-1「从四表库带入未审数」

🔴 `adjudication_prefill` **不做桶预聚合**：G1-1 的行维度是
``(投资成本 / 累计公允价值变动) × (交易性 / 划分为 / 指定为) × 7 品种``，
其中「分类」是会计判断、四表里没有，「品种」的客户叶子名多为银行户名/部门
（`classify_g1_leaf` 全归 `other` 是设计如此，品种靠 G1-2 明细 SUMIF 回流）。
故统一由 `four_table/g_cycle_adjudication_prefill` 下发**逐叶子明细**，
归类与「待归类」交前端 `gCycleAdjudicationSeed.ts` 处理。

交易性金融资产不计提减值准备（以公允价值计量，变动计入当期损益），故无 provision。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table import (
    build_g_adjudication_prefill,
    LeafRow,
    aggregate_leaves,
    filter_by_prefixes,
    parent_totals,
    resolve_semantic_accounts,
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table.g_cycle_specs import G1_SPEC

from ._context import RenderContext

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 科目定位规格（单一真源）
# ─────────────────────────────────────────────────────────────────────────────

#: 科目定位改走**语义驱动**（单一真源 `four_table/g_cycle_specs.G1_SPEC`）。
#: G1 底稿同时管理交易性金融资产（1101）与衍生金融资产（1102），
#: G1_SPEC 声明了双槽 `gross`（交易性金融资产）+ `derivative`（衍生金融资产）。
G1_ACCOUNT_SPEC = G1_SPEC

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


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数：叶子科目分类
# ─────────────────────────────────────────────────────────────────────────────


def classify_g1_leaf(name: str, code: str) -> str:
    """根据科目名称/编码将子科目映射到 G1 投资品种分类。

    名称优先（按关键字判定），编码兜底。判定顺序有意义：
    - 衍生必须先于其他（「衍生金融资产_成本」含「成本」但不是 cost）
    - 债券/票据先于通用「其他」
    """
    n = (name or "").lower()
    # 名称关键词优先
    if any(kw in n for kw in ("衍生", "期权", "期货", "远期", "互换", "掉期")):
        return "derivative"
    if any(kw in n for kw in ("股票", "股权", "股份")):
        return "stock"
    if any(kw in n for kw in ("基金",)):
        return "fund"
    if any(kw in n for kw in ("理财", "信托", "结构性存款")):
        return "fund"
    if any(kw in n for kw in ("债券", "债", "票据")):
        return "bond"
    # 编码兜底（致同常见惯例）
    c = (code or "").strip()
    # 去掉 1101 前缀后看首段
    for prefix in ("1101.", "1101"):
        if c.startswith(prefix) and len(c) > len(prefix):
            suffix = c[len(prefix):].lstrip(".")
            if suffix.startswith("01"):
                return "stock"
            if suffix.startswith("02"):
                return "fund"
            if suffix.startswith("03"):
                return "bond"
            if suffix.startswith("04"):
                return "derivative"
            break
    return "other"



# ─────────────────────────────────────────────────────────────────────────────
# 四表取数主入口
# ─────────────────────────────────────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取 1101 交易性金融资产的 tb_balance 数据，走共享件叶子聚合。

    返回:
        {
            "tb_values": {"opening": ..., "closing": ..., "by_category": [...]},
            "tb_source_codes": {...},
            "adjudication_prefill": {...},
        }
    取数失败降级为空 dict，前端允许手填。
    """
    result: dict = {"tb_values": {}, "tb_source_codes": {}, "adjudication_prefill": {}}

    try:
        # Step 1: 解析科目码（语义驱动，逐项目定位）
        accounts = await resolve_semantic_accounts(ctx, G1_ACCOUNT_SPEC)

        # Step 2: 从 tb_balance 取所有相关行
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        # 用原始码前缀集查询（语义解析件返 codes_of）
        query_prefixes = accounts.codes_of("gross")
        if not query_prefixes:
            result["tb_source_codes"] = accounts.as_dict()
            return result

        # 构建 OR 条件：code == prefix OR code LIKE 'prefix.%'
        conditions = []
        for p in query_prefixes:
            conditions.append(TbBalance.account_code == p)
            conditions.append(TbBalance.account_code.like(f"{p}.%"))

        rows = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_direction,
                TbBalance.dataset_id,
            ).where(sa.and_(active_filter, sa.or_(*conditions)))
        )
        all_rows = to_leaf_rows(rows.fetchall())

        if not all_rows:
            # 输出溯源信息（即使无数据）
            result["tb_source_codes"] = accounts.as_dict()
            return result

        # Step 3: 取叶子
        leaves = select_leaves(all_rows)
        filtered_leaves = filter_by_prefixes(leaves, query_prefixes)

        # Step 4: 聚合
        agg = aggregate_leaves(filtered_leaves, query_prefixes)

        # 父科目勾稽
        parent = parent_totals(all_rows, query_prefixes[0] if len(query_prefixes) == 1 else "")
        parent_check = None
        if parent.get("closing", 0) != 0 or parent.get("opening", 0) != 0:
            leaf_sum_closing = sum(r.closing for r in filtered_leaves)
            parent_check = {
                "leaf_sum": leaf_sum_closing,
                "parent": parent.get("closing", 0),
                "diff": round(leaf_sum_closing - parent.get("closing", 0), 2),
            }

        # Step 5: 分类构建 by_category（兼容既有前端消费）
        by_category: list[dict] = []
        for leaf in filtered_leaves:
            category = classify_g1_leaf(leaf.account_name, leaf.account_code)
            by_category.append({
                "account_code": leaf.account_code,
                "account_name": leaf.account_name,
                "category": category,
                "opening": leaf.opening,
                "closing": leaf.closing,
            })

        # Step 6: 构建预填

        # Step 7: 溯源
        source_codes = accounts.as_dict()
        # 审定表「从四表库带入未审数」统一载荷（逐叶子明细，归类在前端做）
        result["adjudication_prefill"] = build_g_adjudication_prefill(
            "G1", accounts, all_rows
        )
        source_codes["gross"] = [r.account_code for r in filtered_leaves]
        if parent_check:
            source_codes["parent_check"] = parent_check

        result["tb_values"] = {
            "opening": agg["opening"],
            "closing": agg["closing"],
            "by_category": by_category,
        }
        result["tb_source_codes"] = source_codes

    except Exception as e:  # noqa: BLE001 — 取数失败降级为空，前端允许手填
        logger.warning("G1 TB fetch failed: %s", e)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# render 主入口
# ─────────────────────────────────────────────────────────────────────────────


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
        "account_code": "1101",
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

    # 四表取数（交易性金融资产 1101）
    tb_data = await _fetch_tb_data(ctx)
    tb_values = tb_data["tb_values"]
    tb_source_codes = tb_data["tb_source_codes"]

    # 溯源信息注入 project_context
    project_context["tb_source_codes"] = tb_source_codes
    project_context["tb_amount"] = tb_values.get("closing", 0) if tb_values else 0

    return {
        "component_type": "g1-trading-financial-assets",
        "invest_types": G1_INVEST_TYPES,
        "measure_types": G1_MEASURE_TYPES,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": "1101",
        "prefix": "G1",
        # G1-1 审定表试算表列只读 seed（四表共享件取数）
        "tb_values": tb_values,
        # 审定表分行预填（按叶子科目名称归类到投资品种）
        "adjudication_prefill": tb_data["adjudication_prefill"],
        # 取数溯源（前端 WpFourTableSourcePanel 消费）
        "tb_source_codes": tb_source_codes,
        # 审定数回读 seed（EventBus 持久化后刷新不丢失）
        "adjudicated_amount": adjudicated_amount,
    }
