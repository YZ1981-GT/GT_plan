"""LLM 调用监控指标收集器

记录每次 LLM 调用的 timestamp / duration_ms / tokens_used / success / model，
提供聚合统计（total_calls / success_count / failure_count / avg_duration_ms / total_tokens）
和最近 100 条调用记录。

Requirements: 非功能需求-可观测性
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMCallRecord:
    """单次 LLM 调用记录"""

    timestamp: float
    duration_ms: float
    tokens_used: int
    success: bool
    model: str
    error: str | None = None
    task_code: str | None = None
    deployment: str | None = None
    fallback_used: bool = False
    error_code: str | None = None
    verifier_status: str | None = None
    ttft_ms: int | None = None
    tokens_per_second: float | None = None


class LLMMetricsCollector:
    """线程安全的 LLM 调用指标收集器（内存存储）"""

    MAX_RECENT_CALLS = 100

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._recent_calls: deque[LLMCallRecord] = deque(maxlen=self.MAX_RECENT_CALLS)
        self._total_calls: int = 0
        self._success_count: int = 0
        self._failure_count: int = 0
        self._total_duration_ms: float = 0.0
        self._total_tokens: int = 0
        self._human_actions: dict[str, int] = {
            "confirmed": 0, "revised": 0, "rejected": 0, "undone": 0,
        }

    def record_call(
        self,
        duration_ms: float,
        tokens_used: int,
        success: bool,
        model: str,
        error: str | None = None,
        *,
        task_code: str | None = None,
        deployment: str | None = None,
        fallback_used: bool = False,
        error_code: str | None = None,
        verifier_status: str | None = None,
        ttft_ms: int | None = None,
        tokens_per_second: float | None = None,
    ) -> None:
        """记录一次 LLM 调用"""
        record = LLMCallRecord(
            timestamp=time.time(),
            duration_ms=duration_ms,
            tokens_used=tokens_used,
            success=success,
            model=model,
            error=error,
            task_code=task_code,
            deployment=deployment,
            fallback_used=fallback_used,
            error_code=error_code,
            verifier_status=verifier_status,
            ttft_ms=ttft_ms,
            tokens_per_second=tokens_per_second,
        )
        with self._lock:
            self._recent_calls.append(record)
            self._total_calls += 1
            if success:
                self._success_count += 1
            else:
                self._failure_count += 1
            self._total_duration_ms += duration_ms
            self._total_tokens += tokens_used

    def get_metrics(self) -> dict[str, Any]:
        """获取聚合指标 + 最近调用记录"""
        with self._lock:
            avg_duration_ms = (
                self._total_duration_ms / self._total_calls
                if self._total_calls > 0
                else 0.0
            )
            recent_calls = [
                {
                    "timestamp": r.timestamp,
                    "duration_ms": round(r.duration_ms, 1),
                    "tokens_used": r.tokens_used,
                    "success": r.success,
                    "model": r.model,
                    "error": r.error,
                    "task_code": r.task_code,
                    "deployment": r.deployment,
                    "fallback_used": r.fallback_used,
                    "error_code": r.error_code,
                    "verifier_status": r.verifier_status,
                    "ttft_ms": r.ttft_ms,
                    "tokens_per_second": r.tokens_per_second,
                }
                for r in reversed(self._recent_calls)  # 最新的在前
            ]
            return {
                "total_calls": self._total_calls,
                "success_count": self._success_count,
                "failure_count": self._failure_count,
                "avg_duration_ms": round(avg_duration_ms, 1),
                "total_tokens": self._total_tokens,
                "human_actions": dict(self._human_actions),
                "recent_calls": recent_calls,
            }

    def record_human_action(self, action: str) -> None:
        """记录低基数人工处置，不记录项目、用户或正文。"""
        with self._lock:
            if action in self._human_actions:
                self._human_actions[action] += 1

    def reset(self) -> None:
        """重置所有指标（主要用于测试）"""
        with self._lock:
            self._recent_calls.clear()
            self._total_calls = 0
            self._success_count = 0
            self._failure_count = 0
            self._total_duration_ms = 0.0
            self._total_tokens = 0
            self._human_actions = {
                "confirmed": 0, "revised": 0, "rejected": 0, "undone": 0,
            }


# 全局单例
llm_metrics = LLMMetricsCollector()
