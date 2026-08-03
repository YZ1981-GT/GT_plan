"""N1 递延所得税资产 — 专属渲染策略.

component_type = "n1-deferred-tax-assets"

N1 前端组件 GtN1DeferredTaxAssets 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/测算表/亏损检查/调整/附注等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 N1 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目1811递延所得税资产（**借方/资产类科目**）：期末=期初+借方-贷方
N税费循环中的资产类科目。可抵扣暂时性差异×适用税率=递延所得税资产。
数据持久化在 checklist_responses 表，item_id 前缀为 "N1-*"。

Requirements: 1.6
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.report_account_mapping import resolve_report_line_account_codes

from ._context import RenderContext
from app.services.four_table import resolve_semantic_accounts
from app.services.four_table.n_cycle_specs import N1_SPEC

logger = logging.getLogger(__name__)

_N1_ACCOUNT_CODE = "1811"
_N1_LIABILITY_ACCOUNT_CODE = "2901"

# 报表行编码（**DB 只读实证**：`report_config` 四套准则 listed/soe × standalone/consolidated
# 全部一致 —— `BS-036 递延所得税资产 = TB('1811','期末余额')`、
# `BS-067 递延所得税负债 = TB('2901','期末余额')`）。
# 🔴 仓库里曾并存 `BS-049` / `BS-018` 两个错写法：实测 `BS-049` = 应交税费，
# `BS-018` 在上市是「流动资产合计」、在国企是「存货」→ 一律不得使用。
_ASSET_ROW_CODE = "BS-036"
_LIABILITY_ROW_CODE = "BS-067"
# 🔴 审定数真源键：前端 useN1Adjudication._syncTotals 写 `N1-1-total-audited` 的 remark 列。
# 旧常量 `N1-1-adjudicated-amount`(conclusion) 前端从未写过 → adjudicated_amount 恒 None（死字段）。
_ADJUDICATED_ITEM_ID = "N1-1-total-audited"
_ADJUDICATED_LEGACY_ITEM_ID = "N1-1-adjudicated-amount"

N1_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "n1-deferred-tax-assets"},
    {"sheet_name": "递延所得税资产审计程序表的N1A", "component_type": "n1-deferred-tax-assets"},
    {"sheet_name": "递延所得税资产审定表N1-1", "component_type": "n1-deferred-tax-assets"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "n1-deferred-tax-assets"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "n1-deferred-tax-assets"},
    {"sheet_name": "递延所得税资产明细表N1-2", "component_type": "n1-deferred-tax-assets"},
    {"sheet_name": "调整分录汇总N1-3", "component_type": "n1-deferred-tax-assets"},
    {"sheet_name": "递延所得税资产（负债）测算表N1-4", "component_type": "n1-deferred-tax-assets"},
    {"sheet_name": "可用以后年度税前利润弥补的亏损检查表的N1-5", "component_type": "n1-deferred-tax-assets"},
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


# ─── TB 取数（资产类！期末余额）──────────────────────────────────────────────


def _code_predicate(code: str):
    """单个科目码 → tb_balance 过滤谓词（单码走前缀、``start~end`` 走区间）。

    与 `report_account_mapping.build_trial_balance_code_filter` 同语义，但那个函数
    把列名写死为 `standard_account_code`（`trial_balance` 的列），而这里查的是
    `tb_balance`（列名 `account_code`）→ 只能自建谓词，不能复用。
    """
    if "~" in code:
        lo, hi = (p.strip() for p in code.split("~", 1))
        return sa.and_(
            TbBalance.account_code >= lo,
            TbBalance.account_code <= hi + "\uffff",  # 覆盖区间上界下所有子科目
        )
    return TbBalance.account_code.like(f"{code}%")


def _leaf_rows(rows: list[Any]) -> list[Any]:
    """只保留叶子行（无更深层级），防与中间级 rollup 双算。

    🔴 有意用**不带点**的 `startswith`：科目表既有点分层级（`1811.01`）也有
    平铺层级（`181101`），不带点两者都能正确判定；带点会把平铺层级的父级也当叶子
    → 与子科目双算。
    """
    codes = [(r.account_code or "").strip() for r in rows]
    return [
        r
        for r in rows
        if not any(
            c != (r.account_code or "").strip()
            and c.startswith((r.account_code or "").strip())
            for c in codes
        )
    ]


async def _resolve_account_codes(
    ctx: RenderContext, row_code: str, fallback: list[str]
) -> list[str]:
    """按报表行规则映射解析取数科目集（fail-open）。

    走 `report_config.formula` 单一真源，使项目级自定义映射（企业编码/口径差异）
    能自动带到底稿取数；解析失败 / 无配置 / 公式为空一律回退 `fallback`，
    绝不阻断渲染。
    """
    try:
        codes = await resolve_report_line_account_codes(
            ctx.db, ctx.project_id, row_code, fallback=fallback
        )
        return [c for c in codes if str(c).strip()] or list(fallback)
    except Exception as e:  # noqa: BLE001 — 映射解析失败按 fallback 处理
        logger.warning("N1 render: 报表行 %s 科目映射解析失败: %s", row_code, e)
        return list(fallback)


async def _fetch_tb_for_codes(
    ctx: RenderContext,
    codes: list[str],
    *,
    account_name: str,
    direction: str,
    absolute: bool = False,
) -> dict[str, Any]:
    """从 tb_balance 取给定科目集的余额（科目级优先 → 无则叶子聚合）。

    Args:
        codes: 科目集（单码或 ``start~end`` 区间），来自报表行规则映射。
        direction: ``debit``（资产类 1811）/ ``credit``（负债类 2901）。
        absolute: 取绝对值归一。负债类必须开 —— 活体实测 `2901` 期末同时存在
            `-233512.19`（负数约定）与 `200530.32`（绝对值约定）两种符号口径。
    """
    result: dict[str, Any] = {
        "account_code": codes[0] if codes else "",
        "account_codes": list(codes),
        "account_name": account_name,
        "direction": direction,
        "begin_balance": 0,
        "debit_amount": 0,
        "credit_amount": 0,
        "end_balance": 0,
    }
    if not codes:
        return result
    try:
        # 平台统一范式：await get_active_filter(db, Table.__table__, project_id, year)
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
        )
        single_codes = {c.strip() for c in codes if "~" not in c}
        all_rows = (
            await ctx.db.execute(
                sa.select(
                    TbBalance.account_code,
                    TbBalance.opening_balance.label("begin_balance"),
                    TbBalance.debit_amount,
                    TbBalance.credit_amount,
                    TbBalance.closing_balance.label("end_balance"),
                ).where(
                    sa.or_(*[_code_predicate(c) for c in codes]),
                    active_filter,
                )
            )
        ).fetchall()

        # ① 优先取科目级精确行（父级即科目总额，不与子科目双算）
        rows = [r for r in all_rows if (r.account_code or "").strip() in single_codes]
        # ② 无科目级行（客户按子科目挂账）→ 取叶子子科目聚合
        if not rows:
            rows = _leaf_rows(list(all_rows))

        norm = abs if absolute else (lambda v: v)
        for row in rows:
            result["begin_balance"] += norm(_parse_num(row.begin_balance))
            result["debit_amount"] += norm(_parse_num(row.debit_amount))
            result["credit_amount"] += norm(_parse_num(row.credit_amount))
            result["end_balance"] += norm(_parse_num(row.end_balance))
        for k in ("begin_balance", "debit_amount", "credit_amount", "end_balance"):
            result[k] = round(result[k], 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("N1 render: TB 取数失败(%s): %s", account_name, e)
    return result


# ─── 审定表未审数预填（tb_balance 1811 子科目 → 暂时性差异 7 类）──────────────

# 审定表 7 类暂时性差异（对齐源模板 N1-1 A7~A13 与前端 N1_ADJUDICATION_CATEGORIES）
_N1_CATEGORY_OTHER = "其他"
_N1_ADJUDICATION_CATEGORIES = [
    "资产减值准备",
    "可抵扣亏损",
    "内部交易未实现利润",
    "公允价值变动",
    "租赁负债",
    "购入摊销年限小于税法规定的资产",
    _N1_CATEGORY_OTHER,
]


def _classify_n1_subaccount(name: str | None) -> str:
    """按子科目名称关键字归入审定表 7 类（无法识别 → 其他）。

    映射依据 = 源模板 N1-2 明细「类别」列语义 + 实测 tb_balance 子科目名
    （1811.02 资产减值准备 / 1811.04 可抵扣亏损 / 1811.07 经营租赁和企业年金 …）。
    """
    n = (name or "").strip()
    if any(k in n for k in ("减值", "坏账", "跌价")):
        return "资产减值准备"
    if "亏损" in n:
        return "可抵扣亏损"
    if any(k in n for k in ("内部交易", "未实现")):
        return "内部交易未实现利润"
    if "公允价值" in n:
        return "公允价值变动"
    if any(k in n for k in ("租赁", "使用权", "年金")):
        return "租赁负债"
    if "摊销" in n:
        return "购入摊销年限小于税法规定的资产"
    return _N1_CATEGORY_OTHER


# ─── 负债段语义槽（源模板 R23:R27）─────────────────────────────────────────────

# 🔴 用**英文语义槽**而非中文显示名作键：源模板负债段第 4 项两版用语不同
# （上市 A26「使用权资产」/ 国企 A26「租赁形成」）→ 中文名作键必然让一版对不上。
# 显示名映射的单一真源在前端 `N1_LIABILITY_SLOT_LABEL`。
_N1_LIABILITY_SLOT_OTHER = "other"
_N1_LIABILITY_SLOTS = [
    "depreciation",             # 购入摊销年限大于税法规定的资产
    "afs_fv",                   # 可供出售金融资产公允价值变动
    "investment_property_fv",   # 投资性房地产公允价值变动
    "lease",                    # 使用权资产(上市) / 租赁形成(国企)
    _N1_LIABILITY_SLOT_OTHER,   # 其他
]


def _classify_n1_liability_subaccount(name: str | None) -> str:
    """按子科目名称关键字归入负债段 5 个语义槽（无法识别 → ``other``）。

    映射依据 = 源模板 `附注披露信息（上市公司）` R23:R27 / `附注披露信息（国企）` R23:R27
    的行语义 + 实测 tb_balance 子科目名（2901.01 公允价值变动 /
    2901.02 固定资产加速折旧 / 2901.03 经营租赁相关）。

    🔴 判定顺序有意如此：`投资性房地产` 必须先于泛化的 `公允价值`，否则
    「投资性房地产公允价值变动」会被 `afs_fv` 抢走。同理 `加速折旧`（税法折旧快于
    账面 ⇒ 账面摊销年限大于税法规定）归 `depreciation`。
    """
    n = (name or "").strip()
    if "投资性房地产" in n:
        return "investment_property_fv"
    if any(k in n for k in ("加速折旧", "摊销年限", "折旧年限", "加速摊销")):
        return "depreciation"
    if any(k in n for k in ("租赁", "使用权")):
        return "lease"
    if "公允价值" in n:
        return "afs_fv"
    return _N1_LIABILITY_SLOT_OTHER


async def _fetch_sub_account_rows(
    ctx: RenderContext, codes: list[str]
) -> list[Any]:
    """取给定科目集下的**叶子子科目**行（排除科目级父行本身）。

    资产段与负债段预填共用，避免两处各写一份叶子判定。
    查询失败向上抛，由调用方按 fail-open 处理。
    """
    if not codes:
        return []
    active_filter = await get_active_filter(
        ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
    )
    rows = (
        await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
            ).where(
                sa.or_(*[_code_predicate(c) for c in codes]),
                active_filter,
            )
        )
    ).fetchall()
    # 排除科目级父行（它是总额，不参与分类拆分）
    roots = {c.strip() for c in codes if "~" not in c}
    sub = [r for r in rows if (r.account_code or "").strip() and (r.account_code or "").strip() not in roots]
    return _leaf_rows(sub)


def _aggregate_by_slot(
    rows: list[Any],
    classify,
    *,
    absolute: bool = False,
) -> dict[str, dict[str, float]]:
    """叶子行 → {槽: {opening, closing}}；全零槽跳过。

    Args:
        absolute: 负债类开启（活体实测 `2901` 两种符号约定并存，统一归一为正数）。
    """
    norm = abs if absolute else (lambda v: v)
    agg: dict[str, dict[str, float]] = {}
    for r in rows:
        slot = classify(r.account_name)
        cell = agg.setdefault(slot, {"opening": 0.0, "closing": 0.0})
        cell["opening"] += norm(_parse_num(r.opening_balance))
        cell["closing"] += norm(_parse_num(r.closing_balance))
    return {
        slot: {"opening": round(v["opening"], 2), "closing": round(v["closing"], 2)}
        for slot, v in agg.items()
        if abs(v["opening"]) >= 0.005 or abs(v["closing"]) >= 0.005
    }


async def _build_liability_prefill(
    ctx: RenderContext, codes: list[str] | None = None
) -> dict[str, dict[str, float]]:
    """从 tb_balance 递延所得税负债 **叶子子科目**按负债段 5 语义槽预填期初/期末。

    与资产段 `_build_adjudication_prefill` 同范式：
    - 只取叶子（防与父级/中间级双算）；
    - 名称按关键字归槽（`_classify_n1_liability_subaccount`）；
    - 全零槽跳过；只有父级科目（无子科目）→ 返回 ``{}``（不虚构分类，
      披露表负债段仍可由 N3 底稿或手工填，`trial_balance_liability` 给总额做反向校验）；
    - 查询失败优雅降级返回 ``{}``，不阻塞渲染。
    """
    try:
        rows = await _fetch_sub_account_rows(
            ctx, codes or [_N1_LIABILITY_ACCOUNT_CODE]
        )
    except Exception as e:  # noqa: BLE001 — 预填失败按空处理，不阻塞渲染
        logger.warning("N1 render: 负债段预填 tb_balance 查询失败: %s", e)
        return {}
    return _aggregate_by_slot(rows, _classify_n1_liability_subaccount, absolute=True)


async def _build_adjudication_prefill(
    ctx: RenderContext, codes: list[str] | None = None
) -> dict[str, dict[str, float]]:
    """从 tb_balance 科目 1811 **叶子子科目**按暂时性差异类别预填审定表期初/期末未审数。

    照平台铁律「X-1 审定表未审数从 tb_balance 明细子科目预填」：
    - 只取 ``1811.%`` 叶子子科目（无更深层级），防与父级/中间级双算。
    - 子科目名按关键字归入审定表 7 类（``_classify_n1_subaccount``），同类聚合。
    - 仅有父级 1811（无子科目）时无法分类 → 返回 ``{}``（审定表仍由 N1-2/手工填，
      TB 核对行显示 1811 合计做反向校验）。
    - 全零类别跳过；查询失败优雅降级返回 ``{}``，不阻塞渲染。
    - 前端只在**无持久化**时套用（编辑后不覆盖）。

    返回：``{ 类别: {"opening": float, "closing": float} }``（1811 为借方/资产类，直取不取绝对值）。
    """
    try:
        rows = await _fetch_sub_account_rows(ctx, codes or [_N1_ACCOUNT_CODE])
    except Exception as e:  # noqa: BLE001 — 预填失败按空处理，不阻塞渲染
        logger.warning("N1 render: 审定表预填 tb_balance 查询失败: %s", e)
        return {}
    return _aggregate_by_slot(rows, _classify_n1_subaccount)


# ─── 主渲染函数 ───────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict[str, Any]:
    """N1 递延所得税资产专属渲染策略.

    轻量返回：project_context + responses_snapshot + TB数据。
    前端 GtN1DeferredTaxAssets 为自加载组件（各子组件独立拉取 checklist_responses）。
    """
    # ─── 读取 checklist_responses 快照 ─────────────────────────────────
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
        # 提取审定数（真源 remark；旧键作向后兼容回退）
        snap = responses_snapshot.get(_ADJUDICATED_ITEM_ID)
        if snap is not None:
            raw_adj = snap.get("remark") or snap.get("conclusion")
            if raw_adj is not None:
                adjudicated_amount = _parse_num(raw_adj)
        if adjudicated_amount is None:
            legacy = responses_snapshot.get(_ADJUDICATED_LEGACY_ITEM_ID)
            if legacy is not None:
                raw_legacy = legacy.get("conclusion") or legacy.get("remark")
                if raw_legacy is not None:
                    adjudicated_amount = _parse_num(raw_legacy)
    except Exception as e:  # noqa: BLE001
        logger.warning("N1 render: checklist_responses 查询失败: %s", e)

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
        logger.warning("N1 render: project context 查询失败: %s", e)

    # ─── 科目映射（report_config 单一真源，fail-open 回退硬编码科目）──────────
    asset_codes = await _resolve_account_codes(ctx, _ASSET_ROW_CODE, [_N1_ACCOUNT_CODE])
    liability_codes = await _resolve_account_codes(
        ctx, _LIABILITY_ROW_CODE, [_N1_LIABILITY_ACCOUNT_CODE]
    )

    # ─── TB 取数（资产侧 1811 借方 / 负债侧 2901 贷方）─────────────────────
    tb = await _fetch_tb_for_codes(
        ctx, asset_codes, account_name="递延所得税资产", direction="debit"
    )
    tb_liability = await _fetch_tb_for_codes(
        ctx,
        liability_codes,
        account_name="递延所得税负债",
        direction="credit",
        absolute=True,
    )

    # ─── 分类预填（叶子子科目 → 披露/审定分类；前端无持久化时套用）─────────
    adjudication_prefill = await _build_adjudication_prefill(ctx, asset_codes)
    liability_prefill = await _build_liability_prefill(ctx, liability_codes)

    return {
        "account_code": _N1_ACCOUNT_CODE,
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        # TB 余额数据（科目1811，借方/资产类）
        "trial_balance": tb,
        # TB 余额数据（科目2901，贷方/负债类，已 abs() 归一为披露口径正数）
        "trial_balance_liability": tb_liability,
        # 审定表未审数预填（{类别: {opening, closing}}；前端仅无持久化时套用）
        "adjudication_prefill": adjudication_prefill,
        # 披露表负债段预填（{语义槽: {opening, closing}}；显示名映射在前端单一真源）
        "liability_prefill": liability_prefill,
        # 取数溯源：报表行规则映射解析出的科目集（供前端展示「取数来源」）
        "tb_source_codes": {
            "asset": {"row_code": _ASSET_ROW_CODE, "codes": asset_codes},
            "liability": {"row_code": _LIABILITY_ROW_CODE, "codes": liability_codes},
        },
        # 资产类公式方向元数据
        "formula_direction": {
            "account_code": "1811",
            "account_name": "递延所得税资产",
            "direction": "debit",  # 借方/资产类！
            "end_balance_formula": "begin + debit - credit",  # 期末=期初+借方-贷方
            "note": (
                "资产类借方科目：递延所得税资产增加在借方（确认时借记1811），"
                "转回时贷方减少。核心引擎：递延所得税资产=可抵扣暂时性差异×适用税率。"
                "与N3递延所得税负债对应（同源暂时性差异分列）。"
            ),
        },
        # N1 特有元数据
        "n1_metadata": {
            "engine": "deferred_tax_asset",
            "formula": "deferred_tax_asset = deductible_temporary_difference × tax_rate",
            "loss_formula": "recognizable = min(unrecovered_loss, future_taxable_income) × tax_rate",
            "cross_wp_links": ["N3", "N5-8"],
        },
        # sheet 列表元数据
        "sheets": N1_SHEETS,
        "component_type": "n1-deferred-tax-assets",
    }
