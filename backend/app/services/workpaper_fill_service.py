"""底稿 AI 填充服务

基于 AI 模型自动填充审计底稿内容，包括：
- 文本描述填充（审计说明、结论）
- 计算验证（数值计算、钩稽关系）
- 异常标注（标记需要关注的异常项）
- 分析性复核生成
- 底稿数据生成
- 附注初稿生成

`WorkpaperFillService` 的全部方法按职责拆分到 `app.services.wp_fill` 子包的 5 个
Mixin，本文件仅保留 `__init__` 与多继承组合。方法仍挂在实例上，对外 API 零变更。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wp_fill import (
    FillTaskMixin,
    AnalyticalReviewMixin,
    DataGenMixin,
    NoteDraftMixin,
    ReviewPromptMixin,
)


class WorkpaperFillService(
    FillTaskMixin,
    AnalyticalReviewMixin,
    DataGenMixin,
    NoteDraftMixin,
    ReviewPromptMixin,
):
    """底稿 AI 填充服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
