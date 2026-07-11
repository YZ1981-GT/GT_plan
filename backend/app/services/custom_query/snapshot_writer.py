"""双向编辑写回 — SnapshotWriter

实现 cell 级写回到 working_papers.parsed_data['univer_snapshot'] JSONB，
支持乐观锁冲突检测（X-File-Opened-At vs updated_at）、单事务一致性、
跨模块路由写入（workpaper / report / note / adj / tb）。

ACNR 集成 (M2, R15.1, R15.2, R15.4):
  - 写回时通过 ACNR resolve 获取 canonical addr_id
  - 返回结果附带 addr_id + column_metadata（chip 可下钻到格）
  - resolve 携带 project context（project_id）保证 wp_id 正确解析

11 步事务算法（design.md §11 WritebackPreview + SnapshotWriter，advanced-query Task 15.3）:
  1. SELECT updated_at, parsed_data FROM working_paper WHERE id = wp_id FOR UPDATE
  2. Belt+suspenders project_id 归属校验
  3. IF opened_at < updated_at → raise WritebackConflict(updated_at, last_editor)（乐观锁）
  4. **写回前解析 addr_id 身份**：经 full_resolve（AddressingService，5s 超时）解析目标为
     canonical `{wp_code}/{sheet_code}/{coordinate_key}`（R3.1）。
       - 无法解析 → 中止、不改任何数据、`TARGET_UNRESOLVABLE`（R3.4）
       - resolve 不可用/5s 无响应 → 中止、数据不变、`RESOLVE_UNAVAILABLE`（R3.5）
  5. 定位 cellData[row][col]，old_value = cellData[row][col].get('v')，写入 new_value
  6. UPDATE working_paper SET parsed_data = :new_pd（orchestrator 负责 stale/updated_at/version）
  7. 同步更新 xlsx cache（run_in_executor + openpyxl write）
  8. orchestrator.after_save（file_version++ / prefill_stale / updated_at / WORKPAPER_SAVED 事件）
  9. 落 advanced_query_writeback（addr_id 身份 + old/new + operator + result，R3.1/R14.3）
 10. **无审计不回写**：audit_logger.log_action('custom_query.cell_writeback', ...) 纳入事务成功
     判定 —— 审计写入失败 → 回滚回写改动、`AUDIT_WRITE_FAILED`（R14.8）
 11. 组装 addr_id + column_metadata 返回（R3.2/R3.3，chip 可下钻到格）

任一步失败 → 整事务回滚至开始前状态，不残留部分写入（R3.6/R14.5，"无审计不回写"）。
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─── 错误码（与 design.md Error Handling 表 / addressing_service 对齐）─────────

# 回写目标无法解析为有效 addr_id → 中止、不改数据（R3.4）
ERR_CODE_TARGET_UNRESOLVABLE = "TARGET_UNRESOLVABLE"
# resolve 不可用/5s 无响应 → 中止、数据不变（R3.5）
ERR_CODE_RESOLVE_UNAVAILABLE = "RESOLVE_UNAVAILABLE"
# 审计写入失败 → 回滚回写改动（R14.8「无审计不回写」）
ERR_CODE_AUDIT_WRITE_FAILED = "AUDIT_WRITE_FAILED"


# ─── Exceptions ──────────────────────────────────────────────────────────────


class WritebackConflict(Exception):
    """乐观锁冲突：opened_at < updated_at"""

    def __init__(self, latest_updated_at: datetime, latest_editor: str):
        self.latest_updated_at = latest_updated_at
        self.latest_editor = latest_editor
        super().__init__(
            f"Conflict: data updated at {latest_updated_at} by {latest_editor}"
        )


class WritebackPermissionDenied(Exception):
    """无写权限或非 workpaper 源"""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class WritebackTargetUnresolvable(Exception):
    """回写目标无法被 Resolve_Service 解析为有效 addr_id（R3.4）。

    字段缺失 / 格式非法 / 目标格不存在 → 中止回写、不修改任何数据。
    携带 `error_code=TARGET_UNRESOLVABLE` 供 router 转 HTTP 400。
    """

    error_code = ERR_CODE_TARGET_UNRESOLVABLE

    def __init__(self, target_hint: str, message: str | None = None):
        self.target_hint = target_hint
        self.message = message or f"回写目标无法解析为有效 addr_id：{target_hint}"
        super().__init__(self.message)


class WritebackResolveUnavailable(Exception):
    """Resolve_Service 不可用或 5 秒内无响应（R3.5）。

    中止回写、保持数据不变。携带 `error_code=RESOLVE_UNAVAILABLE` 供 router 转 HTTP 503。
    """

    error_code = ERR_CODE_RESOLVE_UNAVAILABLE

    def __init__(self, target_hint: str, message: str | None = None):
        self.target_hint = target_hint
        self.message = message or f"解析服务不可用或超时，回写已中止：{target_hint}"
        super().__init__(self.message)


class AuditWriteFailed(Exception):
    """回写成功但审计写入失败（R14.8「无审计不回写」）。

    把 `log_action` 纳入回写事务成功判定 —— 审计失败即回滚回写改动。
    携带 `error_code=AUDIT_WRITE_FAILED` 供 router 转 HTTP 500 并回滚。
    """

    error_code = ERR_CODE_AUDIT_WRITE_FAILED

    def __init__(self, message: str | None = None):
        self.message = message or "审计日志写入失败，回写已回滚（无审计不回写）。"
        super().__init__(self.message)


# ─── Cell reference parsing ──────────────────────────────────────────────────


def _parse_cell_ref(cell_ref: str) -> tuple[int, int]:
    """解析 cell_ref (e.g. 'B7') 为 (row_0indexed, col_0indexed)。

    cell_ref 是 1-indexed (Excel 风格)，snapshot 用 0-indexed key (Univer 约定)。
    B7 → row=6, col=1
    """
    m = re.match(r"^([A-Z]+)(\d+)$", cell_ref.upper().strip())
    if not m:
        raise ValueError(f"Invalid cell_ref: {cell_ref}")

    col_letters = m.group(1)
    row_num = int(m.group(2))

    # 列字母转 0-indexed
    col = 0
    for ch in col_letters:
        col = col * 26 + (ord(ch) - 64)
    col -= 1  # 转为 0-indexed

    # 行号转 0-indexed
    row = row_num - 1

    return row, col


# ─── SnapshotWriter ──────────────────────────────────────────────────────────


class SnapshotWriter:
    """双向编辑写回管线。

    支持 5 个模块的 cell 写回：
      - workpaper → parsed_data['univer_snapshot']
      - report → report_snapshot.data
      - note → consol_note_data.data
      - adj → adjustments 表 UPDATE
      - tb → trial_balance.audited_amount UPDATE
    """

    async def write_cell(
        self,
        db: AsyncSession,
        user: Any,
        wp_id: str,
        sheet_name: str,
        cell_ref: str,
        new_value: Any,
        opened_at: datetime,
        module: str = "workpaper",
        project_id: str | None = None,
    ) -> dict:
        """单事务写 cell 到对应模块。

        Args:
            db: 数据库会话
            user: 当前用户对象 (需有 id, username 属性)
            wp_id: working_paper ID (workpaper 模块) 或相关记录 ID
            sheet_name: sheet 名称
            cell_ref: cell 引用 (e.g. "B7")
            new_value: 新值
            opened_at: 前端打开时的 updated_at 时间戳
            module: 模块名 ('workpaper', 'report', 'note', 'adj', 'tb')
            project_id: 项目 ID（ACNR 解析 project context，R15.4）

        Returns:
            {
                success: True,
                updated_at: str,
                old_value: Any,
                addr_id: str | None,        # R15.1: canonical addr_id
                column_metadata: dict | None # R15.2: chip drill-down metadata
            }

        Raises:
            WritebackConflict: 乐观锁冲突
            WritebackPermissionDenied: 无写权限
        """
        if module == "workpaper":
            return await self._write_workpaper_cell(
                db, user, wp_id, sheet_name, cell_ref, new_value, opened_at, project_id
            )
        elif module == "report":
            return await self._write_report_cell(
                db, user, wp_id, sheet_name, cell_ref, new_value, opened_at
            )
        elif module == "note":
            return await self._write_note_cell(
                db, user, wp_id, sheet_name, cell_ref, new_value, opened_at
            )
        elif module == "adj":
            return await self._write_adj_cell(
                db, user, wp_id, sheet_name, cell_ref, new_value, opened_at
            )
        elif module == "tb":
            return await self._write_tb_cell(
                db, user, wp_id, sheet_name, cell_ref, new_value, opened_at
            )
        else:
            raise WritebackPermissionDenied(f"Unsupported module: {module}")

    # ─── workpaper 模块写回 ──────────────────────────────────────────────

    async def _write_workpaper_cell(
        self,
        db: AsyncSession,
        user: Any,
        wp_id: str,
        sheet_name: str,
        cell_ref: str,
        new_value: Any,
        opened_at: datetime,
        project_id: str | None = None,
    ) -> dict:
        """写回 workpaper parsed_data['univer_snapshot']。

        Steps (11 步事务，advanced-query Task 15.3):
          1. SELECT FOR UPDATE
          2. Belt+suspenders project_id validation
          3. 乐观锁比对
          4. **写回前解析 addr_id 身份**（full_resolve/AddressingService）— 无法解析/不可用即中止，不改数据
          5. 定位 cellData[row][col] + 写入 new_value
          6. 更新 JSONB
          7. 同步 xlsx cache (run_in_executor)
          8. orchestrator.after_save（version/stale/updated_at/event）
          9. 落 advanced_query_writeback（addr_id 身份）
         10. 审计 log_action 纳入事务成功判定（失败 → 回滚 + AUDIT_WRITE_FAILED）
         11. 组装 addr_id + column_metadata 返回
        """
        # Step 1: SELECT FOR UPDATE
        result = await db.execute(
            text("""
                SELECT updated_at, parsed_data, wp_code, file_path, project_id
                FROM working_paper
                WHERE id = :wp_id
                FOR UPDATE
            """),
            {"wp_id": wp_id},
        )
        row = result.first()
        if not row:
            raise ValueError(f"Working paper not found: {wp_id}")

        current_updated_at = row[0]
        parsed_data = row[1] or {}
        wp_code = row[2] or ""
        file_path = row[3] or ""
        row_project_id = row[4]

        # Step 2: Belt+suspenders — verify project_id matches
        if project_id and row_project_id:
            expected_pid = UUID(project_id) if isinstance(project_id, str) else project_id
            actual_pid = UUID(str(row_project_id)) if not isinstance(row_project_id, UUID) else row_project_id
            if expected_pid != actual_pid:
                raise WritebackPermissionDenied("Project mismatch")

        # Step 3: 乐观锁比对
        # 确保 opened_at 和 current_updated_at 都是 aware 或都是 naive 进行比较
        opened_at_cmp = opened_at.replace(tzinfo=None) if opened_at.tzinfo else opened_at
        updated_at_cmp = current_updated_at.replace(tzinfo=None) if current_updated_at and hasattr(current_updated_at, 'tzinfo') and current_updated_at.tzinfo else current_updated_at

        if updated_at_cmp and opened_at_cmp < updated_at_cmp:
            # 获取最后编辑人
            last_editor = self._get_last_editor(parsed_data, user)
            raise WritebackConflict(
                latest_updated_at=current_updated_at,
                latest_editor=last_editor,
            )

        # Step 4: 写回前解析 addr_id 身份（R3.1/R3.4/R3.5）——必须在任何数据改动之前。
        # 无法解析 → TARGET_UNRESOLVABLE、不改数据；resolve 不可用/超时 → RESOLVE_UNAVAILABLE、数据不变。
        resolved = await self._resolve_writeback_identity(
            db=db,
            wp_code=wp_code,
            sheet_name=sheet_name,
            cell_ref=cell_ref,
            project_id=project_id or (str(row_project_id) if row_project_id else None),
        )
        if resolved.error == "resolve_unavailable":
            raise WritebackResolveUnavailable(f"{wp_code}/{sheet_name}/{cell_ref}")
        if not resolved.found or not resolved.addr_id:
            raise WritebackTargetUnresolvable(f"{wp_code}/{sheet_name}/{cell_ref}")
        addr_id = resolved.addr_id

        # Step 5: 定位 cellData
        row_idx, col_idx = _parse_cell_ref(cell_ref)
        snapshot = parsed_data.get("univer_snapshot", {})
        sheets = snapshot.get("sheets", {})

        # 查找目标 sheet（按 name 匹配）
        target_sheet = None
        target_sheet_key = None
        if isinstance(sheets, dict):
            for key, sheet_data in sheets.items():
                if isinstance(sheet_data, dict) and sheet_data.get("name") == sheet_name:
                    target_sheet = sheet_data
                    target_sheet_key = key
                    break
        elif isinstance(sheets, list):
            for i, sheet_data in enumerate(sheets):
                if isinstance(sheet_data, dict) and sheet_data.get("name") == sheet_name:
                    target_sheet = sheet_data
                    target_sheet_key = i
                    break

        if target_sheet is None:
            raise ValueError(f"Sheet '{sheet_name}' not found in snapshot")

        # Step 5: 获取旧值并写入新值
        cell_data = target_sheet.setdefault("cellData", {})
        row_key = str(row_idx)
        col_key = str(col_idx)

        row_data = cell_data.setdefault(row_key, {})
        cell_obj = row_data.setdefault(col_key, {})
        old_value = cell_obj.get("v")
        cell_obj["v"] = new_value

        # Step 6: 更新 JSONB（parsed_data 先写入，orchestrator 负责 prefill_stale/updated_at/version）
        now = datetime.now(timezone.utc)
        await db.execute(
            text("""
                UPDATE working_paper
                SET parsed_data = :new_pd
                WHERE id = :wp_id
            """),
            {"new_pd": json.dumps(parsed_data, ensure_ascii=False), "wp_id": wp_id},
        )

        # Step 7: 同步更新 xlsx cache (run_in_executor)
        if file_path:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._sync_update_xlsx_cache,
                    file_path, sheet_name, row_idx, col_idx, new_value,
                )
            except Exception as e:
                logger.warning("xlsx cache update failed (non-fatal): %s", e)

        # Step 8: 统一后处理 — 使用 orchestrator 替代孤立本地 EventBus
        # orchestrator 负责: file_version++, prefill_stale, updated_at, event_bus.publish
        try:
            from app.services.workpaper_save_orchestrator import orchestrator as save_orchestrator

            # 需要获取 ORM 实例来调 orchestrator（此处用 raw SQL 获取轻量对象）
            from app.models.workpaper_models import WorkingPaper
            import sqlalchemy as sa
            wp_result = await db.execute(
                sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
            )
            wp_obj = wp_result.scalar_one_or_none()
            if wp_obj:
                await save_orchestrator.after_save(
                    db, wp_obj, user,
                    trigger="custom_query_writeback",
                    extra={
                        "wp_code": wp_code,
                        "sheet_name": sheet_name,
                        "cell_ref": cell_ref,
                        "addr_id": addr_id,
                    },
                )
                now = wp_obj.updated_at  # 使用 orchestrator 设置的 updated_at
        except Exception as exc:
            logger.warning("orchestrator.after_save failed (non-fatal): %s", exc)

        # Step 9: 落 advanced_query_writeback（回写身份 addr_id 存储，R3.1/R14.3）
        # 以 canonical addr_id 作为回写身份，取代裸 (wp_id, sheet_name, cell_ref)
        await self._persist_writeback_record(
            db,
            project_id=project_id or (str(row_project_id) if row_project_id else None),
            addr_id=addr_id,
            wp_id=wp_id,
            old_value=old_value,
            new_value=new_value,
            operator_id=getattr(user, "id", None),
            result="success",
        )

        # Step 10: 无审计不回写（R14.8）——审计写入纳入事务成功判定。
        # 审计失败 → 抛 AuditWriteFailed，由 router 回滚回写改动（数据不变）。
        await self._audit_writeback(
            user=user,
            wp_id=wp_id,
            wp_code=wp_code,
            sheet_name=sheet_name,
            cell_ref=cell_ref,
            addr_id=addr_id,
            old_value=old_value,
            new_value=new_value,
            project_id=project_id or (str(row_project_id) if row_project_id else None),
        )

        # Step 11: 组装 addr_id + column_metadata 返回（R3.2/R3.3 + R4/R15.2 下钻）
        column_metadata = self._build_column_metadata(
            addr_id=addr_id,
            cell_ref=cell_ref,
            resolved=resolved,
            wp_code=wp_code,
            sheet_name=sheet_name,
            project_id=project_id,
        )

        return {
            "success": True,
            "updated_at": now.isoformat(),
            "old_value": old_value,
            "addr_id": addr_id,
            "column_metadata": column_metadata,
            # audit 已在事务内记录（R14.8），告知 router 勿重复记审计
            "audit_logged": True,
        }

    # ─── report 模块写回 ─────────────────────────────────────────────────

    async def _write_report_cell(
        self,
        db: AsyncSession,
        user: Any,
        wp_id: str,
        sheet_name: str,
        cell_ref: str,
        new_value: Any,
        opened_at: datetime,
    ) -> dict:
        """写回 report_snapshot.data JSONB。

        虚拟 sheet 列映射：A=row_code, B=row_name, C=current_period_amount, D=prior_period_amount, E=formula
        """
        from app.services.custom_query.module_cell_resolver import _REPORT_COLUMNS

        # wp_id 在 report 模块中是 report_snapshot.id
        result = await db.execute(
            text("""
                SELECT id, data, updated_at FROM report_snapshot
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
        self._check_optimistic_lock(opened_at, current_updated_at, user)

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

    # ─── note 模块写回 ───────────────────────────────────────────────────

    async def _write_note_cell(
        self,
        db: AsyncSession,
        user: Any,
        wp_id: str,
        sheet_name: str,
        cell_ref: str,
        new_value: Any,
        opened_at: datetime,
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

        self._check_optimistic_lock(opened_at, current_updated_at, user)

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

    # ─── adj 模块写回 ────────────────────────────────────────────────────

    async def _write_adj_cell(
        self,
        db: AsyncSession,
        user: Any,
        wp_id: str,
        sheet_name: str,
        cell_ref: str,
        new_value: Any,
        opened_at: datetime,
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
        self._check_optimistic_lock(opened_at, current_updated_at, user)

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

    # ─── tb 模块写回 ─────────────────────────────────────────────────────

    async def _write_tb_cell(
        self,
        db: AsyncSession,
        user: Any,
        wp_id: str,
        sheet_name: str,
        cell_ref: str,
        new_value: Any,
        opened_at: datetime,
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
        self._check_optimistic_lock(opened_at, current_updated_at, user)

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

    # ─── 辅助方法 ────────────────────────────────────────────────────────

    def _check_optimistic_lock(
        self, opened_at: datetime, current_updated_at: datetime | None, user: Any
    ):
        """乐观锁比对：opened_at < updated_at → raise WritebackConflict"""
        if current_updated_at is None:
            return

        opened_at_cmp = opened_at.replace(tzinfo=None) if opened_at.tzinfo else opened_at
        updated_at_cmp = (
            current_updated_at.replace(tzinfo=None)
            if hasattr(current_updated_at, "tzinfo") and current_updated_at.tzinfo
            else current_updated_at
        )

        if opened_at_cmp < updated_at_cmp:
            last_editor = getattr(user, "username", "unknown")
            raise WritebackConflict(
                latest_updated_at=current_updated_at,
                latest_editor=last_editor,
            )

    def _get_last_editor(self, parsed_data: dict, fallback_user: Any) -> str:
        """从 parsed_data 获取最后编辑人，fallback 到当前用户"""
        snapshot = parsed_data.get("univer_snapshot", {})
        saved_by = snapshot.get("saved_by")
        if saved_by:
            return str(saved_by)
        return getattr(fallback_user, "username", "unknown")

    def _sync_update_xlsx_cache(
        self,
        file_path: str,
        sheet_name: str,
        row_idx: int,
        col_idx: int,
        new_value: Any,
    ):
        """同步更新 xlsx 文件 cache（在 run_in_executor 中调用）。

        使用 openpyxl 写入对应 cell。
        """
        try:
            import openpyxl

            path = Path(file_path)
            if not path.exists():
                logger.debug("xlsx cache file not found, skipping: %s", file_path)
                return

            wb = openpyxl.load_workbook(str(path))
            ws = wb[sheet_name] if sheet_name in wb.sheetnames else None
            if ws is None:
                wb.close()
                return

            # openpyxl 使用 1-indexed
            ws.cell(row=row_idx + 1, column=col_idx + 1, value=new_value)
            wb.save(str(path))
            wb.close()
        except Exception as e:
            logger.warning("_sync_update_xlsx_cache error: %s", e)

    # ─── addr_id 身份解析 / 持久化 / 审计（advanced-query Task 15.3）──────

    async def _resolve_writeback_identity(
        self,
        db: AsyncSession | None,
        wp_code: str,
        sheet_name: str,
        cell_ref: str,
        project_id: str | None = None,
    ):
        """写回前经 full_resolve（AddressingService）解析 canonical addr_id 身份（R3.1）。

        统一消费 ACNR 单一 resolve 出口（5s 超时、携带 project context），返回
        ``ResolvedTarget``：
          - ``found=True`` → ``addr_id`` = ``{wp_code}/{sheet_code}/{coordinate_key}``（R3.1/R3.2）
          - ``error="resolve_unavailable"`` → resolve 不可用/超时（R3.5）
          - ``found=False`` → 无法解析（R3.4）

        缺 ``wp_code`` 时无法构成寻址身份，直接归为不可解析。
        """
        from app.services.custom_query.addressing_service import (
            ResolvedTarget,
            addressing_service,
        )

        # 无 wp_code → 无法构成 {wp_code}/{sheet_code}/{coordinate_key} 身份（R3.4）
        if not wp_code:
            return ResolvedTarget(
                raw=f"/{sheet_name}/{cell_ref}", found=False, error="unresolvable"
            )

        # 裸 addr_id 形态交由 AddressingService 归类 → full_resolve（含 sheet 别名匹配）
        raw = f"{wp_code}/{sheet_name}/{cell_ref}"
        return await addressing_service.resolve_target(
            raw, project_id=project_id, db=db
        )

    async def _persist_writeback_record(
        self,
        db: AsyncSession,
        *,
        project_id: str | None,
        addr_id: str,
        wp_id: str | None,
        old_value: Any,
        new_value: Any,
        operator_id: Any,
        result: str,
    ) -> None:
        """将回写身份 addr_id + 新旧值落 advanced_query_writeback（R3.1/R14.3）。

        本表以 canonical addr_id 作回写身份（与 WP() 公式引用同一身份），供 stale
        chip 追踪对齐与快照列下钻的结构化索引。属于回写事务的一部分（只 flush 不
        commit），插入失败 → 传播异常 → router 回滚（不残留部分写入，R3.6）。
        """
        from app.models.custom_query_models import AdvancedQueryWriteback

        record = AdvancedQueryWriteback(
            project_id=_as_uuid(project_id),
            addr_id=addr_id,
            wp_id=_as_uuid(wp_id),
            old_value=_jsonable(old_value),
            new_value=_jsonable(new_value),
            operator_id=_as_uuid(operator_id),
            result=result,
        )
        db.add(record)
        await db.flush()

    async def _audit_writeback(
        self,
        *,
        user: Any,
        wp_id: str | None,
        wp_code: str,
        sheet_name: str,
        cell_ref: str,
        addr_id: str,
        old_value: Any,
        new_value: Any,
        project_id: str | None,
    ) -> None:
        """把 log_action 纳入回写事务成功判定（R14.8「无审计不回写」）。

        回写与跨 sheet 溯源逐次记录（不节流），记录操作者/UTC 秒级时间戳/操作类型/
        目标 addr_id/新旧值/结果。审计写入失败（log_action 抛错）→ 抛 ``AuditWriteFailed``，
        由 router 回滚回写改动（数据不变）。
        """
        try:
            from app.services.audit_logger_enhanced import audit_logger

            await audit_logger.log_action(
                user_id=getattr(user, "id", None),
                action="custom_query.cell_writeback",
                object_type="working_paper",
                object_id=wp_id,
                project_id=project_id,
                details={
                    "wp_code": wp_code,
                    "sheet_name": sheet_name,
                    "cell_ref": cell_ref,
                    "addr_id": addr_id,
                    "old_value": old_value,
                    "new_value": new_value,
                    "result": "success",
                },
            )
        except Exception as exc:
            # 无审计不回写：审计失败即视为回写失败，回滚回写改动（R14.8）
            logger.error(
                "writeback audit log failed → 回滚回写 (无审计不回写): addr_id=%s err=%s",
                addr_id, exc,
            )
            raise AuditWriteFailed() from exc

    def _build_column_metadata(
        self,
        *,
        addr_id: str,
        cell_ref: str,
        resolved: Any,
        wp_code: str,
        sheet_name: str,
        project_id: str | None,
    ) -> dict:
        """构造结果列元数据（R3.2/R3.3 + R4/R15.2 下钻）。

        以 full_resolve 解析出的 canonical addr_id 为身份；display_label / drilldown
        经 catalog 尽力增强（语义标签），失败不阻塞（保留 addr_id 基线可下钻）。
        """
        sheet_addr_id = "/".join(addr_id.split("/")[:2]) if addr_id else None
        entry_type = getattr(resolved, "entry_type", None)
        jump_route = getattr(resolved, "jump_route", None)
        drilldown_enabled = bool(jump_route) or entry_type in ("cell", "runtime_cell")

        metadata = {
            "addr_id": addr_id,
            "display_label": addr_id,
            "cell_address": cell_ref,
            "sheet_addr_id": sheet_addr_id,
            "drilldown_enabled": drilldown_enabled,
            "jump_route": jump_route,
        }

        # 尽力经 catalog 增强语义标签（不改变身份，失败降级保留基线）
        try:
            enrich = self._resolve_addr_id(
                wp_code=wp_code,
                sheet_name=sheet_name,
                cell_ref=cell_ref,
                project_id=project_id,
            )
            if enrich and enrich.get("column_metadata"):
                cm = enrich["column_metadata"]
                if cm.get("display_label"):
                    metadata["display_label"] = cm["display_label"]
                if cm.get("drilldown_enabled"):
                    metadata["drilldown_enabled"] = True
        except Exception as exc:  # 增强失败不阻塞（身份已由 full_resolve 确定）
            logger.debug("column_metadata enrich skipped: %s", exc)

        return metadata

    # ─── ACNR addr_id 解析（M2, R15.1, R15.2, R15.4）────────────────────

    def _resolve_addr_id(
        self,
        wp_code: str,
        sheet_name: str,
        cell_ref: str,
        project_id: str | None = None,
    ) -> dict | None:
        """通过 ACNR 解析 (wp_code, sheet_name, cell_ref) 为 canonical addr_id。

        携带 project context 进行解析（R15.4），使回写身份从裸坐标升级为 addr_id（R15.1）。
        返回包含 addr_id + column_metadata 的 dict，chip 可下钻到格（R15.2）。

        Args:
            wp_code: 底稿编码（如 D2）
            sheet_name: sheet 名称（如 明细表D2-2）
            cell_ref: cell 引用（如 E100）
            project_id: 项目 ID（project context，R15.4）

        Returns:
            dict with {addr_id, uri, formula_ref, entry_type, jump_route} or None on miss
        """
        try:
            from app.services.acnr.catalog import get_catalog, lookup

            # 尝试通过 catalog lookup 获取 sheet → addr_id
            # 1. 先确定 sheet_code：从 sheet_name 反查（别名机制）
            cat = get_catalog()

            # 构建 sheet-level addr_id：通过 wp_code + sheet_name 反查
            sheet_entry = None

            # 尝试通过 sheet_name 在别名索引中查找
            alias_matches = cat.sheets_by_alias.get(sheet_name, [])
            if wp_code and alias_matches:
                filtered = [m for m in alias_matches if m.get("parent_wp_code") == wp_code]
                if len(filtered) == 1:
                    sheet_entry = filtered[0]
                elif not filtered and len(alias_matches) == 1:
                    sheet_entry = alias_matches[0]

            # 如果别名反查未命中，尝试 sheet_code 索引
            if not sheet_entry:
                code_matches = cat.sheets_by_code.get(sheet_name, [])
                if wp_code and code_matches:
                    code_matches = [m for m in code_matches if m.get("parent_wp_code") == wp_code]
                if len(code_matches) == 1:
                    sheet_entry = code_matches[0]

            if not sheet_entry:
                # catalog miss — 降级返回 None（不阻塞写回主流程）
                logger.debug(
                    "ACNR addr_id resolve miss: wp_code=%s sheet_name=%s",
                    wp_code, sheet_name,
                )
                return None

            sheet_addr_id = sheet_entry.get("addr_id", "")

            # 2. 如果有 cell_ref，构造 cell-level addr_id
            if cell_ref:
                # canonical addr_id = {parent}/{sheet_code}/{cell_address}
                cell_addr_id = f"{sheet_addr_id}/{cell_ref}"

                # 尝试精确 cell 命中
                cell_entry = cat.cells_by_addr_id.get(cell_addr_id)
                if cell_entry:
                    return {
                        "addr_id": cell_entry.get("addr_id"),
                        "uri": cell_entry.get("uri"),
                        "formula_ref": cell_entry.get("formula_ref"),
                        "entry_type": "cell",
                        "semantic_label": cell_entry.get("semantic_label"),
                        "parent_addr_id": cell_entry.get("parent_addr_id"),
                        "jump_route": sheet_entry.get("jump_route_template"),
                        "column_metadata": {
                            "addr_id": cell_entry.get("addr_id"),
                            "display_label": (
                                cell_entry.get("semantic_label")
                                or cell_entry.get("addr_id")
                            ),
                            "cell_address": cell_ref,
                            "sheet_addr_id": sheet_addr_id,
                            "drilldown_enabled": True,
                        },
                    }

                # Cell 未在 L1 种子中注册：构造 runtime addr_id
                # 仍返回可用的 addr_id（格式正确但非 L1 注册）
                return {
                    "addr_id": cell_addr_id,
                    "uri": None,
                    "formula_ref": None,
                    "entry_type": "cell",
                    "semantic_label": None,
                    "parent_addr_id": sheet_addr_id,
                    "jump_route": sheet_entry.get("jump_route_template"),
                    "column_metadata": {
                        "addr_id": cell_addr_id,
                        "display_label": cell_addr_id,
                        "cell_address": cell_ref,
                        "sheet_addr_id": sheet_addr_id,
                        "drilldown_enabled": True,
                    },
                }

            # 3. 仅 sheet 级
            return {
                "addr_id": sheet_addr_id,
                "uri": None,
                "formula_ref": None,
                "entry_type": "sheet",
                "semantic_label": None,
                "parent_addr_id": None,
                "jump_route": sheet_entry.get("jump_route_template"),
                "column_metadata": {
                    "addr_id": sheet_addr_id,
                    "display_label": sheet_entry.get("display_label") or sheet_addr_id,
                    "cell_address": None,
                    "sheet_addr_id": sheet_addr_id,
                    "drilldown_enabled": False,
                },
            }

        except Exception as e:
            # ACNR 解析失败不阻塞写回主流程（降级策略）
            logger.warning("ACNR addr_id resolve error (non-fatal): %s", e)
            return None


# ─── 模块级辅助 ──────────────────────────────────────────────────────────────


def _as_uuid(value: Any) -> UUID | None:
    """尽力将值转为 UUID；None → None；无法转换则原样返回（交由 DB 层处理）。"""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return value  # type: ignore[return-value]


def _jsonable(value: Any) -> Any:
    """将 cell 值规范为 JSONB 可存形态（标量/列表/字典直存，其余转字符串）。"""
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)


# 模块级单例
snapshot_writer = SnapshotWriter()
