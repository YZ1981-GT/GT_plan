"""H3 投资性房地产 — 专属渲染策略.

四表取数走**语义驱动的逐项目科目定位**（`four_table/semantic_account_resolver`），
四个槽：原值 / 累计折旧 / 累计摊销 / 减值准备。返回 allResponses + projectContext
+ tb_values + tb_source_codes + measurement_model；双计量模式(成本/公允价值)控制前端显隐。

🔴 **2026-08-01 修掉的三个缺陷**（详见 `four_table/h3_account_scope` 的 docstring）：

1. **取错整个科目族** —— 原 `_H3_ACCOUNT_PREFIXES` 写 ``{"1503": 原值, "1504": 累计折旧}``，
   而 ``1503 = 可供出售金融资产``（G6 域）、``1504 = 债权投资``（G4 域）。
   投资性房地产真实科目族是 ``1521 / 1525 / 1526 / 1527``。
2. **缺两个槽** —— 累计摊销（土地使用权）与减值准备完全没取。
3. **叶子判定缺点号边界** —— ``c.startswith(code)`` 会让 ``15210`` 被当成 ``1521`` 的子科目；
   改用 `leaf_aggregation.select_leaves`（与 `trial_balance_service.recalc` 同语义）。

且不再写死标准码：`account_mapping` 实证同一原始码 ``1525 投资性房地产累计折旧`` 在
1 个项目映射到 ``1521``（并入母科目）、在 4 个项目映射到 ``1525``（独立）
→ 按码取数在部分项目必然取空或混算。
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.h_cycle_adjudication_prefill import (
    attach_h_segment_prefill,
)
from app.services.four_table.h3_account_scope import (
    H3_ACCOUNT_SPEC,
    H3_SLOT_KEY_PREFIX,
)
from app.services.four_table.leaf_aggregation import (
    aggregate_leaves,
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table.semantic_account_resolver import (
    SemanticAccountResult,
    resolve_semantic_accounts,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)

H3_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h3-investment-property"},
    {"sheet_name": "投资性房地产实质性程序表H3A", "component_type": "h3-investment-property"},
    {"sheet_name": "审定表H3-1", "component_type": "h3-investment-property"},
    {"sheet_name": "明细表H3-2", "component_type": "h3-investment-property"},
    {"sheet_name": "调整分录汇总H3-3", "component_type": "h3-investment-property"},
    {"sheet_name": "会计政策检查表H3-4", "component_type": "h3-investment-property"},
    {"sheet_name": "增减检查表H3-5", "component_type": "h3-investment-property"},
    {"sheet_name": "互转审核表H3-6", "component_type": "h3-investment-property"},
    {"sheet_name": "折旧测算表H3-7", "component_type": "h3-investment-property"},
    {"sheet_name": "公允价值复核表H3-8", "component_type": "h3-investment-property"},
    {"sheet_name": "盘点检查表H3-9", "component_type": "h3-investment-property"},
    {"sheet_name": "减值测算表H3-10", "component_type": "h3-investment-property"},
    {"sheet_name": "可收回金额测试表H3-11", "component_type": "h3-investment-property"},
    {"sheet_name": "产权核对表H3-12", "component_type": "h3-investment-property"},
    {"sheet_name": "关联交易检查表H3-13", "component_type": "h3-investment-property"},
    {"sheet_name": "租金收入测算表H3-14", "component_type": "h3-investment-property"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h3-investment-property"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h3-investment-property"},
]


def build_h3_tb_values(
    accounts: SemanticAccountResult,
    tb_rows,
    trial_rows,
) -> dict[str, float]:
    """按语义槽聚合四表金额。纯函数（可独立单测，无 DB）。

    输出键沿用既有契约（``ip_*`` / ``dep_*``）并**新增** ``amort_*`` / ``impair_*``::

        {slot_prefix}_unadjusted_opening / _closing / _debit / _credit   ← tb_balance 叶子
        {slot_prefix}_unadjusted / {slot_prefix}_audited                 ← trial_balance

    Args:
        accounts: :func:`resolve_semantic_accounts` 的结果（逐项目定位）。
        tb_rows: `tb_balance` 全量行（**不要预先按科目过滤** —— 叶子判定需要看到
            全部兄弟行，否则父子双算）。
        trial_rows: `trial_balance` 行（``standard_account_code`` / ``unadjusted_amount``
            / ``audited_amount``）。

    Returns:
        金额字典。某槽在本项目无对应科目时该槽**不产生任何键**（而非产生 0）——
        让前端能区分「本项目无此科目」与「余额为 0」。
    """
    leaves = select_leaves(to_leaf_rows(tb_rows))
    out: dict[str, float] = {}

    for slot_key, prefix in H3_SLOT_KEY_PREFIX.items():
        slot = accounts.slots.get(slot_key)
        if slot is None or not slot.found:
            continue
        agg = aggregate_leaves(leaves, slot.codes)
        out[f"{prefix}_unadjusted_opening"] = agg["opening"]
        out[f"{prefix}_unadjusted_closing"] = agg["closing"]
        out[f"{prefix}_unadjusted_debit"] = agg["debit"]
        out[f"{prefix}_unadjusted_credit"] = agg["credit"]

    # trial_balance：按**标准码**精确匹配（不用 LIKE 前缀 —— 会把兄弟科目族吃进来）
    by_code: dict[str, tuple[float, float]] = {}
    for row in trial_rows or []:
        get = row.get if isinstance(row, dict) else (lambda k, _r=row: getattr(_r, k, None))
        code = str(get("standard_account_code") or "").strip()
        if not code:
            continue
        prev = by_code.get(code, (0.0, 0.0))
        by_code[code] = (
            prev[0] + float(get("unadjusted_amount") or 0),
            prev[1] + float(get("audited_amount") or 0),
        )

    for slot_key, prefix in H3_SLOT_KEY_PREFIX.items():
        slot = accounts.slots.get(slot_key)
        if slot is None or not slot.found:
            continue
        wanted = set(slot.standard_codes)
        if not wanted:
            continue
        unadj = sum(v[0] for c, v in by_code.items() if c in wanted)
        audited = sum(v[1] for c, v in by_code.items() if c in wanted)
        out[f"{prefix}_unadjusted"] = unadj
        out[f"{prefix}_audited"] = audited

    return out


async def _fetch_tb_data(ctx: RenderContext) -> tuple[dict, SemanticAccountResult]:
    """按语义槽取投资性房地产四表数据（原值 / 累计折旧 / 累计摊销 / 减值准备）。

    Returns:
        ``(tb_values, accounts)`` —— ``accounts`` 供 render 下发 `tb_source_codes` 溯源。
    """
    accounts = await resolve_semantic_accounts(ctx, H3_ACCOUNT_SPEC)

    tb_rows: list = []
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
                TbBalance.closing_direction,
                TbBalance.dataset_id,
            ).where(active_filter)
        )
        tb_rows = list(result.fetchall())
    except Exception as e:  # noqa: BLE001
        logger.warning("H3 TB balance fetch failed: %s", e)

    trial_rows: list = []
    standard_codes = sorted(
        {c for slot in accounts.slots.values() for c in slot.standard_codes if c}
    )
    if standard_codes:
        try:
            result = await ctx.db.execute(
                sa.text(
                    "SELECT standard_account_code, unadjusted_amount, audited_amount "
                    "FROM trial_balance "
                    "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                    "  AND standard_account_code = ANY(:codes)"
                ),
                {"pid": str(ctx.project_id), "year": ctx.year, "codes": standard_codes},
            )
            trial_rows = list(result.fetchall())
        except Exception as e:  # noqa: BLE001
            logger.warning("H3 trial_balance fetch failed: %s", e)

    tb = build_h3_tb_values(accounts, tb_rows, trial_rows)

    # 从trial_balance取6051其他业务收入审定发生额（供前端租金勾稽）
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT SUM(audited_amount) AS total
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code LIKE '6051%'
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        row = result.fetchone()
        tb["tb_6051_audited"] = float(row.total) if row and row.total else None
    except Exception as e:  # noqa: BLE001
        logger.warning("H3 tb_6051 fetch failed: %s", e)
        tb["tb_6051_audited"] = None

    return tb, accounts


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/适用准则/模板变体）."""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category,
                       p.applicable_standard_v2 AS applicable_standards,
                       p.template_type, p.report_scope
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
            project_ctx["template_type"] = (
                str(row.template_type.value) if hasattr(row.template_type, "value")
                else (str(row.template_type) if row.template_type else "")
            )
            project_ctx["report_scope"] = (
                str(row.report_scope.value) if hasattr(row.report_scope, "value")
                else (str(row.report_scope) if row.report_scope else "")
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("H3 project context load failed: %s", e)
    return project_ctx


async def _load_measurement_model(ctx: RenderContext) -> str:
    """加载计量模式（cost/fair_value）——从 checklist_responses 中读取."""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT conclusion FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = 'H3-measurement-model' LIMIT 1"
            ),
            {"wp_id": str(ctx.wp_id)},
        )
        row = result.fetchone()
        if row and row.conclusion in ("cost", "fair_value"):
            return row.conclusion
    except Exception as e:  # noqa: BLE001
        logger.warning("H3 measurement_model load failed: %s", e)
    return "cost"  # 默认成本模式


async def render(ctx: RenderContext) -> dict | None:
    """H3投资性房地产渲染策略：allResponses + projectContext + TB数据 + measurement_model."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 3000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H3-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H3 render responses load failed: %s", e)

    tb_values, accounts = await _fetch_tb_data(ctx)
    project_context = await _load_project_context(ctx)
    measurement_model = await _load_measurement_model(ctx)

    # 将 tb_6051_audited 从 tb_values 提升到 project_context（前端消费语义更清晰）
    project_context["tb_6051_audited"] = tb_values.pop("tb_6051_audited", None)
    # 取数溯源（本项目实际命中的科目 + 报表行 + 与 report_config 的冲突）
    project_context["tb_source_codes"] = accounts.as_dict()

    payload: dict = {
        "component_type": "h3-investment-property",
        # 🔴 原写死 ["1503","1504"]（= 可供出售金融资产 / 债权投资，另两个循环的科目）
        #    改为本项目实际定位到的科目码；无该科目时为空列表（宁缺勿造）
        "account_codes": sorted(
            {c for slot in accounts.slots.values() for c in slot.codes if c}
        ),
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": accounts.as_dict(),
        "project_context": project_context,
        "measurement_model": measurement_model,
        "prefix": "H3",
        "sheets": H3_SHEETS,
    }

    # ─── 审定表四表预填（spec h-cycle Task 5；H5~H10 已有，H1~H4 原缺）──
    await attach_h_segment_prefill(
        ctx,
        payload,
        cycle="H3",
        accounts=accounts,
        slot_key_prefix=H3_SLOT_KEY_PREFIX,
    )

    return payload
