# -*- coding: utf-8 -*-
"""Task 5 守卫：D4-9 bridge `publish_definitions`（design §3 交付物，行为级）。

spec: d4-9-customer-structure-bidirectional-writeback / Task 5
Requirements: 9 (single-direction identity references / fail-closed digest 一致性)

## 这个文件证明什么，以及为什么这样证明

design §3 把 `publish_definitions` 列为本 bridge 的 Task-5 交付物（镜像 D4-2 sibling
`phase5_d4_revenue_detail.publish_definitions`）：按固定 DAG
`authority_model → template → instrumentation → contract → bundle` 发布本 entry 的四个
definition + typed bundle，并在发布 contract 后**逐字节比对**已发布 template/instrumentation
digest 与契约声明的 `template_definition_sha256` / `instrumentation_definition_sha256`
（单向引用断裂即 fail-closed）。

本守卫**不 stub 真实 publisher、不 DB、不 OnlyOffice**：`publisher` 是 duck-typed 异步接口
（`publish_definition(...) -> .definition_id/.sha256`、`publish_bundle(...) -> .bundle_id/
.canonical_sha256`）。我们用一个 **FAKE 内存 publisher** 忠实复现它：`publish_definition`
记录每次调用、返回 `.definition_id`（fresh uuid）+ `.sha256`（= 该 payload 的
`canonical_digest`，与生产 `DefinitionPublisher` 用同一函数），故已发布 template/
instrumentation digest 恰等契约声明值 ⇒ happy-path 的一致性门通过。

- PASS：`publish_definitions(fake)` 返回 `Phase5Definitions`，四 definition id/digest +
  bundle id/sha256 全非空；fake 记录恰 4 次 `publish_definition`，kinds/logical_ids 齐；
  template 调用带 `blob_bytes`（权威模板字节）+ `structure_hash`；已发布 template/
  instrumentation sha256 == 契约声明的 `template_definition_sha256` /
  `instrumentation_definition_sha256`。
- MUTATION / FAIL-CLOSED：让 fake 对 template（或 instrumentation）返回**错误** sha256
  （= 篡改 payload 的 digest），断言 `publish_definitions` 抛 `EntrySelectionError`
  「单向引用断裂」。证明一致性门**绑定**已发布 digest，而非恒真重言式。

## 为什么 fake 忠实

生产 `DefinitionPublisher.publish_definition` 返回的 `.sha256` 就是
`hashlib.sha256(canonical_json_bytes(payload)).hexdigest()` == `canonical_digest(payload)`；
本 fake 用完全相同的 `canonical_digest(payload)`，故对 happy path 与生产行为逐字节等价。
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import (  # noqa: E402
    phase5_d4_customer_structure as bridge,
)
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402
from app.services.workpaper_sync.models import DefinitionKind  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# FAKE 内存 publisher（无 DB / 无 OnlyOffice；忠实复现 duck-typed 异步接口）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class _FakePublishedDefinition:
    definition_id: uuid.UUID
    sha256: str


@dataclass
class _FakePublishedBundle:
    bundle_id: uuid.UUID
    canonical_sha256: str


@dataclass
class _DefinitionCall:
    kind: Any
    payload: Any
    logical_id: str
    semantic_version: str
    blob_bytes: bytes | None
    structure_hash: str | None


@dataclass
class _FakePublisher:
    """记录调用 + 按 payload 的 canonical_digest 返回 sha256（与生产一致）。

    `sha256_override` 允许对某个 kind 强制返回错误 digest（mutation / fail-closed 检验）。
    """

    definition_calls: list[_DefinitionCall] = field(default_factory=list)
    bundle_calls: list[dict[str, Any]] = field(default_factory=list)
    sha256_override: dict[DefinitionKind, str] = field(default_factory=dict)

    async def publish_definition(
        self,
        *,
        kind: Any,
        payload: Any,
        logical_id: str,
        semantic_version: str,
        blob_bytes: bytes | None = None,
        structure_hash: str | None = None,
    ) -> _FakePublishedDefinition:
        k = kind if isinstance(kind, DefinitionKind) else DefinitionKind(kind)
        self.definition_calls.append(
            _DefinitionCall(
                kind=k,
                payload=payload,
                logical_id=logical_id,
                semantic_version=semantic_version,
                blob_bytes=blob_bytes,
                structure_hash=structure_hash,
            )
        )
        sha = self.sha256_override.get(k, canonical_digest(payload))
        return _FakePublishedDefinition(definition_id=uuid.uuid4(), sha256=sha)

    async def publish_bundle(
        self,
        *,
        authority_model_definition_id: uuid.UUID,
        authority_model: Any,
        authority_model_definition_sha256: str,
        slots: Any,
    ) -> _FakePublishedBundle:
        self.bundle_calls.append(
            {
                "authority_model_definition_id": authority_model_definition_id,
                "authority_model": authority_model,
                "authority_model_definition_sha256": authority_model_definition_sha256,
                "slots": dict(slots),
            }
        )
        # 确定性 hash（任意但稳定）。
        canon = "|".join(
            f"{getattr(s, 'value', s)}:{spec.get('digest')}"
            for s, spec in sorted(slots.items(), key=lambda kv: getattr(kv[0], "value", str(kv[0])))
        )
        import hashlib

        return _FakePublishedBundle(
            bundle_id=uuid.uuid4(),
            canonical_sha256=hashlib.sha256(canon.encode("utf-8")).hexdigest(),
        )


# ═══════════════════════════════════════════════════════════════════════════
# PASS —— fake publisher 走完整 publish_definitions
# ═══════════════════════════════════════════════════════════════════════════


class TestPublishDefinitionsPass:
    @pytest.fixture()
    def published(self) -> tuple[_FakePublisher, bridge.Phase5Definitions]:
        fake = _FakePublisher()
        result = asyncio.run(bridge.publish_definitions(fake))
        return fake, result

    def test_returns_phase5_definitions_with_all_ids_and_digests(
        self, published: tuple[_FakePublisher, bridge.Phase5Definitions]
    ) -> None:
        _fake, result = published
        assert isinstance(result, bridge.Phase5Definitions)
        # 四 definition id 全非空 uuid。
        for did in (
            result.authority_model_definition_id,
            result.template_definition_id,
            result.instrumentation_definition_id,
            result.contract_definition_id,
            result.bundle_id,
        ):
            assert isinstance(did, uuid.UUID)
        # 四 definition digest + bundle digest 全非空。
        for digest in (
            result.authority_model_definition_sha256,
            result.template_definition_sha256,
            result.instrumentation_definition_sha256,
            result.contract_definition_sha256,
            result.bundle_sha256,
        ):
            assert isinstance(digest, str) and len(digest) == 64

    def test_records_exactly_four_definition_calls_with_expected_kinds(
        self, published: tuple[_FakePublisher, bridge.Phase5Definitions]
    ) -> None:
        fake, _result = published
        assert len(fake.definition_calls) == 4
        kinds = [c.kind for c in fake.definition_calls]
        assert kinds == [
            DefinitionKind.authority_model,
            DefinitionKind.template,
            DefinitionKind.instrumentation,
            DefinitionKind.contract,
        ]

    def test_logical_ids_bound_to_adapter_id(
        self, published: tuple[_FakePublisher, bridge.Phase5Definitions]
    ) -> None:
        fake, _result = published
        by_kind = {c.kind: c for c in fake.definition_calls}
        assert by_kind[DefinitionKind.authority_model].logical_id == (
            f"{bridge.ADAPTER_ID}.authority-model"
        )
        assert by_kind[DefinitionKind.template].logical_id == f"{bridge.ADAPTER_ID}.template"
        assert by_kind[DefinitionKind.instrumentation].logical_id == (
            f"{bridge.ADAPTER_ID}.instrumentation"
        )
        # contract 的 logical_id 就是裸 ADAPTER_ID。
        assert by_kind[DefinitionKind.contract].logical_id == bridge.ADAPTER_ID

    def test_template_call_carries_blob_bytes_and_structure_hash(
        self, published: tuple[_FakePublisher, bridge.Phase5Definitions]
    ) -> None:
        fake, _result = published
        template_call = next(
            c for c in fake.definition_calls if c.kind is DefinitionKind.template
        )
        # blob_bytes 是权威模板字节（非空、等于 read_authoritative_template）。
        assert isinstance(template_call.blob_bytes, (bytes, bytearray))
        assert template_call.blob_bytes == bridge.read_authoritative_template()
        # structure_hash 非空，且等于 template payload 的 normalized_structure_hash。
        assert isinstance(template_call.structure_hash, str) and template_call.structure_hash
        assert (
            template_call.structure_hash
            == bridge.template_definition_payload()["normalized_structure_hash"]
        )
        # 其它三个 definition 调用不带 blob_bytes。
        for c in fake.definition_calls:
            if c.kind is not DefinitionKind.template:
                assert c.blob_bytes is None

    def test_published_digests_match_contract_declared(
        self, published: tuple[_FakePublisher, bridge.Phase5Definitions]
    ) -> None:
        """已发布 template/instrumentation sha256 == 契约声明值（happy-path 一致性门）。"""
        _fake, result = published
        contract = bridge.load_contract_from_disk()
        assert result.template_definition_sha256 == contract.template_definition_sha256
        assert (
            result.instrumentation_definition_sha256
            == contract.instrumentation_definition_sha256
        )

    def test_bundle_slots_reference_published_definitions(
        self, published: tuple[_FakePublisher, bridge.Phase5Definitions]
    ) -> None:
        fake, result = published
        assert len(fake.bundle_calls) == 1
        slots = fake.bundle_calls[0]["slots"]
        from app.services.workpaper_sync.models import BundleSlot

        # 三个 slot 的 digest 与返回快照一致。
        assert slots[BundleSlot.template]["digest"] == result.template_definition_sha256
        assert (
            slots[BundleSlot.instrumentation]["digest"]
            == result.instrumentation_definition_sha256
        )
        assert slots[BundleSlot.contract]["digest"] == result.contract_definition_sha256


# ═══════════════════════════════════════════════════════════════════════════
# MUTATION / FAIL-CLOSED —— 错误 digest ⇒ 单向引用断裂
#   证明一致性门绑定已发布 digest（非恒真重言式）。
# ═══════════════════════════════════════════════════════════════════════════


class TestPublishDefinitionsFailClosed:
    def test_wrong_template_digest_raises(self) -> None:
        # 篡改一个 payload，取其 digest 作为 template 的错误返回 sha256。
        tampered = dict(bridge.template_definition_payload())
        tampered["__tamper__"] = "x"
        wrong = canonical_digest(tampered)
        fake = _FakePublisher(sha256_override={DefinitionKind.template: wrong})
        with pytest.raises(bridge.EntrySelectionError, match="单向引用断裂"):
            asyncio.run(bridge.publish_definitions(fake))

    def test_wrong_instrumentation_digest_raises(self) -> None:
        tampered = dict(bridge.instrumentation_definition_payload())
        tampered["__tamper__"] = "x"
        wrong = canonical_digest(tampered)
        fake = _FakePublisher(sha256_override={DefinitionKind.instrumentation: wrong})
        with pytest.raises(bridge.EntrySelectionError, match="单向引用断裂"):
            asyncio.run(bridge.publish_definitions(fake))
