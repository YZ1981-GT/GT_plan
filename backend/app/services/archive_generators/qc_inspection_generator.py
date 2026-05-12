"""归档章节 03 — 质控抽查报告生成器

Refinement Round 7 P1 补完：为归档包生成质控抽查报告文本。

查询项目的 QcInspection 批次及其子项，输出结构化文本报告。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def generate_qc_inspection_report(
    project_id: UUID, db: AsyncSession
) -> bytes | None:
    """生成质控抽查报告文本内容。

    Args:
        project_id: 项目 UUID
        db: 异步数据库会话

    Returns:
        UTF-8 编码的报告字节，无数据时返回 None。
    """
    from app.models.core import Project
    from app.models.qc_inspection_models import QcInspection

    # 查询项目名称
    proj_stmt = select(Project).where(Project.id == project_id)
    proj_result = await db.execute(proj_stmt)
    project = proj_result.scalar_one_or_none()
    project_name = project.name if project else str(project_id)

    # 查询该项目所有抽查批次（含子项，selectin 自动加载）
    stmt = (
        select(QcInspection)
        .where(
            QcInspection.project_id == project_id,
            QcInspection.is_deleted == False,  # noqa: E712
        )
        .order_by(QcInspection.created_at.asc())
    )
    result = await db.execute(stmt)
    inspections = list(result.scalars().all())

    if not inspections:
        return None

    # 构建报告文本
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "质控抽查报告",
        f"项目: {project_name}",
        f"日期: {now_str}",
        "",
        "抽查批次:",
        "",
    ]

    for idx, inspection in enumerate(inspections, 1):
        started = (
            inspection.started_at.strftime("%Y-%m-%d")
            if inspection.started_at
            else "未开始"
        )
        completed = (
            inspection.completed_at.strftime("%Y-%m-%d")
            if inspection.completed_at
            else "进行中"
        )
        lines.append(f"  批次 {idx}: 策略={inspection.strategy} | 状态={inspection.status}")
        lines.append(f"    开始: {started} | 完成: {completed}")

        # 列出子项
        items = inspection.items or []
        if items:
            lines.append(f"    抽查子项 ({len(items)} 项):")
            for item in items:
                verdict = item.qc_verdict or "待评定"
                lines.append(
                    f"      - 底稿 {item.wp_id} | 状态={item.status} | 结论={verdict}"
                )
        else:
            lines.append("    抽查子项: 无")
        lines.append("")

    content = "\n".join(lines)
    return content.encode("utf-8")
