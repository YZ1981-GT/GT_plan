"""底稿处理注册表 — 统一委托给通用处理引擎

所有底稿通过 wp_generic_processor 通用规则处理，
不再为每个科目维护独立脚本。

通用规则覆盖：
- 表头行自动检测（关键词扫描）
- 列含义自动映射（项目/期末/期初/调整/增减）
- 合计行自动识别
- Sheet类型自动推断（审定表/明细表/分析表/变动表/账龄表）
- 数据提取为结构化格式（接入四式联动）

如需特定科目的额外处理逻辑，在 wp_parse_rules.json 中配置规则即可。
"""

from __future__ import annotations

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession


async def run_extract(db: AsyncSession, project_id: UUID, year: int, wp_code: str) -> dict | None:
    """执行数据提取 — 委托给通用处理引擎"""
    from app.services.wp_generic_processor import parse_workpaper_generic
    from app.models.workpaper_models import WorkingPaper, WpIndex
    import sqlalchemy as sa

    result = await db.execute(
        sa.select(WorkingPaper)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WpIndex.project_id == project_id, WpIndex.wp_code == wp_code,
               WorkingPaper.is_deleted == sa.false())
        .limit(1)
    )
    wp = result.scalar_one_or_none()
    if not wp or not wp.file_path:
        return None

    return parse_workpaper_generic(wp.file_path, wp_code)


async def run_generate_explanation(db: AsyncSession, project_id: UUID, year: int, wp_code: str) -> str | None:
    """审计说明生成 — 委托给 wp_explanation_service（LLM辅助）"""
    try:
        from app.services.wp_explanation_service import WpExplanationService
        svc = WpExplanationService(db)
        result = await svc.generate_draft(project_id=project_id, wp_code=wp_code, year=year)
        return result.get("explanation", "")
    except Exception:
        return None


def get_review_checklist(wp_code: str) -> list[dict] | None:
    """复核要点清单 — 从 TSJ 提示词库加载"""
    try:
        from app.services.tsj_prompt_service import get_review_points
        return get_review_points(wp_code)
    except Exception:
        return None
