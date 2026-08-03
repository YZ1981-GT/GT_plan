"""F2 存货底稿核心组 — 专属渲染策略."""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.f2_extraction.category_rules import (
    classify_f2_leaf,
    is_f2_impairment_category,
    top_level_code,
)
from app.services.four_table import LeafRow, select_leaves, to_leaf_rows

from ._context import RenderContext
from app.services.four_table import resolve_semantic_accounts
from app.services.four_table.f_cycle_specs import F2_SPEC

logger = logging.getLogger(__name__)

#: F2-1 审定表分类行（rowKey/label 顺序 = 审定表行序）。
#:
#: 🔴 `account` 字段是**兜底 / 展示用，运行时取数一律不据此写死**。
#:   实证（`account_chart` `source='standard'`，9 个真实项目）：库内并存两个互不兼容的
#:   标准存货科目表变体，`1405`/`1406`/`1407`/`1408`/`1411`/`1416`/`1451`/`1461`
#:   的名称↔编码对应完全冲突（同一个 `1406` 一半项目是「库存商品」、另一半是「发出商品」）
#:   → **不存在一组写死就对的编码**。归集判据见
#:   `app.services.f2_extraction.category_rules.classify_f2_leaf`（按**科目名称**）。
#:
#: spec: .kiro/specs/f2-inventory-account-mapping-and-linkage/
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


#: 存货科目一级码区间（报表行 `BS-010 = SUM_TB('1401~1499','期末余额')`）。
_F2_INVENTORY_CODE_LO = "1401"
_F2_INVENTORY_CODE_HI = "1499"


def _is_inventory_code(account_code: str | None) -> bool:
    """一级科目段落在 `1401~1499` 内（区间口径与报表行 BS-010 一致）。纯函数。"""
    head = top_level_code(account_code)
    return bool(head) and _F2_INVENTORY_CODE_LO <= head <= _F2_INVENTORY_CODE_HI


def build_category_prefill(
    leaves: list[LeafRow],
    chart_names: dict[str, str] | None = None,
) -> dict[str, dict[str, float]]:
    """把存货**叶子**行按科目名称归入 F2-1 分类桶（纯函数，可单测）。

    Args:
        leaves: 已 `select_leaves` 的叶子行（严格点号边界判叶子，共享件口径）。
        chart_names: ``{一级码: 科目名}``，供叶子名未命中时回退父级名。

    Returns:
        ``{rowKey: {"opening": x, "closing": y}}``；只含**实际出现**且非全零的桶。
        备抵桶（`impairment-provision`）取绝对值（两种符号约定同解）。

    不变量（Property 1）：各桶（含 `other`）期末之和 == 全部叶子期末之和。
    """
    names = chart_names or {}
    buckets: dict[str, dict[str, float]] = {}
    for row in leaves or []:
        if not _is_inventory_code(row.account_code):
            continue
        parent = names.get(top_level_code(row.account_code))
        key = classify_f2_leaf(row.account_name, parent)
        b = buckets.setdefault(key, {"opening": 0.0, "closing": 0.0})
        b["opening"] += float(row.opening or 0)
        b["closing"] += float(row.closing or 0)
    out: dict[str, dict[str, float]] = {}
    for key, b in buckets.items():
        opening, closing = b["opening"], b["closing"]
        if is_f2_impairment_category(key):
            opening, closing = abs(opening), abs(closing)
        opening, closing = round(opening, 2), round(closing, 2)
        if opening == 0 and closing == 0:
            continue
        out[key] = {"opening": opening, "closing": closing}
    return out


async def _build_adjudication_prefill_v2(ctx: RenderContext) -> dict[str, dict]:
    """灰度开时：委托 extract_f2_category_values（新口径）取数。

    返回结构：{ rowKey: {opening, increase, decrease, closing, formulas, source_codes} }
    """
    from app.services.f2_extraction.extract import (
        ANCHOR_ACCOUNT_SEP,
        extract_f2_category_values,
    )
    from app.services.f2_extraction.presets import resolve_effective

    try:
        effective_bindings = await resolve_effective(ctx.db, ctx.wp_id, ctx.project_id)
    except Exception as e:
        logger.warning("F2 render: resolve_effective 失败, 回退默认绑定: %s", e)
        from app.services.f2_extraction.extract import build_default_bindings
        # 🔴 按**本项目实际科目表**生成绑定（写死编码在两版标准科目表下都可能错，
        #   见 `category_rules` 的实证表）；取不到科目表时才回退写死兜底。
        effective_bindings = build_default_bindings(
            await build_inventory_accounts(ctx)
        )

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
        # 同一 rowKey+field 可能对应多个科目码（如「周转材料」= 周转材料+包装物+
        # 低值易耗品），锚点带 `@code` 后缀区分 → 解析前截断，值按 `+=` 累加。
        anchor = anchor.split(ANCHOR_ACCOUNT_SEP, 1)[0]
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
        # 🔴 `+=` 不是 `=` —— 一个 rowKey 可能由多个科目码组成（见上方 `@code` 注释），
        #   写 `=` 会让后来的码覆盖前面的码（周转材料只剩最后一个子类）。
        entry[field] += info["value"]
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

    if _sem_accounts:
        result.setdefault('tb_source_codes', _sem_accounts.as_dict())

    return result


async def _build_adjudication_prefill(ctx: RenderContext) -> dict[str, dict[str, float]]:
    """无持久化审定数据时，从 tb_balance 存货科目预填各分类行期初/期末未审数。

    🔴 归集判据是**科目名称**不是编码 —— 存货科目的编码语义在本平台内不唯一
    （两版标准科目表并存，`1405`/`1406`/`1407`/`1408`/`1411`/`1416`/`1461` 全部冲突），
    按编码写死必然整表错位。详见
    `app.services.f2_extraction.category_rules`。

    - 叶子判定委托平台共享件 `four_table.select_leaves`（严格点号边界）——
      替代旧的 `_row_depth` + `max(by_depth)` 取最深层级（客户科目树参差时会整段丢叶子，
      与 K1 已修的同款 bug）。
    - 备抵（跌价准备）由名称识别并取绝对值。
    - 查询失败优雅降级返回 `{}`，不阻断渲染。

    返回结构：`{ rowKey: {"opening": float, "closing": float}, ... }`
    """
    from app.core.config import settings

    if settings.F2_FOUR_TABLE_EXTRACTION_ENABLED:
        return await _build_adjudication_prefill_v2(ctx)
    leaves = await _fetch_f2_inventory_leaves(ctx)
    if not leaves:
        return {}
    chart_names = await _fetch_inventory_chart_names(ctx)
    return build_category_prefill(leaves, chart_names)


async def _fetch_f2_inventory_leaves(ctx: RenderContext) -> list[LeafRow]:
    """取本项目 14xx 存货科目的**叶子**行（active 数据集，fail-open）。"""
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
            ).where(sa.and_(active_filter, TbBalance.account_code.like("14%")))
        )
        return select_leaves(to_leaf_rows(result.fetchall()))
    except Exception as e:  # noqa: BLE001 — 预填失败按空处理，不阻塞渲染
        logger.warning("F2 render: 审定表预填 tb_balance 查询失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
        return []


async def _fetch_inventory_chart_names(ctx: RenderContext) -> dict[str, str]:
    """本项目 14xx 一级科目 ``{码: 名}``（供叶子名未命中时回退父级名）。fail-open。"""
    try:
        rows = (
            await ctx.db.execute(
                sa.text(
                    "SELECT DISTINCT account_code, account_name FROM account_chart "
                    "WHERE project_id = :pid AND is_deleted = false "
                    "AND account_code ~ '^14' AND length(account_code) = 4 "
                    "AND source = 'client'"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchall()
        names = {r.account_code: r.account_name for r in rows if r.account_name}
        if names:
            return names
        # 客户科目表缺失时回退 standard 变体（仍是本项目自己的那一版）
        rows = (
            await ctx.db.execute(
                sa.text(
                    "SELECT DISTINCT account_code, account_name FROM account_chart "
                    "WHERE project_id = :pid AND is_deleted = false "
                    "AND account_code ~ '^14' AND length(account_code) = 4"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchall()
        return {r.account_code: r.account_name for r in rows if r.account_name}
    except Exception as e:  # noqa: BLE001
        logger.warning("F2 render: account_chart 查询失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
        return {}


async def build_inventory_accounts(ctx: RenderContext) -> list[dict]:
    """本项目实际存在的存货科目清单（供前端 AJE 科目下拉 / 溯源，替代写死清单）。

    Returns:
        ``[{"code", "name", "row_key"}]``，按编码升序；查询失败返回 ``[]``
        （前端回退既有静态清单 → 零回归）。
    """
    try:
        rows = (
            await ctx.db.execute(
                sa.text(
                    "SELECT DISTINCT account_code, account_name FROM account_chart "
                    "WHERE project_id = :pid AND is_deleted = false "
                    "AND account_code ~ '^14' "
                    "ORDER BY account_code"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning("F2 render: inventory_accounts 查询失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
        return []
    names = {
        r.account_code: r.account_name
        for r in rows
        if len(str(r.account_code or "")) == 4 and r.account_name
    }
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        code = str(r.account_code or "").strip()
        if not code or code in seen or not _is_inventory_code(code):
            continue
        seen.add(code)
        out.append({
            "code": code,
            "name": r.account_name or "",
            "row_key": classify_f2_leaf(r.account_name, names.get(top_level_code(code))),
        })
    return out


async def render(ctx: RenderContext) -> dict | None:

    # 科目定位（语义驱动，additive）
    try:
        _sem_accounts = await resolve_semantic_accounts(ctx, F2_SPEC)
    except Exception:  # noqa: BLE001
        _sem_accounts = None

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

    # ─── F2-1 TB 核对标量（存货净额 BS-010，走规则映射） ──────────────────
    # 🔴 报表行次 BS-010=存货（SUM_TB('1401~1499')）；此前误用 BS-008（预付款项 1123），
    #    规则解析返回 1123 使 fallback 从未生效 → 核对标量取的是预付款项净额而非存货。
    year = project_context.get("audit_year")
    if year:
        try:
            from app.services.report_account_mapping import (
                resolve_report_line_account_codes,
                build_trial_balance_code_filter,
            )

            codes = await resolve_report_line_account_codes(
                db, ctx.project_id, "BS-010",
                fallback=["1401~1499"],
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
                # 供前端 useF2Adjudication 作 TB 核对标量只读回退 seed（不覆盖手工录入）。
                # 前端 allResponses 来自 checklist-responses 端点（非 render responses_snapshot），
                # 故经 project_context.tb_amount 透传，而非注入 responses_snapshot。
                project_context["tb_amount"] = audited if audited else unadjusted
        except Exception as e:  # noqa: BLE001
            logger.warning("F2 render: trial_balance 存货净额查询失败: %s", e)

    # ─── 本项目实际存货科目清单（前端 AJE 下拉 / 溯源；替代写死清单）─────────
    inventory_accounts = await build_inventory_accounts(ctx)
    project_context["inventory_accounts"] = inventory_accounts
    # 取数溯源：报表行 + 按名称归类的科目明细（供 F2FourTableSourcePanel 展示）
    classified: dict[str, list[str]] = {}
    for item in inventory_accounts:
        classified.setdefault(item["row_key"], []).append(item["code"])
    project_context["tb_source_codes"] = {
        "row_code": "BS-010",
        "codes": [f"{_F2_INVENTORY_CODE_LO}~{_F2_INVENTORY_CODE_HI}"],
        "classified_by": "account_name",
        "classified": classified,
    }

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
