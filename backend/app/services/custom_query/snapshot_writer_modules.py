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

# 哨兵值：区分「调用方没传 node_key」与「调用方显式传 None（legacy NULL 行）」
_UNSET = object()


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

class NoteOwnershipMismatch(Exception):
    """附注记录归属不匹配：请求的 project/year/section/node_key 与数据库行不一致。

    设计 §五.2：writer 在 FOR UPDATE 后逐项比较归属字段，不匹配则拒绝回滚。
    """

    def __init__(self, field: str, expected: Any, actual: Any):
        self.field = field
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"附注记录归属校验失败：{field} 不匹配"
            f"（请求值={expected!r}，记录值={actual!r}）"
        )


class NoteRecordNotFound(Exception):
    """附注记录不存在或已删除，不回退到 legacy NULL 行。

    设计 §五.2：找不到该节点记录即拒绝。
    """

    def __init__(self, record_id: str):
        self.record_id = record_id
        super().__init__(f"附注记录不存在：{record_id}")


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
    note_record_id: str | None = None,
    note_section_id: str | None = None,
    note_year: int | None = None,
    note_node_key: str | None = _UNSET,
    note_project_id: str | None = None,
) -> dict:
    """写回 consol_note_data.data JSONB。

    虚拟 sheet 列映射：A=code, B=name, C=year_end, D=year_begin, E=formula

    设计 §五.2 归属校验流程：
    1. SELECT ... FOR UPDATE（PG）或普通 SELECT（SQLite）锁定记录
    2. 逐项比较 project_id/year/section_id/node_key 与请求字段
    3. 不匹配 → NoteOwnershipMismatch → 路由回滚事务
    4. 记录不存在 → NoteRecordNotFound → 不 fallback 到 legacy NULL 行
    """
    from app.services.custom_query.module_cell_resolver import _NOTE_COLUMNS

    # ── 确定查询目标 ID ──────────────────────────────────────────────────────
    # 新版请求通过 note_record_id 传入精确记录 ID；
    # 旧版兼容路径用 wp_id（= body.wp_code）。
    target_id_str = note_record_id or wp_id
    import uuid as _uuid_mod
    try:
        target_id = _uuid_mod.UUID(target_id_str) if isinstance(target_id_str, str) else target_id_str
    except (ValueError, AttributeError):
        raise NoteRecordNotFound(str(target_id_str))

    # ── Step 1: SELECT ... FOR UPDATE（兼容 SQLite）─────────────────────────
    # SQLite 不支持 FOR UPDATE，通过 ORM with_for_update() 让 SQLAlchemy
    # 根据 dialect 决定是否生成 FOR UPDATE 子句。SQLite 时退化为普通 SELECT。
    from app.models.consol_note_data_models import ConsolNoteData
    from sqlalchemy import select as sa_select

    stmt = sa_select(ConsolNoteData).where(ConsolNoteData.id == target_id)
    try:
        stmt = stmt.with_for_update()
    except Exception:
        # SQLite 等不支持 FOR UPDATE 的后端 → 使用普通 SELECT
        pass

    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record is None:
        raise NoteRecordNotFound(str(target_id))

    # ── Step 2: 归属字段逐项校验（设计 §五.2）────────────────────────────────
    # 只要调用方传入了归属字段就进行严格比对；旧版不传则跳过（向后兼容）。
    _has_ownership = (
        note_project_id is not None
        or note_year is not None
        or note_section_id is not None
        or note_node_key is not _UNSET
    )
    if _has_ownership:
        # project_id 比较：统一为字符串比较（UUID 与 str 混用）
        if note_project_id is not None:
            db_pid = str(record.project_id)
            req_pid = str(note_project_id)
            if db_pid != req_pid:
                raise NoteOwnershipMismatch("project_id", req_pid, db_pid)

        # year 比较
        if note_year is not None:
            db_year = record.year
            if db_year != note_year:
                raise NoteOwnershipMismatch("year", note_year, db_year)

        # section_id 比较
        if note_section_id is not None:
            db_sec = record.section_id
            if db_sec != note_section_id:
                raise NoteOwnershipMismatch("section_id", note_section_id, db_sec)

        # node_key 比较：None（legacy NULL 行）是合法值，需精确匹配
        if note_node_key is not _UNSET:
            db_nk = record.node_key
            if db_nk != note_node_key:
                raise NoteOwnershipMismatch("node_key", note_node_key, db_nk)

    # ── Step 3: 乐观锁 ─────────────────────────────────────────────────────
    current_updated_at = record.updated_at
    data = record.data or {}

    check_lock(opened_at, current_updated_at, user)

    # ── Step 4: 定位 cell 并更新（设计 §五.2：行列越界与形状校验）────────────
    row_idx, col_idx = _parse_cell_ref(cell_ref)
    rows_arr = data.get("rows", [])

    data_row_idx = row_idx - 1
    if data_row_idx < 0 or data_row_idx >= len(rows_arr):
        raise ValueError(
            f"行索引越界：{cell_ref}（有效行数 {len(rows_arr)}，"
            f"请求行 {row_idx}）"
        )

    col_name = _NOTE_COLUMNS[col_idx] if col_idx < len(_NOTE_COLUMNS) else None
    if not col_name:
        raise ValueError(
            f"列索引越界：{cell_ref}（有效列数 {len(_NOTE_COLUMNS)}，"
            f"请求列 {col_idx}）"
        )

    # dict 行和 list 行的取值方式不同；保留非目标 cell 和原行形状
    target_row = rows_arr[data_row_idx]
    if isinstance(target_row, dict):
        old_value = target_row.get(col_name)
        target_row[col_name] = new_value
    elif isinstance(target_row, list):
        if col_idx < len(target_row):
            old_value = target_row[col_idx]
            target_row[col_idx] = new_value
        else:
            raise ValueError(
                f"二维数组行列索引越界：{cell_ref}（该行长度 {len(target_row)}，"
                f"请求列 {col_idx}）"
            )
    else:
        raise ValueError(
            f"不支持的行数据形状：{type(target_row).__name__}（"
            f"仅支持 dict 对象行与 list 二维数组行）"
        )

    # ── Step 5: UPDATE ─────────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    # SQLite 存 UUID 为 32 位 hex（无连字符），使用 .hex 保持一致
    nid_param = target_id.hex if hasattr(target_id, 'hex') else str(target_id)
    await db.execute(
        text("""
            UPDATE consol_note_data
            SET data = :new_data, updated_at = :now
            WHERE id = :nid
        """),
        {"new_data": json.dumps(data, ensure_ascii=False), "nid": nid_param, "now": now},
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
        text("""
            SELECT id, project_id, year, standard_account_code,
                   audited_amount, updated_at
            FROM trial_balance
            WHERE id = :tid
            FOR UPDATE
        """),
        {"tid": wp_id},
    )
    row = result.first()
    if not row:
        raise ValueError(f"Trial balance record not found: {wp_id}")

    current_updated_at = row[5]
    check_lock(opened_at, current_updated_at, user)

    _, col_idx = _parse_cell_ref(cell_ref)
    # 只允许写 audited_amount (G 列, col_idx=6)
    if col_idx != 6:
        raise WritebackPermissionDenied(
            "Only audited_amount (column G) is writable in trial_balance"
        )

    from app.services.tb_audited_writer import publish_rows

    publish_report = await publish_rows(
        db,
        row[1],
        int(row[2]),
        [{
            "trial_balance_id": row[0],
            "account_code": row[3],
            "audited_amount": new_value,
        }],
        source="custom-query:tb-cell",
    )
    if not publish_report.updated_rows:
        reason = publish_report.skipped[0].reason if publish_report.skipped else "未更新试算表"
        raise ValueError(f"Trial balance record was not updated: {wp_id}（{reason}）")

    published = publish_report.updated_rows[0]
    return {
        "success": True,
        "updated_at": published.published_at.isoformat(),
        "old_value": published.previous_amount,
    }
