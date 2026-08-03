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
from app.services.four_table.g7_investment_buckets import (
    BUCKET_IMPAIRMENT,
    BUCKET_OTHER,
    BUCKET_OTHER_LABEL,
    CATEGORY_BUCKETS,
    MOVEMENT_NATURE_BUCKETS,
    bucket_defs_payload,
    bucket_label,
    classify_g7_leaf,
)
from app.services.four_table.leaf_aggregation import (
    LeafRow,
    aggregate_leaves,
    filter_by_prefixes,
    parent_totals,
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table import resolve_semantic_accounts
from app.services.four_table.g_cycle_specs import G7_SPEC

from ._context import RenderContext

logger = logging.getLogger(__name__)

#: G7 科目定位改走**语义驱动**（单一真源 `four_table/g_cycle_specs.G7_SPEC`）。
#: G7_SPEC 声明双槽 `gross`（长期股权投资 1511）+ `provision`（减值准备 1512）。
G7_ACCOUNT_SPEC = G7_SPEC

#: 🔴 过渡期兼容：旧 `ReportLineAccountSpec` 形态，供守卫测试直接调
#: `resolve_report_line_accounts` 验证旧路径行为（待测试全面迁移后删除）。
from app.services.four_table.report_line_accounts import ReportLineAccountSpec as _RLA
G7_RLA_SPEC = _RLA(
    row_code="BS-024",
    fallback_gross=("1511",),
    provision_row_code="IMP-009",
    fallback_provision=("1512",),
)

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
        # 逐字取自源 xlsx tab 名（守卫 openpyxl 直读比对）；旧值 `审定表G7-1` 缺科目前缀，
        # 会让 `?sheet=` 深链与公式预设的 sheet 字段分叉。
        "sheetName": "长期股权投资审定表G7-1",
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


def _r2(v: float) -> float:
    return round(float(v or 0), 2)


def _extract_codes(accounts, slot_key: str) -> list[str]:
    """从 SemanticAccountResult 或 ReportLineAccounts 提取科目码前缀集。"""
    if hasattr(accounts, "codes_of"):
        return accounts.codes_of(slot_key)
    # ReportLineAccounts 兼容（测试 fixture 仍会传入）
    if slot_key == "gross":
        return list(getattr(accounts, "gross", []))
    if slot_key == "provision":
        return list(getattr(accounts, "provision", []))
    return []


async def _load_g7_leaves(
    ctx: RenderContext,
) -> tuple[object | None, list[LeafRow], list[LeafRow]]:
    """解析 G7 科目 + 一次查询取回 `tb_balance` 行。全程 fail-open。

    Returns:
        ``(accounts, all_rows, leaves)``；解析或查询失败时 ``(accounts_or_None, [], [])``。

    🔴 已迁移到 `semantic_account_resolver`：返回的 accounts 是 `SemanticAccountResult`，
    下游消费方通过 `.codes_of("gross")` / `.codes_of("provision")` 取科目码前缀集。
    为兼容旧消费方（`build_g7_tb_values` / `build_g7_leaf_categories` / `build_g7_source_codes`
    读 `accounts.gross` / `accounts.provision` 属性），本函数返回一个适配对象。
    """
    try:
        accounts = await resolve_semantic_accounts(ctx, G7_ACCOUNT_SPEC)
    except Exception as e:  # noqa: BLE001 — 解析失败不阻断 render
        logger.warning("G7 科目解析失败: %s", e)
        return None, [], []

    prefixes = list(accounts.codes_of("gross")) + list(accounts.codes_of("provision"))
    if not prefixes:
        return accounts, [], []

    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        # 科目过滤下推 SQL（tb_balance 单项目可达百万行）；仍是**一次查询**同时取回
        # 原值组与备抵组。这里的 LIKE 只做粗筛，精确的点号边界由 filter_by_prefixes 保证。
        prefix_filter = sa.or_(
            *[TbBalance.account_code.like(f"{p}%") for p in prefixes]
        )
        result_rows = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_direction,
            ).where(sa.and_(active_filter, prefix_filter))
        )
        all_rows = to_leaf_rows(result_rows.fetchall())
    except Exception as e:  # noqa: BLE001 — 取数失败降级为空，前端允许手填
        logger.warning("G7 tb_balance 取数失败: %s", e)
        return accounts, [], []

    return accounts, all_rows, select_leaves(all_rows)


def build_g7_tb_values(
    accounts: object | None,
    all_rows: list[LeafRow],
    leaves: list[LeafRow],
) -> dict:
    """G7-1 审定表 TB 核对列的只读 seed（纯函数）。

    备抵侧 ``absolute=True``：`1512` 活体为**负值存储**，不归一会让前端显负数。
    无命中返回 ``{}``（宁缺勿造，前端手填）。
    """
    if accounts is None or not leaves:
        return {}
    gross_codes = _extract_codes(accounts, "gross")
    prov_codes = _extract_codes(accounts, "provision")
    gross = aggregate_leaves(leaves, gross_codes)
    provision = aggregate_leaves(leaves, prov_codes, absolute=True)
    gross_leaf_codes = sorted(r.account_code for r in filter_by_prefixes(leaves, gross_codes))
    prov_leaf_codes = sorted(
        r.account_code for r in filter_by_prefixes(leaves, prov_codes)
    )
    if not gross_leaf_codes and not prov_leaf_codes:
        return {}
    return {
        "opening": _r2(gross["opening"]),
        "closing": _r2(gross["closing"]),
        "impairment": _r2(provision["closing"]),
        "impairment_opening": _r2(provision["opening"]),
        "source_codes": {"gross": gross_leaf_codes, "impairment": prov_leaf_codes},
    }


def build_g7_leaf_categories(
    accounts: object | None, leaves: list[LeafRow]
) -> dict | None:
    """叶子科目 → 业务桶合计（纯函数）。分类走单一真源 `g7_investment_buckets`。

    输出 ``buckets`` 为按桶键的明细（含参与该桶的叶子码），供前端溯源与预填；
    另保留 ``cost`` / ``profit_loss`` / ``oci`` / ``other_equity`` / ``impairment``
    五个扁平键 —— 前端 `G7TabAdjudication` 的核对卡片当前读它们（Wave 2 切到
    ``buckets`` 后即删，届时守卫会要求移除）。

    未能归类的叶子进 ``unmapped``（**不并入任何桶**，宁缺勿造）。
    """
    if accounts is None or not leaves:
        return None
    gross_codes = _extract_codes(accounts, "gross")
    prov_codes = _extract_codes(accounts, "provision")
    picked = filter_by_prefixes(leaves, list(gross_codes) + list(prov_codes))
    if not picked:
        return None

    provision_prefixes = set(prov_codes)
    buckets: dict[str, dict] = {}
    unmapped: list[dict] = []
    for row in picked:
        bucket = classify_g7_leaf(row.account_name, row.account_code)
        if not bucket:
            unmapped.append(
                {
                    "code": row.account_code,
                    "name": row.account_name,
                    "amount": _r2(row.closing),
                }
            )
            continue
        # 备抵侧取绝对值（负值存储归一）；原值侧保留符号（借方合法为负的叶子存在，
        # 翻正会破坏「叶子和 == 父额」勾稽）
        is_provision = any(
            row.account_code == p or row.account_code.startswith(p + ".")
            for p in provision_prefixes
        )
        slot = buckets.setdefault(
            bucket,
            {
                "bucket": bucket,
                "label": bucket_label(bucket),
                "opening": 0.0,
                "closing": 0.0,
                "increase": 0.0,
                "decrease": 0.0,
                "codes": [],
                "is_provision": is_provision,
            },
        )
        sign_fix = abs if is_provision else (lambda v: v)
        slot["opening"] += sign_fix(row.opening)
        slot["closing"] += sign_fix(row.closing)
        # 🔴 增减方向按科目性质定：备抵是**贷方**科目，`credit_amount` 是计提（增加）、
        # `debit_amount` 是转回/核销（减少）—— 与原值侧相反。活体实证（2aa00f57 的
        # 1512）：期初 2,840,032.97 + 计提 1,950,000.00 = 期末 4,790,032.97，
        # 若照原值侧口径把 credit 当减少，roll-forward 必然不平。
        if is_provision:
            slot["increase"] += sign_fix(row.credit)
            slot["decrease"] += sign_fix(row.debit)
        else:
            slot["increase"] += sign_fix(row.debit)
            slot["decrease"] += sign_fix(row.credit)
        slot["codes"].append(row.account_code)
        slot["is_provision"] = slot["is_provision"] or is_provision

    for slot in buckets.values():
        for k in ("opening", "closing", "increase", "decrease"):
            slot[k] = _r2(slot[k])
        slot["codes"] = sorted(slot["codes"])

    def _closing(bucket: str) -> float:
        return float(buckets.get(bucket, {}).get("closing", 0.0))

    return {
        "buckets": buckets,
        # ── 以下五键为 Wave 2 前端切换前的兼容输出（切换后删）──────────────
        "cost": _r2(sum(_closing(b) for b in CATEGORY_BUCKETS)),
        "profit_loss": _closing("equity_profit"),
        "oci": _closing("oci"),
        "other_equity": _closing("other_equity"),
        "impairment": _closing(BUCKET_IMPAIRMENT),
        # ────────────────────────────────────────────────────────────────
        "unmapped": unmapped,
        "source": "tb_balance",
    }


def build_g7_adjudication_prefill(
    accounts: object | None, leaves: list[LeafRow]
) -> dict:
    """G7-1 审定表「未审数」四表预填（纯函数）。

    形态::

        {"gross": {bucket: {label, opening, increase, decrease, closing,
                            codes, roll_forward_ok}}, ,
         "impairment": {"total": {...}}}

    - 被投资单位类别桶（子公司 / 合营 / 联营）各自成行，**无叶子则该键不出现**；
    - 变动性质桶（损益调整 / 其他综合收益 / 其他权益变动）汇总到 ``other`` 桶
      —— 四表库没有「这笔调整属于哪家被投资单位」的信息，机械摊入前三类是造假；
      源模板每块第 4 行本就是空白可改名占位行（`长期股权投资审定表G7-1!A11:B11` 等）；
    - ``roll_forward_ok=False`` 时保留 ``closing`` 原值（暴露不平，不掩盖）；
    - 无任何叶子返回 ``{}``（宁缺勿造，不塞 0 骨架）。
    """
    cats = build_g7_leaf_categories(accounts, leaves)
    if not cats:
        return {}
    buckets: dict[str, dict] = cats.get("buckets") or {}

    def _row(label: str, parts: list[dict]) -> dict:
        # increase / decrease 已在 build_g7_leaf_categories 按科目性质（原值 / 备抵）定向
        opening = _r2(sum(p["opening"] for p in parts))
        increase = _r2(sum(p["increase"] for p in parts))
        decrease = _r2(sum(p["decrease"] for p in parts))
        closing = _r2(sum(p["closing"] for p in parts))
        codes = sorted(c for p in parts for c in p.get("codes", []))
        return {
            "label": label,
            "opening": opening,
            "increase": increase,
            "decrease": decrease,
            "closing": closing,
            "codes": codes,
            "roll_forward_ok": abs(_r2(opening + increase - decrease) - closing) < 0.01,
        }

    gross: dict[str, dict] = {}
    for bucket in CATEGORY_BUCKETS:
        slot = buckets.get(bucket)
        if slot:
            gross[bucket] = _row(slot["label"], [slot])

    nature_parts = [buckets[b] for b in MOVEMENT_NATURE_BUCKETS if b in buckets]
    if nature_parts:
        gross[BUCKET_OTHER] = {
            **_row(BUCKET_OTHER_LABEL, nature_parts),
            "from_buckets": [p["bucket"] for p in nature_parts],
        }

    impairment: dict[str, dict] = {}
    imp_slot = buckets.get(BUCKET_IMPAIRMENT)
    if imp_slot:
        impairment["total"] = _row(imp_slot["label"], [imp_slot])

    if not gross and not impairment:
        return {}
    out: dict = {}
    if gross:
        out["gross"] = gross
    if impairment:
        out["impairment"] = impairment
    return out


def build_g7_source_codes(
    accounts: object | None,
    all_rows: list[LeafRow],
    leaves: list[LeafRow],
) -> dict:
    """取数溯源（供前端 `WpFourTableSourcePanel` 与审计追溯）。纯函数。

    含「叶子和 vs 父科目额」两口径自检。
    已迁移到 SemanticAccountResult，直接用 `accounts.as_dict()` 输出标准溯源格式，
    并附加 G7 特有的 `parent_check`。
    """
    if accounts is None:
        return {}
    gross_codes = _extract_codes(accounts, "gross")
    prov_codes = _extract_codes(accounts, "provision")
    gross_leaf_codes = sorted(
        r.account_code for r in filter_by_prefixes(leaves, gross_codes)
    )
    prov_leaf_codes = sorted(
        r.account_code for r in filter_by_prefixes(leaves, prov_codes)
    )
    leaf_sum = _r2(aggregate_leaves(leaves, gross_codes)["closing"])
    parent = 0.0
    for prefix in gross_codes:
        parent += parent_totals(all_rows, prefix)["closing"]
    parent = _r2(parent)
    # 基于 SemanticAccountResult.as_dict() 输出标准溯源格式 + G7 扩展字段
    base = accounts.as_dict()
    base["gross"] = gross_leaf_codes
    base["provision"] = prov_leaf_codes
    base["parent_check"] = {
        "leaf_sum": leaf_sum,
        "parent": parent,
        "diff": _r2(leaf_sum - parent),
    }
    return base


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

    # 科目 + tb_balance 一次取回（fail-open）；下面的取数键全部由它派生
    accounts, all_rows, leaves = await _load_g7_leaves(ctx)
    # 🔴 account_code 来自语义解析结果，不再是常量前缀
    gross_codes = _extract_codes(accounts, "gross") if accounts else []
    prov_codes = _extract_codes(accounts, "provision") if accounts else []
    resolved_account_code = gross_codes[0] if gross_codes else "1511"
    resolved_impairment_code = prov_codes[0] if prov_codes else "1512"

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": resolved_account_code,
        "impairment_account_code": resolved_impairment_code,
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

    tb_values = build_g7_tb_values(accounts, all_rows, leaves)
    # 取数溯源（报表行 / 标准码 / 客户叶子码 / 叶子和 vs 父额自检）
    project_context["tb_source_codes"] = build_g7_source_codes(accounts, all_rows, leaves)

    # 灰度：叶子桶合计 + 审定表未审数预填；关闭/无数据为 None/{}（前端隐藏对应 UI）
    gated = bool(settings.G7_FOUR_TABLE_EXTRACTION_ENABLED)
    tb_leaf_categories = build_g7_leaf_categories(accounts, leaves) if gated else None
    adjudication_prefill = (
        build_g7_adjudication_prefill(accounts, leaves) if gated else {}
    )

    return {
        "component_type": "g7-long-term-equity-main",
        # 7 个 sheet 配置（componentType / sheetName / columns / rows）
        "sheets": G7_MAIN_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": resolved_account_code,
        "prefix": "G7",
        # G7-1 审定表试算表列只读 seed（真接线：render→html_data→FormData→组件 watch）
        "tb_values": tb_values,
        # G7-1 分类核对（叶子桶合计）；灰度关闭为 None（additive，前端隐藏核对卡片）
        "tb_leaf_categories": tb_leaf_categories,
        # G7-1 未审数四表预填（灰度关闭为 {}）
        "adjudication_prefill": adjudication_prefill,
        # 桶声明下发（前端不再抄一份中文标签 / R11.3）
        "bucket_defs": bucket_defs_payload(),
        # 审定数回读 seed（EventBus 持久化后刷新不丢失）
        "adjudicated_amount": adjudicated_amount,
    }
