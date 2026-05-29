"""C 类底稿 → disclosure_notes 模块单向同步服务

按 design §12.1 推荐选项 A：底稿是编辑入口，disclosure_notes 模块仅作展示+独立编辑（向后兼容）。
当用户在 C 类附注底稿 sheet 保存数据时，自动 push 到 disclosure_notes 表对应 section。

Validates: Requirements 3.11.5 §4.2（附注双源问题）+ design §12.1
Validates: Requirements US-3（C 类底稿 → 附注自动同步）
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User
from app.models.report_models import (
    ContentType,
    DisclosureNote,
    NoteStatus,
    SourceTemplate,
)
from app.services.conflict_resolution_service import (
    _check_manual_override_before_propagate,
)

logger = logging.getLogger(__name__)


# ─── Conflict Error ──────────────────────────────────────────────────────────


class ConflictError(Exception):
    """附注侧有更新的手动编辑，与底稿同步冲突。"""

    def __init__(self, note_id: UUID, note_updated: datetime, last_sync_at: datetime | None = None):
        self.note_id = note_id
        self.note_updated = note_updated
        self.last_sync_at = last_sync_at
        super().__init__(
            f"Conflict: note {note_id} updated at {note_updated}, "
            f"last sync at {last_sync_at}"
        )

def _detect_manual_override(table_data: dict[str, Any] | None) -> bool:
    """读取 disclosure_note.table_data 中的 ``_manual_override`` 标记。

    约定字段位置（任一为 True 即视为 manual_override）：
      1. ``table_data['_manual_override']``           顶层标记
      2. ``table_data['sub_table_data']['_manual_override']``  子表标记

    无字段或不为 True 时返回 False（默认 allow，不影响既有写入路径）。
    """
    if not isinstance(table_data, dict):
        return False
    if table_data.get("_manual_override") is True:
        return True
    sub = table_data.get("sub_table_data")
    if isinstance(sub, dict) and sub.get("_manual_override") is True:
        return True
    return False


def _count_rows_synced(sub_table_data: dict[str, list[dict]] | None) -> int:
    """统计 sub_table_data 中所有子表行数总和。"""
    if not sub_table_data:
        return 0
    total = 0
    for rows in sub_table_data.values():
        if isinstance(rows, list):
            total += len(rows)
    return total


def _derive_section_title(section_id: str) -> str:
    """从 section_id 派生默认标题（用于新建场景）。

    Examples:
        "五-1-1 应收账款" → "应收账款"
        "五-1-1" → "五-1-1"
    """
    if not section_id:
        return ""
    parts = section_id.strip().split(maxsplit=1)
    if len(parts) == 2:
        return parts[1]
    return section_id


def _derive_year(payload_year: int | None) -> int:
    """优先使用 payload 中的 year，否则取当前年（兜底）。"""
    if payload_year and isinstance(payload_year, int):
        return payload_year
    return datetime.now(timezone.utc).year


async def sync_from_workpaper(
    db: AsyncSession,
    project_id: UUID,
    *,
    wp_id: UUID,
    sheet_name: str,
    section_id: str,
    sub_table_data: dict[str, list[dict]],
    current_standard: str,
    user: User,
    year: int | None = None,
    propagation_origin: Literal["user_edit", "system_recompute"] = "user_edit",
) -> dict[str, Any]:
    """C 类底稿 sheet 保存时，将 sub_table_data 同步到 disclosure_notes 模块对应 section。

    行为：
    - 查 disclosure_notes WHERE (project_id, year, note_section=section_id, is_deleted=false)
    - 已存在：更新 table_data（merge sub_table_data）+ 同步标记
    - 不存在：新建一条记录（status=draft，content_type=table）+ 同步标记

    manual_override 守卫（Req 7 AC 1/2/6/7）：
    - 如果目标 disclosure_note 当前 table_data 带有 ``_manual_override=True`` 标记，
      调用 ``_check_manual_override_before_propagate`` hook：
        * propagation_origin='user_edit'   → 入队 cross_module_conflict 并跳过 table_data 更新
        * propagation_origin='system_recompute' → auto_resolve 留痕并继续写入
    - 如果目标无 manual_override，正常写入（保持既有行为，不影响兼容性）

    Returns:
        {
            "success": True,
            "section_id": str,
            "synced_at": ISO timestamp,
            "rows_synced": int,
            "created": bool,             # 本次是否新建（True=create，False=update）
            "blocked_by_manual_override": bool,  # 是否被 manual_override 拦截（True=table_data 未更新）
        }
    """
    if not section_id or not section_id.strip():
        raise ValueError("section_id 不能为空")
    section_id = section_id.strip()

    target_year = _derive_year(year)
    now = datetime.now(timezone.utc)
    rows_synced = _count_rows_synced(sub_table_data)

    # ─── 查现有记录 ───────────────────────────────────────────────────
    stmt = sa.select(DisclosureNote).where(
        DisclosureNote.project_id == project_id,
        DisclosureNote.year == target_year,
        DisclosureNote.note_section == section_id,
        DisclosureNote.is_deleted == sa.false(),
    )
    result = await db.execute(stmt)
    note = result.scalar_one_or_none()

    # 构建合并后的 table_data
    # 约定：将 C sheet 的 sub_table_data 整体写入 table_data["sub_table_data"]，
    #     并保留 _source / _current_standard / _last_sync_wp / _last_sync_sheet 元数据
    new_table_data: dict[str, Any] = dict(note.table_data) if note and note.table_data else {}
    new_table_data["sub_table_data"] = dict(sub_table_data or {})
    new_table_data["_source"] = "workpaper"
    new_table_data["_current_standard"] = current_standard
    new_table_data["_last_sync_wp_id"] = str(wp_id)
    new_table_data["_last_sync_sheet"] = sheet_name
    new_table_data["_last_sync_at"] = now.isoformat()

    created = False
    blocked_by_manual_override = False

    if note is None:
        # ─── 新建 ─────────────────────────────────────────────────────
        # 从 current_standard（如 "soe_standalone" / "listed_standalone"）派生 source_template
        source_template_value: SourceTemplate | None = None
        if current_standard:
            cs = current_standard.lower()
            if cs.startswith("listed"):
                source_template_value = SourceTemplate.listed
            elif cs.startswith("soe"):
                source_template_value = SourceTemplate.soe
        note = DisclosureNote(
            project_id=project_id,
            year=target_year,
            note_section=section_id,
            section_title=_derive_section_title(section_id),
            content_type=ContentType.table,
            table_data=new_table_data,
            source_template=source_template_value,
            status=NoteStatus.draft,
            last_sync_source="workpaper",
            last_sync_wp_id=wp_id,
            last_sync_at=now,
            last_sync_user_id=user.id,
            updated_by=user.id,
        )
        db.add(note)
        created = True
        logger.info(
            "wp_disclosure_sync: created new disclosure_note "
            "project=%s section=%s wp_id=%s rows=%d",
            project_id, section_id, wp_id, rows_synced,
        )
    else:
        # ─── 更新 ─────────────────────────────────────────────────────
        # manual_override 守卫：写入前先看目标是否有 _manual_override 标记
        is_manual_override = _detect_manual_override(note.table_data)
        if is_manual_override:
            decision = await _check_manual_override_before_propagate(
                db=db,
                project_id=project_id,
                source_module="workpaper",
                source_id=wp_id,
                target_module="disclosure",
                target_id=note.id,
                target_field=f"sub_table_data.{section_id}",
                new_value=sheet_name,  # 上游标识（具体值由 sub_table_data 表达，过长不入审计 details）
                current_value=None,
                is_manual_override=True,
                user_id=user.id,
                propagation_origin=propagation_origin,
            )
            if decision == "block_enqueued":
                # 拦截：跳过 table_data 更新，仅记录 last_sync_at（说明同步已被尝试但被守卫拦下）
                blocked_by_manual_override = True
                note.last_sync_source = "workpaper"
                note.last_sync_wp_id = wp_id
                note.last_sync_at = now
                note.last_sync_user_id = user.id
                logger.info(
                    "wp_disclosure_sync: BLOCKED by manual_override "
                    "id=%s section=%s wp_id=%s",
                    note.id, section_id, wp_id,
                )
                await db.commit()
                return {
                    "success": True,
                    "section_id": section_id,
                    "synced_at": now.isoformat(),
                    "rows_synced": 0,
                    "created": False,
                    "blocked_by_manual_override": True,
                }
            # decision in ('auto_resolved', 'allow') → 继续走更新分支
        note.table_data = new_table_data
        note.last_sync_source = "workpaper"
        note.last_sync_wp_id = wp_id
        note.last_sync_at = now
        note.last_sync_user_id = user.id
        note.updated_by = user.id
        note.updated_at = now
        logger.info(
            "wp_disclosure_sync: updated disclosure_note "
            "id=%s section=%s wp_id=%s rows=%d",
            note.id, section_id, wp_id, rows_synced,
        )

    await db.commit()

    return {
        "success": True,
        "section_id": section_id,
        "synced_at": now.isoformat(),
        "rows_synced": rows_synced,
        "created": created,
        "blocked_by_manual_override": blocked_by_manual_override,
    }


# ─── US-3: HTML 路径同步服务类 ────────────────────────────────────────────────


class WpDisclosureSyncService:
    """C 类底稿 → disclosure_notes 同步服务（HTML 渲染器路径）。

    Validates: Requirements US-3（C 类底稿 → 附注自动同步）
    """

    async def sync_from_html(
        self,
        db: AsyncSession,
        wp_id: UUID,
        sheet_name: str,
        sub_table_data: dict,
        *,
        project_id: UUID,
        user: User,
        force: bool = False,
    ) -> dict[str, Any]:
        """从 HTML 渲染器的 C 类底稿同步到 disclosure_notes。

        Steps:
        1. 查 wp_code → 映射到 disclosure_notes.section_id
        2. 读 disclosure_notes 当前值
        3. 冲突检测（除非 force=True）
        4. 写入 table_data + is_stale=False
        5. 审计日志
        6. SSE 通知

        Args:
            db: async DB session
            wp_id: 底稿 ID
            sheet_name: C 类附注 sheet 名
            sub_table_data: 子表数据
            project_id: 项目 ID
            user: 当前用户
            force: 强制覆盖（跳过冲突检测）

        Returns:
            同步结果 dict

        Raises:
            ConflictError: 附注侧有更新的手动编辑
        """
        now = datetime.now(timezone.utc)

        # 1. 查映射：通过 sheet_name 推导 section_id
        mapping = await self._get_section_mapping(db, wp_id, sheet_name)
        if not mapping:
            logger.debug(
                "sync_from_html: no mapping for wp_id=%s sheet=%s, skip",
                wp_id, sheet_name,
            )
            return {
                "success": True,
                "synced": False,
                "reason": "no_mapping",
            }

        section_id = mapping["section_id"]
        last_sync_at = mapping.get("last_sync_at")

        # 2. 读 disclosure_notes 当前值
        note = await self._get_note(db, project_id, section_id)

        if note is None:
            # 无现有记录 → 新建
            note = DisclosureNote(
                project_id=project_id,
                year=now.year,
                note_section=section_id,
                section_title=_derive_section_title(section_id),
                content_type=ContentType.table,
                table_data={"sub_table_data": sub_table_data},
                status=NoteStatus.draft,
                is_stale=False,
                last_sync_source="workpaper_html",
                last_sync_wp_id=wp_id,
                last_sync_at=now,
                last_sync_user_id=user.id,
                updated_by=user.id,
            )
            db.add(note)
            await db.flush()
            try:
                await self._write_audit_log(db, "disclosure_sync_create", wp_id, section_id, user)
            except Exception as exc:
                logger.warning("Audit log write failed (non-blocking): %s", exc)
            self._broadcast_synced(project_id, section_id)
            await db.commit()
            return {
                "success": True,
                "synced": True,
                "section_id": section_id,
                "synced_at": now.isoformat(),
                "created": True,
            }

        # 3. 冲突检测
        if not force and last_sync_at and note.updated_at:
            if note.updated_at > last_sync_at:
                raise ConflictError(
                    note_id=note.id,
                    note_updated=note.updated_at,
                    last_sync_at=last_sync_at,
                )

        # 4. 写入（原子操作）
        existing_table_data = dict(note.table_data) if note.table_data else {}
        existing_table_data["sub_table_data"] = sub_table_data
        existing_table_data["_source"] = "workpaper_html"
        existing_table_data["_last_sync_wp_id"] = str(wp_id)
        existing_table_data["_last_sync_sheet"] = sheet_name
        existing_table_data["_last_sync_at"] = now.isoformat()

        note.table_data = existing_table_data
        note.is_stale = False
        note.last_sync_source = "workpaper_html"
        note.last_sync_wp_id = wp_id
        note.last_sync_at = now
        note.last_sync_user_id = user.id
        note.updated_by = user.id
        note.updated_at = now

        # 5. 审计日志（失败不阻断主流程）
        try:
            await self._write_audit_log(db, "disclosure_sync_update", wp_id, section_id, user)
        except Exception as exc:
            logger.warning("Audit log write failed (non-blocking): %s", exc)

        # 6. SSE 通知
        self._broadcast_synced(project_id, section_id)

        await db.commit()

        return {
            "success": True,
            "synced": True,
            "section_id": section_id,
            "synced_at": now.isoformat(),
            "created": False,
        }

    async def _get_section_mapping(
        self, db: AsyncSession, wp_id: UUID, sheet_name: str
    ) -> dict[str, Any] | None:
        """查 wp_id + sheet_name → section_id 映射。

        策略：查 disclosure_notes 中 last_sync_wp_id = wp_id 且
        table_data._last_sync_sheet = sheet_name 的记录。
        如果找不到，尝试从 sheet_name 推导 section_id（C 类 sheet 命名约定）。
        """
        # 方式 1：查已有同步记录
        stmt = sa.select(DisclosureNote).where(
            DisclosureNote.last_sync_wp_id == wp_id,
            DisclosureNote.is_deleted == sa.false(),
        )
        result = await db.execute(stmt)
        notes = result.scalars().all()

        for n in notes:
            td = n.table_data or {}
            if td.get("_last_sync_sheet") == sheet_name:
                return {
                    "section_id": n.note_section,
                    "last_sync_at": n.last_sync_at,
                }

        # 方式 2：从 sheet_name 推导（C 类 sheet 命名约定：如 "应收账款附注C" → "五-1-1 应收账款"）
        # 简化：用 sheet_name 作为 section_id 查找
        stmt2 = sa.select(DisclosureNote).where(
            DisclosureNote.note_section.ilike(f"%{sheet_name.replace('附注C', '').replace('附注', '')}%"),
            DisclosureNote.is_deleted == sa.false(),
        ).limit(1)
        result2 = await db.execute(stmt2)
        note2 = result2.scalar_one_or_none()
        if note2:
            return {
                "section_id": note2.note_section,
                "last_sync_at": note2.last_sync_at,
            }

        return None

    async def _get_note(
        self, db: AsyncSession, project_id: UUID, section_id: str
    ) -> DisclosureNote | None:
        """读 disclosure_notes 当前值。"""
        stmt = sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.note_section == section_id,
            DisclosureNote.is_deleted == sa.false(),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _write_audit_log(
        self, db: AsyncSession, action: str, wp_id: UUID, section_id: str, user: User
    ) -> None:
        """写入审计日志。"""
        try:
            from app.models.audit_log_models import AuditLogEntry

            log_entry = AuditLogEntry(
                user_id=user.id,
                action_type=action,
                object_type="disclosure_note",
                object_id=None,
                payload={
                    "wp_id": str(wp_id),
                    "section_id": section_id,
                    "source": "workpaper_html",
                },
            )
            db.add(log_entry)
        except Exception as exc:
            # 审计日志写入失败不阻断主流程
            logger.warning("Failed to write audit log: %s", exc)

    def _broadcast_synced(self, project_id: UUID, section_id: str) -> None:
        """发布 note.synced SSE 事件（非阻塞）。"""
        try:
            from app.services.event_bus import event_bus

            event_bus.broadcast_raw(
                event_type="note.synced",
                extra={
                    "project_id": str(project_id),
                    "section_id": section_id,
                },
            )
        except Exception as exc:
            logger.warning("Failed to broadcast note.synced SSE: %s", exc)


# ─── Module-level singleton ──────────────────────────────────────────────────

wp_disclosure_sync_service = WpDisclosureSyncService()
