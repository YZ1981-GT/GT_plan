"""安全监控服务 — IP检测 + 会话管理 + 安全事件日志

Phase 8 Task 10.3: 安全监控
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


class SecurityMonitor:
    """安全监控服务。"""

    # In-memory stores (production: use Redis)
    _ip_attempts: dict[str, list[float]] = defaultdict(list)
    _sessions: dict[str, dict] = {}
    _security_events: list[dict] = []

    # Thresholds
    SUSPICIOUS_IP_THRESHOLD = 10  # requests per minute
    SESSION_MAX_AGE = 7200  # 2 hours

    def record_ip_access(self, ip: str, endpoint: str = ""):
        """记录 IP 访问。"""
        now = time.time()
        self._ip_attempts[ip].append(now)
        # Clean old entries (keep last 5 minutes)
        cutoff = now - 300
        self._ip_attempts[ip] = [t for t in self._ip_attempts[ip] if t > cutoff]

    def is_suspicious_ip(self, ip: str) -> bool:
        """检测异常 IP（短时间内大量请求）。"""
        now = time.time()
        cutoff = now - 60  # last minute
        recent = [t for t in self._ip_attempts.get(ip, []) if t > cutoff]
        return len(recent) > self.SUSPICIOUS_IP_THRESHOLD

    def get_ip_stats(self, ip: str) -> dict:
        """获取 IP 访问统计。"""
        attempts = self._ip_attempts.get(ip, [])
        now = time.time()
        return {
            "ip": ip,
            "total_attempts": len(attempts),
            "last_minute": len([t for t in attempts if t > now - 60]),
            "last_5_minutes": len([t for t in attempts if t > now - 300]),
            "is_suspicious": self.is_suspicious_ip(ip),
        }

    # ---- Session management ----

    def create_session(self, user_id: str, ip: str, user_agent: str = "") -> str:
        """创建会话记录。"""
        session_id = f"sess_{user_id}_{int(time.time())}"
        self._sessions[session_id] = {
            "user_id": user_id,
            "ip": ip,
            "user_agent": user_agent,
            "created_at": time.time(),
            "last_active": time.time(),
            "is_active": True,
        }
        self._log_event("session_created", {"user_id": user_id, "ip": ip})
        return session_id

    def get_active_sessions(self, user_id: str | None = None) -> list[dict]:
        """获取活跃会话列表。"""
        now = time.time()
        sessions = []
        for sid, info in self._sessions.items():
            if not info["is_active"]:
                continue
            if now - info["last_active"] > self.SESSION_MAX_AGE:
                info["is_active"] = False
                continue
            if user_id and info["user_id"] != user_id:
                continue
            sessions.append({"session_id": sid, **info})
        return sessions

    def terminate_session(self, session_id: str) -> bool:
        """终止会话。"""
        if session_id in self._sessions:
            self._sessions[session_id]["is_active"] = False
            self._log_event("session_terminated", {"session_id": session_id})
            return True
        return False

    # ---- Security event log ----

    def _log_event(self, event_type: str, details: dict):
        self._security_events.append({
            "event_type": event_type,
            "details": details,
            "timestamp": time.time(),
        })
        if len(self._security_events) > 1000:
            self._security_events = self._security_events[-1000:]

    def get_security_events(self, limit: int = 50, event_type: str | None = None) -> list[dict]:
        """获取安全事件日志。"""
        events = self._security_events
        if event_type:
            events = [e for e in events if e["event_type"] == event_type]
        return events[-limit:]

    def get_login_attempts(self, username: str | None = None, limit: int = 50) -> list[dict]:
        """获取登录尝试记录。"""
        events = [e for e in self._security_events if e["event_type"] in ("login_success", "login_failed")]
        if username:
            events = [e for e in events if e["details"].get("username") == username]
        return events[-limit:]

    def record_login_attempt(self, username: str, ip: str, success: bool):
        """记录登录尝试。"""
        self._log_event(
            "login_success" if success else "login_failed",
            {"username": username, "ip": ip},
        )
        self.record_ip_access(ip, "login")


# Global instance
security_monitor = SecurityMonitor()
