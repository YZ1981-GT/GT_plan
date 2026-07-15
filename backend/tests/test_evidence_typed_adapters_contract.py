"""Contract tests for typed evidence adapters — Task 4.1 (Wave 3).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R3, R4, R6, R10
Properties: P1 (项目隔离), P6 (EvidenceRef 完整性)

Validates:
- All 10 evidence types have registered adapters
- Each adapter satisfies the EvidenceAdapter protocol
- Registry lookup works correctly
- Unsupported types raise the correct error
"""

from __future__ import annotations

import uuid

import pytest

from app.services.evidence_governance.typed_adapters import (
    SUPPORTED_EVIDENCE_TYPES,
    AiContentAdapter,
    AttachmentVersionAdapter,
    ConfirmationAdapter,
    DeliverableAdapter,
    DisclosureNoteAdapter,
    EvidenceAdapter,
    LocatorInfo,
    ReportAdapter,
    ResolvedTarget,
    ReviewOpinionAdapter,
    SamplingItemAdapter,
    VoucherAdapter,
    WorkpaperCellAdapter,
    get_adapter,
    list_adapters,
)
from app.services.evidence_governance.frozen_contracts import (
    EvidenceErrorCode,
    EvidenceGovernanceError,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Registry completeness — all 10 Controlled Modules registered
# ─────────────────────────────────────────────────────────────────────────────

EXPECTED_EVIDENCE_TYPES = frozenset({
    "workpaper_cell",
    "sampling_item",
    "voucher",
    "confirmation",
    "review_opinion",
    "disclosure_note",
    "report",
    "ai_content",
    "deliverable",
    "attachment_version",
})


def test_all_10_evidence_types_registered():
    """All 10 Controlled Modules must be in the registry."""
    assert SUPPORTED_EVIDENCE_TYPES == EXPECTED_EVIDENCE_TYPES


def test_registry_count_is_10():
    """Exactly 10 adapters in the registry."""
    assert len(list_adapters()) == 10


# ─────────────────────────────────────────────────────────────────────────────
# 2. Protocol conformance — each adapter is an EvidenceAdapter
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("evidence_type", sorted(EXPECTED_EVIDENCE_TYPES))
def test_adapter_satisfies_protocol(evidence_type: str):
    """Each adapter instance must satisfy the EvidenceAdapter runtime protocol."""
    adapter = get_adapter(evidence_type)
    assert isinstance(adapter, EvidenceAdapter), (
        f"{evidence_type} adapter does not satisfy EvidenceAdapter protocol"
    )


@pytest.mark.parametrize(
    "adapter_cls,expected_type",
    [
        (WorkpaperCellAdapter, "workpaper_cell"),
        (SamplingItemAdapter, "sampling_item"),
        (VoucherAdapter, "voucher"),
        (ConfirmationAdapter, "confirmation"),
        (ReviewOpinionAdapter, "review_opinion"),
        (DisclosureNoteAdapter, "disclosure_note"),
        (ReportAdapter, "report"),
        (AiContentAdapter, "ai_content"),
        (DeliverableAdapter, "deliverable"),
        (AttachmentVersionAdapter, "attachment_version"),
    ],
)
def test_adapter_evidence_type_attribute(adapter_cls, expected_type: str):
    """Each adapter class has the correct evidence_type attribute."""
    adapter = adapter_cls()
    assert adapter.evidence_type == expected_type


# ─────────────────────────────────────────────────────────────────────────────
# 3. Registry lookup
# ─────────────────────────────────────────────────────────────────────────────

def test_get_adapter_returns_correct_instance():
    """get_adapter returns the expected adapter type."""
    assert isinstance(get_adapter("workpaper_cell"), WorkpaperCellAdapter)
    assert isinstance(get_adapter("attachment_version"), AttachmentVersionAdapter)
    assert isinstance(get_adapter("ai_content"), AiContentAdapter)


def test_get_adapter_unsupported_type_raises():
    """Unsupported evidence type raises SCOPE_NOT_FOUND_OR_FORBIDDEN."""
    with pytest.raises(EvidenceGovernanceError) as exc_info:
        get_adapter("nonexistent_type")
    assert exc_info.value.error_code == EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN


def test_get_adapter_empty_string_raises():
    """Empty string evidence type raises error."""
    with pytest.raises(EvidenceGovernanceError):
        get_adapter("")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Contract shape — all adapters have required methods
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_METHODS = ("resolve", "can_read", "can_edit", "locate", "lock_for_update")


@pytest.mark.parametrize("evidence_type", sorted(EXPECTED_EVIDENCE_TYPES))
def test_adapter_has_all_required_methods(evidence_type: str):
    """Each adapter must expose all 5 contract methods."""
    adapter = get_adapter(evidence_type)
    for method_name in REQUIRED_METHODS:
        method = getattr(adapter, method_name, None)
        assert method is not None, f"{evidence_type} missing {method_name}"
        assert callable(method), f"{evidence_type}.{method_name} not callable"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Data classes (result types)
# ─────────────────────────────────────────────────────────────────────────────

def test_resolved_target_frozen():
    """ResolvedTarget is a frozen dataclass."""
    rt = ResolvedTarget(
        target_id="abc",
        project_id=uuid.uuid4(),
        audit_year=2025,
    )
    assert rt.target_id == "abc"
    with pytest.raises(Exception):  # frozen
        rt.target_id = "xyz"  # type: ignore


def test_locator_info_frozen():
    """LocatorInfo is a frozen dataclass."""
    li = LocatorInfo(
        target_id="abc",
        evidence_type="voucher",
        route="/workpapers/123",
    )
    assert li.evidence_type == "voucher"
    with pytest.raises(Exception):  # frozen
        li.evidence_type = "other"  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# 6. No FK-less generic raw insert (structural invariant)
# ─────────────────────────────────────────────────────────────────────────────

def test_adapters_do_not_create_objects():
    """Adapters resolve/read/edit/locate/lock — they never INSERT new rows.

    This is a structural invariant from design §3.2: adapters must NOT use
    FK-less generic raw insert to fake objects.
    """
    import inspect

    for evidence_type, adapter in list_adapters().items():
        for method_name in REQUIRED_METHODS:
            method = getattr(adapter, method_name)
            source = inspect.getsource(method)
            assert "INSERT" not in source.upper() or "INSERT" in source.upper().split("--")[0] == False, (
                f"{evidence_type}.{method_name} appears to contain INSERT"
            )


def test_adapters_use_select_only():
    """Adapter methods only use SELECT/FOR UPDATE — no DML (INSERT/UPDATE/DELETE)."""
    import inspect

    dml_keywords = {"INSERT INTO", "UPDATE ", "DELETE FROM"}
    for evidence_type, adapter in list_adapters().items():
        for method_name in REQUIRED_METHODS:
            method = getattr(adapter, method_name)
            source = inspect.getsource(method).upper()
            for keyword in dml_keywords:
                assert keyword not in source, (
                    f"{evidence_type}.{method_name} uses DML '{keyword}' — "
                    f"adapters must NOT create/modify objects"
                )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Registry stability — list_adapters returns dict copy
# ─────────────────────────────────────────────────────────────────────────────

def test_list_adapters_returns_copy():
    """list_adapters returns a copy — mutating it doesn't affect the registry."""
    registry = list_adapters()
    registry["fake"] = None  # type: ignore
    assert "fake" not in list_adapters()
