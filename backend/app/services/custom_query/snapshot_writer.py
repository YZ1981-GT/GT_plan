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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.custom_query import snapshot_writer_addr_id as _addr
from app.services.custom_query import snapshot_writer_modules as _mod

# 共享定义（错误码 / 异常 / cell_ref 解析）实现在 snapshot_writer_shared —— 伴生模块
# 也要用它们，放在本文件会造成循环导入。此处 re-export：既有
# `from ...snapshot_writer import WritebackConflict` 的调用方与测试不受影响
# （同一对象，isinstance / except 判定不变）。
from app.services.custom_query.snapshot_writer_shared import (  # noqa: F401  (re-export)
    ERR_CODE_AUDIT_WRITE_FAILED,
    ERR_CODE_RESOLVE_UNAVAILABLE,
    ERR_CODE_TARGET_UNRESOLVABLE,
    AuditWriteFailed,
    WritebackConflict,
    WritebackPermissionDenied,
    WritebackResolveUnavailable,
    WritebackTargetUnresolvable,
    parse_cell_ref as _parse_cell_ref,
)

logger = logging.getLogger(__name__)


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
        if isinstance(sheets, dict):
            for sheet_data in sheets.values():
                if isinstance(sheet_data, dict) and sheet_data.get("name") == sheet_name:
                    target_sheet = sheet_data
                    break
        elif isinstance(sheets, list):
            for i, sheet_data in enumerate(sheets):
                if isinstance(sheet_data, dict) and sheet_data.get("name") == sheet_name:
                    target_sheet = sheet_data
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
        #
        # 非致命，但**不能静默**：这里挂掉意味着 file_version 没++、prefill_stale 没标、
        # WORKPAPER_SAVED 没发 —— 下游 cross_ref / stale / SSE 全不触发，而用户看到的
        # 是「保存成功」。原实现把整块（含 ORM select）吞成一条 WARNING，正是最贵的那类
        # fail-open：接线错了也表现为「静默成功」。故改为记 ERROR 并在返回体带 warnings。
        downstream_warnings: list[str] = []
        try:
            from app.services.workpaper_save_orchestrator import orchestrator as save_orchestrator

            # 需要获取 ORM 实例来调 orchestrator（此处用 raw SQL 获取轻量对象）
            from app.models.workpaper_models import WorkingPaper
            import sqlalchemy as sa
            wp_result = await db.execute(
                sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
            )
            wp_obj = wp_result.scalar_one_or_none()
            if wp_obj is None:
                # 我们刚刚 SELECT ... FOR UPDATE 过这一行，此处取不到属真实异常，
                # 不是「正常情况」——原实现连这条都不记，联动静默失效无从发现。
                logger.error(
                    "orchestrator 前置取 ORM 实例失败：working_paper %s 存在但 ORM 查不到，"
                    "下游联动（cross_ref/stale/SSE）未触发",
                    wp_id,
                )
                downstream_warnings.append("下游联动未触发：底稿 ORM 实例不可用")
            else:
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
            logger.error(
                "orchestrator.after_save 失败（回写已落库，但下游联动未触发）: %s",
                exc,
                exc_info=True,
            )
            downstream_warnings.append(f"下游联动未触发：{exc}")

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

        payload: dict = {
            "success": True,
            "updated_at": now.isoformat(),
            "old_value": old_value,
            "addr_id": addr_id,
            "column_metadata": column_metadata,
            # audit 已在事务内记录（R14.8），告知 router 勿重复记审计
            "audit_logged": True,
        }
        # 下游联动没跑起来时必须让调用方看得见（Step 8 非致命但不静默）
        if downstream_warnings:
            payload["warnings"] = downstream_warnings
        return payload
    # ─── 非 workpaper 模块写回（实现在 snapshot_writer_modules）──────────
    # 四个模块写回都是「SELECT FOR UPDATE → 乐观锁 → 定位虚拟 sheet 列 → UPDATE」的
    # 同构流程，与 workpaper 的 11 步事务无关，故下沉到伴生模块。类上保留同名薄委托：
    # 既有测试用 hasattr 检查模块分派、并用实例赋值做替身，搬走会让两者失效。

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
        """写回 report_snapshot.data JSONB（委托 snapshot_writer_modules）。"""
        return await _mod.write_report_cell(
            db, user, wp_id, sheet_name, cell_ref, new_value, opened_at,
            check_lock=self._check_optimistic_lock,
        )
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
        """写回 consol_note_data.data JSONB（委托 snapshot_writer_modules）。"""
        return await _mod.write_note_cell(
            db, user, wp_id, sheet_name, cell_ref, new_value, opened_at,
            check_lock=self._check_optimistic_lock,
        )
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
        """写回 adjustments 表（委托 snapshot_writer_modules）。"""
        return await _mod.write_adj_cell(
            db, user, wp_id, sheet_name, cell_ref, new_value, opened_at,
            check_lock=self._check_optimistic_lock,
        )
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
        """写回 trial_balance.audited_amount（委托 snapshot_writer_modules）。"""
        return await _mod.write_tb_cell(
            db, user, wp_id, sheet_name, cell_ref, new_value, opened_at,
            check_lock=self._check_optimistic_lock,
        )

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
    # 实现在 snapshot_writer_addr_id（纯查 catalog、不碰 self），类上留薄委托：
    # 既有测试直接调 writer._resolve_addr_id(...) 并做实例赋值替身。

    def _resolve_addr_id(
        self,
        wp_code: str,
        sheet_name: str,
        cell_ref: str,
        project_id: str | None = None,
    ) -> dict | None:
        """(wp_code, sheet_name, cell_ref) → canonical addr_id（委托伴生模块）。"""
        return _addr.resolve_addr_id(wp_code, sheet_name, cell_ref, project_id)


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
