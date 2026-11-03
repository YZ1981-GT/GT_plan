"""合伙人仪表盘 Pydantic Schema 定义

Validates: Requirements 9.2
"""

from pydantic import BaseModel, Field


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


class CheckStatusItem(BaseModel):
    """非通过检查项的五态与原因（需求 16.5）"""

    check_name: str
    status: str  # failed / not_executed / not_applicable / error
    reason: str = ""
    branch_id: str = ""
    severity: str = ""


class VRSummaryData(BaseModel):
    """验证规则汇总数据

    ``blocking_failed`` / ``by_cycle`` 保持「失败」含义；未执行 / 不适用 / 检查异常记在 ``status_counts`` 与
    ``not_passed_checks``（ADR-FHIC-14 第 5 点展示行）。``all_passed`` 只在每项都通过时为真（与 consistency-check 同口径，
    需求 16.5）。
    """

    total_rules: int
    blocking_failed: int
    all_passed: bool
    by_cycle: list[CycleVRStat]
    unavailable: bool = False
    reason: str | None = None
    status_counts: dict[str, int] = Field(default_factory=dict)
    not_passed_checks: list[CheckStatusItem] = Field(default_factory=list)


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
