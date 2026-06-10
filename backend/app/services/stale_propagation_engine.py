"""Stale Propagation Engine — 统一联动总线 (Sprint 2)

统一入口：变更 → BFS → 写 DB → SSE 推送
降级模式：依赖图加载失败 / Redis 断连 → 回退 event_handlers 粗粒度 mark_stale

Validates: Requirements F6, F7, F8, F25, F28
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session as async_session_factory

logger = logging.getLogger(__name__)

# Data directory for unified_dependency_graph.json
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


class StalePropagationEngine:
    """统一 Stale 传播引擎。

    - on_change(): 统一入口
    - _bfs(): BFS 遍历依赖图，visited 防环，max_depth 截断
    - _mark_stale_by_uri(): 按 URI 前缀分发写 DB
    - _notify_frontend(): SSE 推送 linkage:stale-changed 事件
    """

    def __init__(self) -> None:
        self._graph: dict[str, list[str]] = {}  # adjacency list (source → targets)
        self._reverse_graph: dict[str, list[str]] = {}  # target → sources
        self._degraded: bool = False
        self._loaded: bool = False
        self._load_graph()

    # ─── Graph Loading ────────────────────────────────────────────────────

    def _load_graph(self) -> None:
        """从 unified_dependency_graph.json 加载依赖图到内存邻接表。"""
        graph_path = DATA_DIR / "unified_dependency_graph.json"
        if not graph_path.exists():
            logger.warning(
                "unified_dependency_graph.json not found at %s, entering degraded mode",
                graph_path,
            )
            self._degraded = True
            return

        try:
            data = json.loads(graph_path.read_text(encoding="utf-8"))
            edges = data.get("edges", [])
            for edge in edges:
                source = edge.get("source", "")
                target = edge.get("target", "")
                if source and target:
                    self._graph.setdefault(source, []).append(target)
                    self._reverse_graph.setdefault(target, []).append(source)
            self._loaded = True
            self._degraded = False
            logger.info(
                "StalePropagationEngine: loaded %d edges into adjacency list",
                len(edges),
            )
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.warning(
                "Failed to load unified_dependency_graph.json: %s, entering degraded mode",
                e,
            )
            self._degraded = True

    def reload_graph(self) -> None:
        """重新加载依赖图（用于图更新后刷新）。"""
        self._graph.clear()
        self._reverse_graph.clear()
        self._loaded = False
        self._load_graph()

    # ─── BFS Traversal (Task 2.2) ────────────────────────────────────────

    def _bfs(self, start: str, max_depth: int = 5) -> list[str]:
        """BFS 遍历依赖图，返回受影响的下游 URI 列表。

        - visited 集合防环
        - max_depth 截断防止无限传播
        - 不包含 start 自身
        """
        if not self._graph:
            return []

        visited: set[str] = set()
        visited.add(start)
        queue: deque[tuple[str, int]] = deque()
        queue.append((start, 0))
        affected: list[str] = []

        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            neighbors = self._graph.get(current, [])
            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    affected.append(neighbor)
                    queue.append((neighbor, depth + 1))

        return affected

    # ─── Mark Stale by URI (Task 2.3) ────────────────────────────────────

    async def _mark_stale_by_uri(
        self, uris: list[str], project_id: UUID | str, year: int
    ) -> dict[str, int]:
        """按 URI 前缀分发写 DB：

        - WP:* → UPDATE working_paper SET prefill_stale=true WHERE wp_code=...
        - REPORT:* → UPDATE financial_report SET is_stale=true WHERE ...
        - NOTE:* → UPDATE disclosure_notes SET is_stale=true WHERE ...
        - DELIVERABLE:{word_export_task_id}:{section_code} → UPDATE deliverable_section_state SET is_stale=true
        """
        pid = str(project_id)
        counts: dict[str, int] = {"wp": 0, "report": 0, "note": 0, "deliverable": 0}

        # Group URIs by module prefix
        wp_codes: list[str] = []
        report_codes: list[str] = []
        note_codes: list[str] = []
        # DELIVERABLE:{word_export_task_id}:{section_code}
        deliverable_codes: list[tuple[str, str]] = []

        for uri in uris:
            parts = uri.split(":", 2)
            module = parts[0].upper() if parts else ""
            code = parts[1] if len(parts) > 1 else ""
            if module == "WP" and code:
                wp_codes.append(code)
            elif module == "REPORT" and code:
                report_codes.append(code)
            elif module == "NOTE" and code:
                note_codes.append(code)
            elif module == "DELIVERABLE" and code:
                section_code = parts[2] if len(parts) > 2 else ""
                if section_code:
                    deliverable_codes.append((code, section_code))

        async with async_session_factory() as session:
            try:
                # Mark workpapers stale (working_paper 通过 wp_index 关联 wp_code)
                if wp_codes:
                    result = await session.execute(
                        text(
                            "UPDATE working_paper SET prefill_stale = true "
                            "WHERE project_id = :pid AND wp_index_id IN ("
                            "  SELECT id FROM wp_index WHERE wp_code = ANY(:codes)"
                            ")"
                        ),
                        {"pid": pid, "codes": wp_codes},
                    )
                    counts["wp"] = result.rowcount or 0

                # Mark reports stale
                if report_codes:
                    result = await session.execute(
                        text(
                            "UPDATE financial_report SET is_stale = true "
                            "WHERE project_id = :pid AND year = :year "
                            "AND row_code = ANY(:codes)"
                        ),
                        {"pid": pid, "year": year, "codes": report_codes},
                    )
                    counts["report"] = result.rowcount or 0

                # Mark notes stale (实际列名 note_section 不是 section_code)
                if note_codes:
                    result = await session.execute(
                        text(
                            "UPDATE disclosure_notes SET is_stale = true "
                            "WHERE project_id = :pid AND year = :year "
                            "AND note_section = ANY(:codes)"
                        ),
                        {"pid": pid, "year": year, "codes": note_codes},
                    )
                    counts["note"] = result.rowcount or 0

                # Mark deliverable sections stale (deliverable_section_state)
                if deliverable_codes:
                    total_deliverable = 0
                    for wid, sc in deliverable_codes:
                        res = await session.execute(
                            text(
                                "UPDATE deliverable_section_state SET is_stale = true "
                                "WHERE word_export_task_id = :wid "
                                "AND section_code = :sc "
                                "AND is_stale = false"
                            ),
                            {"wid": wid, "sc": sc},
                        )
                        total_deliverable += res.rowcount or 0
                    counts["deliverable"] = total_deliverable

                await session.commit()
                logger.info(
                    "[StalePropagation] Marked stale: wp=%d report=%d note=%d deliverable=%d (project=%s)",
                    counts["wp"],
                    counts["report"],
                    counts["note"],
                    counts["deliverable"],
                    pid,
                )
            except Exception as e:
                await session.rollback()
                logger.warning("[StalePropagation] _mark_stale_by_uri failed: %s", e)

        return counts

    # ─── SSE Notify Frontend (Task 2.4 + Sprint 4 Task 4.6) ─────────────────────

    async def _notify_frontend(
        self, project_id: UUID | str, affected_uris: list[str]
    ) -> None:
        """SSE 推送 linkage:stale-changed 事件给前端。

        事件格式：
        {
            "event_type": "LINKAGE_STALE_CHANGED",
            "project_id": "...",
            "extra": {
                "linkage_event": "stale-changed",
                "affected_uris": [...],
                "total_affected": N,
                "affected_modules": ["WP", "REPORT", "NOTE"]
            }
        }
        """
        try:
            from app.models.audit_platform_schemas import EventPayload, EventType
            from app.services.event_bus import event_bus

            # 提取受影响的模块列表
            affected_modules = list(set(
                uri.split(":")[0].upper()
                for uri in affected_uris
                if ":" in uri
            ))

            await event_bus.publish_immediate(
                EventPayload(
                    event_type=EventType.LINKAGE_STALE_CHANGED,
                    project_id=str(project_id),
                    extra={
                        "linkage_event": "stale-changed",
                        "affected_uris": affected_uris[:50],  # 限制 payload 大小
                        "total_affected": len(affected_uris),
                        "affected_modules": affected_modules,
                    },
                )
            )
        except Exception as e:
            logger.warning("[StalePropagation] _notify_frontend failed: %s", e)

    # ─── Audit Log ────────────────────────────────────────────────────────

    async def _write_audit_log(
        self,
        source_uri: str,
        affected_uris: list[str],
        project_id: UUID | str,
        duration_ms: int = 0,
    ) -> None:
        """写入传播审计日志到 linkage_audit_log 表。"""
        try:
            async with async_session_factory() as session:
                await session.execute(
                    text(
                        "INSERT INTO linkage_audit_log "
                        "(id, source_uri, affected_count, duration_ms, project_id, created_at) "
                        "VALUES (gen_random_uuid(), :source_uri, :affected_count, :duration_ms, :project_id, NOW())"
                    ),
                    {
                        "source_uri": source_uri,
                        "affected_count": len(affected_uris),
                        "duration_ms": duration_ms,
                        "project_id": str(project_id),
                    },
                )
                await session.commit()
        except Exception as e:
            # 审计日志写入失败不应阻断主流程
            logger.warning(
                "[StalePropagation-Audit] Failed to write audit log: %s (source=%s affected=%d)",
                e,
                source_uri,
                len(affected_uris),
            )

    # ─── Degraded Fallback (Task 2.6) ────────────────────────────────────

    async def _fallback_mark_stale(self, project_id: UUID | str) -> dict[str, Any]:
        """降级模式：跳过 BFS，回退到 event_handlers 粗粒度 mark_stale。"""
        logger.warning(
            "[StalePropagation] Degraded mode: fallback to bulk mark_stale for project=%s",
            project_id,
        )
        try:
            async with async_session_factory() as session:
                from app.services.prefill_engine import mark_stale
                count = await mark_stale(session, str(project_id))
                await session.commit()
                return {"degraded": True, "affected": [], "total": count}
        except Exception as e:
            logger.warning("[StalePropagation] Fallback mark_stale failed: %s", e)
            return {"degraded": True, "affected": [], "total": 0, "error": str(e)}

    # ─── Unified Entry Point (Task 2.5) ──────────────────────────────────

    async def on_change(
        self, source_uri: str, project_id: UUID | str, year: int
    ) -> dict[str, Any]:
        """统一入口：变更 → BFS → 写 DB → SSE 推送。

        Parameters
        ----------
        source_uri : str
            变更源 URI，格式 {module}:{code}:{sheet_name}:{label}
        project_id : UUID | str
            项目 ID
        year : int
            年度

        Returns
        -------
        dict with keys: affected (list[str]), total (int), degraded (bool)
        """
        # 降级模式检查：如果图未加载，尝试重新加载
        if self._degraded:
            self._load_graph()
            if self._degraded:
                return await self._fallback_mark_stale(project_id)

        start_time = time.time()

        # BFS 遍历
        affected_uris = self._bfs(source_uri, max_depth=5)

        if not affected_uris:
            return {"affected": [], "total": 0, "degraded": False}

        # 写 DB stale 标记
        await self._mark_stale_by_uri(affected_uris, project_id, year)

        # SSE 推送前端
        await self._notify_frontend(project_id, affected_uris)

        # 审计日志
        duration_ms = int((time.time() - start_time) * 1000)
        await self._write_audit_log(source_uri, affected_uris, project_id, duration_ms)

        logger.info(
            "[StalePropagation] on_change completed: source=%s affected=%d duration=%dms",
            source_uri,
            len(affected_uris),
            duration_ms,
        )

        return {
            "affected": affected_uris,
            "total": len(affected_uris),
            "degraded": False,
            "duration_ms": duration_ms,
        }

    @property
    def is_degraded(self) -> bool:
        """当前是否处于降级模式。"""
        return self._degraded

    @property
    def graph_size(self) -> int:
        """依赖图边数。"""
        return sum(len(v) for v in self._graph.values())


# ─── Module-level singleton ──────────────────────────────────────────────────

stale_engine = StalePropagationEngine()
