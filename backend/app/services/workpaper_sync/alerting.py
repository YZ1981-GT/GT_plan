# -*- coding: utf-8 -*-
"""版本化 `AlertRuleRegistry`：阈值、窗口、严重级别、去重键、恢复条件与 runbook。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 29
Requirements: 13.7, 13.9
Properties: P68（告警与 timeline 共用归因字段）

═══ 为什么规则要「注册」而不是写在监控系统里 ═══

Requirement 13.9 要求「以**版本化可测试** alert rules 区分」十四类状况，「每条规则须定义
阈值、窗口、严重级别、去重键、恢复条件和 runbook」。写在 Grafana/Alertmanager 里的规则
无法被本仓库的测试驱动，于是三件事都验证不了：

1. **覆盖面** —— 13.9 点名的每一类是否都有规则（漏一类＝那类故障永远静默）；
2. **不误报/不漏报的分型** —— 例如「无 successor 的 recovery_required」必须有自己的
   规则和 runbook，不能落进通用 error 告警（Task 29 明文禁止压平）；
3. **去重键是否可归因** —— 去重键必须是该指标真实带得出的维度，否则同一 room 的十次
   抖动会炸成十条告警，或者反过来把两个 room 的故障合成一条。

所以规则表是 JSON 配置 + 本模块解析 + :func:`validate_registry` 自检，并与
:mod:`app.services.workpaper_sync.metrics` 的目录**双向锁死**：

* 规则引用的 `metric` 必须在 `METRIC_CATALOG` 里（否则规则永不触发）；
* 每个 `alert_required=True` 的指标必须**恰有一条**规则（否则「已覆盖」是假的）；
* 规则的 `dedupe_key_fields` 必须是该指标归因等级允许的维度的子集。

第二条是这份实现里最重要的一条：它让「加指标忘了加规则」和「删规则」两个方向都打红。

═══ synthetic event 评估 ═══

:meth:`AlertRuleRegistry.evaluate` 吃的是 :class:`~app.services.workpaper_sync.metrics.MetricSample`
序列（守卫用合成事件驱动），返回按 `(rule_id, dedupe_key)` 去重后的 :class:`AlertInstance`。
它**不**连接任何外部系统 —— 判据是「规则在给定事件流上是否恰好触发」，而不是「告警是否
发到了钉钉」。

═══ 恢复条件 ═══

两种，不多不少：

* `below_threshold` —— 计数/水位在恢复窗口内回落到阈值以下（抖动型：outbox 深度、
  fence 失效频率）；
* `explicit_resolution` —— 必须有人处理（close singleton 违规、candidate 误暴露、
  post-durable 失败）。这类**不许**自动恢复：数据可能已经不一致，静默消失等于把
  一次真实事故从记录里抹掉。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Iterable, Mapping, Sequence

from app.services.workpaper_sync.metrics import (
    METRICS_BY_NAME,
    AttributionDim,
    MetricDefinition,
    MetricKind,
    MetricSample,
)
from app.services.workpaper_sync.models import SyncDomainError

#: 规则表真源。
ALERT_RULES_PATH: Final[Path] = (
    Path(__file__).resolve().parents[3] / "data" / "workpaper_sync_alert_rules.json"
)


class AlertConfigError(SyncDomainError):
    """规则表缺失/非法。无规则时**不** fallback —— 静默无告警是最糟的形态。"""

    error_code = "alert_rules_invalid"


class AlertUsageError(SyncDomainError):
    """评估调用协议违规。"""

    error_code = "alert_usage_invalid"


class AlertSeverity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertComparison(str, Enum):
    #: 窗口内命中事件数 ≥ 阈值。
    count_gte = "count_gte"
    #: 最新 gauge 水位 ≥ 阈值。
    gauge_gte = "gauge_gte"
    #: 出现一次即触发（阈值必须为 1）。
    any_occurrence = "any_occurrence"


class RecoveryKind(str, Enum):
    below_threshold = "below_threshold"
    explicit_resolution = "explicit_resolution"


class AlertCondition(str, Enum):
    """Requirement 13.9 逐条点名的状况 + Task 29 追加的两条分型。

    🔴 这个枚举是**封闭**的，且与规则表一一对应：
    多一条规则没有 condition ⇒ 解析失败；一个 condition 没有规则 ⇒
    :func:`validate_registry` 打红。「加了指标忘加规则」和「悄悄删规则」都会被抓。
    """

    onlyoffice_unavailable = "onlyoffice_unavailable"
    callback_not_delivered = "callback_not_delivered"
    unmatched_status2 = "unmatched_status2"
    recovery_backlog = "recovery_backlog"
    close_intent_singleton_violation = "close_intent_singleton_violation"
    close_leader_no_successor = "close_leader_no_successor"
    post_durable_processing_failure = "post_durable_processing_failure"
    permission_or_write_fence_invalidated = "permission_or_write_fence_invalidated"
    definition_bundle_drift = "definition_bundle_drift"
    candidate_exposed = "candidate_exposed"
    candidate_finalize_failure = "candidate_finalize_failure"
    refresh_required_backlog = "refresh_required_backlog"
    canonical_rematerialize_failure = "canonical_rematerialize_failure"
    outbox_backlog = "outbox_backlog"
    orphan_retention_backlog = "orphan_retention_backlog"
    windows_file_in_use = "windows_file_in_use"
    cross_participant_key_reuse = "cross_participant_key_reuse"


#: Requirement 13.9 原文点名的十四类 → 本注册表的 condition。
#:
#: 这张表存在的唯一目的是让「13.9 是否被逐条覆盖」可被机器核对，而不是靠人读一遍
#: requirements。它是**独立分母**：不是从规则表推出来的，所以规则表少一条会红，
#: 而不是两边一起变。
REQUIREMENT_13_9_CONDITIONS: Final[Mapping[str, AlertCondition]] = {
    "OO 服务不可用": AlertCondition.onlyoffice_unavailable,
    "callback 不达": AlertCondition.callback_not_delivered,
    "无法归组的 status=2": AlertCondition.unmatched_status2,
    "recovery case/claim/download-only 积压": AlertCondition.recovery_backlog,
    "close-intent singleton 违规": AlertCondition.close_intent_singleton_violation,
    "callback 已 durable 后处理失败": AlertCondition.post_durable_processing_failure,
    "permission/write fence 失效": AlertCondition.permission_or_write_fence_invalidated,
    "definition bundle/contract/template 漂移": AlertCondition.definition_bundle_drift,
    "candidate finalize 失败": AlertCondition.candidate_finalize_failure,
    "candidate 误暴露": AlertCondition.candidate_exposed,
    "refresh-required 积压": AlertCondition.refresh_required_backlog,
    "canonical rematerialize 失败": AlertCondition.canonical_rematerialize_failure,
    "outbox 堆积": AlertCondition.outbox_backlog,
    "orphan/retention backlog": AlertCondition.orphan_retention_backlog,
    "Windows 文件占用": AlertCondition.windows_file_in_use,
}

#: runbook 至少要能回答「怎么判断」「怎么处理」「什么不能做」，太短的必然是占位。
MIN_RUNBOOK_CHARS: Final[int] = 60


@dataclass(frozen=True)
class RecoveryCondition:
    kind: RecoveryKind
    window_seconds: int

    @property
    def auto_recovers(self) -> bool:
        return self.kind is RecoveryKind.below_threshold


@dataclass(frozen=True)
class AlertRule:
    rule_id: str
    condition: AlertCondition
    metric: str
    severity: AlertSeverity
    comparison: AlertComparison
    threshold: float
    window_seconds: int
    result_filter: tuple[str, ...]
    dedupe_key_fields: tuple[AttributionDim, ...]
    recovery: RecoveryCondition
    runbook: str

    def dedupe_key(self, labels: Mapping[str, Any]) -> str:
        """去重键：按声明顺序拼 `dim=value`，缺值写 `-`（不省略，避免两键相撞）。"""
        return "|".join(
            f"{dim.value}={labels.get(dim.value, '-')}" for dim in self.dedupe_key_fields
        )

    def matches(self, sample: MetricSample) -> bool:
        if sample.metric != self.metric:
            return False
        if not self.result_filter:
            return True
        return sample.result in self.result_filter


@dataclass(frozen=True)
class AlertInstance:
    rule_id: str
    condition: AlertCondition
    severity: AlertSeverity
    dedupe_key: str
    observed: float
    threshold: float
    window_seconds: int
    sample_count: int
    auto_recovers: bool
    runbook: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "condition": self.condition.value,
            "severity": self.severity.value,
            "dedupe_key": self.dedupe_key,
            "observed": self.observed,
            "threshold": self.threshold,
            "window_seconds": self.window_seconds,
            "sample_count": self.sample_count,
            "auto_recovers": self.auto_recovers,
            "runbook": self.runbook,
        }


class AlertRuleRegistry:
    """解析后的规则表。构造即校验（坏规则不该有机会参与评估）。"""

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        catalog: Mapping[str, MetricDefinition] | None = None,
    ) -> None:
        self._catalog = dict(catalog or METRICS_BY_NAME)
        self.registry_version = str(config.get("registry_version") or "").strip()
        if not self.registry_version:
            raise AlertConfigError("规则表缺 registry_version —— 告警语义变化必须可追溯")
        self.schema_version = int(config.get("schema_version") or 0)
        if self.schema_version <= 0:
            raise AlertConfigError("规则表 schema_version 必须为正整数")

        raw_rules = config.get("rules")
        if not isinstance(raw_rules, Sequence) or isinstance(raw_rules, (str, bytes)):
            raise AlertConfigError("规则表 rules 必须是数组")
        if not raw_rules:
            raise AlertConfigError("规则表为空 —— 空表会让所有覆盖判据恒成立（假绿）")

        rules: list[AlertRule] = []
        for raw in raw_rules:
            if not isinstance(raw, Mapping):
                raise AlertConfigError("rules[] 元素必须是对象")
            rules.append(self._parse_rule(raw))
        by_id: dict[str, AlertRule] = {}
        for rule in rules:
            if rule.rule_id in by_id:
                raise AlertConfigError(f"rule_id 重复: {rule.rule_id}")
            by_id[rule.rule_id] = rule
        self.rules: tuple[AlertRule, ...] = tuple(rules)
        self.rules_by_id: Mapping[str, AlertRule] = by_id
        by_condition: dict[AlertCondition, AlertRule] = {}
        for rule in rules:
            if rule.condition in by_condition:
                raise AlertConfigError(
                    f"condition {rule.condition.value} 被两条规则占用 "
                    f"({by_condition[rule.condition].rule_id} / {rule.rule_id}) —— "
                    "一类状况只能有一条规则，否则同一故障双报"
                )
            by_condition[rule.condition] = rule
        self.rules_by_condition: Mapping[AlertCondition, AlertRule] = by_condition

    # ------------------------------------------------------------------
    # 解析
    # ------------------------------------------------------------------

    def _parse_rule(self, raw: Mapping[str, Any]) -> AlertRule:
        rule_id = str(raw.get("rule_id") or "").strip()
        if not rule_id:
            raise AlertConfigError("规则缺 rule_id")
        try:
            condition = AlertCondition(str(raw.get("condition")))
        except ValueError as exc:
            raise AlertConfigError(
                f"{rule_id}: condition {raw.get('condition')!r} 未登记 AlertCondition"
            ) from exc
        metric = str(raw.get("metric") or "")
        definition = self._catalog.get(metric)
        if definition is None:
            raise AlertConfigError(
                f"{rule_id}: metric {metric!r} 不在 METRIC_CATALOG —— 规则会永不触发"
            )
        try:
            severity = AlertSeverity(str(raw.get("severity")))
        except ValueError as exc:
            raise AlertConfigError(
                f"{rule_id}: severity {raw.get('severity')!r} 非法"
            ) from exc
        try:
            comparison = AlertComparison(str(raw.get("comparison")))
        except ValueError as exc:
            raise AlertConfigError(
                f"{rule_id}: comparison {raw.get('comparison')!r} 非法"
            ) from exc
        try:
            threshold = float(raw["threshold"])
            window_seconds = int(raw["window_seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AlertConfigError(f"{rule_id}: threshold/window_seconds 非法") from exc
        if threshold <= 0:
            raise AlertConfigError(
                f"{rule_id}: threshold 必须为正 —— 0 会让规则对任何空事件流都触发"
            )
        if window_seconds <= 0:
            raise AlertConfigError(f"{rule_id}: window_seconds 必须为正")
        if comparison is AlertComparison.any_occurrence and threshold != 1:
            raise AlertConfigError(
                f"{rule_id}: any_occurrence 的 threshold 只能是 1，实得 {threshold}"
            )
        if comparison is AlertComparison.gauge_gte and definition.kind is not MetricKind.gauge:
            raise AlertConfigError(
                f"{rule_id}: gauge_gte 只能用于 gauge，{metric} 是 {definition.kind.value}"
            )
        if comparison is not AlertComparison.gauge_gte and definition.kind is MetricKind.gauge:
            raise AlertConfigError(
                f"{rule_id}: gauge 指标 {metric} 只能用 gauge_gte"
            )

        raw_filter = raw.get("result_filter")
        if raw_filter is None or not isinstance(raw_filter, Sequence) or isinstance(raw_filter, str):
            raise AlertConfigError(f"{rule_id}: result_filter 必须是数组（可为空数组）")
        result_filter = tuple(str(item) for item in raw_filter)
        unknown_results = sorted(set(result_filter) - set(definition.result_domain))
        if unknown_results:
            raise AlertConfigError(
                f"{rule_id}: result_filter {unknown_results} 不在 {metric} 的封闭域 "
                f"{list(definition.result_domain)} —— 拼错的过滤值会让规则静默不触发"
            )
        if definition.result_domain and not result_filter:
            raise AlertConfigError(
                f"{rule_id}: {metric} 有封闭 result 域，规则必须显式声明关心哪些结果 —— "
                "空过滤会把成功结果也算进告警"
            )

        raw_dims = raw.get("dedupe_key_fields")
        if not isinstance(raw_dims, Sequence) or isinstance(raw_dims, str) or not raw_dims:
            raise AlertConfigError(
                f"{rule_id}: dedupe_key_fields 必须是非空数组 —— 无去重键会让抖动炸成刷屏"
            )
        dims: list[AttributionDim] = []
        for item in raw_dims:
            try:
                dims.append(AttributionDim(str(item)))
            except ValueError as exc:
                raise AlertConfigError(
                    f"{rule_id}: 去重维度 {item!r} 不是 AttributionDim"
                ) from exc
        allowed = set(definition.required_dims) | {
            AttributionDim.project,
            AttributionDim.wp,
            AttributionDim.entry,
        }
        illegal = sorted(d.value for d in dims if d not in allowed)
        if illegal:
            raise AlertConfigError(
                f"{rule_id}: 去重维度 {illegal} 不在 {metric}"
                f"（{definition.attribution.value}）可归因的维度里 —— "
                "去重键取不到值时所有告警会合成一条"
            )

        raw_recovery = raw.get("recovery")
        if not isinstance(raw_recovery, Mapping):
            raise AlertConfigError(f"{rule_id}: recovery 必须是对象")
        try:
            recovery = RecoveryCondition(
                kind=RecoveryKind(str(raw_recovery.get("kind"))),
                window_seconds=int(raw_recovery["window_seconds"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AlertConfigError(f"{rule_id}: recovery 非法: {raw_recovery!r}") from exc
        if recovery.window_seconds < window_seconds:
            raise AlertConfigError(
                f"{rule_id}: 恢复窗口 {recovery.window_seconds}s 小于触发窗口 "
                f"{window_seconds}s —— 会在故障仍在发生时宣布恢复"
            )

        runbook = str(raw.get("runbook") or "").strip()
        if len(runbook) < MIN_RUNBOOK_CHARS:
            raise AlertConfigError(
                f"{rule_id}: runbook 少于 {MIN_RUNBOOK_CHARS} 字 —— "
                "占位 runbook 等于没有 runbook（Requirement 13.9 明确要求）"
            )
        return AlertRule(
            rule_id=rule_id,
            condition=condition,
            metric=metric,
            severity=severity,
            comparison=comparison,
            threshold=threshold,
            window_seconds=window_seconds,
            result_filter=result_filter,
            dedupe_key_fields=tuple(dims),
            recovery=recovery,
            runbook=runbook,
        )

    # ------------------------------------------------------------------
    # 评估
    # ------------------------------------------------------------------

    def evaluate(
        self,
        samples: Iterable[MetricSample],
        *,
        now: datetime | None = None,
    ) -> tuple[AlertInstance, ...]:
        """在 synthetic 事件流上求触发的告警（已按 `(rule, dedupe_key)` 去重）。

        `samples` 不带时间戳 —— 调用方按窗口自行切片后传入。这是刻意的：把「窗口切片」
        留给调用方，本方法就只有「阈值 + 去重 + 分型」三件事，判据不会被时间抖动污染。
        """
        del now  # 保留参数以固定调用形态；窗口切片由调用方负责（见 docstring）
        collected = list(samples)
        instances: list[AlertInstance] = []
        for rule in self.rules:
            buckets: dict[str, list[MetricSample]] = {}
            for sample in collected:
                if not rule.matches(sample):
                    continue
                buckets.setdefault(rule.dedupe_key(sample.labels), []).append(sample)
            for key, bucket in sorted(buckets.items()):
                observed = (
                    bucket[-1].value
                    if rule.comparison is AlertComparison.gauge_gte
                    else float(sum(s.value for s in bucket))
                )
                if observed < rule.threshold:
                    continue
                instances.append(
                    AlertInstance(
                        rule_id=rule.rule_id,
                        condition=rule.condition,
                        severity=rule.severity,
                        dedupe_key=key,
                        observed=observed,
                        threshold=rule.threshold,
                        window_seconds=rule.window_seconds,
                        sample_count=len(bucket),
                        auto_recovers=rule.recovery.auto_recovers,
                        runbook=rule.runbook,
                    )
                )
        return tuple(instances)

    def recovery_deadline(self, rule_id: str, *, fired_at: datetime) -> datetime | None:
        """自动恢复型规则的恢复评估时刻；显式处理型返回 ``None``。"""
        rule = self.rules_by_id.get(rule_id)
        if rule is None:
            raise AlertUsageError(f"未知 rule_id: {rule_id}")
        if not rule.recovery.auto_recovers:
            return None
        if fired_at.tzinfo is None:
            raise AlertUsageError("fired_at 必须带时区（服务端时钟，Requirement 13.10）")
        return fired_at.astimezone(timezone.utc) + timedelta(
            seconds=rule.recovery.window_seconds
        )

    def fingerprint(self) -> dict[str, Any]:
        return {
            "registry_version": self.registry_version,
            "schema_version": self.schema_version,
            "rule_count": len(self.rules),
            "rule_ids": [rule.rule_id for rule in self.rules],
        }


def validate_registry(registry: AlertRuleRegistry) -> tuple[str, ...]:
    """注册表 ↔ 指标目录 ↔ Requirement 13.9 的三向核对。空 = 合规。"""
    problems: list[str] = []

    required_metrics = {
        name for name, definition in METRICS_BY_NAME.items() if definition.alert_required
    }
    covered_metrics = {rule.metric for rule in registry.rules}
    for metric in sorted(required_metrics - covered_metrics):
        problems.append(
            f"指标 {metric} 声明 alert_required=True 但没有任何规则 —— "
            "「已覆盖」是假的"
        )
    for metric in sorted(covered_metrics - required_metrics):
        problems.append(
            f"规则引用了 alert_required=False 的指标 {metric} —— "
            "要么给指标打上 alert_required，要么删规则；两侧必须一致"
        )

    for label, condition in sorted(REQUIREMENT_13_9_CONDITIONS.items()):
        if condition not in registry.rules_by_condition:
            problems.append(
                f"Requirement 13.9 的「{label}」没有对应规则（condition={condition.value}）"
            )
    for condition in AlertCondition:
        if condition not in registry.rules_by_condition:
            problems.append(f"AlertCondition.{condition.name} 没有规则")

    for rule in registry.rules:
        if rule.severity is AlertSeverity.info and rule.recovery.auto_recovers is False:
            problems.append(
                f"{rule.rule_id}: info 级却要求人工恢复 —— 级别与恢复方式矛盾"
            )
    return tuple(problems)


def load_alert_config(path: Path | None = None) -> Mapping[str, Any]:
    target = path or ALERT_RULES_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AlertConfigError(
            f"告警规则表缺失: {target} —— 无规则时不得宣称同步链可运维"
        ) from exc
    except json.JSONDecodeError as exc:
        raise AlertConfigError(f"告警规则表不是合法 JSON: {target}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise AlertConfigError(f"告警规则表根节点必须是对象: {target}")
    return payload


@lru_cache(maxsize=1)
def load_alert_registry() -> AlertRuleRegistry:
    return AlertRuleRegistry(load_alert_config())


__all__ = [
    "ALERT_RULES_PATH",
    "MIN_RUNBOOK_CHARS",
    "REQUIREMENT_13_9_CONDITIONS",
    "AlertComparison",
    "AlertCondition",
    "AlertConfigError",
    "AlertInstance",
    "AlertRule",
    "AlertRuleRegistry",
    "AlertSeverity",
    "AlertUsageError",
    "RecoveryCondition",
    "RecoveryKind",
    "load_alert_config",
    "load_alert_registry",
    "validate_registry",
]
