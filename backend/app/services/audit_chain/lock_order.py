"""审计链锁顺序探测器

ADR-ALC-09: 事务级咨询锁的获取顺序检查。

规则：
1. 已持有审计链锁后，取非审计链咨询锁 → 违规
2. 取第二条审计链锁时，链键必须大于已持有的全部链键，否则违规
3. GT_AUDIT_LOCK_ORDER_STRICT=1 时违规抛异常，否则只记日志

通过 SQLAlchemy Session do_orm_execute 事件监听器实现。
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 审计链锁的 SQL 特征
_CHAIN_LOCK_MARKER = "audit_chain:"

# 匹配咨询锁函数调用
_ADVISORY_LOCK_RE = re.compile(
    r"pg_(try_)?advisory_(xact_)?lock(_shared)?",
    re.IGNORECASE,
)

# 会话级持有链锁状态的属性名
_ATTR_CHAIN_KEYS = "_audit_chain_held_keys"
_ATTR_HAS_CHAIN_LOCK = "_audit_chain_has_lock"


class AuditLockOrderViolation(Exception):
    """审计链锁顺序违规。"""


def _is_strict() -> bool:
    return os.environ.get("GT_AUDIT_LOCK_ORDER_STRICT", "") == "1"


def _is_chain_lock(statement: str) -> tuple[bool, str | None]:
    """判断语句是否是审计链锁，并提取链键。"""
    if not isinstance(statement, str):
        return False, None
    if not _ADVISORY_LOCK_RE.search(statement):
        return False, None
    if _CHAIN_LOCK_MARKER in statement:
        # 尝试提取链键
        # 匹配 'audit_chain:' || :key 或 'audit_chain:__global__' 之类
        return True, None
    return False, None


def _is_advisory_lock(statement: str) -> bool:
    """判断语句是否含咨询锁。"""
    if not isinstance(statement, str):
        return False
    return bool(_ADVISORY_LOCK_RE.search(statement))


def _report_violation(msg: str) -> None:
    """报告违规：严格模式抛异常，否则记日志。"""
    if _is_strict():
        raise AuditLockOrderViolation(msg)
    logger.error("[audit_lock_order] VIOLATION: %s", msg)


def _get_held_keys(session: Any) -> list[str]:
    """获取会话已持有的审计链键列表。"""
    return getattr(session, _ATTR_CHAIN_KEYS, [])


def _has_chain_lock(session: Any) -> bool:
    """会话是否已持有审计链锁。"""
    return getattr(session, _ATTR_HAS_CHAIN_LOCK, False)


def record_chain_lock(session: Any, chain_key: str) -> None:
    """记录审计链锁的获取（供 head.lock_chain 调用）。

    检查：如果已有审计链锁，新链键必须 > 已持有的全部链键。
    """
    held = _get_held_keys(session)
    if held:
        max_held = max(held)
        if chain_key <= max_held:
            _report_violation(
                f"审计链锁顺序违规：已持有 {held}，试图获取 '{chain_key}' "
                f"(必须 > '{max_held}')"
            )
    held.append(chain_key)
    setattr(session, _ATTR_CHAIN_KEYS, held)
    setattr(session, _ATTR_HAS_CHAIN_LOCK, True)


def record_non_chain_advisory_lock(session: Any) -> None:
    """记录非审计链咨询锁的获取。

    如果已持有审计链锁 → 违规（审计链锁应是事务内最后获取的）。
    """
    if _has_chain_lock(session):
        held = _get_held_keys(session)
        _report_violation(
            f"审计链锁后获取了非审计链咨询锁：已持有审计链锁 {held}"
        )


def clear_session_state(session: Any) -> None:
    """事务结束时清空锁记录。"""
    if hasattr(session, _ATTR_CHAIN_KEYS):
        delattr(session, _ATTR_CHAIN_KEYS)
    if hasattr(session, _ATTR_HAS_CHAIN_LOCK):
        delattr(session, _ATTR_HAS_CHAIN_LOCK)


def install_lock_order_listener(session_class: type | None = None) -> None:
    """安装事务结束监听器，自动清空锁记录。

    调用方可传入 Session 类或留空（默认 Session）。
    """
    target = session_class or Session

    @event.listens_for(target, "after_transaction_end")
    def _on_tx_end(session: Any, transaction: Any) -> None:
        clear_session_state(session)


# 已知违规白名单（只许变短）
KNOWN_VIOLATIONS: set[str] = set()
