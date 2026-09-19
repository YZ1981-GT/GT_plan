"""ConsistencyGate 主类 — 组合各域 mixin

Property 10: overall="pass" iff 所有 blocking 检查 passed=true
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.consistency_gate._base_checks import BaseChecksMixin
from app.services.consistency_gate._cycle_checks import CycleChecksMixin
from app.services.consistency_gate._d4_checks import D4ChecksMixin
from app.services.consistency_gate._e1_checks import E1ChecksMixin
from app.services.consistency_gate._helpers import HelpersMixin
from app.services.consistency_gate._impl import ConsistencyGate as _ImplGate


class ConsistencyGate(
    BaseChecksMixin,
    E1ChecksMixin,
    D4ChecksMixin,
    CycleChecksMixin,
    HelpersMixin,
):
    """一致性门控 — 全部检查组合

    Property 10: overall="pass" iff 所有 blocking 检查 passed=true
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # run_all_checks 从 _impl 复用
    run_all_checks = _ImplGate.run_all_checks
