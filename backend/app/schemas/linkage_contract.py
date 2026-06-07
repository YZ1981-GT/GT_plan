"""LinkageContract 统一数据联动契约 schema。

P0 增强版：
- source_type / target_type 枚举统一（含 trial_balance 别名 tb）
- status: current / stale / conflict / manual_override
- confidence: system / manual / ai_suggested / ai_confirmed（高/中/低语义映射）
- 新增 conflict_id 字段（P1 冲突调解预留）
"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """数据来源类型枚举。"""
    trial_balance = "trial_balance"
    ledger = "ledger"
    audit_sheet = "audit_sheet"
    workpaper = "workpaper"
    adjustment = "adjustment"
    report = "report"
    note = "note"
    attachment = "attachment"
    ai = "ai"


class TargetType(str, Enum):
    """数据目标类型枚举（与 SourceType 值域一致）。"""
    trial_balance = "trial_balance"
    ledger = "ledger"
    audit_sheet = "audit_sheet"
    workpaper = "workpaper"
    adjustment = "adjustment"
    report = "report"
    note = "note"
    attachment = "attachment"
    ai = "ai"


class LinkageStatus(str, Enum):
    """联动状态枚举。"""
    current = "current"
    stale = "stale"
    conflict = "conflict"
    manual_override = "manual_override"


class LinkageConfidence(str, Enum):
    """置信度枚举。

    语义映射：
    - system = high（系统自动计算，最可信）
    - manual = high（人工确认）
    - ai_confirmed = medium（AI 生成且已确认）
    - ai_suggested = low（AI 建议未确认）
    """
    system = "system"
    manual = "manual"
    ai_suggested = "ai_suggested"
    ai_confirmed = "ai_confirmed"


# 置信度到高/中/低的映射
CONFIDENCE_LEVEL_MAP: dict[LinkageConfidence, str] = {
    LinkageConfidence.system: "high",
    LinkageConfidence.manual: "high",
    LinkageConfidence.ai_confirmed: "medium",
    LinkageConfidence.ai_suggested: "low",
}


class LinkageContract(BaseModel):
    """统一数据联动契约。

    描述审计平台中任意两个对象之间的数据引用关系，
    包含来源、目标、金额、状态、跳转路由和审计日志信息。
    """
    source_type: SourceType = Field(description="来源对象类型")
    source_id: str = Field(description="来源对象 ID")
    source_cell: Optional[str] = Field(default=None, description="来源单元格或字段")
    target_type: TargetType = Field(description="目标对象类型")
    target_id: str = Field(description="目标对象 ID")
    target_cell: Optional[str] = Field(default=None, description="目标单元格或字段")
    amount: Optional[str] = Field(default=None, description="Decimal 金额字符串")
    basis: Optional[str] = Field(default=None, description="取数口径说明")
    status: LinkageStatus = Field(default=LinkageStatus.current, description="联动状态")
    confidence: LinkageConfidence = Field(default=LinkageConfidence.system, description="置信度")
    route: Optional[str] = Field(default=None, description="前端可跳转路由")
    audit_log_id: Optional[str] = Field(default=None, description="留痕 ID")
    conflict_id: Optional[str] = Field(default=None, description="关联冲突记录 ID（P1 冲突调解）")

    @property
    def confidence_level(self) -> str:
        """返回置信度对应的 high/medium/low 级别。"""
        return CONFIDENCE_LEVEL_MAP.get(self.confidence, "low")


class ResolveRouteRequest(BaseModel):
    """POST /api/projects/{pid}/linkage/resolve-route 请求体。"""
    target_type: TargetType = Field(description="目标类型")
    target_id: str = Field(description="目标 ID（可为 wp_code 或 UUID）")
    target_cell: Optional[str] = Field(default=None, description="目标单元格（附注定位用）")


class ResolveRouteResponse(BaseModel):
    """路由解析响应。"""
    route: Optional[str] = Field(description="解析后的前端路由，None 表示无法解析")
    resolved_id: Optional[str] = Field(default=None, description="解析后的实际 ID（如 wp_code→wp_id）")
    error: Optional[str] = Field(default=None, description="解析失败原因")
