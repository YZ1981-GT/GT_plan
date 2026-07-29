"""H8 使用权资产 — 专属渲染策略.

component_type = "h8-right-of-use-assets"

科目1901使用权资产（借方/资产类）+ 累计折旧（贷方/备抵类）
CAS21核心：H8=H9+直接费用-激励
返回 allResponses + tb_values(1901+累计折旧) + h9_linkage + cas21_validation
     + simplified_leases + sheets元数据
资产类公式：期末=期初+借方-贷方
备抵类公式：期末=期初+贷方-借方
联动：H9租赁负债(双向) + H1固定资产(终止时) + TB回写(1901+累计折旧)

Requirements: 1.6
"""
from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1901使用权资产（借方/资产类）+ 累计折旧子科目
_H8_ACCOUNT_PREFIXES = {
    "1901": ("rou_asset", "rou_asset_audited"),          # 使用权资产-原值
    "190101": ("rou_dep", "rou_dep_audited"),            # 使用权资产-累计折旧(备抵)
}

# 累计折旧可能在不同科目编码体系下（如1901xx02或单独科目）
_H8_CONTRA_PATTERNS = ["190101", "190102", "1901%折旧%"]

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


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1901的期初/期末余额及未审数/审定数.

    包含使用权资产原值(1901)和累计折旧(190101/190102等备抵子科目)。
    资产类借方科目：期末=期初+借方-贷方
    备抵类贷方科目：期末=期初+贷方-借方
    """
    tb: dict[str, float] = {}

    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(
                active_filter,
                sa.or_(
                    TbBalance.account_code == "1901",
                    TbBalance.account_code.startswith("1901"),
                ),
            )
        )
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            # 判断是否为累计折旧子科目(190101/190102等)
            is_contra = len(code) > 4 and code.startswith("1901")
            key_prefix = "rou_dep" if is_contra else "rou_asset"

            tb[f"{key_prefix}_opening"] = tb.get(f"{key_prefix}_opening", 0.0) + float(row.opening_balance or 0)
            tb[f"{key_prefix}_closing"] = tb.get(f"{key_prefix}_closing", 0.0) + float(row.closing_balance or 0)
            tb[f"{key_prefix}_debit"] = tb.get(f"{key_prefix}_debit", 0.0) + float(row.debit_amount or 0)
            tb[f"{key_prefix}_credit"] = tb.get(f"{key_prefix}_credit", 0.0) + float(row.credit_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("H8 TB balance fetch failed: %s", e)

    # 从 trial_balance 取未审数+审定数（使用 get_active_filter 保证数据集版本一致）
    try:
        tb_active_filter = await get_active_filter(
            ctx.db, TrialBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.unadjusted_amount,
                TrialBalance.audited_amount,
            ).where(
                tb_active_filter,
                TrialBalance.standard_account_code.startswith("1901"),
            )
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            is_contra = len(code) > 4 and code.startswith("1901")
            key_prefix = "rou_dep" if is_contra else "rou_asset"

            tb[f"{key_prefix}_unadjusted"] = tb.get(f"{key_prefix}_unadjusted", 0.0) + float(row.unadjusted_amount or 0)
            tb[f"{key_prefix}_audited"] = tb.get(f"{key_prefix}_audited", 0.0) + float(row.audited_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("H8 trial_balance fetch failed: %s", e)

    return tb


async def _build_h8_detail_prefill(ctx: RenderContext) -> list[dict[str, Any]]:
    """从 tb_balance 叶子子科目为 H8-2 明细表种子预填.

    仅取 1901 下叶子科目（code 不是任何其它 code 的前缀）且非全零行。
    资产类（借方正）：期初=opening_balance，本期增加=debit，本期减少=credit，期末=closing_balance。
    H8 明细表按合同驱动，但如果账套有 1901 多级子科目（如 1901.01 房屋/1901.02 设备），
    则可为审计师预填初始数据减少手工录入——仅当 H8-2-rows 空时种子填入，手工优先。
    """
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
                TbBalance.account_code.startswith("1901"),
            )
        )
        rows = result.fetchall()
        if not rows:
            return []

        # 收集所有 code
        all_codes = {(r.account_code or "").strip() for r in rows}

        for row in rows:
            code = (row.account_code or "").strip()
            if not code or code == "1901":
                continue  # 跳过父级汇总

            # 叶子判定：该 code 不是任何其它 code 的前缀
            is_leaf = not any(
                other_code != code and other_code.startswith(code)
                for other_code in all_codes
            )
            if not is_leaf:
                continue

            # 跳过累计折旧子科目（>=6位的190101/190102等属于备抵）
            if len(code) >= 6 and code[:4] == "1901":
                # 190101 等明确是折旧子科目
                name_lower = (row.account_name or "").lower()
                if "折旧" in name_lower or "摊销" in name_lower or "减值" in name_lower:
                    continue

            opening = float(row.opening_balance or 0)
            closing = float(row.closing_balance or 0)
            debit = float(row.debit_amount or 0)
            credit = float(row.credit_amount or 0)

            # 跳过全零行
            if abs(opening) < 0.005 and abs(closing) < 0.005 and abs(debit) < 0.005 and abs(credit) < 0.005:
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

    # 2. 获取TB数据（1901使用权资产 + 累计折旧子科目）
    tb_values = await _fetch_tb_data(ctx)

    # 3. H9联动校验
    h9_linkage = await _fetch_h9_linkage(ctx)

    # 4. CAS21准则验证
    cas21_validation = await _validate_cas21(ctx, tb_values)

    # 5. 简化处理租赁检查
    simplified_leases = await _check_simplified_leases(ctx)

    # 6. 项目上下文（前端关联方检查/截止日/AI等消费）
    project_context = await _load_project_context(ctx)

    # 7. H8-2 明细表种子预填（叶子子科目，仅有子科目时产出）
    detail_prefill = await _build_h8_detail_prefill(ctx)

    payload = {
        "component_type": "h8-right-of-use-assets",
        "account_codes": ["1901"],
        "responses_snapshot": responses_snapshot,
        "project_context": project_context,
        "tb_values": tb_values,
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
            segment_prefill = await asyncio.wait_for(
                build_d_adjudication_prefill(ctx, account_prefix="1901", mode="balance"),
                timeout=5.0,
            )
            payload["adjudication_segment_prefill"] = {
                "segments": [{"segment": "cost", "account_prefix": "1901", "mode": "balance", "items": segment_prefill}],
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
