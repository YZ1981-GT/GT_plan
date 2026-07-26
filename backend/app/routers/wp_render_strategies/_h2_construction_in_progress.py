"""H2 在建工程 — 专属渲染策略.

科目1604在建工程（借方/资产类）
返回 allResponses + projectContext + TB数据(1604)
三角勾稽含转固扣减：期末=期初+增加-减少-转固
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1604在建工程 + 1605工程物资（审定表与试算核对）
# 键名同时提供短名与 cip_1604_* / eng_mat_1605_* 别名，兼容前后端
_H2_ACCOUNT_PREFIXES = {
    "1604": ("cip_unadjusted", "cip_audited"),
    "1605": ("eng_mat_unadjusted", "eng_mat_audited"),
}

H2_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "在建工程实质性程序表H2A", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "审定表H2-1", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "明细表H2-2", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "调整分录汇总H2-3", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "分析表H2-4", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "转固时点检查表H2-5", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "在建工程审核记录H2-6", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "工程造价比较表H2-7", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "增加检查表H2-8", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "减少检查表H2-9", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "利息资本化测算表（无专门借款）H2-10", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "利息资本化测算表（有专门借款）H2-11", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "监盘计划H2-12", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "盘点检查表H2-13", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "监盘小结H2-14", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "减值测算表H2-15", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "可收回金额测试表H2-16", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "关联交易检查表H2-17", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h2-construction-in-progress"},
]


def _alias_tb_keys(tb: dict[str, float]) -> dict[str, float]:
    """补充前端常用别名键，避免 cip_unadjusted vs cip_1604_unadjusted 不一致."""
    aliases = {
        "cip_1604_unadjusted": tb.get("cip_unadjusted", 0.0),
        "cip_1604_audited": tb.get("cip_audited", 0.0),
        "eng_mat_1605_unadjusted": tb.get("eng_mat_unadjusted", 0.0),
        "eng_mat_1605_audited": tb.get("eng_mat_audited", 0.0),
    }
    for k, v in aliases.items():
        tb.setdefault(k, v)
    return tb


def _is_leaf(code: str, all_codes: set[str]) -> bool:
    """判定该科目是否为叶子节点（不是任何其它科目的前缀）。防止父子双算。"""
    for other in all_codes:
        if other != code and other.startswith(code):
            return False
    return True


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1604/1605的期初/期末余额及未审数/审定数（只取叶子防双算）."""
    tb: dict[str, float] = {}
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
        all_rows = result.fetchall()
        # 收集 1604/1605 前缀下的全部科目码，用于叶子判定
        h2_codes: set[str] = set()
        for row in all_rows:
            code = (row.account_code or "").strip()
            for prefix in _H2_ACCOUNT_PREFIXES:
                if code == prefix or code.startswith(prefix):
                    h2_codes.add(code)
                    break
        # 只累加叶子科目（防父子双算）
        for row in all_rows:
            code = (row.account_code or "").strip()
            if code not in h2_codes:
                continue
            if not _is_leaf(code, h2_codes):
                continue
            for prefix, (unadj_key, _audited_key) in _H2_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 TB balance fetch failed: %s", e)

    # 从trial_balance取未审数/审定数（1604 + 1605）— 使用 ORM 模型 + get_active_filter 确保
    # 只读 active dataset（与 tb_balance 段口径一致），避免裸 is_deleted 漏读 superseded 行。
    try:
        tb_filter = await get_active_filter(
            ctx.db, TrialBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.unadjusted_amount,
                TrialBalance.audited_amount,
            ).where(
                tb_filter,
                sa.or_(
                    TrialBalance.standard_account_code.like("1604%"),
                    TrialBalance.standard_account_code.like("1605%"),
                ),
            )
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _H2_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 trial_balance fetch failed: %s", e)

    return _alias_tb_keys(tb)


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/适用准则/资产负债表日/关联方清单）."""
    project_ctx: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
        "applicable_standards": "",
        # bs_date（资产负债表日）：供 H2-5 转固期后窗口/少计折旧 asOf、H2-13 盘点基准日等取数
        "bs_date": "",
        # 关联方清单：供 H2-17 关联交易检查自动识别
        "related_parties": [],
    }
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category, p.applicable_standard_v2 AS applicable_standards
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
            if row.audit_year:
                project_ctx["bs_date"] = f"{row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 project context load failed: %s", e)

    # 关联方清单：从关联方登记表（related_party_registry）取项目级名单
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
        logger.warning("H2 render: related_parties 查询失败: %s", e)

    return project_ctx


async def _build_h2_detail_prefill(ctx: RenderContext) -> list[dict]:
    """从 tb_balance 1604% 叶子科目构建 H2-2 明细行种子（Persist_First 由前端控制）。"""
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
            ).where(active_filter)
        )
        all_rows = result.fetchall()
        codes_1604: set[str] = set()
        for row in all_rows:
            code = (row.account_code or "").strip()
            if code == "1604" or code.startswith("1604"):
                codes_1604.add(code)
        prefill: list[dict] = []
        for row in all_rows:
            code = (row.account_code or "").strip()
            if code not in codes_1604:
                continue
            if not _is_leaf(code, codes_1604):
                continue
            opening = abs(float(row.opening_balance or 0))
            closing = abs(float(row.closing_balance or 0))
            if opening < 0.005 and closing < 0.005:
                continue
            name = (row.account_name or "").strip() or (code[4:].lstrip(".") if len(code) > 4 else code)
            prefill.append({"name": name, "cipBegin": opening, "cipEnd": closing, "category": "自动种子"})
        return prefill
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 detail prefill failed: %s", e)
        return []


async def render(ctx: RenderContext) -> dict | None:
    """H2在建工程渲染策略：allResponses + projectContext + TB数据."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H2-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 render responses load failed: %s", e)

    tb_values = await _fetch_tb_data(ctx)
    project_context = await _load_project_context(ctx)

    # 灰度门控：H2_FOUR_TABLE_EXTRACTION_ENABLED 控制是否输出 detail_prefill
    from app.core.config import settings
    if settings.H2_FOUR_TABLE_EXTRACTION_ENABLED:
        detail_prefill = await _build_h2_detail_prefill(ctx)
    else:
        detail_prefill = []

    return {
        "component_type": "h2-construction-in-progress",
        "account_codes": ["1604", "1605"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "detail_prefill": detail_prefill,
        "prefix": "H2",
        "sheets": H2_SHEETS,
    }
