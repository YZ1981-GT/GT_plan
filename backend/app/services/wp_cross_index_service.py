"""交叉索引解析服务 — →底稿编码-页码 格式自动识别+双向链接

Sprint 11 Task 11.5 (Stub)

完整实现需要 Univer 单元格内容解析 + 正则匹配。
此处提供后端解析逻辑和双向链接管理。
"""

from __future__ import annotations

import re
import uuid
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 交叉索引格式：→D2-3 表示引用 D2 底稿第 3 页
CROSS_INDEX_PATTERN = re.compile(r"→([A-Z]\d+(?:\.\d+)?)-?(\d+)?")


class CrossIndexLink:
    """交叉索引链接"""
    def __init__(
        self,
        source_wp_id: str,
        source_cell: str,
        target_wp_code: str,
        target_page: Optional[int] = None,
    ):
        self.source_wp_id = source_wp_id
        self.source_cell = source_cell
        self.target_wp_code = target_wp_code
        self.target_page = target_page


class WpCrossIndexService:
    """交叉索引管理"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def parse_cross_references(cell_content: str) -> list[dict]:
        """解析单元格内容中的交叉索引引用"""
        matches = CROSS_INDEX_PATTERN.findall(cell_content)
        refs = []
        for match in matches:
            wp_code = match[0]
            page = int(match[1]) if match[1] else None
            refs.append({
                "wp_code": wp_code,
                "page": page,
                "raw": f"→{wp_code}" + (f"-{page}" if page else ""),
            })
        return refs

    async def get_outgoing_refs(
        self,
        *,
        wp_id: uuid.UUID,
    ) -> list[dict]:
        """获取该底稿引用的其他底稿（引用了）"""
        # Stub: 实际实现扫描底稿所有单元格内容
        return []

    async def get_incoming_refs(
        self,
        *,
        wp_id: uuid.UUID,
        wp_code: str,
    ) -> list[dict]:
        """获取引用了该底稿的其他底稿（被引用）"""
        # Stub: 实际实现反向查询
        return []

    async def build_bidirectional_links(
        self,
        *,
        project_id: uuid.UUID,
    ) -> dict:
        """构建项目内所有底稿的双向交叉索引"""
        # Stub: 实际实现遍历所有底稿单元格
        return {"total_links": 0, "links": []}
