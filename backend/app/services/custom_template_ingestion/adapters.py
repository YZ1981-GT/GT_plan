"""CustomWorkbookAdapter SPI 与字段级实现（Task 8）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 8.4, 8.5, 8.6, 8.8

## design §8 adapter SPI

```
extract(bytes, manifest)              -> ProjectionSnapshot
validate(mutations, base)             -> ValidationResult
apply(staging, mutations, manifest)   -> ApplyResult
diff(before, after, manifest)         -> PreservationDiff
rebase(base, current, incoming)       -> RebaseResult
merge(base, current, incoming, manifest) -> MergeResult
```

adapter 声明 managed / unmanaged 边界与 formula boundary（哪些字段可被 Grid 编辑、
哪些 OOXML part 只保留不投影）。

本文件提供:
  * ``CustomWorkbookAdapter`` Protocol（editable_grid 的契约）；
  * ``FieldLevelWorkbookAdapter`` 一个不依赖 openpyxl 的确定性实现，用「字段→typed
    value」的内容模型演示 managed 合并 / unmanaged 保留 / 同字段冲突可见 /
    三方 merge 不同字段自动合并；
  * ``DeterministicExtractor`` —— read_only_html 只需 extractor 的最小实现。

字段级 three-way merge 语义（Requirement 14.1/14.2 的 adapter 基座，Task 15 复用）:
  * base→current 与 base→incoming 改动不同 managed field → 自动合并；
  * 双方改同一 field 为不同 typed value → typed conflict（禁止整文件 LWW）；
  * unmanaged parts 通过 preservation diff 保留。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from app.services.custom_template_ingestion.mapping import (
    CustomProjectionManifest,
    ProjectionMode,
)

__all__ = [
    "ImmutableBytes",
    "ManagedMutation",
    "ProjectionSnapshot",
    "ValidationResult",
    "ApplyResult",
    "PreservationDiff",
    "FieldConflict",
    "RebaseResult",
    "MergeResult",
    "CustomWorkbookAdapter",
    "FieldLevelWorkbookAdapter",
    "DeterministicExtractor",
    "decode_workbook_model",
    "encode_workbook_model",
]


# ─────────────────────────────────────────────────────────────────────────────
# 内容模型（不依赖 openpyxl；演示与测试用确定性 JSON 编码）
# ─────────────────────────────────────────────────────────────────────────────
#
# workbook bytes 在本实现里是 UTF-8 JSON：
#   {"managed": {field_id: typed_value}, "unmanaged": {part: value}}
# 生产 adapter 会以 openpyxl staging workbook 替换编解码，但 SPI 语义一致。


def decode_workbook_model(payload: bytes) -> dict[str, dict[str, Any]]:
    try:
        obj = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"managed": {}, "unmanaged": {}}
    managed = dict(obj.get("managed") or {})
    unmanaged = dict(obj.get("unmanaged") or {})
    return {"managed": managed, "unmanaged": unmanaged}


def encode_workbook_model(model: Mapping[str, Mapping[str, Any]]) -> bytes:
    payload = json.dumps(
        {
            "managed": dict(model.get("managed") or {}),
            "unmanaged": dict(model.get("unmanaged") or {}),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return payload.encode("utf-8")


ImmutableBytes = bytes


@dataclass(frozen=True, slots=True)
class ManagedMutation:
    field_id: str
    value: Any
    value_type: str

    def to_dict(self) -> dict[str, Any]:
        return {"fieldId": self.field_id, "value": self.value, "valueType": self.value_type}


@dataclass(frozen=True, slots=True)
class ProjectionSnapshot:
    sheet_uid: str
    managed_values: Mapping[str, Any]
    unmanaged_parts: tuple[str, ...]
    source_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheetUid": self.sheet_uid,
            "managedValues": dict(self.managed_values),
            "unmanagedParts": list(self.unmanaged_parts),
            "sourceDigest": self.source_digest,
        }


@dataclass(frozen=True, slots=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": list(self.errors)}


@dataclass(frozen=True, slots=True)
class ApplyResult:
    ok: bool
    new_bytes: bytes | None
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "newDigest": hashlib.sha256(self.new_bytes).hexdigest() if self.new_bytes else None,
            "errors": list(self.errors),
        }


@dataclass(frozen=True, slots=True)
class PreservationDiff:
    preserved_unmanaged: tuple[str, ...]
    lost_unmanaged: tuple[str, ...]
    changed_managed: tuple[str, ...]

    @property
    def unmanaged_preserved(self) -> bool:
        return not self.lost_unmanaged

    def to_dict(self) -> dict[str, Any]:
        return {
            "preservedUnmanaged": list(self.preserved_unmanaged),
            "lostUnmanaged": list(self.lost_unmanaged),
            "changedManaged": list(self.changed_managed),
            "unmanagedPreserved": self.unmanaged_preserved,
        }


@dataclass(frozen=True, slots=True)
class FieldConflict:
    field_id: str
    base_value: Any
    current_value: Any
    incoming_value: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "fieldId": self.field_id,
            "baseValue": self.base_value,
            "currentValue": self.current_value,
            "incomingValue": self.incoming_value,
        }


@dataclass(frozen=True, slots=True)
class RebaseResult:
    ok: bool
    rebased: tuple[ManagedMutation, ...]
    conflicts: tuple[FieldConflict, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "rebased": [m.to_dict() for m in self.rebased],
            "conflicts": [c.to_dict() for c in self.conflicts],
        }


@dataclass(frozen=True, slots=True)
class MergeResult:
    ok: bool
    merged_bytes: bytes | None
    conflicts: tuple[FieldConflict, ...]
    preservation: PreservationDiff

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mergedDigest": hashlib.sha256(self.merged_bytes).hexdigest() if self.merged_bytes else None,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "preservation": self.preservation.to_dict(),
        }


@runtime_checkable
class CustomWorkbookAdapter(Protocol):
    """editable_grid 的六方法 SPI（design §8）。"""

    adapter_id: str
    adapter_version: str

    def extract(self, data: ImmutableBytes, manifest: CustomProjectionManifest) -> ProjectionSnapshot: ...
    def validate(self, mutations: tuple[ManagedMutation, ...], base: ProjectionSnapshot) -> ValidationResult: ...
    def apply(self, staging: bytes, mutations: tuple[ManagedMutation, ...], manifest: CustomProjectionManifest) -> ApplyResult: ...
    def diff(self, before: ImmutableBytes, after: ImmutableBytes, manifest: CustomProjectionManifest) -> PreservationDiff: ...
    def rebase(self, base: ImmutableBytes, current: ImmutableBytes, incoming: tuple[ManagedMutation, ...]) -> RebaseResult: ...
    def merge(self, base: ImmutableBytes, current: ImmutableBytes, incoming: ImmutableBytes, manifest: CustomProjectionManifest) -> MergeResult: ...


class DeterministicExtractor:
    """read_only_html 最小实现：只 extract，无 mutation endpoint。"""

    def extract(self, data: ImmutableBytes, manifest: CustomProjectionManifest) -> ProjectionSnapshot:
        model = decode_workbook_model(data)
        managed = model["managed"]
        # read_only：投影所有非空值为只读视图，但不暴露 managed mutation。
        return ProjectionSnapshot(
            sheet_uid=manifest.sheet_uid,
            managed_values=dict(managed),
            unmanaged_parts=tuple(sorted(model["unmanaged"])),
            source_digest=hashlib.sha256(data).hexdigest(),
        )


class FieldLevelWorkbookAdapter:
    """确定性字段级 adapter，实现全部六个 SPI 方法。

    managed boundary = manifest 的 managed_field_ids；只有这些字段可被 mutation
    写入。unmanaged parts 一律保留。
    """

    def __init__(self, *, adapter_id: str, adapter_version: str) -> None:
        self.adapter_id = adapter_id
        self.adapter_version = adapter_version

    # ── extract ──
    def extract(self, data: ImmutableBytes, manifest: CustomProjectionManifest) -> ProjectionSnapshot:
        model = decode_workbook_model(data)
        managed_ids = manifest.managed_field_ids
        managed = {k: v for k, v in model["managed"].items() if k in managed_ids}
        return ProjectionSnapshot(
            sheet_uid=manifest.sheet_uid,
            managed_values=managed,
            unmanaged_parts=tuple(sorted(model["unmanaged"])),
            source_digest=hashlib.sha256(data).hexdigest(),
        )

    # ── validate ──
    def validate(
        self,
        mutations: tuple[ManagedMutation, ...],
        base: ProjectionSnapshot,
    ) -> ValidationResult:
        errors: list[str] = []
        managed_keys = set(base.managed_values)
        for mut in mutations:
            if mut.field_id not in managed_keys:
                errors.append(f"unmanaged_or_unknown_field:{mut.field_id}")
            if not _type_matches(mut.value, mut.value_type):
                errors.append(f"type_mismatch:{mut.field_id}:{mut.value_type}")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    # ── apply ──
    def apply(
        self,
        staging: bytes,
        mutations: tuple[ManagedMutation, ...],
        manifest: CustomProjectionManifest,
    ) -> ApplyResult:
        model = decode_workbook_model(staging)
        managed_ids = manifest.managed_field_ids
        errors: list[str] = []
        new_managed = dict(model["managed"])
        for mut in mutations:
            if mut.field_id not in managed_ids:
                errors.append(f"apply_rejects_unmanaged:{mut.field_id}")
                continue
            new_managed[mut.field_id] = mut.value
        if errors:
            return ApplyResult(ok=False, new_bytes=None, errors=tuple(errors))
        new_bytes = encode_workbook_model({
            "managed": new_managed,
            "unmanaged": model["unmanaged"],  # unmanaged 原样保留
        })
        return ApplyResult(ok=True, new_bytes=new_bytes, errors=())

    # ── diff ──
    def diff(
        self,
        before: ImmutableBytes,
        after: ImmutableBytes,
        manifest: CustomProjectionManifest,
    ) -> PreservationDiff:
        b = decode_workbook_model(before)
        a = decode_workbook_model(after)
        before_unmanaged = set(b["unmanaged"])
        after_unmanaged = set(a["unmanaged"])
        preserved = sorted(
            k for k in before_unmanaged & after_unmanaged
            if b["unmanaged"][k] == a["unmanaged"][k]
        )
        lost = sorted(
            k for k in before_unmanaged
            if k not in after_unmanaged or a["unmanaged"].get(k) != b["unmanaged"][k]
        )
        changed = sorted(
            k for k in set(b["managed"]) | set(a["managed"])
            if b["managed"].get(k) != a["managed"].get(k)
        )
        return PreservationDiff(
            preserved_unmanaged=tuple(preserved),
            lost_unmanaged=tuple(lost),
            changed_managed=tuple(changed),
        )

    # ── rebase ──
    def rebase(
        self,
        base: ImmutableBytes,
        current: ImmutableBytes,
        incoming: tuple[ManagedMutation, ...],
    ) -> RebaseResult:
        base_m = decode_workbook_model(base)["managed"]
        curr_m = decode_workbook_model(current)["managed"]
        rebased: list[ManagedMutation] = []
        conflicts: list[FieldConflict] = []
        for mut in incoming:
            base_val = base_m.get(mut.field_id)
            curr_val = curr_m.get(mut.field_id)
            if curr_val != base_val and curr_val != mut.value:
                # current 也动了同字段且与 incoming 不同 → conflict
                conflicts.append(FieldConflict(
                    field_id=mut.field_id,
                    base_value=base_val,
                    current_value=curr_val,
                    incoming_value=mut.value,
                ))
            else:
                rebased.append(mut)
        return RebaseResult(ok=not conflicts, rebased=tuple(rebased), conflicts=tuple(conflicts))

    # ── merge (three-way, field level) ──
    def merge(
        self,
        base: ImmutableBytes,
        current: ImmutableBytes,
        incoming: ImmutableBytes,
        manifest: CustomProjectionManifest,
    ) -> MergeResult:
        base_model = decode_workbook_model(base)
        curr_model = decode_workbook_model(current)
        inc_model = decode_workbook_model(incoming)
        managed_ids = manifest.managed_field_ids

        base_m = base_model["managed"]
        curr_m = curr_model["managed"]
        inc_m = inc_model["managed"]

        merged: dict[str, Any] = dict(base_m)
        conflicts: list[FieldConflict] = []

        all_fields = (set(base_m) | set(curr_m) | set(inc_m)) & managed_ids
        for fid in sorted(all_fields):
            b = base_m.get(fid)
            c = curr_m.get(fid)
            i = inc_m.get(fid)
            curr_changed = c != b
            inc_changed = i != b
            if curr_changed and inc_changed and c != i:
                # 同字段不同 typed value → 冲突（禁止 LWW）
                conflicts.append(FieldConflict(fid, b, c, i))
                merged[fid] = c  # 保留 current 值待人工裁决，不静默覆盖
            elif inc_changed:
                merged[fid] = i
            elif curr_changed:
                merged[fid] = c
            else:
                merged[fid] = b

        # unmanaged：合并双方，冲突则保留 current，但记入 preservation diff。
        merged_unmanaged: dict[str, Any] = dict(base_model["unmanaged"])
        merged_unmanaged.update(inc_model["unmanaged"])
        merged_unmanaged.update(curr_model["unmanaged"])

        merged_bytes = encode_workbook_model({
            "managed": merged,
            "unmanaged": merged_unmanaged,
        })
        preservation = self.diff(base, merged_bytes, manifest)
        return MergeResult(
            ok=not conflicts,
            merged_bytes=merged_bytes if not conflicts else None,
            conflicts=tuple(conflicts),
            preservation=preservation,
        )


def _type_matches(value: Any, value_type: str) -> bool:
    if value_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if value_type == "string":
        return isinstance(value, str)
    if value_type == "bool":
        return isinstance(value, bool)
    if value_type == "formula":
        return isinstance(value, str) and value.startswith("=")
    if value_type == "date":
        return isinstance(value, str)
    return False
