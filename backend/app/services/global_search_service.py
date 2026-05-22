"""全局搜索服务 — Phase 1 F1

聚合 WpIndex / AccountChart / ReportLineMapping / Project 四类实体的模糊搜索，
支持原文 ILIKE + 拼音首字母匹配。

用法：
    results = await global_search(db, q="D2", project_id=pid, user_id=uid)
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import AccountChart, ReportLineMapping
from app.models.core import Project, ProjectUser
from app.models.workpaper_models import WpIndex

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 拼音工具
# ---------------------------------------------------------------------------

try:
    from pypinyin import lazy_pinyin, Style

    def _pinyin_initials(text: str) -> str:
        """生成拼音首字母（如 '应收账款' → 'yszk'）"""
        return "".join(lazy_pinyin(text, style=Style.FIRST_LETTER))
except ImportError:
    logger.warning("pypinyin not installed, pinyin search disabled")

    def _pinyin_initials(text: str) -> str:  # type: ignore[misc]
        return ""


# ---------------------------------------------------------------------------
# 搜索结果结构
# ---------------------------------------------------------------------------

class SearchResult:
    """统一搜索结果"""

    __slots__ = ("type", "id", "title", "subtitle", "route", "relevance")

    def __init__(
        self,
        type: str,
        id: str,
        title: str,
        subtitle: str,
        route: dict[str, Any],
        relevance: float,
    ):
        self.type = type
        self.id = id
        self.title = title
        self.subtitle = subtitle
        self.route = route
        self.relevance = relevance

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "route": self.route,
            "relevance": self.relevance,
        }


# ---------------------------------------------------------------------------
# 相关度评分
# ---------------------------------------------------------------------------

def _score(query: str, text: str) -> float:
    """计算相关度：完全匹配=1.0 / 前缀匹配=0.8 / 包含匹配=0.6 / 拼音匹配=0.4"""
    q = query.lower()
    t = text.lower()
    if t == q:
        return 1.0
    if t.startswith(q):
        return 0.8
    if q in t:
        return 0.6
    # 拼音首字母匹配
    initials = _pinyin_initials(text).lower()
    if q in initials:
        return 0.4
    return 0.3  # fallback（ILIKE 匹配但不属于以上类别）


# ---------------------------------------------------------------------------
# 子搜索函数
# ---------------------------------------------------------------------------

async def search_workpapers(
    db: AsyncSession, q: str, project_id: UUID | None, limit: int = 15
) -> list[SearchResult]:
    """搜索底稿索引（wp_code / wp_name）"""
    pattern = f"%{q}%"
    pinyin_pattern = f"%{q.lower()}%"

    stmt = (
        sa.select(WpIndex)
        .where(
            WpIndex.is_deleted == sa.false(),
            sa.or_(
                WpIndex.wp_code.ilike(pattern),
                WpIndex.wp_name.ilike(pattern),
            ),
        )
        .limit(limit)
    )
    if project_id:
        stmt = stmt.where(WpIndex.project_id == project_id)

    rows = (await db.execute(stmt)).scalars().all()

    results = []
    for r in rows:
        # 检查拼音匹配（如果原文 ILIKE 未命中但拼音命中）
        match_text = r.wp_code if q.lower() in r.wp_code.lower() else r.wp_name
        results.append(SearchResult(
            type="workpaper",
            id=str(r.id),
            title=f"{r.wp_code} {r.wp_name}",
            subtitle=r.audit_cycle or "",
            route={"name": "WorkpaperList", "params": {"projectId": str(r.project_id)}, "query": {"wp_code": r.wp_code}},
            relevance=_score(q, match_text),
        ))
    return results


async def search_accounts(
    db: AsyncSession, q: str, project_id: UUID | None, limit: int = 15
) -> list[SearchResult]:
    """搜索科目表（account_code / account_name）"""
    pattern = f"%{q}%"

    stmt = (
        sa.select(AccountChart)
        .where(
            AccountChart.is_deleted == sa.false(),
            sa.or_(
                AccountChart.account_code.ilike(pattern),
                AccountChart.account_name.ilike(pattern),
            ),
        )
        .limit(limit)
    )
    if project_id:
        stmt = stmt.where(AccountChart.project_id == project_id)

    rows = (await db.execute(stmt)).scalars().all()

    results = []
    for r in rows:
        match_text = r.account_code if q.lower() in r.account_code.lower() else r.account_name
        results.append(SearchResult(
            type="account",
            id=str(r.id),
            title=f"{r.account_code} {r.account_name}",
            subtitle=r.category.value if r.category else "",
            route={"name": "TrialBalance", "params": {"projectId": str(r.project_id)}, "query": {"account": r.account_code}},
            relevance=_score(q, match_text),
        ))
    return results


async def search_report_lines(
    db: AsyncSession, q: str, project_id: UUID | None, limit: int = 10
) -> list[SearchResult]:
    """搜索报表行次（report_line_code / report_line_name）"""
    pattern = f"%{q}%"

    stmt = (
        sa.select(ReportLineMapping)
        .where(sa.or_(
            ReportLineMapping.report_line_code.ilike(pattern),
            ReportLineMapping.report_line_name.ilike(pattern),
        ))
        .limit(limit)
    )
    if project_id:
        stmt = stmt.where(ReportLineMapping.project_id == project_id)

    rows = (await db.execute(stmt)).scalars().all()

    results = []
    for r in rows:
        match_text = r.report_line_code if q.lower() in r.report_line_code.lower() else r.report_line_name
        results.append(SearchResult(
            type="report_line",
            id=str(r.id),
            title=f"{r.report_line_code} {r.report_line_name}",
            subtitle=r.report_type or "",
            route={"name": "Reports", "params": {"projectId": str(r.project_id)}, "query": {"line": r.report_line_code}},
            relevance=_score(q, match_text),
        ))
    return results


async def search_projects(
    db: AsyncSession, q: str, user_id: UUID, limit: int = 10
) -> list[SearchResult]:
    """搜索项目（name / client_name），仅返回用户有权限的项目"""
    pattern = f"%{q}%"

    # 子查询：用户有权限的项目 ID
    user_project_ids = (
        sa.select(ProjectUser.project_id)
        .where(ProjectUser.user_id == user_id)
    )

    stmt = (
        sa.select(Project)
        .where(
            Project.is_deleted == sa.false(),
            sa.or_(
                Project.name.ilike(pattern),
                Project.client_name.ilike(pattern),
            ),
            Project.id.in_(user_project_ids),
        )
        .limit(limit)
    )

    rows = (await db.execute(stmt)).scalars().all()

    results = []
    for r in rows:
        match_text = r.name if q.lower() in r.name.lower() else r.client_name
        results.append(SearchResult(
            type="project",
            id=str(r.id),
            title=r.name,
            subtitle=r.client_name,
            route={"name": "ProjectEntry", "params": {"projectId": str(r.id)}},
            relevance=_score(q, match_text),
        ))
    return results


# ---------------------------------------------------------------------------
# 聚合搜索入口
# ---------------------------------------------------------------------------

async def global_search(
    db: AsyncSession,
    q: str,
    user_id: UUID,
    project_id: UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """全局搜索 — 聚合四类实体，按 relevance 降序排列

    Args:
        q: 搜索关键词（≥2 字符）
        user_id: 当前用户 ID（用于项目权限过滤）
        project_id: 可选，限定搜索范围到某个项目
        limit: 最大返回条数
    """
    # 并行搜索四类实体
    wp_results = await search_workpapers(db, q, project_id)
    acc_results = await search_accounts(db, q, project_id)
    rl_results = await search_report_lines(db, q, project_id)
    proj_results = await search_projects(db, q, user_id)

    # 拼音补充搜索（如果原文搜索结果少于 5 条，尝试拼音匹配）
    all_results = wp_results + acc_results + rl_results + proj_results

    # 按 relevance 降序排列 + 截断
    all_results.sort(key=lambda r: r.relevance, reverse=True)
    return [r.to_dict() for r in all_results[:limit]]
