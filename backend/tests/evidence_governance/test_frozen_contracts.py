"""冻结共享契约测试 — API/幂等键/expected-version/错误码/ActorContext/canonical hash。

同时以属性测试锁定 P3（actor 完备 XOR）与 P5（哈希绑定）的纯谓词部分，并对
禁止分叉 CI 守卫做行为测试（正确检出 fork 反模式 + 治理层当前零违规）。

使用 backend/tests/conftest.py 全局 fast profile（max_examples=5）。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 1.5
Requirements: R1, R5, R7, R8, R9, R11, R12, R15
Properties: P3, P5, P25
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
import uuid
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.evidence_governance import frozen_contracts as fc

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GUARD_PATH = (
    PROJECT_ROOT / "backend" / "scripts" / "check" / "check_evidence_no_fork.py"
)


def _load_guard_module():
    spec = importlib.util.spec_from_file_location("check_evidence_no_fork", GUARD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_evidence_no_fork"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# API 约定
# ---------------------------------------------------------------------------


def test_api_headers_and_root_frozen():
    assert fc.IDEMPOTENCY_KEY_HEADER == "Idempotency-Key"
    assert fc.EXPECTED_VERSION_HEADER == "If-Match"
    assert "{project_id}" in fc.API_ROOT_TEMPLATE
    assert "{year}" in fc.API_ROOT_TEMPLATE
    assert fc.CURSOR_PAGE_DEFAULT_LIMIT == 100
    assert fc.CURSOR_PAGE_MAX_LIMIT == 200
    assert fc.CURSOR_PAGE_DEFAULT_LIMIT <= fc.CURSOR_PAGE_MAX_LIMIT


# ---------------------------------------------------------------------------
# 稳定错误码（design §7.2）
# ---------------------------------------------------------------------------


def test_error_codes_frozen_set():
    expected = {
        "SCOPE_NOT_FOUND_OR_FORBIDDEN",
        "VERSION_CONFLICT",
        "INVALID_STATE_TRANSITION",
        "EVIDENCE_GATE_BLOCKED",
        "ATTACHMENT_TOO_LARGE",
        "MEDIA_TYPE_MISMATCH",
        "METADATA_INCOMPLETE",
        "REQUIRED_FIELD_UNDECIDED",
        "INVALID_MAPPING",
        "LEGAL_HOLD_ACTIVE",
        "CAPACITY_BACKPRESSURE",
        "DEPENDENCY_DEGRADED",
    }
    assert {c.value for c in fc.EvidenceErrorCode} == expected


def test_every_error_code_has_http_status():
    for code in fc.EvidenceErrorCode:
        assert code in fc.ERROR_CODE_HTTP_STATUS
        assert 400 <= fc.ERROR_CODE_HTTP_STATUS[code] < 600


def test_key_error_code_http_mapping():
    m = fc.ERROR_CODE_HTTP_STATUS
    assert m[fc.EvidenceErrorCode.LEGAL_HOLD_ACTIVE] == 423
    assert m[fc.EvidenceErrorCode.CAPACITY_BACKPRESSURE] == 429
    assert m[fc.EvidenceErrorCode.DEPENDENCY_DEGRADED] == 503
    assert m[fc.EvidenceErrorCode.ATTACHMENT_TOO_LARGE] == 413
    assert m[fc.EvidenceErrorCode.MEDIA_TYPE_MISMATCH] == 415


def test_governance_error_carries_status():
    err = fc.EvidenceGovernanceError(fc.EvidenceErrorCode.LEGAL_HOLD_ACTIVE)
    assert err.http_status == 423
    assert err.error_code is fc.EvidenceErrorCode.LEGAL_HOLD_ACTIVE


# ---------------------------------------------------------------------------
# ActorContext（P3：actor XOR + Service 禁人工确认）
# ---------------------------------------------------------------------------


def test_actor_user_valid():
    uid = uuid.uuid4()
    actor = fc.ActorContext.for_user(uid)
    assert actor.actor_type is fc.ActorType.USER
    assert actor.actor_user_id == uid
    assert actor.actor_service_identity_id is None
    assert not actor.is_service


def test_actor_service_valid():
    sid = uuid.uuid4()
    actor = fc.ActorContext.for_service(sid)
    assert actor.is_service
    assert actor.actor_service_identity_id == sid
    assert actor.actor_user_id is None


def test_actor_user_without_id_rejected():
    with pytest.raises(ValueError):
        fc.ActorContext(actor_type=fc.ActorType.USER)


def test_actor_service_without_id_rejected():
    with pytest.raises(ValueError):
        fc.ActorContext(actor_type=fc.ActorType.SERVICE)


def test_actor_no_dual_identity():
    with pytest.raises(ValueError):
        fc.ActorContext(
            actor_type=fc.ActorType.USER,
            actor_user_id=uuid.uuid4(),
            actor_service_identity_id=uuid.uuid4(),
        )


def test_service_identity_forbidden_human_actions():
    actor = fc.ActorContext.for_service(uuid.uuid4())
    for action in ("ocr_confirm", "ai_confirm", "review_close", "hold_release"):
        assert not actor.can_perform_human_action(action)
        with pytest.raises(fc.EvidenceGovernanceError):
            actor.assert_human_action(action)


def test_user_can_perform_human_actions():
    actor = fc.ActorContext.for_user(uuid.uuid4())
    assert actor.can_perform_human_action("ocr_confirm")
    actor.assert_human_action("ai_confirm")  # 不抛


@given(
    is_service=st.booleans(),
    a=st.uuids(),
    b=st.uuids(),
)
def test_property_actor_xor(is_service, a, b):
    """P3: 成功 actor 恰有 user/service XOR；审计投影只含标识不含双主体。"""
    if is_service:
        actor = fc.ActorContext.for_service(a)
    else:
        actor = fc.ActorContext.for_user(a)
    d = actor.to_audit_dict()
    has_user = d["actor_user_id"] is not None
    has_service = d["actor_service_identity_id"] is not None
    assert has_user != has_service  # 恰好一个


# ---------------------------------------------------------------------------
# canonical JSON / hash（P5：哈希绑定）
# ---------------------------------------------------------------------------


def test_sha256_hex_format():
    h = fc.sha256_hex("hello")
    assert fc.SHA256_HEX_RE.match(h)
    assert h == h.lower()
    assert len(h) == 64
    assert fc.is_sha256_hex(h)
    assert not fc.is_sha256_hex("XYZ")
    assert not fc.is_sha256_hex(None)


def test_canonical_json_key_order_stable():
    a = {"b": 1, "a": 2, "c": {"z": 9, "y": 8}}
    b = {"c": {"y": 8, "z": 9}, "a": 2, "b": 1}
    assert fc.canonical_json(a) == fc.canonical_json(b)
    assert fc.content_hash_of(a) == fc.content_hash_of(b)


def test_canonical_json_preserves_unicode():
    obj = {"名称": "应收账款", "金额": "1234.00"}
    s = fc.canonical_json(obj)
    assert "应收账款" in s  # 不转义为 \uXXXX


def test_content_hash_changes_on_mutation():
    base = {"amount": "100.00", "unit": "元"}
    mutated = {"amount": "100.01", "unit": "元"}
    assert fc.content_hash_of(base) != fc.content_hash_of(mutated)


@given(
    payload=st.dictionaries(
        st.text(min_size=1, max_size=8),
        st.integers() | st.text(max_size=16) | st.booleans(),
        max_size=6,
    )
)
def test_property_hash_binding(payload):
    """P5: 相同字节摘要一致；canonical hash 对键顺序不敏感、可离线复算。"""
    import json as _json

    reordered = dict(sorted(payload.items(), reverse=True))
    assert fc.content_hash_of(payload) == fc.content_hash_of(reordered)
    # 与手工 canonical 序列化再哈希一致（离线可复算）
    manual = _json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    assert fc.content_hash_of(payload) == fc.sha256_hex(manual)


# ---------------------------------------------------------------------------
# adapter contract 清单可加载 + 引擎数
# ---------------------------------------------------------------------------


def test_manifest_loadable_and_versioned():
    manifest = fc.load_engine_contracts()
    assert manifest["task"] == "1.5"
    assert len(manifest["engines"]) >= 8
    assert fc.FROZEN_CONTRACT_VERSION == "1.0.0"
    assert len(fc.FROZEN_ENGINE_NAMES) == 8


# ---------------------------------------------------------------------------
# 禁止分叉 CI 守卫行为
# ---------------------------------------------------------------------------


def test_no_fork_guard_passes_on_current_governance_layer():
    """治理层当前只含 frozen_contracts（无引擎复制）→ 守卫零违规。"""
    guard = _load_guard_module()
    manifest = guard.load_manifest(guard.MANIFEST_PATH)
    canonical = guard.collect_canonical_symbols(manifest)
    markers = guard.collect_fork_markers(manifest)
    roots = [guard.PROJECT_ROOT / r for r in manifest["governance_scan_roots"]]
    violations, scanned = guard.scan_roots(roots, canonical, markers)
    assert scanned >= 1, "应至少扫描到 frozen_contracts.py / __init__.py"
    assert violations == [], f"治理层出现分叉: {violations}"


def test_no_fork_guard_detects_redefinition(tmp_path):
    """守卫必须能检出治理层重定义 canonical 引擎类 / 复制引擎私有方法。"""
    guard = _load_guard_module()
    manifest = guard.load_manifest(guard.MANIFEST_PATH)
    canonical = guard.collect_canonical_symbols(manifest)
    markers = guard.collect_fork_markers(manifest)

    forked = tmp_path / "forked_service.py"
    forked.write_text(
        textwrap.dedent(
            '''
            class AttachmentService:  # 分叉：重定义 canonical 引擎
                def _paperless_uri(self, x):  # 复制引擎私有实现
                    return "paperless://" + str(x)

            def full_resolve():  # 分叉：重定义 ACNR canonical 函数
                pass

            URL = "http://x/api/documents/post_document/"  # 绕过引擎直连
            '''
        ),
        encoding="utf-8",
    )
    hits = guard.scan_file(forked, canonical, markers)
    kinds = {h["kind"] for h in hits}
    assert "REDEFINE_CANONICAL" in kinds
    assert "COPY_ENGINE_INTERNAL" in kinds
    assert "BYPASS_ENGINE_DIRECT_CALL" in kinds


def test_no_fork_guard_clean_file_no_false_positive(tmp_path):
    """合规委托文件（import 引擎 + 调用）不得误报。"""
    guard = _load_guard_module()
    manifest = guard.load_manifest(guard.MANIFEST_PATH)
    canonical = guard.collect_canonical_symbols(manifest)
    markers = guard.collect_fork_markers(manifest)

    clean = tmp_path / "clean_adapter.py"
    clean.write_text(
        textwrap.dedent(
            '''
            from app.services.attachment_service import AttachmentService

            class SecureAttachmentGateway:
                def __init__(self, db):
                    self._svc = AttachmentService(db)

                async def upload(self, project_id, file_name, content, actor):
                    return await self._svc.upload_attachment_file(
                        project_id, file_name, content, created_by=actor,
                    )
            '''
        ),
        encoding="utf-8",
    )
    hits = guard.scan_file(clean, canonical, markers)
    assert hits == [], f"合规委托文件被误报: {hits}"
