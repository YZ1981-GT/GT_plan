"""附注「披露同步 / 校验就绪度」只读看板服务（附注模块联动复盘 P0-1 / P0-4）。

问题背景（2026-07-26 复盘实测）
--------------------------------
底稿→附注结构化推送（46 个 ``buildXSyncPayload`` + 列头覆盖率守卫全绿）在生产
**零使用**：``disclosure_notes`` 中 ``table_data._source in (workpaper, workpaper_html)``
为 0 条、``last_sync_source`` 为 0 条。根因不是链路不通（live round-trip 早已验证），
而是 push 模型要求审计师逐张底稿打开披露 tab 点「同步到附注」，而 UI 上**没有
"哪里还没做"的可见清单**，于是永远没人点。同理附注校验（11 executor + 760/187
条预设）从未跑过并落库（``note_validation_results`` 0 行）。

本服务提供**只读**就绪度视图（不写库、不改数据），供：
- 附注模块「就绪度」看板：列出每章节 有数据 / 是否曾从底稿同步 / stale / findings，
  未同步的可直接跳对应底稿；
- 交付出具前的软闸门（P1-3）：列出"有底稿映射但从未同步"与"存在 error findings"。

映射真源
--------
``backend/data/note_workpaper_sync_registry.json``（由
``backend/scripts/gen_note_wp_sync_registry.py`` 从前端 ``*NoteSectionMap.ts`` 生成，
唯一真源）。**不用** ``note_wp_mapping_service.DEFAULT_WP_MAPPING``——其章节编号
仍是老体系（D1→五、2 / D2→五、3），与权威 五、4 / 五、5 不符。
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "note_workpaper_sync_registry.json"


# ---------------------------------------------------------------------------
# 章节 ↔ 底稿映射（只读，fail-open）
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_registry_entries() -> tuple[dict[str, Any], ...]:
    try:
        raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        entries = raw.get("entries") or []
        return tuple(e for e in entries if isinstance(e, dict))
    except Exception as err:  # pragma: no cover — 文件缺失/非法时安全降级
        logger.warning("note sync registry unavailable: %s", err)
        return ()


def section_workpaper_map() -> dict[str, list[str]]:
    """``note_section → [wp_code]``（listed 与 soe 章节各自成键，可一对多）。"""
    out: dict[str, list[str]] = {}
    for e in _load_registry_entries():
        code = str(e.get("wp_code") or "").strip()
        if not code:
            continue
        for key in ("listed", "soe"):
            sec = e.get(key)
            if isinstance(sec, str) and sec.strip():
                out.setdefault(sec.strip(), [])
                if code not in out[sec.strip()]:
                    out[sec.strip()].append(code)
    return out


def section_sheet_map() -> dict[str, str]:
    """``note_section → 底稿披露 sheet 真实 tab 名``（缺失则不登记，供跳转带 ?sheet=）。"""
    out: dict[str, str] = {}
    for e in _load_registry_entries():
        for sec_key, sheet_key in (("listed", "sheet_listed"), ("soe", "sheet_soe")):
            sec = e.get(sec_key)
            sheet = e.get(sheet_key)
            if isinstance(sec, str) and sec.strip() and isinstance(sheet, str) and sheet.strip():
                out.setdefault(sec.strip(), sheet.strip())
    return out


# ---------------------------------------------------------------------------
# 校验 findings（最新一次 run，按章节聚合）
# ---------------------------------------------------------------------------


async def latest_findings_by_section(
    db: AsyncSession, project_id: UUID, year: int
) -> tuple[dict[str, dict[str, int]], str | None]:
    """读最新一次校验 run，按 ``note_section`` 聚合 error/warning 计数。

    Returns:
        ``({section: {"error": n, "warning": n}}, validated_at_iso | None)``；
        无 run / 异常 → ``({}, None)``（fail-open，看板不因此失败）。
    """
    try:
        row = (
            await db.execute(
                sa.text(
                    "SELECT findings, validation_timestamp FROM note_validation_results "
                    "WHERE project_id = :pid AND year = :yr "
                    "ORDER BY validation_timestamp DESC NULLS LAST LIMIT 1"
                ),
                {"pid": str(project_id), "yr": year},
            )
        ).fetchone()
    except Exception as err:  # pragma: no cover
        logger.warning("load latest validation findings failed: %s", err)
        return {}, None

    if row is None:
        return {}, None
    findings = row[0]
    ts = row[1]
    out: dict[str, dict[str, int]] = {}
    if isinstance(findings, list):
        for f in findings:
            if not isinstance(f, dict):
                continue
            sec = str(f.get("note_section") or "").strip()
            if not sec:
                continue
            sev = str(f.get("severity") or "warning").lower()
            bucket = out.setdefault(sec, {"error": 0, "warning": 0})
            if sev == "error":
                bucket["error"] += 1
            else:
                bucket["warning"] += 1
    return out, (ts.isoformat() if ts is not None else None)


# ---------------------------------------------------------------------------
# 底稿 wp_id 反查（供看板跳转）
# ---------------------------------------------------------------------------


async def _resolve_wp_ids(
    db: AsyncSession, project_id: UUID, wp_codes: set[str]
) -> dict[str, str]:
    """``wp_code → working_paper.id``（仅已生成底稿；查不到则不登记，前端不给跳转）。"""
    if not wp_codes:
        return {}
    try:
        rows = (
            await db.execute(
                sa.text(
                    "SELECT wi.wp_code, wp.id FROM wp_index wi "
                    "JOIN working_paper wp ON wp.wp_index_id = wi.id "
                    "AND wp.is_deleted = false "
                    "WHERE wi.project_id = :pid AND wi.is_deleted = false "
                    "AND wi.wp_code = ANY(:codes)"
                ),
                {"pid": str(project_id), "codes": list(wp_codes)},
            )
        ).fetchall()
    except Exception as err:  # pragma: no cover — 表结构差异时安全降级
        logger.warning("resolve wp ids failed: %s", err)
        return {}
    return {r[0]: str(r[1]) for r in rows if r[0]}


# ---------------------------------------------------------------------------
# 看板主入口
# ---------------------------------------------------------------------------


async def build_readiness(
    db: AsyncSession, project_id: UUID, year: int
) -> dict[str, Any]:
    """构建附注就绪度视图（只读）。

    Returns 结构::

        {
          "summary": {total, with_data, empty, syncable, never_synced, stale,
                      stale_report, error_sections, warning_sections,
                      validated_at, validation_ran},
          "sections": [{note_section, section_title, account_name, has_data,
                        is_stale, stale_source, last_sync_at, last_sync_source,
                        last_sync_wp_id, wp_codes, wp_ids, wp_sheet,
                        needs_sync, findings:{error,warning}}]
        }
    """
    from app.services.note_content_utils import note_has_data

    notes = (
        (
            await db.execute(
                sa.select(DisclosureNote)
                .where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.is_deleted == sa.false(),
                )
                .order_by(DisclosureNote.sort_order)
            )
        )
        .scalars()
        .all()
    )

    sec_wp = section_workpaper_map()
    sec_sheet = section_sheet_map()
    findings_map, validated_at = await latest_findings_by_section(db, project_id, year)

    needed_codes: set[str] = set()
    for n in notes:
        needed_codes.update(sec_wp.get(n.note_section or "", []))
    wp_ids = await _resolve_wp_ids(db, project_id, needed_codes)

    sections: list[dict[str, Any]] = []
    summary = {
        "total": 0,
        "with_data": 0,
        "empty": 0,
        "syncable": 0,
        "never_synced": 0,
        "stale": 0,
        "stale_report": 0,
        "error_sections": 0,
        "warning_sections": 0,
    }

    for n in notes:
        section = n.note_section or ""
        codes = sec_wp.get(section, [])
        has_data = bool(note_has_data(n))
        f = findings_map.get(section) or {"error": 0, "warning": 0}
        last_sync_at = n.last_sync_at.isoformat() if n.last_sync_at else None
        needs_sync = bool(codes) and last_sync_at is None

        summary["total"] += 1
        if has_data:
            summary["with_data"] += 1
        else:
            summary["empty"] += 1
        if codes:
            summary["syncable"] += 1
        if needs_sync:
            summary["never_synced"] += 1
        if getattr(n, "is_stale", False):
            summary["stale"] += 1
            if (getattr(n, "stale_source", None) or "") == "report":
                summary["stale_report"] += 1
        if f.get("error"):
            summary["error_sections"] += 1
        elif f.get("warning"):
            summary["warning_sections"] += 1

        sections.append(
            {
                "note_section": section,
                "section_title": n.section_title or "",
                "account_name": n.account_name or "",
                "has_data": has_data,
                "is_stale": bool(getattr(n, "is_stale", False)),
                "stale_source": getattr(n, "stale_source", None),
                "last_sync_at": last_sync_at,
                "last_sync_source": n.last_sync_source,
                "last_sync_wp_id": str(n.last_sync_wp_id) if n.last_sync_wp_id else None,
                "wp_codes": codes,
                "wp_ids": {c: wp_ids[c] for c in codes if c in wp_ids},
                "wp_sheet": sec_sheet.get(section),
                "needs_sync": needs_sync,
                "findings": {"error": f.get("error", 0), "warning": f.get("warning", 0)},
            }
        )

    summary["validated_at"] = validated_at
    summary["validation_ran"] = validated_at is not None
    return {"summary": summary, "sections": sections}


async def run_validation_best_effort(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    template_type: str | None = None,
) -> dict | None:
    """写操作（生成/刷新/底稿同步）成功后自动补跑一次附注校验并落库（P0-4）。

    历史上校验只在用户手点「✅校验」时才跑 → ``note_validation_results`` 长期 0 行，
    11 个 executor 与 760/187 条预设全部空转。此处 fail-open 补跑：任何异常吞掉并
    回滚校验事务，**绝不影响已提交的主操作**。

    Returns: 校验摘要 dict（供响应 additive 携带）或 None（跳过/失败）。
    """
    try:
        from app.services.note_validation_engine import NoteValidationEngine

        result = await NoteValidationEngine(db).validate_all(
            project_id, year, template_type=template_type,
        )
        await db.commit()
        if isinstance(result, dict):
            return {
                k: result.get(k)
                for k in (
                    "total_rules",
                    "passed",
                    "failed",
                    "error_count",
                    "warning_count",
                )
                if k in result
            }
        return None
    except Exception as err:
        logger.warning("auto validation after write skipped: %s", err)
        try:
            await db.rollback()
        except Exception:
            pass
        return None


__all__ = [
    "build_readiness",
    "latest_findings_by_section",
    "run_validation_best_effort",
    "section_workpaper_map",
    "section_sheet_map",
]
