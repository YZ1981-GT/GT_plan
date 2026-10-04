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


def _norm_scope_project_id(value: Any) -> str | None:
    """归一化 project_id 用于逐项比对。

    请求携带的是字符串形态；``FOR UPDATE`` 读出的列在 PG 是 ``UUID``、在 SQLite 是
    ``str``。统一转小写去连字符的 hex 形态，避免 ``UUID('...')`` vs ``'...'`` 这类表征
    差异把合法请求误判成跨项目越权。无法归一的原样返回（交由等值比较拒绝）。
    """
    if value is None:
        return None
    from uuid import UUID

    try:
        return UUID(str(value)).hex
    except (ValueError, TypeError, AttributeError):
        return str(value)


def _verify_note_scope(
    *,
    wp_id: str,
    row_project_id: Any,
    row_year: Any,
    row_section_id: Any,
    row_node_key: Any,
    req_project_id: str | None,
    req_year: int | None,
    req_section_id: str | None,
    req_node_key: str | None,
) -> None:
    """Task 3.4：``FOR UPDATE`` 锁定记录后，逐项复验请求携带的归属元组。

    附注记录的归属元组为 ``(project_id, year, section_id, node_key)``（设计 §二.3、§五.2，
    ADR-CNSC-004）。``wp_id`` 是可猜测的记录 ID，**不是**授权边界 —— 必须用请求显式携带的
    归属字段逐项与锁定行的实际列值相等比较，任一不符即越权拒绝（R3.3/R3.4）。

    - ``node_key``：请求与记录必须同为节点键或同为 legacy ``None``。请求给节点键而记录是
      legacy NULL（或反之）即不匹配 —— **不**把节点写入重定向到 NULL legacy 行（R3.2、
      ADR-CNSC-004：节点专属写回不得因记录缺失/不符而改写 legacy）。
    - 任一字段不符 → ``WritebackPermissionDenied`` → router 回滚，``consol_note_data`` 不变
      （R3.6「写回被拒绝、记录不存在或归属不匹配 → 事务回滚，不更新任何行」）。

    向后兼容：仅当调用方提供了归属上下文（``req_project_id`` 非空，即 note 模块路径）时才
    强制复验；旧调用未传归属时保持原行为，不改变现有乐观锁语义。
    """
    # 旧调用未携带归属上下文（workpaper/report/adj/tb 复用本函数无意义）——不强制。
    if req_project_id is None:
        return

    mismatches: list[str] = []

    if _norm_scope_project_id(req_project_id) != _norm_scope_project_id(row_project_id):
        mismatches.append("project_id")

    # year：请求侧是 int | None；记录侧可能是 int（SQLite/PG）。显式携带时必须相等。
    if req_year is not None:
        row_year_cmp = int(row_year) if row_year is not None else None
        if req_year != row_year_cmp:
            mismatches.append("year")

    if req_section_id is not None and req_section_id != row_section_id:
        mismatches.append("section_id")

    # node_key：节点身份。请求给节点键 → 记录必须是同一节点键；请求为 legacy（None）→
    # 记录必须也是 legacy（node_key IS NULL）。两侧必须同类且相等。
    if req_node_key != row_node_key:
        mismatches.append("node_key")

    if mismatches:
        raise WritebackPermissionDenied(
            "附注记录归属校验失败（归属不一致，拒绝写回）："
            f"记录 {wp_id} 的 {','.join(mismatches)} 与请求不符"
        )


def _write_note_row_cell(
    row_obj: Any,
    col_idx: int,
    new_value: Any,
    columns: list[str],
    cell_ref: str,
) -> Any:
    """Task 3.5：按行形态把 ``new_value`` 原位写入 ``row_obj`` 的第 ``col_idx`` 列，返回旧值。

    附注 ``consol_note_data.data["rows"]`` 的实际持久化形态有两种（与 custom_query 取数器
    ``module_cell_resolver._query_note_cells`` 的虚拟 sheet 构建逐一对应 —— 读写同口径）：

    - **dict 对象行**：列号经 ``columns``（``_NOTE_COLUMNS``：A=code, B=name, C=year_end,
      D=year_begin, E=formula）映射成键名原位更新。只改目标键，保留其余键与键序、不改写成
      数组（设计 §五、需求 3.5）。
    - **二维数组行**（``list``）：按**位置列号**写入（col_idx == 数组下标，与取数器
      ``item[col_idx]`` 的位置映射一致）。保留该行其它列与其它行；该行比目标列窄时**只补到
      目标列**（``extend`` 到 ``col_idx+1``），不强制全行等宽（与 ``consol_note_formula_service.
      fill_rows`` 的 2.4 口径一致，避免同一附注数据两套写入语义冲突）。

    边界与形状错误（需求 3.5、设计 §五「越界或不支持的数据形状返回明确客户端错误」）：

    - ``col_idx`` 超出已知列映射范围（``>= len(columns)``）→ ``ValueError``（router 转 400）。
      两种形态同一列上限，与取数器 ``col_name = columns[col_idx] if col_idx < len(columns)``
      的读侧口径对齐。
    - 行对象既非 dict 也非 list（如 ``None`` / 标量）→ ``ValueError``：不支持的数据形状，
      不猜测、不就地改造。

    不处理行越界（``data_row_idx`` 范围）—— 那是调用方在定位行时已做的检查。
    """
    if col_idx < 0 or col_idx >= len(columns):
        raise ValueError(f"Column index out of range: {cell_ref}")

    if isinstance(row_obj, dict):
        # 对象行：列号 → 键名，原位写入，保留其余键与键序。
        col_name = columns[col_idx]
        old_value = row_obj.get(col_name)
        row_obj[col_name] = new_value
        return old_value

    if isinstance(row_obj, list):
        # 二维数组行：按位置列号写入，保留其它列；窄行只补到目标列，不强制等宽。
        old_value = row_obj[col_idx] if col_idx < len(row_obj) else None
        if col_idx >= len(row_obj):
            row_obj.extend([""] * (col_idx + 1 - len(row_obj)))
        row_obj[col_idx] = new_value
        return old_value

    # 既非对象行也非数组行 → 不支持的形状，明确拒绝（不就地改造成某种形态）。
    raise ValueError(
        f"Unsupported note row shape at {cell_ref}: "
        f"行既非对象（dict）也非二维数组（list），类型为 {type(row_obj).__name__}"
    )


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
    project_id: str | None = None,
    year: int | None = None,
    section_id: str | None = None,
    node_key: str | None = None,
) -> dict:
    """写回 consol_note_data.data JSONB。

    虚拟 sheet 列映射：A=code, B=name, C=year_end, D=year_begin, E=formula

    节点归属（R3.3/R3.4；设计 §五.2、ADR-CNSC-004）
    ------------------------------------------------
    附注记录的归属元组为 ``(project_id, year, section_id, node_key)``。请求现**显式携带**
    该元组（经 ``record id = wp_id`` 定位行、``cell_ref`` 定位单元格、``opened_at`` 乐观锁）。
    不得把可猜测的 ``wp_id`` 当作项目或节点授权边界。

    Task 3.3 的**字段扩展**部分把归属字段纳入签名并随 ``SELECT ... FOR UPDATE`` 一并读出
    数据库记录的归属列。**Task 3.4（本次）**：锁定记录后经 ``_verify_note_scope`` 逐项复验
    归属元组 —— 缺行或任一字段不匹配即拒绝（``WritebackPermissionDenied`` / ``ValueError``），
    由 router 回滚、``consol_note_data`` 不变、**不 fallback 到 legacy NULL 行**（R3.3/R3.4/
    R3.6、ADR-CNSC-004）。调用方未传归属字段时（旧调用）保持原行为，不改变现有乐观锁语义。

    Task 3.5（本次）：单元格写入经 ``_write_note_row_cell`` **同时支持 dict 对象行与二维数组行**，
    只改目标 cell、保留其余行列与原行形状；行列越界与不支持的行形状返回明确 ``ValueError``
    （router 转 400）。读写列映射与取数器 ``module_cell_resolver`` 的虚拟 sheet 口径一致
    （``_NOTE_COLUMNS``：A=code, B=name, C=year_end, D=year_begin, E=formula）。
    """
    from app.services.custom_query.module_cell_resolver import _NOTE_COLUMNS

    # 随 FOR UPDATE 一并读出归属列（project_id/year/section_id/node_key），供 Task 3.4
    # 在锁定记录后逐项复验。本任务（3.3）只负责把这些列读出来并挂到结果上。
    result = await db.execute(
        text("""
            SELECT id, data, updated_at,
                   project_id, year, section_id, node_key
            FROM consol_note_data
            WHERE id = :nid
            FOR UPDATE
        """),
        {"nid": wp_id},
    )
    row = result.first()
    if not row:
        # 记录不存在 → 拒绝（R3.6）。**不** fallback 到 legacy NULL 行：节点专属写回
        # 不得因记录缺失改写 legacy（ADR-CNSC-004）。
        raise ValueError(f"Note data not found: {wp_id}")

    # 数据库记录的归属元组（Task 3.4 据此逐项比对请求携带的归属字段）
    row_project_id = row[3]
    row_year = row[4]
    row_section_id = row[5]
    row_node_key = row[6]

    # Task 3.4：锁定记录后逐项复验归属元组 (project_id, year, section_id, node_key)。
    # wp_id 是可猜测的记录 ID，不是授权边界 —— 任一归属字段与锁定行不符即越权拒绝，
    # 由 router 回滚（R3.3/R3.4/R3.6）。复验在乐观锁与任何数据改动之前执行：越权请求
    # 不应泄露记录是否「已被他人改动」这类乐观锁状态。
    _verify_note_scope(
        wp_id=wp_id,
        row_project_id=row_project_id,
        row_year=row_year,
        row_section_id=row_section_id,
        row_node_key=row_node_key,
        req_project_id=project_id,
        req_year=year,
        req_section_id=section_id,
        req_node_key=node_key,
    )

    current_updated_at = row[2]
    data = row[1] or {}

    check_lock(opened_at, current_updated_at, user)

    row_idx, col_idx = _parse_cell_ref(cell_ref)
    rows_arr = data.get("rows", [])

    # 行越界检查（data_row_idx = row_idx - 1：虚拟 sheet 第 1 行是表头，第 2 行起是数据）。
    data_row_idx = row_idx - 1
    if data_row_idx < 0 or data_row_idx >= len(rows_arr):
        raise ValueError(f"Row index out of range: {cell_ref}")

    # Task 3.5：按行形态（dict 对象行 / 二维数组行）原位写目标 cell，保留其它行列与原形状；
    # 列越界或不支持的形状由 _write_note_row_cell 抛 ValueError（router 转 400）。
    old_value = _write_note_row_cell(
        rows_arr[data_row_idx], col_idx, new_value, _NOTE_COLUMNS, cell_ref,
    )

    now = datetime.now(timezone.utc)
    await db.execute(
        text("""
            UPDATE consol_note_data
            SET data = :new_data, updated_at = :now
            WHERE id = :nid
        """),
        {"new_data": json.dumps(data, ensure_ascii=False), "nid": wp_id, "now": now},
    )

    return {
        "success": True,
        "updated_at": now.isoformat(),
        "old_value": old_value,
        # 数据库记录的归属元组回传 —— Task 3.4 在此之上加锁后复验，Task 3.6 据此断言。
        "record_scope": {
            "project_id": str(row_project_id) if row_project_id is not None else None,
            "year": int(row_year) if row_year is not None else None,
            "section_id": row_section_id,
            "node_key": row_node_key,
        },
    }

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
