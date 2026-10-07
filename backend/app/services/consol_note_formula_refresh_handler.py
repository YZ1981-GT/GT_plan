"""合并附注 V2 节点级自动刷新事件编排。

金额计算和写回统一委托给 ``fill_by_formula`` / ``fill_note_sections``；本模块只负责：

* 识别允许触发自动刷新的事件边界；
* 在独立数据库会话中读取当前企业树和项目模板；
* 按稳定的完整 ``node_key`` 遍历节点并隔离每个节点的提交；
* 返回和记录逐节点、逐章节的持久化/跳过/失败结果。

自动刷新是上游事务提交后的下游动作。任何章节失败都不能回滚上游试算表、调整分录
或底稿保存事务，也不能被包装成全量成功。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.models.audit_platform_schemas import EventPayload, EventType

logger = logging.getLogger(__name__)

# WORKPAPER_SAVED 只有明确声明附注影响时才进入自动刷新。声明契约保持窄口径，避免
# 普通底稿保存把所有合并附注章节无条件重写；兼容少量已经存在的字段拼写，但不会把
# ``section_id`` 单独出现解释成“需要刷新”。
_NOTE_REFRESH_DECLARATION_KEYS = (
    "consol_note_refresh",
    "consol_note_affected",
    "affects_consol_note",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _event_extra(event: EventPayload) -> dict[str, Any]:
    extra = getattr(event, "extra", None)
    return extra if isinstance(extra, dict) else {}


def _declares_note_refresh(event: EventPayload) -> bool:
    """判断底稿保存是否显式声明会影响合并附注公式。"""
    extra = _event_extra(event)
    return any(extra.get(key) is True for key in _NOTE_REFRESH_DECLARATION_KEYS)


def _requested_sections(event: EventPayload) -> list[str] | None:
    """读取事件声明的章节范围；没有范围时返回 None，表示当前模板全部章节。"""
    extra = _event_extra(event)
    raw = extra.get("section_ids")
    if raw is None:
        raw = extra.get("consol_note_section_ids")
    if raw is None:
        raw = extra.get("section_id") or extra.get("note_section")
    if raw is None:
        return None
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        return []
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def _dedup_key(event: EventPayload) -> str:
    """与 EventBus 相同的公开可观测去重身份（不依赖内部 pending 状态）。"""
    from app.services.event_bus import event_bus

    return event_bus._build_dedup_key(event)


def _node_result(node: Any) -> dict[str, Any]:
    return {
        "node_key": getattr(node, "node_key", None),
        "node_label": getattr(node, "display_name", None) or getattr(node, "company_name", None),
        "status": "pending",
        "sections": [],
        "persisted": 0,
        "failed": 0,
        "skipped": 0,
    }


async def handle_consol_note_formula_refresh(event: EventPayload) -> dict[str, object]:
    """处理合并附注自动刷新事件，并以 fail-open 方式返回结构化结果。

    ``TRIAL_BALANCE_UPDATED`` 是金额变更的唯一自动刷新入口。
    ``ADJUSTMENT_APPROVED`` 不在这里订阅：现有审批 handler 会发布下游 TB 事件，
    避免审批和 TB 两条路径重复写入同一章节。
    """
    started_at = _now()
    project_id = _as_uuid(getattr(event, "project_id", None))
    year = getattr(event, "year", None)
    event_type = getattr(getattr(event, "event_type", None), "value", getattr(event, "event_type", None))
    base: dict[str, Any] = {
        "project_id": str(project_id) if project_id else None,
        "year": year,
        "template_type": None,
        "event_type": event_type,
        "dedup_key": None,
        "status": "skipped",
        "persisted": [],
        "skipped": [],
        "failed": [],
        "started_at": started_at,
        "ended_at": None,
    }

    if project_id is None or not isinstance(year, int) or isinstance(year, bool) or year <= 0:
        base["status"] = "failed"
        base["failed"].append({
            "scope": "event",
            "error": "事件缺少有效的 project_id 或 year",
            "retry": False,
        })
        base["ended_at"] = _now()
        logger.warning("合并附注自动刷新拒绝无效事件：%s", base)
        return base

    try:
        base["dedup_key"] = _dedup_key(event)
    except Exception:
        # 去重键只用于观测，不能阻断已经进入 handler 的事件。
        base["dedup_key"] = None

    if event_type == EventType.WORKPAPER_SAVED.value and not _declares_note_refresh(event):
        base["skipped"].append({
            "scope": "event",
            "reason": "WORKPAPER_SAVED 未声明影响合并附注",
        })
        base["ended_at"] = _now()
        logger.info("合并附注自动刷新跳过底稿保存：%s", base)
        return base

    try:
        from app.core.database import async_session as async_session_factory
        from app.services.consol_note_formula_service import (
            consol_note_tables,
            fill_note_sections,
            resolve_note_template_type,
        )
        from app.services.consol_context_service import (
            build_consol_context,
            validate_context,
        )
        from app.services.consol_note_gray_service import is_consol_note_v2_enabled
        from app.services.consol_report_view_service import load_view_context
        from app.services.consol_tree_service import build_tree, iter_nodes

        # 这里新开会话，明确与发布事件的业务会话隔离。即使下游失败，也不会把上游
        # 已提交的 TB/调整/底稿事务置为 rollback-only。
        async with async_session_factory() as db:
            if not await is_consol_note_v2_enabled(db, project_id):
                base["skipped"].append({
                    "scope": "event",
                    "reason": "项目未启用合并附注 V2",
                })
                base["ended_at"] = _now()
                logger.info("合并附注自动刷新跳过 V2 关闭项目：%s", base)
                return base

            template_type = await resolve_note_template_type(db, project_id)
            base["template_type"] = template_type
            tables = [
                table for table in consol_note_tables(template_type)
                if table.get("enabled", True) is not False
            ]
            requested = _requested_sections(event)
            if requested is not None:
                requested_set = set(requested)
                tables = [table for table in tables if table.get("section_id") in requested_set]
            section_ids = list(dict.fromkeys(
                str(table.get("section_id"))
                for table in tables
                if table.get("section_id")
            ))
            if not section_ids:
                reason = "事件声明的章节不存在" if requested is not None else "模板没有可刷新的章节"
                base["skipped"].append({"scope": "event", "reason": reason})
                base["ended_at"] = _now()
                logger.info("合并附注自动刷新无章节可处理：%s", base)
                return base

            tree = await build_tree(db, project_id)
            if tree is None:
                base["skipped"].append({"scope": "event", "reason": "当前项目没有有效合并树"})
                base["ended_at"] = _now()
                logger.info("合并附注自动刷新无树：%s", base)
                return base

            event_context = event.resolved_context()
            if event_context is None:
                context = await build_consol_context(
                    db,
                    project_id,
                    year,
                    tree=tree,
                )
            else:
                validate_context(event_context, project_id, year, tree=tree)
                context = event_context
            view_context = await load_view_context(
                db,
                project_id,
                year,
                context=context,
                tree=tree,
            )
            if view_context is None:
                base["skipped"].append({"scope": "event", "reason": "无法加载合并计算上下文"})
                base["ended_at"] = _now()
                logger.info("合并附注自动刷新无视图上下文：%s", base)
                return base

            seen: set[str] = set()
            nodes = []
            for node in iter_nodes(tree):
                node_key = str(getattr(node, "node_key", "") or "").strip()
                if not node_key or node_key in seen:
                    continue
                seen.add(node_key)
                nodes.append(node)

            if not nodes:
                base["skipped"].append({"scope": "event", "reason": "企业树没有有效 node_key"})
                base["ended_at"] = _now()
                logger.info("合并附注自动刷新无有效节点：%s", base)
                return base

            for node in nodes:
                node_key = str(node.node_key)
                node_out = _node_result(node)
                try:
                    result = await fill_note_sections(
                        db,
                        project_id,
                        year,
                        section_ids,
                        node_key=node_key,
                        template_type=template_type,
                        context=context,
                        tree=tree,
                        view_context=view_context,
                    )
                    # 一个节点的成功章节先提交；后续节点失败不能撤销已完成节点。
                    if result.get("results"):
                        # fill_note_sections 已按章节 SAVEPOINT 隔离失败；这里只提交本节点
                        # 的成功章节，不能因另一个章节失败而 rollback 整个节点的成功写入。
                        await db.commit()

                    for persisted in result.get("results", []):
                        item = {
                            "node_key": node_key,
                            "section_id": persisted.get("section_id"),
                            "template_type": template_type,
                            "status": persisted.get("status", "persisted"),
                            "record_id": persisted.get("record_id"),
                            "manual_preserved_count": persisted.get("kept_manual_count", 0),
                        }
                        node_out["sections"].append(item)
                        node_out["persisted"] += 1
                        base["persisted"].append(item)
                    for failure in result.get("failures", []):
                        item = {
                            "node_key": node_key,
                            "section_id": failure.get("section_id"),
                            "template_type": template_type,
                            "status": "failed",
                            "error": str(failure.get("error") or "章节刷新失败"),
                            "retry": True,
                        }
                        node_out["sections"].append(item)
                        node_out["failed"] += 1
                        base["failed"].append(item)
                    node_out["skipped"] = len(section_ids) - len(node_out["sections"])
                    if node_out["failed"]:
                        node_out["status"] = "failed" if not node_out["persisted"] else "partial"
                    elif node_out["persisted"]:
                        node_out["status"] = "persisted"
                    else:
                        node_out["status"] = "skipped"
                except Exception as exc:  # noqa: BLE001 - 单节点失败不阻断后续节点
                    await db.rollback()
                    error_text = str(exc)
                    node_out["status"] = "failed"
                    node_out["failed"] = len(section_ids)
                    # 节点级异常可能发生在章节编排器循环之前，不能只返回一个
                    # section_id=None 的笼统错误；按本次实际待处理章节展开，调用方
                    # 才能逐章展示和重试，也能让 failed 计数与失败条目数一致。
                    for section_id in section_ids:
                        item = {
                            "node_key": node_key,
                            "section_id": section_id,
                            "template_type": template_type,
                            "status": "failed",
                            "error": error_text,
                            "retry": True,
                        }
                        node_out["sections"].append(item)
                        base["failed"].append(item)
                base.setdefault("nodes", []).append(node_out)

            if base["failed"] and base["persisted"]:
                base["status"] = "partial"
            elif base["failed"]:
                base["status"] = "failed"
            elif base["persisted"]:
                base["status"] = "persisted"
            else:
                base["status"] = "skipped"
    except Exception as exc:  # noqa: BLE001 - 自动下游必须 fail-open
        base["status"] = "failed"
        base["failed"].append({
            "scope": "event",
            "error": str(exc),
            "retry": True,
        })
        logger.exception(
            "合并附注自动刷新失败（fail-open）：project=%s year=%s event=%s",
            project_id,
            year,
            event_type,
        )

    base["ended_at"] = _now()
    logger.info(
        "合并附注自动刷新完成：project=%s year=%s status=%s persisted=%d failed=%d",
        project_id,
        year,
        base["status"],
        len(base["persisted"]),
        len(base["failed"]),
    )
    return base


def register_consol_note_formula_refresh_handler(event_bus: Any) -> None:
    """注册附注自动刷新 handler。

    只订阅 TB 和显式声明附注影响的底稿保存；不直接订阅 ADJUSTMENT_APPROVED，
    因为审批重算 handler 会发布唯一的 TRIAL_BALANCE_UPDATED 下游事件。
    """
    for event_type in (EventType.TRIAL_BALANCE_UPDATED, EventType.WORKPAPER_SAVED):
        handlers = getattr(event_bus, "_handlers", {}).get(event_type, [])
        if handle_consol_note_formula_refresh not in handlers:
            event_bus.subscribe(event_type, handle_consol_note_formula_refresh)
    logger.info(
        "已注册合并附注节点级自动刷新 handler（TRIAL_BALANCE_UPDATED、WORKPAPER_SAVED）"
    )
