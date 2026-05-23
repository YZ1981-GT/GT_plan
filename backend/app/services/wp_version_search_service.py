"""底稿历史版本搜索服务

proposal-remaining-18 task 5.4 (S-4)：版本对比页面增加搜索框，支持在历史版本
parsed_data 中搜索特定值。

设计要点：
- 搜索范围 = ``working_paper_snapshots`` 表中的 ``snapshot_data.formula_values`` /
  ``snapshot_data.audited_amounts`` 两个字典；以及当前活跃版本（``working_paper.parsed_data.cells``）。
- key 形如 ``"Sheet1!A1"``（snapshot 序列化结构）或 ``{sheet}!{cell_ref}`` 字符串
  （parsed_data.cells 顶层 dict key 同结构，详见 prefill_engine._resolve_wp_formula）。
- 模糊匹配 cell.v 字段（数字/字符串），不区分大小写。
- 结果列表含：``version_id`` / ``trigger_event`` / ``sheet`` / ``cell_ref`` /
  ``value`` / ``snapshot_at``，前端可点击跳转。

为便于单测，``search_in_snapshot_data`` 与 ``search_in_parsed_data`` 设计为纯函数，
不依赖 DB / ORM；DB 访问在 ``search_versions`` 中编排。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# 纯函数：单条 cells/快照字典搜索
# ---------------------------------------------------------------------------


def _split_cell_key(key: str) -> tuple[str, str]:
    """拆分 ``"Sheet1!A1"`` → ``("Sheet1", "A1")``；不含 ``!`` 则 sheet 留空。"""
    if "!" in key:
        sheet, cell_ref = key.split("!", 1)
        return sheet, cell_ref
    return "", key


def _value_matches(value: Any, keyword: str) -> bool:
    """模糊匹配单元格值

    数字 / 字符串均按字符串包含判断，不区分大小写。``None``/空字符串视为未命中。
    """
    if value is None:
        return False
    text = str(value)
    if not text:
        return False
    return keyword.lower() in text.lower()


def search_in_snapshot_data(
    snapshot_data: dict[str, Any] | None,
    keyword: str,
    *,
    max_results: int = 200,
) -> list[dict[str, Any]]:
    """在单个快照的 ``snapshot_data`` 中搜索关键字

    snapshot_data 结构（``WpSnapshotService.create_snapshot``）::

        {
            "formula_values": {"Sheet1!A1": "100", ...},
            "audited_amounts": {"1001": 12345.6, ...},
            "captured_at": "...",
        }

    返回逐条命中结果（不含 version_id / snapshot_at，由调用方补齐）。
    """
    if not snapshot_data or not keyword:
        return []

    hits: list[dict[str, Any]] = []

    # 1) formula_values：key 形如 "Sheet1!A1"
    formulas = snapshot_data.get("formula_values") or {}
    if isinstance(formulas, dict):
        for key, value in formulas.items():
            if len(hits) >= max_results:
                return hits
            if _value_matches(value, keyword):
                sheet, cell_ref = _split_cell_key(str(key))
                hits.append(
                    {
                        "field": "formula_value",
                        "sheet": sheet,
                        "cell_ref": cell_ref,
                        "value": value,
                    }
                )

    # 2) audited_amounts：key 通常是 account_code（无 sheet 前缀）
    audited = snapshot_data.get("audited_amounts") or {}
    if isinstance(audited, dict):
        for key, value in audited.items():
            if len(hits) >= max_results:
                return hits
            if _value_matches(value, keyword):
                hits.append(
                    {
                        "field": "audited_amount",
                        "sheet": "",
                        "cell_ref": str(key),
                        "value": value,
                    }
                )

    return hits


def search_in_parsed_data(
    parsed_data: dict[str, Any] | None,
    keyword: str,
    *,
    max_results: int = 200,
) -> list[dict[str, Any]]:
    """在 ``working_paper.parsed_data.cells`` 中搜索关键字

    parsed_data.cells 结构有两种常见形态：

    1. 顶层 dict，key 形如 ``"Sheet1!A1"``，value 为标量或 ``{"v": ..., "f": ...}``。
       （prefill_engine 写回结构）
    2. 顶层 dict，key 形如 ``"Sheet1"``，value 为 ``{"A1": {"v": ..., "f": ...}}``。
       （Univer snapshot 结构）

    两种均支持。返回结构同 ``search_in_snapshot_data``。
    """
    if not parsed_data or not keyword:
        return []
    cells = parsed_data.get("cells")
    if not isinstance(cells, dict):
        return []

    hits: list[dict[str, Any]] = []

    for key, raw in cells.items():
        if len(hits) >= max_results:
            return hits

        # 形态 1：扁平 "Sheet1!A1" → 标量 / dict
        if "!" in str(key):
            sheet, cell_ref = _split_cell_key(str(key))
            value = _extract_cell_value(raw)
            if _value_matches(value, keyword):
                hits.append(
                    {
                        "field": "cell",
                        "sheet": sheet,
                        "cell_ref": cell_ref,
                        "value": value,
                    }
                )
            continue

        # 形态 2：嵌套 sheet → {cell_ref → {v, f}}
        if isinstance(raw, dict):
            for inner_ref, inner_val in raw.items():
                if len(hits) >= max_results:
                    return hits
                value = _extract_cell_value(inner_val)
                if _value_matches(value, keyword):
                    hits.append(
                        {
                            "field": "cell",
                            "sheet": str(key),
                            "cell_ref": str(inner_ref),
                            "value": value,
                        }
                    )

    return hits


def _extract_cell_value(raw: Any) -> Any:
    """从单元格数据提取值

    支持标量、``{"v": value, "f": formula}`` dict、Univer ``{"v": ...}`` 结构。
    """
    if isinstance(raw, dict):
        # 优先 v 字段
        if "v" in raw:
            return raw["v"]
        # 其次 value / val 字段
        for k in ("value", "val"):
            if k in raw:
                return raw[k]
        return None
    return raw


# ---------------------------------------------------------------------------
# DB 编排：跨多个快照 + 当前活跃版本
# ---------------------------------------------------------------------------


async def search_versions(
    db: AsyncSession,
    wp_id: UUID,
    keyword: str,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """在底稿全部历史版本（含当前活跃版本）的 cells 中模糊搜索

    返回扁平命中列表（按 ``snapshot_at`` 倒序，最新在前），单条结构::

        {
          "version_id": "<uuid>" | "current",
          "trigger_event": "prefill" | "review" | "sign" | "current",
          "snapshot_at": "2026-...T...",
          "sheet": "Sheet1",
          "cell_ref": "A1",
          "value": "...",
          "field": "formula_value" | "audited_amount" | "cell",
        }

    查询包含两部分：
    1. ``workpaper_snapshots.snapshot_data`` 历史快照
    2. ``working_paper.parsed_data`` 当前活跃版本（标记 version_id="current"）
    """
    if not keyword:
        return []

    results: list[dict[str, Any]] = []

    # 1) 历史快照（按 created_at DESC）
    snapshot_rows = (
        await db.execute(
            sa.text(
                """
                SELECT id, trigger_event, created_at, snapshot_data
                FROM workpaper_snapshots
                WHERE wp_id = :wid
                ORDER BY created_at DESC
                """
            ),
            {"wid": str(wp_id)},
        )
    ).fetchall()

    for row in snapshot_rows:
        version_id = str(row.id)
        trigger_event = row.trigger_event
        snapshot_at = row.created_at.isoformat() if row.created_at else None
        for hit in search_in_snapshot_data(row.snapshot_data, keyword, max_results=limit):
            if len(results) >= limit:
                return results
            results.append(
                {
                    **hit,
                    "version_id": version_id,
                    "trigger_event": trigger_event,
                    "snapshot_at": snapshot_at,
                }
            )

    # 2) 当前活跃版本
    if len(results) < limit:
        current_row = (
            await db.execute(
                sa.text(
                    """
                    SELECT parsed_data, file_version, updated_at
                    FROM working_paper
                    WHERE id = :wid
                    """
                ),
                {"wid": str(wp_id)},
            )
        ).first()
        if current_row is not None:
            updated_at = current_row.updated_at
            snapshot_at = (
                updated_at.isoformat() if isinstance(updated_at, datetime) else None
            )
            for hit in search_in_parsed_data(
                current_row.parsed_data, keyword, max_results=limit - len(results)
            ):
                if len(results) >= limit:
                    return results
                results.append(
                    {
                        **hit,
                        "version_id": "current",
                        "trigger_event": "current",
                        "snapshot_at": snapshot_at,
                    }
                )

    return results


__all__ = [
    "search_in_snapshot_data",
    "search_in_parsed_data",
    "search_versions",
]
