"""D2 应收账款 — 专属渲染策略.

component_type = "d2-accounts-receivable"

与 D4 同理：前端 GtD2AccountsReceivable 为 sheetName 分发组件（外层 GtWpRenderer 目录行 chips 导航），
本策略返回轻量 html_data，使 component_type 命中 RENDERER_DISPATCH，避免多 sheet
dispatch 循环把 D2 各 sheet 重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "D2-*"。
"""

from __future__ import annotations

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

# D2 wp_code base（Tier A 提取公式 / 锚点登记 key）
_D2_WP_CODE = "D2"


async def render(ctx: RenderContext) -> dict | None:
    """D2 应收账款渲染策略 — 返回轻量 html_data。"""
    wp_id = ctx.wp_id
    db = ctx.db

    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D2-%' "
                "LIMIT 1000"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("D2 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
        "bs_date": "",
        "related_parties": [],
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
            # bs_date（资产负债表日）：审计年度 → {year}-12-31，供 D2-7 凭证检查/截止测试/期后回款取数使用
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("D2 render: project context 查询失败: %s", e)

    # 关联方清单：从关联方登记表（RelatedPartyRegistry）取项目级名单，供 D2-2 明细表关联方自动识别
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
        logger.warning("D2 render: related_parties 查询失败: %s", e)

    html_data: dict = {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }

    # ─── Tier B 四表库审定表预填（D2：宁缺勿造 R3.4，ADDITIVE，灰度开关控制）───────
    # spec: d-cycle-four-table-extraction-formulas (R1.1 / R2.3 / R3.4 / R7.1 / R7.2
    #        / Property 9)
    #
    # 【宁缺勿造决策】D2-1 审定表按**信用风险组合方式**固定三分类行（单项计提 /
    # 账龄组合 / 客户类型组合），而 trial_balance / tb_balance 的 1122 应收账款
    # **只有科目总额、无信用风险组合维度**（分类是审计判断，非科目结构）→ 无法把
    # TB 叶子子科目干净映射到分类行。故 D2 render **不返回 adjudication_prefill**
    # （不臆造分类行未审数 = 诚实的部分覆盖，对齐 R3.4）。
    #
    # D2 四表库数据的正确落点（均为既有链路，本 render 不重复介入，手工优先精度）：
    #   * D2-1 `D2-adj-tb-amount`（1122 总额，TB↔审定核对行）—— 已由前端
    #     `useD2FormData.loadAll` 从 trial_balance 1122 seed；并注册为 Tier A **可编辑**
    #     公式 `TB('1122','期末余额')`（d_cycle_extraction_presets.json，公式管理面板
    #     可查可编，求值经 get_active_filter 与 Tier B 同口径）。本 render 不重复 seed。
    #   * D2-1 分类行未审 ← D2-2 明细 **SUMIF 聚合**（`useD2Adjudication`，按信用风险
    #     组合方式），非四表库直接可填。
    #   * D2-2 明细 ← `tb_aux_balance` 1122 按**客户维度**归集（`importFromAuxBalance`，
    #     Tier B 复杂归集）+ 序时账期后回款（`importPostPaymentFromLedger`）—— 前端既有
    #     一键取数，非单条公式，本 render 不介入、不与之冲突。
    #
    # → 因此 D2 render 输出在开关开/关时**逐字节等价**（不新增 adjudication_prefill
    #   或任何键，Property 9 天然成立，零回归）。保留此显式分支为决策文档锚点：未来若
    #   D2-1 结构支持叶子明细行、或出现可干净映射的四表库维度，可在此接入 Tier B seed。
    if settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        logger.debug(
            "D2 render: 宁缺勿造（R3.4）— 无干净 TB→审定表分类行映射，"
            "不发 adjudication_prefill（wp_id=%s）",
            wp_id,
        )

        # ─── 科目定位：报表规则映射驱动（替代硬编码 1122 / 1231-02）─────────────
        # spec: d-cycle-four-table-extraction-and-disclosure-completion R1
        #
        # 改造前这里是两段硬编码 `LIKE '1122%'` / `LIKE '1231-02%'` 的裸 SQL，且
        # `tb_source_codes` 自标 `resolved_from="hardcoded"`。金额本身是对的
        # （前缀精确到子码、无 1231 父子双算），问题在于 **`report_config` 改科目就失效**：
        # BS-006 的公式在四个准则下并不相同（`listed_standalone` 是
        # `TB('1122') - TB('1231')` 用**整个 1231**、`soe_standalone` 才是 `1231-02`、
        # 两个 consolidated 不减备抵），硬编码只能对上其中一种。
        #
        # 🔴 备抵必须**无条件**叠名称过滤：`account_mapping` 有一条 `auto_fuzzy` 错映射
        # `1231.05 坏账准备_长期应收款 → 1231-02`（2 个项目）。此时
        # `provision_resolved_from='report_config'` ⇒ 共享件的 `use_provision_name_filter`
        # 为 False ⇒ 既有机制**不叠过滤** ⇒ 长期应收款的坏账会进入 D2 备抵。
        # 过滤在 `fetch_d_cycle_tb` 内部按 `subject_keywords=('应收账款',)` 执行
        # （关键词不能写宽成「应收」—— 那条错映射的科目名含「应收」但不含「应收账款」）。
        d2_codes = None
        try:
            d2_codes = await resolve_d_cycle_account_codes(ctx, _D2_WP_CODE)
        except Exception as e:  # noqa: BLE001 — fail-open
            logger.warning("D2 render: 科目解析异常（fail-open 用兜底码）: %s", e)

        if d2_codes is not None:
            # TB 核对标量（净额口径：原值 − 坏账准备）。
            # 源模板 审定表D2-1 的被比较项是「三、应收账款净值」合计 A27；
            # report_config BS-006 soe_standalone 同口径。
            # 给 project_context 下发 tb_amount（净额）供前端 seed 回退，保证
            # 「灰度开 + Tier A 被停用」时核对行不回落到原值（D1 同款缺陷已实测）。
            await seed_tb_amount_scalars(
                ctx, d2_codes, project_context, net_of_provision=True
            )

            # tb_balance 叶子级取数 + 备抵名称过滤 + 三口径自检（前端消费，非 dead output）
            d2_tb = await fetch_d_cycle_tb(ctx, d2_codes)
            html_data["tb_source_codes"] = build_d_tb_source_codes(d2_codes, d2_tb)
            html_data["parent_check"] = d2_tb.parent_check

        # ─── Tier A 公式驱动 TB 核对行 transient seed（P0-1 主机制）──────────────
        # spec: d-cycle-tier-a-writeback-detail-seed R3（决策1/3 / Property 6/7/10/11/13）
        # 用 resolve_effective 的有效 Tier A 公式（默认 TB('1122','期末余额')）求值 transient
        # seed 单标量 TB 核对行锚点 D2-adj-tb-amount 进 responses_snapshot（不落库；手工优先；
        # disabled 跳过；写对字段 remark；fail-open）。主开关关（默认）→ 不 seed，零回归。
        try:
            await seed_tier_a_reconciliation(
                ctx,
                _D2_WP_CODE,
                responses_snapshot,
                resolve_effective=resolve_effective,
                evaluate_wp_formula_expression=evaluate_wp_formula_expression,
            )
        except Exception as e:  # noqa: BLE001 — 兜底 fail-open，不阻断 render
            logger.warning("D2 render: Tier A seed 兜底异常（fail-open）: %s", e)

    return html_data
