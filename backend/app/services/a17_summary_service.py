"""a17_summary_service — A17-1 重大事项概要 章节定义 + 拉取服务

提供:
- get_chapter_definitions() → 返回 16 章定义（缓存）
- pull_chapter_data(db, project_id, chapter_id) → 从上游模块拉取章节数据

P1 MVP:
  - ch01 拉取项目信息（client_name, audit_period, partner）
  - ch07/ch16 手工章节返回提示
  - 其余章节返回"数据源未就绪"
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, User
from app.services.issue_hints_service import get_issue_hints

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_CHAPTER_DEFS_PATH = _DATA_DIR / "a17_chapter_definitions.json"


@lru_cache(maxsize=1)
def _load_chapter_definitions() -> list[dict]:
    """加载并缓存 16 章定义 JSON"""
    try:
        return json.loads(_CHAPTER_DEFS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Failed to load a17_chapter_definitions.json: %s", e)
        return []


def get_chapter_definitions() -> list[dict]:
    """返回 A17-1 全部章节定义（16 章）"""
    return _load_chapter_definitions()


async def pull_chapter_data(
    db: AsyncSession, project_id: UUID, chapter_id: str
) -> dict:
    """从上游数据源拉取指定章节的数据。

    返回:
        {content: str|None, source_label: str|None, message: str|None}
    """
    chapters = get_chapter_definitions()
    chapter = next((ch for ch in chapters if ch["id"] == chapter_id), None)

    if chapter is None:
        return {"content": None, "source_label": None, "message": "未知章节"}

    ds = chapter.get("data_source", {})
    ds_type = ds.get("type", "auto")
    ready = ds.get("ready")

    # ── 手工章节（ch07, ch16）──
    if ds_type == "manual":
        return {
            "content": None,
            "source_label": None,
            "message": "此章节为手工填写",
        }

    # ── ch01: 项目信息拉取 ──
    if chapter_id == "A17-1-ch01":
        return await _pull_ch01_project_info(db, project_id)

    # ── ch15: 其他特殊考虑事项（issue_tickets + A13 + A14）──
    if chapter_id == "A17-1-ch15":
        return await _pull_ch15_special_matters(db, project_id)

    # ── 其余章节: 数据源未就绪 ──
    if ready is True:
        # 标记 ready 但非 ch01 → 未来扩展点
        return {
            "content": None,
            "source_label": None,
            "message": "数据源接口待实现",
        }

    # partial 或 false
    return {
        "content": None,
        "source_label": None,
        "message": "数据源未就绪",
    }


async def _pull_ch01_project_info(db: AsyncSession, project_id: UUID) -> dict:
    """ch01: 从项目信息拉取审计业务约定范围数据"""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if project is None:
        return {
            "content": None,
            "source_label": None,
            "message": "项目不存在",
        }

    # 获取签字合伙人名称
    partner_name: str | None = None
    if project.partner_id:
        partner_stmt = select(User.username).where(User.id == project.partner_id)
        partner_result = await db.execute(partner_stmt)
        partner_name = partner_result.scalar_one_or_none()

    # 格式化审计期间
    period_start = (
        project.audit_period_start.strftime("%Y年%m月%d日")
        if project.audit_period_start
        else "未设置"
    )
    period_end = (
        project.audit_period_end.strftime("%Y年%m月%d日")
        if project.audit_period_end
        else "未设置"
    )

    lines = [
        f"被审计单位：{project.client_name}",
        f"审计期间：{period_start} 至 {period_end}",
    ]
    if partner_name:
        lines.append(f"签字会计师：{partner_name}")
    if project.business_category:
        lines.append(f"业务分类：{project.business_category} 类")

    content = "\n".join(lines)

    return {
        "content": content,
        "source_label": "project_info",
    }


async def _pull_ch15_special_matters(db: AsyncSession, project_id: UUID) -> dict:
    """ch15: 其他特殊考虑事项 — 舞弊线索(issue_hints) + A13错报 + A14缺陷计数"""
    lines: list[str] = []

    # ── 1. issue_hints 舞弊线索 ──
    try:
        hints = await get_issue_hints(db, project_id)
        fraud = hints.get("fraud", {})
        fraud_count = fraud.get("count", 0)
        if fraud_count > 0:
            titles = [item["title"] for item in fraud.get("items", [])]
            lines.append(f"舞弊相关问题单：{fraud_count} 条")
            for t in titles:
                lines.append(f"  - {t}")
        else:
            lines.append("舞弊相关问题单：0 条")
        lines.append("（仅标题关键词启发式，召回不完备，仅供提示）")
    except Exception as e:
        logger.warning("ch15 issue_hints 查询失败: %s", e)
        lines.append("舞弊相关问题单：查询失败")

    # ── 2. A13 未更正错报计数 ──
    try:
        from app.models.audit_platform_models import UnadjustedMisstatement
        from sqlalchemy import func as sa_func

        mis_stmt = (
            select(sa_func.count())
            .select_from(UnadjustedMisstatement)
            .where(
                UnadjustedMisstatement.project_id == project_id,
                UnadjustedMisstatement.is_deleted == False,  # noqa: E712
            )
        )
        mis_result = await db.execute(mis_stmt)
        mis_count = mis_result.scalar() or 0
        lines.append(f"A13 未更正错报：{mis_count} 项")
    except Exception as e:
        logger.warning("ch15 A13 错报计数失败: %s", e)
        lines.append("A13 未更正错报：数据源未就绪")

    # ── 3. A14 内控缺陷计数 ──
    try:
        from app.models.phase15_models import IssueTicket
        from sqlalchemy import func as sa_func2

        def_count_stmt = (
            select(sa_func2.count())
            .select_from(IssueTicket)
            .where(
                IssueTicket.project_id == project_id,
                IssueTicket.category == "internal_control",
            )
        )
        def_result = await db.execute(def_count_stmt)
        def_count = def_result.scalar() or 0
        lines.append(f"A14 内控缺陷：{def_count} 项")
    except Exception as e:
        logger.warning("ch15 A14 缺陷计数失败: %s", e)
        lines.append("A14 内控缺陷：数据源未就绪")

    content = "\n".join(lines)
    return {
        "content": content,
        "source_label": "issue_hints+A13+A14",
    }
