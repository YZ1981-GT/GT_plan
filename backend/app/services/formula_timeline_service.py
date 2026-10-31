"""公式版本时间轴聚合服务（spec: formula-hub-integrity-closure 任务 28；ADR-FHIC-16）。

合并五数据源为统一时间轴，每个子源在 SAVEPOINT 内执行互不影响：
1. 公式审计日志（audit_log_entries WHERE action_type='formula.changed'，payload->>'project_id' + ts）
2. 全局发布历史（formula_publish WHERE status='published'，published_at / change_set / published_by）
3. 模板版本更新（formula_template_version，published_at）
4. 推送运行记录（formula_push_run）
5. 冲突解决记录（formula_sync_item）
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 事件类型标签和图标
EVENT_TYPES = {
    "formula_changed": {"icon": "🟡", "label": "公式变更", "color": "warning"},
    "global_publish": {"icon": "🔵", "label": "全局发布", "color": "primary"},
    "template_update": {"icon": "🟣", "label": "模板更新", "color": "info"},
    "push_run": {"icon": "🟢", "label": "推送执行", "color": "success"},
    "conflict_resolved": {"icon": "🔴", "label": "冲突解决", "color": "danger"},
}

# 子源中文名映射（用于 unavailable_sources）
_SOURCE_LABELS = {
    "audit_log": "公式审计日志",
    "publish": "全局发布历史",
    "template": "模板版本更新",
    "push": "推送运行记录",
    "conflict": "冲突解决记录",
}


async def build_timeline(
    db: AsyncSession, project_id: uuid.UUID, year: int, *, limit: int = 200
) -> dict[str, Any]:
    """聚合五数据源，按时间倒序返回统一时间轴。

    每个子源包在 SAVEPOINT 内（ADR-FHIC-16）：某源查询失败只影响自己，
    其余子源照常返回。失败源记入 ``unavailable_sources``。
    """
    events: list[dict[str, Any]] = []
    unavailable_sources: list[dict[str, str]] = []

    sources = [
        ("audit_log", _audit_log_events, (db, project_id, year, limit)),
        ("publish", _publish_events, (db, project_id, limit)),
        ("template", _template_events, (db, project_id, limit)),
        ("push", _push_events, (db, project_id, year, limit)),
        ("conflict", _conflict_events, (db, project_id, limit)),
    ]

    for source_key, fn, args in sources:
        try:
            async with db.begin_nested():
                result = await fn(*args)
            events.extend(result)
        except Exception as exc:
            label = _SOURCE_LABELS.get(source_key, source_key)
            msg = f"{type(exc).__name__}: {exc}"
            unavailable_sources.append({"source": label, "message": msg})
            logger.warning("时间轴子源 %s 查询失败", source_key, exc_info=True)

    # 按时间倒序排列
    events.sort(key=lambda e: e.get("timestamp") or "", reverse=True)

    # 截断
    events = events[:limit]

    return {
        "project_id": str(project_id),
        "year": year,
        "total": len(events),
        "events": events,
        "event_types": EVENT_TYPES,
        "unavailable_sources": unavailable_sources,
    }


async def _audit_log_events(
    db: AsyncSession, project_id: uuid.UUID, year: int, limit: int
) -> list[dict[str, Any]]:
    """公式审计日志：真实字段 payload->>'project_id' + ts。"""
    from app.models.audit_log_models import AuditLogEntry

    rows = (await db.execute(
        sa.select(AuditLogEntry).where(
            AuditLogEntry.action_type == "formula.changed",
            AuditLogEntry.payload["project_id"].astext == str(project_id),
        ).order_by(AuditLogEntry.ts.desc()).limit(limit)
    )).scalars().all()

    return [{
        "type": "formula_changed",
        "timestamp": r.ts.isoformat() if r.ts else None,
        "summary": _formula_changed_summary(r),
        "detail": _safe_payload(r),
        "user_id": str(r.user_id) if r.user_id else None,
    } for r in rows]


async def _publish_events(
    db: AsyncSession, project_id: uuid.UUID, limit: int
) -> list[dict[str, Any]]:
    """全局发布历史：status='published' + published_at / change_set / published_by。

    项目准则取 formula_settings.projects.get_project（ADR-FHIC-16）。
    """
    from app.models.formula_setting_models import FormulaPublish
    from app.services.formula_settings.projects import get_project

    # 取项目准则 scope 用于过滤
    _project_scope: str | None = None
    try:
        info = await get_project(db, "report", project_id)
        if info:
            _project_scope = info.scope
    except Exception:
        pass  # scope 查不到就不过滤

    q = sa.select(FormulaPublish).where(FormulaPublish.status == "published")
    if _project_scope:
        q = q.where(
            sa.or_(
                FormulaPublish.scope == _project_scope,
                FormulaPublish.scope == "*",
                FormulaPublish.scope.is_(None),
            )
        )
    rows = (await db.execute(
        q.order_by(FormulaPublish.published_at.desc()).limit(limit)
    )).scalars().all()

    return [{
        "type": "global_publish",
        "timestamp": r.published_at.isoformat() if r.published_at else None,
        "summary": f"全局发布 · 域 {r.domain} · 范围 {r.scope}",
        "detail": {
            "domain": r.domain, "scope": r.scope,
            "change_set": r.change_set,
            "published_by": str(r.published_by) if r.published_by else None,
            "source": r.source,
        },
        "user_id": str(r.published_by) if r.published_by else None,
    } for r in rows]


async def _template_events(
    db: AsyncSession, project_id: uuid.UUID, limit: int
) -> list[dict[str, Any]]:
    """模板版本更新：published_at。"""
    from app.models.formula_setting_models import (
        FormulaTemplateSubscription,
        FormulaTemplateVersion,
    )

    subs = (await db.execute(
        sa.select(FormulaTemplateSubscription.template_id).where(
            FormulaTemplateSubscription.project_id == project_id,
            FormulaTemplateSubscription.is_active == sa.true(),
        )
    )).scalars().all()

    if not subs:
        return []

    rows = (await db.execute(
        sa.select(FormulaTemplateVersion).where(
            FormulaTemplateVersion.template_id.in_(subs),
        ).order_by(FormulaTemplateVersion.published_at.desc()).limit(limit)
    )).scalars().all()

    return [{
        "type": "template_update",
        "timestamp": r.published_at.isoformat() if r.published_at else None,
        "summary": f"模板版本 v{r.version}",
        "detail": {
            "template_id": str(r.template_id), "version": r.version,
            "published_by": str(r.published_by) if r.published_by else None,
            "note": r.note,
        },
    } for r in rows]


async def _push_events(
    db: AsyncSession, project_id: uuid.UUID, year: int, limit: int
) -> list[dict[str, Any]]:
    """推送运行记录。"""
    from app.models.formula_push_models import FormulaPushRun

    rows = (await db.execute(
        sa.select(FormulaPushRun).where(
            FormulaPushRun.project_id == project_id,
            FormulaPushRun.year == year,
        ).order_by(FormulaPushRun.started_at.desc()).limit(limit)
    )).scalars().all()

    return [{
        "type": "push_run",
        "timestamp": r.started_at.isoformat() if r.started_at else None,
        "summary": f"推送 · {r.trigger_source} · 写入 {r.written_count} / 跳过 {r.skipped_count}",
        "detail": {
            "trigger": r.trigger_source, "status": r.status,
            "written": r.written_count, "unchanged": r.unchanged_count,
            "kept": r.kept_count, "skipped": r.skipped_count,
        },
    } for r in rows]


async def _conflict_events(
    db: AsyncSession, project_id: uuid.UUID, limit: int
) -> list[dict[str, Any]]:
    """冲突解决记录。"""
    from app.models.formula_setting_models import FormulaSyncItem

    rows = (await db.execute(
        sa.select(FormulaSyncItem).where(
            FormulaSyncItem.project_id == project_id,
            FormulaSyncItem.status != "pending",
        ).order_by(FormulaSyncItem.updated_at.desc()).limit(limit)
    )).scalars().all()

    return [{
        "type": "conflict_resolved",
        "timestamp": r.updated_at.isoformat() if r.updated_at else None,
        "summary": f"冲突解决 · 域 {r.domain} · {r.slot_key} · {r.status}",
        "detail": {
            "domain": r.domain, "slot_key": r.slot_key, "status": r.status,
            "resolution": r.resolution,
        },
    } for r in rows]


def _formula_changed_summary(entry: Any) -> str:
    """从审计日志 payload 中提取变更摘要。"""
    payload = getattr(entry, "payload", None) or {}
    module = payload.get("module", "")
    row_code = payload.get("row_code", "")
    action = payload.get("action", "changed")
    parts = [p for p in [module, row_code, action] if p]
    return "公式变更" + (" · " + " · ".join(parts) if parts else "")


def _safe_payload(entry: Any) -> dict:
    """安全提取 payload，避免序列化问题。"""
    payload = getattr(entry, "payload", None)
    if isinstance(payload, dict):
        return payload
    return {}
