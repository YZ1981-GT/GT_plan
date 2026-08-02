"""F4 应付账款 — 专属渲染策略（四表取数走平台共享件）。

componentType: f4-accounts-payable

**科目定位链路**::

    report_config  BS-045 应付账款 = TB('2202','期末余额')      ← 四准则一致（DB 实证）
          │  resolve_report_line_accounts(ctx, F4_ACCOUNT_SPEC)
          ▼
    gross = ['2202'] → tb_balance 宽取子树 → resolve_leaf_totals（叶子 + 父额勾稽）
          │  classify_f4_leaf（按名称，顺序即优先级）
          ▼
    adjudication_prefill = {goods, construction, equipment, service, other}

**改造前的缺陷**

1. 裸 SQL ``standard_account_code LIKE '2202%'``，不走报表行解析。
2. 只给一个标量 `tb_amount`（期末），而 F4-1 是**双期表**（期初数 / 期末数各四列）
   → 期初「试算平衡表数」行永远为 0、期初差异 = 全额假差异。
3. **完全没有 `adjudication_prefill`** —— 而客户 `2202` 子科目天然对应 F4-1
   「一、按照性质分类」五桶（实证 `2202.01 应付货款`→货款 / `2202.11 工程设备款`→工程款
   / `2202.96 门店统购款`→货款），四表入库后按性质区全零。
4. 无叶子聚合（`trial_balance` 侧在部分项目有父子双算陈旧数据，见 spec Notes G1）。
5. 无取数溯源。

spec: .kiro/specs/f-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 2.1~2.7 / Property 1, 2, 3, 5, 7, 13
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.services.four_table import (
    LeafRow,
    LeafTotals,
    ReportLineAccounts,
    ReportLineAccountSpec,
    fetch_tb_subtree,
    fetch_trial_balance_amounts,
    leaf_sign_map,
    resolve_leaf_totals,
    resolve_report_line_accounts,
    select_leaves,
)
from app.services.four_table.f4_nature_buckets import (
    build_f4_leaf_natures,
    build_f4_nature_prefill,
    f4_bucket_payload,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)

F4_SHEETS = [
    "F4A",
    "F4-1",
    "附注披露(上市)",
    "附注披露(国企)",
    "F4-2",
    "F4-3",
    "F4-4",
    "F4-5",
    "F4-6",
    "F4-7",
    "F4-8",
    "F4-9",
]

#: 应付账款科目定位规格（``BS-045`` 四准则公式一致；负债无备抵科目）
F4_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code="BS-045",
    fallback_gross=("2202",),
    # 🔴 负债类必须声明（见 `ReportLineAccountSpec.gross_direction` 的说明）
    gross_direction="credit",
)

_F4_FALLBACK_CODE = "2202"
_CROSS_CHECK_TOLERANCE = 0.01


# ─────────────────────────── 纯函数（无 DB，可单测） ───────────────────────────


def build_f4_tb_amounts(
    totals: LeafTotals, tb_row: dict[str, float] | None
) -> dict[str, float]:
    """构造 F4-1「试算平衡表数」双期核对基准。

    🔴 **兼容性**：键名 ``tb_amount`` / ``tb_amount_unadjusted`` / ``tb_amount_audited``
    保持不变（前端 `f4TbAmount` inject 与 `useF4Adjudication.tbAmountSeed` 已在读）。

    🔴 **口径变更（有意为之，同 F3）**：``tb_amount`` 改为**优先取叶子聚合期末** ——
    叶子口径带 ``parent_check.diff == 0`` 自证，而 `trial_balance` 在部分项目是旧版
    recalc 的父子双算陈旧数据（实证 `2aa00f57` 的 `2202` 是真值 2 倍：534,617,953.54
    vs 267,308,976.77）。`trial_balance` 口径仍下发在 ``tb_amount_tb`` 供并列核对。

    Returns:
        含 ``tb_amount`` / ``tb_amount_opening`` / ``tb_amount_closing_leaf`` /
        ``tb_amount_opening_leaf`` / ``tb_amount_unadjusted`` / ``tb_amount_audited``
        / ``tb_amount_tb``。
    """
    tb_unadj = round(abs(float((tb_row or {}).get("unadjusted") or 0)), 2)
    tb_audited = round(abs(float((tb_row or {}).get("audited") or 0)), 2)
    tb_close = tb_audited if abs(tb_audited) > 1e-9 else tb_unadj
    leaf_close = round(totals.closing, 2)
    leaf_open = round(totals.opening, 2)
    return {
        # 叶子口径优先（可自证）；四表无该科目族数据时才回退 trial_balance
        "tb_amount": leaf_close if totals.leaf_codes else tb_close,
        "tb_amount_tb": tb_close,
        "tb_amount_unadjusted": tb_unadj,
        "tb_amount_audited": tb_audited,
        # 🔴 新增：`trial_balance` v2 只有期末，故期初只能取叶子聚合口径
        "tb_amount_opening": leaf_open,
        "tb_amount_closing_leaf": leaf_close,
        "tb_amount_opening_leaf": leaf_open,
    }


def build_f4_cross_check(
    totals: LeafTotals, tb_row: dict[str, float] | None
) -> dict:
    """两口径核对（叶子聚合 vs `trial_balance`）。差异必须可见，不静默取其一。"""
    if tb_row is None:
        return {
            "leaf_closing": round(totals.closing, 2),
            "trial_balance_closing": None,
            "diff": None,
            "available": False,
        }
    tb_audited = abs(float(tb_row.get("audited") or 0))
    tb_unadj = abs(float(tb_row.get("unadjusted") or 0))
    tb_close = tb_audited if abs(tb_audited) > 1e-9 else tb_unadj
    diff = round(totals.closing - tb_close, 2)
    return {
        "leaf_closing": round(totals.closing, 2),
        "trial_balance_closing": round(tb_close, 2),
        "diff": diff,
        "available": True,
        "matched": abs(diff) <= _CROSS_CHECK_TOLERANCE,
    }


def build_f4_source_codes(
    accounts: ReportLineAccounts,
    totals: LeafTotals,
    tb_row: dict[str, float] | None,
) -> dict:
    """取数溯源（前端 `F4FourTableSourcePanel` 消费）。"""
    return {
        "row_code": accounts.row_code,
        "resolved_from": accounts.resolved_from,
        "formula": accounts.formula,
        "gross_standard": list(accounts.gross_standard),
        "gross": list(accounts.gross),
        "leaf_codes": list(totals.leaf_codes),
        "convention": dict(totals.convention),
        "parent_check": {
            "leaf_opening": round(totals.opening, 2),
            "leaf_closing": round(totals.closing, 2),
            "parent_opening": round(totals.parent.get("opening", 0.0), 2),
            "parent_closing": round(totals.parent.get("closing", 0.0), 2),
            "diff": {k: round(v, 2) for k, v in (totals.diff or {}).items()},
            "matched": totals.matched,
        },
        "tb_cross_check": build_f4_cross_check(totals, tb_row),
        "buckets": f4_bucket_payload(),
    }


def build_f4_adjudication_prefill(
    rows: list[LeafRow], account_code: str
) -> dict[str, dict] | None:
    """按款项性质预填 F4-1「一、按照性质分类」未审数（双期）。

    🔴 宁缺勿造：无子科目时返回 ``None``（把父额整笔塞进「货款」是造假）。
    """
    code = str(account_code or _F4_FALLBACK_CODE)
    leaves = [r for r in select_leaves(rows) if r.account_code != code]
    if not leaves:
        return None
    natures = build_f4_leaf_natures(leaves, leaf_sign_map(rows, code))
    return build_f4_nature_prefill(natures) or None


def build_f4_leaf_nature_payload(
    rows: list[LeafRow], account_code: str
) -> list[dict]:
    """逐叶子归类明细（溯源面板；`2202.11 工程设备款` 会标 ``ambiguous``）。"""
    code = str(account_code or _F4_FALLBACK_CODE)
    leaves = [r for r in select_leaves(rows) if r.account_code != code]
    if not leaves:
        return []
    return [n.as_dict() for n in build_f4_leaf_natures(leaves, leaf_sign_map(rows, code))]


def _primary_code(accounts: ReportLineAccounts) -> str:
    for c in accounts.gross:
        if c:
            return c
    return _F4_FALLBACK_CODE


# ────────────────────────────────── render ───────────────────────────────────


async def render(ctx: RenderContext) -> dict | None:
    db = ctx.db
    wp_id = str(ctx.wp_id)

    # ─── checklist_responses 快照 ────────────────────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND (item_id LIKE :pfx OR item_id LIKE 'F4A%') LIMIT 800"
            ),
            {"wp_id": wp_id, "pfx": "F4-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:
        logger.warning("F4 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ───────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
        "bs_date": "",
        "related_parties": [],
        "tb_amount": 0,
        "tb_amount_unadjusted": 0,
        "tb_amount_audited": 0,
        # 取数溯源（前端 F4FourTableSourcePanel 消费）
        "tb_source_codes": {},
    }
    try:
        proj_row = (
            await db.execute(
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
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("F4 render: project context 查询失败: %s", e)

    # ─── 关联方清单（related_party_registry） ────────────────────────────
    try:
        rp_rows = (
            await db.execute(
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
        logger.warning("F4 render: related_parties 查询失败: %s", e)

    # ─── 四表取数：报表行解析 → 叶子聚合（含父额勾稽）→ 性质预填 ──────────────
    accounts = await _resolve_f4_accounts(ctx)
    code = _primary_code(accounts)
    rows = await fetch_tb_subtree(db, ctx.project_id, ctx.year, accounts.gross)
    totals = resolve_leaf_totals(rows, code)
    tb_row = await fetch_trial_balance_amounts(
        db, ctx.project_id, ctx.year, accounts.gross_standard
    )

    project_context.update(build_f4_tb_amounts(totals, tb_row))
    project_context["tb_source_codes"] = build_f4_source_codes(accounts, totals, tb_row)

    return {
        "component_type": "f4-accounts-payable",
        "account_code": code,
        "prefix": "F4",
        "sheets": F4_SHEETS,
        "project_context": project_context,
        "adjudication_prefill": build_f4_adjudication_prefill(rows, code),
        "leaf_categories": build_f4_leaf_nature_payload(rows, code),
        "responses_snapshot": responses_snapshot,
    }


async def _resolve_f4_accounts(ctx: RenderContext) -> ReportLineAccounts:
    """解析 F4 科目（报表映射规则驱动；共享件内部已 fail-open）。"""
    return await resolve_report_line_accounts(ctx, F4_ACCOUNT_SPEC)
