"""试算表正式导出（`EXPORT_SURFACE_REGISTRY.trial_balance_export`）。

🔴 **本模块是补一个真实缺陷**：前端 `views/TrialBalance.vue` 的「导出」按钮调
`P.trialBalance.export(pid)`（= `/api/projects/{pid}/trial-balance/export?year=`），
而后端**从来没有这个端点** ⇒ 点一次 404、拿不到任何文件。同一形态的
`/trial-balance/summary/export`、`/trial-balance/bulk-export` 也都只在注册表里。

出口分类 = **formal**（正式出具），因此必须：

1. **金额按 `ExportUnitPolicy.divisor` 折算**（Decimal `ROUND_HALF_UP` 到 0.01）；
2. **写单位标注**（「金额单位：元/千元/万元」）—— 数值与标注同源，
   否则「按万元折算但标注写元」比不折算更危险；
3. **不写 `_GT_EXPORT_META`** —— 那是 data_exchange 的标记；formal 出口出现它
   意味着「正式件被当成数据交换件」，`assert_formal_has_no_meta` 会拦。

设计纪律（与 `report_body_service` 的 placeholder 折算同口径）：

- `divisor == 1` **不做量化**（`1234.5` 不变成 `1234.50`）；
- `None` / 空串 → 空单元格（缺数 ≠ 零）；
- 非数字（脏数据里的占位文本）原样写成文本，不中断整份导出。
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

#: 金额列 → 中文表头。顺序即导出列顺序。
_AMOUNT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("opening_balance", "期初余额"),
    ("unadjusted_amount", "未审数"),
    ("rje_adjustment", "重分类调整"),
    ("aje_adjustment", "审计调整"),
    ("wp_adjustment", "底稿调整"),
    ("audited_amount", "审定数"),
)

_UNIT_LABELS: dict[str, str] = {
    "yuan": "元",
    "qian": "千元",
    "wan": "万元",
}


def convert_amount(
    raw: Any, divisor: int
) -> Decimal | str | None:
    """把一个金额转成导出值。

    Returns:
        - `None`：缺数（raw 是 None / 空串）⇒ 空单元格
        - `Decimal`：可解析数字，已按 divisor 折算并量化到 0.01
        - `str`：不可解析（占位文本等）⇒ 原样保留，不中断导出

    🔴 `divisor == 1` 不做量化：元口径下 `1234.5` 必须还是 `1234.5`，
    量化成 `1234.50` 会让「元」和「万元」两种导出的字符串形态不一致，
    下游按字符串比对时误判成「数值变了」。
    """
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return str(raw)
    if divisor == 1:
        return value
    return (value / Decimal(divisor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_trial_balance_workbook(
    rows: list[dict[str, Any]],
    *,
    policy_snapshot: str | None = None,
    year: int | None = None,
    company_code: str = "001",
) -> bytes:
    """生成试算表 xlsx。

    Args:
        rows: 与 `GET /api/projects/{pid}/trial-balance` 同结构的行
        policy_snapshot: `export_policy_snapshot.build_policy_snapshot` 的输出；
            `None` ⇒ 元口径不折算（保持旧行为，便于既有调用方）
        year: 导出年度（写进标题，缺失时标题不带年度）
        company_code: 企业代码（写进标题）

    Returns:
        xlsx 字节
    """
    unit, divisor = _read_policy(policy_snapshot)

    wb = Workbook()
    ws = wb.active
    ws.title = "试算表"

    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="DDEBF7")

    # ── 标题 ──
    title_parts = ["试算平衡表"]
    if year is not None:
        title_parts.append(f"{year} 年度")
    if company_code:
        title_parts.append(f"企业代码 {company_code}")
    ws.cell(row=1, column=1, value="  ".join(title_parts)).font = Font(bold=True, size=14)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4 + len(_AMOUNT_COLUMNS))

    # ── 单位标注（数值与标注同源）──
    ws.cell(row=2, column=1, value=f"金额单位：{_UNIT_LABELS.get(unit, unit)}").font = Font(italic=True)

    # ── 表头 ──
    headers = ["科目编码", "科目名称", "类别", "方向"] + [label for _, label in _AMOUNT_COLUMNS]
    for idx, text in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=idx, value=text)
        cell.font = bold
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center")

    # ── 数据行 ──
    for offset, row in enumerate(rows):
        r = 4 + offset
        ws.cell(row=r, column=1, value=row.get("standard_account_code") or "")
        ws.cell(row=r, column=2, value=row.get("account_name") or "")
        ws.cell(row=r, column=3, value=row.get("account_category") or "")
        ws.cell(row=r, column=4, value=_direction_label(row.get("direction")))
        for col_offset, (key, _label) in enumerate(_AMOUNT_COLUMNS):
            value = convert_amount(row.get(key), divisor)
            ws.cell(row=r, column=5 + col_offset, value=value)

    # ── 列宽 ──
    widths = [16, 32, 12, 8] + [16] * len(_AMOUNT_COLUMNS)
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _direction_label(direction: Any) -> str:
    """方向 → 中文（导出件给审计师看，不写 `debit`）。"""
    if direction == "debit":
        return "借"
    if direction == "credit":
        return "贷"
    return ""


def _read_policy(snapshot: str | None) -> tuple[str, int]:
    """从快照 JSON 取 (unit, divisor)。快照非法时**抛**，不静默按元导出。

    🔴 静默回落会让「万元」项目拿到元口径文件，金额差 1 万倍且看不出。
    """
    if not snapshot:
        return "yuan", 1
    import json

    payload = json.loads(snapshot)
    unit = payload.get("unit")
    divisor = payload.get("divisor")
    if not isinstance(unit, str) or not isinstance(divisor, int) or divisor <= 0:
        raise ValueError(f"unit_policy_snapshot 非法（unit={unit!r}, divisor={divisor!r}）")
    return unit, divisor
