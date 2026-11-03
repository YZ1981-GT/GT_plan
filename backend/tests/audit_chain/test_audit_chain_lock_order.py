"""锁顺序探测器单元测试

ADR-ALC-09: 审计链锁是事务内最后获取的咨询锁。
"""
from __future__ import annotations

import os

import pytest

from app.services.audit_chain.lock_order import (
    AuditLockOrderViolation,
    clear_session_state,
    record_chain_lock,
    record_non_chain_advisory_lock,
)


class _FakeSession:
    """模拟 SQLAlchemy Session 的属性存储。"""
    pass


@pytest.fixture(autouse=True)
def _strict_mode(monkeypatch):
    """测试中始终启用严格模式。"""
    monkeypatch.setenv("GT_AUDIT_LOCK_ORDER_STRICT", "1")


class TestLockOrderDetector:
    """锁顺序探测器。"""

    def test_single_chain_lock_ok(self):
        """单条审计链锁 → 无违规。"""
        s = _FakeSession()
        record_chain_lock(s, "project:aaa")
        clear_session_state(s)

    def test_chain_then_non_chain_violation(self):
        """持有审计链锁后取非审计链咨询锁 → 违规。"""
        s = _FakeSession()
        record_chain_lock(s, "__global__")
        with pytest.raises(AuditLockOrderViolation, match="非审计链咨询锁"):
            record_non_chain_advisory_lock(s)
        clear_session_state(s)

    def test_non_chain_then_chain_ok(self):
        """先取非审计链锁，再取审计链锁 → 无违规。"""
        s = _FakeSession()
        record_non_chain_advisory_lock(s)  # 此时没有审计链锁 → ok
        record_chain_lock(s, "__global__")
        clear_session_state(s)

    def test_ascending_chain_keys_ok(self):
        """多条审计链锁按升序获取 → 无违规。"""
        s = _FakeSession()
        record_chain_lock(s, "__global__")
        record_chain_lock(s, "project:aaa")
        record_chain_lock(s, "project:bbb")
        clear_session_state(s)

    def test_descending_chain_keys_violation(self):
        """多条审计链锁按降序获取 → 违规。"""
        s = _FakeSession()
        record_chain_lock(s, "project:bbb")
        with pytest.raises(AuditLockOrderViolation, match="顺序违规"):
            record_chain_lock(s, "project:aaa")
        clear_session_state(s)

    def test_duplicate_chain_key_violation(self):
        """同一链键获取两次 → 违规（不大于已持有的最大键）。"""
        s = _FakeSession()
        record_chain_lock(s, "__global__")
        with pytest.raises(AuditLockOrderViolation, match="顺序违规"):
            record_chain_lock(s, "__global__")
        clear_session_state(s)

    def test_clear_resets_state(self):
        """事务结束后清空状态 → 再次获取无违规。"""
        s = _FakeSession()
        record_chain_lock(s, "project:aaa")
        clear_session_state(s)
        # 清空后重新获取应该没问题
        record_chain_lock(s, "__global__")
        clear_session_state(s)

    def test_non_strict_mode_no_raise(self, monkeypatch):
        """非严格模式 → 违规只记日志不抛异常。"""
        monkeypatch.setenv("GT_AUDIT_LOCK_ORDER_STRICT", "0")
        s = _FakeSession()
        record_chain_lock(s, "project:bbb")
        # 不应抛出
        record_chain_lock(s, "project:aaa")
        clear_session_state(s)
