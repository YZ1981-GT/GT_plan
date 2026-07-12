"""一致性门控 — E1↔CFS 勾稽规则（3 条）

E1 spec Sprint 1 Task 1.13: 动态容差 + 3 条勾稽规则
"""
from __future__ import annotations

from app.services.consistency_gate._impl import ConsistencyGate as _Impl


class E1ChecksMixin:
    """E1↔CFS 勾稽"""

    check_e1_cfs_reconciliation = _Impl.check_e1_cfs_reconciliation
