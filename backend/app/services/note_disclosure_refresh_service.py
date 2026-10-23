"""附注从披露表刷新服务。

数据流：底稿披露表（由前端 buildXSyncPayload 同步写入 disclosure_notes.table_data）
       → 本服务读取已保存的 sub_table_data → 标记 stale 清除 / 触发下游。

**不重建 sub_table_data**（那是 69 个前端 payload builder 的职责）。
本服务读取它们的产物，确保附注侧的 _source / stale 标记 / 同步指纹正确。

当 WORKPAPER_SAVED 事件触发时：
1. 按 wp_code 查 note_workpaper_sync_registry → 确定目标附注章节
2. 读 disclosure_notes.table_data.sub_table_data（已由前端同步的数据）
3. 如果有数据 → 清除 is_stale + 确保 _source=workpaper
4. 如果无数据 → 标记 is_stale + 提示用户去披露表确认

手动「刷新附注」时对全部有映射的章节执行上述逻辑。

spec: note-data-from-disclosure-table
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "note_workpaper_sync_registry.json"


# ── 注册表加载 ────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, dict[str, str]]:
    """wp_code → {listed: 章节号, soe: 章节号, sheet_listed, sheet_soe}。

    与 disclosure_stale_marker._registry 同源同格式，独立缓存避免循环依赖。
    """
    try:
        doc = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("note_disclosure_refresh: registry unavailable: %s", exc)
        return {}
    out: dict[str, dict[str, str]] = {}
    for e in doc.get("entries") or []:
        if not isinstance(e, dict):
            continue
        code = str(e.get("wp_code") or "").strip()
        if not code:
            continue
        out[code] = {
            k: str(e.get(k) or "").strip()
            for k in ("listed", "soe", "sheet_listed", "sheet_soe")
            if str(e.get(k) or "").strip()
        }
    return out


def sections_for_wp_code(wp_code: str, variant: str | None = None) -> list[str]:
    """该底稿对应的附注章节号。variant 可选过滤 listed/soe。"""
    entry = _load_registry().get(wp_code.strip())
    if not entry:
        return []
    if variant:
        sec = entry.get(variant)
        return [sec] if sec else []
    return [v for k, v in entry.items() if k in ("listed", "soe") and v]


def all_wp_codes() -> list[str]:
    """所有有附注映射的底稿编码。"""
    return list(_load_registry().keys())


# ── 刷新结果 ──────────────────────────────────────────────────────────────────


@dataclass
class RefreshSectionResult:
    section_id: str
    wp_code: str
    status: str  # "refreshed" | "no_data" | "stale_marked" | "not_found" | "skipped"
    rows_count: int = 0
    message: str = ""


@dataclass
class RefreshResult:
    refreshed: int = 0
    stale_marked: int = 0
    skipped: int = 0
    not_found: int = 0
    sections: list[RefreshSectionResult] = field(default_factory=list)


# ── 核心：单章节刷新 ─────────────────────────────────────────────────────────


async def refresh_note_section(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    wp_code: str,
    section_id: str,
    triggered_by: UUID | None = None,
) -> RefreshSectionResult:
    """刷新单个附注章节：从已保存的 table_data 检查数据状态。

    逻辑：
    - 查 disclosure_notes WHERE (project_id, year, note_section)
    - 有 sub_table_data 且非空 → 清除 is_stale，确保 _source=workpaper
    - 无 sub_table_data 或为空 → 标记 is_stale，记录原因
    """
    from app.models.report_models import DisclosureNote

    note = (await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == section_id,
            DisclosureNote.is_deleted == sa.false(),
        ).with_for_update()
    )).scalar_one_or_none()

    if note is None:
        return RefreshSectionResult(
            section_id=section_id, wp_code=wp_code,
            status="not_found", message="附注章节尚未生成",
        )

    td = note.table_data if isinstance(note.table_data, dict) else {}
    sub = td.get("sub_table_data")
    has_data = isinstance(sub, dict) and any(
        isinstance(rows, list) and len(rows) > 0
        for rows in sub.values()
    )

    now = datetime.now(timezone.utc)

    if has_data:
        # 数据已由前端同步过来 → 确保标记正确 + 增量推送行结构
        td["_source"] = "workpaper"
        td["_last_refresh_at"] = now.isoformat()

        # spec: note-data-from-disclosure-table 近期改进 3 — 增量推送
        # sub_table_data 已在 table_data 里（前端同步写入的），确保 stale 清除
        # 并触发下游事件（SSE 通知前端刷新）
        note.table_data = td
        flag_modified(note, "table_data")
        note.is_stale = False
        note.stale_source = None
        note.last_sync_source = "disclosure_refresh"
        note.last_sync_at = now
        if triggered_by:
            note.updated_by = triggered_by
            note.last_sync_user_id = triggered_by
        note.updated_at = now
        await db.flush()

        # 发布 NOTE_UPDATED 事件让前端 SSE 刷新（如果 eventbus 可用）
        try:
            from app.models.audit_platform_schemas import EventPayload, EventType
            from app.services.event_bus import event_bus
            await event_bus.publish(EventPayload(
                event_type=EventType.NOTE_UPDATED,
                project_id=project_id,
                year=year,
                extra={"note_section": section_id, "source": "disclosure_refresh"},
            ))
        except Exception:
            pass  # SSE 通知是尽力而为，不阻断刷新

        rows_count = sum(
            len(rows) for rows in sub.values()
            if isinstance(rows, list)
        )
        return RefreshSectionResult(
            section_id=section_id, wp_code=wp_code,
            status="refreshed", rows_count=rows_count,
            message=f"已从披露表刷新（{rows_count} 行）",
        )
    else:
        # 无数据（前端从未同步过）→ 标记 stale
        note.is_stale = True
        note.stale_source = "disclosure_refresh_no_data"
        note.updated_at = now
        await db.flush()

        return RefreshSectionResult(
            section_id=section_id, wp_code=wp_code,
            status="stale_marked",
            message="披露表数据为空，请先在底稿中完成披露表编制并保存",
        )


# ── 单底稿刷新 ────────────────────────────────────────────────────────────────


async def refresh_note_from_disclosure(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    wp_code: str,
    *,
    variant: str | None = None,
    triggered_by: UUID | None = None,
) -> RefreshResult:
    """从底稿披露表刷新该底稿对应的全部附注章节。

    variant: 项目的准则变体（listed/soe），传入后只刷新匹配的章节。
    """
    sections = sections_for_wp_code(wp_code, variant)
    if not sections:
        return RefreshResult(skipped=1, sections=[
            RefreshSectionResult(
                section_id="", wp_code=wp_code,
                status="skipped", message="该底稿无附注映射",
            ),
        ])

    result = RefreshResult()
    for section_id in sections:
        sr = await refresh_note_section(
            db, project_id, year,
            wp_code=wp_code, section_id=section_id,
            triggered_by=triggered_by,
        )
        result.sections.append(sr)
        if sr.status == "refreshed":
            result.refreshed += 1
        elif sr.status == "stale_marked":
            result.stale_marked += 1
        elif sr.status == "not_found":
            result.not_found += 1
        else:
            result.skipped += 1

    return result


# ── 全量刷新 ──────────────────────────────────────────────────────────────────


async def refresh_all_notes(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    variant: str | None = None,
    triggered_by: UUID | None = None,
) -> RefreshResult:
    """一键刷新全部有底稿映射的附注章节。"""
    total = RefreshResult()

    for wp_code in all_wp_codes():
        sub = await refresh_note_from_disclosure(
            db, project_id, year, wp_code,
            variant=variant, triggered_by=triggered_by,
        )
        total.refreshed += sub.refreshed
        total.stale_marked += sub.stale_marked
        total.skipped += sub.skipped
        total.not_found += sub.not_found
        total.sections.extend(sub.sections)

    return total


# ── WORKPAPER_SAVED 事件 handler ──────────────────────────────────────────────


def _uuid_or_none(value: Any) -> UUID | None:
    """事件 extra 里的 id（JSON 化后是字符串）；缺失或不是 UUID 一律当没给。"""
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value)) if value else None
    except ValueError:
        return None


async def handle_workpaper_saved(payload: Any) -> dict[str, Any]:
    """WORKPAPER_SAVED 事件处理：刷新该底稿对应的附注章节。

    fail-soft：异常只 warning，不冒泡到底稿保存。
    """
    project_id = getattr(payload, "project_id", None)
    if not project_id:
        return {"status": "no_project"}

    extra = getattr(payload, "extra", None) or {}
    wp_code = extra.get("wp_code", "")
    if not wp_code or not isinstance(wp_code, str):
        return {"status": "no_wp_code"}

    wp_code = wp_code.strip()
    year = getattr(payload, "year", None)
    if not year:
        return {"status": "no_year"}

    sections = sections_for_wp_code(wp_code)
    if not sections:
        return {"status": "no_mapping"}

    # 修前 `UUID(user_id)` 在 try 之外：一个不合法的 user_id 就让 handler 直接抛出
    triggered_by = _uuid_or_none(extra.get("user_id"))

    try:
        from app.core.database import async_session

        async with async_session() as db:
            try:
                # spec: backend-disclosure-payload-builder — 尝试后端 builder
                from app.services.disclosure_payload_builder_service import build_and_sync, get_builder
                if get_builder(wp_code) is not None:
                    try:
                        await build_and_sync(
                            db, project_id, year, wp_code,
                            triggered_by=triggered_by,
                        )
                    except Exception as build_exc:
                        # builder 已回滚到自己的保存点，下面的刷新仍在健康的事务上
                        logger.warning(
                            "note_disclosure_refresh: builder failed for %s, "
                            "falling back to refresh: %s", wp_code, build_exc,
                        )

                result = await refresh_note_from_disclosure(
                    db, project_id, year, wp_code,
                    triggered_by=triggered_by,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        return {
            "status": "ok",
            "wp_code": wp_code,
            "refreshed": result.refreshed,
            "stale_marked": result.stale_marked,
        }
    except Exception as exc:
        logger.warning(
            "note_disclosure_refresh: handler failed project=%s wp_code=%s: %s",
            project_id, wp_code, exc,
        )
        return {"status": "failed", "error": str(exc)}
