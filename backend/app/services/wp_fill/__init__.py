"""底稿 AI 填充服务 Mixin 子包

`WorkpaperFillService` 按职责拆分到 5 个 Mixin，主 class 多继承组合。
每个 Mixin 是普通 class，方法签名（含 `self`）逐字不变，方法仍挂在实例上，
`self.db`/`self.ai_service` 等实例属性在主 class 的 `__init__` 设置后于 mixin 内正常访问。
"""

from app.services.wp_fill._analytical_review import AnalyticalReviewMixin
from app.services.wp_fill._data_gen import DataGenMixin
from app.services.wp_fill._fill_task import FillTaskMixin
from app.services.wp_fill._note_draft import NoteDraftMixin
from app.services.wp_fill._review_prompt import ReviewPromptMixin

__all__ = [
    "FillTaskMixin",
    "AnalyticalReviewMixin",
    "DataGenMixin",
    "NoteDraftMixin",
    "ReviewPromptMixin",
]
