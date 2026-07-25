"""审计检查聚合服务包（audit-check-review-gate-hardening）。

导出统一模型、汇总、聚合器与 source 常量，供路由层与聚合逻辑复用。
"""

from app.services.audit_check.models import (
    ALL_SOURCES,
    BACKEND_COMPUTED_SOURCES,
    FRONTEND_REPORTABLE_SOURCES,
    PROJECT_WP_CODE,
    SEVERITY_BLOCKING,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    AuditCheckItem,
    AuditCheckSource,
    ProjectCheckSummary,
    from_fine_check_dict,
)
from app.services.audit_check.aggregator import AuditCheckAggregator

__all__ = [
    "AuditCheckItem",
    "AuditCheckSource",
    "ProjectCheckSummary",
    "AuditCheckAggregator",
    "from_fine_check_dict",
    "ALL_SOURCES",
    "BACKEND_COMPUTED_SOURCES",
    "FRONTEND_REPORTABLE_SOURCES",
    "PROJECT_WP_CODE",
    "SEVERITY_BLOCKING",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
]
