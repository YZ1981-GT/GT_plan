"""K1 其他应收款 — 专属渲染策略.

componentType: k1-other-receivables
科目 1221 其他应收款（借方/资产类）+ 坏账准备（贷方/资产备抵类）。

返回 allResponses + projectContext + TB数据(1221+坏账准备)
+ adjudication_prefill（无持久化审定未审数时从 tb_balance 预填）
供前端 K1-1 审定表试算表列（只读）seed / 期后回款窗口。
"""

from __future__ import annotations

import logging
import re

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1221其他应收款(借方/资产类) + 1231坏账准备(贷方/备抵类)
_K1_ACCOUNT_PREFIXES = {
    "1221": ("receivable_unadjusted", "receivable_audited"),  # 其他应收款
    "1231": ("bad_debt_unadjusted", "bad_debt_audited"),  # 坏账准备
}

# 款项性质关键词 → K1-1 nature syncKey
_NATURE_RULES: list[tuple[str, str]] = [
    (r"保证金", "margin"),
    (r"押金", "deposit"),
    (r"备用金", "petty"),
    (r"往来|代垫|关联", "intercompany"),
]

K1_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k1-other-receivables"},
    {"sheet_name": "其他应收款实质性程序表K1A", "component_type": "k1-other-receivables"},
    {"sheet_name": "审定表K1-1", "component_type": "k1-other-receivables"},
    {"sheet_name": "明细表K1-2", "component_type": "k1-other-receivables"},
    {"sheet_name": "坏账准备明细表K1-3", "component_type": "k1-other-receivables"},
    {"sheet_name": "调整分录汇总K1-4", "component_type": "k1-other-receivables"},
    {"sheet_name": "大额其他应收款情况分析表K1-5", "component_type": "k1-other-receivables"},
    {"sheet_name": "信用减值损失会计政策检查K1-6", "component_type": "k1-other-receivables"},
    {"sheet_name": "三阶段划分检查表K1-7", "component_type": "k1-other-receivables"},
    {"sheet_name": "坏账准备测算K1-8", "component_type": "k1-other-receivables"},
    {"sheet_name": "坏账准备转回收回核销检查表K1-9", "component_type": "k1-other-receivables"},
    {"sheet_name": "长期未收回款项检查表K1-10", "component_type": "k1-other-receivables"},
    {"sheet_name": "关联方及交易检查表K1-11", "component_type": "k1-other-receivables"},
    {"sheet_name": "其他应收款检查表K1-12", "component_type": "k1-other-receivables"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "k1-other-receivables"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "k1-other-receivables"},
]


def _classify_nature(name: str) -> str:
    text = (name or "").strip()
    for pattern, key in _NATURE_RULES:
        if re.search(pattern, text):
            return key
    return "other-nature"


def _row_depth(code: str, prefix: str) -> int:
    """1221→0 / 1221.01→1 / 1221.01.02→2."""
    if code == prefix:
        return 0
    rest = code[len(prefix) :].lstrip(".")
    if not rest:
        return 0
    return len(rest.split("."))


def _aggregate_prefix_deepest(
    rows: list,
    prefix: str,
    *,
    abs_amount: bool = False,
) -> dict[str, float]:
    """按最深明细层级汇总，避免父子科目重复计数."""
    by_depth: dict[int, list] = {}
    for r in rows:
        code = (r.account_code or "").strip()
        if not (code == prefix or code.startswith(prefix)):
            continue
        depth = _row_depth(code, prefix)
        by_depth.setdefault(depth, []).append(r)
    if not by_depth:
        return {"opening": 0.0, "closing": 0.0, "debit": 0.0, "credit": 0.0}
    chosen = by_depth[max(by_depth.keys())]
    opening = sum(float(r.opening_balance or 0) for r in chosen)
    closing = sum(float(r.closing_balance or 0) for r in chosen)
    debit = sum(float(getattr(r, "debit_amount", 0) or 0) for r in chosen)
    credit = sum(float(getattr(r, "credit_amount", 0) or 0) for r in chosen)
    if abs_amount:
        opening, closing = abs(opening), abs(closing)
        debit, credit = abs(debit), abs(credit)
    return {
        "opening": opening,
        "closing": closing,
        "debit": debit,
        "credit": credit,
    }


async def _fetch_tb_balance_rows(ctx: RenderContext) -> list:
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
            ).where(active_filter)
        )
        return list(result.fetchall())
    except Exception as e:  # noqa: BLE001
        logger.warning("K1 TB balance fetch failed: %s", e)
        return []


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1221+1231的期初/期末余额及借贷发生额（最深层级，防重复计数）."""
    tb: dict[str, float] = {}
    rows = await _fetch_tb_balance_rows(ctx)
    if rows:
        for prefix, (unadj_key, _audited_key) in _K1_ACCOUNT_PREFIXES.items():
            agg = _aggregate_prefix_deepest(rows, prefix, abs_amount=(prefix == "1231"))
            tb[f"{unadj_key}_opening"] = agg["opening"]
            tb[f"{unadj_key}_closing"] = agg["closing"]
            tb[f"{unadj_key}_debit"] = agg["debit"]
            tb[f"{unadj_key}_credit"] = agg["credit"]

    # 从 trial_balance 取未审数/审定数
    try:
        result = await ctx.db.execute(
            sa.text(
                """
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND (standard_account_code LIKE '1221%' OR standard_account_code LIKE '1231%')
            """
            ),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _K1_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("K1 trial_balance fetch failed: %s", e)

    return tb


async def _build_adjudication_prefill(ctx: RenderContext) -> dict:
    """无持久化审定未审数时，从 tb_balance 预填 K1-1 组合/性质行.

    返回::
        {
          "receivable_total": {"opening", "closing", "debit", "credit"},
          "bad_debt_total": {...},
          "nature": { syncKey: {"opening", "closing"}, ... },
          "portfolio": { "aging"|"individual"|...: {"opening", "closing"}, ... },
        }
    """
    rows = await _fetch_tb_balance_rows(ctx)
    if not rows:
        return {}

    rec = _aggregate_prefix_deepest(rows, "1221", abs_amount=False)
    bd = _aggregate_prefix_deepest(rows, "1231", abs_amount=True)

    # 性质分布：仅取 1221 最深叶子明细，按科目名称归类
    by_depth: dict[int, list] = {}
    for r in rows:
        code = (r.account_code or "").strip()
        if not (code == "1221" or code.startswith("1221")):
            continue
        depth = _row_depth(code, "1221")
        by_depth.setdefault(depth, []).append(r)

    nature: dict[str, dict[str, float]] = {}
    if by_depth:
        leaves = by_depth[max(by_depth.keys())]
        # 若只有一级科目本身，无法拆性质 → 整笔进「其他」
        for r in leaves:
            name = (getattr(r, "account_name", None) or "").strip()
            key = _classify_nature(name) if name else "other-nature"
            bucket = nature.setdefault(key, {"opening": 0.0, "closing": 0.0})
            bucket["opening"] += float(r.opening_balance or 0)
            bucket["closing"] += float(r.closing_balance or 0)

    # 组合：无明细分类时默认全部进账龄组合；有性质拆分时仍把总额放账龄组合作未审兜底
    portfolio: dict[str, dict[str, float]] = {
        "aging": {"opening": rec["opening"], "closing": rec["closing"]},
    }
    portfolio_bd: dict[str, dict[str, float]] = {
        "aging": {"opening": bd["opening"], "closing": bd["closing"]},
    }

    prefill: dict = {
        "receivable_total": rec,
        "bad_debt_total": bd,
        "nature": nature,
        "portfolio": portfolio,
        "portfolio_provision": portfolio_bd,
    }
    # 空预填不返回
    if rec["opening"] == 0 and rec["closing"] == 0 and bd["opening"] == 0 and bd["closing"] == 0:
        return {}
    return prefill


def _has_persisted_adjudication(responses_snapshot: dict) -> bool:
    """任一 K1-1-*-unadj 有非零值 → 视为已编辑，不再预填."""
    for item_id, payload in responses_snapshot.items():
        if not str(item_id).startswith("K1-1-") or not str(item_id).endswith("-unadj"):
            continue
        raw = (payload or {}).get("remark") or (payload or {}).get("conclusion") or ""
        try:
            if abs(float(raw)) >= 0.005:
                return True
        except (TypeError, ValueError):
            continue
    return False


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/bs_date/关联方）."""
    project_ctx: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
        "bs_date": "",
        "related_parties": [],
        "bad_debt_account_prefix": "1231",
    }
    try:
        result = await ctx.db.execute(
            sa.text(
                """
                SELECT p.client_name, p.audit_year, p.business_category
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
            """
            ),
            {"wp_id": str(ctx.wp_id)},
        )
        row = result.fetchone()
        if row:
            project_ctx["client_name"] = row.client_name or ""
            project_ctx["audit_year"] = str(row.audit_year) if row.audit_year else ""
            project_ctx["business_category"] = row.business_category or ""
            if row.audit_year:
                project_ctx["bs_date"] = f"{row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("K1 project context load failed: %s", e)

    # B19 关联方清单：供 K1-2 批量匹配 / K1-11 完整性校验
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
        logger.warning("K1 render: related_parties 查询失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass

    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """K1其他应收款渲染策略：allResponses + projectContext + TB数据 + 预填."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "K1-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K1 render responses load failed: %s", e)

    tb_values = await _fetch_tb_data(ctx)
    project_context = await _load_project_context(ctx)

    adjudication_prefill: dict = {}
    if not _has_persisted_adjudication(responses_snapshot):
        adjudication_prefill = await _build_adjudication_prefill(ctx)

    return {
        "component_type": "k1-other-receivables",
        "account_codes": ["1221", "1231"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "adjudication_prefill": adjudication_prefill,
        "project_context": project_context,
        "prefix": "K1",
        "sheets": K1_SHEETS,
    }
