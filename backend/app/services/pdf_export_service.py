"""PDF 导出服务 — 将底稿及AI内容导出为带标注的 PDF

提供两种导出模式：
1. export_workpaper_with_ai_markers: 在底稿 PDF 中高亮标注 AI 生成的内容（淡紫色）
2. generate_ai_content_pdf: 生成独立的 AI 内容报告（包含"AI辅助"水印标签）
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional
from uuid import UUID

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PDFExportService:
    """PDF 导出服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_workpaper_with_ai_markers(
        self, workpaper_id: UUID, output_path: str
    ) -> dict[str, Any]:
        """
        导出底稿为 PDF，AI 生成的内容以淡紫色高亮显示。

        Args:
            workpaper_id: 底稿 ID
            output_path: 输出文件路径

        Returns:
            {"file_path": str, "ai_content_count": int, "page_count": int}
        """
        from app.models.ai_models import AIContent

        # 查询关联的 AI 内容
        stmt = select(AIContent).where(
            AIContent.source_type == "workpaper",
            AIContent.source_id == workpaper_id,
            AIContent.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        ai_contents = result.scalars().all()

        # 构建 PDF
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "Title",
            parent=styles["Title"],
            fontSize=16,
            spaceAfter=20,
        )
        ai_style = ParagraphStyle(
            "AIHighlight",
            parent=styles["Normal"],
            backColor=colors.HexColor("#E8D5FF"),
            borderColor=colors.HexColor("#9B59B6"),
            borderWidth=1,
            borderPadding=4,
            fontName="Helvetica",
            fontSize=10,
            leading=14,
        )
        normal_style = styles["Normal"]

        story: List[Any] = []

        # 标题
        story.append(Paragraph("底稿内容（AI辅助标注）", title_style))
        story.append(
            Paragraph(
                f"底稿ID: {workpaper_id} &nbsp;&nbsp; "
                f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                normal_style,
            )
        )
        story.append(Spacer(1, 0.5 * cm))

        # AI 内容
        ai_count = 0
        for content in ai_contents:
            ai_count += 1
            summary = content.summary or content.content_text[:200]
            story.append(
                Paragraph(
                    f"<b>[AI辅助 · 置信度: {content.confidence_score:.0%}]</b> {summary}",
                    ai_style,
                )
            )
            story.append(Spacer(1, 0.3 * cm))

        if ai_count == 0:
            story.append(Paragraph("（本底稿暂无 AI 辅助生成的内容）", normal_style))

        # 水印页脚
        story.append(Spacer(1, 1 * cm))
        story.append(
            Paragraph(
                f"<i>共 {ai_count} 处 AI 辅助内容 · 审计作业平台导出</i>",
                normal_style,
            )
        )

        doc.build(story)

        logger.info(f"底稿 PDF 已导出: {output_path}，AI 内容 {ai_count} 处")
        return {
            "file_path": output_path,
            "ai_content_count": ai_count,
            "page_count": 1,
        }

    async def generate_ai_content_pdf(
        self, project_id: UUID, output_path: str
    ) -> dict[str, Any]:
        """
        生成项目中所有 AI 内容的独立 PDF 报告。

        Args:
            project_id: 项目 ID
            output_path: 输出文件路径

        Returns:
            {"file_path": str, "ai_content_count": int, "page_count": int}
        """
        from app.models.ai_models import AIContent

        stmt = select(AIContent).where(
            AIContent.project_id == project_id,
            AIContent.is_deleted == False,  # noqa: E712
        ).order_by(AIContent.created_at.desc())
        result = await self.db.execute(stmt)
        ai_contents = result.scalars().all()

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "Title",
            parent=styles["Title"],
            fontSize=18,
            spaceAfter=12,
        )
        subtitle_style = ParagraphStyle(
            "Subtitle",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.grey,
            spaceAfter=20,
        )
        ai_header_style = ParagraphStyle(
            "AIHeader",
            parent=styles["Normal"],
            backColor=colors.HexColor("#E8D5FF"),
            borderColor=colors.HexColor("#9B59B6"),
            borderWidth=1,
            borderPadding=6,
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            spaceAfter=4,
        )
        content_style = ParagraphStyle(
            "Content",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            spaceAfter=12,
        )

        story: List[Any] = []

        # 标题页
        story.append(Paragraph("AI 辅助内容报告", title_style))
        story.append(
            Paragraph(
                f"项目ID: {project_id} &nbsp;&nbsp; "
                f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                subtitle_style,
            )
        )

        ai_count = 0
        for content in ai_contents:
            ai_count += 1
            content_type = content.content_type.value if hasattr(content.content_type, "value") else content.content_type
            story.append(
                Paragraph(
                    f"<b>[{ai_count}] {content_type} · "
                    f"置信度: {content.confidence_score:.0%}</b>",
                    ai_header_style,
                )
            )
            summary = content.summary or content.content_text[:500]
            story.append(Paragraph(summary, content_style))

        if ai_count == 0:
            story.append(Paragraph("（暂无 AI 辅助内容）", content_style))

        # 汇总
        story.append(Spacer(1, 0.5 * cm))
        summary_data = [
            ["AI 辅助内容总数", str(ai_count)],
            ["报告生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ]
        summary_table = Table(summary_data, colWidths=[6 * cm, 10 * cm])
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F5F5")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(summary_table)

        doc.build(story)

        logger.info(f"AI 内容 PDF 已生成: {output_path}，共 {ai_count} 处")
        return {
            "file_path": output_path,
            "ai_content_count": ai_count,
            "page_count": 1,
        }
