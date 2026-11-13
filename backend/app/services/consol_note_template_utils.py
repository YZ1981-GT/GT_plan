"""合并附注模板表结构工具：多级表头 → 列分组、列元数据、行类型（含表内嵌子表头）、保存时合计回填。

按 ``file_size_whitelist.txt`` 登记的拆分方向从 ``consol_note_formula_service.py`` 原样抽出（2026-11-04）；
那边以原名导入，既有引用不变。都是纯函数，不读库。
"""
from __future__ import annotations

from typing import Any


def multi_header_to_column_groups(
    multi_header: list[list[str]] | None,
) -> list[dict] | None:
    """从 multi_header 推导 _column_groups（与单体附注模板同格式）。

    算法：第一行的非空连续区间 = 一个分组（空字符串表示被同组合并）。
    第一列（标签列）跳过。包含 span=1 的分组（与单体附注模板一致）。
    无 multi_header 或只有一行 ⇒ 返回 None。

    >>> multi_header_to_column_groups([
    ...     ["账  龄", "期末数", "", "期初数", ""],
    ...     ["", "账面余额", "坏账准备", "账面余额", "坏账准备"],
    ... ])
    [{'group': '期末数', 'start': 1, 'span': 2}, {'group': '期初数', 'start': 3, 'span': 2}]
    """
    if not multi_header or len(multi_header) < 2:
        return None
    row0 = multi_header[0]
    groups: list[dict] = []
    i = 1  # 跳过标签列（col 0）
    while i < len(row0):
        text = (row0[i] or "").strip()
        if text:
            span = 1
            while i + span < len(row0) and not (row0[i + span] or "").strip():
                span += 1
            groups.append({"group": text, "start": i, "span": span})
            i += span
        else:
            i += 1
    return groups if groups else None


def _infer_row_type(label: str) -> str:
    """从行首列文本推导 row_type（data/total/subtotal）。

    与单体 / 来源行同一口径（``note_total_terms.label_row_type``）：以「小计」结尾 = subtotal（先判；旧正则把「小计」
    当合计 ⇒ 多段小计全按合计加总）、「合计」「总计」= total。
    """
    from app.services.note_total_terms import label_row_type

    return label_row_type(label)


def _ensure_columns(section: dict) -> None:
    """自动从 headers 生成 columns 列元数据（如果缺失）。"""
    if section.get("columns"):
        return
    headers = section.get("headers")
    if not isinstance(headers, list) or not headers:
        return
    cols = []
    for i, h in enumerate(headers):
        col: dict = {"key": h, "label": h}
        if i == 0:
            col["is_label"] = True
            col["flat"] = True
        cols.append(col)
    section["columns"] = cols


def _is_embedded_header_row(row: list, headers: list) -> bool:
    """检测 rows 中的一行是否是嵌入的子表头（而非数据行）。

    判据：row[0] 与 headers[0] 文字相同（去空白和 HTML 标签后），
    说明 rows 把 headers 列名重复了一遍作为子表头行。
    """
    if not isinstance(row, list) or not row or not headers:
        return False
    import re

    def clean(s: Any) -> str:
        return re.sub(r"<br\s*/?>", "", re.sub(r"[\s\u3000]+", "", str(s or "")))

    return clean(row[0]) == clean(headers[0]) and bool(clean(row[0]))


def _ensure_row_types(section: dict) -> None:
    """自动为 rows 中的每一行推导 _row_type（不改原数组结构，附加到 section）。

    CP-04 扩展：检测 rows 前几行是否是嵌入的子表头（合并附注模板的常见形态），
    标注为 ``header`` 类型，同时记录 ``_header_row_indexes`` 供前端分离渲染。
    """
    rows = section.get("rows")
    if not isinstance(rows, list) or not rows:
        return
    # 如果已有 _row_types 则不覆盖
    if section.get("_row_types"):
        return
    headers = section.get("headers", [])
    row_types = []
    header_row_indexes = []
    for i, row in enumerate(rows):
        if isinstance(row, list) and row:
            # 只检查前 3 行，且必须从第 0 行连续开始
            if i <= 2 and i == len(header_row_indexes) and _is_embedded_header_row(row, headers):
                row_types.append("header")
                header_row_indexes.append(i)
            else:
                row_types.append(_infer_row_type(str(row[0])))
        else:
            row_types.append("data")
    section["_row_types"] = row_types
    if header_row_indexes:
        section["_header_row_indexes"] = header_row_indexes


def _safe_float(val: Any) -> float | None:
    """安全转 float，空串/非数字返 None。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "").replace("，", "")
    if not s:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def backfill_total_rows(
    rows: list[list],
    row_types: list[str] | None = None,
) -> bool:
    """保存时合计 / 小计空格回填：按合计构成（``note_total_terms``，与单体 / 拉数 / 汇总同一判定）只填判得准的合计行，
    已有值的单元格不覆盖；构成里的格全空不填。

    row_types 与 rows 等长，标识每行类型（未提供时从行首列文本推导）。返回是否有值被回填。旧算法「向上到上一个
    合计 / 小计为止」把「小计 / 减：坏账准备 / 合计」的合计填成坏账准备、在「其中：」表上重复加明细。
    """
    from decimal import Decimal

    from app.services.note_total_terms import sum_terms, total_order, total_terms

    if not rows:
        return False
    if not row_types:
        row_types = [_infer_row_type(str(r[0]) if r else "") for r in rows]
    shaped = [
        {"label": str(r[0]) if isinstance(r, (list, tuple)) and r else "",
         "row_type": row_types[i] if i < len(row_types) else "data"}
        for i, r in enumerate(rows)
    ]
    plans, _reasons = total_terms(shaped)

    def cell(j: int, ci: int) -> Decimal | None:
        dr = rows[j] if 0 <= j < len(rows) else None
        v = _safe_float(dr[ci]) if isinstance(dr, (list, tuple)) and ci < len(dr) else None
        return Decimal(str(v)) if v is not None else None

    changed = False
    for ri in total_order(shaped, plans):
        row = rows[ri]
        if not isinstance(row, list):
            continue
        for ci in range(1, len(row)):
            if _safe_float(row[ci]) is not None:
                continue  # 已有值，不覆盖
            total = sum_terms(plans[ri], lambda j, ci=ci: cell(j, ci))
            if total is None:
                continue
            row[ci] = str(int(total)) if total == total.to_integral_value() else str(total.normalize())
            changed = True
    return changed
