"""F5 营业成本 — 专属渲染策略（四表取数走平台共享件）。

**科目定位链路**::

    report_config  IS-002 减：营业成本 = SUM_TB('6401~6499','本期发生额')  ← 四准则一致
          │  resolve_report_line_accounts(ctx, F5_ACCOUNT_SPEC)
          ▼
    区间规格 → sql_prefixes_for_specs 宽取 → filter_by_code_specs 精确收敛
          │  classify_f5_leaf（按名称；未命中不并入）
          ▼
    adjudication_prefill = {main: 主营业务成本, other: 其他业务成本}

**改造前的三个缺陷**

1. **裸 SQL ``standard_account_code LIKE '6401%'`` 漏掉全部其他业务成本** ——
   `6402` / `6404`（实证 6 个项目 `6402` 是「其他业务成本」、`df5b8403` 的 `6402` 是
   「其他业务支出」而 `6404` 才是「其他业务成本」）→ F5-1「试算平衡表数」少算，
   「差异数」行常亮假告警。
2. **`_ROLLFORWARD_ACCOUNTS` 的科目名标错** —— 原写
   ``1401 原材料 / 1404 在产品 / 1405 产成品``，但两个标准科目表变体里
   ``1401`` 都是**材料采购**（全库期末 0.00）、``1403`` 才是原材料、
   ``1405`` 在变体 A 是自制半成品 / 变体 B 是库存商品 →
   F5-7 成本倒轧表的期初 / 期末材料、在产品、产成品**全部取错**。
   改为复用 F2 已建的按名称分类真源 `f2_extraction.category_rules`。
3. ``code.startswith(prefix)`` 无点号边界且**不筛叶子** → 父子双算。

**损益类取数口径**（Requirement 3.2 / Property 6）

`tb_balance` 损益类在含年末结转损益的全年账上 ``debit_amount == credit_amount``，
实证 `2aa00f57` 的 `6401` 四行 ``debit − credit`` 全为 0.00 → **必须取叶子
`debit_amount` 之和**。按名称归类后的合计与 `trial_balance` 的 ``6401+6402+6404``
在 6 个项目上分文不差（另 3 个的差异已定位为 `trial_balance` 侧陈旧数据，见 spec Notes）。

spec: .kiro/specs/f-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 3.1~3.6 / Property 1, 2, 3, 4, 6, 13
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.services.f2_extraction.category_rules import classify_f2_leaf, top_level_code
from app.services.four_table import (
    LeafRow,
    ReportLineAccounts,
    ReportLineAccountSpec,
    fetch_tb_subtree,
    fetch_trial_balance_amounts,
    filter_by_code_specs,
    resolve_semantic_accounts,
    select_leaves,
    sql_prefixes_for_specs,
)
from app.services.four_table.f_cycle_specs import F5_SPEC
from app.services.four_table.f5_cost_segments import (
    build_f5_leaf_segments,
    build_f5_segment_prefill,
    build_f5_unmapped,
    f5_segment_payload,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)

#: 营业成本科目定位规格。``IS-002`` 是**区间口径** ``SUM_TB('6401~6499')``。
#:
#: ⚠️ 该区间**过宽** —— 会把 ``6403 税金及附加``（独立报表行 ``IS-003``）圈进来。
#: 收敛靠 `f5_cost_segments.classify_f5_leaf` 按名称归类 + 未命中不并入
#: （实证：排除后与 `trial_balance` 的 6401+6402+6404 分文不差）。
F5_ACCOUNT_SPEC = F5_SPEC

#: 存货报表行（供 F5-7 成本倒轧表取原材料 / 在产品 / 产成品）
_F5_INVENTORY_SPEC = ReportLineAccountSpec(
    row_code="BS-010",
    fallback_gross=("1401~1499",),
)

#: F2 分类 rowKey → F5-7 成本倒轧表字段名。
#:
#: 🔴 用**分类 rowKey** 而非科目编码 —— 存货编码语义在项目间冲突
#: （见 `f2_extraction.category_rules` 的两变体对照表）。
_ROLLFORWARD_BY_CATEGORY: dict[str, tuple[str, str]] = {
    "raw-materials": ("openingMaterial", "closingMaterial"),
    "semi-finished": ("openingWIP", "closingWIP"),
    "finished-goods": ("openingFG", "closingFG"),
}

_CROSS_CHECK_TOLERANCE = 0.01


# ─────────────────────────── 纯函数（无 DB，可单测） ───────────────────────────


def build_f5_rollforward(rows: list[LeafRow], specs) -> dict[str, float]:
    """按 F2 分类真源归集 F5-7 成本倒轧表的期初 / 期末（原材料 / 在产品 / 产成品）。

    只汇总**叶子**（避免父子双算），归类走 `classify_f2_leaf`（叶子名未命中回退
    父级一级科目名）。未命中三类的存货科目不参与（不塞进任一格）。
    """
    scoped = filter_by_code_specs(rows, specs)
    if not scoped:
        return {}
    name_by_top = {
        r.account_code: r.account_name for r in rows if "." not in r.account_code
    }
    out: dict[str, float] = {}
    for row in select_leaves(scoped):
        category = classify_f2_leaf(
            row.account_name, name_by_top.get(top_level_code(row.account_code))
        )
        pair = _ROLLFORWARD_BY_CATEGORY.get(category)
        if pair is None:
            continue
        open_key, close_key = pair
        out[open_key] = round(out.get(open_key, 0.0) + row.opening, 2)
        out[close_key] = round(out.get(close_key, 0.0) + row.closing, 2)
    return out


def build_f5_cost_leaves(rows: list[LeafRow], specs) -> list[LeafRow]:
    """从宽取结果精确收敛到 ``6401~6499`` 区间的叶子。"""
    scoped = filter_by_code_specs(rows, specs)
    return select_leaves(scoped)


def build_f5_trial_balance_codes(segments) -> list[str]:
    """`trial_balance` 对照查询用的标准码集 = **已归类叶子的一级科目段**。

    🔴 **不能直接把 `IS-002` 的区间 `6401~6499` 拿去查 `trial_balance`** —— 那样
    对照口径里混着 ``6403 税金及附加``，两口径差异恒等于 6403 金额，把真正的问题
    （`trial_balance` 陈旧父子双算）淹没在噪声里。

    实证 `0ec33ac9`：区间口径查出 813,478,667.33（含 6403 的 3,231,580.11），
    按已归类一级段 ``['6401']`` 查出 810,247,087.22 → 与叶子口径**分文不差**。

    未归类叶子（6403）不进查询码集，故两口径覆盖同一科目集合，差异才有诊断意义。
    """
    codes = {
        str(s.code or "").split(".", 1)[0]
        for s in segments or []
        if not s.unmatched and s.code
    }
    return sorted(c for c in codes if c)


def build_f5_tb_amounts(
    cost_total: float, tb_row: dict[str, float] | None
) -> dict[str, float]:
    """构造 F5-1「试算平衡表数」核对基准。

    🔴 **语义变更（待用户确认，见 spec 的「待用户裁决」2）**：``tb_amount`` 原本是
    「`trial_balance` 的 6401 主营业务成本」，现改为**营业成本合计**（主营 + 其他），
    与报表行 `IS-002` 口径一致；原口径的值移到 ``tb_amount_main`` 保留。

    取值优先级 = 叶子聚合合计（口径可自证）→ `trial_balance`。这与资产负债类
    （F3/F4 以 `trial_balance` 为核对基准）相反，因为损益类的 `trial_balance`
    存在**结构性口径缺陷**（``debit − credit`` 恒为 0，见 spec Notes G2）。
    """
    tb_unadj = round(float((tb_row or {}).get("unadjusted") or 0), 2)
    tb_audited = round(float((tb_row or {}).get("audited") or 0), 2)
    tb_close = tb_audited if abs(tb_audited) > 1e-9 else tb_unadj
    leaf_total = round(cost_total, 2)
    return {
        "tb_amount": leaf_total if abs(leaf_total) > 1e-9 else tb_close,
        "tb_amount_unadjusted": tb_unadj,
        "tb_amount_audited": tb_audited,
        "tb_amount_leaf": leaf_total,
        "tb_amount_tb": tb_close,
    }


def build_f5_cross_check(
    cost_total: float, tb_row: dict[str, float] | None
) -> dict:
    """两口径核对（叶子借方聚合 vs `trial_balance`）。差异必须可见。

    ⚠️ 本循环的差异**大概率非零且是 `trial_balance` 侧的问题**：实证 `2aa00f57`
    该表的 6401 是叶子口径的 3 倍（旧版 recalc 父子双算），`4f6dbc36` /
    `f064f5e4` 该年无记录。溯源面板据此提示「建议重跑试算平衡表」。
    """
    if tb_row is None:
        return {
            "leaf_total": round(cost_total, 2),
            "trial_balance_total": None,
            "diff": None,
            "available": False,
        }
    tb_audited = float(tb_row.get("audited") or 0)
    tb_unadj = float(tb_row.get("unadjusted") or 0)
    tb_close = tb_audited if abs(tb_audited) > 1e-9 else tb_unadj
    diff = round(cost_total - tb_close, 2)
    return {
        "leaf_total": round(cost_total, 2),
        "trial_balance_total": round(tb_close, 2),
        "diff": diff,
        "available": True,
        "matched": abs(diff) <= _CROSS_CHECK_TOLERANCE,
    }


def build_f5_source_codes(
    accounts: ReportLineAccounts,
    leaves: list[LeafRow],
    cost_total: float,
    unmapped: list[dict],
    tb_row: dict[str, float] | None,
    tb_codes: list[str] | None = None,
) -> dict:
    """取数溯源（前端 `F5FourTableSourcePanel` 消费）。"""
    return {
        "row_code": accounts.row_code,
        "resolved_from": accounts.resolved_from,
        "formula": accounts.formula,
        "gross_standard": list(accounts.gross_standard),
        "gross": list(accounts.gross),
        "leaf_codes": sorted(r.account_code for r in leaves),
        "leaf_total_debit": round(cost_total, 2),
        "trial_balance_codes": list(tb_codes or []),
        # 被区间圈进来但按名称判定不属营业成本的科目（典型 = 6403 税金及附加）
        "excluded": unmapped,
        "excluded_total": round(sum(float(u.get("debit") or 0) for u in unmapped), 2),
        "tb_cross_check": build_f5_cross_check(cost_total, tb_row),
        "segments": f5_segment_payload(),
    }


# ────────────────────────────────── render ───────────────────────────────────


async def render(ctx: RenderContext) -> dict | None:
    responses_snapshot: dict = {}
    adjudicated_cogs = ""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 800"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "F5-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
        # F5-7 校验区回退：读取已持久化的审定营业成本
        adjudicated_cogs = responses_snapshot.get("F5-7-adjudicated-cogs", {}).get("remark", "")
    except Exception as e:  # noqa: BLE001
        logger.warning("F5 render failed: %s", e)

    # ─── project_context ─────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "bs_date": "",
        "related_parties": [],
        "tb_amount": 0,
        "tb_amount_unadjusted": 0,
        "tb_amount_audited": 0,
        "tb_source_codes": {},
    }
    try:
        proj_row = (
            await ctx.db.execute(
                sa.text("SELECT client_name, audit_year FROM projects WHERE id = :pid"),
                {"pid": str(ctx.project_id)},
            )
        ).fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("F5 render: project context failed: %s", e)

    # ─── 关联方清单 ──────────────────────────────────────────────────────
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
        project_context["related_parties"] = [r.name for r in rp_rows if r.name]
    except Exception as e:  # noqa: BLE001
        logger.warning("F5 render: related_parties failed: %s", e)

    # ─── 四表取数：营业成本（IS-002 区间口径，按名称收敛）────────────────────
    accounts = await resolve_semantic_accounts(ctx, F5_ACCOUNT_SPEC)
    cost_specs = list(accounts.gross) or list(F5_ACCOUNT_SPEC.fallback_gross)
    cost_rows = await fetch_tb_subtree(
        ctx.db, ctx.project_id, ctx.year, sql_prefixes_for_specs(cost_specs)
    )
    cost_leaves = build_f5_cost_leaves(cost_rows, cost_specs)
    segments = build_f5_leaf_segments(cost_leaves)
    segment_prefill = build_f5_segment_prefill(segments)
    unmapped = build_f5_unmapped(segments)
    cost_total = sum(float(v.get("amount") or 0) for v in segment_prefill.values())

    # 🔴 对照口径必须与叶子口径**同科目集**（排除 6403），见 build_f5_trial_balance_codes
    tb_codes = build_f5_trial_balance_codes(segments) or ["6401", "6402", "6404"]
    tb_row = await fetch_trial_balance_amounts(
        ctx.db, ctx.project_id, ctx.year, tb_codes
    )
    project_context.update(build_f5_tb_amounts(cost_total, tb_row))
    project_context["tb_amount_main"] = float(
        (segment_prefill.get("main") or {}).get("amount") or 0
    )
    project_context["tb_source_codes"] = build_f5_source_codes(
        accounts, cost_leaves, cost_total, unmapped, tb_row, tb_codes
    )

    # ─── F5-7 成本倒轧：原材料 / 在产品 / 产成品（走 F2 分类真源，不猜编码）──────
    inv_accounts = await resolve_semantic_accounts(ctx, _F5_INVENTORY_SPEC)
    inv_specs = list(inv_accounts.gross) or list(_F5_INVENTORY_SPEC.fallback_gross)
    inv_rows = await fetch_tb_subtree(
        ctx.db, ctx.project_id, ctx.year, sql_prefixes_for_specs(inv_specs)
    )
    rollforward_tb = build_f5_rollforward(inv_rows, inv_specs)

    return {
        "account_code": (accounts.gross_standard or ["6401"])[0],
        "responses_snapshot": responses_snapshot,
        "prefix": "F5",
        "rollforward_tb": rollforward_tb,
        "adjudicated_cogs": adjudicated_cogs,
        "project_context": project_context,
        "adjudication_prefill": segment_prefill or None,
        "leaf_categories": [s.as_dict() for s in segments],
    }
