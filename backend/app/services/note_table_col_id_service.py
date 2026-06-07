"""附注表格/列 ID 服务

提供运行时 table_id / col_id 生成与解析，确保：
- 缺失 table_id 的表生成稳定标识（基于表名 slugify 或位置）
- 缺失 col_id 的列生成稳定标识（基于列头 slugify 或位置）
- 已有 ID 不覆盖（幂等）
- 公式/来源面板优先读取 col_id，缺失回退列下标

Validates: Requirements 3.1, 3.3
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slugify 工具（与 generate_note_semantic_sidecars.py 逻辑一致）
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """将中文/英文文本转为稳定 slug。

    规则：
    1. 去除 HTML 标签
    2. 空格和常用标点转下划线
    3. ASCII 字母数字和下划线保留；中文字符保留
    4. 连续下划线归一化
    5. 去除首尾下划线
    """
    # 去除 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    # 替换空格和常用标点为下划线
    text = re.sub(r"[\s（）()【】\[\]、，。：；""'']+", "_", text)
    # 保留 ASCII 字母数字和下划线，中文字符保留
    cleaned: list[str] = []
    for ch in text:
        if ch == "_":
            cleaned.append("_")
        elif ch.isascii() and (ch.isalnum() or ch == "_"):
            cleaned.append(ch.lower())
        elif unicodedata.category(ch).startswith("L"):
            cleaned.append(ch)
        else:
            cleaned.append("_")
    slug = "".join(cleaned)
    # 连续下划线归一化
    slug = re.sub(r"_+", "_", slug)
    slug = slug.strip("_")
    return slug


def _make_unique(slug: str, existing: set[str]) -> str:
    """确保 slug 在 existing 集合中唯一，重复时追加序号。"""
    if slug not in existing:
        existing.add(slug)
        return slug
    idx = 2
    while f"{slug}_{idx}" in existing:
        idx += 1
    unique = f"{slug}_{idx}"
    existing.add(unique)
    return unique


# ---------------------------------------------------------------------------
# 4.1 ensure_table_ids
# ---------------------------------------------------------------------------


def ensure_table_ids(table_data: dict[str, Any]) -> dict[str, Any]:
    """为 table_data._tables 中缺失 table_id 的表生成稳定 table_id。

    生成规则：
    - slugify(table.name) → 若为空则 table_{idx} → 确保唯一

    幂等：已有 table_id 的表不改变。
    不修改原始入参，返回新字典。

    Args:
        table_data: disclosure_note.table_data 字典

    Returns:
        带稳定 table_id 的 table_data 副本
    """
    if not isinstance(table_data, dict):
        return {}

    result = dict(table_data)
    tables = table_data.get("_tables")
    if not isinstance(tables, list) or not tables:
        return result

    existing_ids: set[str] = set()
    # 先收集已有的 table_id
    for tbl in tables:
        if isinstance(tbl, dict):
            tid = tbl.get("table_id")
            if isinstance(tid, str) and tid.strip():
                existing_ids.add(tid.strip())

    enriched_tables: list[Any] = []
    for idx, tbl in enumerate(tables):
        if not isinstance(tbl, dict):
            enriched_tables.append(tbl)
            continue
        enriched_tbl = dict(tbl)
        tid = tbl.get("table_id")
        if not (isinstance(tid, str) and tid.strip()):
            # 需要生成
            name = tbl.get("name", "")
            if isinstance(name, str) and name.strip():
                slug = _slugify(name.strip())
            else:
                slug = ""
            if not slug:
                slug = f"table_{idx}"
            enriched_tbl["table_id"] = _make_unique(slug, existing_ids)
        enriched_tables.append(enriched_tbl)

    result["_tables"] = enriched_tables
    return result


# ---------------------------------------------------------------------------
# 4.2 ensure_column_ids
# ---------------------------------------------------------------------------


def ensure_column_ids(table_data: dict[str, Any]) -> dict[str, Any]:
    """为 table_data._tables 中缺失 col_id 的列生成稳定 col_id。

    优先从 columns[] 读取，若 columns 不存在则从 headers[] 构建。

    生成规则：
    - slugify(header_text) → 若为空则 col_{idx} → 确保唯一

    幂等：已有 col_id 的列不改变。
    不修改原始入参，返回新字典。

    Args:
        table_data: disclosure_note.table_data 字典

    Returns:
        带稳定 col_id 的 table_data 副本
    """
    if not isinstance(table_data, dict):
        return {}

    result = dict(table_data)
    tables = table_data.get("_tables")
    if not isinstance(tables, list) or not tables:
        return result

    enriched_tables: list[Any] = []
    for tbl in tables:
        if not isinstance(tbl, dict):
            enriched_tables.append(tbl)
            continue
        enriched_tbl = dict(tbl)

        columns = tbl.get("columns")
        headers = tbl.get("headers")

        if isinstance(columns, list) and columns:
            # 已有 columns 结构，补全缺失的 col_id
            existing_col_ids: set[str] = set()
            # 先收集已有 col_id
            for col in columns:
                if isinstance(col, dict):
                    cid = col.get("col_id")
                    if isinstance(cid, str) and cid.strip():
                        existing_col_ids.add(cid.strip())

            enriched_cols: list[Any] = []
            for c_idx, col in enumerate(columns):
                if not isinstance(col, dict):
                    enriched_cols.append(col)
                    continue
                enriched_col = dict(col)
                cid = col.get("col_id")
                if not (isinstance(cid, str) and cid.strip()):
                    label = col.get("label", "")
                    if isinstance(label, str) and label.strip():
                        slug = _slugify(label.strip())
                    else:
                        slug = ""
                    if not slug:
                        slug = f"col_{c_idx}"
                    enriched_col["col_id"] = _make_unique(slug, existing_col_ids)
                enriched_cols.append(enriched_col)
            enriched_tbl["columns"] = enriched_cols

        elif isinstance(headers, list) and headers:
            # 从 headers 构建 columns
            existing_col_ids = set()
            new_columns: list[dict[str, str]] = []
            for c_idx, header in enumerate(headers):
                header_text = header if isinstance(header, str) else str(header)
                label = re.sub(r"<[^>]+>", "", header_text).strip()
                slug = _slugify(header_text)
                if not slug:
                    slug = f"col_{c_idx}"
                col_id = _make_unique(slug, existing_col_ids)
                new_columns.append({"col_id": col_id, "label": label})
            enriched_tbl["columns"] = new_columns

        enriched_tables.append(enriched_tbl)

    result["_tables"] = enriched_tables
    return result


# ---------------------------------------------------------------------------
# 4.3 resolve_col_reference
# ---------------------------------------------------------------------------


def resolve_col_reference(table: dict[str, Any], col_ref: str | int) -> int:
    """解析列引用为列下标。

    - col_ref 为 int：直接作为列下标
    - col_ref 为 str (col_id)：在 table.columns 中查找匹配的 col_id，返回下标
    - 找不到时 log warning 并回退为 0

    Args:
        table: 单张表字典，含 columns[] 数组
        col_ref: col_id 字符串或列下标整数

    Returns:
        列下标 (0-based)
    """
    if isinstance(col_ref, int):
        return col_ref

    if not isinstance(col_ref, str):
        logger.warning(
            "resolve_col_reference: col_ref 类型不合法 (%s)，回退为 0",
            type(col_ref).__name__,
        )
        return 0

    columns = table.get("columns")
    if isinstance(columns, list):
        for idx, col in enumerate(columns):
            if isinstance(col, dict) and col.get("col_id") == col_ref:
                return idx

    logger.warning(
        "resolve_col_reference: col_id '%s' 未找到，回退为 0",
        col_ref,
    )
    return 0
