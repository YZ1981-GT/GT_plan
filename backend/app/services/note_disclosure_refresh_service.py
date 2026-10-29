"""附注 ← 底稿披露表：同步状态（只读）。

数据流：底稿披露表由前端披露 Tab 的 ``buildXSyncPayload`` 现算，经 ``sync-from-workpaper`` 写进
``disclosure_notes.table_data.sub_table_data``（``wp_disclosure_sync_service.sync_from_workpaper``，写入时
同时清 stale、广播 ``note.synced``）。后端**算不出**披露表（spec note-pull-header-formula-closure ADR-1）：

- 不重建 ``sub_table_data``：原后端披露表 builder 与前端不是同一口径（D2 账龄期末恒 0、坏账准备恒 0、
  标准 builder 只产出一张两行表），2026-10-26 起不接任何写路径、2026-10-27 删除（spec note-pull-followup-closure R17）；
- 不改附注标记：底稿保存时后端拿不到披露表新值，原先在这里「有 sub_table_data 就清 stale」会掩盖真实过期
  （与 ``disclosure_stale_marker`` 互相打架），没有 sub_table_data 就标「披露表数据为空」会给从未由底稿同步、
  数据来自模板取数 / 公式推送的章节误标待更新。

本模块只回答「这个章节有没有从底稿披露表同步过、同步了几行、什么时候」，供 ``refresh-from-disclosure``
状态查询与诊断使用；不再订阅 ``WORKPAPER_SAVED``。附注刷新时真正的取数见 ``note_workpaper_pull_service``。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "note_workpaper_sync_registry.json"


# ── 注册表加载 ────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, dict[str, Any]]:
    """wp_code → 原始注册项；章节展开统一走 ``registry_sections``。"""
    try:
        doc = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("note_disclosure_refresh: registry unavailable: %s", exc)
        return {}
    out: dict[str, dict[str, Any]] = {}
    for e in doc.get("entries") or []:
        if not isinstance(e, dict):
            continue
        code = str(e.get("wp_code") or "").strip()
        if code:
            out[code] = dict(e)
    return out


def sections_for_wp_code(wp_code: str, variant: str | None = None) -> list[str]:
    """该底稿对应的全部附注章节；包含 ``*_sections`` 复数映射。"""
    from app.services.note_readiness_service import registry_sections

    entry = _load_registry().get(wp_code.strip())
    if not entry:
        return []
    variants = (variant,) if variant else ("listed", "soe")
    return list(dict.fromkeys(
        section
        for item_variant in variants
        for section in registry_sections(entry, item_variant)
    ))


def all_wp_codes() -> list[str]:
    """所有有附注映射的底稿编码。"""
    return list(_load_registry().keys())


# ── 刷新结果 ──────────────────────────────────────────────────────────────────


@dataclass
class RefreshSectionResult:
    section_id: str
    wp_code: str
    status: str  # "synced" | "not_synced" | "not_found" | "skipped"
    rows_count: int = 0
    message: str = ""


@dataclass
class RefreshResult:
    synced: int = 0
    not_synced: int = 0
    skipped: int = 0
    not_found: int = 0
    sections: list[RefreshSectionResult] = field(default_factory=list)


# ── 核心：单章节同步状态（只读） ───────────────────────────────────────────


def _is_synced_from_workpaper(td: dict) -> bool:
    """章节表格确由底稿披露表同步过：带同步指纹（只有披露同步写；公式推送 2026-10-27 起不写，
    spec note-pull-followup-closure R3.2）。"""
    return bool(td.get("_last_sync_wp_id"))


async def refresh_note_section(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    wp_code: str,
    section_id: str,
    triggered_by: UUID | None = None,  # noqa: ARG001 —— 保留签名兼容；只读不记操作人
) -> RefreshSectionResult:
    """单个附注章节的底稿披露表同步状态（只读，不改任何字段）。

    - 章节不存在 → ``not_found``
    - 没有同步指纹或没有 ``sub_table_data`` 行 → ``not_synced``（数据来自模板取数 / 公式推送，不标待更新）
    - 有 → ``synced``（行数 + 上次同步时间）
    """
    from app.models.report_models import DisclosureNote

    note = (await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == section_id,
            DisclosureNote.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()

    if note is None:
        return RefreshSectionResult(
            section_id=section_id, wp_code=wp_code,
            status="not_found", message="附注章节尚未生成",
        )

    td = note.table_data if isinstance(note.table_data, dict) else {}
    sub = td.get("sub_table_data")
    rows_count = sum(len(rows) for rows in sub.values() if isinstance(rows, list)) if isinstance(sub, dict) else 0
    if rows_count == 0 or not (_is_synced_from_workpaper(td) or td.get("_source") in ("workpaper", "workpaper_html")):
        return RefreshSectionResult(
            section_id=section_id, wp_code=wp_code, status="not_synced",
            message=f"尚未从底稿 {wp_code} 的披露表同步：打开该底稿的附注披露页保存一次即可同步",
        )
    synced_at = td.get("_last_sync_at") or (note.last_sync_at.isoformat() if note.last_sync_at else "")
    return RefreshSectionResult(
        section_id=section_id, wp_code=wp_code, status="synced", rows_count=rows_count,
        message=f"已从底稿 {wp_code} 的披露表同步 {rows_count} 行" + (f"（{synced_at[:19]}）" if synced_at else ""),
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
        if sr.status == "synced":
            result.synced += 1
        elif sr.status == "not_synced":
            result.not_synced += 1
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
        total.synced += sub.synced
        total.not_synced += sub.not_synced
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
    """底稿保存后该底稿对应附注章节的同步状态（只读诊断，**不订阅**、不写库）。

    2026-10-26 前这里会先跑后端 builder 把错数写进附注、再按有无 ``sub_table_data`` 清 / 标 stale；两件事都
    已移除（模块文档）。底稿披露表 → 附注的同步只由前端披露 Tab 保存后的自动同步与附注刷新时的离屏同步完成。
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

    try:
        from app.core.database import async_session

        async with async_session() as db:
            result = await refresh_note_from_disclosure(db, project_id, year, wp_code)
        return {
            "status": "ok",
            "wp_code": wp_code,
            "synced": result.synced,
            "not_synced": result.not_synced,
        }
    except Exception as exc:
        logger.warning(
            "note_disclosure_refresh: status probe failed project=%s wp_code=%s: %s",
            project_id, wp_code, exc,
        )
        return {"status": "failed", "error": str(exc)}
