"""归档章节 05 — AI 贡献明细生成器

V3 收官增强 Req 6.6：归档报告 AI 贡献明细章节自动汇总。

查询项目的 ai_content_log 全部记录，按 instance_type 分组并按 generated_at
倒序输出，含项目名 / 日期 / 总数 / 状态分组（pending/confirmed/revised/
rejected）/ 按 instance_type 分组的明细。

每条记录显示：generated_at / model / target_cell / 内容前 80 字符 /
confirm_action / confirmed_by / confirmed_at。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_PREVIEW_LEN = 80
_STATUS_LABELS = {
    "pending": "待确认",
    "confirmed": "已确认",
    "revised": "已修订",
    "rejected": "已拒绝",
}


def _format_dt(dt: datetime | None) -> str:
    """格式化 datetime 为 'YYYY-MM-DD HH:MM:SS UTC'，None 返回 '-'。"""
    if dt is None:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _content_preview(text: str | None) -> str:
    """截取内容前 N 字符，None/空 返回 '<空>'。"""
    if not text:
        return "<空>"
    text = text.replace("\n", " ").replace("\r", " ").strip()
    if len(text) <= _PREVIEW_LEN:
        return text
    return text[:_PREVIEW_LEN] + "…"


def _instance_type_from_target_cell(target_cell: str | None) -> str:
    """从 target_cell 'instance_type:uuid[:field]' 解析 instance_type。"""
    if not target_cell:
        return "unknown"
    return target_cell.split(":", 1)[0] or "unknown"


async def generate_ai_contributions_report(
    project_id: UUID, db: AsyncSession
) -> bytes | None:
    """生成 AI 贡献明细报告文本内容。

    Args:
        project_id: 项目 UUID
        db: 异步数据库会话

    Returns:
        UTF-8 编码的报告字节，无 ai_content_log 记录时返回 None。
    """
    from app.models.core import Project
    from app.models.v3_refinement_models import AiContentLog

    # 查询项目名称
    proj_stmt = select(Project).where(Project.id == project_id)
    proj_result = await db.execute(proj_stmt)
    project = proj_result.scalar_one_or_none()
    project_name = project.name if project else str(project_id)

    # 查询全部 ai_content_log，按 generated_at 倒序
    stmt = (
        select(AiContentLog)
        .where(AiContentLog.project_id == project_id)
        .order_by(AiContentLog.generated_at.desc())
    )
    result = await db.execute(stmt)
    logs = list(result.scalars().all())

    if not logs:
        return None

    # 状态计数
    status_counts: dict[str, int] = {k: 0 for k in _STATUS_LABELS}
    for log in logs:
        action = log.confirm_action or "pending"
        if action in status_counts:
            status_counts[action] += 1
        else:
            status_counts.setdefault(action, 0)
            status_counts[action] += 1

    # 按 instance_type 分组（保留 generated_at 倒序）
    grouped: dict[str, list[AiContentLog]] = {}
    for log in logs:
        itype = _instance_type_from_target_cell(log.target_cell)
        grouped.setdefault(itype, []).append(log)

    # 构建报告文本
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "AI 贡献明细",
        f"项目: {project_name}",
        f"日期: {now_str}",
        "",
        f"AI 内容总数: {len(logs)}",
        "",
        "按状态分组:",
    ]
    for action, label in _STATUS_LABELS.items():
        lines.append(f"  {label} ({action}): {status_counts.get(action, 0)}")
    lines.append("")

    # 按 instance_type 分组明细（按 type 名称排序，保证输出稳定）
    lines.append("按业务类型分组明细:")
    lines.append("")
    for itype in sorted(grouped.keys()):
        group_logs = grouped[itype]
        lines.append(f"[{itype}] 共 {len(group_logs)} 条")

        for idx, log in enumerate(group_logs, 1):
            action = log.confirm_action or "pending"
            action_label = _STATUS_LABELS.get(action, action)

            # 优先展示 revised_content（如果存在），否则 generated_content
            shown_content = (
                log.revised_content if action == "revised" and log.revised_content
                else log.generated_content
            )

            lines.append(f"  {idx}. 时间: {_format_dt(log.generated_at)}")
            lines.append(f"     模型: {log.model}")
            lines.append(f"     目标: {log.target_cell or '-'}")
            lines.append(f"     内容: {_content_preview(shown_content)}")
            lines.append(f"     状态: {action_label} ({action})")
            lines.append(
                f"     确认人: {log.confirmed_by if log.confirmed_by else '-'}"
            )
            lines.append(f"     确认时间: {_format_dt(log.confirmed_at)}")
            lines.append("")

    content = "\n".join(lines)
    return content.encode("utf-8")
