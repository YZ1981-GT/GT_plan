"""RenderContext — 策略函数的统一上下文容器

每次 get_render_config 调用构造一个 RenderContext 实例，
传入对应策略函数。prep_info 为 lazy 字段，仅需要时填充。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.workpaper_models import WorkingPaper
    from app.services.wp_classification_service import ClassificationResult


@dataclass
class CrossRefItem:
    """跨底稿引用条目（轻量 dataclass 版本，避免 router 循环导入）"""

    wp_code: str
    cell: str | None = None


@dataclass
class RenderContext:
    """渲染策略函数的统一入参上下文

    Attributes:
        db: 异步数据库会话
        project_id: 项目 UUID
        wp_id: 底稿 UUID
        wp_code: 底稿编号（如 D1-1、B50）
        working_paper: WorkingPaper ORM 实例
        classification: 分类结果
        component_type: 渲染组件类型（如 "audit-sheet"、"b-index"）
        sheet_html_data: 已有持久化 HTML 数据（可能为 None）
        sheet_schema: YAML schema 解析结果
        template_file_path: 模板文件路径
        year: 会计年度
        business_category: 行业分类
        cross_ref_items: 跨底稿引用列表
        prep_info: 准备信息（lazy，构造时置 None，策略函数按需填充）
    """

    db: AsyncSession
    project_id: UUID
    wp_id: UUID
    wp_code: str
    working_paper: WorkingPaper
    classification: ClassificationResult
    component_type: str
    sheet_html_data: dict | None
    sheet_schema: dict | None
    template_file_path: str | None
    year: int | None
    business_category: str
    cross_ref_items: list[CrossRefItem] = field(default_factory=list)
    prep_info: dict[str, str] | None = field(default=None)
    # 同底稿全部 sheet 的分类结果列表（B-Index 导航需遍历所有 sheet）
    classifications: list[ClassificationResult] = field(default_factory=list)
    # 审计循环代号（如 "D"），B-Index 跨底稿目录需要
    audit_cycle: str | None = field(default=None)
    # 多文件聚合：该 sheet 内容来源模板文件路径列表（空=用 template_file_path）。
    # 由 wp_account_package_resolver 解析，供合并策略读多源内容。
    source_files: list[str] = field(default_factory=list)
