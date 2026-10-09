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


# ─── 模板表名 + multi_header + _column_groups 回填 ───────────────────────────


def carry_template_table_names(
    table_data: dict | None,
    source_template: str | None,
    section_number: str | None,
) -> None:
    """按模板位序回填 ``_tables`` 中缺失的业务表名、multi_header、_column_groups（不写库）。"""
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
        tpl_name = str(tpl_tbl.get("name") or "").strip()
        if not tpl_name:
            continue
        current_name = str(tbl.get("name") or "").strip()
        tbl_h0 = str((tbl.get("headers") or [""])[0]).strip() if tbl.get("headers") else ""
        tpl_h0 = str((tpl_tbl.get("headers") or [""])[0]).strip() if tpl_tbl.get("headers") else ""
        if _norm_label(tbl_h0) == _norm_label(tpl_h0) or _norm_label(current_name) == _norm_label(tbl_h0):
            tbl["name"] = tpl_name
        if not tbl.get("multi_header") and tpl_tbl.get("multi_header"):
            tbl["multi_header"] = tpl_tbl["multi_header"]
        if not tbl.get("_column_groups") and tpl_tbl.get("_column_groups"):
            tbl["_column_groups"] = tpl_tbl["_column_groups"]


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
