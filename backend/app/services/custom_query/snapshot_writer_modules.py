"""非 workpaper 模块的 cell 写回实现（report / note / adj / tb）。

从 ``snapshot_writer.py`` 抽出（该文件已达 800 行门禁上限）。四者是同构流程 ——
``SELECT ... FOR UPDATE`` → 乐观锁 → 按虚拟 sheet 列映射定位 → ``UPDATE``，与 workpaper
的 11 步事务（addr_id 解析 / xlsx cache / orchestrator 联动 / 无审计不回写）无关。

``SnapshotWriter`` 上保留同名薄委托方法：既有测试用 ``hasattr`` 检查模块分派、并用实例
赋值做替身，把方法整个搬走会让两者失效。乐观锁校验经 ``check_lock`` 注入，避免伴生模块
反向依赖 writer 实例。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.custom_query.snapshot_writer_shared import (
    WritebackPermissionDenied,
    parse_cell_ref as _parse_cell_ref,
)

CheckLock = Callable[[datetime, Any, Any], None]


async def write_report_cell(
    db: AsyncSession,
    user: Any,
    wp_id: str,
    sheet_name: str,
    cell_ref: str,
    new_value: Any,
    opened_at: datetime,
    *,
    check_lock: CheckLock,
) -> dict:
    """写回 report_snapshot.data JSONB。

    虚拟 sheet 列映射：A=row_code, B=row_name, C=current_period_amount, D=prior_period_amount, E=formula
    """
    from app.services.custom_query.module_cell_resolver import _REPORT_COLUMNS

    # wp_id 在 report 模块中是 report_snapshot.id
    result = await db.execute(
        text("""
            -- report_snapshot 无 updated_at 列；时间戳列真名是 generated_at。
            -- 用别名保持下游按 updated_at 取值不变。
            SELECT id, data, generated_at AS updated_at FROM report_snapshot
            WHERE id = :rid
            FOR UPDATE
        """),
        {"rid": wp_id},
    )
    row = result.first()
    if not row:
        raise ValueError(f"Report snapshot not found: {wp_id}")

    current_updated_at = row[2]
    data = row[1] or {}

    # 乐观锁
    check_lock(opened_at, current_updated_at, user)

    # 解析 cell_ref 定位虚拟 sheet 行列
    row_idx, col_idx = _parse_cell_ref(cell_ref)
    rows_arr = data.get("rows", [])

    # 虚拟 sheet: 第 1 行是表头，第 2 行起是数据
    data_row_idx = row_idx - 1  # 第 2 行 = rows[0]
    if data_row_idx < 0 or data_row_idx >= len(rows_arr):
        raise ValueError(f"Row index out of range: {cell_ref}")

    col_name = _REPORT_COLUMNS[col_idx] if col_idx < len(_REPORT_COLUMNS) else None
    if not col_name:
        raise ValueError(f"Column index out of range: {cell_ref}")

    old_value = rows_arr[data_row_idx].get(col_name)
    rows_arr[data_row_idx][col_name] = new_value

    now = datetime.now(timezone.utc)
    await db.execute(
        text("""
            UPDATE report_snapshot
            SET data = :new_data, updated_at = :now
            WHERE id = :rid
        """),
        {"new_data": json.dumps(data, ensure_ascii=False), "rid": wp_id, "now": now},
    )

    return {"success": True, "updated_at": now.isoformat(), "old_value": old_value}

async def write_note_cell(
    db: AsyncSession,
    user: Any,
    wp_id: str,
    sheet_name: str,
    cell_ref: str,
    new_value: Any,
    opened_at: datetime,
    *,
    check_lock: CheckLock,
) -> dict:
    """写回 consol_note_data.data JSONB。

    虚拟 sheet 列映射：A=code, B=name, C=year_end, D=year_begin, E=formula
    """
    from app.services.custom_query.module_cell_resolver import _NOTE_COLUMNS

    result = await db.execute(
        text("""
            SELECT id, data, updated_at FROM consol_note_data
            WHERE id = :nid
            FOR UPDATE
        """),
        {"nid": wp_id},
    )
    row = result.first()
    if not row:
        raise ValueError(f"Note data not found: {wp_id}")

    current_updated_at = row[2]
    data = row[1] or {}

    check_lock(opened_at, current_updated_at, user)

    row_idx, col_idx = _parse_cell_ref(cell_ref)
    rows_arr = data.get("rows", [])

    data_row_idx = row_idx - 1
    if data_row_idx < 0 or data_row_idx >= len(rows_arr):
        raise ValueError(f"Row index out of range: {cell_ref}")

    col_name = _NOTE_COLUMNS[col_idx] if col_idx < len(_NOTE_COLUMNS) else None
    if not col_name:
        raise ValueError(f"Column index out of range: {cell_ref}")

    old_value = rows_arr[data_row_idx].get(col_name)
    rows_arr[data_row_idx][col_name] = new_value

    now = datetime.now(timezone.utc)
    await db.execute(
        text("""
            UPDATE consol_note_data
            SET data = :new_data, updated_at = :now
            WHERE id = :nid
        """),
        {"new_data": json.dumps(data, ensure_ascii=False), "nid": wp_id, "now": now},
    )

    return {"success": True, "updated_at": now.isoformat(), "old_value": old_value}

async def write_adj_cell(
    db: AsyncSession,
    user: Any,
    wp_id: str,
    sheet_name: str,
    cell_ref: str,
    new_value: Any,
    opened_at: datetime,
    *,
    check_lock: CheckLock,
) -> dict:
    """写回 adjustments 表 UPDATE。

    虚拟 sheet 列映射：A=entry_no, B=account_code, C=account_name, D=debit_amount, E=credit_amount, F=description
    wp_id 在 adj 模块中是 adjustment 记录的 id。
    """
    from app.services.custom_query.module_cell_resolver import _ADJ_COLUMNS

    result = await db.execute(
        text("SELECT id, updated_at FROM adjustments WHERE id = :aid FOR UPDATE"),
        {"aid": wp_id},
    )
    row = result.first()
    if not row:
        raise ValueError(f"Adjustment not found: {wp_id}")

    current_updated_at = row[1]
    check_lock(opened_at, current_updated_at, user)

    _, col_idx = _parse_cell_ref(cell_ref)
    col_name = _ADJ_COLUMNS[col_idx] if col_idx < len(_ADJ_COLUMNS) else None
    if not col_name:
        raise ValueError(f"Column index out of range: {cell_ref}")

    now = datetime.now(timezone.utc)
    await db.execute(
        text(f"""
            UPDATE adjustments
            SET {col_name} = :new_val, updated_at = :now
            WHERE id = :aid
        """),
        {"new_val": new_value, "now": now, "aid": wp_id},
    )

    return {"success": True, "updated_at": now.isoformat(), "old_value": None}

async def write_tb_cell(
    db: AsyncSession,
    user: Any,
    wp_id: str,
    sheet_name: str,
    cell_ref: str,
    new_value: Any,
    opened_at: datetime,
    *,
    check_lock: CheckLock,
) -> dict:
    """写回 trial_balance.audited_amount UPDATE。

    虚拟 sheet 列映射：A=account_code, B=account_name, C=opening_balance, D=debit_amount, E=credit_amount, F=closing_balance, G=audited_amount
    wp_id 在 tb 模块中是 trial_balance 记录的 id。
    """
    result = await db.execute(
        text("SELECT id, updated_at FROM trial_balance WHERE id = :tid FOR UPDATE"),
        {"tid": wp_id},
    )
    row = result.first()
    if not row:
        raise ValueError(f"Trial balance record not found: {wp_id}")

    current_updated_at = row[1]
    check_lock(opened_at, current_updated_at, user)

    _, col_idx = _parse_cell_ref(cell_ref)
    # 只允许写 audited_amount (G 列, col_idx=6)
    if col_idx != 6:
        raise WritebackPermissionDenied(
            "Only audited_amount (column G) is writable in trial_balance"
        )

    now = datetime.now(timezone.utc)
    await db.execute(
        text("""
            UPDATE trial_balance
            SET audited_amount = :new_val, updated_at = :now
            WHERE id = :tid
        """),
        {"new_val": new_value, "now": now, "tid": wp_id},
    )

    return {"success": True, "updated_at": now.isoformat(), "old_value": None}
