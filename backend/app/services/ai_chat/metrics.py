"""AI Chat Run Prometheus 指标（dsh-agent-panel-integration Task 12 / Req 12.8）

结构化指标覆盖：
- active_runs gauge：当前正在执行的 run 数
- queued_runs gauge：有界队列中等待的 run 数
- queue_wait_seconds histogram：run 从入队到开始执行的等待时长
- run_latency_seconds histogram：run 总执行时长（queued→terminal）
- tokens_total counter：模型消耗的 token 总量（只存计数，不存内容）
- cancel_latency_seconds histogram：从请求取消到终态确认的延迟
- denials_total counter：授权拒绝次数（按 denial_code 分标签）
- attachment_bytes_total counter：附件上传字节总量
- cleanup_failures_total counter：附件清理失败次数
- runs_total counter：run 状态转换计数（按 status/engine 分标签）

🔴 指标不记录 token 正文、完整正文、附件内容或未脱敏上下文（Req 12.7）。

prometheus_client 未安装时用 _Stub 占位，保证 import 不破坏。
render_ai_chat_metrics() 产出独立 /metrics/ai-chat 端点的 body + content-type。
"""

from __future__ import annotations

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PROMETHEUS_AVAILABLE = False

    class _Stub:
        """Nil-op 占位 — 签名兼容 prometheus_client。"""

        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

        def dec(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

    Counter = Histogram = Gauge = _Stub  # type: ignore[misc,assignment]
    CollectorRegistry = _Stub  # type: ignore[misc,assignment]
    CONTENT_TYPE_LATEST = "text/plain"

    def generate_latest(*args, **kwargs):  # type: ignore[misc]
        return b"# prometheus_client not installed\n"


# 独立 registry — 不与 ledger_import 或 fastapi-prometheus 冲突
AI_CHAT_REGISTRY = CollectorRegistry() if _PROMETHEUS_AVAILABLE else None


# ---------------------------------------------------------------------------
# 指标定义
# ---------------------------------------------------------------------------

if _PROMETHEUS_AVAILABLE:
    ACTIVE_RUNS = Gauge(
        "ai_chat_active_runs",
        "Number of AI chat runs currently being executed",
        registry=AI_CHAT_REGISTRY,
    )
    QUEUED_RUNS = Gauge(
        "ai_chat_queued_runs",
        "Number of AI chat runs waiting in the bounded queue",
        registry=AI_CHAT_REGISTRY,
    )
    QUEUE_WAIT_SECONDS = Histogram(
        "ai_chat_queue_wait_seconds",
        "Time a run spends in queue before execution starts",
        buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
        registry=AI_CHAT_REGISTRY,
    )
    RUN_LATENCY_SECONDS = Histogram(
        "ai_chat_run_latency_seconds",
        "Total run duration from queued to terminal state",
        ["engine", "status"],
        buckets=[1, 5, 10, 30, 60, 120, 180, 300],
        registry=AI_CHAT_REGISTRY,
    )
    TOKENS_TOTAL = Counter(
        "ai_chat_tokens_total",
        "Total tokens consumed by AI chat runs",
        ["engine", "token_type"],
        registry=AI_CHAT_REGISTRY,
    )
    CANCEL_LATENCY_SECONDS = Histogram(
        "ai_chat_cancel_latency_seconds",
        "Delay from cancel request to terminal confirmation",
        buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
        registry=AI_CHAT_REGISTRY,
    )
    DENIALS_TOTAL = Counter(
        "ai_chat_denials_total",
        "Number of access denials for AI chat resources",
        ["denial_code"],
        registry=AI_CHAT_REGISTRY,
    )
    ATTACHMENT_BYTES_TOTAL = Counter(
        "ai_chat_attachment_bytes_total",
        "Total bytes uploaded as AI chat attachments",
        registry=AI_CHAT_REGISTRY,
    )
    CLEANUP_FAILURES_TOTAL = Counter(
        "ai_chat_cleanup_failures_total",
        "Number of failed attachment cleanup attempts",
        registry=AI_CHAT_REGISTRY,
    )
    RUNS_TOTAL = Counter(
        "ai_chat_runs_total",
        "Total AI chat run state transitions",
        ["engine", "status"],
        registry=AI_CHAT_REGISTRY,
    )
else:
    ACTIVE_RUNS = Gauge()
    QUEUED_RUNS = Gauge()
    QUEUE_WAIT_SECONDS = Histogram()
    RUN_LATENCY_SECONDS = Histogram()
    TOKENS_TOTAL = Counter()
    CANCEL_LATENCY_SECONDS = Histogram()
    DENIALS_TOTAL = Counter()
    ATTACHMENT_BYTES_TOTAL = Counter()
    CLEANUP_FAILURES_TOTAL = Counter()
    RUNS_TOTAL = Counter()


# ---------------------------------------------------------------------------
# 便捷收集函数（供 coordinator / engine / routes 调用）
# ---------------------------------------------------------------------------


def set_active_runs(count: int) -> None:
    """更新当前 active run 数。"""
    if _PROMETHEUS_AVAILABLE:
        ACTIVE_RUNS.set(count)


def set_queued_runs(count: int) -> None:
    """更新当前 queued run 数。"""
    if _PROMETHEUS_AVAILABLE:
        QUEUED_RUNS.set(count)


def observe_queue_wait(seconds: float) -> None:
    """记录 run 的队列等待时长。"""
    if _PROMETHEUS_AVAILABLE:
        QUEUE_WAIT_SECONDS.observe(seconds)


def observe_run_latency(engine: str, status: str, seconds: float) -> None:
    """记录 run 总执行时长。"""
    if _PROMETHEUS_AVAILABLE:
        RUN_LATENCY_SECONDS.labels(engine=engine, status=status).observe(seconds)


def inc_tokens(engine: str, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
    """累加 token 消耗量（只计数，不传正文 — Req 12.7）。"""
    if _PROMETHEUS_AVAILABLE:
        if prompt_tokens:
            TOKENS_TOTAL.labels(engine=engine, token_type="prompt").inc(prompt_tokens)
        if completion_tokens:
            TOKENS_TOTAL.labels(engine=engine, token_type="completion").inc(completion_tokens)


def observe_cancel_latency(seconds: float) -> None:
    """记录取消延迟（从请求到终态确认）。"""
    if _PROMETHEUS_AVAILABLE:
        CANCEL_LATENCY_SECONDS.observe(seconds)


def inc_denial(denial_code: str) -> None:
    """记录一次授权拒绝。"""
    if _PROMETHEUS_AVAILABLE:
        DENIALS_TOTAL.labels(denial_code=denial_code).inc()


def inc_attachment_bytes(byte_count: int) -> None:
    """累加附件上传字节数。"""
    if _PROMETHEUS_AVAILABLE:
        ATTACHMENT_BYTES_TOTAL.inc(byte_count)


def inc_cleanup_failure() -> None:
    """记录一次附件清理失败。"""
    if _PROMETHEUS_AVAILABLE:
        CLEANUP_FAILURES_TOTAL.inc()


def inc_run_status(engine: str, status: str) -> None:
    """记录 run 状态转换。"""
    if _PROMETHEUS_AVAILABLE:
        RUNS_TOTAL.labels(engine=engine, status=status).inc()


# ---------------------------------------------------------------------------
# /metrics 渲染
# ---------------------------------------------------------------------------


def render_ai_chat_metrics() -> tuple[bytes, str]:
    """生成 AI chat metrics 响应体 + content-type。"""
    if not _PROMETHEUS_AVAILABLE:
        return b"# prometheus_client not installed\n", "text/plain"
    return generate_latest(AI_CHAT_REGISTRY), CONTENT_TYPE_LATEST


__all__ = [
    "AI_CHAT_REGISTRY",
    "ACTIVE_RUNS",
    "QUEUED_RUNS",
    "QUEUE_WAIT_SECONDS",
    "RUN_LATENCY_SECONDS",
    "TOKENS_TOTAL",
    "CANCEL_LATENCY_SECONDS",
    "DENIALS_TOTAL",
    "ATTACHMENT_BYTES_TOTAL",
    "CLEANUP_FAILURES_TOTAL",
    "RUNS_TOTAL",
    "set_active_runs",
    "set_queued_runs",
    "observe_queue_wait",
    "observe_run_latency",
    "inc_tokens",
    "observe_cancel_latency",
    "inc_denial",
    "inc_attachment_bytes",
    "inc_cleanup_failure",
    "inc_run_status",
    "render_ai_chat_metrics",
]
