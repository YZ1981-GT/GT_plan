"""D6 合同资产 — 专属渲染策略.

component_type = "d6-contract-assets"
返回 html_data 含：审定表三区块结构 + 明细表行数据 + 减值明细 + ECL组合数据 + 各sheet配置。
数据持久化在 checklist_responses 表，item_id前缀为 "D6-{sheetCode}-{field}"。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from app.core.config import settings
from app.services.d_cycle_extraction.detail_aggregation import (
    aggregate_d6_detail_rows,
)
from app.services.d_cycle_extraction.prefill import (
    MODE_BALANCE,
    build_d_adjudication_prefill,
)
from app.services.d_cycle_extraction.presets import resolve_effective
from app.services.d_cycle_extraction.tier_a_seed import (
    seed_tier_a_reconciliation,
)
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression

from ._context import RenderContext

logger = logging.getLogger(__name__)

# D6 合同资产科目前缀（Tier B 审定表原值 block1 未审数取数来源）
_D6_ACCOUNT_PREFIX = "1402"

# D6 wp_code base（Tier A 提取公式 / 锚点登记 key）
_D6_WP_CODE = "D6"

# D6-2 明细表行存储 item_id（checklist_responses.remark 存 JSON 数组）
_D6_DETAIL_ITEM_ID = "D6-2-rows"


def _detail_rows_empty(responses_snapshot: dict) -> bool:
    """判定 D6-2 明细表是否完全空（手工优先 R4.2 / Property 8）.

    D6-2 行存储于 checklist_responses item_id=`D6-2-rows` 的 `remark` 字段（JSON 数组字符串，
    参照 import-aux-balance 端点 item_id）。`[]`/`null`/`{}`/空/缺失 = 空（可 seed）；
    非空数组 = 已有行（手工录入或既有一键取数结果）→ 不 seed（不覆盖）。

    判空稳健：无法解析或非列表结构一律保守视为「非空」（不 seed），避免覆盖不明数据。
    """
    val = (responses_snapshot or {}).get(_D6_DETAIL_ITEM_ID)
    if not isinstance(val, dict):
        return True  # 缺失
    remark = (val.get("remark") or "").strip()
    if not remark or remark in ("[]", "null", "{}"):
        return True  # 空/空标记
    try:
        parsed = json.loads(remark)
    except (ValueError, TypeError):
        return False  # 无法解析但非空 → 保守视为有内容，不 seed
    if isinstance(parsed, list):
        return len(parsed) == 0
    return False  # 非列表意外结构 → 保守视为非空


async def _seed_d6_detail_prefill(
    ctx: RenderContext, responses_snapshot: dict
) -> list[dict] | None:
    """P0-2：D6-2 明细表维度归集 transient 自动 seed（决策4 / R4 / Property 8/9/11/13）.

    D6-2 明细完全空时，调既有可复用归集 `aggregate_d6_detail_rows`（tb_aux_balance 1402
    客户/合同维度，复用不新造第 3 套四表库读取 / Property 9）得明细行，附 `source:"four-table"`
    标注供前端识别为自动取数，作 `detail_prefill` transient 返回（不落库 / Property 13）。
    手工优先（已有行 → 返回 None 不 seed / Property 8）+ fail-open 空（归集异常 → None / R4.5）。
    行字段用 aggregate_d6_detail_rows 产出的 30 列 schema。
    """
    if not _detail_rows_empty(responses_snapshot):
        return None  # 手工优先：已有行 → 不覆盖
    try:
        rows = await aggregate_d6_detail_rows(ctx.db, str(ctx.project_id))
    except Exception as e:  # noqa: BLE001 — 归集失败 fail-open 空（R4.5）
        logger.warning("D6 render: detail_prefill 归集失败（fail-open，省略）: %s", e)
        return None
    if not rows:
        return None
    return [{**row, "source": "four-table"} for row in rows]


def _block1_has_user_data(responses_snapshot: dict) -> bool:
    """判定审定表 block1（原值）是否已有用户/既有一键取数录入的未审数据.

    手工优先（R1.5 / Property 2）：block1 原值锚点完全为空时才自动预填；
    只要 block1 已有行键清单或任一原值未审 per-field 值非空，即视为已填，
    render 不再返回 adjudication_prefill（不覆盖手工/既有一键取数结果）。

    锚点来源见 `d_cycle_anchor_registry.json`（D6）：
      * `D6-1-adj-block1-rowKeys`（JSON 行键清单，结构性）
      * `re:^D6-1-adj-block1-.+-(priorUnadjusted|currentUnadjusted|...)$`（per-field）
    """
    for item_id, val in (responses_snapshot or {}).items():
        if not item_id.startswith("D6-1-adj-block1-"):
            continue
        remark = ""
        if isinstance(val, dict):
            remark = (val.get("remark") or "").strip()
        if item_id == "D6-1-adj-block1-rowKeys":
            # 行键清单非空数组视为已建行（用户/既有已填）
            if remark and remark not in ("[]", "null", "{}"):
                return True
            continue
        # per-field 原值未审数（期初/期末）非空即视为已填
        if item_id.endswith("-priorUnadjusted") or item_id.endswith("-currentUnadjusted"):
            if remark:
                return True
    return False


async def _seed_tier_a_reconciliation(ctx: RenderContext, responses_snapshot: dict) -> None:
    """D6 Tier A render transient seed —— 委托共享助手（DRY / Task 4.2）.

    从 Task 4.1 的 D6 私有实现提取到 `d_cycle_extraction.tier_a_seed`（供 D1-D7 复用），
    此处保留薄委托 + 注入 D6 模块级 `resolve_effective`/`evaluate_wp_formula_expression`
    （kwargs RHS 于**调用时**从 D6 模块全局解析 → 现有 D6 测试 monkeypatch `d6.*` 仍生效）。
    规则/语义/fail-open 完全等价原实现，详见共享助手 docstring。
    """
    await seed_tier_a_reconciliation(
        ctx,
        _D6_WP_CODE,
        responses_snapshot,
        resolve_effective=resolve_effective,
        evaluate_wp_formula_expression=evaluate_wp_formula_expression,
    )


async def render(ctx: RenderContext) -> dict | None:
    """D6 合同资产渲染策略.

    返回完整 html_data：
    - sections: 各sheet元数据配置
    - adjudication_config: 审定表三区块固定行结构
    - detail_columns: 明细表D6-2 30列定义
    - impairment_columns: 减值准备明细D6-3 14列定义
    - ecl_config: ECL测算D6-8配置
    - project_context: 项目上下文
    - disclosure_visibility: 适用性标准判断
    - responses_snapshot: 关键item_id的已保存数据
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 审定表三区块固定行结构 ───────────────────────────────────────────
    adjudication_config = {
        "blocks": [
            {
                "blockKey": "block1",
                "blockTitle": "一、合同资产原值",
                "subtotalLabel": "小计",
                "deductionLabel": "减：列示于其他非流动资产的合同资产",
                "totalLabel": "合同资产原值小计",
            },
            {
                "blockKey": "block2",
                "blockTitle": "二、合同资产坏账准备",
                "subtotalLabel": "小计",
                "deductionLabel": "减：列示于其他非流动资产的合同资产坏账准备",
                "totalLabel": "合同资产坏账准备小计",
            },
            {
                "blockKey": "block3",
                "blockTitle": "三、合同资产净值",
                "subtotalLabel": "小计",
                "deductionLabel": "减：列示于其他非流动资产的合同资产净值",
                "totalLabel": "合同资产净值合计",
                "extraRows": ["试算平衡表数", "差异数"],
            },
        ],
        "columns": [
            "项目", "期初未审", "期初AJE", "期初RJE", "期初审定",
            "期末未审", "期末AJE", "期末RJE", "期末审定", "变动额", "变动率", "原因分析",
        ],
    }

    # ─── sections 结构定义（12个sheet） ────────────────────────────────────
    sections = [
        {"code": "D6A", "label": "实质性程序表D6A", "type": "procedure"},
        {"code": "D6-1", "label": "合同资产审定表D6-1", "type": "adjudication"},
        {"code": "D6-2", "label": "合同资产明细表D6-2", "type": "detail"},
        {"code": "D6-3", "label": "合同资产减值准备明细表D6-3", "type": "impairment_detail"},
        {"code": "D6-4", "label": "调整分录汇总表D6-4", "type": "adjustment"},
        {"code": "D6-5", "label": "关联关系及交易检查D6-5", "type": "related_party"},
        {"code": "D6-6", "label": "合同资产检查表D6-6", "type": "inspection"},
        {"code": "D6-7", "label": "合同资产减值准备会计政策检查D6-7", "type": "policy_check"},
        {"code": "D6-8", "label": "合同资产减值准备测算D6-8", "type": "ecl_calculation"},
        {"code": "D6-9", "label": "减值准备转回核销检查D6-9", "type": "writeoff_check"},
        {"code": "D6-NOTE-LISTED", "label": "合同资产附注披露信息（上市公司）", "type": "disclosure"},
        {"code": "D6-NOTE-SOE", "label": "合同资产附注披露信息（国企）", "type": "disclosure"},
    ]

    # ─── ECL测算配置 ──────────────────────────────────────────────────────
    ecl_config = {
        "single_columns": [
            {"key": "debtorName", "label": "债务人名称", "width": 140, "editable": True},
            {"key": "auditedBalance", "label": "审定余额①", "width": 110, "editable": True, "type": "number"},
            {"key": "lossRate", "label": "损失率②", "width": 90, "editable": True, "type": "number"},
            {"key": "expectedProvision", "label": "应计提③", "width": 100, "editable": False, "formula": "①×②"},
            {"key": "bookBalance", "label": "账面余额④", "width": 100, "editable": True, "type": "number"},
            {"key": "difference", "label": "差异⑤", "width": 90, "editable": False, "formula": "③-④"},
            {"key": "basis", "label": "依据", "width": 120, "editable": True},
            {"key": "indexRef", "label": "索引号", "width": 80, "editable": True},
        ],
        "aging_bands": ["1年以内", "1-2年", "2-3年", "3-4年", "4-5年", "5年以上"],
    }

    # ─── 从 checklist_responses 加载关键数据快照 ──────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D6-%' "
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
        logger.warning("D6 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

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
        logger.warning("D6 render: project context 查询失败: %s", e)
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

    # bs_date for cutoff / post-period usage
    project_context["bs_date"] = f"{project_context['audit_year']}-12-31" if project_context["audit_year"] else ""

    # ─── TB预填: 科目1402合同资产期末审定/未审 ──────────────────────────
    tb_amount = 0
    try:
        tb_result = await db.execute(
            sa.text(
                "SELECT COALESCE(SUM(ABS(audited_amount)), SUM(ABS(unadjusted_amount)), 0) AS amount "
                "FROM trial_balance "
                "WHERE project_id = :pid AND standard_account_code LIKE '1402%' "
                "AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )
        tb_row = tb_result.fetchone()
        if tb_row and tb_row.amount:
            tb_amount = float(tb_row.amount)
    except Exception as e:
        logger.warning("D6 render: trial_balance 1402 查询失败: %s", e)

    project_context["tb_amount"] = tb_amount

    # ─── 关联方注册表 ────────────────────────────────────────────────────
    related_parties: list = []
    try:
        rp_result = await db.execute(
            sa.text(
                "SELECT name, relation_type "
                "FROM related_party_registry "
                "WHERE project_id = :pid AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )
        for rp_row in rp_result.fetchall():
            related_parties.append({
                "name": rp_row.name or "",
                "type": rp_row.relation_type or "",
            })
    except Exception as e:
        logger.warning("D6 render: related_party_registry 查询失败: %s", e)

    project_context["related_parties"] = related_parties

    # ─── Tier A 公式驱动 TB 核对行 transient seed（P0-1 主机制，灰度开关控制）─────
    # spec: d-cycle-tier-a-writeback-detail-seed R3（决策1/3 / Property 6/7/10/11/13）
    # 主开关关（默认）→ 不 seed，responses_snapshot 逐字节等价当前（Property 10 零回归）。
    # 主开关开 → 用 resolve_effective 的有效 Tier A 公式求值 transient seed TB 核对行锚点
    # （D6-1-tb-amount）进 responses_snapshot（不落库；手工优先；disabled 跳过；写对字段
    # remark；fail-open）。任一环异常一律 fail-open（不阻断 render）。
    if settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            await _seed_tier_a_reconciliation(ctx, responses_snapshot)
        except Exception as e:  # noqa: BLE001 — 兜底 fail-open，不阻断 render
            logger.warning("D6 render: Tier A seed 兜底异常（fail-open）: %s", e)

    html_data: dict = {
        "sections": sections,
        "adjudication_config": adjudication_config,
        "ecl_config": ecl_config,
        "project_context": project_context,
        "disclosure_visibility": disclosure_visibility,
        "responses_snapshot": responses_snapshot,
    }

    # ─── Tier B 四表库审定表预填（ADDITIVE，灰度开关控制）─────────────────
    # spec: d-cycle-four-table-extraction-formulas (R1.1/1.5/1.6/2.3/7.1/7.2)
    # 开关关闭（默认）→ 不返回 adjudication_prefill，render 逐字节等价当前（Property 9）。
    # 开关开启 → 从 tb_balance 1402 叶子子科目取期初/期末余额，仅在 block1 原值锚点
    # 完全为空时并入（手工优先 Property 2），供前端 seed block1 原值 期初/期末未审行。
    # 任一环异常一律 fail-open（省略 adjudication_prefill，不阻断 render）。
    if settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            if not _block1_has_user_data(responses_snapshot):
                seed_rows = await build_d_adjudication_prefill(
                    ctx, account_prefix=_D6_ACCOUNT_PREFIX, mode=MODE_BALANCE
                )
                if seed_rows:
                    # 镜像 K9/K1/N5：adjudication_prefill 为行列表，附来源标注供前端识别
                    # 为自动取数。D6 仅 block1（原值）四表可填 → opening/closing 映射
                    # 期初未审/期末未审（对齐 anchor registry D6-1-adj-block1-*）。
                    html_data["adjudication_prefill"] = [
                        {
                            "code": r["code"],
                            "name": r["name"],
                            "opening_balance": r["opening_balance"],
                            "closing_balance": r["closing_balance"],
                            "block": "block1",
                            "source": "four-table",
                        }
                        for r in seed_rows
                    ]
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "D6 render: adjudication_prefill 构建失败（fail-open，省略）: %s", e
            )

    # ─── P0-2：D6-2 明细表维度归集 transient 自动 seed（主 ∧ 子开关门控）──────
    # spec: d-cycle-tier-a-writeback-detail-seed R4（决策4 / Property 8/9/11/13）
    # 生效条件 = 主开关 D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED ∧ 子开关 D_CYCLE_DETAIL_SEED_ENABLED
    #   （子开关默认关，被主开关 AND；故可"发 P0-1、压 P0-2" / R5.2）。任一关 → 无 detail seed
    #   （Property 8/10 零回归）。
    # 明细完全空时调既有归集 aggregate_d6_detail_rows（复用不新造 / Property 9）transient seed
    # 明细行进 detail_prefill（不落库 / Property 13；手工优先：有行不 seed；fail-open 空 / R4.5）。
    # 前端手动"一键取数"按钮保留（自动 seed 为叠加 / R4.6）。任一环异常一律 fail-open。
    if (
        settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED
        and settings.D_CYCLE_DETAIL_SEED_ENABLED
    ):
        try:
            detail_prefill = await _seed_d6_detail_prefill(ctx, responses_snapshot)
            if detail_prefill:
                html_data["detail_prefill"] = detail_prefill
        except Exception as e:  # noqa: BLE001 — 兜底 fail-open，不阻断 render
            logger.warning("D6 render: detail_prefill 兜底异常（fail-open）: %s", e)

    return html_data
