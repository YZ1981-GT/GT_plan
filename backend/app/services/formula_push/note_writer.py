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

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.formula_push.js_compat import js_json_number, read_number

logger = logging.getLogger(__name__)

# ─── 附注模板数据（按需加载，进程生命周期内缓存） ──────────────────────────
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"

_TEMPLATE_CACHE: dict[str, list[dict]] = {}


def _load_note_template(template_type: str) -> list[dict]:
    """加载附注模板 sections 列表，缓存。"""
    if template_type in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[template_type]
    path = _DATA_DIR / f"note_template_{template_type}.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    sections = data.get("sections") or []
    _TEMPLATE_CACHE[template_type] = sections
    return sections


def _find_template_table(
    template_type: str, section_number: str, table_name: str,
) -> dict | None:
    """从附注模板中按 section_number 和 table name 定位到目标表定义。"""
    sections = _load_note_template(template_type)
    for sec in sections:
        if sec.get("section_number") != section_number:
            continue
        for tbl in sec.get("tables") or []:
            if tbl.get("name") == table_name:
                return tbl
    return None


#: 附注字段 → (披露行取值键, addr_id 期间后缀)
#
# 字段由规则 target.fields 按需声明；登记表是字段语义的唯一真源。
# ⚠ 顺序决定 build_main_skeleton 骨架行的键序和 e1_note_skeleton.json 夹具对拍，
#   新增字段必须追加到末尾，不得调换已有顺序。
NOTE_FIELDS: dict[str, tuple[str, str]] = {
    "end_amount": ("ending", "end"),
    "prior_amount": ("opening", "prior"),
    # ── D1~D7 应收票据族六字段（batch-e Task 1~2） ─────────────────────
    # value_key = 字段名本身（六字段每个取不同值，不像 end_amount/prior_amount 只有两个值）
    "end_balance": ("end_balance", "end"),       # 期末余额
    "end_provision": ("end_provision", "end"),   # 期末坏账准备
    "end_book_value": ("end_book_value", "end"), # 期末账面价值
    "prior_balance": ("prior_balance", "prior"),       # 期初余额
    "prior_provision": ("prior_provision", "prior"),   # 期初坏账准备
    "prior_book_value": ("prior_book_value", "prior"), # 期初账面价值
}

#: 默认骨架字段——不指定 fields 时 build_main_skeleton 沿用此列表（E1 等旧规则向后兼容）。
_DEFAULT_SKELETON_FIELDS: list[str] = ["end_amount", "prior_amount"]


@dataclass(frozen=True)
class MainSkeleton:
    """后端构建的附注主表骨架，与前端 buildE1SyncPayload 产出逐字一致。"""
    rows: list[dict]
    columns: list[dict]


def build_main_skeleton(
    template_type: str, section: str, table_name: str,
    fields: Sequence[str] | None = None,
) -> MainSkeleton | None:
    """按规则声明的附注章节和表名构建主表骨架。

    产出 rows = [{label, *fields: None, is_total?}]，columns 与模板定义一致。
    ``fields`` 指定时只为这些字段建列（D1 六字段等），为 None 时用旧默认（end_amount/prior_amount）。
    找不到模板类型、章节或表返回 None；章节不再由模板类型隐式推导。

    spec: formula-push-all-subjects-rollout · design §六 6.3 · 需求 5.2
    """
    try:
        tbl_def = _find_template_table(template_type, section, table_name)
    except FileNotFoundError:
        # 保留未知模板类型的旧调用语义：无法加载模板时视为没有表定义。
        return None
    if tbl_def is None:
        return None
    # 确定要建的字段列表
    field_names = list(fields) if fields else _DEFAULT_SKELETON_FIELDS
    rows: list[dict] = []
    for row_def in tbl_def.get("rows") or []:
        label = row_def.get("label", "")
        row: dict = {"label": label}
        row.update({fn: None for fn in field_names})
        if row_def.get("is_total"):
            row["is_total"] = True
        rows.append(row)
    columns: list[dict] = []
    for col_def in tbl_def.get("columns") or []:
        col: dict = {}
        for k in ("key", "label", "is_label", "flat", "format"):
            if k in col_def:
                col[k] = col_def[k]
        columns.append(col)
    return MainSkeleton(rows=rows, columns=columns)


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

#: 明确非底稿来源——只有这些值才判"模板取数维护"；_source=None 视为未标记（放行）。
#: spec: formula-push-note-skip-reduction · 需求 1.3
_KNOWN_NON_WORKPAPER: frozenset[str] = frozenset({"template", "import", "migration"})


def locate_table(table_data: Any, table: str) -> tuple[NoteTable | None, str | None]:
    """定位附注表；返回 (表, None) 或 (None, 中文跳过原因)。

    分级判断（spec: formula-push-note-skip-reduction · 需求 1.1–1.3）：
    - ``_source`` 明确非底稿 → 跳过
    - ``sub_table_data`` 存在且含目标子表 → 按子表定位
    - 无 ``sub_table_data`` 但有顶层 ``rows`` → 旧格式兜底
    """
    if not isinstance(table_data, dict) or not table_data:
        return None, "附注章节尚无表格数据"

    source = table_data.get("_source")

    # ① 明确非底稿来源 → 跳过
    if source in _KNOWN_NON_WORKPAPER:
        return None, "附注由模板取数维护（尚未与底稿同步），公式推送不改写"

    # ② sub_table_data 存在 → 按子表定位（原有主路径）
    sub = table_data.get("sub_table_data")
    if isinstance(sub, dict) and sub:
        rows = sub.get(table)
        if not isinstance(rows, list):
            return None, f"附注中没有「{table}」表"
        cols = table_data.get("_sub_table_columns")
        defs = [d for d in ((cols or {}).get(table) or []) if isinstance(d, dict) and d.get("key")] if isinstance(
            cols, dict) else []
        label_def = next((d for d in defs if d.get("is_label")), defs[0] if defs else None)
        value_keys = [d["key"] for d in defs if d is not label_def]
        return NoteTable(rows=rows, value_keys=value_keys, section_locked=detect_manual_override(table_data)), None

    # ③ 无 sub_table_data 但有顶层 rows → 旧格式兜底（需求 1.2）
    rows = table_data.get("rows")
    if isinstance(rows, list) and rows:
        # 旧格式的 values 列表按位置：[0]=期末 [1]=期初，映射到标准字段名
        return NoteTable(rows=rows, value_keys=["end_amount", "prior_amount"],
                         section_locked=detect_manual_override(table_data)), None

    return None, "附注章节无可定位的表格数据"


def row_label(row: Any) -> str:
    return str(row.get("label") or "").strip() if isinstance(row, dict) else ""


def find_row(rows: Sequence[Any], labels: Sequence[str]) -> int | None:
    """按标签找行：先精确匹配，再去常见后缀（"小计"等）二次匹配。

    spec: formula-push-note-skip-reduction · 需求 2.2
    """
    wanted = [str(label).strip() for label in labels if str(label or "").strip()]
    # ① 精确匹配
    for label in wanted:
        for index, row in enumerate(rows):
            if row_label(row) == label and not (isinstance(row, dict) and row.get("is_total")):
                return index
    # ② 去"小计"后缀再匹配（D1 noteType 带"小计"而附注行不带）
    _STRIP_SUFFIXES = ("小计",)
    for label in wanted:
        for suffix in _STRIP_SUFFIXES:
            if label.endswith(suffix):
                stripped = label[:-len(suffix)]
                if stripped:
                    for index, row in enumerate(rows):
                        if row_label(row) == stripped and not (isinstance(row, dict) and row.get("is_total")):
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


def has_obscured_data(table_data: dict, table_name: str) -> str | None:
    """检查附注章节是否有会被骨架遮挡的数据（需求 5.2）。

    如果 sub_table_data 以外有非空非零数值（顶层 rows/_tables 有业务数据）、
    或 sub_table_data 里该表以外的子表有人工/锁定单元格，返回中文原因；否则 None。

    只检查该表**缺失**时的「原表格」——即 rows / _tables 里可能存在用户不可见
    但将被骨架覆盖的数据。
    """
    rows = table_data.get("rows")
    if isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            for k, v in r.items():
                if k in ("label", "row_type", "is_total", "is_label") or k.startswith("_"):
                    continue
                # spec: formula-push-note-skip-reduction · 需求 4.1
                # values 是列表，逐元素检查（[None, None] 不算有数据）
                if k == "values":
                    if isinstance(v, list) and any(
                        e is not None and e != 0 and e != "" and e != "0"
                        for e in v
                    ):
                        return f"顶层 rows 含非空数值（values={v!r}）"
                    continue
                if v is not None and v != 0 and v != "" and v != "0":
                    return f"顶层 rows 含非空数值（{k}={v!r}）"
    tables = table_data.get("_tables")
    if isinstance(tables, list):
        for t in tables:
            if not isinstance(t, dict):
                continue
            t_rows = t.get("rows")
            if isinstance(t_rows, list) and len(t_rows) > 0:
                for r in t_rows:
                    if not isinstance(r, dict):
                        continue
                    vals = r.get("values")
                    if isinstance(vals, list):
                        for v in vals:
                            if v is not None and v != 0 and v != "" and v != "0":
                                return f"_tables 含非空数值"
    return None
