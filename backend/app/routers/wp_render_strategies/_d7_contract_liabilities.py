"""D7 合同负债 — 专属渲染策略.

component_type = "d7-contract-liabilities"
返回 html_data 含：审定表双区块结构 + 明细表行数据 + 各sheet配置。
数据持久化在 checklist_responses 表，item_id前缀为 "D7-{sheetCode}-{field}"。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from app.core.config import settings
from app.services.d_cycle_extraction.d_account_resolver import (
    resolve_d_cycle_account_codes,
)
from app.services.d_cycle_extraction.d_tb_fetch import (
    build_d_tb_source_codes,
    fetch_d_cycle_tb,
    seed_tb_amount_scalars,
)
from app.services.d_cycle_extraction.presets import resolve_effective
from app.services.d_cycle_extraction.tier_a_seed import (
    seed_tier_a_reconciliation,
)
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression

from ._context import RenderContext

logger = logging.getLogger(__name__)

# D7 wp_code base（Tier A 提取公式 / 锚点登记 key）
_D7_WP_CODE = "D7"


async def render(ctx: RenderContext) -> dict | None:
    """D7 合同负债渲染策略.

    返回完整 html_data：
    - sections: 各sheet元数据配置
    - adjudication_config: 审定表双区块固定行结构
    - project_context: 项目上下文
    - disclosure_visibility: 适用性标准判断
    - responses_snapshot: 关键item_id的已保存数据
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 审定表双区块固定行结构 ───────────────────────────────────────────
    adjudication_config = {
        "blocks": [
            {
                "blockKey": "nature",
                "blockTitle": "一、按性质分类",
                "rows": [
                    {"rowKey": "revenue", "label": "预收货款"},
                    {"rowKey": "development", "label": "开发项目预收款"},
                    {"rowKey": "engineering", "label": "预收工程款"},
                    {"rowKey": "other", "label": "其他"},
                ],
                "subtotalLabel": "小计",
                "deductionLabel": "减：计入其他非流动负债的合同负债",
                "totalLabel": "合同负债合计",
            },
            {
                "blockKey": "aging",
                "blockTitle": "二、按账龄分类",
                "rows": [
                    {"rowKey": "within-1-year", "label": "1年以内(含1年)"},
                    {"rowKey": "1-to-2-years", "label": "1至2年(含2年)"},
                    {"rowKey": "2-to-3-years", "label": "2至3年(含3年)"},
                    {"rowKey": "over-3-years", "label": "3年以上"},
                ],
                "totalLabel": "合计",
                "extraRows": ["试算平衡表数", "差异数"],
            },
        ],
        "columns": [
            "项目", "期初未审", "期初AJE", "期初RJE", "期初审定",
            "期末未审", "期末AJE", "期末RJE", "期末审定", "变动额", "变动率", "原因分析",
        ],
    }

    # ─── sections 结构定义（9个sheet） ─────────────────────────────────────
    sections = [
        {"code": "D7A", "label": "合同负债审计程序表D7A", "type": "procedure"},
        {"code": "D7-1", "label": "合同负债审定表D7-1", "type": "adjudication"},
        {"code": "D7-2", "label": "合同负债明细表D7-2", "type": "detail"},
        {"code": "D7-3", "label": "合同负债调整分录汇总D7-3", "type": "adjustment"},
        {"code": "D7-4", "label": "合同负债分析表D7-4", "type": "analysis"},
        {"code": "D7-5", "label": "账龄1年以上合同负债检查D7-5", "type": "long_term"},
        {"code": "D7-6", "label": "关联方合同负债检查D7-6", "type": "related_party"},
        {"code": "D7-7", "label": "合同负债凭证检查D7-7", "type": "voucher_check"},
        {"code": "D7-NOTE", "label": "合同负债附注披露", "type": "disclosure"},
    ]

    # ─── 从 checklist_responses 加载关键数据快照 ──────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D7-%' "
                "LIMIT 500"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("D7 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)
        try:
            await db.rollback()
        except Exception:
            pass

    # ─── 项目上下文 + 适用性判断 ─────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
        "applicable_standards": "",
        "bs_date": "",
        "related_parties": [],
        "tb_amount": 0,
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
            raw_standards = proj_row.applicable_standards
            if isinstance(raw_standards, dict):
                project_context["applicable_standards"] = raw_standards.get("type", "")
            else:
                project_context["applicable_standards"] = str(raw_standards or "")
            # bs_date 供期后窗口判断
            audit_year = proj_row.audit_year or ""
            project_context["bs_date"] = f"{audit_year}-12-31" if audit_year else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("D7 render: project context 查询失败: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass

    # ─── related_parties（关联方清单） ────────────────────────────────────
    try:
        rp_result = await db.execute(
            sa.text(
                "SELECT name FROM related_party_registry "
                "WHERE project_id = :pid AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )
        project_context["related_parties"] = [
            row.name for row in rp_result.fetchall() if row.name
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("D7 render: related_parties 查询失败: %s", e)
        project_context["related_parties"] = []
        try:
            await db.rollback()
        except Exception:
            pass

    # ─── tb_amount：报表规则映射驱动（替代硬编码 2205，供 TB 自动预填）──────────
    # spec: d-cycle-four-table-extraction-and-disclosure-completion R1
    #
    # ⚠️ 本次改造**不是修取数 bug** —— 改造前的 `LIKE '2205%'` 查的是 `trial_balance`
    # （**标准码**体系），而 `trial_balance` 本身就是经 `account_mapping` 映射后的标准码，
    # 故它能正确命中：实测 5 个项目 / 合计 7,855.34（其中那个客户用 client 码 `2204`
    # 的项目，映射后在本表就是 `2205`）。
    # 收益在于**消除硬编码**：`report_config` 的 BS-047 一旦改科目（或项目级
    # `project:{id}` 覆盖），硬编码就取错而无任何报错线索。
    #
    # 零回归判据：改造前后 `project_context.tb_amount` 在真实库上逐项目相等
    # （`build_trial_balance_code_filter` 单码同样用 `LIKE '{code}%'`，语义一致）。
    d7_codes = None
    try:
        d7_codes = await resolve_d_cycle_account_codes(ctx, _D7_WP_CODE)
        await seed_tb_amount_scalars(
            ctx, d7_codes, project_context, write_zero_when_missing=True
        )
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning("D7 render: 科目解析/取数异常（fail-open）: %s", e)
        project_context.setdefault("tb_amount", 0)

    # 附注适用性
    standards = str(project_context.get("applicable_standards", "")).lower()
    disclosure_visibility = {
        "listed": "listed" in standards,
        "soe": "soe" in standards,
    }

    html_data = {
        "sections": sections,
        "adjudication_config": adjudication_config,
        "project_context": project_context,
        "disclosure_visibility": disclosure_visibility,
        "responses_snapshot": responses_snapshot,
    }

    # ─── Tier B 四表库审定表预填（D7：宁缺勿造 R3.4，ADDITIVE，灰度开关控制）───────
    # spec: d-cycle-four-table-extraction-formulas (R1.1 / R2.3 / R3.4 / R7.1 / R7.2
    #        / Property 9)
    #
    # 【宁缺勿造决策】D7-1 审定表双区块固定分类（一、按性质：预收货款/开发项目预收款/
    # 预收工程款/其他；二、按账龄段），未审数由 D7-2 明细（`D7-2-rows`）经 SUMIF 聚合派生
    # （useD7Adjudication natAgg/agingByKey）；而 trial_balance / tb_balance 的 2205
    # **只有科目总额、无「性质/账龄」组合维度** → 无法把 TB 干净映射到分类行 → D7 render
    # **不返回 adjudication_prefill**（不臆造分类行未审数 = 诚实部分覆盖，对齐 R3.4，同 D3）。
    #
    # D7 四表库数据的正确落点（均为既有链路，本 render 不介入，手工优先精度）：
    #   * D7-1 `D7-1-adj-aging-trial-balance-currentAudited`（2205 总额，试算平衡表数核对行）
    #     —— 已由 render project_context.tb_amount(2205) seed（前端 tbSeedAmount 回退）；
    #     注册为 Tier A **可编辑**公式 TB('2205','期末余额')（公式管理面板可查可编，求值经
    #     get_active_filter 与 Tier B 同口径）。
    #   * D7-2 明细 ← tb_aux_balance 2205 按**客户/合同维度**归集（Tier B 复杂归集）—— 非
    #     单条公式，本 render 不介入、不冲突。
    #
    # → 因此 D7 render 输出在开关开/关时**逐字节等价**（不新增任何键，Property 9 天然成立，
    #   零回归）。
    if settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        logger.debug(
            "D7 render: 宁缺勿造（R3.4）— 无干净 TB→审定表分类行映射（性质/账龄 "
            "SUMIF from D7-2），不发 adjudication_prefill（wp_id=%s）",
            wp_id,
        )
        # ─── 取数溯源与三口径自检（新增，前端消费）────────────────────────────
        if d7_codes is not None:
            try:
                _d7_tb = await fetch_d_cycle_tb(ctx, d7_codes)
                html_data["tb_source_codes"] = build_d_tb_source_codes(d7_codes, _d7_tb)
                html_data["parent_check"] = _d7_tb.parent_check
            except Exception as e:  # noqa: BLE001 — fail-open
                logger.warning("D7 render: 取数溯源构造异常（fail-open）: %s", e)

        # ─── Tier A 公式驱动 TB 核对行 transient seed（P0-1 主机制）──────────────
        # spec: d-cycle-tier-a-writeback-detail-seed R3（决策1/3 / Property 6/7/10/11/13）
        # 用 resolve_effective 的有效 Tier A 公式（默认 TB('2205','期末余额')）求值 transient
        # seed 试算平衡表数核对行锚点 D7-1-adj-aging-trial-balance-currentAudited（及 registry
        # 登记的 priorAudited，若有预设）进 responses_snapshot（不落库；手工优先；disabled 跳过；
        # 写对字段 remark；fail-open）。主开关关（默认）→ 不 seed，零回归。
        try:
            await seed_tier_a_reconciliation(
                ctx,
                _D7_WP_CODE,
                responses_snapshot,
                resolve_effective=resolve_effective,
                evaluate_wp_formula_expression=evaluate_wp_formula_expression,
            )
        except Exception as e:  # noqa: BLE001 — 兜底 fail-open，不阻断 render
            logger.warning("D7 render: Tier A seed 兜底异常（fail-open）: %s", e)

    return html_data
