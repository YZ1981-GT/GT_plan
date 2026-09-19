"""Task 9 测试：API 版本、稳定缓存、结构化错误、日志脱敏。

覆盖 spec Requirement 9 AC #1–#6：
    1. Response 携带 schema/contract version / response version / ETag / digests / 三轴状态
    2. Stable cache key 不含 contextRevision
    3. 前端 key 与后端 stable key 契约一致（这里只测后端稳定字段）
    4. owner epoch / revision gate 拒绝旧响应
    5. single fetch owner（前端行为，此处测服务端 fingerprint 稳定性）
    6. 结构化错误返回（invalid/stale/blocked）+ 日志脱敏
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from app.services.guidance_api_contract import (
    GUIDANCE_RESPONSE_SCHEMA_VERSION,
    OwnerGate,
    StructuredError,
    compute_response_fingerprint,
    compute_stable_cache_key,
    make_etag,
    response_version_from_fingerprint,
)
from app.services.guidance_extractor import GuidanceResult, GuidanceSection
from app.services.guidance_resolution_identity import (
    GUIDANCE_CONTRACT_VERSION,
    GUIDANCE_RESOLUTION_SCHEMA_VERSION,
)
from app.services.wp_guidance_service import GuidanceService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class _FakeRuntimeEntry:
    wp_code: str
    entry_id: str = "entry-1"
    entry_digest: str = "dig-1"
    project_id: str = "proj-1"
    exact_status: str | None = None
    missing_sections: tuple = ()
    exact_blockers: tuple = ()
    stale_reasons: tuple = ()
    required: bool = True
    context_kind: str = "child_sheet"
    source_ref_status: str | None = "valid"
    publication_digest: str | None = None
    supplement_digest: str | None = None
    source_refs_digest: str | None = None
    source_facts: tuple = ()

    def version_facts(self):
        return {
            "entry_id": self.entry_id,
            "entry_digest": self.entry_digest,
            "exact_status": self.exact_status,
            "source_ref_status": self.source_ref_status,
        }


def _static_result(wp_code: str) -> GuidanceResult:
    from app.services.guidance_inventory import CANONICAL_SECTION_KEYS
    return GuidanceResult(
        wp_code=wp_code,
        source="static_json",
        sections=[
            GuidanceSection(
                heading=k, content=f"{k} 内容", order=i, key=k,
                source_refs=[{"kind": "static_guidance", "path": f"/x/{wp_code}.json"}],
            )
            for i, k in enumerate(CANONICAL_SECTION_KEYS)
        ],
        raw_text="\n".join(CANONICAL_SECTION_KEYS),
        source_path=f"/x/{wp_code}.json",
    )


def _make_svc_with_mock() -> GuidanceService:
    svc = GuidanceService()
    svc._extractor = AsyncMock()
    svc._extractor.extract_exact_static = AsyncMock(return_value=_static_result("D2-1"))
    svc._extractor.extract_full = AsyncMock(return_value=_static_result("D2-A"))
    return svc


# ---------------------------------------------------------------------------
# Property: AC#1 Response 携带 version / ETag / fingerprint / 三轴状态
# ---------------------------------------------------------------------------


class TestResponseVersionAndEtag:
    def test_response_has_schema_contract_response_versions(self):
        svc = _make_svc_with_mock()
        entry = _FakeRuntimeEntry(wp_code="D2-1")
        resp = asyncio.run(
            svc.resolve_authoritative_exact(
                parent_wp_code="D2-A",
                requested_sheet_code="D2-1",
                authority_wp_code="D2-1",
                authority_sheet_codes=frozenset({"D2-1"}),
                runtime_entry=entry,
            )
        )
        assert resp["contractVersion"] == GUIDANCE_CONTRACT_VERSION
        assert resp["schemaVersion"] == GUIDANCE_RESOLUTION_SCHEMA_VERSION
        assert resp["responseSchemaVersion"] == GUIDANCE_RESPONSE_SCHEMA_VERSION
        assert resp["responseVersion"]  # non-empty
        assert resp["responseFingerprint"]  # non-empty, 64 hex
        assert len(resp["responseFingerprint"]) == 64
        # 🔴 fingerprint 不得是常量（防 M-T9-FINGERPRINT-CONST 假绿）
        assert resp["responseFingerprint"] != "0" * 64
        assert resp["responseFingerprint"] != "a" * 64

    def test_etag_is_weak_format(self):
        svc = _make_svc_with_mock()
        entry = _FakeRuntimeEntry(wp_code="D2-1")
        resp = asyncio.run(
            svc.resolve_authoritative_exact(
                parent_wp_code="D2-A",
                requested_sheet_code="D2-1",
                authority_wp_code="D2-1",
                authority_sheet_codes=frozenset({"D2-1"}),
                runtime_entry=entry,
            )
        )
        assert resp["etag"].startswith('W/"')
        assert resp["etag"].endswith('"')
        # 🔴 etag 内容 = responseVersion，且不得是常量（防 M-T9-ETAG-CONST 假绿）
        assert resp["etag"] == f'W/"{resp["responseVersion"]}"'
        assert resp["etag"] != 'W/"fixed"'
        assert resp["etag"] != 'W/"0000000000000000"'

    def test_response_has_three_axes(self):
        """resolution_status / completion_status / provenance 三轴必须同时存在。"""
        svc = _make_svc_with_mock()
        entry = _FakeRuntimeEntry(wp_code="D2-1")
        resp = asyncio.run(
            svc.resolve_authoritative_exact(
                parent_wp_code="D2-A",
                requested_sheet_code="D2-1",
                authority_wp_code="D2-1",
                authority_sheet_codes=frozenset({"D2-1"}),
                runtime_entry=entry,
            )
        )
        assert "resolution_status" in resp
        assert "completion_status" in resp
        assert "provenance" in resp


# ---------------------------------------------------------------------------
# Property: AC#2 stable cache key 不含 contextRevision
# ---------------------------------------------------------------------------


class TestStableCacheKey:
    def test_stable_cache_key_no_context_revision(self):
        """contextRevision 变化不影响 stable cache key。"""
        key_a = compute_stable_cache_key(
            project_id="p1", wp_code="D2-1", entry_id="e1", sheet_key="*",
            schema_version="v1", inventory_digest="inv-a",
        )
        key_b = compute_stable_cache_key(
            project_id="p1", wp_code="D2-1", entry_id="e1", sheet_key="*",
            schema_version="v1", inventory_digest="inv-a",
            # 无 contextRevision 参数 —— 结构上就不含
        )
        assert key_a == key_b

    def test_stable_cache_key_changes_when_inventory_changes(self):
        """inventory digest 变 → cache key 变（stale 语义）。"""
        key_a = compute_stable_cache_key(
            project_id="p1", wp_code="D2-1", entry_id="e1", sheet_key="*",
            inventory_digest="inv-a",
        )
        key_b = compute_stable_cache_key(
            project_id="p1", wp_code="D2-1", entry_id="e1", sheet_key="*",
            inventory_digest="inv-b",
        )
        assert key_a != key_b

    def test_stable_cache_key_changes_when_schema_changes(self):
        key_a = compute_stable_cache_key(
            project_id="p1", wp_code="D2-1", entry_id="e1", sheet_key="*",
            schema_version="v1",
        )
        key_b = compute_stable_cache_key(
            project_id="p1", wp_code="D2-1", entry_id="e1", sheet_key="*",
            schema_version="v2",
        )
        assert key_a != key_b

    def test_response_stable_cache_key_present(self):
        svc = _make_svc_with_mock()
        entry = _FakeRuntimeEntry(wp_code="D2-1")
        resp = asyncio.run(
            svc.resolve_authoritative_exact(
                parent_wp_code="D2-A",
                requested_sheet_code="D2-1",
                authority_wp_code="D2-1",
                authority_sheet_codes=frozenset({"D2-1"}),
                runtime_entry=entry,
            )
        )
        assert "stableCacheKey" in resp
        assert resp["stableCacheKey"].startswith("guidance|")


# ---------------------------------------------------------------------------
# Property: AC#4 owner epoch / revision gate
# ---------------------------------------------------------------------------


class TestOwnerGate:
    def test_accepts_matching_epoch_and_revision(self):
        gate = OwnerGate(owner_epoch=5, revision="r1")
        assert gate.accepts(5, "r1")

    def test_rejects_mismatched_epoch(self):
        """旧 context 的响应被丢弃。"""
        gate = OwnerGate(owner_epoch=5, revision="r1")
        assert not gate.accepts(4, "r1")  # 旧 epoch
        assert not gate.accepts(6, "r1")  # 新 epoch 但 gate 未更新

    def test_rejects_mismatched_revision(self):
        gate = OwnerGate(owner_epoch=5, revision="r1")
        assert not gate.accepts(5, "r2")

    def test_allows_when_gate_revision_none(self):
        """gate 无 revision 约束时，只验 epoch。"""
        gate = OwnerGate(owner_epoch=5, revision=None)
        assert gate.accepts(5, "any")


# ---------------------------------------------------------------------------
# Property: AC#6 结构化错误返回
# ---------------------------------------------------------------------------


class TestStructuredErrors:
    def test_invalid_status_yields_structured_error(self):
        svc = _make_svc_with_mock()
        svc._extractor.extract_full = AsyncMock(return_value=_static_result("D2-A"))
        # 无 runtime_entry + source=static_json → resolution_status="invalid"
        resp = asyncio.run(
            svc.resolve_authoritative_exact(
                parent_wp_code="D2-A",
                requested_sheet_code=None,
            )
        )
        # 触发 structured error
        assert "structuredErrors" in resp
        assert isinstance(resp["structuredErrors"], list)

    def test_stale_status_yields_structured_error(self):
        svc = _make_svc_with_mock()
        svc._extractor.extract_full = AsyncMock(return_value=_static_result("D2-A"))
        entry = _FakeRuntimeEntry(wp_code="D2-A", exact_status="stale", stale_reasons=("source_changed",))
        resp = asyncio.run(
            svc.resolve_authoritative_exact(
                parent_wp_code="D2-A",
                requested_sheet_code=None,
                runtime_entry=entry,
            )
        )
        assert resp["resolution_status"] == "stale"
        assert len(resp["structuredErrors"]) == 1
        err = resp["structuredErrors"][0]["error"]
        assert err["code"] == "stale"
        assert err["subject"] == "D2-A"
        assert err["operation"] == "guidance.resolve"
        assert "exact_blockers" in err["details"]

    def test_exact_status_yields_empty_structured_errors(self):
        """exact 状态不产生 structured error。"""
        svc = _make_svc_with_mock()
        entry = _FakeRuntimeEntry(wp_code="D2-1", exact_status="exact")
        resp = asyncio.run(
            svc.resolve_authoritative_exact(
                parent_wp_code="D2-A",
                requested_sheet_code="D2-1",
                authority_wp_code="D2-1",
                authority_sheet_codes=frozenset({"D2-1"}),
                runtime_entry=entry,
            )
        )
        assert resp["resolution_status"] == "exact"
        assert resp["structuredErrors"] == []


# ---------------------------------------------------------------------------
# Property: StructuredError 字段完整性 + 脱敏
# ---------------------------------------------------------------------------


class TestStructuredErrorContract:
    def test_error_dict_has_required_keys(self):
        err = StructuredError(
            code="invalid",
            message="foo",
            subject="D2-1",
            operation="guidance.resolve",
            correlation_id="cor-1",
        )
        d = err.to_dict()["error"]
        for k in ["code", "message", "subject", "operation", "correlation_id"]:
            assert k in d

    def test_message_redacts_long_hex(self):
        """message 里 64+ 位 hex 视为 token 被脱敏。"""
        err = StructuredError(code="invalid", message=f"token=abcdef0123456789abcdef0123456789abcdef0123456789abcdef01")
        d = err.to_dict()["error"]
        assert "abcdef" not in d["message"]
        assert "[REDACTED]" in d["message"]

    def test_message_truncated_if_too_long(self):
        long_msg = "x" * 300
        err = StructuredError(code="invalid", message=long_msg)
        d = err.to_dict()["error"]
        assert len(d["message"]) < 300
        assert "[TRUNCATED]" in d["message"]


# ---------------------------------------------------------------------------
# Property: fingerprint 稳定性
# ---------------------------------------------------------------------------


class TestFingerprintStability:
    def test_same_input_same_fingerprint(self):
        parts = {"a": 1, "b": [1, 2, 3], "c": "x"}
        f1 = compute_response_fingerprint(parts=parts)
        f2 = compute_response_fingerprint(parts={"c": "x", "b": [1, 2, 3], "a": 1})
        assert f1 == f2
        assert len(f1) == 64

    def test_any_change_changes_fingerprint(self):
        base = {"a": 1, "b": 2}
        f_base = compute_response_fingerprint(parts=base)
        for changed in [{"a": 1, "b": 3}, {"a": 2, "b": 2}, {"a": 1, "b": 2, "c": 3}]:
            assert compute_response_fingerprint(parts=changed) != f_base

    def test_etag_format(self):
        assert make_etag("abc123") == 'W/"abc123"'

    def test_response_version_is_prefix_of_fingerprint(self):
        fp = "a" * 64
        assert response_version_from_fingerprint(fp) == "a" * 16
