"""统一公式来源信封与定义身份契约。

S5 只覆盖报表 current、附注自动公式和公式推送目标。底稿域等 S1
统一有效定义后再接入同一契约。
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Mapping
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.formula_settings.definitions import exec_view

ProvenanceDomain = Literal["report", "note", "push"]
ProvenanceValueSlot = Literal["current", "prior", "opening", "adjustment"]
ProvenanceValueState = Literal[
    "auto", "manual", "locked", "kept", "pending_confirm", "failed"
]


class InputAtom(BaseModel):
    """一次实际取数的可序列化记录。"""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    key: str = Field(min_length=1, max_length=512)
    value: Any
    source_ref: str | None = Field(default=None, max_length=1024)
    source_project_id: UUID | None = None


@dataclass(frozen=True)
class DefinitionIdentity:
    """执行前解析出的定义版本、hash、层级和来源记录。"""

    version: int
    definition_hash: str
    layer: str
    source_id: str | None = None
    definition_ref: Mapping[str, str] = field(default_factory=dict)
    definition_snapshot: Mapping[str, Any] = field(default_factory=dict)


def _canonical_value(value: Any) -> Any:
    """转成跨 Python / JSON 稳定的值；金额统一使用定点文本。"""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        resolved = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return resolved.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("来源摘要不接受 NaN 或无穷金额")
        return format(value, "f")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("来源摘要不接受 NaN 或无穷浮点数")
        return format(Decimal(str(value)), "f")
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        values = [_canonical_value(item) for item in value]
        return sorted(values, key=canonical_json)
    return str(value)


def canonical_json(value: Any) -> str:
    """返回稳定、无空白、拒绝非有限数字的 JSON 文本。"""
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def push_definition_hash(rule: Any, ruleset_hash: str | None = None) -> str:
    """生成推送规则身份 hash，仅包含实际执行字段和规则集摘要。"""
    return sha256_canonical(push_rule_snapshot(rule, ruleset_hash))


def normalize_input_atom(
    kind: str,
    key: str,
    value: Any,
    source_ref: str | None = None,
    source_project_id: UUID | str | None = None,
) -> InputAtom:
    """规范化并限制实际输入原子，拒绝不可审计的对象序列化。"""
    canonical = _canonical_input_value(value)
    if len(canonical_json(canonical).encode("utf-8")) > _MAX_INPUT_VALUE_BYTES:
        raise ValueError("来源输入值超过展示安全上限")
    return InputAtom(
        kind=str(kind),
        key=str(key),
        value=canonical,
        source_ref=str(source_ref) if source_ref is not None else None,
        source_project_id=UUID(str(source_project_id)) if source_project_id is not None else None,
    )


def input_digest(inputs: list[InputAtom] | list[Mapping[str, Any]]) -> str:
    """按 multiset 计算输入摘要；重复 key 不覆盖，非法对象不静默字符串化。"""
    normalized = [
        normalize_input_atom(
            item.kind, item.key, item.value, item.source_ref, item.source_project_id,
        ) if isinstance(item, InputAtom) else normalize_input_atom(
            str(item.get("kind") or ""), str(item.get("key") or ""), item.get("value"),
            item.get("source_ref"), item.get("source_project_id"),
        )
        for item in inputs
    ]
    canonical_atoms = sorted(
        canonical_json(item.model_dump(mode="python")) for item in normalized
    )
    return hashlib.sha256(canonical_json(canonical_atoms).encode("utf-8")).hexdigest()


def input_summary(
    inputs: list[InputAtom] | list[Mapping[str, Any]],
    *,
    limit: int = 200,
) -> tuple[list[InputAtom], int, bool, str]:
    """返回稳定排序的展示输入、全量数量、截断标志和全量 digest。"""
    if limit < 0:
        raise ValueError("输入展示上限不能为负数")
    atoms = [
        normalize_input_atom(
            item.kind,
            item.key,
            item.value,
            item.source_ref,
            item.source_project_id,
        )
        if isinstance(item, InputAtom)
        else normalize_input_atom(
            str(item.get("kind") or ""),
            str(item.get("key") or ""),
            item.get("value"),
            item.get("source_ref"),
            item.get("source_project_id"),
        )
        for item in inputs
    ]
    ordered = sorted(atoms, key=lambda atom: canonical_json(atom.model_dump(mode="python")))
    return ordered[:limit], len(ordered), len(ordered) > limit, input_digest(ordered)


def report_definition_identity(config: Any) -> DefinitionIdentity:
    """从有效报表配置解析身份，保存实际来源与 canonical 执行投影。"""
    definition = {
        key: getattr(config, key, None)
        for key in (
            "formula", "aje_formula", "rje_formula", "formula_category",
        )
    }
    version = int(
        getattr(config, "effective_definition_version", None)
        or getattr(config, "definition_version", None)
        or getattr(config, "formula_version", None)
        or 1
    )
    layer = getattr(config, "effective_definition_layer", None)
    if not layer:
        standard = str(getattr(config, "applicable_standard", ""))
        layer = "project" if standard.startswith("project:") else "global"
    source_id = getattr(config, "effective_source_id", None) or getattr(config, "id", None)
    if source_id is None:
        source_id = f"{getattr(config, 'report_type', '')}:{getattr(config, 'row_code', '')}:{layer}"
    snapshot = exec_view("report", definition) or {}
    return definition_identity(
        version=version, layer=str(layer), kind="report_config", source_id=str(source_id), snapshot=snapshot,
    )


def note_definition_identity(slot: Any) -> DefinitionIdentity:
    """从 EffectiveSlot 解析附注公式的实际来源层、稳定引用与执行投影。"""
    layer = str(getattr(slot, "layer", "preset") or "preset")
    local = getattr(slot, "local", None)
    upstream = getattr(slot, "upstream", None)
    source = local if layer in {"project", "template", "pinned"} and local is not None else upstream
    definition = getattr(slot, "definition", None)
    version = int(getattr(source, "version", None) or 1)
    slot_key = str(getattr(slot, "slot_key", "") or "unknown")
    source_id = getattr(source, "row_id", None) or f"{layer}:{slot_key}"
    snapshot = exec_view("note", definition) or {"slot_key": slot_key}
    return definition_identity(
        version=version,
        layer=layer,
        kind="preset" if layer == "preset" else "formula_setting",
        source_id=str(source_id),
        snapshot=snapshot,
    )


def push_rule_snapshot(rule: Any, ruleset_hash: str | None = None) -> dict[str, Any]:
    """仅保留推送执行所需字段，描述文本变化不触发 stale。"""
    return {
        "rule_id": str(getattr(rule, "rule_id", "")),
        "page_key": str(getattr(rule, "page_key", "")),
        "stage": str(getattr(rule, "stage", "")),
        "policy": str(getattr(rule, "policy", "")),
        "target": asdict(getattr(rule, "target", {})) if is_dataclass(getattr(rule, "target", None)) else getattr(rule, "target", {}),
        "source": asdict(getattr(rule, "source", {})) if is_dataclass(getattr(rule, "source", None)) else getattr(rule, "source", {}),
        "triggers": list(getattr(rule, "triggers", ()) or ()),
        "version": int(getattr(rule, "version", 1) or 1),
        "status": str(getattr(rule, "status", "active")),
        "ruleset_hash": ruleset_hash,
    }


def push_rule_identity(rule: Any, ruleset_hash: str | None = None) -> DefinitionIdentity:
    snapshot = push_rule_snapshot(rule, ruleset_hash)
    rule_id = str(getattr(rule, "rule_id", "") or "unknown")
    return definition_identity(
        version=int(getattr(rule, "version", None) or 1),
        layer="system",
        kind="push_rule",
        source_id=rule_id,
        snapshot=snapshot,
    )


# ADR-FPE-12 的正式写入契约。
CalculationStatus = Literal["succeeded", "failed", "skipped"]


class ProvenanceEnvelopeV1(BaseModel):
    """一次不可变的公式计算尝试，而不是当前最终值来源。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    attempt_id: UUID = Field(default_factory=uuid4)
    domain: ProvenanceDomain
    value_slot: ProvenanceValueSlot = "current"
    run_id: UUID
    computed_at: datetime
    computed_by: UUID | None = None
    calc_version: str = Field(min_length=1, max_length=100)
    definition_ref: dict[str, str] = Field(min_length=1)
    definition_version: int = Field(ge=1)
    definition_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    definition_layer: str = Field(min_length=1, max_length=64)
    definition_snapshot: dict[str, Any]
    inputs: list[InputAtom] = Field(default_factory=list)
    input_count: int = Field(ge=0)
    inputs_truncated: bool = False
    input_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    calculated_value: Any | None = None
    calculation_status: CalculationStatus
    error_code: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _validate_attempt(self) -> "ProvenanceEnvelopeV1":
        if self.calculation_status == "succeeded" and self.calculated_value is None:
            raise ValueError("成功的公式计算必须保存 calculated_value")
        if self.calculation_status != "succeeded" and self.error_code is None:
            raise ValueError("失败或跳过的公式计算必须保存稳定 error_code")
        if self.input_count < len(self.inputs):
            raise ValueError("input_count 不能小于展示输入数")
        return self


class FinalValueProvenanceV1(BaseModel):
    """当前最终值的状态，以及最近计算和实际采用计算的独立引用。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    value_slot: ProvenanceValueSlot = "current"
    value_state: ProvenanceValueState
    calculation_applied: bool = False
    applied_attempt: ProvenanceEnvelopeV1 | None = None
    last_calculation: ProvenanceEnvelopeV1 | None = None

    @model_validator(mode="after")
    def _validate_final_value(self) -> "FinalValueProvenanceV1":
        if not self.calculation_applied:
            return self
        if self.applied_attempt is None or self.last_calculation is None:
            raise ValueError("已采用计算必须同时保存 applied_attempt 和 last_calculation")
        if self.last_calculation.calculation_status != "succeeded":
            raise ValueError("失败或跳过的计算不能成为当前最终值来源")
        if self.applied_attempt.attempt_id != self.last_calculation.attempt_id:
            raise ValueError("已采用计算必须是最近一次计算")
        return self


_MAX_INPUT_VALUE_BYTES = 4096
_REDACTED_INPUT_KEY = "（无权查看来源）"


def _canonical_input_value(value: Any) -> Any:
    """输入摘要仅接受有明确 JSON 语义的值，金额统一为定点文本。"""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        when = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("来源摘要不接受 NaN 或无穷金额")
        return format(value, "f")
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("来源摘要不接受 NaN 或无穷浮点数")
        return format(Decimal(str(value)), "f")
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("来源输入对象的键必须是字符串")
        return {key: _canonical_input_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_input_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonical_input_value(item) for item in value), key=canonical_json)
    raise TypeError(f"来源摘要不支持 {type(value).__name__} 类型")


def definition_identity(
    *,
    version: int,
    layer: str,
    kind: str,
    source_id: str,
    snapshot: Mapping[str, Any],
) -> DefinitionIdentity:
    """从稳定引用和 canonical 执行快照建立可审计定义身份。"""
    canonical_snapshot = _canonical_input_value(dict(snapshot))
    return DefinitionIdentity(
        version=int(version),
        definition_hash=sha256_canonical(canonical_snapshot),
        layer=str(layer),
        source_id=str(source_id),
        definition_ref={"kind": str(kind), "id": str(source_id)},
        definition_snapshot=canonical_snapshot,
    )


def _identity_payload(identity: DefinitionIdentity) -> tuple[dict[str, str], dict[str, Any]]:
    ref = dict(identity.definition_ref)
    if not ref:
        ref = {"kind": "legacy", "id": identity.source_id or "unknown"}
    snapshot = dict(identity.definition_snapshot)
    if not snapshot:
        raise ValueError("来源信封必须保存定义执行快照")
    if sha256_canonical(snapshot) != identity.definition_hash:
        raise ValueError("定义快照与 definition_hash 不一致")
    return ref, snapshot


def build_attempt(
    *,
    domain: ProvenanceDomain,
    identity: DefinitionIdentity,
    run_id: UUID,
    computed_at: datetime,
    computed_by: UUID | None,
    calc_version: str,
    inputs: list[InputAtom] | list[Mapping[str, Any]],
    calculated_value: Any | None,
    calculation_status: CalculationStatus,
    error_code: str | None = None,
    value_slot: ProvenanceValueSlot = "current",
    input_limit: int = 200,
) -> ProvenanceEnvelopeV1:
    """创建一次计算尝试；失败/跳过绝不伪装成成功数值。"""
    ref, snapshot = _identity_payload(identity)
    display, count, truncated, digest = input_summary(inputs, limit=input_limit)
    when = computed_at if computed_at.tzinfo is not None else computed_at.replace(tzinfo=timezone.utc)
    return ProvenanceEnvelopeV1(
        domain=domain,
        value_slot=value_slot,
        run_id=run_id,
        computed_at=when,
        computed_by=computed_by,
        calc_version=calc_version,
        definition_ref=ref,
        definition_version=identity.version,
        definition_hash=identity.definition_hash,
        definition_layer=identity.layer,
        definition_snapshot=snapshot,
        inputs=display,
        input_count=count,
        inputs_truncated=truncated,
        input_digest=digest,
        calculated_value=(None if calculated_value is None else _canonical_input_value(calculated_value)),
        calculation_status=calculation_status,
        error_code=error_code,
    )


def advance_final_value(
    existing: FinalValueProvenanceV1 | Mapping[str, Any] | None,
    *,
    value_slot: ProvenanceValueSlot,
    value_state: ProvenanceValueState,
    attempt: ProvenanceEnvelopeV1 | None,
    calculation_applied: bool,
) -> FinalValueProvenanceV1:
    """以新尝试更新最终值来源，未采用尝试保留旧 applied attempt。"""
    prior = (
        existing if isinstance(existing, FinalValueProvenanceV1)
        else FinalValueProvenanceV1.model_validate(existing) if existing else None
    )
    if attempt is not None and attempt.value_slot != value_slot:
        raise ValueError("计算尝试与最终值的 value_slot 不一致")
    if calculation_applied:
        if attempt is None or attempt.calculation_status != "succeeded":
            raise ValueError("只有成功的计算尝试可以成为最终值来源")
        applied = attempt
    else:
        applied = prior.applied_attempt if prior is not None else None
    return FinalValueProvenanceV1(
        value_slot=value_slot,
        value_state=value_state,
        calculation_applied=calculation_applied,
        applied_attempt=applied,
        last_calculation=attempt if attempt is not None else (prior.last_calculation if prior else None),
    )


def redact_inputs_for_projects(
    inputs: list[InputAtom], *, allowed_project_ids: set[UUID | str]
) -> tuple[list[InputAtom], bool]:
    """按当前读取者可见项目脱敏跨项目输入，不影响完整 digest。"""
    allowed = {str(project_id) for project_id in allowed_project_ids}
    result: list[InputAtom] = []
    redacted = False
    for atom in inputs:
        if atom.source_project_id is not None and str(atom.source_project_id) not in allowed:
            result.append(atom.model_copy(update={
                "key": _REDACTED_INPUT_KEY, "value": None, "source_ref": None,
            }))
            redacted = True
        else:
            result.append(atom)
    return result, redacted



def redact_final_provenance(
    raw: Any, *, allowed_project_ids: set[UUID | str],
) -> tuple[dict[str, Any] | None, bool, bool]:
    """校验最终值包装并按当前请求人的项目可见范围脱敏输入。"""
    if raw is None:
        return None, False, True
    legacy = False
    try:
        envelope = FinalValueProvenanceV1.model_validate(raw)
        payload = envelope.model_dump(mode="json")
    except Exception:  # 历史行或早期草稿：展示为 legacy，不伪造新来源语义。
        payload = dict(raw) if isinstance(raw, Mapping) else None
        return payload, False, True
    allowed = {str(project_id) for project_id in allowed_project_ids}
    redacted = False
    for attempt_key in ("applied_attempt", "last_calculation"):
        attempt = payload.get(attempt_key)
        if not isinstance(attempt, dict):
            continue
        for atom in attempt.get("inputs") or []:
            if not isinstance(atom, dict):
                continue
            source_project_id = atom.get("source_project_id")
            if source_project_id and str(source_project_id) not in allowed:
                atom["key"] = "（无权查看来源）"
                atom["value"] = None
                atom["source_ref"] = None
                atom["source_project_id"] = None
                redacted = True
    return payload, redacted, legacy
