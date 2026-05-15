"""底稿结论提取与汇总服务

Sprint 8 Task 8.4: 结论提取 + 汇总 + 分类。
从 wp_template_metadata.conclusion_cell 定位结论单元格，提取并汇总。
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 结论分类
CONCLUSION_TYPES = {
    "no_exception": "无异常",
    "adjusted": "存在差异已调整",
    "material_misstatement": "存在重大错报",
    "scope_limitation": "审计范围受限",
    "pending": "待完成",
    "not_applicable": "不适用",
}

# 结论关键词→分类映射
_CONCLUSION_KEYWORDS = {
    "no_exception": ["无异常", "未发现异常", "核对一致", "无重大差异", "符合"],
    "adjusted": ["已调整", "调整分录", "已更正", "差异已消除"],
    "material_misstatement": ["重大错报", "重大差异", "未调整", "重大偏差"],
    "scope_limitation": ["范围受限", "无法获取", "未能实施"],
}


class WpConclusionService:
    """底稿结论服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def extract_conclusion(self, wp_id: UUID) -> Optional[dict]:
        """从底稿提取结论

        根据 wp_template_metadata.conclusion_cell 定位结论内容。

        Returns:
            {conclusion_text, conclusion_type, wp_code, wp_name}
        """
        # 获取底稿及其模板元数据
        row = (await self.db.execute(sa.text("""
            SELECT w.id, w.parsed_data, i.wp_code, i.wp_name,
                   m.conclusion_cell
            FROM working_paper w
            JOIN wp_index i ON w.wp_index_id = i.id
            LEFT JOIN wp_template_metadata m ON m.wp_code = i.wp_code
            WHERE w.id = :wid
        """), {"wid": str(wp_id)})).first()

        if not row:
            return None

        conclusion_text = ""
        # 从 conclusion_cell 配置提取
        if row.conclusion_cell and row.parsed_data:
            cell_config = row.conclusion_cell  # e.g. {"sheet": "审定表", "cell": "B30"}
            if isinstance(cell_config, dict):
                # 尝试从 parsed_data 中按 cell 引用取值
                sheet = cell_config.get("sheet", "")
                cell = cell_config.get("cell", "")
                pd = row.parsed_data or {}
                # 简化：从 parsed_data 的 cells 字典取值
                cells = pd.get("cells", {})
                conclusion_text = cells.get(f"{sheet}!{cell}", "")

        # 如果没有从 cell 取到，尝试从 parsed_data 的 conclusion 字段取
        if not conclusion_text and row.parsed_data:
            conclusion_text = row.parsed_data.get("conclusion", "")

        # 分类
        conclusion_type = self._classify_conclusion(conclusion_text)

        return {
            "wp_id": str(wp_id),
            "wp_code": row.wp_code,
            "wp_name": row.wp_name,
            "conclusion_text": conclusion_text,
            "conclusion_type": conclusion_type,
            "conclusion_label": CONCLUSION_TYPES.get(conclusion_type, "未知"),
        }

    async def get_project_conclusions(
        self, project_id: UUID, cycle: Optional[str] = None
    ) -> list[dict]:
        """获取项目所有底稿结论汇总

        Args:
            project_id: 项目 ID
            cycle: 可选循环过滤 (D/E/F/...)

        Returns:
            结论列表
        """
        q = """
            SELECT w.id FROM working_paper w
            JOIN wp_index i ON w.wp_index_id = i.id
            WHERE w.project_id = :pid AND w.is_deleted = false
        """
        params: dict = {"pid": str(project_id)}

        if cycle:
            q += " AND i.wp_code LIKE :prefix"
            params["prefix"] = f"{cycle}%"

        q += " ORDER BY i.wp_code"
        rows = (await self.db.execute(sa.text(q), params)).fetchall()

        conclusions = []
        for row in rows:
            c = await self.extract_conclusion(UUID(row.id))
            if c:
                conclusions.append(c)

        return conclusions

    async def get_summary_by_cycle(self, project_id: UUID) -> dict:
        """按循环汇总结论统计

        Returns:
            {cycles: [{cycle, total, by_type: {no_exception: N, ...}}]}
        """
        conclusions = await self.get_project_conclusions(project_id)

        cycle_stats: dict[str, dict] = {}
        for c in conclusions:
            wp_code = c.get("wp_code", "")
            cycle = wp_code[0].upper() if wp_code else "?"

            if cycle not in cycle_stats:
                cycle_stats[cycle] = {"total": 0, "by_type": {}}

            cycle_stats[cycle]["total"] += 1
            ctype = c.get("conclusion_type", "pending")
            cycle_stats[cycle]["by_type"].setdefault(ctype, 0)
            cycle_stats[cycle]["by_type"][ctype] += 1

        return {
            "cycles": [
                {"cycle": k, **v}
                for k, v in sorted(cycle_stats.items())
            ],
            "total_workpapers": len(conclusions),
            "total_with_conclusion": sum(
                1 for c in conclusions if c.get("conclusion_type") != "pending"
            ),
        }

    def _classify_conclusion(self, text: str) -> str:
        """根据结论文本自动分类"""
        if not text or not text.strip():
            return "pending"

        text_lower = text.lower()
        for ctype, keywords in _CONCLUSION_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return ctype

        # 有文本但无法分类，默认为无异常
        return "no_exception"
