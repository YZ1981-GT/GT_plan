"""底稿披露同步的子表 owner 清册。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Mapping, Protocol
from uuid import UUID


class _OwnerRowScope(Protocol):
    """owner 摘要所需的最小行范围契约。"""

    owner_row_code: str


#: 附注行内的底稿子表 owner 清册。清册与表数据位于同一 JSONB、受同一行锁保护，
#: 因而「写新表 / 删旧表 / 推进 owner」可以在同一事务内完成。
TABLE_OWNER_LEDGER_KEY = "_workpaper_table_owners"


def owner_payload_sha256(
    *,
    tables: Mapping[str, Any],
    columns: Mapping[str, Any],
    note_texts: list[dict[str, Any]],
    removed_text_sections: list[str],
    row_scopes: Mapping[str, _OwnerRowScope],
) -> str:
    """计算 owner 本次输入的稳定摘要（不含时间戳和客户端旧基线）。"""
    payload = {
        "tables": tables,
        "columns": columns,
        "note_texts": note_texts,
        "removed_text_sections": removed_text_sections,
        "row_scopes": {
            name: {"owner_row_code": scope.owner_row_code}
            for name, scope in sorted(row_scopes.items())
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_table_owner_ledger(
    table_data: dict[str, Any],
    *,
    owner_key: str,
    wp_id: UUID,
    sheet_name: str,
    pushed_tables: Mapping[str, Any],
    columns: Mapping[str, Any],
    note_texts: list[dict[str, Any]],
    removed_text_sections: list[str],
    row_scopes: Mapping[str, _OwnerRowScope],
    replace_owned_tables: bool,
    synced_at: datetime,
) -> list[str]:
    """在附注行内原子推进 owner，并只删除该 owner 已放弃且无人共管的表。

    首次没有该 owner 的清册时只登记本次集合，不猜测历史表归属。显式空表仍是
    owner 当前拥有的表；只有从本次集合中消失的旧表才进入删除候选。数据与列定义
    始终一起删除，避免留下孤儿列头。
    """
    raw_ledger = table_data.get(TABLE_OWNER_LEDGER_KEY)
    raw_owners = raw_ledger.get("owners") if isinstance(raw_ledger, dict) else None
    owners: dict[str, Any] = dict(raw_owners) if isinstance(raw_owners, dict) else {}
    previous = owners.get(owner_key)
    previous_tables = {
        str(name)
        for name in (previous.get("tables") if isinstance(previous, dict) else []) or []
        if str(name) and not str(name).startswith("_")
    }
    current_tables = {
        str(name)
        for name in pushed_tables
        if str(name) and not str(name).startswith("_")
    }

    dropped: list[str] = []
    if replace_owned_tables and isinstance(previous, dict):
        protected_by_others: set[str] = set()
        for other_key, other in owners.items():
            if other_key == owner_key or not isinstance(other, dict):
                continue
            protected_by_others.update(
                str(name)
                for name in (other.get("tables") or [])
                if str(name) and not str(name).startswith("_")
            )
        candidates = sorted(previous_tables - current_tables - protected_by_others)
        sub = dict(table_data.get("sub_table_data") or {})
        cols = dict(table_data.get("_sub_table_columns") or {})
        for name in candidates:
            existed = name in sub or name in cols
            sub.pop(name, None)
            cols.pop(name, None)
            if existed:
                dropped.append(name)
        table_data["sub_table_data"] = sub
        if cols or "_sub_table_columns" in table_data:
            table_data["_sub_table_columns"] = cols

    owners[owner_key] = {
        "wp_id": str(wp_id),
        "sheet_name": sheet_name,
        "tables": sorted(current_tables),
        "payload_sha256": owner_payload_sha256(
            tables=pushed_tables,
            columns=columns,
            note_texts=note_texts,
            removed_text_sections=removed_text_sections,
            row_scopes=row_scopes,
        ),
        "synced_at": synced_at.isoformat(),
    }
    table_data[TABLE_OWNER_LEDGER_KEY] = {"version": 1, "owners": owners}
    return dropped
