"""F1 预付账款 — 专属渲染策略.

component_type = "f1-prepayment"
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 预付账款(资产借方) / 存货 / 应付账款 —— 供 F1-1 试算核对及 F1-4 跨循环取数
_F1_TB_PREFIXES = ("1123", "1401", "2202")


async def _fetch_f1_tb_context(ctx: RenderContext) -> dict[str, float]:
    """从 tb_balance 取 1123(预付)/1401(存货)/2202(应付) 期末余额（v1 借正贷负口径）."""
    balances: dict[str, float] = {}
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.closing_balance,
            ).where(active_filter)
        )
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            for prefix in _F1_TB_PREFIXES:
                if code == prefix or code.startswith(prefix):
                    balances[prefix] = balances.get(prefix, 0.0) + float(row.closing_balance or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("F1 render: tb_balance 取数失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
    return balances


async def _fetch_f1_1123_audited(ctx: RenderContext) -> float | None:
    """从 trial_balance(v2 正数口径) 取 1123 审定数(无则未审数)，供 F1-1 试算核对预填."""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT unadjusted_amount, audited_amount "
                "FROM trial_balance "
                "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                "AND standard_account_code LIKE '1123%'"
            ),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        audited = 0.0
        unadjusted = 0.0
        found = False
        for row in result.fetchall():
            found = True
            audited += float(row.audited_amount or 0)
            unadjusted += float(row.unadjusted_amount or 0)
        if not found:
            return None
        return audited if abs(audited) > 1e-9 else unadjusted
    except Exception as e:  # noqa: BLE001
        logger.warning("F1 render: trial_balance 1123 取数失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
        return None


async def render(ctx: RenderContext) -> dict | None:
    """F1 预付账款渲染策略."""
    wp_id = ctx.wp_id
    db = ctx.db

    # rowKey 与前端 useF1Adjudication.NATURE_ROWS 对齐（前端以自身常量为准，此处仅作参考元数据）
    adjudication_config = {
        "nature_rows": [
            {"rowKey": "goods", "label": "货款"},
            {"rowKey": "construction", "label": "工程款"},
            {"rowKey": "equipment", "label": "设备款"},
            {"rowKey": "service", "label": "服务费"},
            {"rowKey": "other", "label": "其他"},
        ],
        "aging_rows": [
            {"rowKey": "within-1-year", "label": "1年以内含1年"},
            {"rowKey": "1-to-2-years", "label": "1至2年含2年"},
            {"rowKey": "2-to-3-years", "label": "2至3年含3年"},
            {"rowKey": "over-3-years", "label": "3年以上"},
        ],
    }

    sections = [
        {"code": "F1A", "label": "F1A 程序表", "type": "procedure"},
        {"code": "F1-1", "label": "F1-1 审定表", "type": "adjudication"},
        {"code": "F1-2", "label": "F1-2 明细表", "type": "detail"},
        {"code": "F1-3", "label": "F1-3 调整分录", "type": "adjustment"},
        {"code": "F1-4", "label": "F1-4 实质性分析", "type": "analysis"},
        {"code": "F1-5", "label": "F1-5 长期挂款检查", "type": "long_term"},
        {"code": "F1-6", "label": "F1-6 关联方检查", "type": "related_party"},
        {"code": "F1-7", "label": "F1-7 综合检查", "type": "comprehensive_check"},
        {"code": "F1-NOTE", "label": "附注", "type": "disclosure"},
        {"code": "F1-CONF", "label": "函证程序", "type": "confirmation_procedure"},
    ]

    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'F1-%' "
                "LIMIT 800"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("F1 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
        "applicable_standards": "",
        "bs_date": "",
        "related_parties": [],
        # F1-4 跨循环取数（tb_balance 期末余额；应付取绝对值供正数展示）
        "inventory_balance_current": 0.0,
        "payable_balance_current": 0.0,
        # F1-1 试算核对预填（1123 审定/未审；组件只读回退 seed）
        "prepaid_tb_amount": 0.0,
    }

    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, business_category, "
                "applicable_standard_v2 AS applicable_standards "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = proj_row.business_category or ""
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
            raw_standards = proj_row.applicable_standards
            # applicable_standard_v2 可能是 JSONB(dict) 或 string 或 None
            if isinstance(raw_standards, dict):
                project_context["applicable_standards"] = (
                    raw_standards.get("type")
                    or raw_standards.get("entity_type")
                    or ""
                )
            elif isinstance(raw_standards, str):
                project_context["applicable_standards"] = raw_standards
            else:
                project_context["applicable_standards"] = ""
    except Exception as e:  # noqa: BLE001
        logger.warning("F1 render: project context 查询失败: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass

    # 关联方清单：从关联方登记表取项目级名单，供 F1-2 关联方识别 / F1-6 完整性校验
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
        logger.warning("F1 render: related_parties 查询失败: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass

    # TB 取数：F1-1 试算核对预填(1123) + F1-4 存货/应付余额
    tb_balances = await _fetch_f1_tb_context(ctx)
    project_context["inventory_balance_current"] = round(tb_balances.get("1401", 0.0), 2)
    # 应付账款(2202)为负债贷方，tb_balance 借正贷负 → 取绝对值供 F1-4 正数展示
    project_context["payable_balance_current"] = round(abs(tb_balances.get("2202", 0.0)), 2)

    # F1-1 试算平衡表数(1123)：优先 trial_balance 审定/未审，回退 tb_balance 期末。
    # 前端 allResponses 来自 checklist-responses 端点（非本 responses_snapshot），故同时：
    #  ① 注入 responses_snapshot（供确有消费该键的路径使用）
    #  ② 放入 project_context.prepaid_tb_amount 供 F1-1 组件作只读回退 seed（不覆盖手工录入）
    seed_tb = await _fetch_f1_1123_audited(ctx)
    if seed_tb is None:
        seed_tb = tb_balances.get("1123")
    if seed_tb is not None and abs(seed_tb) > 1e-9:
        project_context["prepaid_tb_amount"] = round(seed_tb, 2)
        if "F1-adj-trial-balance-amount" not in responses_snapshot:
            responses_snapshot["F1-adj-trial-balance-amount"] = {
                "conclusion": "",
                "remark": str(round(seed_tb, 2)),
            }

    raw_std = project_context["applicable_standards"]
    standards = raw_std.lower() if isinstance(raw_std, str) else ""
    disclosure_visibility = {
        "listed": "listed" in standards,
        "soe": "soe" in standards,
    }

    return {
        "sections": sections,
        "adjudication_config": adjudication_config,
        "project_context": project_context,
        "disclosure_visibility": disclosure_visibility,
        "responses_snapshot": responses_snapshot,
        "account_code": "1123",
    }
