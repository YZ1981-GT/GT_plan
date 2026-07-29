"""F2 存货底稿核心组 — 专属渲染策略."""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

F2_CATEGORIES = [
    {"rowKey": "raw-materials", "label": "原材料", "account": "1401"},
    {"rowKey": "material-in-transit", "label": "材料采购在途", "account": "1402"},
    {"rowKey": "revolving-materials", "label": "周转材料", "account": "1403"},
    {"rowKey": "semi-finished", "label": "自制半成品", "account": "1404"},
    {"rowKey": "outsourced-processing", "label": "委托加工物资", "account": "1405"},
    {"rowKey": "finished-goods", "label": "库存商品", "account": "1406"},
    {"rowKey": "goods-in-transit", "label": "发出商品", "account": "1407"},
    {"rowKey": "dev-products", "label": "开发产品", "account": "1408"},
    {"rowKey": "dev-costs", "label": "开发成本", "account": "1409"},
    {"rowKey": "contract-performance", "label": "合同履约成本", "account": "1410"},
    {"rowKey": "consumable-bio", "label": "消耗性生物资产", "account": "1411"},
    {"rowKey": "price-difference", "label": "商品进销差价", "account": "1412"},
    {"rowKey": "impairment-provision", "label": "存货跌价准备", "account": "1471"},
]


def _row_depth(row, account: str) -> int:
    """判定 tb_balance 行相对科目的明细层级（越大越深）。

    优先用 level 列；无则按 code 的 "." 段数；再无则按是否等于一级科目粗判。
    """
    if getattr(row, "level", None) is not None:
        try:
            return int(row.level)
        except (TypeError, ValueError):  # noqa: PERF203
            pass
    code = (row.account_code or "").strip()
    if "." in code:
        return code.count(".") + 1
    return 1 if code == account else 2


async def _build_adjudication_prefill_v2(ctx: RenderContext) -> dict[str, dict]:
    """灰度开时：委托 extract_f2_category_values（新口径）取数。

    返回结构：{ rowKey: {opening, increase, decrease, closing, formulas, source_codes} }
    """
    from app.services.f2_extraction.extract import extract_f2_category_values
    from app.services.f2_extraction.presets import resolve_effective

    try:
        effective_bindings = await resolve_effective(ctx.db, ctx.wp_id, ctx.project_id)
    except Exception as e:
        logger.warning("F2 render: resolve_effective 失败, 回退默认绑定: %s", e)
        from app.services.f2_extraction.extract import build_default_bindings
        effective_bindings = build_default_bindings()

    raw_result = await extract_f2_category_values(ctx, effective_bindings)
    # raw_result: {anchor: {value, account, column, is_abs, source_codes}}

    # 按 rowKey 聚合：anchor = F2-1-{block}-{rowKey}-{field}
    from collections import defaultdict

    by_row: dict[str, dict] = defaultdict(
        lambda: {
            "opening": 0.0,
            "increase": 0.0,
            "decrease": 0.0,
            "closing": 0.0,
            "formulas": {},
            "source_codes": set(),
        }
    )

    for anchor, info in raw_result.items():
        # anchor = F2-1-{block}-{rowKey}-{field}
        # block ∈ {gross, impairment}, field ∈ {opening, increase, decrease}
        # rowKey 可含连字符如 raw-materials
        # 解析策略：去掉 "F2-1-" 前缀，末尾取 field，中间解析 block 和 rowKey
        if not anchor.startswith("F2-1-"):
            continue
        remainder = anchor[5:]  # 去掉 "F2-1-"

        # 末尾 field
        for candidate_field in ("opening", "increase", "decrease"):
            suffix = f"-{candidate_field}"
            if remainder.endswith(suffix):
                field = candidate_field
                remainder = remainder[: -len(suffix)]
                break
        else:
            continue

        # remainder = {block}-{rowKey}
        # block ∈ {gross, impairment}
        if remainder.startswith("gross-"):
            row_key = remainder[6:]
        elif remainder.startswith("impairment-"):
            row_key = remainder[11:]
        else:
            continue

        entry = by_row[row_key]
        entry[field] = info["value"]
        entry["source_codes"].update(info.get("source_codes") or [])

        # 从 effective_bindings 取公式表达式
        # 找到匹配的 binding 取 expression
        for b in effective_bindings:
            if b.get("anchor") == anchor:
                entry["formulas"][field] = b.get("expression", "")
                break

    # 计算 closing = opening + increase - decrease（审计 roll-forward 一致）
    result: dict[str, dict] = {}
    for row_key, entry in by_row.items():
        opening = entry["opening"]
        increase = entry["increase"]
        decrease = entry["decrease"]
        closing = opening + increase - decrease

        # 全零跳过
        if (
            abs(opening) < 0.005
            and abs(increase) < 0.005
            and abs(decrease) < 0.005
            and abs(closing) < 0.005
        ):
            continue

        result[row_key] = {
            "opening": opening,
            "increase": increase,
            "decrease": decrease,
            "closing": closing,
            "formulas": entry["formulas"],
            "source_codes": sorted(entry["source_codes"]),
        }

    return result


async def _build_adjudication_prefill(ctx: RenderContext) -> dict[str, dict[str, float]]:
    """无持久化审定数据时，从 tb_balance 存货科目预填各分类行期初/期末未审数。

    照 J1/D5 范式：
    - 资产类 1401~1412：opening/closing 直取（存货借方为正）。
    - 跌价准备 1471 为备抵科目：取绝对值。
    - 每个分类按 code 前缀归集，优先最深明细层级（二级/三级）汇总，退一级总额，
      避免层级重复计数。
    - 查询失败优雅降级返回 {}，不阻断渲染。

    返回结构：{ rowKey: {"opening": float, "closing": float}, ... }
    """
    from app.core.config import settings

    if settings.F2_FOUR_TABLE_EXTRACTION_ENABLED:
        return await _build_adjudication_prefill_v2(ctx)
    tb_values: dict[str, dict[str, float]] = {}
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.level,
            ).where(active_filter)
        )
        rows = result.fetchall()
    except Exception as e:  # noqa: BLE001 — 预填失败按空处理，不阻塞渲染
        logger.warning("F2 render: 审定表预填 tb_balance 查询失败: %s", e)
        return {}

    for cat in F2_CATEGORIES:
        account = cat["account"]
        row_key = cat["rowKey"]
        # 收集匹配该科目前缀的行（code == account 或 code 以 account 开头的子科目）
        by_depth: dict[int, list] = {}
        for r in rows:
            code = (r.account_code or "").strip()
            if not code:
                continue
            if code == account or code.startswith(account):
                depth = _row_depth(r, account)
                by_depth.setdefault(depth, []).append(r)
        if not by_depth:
            continue
        # 优先最深明细层级（三级/二级），退一级
        chosen = by_depth[max(by_depth.keys())]
        opening = sum(float(r.opening_balance or 0) for r in chosen)
        closing = sum(float(r.closing_balance or 0) for r in chosen)
        if account == "1471":  # 跌价准备为备抵科目，取绝对值
            opening = abs(opening)
            closing = abs(closing)
        if opening == 0 and closing == 0:
            continue
        tb_values[row_key] = {"opening": opening, "closing": closing}
    return tb_values


async def render(ctx: RenderContext) -> dict | None:
    wp_id = ctx.wp_id
    db = ctx.db

    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'F2-%' "
                "LIMIT 1200"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("F2 render: checklist_responses 失败: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "applicable_standards": "",
        # bs_date（资产负债表日）：供期后出库取数窗口/截止测试基准日等使用
        "bs_date": "",
        # 关联方清单：供关联采购识别自动化
        "related_parties": [],
    }
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, applicable_standard_v2 AS applicable_standards "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            raw_std = proj_row.applicable_standards
            if isinstance(raw_std, dict):
                project_context["applicable_standards"] = raw_std.get("type", "")
            else:
                project_context["applicable_standards"] = raw_std or ""
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("F2 render: project context 失败: %s", e)

    # 关联方清单：从关联方登记表（related_party_registry）取项目级未删除名单
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
        logger.warning("F2 render: related_parties 查询失败: %s", e)

    # ─── F2-1 TB 核对标量（存货净额 BS-008，走规则映射） ──────────────────
    year = project_context.get("audit_year")
    if year:
        try:
            from app.services.report_account_mapping import (
                resolve_report_line_account_codes,
                build_trial_balance_code_filter,
            )

            codes = await resolve_report_line_account_codes(
                db, ctx.project_id, "BS-008",
                fallback=["1401", "1402", "1403", "1404", "1405", "1406",
                          "1407", "1408", "1409", "1410", "1411", "1412", "1471"],
            )
            where_clause, code_params = build_trial_balance_code_filter(codes)
            project_context["tb_source_codes"] = codes
            tb_row = (
                await db.execute(
                    sa.text(
                        "SELECT COALESCE(SUM(audited_amount), 0) AS audited, "
                        "COALESCE(SUM(unadjusted_amount), 0) AS unadjusted "
                        "FROM trial_balance "
                        "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                        f"AND {where_clause}"
                    ),
                    {"pid": str(ctx.project_id), "year": int(year), **code_params},
                )
            ).fetchone()
            if tb_row:
                audited = float(tb_row.audited or 0)
                unadjusted = float(tb_row.unadjusted or 0)
                project_context["tb_amount"] = audited if audited else unadjusted
        except Exception as e:  # noqa: BLE001
            logger.warning("F2 render: trial_balance 存货净额查询失败: %s", e)

    # ─── F2-1 审定表 TB 子科目预填 ────────────────────────────────────────
    tb_values = await _build_adjudication_prefill(ctx)
    # 仅当无持久化 F2-adjudication-data 时输出预填 seed（不覆盖用户已编辑数据）
    has_persisted_adjudication = "F2-adjudication-data" in responses_snapshot
    adjudication_prefill: dict = {} if has_persisted_adjudication else dict(tb_values)

    return {
        "categories": F2_CATEGORIES,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "adjudication_prefill": adjudication_prefill,
        "adjudication_blocks": ["gross", "impairment", "net"],
    }
