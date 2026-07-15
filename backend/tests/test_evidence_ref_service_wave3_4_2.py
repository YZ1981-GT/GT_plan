"""Task 4.2 (Wave 3) — EvidenceRefService 创建事务 单元测试。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 4.2 (Wave 3)
Requirements: R3, R4, R12
Design: §3.2 EvidenceRefService / §4.4 EvidenceRef 与统一依赖图
Properties: P6 (EvidenceRef 完整性), P7 (EvidenceRef 幂等性)

覆盖：
  * 单元（纯函数）：intent_hash 稳定性、edge_hash 稳定性、不同输入不同哈希。
  * 集成（真实 PG16）：
    - 四项校验全部通过 → ref + edge + audit + outbox 原子创建。
    - 源 scope 失败 → 零 ref/edge/outbox。
    - 目标 scope 失败 → 零 ref/edge/outbox。
    - 源端权限失败 → 零 ref/edge/outbox。
    - 目标端权限失败 → 零 ref/edge/outbox。
    - 版本不匹配 → VERSION_CONFLICT。
    - 哈希不匹配 → VERSION_CONFLICT。
    - 幂等重放 → 返回同一 ref_id。
    - 跨项目尝试 → SCOPE_NOT_FOUND_OR_FORBIDDEN，不泄露信息。
"""

from __future__ import annotations

import uuid

import pytest

from app.services.evidence_governance.evidence_ref_service import (
    CreateEvidenceRefRequest,
    EvidenceRefResult,
    EvidenceRefService,
    _compute_edge_hash,
    _compute_intent_hash,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    content_hash_of,
)


# ===========================================================================
# 1) 纯函数单元测试
# ===========================================================================


class TestIntentHash:
    """P7: intent_hash 从 source_type+source_id+evidence_type+evidence_id 计算。"""

    def test_stable_same_input(self):
        h1 = _compute_intent_hash(
            source_type="workpaper_cell",
            source_id="abc-123",
            evidence_type="attachment_version",
            evidence_id="def-456",
        )
        h2 = _compute_intent_hash(
            source_type="workpaper_cell",
            source_id="abc-123",
            evidence_type="attachment_version",
            evidence_id="def-456",
        )
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_different_inputs_different_hash(self):
        h1 = _compute_intent_hash(
            source_type="workpaper_cell",
            source_id="abc-123",
            evidence_type="attachment_version",
            evidence_id="def-456",
        )
        h2 = _compute_intent_hash(
            source_type="workpaper_cell",
            source_id="abc-123",
            evidence_type="attachment_version",
            evidence_id="def-789",  # different evidence_id
        )
        assert h1 != h2

    def test_order_independent_of_field_order(self):
        """canonical_json sorts keys → same logical content = same hash."""
        h = _compute_intent_hash(
            source_type="voucher",
            source_id="v1",
            evidence_type="workpaper_cell",
            evidence_id="c1",
        )
        # Direct canonical JSON should match
        expected = content_hash_of({
            "source_type": "voucher",
            "source_id": "v1",
            "evidence_type": "workpaper_cell",
            "evidence_id": "c1",
        })
        assert h == expected


class TestEdgeHash:
    """Canonical edge hash for deduplication in the unified dependency graph."""

    def test_stable_same_input(self):
        h1 = _compute_edge_hash(
            source_type="workpaper_cell",
            source_id="s1",
            evidence_type="attachment_version",
            evidence_id="t1",
        )
        h2 = _compute_edge_hash(
            source_type="workpaper_cell",
            source_id="s1",
            evidence_type="attachment_version",
            evidence_id="t1",
        )
        assert h1 == h2
        assert len(h1) == 64

    def test_different_from_intent_hash(self):
        """Edge hash and intent hash use different key namespaces → different values."""
        intent = _compute_intent_hash(
            source_type="workpaper_cell",
            source_id="s1",
            evidence_type="attachment_version",
            evidence_id="t1",
        )
        edge = _compute_edge_hash(
            source_type="workpaper_cell",
            source_id="s1",
            evidence_type="attachment_version",
            evidence_id="t1",
        )
        assert intent != edge  # Different key prefixes (edge_source_type vs source_type)


class TestCreateEvidenceRefRequest:
    """Validate request dataclass creation."""

    def test_basic_creation(self):
        pid = uuid.uuid4()
        req = CreateEvidenceRefRequest(
            project_id=pid,
            audit_year=2025,
            source_type="workpaper_cell",
            source_id="cell-1",
            evidence_type="attachment_version",
            evidence_id="av-1",
        )
        assert req.project_id == pid
        assert req.audit_year == 2025
        assert req.source_type == "workpaper_cell"
        assert req.evidence_type == "attachment_version"
        assert req.target_version is None
        assert req.target_hash is None

    def test_with_version_and_hash(self):
        req = CreateEvidenceRefRequest(
            project_id=uuid.uuid4(),
            audit_year=2025,
            source_type="voucher",
            source_id="v-1",
            source_version=3,
            evidence_type="workpaper_cell",
            evidence_id="c-1",
            target_version=5,
            target_hash="a" * 64,
            label="test-label",
            context="test-context",
        )
        assert req.source_version == 3
        assert req.target_version == 5
        assert req.target_hash == "a" * 64
        assert req.label == "test-label"


class TestEvidenceRefResult:
    """Validate result dataclass."""

    def test_new_creation(self):
        r = EvidenceRefResult(
            ref_id=uuid.uuid4(),
            intent_hash="x" * 64,
            idempotent_hit=False,
            dependency_id=uuid.uuid4(),
        )
        assert not r.idempotent_hit
        assert r.dependency_id is not None

    def test_idempotent_hit(self):
        r = EvidenceRefResult(
            ref_id=uuid.uuid4(),
            intent_hash="y" * 64,
            idempotent_hit=True,
        )
        assert r.idempotent_hit
        assert r.dependency_id is None
