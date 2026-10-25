"""单体附注 table_data 读时增强（不写库）。

对齐合并附注 ``consol_note_sections.py`` 的 ``_ensure_columns`` / ``_ensure_row_types`` /
``multi_header_to_column_groups`` 增强逻辑，同时回填模板业务表名和 ``_column_groups``。

所有函数只修改传入的 dict 引用，不做数据库操作。

spec: P2 单体附注渲染对齐
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_WS_NORM = re.compile(r"[\s\u3000]+")
_TOTAL_RE = re.compile(r"^(合\s*计|小\s*计)$")


def _norm_label(s: str) -> str:
    return _WS_NORM.sub("", str(s or "").strip())


# ─── 模板表索引（按 section_number 缓存） ────────────────────────────────────


@lru_cache(maxsize=16)
def _load_template_tables_index(
    template_type: str, mtime: float,
) -> dict[str, list[dict]]:
    """``{section_number: [table_dict, ...]}``，带 mtime 缓存。"""
    path = _DATA_DIR / f"note_template_{template_type}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    index: dict[str, list[dict]] = {}
    for sec in data.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        num = str(sec.get("section_number") or "").strip()
        tables = sec.get("tables")
        if num and isinstance(tables, list):
            index[num] = tables
    return index


# ─── 模板结构回填（表名 + headers + values + multi_header + _column_groups）─


def _align_table_to_template(tbl: dict, tpl_tbl: dict) -> None:
    """把单个 _tables 项对齐到模板结构（不写库，只改内存中的 dict）。

    回填内容：name / headers / multi_header / _column_groups。
    当模板列数 > 数据列数时，同时扩展 rows[].values / _cell_meta / _cell_modes。
    """
    tpl_name = str(tpl_tbl.get("name") or "").strip()
    tpl_headers: list[str] = tpl_tbl.get("headers") or []
    tpl_h0 = str(tpl_headers[0]).strip() if tpl_headers else ""

    data_headers: list[str] = tbl.get("headers") or []
    data_h0 = str(data_headers[0]).strip() if data_headers else ""
    current_name = str(tbl.get("name") or "").strip()

    # 交叉校验：首列标签去空白后一致（或互为前缀），才认为是同一张表
    norm_dh0 = _norm_label(data_h0)
    norm_th0 = _norm_label(tpl_h0)
    norm_name = _norm_label(current_name)
    h0_match = (norm_dh0 == norm_th0
                or norm_name == norm_dh0
                or (norm_dh0 and norm_th0 and (norm_dh0.startswith(norm_th0) or norm_th0.startswith(norm_dh0))))
    if not h0_match:
        return

    # 1. 回填表名
    if tpl_name:
        tbl["name"] = tpl_name

    # 2. 回填 headers（模板列数 ≥ 数据列数时替换）
    tpl_col_count = len(tpl_headers)
    data_col_count = len(data_headers)
    if tpl_col_count > 0 and tpl_col_count >= data_col_count:
        tbl["headers"] = list(tpl_headers)  # 拷贝
        # 扩展 rows 中的 values 到模板列数
        tpl_value_count = tpl_col_count - 1  # headers[0] 是标签列
        _expand_rows_values(tbl, tpl_value_count)

    # 3. 回填 multi_header / _column_groups
    if not tbl.get("multi_header") and tpl_tbl.get("multi_header"):
        tbl["multi_header"] = tpl_tbl["multi_header"]
    if not tbl.get("_column_groups") and tpl_tbl.get("_column_groups"):
        tbl["_column_groups"] = tpl_tbl["_column_groups"]


def _expand_rows_values(tbl: dict, target_value_count: int) -> None:
    """把 rows 中每行的 values 扩展到 target_value_count（不足补 None）。

    同时扩展 _cell_meta 和 _cell_modes sidecar（键是 "0","1",... 字符串索引）。
    """
    rows = tbl.get("rows")
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        values = row.get("values")
        if isinstance(values, list):
            while len(values) < target_value_count:
                values.append(None)
        # _cell_meta / _cell_modes 不需要扩展——缺键时前端按空处理


def carry_template_table_names(
    table_data: dict | None,
    source_template: str | None,
    section_number: str | None,
) -> None:
    """按模板位序回填 ``_tables`` 的完整结构（不写库）。

    回填：表名 / headers / multi_header / _column_groups / rows.values 扩展。
    只在 headers[0] 交叉校验通过时才操作（防止位序错位导致串表）。
    """
    if not table_data or not isinstance(table_data, dict):
        return
    tables = table_data.get("_tables")
    if not tables or not isinstance(tables, list):
        return
    if not section_number:
        return

    from app.services.note_table_guidance import resolve_template_type

    tt = resolve_template_type(source_template, section_number) or source_template or "soe"
    path = _DATA_DIR / f"note_template_{tt}.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return
    tpl_tables = _load_template_tables_index(tt, mtime).get(
        str(section_number).strip(), []
    )
    if not tpl_tables:
        return

    for i, tbl in enumerate(tables):
        if not isinstance(tbl, dict) or i >= len(tpl_tables):
            continue
        tpl_tbl = tpl_tables[i]
        if not isinstance(tpl_tbl, dict):
            continue
        _align_table_to_template(tbl, tpl_tbl)


# ─── dict 格式 rows 的 _row_types 推导 ──────────────────────────────────────


def infer_row_types_from_dict_rows(section: dict) -> None:
    """从字典格式 rows（单体附注）推导 ``_row_types``，覆盖 ``_ensure_row_types`` 对 dict rows 全标 data 的结果。"""
    rows = section.get("rows")
    if not isinstance(rows, list) or not rows:
        return
    if not isinstance(rows[0], dict):
        return
    row_types: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            row_types.append("data")
            continue
        rt = row.get("row_type")
        if rt in ("total", "subtotal", "header"):
            row_types.append(rt)
        elif row.get("is_total"):
            row_types.append("total")
        else:
            label = re.sub(r"[\s\u3000]+", "", str(row.get("label") or ""))
            if _TOTAL_RE.match(label):
                row_types.append("total" if "合" in label else "subtotal")
            else:
                row_types.append("data")
    section["_row_types"] = row_types


# ─── 顶层入口：一次性增强整个 table_data ─────────────────────────────────────


def enrich_note_table_data(
    table_data: dict | None,
    source_template: str | None,
    section_number: str | None,
) -> None:
    """对单体附注 detail 端点返回的 ``table_data`` 做全量读时增强。

    顺序：模板回填 → _column_groups → _ensure_columns → _ensure_row_types → dict row_types。
    """
    if not table_data or not isinstance(table_data, dict):
        return

    # 1. 模板表名 + multi_header + _column_groups 回填
    try:
        carry_template_table_names(table_data, source_template, section_number)
    except Exception:
        logger.warning("note_table_enrichment: carry_template_table_names failed section=%s", section_number, exc_info=True)

    # 2. _column_groups / _row_types 增强
    try:
        from app.services.consol_note_formula_service import (
            multi_header_to_column_groups,
            _ensure_columns,
            _ensure_row_types,
        )

        tables = table_data.get("_tables") or []
        for tbl in tables:
            if not isinstance(tbl, dict):
                continue
            if not tbl.get("_column_groups"):
                mh = tbl.get("multi_header")
                if mh:
                    groups = multi_header_to_column_groups(mh)
                    if groups:
                        tbl["_column_groups"] = groups
            _ensure_columns(tbl)
            _ensure_row_types(tbl)
            infer_row_types_from_dict_rows(tbl)

        # 旧格式单表
        if not tables and table_data.get("rows"):
            if not table_data.get("_column_groups"):
                mh = table_data.get("multi_header")
                if mh:
                    groups = multi_header_to_column_groups(mh)
                    if groups:
                        table_data["_column_groups"] = groups
            _ensure_columns(table_data)
            _ensure_row_types(table_data)
            infer_row_types_from_dict_rows(table_data)
    except Exception:
        logger.warning("note_table_enrichment: column_groups/row_types failed section=%s", section_number, exc_info=True)
