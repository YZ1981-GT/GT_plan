"""公式版本时间轴聚合服务（spec: formula-management-deep-optimization · R6）。

合并五数据源为统一时间轴：
1. 公式审计日志（audit_log_entries WHERE action_type='formula.changed'）
2. 全局发布历史（formula_publishes）
3. 模板更新（formula_template_versions）
4. 推送触发（formula_push_run）
5. 冲突解决（formula_sync_items WHERE status='resolved'）
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


async def build_timeline(
    db: AsyncSession, project_id: uuid.UUID, year: int, *, limit: int = 200
) -> dict[str, Any]:
    """聚合五数据源，按时间倒序返回统一时间轴。"""
    events: list[dict[str, Any]] = []

    events.extend(await _audit_log_events(db, project_id, year, limit))
    events.extend(await _publish_events(db, limit))
    events.extend(await _template_events(db, project_id, limit))
    events.extend(await _push_events(db, project_id, year, limit))
    events.extend(await _conflict_events(db, project_id, limit))

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
    }


async def _audit_log_events(
    db: AsyncSession, project_id: uuid.UUID, year: int, limit: int
) -> list[dict[str, Any]]:
    """公式审计日志。"""
    try:
        from app.models.audit_log_models import AuditLogEntry

        rows = (await db.execute(
            sa.select(AuditLogEntry).where(
                AuditLogEntry.action_type == "formula.changed",
                AuditLogEntry.project_id == project_id,
            ).order_by(AuditLogEntry.created_at.desc()).limit(limit)
        )).scalars().all()

        return [{
            "type": "formula_changed",
            "timestamp": r.created_at.isoformat() if r.created_at else None,
            "summary": _formula_changed_summary(r),
            "detail": _safe_payload(r),
            "user_id": str(r.user_id) if r.user_id else None,
        } for r in rows]
    except Exception:
        logger.warning("审计日志查询失败", exc_info=True)
        return []


async def _publish_events(db: AsyncSession, limit: int) -> list[dict[str, Any]]:
    """全局发布历史。"""
    try:
        from app.models.formula_setting_models import FormulaPublish

        rows = (await db.execute(
            sa.select(FormulaPublish).where(
                FormulaPublish.status == "applied",
            ).order_by(FormulaPublish.created_at.desc()).limit(limit)
        )).scalars().all()

        return [{
            "type": "global_publish",
            "timestamp": r.created_at.isoformat() if r.created_at else None,
            "summary": f"全局发布 · 域 {r.domain} · 范围 {r.scope}",
            "detail": {
                "domain": r.domain, "scope": r.scope,
                "change_count": len(r.changes or []) if hasattr(r, 'changes') else 0,
                "source": getattr(r, 'source', None),
            },
            "user_id": str(r.user_id) if hasattr(r, 'user_id') and r.user_id else None,
        } for r in rows]
    except Exception:
        logger.warning("发布历史查询失败", exc_info=True)
        return []


async def _template_events(
    db: AsyncSession, project_id: uuid.UUID, limit: int
) -> list[dict[str, Any]]:
    """模板版本更新。"""
    try:
        from app.models.formula_setting_models import (
            FormulaTemplateSubscription,
            FormulaTemplateVersion,
        )

        # 查本项目订阅的模板的版本更新
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
            ).order_by(FormulaTemplateVersion.created_at.desc()).limit(limit)
        )).scalars().all()

        return [{
            "type": "template_update",
            "timestamp": r.created_at.isoformat() if r.created_at else None,
            "summary": f"模板版本 v{r.version}",
            "detail": {
                "template_id": str(r.template_id), "version": r.version,
                "note": getattr(r, 'note', None),
            },
        } for r in rows]
    except Exception:
        logger.warning("模板历史查询失败", exc_info=True)
        return []


async def _push_events(
    db: AsyncSession, project_id: uuid.UUID, year: int, limit: int
) -> list[dict[str, Any]]:
    """推送运行记录。"""
    try:
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
    except Exception:
        logger.warning("推送历史查询失败", exc_info=True)
        return []


async def _conflict_events(
    db: AsyncSession, project_id: uuid.UUID, limit: int
) -> list[dict[str, Any]]:
    """冲突解决记录。"""
    try:
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
                "resolution": getattr(r, 'resolution', None),
            },
        } for r in rows]
    except Exception:
        logger.warning("冲突历史查询失败", exc_info=True)
        return []


def _formula_changed_summary(entry: Any) -> str:
    """从审计日志 payload 中提取变更摘要。"""
    payload = getattr(entry, 'payload', None) or {}
    module = payload.get("module", "")
    row_code = payload.get("row_code", "")
    action = payload.get("action", "changed")
    parts = [p for p in [module, row_code, action] if p]
    return "公式变更" + (" · " + " · ".join(parts) if parts else "")


def _safe_payload(entry: Any) -> dict:
    """安全提取 payload，避免序列化问题。"""
    payload = getattr(entry, 'payload', None)
    if isinstance(payload, dict):
        return payload
    return {}
