"""H4 工程物资 — 专属渲染策略.

component_type = "h4-engineering-materials"

科目1605工程物资（借方/资产类）+ 1604在建工程（报表核对带入）
返回 allResponses + projectContext + TB数据(1605/1604) + sheets元数据
资产类公式：期末=期初+借方-贷方；审定=未审+账项调整
联动H2在建工程：H4减少→H2物资消耗；H4-1报表核对←TB·1604/H2-1

    Requirements: 1.6
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter
from app.core.config import settings

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1605工程物资 + 1604在建工程（H4-1 与报表核对带入）
_H4_ACCOUNT_PREFIXES = {
    "1605": ("eng_mat_1605_unadjusted", "eng_mat_1605_audited"),
    "1604": ("cip_1604_unadjusted", "cip_1604_audited"),
}

H4_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h4-engineering-materials"},
    {"sheet_name": "工程物资实质性程序表H4A", "component_type": "h4-engineering-materials"},
    {"sheet_name": "审定表H4-1", "component_type": "h4-engineering-materials"},
    {"sheet_name": "明细表H4-2", "component_type": "h4-engineering-materials"},
    {"sheet_name": "调整分录汇总H4-3", "component_type": "h4-engineering-materials"},
    {"sheet_name": "增加检查表H4-4", "component_type": "h4-engineering-materials"},
    {"sheet_name": "减少检查表H4-5", "component_type": "h4-engineering-materials"},
    {"sheet_name": "监盘计划H4-6A", "component_type": "h4-engineering-materials"},
    {"sheet_name": "盘点检查表H4-6", "component_type": "h4-engineering-materials"},
    {"sheet_name": "监盘小结H4-6B", "component_type": "h4-engineering-materials"},
    {"sheet_name": "减值测算表H4-7", "component_type": "h4-engineering-materials"},
    {"sheet_name": "可收回金额测试表H4-8", "component_type": "h4-engineering-materials"},
    {"sheet_name": "关联交易检查表H4-9", "component_type": "h4-engineering-materials"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h4-engineering-materials"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h4-engineering-materials"},
]


def _is_leaf(code: str, all_codes: set[str]) -> bool:
    """判断 code 是否为叶子科目（不是任何其它 code 的前缀）.

    防止父子科目同时累加导致双算。
    """
    for other in all_codes:
        if other != code and other.startswith(code):
            return False
    return True


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1605/1604的期初/期末余额及未审数/审定数.

    使用 get_active_filter 统一口径 + 叶子过滤防双算。
    """
    tb: dict[str, float] = {}

    # ─── 从 tb_balance 取余额数据（使用 get_active_filter + 叶子过滤） ───
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(active_filter)
        )
        # 第一遍：收集匹配前缀的所有科目码
        matched_rows: list[tuple] = []
        all_matched_codes: set[str] = set()
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            for prefix in _H4_ACCOUNT_PREFIXES:
                if code == prefix or code.startswith(prefix):
                    matched_rows.append(row)
                    all_matched_codes.add(code)
                    break

        # 第二遍：只累加叶子科目（防父子双算）
        for row in matched_rows:
            code = (row.account_code or "").strip()
            if not _is_leaf(code, all_matched_codes):
                continue
            for prefix, (unadj_key, _audited_key) in _H4_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H4 TB balance fetch failed: %s", e)

    # ─── 从 trial_balance 取未审数+审定数（使用 get_active_filter 统一口径） ───
    try:
        tb_active_filter = await get_active_filter(
            ctx.db, TrialBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.unadjusted_amount,
                TrialBalance.audited_amount,
            ).where(
                tb_active_filter,
                sa.or_(
                    TrialBalance.standard_account_code.like("1605%"),
                    TrialBalance.standard_account_code.like("1604%"),
                ),
            )
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _H4_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H4 trial_balance fetch failed: %s", e)

    # 别名：与 H2 渲染键对齐，便于前端统一读取
    tb.setdefault("cip_unadjusted", tb.get("cip_1604_unadjusted", 0.0))
    tb.setdefault("cip_audited", tb.get("cip_1604_audited", 0.0))

    return tb


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/行业分类/资产负债表日/关联方）."""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category,
                       p.applicable_standard_v2 AS applicable_standards,
                       p.template_type
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
            project_ctx["template_type"] = row.template_type or "listed"
            # 资产负债表日（默认年末）
            year = row.audit_year or 2025
            project_ctx["bs_date"] = f"{year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("H4 project context load failed: %s", e)

    # 关联方清单（供 H4-9 关联交易核对）
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT name, relation_type, is_controlled_by_same_party
                FROM related_party_registry
                WHERE project_id = :pid AND is_deleted = false
            """),
            {"pid": str(ctx.project_id)},
        )
        parties = []
        for row in result.fetchall():
            parties.append({
                "name": row.name or "",
                "relation_type": row.relation_type or "",
                "is_controlled_by_same_party": bool(row.is_controlled_by_same_party),
            })
        project_ctx["related_parties"] = parties
    except Exception as e:  # noqa: BLE001
        logger.warning("H4 related_parties load failed: %s", e)
        project_ctx["related_parties"] = []

    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """H4工程物资渲染策略：allResponses + projectContext + TB数据 + sheets."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H4-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H4 render responses load failed: %s", e)

    tb_values = await _fetch_tb_data(ctx)
    project_context = await _load_project_context(ctx)

    result_dict: dict = {
        "component_type": "h4-engineering-materials",
        "account_codes": ["1605", "1604"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "H4",
        "sheets": H4_SHEETS,
        "meta": {"sheet_count": 15, "wp_code": "H4"},
    }

    # ─── 灰度开关：四表取数增强（默认 False = 逐字节零回归） ───
    if settings.H4_FOUR_TABLE_EXTRACTION_ENABLED:
        project_context["h4_extraction_enabled"] = True
        # H4-2 明细种子（Persist-First 由前端判定，后端只提供候选）
        detail_prefill = await _build_h4_detail_prefill(ctx)
        if detail_prefill:
            result_dict["detail_prefill"] = detail_prefill

    return result_dict


# ═══════════════════════════════════════════════════════════════════════════════
# H4-2 明细表种子：从 tb_balance 1605 叶子提取（灰度开关内调用）
# ═══════════════════════════════════════════════════════════════════════════════


def _derive_category(account_name: str) -> str:
    """从科目名称末段派生物资分类（如 '工程物资-钢材' → '钢材'）."""
    if not account_name:
        return "其他"
    # 尝试多种分隔符
    for sep in ("-", "_", "·", "/", "—", "－"):
        if sep in account_name:
            parts = account_name.split(sep)
            last = parts[-1].strip()
            if last:
                return last
    # 无分隔符：去掉 "工程物资" 前缀
    cleaned = account_name.replace("工程物资", "").strip()
    return cleaned or account_name


async def _build_h4_detail_prefill(ctx: RenderContext) -> list[dict]:
    """从 tb_balance 提取 1605 叶子科目种子行（fail-open）."""
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
            ).where(
                active_filter,
                TbBalance.account_code.like("1605%"),
            )
        )
        rows = result.fetchall()
        if not rows:
            return []

        # 收集所有码用于叶子判定
        all_codes = {(r.account_code or "").strip() for r in rows}

        prefill: list[dict] = []
        for row in rows:
            code = (row.account_code or "").strip()
            if not code:
                continue
            # 只取叶子
            if not _is_leaf(code, all_codes):
                continue
            # 排除全零行
            opening = float(row.opening_balance or 0)
            debit = float(row.debit_amount or 0)
            credit = float(row.credit_amount or 0)
            closing = float(row.closing_balance or 0)
            if (abs(opening) < 0.005 and abs(debit) < 0.005
                    and abs(credit) < 0.005 and abs(closing) < 0.005):
                continue

            name = (row.account_name or "").strip()
            prefill.append({
                "category": _derive_category(name),
                "name": name,
                "accountCode": code,
                "beginAmount": abs(opening),
                "purchaseAmount": abs(debit),
                "usageAmount": abs(credit),
                "endAmount": abs(closing),
                "source": "tb_balance",
            })

        return prefill
    except Exception as e:  # noqa: BLE001
        logger.warning("H4 _build_h4_detail_prefill failed: %s", e)
        return []
