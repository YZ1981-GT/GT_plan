"""一致性门控服务 — 五态模型

ADR-FHIC-14。CheckItem / ConsistencyResult 的唯一定义在 _models.py。
gate_decision 在 _decision.py。
"""

from app.services.consistency_gate._models import (  # noqa: F401
    CheckItem,
    ConsistencyResult,
    FIVE_STATES,
    check_status,
    five_state_counts,
    not_passed_checks,
    _ok,
    _fail,
    _not_executed,
    _not_applicable,
    _error,
)
from app.services.consistency_gate._decision import (  # noqa: F401
    GateDecision,
    gate_decision,
)
from app.services.consistency_gate._impl import ConsistencyGate  # noqa: F401

__all__ = [
    "CheckItem",
    "ConsistencyResult",
    "ConsistencyGate",
    "GateDecision",
    "gate_decision",
]
