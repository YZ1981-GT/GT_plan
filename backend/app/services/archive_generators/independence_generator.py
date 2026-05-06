"""归档章节 04 — 独立性声明生成器

Refinement Round 7 P1 补完：为归档包生成独立性声明汇总文本。

查询项目的独立性声明记录，输出结构化文本报告（含各声明人的答案摘要）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def generate_independence_declarations(
    project_id: UUID, db: AsyncSession
) -> bytes | None:
    """生成独立性声明汇总文本内容。

    Args:
        project_id: 项目 UUID
        db: 异步数据库会话

    Returns:
        UTF-8 编码的声明汇总字节，无数据时返回 None。
    """
    from app.models.core import Project
    from app.services.independence_service import IndependenceService

    # 查询项目名称
    from sqlalchemy import select

    proj_stmt = select(Project).where(Project.id == project_id)
    proj_result = await db.execute(proj_stmt)
    project = proj_result.scalar_one_or_none()
    project_name = project.name if project else str(project_id)

    # 查询项目的独立性声明
    declarations = await IndependenceService.list_declarations(db, project_id)
    if not declarations:
        return None

    # 构建报告文本
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "独立性声明汇总",
        f"项目: {project_name}",
        f"日期: {now_str}",
        "",
        f"声明总数: {len(declarations)}",
        "",
    ]

    for idx, decl in enumerate(declarations, 1):
        lines.append(f"  声明 {idx}:")
        lines.append(f"    声明人: {decl.declarant_id}")
        lines.append(f"    年度: {decl.declaration_year}")
        lines.append(f"    状态: {decl.status}")

        signed_str = decl.signed_at.strftime("%Y-%m-%d") if decl.signed_at else "未签署"
        lines.append(f"    签署日期: {signed_str}")

        # 答案摘要
        answers = decl.answers or {}
        if answers:
            yes_count = sum(
                1 for v in answers.values()
                if (isinstance(v, dict) and v.get("answer") == "yes")
                or v == "yes"
            )
            no_count = sum(
                1 for v in answers.values()
                if (isinstance(v, dict) and v.get("answer") == "no")
                or v == "no"
            )
            lines.append(f"    答案: 共 {len(answers)} 题 (是={yes_count}, 否={no_count})")
        else:
            lines.append("    答案: 未填写")
        lines.append("")

    content = "\n".join(lines)
    return content.encode("utf-8")
