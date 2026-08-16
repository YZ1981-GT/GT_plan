"""D3 预收账款 — 专属渲染策略.

component_type = "d3-prepaid-accounts"
返回 html_data 含：审定表双区块配置 + 明细表列定义 + 各sheet元数据 + 项目上下文。
数据持久化在 checklist_responses 表，item_id前缀为 "D3-{sheetPrefix}-{field}"。
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

# D3 wp_code base（Tier A 提取公式 / 锚点登记 key）
_D3_WP_CODE = "D3"


async def render(ctx: RenderContext) -> dict | None:
    """D3 预收账款渲染策略.

    返回完整 html_data：
    - sections: 各sheet元数据配置
    - adjudication_config: 审定表双区块固定结构
    - project_context: 项目上下文
    - applicable_standards: 适用性标准判断
    - responses_snapshot: 关键item_id的已保存数据
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 审定表双区块结构 ──────────────────────────────────────────────────
    adjudication_config = {
        "nature_rows": [
            {"rowKey": "fixed-asset-sales", "label": "预收销售固定资产款"},
            {"rowKey": "land-use-right", "label": "预收销售土地使用权款"},
            {"rowKey": "contract-invalid", "label": "合同不成立时已收取的对价"},
            {"rowKey": "other", "label": "其他"},
        ],
        "aging_rows": [
            {"rowKey": "within-1-year", "label": "1年以内"},
            {"rowKey": "1-to-2-years", "label": "1至2年"},
            {"rowKey": "2-to-3-years", "label": "2至3年"},
            {"rowKey": "over-3-years", "label": "3年以上"},
        ],
    }

    # ─── sections 结构定义（9个Tab） ──────────────────────────────────────
    sections = [
        {"code": "D3A", "label": "D3A 程序表", "type": "procedure"},
        {"code": "D3-1", "label": "D3-1 审定表", "type": "adjudication"},
        {"code": "D3-2", "label": "D3-2 明细表", "type": "detail"},
        {"code": "D3-3", "label": "D3-3 调整分录", "type": "adjustment"},
        {"code": "D3-4", "label": "D3-4 分析表", "type": "analysis"},
        {"code": "D3-5", "label": "D3-5 长期检查", "type": "long_term"},
        {"code": "D3-6", "label": "D3-6 关联方", "type": "related_party"},
        {"code": "D3-7", "label": "D3-7 凭证检查", "type": "voucher_check"},
        {"code": "D3-NOTE", "label": "附注", "type": "disclosure"},
    ]

    # ─── 从 checklist_responses 加载关键数据快照 ──────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D3-%' "
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
        logger.warning("D3 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 + 适用性判断 ─────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
        "applicable_standards": "",
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
        logger.warning("D3 render: project context 查询失败: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass

    # 附注适用性
    raw_std = project_context["applicable_standards"]
    standards = raw_std.lower() if isinstance(raw_std, str) else ""
    disclosure_visibility = {
        "listed": "listed" in standards,
        "soe": "soe" in standards,
    }

    # ─── 本循环 TB 核对标量（预收款项 2203）─────────────────────────────────
    # spec: d-cycle-four-table-extraction-and-disclosure-completion R1 / Task 6
    #
    # 🔴 改造前 D3 **一次都没查过自己的科目** —— 全文只有下方那段 `2205%`（那是有意的
    # D3↔D7 交叉核对，取的是**合同负债**），于是 `project_context` 里既无 `tb_amount`
    # 也无任何本循环金额。审定表的 TB 核对数只能靠 Tier A transient seed
    # （锚点 `D3-adj-trial-balance-amount`），一旦该 Tier A 公式被停用或灰度关闭，
    # 前端就完全没有回退来源。
    #
    # 实证：`2203` 在 `trial_balance` 有 9 个项目 / 合计 77,338,768.39
    # （而它一直查的 `2205` 只有 7,855.34，差 4 个数量级）。
    #
    # 本段补齐 `tb_amount` / `tb_amount_unadjusted` / `tb_amount_audited`
    # （与 D5/D6/D7 同键名，前端 seed 回退才能命中），并经 `resolve_d_cycle_account_codes`
    # 走报表规则映射（`BS-046`），不硬编码 `2203`。
    d3_codes = None
    try:
        d3_codes = await resolve_d_cycle_account_codes(ctx, _D3_WP_CODE)
        await seed_tb_amount_scalars(
            ctx, d3_codes, project_context, write_zero_when_missing=True
        )
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning("D3 render: 科目解析/取数异常（fail-open）: %s", e)
        project_context.setdefault("tb_amount", 0)

    # ─── D7 合同负债(2205)审定数注入（供 D3 披露表 D3↔D7 交叉核对）─────────────
    # 前端 D3TabDisclosureListed/Soe 读 allResponses['D3-d7-tb-audited-amount'].remark
    # 显示「预收账款(D3) + 合同负债(D7)」金额对照（CAS14 预收拆分口径核对）。
    # trial_balance 2205 审定额 = 全项目合同负债权威真源（两底稿共用 TB 单一真源），
    # 与 D7 审定表回写后的 TB 一致。
    try:
        d7_result = await db.execute(
            sa.text(
                "SELECT SUM(audited_amount) AS total "
                "FROM trial_balance "
                "WHERE project_id = :pid AND standard_account_code LIKE '2205%' "
                "AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )
        d7_row = d7_result.fetchone()
        d7_audited = float(d7_row.total) if d7_row and d7_row.total is not None else None
        if d7_audited is not None:
            # 负债贷方存正数（trial_balance v2 正数口径），直接用
            responses_snapshot["D3-d7-tb-audited-amount"] = {
                "conclusion": "",
                "remark": str(d7_audited),
            }
    except Exception as e:  # noqa: BLE001
        logger.debug("D3 render: D7(2205) TB 审定查询失败（不阻断）: %s", e)

    html_data: dict = {
        "sections": sections,
        "adjudication_config": adjudication_config,
        "project_context": project_context,
        "disclosure_visibility": disclosure_visibility,
        "responses_snapshot": responses_snapshot,
    }

    # ─── Tier B 四表库审定表预填（D3：宁缺勿造 R3.4，ADDITIVE，灰度开关控制）───────
    # spec: d-cycle-four-table-extraction-formulas (Task 5.2 / R1.1 R2.3 R3.4 R7.1 R7.2
    #        / Property 9)
    #
    # 【宁缺勿造决策】D3-1 审定表按**双区块固定分类**（一、按性质：预收销售固定资产款 /
    # 土地使用权款 / 合同不成立时已收取的对价 / 其他；二、按账龄：账龄配置段），未审数由
    # **D3-2 明细（`D3-det-rows`）经 cross-sheet 按性质 / 账龄 SUMIF 聚合**填入
    # （`useD3Adjudication` natureAggregation / agingByKey），非从 tb_balance 叶子直接填。
    # trial_balance / tb_balance 2203 预收账款**只有科目总额、无「性质 / 账龄」组合维度**
    # （分类是审计判断，非科目结构）→ 无法把 TB 干净映射到审定表分类行。故 D3 render
    # **不返回 adjudication_prefill**（不臆造分类行未审数 = 诚实的部分覆盖，对齐 R3.4）。
    #
    # D3 四表库数据的正确落点（均为既有链路，本 render 不重复介入，手工优先精度）：
    #   * D3-1 `D3-adj-trial-balance-amount`（2203 总额，TB↔账龄合计核对行，同为 D3-2
    #     明细核对标量）—— 注册为 Tier A **可编辑**公式 `TB('2203','期末余额')`
    #     （d_cycle_extraction_presets.json，公式管理面板可查可编，求值经 get_active_filter
    #     与 Tier B 同口径，seed 到该锚点）。本 render 不重复 seed（不与 Tier A 求值路径竞争）。
    #   * D3-1 分类行未审 ← D3-2 明细 **SUMIF 聚合**（`useD3Adjudication`，按性质 / 账龄），
    #     非四表库直接可填。
    #   * D3-2 明细 ← `tb_aux_balance` 2203 按**客户维度**归集（`importFromAuxBalance`
    #     → `/d3/import-aux-balance`，Tier B 复杂归集）—— 前端既有一键取数，非单条公式，
    #     本 render 不介入、不与之冲突。
    #
    # → 因此 D3 render 输出在开关开/关时**逐字节等价**（不新增 adjudication_prefill 或任何键，
    #   Property 9 天然成立，零回归）。保留此显式分支为决策文档锚点：未来若 D3-1 结构支持
    #   叶子明细行、或出现可干净映射的四表库维度，可在此接入 Tier B seed。
    if settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        logger.debug(
            "D3 render: 宁缺勿造（R3.4）— 无干净 TB→审定表分类行映射（性质/账龄固定分类），"
            "不发 adjudication_prefill（wp_id=%s）",
            wp_id,
        )
        # ─── 取数溯源与三口径自检（新增，前端消费）────────────────────────────
        if d3_codes is not None:
            try:
                _d3_tb = await fetch_d_cycle_tb(ctx, d3_codes)
                html_data["tb_source_codes"] = build_d_tb_source_codes(d3_codes, _d3_tb)
                html_data["parent_check"] = _d3_tb.parent_check
            except Exception as e:  # noqa: BLE001 — fail-open
                logger.warning("D3 render: 取数溯源构造异常（fail-open）: %s", e)

        # ─── Tier A 公式驱动 TB 核对行 transient seed（P0-1 主机制）──────────────
        # spec: d-cycle-tier-a-writeback-detail-seed R3（决策1/3 / Property 6/7/10/11/13）
        # 用 resolve_effective 的有效 Tier A 公式（默认 TB('2203','期末余额')）求值 transient
        # seed 单标量 TB↔账龄合计核对行锚点 D3-adj-trial-balance-amount 进 responses_snapshot
        # （不落库；手工优先；disabled 跳过；写对字段 remark；fail-open）。主开关关 → 零回归。
        try:
            await seed_tier_a_reconciliation(
                ctx,
                _D3_WP_CODE,
                responses_snapshot,
                resolve_effective=resolve_effective,
                evaluate_wp_formula_expression=evaluate_wp_formula_expression,
            )
        except Exception as e:  # noqa: BLE001 — 兜底 fail-open，不阻断 render
            logger.warning("D3 render: Tier A seed 兜底异常（fail-open）: %s", e)

    return html_data
