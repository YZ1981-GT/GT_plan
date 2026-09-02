# -*- coding: utf-8 -*-
"""immutable definition/bundle store：发布 DAG、bundle canonicalizer、typed null marker
registry 与 alias。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 12
Requirements: 2.3, 6.2, 6.10, 9.1, 9.8, 9.11
Properties: P28 / P7

═══ 一、发布 DAG 为什么必须是**代码里的偏序**而不是文档约定 ═══

design 明文固定 `template → instrumentation → contract → bundle → representation`。
只写在文档里的话，唯一后果是「谁先写谁定」：instrumentation 里塞一个
`contract_definition_sha256` 在语法上完全合法，DB 也存得下，直到某天 contract 改版
后旧 instrumentation 的 digest 跟着漂移，历史 operation 的 identity 就跟着变。

所以本模块把 DAG 落成两条可执行判据：

1. :func:`assert_publish_order` —— 阶段偏序（前置阶段必须已 approved）；
2. **payload 级反向引用禁令** —— :func:`validate_instrumentation_payload` 拒绝任何
   `contract_*` / `bundle_*` / `definition_bundle_*` 键（Requirement 6.14 的
   「instrumentation payload 不得反向引用 contract 或 bundle digest」）。

只有第 1 条时，反向引用可以「先发 contract、再发引用它的 instrumentation」绕过；
只有第 2 条时，可以「contract 引用一个还没 approved 的 template digest」绕过。
两条都要。

═══ 二、canonical payload 为什么禁止内嵌自身 UUID/hash ═══

Requirement 6.2 / 6.14：contract/instrumentation 的 canonical payload 是**跨环境可
复现**的语义快照，digest 由 payload 算出。若 payload 里再写自己的 artifact UUID 或
sha256，就成了自引用：换个环境重算 digest 必然不同，「同一语义 → 同一 digest」这条
前提直接崩掉，历史 operation 也无法按 digest 复核。

═══ 三、bundle canonicalizer 的 fail-closed 反例清单 ═══

:func:`build_bundle_canonical_payload` 对下列输入**在 canonicalization 之前**拒绝，
绝不把它们编码进 canonical bytes：

======  ==========================================  =========================
反例    形态                                        判据
======  ==========================================  =========================
FC-1    slot 整个键缺失                             slot omission
FC-2    slot 值为 Python ``None``（SQL NULL）        null slot
FC-3    slot 值为 JSON ``null``                     null slot
FC-4    type/ref/digest 任一为空串或纯空白           empty slot field
FC-5    digest 为 64 个 0                            all-zero digest
FC-6    digest 非 64 位小写 hex                      malformed digest
FC-7    marker type 不在 registry                    unregistered marker
FC-8    marker 用了别的 slot 的 marker                cross-slot marker
FC-9    marker digest ≠ registry 真实 digest          marker digest mismatch
FC-10   ``definition`` ref 不是 ``definition:<uuid>``  malformed definition ref
FC-11   child kind/state/digest 与 slot 声明不符      child mismatch（DB 侧二次锁）
FC-12   ``projection_contract`` 任一 slot 用 marker    marker 冒充 contract
FC-13   authority model digest 空/全零                 invalid authority digest
FC-14   authority model 枚举未登记                     unknown authority model
======  ==========================================  =========================

FC-2/FC-3 必须分开：`None` 来自 SQL NULL（ORM 读出来就是 None），JSON `null` 来自
人写的 JSON 文件。两条走同一 `is None` 判据即可覆盖，但守卫必须**两个用例都测** ——
只测一条时把另一条的入口删掉不会红。
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleIntegrityError,
    BundleSlot,
    BundleSlotSpec,
    DefinitionKind,
    DefinitionState,
    IdentityError,
    SyncDomainError,
    is_digest,
    validate_bundle_slot,
    validate_bundle_slots,
)

# ═══════════════════════════════════════════════════════════════════════════
# 0. canonical 序列化（跨 Python/TypeScript 可复现）
# ═══════════════════════════════════════════════════════════════════════════

_ALL_ZERO_DIGEST: Final[str] = "0" * 64


def json_safe(value: Any) -> Any:
    """把业务值转成 JSON 可序列化形态（**只影响表示，不改业务值**）。

    `Decimal` / `date` / `datetime` 是 projection 与冲突三值里的**合法**值类型，
    但 JSON 没有它们。转成字符串而不是 `float`：`float(Decimal("0.1"))` 会引入二进制
    误差，让同一金额在两次序列化里算出不同 digest。

    🔴 为什么放在这里（Task 26 追加）：本函数原先只存在于 `content_mutation._json_safe`，
    于是 `conflicts.ValueEnvelope.to_jsonb()` 没有它 —— 任何 `amount` / `date` 字段的
    同字段异值冲突在算 `conflict_set_digest` 时直接
    `TypeError: Object of type Decimal is not JSON serializable`
    （Task 26 在真库上实测到：D2 应收账款的行金额冲突整条路径崩溃）。
    修在最底层（与 :func:`canonical_json_bytes` 同一模块）才能让所有 canonical 序列化
    共用**一份**口径；`content_mutation._json_safe` 现在委派本函数。
    """
    if isinstance(value, Decimal):
        # `format(v, "f")` 而不是 `str(v)`：后者对 `Decimal("1E+2")` 给出 `'1E+2'`，
        # 于是同一金额的两种十进制表示会算出两个 digest。
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in sorted(value.items())}
    return value


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    """canonical JSON bytes：UTF-8、递归键排序、无多余空白、禁 NaN/Infinity。

    `separators=(",", ":")` + `sort_keys=True` + `ensure_ascii=False` 三者合起来让
    「同一语义 → 同一字节」在 Python 与 TypeScript 之间可复现（TS 侧
    `JSON.stringify` 配合递归排序即等价）。`allow_nan=False` 是必须的：NaN 在 JSON
    里不合法，放过去会让两侧序列化结果不同。
    """
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_digest(payload: Mapping[str, Any]) -> str:
    """canonical payload 的 SHA-256（小写 hex）。"""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 1. 发布 DAG
# ═══════════════════════════════════════════════════════════════════════════


class PublishStage(str, Enum):
    """发布 DAG 的阶段。顺序即偏序（design §Data Model / Requirement 6.2）。"""

    template = "template"
    instrumentation = "instrumentation"
    contract = "contract"
    bundle = "bundle"
    representation = "representation"


#: `template → instrumentation → contract → bundle → representation`
PUBLISH_DAG: Final[tuple[PublishStage, ...]] = (
    PublishStage.template,
    PublishStage.instrumentation,
    PublishStage.contract,
    PublishStage.bundle,
    PublishStage.representation,
)

#: 每个阶段的直接前置（authority_model 是 bundle 的必填 child，但**不在**这条链上：
#: 它独立先行批准，故不作为 instrumentation/contract 的前置）。
PUBLISH_PREREQUISITES: Final[Mapping[PublishStage, tuple[PublishStage, ...]]] = {
    PublishStage.template: (),
    PublishStage.instrumentation: (PublishStage.template,),
    PublishStage.contract: (PublishStage.template, PublishStage.instrumentation),
    PublishStage.bundle: (
        PublishStage.template,
        PublishStage.instrumentation,
        PublishStage.contract,
    ),
    PublishStage.representation: (PublishStage.bundle,),
}


class PublishOrderError(SyncDomainError):
    """发布 DAG 被破坏（前置阶段未 approved，或出现反向引用）。"""

    error_code = "publish_dag_violation"


def stage_index(stage: PublishStage | str) -> int:
    st = stage if isinstance(stage, PublishStage) else PublishStage(stage)
    return PUBLISH_DAG.index(st)


def assert_publish_order(
    *, stage: PublishStage | str, approved_stages: set[PublishStage] | set[str]
) -> None:
    """断言 `stage` 的全部直接前置都已 approved，否则 :class:`PublishOrderError`。

    对 `projection_contract` 语义：bundle 的三个前置都必须真实 approved。
    `custom_authoritative_ooxml / opaque_single_onlyoffice` 用 typed null marker 时，
    对应前置由 :func:`build_bundle_canonical_payload` 的 marker 分支放行 ——
    故本函数只接受调用方传入的 `approved_stages`，不自己推断 authority model。
    """
    st = stage if isinstance(stage, PublishStage) else PublishStage(stage)
    approved = {
        s if isinstance(s, PublishStage) else PublishStage(s) for s in approved_stages
    }
    missing = [p.value for p in PUBLISH_PREREQUISITES[st] if p not in approved]
    if missing:
        raise PublishOrderError(
            f"发布 DAG 违规：{st.value} 的前置阶段 {missing} 尚未 approved"
            f"（固定顺序 {' → '.join(s.value for s in PUBLISH_DAG)}）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. typed null marker registry（版本化）
# ═══════════════════════════════════════════════════════════════════════════

#: marker canonical payload schema。**必须与 V151 seed 的字节形态逐字一致**，
#: 否则 DB trigger 解析出的 digest 与本模块算的不同 ⇒ 所有 marker bundle fail。
MARKER_SCHEMA_VERSION: Final[str] = "definition-bundle-marker:v1"


def marker_canonical_payload(slot: BundleSlot | str) -> dict[str, str]:
    s = slot.value if isinstance(slot, BundleSlot) else str(slot)
    return {"schema_version": MARKER_SCHEMA_VERSION, "slot": s, "value": "none"}


def marker_digest(slot: BundleSlot | str) -> str:
    """typed null marker 的真实 digest。

    🔴 与 `test_task10_repository_pg._marker_sha` / V151 seed 同源：
    `{"schema_version":"definition-bundle-marker:v1","slot":"<slot>","value":"none"}`
    的 UTF-8 SHA-256。此处用 :func:`canonical_json_bytes` 生成，键顺序恰为
    `schema_version < slot < value`（字典序），与手写字面量一致。
    """
    return canonical_digest(marker_canonical_payload(slot))


@dataclass(frozen=True)
class TypedNullMarker:
    """registry 中一个版本化 typed null marker。"""

    slot: BundleSlot
    version: int
    slot_type: str
    slot_ref: str
    slot_digest: str


def _build_marker_registry() -> dict[str, TypedNullMarker]:
    out: dict[str, TypedNullMarker] = {}
    # v1：三个可选 child 各一个 marker。`template` 也登记 marker 是为了
    # `opaque_single_onlyoffice`（用户上传的 opaque 文件没有平台模板）。
    for slot in BundleSlot:
        slot_type = f"{slot.value}:none:v1"
        out[slot_type] = TypedNullMarker(
            slot=slot,
            version=1,
            slot_type=slot_type,
            slot_ref=f"marker:{slot_type}",
            slot_digest=marker_digest(slot),
        )
    return out


#: `slot_type` → marker。registry 是 marker 的**唯一**来源；
#: 未登记的 `xxx:none:vN` 一律拒绝（FC-7）。
TYPED_NULL_MARKERS: Final[dict[str, TypedNullMarker]] = _build_marker_registry()


def marker_for(slot: BundleSlot | str, *, version: int = 1) -> TypedNullMarker:
    s = slot if isinstance(slot, BundleSlot) else BundleSlot(slot)
    key = f"{s.value}:none:v{version}"
    marker = TYPED_NULL_MARKERS.get(key)
    if marker is None:
        raise BundleIntegrityError(f"typed null marker 未登记: {key!r}")
    return marker


def marker_slot_spec(slot: BundleSlot | str, *, version: int = 1) -> BundleSlotSpec:
    m = marker_for(slot, version=version)
    return BundleSlotSpec(m.slot, m.slot_type, m.slot_ref, m.slot_digest)


def definition_slot_spec(
    slot: BundleSlot | str, *, definition_id: uuid.UUID, definition_sha256: str
) -> BundleSlotSpec:
    s = slot if isinstance(slot, BundleSlot) else BundleSlot(slot)
    return BundleSlotSpec(s, "definition", f"definition:{definition_id}", definition_sha256)


# ═══════════════════════════════════════════════════════════════════════════
# 3. payload 校验（发布器入口；反向引用禁令在此）
# ═══════════════════════════════════════════════════════════════════════════

#: canonical payload 里**禁止**出现的自引用键（Requirement 6.2 / 6.14）。
_SELF_REFERENCE_KEYS: Final[frozenset[str]] = frozenset({
    "definition_artifact_id", "definition_sha256", "artifact_id", "artifact_uuid",
    "id", "sha256", "self_sha256", "own_digest",
})

#: instrumentation payload 里**禁止**出现的反向引用键前缀。
_BACKWARD_REFERENCE_PREFIXES: Final[tuple[str, ...]] = (
    "contract_", "definition_bundle_", "bundle_",
)


def _walk_keys(payload: Any, prefix: str = "") -> list[str]:
    """递归收集全部键的点路径（用于自引用/反向引用检测）。"""
    out: list[str] = []
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            out.append(str(k))
            out.extend(_walk_keys(v, path))
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            out.extend(_walk_keys(item, prefix))
    return out


def _assert_no_self_reference(kind: DefinitionKind, payload: Mapping[str, Any]) -> None:
    hit = sorted(set(_walk_keys(payload)) & _SELF_REFERENCE_KEYS)
    if hit:
        raise IdentityError(
            f"{kind.value} canonical payload 不得内嵌自身 artifact UUID/hash，"
            f"实得键 {hit}（Requirement 6.2：digest 由 payload 算出，自引用会破坏可复现性）"
        )


def validate_template_payload(payload: Mapping[str, Any]) -> None:
    """template definition payload：只要求 schema_version + template_sha256。"""
    _require_schema_version(payload, "template-definition")
    _assert_no_self_reference(DefinitionKind.template, payload)
    if not is_digest(payload.get("template_sha256")):
        raise IdentityError(
            "template payload 必须含非空非全零 `template_sha256`（模板 blob 的内容身份）"
        )


def validate_instrumentation_payload(payload: Mapping[str, Any]) -> None:
    """instrumentation payload：单向引用 template digest，**禁止**反向引用 contract/bundle。"""
    _require_schema_version(payload, "instrumentation-definition")
    _assert_no_self_reference(DefinitionKind.instrumentation, payload)
    if not is_digest(payload.get("template_definition_sha256")):
        raise IdentityError(
            "instrumentation payload 必须单向引用已发布 template 的 "
            "`template_definition_sha256`"
        )
    keys = set(_walk_keys(payload))
    backward = sorted(
        k for k in keys if k.startswith(_BACKWARD_REFERENCE_PREFIXES)
    )
    if backward:
        raise PublishOrderError(
            "instrumentation payload 出现反向引用键 "
            f"{backward} —— 发布 DAG 固定为 template → instrumentation → contract → "
            "bundle → representation，instrumentation 不得引用 contract/bundle digest"
        )


def validate_contract_payload(payload: Mapping[str, Any]) -> None:
    """contract payload：单向引用 template + instrumentation digests，禁止引用 bundle。"""
    _require_schema_version(payload, "contract-definition")
    _assert_no_self_reference(DefinitionKind.contract, payload)
    for field in ("template_definition_sha256", "instrumentation_definition_sha256"):
        if not is_digest(payload.get(field)):
            raise IdentityError(
                f"contract payload 必须单向引用已发布 definition 的 `{field}`"
            )
    keys = set(_walk_keys(payload))
    forward = sorted(k for k in keys if k.startswith(("definition_bundle_", "bundle_")))
    if forward:
        raise PublishOrderError(
            f"contract payload 出现前向引用键 {forward} —— contract 在 bundle 之前发布，"
            "不得引用尚不存在的 bundle digest"
        )


def validate_authority_model_payload(payload: Mapping[str, Any]) -> AuthorityModel:
    """authority model payload：封闭枚举 + schema_version；返回枚举值。"""
    _require_schema_version(payload, "authority-model-definition")
    _assert_no_self_reference(DefinitionKind.authority_model, payload)
    raw = payload.get("authority_model")
    try:
        return AuthorityModel(raw)
    except (ValueError, TypeError) as exc:
        raise BundleIntegrityError(
            f"authority_model 必须是封闭枚举 "
            f"{sorted(m.value for m in AuthorityModel)}，实得 {raw!r}"
        ) from exc


def _require_schema_version(payload: Mapping[str, Any], expected_prefix: str) -> None:
    sv = payload.get("schema_version")
    if not isinstance(sv, str) or not sv.strip():
        raise IdentityError(f"canonical payload 缺 `schema_version`（期望 {expected_prefix}:vN）")
    if not sv.startswith(f"{expected_prefix}:"):
        raise IdentityError(
            f"canonical payload 的 schema_version={sv!r} 与 kind 不符"
            f"（期望以 {expected_prefix}: 开头）"
        )


PAYLOAD_VALIDATORS: Final[dict[DefinitionKind, Any]] = {
    DefinitionKind.template: validate_template_payload,
    DefinitionKind.instrumentation: validate_instrumentation_payload,
    DefinitionKind.contract: validate_contract_payload,
    DefinitionKind.authority_model: validate_authority_model_payload,
}


def validate_definition_payload(
    kind: DefinitionKind | str, payload: Mapping[str, Any]
) -> None:
    k = kind if isinstance(kind, DefinitionKind) else DefinitionKind(kind)
    PAYLOAD_VALIDATORS[k](payload)


# ═══════════════════════════════════════════════════════════════════════════
# 4. bundle canonicalizer（FC-1 ~ FC-14）
# ═══════════════════════════════════════════════════════════════════════════

BUNDLE_SCHEMA_VERSION: Final[str] = "definition-bundle:v1"

def _normalize_slot_input(slot: BundleSlot, raw: Any) -> BundleSlotSpec:
    """把外部输入（dict / BundleSlotSpec / None）归一成 spec，非法即拒（FC-2~FC-10）。

    🔴 **形态判据委托 `models.validate_bundle_slot`，本函数不重写一份**（2026-08-25
    变异检验实测的教训）：改造前这里自带 `is_digest` 与 `_DEFINITION_REF_RE` 两份
    副本，与 `models.validate_bundle_slot` 完全重合。后果是把任一侧的检查短路掉都
    **不改变行为** ⇒ 变异检验判 GREEN，「digest 形态」「definition ref 形态」这两条
    判据实际上没有任何单点可锁。

    本函数只保留 models 拿不到的三类判据：
    * **原始输入形态**（None / 缺键 / 值为 NULL / 非 dict）—— models 收的是已构造好的
      `BundleSlotSpec`，看不到「键根本没出现」；
    * **全零 digest 的专属诊断** —— models 的消息把空串/全零/非小写合成一句，
      而 FC-5 要求错误能定位到「忘了算 hash 就填 0」这个**伪身份**成因，
      故这一条刻意保留两层，守卫按「伪身份」字样断言本层真的在起作用；
    * **marker registry 一致性** —— registry 由本模块持有。
    """
    if raw is None:
        raise BundleIntegrityError(
            f"{slot.value} slot 为 NULL —— SQL NULL 与 JSON null 都不得进入 canonical bytes；"
            f"可选 child 必须使用 registry 版本化 typed null marker"
        )
    if isinstance(raw, BundleSlotSpec):
        spec = raw
    elif isinstance(raw, Mapping):
        for key in ("type", "ref", "digest"):
            if key not in raw:
                raise BundleIntegrityError(
                    f"{slot.value} slot 缺字段 {key!r}（slot omission）"
                )
            if raw[key] is None:
                raise BundleIntegrityError(
                    f"{slot.value} slot 字段 {key!r} 为 NULL（不得进入 canonical bytes）"
                )
        spec = BundleSlotSpec(
            slot, str(raw["type"]).strip(), str(raw["ref"]).strip(), str(raw["digest"]).strip()
        )
    else:
        raise BundleIntegrityError(
            f"{slot.value} slot 类型非法: {type(raw).__name__}（需 dict 或 BundleSlotSpec）"
        )

    # slot 键一致性与「type/ref 空串」判据同样在 models 单点，不复制。
    if str(spec.slot_digest).strip() == _ALL_ZERO_DIGEST:
        raise BundleIntegrityError(
            f"{slot.value} slot digest 为全零 hash —— 「忘了算 hash 就填 0」是伪身份，"
            "在 char(64) 与 hex 正则层面都合法，必须单独拒绝"
        )
    # digest 形态（64 位小写 hex）与 `definition:<uuid>` ref 形态、marker 归属 slot
    # 的判据全部由 models 的单一实现负责，本模块不再复制。
    validate_bundle_slot(spec)

    if spec.slot_type == "definition":
        return spec

    marker = TYPED_NULL_MARKERS.get(spec.slot_type)
    if marker is None:
        raise BundleIntegrityError(
            f"{slot.value} slot type={spec.slot_type!r} 既非 'definition' 也非 registry "
            f"登记的版本化 typed null marker（已登记 {sorted(TYPED_NULL_MARKERS)}）"
        )
    if marker.slot is not slot:
        raise BundleIntegrityError(
            f"{slot.value} slot 用了 {marker.slot.value} 的 marker: {spec.slot_type!r}"
        )
    if spec.slot_ref != marker.slot_ref:
        raise BundleIntegrityError(
            f"{slot.value} marker ref 与 registry 不一致："
            f"实得 {spec.slot_ref!r}，registry {marker.slot_ref!r}"
        )
    if spec.slot_digest != marker.slot_digest:
        raise BundleIntegrityError(
            f"{slot.value} marker digest 与 registry 真实 digest 不一致："
            f"实得 {spec.slot_digest!r}，registry {marker.slot_digest!r}"
        )
    return spec


def normalize_bundle_slot_map(
    slots: Mapping[BundleSlot | str, Any]
) -> dict[BundleSlot, BundleSlotSpec]:
    """把外部 slot map 归一成 `{BundleSlot: BundleSlotSpec}`；FC-1~FC-10 在此拒绝。

    键允许是 :class:`BundleSlot` 或字符串（JSON 文件读出来就是字符串）。
    「缺键」与「键在但值为 NULL」是两条独立判据，分别报错 —— 合并成一条后，
    把 `if raw is None` 分支删掉不会让守卫变红。
    """
    keyed: dict[BundleSlot, Any] = {}
    for raw_key, raw_value in slots.items():
        try:
            k = raw_key if isinstance(raw_key, BundleSlot) else BundleSlot(raw_key)
        except (ValueError, TypeError) as exc:
            raise BundleIntegrityError(f"bundle slot 键未登记: {raw_key!r}") from exc
        keyed[k] = raw_value
    missing = [s.value for s in BundleSlot if s not in keyed]
    if missing:
        raise BundleIntegrityError(
            f"bundle typed slots 缺失: {missing}（template/instrumentation/contract 三 slot "
            "必须全出现，且 authority model 独立必填）"
        )
    return {slot: _normalize_slot_input(slot, keyed[slot]) for slot in BundleSlot}


def normalize_authority_digest(value: Any) -> str:
    """FC-13：authority model digest 只做 NULL 判定与归一。

    🔴 digest 的**形态**判据（非空 / 非全零 / 64 位小写 hex）由
    `models.validate_bundle_slots` 的 `is_digest(authority_model_definition_sha256)`
    单点负责，本函数不再复制一份 —— 与 :func:`_normalize_slot_input` 同一理由：
    两份重合实现让任一侧被短路都不改变行为，变异检验判 GREEN。
    """
    if value is None:
        raise BundleIntegrityError("bundle 的 authority model digest 为 NULL")
    return str(value).strip()


def coerce_authority_model(value: Any) -> AuthorityModel:
    """FC-14：authority model 必须是封闭枚举。"""
    try:
        return value if isinstance(value, AuthorityModel) else AuthorityModel(value)
    except (ValueError, TypeError) as exc:
        raise BundleIntegrityError(
            f"authority model 枚举未登记: {value!r}"
            f"（封闭枚举 {sorted(m.value for m in AuthorityModel)}）"
        ) from exc


def build_bundle_canonical_payload(
    *,
    authority_model: AuthorityModel | str,
    authority_model_definition_sha256: str,
    slots: Mapping[BundleSlot | str, Any],
) -> dict[str, Any]:
    """构造 bundle canonical payload；任一 FC 反例在 canonicalization **之前**拒绝。

    返回的 dict 直接交 :func:`canonical_json_bytes` 得到 canonical bytes；本函数
    绝不返回含 null/空串/全零 hash 的 payload —— 「不合法的东西根本不会被编码」是
    Requirement 6.2 的原文要求。
    """
    am = coerce_authority_model(authority_model)
    am_digest = normalize_authority_digest(authority_model_definition_sha256)
    normalized = normalize_bundle_slot_map(slots)

    # FC-12：projection_contract 三 child 必须全为 approved definition（marker 不得冒充）。
    validate_bundle_slots(
        authority_model=am,
        authority_model_definition_sha256=am_digest,
        slots=normalized,
    )

    payload: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "authority_model": {"type": "definition", "sha256": am_digest},
    }
    for slot in BundleSlot:
        spec = normalized[slot]
        payload[slot.value] = {"type": spec.slot_type, "sha256": spec.slot_digest}
    return payload


def bundle_canonical_bytes(**kwargs: Any) -> bytes:
    return canonical_json_bytes(build_bundle_canonical_payload(**kwargs))


def bundle_canonical_digest(**kwargs: Any) -> str:
    return hashlib.sha256(bundle_canonical_bytes(**kwargs)).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 5. alias registry —— 只指向 immutable 快照，且**只在发布期可用**
# ═══════════════════════════════════════════════════════════════════════════


#: 历史读取禁用 alias 的文案（提成常量，让 `resolve_for_history` 的 raise 保持单行）。
_ALIAS_HISTORY_FORBIDDEN: Final[str] = (
    "历史读取（operation/retry/rollback/evidence）不得按 alias {alias!r} 重组 bundle "
    "—— 必须读 frozen `definition_bundle_id` + `definition_bundle_sha256`"
)


class AliasResolutionForbiddenError(SyncDomainError):
    """历史读取路径调用 alias 解析（Requirement 2.10 / Property 7 / 28）。

    🔴 这个禁令必须是**恒抛方法**，不能靠「不提供 alias API」。design 明确
    「历史读取不得按当前 registry alias 重组 bundle」；只要 alias API 存在且
    没有场景门，某天就会有人在 retry 路径上调它，而那时 bundle digest 已经漂移，
    表现为「同一个历史 operation 重跑出不同结果」—— 最难查的一类。
    """

    error_code = "alias_resolution_forbidden"


@dataclass(frozen=True)
class DefinitionAliasTarget:
    """alias 指向的 immutable 快照（**只能**是 approved definition/bundle 的具体 id+digest）。"""

    alias: str
    definition_id: uuid.UUID
    definition_sha256: str
    kind: DefinitionKind | None = None


class DefinitionAliasRegistry:
    """逻辑 alias → approved immutable 快照。

    两个方法名刻意不同：

    * :meth:`resolve_for_publish` —— 发布/组 bundle 时可用（那时「最新版」正是意图）；
    * :meth:`resolve_for_history` —— **恒抛**。历史 operation/retry/evidence 只能读
      自己 frozen 的 bundle FK + digest。
    """

    def __init__(self, targets: Mapping[str, DefinitionAliasTarget] | None = None) -> None:
        self._targets: dict[str, DefinitionAliasTarget] = dict(targets or {})

    def register(self, target: DefinitionAliasTarget) -> None:
        if not is_digest(target.definition_sha256):
            raise IdentityError(
                f"alias {target.alias!r} 的目标 digest 非法: {target.definition_sha256!r}"
            )
        self._targets[target.alias] = target

    def resolve_for_publish(self, alias: str) -> DefinitionAliasTarget:
        target = self._targets.get(alias)
        if target is None:
            raise BundleIntegrityError(f"definition alias 未登记: {alias!r}")
        return target

    def resolve_for_history(self, alias: str) -> DefinitionAliasTarget:
        # 🔴 单行 raise 是刻意的：变异检验只能整行替换，多行语句的首行被替换会破坏
        #    续行语法 ⇒ 文件级 collect ERROR ⇒ 判定退化成 WRONG-TEST。
        raise AliasResolutionForbiddenError(_ALIAS_HISTORY_FORBIDDEN.format(alias=alias))

    def __contains__(self, alias: object) -> bool:
        return alias in self._targets


# ═══════════════════════════════════════════════════════════════════════════
# 6. 发布器（文件系统 + DB 两侧的组合入口）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PublishedDefinition:
    """一次 definition 发布的结果。"""

    definition_id: uuid.UUID
    kind: DefinitionKind
    sha256: str
    blob_artifact_id: uuid.UUID
    relative_path: str
    state: DefinitionState


@dataclass(frozen=True)
class PublishedBundle:
    """一次 bundle 发布的结果（canonical bytes 已内容寻址落盘）。"""

    bundle_id: uuid.UUID
    canonical_sha256: str
    canonical_payload_artifact_id: uuid.UUID
    authority_model: AuthorityModel
    authority_model_definition_id: uuid.UUID
    slots: Mapping[BundleSlot, BundleSlotSpec]
    state: DefinitionState


class DefinitionPublisher:
    """按 DAG 发布 definition/bundle：canonical bytes → artifact → definition row。

    * 文件系统侧走 Task 11 的 `CanonicalArtifactRepository.publish_definition_blob` /
      `publish_bundle_canonical_bytes`（内容寻址不可变）；
    * DB 侧走 Task 10 的 `WorkpaperSyncRepository.create_definition_artifact` /
      `create_definition_bundle`（只 flush 不 commit，事务边界由调用方持有）。

    本类**不**自己拼路径、不自己算 digest 之外的身份，也不 commit。
    """

    def __init__(self, *, artifacts: Any, repository: Any, project_id: uuid.UUID,
                 wp_id: uuid.UUID, source_commit: str) -> None:
        self._artifacts = artifacts
        self._repo = repository
        self._project_id = project_id
        self._wp_id = wp_id
        self._source_commit = source_commit
        self._approved_stages: set[PublishStage] = set()

    @property
    def approved_stages(self) -> frozenset[PublishStage]:
        return frozenset(self._approved_stages)

    def mark_stage_approved(self, stage: PublishStage | str) -> None:
        self._approved_stages.add(
            stage if isinstance(stage, PublishStage) else PublishStage(stage)
        )

    async def publish_definition(
        self,
        *,
        kind: DefinitionKind | str,
        payload: Mapping[str, Any],
        logical_id: str,
        semantic_version: str,
        blob_bytes: bytes | None = None,
        structure_hash: str | None = None,
        approved: bool = True,
    ) -> PublishedDefinition:
        """发布一个 definition artifact（含 payload 校验 + DAG 前置校验）。

        `blob_bytes` 为 None 时用 canonical payload bytes 作为 blob（json 类
        definition）；template 类需显式传入模板字节。
        """
        k = kind if isinstance(kind, DefinitionKind) else DefinitionKind(kind)
        validate_definition_payload(k, payload)
        if k in (DefinitionKind.instrumentation, DefinitionKind.contract):
            assert_publish_order(
                stage=PublishStage(k.value), approved_stages=self._approved_stages
            )

        canonical = canonical_json_bytes(payload)
        digest = hashlib.sha256(canonical).hexdigest()
        blob = blob_bytes if blob_bytes is not None else canonical
        published = self._artifacts.publish_definition_blob(
            project_id=self._project_id,
            wp_id=self._wp_id,
            definition_kind=k.value,
            payload=blob,
        )
        blob_row = await self._repo.register_artifact(
            project_id=self._project_id,
            wp_id=self._wp_id,
            kind="definition",
            state="published",
            relative_path=published.relative_path,
            sha256=published.sha256,
            size_bytes=published.size_bytes,
            document_type=published.document_type,
            retention_class="definition",
        )
        row = await self._repo.create_definition_artifact(
            kind=k.value,
            logical_id=logical_id,
            semantic_version=semantic_version,
            blob_artifact_id=blob_row.id,
            sha256=digest,
            source_commit=self._source_commit,
            structure_hash=structure_hash,
            authority_model_type=(
                validate_authority_model_payload(payload).value
                if k is DefinitionKind.authority_model
                else None
            ),
            approved=approved,
        )
        if approved and k is not DefinitionKind.authority_model:
            self.mark_stage_approved(PublishStage(k.value))
        return PublishedDefinition(
            definition_id=row.id,
            kind=k,
            sha256=digest,
            blob_artifact_id=blob_row.id,
            relative_path=published.relative_path,
            state=DefinitionState.approved if approved else DefinitionState.candidate,
        )

    async def publish_bundle(
        self,
        *,
        authority_model_definition_id: uuid.UUID,
        authority_model: AuthorityModel | str,
        authority_model_definition_sha256: str,
        slots: Mapping[BundleSlot | str, Any],
        approved: bool = True,
    ) -> PublishedBundle:
        """组 + 发布 typed definition bundle。

        `projection_contract` 时先按 DAG 断言三个前置阶段都已 approved；marker 型
        authority model 只断言实际用了 definition 的那些 slot。
        """
        am = coerce_authority_model(authority_model)
        payload = build_bundle_canonical_payload(
            authority_model=am,
            authority_model_definition_sha256=authority_model_definition_sha256,
            slots=slots,
        )
        normalized = normalize_bundle_slot_map(slots)
        required = {
            PublishStage(slot.value)
            for slot, spec in normalized.items()
            if spec.is_definition
        }
        missing = sorted(s.value for s in required - self._approved_stages)
        if missing:
            raise PublishOrderError(
                f"bundle 发布前置未 approved: {missing}"
                f"（固定顺序 {' → '.join(s.value for s in PUBLISH_DAG)}）"
            )

        canonical = canonical_json_bytes(payload)
        published = self._artifacts.publish_bundle_canonical_bytes(
            project_id=self._project_id, wp_id=self._wp_id, canonical_bytes=canonical
        )
        blob_row = await self._repo.register_artifact(
            project_id=self._project_id,
            wp_id=self._wp_id,
            kind="definition",
            state="published",
            relative_path=published.relative_path,
            sha256=published.sha256,
            size_bytes=published.size_bytes,
            document_type=published.document_type,
            retention_class="definition",
        )
        row = await self._repo.create_definition_bundle(
            authority_model_definition_id=authority_model_definition_id,
            slots=normalized,
            canonical_payload_artifact_id=blob_row.id,
            canonical_payload_sha256=published.sha256,
            approved=approved,
        )
        if approved:
            self.mark_stage_approved(PublishStage.bundle)
        return PublishedBundle(
            bundle_id=row.id,
            canonical_sha256=published.sha256,
            canonical_payload_artifact_id=blob_row.id,
            authority_model=am,
            authority_model_definition_id=authority_model_definition_id,
            slots=normalized,
            state=DefinitionState.approved if approved else DefinitionState.candidate,
        )


def definition_store_relative_path(kind: str, sha256: str) -> str:
    """definition store 的内容寻址相对路径（与 design §Filesystem Layout 一致）。"""
    from app.services.workpaper_sync.artifacts import (
        DEFINITION_EXTENSIONS,
        DEFINITION_SUBDIRS,
    )

    if kind not in DEFINITION_SUBDIRS:
        raise BundleIntegrityError(f"definition kind 未登记: {kind!r}")
    if not is_digest(sha256):
        raise IdentityError(f"definition sha256 非法: {sha256!r}")
    return str(
        Path("definition_store") / DEFINITION_SUBDIRS[kind] / f"{sha256}{DEFINITION_EXTENSIONS[kind]}"
    ).replace("\\", "/")


__all__ = [
    "json_safe", "canonical_json_bytes", "canonical_digest",
    "PublishStage", "PUBLISH_DAG", "PUBLISH_PREREQUISITES", "PublishOrderError",
    "stage_index", "assert_publish_order",
    "MARKER_SCHEMA_VERSION", "marker_canonical_payload", "marker_digest",
    "TypedNullMarker", "TYPED_NULL_MARKERS", "marker_for", "marker_slot_spec",
    "definition_slot_spec",
    "validate_template_payload", "validate_instrumentation_payload",
    "validate_contract_payload", "validate_authority_model_payload",
    "validate_definition_payload", "PAYLOAD_VALIDATORS",
    "BUNDLE_SCHEMA_VERSION", "build_bundle_canonical_payload",
    "normalize_bundle_slot_map", "normalize_authority_digest", "coerce_authority_model",
    "bundle_canonical_bytes", "bundle_canonical_digest",
    "AliasResolutionForbiddenError", "DefinitionAliasTarget", "DefinitionAliasRegistry",
    "PublishedDefinition", "PublishedBundle", "DefinitionPublisher",
    "definition_store_relative_path",
]
