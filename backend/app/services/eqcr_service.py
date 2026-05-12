"""EQCR 服务 — 向后兼容入口

实际实现拆分到 eqcr_workbench_service.py 和 eqcr_domain_service.py。
"""
from app.services.eqcr_workbench_service import EqcrWorkbenchService  # noqa: F401
from app.services.eqcr_domain_service import EqcrDomainService  # noqa: F401

# 向后兼容：保留 EqcrService 名称
class EqcrService(EqcrWorkbenchService, EqcrDomainService):
    """组合服务（向后兼容）。新代码建议直接用 EqcrWorkbenchService 或 EqcrDomainService。"""
    pass

# Re-export constants
from app.services.eqcr_workbench_service import (  # noqa: F401, E402
    EQCR_CORE_DOMAINS,
    PROGRESS_NOT_STARTED,
    PROGRESS_IN_PROGRESS,
    PROGRESS_APPROVED,
    PROGRESS_DISAGREE,
)
