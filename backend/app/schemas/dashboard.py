"""合伙人仪表盘 Pydantic Schema 定义

Validates: Requirements 9.2
"""

from pydantic import BaseModel


class CycleProgressItem(BaseModel):
    """循环进度项"""

    cycle: str  # "D" | "E" | ... | "N"
    cycle_name: str  # "销售收入" | "货币资金" | ...
    total_procedures: int
    completed_procedures: int
    trimmed_procedures: int
    progress_rate: float  # 0.0 ~ 100.0


class FailedRuleItem(BaseModel):
    """未通过的 VR 规则"""

    rule_id: str
    rule_name: str
    details: str | None = None


class CycleVRStat(BaseModel):
    """按循环分组的 VR 统计"""

    cycle: str
    blocking_failed: int
    failed_rules: list[FailedRuleItem]


class VRSummaryData(BaseModel):
    """验证规则汇总数据"""

    total_rules: int
    blocking_failed: int
    all_passed: bool
    by_cycle: list[CycleVRStat]


class ReviewItem(BaseModel):
    """复核意见项"""

    id: str
    review_layer: str  # "L5" | "L4" | "L3" | "L2" | "L1"
    summary: str  # 前 80 字符
    created_at: str
    wp_code: str
    sheet_name: str | None = None
    cell_ref: str | None = None


class OpenReviewsData(BaseModel):
    """未解决复核意见数据"""

    total: int
    by_layer: dict[str, int]  # {"L5": 2, "L4": 5, ...}
    items: list[ReviewItem]


class StageItem(BaseModel):
    """项目阶段项"""

    name: str
    status: str  # "completed" | "current" | "pending"
    entered_at: str | None = None
    completed_at: str | None = None
    summary: str | None = None


class TimelineData(BaseModel):
    """项目时间线数据"""

    current_stage: str  # "planning" | "execution" | "review" | "reporting"
    stages: list[StageItem]


class CycleTrimStat(BaseModel):
    """按循环分组的裁剪统计"""

    cycle: str
    total: int
    trimmed: int
    rate: float
    warning: bool  # rate > 50%


class TrimmingData(BaseModel):
    """裁剪概览数据"""

    available: bool  # procedure-applicability-trimming 是否已实施
    total_procedures: int
    trimmed_count: int
    trim_rate: float
    by_cycle: list[CycleTrimStat]


class DashboardSummaryResponse(BaseModel):
    """仪表盘聚合响应"""

    project_name: str
    audit_year: int
    last_updated: str  # ISO 8601

    cycle_progress: list[CycleProgressItem] | None = None
    vr_summary: VRSummaryData | None = None
    open_reviews: OpenReviewsData | None = None
    timeline: TimelineData | None = None
    trimming_overview: TrimmingData | None = None

    errors: dict[str, str] | None = None  # {"vr_summary": "ConsistencyGate timeout", ...}
