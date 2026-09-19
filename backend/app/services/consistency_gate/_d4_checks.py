"""一致性门控 — D4 营业收入勾稽规则（4 条）

D spec F7: 4 条 D4 营业收入勾稽规则
"""
from __future__ import annotations

from app.services.consistency_gate._impl import ConsistencyGate as _Impl


class D4ChecksMixin:
    """D4 营业收入勾稽"""

    check_d4_revenue_reconciliation = _Impl.check_d4_revenue_reconciliation
