"""跨底稿引用变更检测服务

按 design §2.2 Write Path 步骤 3：
  保存时比较 old vs new html_data 中被其他底稿引用的 cell 值，
  检测是否有跨底稿引用变化，若有则通知 SSE 订阅方刷新。

Requirements: 3.11.4（跨底稿引用传播）+ 3.11.5 + 3.11.6
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.models.workpaper_models import WpCrossRef, WpIndex

logger = logging.getLogger(__name__)

# cross_wp_references.json 路径
_CWR_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cross_wp_references.json"


class CrossRefChange:
    """表示一个跨底稿引用变更"""

    def __init__(
        self,
        ref_id: str,
        source_wp_code: str,
        source_sheet: str,
        target_wp_code: str,
        target_sheet: str | None = None,
        target_cell: str | None = None,
    ):
        self.ref_id = ref_id
        self.source_wp_code = source_wp_code
        self.source_sheet = source_sheet
        self.target_wp_code = target_wp_code
        self.target_sheet = target_sheet
        self.target_cell = target_cell

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_id": self.ref_id,
            "source_wp_code": self.source_wp_code,
            "source_sheet": self.source_sheet,
            "target_wp_code": self.target_wp_code,
            "target_sheet": self.target_sheet,
            "target_cell": self.target_cell,
        }


class CrossRefService:
    """跨底稿引用变更检测"""

    def __init__(self) -> None:
        self._references: list[dict] | None = None

    def _load_references(self) -> list[dict]:
        """加载 cross_wp_references.json（懒加载 + 缓存）"""
        if self._references is not None:
            return self._references
        try:
            data = json.loads(_CWR_PATH.read_text(encoding="utf-8"))
            self._references = data.get("references", [])
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load cross_wp_references.json: %s", exc)
            self._references = []
        return self._references

    def detect_changes(
        self,
        wp_code: str,
        sheet_name: str,
        old_html_data: dict | None,
        new_html_data: dict,
        changed_cells: list[str] | None = None,
    ) -> list[CrossRefChange]:
        """检测跨底稿引用变更。

        比较 old vs new html_data，找出被其他底稿引用的 cell 是否有值变化。
        如果 changed_cells 提供了，只检查这些 cell 是否在引用列表中。

        Args:
            wp_code: 当前底稿编码（如 'D2'）
            sheet_name: 当前 sheet 名
            old_html_data: 保存前的 html_data（可能为 None）
            new_html_data: 保存后的 html_data
            changed_cells: 前端传入的变更 cell 列表（可选优化）

        Returns:
            受影响的跨底稿引用变更列表
        """
        references = self._load_references()
        if not references:
            return []

        # 找出引用当前底稿的条目
        affected: list[CrossRefChange] = []
        for ref in references:
            source_wp = ref.get("source_wp", "")
            # 匹配 source_wp 前缀（如 D2 匹配 D2-1, D2-2 等）
            if not source_wp.startswith(wp_code):
                continue

            # 如果引用指定了 source_sheet，检查是否匹配
            ref_source_sheet = ref.get("source_sheet")
            if ref_source_sheet and ref_source_sheet != sheet_name:
                continue

            # 如果有 changed_cells 且引用指定了 source_cell，检查交集
            ref_source_cell = ref.get("source_cell")
            if changed_cells and ref_source_cell:
                if ref_source_cell not in changed_cells:
                    continue

            # 如果没有 old_html_data，首次保存视为变更
            if old_html_data is None:
                affected.append(CrossRefChange(
                    ref_id=ref.get("ref_id", ""),
                    source_wp_code=source_wp,
                    source_sheet=sheet_name,
                    target_wp_code=ref.get("target_wp", ""),
                    target_sheet=ref.get("target_sheet"),
                    target_cell=ref.get("target_cell"),
                ))
                continue

            # 有 old_html_data 时，比较数据是否有实质变化
            # 简化策略：如果 html_data 整体有变化且存在引用关系，视为变更
            if old_html_data != new_html_data:
                affected.append(CrossRefChange(
                    ref_id=ref.get("ref_id", ""),
                    source_wp_code=source_wp,
                    source_sheet=sheet_name,
                    target_wp_code=ref.get("target_wp", ""),
                    target_sheet=ref.get("target_sheet"),
                    target_cell=ref.get("target_cell"),
                ))

        return affected

    async def get_wp_code_for_wp_id(
        self,
        wp_id: UUID,
        db: AsyncSession,
    ) -> str | None:
        """通过 wp_id 获取 wp_code"""
        from app.models.workpaper_models import WorkingPaper

        query = (
            sa.select(WpIndex.wp_code)
            .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
            .where(WorkingPaper.id == wp_id)
        )
        result = await db.execute(query)
        row = result.scalar_one_or_none()
        return row


# 单例
cross_ref_service = CrossRefService()
