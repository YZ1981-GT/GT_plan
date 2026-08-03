"""F3 应付票据 — 专属渲染策略（四表取数走平台共享件）。

**科目定位链路**（禁硬编码前缀，见 `four_table.report_line_accounts` 的模块 docstring）::

    report_config  BS-044 应付票据 = TB('2201','期末余额')      ← 四准则一致（DB 实证）
          │  resolve_report_line_accounts(ctx, F3_ACCOUNT_SPEC)
          ▼
    gross_standard = ['2201']              标准码
          │  account_mapping 反解
          ▼
    gross = ['2201']                       原始码前缀
          │  tb_balance 宽取整棵子树 + resolve_leaf_totals（叶子 + 父额勾稽自检）
          ▼
    leaves = [2201.01 银行承兑, 2201.02 商业承兑, 2201.03 信用证]
          │  classify_f3_leaf（按名称，顺序即优先级）
          ▼
    adjudication_prefill = {bank: …, commercial: …, letter_of_credit: …}

**改造前的缺陷**（本文件历史实现）

1. 硬编码 ``_F3_ACCOUNT = "2201"``，不走报表行解析。
2. ``code.startswith(_F3_ACCOUNT)`` 无点号边界（前缀 `2201` 会误吃 `22010`）；
   且**不筛叶子** —— 父科目与子科目全加 → 父子双算。
3. **完全没有 `adjudication_prefill`** —— 而 `2201.03 信用证` 是活体大额科目
   （项目 `0ec33ac9` 期末 93,443,600.00 占 2201 的 92%），四表入库后 F3-1
   审定表这笔钱无处落数、试算核对差异 = 全额。
4. `tb_values` 只有期末，而 F3-1 是**双期表**（期初数 / 期末数各四列）。
5. 无取数溯源，审计师无法追溯这个数从哪来。

spec: .kiro/specs/f-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.1~1.7 / Property 1, 2, 3, 5, 7, 13
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
from app.services.four_table.f3_note_categories import (
    build_f3_bucket_prefill,
    build_f3_leaf_categories,
    f3_category_payload,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)

F3_SHEETS = [
    "F3A",
    "F3-1",
    "F3-2",
    "F3-3",
    "F3-4",
    "F3-5",
    "F3-6",
    "F3-7",
    "附注披露信息(上市公司)",
    "附注披露信息(国企)",
]

#: 应付票据科目定位规格。``BS-044`` 在四准则下公式一致（``TB('2201','期末余额')``）；
#: 无备抵科目（应付票据是负债，不计提减值），故不声明 ``fallback_provision``。
F3_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code="BS-044",
    fallback_gross=("2201",),
    # 🔴 负债类必须声明 —— 否则 `split_gross_provision` 按「credit 即备抵」把 2201
    #   判成备抵科目，`gross_standard` 为空 → resolved_from 退化成 fallback。
    gross_direction="credit",
)

#: 兜底科目码（仅 `report_config` 解析失败时用；**不得**作为查询主路径）
_F3_FALLBACK_CODE = "2201"

#: 两口径差异容差（元）
_CROSS_CHECK_TOLERANCE = 0.01


# ─────────────────────────── 纯函数（无 DB，可单测） ───────────────────────────


def build_f3_tb_values(
    totals: LeafTotals,
    tb_row: dict[str, float] | None,
    account_code: str,
) -> dict[str, float]:
    """构造 `tb_values`（双期 + 两口径）。

    🔴 **兼容性**：键名 ``tb_values[account_code]`` 保持不变（前端
    `useF3FormData.seedTrialBalance` 与 `useF3Adjudication.tbAmountSeed` 已在读它）。

    🔴 **口径变更（有意为之）**：改造前该值优先取 `trial_balance`，现改为**优先取叶子
    聚合期末**。理由 —— 叶子口径带 ``parent_check.diff == 0`` 自证，而 `trial_balance`
    在部分项目是旧版 recalc 的父子双算陈旧数据（实证 `2aa00f57` 的 `2201` 是真值的
    2 倍：30,058,093.28 vs 15,029,046.64）。核对基准取一个无法自证且已知会错的数，
    等于让审定表「差异数」行长期显示假差异。

    `trial_balance` 口径仍下发在 ``{code}_closing_tb``，由溯源面板并列展示 + 差异提示，
    审计师能看到两个数而不是被静默误导（Property 13）。

    Returns:
        ``{code, code_opening, code_closing_leaf, code_opening_leaf,
           code_closing_tb, code_unadjusted_tb, code_audited_tb}``（值为 0 的键仍下发，
        让前端能区分「取到 0」与「没取到」）。
    """
    code = str(account_code or _F3_FALLBACK_CODE)
    leaf_close = round(totals.closing, 2)
    leaf_open = round(totals.opening, 2)
    tb_unadj = round(abs(float((tb_row or {}).get("unadjusted") or 0)), 2)
    tb_audited = round(abs(float((tb_row or {}).get("audited") or 0)), 2)
    tb_close = tb_audited if abs(tb_audited) > 1e-9 else tb_unadj

    # 叶子口径优先（可自证）；四表无该科目族数据时才回退 trial_balance
    authoritative = leaf_close if totals.leaf_codes else tb_close

    return {
        code: authoritative,
        f"{code}_opening": leaf_open,
        f"{code}_closing_leaf": leaf_close,
        f"{code}_opening_leaf": leaf_open,
        f"{code}_closing_tb": tb_close,
        f"{code}_unadjusted_tb": tb_unadj,
        f"{code}_audited_tb": tb_audited,
    }


def build_f3_cross_check(
    totals: LeafTotals, tb_row: dict[str, float] | None
) -> dict:
    """两口径核对（叶子聚合 vs `trial_balance`），差异由前端溯源面板 danger 展示。

    ⚠️ `trial_balance` 在部分项目存在旧版 recalc 的父子双算陈旧数据（spec Notes G1），
    故**不能**静默取其一 —— 差异必须可见（Property 13）。
    """
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


def build_f3_source_codes(
    accounts: ReportLineAccounts,
    totals: LeafTotals,
    tb_row: dict[str, float] | None,
) -> dict:
    """取数溯源（前端 `F3FourTableSourcePanel` 消费，非 dead output）。"""
    out = {
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
        "tb_cross_check": build_f3_cross_check(totals, tb_row),
        "categories": f3_category_payload(),
    }
    return out


def build_f3_adjudication_prefill(
    rows: list[LeafRow], account_code: str
) -> dict[str, dict] | None:
    """按票据种类预填 F3-1 审定表未审数（双期）。

    🔴 **宁缺勿造**：项目科目表只有父科目 `2201`（无子科目）时返回 ``None`` ——
    此时把父额整笔塞进「银行承兑汇票」是造假，审定表应回退手工录入
    （试算核对行仍有总额，不影响核对）。

    Returns:
        ``{bucket_key: {"opening","closing","label","codes"}}`` 或 ``None``。
    """
    code = str(account_code or _F3_FALLBACK_CODE)
    leaves = [r for r in select_leaves(rows) if r.account_code != code]
    if not leaves:
        return None
    sign_map = leaf_sign_map(rows, code)
    categories = build_f3_leaf_categories(leaves, sign_map)
    prefill = build_f3_bucket_prefill(categories)
    return prefill or None


def build_f3_leaf_category_payload(
    rows: list[LeafRow], account_code: str
) -> list[dict]:
    """逐叶子归类明细（溯源面板「叶子归类」表，`ambiguous` 行标黄提示复核）。"""
    code = str(account_code or _F3_FALLBACK_CODE)
    leaves = [r for r in select_leaves(rows) if r.account_code != code]
    if not leaves:
        return []
    sign_map = leaf_sign_map(rows, code)
    return [c.as_dict() for c in build_f3_leaf_categories(leaves, sign_map)]


# ─────────────────────────────── DB 访问 ──────────────────────────────────────


async def _resolve_f3_accounts(ctx: RenderContext) -> ReportLineAccounts:
    """解析 F3 科目（报表映射规则驱动；共享件内部已 fail-open）。"""
    return await resolve_report_line_accounts(ctx, F3_ACCOUNT_SPEC)


def _primary_code(accounts: ReportLineAccounts) -> str:
    """取用于叶子聚合与勾稽的主科目原始码（极小前缀集的第一个）。"""
    for c in accounts.gross:
        if c:
            return c
    return _F3_FALLBACK_CODE


async def render(ctx: RenderContext) -> dict | None:
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND (item_id LIKE :pfx OR item_id LIKE 'F3A%') LIMIT 800"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "F3-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:
        logger.warning("F3 render failed: %s", e)

    # 项目上下文
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
        "bs_date": "",
        # 取数溯源（前端 F3FourTableSourcePanel 消费）
        "tb_source_codes": {},
    }
    try:
        proj_row = (
            await ctx.db.execute(
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
        logger.warning("F3 render: project context 查询失败: %s", e)

    # ─── 四表取数：报表行解析 → 叶子聚合（含父额勾稽）→ 分类预填 ────────────────
    accounts = await _resolve_f3_accounts(ctx)
    code = _primary_code(accounts)
    rows = await fetch_tb_subtree(ctx.db, ctx.project_id, ctx.year, accounts.gross)
    totals = resolve_leaf_totals(rows, code)
    tb_row = await fetch_trial_balance_amounts(
        ctx.db, ctx.project_id, ctx.year, accounts.gross_standard
    )

    tb_values = build_f3_tb_values(totals, tb_row, code)
    project_context["tb_source_codes"] = build_f3_source_codes(accounts, totals, tb_row)
    adjudication_prefill = build_f3_adjudication_prefill(rows, code)
    leaf_categories = build_f3_leaf_category_payload(rows, code)

    return {
        "component_type": "f3-notes-payable",
        "account_code": code,
        "prefix": "F3",
        "sheets": F3_SHEETS,
        "project_context": project_context,
        "tb_values": tb_values,
        "adjudication_prefill": adjudication_prefill,
        "leaf_categories": leaf_categories,
        "responses_snapshot": responses_snapshot,
    }
