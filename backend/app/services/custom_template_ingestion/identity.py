"""稳定身份载体解析与候选 instrumentation（Task 8）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 7.5, 8.2, 8.3

## 消费 G-ID，不复制其接口

本模块 **import** ``app.services.guidance_gid`` 的
``StableSheetIdentity`` / ``sheet_identity_from_authority`` 作为 sheet 稳定身份的
唯一权威来源；任何本地重定义 sheet identity schema 都是 conformance failure。

## design §7 稳定身份优先级

1. workbook 已有不可变业务 key / defined-name / custom metadata carrier；
2. 用户确认后，在**新 immutable instrumented candidate** 中写入平台
   metadata/defined-name carrier，并通过 reopen / package roundtrip /
   preservation diff；
3. 无法安全 instrument 时，动态区域不允许 editable projection（降级）。

Label、sheet order、row index **不是** carrier —— 本模块用结构性判据锁死
（``LABEL_LIKE_CARRIER_KINDS`` 不含 label/order/row-index，且 instrumentation
只接受可写回不可变 carrier）。
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

# G-ID 权威：sheet 稳定身份只从这里来。
from app.services.guidance_gid import (
    StableSheetIdentity,
    sheet_identity_from_authority,
)

__all__ = [
    "IdentityCarrierKind",
    "NON_CARRIER_SIGNALS",
    "CARRIER_KINDS",
    "INSTRUMENTABLE_CARRIER_KINDS",
    "StableFieldIdentity",
    "CarrierResolution",
    "InstrumentationError",
    "InstrumentedCandidate",
    "resolve_field_identity",
    "instrument_candidate",
    "can_support_editable_grid",
    "StableSheetIdentity",
    "sheet_identity_from_authority",
]


class IdentityCarrierKind(str, Enum):
    """载体种类。与 semantic_preflight.IdentityCarrierKind 语义一致，
    但此处再加入 ``PLATFORM_DEFINED_NAME`` 表示 instrumentation 写入的平台载体。"""

    DEFINED_NAME = "defined_name"
    CUSTOM_DOC_PROP = "custom_doc_prop"
    TABLE_COLUMN = "table_column"
    HIDDEN_META_CELL = "hidden_meta_cell"
    PLATFORM_DEFINED_NAME = "platform_defined_name"


#: 明确 **不是** 稳定身份载体的信号（design §7 末句）。resolve/instrument 见到
#: 这些一律拒绝，防止有人把 label / 行下标 / sheet 顺序当身份。
NON_CARRIER_SIGNALS: frozenset[str] = frozenset({
    "label",
    "display_name",
    "sheet_order",
    "row_index",
    "column_index",
    "array_index",
    "position",
})

#: 可作为已存在稳定载体的种类（不含平台后写入的种类，那属 instrumentation 产物）。
CARRIER_KINDS: frozenset[IdentityCarrierKind] = frozenset({
    IdentityCarrierKind.DEFINED_NAME,
    IdentityCarrierKind.CUSTOM_DOC_PROP,
    IdentityCarrierKind.TABLE_COLUMN,
    IdentityCarrierKind.HIDDEN_META_CELL,
    IdentityCarrierKind.PLATFORM_DEFINED_NAME,
})

#: 可由平台安全 instrument 写入的载体种类（可写回、不破坏既有语义、可 roundtrip）。
INSTRUMENTABLE_CARRIER_KINDS: frozenset[IdentityCarrierKind] = frozenset({
    IdentityCarrierKind.PLATFORM_DEFINED_NAME,
    IdentityCarrierKind.CUSTOM_DOC_PROP,
})


class InstrumentationError(ValueError):
    """instrumentation 不可安全完成（roundtrip/diff 失败或试图改原始物）。"""


@dataclass(frozen=True, slots=True)
class StableFieldIdentity:
    """字段/行/列稳定身份。绑定到 G-ID 的 sheet identity，不以 label/下标为 key。"""

    sheet: StableSheetIdentity
    carrier_kind: IdentityCarrierKind
    carrier_key: str
    locator: str
    #: True 表示身份来自平台在 instrumented candidate 里写入的载体，
    #: 而非 workbook 原生既有载体。
    instrumented: bool

    def __post_init__(self) -> None:
        folded = self.carrier_key.strip().casefold()
        if not folded:
            raise ValueError("carrier_key 不得为空")
        if folded in NON_CARRIER_SIGNALS:
            raise ValueError(
                f"{self.carrier_key!r} 是 label/下标类信号，不是稳定身份载体"
            )
        if self.carrier_kind not in CARRIER_KINDS:
            raise ValueError(f"未知载体种类: {self.carrier_kind}")

    @property
    def identity_key(self) -> str:
        return "|".join([
            self.sheet.catalog_key,
            self.carrier_kind.value,
            self.carrier_key,
        ])

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheet": self.sheet.to_dict(),
            "carrierKind": self.carrier_kind.value,
            "carrierKey": self.carrier_key,
            "locator": self.locator,
            "instrumented": self.instrumented,
            "identityKey": self.identity_key,
        }


@dataclass(frozen=True, slots=True)
class CarrierResolution:
    """一次身份解析结果：要么有稳定身份，要么给出降级理由。"""

    identity: StableFieldIdentity | None
    requires_instrumentation: bool
    downgrade_reason: str | None

    @property
    def resolved(self) -> bool:
        return self.identity is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolved": self.resolved,
            "identity": self.identity.to_dict() if self.identity else None,
            "requiresInstrumentation": self.requires_instrumentation,
            "downgradeReason": self.downgrade_reason,
        }


def resolve_field_identity(
    *,
    sheet: StableSheetIdentity,
    requested_carrier_kind: str,
    requested_carrier_key: str,
    existing_carrier_keys: Mapping[str, str],
) -> CarrierResolution:
    """按 design §7 优先级解析字段身份。

    参数:
      * ``existing_carrier_keys``：workbook 已观测到的既有稳定载体
        （carrier_key → locator），来自 semantic preflight 的 identity_carriers。

    返回 ``CarrierResolution``：
      * 命中既有载体 → 立即 resolved（instrumented=False）；
      * 载体种类可 instrument 但当前不存在 → requires_instrumentation=True，
        identity=None（调用方须先 ``instrument_candidate``）；
      * 既无既有载体又不可 instrument → downgrade（identity=None）。
    """
    key = (requested_carrier_key or "").strip()
    if not key or key.casefold() in NON_CARRIER_SIGNALS:
        return CarrierResolution(
            identity=None,
            requires_instrumentation=False,
            downgrade_reason="carrier_key_is_label_or_index",
        )
    try:
        kind = IdentityCarrierKind(requested_carrier_kind)
    except ValueError:
        return CarrierResolution(
            identity=None,
            requires_instrumentation=False,
            downgrade_reason="unknown_carrier_kind",
        )

    # 1) 优先既有载体
    locator = existing_carrier_keys.get(key)
    if locator is not None:
        return CarrierResolution(
            identity=StableFieldIdentity(
                sheet=sheet,
                carrier_kind=kind,
                carrier_key=key,
                locator=locator,
                instrumented=False,
            ),
            requires_instrumentation=False,
            downgrade_reason=None,
        )

    # 2) 无既有载体：仅当种类可 instrument 才允许后续写入
    if kind in INSTRUMENTABLE_CARRIER_KINDS:
        return CarrierResolution(
            identity=None,
            requires_instrumentation=True,
            downgrade_reason=None,
        )

    # 3) 无载体且不可 instrument → 降级
    return CarrierResolution(
        identity=None,
        requires_instrumentation=False,
        downgrade_reason="no_existing_carrier_and_not_instrumentable",
    )


@dataclass(frozen=True, slots=True)
class InstrumentedCandidate:
    """instrumentation 产物：新 immutable candidate revision + roundtrip 证据。

    绝不改动 quarantine original 或既有 candidate —— 通过携带**新** revision id
    与 **新** artifact digest 结构性保证（原 digest 一并保留供 diff 对照）。
    """

    base_candidate_revision: str
    new_candidate_revision: str
    base_artifact_sha256: str
    new_artifact_sha256: str
    identity: StableFieldIdentity
    reopen_ok: bool
    roundtrip_ok: bool
    preservation_diff_ok: bool

    def __post_init__(self) -> None:
        # 两条不变式各有唯一 owner，避免与 instrument_candidate 冗余（否则单点
        # 变异无法定位到具体 owner）：
        #   * revision 相等 —— 只在此校验（针对直接构造 / instrument 产物）；
        #   * digest 相等  —— 只在此校验（同上）。
        # instrument_candidate 另有「writer 未改字节」的 writer 语义校验，措辞不同、
        # 触发路径不同（noop writer），与本处不重叠。
        if self.new_candidate_revision == self.base_candidate_revision:
            raise InstrumentationError("instrumentation 必须创建新 candidate revision")
        if self.new_artifact_sha256 == self.base_artifact_sha256:
            raise InstrumentationError("instrumentation 必须改变 artifact digest")

    @property
    def verified(self) -> bool:
        return self.reopen_ok and self.roundtrip_ok and self.preservation_diff_ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseCandidateRevision": self.base_candidate_revision,
            "newCandidateRevision": self.new_candidate_revision,
            "baseArtifactSha256": self.base_artifact_sha256,
            "newArtifactSha256": self.new_artifact_sha256,
            "identity": self.identity.to_dict(),
            "reopenOk": self.reopen_ok,
            "roundtripOk": self.roundtrip_ok,
            "preservationDiffOk": self.preservation_diff_ok,
            "verified": self.verified,
        }


def instrument_candidate(
    *,
    sheet: StableSheetIdentity,
    base_candidate_revision: str,
    base_artifact_bytes: bytes,
    carrier_kind: str,
    carrier_key: str,
    writer: "CarrierWriter",
) -> InstrumentedCandidate:
    """在**新** immutable candidate 中写入平台载体，并做 reopen/roundtrip/diff。

    ``writer`` 是可注入的 carrier 写入器（生产由 openpyxl 实现，测试用
    in-memory fake）；本函数负责：
      * 拒绝不可 instrument 的种类；
      * 调用 writer 产出新字节（原字节保持不变，new digest 必不同）；
      * reopen 新字节确认 carrier 存在；
      * package roundtrip 确认可再次读出同 carrier；
      * preservation diff 确认除新增 carrier 外未破坏既有内容。
    """
    key = (carrier_key or "").strip()
    if not key or key.casefold() in NON_CARRIER_SIGNALS:
        raise InstrumentationError("carrier_key 是 label/下标类信号，不可 instrument")
    try:
        kind = IdentityCarrierKind(carrier_kind)
    except ValueError as exc:
        raise InstrumentationError(f"未知载体种类: {carrier_kind}") from exc
    if kind not in INSTRUMENTABLE_CARRIER_KINDS:
        raise InstrumentationError(f"载体种类不可 instrument: {kind.value}")

    result = writer.write_carrier(
        base_bytes=base_artifact_bytes,
        carrier_kind=kind,
        carrier_key=key,
    )
    base_sha = hashlib.sha256(base_artifact_bytes).hexdigest()
    new_sha = hashlib.sha256(result.new_bytes).hexdigest()
    # 「字节是否真变」的不变式单一 owner = InstrumentedCandidate.__post_init__ 的
    # digest 分支（见该处注释）；此处不再重复校验，避免冗余守卫让单点变异无法定位。
    identity = StableFieldIdentity(
        sheet=sheet,
        carrier_kind=kind,
        carrier_key=key,
        locator=result.locator,
        instrumented=True,
    )
    return InstrumentedCandidate(
        base_candidate_revision=base_candidate_revision,
        new_candidate_revision=f"{base_candidate_revision}+instr-{uuid.uuid4().hex[:8]}",
        base_artifact_sha256=base_sha,
        new_artifact_sha256=new_sha,
        identity=identity,
        reopen_ok=result.reopen_ok,
        roundtrip_ok=result.roundtrip_ok,
        preservation_diff_ok=result.preservation_diff_ok,
    )


@dataclass(frozen=True, slots=True)
class CarrierWriteResult:
    new_bytes: bytes
    locator: str
    reopen_ok: bool
    roundtrip_ok: bool
    preservation_diff_ok: bool


class CarrierWriter:
    """carrier 写入器 SPI。生产实现基于 openpyxl；测试可注入 fake。"""

    def write_carrier(
        self,
        *,
        base_bytes: bytes,
        carrier_kind: IdentityCarrierKind,
        carrier_key: str,
    ) -> CarrierWriteResult:  # pragma: no cover - 抽象
        raise NotImplementedError


def can_support_editable_grid(
    resolution: CarrierResolution,
    instrumented: InstrumentedCandidate | None,
) -> bool:
    """editable_grid 的身份前置：既有稳定载体，或已验证的 instrumented 载体。

    design §8 / Requirement 8.3：既无既有 carrier 又不能安全 instrument 时，
    动态区域不得选 editable_grid。
    """
    if resolution.resolved:
        return True
    if resolution.requires_instrumentation:
        return instrumented is not None and instrumented.verified
    return False
