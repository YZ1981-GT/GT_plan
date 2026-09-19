# -*- coding: utf-8 -*-
"""字段级冲突记录、人工裁决选择与 resolve fence（Task 14）。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` / Wave 1 Task 14
Requirements 6.6 / 6.7 / 6.8 / 6.9 / 7.4 / 8.1 / 8.5
Properties P24 / P25 / P26 / P27 / P32 / P35

本模块**只放声明式记录与纯判据**，不含三方规则本身（在 :mod:`merge`），也不含
ORM/session/router。依赖方向单一：``conflicts → definitions/models``，
``merge → conflicts``，绝无反向。

## 三条设计约束

1. **「字段缺失」与「字段被显式清空」是两种输入，落库也不许合并。**
   :class:`ValueEnvelope` 用 ``present`` 布尔把两者分开：``{"present": false}``
   与 ``{"present": true, "value": null}`` 是两个不同的 JSONB 值。若直接用 SQL
   NULL 表示「absent」，`base_value IS NULL` 就同时意味着「会话打开时没有这个字段」
   和「会话打开时这个字段是 null」—— 裁决界面无法区分，回滚也无从下手。

2. **每条拒绝/冲突原因都有自己可分辨的类型或文案。**
   Task 12/13 实测过的最贵一类假绿：两条拒绝路径抛同一异常类、文案又重叠，于是
   把其中一条短路掉之后另一条把它遮蔽 ⇒ 变异检验判 GREEN。因此
   :class:`FenceReason` 的每个成员都有独立文案，
   `TestResolveFence::test_every_reason_message_is_pairwise_distinct` 双向锁死。

3. **不重复实现已有真源。** duplicate→primary 的直指不变式复用
   :func:`app.services.workpaper_sync.models.assert_direct_primary`（Task 10），
   sequence 单调 fold 复用 :func:`~models.fold_effective_sequence`，canonical 字节
   复用 :func:`app.services.workpaper_sync.definitions.canonical_json_bytes`
   （Task 12）。本模块只负责**编排顺序**，不抄一份判据。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Iterator, Mapping, Sequence

from app.services.workpaper_sync.contracts import FieldMode, ValueType
from app.services.workpaper_sync.definitions import (
    canonical_digest,
    canonical_json_bytes,
    json_safe,
)
from app.services.workpaper_sync.models import (
    OperationScope,
    OperationShape,
    SyncDomainError,
    assert_direct_primary,
    classify_operation_shape,
    fold_effective_sequence,
    is_digest,
)

# ═══════════════════════════════════════════════════════════════════════════
# 0. 异常（逐条可分辨；禁止共用一个类型互相遮蔽）
# ═══════════════════════════════════════════════════════════════════════════


class MergeDomainError(SyncDomainError):
    """merge/conflict 域基类。"""

    error_code = "merge_domain_error"


class ConflictRecordError(MergeDomainError):
    """冲突记录本身不自洽（kind 与 protection/values/instances 矛盾）。"""

    error_code = "conflict_record_incoherent"


class ConflictSetIntegrityError(MergeDomainError):
    """冲突集违反 `UNIQUE(operation_id, stable_field_key, row_key, oo_location)`。"""

    error_code = "conflict_set_integrity_violation"


class UnresolvedConflictError(MergeDomainError):
    """存在未裁决冲突就要求产出 merged projection —— 域内**绝不**自动选边。

    🔴 这是 Property 26 的执行侧：同字段异值时不得应用任一侧。若把它降级成
    「默认取 incoming」，AC 4.6「不得自动选 incoming 或 current」立即失效。
    """

    error_code = "conflict_unresolved"


class ProtectedFieldOverrideError(MergeDomainError):
    """试图用 OO 值覆盖公式/auto-source/受保护单元格（AC 6.6「不得覆盖公式结果」）。"""

    error_code = "protected_field_override_forbidden"


class StructuralConflictNotAdjudicableError(MergeDomainError):
    """身份类结构冲突不能靠「选一侧」解决 —— 必须先修结构（fail closed）。

    与 :class:`ProtectedFieldOverrideError` 分成两类：前者是「值可选但公式不能被覆盖」，
    后者是「连值都还对不上（行身份重复/缺失）」。共用类型时短路任一条都会被另一条遮蔽。
    """

    error_code = "structural_conflict_not_adjudicable"


class InstanceSelectionRequiredError(MergeDomainError):
    """Word 同 tag 多实例异值时，`take_incoming` 必须指明取哪个实例（AC 7.4）。"""

    error_code = "word_instance_selection_required"


class UnknownConflictResolutionError(MergeDomainError):
    """裁决指向不存在的冲突（stale 冲突集或前端拼错 key）。"""

    error_code = "conflict_resolution_unknown_target"


class ResolveFenceError(MergeDomainError):
    """resolve fence 的输入不自洽（非判定结果 —— 判定走 :class:`FenceEvaluation`）。"""

    error_code = "resolve_fence_input_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 封闭枚举
# ═══════════════════════════════════════════════════════════════════════════


class ConflictKind(str, Enum):
    """冲突分类（design §`working_paper_sync_conflict` 的 `conflict_kind`）。

    取值必须与 V151 的 `ck_wpsc_conflict_kind` CHECK 逐字一致 ——
    `TestConflictRecordShape::test_kinds_match_the_database_check_constraint`
    直接从迁移 SQL 解析比对，多一个少一个都打红。
    """

    #: 同字段异值：base=A / current=B / incoming=C。
    value = "value"
    #: 受保护字段被 OO 改动（公式 / auto-source / formula_mask 覆盖的单元格）。
    protected = "protected"
    #: 一侧删除、另一侧更新同一 row identity。
    delete_update = "delete_update"
    #: 结构/身份/类型异常（行 UUID 空或重复、identity 载体缺失、类型规范化失败……）。
    schema = "schema"
    #: Word 同一 stable tag 的多个实例值不一致（AC 7.4）。
    duplicate_word_instance = "duplicate_word_instance"


class SchemaAnomalyKind(str, Enum):
    """`schema` 冲突的具体成因。封闭枚举 —— extract 侧只能报这些形态。

    `adjudicable_by_value_choice` 把两类分开：类型规范化失败与「同 key 多位置异值」
    可以由人选一个值收敛（design §Extract「类型转换失败保留原值供裁决」）；行身份类
    异常必须先修结构，选一侧毫无意义（AC 6.15 的 fail-closed 侧）。
    """

    type_normalization_failure = "type_normalization_failure"
    multi_location_divergence = "multi_location_divergence"
    empty_row_identity = "empty_row_identity"
    duplicate_row_identity = "duplicate_row_identity"
    missing_identity_carrier = "missing_identity_carrier"
    unknown_stable_key = "unknown_stable_key"
    reused_tombstoned_row_identity = "reused_tombstoned_row_identity"

    @property
    def adjudicable_by_value_choice(self) -> bool:
        return self in _VALUE_ADJUDICABLE_ANOMALIES


_VALUE_ADJUDICABLE_ANOMALIES: Final[frozenset[SchemaAnomalyKind]] = frozenset(
    {
        SchemaAnomalyKind.type_normalization_failure,
        SchemaAnomalyKind.multi_location_divergence,
    }
)


class FieldSource(str, Enum):
    """字段来源（AC 8.1「字段来源」）。由 contract 的 mode + document_type 派生。"""

    onlyoffice_cell = "onlyoffice_cell"
    onlyoffice_sdt = "onlyoffice_sdt"
    server_formula = "server_formula"
    auto_data_source = "auto_data_source"
    word_free_text = "word_free_text"


class ProtectionPolicy(str, Enum):
    """保护策略（AC 8.1「保护策略」）。三类只读来源分开登记，便于文案与统计。"""

    editable = "editable"
    read_only_formula = "read_only_formula"
    read_only_auto_source = "read_only_auto_source"
    read_only_masked_cell = "read_only_masked_cell"
    word_only = "word_only"

    @property
    def is_protected(self) -> bool:
        return self is not ProtectionPolicy.editable and self is not ProtectionPolicy.word_only


class SuggestedAction(str, Enum):
    """建议动作（AC 8.1「建议动作」）。只是建议 —— 域内不会据此自动选边。"""

    keep_current = "keep_current"
    take_incoming = "take_incoming"
    manual_merge = "manual_merge"
    pick_instance = "pick_instance"
    fix_structure = "fix_structure"


class ResolutionKind(str, Enum):
    """人工裁决动作（AC 8.3）。"""

    keep_current = "keep_current"
    take_incoming = "take_incoming"
    #: 文本字段输入合并值（也可用 `present=False` 表达「合并为删除」）。
    manual = "manual"
    #: Word 多实例：显式取某个 XPath 实例的值。
    take_instance = "take_instance"


class FenceDecision(str, Enum):
    """resolve fence 判定（AC 8.5 / design §冲突解决）。"""

    #: 全部 fence 一致，可按用户选择产出 merged projection。
    proceed = "proceed"
    #: 同一 canonical application 因更高 request sequence 发生 effective-sequence fold：
    #: 规范化到最新 effective sequence 后**继续同一 conflict set**，不得判自己 stale。
    fold = "fold"
    #: fence/sequence 未变但 current revision 已变：以 frozen base 对最新 current 重跑
    #: 三方 merge，返回 409 `CONFLICT_REBASED`。
    rebase = "rebase"
    #: room latest durable 指向**另一个** canonical application 且 effective sequence 更高。
    superseded = "superseded"
    #: 授权/generation/write fence/冲突集身份变化 —— 拒绝，不产生副作用。
    rejected = "rejected"


class FenceReason(str, Enum):
    """判定原因。每个成员有独立文案，禁止互相遮蔽。"""

    ok = "ok"
    same_application_sequence_fold = "same_application_sequence_fold"
    canonical_application_mismatch = "canonical_application_mismatch"
    room_generation_changed = "room_generation_changed"
    write_fence_changed = "write_fence_changed"
    permission_epoch_changed = "permission_epoch_changed"
    client_edit_epoch_changed = "client_edit_epoch_changed"
    room_refresh_required = "room_refresh_required"
    newer_canonical_application = "newer_canonical_application"
    conflict_set_changed = "conflict_set_changed"
    current_revision_changed = "current_revision_changed"
    requested_duplicate_link_invalid = "requested_duplicate_link_invalid"


#: 每个 reason 的用户可见中文文案。**逐条不同** —— 合并文案会让「哪条判据在起作用」
#: 不可分辨，短路其中一条时另一条会把它遮蔽（Task 12/13 实测的 GREEN 成因）。
FENCE_REASON_MESSAGES: Final[Mapping[FenceReason, str]] = {
    FenceReason.ok: "全部乐观锁一致，可提交裁决",
    FenceReason.same_application_sequence_fold: (
        "同一 canonical application 命中更高 request sequence，已规范化到最新 "
        "effective sequence 并继续同一冲突集（不判 stale、不 supersede 自己）"
    ),
    FenceReason.canonical_application_mismatch: (
        "请求携带的 canonical application 与服务端锁定的 application 不一致，"
        "必须先按 requested operation 重新 canonicalize"
    ),
    FenceReason.room_generation_changed: "room generation 已轮转，需重开编辑器确认新基线后再裁决",
    FenceReason.write_fence_changed: "room write fence epoch 已提升（有 participant 被撤销或超时）",
    FenceReason.permission_epoch_changed: "发起人权限 epoch 已变化，原授权不再有效",
    FenceReason.client_edit_epoch_changed: "客户端编辑轮次已变化，冲突预览基于过期快照",
    FenceReason.room_refresh_required: (
        "room 处于 refresh-required：上次 merged 结果与 incoming 不等值，"
        "必须重载编辑器确认新基线后才能继续"
    ),
    FenceReason.newer_canonical_application: (
        "room latest durable 已指向另一个更新的 canonical application，"
        "本冲突集被 supersede，请对最新 operation 重建裁决"
    ),
    FenceReason.conflict_set_changed: "冲突集摘要与服务端重算结果不一致，冲突列表已变更",
    FenceReason.current_revision_changed: (
        "服务端 content revision 已推进，需以 frozen base 对最新 current 重跑三方 merge"
        "（CONFLICT_REBASED）"
    ),
    FenceReason.requested_duplicate_link_invalid: (
        "requested operation 是 terminal duplicate 但其 direct-primary 不变式不成立，"
        "禁止 canonicalize"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# 2. 值信封：absent 与 present-but-null 永不折叠
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ValueEnvelope:
    """一个三方值的可落库形态。

    ``present=False`` = 该 stable key 在这一侧的 projection 里**不存在**（行未创建 /
    行已删除 / 字段尚未出现）；``present=True, value=None`` = 该字段存在但被显式清空。
    两者的 JSONB 表示不同，因此 `base_value` 落库后仍可区分。
    """

    present: bool
    value: Any = None

    def __post_init__(self) -> None:
        if not self.present and self.value is not None:
            raise ConflictRecordError(
                f"ValueEnvelope(present=False) 不得携带值 {self.value!r} —— "
                "「字段不存在」没有值可言；「存在但为空」应写 present=True, value=None"
            )

    @classmethod
    def absent(cls) -> "ValueEnvelope":
        return _ABSENT

    @classmethod
    def of(cls, value: Any) -> "ValueEnvelope":
        return cls(present=True, value=value)

    def to_jsonb(self) -> dict[str, Any]:
        """落库形态。**绝不**把 absent 压成 SQL NULL —— 那会与 present-but-null 撞。

        🔴 值必须过 `json_safe`（Task 26 在真库上实测抓到的 P0）：`amount` 字段的值是
        `Decimal`、`date` 字段是 `date`，二者都不是 JSON 可序列化类型。少了这一步，
        任何金额/日期字段的同字段异值冲突在算 `ConflictSet.digest`（AC 8.5 的
        `conflict_set_digest`）时直接
        `TypeError: Object of type Decimal is not JSON serializable` ——
        整条冲突路径崩溃，而 D2 应收账款的冲突几乎全是金额字段。
        JSONB 列（`base_value`/`current_value`/`incoming_value`）同样受益于这一步。
        """
        if not self.present:
            return {"present": False}
        return {"present": True, "value": json_safe(self.value)}

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_jsonb())


_ABSENT: Final[ValueEnvelope] = ValueEnvelope(present=False)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 定位器与冲突记录
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class WordInstanceRef:
    """Word 同 tag 的一个实例（AC 7.4「列出全部 OO 位置」）。"""

    xpath: str
    value: ValueEnvelope

    def __post_init__(self) -> None:
        if not self.xpath.strip():
            raise ConflictRecordError("WordInstanceRef.xpath 不得为空 —— 实例位置必须可追溯")


@dataclass(frozen=True)
class FieldLocator:
    """一个**已实例化**受管字段的双侧定位（AC 8.1 / 8.2）。

    「已实例化」= 行域字段的 ``{row_uuid}`` 已被具体行身份替换，因此
    `stable_field_key` / `json_pointer` / `oo_location` 都是可直接下钻的终值。
    """

    stable_field_key: str
    business_label: str
    json_pointer: str
    oo_location: str
    field_source: FieldSource
    protection_policy: ProtectionPolicy
    value_type: ValueType
    mode: FieldMode
    row_key: str = ""
    sheet_key: str | None = None
    table_key: str | None = None

    def __post_init__(self) -> None:
        # 与 V151 的 ck_wpsc_* CHECK 对称：这三条落库前就必须成立，否则 insert 才炸。
        if not self.stable_field_key.strip():
            raise ConflictRecordError("stable_field_key 不得为空")
        if not self.business_label.strip():
            raise ConflictRecordError(
                f"{self.stable_field_key}: business_label 不得为空 —— "
                "冲突预览必须能告诉审计师这是哪一项（AC 8.1）"
            )
        if self.json_pointer != "" and not self.json_pointer.startswith("/"):
            raise ConflictRecordError(
                f"{self.stable_field_key}: json_pointer 必须以 `/` 开头或为空串，"
                f"实得 {self.json_pointer!r}"
            )
        if not self.oo_location.strip():
            raise ConflictRecordError(
                f"{self.stable_field_key}: oo_location 不得为空 —— "
                "AC 8.2 要求冲突可追溯到 OO 单元格 / SDT 地址"
            )

    @property
    def is_protected(self) -> bool:
        return self.protection_policy.is_protected

    @property
    def dedupe_key(self) -> tuple[str, str, str]:
        """与 `uq_wpsc_field UNIQUE(operation_id, stable_field_key, row_key, oo_location)` 同构。"""
        return (self.stable_field_key, self.row_key, self.oo_location)


@dataclass(frozen=True)
class ConflictRecord:
    """一条字段级冲突（AC 8.1 的九个要素齐备）。

    字段与 `working_paper_sync_conflict` 一一对应；:meth:`to_row` 是唯一的落库投影，
    `TestConflictRecordShape::test_row_covers_every_ac81_column` 拿 ORM 列名反查覆盖。
    """

    locator: FieldLocator
    kind: ConflictKind
    base: ValueEnvelope
    current: ValueEnvelope
    incoming: ValueEnvelope
    suggested_action: SuggestedAction
    reason: str
    schema_anomaly: SchemaAnomalyKind | None = None
    word_instances: tuple[WordInstanceRef, ...] = ()

    def __post_init__(self) -> None:
        if len(self.reason.strip()) < 8:
            raise ConflictRecordError(
                f"{self.locator.stable_field_key}: reason 过短 —— 每条冲突必须给出"
                "可分辨的原因文案，否则「为什么冲突」不可追溯"
            )
        if self.kind is ConflictKind.protected:
            if not self.locator.is_protected:
                raise ConflictRecordError(
                    f"{self.locator.stable_field_key}: protected 冲突的 protection_policy "
                    f"却是 {self.locator.protection_policy.value} —— 记录自相矛盾"
                )
            if self.suggested_action is not SuggestedAction.keep_current:
                raise ConflictRecordError(
                    f"{self.locator.stable_field_key}: protected 冲突的建议动作只能是 "
                    "keep_current（AC 6.6「不得覆盖公式结果」）"
                )
        if self.kind is ConflictKind.schema:
            if self.schema_anomaly is None:
                raise ConflictRecordError(
                    f"{self.locator.stable_field_key}: schema 冲突必须给出 schema_anomaly，"
                    "否则「结构哪里坏了」不可诊断（AC 5.12）"
                )
        elif self.schema_anomaly is not None:
            raise ConflictRecordError(
                f"{self.locator.stable_field_key}: 只有 schema 冲突才可携带 schema_anomaly，"
                f"实得 kind={self.kind.value}"
            )
        if self.kind is ConflictKind.duplicate_word_instance:
            if len(self.word_instances) < 2:
                raise ConflictRecordError(
                    f"{self.locator.stable_field_key}: duplicate_word_instance 必须列出 ≥2 个"
                    f"实例位置（AC 7.4），实得 {len(self.word_instances)}"
                )
            payloads = {ref.value.canonical_bytes for ref in self.word_instances}
            if len(payloads) < 2:
                raise ConflictRecordError(
                    f"{self.locator.stable_field_key}: 全部实例值相同却报 "
                    "duplicate_word_instance —— 值一致时应合并为一个字段（AC 7.4 前半句）"
                )
        elif self.word_instances:
            raise ConflictRecordError(
                f"{self.locator.stable_field_key}: 只有 duplicate_word_instance 才可携带 "
                f"word_instances，实得 kind={self.kind.value}"
            )
        if self.kind is ConflictKind.delete_update and not (
            (self.current.present is False) ^ (self.incoming.present is False)
        ):
            raise ConflictRecordError(
                f"{self.locator.stable_field_key}: delete_update 要求 current/incoming 中"
                "**恰好一侧**缺失（一侧删、一侧改）"
                f"，实得 current.present={self.current.present} "
                f"incoming.present={self.incoming.present}"
            )

    # ── 派生 ──────────────────────────────────────────────────────────
    @property
    def dedupe_key(self) -> tuple[str, str, str]:
        return self.locator.dedupe_key

    @property
    def adjudicable_by_value_choice(self) -> bool:
        """能否靠「选一侧 / 输入合并值」收敛。"""
        if self.kind is ConflictKind.schema:
            assert self.schema_anomaly is not None  # __post_init__ 已保证
            return self.schema_anomaly.adjudicable_by_value_choice
        return True

    def digest_payload(self) -> dict[str, Any]:
        """进 conflict_set_digest 的 canonical 片段（含三值 —— 值变了摘要就变）。"""
        payload: dict[str, Any] = {
            "stable_field_key": self.locator.stable_field_key,
            "row_key": self.locator.row_key,
            "oo_location": self.locator.oo_location,
            "json_pointer": self.locator.json_pointer,
            "kind": self.kind.value,
            "protection_policy": self.locator.protection_policy.value,
            "base": self.base.to_jsonb(),
            "current": self.current.to_jsonb(),
            "incoming": self.incoming.to_jsonb(),
        }
        if self.schema_anomaly is not None:
            payload["schema_anomaly"] = self.schema_anomaly.value
        if self.word_instances:
            payload["word_instances"] = [
                {"xpath": ref.xpath, "value": ref.value.to_jsonb()}
                for ref in sorted(self.word_instances, key=lambda r: r.xpath)
            ]
        return payload

    def to_row(self) -> dict[str, Any]:
        """`working_paper_sync_conflict` 的列投影（不含 operation/fence 侧列）。"""
        return {
            "stable_field_key": self.locator.stable_field_key,
            "business_label": self.locator.business_label,
            "sheet_key": self.locator.sheet_key,
            "table_key": self.locator.table_key,
            "row_key": self.locator.row_key,
            "json_pointer": self.locator.json_pointer,
            "oo_location": self.locator.oo_location,
            "field_source": self.locator.field_source.value,
            "protection_policy": self.locator.protection_policy.value,
            "suggested_action": self.suggested_action.value,
            "conflict_kind": self.kind.value,
            "base_value": self.base.to_jsonb(),
            "current_value": self.current.to_jsonb(),
            "incoming_value": self.incoming.to_jsonb(),
        }


#: `conflict_set_digest` 的 schema 标记。摘要算法变化必须换版本，
#: 否则旧 operation 的 digest 会与新算法的重算结果对不上而被误判 stale。
CONFLICT_SET_DIGEST_SCHEMA: Final[str] = "gt.sync.conflict_set:v1"


def _sort_key(record: ConflictRecord) -> tuple[str, str, str, str, str]:
    loc = record.locator
    return (loc.sheet_key or "", loc.table_key or "", loc.row_key, loc.stable_field_key, loc.oo_location)


@dataclass(frozen=True)
class ConflictSet:
    """一次 merge 产出的冲突集合。顺序确定、摘要确定、dedupe key 唯一。"""

    records: tuple[ConflictRecord, ...] = ()

    def __post_init__(self) -> None:
        seen: dict[tuple[str, str, str], ConflictRecord] = {}
        for record in self.records:
            key = record.dedupe_key
            if key in seen:
                raise ConflictSetIntegrityError(
                    f"同一 (stable_field_key, row_key, oo_location)={key} 出现两条冲突 —— "
                    "会撞 `uq_wpsc_field`，重复 callback 不得生成重复冲突"
                )
            seen[key] = record
        object.__setattr__(self, "records", tuple(sorted(self.records, key=_sort_key)))

    def __iter__(self) -> Iterator[ConflictRecord]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def __bool__(self) -> bool:
        return bool(self.records)

    @property
    def digest(self) -> str:
        """AC 8.5 的 `conflict_set_digest`。空集也有稳定摘要（不是空串）。"""
        return canonical_digest(
            {
                "schema": CONFLICT_SET_DIGEST_SCHEMA,
                "conflicts": [record.digest_payload() for record in self.records],
            }
        )

    def of_kind(self, kind: ConflictKind) -> tuple[ConflictRecord, ...]:
        return tuple(record for record in self.records if record.kind is kind)

    def by_key(self) -> Mapping[tuple[str, str, str], ConflictRecord]:
        return {record.dedupe_key: record for record in self.records}

    def grouped(self) -> Mapping[tuple[str, str, str], tuple[ConflictRecord, ...]]:
        """按 sheet / table / row 分组（AC 8.2 的冲突预览分组）。"""
        out: dict[tuple[str, str, str], list[ConflictRecord]] = {}
        for record in self.records:
            key = (
                record.locator.sheet_key or "",
                record.locator.table_key or "",
                record.locator.row_key,
            )
            out.setdefault(key, []).append(record)
        return {key: tuple(value) for key, value in sorted(out.items())}


# ═══════════════════════════════════════════════════════════════════════════
# 4. 人工裁决选择
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ResolutionChoice:
    """一条人工裁决（AC 8.3）。dedupe key 与冲突记录同构，逐项对齐。"""

    stable_field_key: str
    kind: ResolutionKind
    row_key: str = ""
    oo_location: str = ""
    manual: ValueEnvelope | None = None
    instance_xpath: str | None = None

    def __post_init__(self) -> None:
        if self.kind is ResolutionKind.manual and self.manual is None:
            raise ConflictRecordError(
                f"{self.stable_field_key}: kind=manual 必须给 manual 值信封"
                "（`present=False` 表示合并为删除）"
            )
        if self.kind is not ResolutionKind.manual and self.manual is not None:
            raise ConflictRecordError(
                f"{self.stable_field_key}: 只有 kind=manual 才可携带 manual 值"
            )
        if self.kind is ResolutionKind.take_instance and not (self.instance_xpath or "").strip():
            raise ConflictRecordError(
                f"{self.stable_field_key}: kind=take_instance 必须给 instance_xpath（AC 7.4）"
            )
        if self.kind is not ResolutionKind.take_instance and self.instance_xpath is not None:
            raise ConflictRecordError(
                f"{self.stable_field_key}: 只有 kind=take_instance 才可携带 instance_xpath"
            )

    @property
    def dedupe_key(self) -> tuple[str, str, str]:
        return (self.stable_field_key, self.row_key, self.oo_location)

    def to_jsonb(self) -> dict[str, Any]:
        """落 `resolution` 列的审计投影（AC 8.6 记录「选择结果」）。"""
        payload: dict[str, Any] = {"kind": self.kind.value}
        if self.manual is not None:
            payload["manual"] = self.manual.to_jsonb()
        if self.instance_xpath is not None:
            payload["instance_xpath"] = self.instance_xpath
        return payload


def resolved_value_for(
    record: ConflictRecord, choice: ResolutionChoice
) -> ValueEnvelope:
    """把一条裁决落成具体值 —— **唯一**的选择求值入口。

    四条禁令各有独立异常类型，互不遮蔽：

    * 受保护字段不得取 incoming / 输入 manual（AC 6.6「不得覆盖公式结果」）
      → :class:`ProtectedFieldOverrideError`
    * 身份类结构冲突不得靠选边收敛（AC 6.15 fail closed）
      → :class:`StructuralConflictNotAdjudicableError`
    * Word 多实例的 `take_incoming` 必须指明实例（AC 7.4）
      → :class:`InstanceSelectionRequiredError`
    * `take_instance` 的 XPath 必须真实存在
      → :class:`UnknownConflictResolutionError`
    """
    if not record.adjudicable_by_value_choice:
        raise StructuralConflictNotAdjudicableError(
            f"{record.locator.stable_field_key}: {record.schema_anomaly.value if record.schema_anomaly else '?'}"
            " 属身份类结构冲突，必须先修正结构（重建行身份 / 恢复 identity 载体）；"
            "选 current 或 incoming 都会把错误结构固化下来"
        )
    if record.locator.is_protected and choice.kind is not ResolutionKind.keep_current:
        raise ProtectedFieldOverrideError(
            f"{record.locator.stable_field_key}: 该字段的保护策略是 "
            f"{record.locator.protection_policy.value}，只允许 keep_current；"
            f"kind={choice.kind.value} 会用 OO 值覆盖公式/auto-source 结果"
            "（AC 6.6 明令禁止，需要改的是 contract 不是单条裁决）"
        )
    if (
        record.kind is ConflictKind.duplicate_word_instance
        and choice.kind is ResolutionKind.take_incoming
    ):
        raise InstanceSelectionRequiredError(
            f"{record.locator.stable_field_key}: 同 tag 有 "
            f"{len(record.word_instances)} 个实例且值不一致，take_incoming 无法确定取哪个；"
            "请改用 take_instance 并指明 XPath，或用 manual 输入合并值（AC 7.4）"
        )
    if choice.kind is ResolutionKind.keep_current:
        return record.current
    if choice.kind is ResolutionKind.take_incoming:
        return record.incoming
    if choice.kind is ResolutionKind.manual:
        assert choice.manual is not None  # __post_init__ 已保证
        return choice.manual
    for ref in record.word_instances:
        if ref.xpath == choice.instance_xpath:
            return ref.value
    raise UnknownConflictResolutionError(
        f"{record.locator.stable_field_key}: take_instance 指定的 XPath "
        f"{choice.instance_xpath!r} 不在实例清单 "
        f"{[ref.xpath for ref in record.word_instances]} 内"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5. resolve fence（AC 8.5）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ResolveFenceRequest:
    """resolve 请求携带的乐观锁 —— AC 8.5 点名的八项一个不少。"""

    expected_current_revision: int
    room_generation: int
    client_edit_epoch: int
    canonical_application_id: uuid.UUID
    application_effective_request_sequence: int
    room_latest_durable_application_id: uuid.UUID | None
    room_latest_durable_sequence: int
    conflict_set_digest: str

    def __post_init__(self) -> None:
        if not is_digest(self.conflict_set_digest):
            raise ResolveFenceError(
                f"conflict_set_digest 必须是 64 位小写 hex 且非全零，"
                f"实得 {self.conflict_set_digest!r}"
            )
        for name in (
            "expected_current_revision",
            "room_generation",
            "client_edit_epoch",
            "application_effective_request_sequence",
            "room_latest_durable_sequence",
        ):
            if getattr(self, name) < 0:
                raise ResolveFenceError(f"{name} 不得为负: {getattr(self, name)}")


@dataclass(frozen=True)
class FrozenApplicationFence:
    """canonical application / frozen request 侧的不可变身份（服务端在 lock 内读出）。"""

    canonical_application_id: uuid.UUID
    effective_request_sequence: int
    write_fence_epoch: int
    initiator_permission_epoch: int
    client_edit_epoch: int


@dataclass(frozen=True)
class RoomDurableFence:
    """room 在同一 wp/room lock 内的当前真值。"""

    generation: int
    write_fence_epoch: int
    initiator_permission_epoch: int
    state_is_refresh_required: bool
    latest_durable_application_id: uuid.UUID | None
    latest_durable_sequence: int
    current_revision: int
    conflict_set_digest: str


@dataclass(frozen=True)
class RequestedOperationLink:
    """requested operation 与其 direct primary（仅当 requested 是 terminal duplicate 时给）。"""

    requested: OperationScope
    primary: OperationScope


@dataclass(frozen=True)
class FenceEvaluation:
    """fence 判定结果。**返回**而不是抛异常 —— router 需要按 decision 映射 409/422。"""

    decision: FenceDecision
    reason: FenceReason
    canonical_application_id: uuid.UUID
    normalized_effective_request_sequence: int
    detail: str = ""

    @property
    def message(self) -> str:
        base = FENCE_REASON_MESSAGES[self.reason]
        return f"{base}（{self.detail}）" if self.detail else base

    @property
    def may_apply(self) -> bool:
        """能否继续产出 merged projection。只有 proceed/fold 可以。"""
        return self.decision in (FenceDecision.proceed, FenceDecision.fold)


def evaluate_resolve_fence(
    *,
    request: ResolveFenceRequest,
    application: FrozenApplicationFence,
    room: RoomDurableFence,
    duplicate_link: RequestedOperationLink | None = None,
) -> FenceEvaluation:
    """AC 8.5 / design §冲突解决的**不可交换顺序**，逐步返回可分辨的 reason。

    顺序（每一步都有自己的 reason，不许合并）::

        0. requested 是 terminal duplicate ⇒ 先验 direct-primary 不变式再 canonicalize
        1. 请求的 canonical application 必须等于服务端锁定的 application
        2. room generation / write fence / permission epoch / client edit epoch
        3. room refresh-required
        4. canonical application identity ↔ room latest durable
           4a. 同一 application ⇒ 规范化 effective sequence 后继续（fold，不判 stale）
           4b. 另一 application 且 effective sequence 更高 ⇒ superseded
        5. conflict_set_digest
        6. current revision ⇒ rebase

    🔴 第 4a 步是「不得 self-supersede」的落点：同一 canonical application 因更高
    request sequence 只做单调 fold（复用 :func:`~models.fold_effective_sequence`），
    绝不把自己判 stale，也绝不形成 duplicate→primary→stale 循环。
    """
    if duplicate_link is not None:
        shape = classify_operation_shape(
            application_id=duplicate_link.requested.application_id,
            duplicate_of_operation_id=duplicate_link.requested.duplicate_of_operation_id,
            state=duplicate_link.requested.state,
        )
        if shape is not OperationShape.duplicate:
            raise ResolveFenceError(
                f"duplicate_link 只应在 requested operation 是 terminal duplicate 时传入，"
                f"实得 shape={shape.value}"
            )
        try:
            # 🔴 复用 Task 10 的唯一真源，不在本模块抄一份直指判据。
            assert_direct_primary(
                loser=duplicate_link.requested,
                target=duplicate_link.primary,
                application_id=application.canonical_application_id,
            )
        except SyncDomainError as exc:
            return FenceEvaluation(
                decision=FenceDecision.rejected,
                reason=FenceReason.requested_duplicate_link_invalid,
                canonical_application_id=application.canonical_application_id,
                normalized_effective_request_sequence=application.effective_request_sequence,
                detail=str(exc),
            )

    def _reject(reason: FenceReason, detail: str) -> FenceEvaluation:
        return FenceEvaluation(
            decision=FenceDecision.rejected,
            reason=reason,
            canonical_application_id=application.canonical_application_id,
            normalized_effective_request_sequence=application.effective_request_sequence,
            detail=detail,
        )

    if request.canonical_application_id != application.canonical_application_id:
        return _reject(
            FenceReason.canonical_application_mismatch,
            f"请求 {request.canonical_application_id} ≠ 服务端 "
            f"{application.canonical_application_id}",
        )
    if request.room_generation != room.generation:
        return _reject(
            FenceReason.room_generation_changed,
            f"请求 generation={request.room_generation}，room={room.generation}",
        )
    if application.write_fence_epoch != room.write_fence_epoch:
        return _reject(
            FenceReason.write_fence_changed,
            f"frozen fence={application.write_fence_epoch}，room={room.write_fence_epoch}",
        )
    if application.initiator_permission_epoch != room.initiator_permission_epoch:
        return _reject(
            FenceReason.permission_epoch_changed,
            f"frozen epoch={application.initiator_permission_epoch}，"
            f"当前={room.initiator_permission_epoch}",
        )
    if request.client_edit_epoch != application.client_edit_epoch:
        return _reject(
            FenceReason.client_edit_epoch_changed,
            f"请求 epoch={request.client_edit_epoch}，application "
            f"frozen={application.client_edit_epoch}",
        )
    if room.state_is_refresh_required:
        return _reject(FenceReason.room_refresh_required, "room.state=refresh_required")

    same_canonical = (
        room.latest_durable_application_id == application.canonical_application_id
    )
    normalized = application.effective_request_sequence
    folded = False
    if same_canonical:
        normalized = fold_effective_sequence(
            application.effective_request_sequence,
            request.application_effective_request_sequence,
        )
        folded = normalized != request.application_effective_request_sequence
    elif (
        room.latest_durable_application_id is not None
        and room.latest_durable_sequence > application.effective_request_sequence
    ):
        return FenceEvaluation(
            decision=FenceDecision.superseded,
            reason=FenceReason.newer_canonical_application,
            canonical_application_id=application.canonical_application_id,
            normalized_effective_request_sequence=application.effective_request_sequence,
            detail=(
                f"room latest durable={room.latest_durable_application_id} "
                f"(seq={room.latest_durable_sequence}) ≠ 本 application "
                f"{application.canonical_application_id} "
                f"(seq={application.effective_request_sequence})"
            ),
        )

    if request.conflict_set_digest != room.conflict_set_digest:
        return _reject(
            FenceReason.conflict_set_changed,
            f"请求 {request.conflict_set_digest[:12]}… ≠ 重算 {room.conflict_set_digest[:12]}…",
        )
    if request.expected_current_revision != room.current_revision:
        return FenceEvaluation(
            decision=FenceDecision.rebase,
            reason=FenceReason.current_revision_changed,
            canonical_application_id=application.canonical_application_id,
            normalized_effective_request_sequence=normalized,
            detail=(
                f"expected={request.expected_current_revision}，"
                f"实际={room.current_revision}"
            ),
        )
    if folded:
        return FenceEvaluation(
            decision=FenceDecision.fold,
            reason=FenceReason.same_application_sequence_fold,
            canonical_application_id=application.canonical_application_id,
            normalized_effective_request_sequence=normalized,
            detail=(
                f"请求 seq={request.application_effective_request_sequence} → 规范化 "
                f"seq={normalized}"
            ),
        )
    return FenceEvaluation(
        decision=FenceDecision.proceed,
        reason=FenceReason.ok,
        canonical_application_id=application.canonical_application_id,
        normalized_effective_request_sequence=normalized,
    )


def assert_all_conflicts_resolved(
    conflicts: ConflictSet, choices: Sequence[ResolutionChoice]
) -> Mapping[tuple[str, str, str], ResolutionChoice]:
    """逐项对齐冲突与裁决 —— 少一条、多一条、重复一条都拒。

    🔴 「同字段冲突不自动选边」的执行侧：缺裁决时抛
    :class:`UnresolvedConflictError`，**不**回落到任何一侧。
    """
    by_key: dict[tuple[str, str, str], ResolutionChoice] = {}
    for choice in choices:
        if choice.dedupe_key in by_key:
            raise UnknownConflictResolutionError(
                f"裁决重复指向同一冲突 {choice.dedupe_key} —— 批量选择必须去重"
            )
        by_key[choice.dedupe_key] = choice

    expected = set(conflicts.by_key())
    provided = set(by_key)
    missing = sorted(expected - provided)
    if missing:
        raise UnresolvedConflictError(
            f"{len(missing)} 条冲突未裁决: {missing[:5]}"
            f"{'…' if len(missing) > 5 else ''} —— 域内绝不自动选 current 或 incoming"
            "（AC 4.6 / Property 26）"
        )
    unknown = sorted(provided - expected)
    if unknown:
        raise UnknownConflictResolutionError(
            f"{len(unknown)} 条裁决指向不存在的冲突: {unknown[:5]}"
            f"{'…' if len(unknown) > 5 else ''} —— 冲突集可能已被 supersede/rebase"
        )
    return by_key


__all__ = [
    # 异常
    "MergeDomainError", "ConflictRecordError", "ConflictSetIntegrityError",
    "UnresolvedConflictError", "ProtectedFieldOverrideError",
    "StructuralConflictNotAdjudicableError", "InstanceSelectionRequiredError",
    "UnknownConflictResolutionError", "ResolveFenceError",
    # 枚举
    "ConflictKind", "SchemaAnomalyKind", "FieldSource", "ProtectionPolicy",
    "SuggestedAction", "ResolutionKind", "FenceDecision", "FenceReason",
    "FENCE_REASON_MESSAGES", "CONFLICT_SET_DIGEST_SCHEMA",
    # 记录
    "ValueEnvelope", "WordInstanceRef", "FieldLocator", "ConflictRecord", "ConflictSet",
    "ResolutionChoice", "resolved_value_for", "assert_all_conflicts_resolved",
    # fence
    "ResolveFenceRequest", "FrozenApplicationFence", "RoomDurableFence",
    "RequestedOperationLink", "FenceEvaluation", "evaluate_resolve_fence",
]
