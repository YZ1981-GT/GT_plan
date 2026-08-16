"""D1 应收票据 — 专属渲染策略.

component_type = "d1-notes-receivable"

D1 前端组件 GtD1NotesReceivable 为自加载组件（onMounted 调 checklist-responses
自行拉取数据），按 sheetName 分发到各子组件（审定表/明细/坏账/业务模式/备查簿/
贴现背书/贴息/附注等）。因此本渲染策略只需返回轻量 html_data（project_context +
responses_snapshot），关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，
避免多 sheet dispatch 循环把 D1 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "D1-*"。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.core.config import settings
from app.services.d_cycle_extraction.d1_account_resolver import (
    D1AccountCodes,
    resolve_d1_account_codes,
)
from app.services.d_cycle_extraction.d1_detail_seed import seed_d1_detail_rows
from app.services.d_cycle_extraction.presets import resolve_effective
from app.services.d_cycle_extraction.tier_a_seed import (
    seed_tier_a_reconciliation,
)
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression

from ._context import RenderContext

logger = logging.getLogger(__name__)

# D1 wp_code base（Tier A 提取公式 / 锚点登记 key）
_D1_WP_CODE = "D1"


def _net_tb_amount(project_context: dict) -> None:
    """把 TB 核对回退标量 ``tb_amount`` 归一为**净额**口径（原值 − 坏账准备）。

    🔴 口径必须与 Tier A 预设 ``D1-adj-tb-amount`` 一致（双证见该预设 description：
    源模板 ``审定表D1-1`` 的 ``E20=E18-E19`` 比的是「三、应收票据净值」；
    ``report_config`` 的 BS-005 在 soe_standalone 下亦为 ``TB('1121')-TB('1231-01')``）。

    主路径是 Tier A 公式求值后 transient seed 到锚点；本标量只是**前端 seed 回退**
    （`GtD1NotesReceivable.tbNotesReceivableAmount`）。此前回退留在原值口径 →
    一旦用户在公式管理里停用该 Tier A 公式，核对行就回落到原值，
    重现「差异恰好等于坏账准备」的假差异（实测项目 0ec33ac9：1,162,288.03）。

    原值保留在 ``tb_amount_gross``，供审定表做取数溯源展示（原值 − 坏账 = 净额）。
    灰度关时本函数不被调用 → render 输出逐字节等价（characterization 零回归）。
    """
    # 未解析出坏账准备（该项目无 1231-01 数据 / 查询 fail-open）→ 净额恒等于原值，
    # 不造 `tb_amount_gross` 溯源键，保持与灰度关时**逐字节等价**（characterization）。
    if "tb_amount" not in project_context or "tb_provision_amount" not in project_context:
        return
    provision = float(project_context.get("tb_provision_amount") or 0)
    for key in ("", "_unadjusted", "_audited"):
        gross_key = f"tb_amount{key}"
        if gross_key not in project_context:
            continue
        gross = float(project_context.get(gross_key) or 0)
        prov = float(project_context.get(f"tb_provision_amount{key}") or 0) if key else provision
        project_context[f"tb_amount_gross{key}"] = gross
        project_context[gross_key] = gross - prov


async def _seed_tb_provision_amount(
    ctx: RenderContext, project_context: dict, codes: D1AccountCodes
) -> None:
    """按解析出的**标准码**补 trial_balance 坏账准备核对标量（原地写 project_context）。

    `trial_balance.standard_account_code` 存标准码（实证 `1231-01`），故这里用
    `codes.provision_standard` 而非原始码。审定优先、审定为 0 回退未审（与原值同口径）。
    备抵科目在 trial_balance v2 正数口径下存正值，直接取绝对值归一为计提口径。
    失败 fail-open：不写键，前端按缺省 0 处理（不阻断 render）。
    """
    if not codes.provision_standard:
        return
    try:
        like_clauses = " OR ".join(
            f"standard_account_code LIKE :c{i}" for i in range(len(codes.provision_standard))
        )
        params: dict = {
            f"c{i}": f"{code}%" for i, code in enumerate(codes.provision_standard)
        }
        params.update({"pid": str(ctx.project_id), "year": ctx.year})
        row = (
            await ctx.db.execute(
                sa.text(
                    "SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadjusted, "
                    "COALESCE(SUM(audited_amount), 0) AS audited "
                    "FROM trial_balance "
                    "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                    f"AND ({like_clauses})"
                ),
                params,
            )
        ).fetchone()
        if row is None:
            return
        audited = abs(float(row.audited or 0))
        unadjusted = abs(float(row.unadjusted or 0))
        project_context["tb_provision_amount"] = audited if audited else unadjusted
        project_context["tb_provision_amount_unadjusted"] = unadjusted
        project_context["tb_provision_amount_audited"] = audited
    except Exception as e:  # noqa: BLE001
        logger.warning("D1 render: trial_balance 坏账准备查询失败（fail-open）: %s", e)


async def render(ctx: RenderContext) -> dict | None:
    """D1 应收票据渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtD1NotesReceivable，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 D1-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D1-%' "
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
        logger.warning("D1 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
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
            # bs_date（资产负债表日）：审计年度 → {year}-12-31，供 D1-3 期后回款/抽凭/截止取数使用
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("D1 render: project context 查询失败: %s", e)

    # 关联方清单：从关联方登记表（RelatedPartyRegistry）取项目级名单，供 D1-3 客户明细表关联方识别
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
        logger.warning("D1 render: related_parties 查询失败: %s", e)

    # 试算平衡表应收票据（科目 1121）未审/审定合计：供 D1-1 审定表试算平衡差异行预填 tb_amount，
    # 使审计师无需手工录入即可看到与 TB 的勾稽差异（审定行仍由 D1-2 明细带入，此处仅锚定 TB 数）。
    try:
        tb_row = (
            await db.execute(
                sa.text(
                    "SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadjusted, "
                    "COALESCE(SUM(audited_amount), 0) AS audited "
                    "FROM trial_balance "
                    "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                    "AND standard_account_code LIKE '1121%'"
                ),
                {"pid": str(ctx.project_id), "year": ctx.year},
            )
        ).fetchone()
        if tb_row:
            audited = float(tb_row.audited or 0)
            unadjusted = float(tb_row.unadjusted or 0)
            # 审定优先；审定为 0 时回退未审（TB 尚未回写审定数的场景）
            project_context["tb_amount"] = audited if audited else unadjusted
            project_context["tb_amount_unadjusted"] = unadjusted
            project_context["tb_amount_audited"] = audited
    except Exception as e:  # noqa: BLE001
        logger.warning("D1 render: trial_balance(1121) 查询失败: %s", e)

    html_data: dict = {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }

    # ─── 四表库取数 seed（D1：实证叶子映射，ADDITIVE，灰度开关控制）───────────────
    # spec: d1-four-table-extraction-formula-wiring (Wave 2 / R1.x R2.x / Property 3, 4)
    #
    # 【实证纠正「宁缺勿造」】已归档 spec d-cycle-four-table-extraction-formulas 曾判定
    # 「TB 1121 只有科目总额、无原值/坏账×银行/商业维度」故不 seed。对入库数据的只读核查
    # 证明该前提不成立——客户科目表在**叶子层**已干净编码 D1 所需两个维度：
    #   * 原值：1121.01 银行承兑汇票 / 1121.02 商业承兑汇票 / 1121.03 信用证
    #     （roll-forward 逐分精确：opening + debit − credit = closing，子科目 closing 之和
    #      = 1121 closing）。
    #   * 坏账：1231.01 坏账准备_应收票据（credit 备抵，两种符号约定下 abs 归一）。
    # 故 D1-2 原值明细 / D1-4 坏账准备明细经 `seed_d1_detail_rows` 从 tb_balance 叶子诚实
    # 取数 seed 进 responses_snapshot（transient 不落库；手工优先；leaf-only；fail-open），
    # 前端 useD1DetailCategory / useD1BadDebt 既有 loadFromResponses 路径零改动即消费。
    # D1-1 审定表原值/坏账未审经既有 cross-sheet 由 D1-2/D1-4 自动派生，净值 = 原值 − 坏账。
    #
    # 说明：本 render 仍**不返回** `adjudication_prefill` 键——D1 seed 走 responses_snapshot
    # 明细行（前端专属组件读 checklist_responses），非 D6 式 adjudication_prefill 顶层键。
    # 其它既有四表库落点保持不变：
    #   * D1-1 `D1-adj-tb-amount`（1121 总额 TB↔审定核对行）← Tier A 公式 `TB('1121','期末余额')`
    #     经 seed_tier_a_reconciliation transient seed（下方，手工优先，与本 seed 各写不同锚点）。
    #   * D1-3 客户明细 `D1-cust-rows` 期后兑付 ← 序时账 1121 贷方（前端一键取数，本 render 不介入）。
    #
    # 灰度关（默认）→ 不进本分支，输出与改动前逐字节等价（Property 3，零回归）。
    if settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        # ─── D1-2 原值 / D1-4 坏账明细行 transient seed（实证叶子映射）──────────────
        # 🔴 门控 = 主开关 ∧ 子开关 `D_CYCLE_DETAIL_SEED_ENABLED`（与 D6-2 同款）。
        # 子开关的语义是 D 循环**通用**的「明细表维度归集 render 自动 seed」（见 config.py：
        # 打开 D-cycle 明细表且明细行完全空时 transient seed 进 render、不落库、手工优先），
        # 本 seed 与之完全同类。首版只挂主开关 → 让文档承诺的「发 P0-1、压 P0-2」（开主开关
        # 拿 Tier A、同时压住明细自动 seed）对 D1 失效：运维为启用 Tier A 而开主开关时会
        # **静默**连带打开 D1 明细 seed 且无法单独回退。故此处与 D6 收敛为同一门控矩阵。
        # ─── 科目定位：报表规则映射驱动（spec d1-extraction-chain-completion R1）────
        # BS-005 应收票据 → report_config.formula → 标准码（1121 / 1231-01）
        #   → account_mapping 反解 → 该项目**原始码**（tb_balance 存原始码）。
        # 全程 fail-open：解析失败回退 1121 / 1231 前缀（等价改动前行为）。
        # 挂在主开关下（不受明细 seed 子开关约束）：`tb_source_codes` 与坏账 TB 核对
        # 标量属 Tier A 取数溯源，与「明细自动 seed」是两件事。
        d1_codes = None
        try:
            d1_codes = await resolve_d1_account_codes(ctx)
            html_data["tb_source_codes"] = d1_codes.as_dict()
        except Exception as e:  # noqa: BLE001
            logger.warning("D1 render: 科目解析异常（fail-open 用兜底前缀）: %s", e)

        # 坏账准备 TB 核对标量（trial_balance 存**标准码**，故用 provision_standard）：
        # 原值 tb_amount 已在上方按 1121% 查过；此处按解析结果补齐坏账口径，供
        # D1-1「二、应收票据坏账准备」区块与 TB 核对（灰度关时不查、行为不变）。
        if d1_codes is not None:
            await _seed_tb_provision_amount(ctx, project_context, d1_codes)
            _net_tb_amount(project_context)

            # ─── 三口径自检（新增，纯加法）─────────────────────────────────
            # spec: d-cycle-four-table-extraction-and-disclosure-completion R1.6
            # 🔴 D1 的科目定位路径（`resolve_d1_account_codes`）**刻意不动** —— 它是本
            # spec 的零回归红线。这里只追加 `parent_check`：叶子和 / 父行 / trial_balance
            # 三个口径并列，用于暴露 `trial_balance` 的父子双算（实证 `1231` 父行与
            # `1231-01..05` 子行在本表**并存**）。只比对前两个口径发现不了这类差异。
            try:
                from app.services.d_cycle_extraction.d_tb_fetch import (
                    fetch_d_cycle_tb as _fetch_d1_tb,
                )

                _d1_tb = await _fetch_d1_tb(ctx, d1_codes)
                html_data["parent_check"] = _d1_tb.parent_check
            except Exception as e:  # noqa: BLE001 — fail-open
                logger.warning("D1 render: parent_check 构造异常（fail-open）: %s", e)

        if settings.D_CYCLE_DETAIL_SEED_ENABLED:
            try:
                await seed_d1_detail_rows(ctx, responses_snapshot, d1_codes)
            except Exception as e:  # noqa: BLE001 — 兜底 fail-open，不阻断 render
                logger.warning("D1 render: 明细 seed 兜底异常（fail-open）: %s", e)

        # ─── Tier A 公式驱动 TB 核对行 transient seed（P0-1 主机制）──────────────
        # spec: d-cycle-tier-a-writeback-detail-seed R3（决策1/3 / Property 6/7/10/11/13）
        # 用 resolve_effective 的有效 Tier A 公式（默认 TB('1121','期末余额')）求值 transient
        # seed 单标量 TB↔审定净值核对行锚点 D1-adj-tb-amount 进 responses_snapshot（不落库；
        # 手工优先；disabled 跳过；写对字段 remark；fail-open）。主开关关（默认）→ 不 seed，零回归。
        try:
            await seed_tier_a_reconciliation(
                ctx,
                _D1_WP_CODE,
                responses_snapshot,
                resolve_effective=resolve_effective,
                evaluate_wp_formula_expression=evaluate_wp_formula_expression,
            )
        except Exception as e:  # noqa: BLE001 — 兜底 fail-open，不阻断 render
            logger.warning("D1 render: Tier A seed 兜底异常（fail-open）: %s", e)

    return html_data
