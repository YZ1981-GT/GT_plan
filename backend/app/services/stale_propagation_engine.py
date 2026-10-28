"""Stale Propagation Engine — 统一联动总线 (Sprint 2)

**唯一对外入口**：`on_change` 方法。所有 stale 传播事件通过 event_handlers 订阅本类。
详细分层说明见 backend/docs/STALE-PROPAGATION-LAYERS.md

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


# ─── 起点身份（acnr-foundation-defect-closure T21，需求 9.3，design §10.2） ────────
#
# 图键与写入口都经 ``acnr.v2_canonical`` 算 identity_key（只调 exact_identity，不用正则从表显示名里猜
# sheet_code）：同一物理格 / 同一张表同一标签的多种写法并入同一个键；算不出身份的输入不写库并返回原因。


def _is_addr_form(uri: str) -> bool:
    """addr_id 形态 ``{wp_code}/{sheet_code}/{末段}``（首个 ``/`` 之前不含冒号）。"""
    head = uri.split("/", 1)[0]
    return ":" not in head and uri.count("/") >= 2


def _identity_of(uri: str, index: Any = None) -> Any:
    """WP 写法或 addr_id → ``CanonicalNode``；非 WP 域返回 None（按字面）。"""
    from app.services.acnr import v2_canonical

    if uri.startswith("WP:"):
        return v2_canonical.canonical_uri(uri, index=index)
    if _is_addr_form(uri):
        return v2_canonical.canonical_addr(uri, index=index)
    return None


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
        # identity_key → 图键列表（同一身份的多种写法）；按目录版本惰性构建（T21）
        self._identity_index: dict[str, list[str]] = {}
        self._identity_version: str | None = None
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
            # 身份索引在首次使用时按当前目录构建（避免导入期加载目录）
            self._identity_index = {}
            self._identity_version = None
            logger.info("StalePropagationEngine: loaded %d edges into adjacency list", len(edges))
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.warning(
                "Failed to load unified_dependency_graph.json: %s, entering degraded mode",
                e,
            )
            self._degraded = True

    def _ensure_identity_index(self) -> dict[str, list[str]]:
        """identity_key → 图键列表；目录版本变化时重建。

        - ``WP:`` 图键经 ``v2_canonical.canonical_uri`` 算身份，同一身份的多种写法进同一个列表（不再
          ``setdefault`` 先到者胜出）；算不出身份的图键只能按字面命中。
        - 其他图键（TB: / REPORT: / addr_id 形态等）只按字面：addr_id 形态的图键若由旧构建器用正则归一得到，
          不能当作可信身份（design §10.2、§16 Q6）。
        """
        from app.services.acnr.catalog import get_catalog

        catalog = get_catalog()
        # 版本含图键数：启动后注入的边（workpaper_trace_stale_integration）新增图键时重建
        version = f"{getattr(catalog, 'registry_version', '') or id(catalog)}#{len(self._graph)}"
        if self._identity_version == version:
            return self._identity_index
        index: dict[str, list[str]] = {}
        for key in self._graph:
            index.setdefault(key, []).append(key)
            if key.startswith("WP:"):
                ident = _identity_of(key, catalog).identity_key
                if ident and ident != key:
                    index.setdefault(ident, []).append(key)
        self._identity_index = index
        self._identity_version = version
        return index

    def _start_keys(self, source_uri: str) -> tuple[list[str], Any]:
        """写入口：输入 → (BFS 起点图键, 无法确定身份时的 CanonicalNode)。

        WP 写法 / addr_id 先算 identity_key 再查索引；identity_key 为空时不给起点并返回原因。
        身份算出但图中无此节点 → ([], None)（空影响，不是错误）。非 WP 域按字面、不加载目录。
        """
        node = _identity_of(source_uri)
        if node is None:
            return ([source_uri] if source_uri in self._graph else []), None
        if not node.identity_key:
            return [], node
        keys = list(self._ensure_identity_index().get(node.identity_key, []))
        if source_uri in self._graph and source_uri not in keys:
            keys.append(source_uri)
        return keys, None

    def reload_graph(self) -> None:
        """重新加载依赖图（用于图更新后刷新）。身份索引随之清空、下次使用时重建。"""
        self._graph.clear()
        self._reverse_graph.clear()
        self._identity_index = {}
        self._identity_version = None
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

    def _bfs_many(self, starts: list[str], max_depth: int = 5) -> list[str]:
        """多起点 BFS（同一身份的多种写法）：起点自身都不计入结果。"""
        if len(starts) == 1:
            return self._bfs(starts[0], max_depth=max_depth)
        affected: list[str] = []
        seen: set[str] = set(starts)
        for start in starts:
            for uri in self._bfs(start, max_depth=max_depth):
                if uri not in seen:
                    seen.add(uri)
                    affected.append(uri)
        return affected

    @staticmethod
    def _unresolved_response(node: Any) -> dict[str, Any]:
        return {
            "affected": [],
            "total": 0,
            "degraded": False,
            "unresolved_code": node.unresolved_code,
            "unresolved_reason": node.unresolved_reason,
        }

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
            变更源 URI（T21：起点只按精确身份，见 ``_start_keys``）：
            - ``WP:{wp_code}:{表名/别名/编码}:{A1 或标签}`` → 经 exact_identity 算 identity_key 后查图
            - addr_id ``{wp_code}/{sheet_code}/{cell}`` → 同上
            - 非 WP 域（REPORT:/TB:/NOTE: 等）→ 按字面
            身份算不出时不写库，返回 ``unresolved_code`` / ``unresolved_reason``。
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

        # 起点只按精确身份（T21 / 需求 9.3）：算不出身份不写库、返回原因
        start_keys, unresolved = self._start_keys(source_uri)
        if unresolved is not None:
            logger.info("[StalePropagation] 起点无法确定身份，不写 stale：%s（%s）",
                        source_uri, unresolved.unresolved_code)
            return self._unresolved_response(unresolved)

        # BFS 遍历
        affected_uris = self._bfs_many(start_keys, max_depth=5) if start_keys else []

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

    def preview_impact(self, source_uri: str, max_depth: int = 5) -> dict[str, Any]:
        """只读下游影响预览：只做 BFS，不写 DB、不推 SSE、不记审计。

        供 ``GET /api/linkage-bus/impact-by-addr`` 用——该端点原来是会写库的 GET
        （调 :meth:`on_change`），改为只读预览后不再有副作用（spec
        acnr-foundation-defect-closure D8 / 需求 10）。

        降级模式下尝试重载图；仍降级则返回空影响 + ``degraded=True``（不回退到
        粗粒度 mark_stale——那是写操作，只读预览不该触发）。
        """
        if self._degraded:
            self._load_graph()
            if self._degraded:
                return {"affected": [], "total": 0, "degraded": True}

        start_keys, unresolved = self._start_keys(source_uri)
        if unresolved is not None:
            return self._unresolved_response(unresolved)
        affected_uris = self._bfs_many(start_keys, max_depth=max_depth) if start_keys else []
        return {
            "affected": affected_uris,
            "total": len(affected_uris),
            "degraded": False,
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
