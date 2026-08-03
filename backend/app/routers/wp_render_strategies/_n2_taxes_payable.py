"""N2 应交税费 — 专属渲染策略.

component_type = "n2-taxes-payable"

N2 前端组件 GtN2TaxesPayable 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/增值税测算/其他税费测算/房产税/土增税/出口退税等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 N2 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目2221应交税费（**贷方/负债类科目**）：期末=期初+贷方-借方
N税费循环最复杂底稿（18 sheet/~180+公式）。
多税种测算引擎：增值税/城建税及附加/房产税/土地增值税/出口退税。
数据持久化在 checklist_responses 表，item_id 前缀为 "N2-*"。

Requirements: 1.6
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext
from app.services.four_table import resolve_semantic_accounts
from app.services.four_table.n_cycle_specs import N2_SPEC

logger = logging.getLogger(__name__)

_N2_ACCOUNT_CODE = "2221"
_ADJUDICATED_ITEM_ID = "N2-1-adjudicated-amount"

N2_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税费审计程序表N2A", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税费审定表N2-1", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税费明细表N2-2", "component_type": "n2-taxes-payable"},
    {"sheet_name": "调整分录汇总N2-3", "component_type": "n2-taxes-payable"},
    {"sheet_name": "税收政策检查N2-4", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税金认定表N2-5", "component_type": "n2-taxes-payable"},
    {"sheet_name": "增值税测算表N2-6", "component_type": "n2-taxes-payable"},
    {"sheet_name": "出口退税核对表N2-7", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交其他税费测算表N2-8", "component_type": "n2-taxes-payable"},
    {"sheet_name": "房产税测算表N2-9", "component_type": "n2-taxes-payable"},
    {"sheet_name": "土地增值税测算表N2-10", "component_type": "n2-taxes-payable"},
    {"sheet_name": "应交税费检查表N2-11", "component_type": "n2-taxes-payable"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "n2-taxes-payable"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "n2-taxes-payable"},
]


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────


def _parse_num(v: Any) -> float:
    """安全解析数值，None/空/NaN→0.0."""
    if v is None or v == "":
        return 0.0
    try:
        f = float(v)
        return 0.0 if f != f else f  # NaN→0.0
    except (ValueError, TypeError):
        return 0.0


# ─── TB 取数（负债类！期末余额）──────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext, year: str | None = None) -> dict[str, Any]:
    """从 tb_balance 取科目2221应交税费余额数据（负债类贷方）."""

    # 科目定位（语义驱动，additive）
    try:
        _sem_accounts = await resolve_semantic_accounts(ctx, N2_SPEC)
    except Exception:  # noqa: BLE001
        _sem_accounts = None

    result: dict[str, Any] = {
        "account_code": _N2_ACCOUNT_CODE,
        "account_name": "应交税费",
        "direction": "credit",
        "begin_balance": 0,
        "debit_amount": 0,
        "credit_amount": 0,
        "end_balance": 0,
    }
    try:
        # 🔴 `get_active_filter` 是 **async** 且签名为 (db, table, project_id, year)。
        #    历史 bug：单参调用 `get_active_filter(ctx.project_id)` → TypeError 被下方
        #    `except Exception` 吞成 warning → TB 取数恒 0，且无任何报错线索
        #    （与 N5 同款坑，见 memory 踩坑铁律）。年度非数字则跳过取数（不崩）。
        try:
            year_int = int(year) if year else None
        except (ValueError, TypeError):
            year_int = None
        if year_int is None:
            return result
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, year_int
        )
        stmt = (
            sa.select(
                TbBalance.opening_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_balance,
            )
            .where(
                TbBalance.account_code == _N2_ACCOUNT_CODE,
                active_filter,
            )
            .limit(1)
        )
        row = (await ctx.db.execute(stmt)).fetchone()
        if row:
            # 读取真实列 opening_balance/closing_balance，输出键保持 begin_balance/end_balance（前端兼容）
            result["begin_balance"] = _parse_num(row.opening_balance)
            result["debit_amount"] = _parse_num(row.debit_amount)
            result["credit_amount"] = _parse_num(row.credit_amount)
            result["end_balance"] = _parse_num(row.closing_balance)
    except Exception as e:  # noqa: BLE001
        logger.warning("N2 render: TB 取数失败: %s", e)
    if _sem_accounts:
        result.setdefault('tb_source_codes', _sem_accounts.as_dict())

    return result


# ─── 审定表预填（从 tb_balance 2221% 叶子子科目按税种归类）────────────────────


def _classify_tax_type(account_name: str | None) -> str:
    """按科目名称归类税种。

    注意关键词包含关系导致的顺序敏感：
    「土地增值税」含「增值税」→ 必须先判 lvt；
    「城镇土地使用税」含「土地」→ 先判 land-use；
    「矿产资源补偿费」含「资源」→ 先于资源税；
    「代扣代缴外国企业所得税」含「企业所得税」→ 先于 cit；
    「代扣代缴个人所得税」含「个人所得税」→ 先于 iit；
    「地方教育」需先于「教育费附加」判定。

    输出键与 `composables/n2TaxLabelMap.ts::N2_TAX_LABEL_MAP[*].classifyKey` 对齐。
    """
    name = account_name or ""
    if "土地增值税" in name:
        return "lvt"
    if "城镇土地使用税" in name or "土地使用" in name:
        return "land-use"
    if "城市维护建设" in name or "城建" in name:
        return "urban"
    # 🔴 增值税必须返回 "vat"（曾错误返回 "urban"，把增值税余额计入城建税预填值）
    #
    # 🔴 「简易计税」**不含「增值税」子串**，必须单列判定 —— 源模板附注提示明确要求：
    #    「增值税，根据"应交税费-未交增值税、简易计税、转让金融商品应交增值税、
    #     代扣代缴增值税"科目贷方余额计算填列」
    #    实测项目 14fb8c10 的 `2221.08 应交税费_简易计税` 曾因此落到 other（漏计入增值税）。
    #    「转让金融商品应交增值税」「代扣代缴增值税」都含「增值税」，由下一条捕获。
    if "简易计税" in name:
        return "vat"
    if "增值税" in name:
        return "vat"
    # 🔴 矿产资源补偿费含「资源」子串 → 必须先于资源税判定
    if "矿产资源" in name:
        return "mineral"
    if "资源税" in name:
        return "resource"
    if "地方教育" in name:
        return "local-education"
    if "教育费附加" in name or "教育" in name:
        return "education"
    # 🔴 代扣代缴外国企业所得税含「企业所得税」→ 必须先判
    if "代扣代缴" in name and "外国" in name:
        return "wh-foreign-cit"
    if "企业所得税" in name:
        return "cit"
    # 🔴 代扣代缴个人所得税含「个人所得税」→ 必须先判
    if "代扣代缴" in name and "个人" in name:
        return "wh-iit"
    if "个人所得税" in name:
        return "iit"
    if "消费税" in name:
        return "consumption"
    if "印花税" in name:
        return "stamp"
    if "房产税" in name:
        return "property"
    if "车船" in name:
        return "vehicle"
    return "other"


# ─── classifyKey → 源模板披露 label（镜像前端 n2TaxLabelMap.ts）──────────────

#: `_classify_tax_type` 输出键 → N2-1/披露表源模板行 label。
#:
#: 🔴 **单一真源镜像**：前端 `composables/n2TaxLabelMap.ts` 的
#: `DISCLOSURE_LABEL_BY_CLASSIFY_KEY`（13 固定行）+ `normalizeTaxLabel` 的合并规则。
#: 契约测试 `test_n2_classify_tax_type.py` 从 `.ts` 源码正则抽取逐条比对，防双真源漂移。
#:
#: 合并规则（与前端 `normalizeTaxLabel` 逐条一致）：
#: - ``iit``（个人所得税）→ 「代扣代缴个人所得税」（源模板只有带前缀的那一行）
#: - ``local-education``（地方教育附加）→ 「教育费附加」（源模板一行合并列示）
#: 不在源模板 13 固定行的税种（``stamp`` 印花税 / ``other``）保留自身中文名，
#: 由前端作「增行」渲染（源模板 R21~R22 预留空行的语义）。
_CLASSIFY_KEY_TO_LABEL: dict[str, str] = {
    # ── 源模板 R8~R20 十三固定行 ──
    "cit": "企业所得税",
    "vat": "增值税",
    "consumption": "消费税",
    "resource": "资源税",
    "lvt": "土地增值税",
    "urban": "城市维护建设税",
    "vehicle": "车船牌照税",
    "property": "房产税",
    "land-use": "土地使用税",
    "education": "教育费附加",
    "mineral": "矿产资源补偿费",
    "wh-foreign-cit": "代扣代缴外国企业所得税",
    "wh-iit": "代扣代缴个人所得税",
    # ── 合并到固定行（与前端 normalizeTaxLabel 一致）──
    "iit": "代扣代缴个人所得税",
    "local-education": "教育费附加",
    # ── 源模板无固定行 → 增行 ──
    "stamp": "印花税",
    "other": "其他",
}

#: 源模板 R8~R20 行序（控制预填数组排序；不在表内的走末尾增行区）
_LABEL_SORT_ORDER: dict[str, int] = {
    "企业所得税": 1,
    "增值税": 2,
    "消费税": 3,
    "资源税": 4,
    "土地增值税": 5,
    "城市维护建设税": 6,
    "车船牌照税": 7,
    "房产税": 8,
    "土地使用税": 9,
    "教育费附加": 10,
    "矿产资源补偿费": 11,
    "代扣代缴外国企业所得税": 12,
    "代扣代缴个人所得税": 13,
}


async def _build_adjudication_prefill(
    ctx: RenderContext, year: str | None = None
) -> list[dict[str, Any]]:
    """从 tb_balance 科目2221%叶子子科目按税种预填审定表未审数（期初/期末）。

    - 查 2221% 全部子科目，优先取叶子（不是其他 code 前缀者），退而取全部；
      叶子检测天然选出最深层明细（三级退二级退一级）。
    - 按科目名称 `_classify_tax_type` 归类税种 → `_CLASSIFY_KEY_TO_LABEL` 转源模板 label。
    - 同 label 的多个叶子累加（如「增值税」与「未交增值税」并入一行）。
    - 负债类贷方，金额取 abs() 规避借正贷负符号。

    Returns:
        **数组**（按源模板 R8~R20 行序，增行在末尾），每项::

            {"tax_type": "增值税", "begin_unadj": 1000.0, "end_unadj": 2000.0,
             "classify_key": "vat", "account_codes": ["2221.01", ...]}

        🔴 **必须是数组不能是 dict**：前端 `N2TabAdjudication.vue` 用
        ``Array.isArray(pf) ? pf : null`` 判定，`useN2Adjudication14` 按
        ``p.tax_type / p.begin_unadj / p.end_unadj`` 取值。历史 bug：本函数曾返回
        ``dict[str,float]``（``{'N2-1-vat-audited': …}``）→ `Array.isArray` 恒 false
        → 预填 100% 失效、审定表永远空行、下游披露表也带不出数据，而 TS（`htmlData` 是
        `any`）/ vitest / 浏览器实测（项目本就无持久化行）全都查不出。
    """
    by_label: dict[str, dict[str, Any]] = {}
    try:
        # 🔴 同 `_fetch_tb_data`：`get_active_filter` 是 **async** 且签名
        #    (db, table, project_id, year)，单参调用会 TypeError 被吞 → 预填恒空。
        try:
            year_int = int(year) if year else None
        except (ValueError, TypeError):
            year_int = None
        if year_int is None:
            return []
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, year_int
        )
        stmt = sa.select(
            TbBalance.account_code,
            TbBalance.account_name,
            TbBalance.opening_balance,
            TbBalance.closing_balance,
        ).where(
            TbBalance.account_code.like(f"{_N2_ACCOUNT_CODE}%"),
            active_filter,
        )
        rows = (await ctx.db.execute(stmt)).fetchall()
        if not rows:
            return []
        codes = [r.account_code for r in rows]
        # 叶子 = 不是其他 code 前缀者（选出最深层明细）
        leaves = [
            r
            for r in rows
            if not any(other != r.account_code and other.startswith(r.account_code) for other in codes)
        ]
        if not leaves:
            leaves = list(rows)
        for r in leaves:
            tt = _classify_tax_type(r.account_name)
            # classifyKey → 源模板 label；未登记的 key 兜底用科目名（保证不丢数据）
            label = _CLASSIFY_KEY_TO_LABEL.get(tt) or (r.account_name or "其他")
            opening = abs(_parse_num(r.opening_balance))
            closing = abs(_parse_num(r.closing_balance))
            slot = by_label.get(label)
            if slot is None:
                slot = {
                    "tax_type": label,
                    "begin_unadj": 0.0,
                    "end_unadj": 0.0,
                    "classify_key": tt,
                    "account_codes": [],
                }
                by_label[label] = slot
            slot["begin_unadj"] = round(slot["begin_unadj"] + opening, 2)
            slot["end_unadj"] = round(slot["end_unadj"] + closing, 2)
            if r.account_code and r.account_code not in slot["account_codes"]:
                slot["account_codes"].append(r.account_code)
    except Exception as e:  # noqa: BLE001
        logger.warning("N2 render: adjudication prefill 构建失败: %s", e)
        return []

    # 按源模板 R8~R20 行序排序；不在固定行内的（印花税/其他/兜底科目名）排到末尾
    return sorted(
        by_label.values(),
        key=lambda s: (_LABEL_SORT_ORDER.get(str(s["tax_type"]), 999), str(s["tax_type"])),
    )


# ─── 主渲染函数 ───────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict[str, Any]:
    """N2 应交税费专属渲染策略.

    轻量返回：project_context + responses_snapshot + TB数据。
    前端 GtN2TaxesPayable 为自加载组件（各子组件独立拉取 checklist_responses）。
    """
    # ─── 读取 checklist_responses 快照（列名对齐 schema: wp_id/conclusion/remark） ───
    responses_snapshot: dict[str, Any] = {}
    adjudicated_amount: float | None = None
    try:
        rows = (
            await ctx.db.execute(
                sa.text(
                    "SELECT item_id, conclusion, remark "
                    "FROM checklist_responses "
                    "WHERE wp_id = :wid"
                ),
                {"wid": str(ctx.wp_id)},
            )
        ).fetchall()
        for r in rows:
            responses_snapshot[r.item_id] = {
                "item_id": r.item_id,
                "conclusion": r.conclusion,
                "remark": r.remark,
            }
        # 提取审定数
        if _ADJUDICATED_ITEM_ID in responses_snapshot:
            raw_adj = responses_snapshot[_ADJUDICATED_ITEM_ID].get("conclusion")
            if raw_adj is not None:
                adjudicated_amount = _parse_num(raw_adj)
    except Exception as e:  # noqa: BLE001
        logger.warning("N2 render: checklist_responses 查询失败: %s", e)

    # ─── 项目上下文 ────────────────────────────────────────────────────
    project_context: dict[str, str] = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
    }
    try:
        proj_row = (
            await ctx.db.execute(
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
    except Exception as e:  # noqa: BLE001
        logger.warning("N2 render: project context 查询失败: %s", e)

    # bs_date
    audit_year = project_context.get("audit_year")
    project_context["bs_date"] = f"{audit_year}-12-31" if audit_year else None  # type: ignore[assignment]

    # 关联方
    related_parties: list[str] = []
    try:
        rp_rows = (await ctx.db.execute(
            sa.text(
                "SELECT party_name FROM related_party_registry "
                "WHERE project_id = :pid AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )).fetchall()
        related_parties = [r.party_name for r in rp_rows]
    except Exception:  # noqa: BLE001
        pass
    project_context["related_parties"] = related_parties  # type: ignore[assignment]

    # ─── TB 取数（科目2221应交税费，贷方/负债类）────────────────────
    tb = await _fetch_tb_data(ctx, year=audit_year)

    # ─── 审定表预填（仅无持久化 N2-1-adjudication-rows 时，不覆盖用户编辑）───
    # 🔴 **数组**形态：前端 `Array.isArray(pf) ? pf : null` 判定，dict 会被判成 null。
    adjudication_prefill: list[dict[str, Any]] = []
    if "N2-1-adjudication-rows" not in responses_snapshot:
        adjudication_prefill = await _build_adjudication_prefill(ctx, year=audit_year)

    return {
        "account_code": _N2_ACCOUNT_CODE,
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        # 审定表预填（**数组**，按税种从 tb_balance 2221% 叶子子科目归类聚合，
        # 按源模板 R8~R20 行序排序；仅无持久化 N2-1-adjudication-rows 时非空）
        "adjudication_prefill": adjudication_prefill,
        # TB 余额数据（科目2221，贷方/负债类）
        "trial_balance": tb,
        # 负债类公式方向元数据
        "formula_direction": {
            "account_code": "2221",
            "account_name": "应交税费",
            "direction": "credit",  # 贷方/负债类！
            "end_balance_formula": "begin + credit - debit",  # 期末=期初+贷方-借方
            "note": (
                "负债类贷方科目：应交税费增加在贷方（计提时贷记2221），"
                "缴纳时借方减少。N税费循环最复杂底稿，涵盖增值税/城建税/"
                "教育费附加/房产税/土地增值税/出口退税多个税种。"
            ),
        },
        # N2 特有元数据
        "n2_metadata": {
            "engine": "multi_tax",
            "vat_formula": "payable_vat = output_vat - (input_vat - input_transfer_out)",
            "surtax_formula": "surtax = (vat + consumption_tax) × rate",
            "property_tax_by_value": "original_value × (1 - deduct_rate) × 1.2%",
            "property_tax_by_rent": "rent_income × 12%",
            "lvt_formula": "appreciation × rate - deduct_items × quick_deduct_coef",
            "cross_wp_links": ["N4", "L8"],
        },
        # sheet 列表元数据
        "sheets": N2_SHEETS,
        "component_type": "n2-taxes-payable",
    }
