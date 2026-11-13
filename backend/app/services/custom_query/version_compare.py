"""高级查询版本向量比较与时效结论（AQF §4.5）。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from app.services.custom_query.version_capture import VersionComponent, VersionVector, vector_hash


@dataclass(frozen=True)
class ComponentChange:
    key: str
    label: str
    status: str
    reason: str
    before: dict[str, Any]
    after: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "label": self.label, "status": self.status,
            "reason": self.reason, "before": self.before, "after": self.after,
        }


@dataclass(frozen=True)
class FreshnessResult:
    status: str
    changes: tuple[ComponentChange, ...]
    weak: bool
    checked_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "changes": [item.as_dict() for item in self.changes],
            "weak": self.weak,
            "checked_at": self.checked_at,
        }


def _component(value: VersionComponent | dict[str, Any]) -> VersionComponent:
    if isinstance(value, VersionComponent):
        return value
    return VersionComponent(
        key=str(value.get("key", "")), table=str(value.get("table", "")), label=str(value.get("label", "")),
        basis=str(value.get("basis", "")), scope=dict(value.get("scope") or {}),
        rows=value.get("rows"), digest=value.get("digest"), latest_update=value.get("latest_update"),
        dataset=value.get("dataset"), weak=bool(value.get("weak")), error=value.get("error"),
    )


def _before_after(before: VersionComponent, after: VersionComponent) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {"rows": before.rows, "latest_update": before.latest_update, "digest": before.digest, "basis": before.basis},
        {"rows": after.rows, "latest_update": after.latest_update, "digest": after.digest, "basis": after.basis},
    )


def _scope_reason(before: VersionComponent, after: VersionComponent) -> str | None:
    old = before.scope.get("cycles", before.scope.get("scope_signature"))
    new = after.scope.get("cycles", after.scope.get("scope_signature"))
    if old != new and (old is not None or new is not None):
        return "您的审计循环范围已变化" if before.key == "scope" else "查询作用域已变化"
    old_standard = before.scope.get("standard")
    new_standard = after.scope.get("standard")
    if old_standard != new_standard and (old_standard is not None or new_standard is not None):
        return f"报表准则由 {old_standard or '未设置'} 变为 {new_standard or '未设置'}"
    return None


def compare_component(before: VersionComponent | dict[str, Any], after: VersionComponent | dict[str, Any]) -> ComponentChange | None:
    """比较单个分量；latest_update 仅展示，不能单独制造变化。"""
    old, new = _component(before), _component(after)
    before_payload, after_payload = _before_after(old, new)
    if old.error or new.error:
        reason = old.error or new.error or "来源版本无法采集"
        return ComponentChange(old.key, old.label or new.label, "unknown", reason, before_payload, after_payload)
    scope_reason = _scope_reason(old, new)
    if scope_reason:
        return ComponentChange(old.key, old.label or new.label, "stale", scope_reason, before_payload, after_payload)
    if old.basis == "dataset" or new.basis == "dataset":
        old_id = (old.dataset or {}).get("id") or old.digest
        new_id = (new.dataset or {}).get("id") or new.digest
        if old_id != new_id:
            if old_id and new_id:
                reason = f"生效数据集已切换（原激活于 {old.latest_update or '未知'}，现激活于 {new.latest_update or '未知'}）"
            elif old_id and not new_id:
                reason = "生效数据集已失效"
            else:
                reason = "已导入生效数据集"
            return ComponentChange(old.key, old.label or new.label, "stale", reason, before_payload, after_payload)
    if old.digest == new.digest and old.rows == new.rows:
        return None
    if old.rows != new.rows:
        return ComponentChange(old.key, old.label or new.label, "stale",
                               f"{old.label or new.label}行数 {old.rows} → {new.rows}", before_payload, after_payload)
    return ComponentChange(old.key, old.label or new.label, "stale",
                           f"{old.label or new.label}有行被修改（最近更新 {new.latest_update or '未知'}）",
                           before_payload, after_payload)


def compare_vectors(
    before: VersionVector | Iterable[VersionComponent | dict[str, Any]] | dict[str, Any],
    after: VersionVector | Iterable[VersionComponent | dict[str, Any]] | dict[str, Any],
    *,
    checked_at: datetime | None = None,
) -> FreshnessResult:
    """按 key 对齐两次采集结果：变化优先于无法判定，最后才是 current。"""
    def items(value: Any) -> list[VersionComponent]:
        if isinstance(value, VersionVector):
            return list(value.components)
        if isinstance(value, dict):
            value = value.get("components", value.get("version_vector", []))
        return [_component(item) for item in value]

    old_items = {item.key: item for item in items(before)}
    new_items = {item.key: item for item in items(after)}
    changes: list[ComponentChange] = []
    for key in sorted(set(old_items) | set(new_items)):
        if key not in old_items:
            item = new_items[key]
            changes.append(ComponentChange(key, item.label, "unknown", "查询时该来源的版本未能采集", {}, item.as_dict()))
            continue
        if key not in new_items:
            item = old_items[key]
            changes.append(ComponentChange(key, item.label, "unknown", "本次判定的来源版本无法采集", item.as_dict(), {}))
            continue
        change = compare_component(old_items[key], new_items[key])
        if change:
            changes.append(change)
    weak = any(item.weak for item in old_items.values()) or any(item.weak for item in new_items.values())
    status = "stale" if any(item.status == "stale" for item in changes) else ("unknown" if changes else "current")
    stamp = (checked_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    return FreshnessResult(status, tuple(changes), weak, stamp)


def compare_version_vectors(before: Iterable[VersionComponent | dict[str, Any]], after: Iterable[VersionComponent | dict[str, Any]]) -> FreshnessResult:
    """兼容调用名；实际比较由 compare_vectors 完成。"""
    return compare_vectors(before, after)


def current_message(result: FreshnessResult) -> str | None:
    if result.status != "current":
        return None
    message = "自查询开始以来未检测到来源变化"
    if result.weak:
        message += "；部分来源仅按更新时间判断，未写更新时间的改动可能检测不到"
    return message


__all__ = ["ComponentChange", "FreshnessResult", "compare_component", "compare_vectors", "compare_version_vectors", "current_message", "vector_hash"]


def compare_vector(
    before: list[dict[str, Any]] | list[VersionComponent],
    after: list[VersionComponent] | list[dict[str, Any]],
) -> dict[str, Any]:
    """便捷接口：直接返回 dict（供路由使用）。"""
    result = compare_vectors(before, after)
    return result.as_dict()
