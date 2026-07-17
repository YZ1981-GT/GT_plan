"""Evidence Governance 可观测性 — 低基数指标、trace 关联与告警（Task 7.4, Wave 6）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R12, R13, R15, R16
Design: §9.3 可观测性, §7.1 command-root 唯一与 transition 多条
Properties: P25 (审计事件覆盖, 部分), P30 (质量指标可复算, 部分)

设计要点（design §9.3）：

- **低基数指标**覆盖 upload / boundary / ref / OCR queue+failure / AI coverage /
  citation / stale age+closure / review reopen / formal gate / archive hash /
  hold / outbox lag / PG pool wait / backpressure。
- 指标标签受**冻结允许集**约束，未知标签统一收敛为 ``other``，保证 series 数
  = |domain| × |outcome| 有界（不因高基数 ID/路径爆炸）。
- API→outbox→worker→外部引擎贯穿 **trace**；告警关联 **command-root / audit
  transition**（``command_root_id`` / ``transition_id`` / ``trace_id``）。
- **AI coverage gap、manifest hash failure、跨 scope denied 异常峰值立即告警**。
- 指标与告警元数据统一经 ``redact_audit_metadata`` 脱敏：**不记录凭据、绝对路径、
  附件/OCR 原文或完整 prompt/answer**（design §7.1）。

进程内单例（GIL + lock 双保险；asyncio 单线程无竞争），零外部依赖，可离线复算
（相同事件序列 → 相同聚合，P30 语义）。DB 持久化由 command-root / outbox 承担，
本收集器只做低基数聚合与告警，不落库大正文（design §9.2）。
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from app.services.evidence_governance.command_audit import redact_audit_metadata

logger = logging.getLogger(__name__)

# ─── Alert Severity ──────────────────────────────────────────────────────────

ALERT_INFO = "info"
ALERT_WARNING = "warning"
ALERT_ERROR = "error"

ALERT_SEVERITIES: frozenset[str] = frozenset({ALERT_INFO, ALERT_WARNING, ALERT_ERROR})

# ─── 低基数指标域（design §9.3 覆盖清单） ─────────────────────────────────────
#: 每个 domain 是一个语义计量域；标签基数由 domain × outcome 有界。
METRIC_DOMAINS: frozenset[str] = frozenset(
    {
        "upload",          # 上传接收（accepted/rejected/quarantined/failed）
        "boundary",        # 存储边界读取拒绝（denied/allowed）
        "ref",             # EvidenceRef 创建/停用（success/rejected/denied）
        "ocr_queue",       # OCR 排队（enqueued/dequeued/backpressure）
        "ocr_failure",     # OCR 失败（failed/retried/dead_letter）
        "ai_coverage",     # AI 入口覆盖（covered/gap）
        "citation",        # 引用定位（hit/miss/mismatch/denied）
        "stale_age",       # stale 账龄（gauge）
        "stale_closure",   # stale 闭包传播（success/degraded）
        "review_reopen",   # 复核重开（reopened/closed/blocked）
        "formal_gate",     # FormalOutput 门禁（allowed/blocked/degraded）
        "archive_hash",    # 归档哈希校验（success/mismatch）
        "hold",            # Legal Hold（created/released/denied）
        "outbox_lag",      # outbox 滞后（gauge）
        "pg_pool_wait",    # PG 连接池等待（gauge）
        "backpressure",    # 背压触发（soft/hard）
    }
)

#: 冻结的 outcome 允许集（全域共享，保证低基数）。未命中 → ``other``。
METRIC_OUTCOMES: frozenset[str] = frozenset(
    {
        "accepted", "rejected", "quarantined", "failed",
        "allowed", "denied", "blocked", "degraded",
        "success", "enqueued", "dequeued", "retried", "dead_letter",
        "covered", "gap", "hit", "miss", "mismatch",
        "reopened", "closed", "created", "released",
        "soft", "hard", "other",
    }
)

#: 冻结的附件治理 **命名点 gauge** 允许集（低基数；无 per-attachment 标签，P2-补）。
#: 与 domain×outcome 计数、账龄分桶 gauge 正交——这些是"当前积压量"点值，单一命名。
#: 未命中此集的命名 gauge 被丢弃（防高基数）。
ATTACHMENT_GOVERNANCE_GAUGES: frozenset[str] = frozenset(
    {
        # 隔离/暂存缓冲（staged+quarantined 未清理）——in-flight 字节与句柄数。
        "attachment_quarantine_buffer_bytes",
        "attachment_quarantine_handle_count",
        # staged Attachment/AttachmentVersion 过 TTL 仍未 available（与 reaper 扫描口径一致）。
        "attachment_orphaned_staged_count",
        # 同时有 legacy version 链与治理 AttachmentVersion 链但不一致的附件数（双模型漂移）。
        "attachment_version_model_drift_count",
    }
)

#: 冻结的告警类型允许集（低基数）。
ALERT_TYPES: frozenset[str] = frozenset(
    {
        "ai_coverage_gap",       # AI 入口覆盖缺口（立即告警）
        "manifest_hash_failure", # 归档 manifest 哈希失败（立即告警）
        "cross_scope_denied_spike",  # 跨 scope 拒绝异常峰值（立即告警）
        "ocr_failure_rate",      # OCR 失败率超阈值
        "ocr_queue_age",         # OCR 排队时长超阈值
        "stale_backlog",         # stale 积压超阈值
        "gate_bypass",           # 门禁绕过尝试
        "outbox_lag",            # outbox 滞后超阈值
        "legal_hold_delete",     # Legal Hold 删除尝试
    }
)

#: gauge 域固定分桶边界（秒 / 计数），保证账龄桶低基数且可复算（P30）。
_AGE_BUCKET_BOUNDS: tuple[float, ...] = (1, 5, 30, 60, 300, 3600, 86400)

#: 跨 scope 拒绝峰值检测默认窗口（秒）与阈值。
DEFAULT_CROSS_SCOPE_WINDOW_SECONDS = 60.0
DEFAULT_CROSS_SCOPE_THRESHOLD = 10

MAX_RECENT_ALERTS = 200


# ─── 数据类 ───────────────────────────────────────────────────────────────────


@dataclass
class AlertEvent:
    """治理告警事件（design §9.3）—— 关联 command-root / audit transition / trace。

    ``metadata`` 已脱敏（不含凭据/绝对路径/原文/完整 prompt-answer）。
    """

    alert_type: str
    severity: str
    reason: str
    command_root_id: Optional[str] = None
    transition_id: Optional[str] = None
    trace_id: Optional[str] = None
    project_id: Optional[str] = None
    audit_year: Optional[int] = None
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class _Gauge:
    """低基数 gauge：count/sum/max + 固定分桶。"""

    count: int = 0
    sum: float = 0.0
    max: float = 0.0
    buckets: dict[str, int] = field(default_factory=dict)

    def observe(self, value: float) -> None:
        self.count += 1
        self.sum += value
        if value > self.max:
            self.max = value
        label = _bucket_label(value)
        self.buckets[label] = self.buckets.get(label, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        avg = self.sum / self.count if self.count else 0.0
        return {
            "count": self.count,
            "sum": round(self.sum, 4),
            "max": round(self.max, 4),
            "avg": round(avg, 4),
            "buckets": dict(sorted(self.buckets.items())),
        }


def _bucket_label(value: float) -> str:
    for bound in _AGE_BUCKET_BOUNDS:
        if value <= bound:
            return f"<={bound:g}"
    return f">{_AGE_BUCKET_BOUNDS[-1]:g}"


def _coerce_domain(domain: str) -> str:
    return domain if domain in METRIC_DOMAINS else "other"


def _coerce_outcome(outcome: str) -> str:
    return outcome if outcome in METRIC_OUTCOMES else "other"


def _coerce_severity(severity: str) -> str:
    return severity if severity in ALERT_SEVERITIES else ALERT_WARNING


def _coerce_alert_type(alert_type: str) -> str:
    return alert_type if alert_type in ALERT_TYPES else "gate_bypass"


# ─── EvidenceGovernanceMetrics (Singleton) ───────────────────────────────────


class EvidenceGovernanceMetrics:
    """治理低基数指标收集器 + trace 关联告警（进程内单例，线程安全）。

    - ``record_event(domain, outcome)``：低基数计数（series = domain × outcome 有界）。
    - ``observe_gauge(domain, value)``：账龄/滞后/池等待 gauge（固定分桶）。
    - ``record_alert(...)``：告警事件，关联 command-root/transition/trace，metadata 脱敏。
    - 立即告警快捷方法：``alert_ai_coverage_gap`` / ``alert_manifest_hash_failure`` /
      ``record_cross_scope_denied``（峰值检测）。
    """

    def __init__(
        self,
        *,
        cross_scope_window_seconds: float = DEFAULT_CROSS_SCOPE_WINDOW_SECONDS,
        cross_scope_threshold: int = DEFAULT_CROSS_SCOPE_THRESHOLD,
    ) -> None:
        self._lock = threading.RLock()
        self._counters: dict[tuple[str, str], int] = defaultdict(int)
        self._gauges: dict[str, _Gauge] = {}
        # 命名点 gauge（当前积压量，如隔离缓冲字节/句柄数/孤儿 staged/双模型漂移）。
        self._named_gauges: dict[str, float] = {}
        self._alert_type_counts: dict[str, int] = defaultdict(int)
        self._recent_alerts: deque[AlertEvent] = deque(maxlen=MAX_RECENT_ALERTS)
        # 跨 scope 拒绝峰值检测：时间戳滑动窗口
        self._cross_scope_window = float(cross_scope_window_seconds)
        self._cross_scope_threshold = int(cross_scope_threshold)
        self._cross_scope_events: deque[float] = deque()

    # ── 计数指标 ─────────────────────────────────────────────────────────

    def record_event(self, *, domain: str, outcome: str, count: int = 1) -> None:
        """记录一次低基数计数事件（domain × outcome 有界）。"""
        key = (_coerce_domain(domain), _coerce_outcome(outcome))
        with self._lock:
            self._counters[key] += int(count)

    # ── gauge（账龄 / 滞后 / 池等待） ─────────────────────────────────────

    def observe_gauge(self, *, domain: str, value: float) -> None:
        """记录一次 gauge 观测（固定分桶，低基数）。"""
        d = _coerce_domain(domain)
        with self._lock:
            g = self._gauges.get(d)
            if g is None:
                g = _Gauge()
                self._gauges[d] = g
            g.observe(float(value))

    # ── 命名点 gauge（附件治理积压量；低基数、无 per-attachment 标签） ───────

    def set_named_gauge(self, name: str, value: float) -> None:
        """记录/覆盖一个命名点 gauge 的当前值（低基数，单一命名，非分桶分布）。

        仅接受 :data:`ATTACHMENT_GOVERNANCE_GAUGES` 冻结集内的名称——未登记名称被丢弃，
        防止 per-attachment/路径等高基数标签混入（design §9.3）。value 为当前积压量点值。
        """
        if name not in ATTACHMENT_GOVERNANCE_GAUGES:
            logger.warning("忽略未登记命名 gauge（防高基数）: %s", name)
            return
        with self._lock:
            self._named_gauges[name] = float(value)

    def get_named_gauge(self, name: str) -> float | None:
        with self._lock:
            return self._named_gauges.get(name)

    # ── 告警 ─────────────────────────────────────────────────────────────

    def record_alert(
        self,
        *,
        alert_type: str,
        reason: str,
        severity: str = ALERT_WARNING,
        command_root_id: str | None = None,
        transition_id: str | None = None,
        trace_id: str | None = None,
        project_id: str | None = None,
        audit_year: int | None = None,
        metadata: dict | None = None,
    ) -> AlertEvent:
        """记录一条告警事件并主动 log（关联 command-root/transition/trace，metadata 脱敏）。"""
        atype = _coerce_alert_type(alert_type)
        sev = _coerce_severity(severity)
        event = AlertEvent(
            alert_type=atype,
            severity=sev,
            reason=reason,
            command_root_id=command_root_id,
            transition_id=transition_id,
            trace_id=trace_id,
            project_id=project_id,
            audit_year=audit_year,
            metadata=redact_audit_metadata(metadata),
        )
        with self._lock:
            self._recent_alerts.append(event)
            self._alert_type_counts[atype] += 1

        log_fn = logger.error if sev == ALERT_ERROR else logger.warning
        log_fn(
            "evidence-governance alert [%s/%s] %s (command_root=%s transition=%s trace=%s)",
            atype, sev, reason, command_root_id, transition_id, trace_id,
        )
        return event

    # ── 立即告警快捷方法（design §9.3） ──────────────────────────────────

    def alert_ai_coverage_gap(
        self,
        *,
        gap_count: int,
        trace_id: str | None = None,
        command_root_id: str | None = None,
        metadata: dict | None = None,
    ) -> AlertEvent | None:
        """AI 入口覆盖缺口 → 立即告警（gap_count>0 时）。

        只记录缺口**数量**（低基数），不记录入口名细节即可满足 "coverage gap 立即告警"；
        细节列表若传入 metadata 也会脱敏。
        """
        self.record_event(domain="ai_coverage", outcome="gap", count=max(0, gap_count))
        if gap_count <= 0:
            return None
        return self.record_alert(
            alert_type="ai_coverage_gap",
            severity=ALERT_ERROR,
            reason=f"AI 入口覆盖缺口: {gap_count} 个未登记入口",
            trace_id=trace_id,
            command_root_id=command_root_id,
            metadata={**(metadata or {}), "gap_count": gap_count},
        )

    def alert_manifest_hash_failure(
        self,
        *,
        reason: str = "归档 manifest 哈希校验失败",
        command_root_id: str | None = None,
        trace_id: str | None = None,
        project_id: str | None = None,
        audit_year: int | None = None,
        metadata: dict | None = None,
    ) -> AlertEvent:
        """归档 manifest 哈希失败 → 立即告警。"""
        self.record_event(domain="archive_hash", outcome="mismatch")
        return self.record_alert(
            alert_type="manifest_hash_failure",
            severity=ALERT_ERROR,
            reason=reason,
            command_root_id=command_root_id,
            trace_id=trace_id,
            project_id=project_id,
            audit_year=audit_year,
            metadata=metadata,
        )

    def record_cross_scope_denied(
        self,
        *,
        domain: str = "boundary",
        command_root_id: str | None = None,
        trace_id: str | None = None,
        project_id: str | None = None,
        audit_year: int | None = None,
        now: float | None = None,
    ) -> AlertEvent | None:
        """记录一次跨 scope / 越界拒绝；窗口内累计超阈值时立即告警（峰值检测）。

        返回非 None 表示本次触发了峰值告警。
        """
        ts = time.time() if now is None else float(now)
        self.record_event(domain=domain, outcome="denied")
        with self._lock:
            self._cross_scope_events.append(ts)
            cutoff = ts - self._cross_scope_window
            while self._cross_scope_events and self._cross_scope_events[0] < cutoff:
                self._cross_scope_events.popleft()
            spike = len(self._cross_scope_events) >= self._cross_scope_threshold
            window_count = len(self._cross_scope_events)
        if not spike:
            return None
        return self.record_alert(
            alert_type="cross_scope_denied_spike",
            severity=ALERT_ERROR,
            reason=(
                f"跨 scope 拒绝异常峰值: {self._cross_scope_window:g}s 内 "
                f"{window_count} 次 (阈值 {self._cross_scope_threshold})"
            ),
            command_root_id=command_root_id,
            trace_id=trace_id,
            project_id=project_id,
            audit_year=audit_year,
            metadata={"window_count": window_count, "domain": _coerce_domain(domain)},
        )

    # ── 阈值告警（可关联原始 command-root/transition） ───────────────────

    def record_threshold_alert(
        self,
        *,
        alert_type: str,
        observed: float,
        threshold: float,
        command_root_id: str | None = None,
        transition_id: str | None = None,
        trace_id: str | None = None,
        project_id: str | None = None,
        audit_year: int | None = None,
    ) -> AlertEvent | None:
        """OCR 失败率 / 排队时长 / stale 积压 / outbox 滞后超阈值 → 告警（design §R12.3）。

        ``observed <= threshold`` 时不告警（返回 None）。
        """
        if observed <= threshold:
            return None
        return self.record_alert(
            alert_type=alert_type,
            severity=ALERT_WARNING,
            reason=f"{alert_type} 超阈值: observed={observed:g} threshold={threshold:g}",
            command_root_id=command_root_id,
            transition_id=transition_id,
            trace_id=trace_id,
            project_id=project_id,
            audit_year=audit_year,
            metadata={"observed": observed, "threshold": threshold},
        )

    # ── 聚合输出 ─────────────────────────────────────────────────────────

    def get_aggregated_metrics(self) -> dict[str, Any]:
        """返回近期聚合指标（低基数；供 metrics 端点与质量面板复用）。"""
        with self._lock:
            by_domain: dict[str, dict[str, int]] = defaultdict(dict)
            for (domain, outcome), n in self._counters.items():
                by_domain[domain][outcome] = n
            return {
                "counters": {d: dict(sorted(o.items())) for d, o in sorted(by_domain.items())},
                "gauges": {d: g.snapshot() for d, g in sorted(self._gauges.items())},
                "named_gauges": dict(sorted(self._named_gauges.items())),
                "alerts": {
                    "total": sum(self._alert_type_counts.values()),
                    "by_type": dict(sorted(self._alert_type_counts.items())),
                    "recent": [asdict(a) for a in list(self._recent_alerts)[-20:]],
                },
            }

    def recent_alerts(self, limit: int = 50) -> list[AlertEvent]:
        with self._lock:
            return list(self._recent_alerts)[-limit:]

    def reset(self) -> None:
        """重置所有指标与告警（测试用）。"""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._named_gauges.clear()
            self._alert_type_counts.clear()
            self._recent_alerts.clear()
            self._cross_scope_events.clear()


# ─── Module-level singleton ──────────────────────────────────────────────────

_metrics: Optional[EvidenceGovernanceMetrics] = None
_singleton_lock = threading.Lock()


def get_evidence_metrics() -> EvidenceGovernanceMetrics:
    """获取全局治理指标收集器单例。"""
    global _metrics
    if _metrics is None:
        with _singleton_lock:
            if _metrics is None:
                _metrics = EvidenceGovernanceMetrics()
    return _metrics


def reset_evidence_metrics() -> None:
    """重置全局指标（测试用）。"""
    global _metrics
    with _singleton_lock:
        _metrics = EvidenceGovernanceMetrics()


__all__ = [
    "ALERT_INFO",
    "ALERT_WARNING",
    "ALERT_ERROR",
    "ALERT_SEVERITIES",
    "METRIC_DOMAINS",
    "METRIC_OUTCOMES",
    "ATTACHMENT_GOVERNANCE_GAUGES",
    "ALERT_TYPES",
    "DEFAULT_CROSS_SCOPE_WINDOW_SECONDS",
    "DEFAULT_CROSS_SCOPE_THRESHOLD",
    "AlertEvent",
    "EvidenceGovernanceMetrics",
    "get_evidence_metrics",
    "reset_evidence_metrics",
]
