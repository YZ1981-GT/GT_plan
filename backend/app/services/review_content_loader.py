"""底稿复核内容加载（内部调用，不经 HTTP）

从 checklist_responses + working_paper.parsed_data 组装 LLM 输入文本，
替代自调 localhost render-config 的脆弱路径。
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.core.database import async_session

logger = logging.getLogger(__name__)

_MAX_RESPONSES_CHARS = 8000
_MAX_PARSED_CHARS = 4000


async def load_workpaper_review_content(
    wp_id: str | UUID,
    sheet_name: str | None = None,
) -> str:
    """加载底稿复核用文本内容

    优先 checklist_responses（实时填写数据），辅以 parsed_data 中的
    html_data / tb_values。失败时返回可读占位，不抛异常。
    """
    wp_id_str = str(wp_id)
    parts: list[str] = []

    try:
        async with async_session() as db:
            # 1. checklist_responses
            rows = (
                await db.execute(
                    text(
                        "SELECT item_id, conclusion, remark, wp_ref "
                        "FROM checklist_responses "
                        "WHERE wp_id = :wp_id "
                        "ORDER BY item_id"
                    ),
                    {"wp_id": wp_id_str},
                )
            ).fetchall()

            if rows:
                items = _filter_and_format_responses(rows, sheet_name)
                if items:
                    text_repr = json.dumps(items, ensure_ascii=False, indent=None)
                    if len(text_repr) > _MAX_RESPONSES_CHARS:
                        text_repr = text_repr[:_MAX_RESPONSES_CHARS] + "...(已截断)"
                    parts.append(f"[checklist_responses]\n{text_repr}")

            # 2. working_paper.parsed_data（可能含 html_data / tb）
            parsed_row = (
                await db.execute(
                    text(
                        "SELECT parsed_data FROM working_paper "
                        "WHERE id = :wp_id AND is_deleted = false"
                    ),
                    {"wp_id": wp_id_str},
                )
            ).first()

            if parsed_row and parsed_row[0]:
                parsed = parsed_row[0]
                if isinstance(parsed, str):
                    try:
                        parsed = json.loads(parsed)
                    except json.JSONDecodeError:
                        parsed = {}
                if isinstance(parsed, dict):
                    html_part = _extract_from_parsed(parsed, sheet_name)
                    if html_part:
                        parts.append(html_part)

    except Exception as e:
        logger.warning("load_workpaper_review_content failed for %s: %s", wp_id_str, e)
        return "(底稿内容获取异常)"

    if not parts:
        return "(底稿无内容或尚未填写)"

    return "\n\n".join(parts)


def _filter_and_format_responses(
    rows: list[Any],
    sheet_name: str | None,
) -> list[dict[str, Any]]:
    """按 sheet_name 前缀过滤 item，输出精简 dict 列表"""
    suffix = _guess_item_prefix(sheet_name) if sheet_name else None
    items: list[dict[str, Any]] = []

    for row in rows:
        item_id = row[0] or ""
        if suffix and not (
            item_id.startswith(suffix)
            or suffix in item_id
            or item_id.startswith(suffix.replace("-", ""))
        ):
            # 无前缀匹配时仍保留通用项（无 sheet 编码的说明/结论）
            if "-" in item_id and any(c.isdigit() for c in item_id):
                continue

        entry: dict[str, Any] = {"item_id": item_id}
        if row[1] is not None:
            entry["conclusion"] = row[1]
        if row[2]:
            remark = row[2]
            if isinstance(remark, str) and len(remark) > 500:
                remark = remark[:500] + "..."
            entry["remark"] = remark
        if row[3]:
            entry["wp_ref"] = row[3]
        items.append(entry)

    # 若过滤后为空，回退到全部（避免误杀）
    if sheet_name and not items and rows:
        return _filter_and_format_responses(rows, None)

    return items


def _guess_item_prefix(sheet_name: str) -> str | None:
    """从 sheet_name 猜测 checklist item_id 前缀，如 '审定表D2-1' → 'D2-1'"""
    import re

    m = re.search(r"([A-Z]\d+(?:-\d+|-[a-z]+(?:-[a-z]+)*))", sheet_name, re.IGNORECASE)
    if m:
        return m.group(1)
    if "截止" in sheet_name:
        return "D2-cutoff"
    if "附注上市" in sheet_name:
        return "D2-note-listed"
    if "附注国企" in sheet_name:
        return "D2-note-soe"
    return None


def _extract_from_parsed(parsed: dict, sheet_name: str | None) -> str | None:
    """从 parsed_data 提取可读片段"""
    parts: list[str] = []

    html_data = parsed.get("html_data")
    if isinstance(html_data, dict):
        # 多 sheet 结构: { "审定表D2-1": {...}, ... }
        target: dict | None = None
        if sheet_name:
            for key, val in html_data.items():
                if not isinstance(val, dict):
                    continue
                key_str = str(key)
                if sheet_name in key_str or key_str in sheet_name:
                    target = val
                    break
            if target is None:
                # 也可能是扁平 html_data（无按 sheet 分桶）
                target = html_data if any(
                    k in html_data for k in ("responses_snapshot", "tb_values", "allResponses")
                ) else None
        else:
            # 取第一个 dict 值或扁平结构
            for val in html_data.values():
                if isinstance(val, dict):
                    target = val
                    break
            if target is None and any(
                k in html_data for k in ("responses_snapshot", "tb_values", "allResponses")
            ):
                target = html_data

        if target:
            for key in ("responses_snapshot", "allResponses", "tb_values"):
                val = target.get(key)
                if val and isinstance(val, (dict, list)):
                    text_repr = json.dumps(val, ensure_ascii=False, indent=None)
                    if len(text_repr) > _MAX_PARSED_CHARS:
                        text_repr = text_repr[:_MAX_PARSED_CHARS] + "...(已截断)"
                    parts.append(f"[{key}]\n{text_repr}")

    # 顶层 tb_values
    tb = parsed.get("tb_values")
    if tb and isinstance(tb, dict) and not any("[tb_values]" in p for p in parts):
        tb_text = json.dumps(tb, ensure_ascii=False, indent=None)
        if len(tb_text) > 2000:
            tb_text = tb_text[:2000] + "...(已截断)"
        parts.append(f"[试算表数据]\n{tb_text}")

    return "\n\n".join(parts) if parts else None
