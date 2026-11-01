"""跨口径转置表：单体把项目写在列、合并写在行（或反之）时的行列互换视图（只读纯函数）。

spec: note-table-structure-formula-pull-closure R14（design §6.6）

**为什么需要**：合并附注的个别数从子企业单体附注拉取，两边模板都按各自权威 Word 排版，
同一张业务表偶有「一边项目作行、另一边项目作列」的写法（如变动表把期间作列 vs 作行）。
这时 ``consol_note_standalone_reader`` 按列语义键认列必然一列都对不上，整表拉不到数、
且原因只报「金额列与合并表一列都没对上」，用户无从下手。

**启用条件极严（宁漏不误判）**：必须同时满足
  ① 合并表的数据列名（除标签列）全部出现在单体表的**行名**里；
  ② 合并表的行名全部出现在单体表的**列名**里；
  ③ 两侧参与比对的名字各 ≥2 个（1×N 表的名字巧合率太高）；
  ④ 合并列名与单体列名无交集、合并行名与单体行名无交集 —— 转置的本质是**角色对调**，
     名字还留在原来的维度上就说明两边本来同口径。
🔴 ①②都要求「非空且全部命中」—— 空集天然满足「⊆」，不设非空门槛就会对任何表返回 True。
🔴 ④ 是真库扫出来的（2026-11-01，10808 对比较命中 1 对、且是假阳）：五、28「商誉减值测试
关键假设」的行名与列名**恰好是同一组参数**（毛利率 / 增长率 / 折现率，列头 `资产组/业务`
本该填实际资产组名），①②同时满足但两边其实是同一口径，转置会把数据转错位。

**只在正常读取失败后重试**（见 ``consol_note_standalone_reader.read_source_table``）：
不把转置视图预先加进选表候选，否则候选集翻倍会干扰既有选表打分，把本来认对的表挤掉。
"""
from __future__ import annotations

from typing import Any

from app.services.note_table_header_library import column_paths, norm

__all__ = ["transpose_view", "looks_transposed", "MIN_NAMES"]

# 参与比对的名字下限：1×N 表只有一个名字，巧合命中率太高（① ② 都按此门槛）
MIN_NAMES = 2

_SKIP_ROW_TYPES = frozenset({
    "expandable", "dynamic_anchor", "dynamic_marker_end",
    "header", "header_label", "title", "section_header",
})


def _row_label(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("label") or "").strip()
    if isinstance(row, (list, tuple)) and row:
        return str(row[0] or "").strip()
    return ""


def _row_cells(row: Any) -> list[Any]:
    """行的数据单元格（不含行名列），与 ``note_table_header_match.row_values`` 同口径。"""
    if isinstance(row, dict):
        values = row.get("values")
        if isinstance(values, list):
            return list(values)
        cells = row.get("cells")
        if isinstance(cells, list):
            return list(cells)
        return []
    if isinstance(row, (list, tuple)):
        return list(row[1:])
    return []


def _data_rows(table: Any) -> list[Any]:
    """表体数据行（剔除占位 / 表头类行；合计行保留——转置后它成为一列，仍可能被认到）。"""
    if not isinstance(table, dict):
        return []
    out: list[Any] = []
    for r in table.get("rows") or []:
        if isinstance(r, dict) and str(r.get("row_type") or "").strip() in _SKIP_ROW_TYPES:
            continue
        if not _row_label(r):
            continue
        out.append(r)
    return out


def _leaf_column_names(table: Any) -> list[str]:
    """数据列名（除标签列），取表头路径最末一段；多级表头下是叶子列名。"""
    paths = column_paths(table if isinstance(table, dict) else None)
    return [p[-1] if p else "" for p in paths[1:]]


def looks_transposed(consol_table: Any, standalone_table: Any) -> bool:
    """单体表相对合并表是否行列互换（见模块注释的三条启用条件）。"""
    if not isinstance(consol_table, dict) or not isinstance(standalone_table, dict):
        return False

    consol_cols = [norm(n) for n in _leaf_column_names(consol_table) if norm(n)]
    consol_rows = [norm(_row_label(r)) for r in _data_rows(consol_table)]
    consol_rows = [n for n in consol_rows if n]
    sa_cols = {norm(n) for n in _leaf_column_names(standalone_table) if norm(n)}
    sa_rows = {norm(_row_label(r)) for r in _data_rows(standalone_table) if norm(_row_label(r))}

    # 🔴 非空门槛：空集满足任何「⊆」，缺这一步判据对任何表恒 True
    if len(consol_cols) < MIN_NAMES or len(consol_rows) < MIN_NAMES:
        return False
    if len(sa_cols) < MIN_NAMES or len(sa_rows) < MIN_NAMES:
        return False

    # ④ 角色必须真的对调：名字还留在原维度上（行名对行名 / 列名对列名）⇒ 两边本来同口径
    if sa_cols & set(consol_cols) or sa_rows & set(consol_rows):
        return False

    # ① 合并的数据列名都在单体行名里；② 合并的行名都在单体列名里
    return all(c in sa_rows for c in consol_cols) and all(r in sa_cols for r in consol_rows)


def transpose_view(table: Any, *, label_header: str | None = None) -> dict[str, Any] | None:
    """行列互换视图：原表每个数据列成为一行，原表每个数据行成为一列。

    返回 ``{name, headers, rows}``（``rows`` 为 ``{label, values}`` 形态，与读取层一致）；
    行或列不足 1 个时返回 None。``_column_groups`` / ``multi_header`` 一律不带出——转置后
    原分组语义不成立，留着会让认列按错的父表头比对。
    """
    if not isinstance(table, dict):
        return None
    rows = _data_rows(table)
    col_names = _leaf_column_names(table)
    if not rows or not col_names:
        return None

    original_label_header = ""
    paths = column_paths(table)
    if paths and paths[0]:
        original_label_header = paths[0][-1]

    out_rows: list[dict[str, Any]] = []
    for c, name in enumerate(col_names):
        values: list[Any] = []
        for r in rows:
            cells = _row_cells(r)
            values.append(cells[c] if c < len(cells) else None)
        out_rows.append({"label": str(name).strip(), "row_type": "data", "values": values})

    return {
        "name": table.get("name"),
        # 标签列列头：调用方指定（通常取合并表的 headers[0]）→ 原表标签列列头 → 空
        "headers": [label_header if label_header is not None else original_label_header,
                    *[_row_label(r) for r in rows]],
        "rows": out_rows,
        "_transposed": True,
    }
