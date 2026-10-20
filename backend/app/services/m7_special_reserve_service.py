"""M7 专项储备 — 明细表 M7-2 导入导出 + 安全生产费计提测试（M7-4）。

``routers/m7_special_reserve.py`` 惰性 import 本模块的四个函数。

* 明细表的列与存储键逐字对齐前端：行字段与顺序取自 ``useM7Detail.ts`` 的 ``_triggerSave``，
  界面恢复读 ``M7-2-full-data`` 的 remark、其次 ``M7-2-rows``（``M7TabDetail.vue``）。
* 计提测试与 ``useM7AccrualEngine.ts`` / ``useM7AccrualTest.ts`` 同式同阈值。

科目：专项储备（贷方 / 权益类）—— 期末 = 期初 + 贷方（计提）− 借方（使用）。
"""

from __future__ import annotations

import io
import math
from typing import Any, Mapping, Sequence

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.m_detail_sheet_io import (
    ComputedColumn,
    DetailSheetSpec,
    InputColumn,
    export_data,
    export_template,
    import_sheet,
    unknown_sheet_message,
)

DETAIL_SHEET = "M7-2"

#: 计提差异重大性阈值 —— 与前端 ``useM7AccrualTest.ts`` 的 ``DEFAULT_THRESHOLD`` 逐值一致
#: （测试读 TS 源码钉住，改一侧另一侧会打红）。
ACCRUAL_THRESHOLD_ABSOLUTE = 1000.0
ACCRUAL_THRESHOLD_RELATIVE = 0.05
ACCRUAL_METHODS: dict[str, str] = {"output": "按产量分档", "revenue": "按营业收入"}


def _change_rate(audited_end: float, prior_end: float) -> float:
    """变动率：上期期末为 0 时审定期末非 0 记 100%（与界面同式）。"""
    if prior_end == 0:
        return 0.0 if audited_end == 0 else 1.0
    return (audited_end - prior_end) / prior_end


def _compute_detail(row: Mapping[str, Any]) -> dict[str, float]:
    """单行公式列，逐式照抄 ``useM7Detail.computedRows``（含运算顺序，与界面逐位相等）。"""
    debit_total = row["debitExpense"] + row["debitCapital"]
    end_balance = row["beginning"] + row["creditAccrual"] - debit_total
    audited_begin = row["beginning"] + row["beginAje"] + row["beginRje"]
    audited_accrual = row["creditAccrual"] + row["accrualAje"] + row["accrualRje"]
    audited_usage = debit_total + row["usageAje"] + row["usageRje"]
    audited_end = audited_begin + audited_accrual - audited_usage
    return {
        "debitTotal": debit_total,
        "endBalance": end_balance,
        "auditedBegin": audited_begin,
        "auditedAccrual": audited_accrual,
        "auditedUsage": audited_usage,
        "auditedEnd": audited_end,
        "changeAmount": audited_end - row["priorEnd"],
        "changeRate": _change_rate(audited_end, row["priorEnd"]),
    }


def _audited_end_total(computed: Sequence[Mapping[str, float]]) -> float:
    """审定期末合计，照抄 ``useM7Detail.totals.auditedEnd``（先分列求和再套期末公式）。"""
    audited_begin = sum(c["auditedBegin"] for c in computed)
    audited_accrual = sum(c["auditedAccrual"] for c in computed)
    audited_usage = sum(c["auditedUsage"] for c in computed)
    return audited_begin + audited_accrual - audited_usage


M7_DETAIL_SPEC = DetailSheetSpec(
    sheet_code=DETAIL_SHEET,
    sheet_title="明细表M7-2",
    full_item_id="M7-2-full-data",
    full_storage="remark",
    fallback_sources=(("M7-2-rows", "remark"),),
    row_item_prefix="M7-2-row-",
    total_item_id="M7-2-auditedEndTotal",
    row_key_prefix="m7-detail-import",
    input_columns=(
        InputColumn("项目名称", "itemName", "text"),
        InputColumn("期初余额", "beginning"),
        InputColumn("本期计提", "creditAccrual"),
        InputColumn("费用化支出", "debitExpense"),
        InputColumn("资本化支出", "debitCapital"),
        InputColumn("期初AJE", "beginAje"),
        InputColumn("期初RJE", "beginRje"),
        InputColumn("计提AJE", "accrualAje"),
        InputColumn("计提RJE", "accrualRje"),
        InputColumn("使用AJE", "usageAje"),
        InputColumn("使用RJE", "usageRje"),
        InputColumn("上期期初", "priorBeginning"),
        InputColumn("上期计提", "priorAccrual"),
        InputColumn("上期使用", "priorUsage"),
        InputColumn("上期期末", "priorEnd"),
        InputColumn("备注", "remark", "text"),
    ),
    computed_columns=(
        ComputedColumn("使用合计", "debitTotal"),
        ComputedColumn("期末余额", "endBalance"),
        ComputedColumn("审定期初", "auditedBegin"),
        ComputedColumn("审定计提", "auditedAccrual"),
        ComputedColumn("审定使用", "auditedUsage"),
        ComputedColumn("审定期末", "auditedEnd"),
        ComputedColumn("变动额", "changeAmount"),
        ComputedColumn("变动率", "changeRate", "ratio"),
    ),
    compute=_compute_detail,
    audited_end_total=_audited_end_total,
    guidance=(
        "使用合计 = 费用化支出 + 资本化支出",
        "期末余额 = 期初余额 + 本期计提 − 使用合计（权益类贷方）",
        "审定期初 = 期初余额 + 期初AJE + 期初RJE；审定计提 = 本期计提 + 计提AJE + 计提RJE",
        "审定使用 = 使用合计 + 使用AJE + 使用RJE；审定期末 = 审定期初 + 审定计提 − 审定使用",
        "变动额 = 审定期末 − 上期期末；变动率 = 变动额 ÷ 上期期末（上期期末为 0 时审定期末非 0 记 100%）",
    ),
)

#: 本前缀长路由三态支持的 sheet（白名单唯一真源）。界面只有 M7-2 有导入导出入口。
SUPPORTED_SHEETS: dict[str, DetailSheetSpec] = {DETAIL_SHEET: M7_DETAIL_SPEC}


def resolve_sheets(sheet: str | None) -> list[DetailSheetSpec]:
    """``None`` / 空 ⇒ 全部支持的 sheet；不认识的 sheet ⇒ 400，不静默回退成导出全部。"""
    code = (sheet or "").strip()
    if not code:
        return list(SUPPORTED_SHEETS.values())
    spec = SUPPORTED_SHEETS.get(code)
    if spec is None:
        raise HTTPException(status_code=400, detail=unknown_sheet_message(code, list(SUPPORTED_SHEETS)))
    return [spec]


async def generate_export_template(wp_id: str, db: AsyncSession, *, sheet: str | None = None) -> io.BytesIO:
    """空白模板（输入列表头 +「编制说明」）。不读库，``wp_id`` / ``db`` 只为与路由签名一致。"""
    return export_template(resolve_sheets(sheet))


async def generate_export_data(wp_id: str, db: AsyncSession, *, sheet: str | None = None) -> io.BytesIO:
    """当前数据（按界面恢复口径读回 + 公式列 + 合计行）。"""
    return await export_data(db, wp_id, resolve_sheets(sheet))


async def import_data(
    wp_id: str,
    content: bytes,
    db: AsyncSession,
    *,
    sheet: str | None = None,
    updated_by: Any = None,
) -> dict[str, Any]:
    """导入并整表替换明细行。前端把 sheet 放在表单字段里（路由收不到）⇒ 缺省按 M7-2。"""
    (spec,) = resolve_sheets(sheet or DETAIL_SHEET)
    return await import_sheet(db, wp_id, content, spec, updated_by=updated_by)


# ── 安全生产费计提测试（M7-4）────────────────────────────────────────────────


def _finite(value: Any, label: str) -> float:
    """缺失按 0（与前端 ``safe()`` 一致）；非数字 / 非有限数字拒绝。"""
    try:
        num = float(0 if value is None else value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"「{label}」不是数字") from exc
    if not math.isfinite(num):
        raise ValueError(f"「{label}」必须是有限数字")
    return num


def is_accrual_diff_material(diff: float, estimated: float) -> bool:
    """计提差异是否重大，逐字照前端 ``isDiffExceedThreshold``。

    |差异| ≤ 绝对阈值 ⇒ 否；应计提为 0 ⇒ 看 |差异| 是否超过绝对阈值；否则看相对差异是否超过比例。
    """
    if abs(diff) <= ACCRUAL_THRESHOLD_ABSOLUTE:
        return False
    if estimated == 0:
        return abs(diff) > ACCRUAL_THRESHOLD_ABSOLUTE
    return abs(diff / estimated) > ACCRUAL_THRESHOLD_RELATIVE


def _accrual_conclusion(diff: float, material: bool) -> str:
    if abs(diff) < 0.005:
        return "计提准确：应计提与账面计提一致。"
    gist = f"少计提 {diff:,.2f} 元" if diff > 0 else f"多计提 {-diff:,.2f} 元"
    tail = "，超过重要性阈值，需关注并说明原因。" if material else "，未超过重要性阈值。"
    return gist + tail


def run_accrual_test(
    *,
    method: str,
    tiers: Sequence[Mapping[str, Any]],
    revenue: float,
    revenue_rate: float,
    booked_accrual: float,
) -> dict[str, Any]:
    """安全生产费计提测试（纯函数）。

    * 按产量：应计提 = Σ（各档产量 × 档位标准）；按收入：应计提 = 营业收入 × 计提比例（小数，0.015 = 1.5%）
    * 差异 = 应计提 − 账面计提（正数为少计提，负数为多计提）——与前端 ``calcAccrualDiff`` 同向
    * 不支持的计提方式、非有限数字 ⇒ ``ValueError``（路由转 400）
    """
    method_key = str(method or "").strip().lower()
    if method_key not in ACCRUAL_METHODS:
        raise ValueError(f"不支持的计提方式「{method}」，可选：output（按产量分档）/ revenue（按营业收入）")
    booked = _finite(booked_accrual, "账面已计提金额")
    detail: dict[str, Any] = {"basis": ACCRUAL_METHODS[method_key]}
    if method_key == "output":
        estimated = 0.0
        tier_rows: list[dict[str, Any]] = []
        for no, tier in enumerate(tiers, start=1):
            output = _finite(tier.get("output"), f"第{no}档产量")
            rate = _finite(tier.get("rate"), f"第{no}档计提标准")
            amount = output * rate
            estimated += amount
            tier_rows.append({"tier": no, "output": output, "rate": rate, "amount": round(amount, 2)})
        detail.update(tiers=tier_rows, formula="应计提 = Σ（各档产量 × 档位标准）")
    else:
        base = _finite(revenue, "营业收入")
        rate = _finite(revenue_rate, "营业收入计提比例")
        estimated = base * rate
        detail.update(revenue=base, revenue_rate=rate, formula="应计提 = 营业收入 × 计提比例")
    diff = estimated - booked
    material = is_accrual_diff_material(diff, estimated)
    detail.update(
        direction="差异 = 应计提 − 账面计提；正数为少计提，负数为多计提",
        threshold={"absolute": ACCRUAL_THRESHOLD_ABSOLUTE, "relative": ACCRUAL_THRESHOLD_RELATIVE},
        conclusion=_accrual_conclusion(diff, material),
    )
    return {
        "method": method_key,
        "estimated": round(estimated, 2),
        "booked": round(booked, 2),
        "diff": round(diff, 2),
        "is_material": material,
        "detail": detail,
    }
