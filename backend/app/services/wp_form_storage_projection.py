"""M 循环「表单存储」→ 单元格坐标的投影（spec `m-cycle-form-storage-cell-projection`）。

## 为什么需要它

`WP()` 表间引用的取值链路是：

```
wp_cell_reader.resolve_wp_cell
  → 查 working_paper.parsed_data
  → extract_custom_cells(parsed_data)
```

M 循环（应付股利 / 实收资本 / 库存股 …）的数据**不在** `parsed_data` 里 ——
它在 `checklist_responses`（表单逐行 JSON）。所以 2026-11-16 实测
`WP('M1','明细表M1-2','D14')` 恒返 `Decimal('0')`，原因
「该底稿以表单方式录入，数据不在单元格中，本期暂不支持取值」
（`acnr/wp_cell_target._storage_kind` 的 `value_in_form_storage`）。

## 本模块做什么

把表单行**即时投影**成 `CellRecord`，让 `extract_custom_cells` 的调用方
在 `records` 为空时多一条取值路径。

## 🔴 核心约束：零写入

投影**不写** `parsed_data`、不写任何新表 —— `checklist_responses` 仍是唯一真源。
理由：前序 spec `m-cycle-key-naming-unification` 任务 4 刚把 M 循环的整表
`*-full-data` 并行写入删掉（双写漂移缺陷）；投影若落库就是倒退。

## 映射规则（全部读 provider，不手写）

| 维度 | 来源 |
|---|---|
| 行号 | `MSheetConfig.first_data_row + i`（i 取自 item_id 的 `row-{i}`） |
| 列号 | `MSheetConfig.fields[].json_key → .column` |
| sheet 名 | `MSheetConfig.sheet_name` |

## 支持的 item_id 形态

只支持**逐行 JSON**：`{前缀}row-{i}-data`（如 `M1-M1-2-row-0-data`）。

不支持（显式给原因，不静默）：
- 整表 JSON（`*-full-data`）—— 前序 spec 已删该写入，若检测到说明有旧数据残留；
- 审定表（`M{n}-1-tb-amount` 等）—— 非行表形态，需「按项目名查行」，另立 spec。
"""
from __future__ import annotations

import importlib
import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

logger = logging.getLogger(__name__)

__all__ = [
    "FORM_ROW_PREFIXES",
    "ProjectedCell",
    "project_form_rows_to_cells",
    "row_prefix_for_wp_code",
]

# ─── 原因码（与 acnr/reasons.CELL_VALUE_REASONS 的键一一对应）─────────────
REASON_ROW_JSON_INVALID = "form_row_json_invalid"
REASON_FIELD_NOT_IN_PROVIDER = "form_field_not_in_provider"
REASON_ROW_BEYOND_TEMPLATE = "form_row_beyond_template"
REASON_DETERMINATION_NOT_PROJECTED = "determination_sheet_not_projected"

#: `row-{i}-data` 的 i 段（允许前后有别的段，如 `M1-M1-2-row-0-data`）。
_ROW_INDEX_RE = re.compile(r"(?:^|-)row-(\d+)-data$")

#: 审定表 / 非行表形态的 item_id（用于给出「暂不支持」而不是「字段不存在」）。
_DETERMINATION_LIKE_RE = re.compile(r"^M\d+(?:-\d+)?-(?:tb-amount|tb-|audited|total|subtotal)")

#: 🔴 `wp_code → (item_id 行前缀, provider 模块名)`。
#:
#: 前缀必须与前端 `useM{n}Detail.ts` 里 `debouncedSave('...row-${i}-data')` 的字面量一致；
#: sheet 名与 first_data_row 不写在这里 —— 从 provider 现读（守卫
#: `test_m_form_storage_projection.py::test_registry_matches_provider` 逐值断言）。
#:
#: M2 有两个 sheet（上市 / 非上市），provider 当前只声明非上市
#: （`m201-unlisted-managed`）⇒ 上市前缀登记但会被 provider 查询判为「缺声明」。
FORM_ROW_PREFIXES: dict[str, tuple[str, str]] = {
    "M1": ("M1-M1-2-row-", "phase5_m1_dividends_payable"),
    "M2": ("M2-M2-2-unlisted-row-", "phase5_m2_paid_in_capital"),
    "M3": ("M3-M3-2-row-", "phase5_m3_treasury_stock"),
    "M4": ("M4-2-row-", "phase5_m4_capital_reserve"),
    "M5": ("M5-2-row-", "phase5_m5_surplus_reserve"),
    "M6": ("M6-2-row-", "phase5_m6_retained_earnings"),
    "M7": ("M7-2-row-", "phase5_m7_special_reserve"),
    "M8": ("M8-2-row-", "phase5_m8_general_risk_reserve"),
    "M9": ("M9-2-row-", "phase5_m9_other_comprehensive_income"),
    "M10": ("M10-2-row-", "phase5_m10_other_equity_instruments"),
}

#: M2 上市版前缀（provider 未声明 ⇒ 会走「不支持」分支；登记在此是为了给出**具体原因**
#: 而不是笼统的「字段不存在」）。
_UNSUPPORTED_PREFIXES: dict[str, str] = {
    "M2-M2-2-listed-row-": "M2 上市版明细表在 provider 中未声明（只有 m201-unlisted-managed）",
}


@dataclass(frozen=True)
class ProjectedCell:
    """投影出的一个单元格：`(sheet 名, A1 坐标, 值)`。"""

    sheet: str
    cell: str
    value: Any


def row_prefix_for_wp_code(wp_code: str) -> str | None:
    """该底稿的行前缀（不在登记表里 ⇒ None）。"""
    entry = FORM_ROW_PREFIXES.get(str(wp_code or "").strip().upper())
    return entry[0] if entry else None


def _col_letter(idx: int) -> str:
    """1 → A, 26 → Z, 27 → AA（列号转字母，与 openpyxl 同口径）。"""
    out = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def _to_cell_value(raw: Any) -> Any:
    """保留原始值：数值转 Decimal 便于取值层比较，其余原样（文本格据此展示）。"""
    if raw is None or isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float, Decimal)):
        try:
            return Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return ""
        # 纯数字字符串按数值处理（表单里金额常以字符串存）
        try:
            return Decimal(s.replace(",", ""))
        except (InvalidOperation, ValueError):
            return raw
    return raw


def project_form_rows_to_cells(
    *,
    wp_code: str,
    rows: Sequence[tuple[str, str | None]],
    sheet_name: str,
    first_data_row: int,
    last_data_row: int,
    field_columns: Mapping[str, str],
) -> tuple[list[ProjectedCell], list[str]]:
    """把逐行 JSON 表单行投影成单元格列表。

    Args:
        wp_code: 底稿编码（M1 / M2 …），只用于原因文案。
        rows: `(item_id, remark)` 序列。`remark` 是 JSON 文本。
        sheet_name: 目标 sheet 名（provider `MSheetConfig.sheet_name`）。
        first_data_row: 模板数据区首行（provider `first_data_row`）。
        last_data_row: 模板数据区末行（provider `last_data_row`）。
        field_columns: `json_key → 列字母`（provider `fields`）。

    Returns:
        `(cells, reasons)`。`cells` 是投影成功的格；`reasons` 是中文失败原因
        （**不静默**：解析失败不当 0）。

    🔴 纯函数：零 IO、零副作用、同输入同输出。
    """
    cells: list[ProjectedCell] = []
    reasons: list[str] = []
    prefix = row_prefix_for_wp_code(wp_code)

    for item_id, remark in rows:
        iid = str(item_id or "")
        # 只处理本底稿的逐行数据键
        if prefix and not iid.startswith(prefix):
            # 审定表 / 非行表形态（`M1-1-tb-amount` 等）→ 显式给「暂不支持」
            # 🔴 判据是「本底稿码开头 + 非行表形态」，不能用行前缀截断比较
            #    （`M1-M1-2-row-` 截断成 `M1-M1-2-` 与 `M1-1-tb-amount` 不匹配）
            if iid.startswith(wp_code) and _DETERMINATION_LIKE_RE.match(iid):
                reasons.append(
                    f"{iid}：{REASON_DETERMINATION_NOT_PROJECTED}"
                    f"（审定表等非行表形态暂不支持投影，本 spec 只做明细表逐行 JSON）"
                )
            continue

        m = _ROW_INDEX_RE.search(iid)
        if not m:
            continue
        try:
            i = int(m.group(1))
        except ValueError:
            continue

        row_no = int(first_data_row) + i
        if row_no > int(last_data_row):
            reasons.append(
                f"{iid}：{REASON_ROW_BEYOND_TEMPLATE}"
                f"（第 {i} 行 ⇒ 模板行 {row_no}，超出数据区 {first_data_row}~{last_data_row}）"
            )
            continue

        if not remark or not str(remark).strip():
            # 空行：不产出格（取值层会按 cell_empty 处理，这是现有语义）
            continue

        try:
            payload = json.loads(remark)
        except (json.JSONDecodeError, TypeError) as exc:
            reasons.append(f"{iid}：{REASON_ROW_JSON_INVALID}（{exc}）")
            continue
        if not isinstance(payload, dict):
            reasons.append(
                f"{iid}：{REASON_ROW_JSON_INVALID}（期望 JSON 对象，实际 {type(payload).__name__}）"
            )
            continue

        for key, raw in payload.items():
            col = field_columns.get(str(key))
            if not col:
                # 前端多写的键（如 UI 派生键）—— 记原因但不阻断整行
                reasons.append(
                    f"{iid}：{REASON_FIELD_NOT_IN_PROVIDER}"
                    f"（字段「{key}」不在 provider 声明里，已跳过）"
                )
                continue
            if raw is None:
                continue
            cells.append(
                ProjectedCell(
                    sheet=sheet_name,
                    cell=f"{str(col).strip().upper()}{row_no}",
                    value=_to_cell_value(raw),
                )
            )

    return cells, reasons


# ══════════════════════════════════════════════════════════════════════════
# DB 读取封装（薄；纯函数在上面）
# ══════════════════════════════════════════════════════════════════════════


async def load_form_storage_cells(
    db, wp_id, wp_code: str
) -> tuple[list[ProjectedCell], list[str]]:
    """查 `checklist_responses` + provider 配置，投影成单元格。

    🔴 只读：不写 `parsed_data`、不写任何表。`checklist_responses` 仍是唯一真源。

    返回 `(cells, reasons)`；底稿不在登记表里 ⇒ 返回 `([], [])`（让上层继续走原路径）。
    """
    entry = FORM_ROW_PREFIXES.get(str(wp_code or "").strip().upper())
    if not entry:
        # 🔴 ACNR 可能把 sheet 绑到「sheet 级底稿」（如 M1-2）而不是父底稿（M1）。
        #    sheet 级底稿在 checklist_responses 里通常没有行（数据都在父底稿的 wp_id 下、
        #    item_id 前缀是父底稿的）⇒ 回落到父底稿码，并**换成父底稿的 wp_id** 再查。
        code = str(wp_code or "").strip().upper()
        parent = code.split("-")[0] if "-" in code else ""
        if parent and parent in FORM_ROW_PREFIXES:
            logger.info("M 循环投影：sheet 级底稿 %s 无登记，回落到父底稿 %s", code, parent)
            parent_wp_id = await _parent_wp_id(db, wp_id)
            if parent_wp_id is not None:
                return await load_form_storage_cells(db, parent_wp_id, parent)
        return [], []
    _prefix, module_name = entry

    import sqlalchemy as sa

    # provider 配置（现读，不缓存：provider 改列后立刻生效）
    try:
        mod = importlib.import_module(f"app.services.workpaper_sync.{module_name}")
        sheets = getattr(getattr(mod, "CONFIG", None), "sheets", None) or ()
        if not sheets:
            return [], [f"{wp_code}：provider 没有 MSheetConfig，无法投影"]
        sh = sheets[0]
        field_columns = {str(f.json_key): str(f.column) for f in sh.fields}
        sheet_name = str(sh.sheet_name)
        first_row = int(sh.first_data_row)
        last_row = int(sh.last_data_row)
    except Exception as exc:  # noqa: BLE001 — 配置问题要可见，但不阻断取值
        logger.warning("M 循环投影：读 provider 配置失败 %s: %s", module_name, exc)
        return [], [f"{wp_code}：读 provider 配置失败（{exc}）"]

    # 查表单行（只取本底稿的逐行数据键）
    rows = (
        await db.execute(
            sa.text(
                "SELECT item_id, remark FROM checklist_responses "
                "WHERE wp_id = :wp AND item_id LIKE :pat "
                "ORDER BY item_id"
            ),
            {"wp": wp_id, "pat": f"{_prefix}%"},
        )
    ).all()

    # 审定表等非行表形态也要能报原因 ⇒ 单独查一次（前缀不同）
    det_rows = (
        await db.execute(
            sa.text(
                "SELECT item_id, remark FROM checklist_responses "
                "WHERE wp_id = :wp AND item_id LIKE :pat AND item_id NOT LIKE :rowpat "
                "ORDER BY item_id"
            ),
            {"wp": wp_id, "pat": f"{wp_code}%", "rowpat": f"{_prefix}%"},
        )
    ).all()

    cells, reasons = project_form_rows_to_cells(
        wp_code=wp_code,
        rows=[(str(r[0]), r[1]) for r in rows] + [(str(r[0]), r[1]) for r in det_rows],
        sheet_name=sheet_name,
        first_data_row=first_row,
        last_data_row=last_row,
        field_columns=field_columns,
    )
    return cells, reasons


async def _parent_wp_id(db, sheet_level_wp_id):
    """sheet 级底稿 → 父底稿的 `working_paper.id`（同项目、`wp_code` 是去掉子码的部分）。

    ACNR 的 `bind_wp_code` 在「项目有 sheet 级底稿」时绑 sheet 级（如 `M1-2`），
    但 M 循环的表单数据都挂在父底稿（`M1`）的 `wp_id` 下
    ⇒ 投影必须换回父底稿的 id 才查得到 `checklist_responses`。
    """
    import sqlalchemy as sa

    row = (
        await db.execute(
            sa.text(
                """
                SELECT parent_wp.id
                FROM working_paper cur
                JOIN wp_index cur_idx ON cur_idx.id = cur.wp_index_id
                JOIN wp_index parent_idx
                  ON parent_idx.project_id = cur_idx.project_id
                 AND parent_idx.wp_code = split_part(cur_idx.wp_code, '-', 1)
                JOIN working_paper parent_wp
                  ON parent_wp.wp_index_id = parent_idx.id
                 AND parent_wp.project_id = cur.project_id
                 AND parent_wp.is_deleted = false
                WHERE cur.id = :wp
                LIMIT 1
                """
            ),
            {"wp": sheet_level_wp_id},
        )
    ).first()
    return row[0] if row else None
