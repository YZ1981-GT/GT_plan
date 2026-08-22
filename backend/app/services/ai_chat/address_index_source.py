"""AddressCoordinateIndexSource（Task 22）

Feature: dsh-agent-panel-integration
Requirements:
  - 6.2：实现并注册 AddressCoordinateIndexSource
  - 6.3：复用现有增量更新/fingerprint/stale
  - 6.4：文本只来自 AddressEntry/ACNR 字段
  - 6.5：ACNR canonical invalidation event 驱动更新
  - 6.6：搜索严格限定 source type；embedding down 返回 semantic_unavailable
Design: "Components and Interfaces → 10. AddressCoordinateIndexSource"

实现 ``IndexSource`` 协议，从 ACNR 的 L3 RuntimeIndex（地址坐标注册表）
提取可索引文本。每个地址条目生成的文本包含：
- addr_id（稳定主键 ``{wp_code}/{sheet_code}/{coordinate_key}``）
- label / domain / formula_ref / description

注册后由 KnowledgeIndexService 统一调度 build_index / incremental_update。
ACNR invalidation 事件通过 ``mark_index_stale`` 标记过期，下次 build 时重建。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = [
    "AddressCoordinateIndexSource",
    "ADDRESS_COORDINATE_SOURCE_TYPE",
    "check_embedding_health",
]

#: 索引源类型标识（与迁移中 enum 值一致）
ADDRESS_COORDINATE_SOURCE_TYPE = "address_coordinate"


class EmbeddingUnavailableError(RuntimeError):
    """Embedding 服务不可用（Task 22 前置检查失败时抛出）。"""

    pass


async def check_embedding_health(db: AsyncSession) -> bool:
    """🔴 前置检查 embedding health（Req 6.2）。

    不可用则任务保持阻塞，不以空索引完成。
    检查方式：尝试对一个短文本做 embedding 调用。

    Returns:
        True 表示可用
    """
    try:
        from app.services.ai_service import AIService

        ai_svc = AIService()
        # 尝试生成一个测试 embedding
        result = await ai_svc.get_embedding("embedding health check")
        if result is not None and len(result) > 0:
            return True
        logger.warning("embedding health check 返回空结果")
        return False
    except Exception as exc:
        logger.warning("embedding health check 失败: %s: %s", type(exc).__name__, exc)
        return False


class AddressCoordinateIndexSource:
    """地址坐标索引源 — 从 ACNR 提取可索引文本。

    实现 ``IndexSource`` 协议：
    - source_type = "address_coordinate"
    - fetch_texts(project_id) → [(source_type, addr_id, text)]

    文本来源（Req 6.4）：
    - ACNR L3 RuntimeIndex 运行时条目
    - 回退：address_registry V1 条目（legacy 兼容）
    """

    source_type: str = ADDRESS_COORDINATE_SOURCE_TYPE

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def fetch_texts(self, project_id: UUID) -> list[tuple[str, str, str]]:
        """提取项目下所有地址坐标的可索引文本。

        Returns:
            [(source_type_str, addr_id, text)] — source_type 为字面量字符串
            （区别于 BusinessDataSource 返回 enum 实例，本源为后期加入，
            KnowledgeIndexService.build_index 对字符串 source_type 也能处理）。
        """
        texts: list[tuple[str, str, str]] = []

        # ① 尝试从 ACNR L3 RuntimeIndex 获取
        try:
            acnr_texts = await self._fetch_from_acnr(project_id)
            if acnr_texts:
                texts.extend(acnr_texts)
                return texts
        except Exception as exc:
            logger.warning(
                "ACNR L3 RuntimeIndex 读取失败，回退 legacy: %s", exc
            )

        # ② 回退：从 legacy address_registry 获取
        try:
            legacy_texts = await self._fetch_from_legacy(project_id)
            texts.extend(legacy_texts)
        except Exception as exc:
            logger.warning(
                "legacy address_registry 读取也失败: %s", exc
            )

        return texts

    async def _fetch_from_acnr(
        self, project_id: UUID
    ) -> list[tuple[str, str, str]]:
        """从 ACNR L3 RuntimeIndex 提取地址坐标文本。"""
        try:
            from app.services.acnr.runtime import query_project_entries
        except ImportError:
            return []

        entries = await query_project_entries(self._db, str(project_id))
        if not entries:
            return []

        results: list[tuple[str, str, str]] = []
        for entry in entries:
            addr_id = _extract_addr_id(entry)
            if not addr_id:
                continue
            text = _build_index_text(entry)
            if text:
                results.append((self.source_type, addr_id, text))

        return results

    async def _fetch_from_legacy(
        self, project_id: UUID
    ) -> list[tuple[str, str, str]]:
        """从 legacy address_registry 读取地址条目。"""
        try:
            from app.services.address_registry import (
                get_registry,
            )

            registry = get_registry()
            entries = registry.list_by_project(str(project_id))
        except (ImportError, Exception):
            return []

        results: list[tuple[str, str, str]] = []
        for entry in entries:
            addr_id = getattr(entry, "addr_id", None) or getattr(entry, "uri", "")
            if not addr_id:
                continue
            text = _build_legacy_index_text(entry)
            if text:
                results.append((self.source_type, str(addr_id), text))

        return results


# ---------------------------------------------------------------------------
# ACNR invalidation 驱动更新（Req 6.5）
# ---------------------------------------------------------------------------


async def on_acnr_invalidate(
    project_id: str,
    *,
    trigger: str | None = None,
) -> None:
    """ACNR canonical invalidation event 处理器。

    收到失效事件后标记地址坐标索引为 stale，下次 build_index 时重建。
    由 ``acnr.events.invalidate`` 的 handler 链调用（需注册）。
    """
    from app.core.database import get_db_contextmanager

    try:
        async with get_db_contextmanager() as db:
            from app.services.knowledge_index_service import KnowledgeIndexService

            svc = KnowledgeIndexService(db)
            stale_count = await svc.mark_index_stale(
                source_id=f"address_coordinate:{project_id}",
            )
            if stale_count:
                logger.info(
                    "地址坐标索引标记 stale（project=%s trigger=%s count=%d）",
                    project_id, trigger, stale_count,
                )
    except Exception as exc:
        logger.warning(
            "on_acnr_invalidate 处理失败（不阻断主流程）: %s", exc
        )


# ---------------------------------------------------------------------------
# 文本构建辅助
# ---------------------------------------------------------------------------


def _extract_addr_id(entry: Any) -> str | None:
    """从 ACNR entry 提取稳定 addr_id。"""
    # ACNR L3 entry 通常有 addr_id 属性
    addr_id = getattr(entry, "addr_id", None)
    if addr_id:
        return str(addr_id)
    # 回退：从 wp_code / sheet_code / coordinate_key 组装
    wp_code = getattr(entry, "wp_code", "")
    sheet_code = getattr(entry, "sheet_code", "")
    coord_key = getattr(entry, "coordinate_key", "") or getattr(entry, "cell", "")
    if wp_code and sheet_code and coord_key:
        return f"{wp_code}/{sheet_code}/{coord_key}"
    return None


def _build_index_text(entry: Any) -> str:
    """从 ACNR entry 构建索引文本。

    Req 6.4：文本只来自 AddressEntry/ACNR 字段。
    包含：label / domain / formula_ref / description / wp_code / sheet 名。
    """
    parts: list[str] = []

    label = getattr(entry, "label", "") or getattr(entry, "display_name", "")
    if label:
        parts.append(label)

    domain = getattr(entry, "domain", "")
    if domain:
        parts.append(f"[{domain}]")

    wp_code = getattr(entry, "wp_code", "")
    if wp_code:
        parts.append(f"底稿:{wp_code}")

    sheet = getattr(entry, "sheet_code", "") or getattr(entry, "sheet_name", "")
    if sheet:
        parts.append(f"Sheet:{sheet}")

    formula_ref = getattr(entry, "formula_ref", "") or getattr(entry, "expression", "")
    if formula_ref:
        parts.append(f"公式:{formula_ref}")

    description = getattr(entry, "description", "") or getattr(entry, "note", "")
    if description:
        parts.append(description)

    return " | ".join(parts) if parts else ""


def _build_legacy_index_text(entry: Any) -> str:
    """从 legacy AddressEntry 构建索引文本。"""
    parts: list[str] = []

    label = getattr(entry, "label", "") or getattr(entry, "display_name", "")
    if label:
        parts.append(label)

    uri = getattr(entry, "uri", "")
    if uri:
        parts.append(uri)

    domain = getattr(entry, "domain", "")
    if domain:
        parts.append(f"[{domain}]")

    return " | ".join(parts) if parts else ""
