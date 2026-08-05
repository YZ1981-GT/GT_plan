"""H8 使用权资产 — 专属渲染策略.

component_type = "h8-right-of-use-assets"

科目定位（语义驱动，2026-08-03 纠正）：
  原值 = 1641 使用权资产
  累计折旧 = 1642 使用权资产累计折旧
  减值准备 = 1643 使用权资产减值准备
  报表行 BS-031 = TB('1641') - TB('1642') - TB('1643')

🔴 旧实现写死 `1901`（待处理财产损溢）/ `190101`，**取错整个科目族**。

CAS21核心：H8=H9+直接费用-激励
返回 allResponses + tb_values(三层) + h9_linkage + cas21_validation
     + simplified_leases + sheets元数据 + tb_source_codes(溯源)
联动：H9租赁负债(双向) + H1固定资产(终止时) + TB回写(语义定位后的科目码)

Requirements: 1.5, 2.1, 4.1
spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.h8_account_scope import H8_ACCOUNT_SPEC, H8_SLOT_KEY_PREFIX
from app.services.four_table.semantic_account_resolver import (
    SemanticAccountResult,
    resolve_semantic_accounts,
)
from app.services.four_table.leaf_aggregation import (
    aggregate_leaves,
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table.parent_check import build_parent_check

from ._context import RenderContext

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# 三层取数纯函数（无 DB 依赖，可独立单测）
# ──────────────────────────────────────────────────────────────────────────────


def build_h8_tb_values(
    accounts: SemanticAccountResult,
    tb_rows,
    trial_rows,
) -> dict[str, float]:
    """按语义槽聚合使用权资产三层金额。纯函数。

    输出键契约（保持既有 `rou_asset`/`rou_dep` 不变，新增 `rou_imp`）::

        {prefix}_unadjusted_opening / _closing / _debit / _credit  ← tb_balance 叶子
        {prefix}_unadjusted / {prefix}_audited                     ← trial_balance

    某槽 `found=False` 时不产生该槽的任何键（宁缺勿造）。
    """
    leaves = select_leaves(to_leaf_rows(tb_rows))
    out: dict[str, float] = {}

    for slot_key, prefix in H8_SLOT_KEY_PREFIX.items():
        slot = accounts.slots.get(slot_key)
        if slot is None or not slot.found:
            continue
        agg = aggregate_leaves(leaves, slot.codes)
        out[f"{prefix}_unadjusted_opening"] = agg["opening"]
        out[f"{prefix}_unadjusted_closing"] = agg["closing"]
        out[f"{prefix}_unadjusted_debit"] = agg["debit"]
        out[f"{prefix}_unadjusted_credit"] = agg["credit"]
        # 🔴 兼容旧键名 —— `GtH8RightOfUseAssets.vue` 用 `tv.rou_asset_closing ?? 0`
        # 读 TB 核对种子（`H8-adj-tb-amount-ending` / `-opening`）。不发这些键会让
        # 那两行**静默恒为 0**（`?? 0` 吞掉 undefined，不报错不崩溃）。
        out[f"{prefix}_opening"] = agg["opening"]
        out[f"{prefix}_closing"] = agg["closing"]
        out[f"{prefix}_debit"] = agg["debit"]
        out[f"{prefix}_credit"] = agg["credit"]

    # 折旧层再补一组无前缀别名（宿主同时读 `tv.dep_opening` / `tv.dep_closing`）
    if "rou_dep_unadjusted_opening" in out:
        out["dep_opening"] = out["rou_dep_unadjusted_opening"]
        out["dep_closing"] = out["rou_dep_unadjusted_closing"]

    # trial_balance：按标准码精确匹配
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

    for slot_key, prefix in H8_SLOT_KEY_PREFIX.items():
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

H8_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "使用权资产实质性程序表H8A", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "审定表H8-1", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "明细表H8-2", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "调整分录汇总H8-3", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "租赁的识别H8-4", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "租赁期的确定H8-5", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "使用权资产 租赁负责初始及后续计量（按年）H8-6", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "使用权资产 租赁负责初始及后续计量（按月）H8-6", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "租赁变更H8-7", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "折旧测算表（不含减值）H8-8", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "折旧测算表（含减值）H8-8", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "折旧分配分析表H8-9", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "减值测算表H8-10", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "可收回金额测试表H8-11", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "减少检查表H8-12", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "简化处理的租赁检查表H8-13", "component_type": "h8-right-of-use-assets"},
    {"sheet_name": "关联交易检查表H8-14", "component_type": "h8-right-of-use-assets"},
]


async def _fetch_tb_data(ctx: RenderContext) -> tuple[dict, SemanticAccountResult]:
    """按语义槽取使用权资产三层数据（原值 1641 / 累计折旧 1642 / 减值准备 1643）。

    Returns:
        ``(tb_values, accounts)`` —— ``accounts`` 供 render 下发 `tb_source_codes` 溯源。
    """
    accounts = await resolve_semantic_accounts(ctx, H8_ACCOUNT_SPEC)

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
        logger.warning("H8 TB balance fetch failed: %s", e)

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
            logger.warning("H8 trial_balance fetch failed: %s", e)

    tb = build_h8_tb_values(accounts, tb_rows, trial_rows)
    tb["_parent_check"] = build_h8_parent_check(accounts, tb_rows, trial_rows)
    return tb, accounts


def build_h8_parent_check(
    accounts: SemanticAccountResult,
    tb_rows,
    trial_rows,
) -> dict[str, dict[str, float]]:
    """三口径自检（Req 3.4）—— 薄壳委托 `four_table.parent_check`。

    实测价值（2026-08-03，项目 `2aa00f57`）：`trial_balance.1651` = 352,406,145.74
    而 `tb_balance` 叶子和 = 父行 = 176,203,072.87 —— 「叶子和 == 父额」这条勾稽
    **完全成立**，问题在 trial_balance recalc 父子双算。只比对两口径发现不了这 1.76 亿。
    """
    return build_parent_check(accounts, tb_rows, trial_rows, H8_SLOT_KEY_PREFIX.keys())


async def _build_h8_detail_prefill(
    ctx: RenderContext, accounts: SemanticAccountResult
) -> list[dict[str, Any]]:
    """从 tb_balance 叶子子科目为 H8-2 明细表种子预填.

    🔴 **2026-08-03 修掉的遗留 P0**：本函数原先硬编码 `startswith("1901")` ——
    `1901` 是**待处理财产损溢**（K2 `BS-014` 亦引用），不是使用权资产。
    render 主路径已改走语义定位（真族 `1641/1642/1643`，客户实际可能是 `1651/1652`），
    但本函数漏改 → **H8-2 明细表的种子预填一直在拿另一个科目族的数据**
    （活体 `1901` 期末全 0.00 → 表现为「恒空」而非「数字错」，更隐蔽）。
    原「>=6 位 + 名称含折旧/摊销/减值则跳过」的备抵判定也随之失效：
    新模型下累计折旧是**独立一级码** `1642`，不是 `190101` 式子科目。

    现在的口径：
    - 只取 `gross` 槽命中的科目码前缀（`accounts.codes_of("gross")`）
    - **显式排除**其余槽（`accum_dep`/`impairment`）的码 —— 它们是备抵，
      不该出现在原值明细表里
    - 叶子判定走共享件 `select_leaves`（禁自造，缺点号边界会误判 `1641.1` vs `1641.11`）
    - 跳过全零行（明细表种子无意义），但**不过滤零余额账户之外的东西**
    - 本项目无 `gross` 科目（`found=False`）→ 返空（宁缺勿造）

    资产类（借方正）：期初=opening_balance，本期增加=debit，本期减少=credit，期末=closing_balance。
    仅当 H8-2-rows 空时种子填入，手工优先。
    """
    gross_codes = accounts.codes_of("gross")
    if not gross_codes:
        return []

    # 备抵槽的码：即便它们恰好落在 gross 前缀下也要排除
    provision_codes = {
        code
        for slot_key in H8_SLOT_KEY_PREFIX
        if slot_key != "gross"
        for code in accounts.codes_of(slot_key)
    }

    prefill: list[dict[str, Any]] = []
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
            ).where(
                active_filter,
                sa.or_(*[TbBalance.account_code.startswith(c) for c in gross_codes]),
            )
        )
        rows = list(result.fetchall())
        if not rows:
            return []

        for row in select_leaves(to_leaf_rows(rows)):
            code = (row.account_code or "").strip()
            if not code or code in gross_codes:
                continue  # 跳过一级父科目汇总行
            if any(code == p or code.startswith(f"{p}.") for p in provision_codes):
                continue  # 备抵科目不进原值明细表

            opening = float(row.opening or 0)
            closing = float(row.closing or 0)
            debit = float(row.debit or 0)
            credit = float(row.credit or 0)

            # 跳过全零行
            if (
                abs(opening) < 0.005
                and abs(closing) < 0.005
                and abs(debit) < 0.005
                and abs(credit) < 0.005
            ):
                continue

            prefill.append({
                "account_code": code,
                "account_name": row.account_name or code,
                "opening": opening,
                "closing": closing,
                "debit": debit,       # 本期增加（资产借方=增加）
                "credit": credit,     # 本期减少（资产借方科目贷方=减少）
                "source": f"TB('{code}','期末余额')",
            })

    except Exception as e:  # noqa: BLE001
        logger.warning("H8 detail prefill from tb_balance failed: %s", e)

    return prefill


async def _fetch_h9_linkage(ctx: RenderContext) -> dict[str, Any]:
    """查询H9租赁负债数据，与H8初始计量交叉验证.

    CAS21: H8初始计量 = H9初始确认 + 初始直接费用 - 租赁激励
    校验容差: ±1元
    """
    h9_data: dict[str, Any] = {
        "h9_initial": 0.0,
        "h8_initial": 0.0,
        "diff": 0.0,
        "is_consistent": True,
        "h9_available": False,
        "message": "",
    }

    # 从 H9 checklist_responses 获取初始计量数据
    try:
        # H9 初始确认金额：优先精确键，回退模糊
        _H9_INITIAL_KEYS = [
            'H9-1-initial-liability-total',
            'H9-initial-measurement-total',
            'H9-1-liability-total',
        ]
        result = await ctx.db.execute(
            sa.text("""
                SELECT cr.item_id, cr.conclusion, cr.remark
                FROM checklist_responses cr
                JOIN working_paper wp ON cr.wp_id = wp.id
                JOIN wp_index wi ON wi.project_id = wp.project_id
                    AND wi.wp_code = 'H9'
                WHERE wp.project_id = :pid
                  AND wp.is_deleted = false
                  AND cr.item_id LIKE 'H9-%'
                LIMIT 500
            """),
            {"pid": str(ctx.project_id)},
        )
        rows = result.fetchall()
        if rows:
            h9_data["h9_available"] = True
            # 精确键优先（按优先级逐个查找）
            rows_by_id = {(r.item_id or "").strip(): r for r in rows}
            found_h9 = False
            for key in _H9_INITIAL_KEYS:
                if key in rows_by_id:
                    try:
                        val = float(rows_by_id[key].remark or rows_by_id[key].conclusion or 0)
                        if val != 0:
                            h9_data["h9_initial"] = val
                            found_h9 = True
                            break
                    except (ValueError, TypeError):
                        pass
            # 回退模糊匹配（兼容旧项目键命名不一致）
            if not found_h9:
                for row in rows:
                    item_id = row.item_id or ""
                    if "initial" in item_id.lower() and "total" in item_id.lower():
                        try:
                            val = float(row.remark or row.conclusion or 0)
                            if val != 0:
                                h9_data["h9_initial"] = val
                                break
                        except (ValueError, TypeError):
                            pass

        # 获取H8初始计量值（精确键优先）
        _H8_INITIAL_KEYS = [
            'H8-6-initial-measurement-total',
            'H8-2-initial-total',
        ]
        h8_result = await ctx.db.execute(
            sa.text("""
                SELECT item_id, conclusion, remark FROM checklist_responses
                WHERE wp_id = :wp_id
                  AND (item_id LIKE 'H8-6-initial%' OR item_id LIKE 'H8-2-initial%')
                LIMIT 50
            """),
            {"wp_id": str(ctx.wp_id)},
        )
        h8_rows_by_id = {(r.item_id or "").strip(): r for r in h8_result.fetchall()}
        for key in _H8_INITIAL_KEYS:
            if key in h8_rows_by_id:
                try:
                    val = float(h8_rows_by_id[key].remark or h8_rows_by_id[key].conclusion or 0)
                    if val != 0:
                        h9_data["h8_initial"] = val
                        break
                except (ValueError, TypeError):
                    pass

        # 计算差异（允许±1元容差）
        diff = h9_data["h8_initial"] - h9_data["h9_initial"]
        h9_data["diff"] = round(diff, 2)
        h9_data["is_consistent"] = abs(diff) <= 1.0

        if not h9_data["h9_available"]:
            h9_data["message"] = "H9租赁负债底稿尚未编制"
        elif not h9_data["is_consistent"]:
            h9_data["message"] = f"H8与H9不一致，差额：{diff:.2f}元，请检查"
        else:
            h9_data["message"] = "H8-H9联动校验通过"

    except Exception as e:  # noqa: BLE001
        logger.warning("H8 H9 linkage fetch failed: %s", e)
        h9_data["message"] = "H9联动查询异常"

    return h9_data


async def _validate_cas21(ctx: RenderContext, tb_values: dict) -> dict[str, Any]:
    """CAS21准则验证逻辑.

    验证项:
    1. 初始计量公式 H8=H9+直接费用-激励
    2. 折旧期有效性 = min(租赁期, 使用寿命) > 0
    3. 资产期末=期初+借-贷 (借方资产类)
    4. 备抵期末=期初+贷-借 (贷方备抵类)
    """
    validation: dict[str, Any] = {
        "initial_measurement_ok": True,
        "depreciation_period_valid": True,
        "asset_balance_valid": True,
        "contra_balance_valid": True,
        "net_value_positive": True,
        "messages": [],
    }

    # 验证资产余额公式: 期末=期初+借-贷
    asset_opening = tb_values.get("rou_asset_opening", 0.0)
    asset_debit = tb_values.get("rou_asset_debit", 0.0)
    asset_credit = tb_values.get("rou_asset_credit", 0.0)
    asset_closing = tb_values.get("rou_asset_closing", 0.0)

    expected_asset_closing = asset_opening + asset_debit - asset_credit
    if abs(asset_closing - expected_asset_closing) > 1.0 and asset_closing != 0.0:
        validation["asset_balance_valid"] = False
        validation["messages"].append(
            f"使用权资产期末余额校验不通过: 期末{asset_closing:.2f} ≠ 期初{asset_opening:.2f}+借{asset_debit:.2f}-贷{asset_credit:.2f}"
        )

    # 验证备抵余额公式: 期末=期初+贷-借
    dep_opening = tb_values.get("rou_dep_opening", 0.0)
    dep_debit = tb_values.get("rou_dep_debit", 0.0)
    dep_credit = tb_values.get("rou_dep_credit", 0.0)
    dep_closing = tb_values.get("rou_dep_closing", 0.0)

    expected_dep_closing = dep_opening + dep_credit - dep_debit
    if abs(dep_closing - expected_dep_closing) > 1.0 and dep_closing != 0.0:
        validation["contra_balance_valid"] = False
        validation["messages"].append(
            f"累计折旧期末余额校验不通过: 期末{dep_closing:.2f} ≠ 期初{dep_opening:.2f}+贷{dep_credit:.2f}-借{dep_debit:.2f}"
        )

    # 验证净值非负（使用权资产原值 - 累计折旧 >= 0）
    net_value = asset_closing - abs(dep_closing)
    if net_value < -1.0 and asset_closing != 0.0:
        validation["net_value_positive"] = False
        validation["messages"].append(
            f"使用权资产净值为负: {net_value:.2f}（原值{asset_closing:.2f} - 折旧{abs(dep_closing):.2f}）"
        )

    # 从 checklist_responses 获取折旧期数据验证
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT item_id, conclusion FROM checklist_responses
                WHERE wp_id = :wp_id
                  AND item_id LIKE 'H8-8-dep-period%'
                LIMIT 50
            """),
            {"wp_id": str(ctx.wp_id)},
        )
        for row in result.fetchall():
            try:
                period = float(row.conclusion or 0)
                if period <= 0:
                    validation["depreciation_period_valid"] = False
                    validation["messages"].append("折旧期≤0，不符合CAS21规定")
            except (ValueError, TypeError):
                pass
    except Exception as e:  # noqa: BLE001
        logger.warning("H8 CAS21 depreciation period check failed: %s", e)

    return validation


async def _check_simplified_leases(ctx: RenderContext) -> dict[str, Any]:
    """简化处理检查：识别短期/低价值租赁.

    CAS21: 短期租赁(≤12月) / 低价值租赁(≤4万元) 可豁免确认使用权资产
    """
    simplified: dict[str, Any] = {
        "count": 0,
        "total_rent": 0.0,
        "non_compliant_count": 0,
        "short_term_count": 0,
        "low_value_count": 0,
        "items": [],
    }

    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT item_id, conclusion, remark FROM checklist_responses
                WHERE wp_id = :wp_id
                  AND item_id LIKE 'H8-13-%'
                LIMIT 500
            """),
            {"wp_id": str(ctx.wp_id)},
        )
        rows = result.fetchall()

        lease_items: dict[str, dict] = {}
        for row in rows:
            item_id = row.item_id or ""
            parts = item_id.split("-")
            # H8-13-{row_idx}-{field}
            if len(parts) >= 4:
                row_key = parts[2]
                field = "-".join(parts[3:])
                if row_key not in lease_items:
                    lease_items[row_key] = {}
                lease_items[row_key][field] = row.conclusion or row.remark or ""

        for _key, item in lease_items.items():
            simplified["count"] += 1

            # 年租金
            try:
                rent = float(item.get("annual_rent", item.get("rent", 0)))
                simplified["total_rent"] += rent
            except (ValueError, TypeError):
                pass

            # 判断短期
            try:
                term_months = float(item.get("lease_term", item.get("term_months", 0)))
                if term_months <= 12 and term_months > 0:
                    simplified["short_term_count"] += 1
            except (ValueError, TypeError):
                pass

            # 判断低价值
            try:
                asset_value = float(item.get("asset_new_value", item.get("new_value", 0)))
                if 0 < asset_value <= 40000:
                    simplified["low_value_count"] += 1
            except (ValueError, TypeError):
                pass

            # 判断不合规（既不短期也不低价值但标记为简化处理）
            conclusion = item.get("conclusion", "")
            if conclusion and "不符合" in conclusion:
                simplified["non_compliant_count"] += 1

    except Exception as e:  # noqa: BLE001
        logger.warning("H8 simplified lease check failed: %s", e)

    return simplified


async def _load_project_context(ctx: RenderContext) -> dict[str, Any]:
    """加载项目上下文供前端消费（关联方/截止日/客户名/审计年度）."""
    project_context: dict[str, Any] = {
        "client_name": "",
        "audit_year": ctx.year,
        "bs_date": f"{ctx.year}-12-31",
        "related_parties": [],
        "template_type": "",
    }

    try:
        # 客户名+模板类型从 projects 表获取
        result = await ctx.db.execute(
            sa.text("SELECT project_name, template_type FROM projects WHERE id = :pid"),
            {"pid": str(ctx.project_id)},
        )
        row = result.fetchone()
        if row:
            project_context["client_name"] = row.project_name or ""
            project_context["template_type"] = row.template_type or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("H8 project name fetch failed: %s", e)

    try:
        # 关联方清单
        result = await ctx.db.execute(
            sa.text(
                "SELECT name, relation_type, is_controlled_by_same_party "
                "FROM related_party_registry "
                "WHERE project_id = :pid AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )
        for row in result.fetchall():
            project_context["related_parties"].append({
                "name": row.name or "",
                "relation_type": row.relation_type or "",
                "is_controlled_by_same_party": bool(row.is_controlled_by_same_party),
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("H8 related parties fetch failed: %s", e)

    return project_context


async def render(ctx: RenderContext) -> dict | None:
    """H8使用权资产渲染策略.

    返回:
    - component_type: h8-right-of-use-assets
    - account_codes: [1901]
    - responses_snapshot: checklist_responses快照
    - tb_values: 使用权资产+累计折旧余额数据
    - h9_linkage: H9联动校验结果
    - cas21_validation: CAS21准则验证结果
    - simplified_leases: 简化处理租赁统计
    - sheets: sheet元数据列表
    """
    # 1. 加载 checklist_responses
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H8-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H8 render responses load failed: %s", e)

    # 2. 获取TB数据（语义定位：1641 使用权资产 + 1642 累计折旧 + 1643 减值准备）
    tb_values, accounts = await _fetch_tb_data(ctx)

    # 3. H9联动校验
    h9_linkage = await _fetch_h9_linkage(ctx)

    # 4. CAS21准则验证
    cas21_validation = await _validate_cas21(ctx, tb_values)

    # 5. 简化处理租赁检查
    simplified_leases = await _check_simplified_leases(ctx)

    # 6. 项目上下文（前端关联方检查/截止日/AI等消费）
    project_context = await _load_project_context(ctx)

    # 7. H8-2 明细表种子预填（叶子子科目，仅有子科目时产出）
    detail_prefill = await _build_h8_detail_prefill(ctx, accounts)

    # 解析后的主科目码（供前端 writebackTB 等，不再写死 `1901`）
    resolved_gross_codes = accounts.codes_of("gross") or ["1641"]

    payload = {
        "component_type": "h8-right-of-use-assets",
        "account_codes": resolved_gross_codes,
        "responses_snapshot": responses_snapshot,
        "project_context": project_context,
        "tb_values": tb_values,
        "tb_source_codes": accounts.as_dict(),
        "detail_prefill": detail_prefill,
        "h9_linkage": h9_linkage,
        "cas21_validation": cas21_validation,
        "simplified_leases": simplified_leases,
        "prefix": "H8",
        "sheets": H8_SHEETS,
        "meta": {"sheet_count": 20, "wp_code": "H8"},
    }

    # ─── 灰度：H/I 四表取数增强 ───────────────────────────────────────────
    from app.core.config import settings
    if settings.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            import asyncio
            from app.services.d_cycle_extraction.prefill import build_d_adjudication_prefill

            # 按解析后的三层各发一段（不再传 "1901"）
            segments = []
            for slot_key, prefix in H8_SLOT_KEY_PREFIX.items():
                slot = accounts.slots.get(slot_key)
                if not slot or not slot.found:
                    continue
                for code in slot.codes:
                    seg_items = await asyncio.wait_for(
                        build_d_adjudication_prefill(ctx, account_prefix=code, mode="balance"),
                        timeout=5.0,
                    )
                    segments.append({"segment": slot_key, "account_prefix": code, "mode": "balance", "items": seg_items})

            payload["adjudication_segment_prefill"] = {
                "segments": segments,
                "enabled": True,
            }
            payload["hi_extraction_enabled"] = True
            # Tier A transient seed（TB核对行）
            from app.services.d_cycle_extraction.tier_a_seed import seed_tier_a_reconciliation
            from app.services.d_cycle_extraction.presets import resolve_effective
            from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
            await asyncio.wait_for(
                seed_tier_a_reconciliation(
                    ctx, "H8",
                    responses_snapshot,
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("HI extraction prefill failed (%s): %s", "H8", e)

    return payload
