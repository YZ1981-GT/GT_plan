"""H1 固定资产 — 专属渲染策略.

科目定位（语义驱动）：
  原值 = 1601 固定资产
  累计折旧 = 1602 累计折旧
  减值准备 = 1603 固定资产减值准备
  报表行 BS-028 = TB('1601')-TB('1602')+TB('1606')  (soe)

返回 allResponses + projectContext + TB汇总 + 按分类预填 + tb_source_codes

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import logging
import re

import sqlalchemy as sa

from app.core.config import settings
from app.models.audit_platform_models import TbBalance, TbLedger, TrialBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.h1_account_scope import H1_ACCOUNT_SPEC, H1_SLOT_KEY_PREFIX
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

# 🔴 _H1_ACCOUNT_PREFIXES 保留作为兼容旧键名映射的引用，不再作取数路径真源
_H1_ACCOUNT_PREFIXES = {
    "1601": ("cost_unadjusted", "cost_audited"),
    "1602": ("dep_unadjusted", "dep_audited"),
    "1603": ("impair_unadjusted", "impair_audited"),
}

_H1_FA_CATEGORIES = (
    "房屋及建筑物",
    "机器设备",
    "运输设备",
    "办公设备",
    "其他设备",
)

H1_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h1-fixed-assets"},
    {"sheet_name": "固定资产审计程序表H1A", "component_type": "h1-fixed-assets"},
    {"sheet_name": "审定表H1-1", "component_type": "h1-fixed-assets"},
    {"sheet_name": "明细表H1-2", "component_type": "h1-fixed-assets"},
    {"sheet_name": "调整分录汇总H1-3", "component_type": "h1-fixed-assets"},
    {"sheet_name": "闲置检查表H1-4", "component_type": "h1-fixed-assets"},
    {"sheet_name": "会计政策估计检查表H1-5", "component_type": "h1-fixed-assets"},
    {"sheet_name": "分析表H1-6", "component_type": "h1-fixed-assets"},
    {"sheet_name": "增加检查表H1-7", "component_type": "h1-fixed-assets"},
    {"sheet_name": "减少检查表H1-8", "component_type": "h1-fixed-assets"},
    {"sheet_name": "监盘计划H1-9", "component_type": "h1-fixed-assets"},
    {"sheet_name": "盘点检查表H1-10", "component_type": "h1-fixed-assets"},
    {"sheet_name": "监盘小结H1-11", "component_type": "h1-fixed-assets"},
    {"sheet_name": "折旧测算表H1-12", "component_type": "h1-fixed-assets"},
    {"sheet_name": "折旧分配分析表H1-13", "component_type": "h1-fixed-assets"},
    {"sheet_name": "减值测算表H1-14", "component_type": "h1-fixed-assets"},
    {"sheet_name": "可收回金额测试表H1-15", "component_type": "h1-fixed-assets"},
    {"sheet_name": "房屋建筑物权属检查表H1-16", "component_type": "h1-fixed-assets"},
    {"sheet_name": "运输设备权属检查表H1-17", "component_type": "h1-fixed-assets"},
    {"sheet_name": "关联交易检查表H1-18", "component_type": "h1-fixed-assets"},
    {"sheet_name": "经营租出固定资产检查表H1-19", "component_type": "h1-fixed-assets"},
    {"sheet_name": "融资租出固定资产检查表H1-20", "component_type": "h1-fixed-assets"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h1-fixed-assets"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h1-fixed-assets"},
]


def _classify_fa_block(code: str) -> str | None:
    c = (code or "").strip()
    if c.startswith("1601"):
        return "cost"
    if c.startswith("1602"):
        return "dep"
    if c.startswith("1603"):
        return "impair"
    return None


def _classify_fa_category(code: str, name: str) -> str:
    """科目名称优先；其次二级码 01~05 启发式；再退化为「机器设备/其他设备」。

    关键词按特异性排序：房屋 → 运输 → 办公/电子 → 机器 → 显式其他。
    办公在机器之前判断，避免「办公设备」被 `设备` 误归机器。
    无任何名称信号且无二级码时，兜底为「其他设备」（由审计师在 H1-1 复核）。
    """
    s = re.sub(r"\s+", "", name or "")
    if re.search(r"房屋|建筑|厂房|仓库|构筑物|不动产|房产|土地", s):
        return "房屋及建筑物"
    if re.search(r"运输|车辆|汽车|客车|货车|专用车|挂车|叉车|拖拉机|船舶|飞机|机动车", s):
        return "运输设备"
    if re.search(r"办公|电子设备|电脑|计算机|打印|复印|服务器|网络|监控|摄像|空调|家具|器具", s):
        return "办公设备"
    if re.search(r"机器|机械|生产|生产线|流水线|机组|专用设备|通用设备|锅炉|电机|装置|仪器|仪表", s):
        return "机器设备"
    if re.search(r"其他|未分类|低值", s):
        return "其他设备"
    # 名称含泛化「设备/机床/工具」但无更具体信号 → 机器设备（较其他设备更贴切）
    if re.search(r"设备|机床|工具", s):
        return "机器设备"

    m = re.match(r"^160[123][.\-]?0?([1-5])", (code or "").strip())
    if m:
        return {
            "1": "房屋及建筑物",
            "2": "机器设备",
            "3": "运输设备",
            "4": "办公设备",
            "5": "其他设备",
        }.get(m.group(1), "其他设备")
    return "其他设备"


def _empty_amt() -> dict:
    return {"begin": 0.0, "debit": 0.0, "credit": 0.0, "end": 0.0, "unadjusted": 0.0}


def _leaf_codes(codes: set[str]) -> set[str]:
    """只保留叶子科目（某 code 不是任何其它 code 的前缀）。

    tb_balance 同时存父级(1601)与子科目(1601.01…)，父子同时累加会双算一倍。
    对齐 E1/K9 的 `_is_leaf` 铁律：只汇总叶子。
    """
    return {c for c in codes if not any(o != c and o.startswith(c) for o in codes)}


async def _build_category_prefill(ctx: RenderContext) -> dict:
    """从 tb_balance 的 1601/1602/1603 子科目按分类聚合，供 H1-1 预填未审数。"""
    buckets: dict[str, dict] = {
        cat: {"category": cat, "cost": _empty_amt(), "dep": _empty_amt(), "impair": _empty_amt(), "needs_review": False}
        for cat in _H1_FA_CATEGORIES
    }
    # 记录纯兜底项（名称无特征信号且无二级码匹配）
    _fallback_codes: set[str] = set()

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
            ).where(active_filter)
        )
        rows = [r for r in result.fetchall() if _classify_fa_block((r.account_code or "").strip())]
        leaves = _leaf_codes({(r.account_code or "").strip() for r in rows})
        for row in rows:
            code = (row.account_code or "").strip()
            if code not in leaves:
                continue  # 父级科目：由其子科目累加，跳过防双算
            block = _classify_fa_block(code)
            if not block:
                continue
            name = (row.account_name or "").strip()
            cat = _classify_fa_category(code, name)
            # 检测是否为纯兜底分类（即名称无任何关键词命中且无二级码匹配）
            if cat == "其他设备":
                s = re.sub(r"\s+", "", name)
                has_keyword = bool(re.search(r"其他|未分类|低值|设备|机床|工具", s))
                has_code = bool(re.match(r"^160[123][.\-]?0?[1-5]", code))
                if not has_keyword and not has_code:
                    _fallback_codes.add(code)
            target = buckets[cat][block]
            begin = float(row.opening_balance or 0)
            end = float(row.closing_balance or 0)
            # 发生额归一为非负：不同账套 tb_balance 对贷方类可能存负数（有符号）或正数（绝对值），
            # 前端 calcContraEndBalance(begin, debit, credit) 期望正数发生额，否则期末与未审数对不上。
            debit = abs(float(row.debit_amount or 0))
            credit = abs(float(row.credit_amount or 0))
            begin_v = begin if block == "cost" else abs(begin)
            end_v = end if block == "cost" else abs(end)
            target["begin"] += begin_v
            target["debit"] += debit
            target["credit"] += credit
            target["end"] += end_v
            target["unadjusted"] += end_v
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 category prefill tb_balance fetch failed: %s", e)

    # 标记含纯兜底科目的分类需要复核
    if _fallback_codes:
        buckets["其他设备"]["needs_review"] = True

    categories = [buckets[c] for c in _H1_FA_CATEGORIES]

    def _sum(block: str) -> float:
        return sum(float(r[block]["unadjusted"]) for r in categories)

    return {
        "categories": categories,
        "totals": {
            "cost1601": _sum("cost"),
            "dep1602": _sum("dep"),
            "impair1603": _sum("impair"),
        },
    }


"""折旧对方科目可用性阈值：填充率 ≥ 80% 才允许按对方科目（费用归属）自动归集。

实证背景：某真实账套 1602 分录 1519 行中 counterpart_account 非空仅 135 行（≈9%），
且凭证为多业务合并记账（按 voucher_no 归集会混入银行存款/应付账款等无关科目，
金额远超当年折旧）→ 默认不提供自动归集，只如实说明原因（宁缺勿造）。
"""
_COUNTERPART_FILL_THRESHOLD = 0.8


async def _probe_counterpart_availability(ctx: RenderContext) -> dict:
    """探测折旧对方科目可用性（Req3.4）。

    returns {"available": bool, "fill_rate": float, "total_lines": int, "reason": str}
    """
    try:
        active_filter = await get_active_filter(
            ctx.db, TbLedger.__table__, ctx.project_id, ctx.year
        )
        row = (
            await ctx.db.execute(
                sa.select(
                    sa.func.count().label("total"),
                    sa.func.count(
                        sa.case(
                            (
                                sa.and_(
                                    TbLedger.counterpart_account.isnot(None),
                                    TbLedger.counterpart_account != "",
                                ),
                                1,
                            )
                        )
                    ).label("filled"),
                ).where(active_filter, TbLedger.account_code.like("1602%"))
            )
        ).fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 counterpart availability probe failed: %s", e)
        return {
            "available": False,
            "fill_rate": 0.0,
            "total_lines": 0,
            "reason": "序时账折旧分录读取失败，无法判断对方科目可用性",
        }

    total = int(getattr(row, "total", 0) or 0)
    filled = int(getattr(row, "filled", 0) or 0)
    if total <= 0:
        return {
            "available": False,
            "fill_rate": 0.0,
            "total_lines": 0,
            "reason": "序时账无累计折旧（1602）分录，无法按对方科目归集",
        }

    fill_rate = round(filled / total, 4)
    if fill_rate >= _COUNTERPART_FILL_THRESHOLD:
        return {
            "available": True,
            "fill_rate": fill_rate,
            "total_lines": total,
            "reason": "",
        }
    return {
        "available": False,
        "fill_rate": fill_rate,
        "total_lines": total,
        "reason": (
            f"序时账未完整记录对方科目（填充率 {fill_rate:.0%}，共 {total} 条折旧分录），"
            "且凭证多为合并记账，无法按费用归属自动归集；请人工核对或与对方底稿（K8/K9/I6/F2/F5）勾稽"
        ),
    }


async def _build_h1_detail_prefill(ctx: RenderContext) -> dict:
    """tb_balance 叶子科目 → H1-2 明细**分类级**取数载荷（Req1）。

    每个叶子科目一行；发生额归一为非负；备抵段 begin/end 取绝对值。
    Card_Level 字段（资产编号/取得日期/年限/残值率等）一律不产出——四表库无资产卡片
    维度（tb_aux_balance 实证无该维度），由客户台账导入或手工补录（Req1.5 / Req8.1）。
    """
    empty = {"rows": [], "totals": {"cost": 0.0, "dep": 0.0, "impair": 0.0}, "source": "tb_balance"}
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
            ).where(active_filter)
        )
        raw = [
            r for r in result.fetchall()
            if _classify_fa_block((r.account_code or "").strip())
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 detail prefill fetch failed: %s", e)
        return empty

    if not raw:
        return empty

    leaves = _leaf_codes({(r.account_code or "").strip() for r in raw})
    # 按**分类**聚合成一行（原值 1601.0x 与折旧 1602.0x 是同类资产的两个侧面，
    # 若按单个科目码拆行会产出"折旧行原值为 0"的错乱明细）。
    by_cat: dict[str, dict] = {}
    needs_review: set[str] = set()
    for row in raw:
        code = (row.account_code or "").strip()
        if code not in leaves:
            continue  # 父级科目：由子科目承载，跳过防双算
        block = _classify_fa_block(code)
        if not block:
            continue
        name = (row.account_name or "").strip()
        cat = _classify_fa_category(code, name)
        if cat == "其他设备":
            s = re.sub(r"\s+", "", name)
            has_keyword = bool(re.search(r"其他|未分类|低值|设备|机床|工具", s))
            has_code = bool(re.match(r"^160[123][.\-]?0?[1-5]", code))
            if not has_keyword and not has_code:
                needs_review.add(code)
        entry = by_cat.setdefault(
            cat,
            {
                "category": cat,
                "source_codes": [],
                "cost": {"begin": 0.0, "debit": 0.0, "credit": 0.0, "end": 0.0},
                "dep": {"begin": 0.0, "debit": 0.0, "credit": 0.0, "end": 0.0},
                "impair": {"begin": 0.0, "debit": 0.0, "credit": 0.0, "end": 0.0},
                "needs_review": False,
            },
        )
        if code not in entry["source_codes"]:
            entry["source_codes"].append(code)
        begin = float(row.opening_balance or 0)
        end = float(row.closing_balance or 0)
        target = entry[block]
        target["begin"] += begin if block == "cost" else abs(begin)
        target["end"] += end if block == "cost" else abs(end)
        target["debit"] += abs(float(row.debit_amount or 0))
        target["credit"] += abs(float(row.credit_amount or 0))

    rows = [by_cat[c] for c in _H1_FA_CATEGORIES if c in by_cat]
    rows += [v for k, v in sorted(by_cat.items()) if k not in _H1_FA_CATEGORIES]
    for r in rows:
        r["source_codes"].sort()
        r["formula"] = " + ".join(f"TB('{c}','期末余额')" for c in r["source_codes"])
        if any(c in needs_review for c in r["source_codes"]):
            r["needs_review"] = True
    totals = {
        "cost": sum(r["cost"]["end"] for r in rows),
        "dep": sum(r["dep"]["end"] for r in rows),
        "impair": sum(r["impair"]["end"] for r in rows),
    }
    return {"rows": rows, "totals": totals, "source": "tb_balance"}


async def _build_h1_ledger_movement(ctx: RenderContext) -> dict:
    """tb_ledger 1601 借/贷方合计（本期增加/减少），供 H1-2 增减核对（Req2）。

    取不到分录时返回 available=False（前端显示"未取到"而非 0/一致）。
    """
    try:
        active_filter = await get_active_filter(
            ctx.db, TbLedger.__table__, ctx.project_id, ctx.year
        )
        row = (
            await ctx.db.execute(
                sa.select(
                    sa.func.count().label("lines"),
                    sa.func.coalesce(sa.func.sum(TbLedger.debit_amount), 0).label("debit_total"),
                    sa.func.coalesce(sa.func.sum(TbLedger.credit_amount), 0).label("credit_total"),
                ).where(active_filter, TbLedger.account_code.like("1601%"))
            )
        ).fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 ledger movement fetch failed: %s", e)
        return {"available": False, "debit_total": 0.0, "credit_total": 0.0, "lines": 0}

    lines = int(getattr(row, "lines", 0) or 0)
    if lines <= 0:
        return {"available": False, "debit_total": 0.0, "credit_total": 0.0, "lines": 0}
    return {
        "available": True,
        "lines": lines,
        "debit_total": abs(float(getattr(row, "debit_total", 0) or 0)),
        "credit_total": abs(float(getattr(row, "credit_total", 0) or 0)),
    }


async def _build_h1_depreciation_movement(ctx: RenderContext) -> dict:
    """tb_ledger 1602 贷方合计（本期折旧计提），供折旧 tab 账面折旧核对（Req3.1）。

    折旧计提在 1602 贷方；取不到分录返回 available=False（前端显示"未取到"）。
    """
    try:
        active_filter = await get_active_filter(
            ctx.db, TbLedger.__table__, ctx.project_id, ctx.year
        )
        row = (
            await ctx.db.execute(
                sa.select(
                    sa.func.count().label("lines"),
                    sa.func.coalesce(sa.func.sum(TbLedger.credit_amount), 0).label("credit_total"),
                ).where(active_filter, TbLedger.account_code.like("1602%"))
            )
        ).fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 depreciation movement fetch failed: %s", e)
        return {"available": False, "provision_total": 0.0, "lines": 0}

    lines = int(getattr(row, "lines", 0) or 0)
    if lines <= 0:
        return {"available": False, "provision_total": 0.0, "lines": 0}
    return {
        "available": True,
        "lines": lines,
        "provision_total": abs(float(getattr(row, "credit_total", 0) or 0)),
    }


async def _build_h1_four_table_prefill(ctx: RenderContext) -> dict:
    """组装 H1 四表取数载荷（各段独立 fail-open，Req6.3）。"""
    async def _safe(coro_fn, fallback):
        try:
            return await coro_fn(ctx)
        except Exception as e:  # noqa: BLE001
            logger.warning("H1 four-table prefill section failed: %s", e)
            return fallback

    detail = await _safe(
        _build_h1_detail_prefill,
        {"rows": [], "totals": {"cost": 0.0, "dep": 0.0, "impair": 0.0}, "source": "tb_balance"},
    )
    ledger = await _safe(
        _build_h1_ledger_movement,
        {"available": False, "debit_total": 0.0, "credit_total": 0.0, "lines": 0},
    )
    depreciation = await _safe(
        _build_h1_depreciation_movement,
        {"available": False, "provision_total": 0.0, "lines": 0},
    )
    counterpart = await _safe(
        _probe_counterpart_availability,
        {"available": False, "fill_rate": 0.0, "total_lines": 0, "reason": "对方科目可用性探测失败"},
    )
    return {
        "enabled": True,
        "detail": detail,
        "ledger_movement": ledger,
        "depreciation": depreciation,
        "counterpart": counterpart,
    }


async def _fetch_tb_data(ctx: RenderContext) -> tuple[dict, SemanticAccountResult]:
    """按语义槽取固定资产三层数据（原值 1601 / 累计折旧 1602 / 减值准备 1603）。

    Returns:
        ``(tb_values, accounts)``
    """
    accounts = await resolve_semantic_accounts(ctx, H1_ACCOUNT_SPEC)

    tb: dict[str, float] = {}
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
        logger.warning("H1 TB balance fetch failed: %s", e)

    # 按语义槽叶子聚合
    leaves = select_leaves(to_leaf_rows(tb_rows))
    for slot_key, prefix in H1_SLOT_KEY_PREFIX.items():
        slot = accounts.slots.get(slot_key)
        if slot is None or not slot.found:
            continue
        agg = aggregate_leaves(leaves, slot.codes)
        tb[f"{prefix}_unadjusted_opening"] = agg["opening"]
        tb[f"{prefix}_unadjusted_closing"] = agg["closing"]
        tb[f"{prefix}_unadjusted_debit"] = agg["debit"]
        tb[f"{prefix}_unadjusted_credit"] = agg["credit"]

    # trial_balance 精确匹配
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
            by_code: dict[str, tuple[float, float]] = {}
            for row in trial_rows:
                code = str(row.standard_account_code or "").strip()
                if not code:
                    continue
                prev = by_code.get(code, (0.0, 0.0))
                by_code[code] = (
                    prev[0] + float(row.unadjusted_amount or 0),
                    prev[1] + float(row.audited_amount or 0),
                )

            for slot_key, prefix in H1_SLOT_KEY_PREFIX.items():
                slot = accounts.slots.get(slot_key)
                if slot is None or not slot.found:
                    continue
                wanted = set(slot.standard_codes)
                if not wanted:
                    continue
                unadj = sum(v[0] for c, v in by_code.items() if c in wanted)
                audited = sum(v[1] for c, v in by_code.items() if c in wanted)
                tb[f"{prefix}_unadjusted"] = unadj
                tb[f"{prefix}_audited"] = audited
        except Exception as e:  # noqa: BLE001
            logger.warning("H1 trial_balance fetch failed: %s", e)

    # 兼容前端旧键名
    if "cost_unadjusted" in tb:
        tb["cost_1601_unadjusted"] = tb["cost_unadjusted"]
    if "dep_unadjusted" in tb:
        tb["dep_1602_unadjusted"] = tb["dep_unadjusted"]
    if "impair_unadjusted" in tb:
        tb["impair_1603_unadjusted"] = tb["impair_unadjusted"]

    tb["_parent_check"] = build_parent_check(
        accounts, tb_rows, trial_rows, H1_SLOT_KEY_PREFIX.keys()
    )
    return tb, accounts


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/适用准则）."""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category,
                       p.applicable_standard_v2 AS applicable_standards,
                       p.template_type, p.report_scope
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
            """),
            {"wp_id": str(ctx.wp_id)},
        )
        row = result.fetchone()
        if row:
            project_ctx["client_name"] = row.client_name or ""
            project_ctx["audit_year"] = str(row.audit_year) if row.audit_year else ""
            project_ctx["business_category"] = row.business_category or ""
            project_ctx["applicable_standards"] = row.applicable_standards or ""
            # 附注披露变体权威源：projects.template_type(soe|listed) + report_scope(standalone|consolidated)
            # 注意 applicable_standard_v2.entity_type 实测与 template_type 可能不一致，不作变体判定依据。
            project_ctx["template_type"] = (
                str(row.template_type.value) if hasattr(row.template_type, "value")
                else (str(row.template_type) if row.template_type else "")
            )
            project_ctx["report_scope"] = (
                str(row.report_scope.value) if hasattr(row.report_scope, "value")
                else (str(row.report_scope) if row.report_scope else "")
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """H1固定资产渲染策略：allResponses + projectContext + TB + 分类预填."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H1%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 render responses load failed: %s", e)

    tb_values, accounts = await _fetch_tb_data(ctx)

    # Wave 6: 审定表 TB 核对走报表行规则映射（Req5.1-5.3）
    try:
        from app.services.report_account_mapping import resolve_report_line_account_codes
        # 固定资产报表行 = BS-028（report_config 实测：listed=TB('1601')-TB('1602')，
        # soe=…+TB('1606')）。此前误用 BS-024（实为「长期股权投资」TB('1511')）→ 反解出 1511，
        # 与固定资产完全无关。fallback 仍含 1603 减值准备（BS-028 公式不含 1603，但 H1 审定表
        # 需覆盖原值/折旧/减值三段，故无映射时兜底三码）。
        h1_source_codes = await resolve_report_line_account_codes(
            ctx.db, ctx.project_id, "BS-028", fallback=["1601", "1602", "1603"]
        )
    except Exception:  # noqa: BLE001
        h1_source_codes = ["1601", "1602", "1603"]
    category_prefill = await _build_category_prefill(ctx)
    project_context = await _load_project_context(ctx)

    # Wave 5: 补充 related_parties + bs_date（Req4.1 — H1-18 关联方/H1-17 年检）
    if "bs_date" not in project_context:
        audit_year = project_context.get("audit_year", "")
        project_context["bs_date"] = f"{audit_year}-12-31" if audit_year else ""
    if "related_parties" not in project_context:
        try:
            rp_result = await ctx.db.execute(
                sa.text(
                    "SELECT name, relation_type FROM related_party_registry "
                    "WHERE project_id = :pid AND is_deleted = false"
                ),
                {"pid": str(ctx.project_id)},
            )
            project_context["related_parties"] = [
                {"name": r.name, "relation_type": r.relation_type or ""}
                for r in rp_result.fetchall()
            ]
        except Exception:  # noqa: BLE001
            project_context["related_parties"] = []

    resolved_codes = sorted({c for slot in accounts.slots.values() if slot.found for c in slot.codes})

    # 🔴 2026-08-03：曾在同一 dict 里写了**两个** `tb_source_codes` 键
    # （前者 `accounts.as_dict()` 语义 dict、后者 `h1_source_codes` 旧路径码列表），
    # Python 静默取最后一个 → 溯源面板拿到数组、`hasSemanticAccountSource` 恒 false、
    # **面板永不渲染**。`get_diagnostics` / vitest / 55 个守卫全查不出，
    # 只有浏览器实测 + 拉 render-config 看实际结构才暴露。
    # 现统一为语义 dict，旧列表并入 `legacy_report_line_codes` 供既有消费方兼容。
    source_codes = accounts.as_dict()
    source_codes["legacy_report_line_codes"] = list(h1_source_codes or [])

    payload = {
        "component_type": "h1-fixed-assets",
        "account_codes": resolved_codes or ["1601", "1602", "1603"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": source_codes,
        "adjudication_category_prefill": category_prefill,
        "project_context": project_context,
        "prefix": "H1",
        "sheets": H1_SHEETS,
    }

    # 灰度：关闭时不输出任何取数字段（逐字节等价现状，Req6.1）
    if getattr(settings, "H1_FOUR_TABLE_EXTRACTION_ENABLED", False):
        try:
            payload["h1_four_table_prefill"] = await _build_h1_four_table_prefill(ctx)
        except Exception as e:  # noqa: BLE001
            logger.warning("H1 four-table prefill assembly failed: %s", e)

    return payload
