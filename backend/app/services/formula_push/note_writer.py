"""附注主表单元格定位 / 读写（纯函数，不碰 DB）。

spec: chain-closure-phase2-formula-push-engine · design §五 附注单元格 / §七 写入 / ADR-PUSH-004

附注 ``table_data`` 三种形态（真库实证）：

* **F2** —— ``sub_table_data[表名]`` 行形如 ``{label, end_amount, prior_amount, is_total?}``
  （底稿 sync-from-workpaper 写入）。无单元格模式，人工改值由推送状态表的「上次推送值」判定。
* **F3** —— ``sub_table_data[表名]`` 行形如 ``{label, values:[...], _cell_modes, _cell_meta}``
  （旧 binding 快照经迁移脚本搬入；运行时**没有**任何刷新器写它 —— 已查证）。列序取
  ``_sub_table_columns[表名]`` 去掉标签列后的顺序；``_cell_modes[i] ∈ {manual, locked}`` 视为人工 / 锁定。
* **F1** —— 只有顶层 ``rows`` / ``_tables``，由附注模板取数维护 ⇒ **不推送**（打上底稿来源标记会让
  读路径只投影 sub_table_data、遮住原表，且各刷新器从此跳过该章节）。

不建行、不改标签（ADR-PUSH-004）；只改目标数值单元格。合计行 = 合计行之前各非合计行之和。

读写口径与附注渲染的投影器 ``note_sub_table_projector`` 对齐（否则写了也看不见）：

* 只认 ``_source ∈ {workpaper, workpaper_html}`` 的章节 —— 投影器只对这两种来源渲染
  ``sub_table_data``，其余来源显示的是 ``rows`` / ``_tables``；
* 行里已有业务键（``end_amount``）就读写业务键，否则才读写 ``values[i]`` —— 投影器逆投影时
  「已存在的业务键不被覆盖」，两者并存时显示的是业务键。
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.services.formula_push.js_compat import js_json_number, read_number

#: 附注字段 → (披露行取值键, addr_id 期间后缀)
NOTE_FIELDS: dict[str, tuple[str, str]] = {
    "end_amount": ("ending", "end"),
    "prior_amount": ("opening", "prior"),
}


@dataclass(frozen=True)
class NoteTable:
    """定位到的附注表。"""

    rows: list            # 原地可改的行列表（调用方传入 table_data 的深拷贝）
    value_keys: list[str]  # F3 列序（去标签列）；F2 为空也可
    section_locked: bool   # 整节人工覆盖（_manual_override）


def detect_manual_override(table_data: Any) -> bool:
    """与 ``wp_disclosure_sync_service._detect_manual_override`` 同判据（顶层或 sub_table_data 标记）。"""
    if not isinstance(table_data, dict):
        return False
    if table_data.get("_manual_override") is True:
        return True
    sub = table_data.get("sub_table_data")
    return isinstance(sub, dict) and sub.get("_manual_override") is True


#: 投影器渲染 sub_table_data 的来源（note_sub_table_projector._WORKPAPER_SOURCES）
WORKPAPER_SOURCES: tuple[str, ...] = ("workpaper", "workpaper_html")


def locate_table(table_data: Any, table: str) -> tuple[NoteTable | None, str | None]:
    """定位附注表；返回 (表, None) 或 (None, 中文跳过原因)。"""
    if not isinstance(table_data, dict) or not table_data:
        return None, "附注章节尚无表格数据"
    sub = table_data.get("sub_table_data")
    if not isinstance(sub, dict) or not sub or table_data.get("_source") not in WORKPAPER_SOURCES:
        return None, "附注由模板取数维护（尚未与底稿同步），公式推送不改写"
    rows = sub.get(table)
    if not isinstance(rows, list):
        return None, f"附注中没有「{table}」表"
    cols = table_data.get("_sub_table_columns")
    defs = [d for d in ((cols or {}).get(table) or []) if isinstance(d, dict) and d.get("key")] if isinstance(
        cols, dict) else []
    # 标签列判定与投影器 _pick_label_def 一致：首个 is_label，否则首列
    label_def = next((d for d in defs if d.get("is_label")), defs[0] if defs else None)
    value_keys = [d["key"] for d in defs if d is not label_def]
    return NoteTable(rows=rows, value_keys=value_keys, section_locked=detect_manual_override(table_data)), None


def row_label(row: Any) -> str:
    return str(row.get("label") or "").strip() if isinstance(row, dict) else ""


def find_row(rows: Sequence[Any], labels: Sequence[str]) -> int | None:
    """按标签找行：先附注字面，再底稿字面（历史同步可能写成底稿口径，如国企「现金」）。"""
    wanted = [str(label).strip() for label in labels if str(label or "").strip()]
    for label in wanted:
        for index, row in enumerate(rows):
            if row_label(row) == label and not (isinstance(row, dict) and row.get("is_total")):
                return index
    return None


def find_total_row(rows: Sequence[Any]) -> int | None:
    for index, row in enumerate(rows):
        if isinstance(row, dict) and (row.get("is_total") or row.get("row_type") == "total"):
            return index
    return None


def _is_f3(row: Any, field: str) -> bool:
    """按位置读写：行无该业务键、但有 ``values`` 列表（投影器同优先级：业务键在先）。"""
    return isinstance(row, dict) and field not in row and isinstance(row.get("values"), list)


def read_cell(row: dict, field: str, value_keys: list[str]) -> tuple[bool, Any, str | None]:
    """读单元格：返回 (可定位, 当前值, 单元格模式)。F3 按列序取 values[i]。"""
    if _is_f3(row, field):
        if field not in value_keys:
            return False, None, None
        i = value_keys.index(field)
        values = row["values"]
        current = values[i] if i < len(values) else None
        mode = (row.get("_cell_modes") or {}).get(str(i))
        return True, current, mode
    return True, row.get(field), None


def write_cell(row: dict, field: str, value: float, value_keys: list[str]) -> None:
    number = js_json_number(value)
    if _is_f3(row, field):
        i = value_keys.index(field)
        values = row["values"]
        while len(values) <= i:
            values.append(None)
        values[i] = number
        return
    row[field] = number


def external_mode(section_locked: bool, cell_mode: str | None) -> str | None:
    """整节人工覆盖或单元格 locked → locked；单元格 manual → manual；其余 None（按推送状态判）。"""
    if section_locked or cell_mode == "locked":
        return "locked"
    if cell_mode == "manual":
        return "manual"
    return None


def total_formula(rows: Sequence[Any], total_index: int, field: str, value_keys: list[str]) -> float:
    """合计 = 合计行之前各非合计行该列之和（缺值按 0；「其中：」行在合计之后，天然不计）。"""
    total = 0.0
    for row in rows[:total_index]:
        if not isinstance(row, dict) or row.get("is_total"):
            continue
        ok, current, _ = read_cell(row, field, value_keys)
        number = read_number(current) if ok else None
        total = total + (number if number is not None else 0.0)
    return total
