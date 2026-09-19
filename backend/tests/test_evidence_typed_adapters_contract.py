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


# ─────────────────────────────────────────────────────────────────────────────
# 8. Schema-drift lock — execute every adapter's SQL against real PostgreSQL 16
# ─────────────────────────────────────────────────────────────────────────────
#
# The bug this locks (spec 4.1/4.2 remediation): several adapter resolve()/locate()
# methods referenced NON-EXISTENT tables/columns (e.g. working_paper.audit_year,
# review_records.project_id, voucher_samples, report_configs, ai_content_logs,
# deliverables, confirmations.year). Those raise asyncpg UndefinedColumn/UndefinedTable
# (→ HTTP 500) the moment the SQL runs. This contract test drives every adapter method
# with a fresh (nonexistent) UUID and asserts it returns the empty result (None/False)
# WITHOUT raising a ProgrammingError — locking the SQL against future schema drift.
#
# Skips gracefully when no PostgreSQL is configured.

import sqlalchemy as sa

from app.services.evidence_governance.frozen_contracts import ActorContext, ActorType


def _pg_async_url() -> str | None:
    import os

    url = os.getenv("DATABASE_URL", "")
    if not url or "postgresql" not in url:
        try:
            from app.core.config import settings

            url = settings.DATABASE_URL or ""
        except Exception:
            url = ""
    if not url or "postgresql" not in url:
        return None
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


@pytest.fixture
async def pg_session():
    """A real-PG session bound to a connection inside an outer transaction that is
    always rolled back — the shared DB is left untouched. Skips on non-PG envs."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    url = _pg_async_url()
    if url is None:
        pytest.skip("requires PostgreSQL 16")

    engine = create_async_engine(url, echo=False)
    conn = await engine.connect()
    outer = await conn.begin()
    session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        await session.close()
        await outer.rollback()
        await conn.close()
        await engine.dispose()


# A service actor passes the project-access gate (is_service → True) so can_read runs
# its SQL rather than short-circuiting on project membership.
_SERVICE_ACTOR = ActorContext(
    actor_type=ActorType.SERVICE,
    actor_service_identity_id=uuid.uuid4(),
)


@pytest.mark.parametrize("evidence_type", sorted(EXPECTED_EVIDENCE_TYPES))
async def test_resolve_nonexistent_returns_none_without_error(evidence_type, pg_session):
    """resolve() on a nonexistent id must return None — never raise UndefinedColumn.

    This is the exact failure mode the 4.1/4.2 remediation fixes: broken column/table
    references surface as asyncpg.ProgrammingError → HTTP 500 on the create path.
    """
    adapter = get_adapter(evidence_type)
    missing_id = str(uuid.uuid4())
    result = await adapter.resolve(
        missing_id,
        project_id=uuid.uuid4(),
        audit_year=2025,
        db=pg_session,
    )
    assert result is None


@pytest.mark.parametrize("evidence_type", sorted(EXPECTED_EVIDENCE_TYPES))
async def test_can_read_nonexistent_returns_false_without_error(evidence_type, pg_session):
    """can_read() SQL executes cleanly against the real schema (returns False)."""
    adapter = get_adapter(evidence_type)
    missing_id = str(uuid.uuid4())
    result = await adapter.can_read(
        missing_id,
        actor=_SERVICE_ACTOR,
        project_id=uuid.uuid4(),
        db=pg_session,
    )
    assert result is False


@pytest.mark.parametrize("evidence_type", sorted(EXPECTED_EVIDENCE_TYPES))
async def test_locate_nonexistent_returns_none_without_error(evidence_type, pg_session):
    """locate() SQL executes cleanly against the real schema (returns None)."""
    adapter = get_adapter(evidence_type)
    missing_id = str(uuid.uuid4())
    result = await adapter.locate(missing_id, db=pg_session)
    assert result is None


@pytest.mark.parametrize("evidence_type", sorted(EXPECTED_EVIDENCE_TYPES))
async def test_lock_for_update_nonexistent_returns_false_without_error(evidence_type, pg_session):
    """lock_for_update() SQL executes cleanly against the real schema (returns False)."""
    adapter = get_adapter(evidence_type)
    missing_id = str(uuid.uuid4())
    result = await adapter.lock_for_update(missing_id, db=pg_session)
    assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# 9. NON-UUID target_id fail-closed — every UUID-column binding is guarded
# ─────────────────────────────────────────────────────────────────────────────
#
# The bug this locks (spec 4.1/4.2 follow-up): adapters bind the raw target_id
# string to a uuid-typed column (WHERE id = :tid). When target_id is NOT a valid
# UUID — a cell locator "D2-1!B5", a composite "{wp}::{item}" with a bad wp_id, or
# a probe id like "probe-src-1" / "uat05-src" — asyncpg raises
# ``DataError: invalid input for query argument ... (invalid UUID ...)`` which
# propagates as HTTP 500 on POST /evidence/refs/references. A non-UUID id must be
# treated as "not found" (None/False) so the caller yields a clean desensitized
# 404 SCOPE_NOT_FOUND_OR_FORBIDDEN, NEVER a 500.
#
# These cases execute against real PG16 and assert None/False WITHOUT raising
# DataError/ProgrammingError. Skips gracefully when no PostgreSQL is configured.

# Clearly non-UUID target_ids seen in the live 500 reproductions + design forms.
_NON_UUID_TARGET_IDS = [
    "probe-src-1",       # generic probe id from the live 500 repro
    "uat05-src",         # UAT probe id
    "D2-1!B5",           # workpaper cell locator (sheet!coord)
    "wp::cell",          # composite-looking but non-UUID wp_id part
    "",                  # empty string
    "not-a-uuid",        # arbitrary garbage
    "12345",             # numeric-looking
]


@pytest.mark.parametrize("evidence_type", sorted(EXPECTED_EVIDENCE_TYPES))
@pytest.mark.parametrize("bad_id", _NON_UUID_TARGET_IDS)
async def test_resolve_non_uuid_returns_none_without_dataerror(evidence_type, bad_id, pg_session):
    """resolve() with a non-UUID target_id must return None — never raise DataError."""
    adapter = get_adapter(evidence_type)
    result = await adapter.resolve(
        bad_id,
        project_id=uuid.uuid4(),
        audit_year=2025,
        db=pg_session,
    )
    assert result is None


@pytest.mark.parametrize("evidence_type", sorted(EXPECTED_EVIDENCE_TYPES))
@pytest.mark.parametrize("bad_id", _NON_UUID_TARGET_IDS)
async def test_can_read_non_uuid_returns_false_without_dataerror(evidence_type, bad_id, pg_session):
    """can_read() with a non-UUID target_id must return False — never raise DataError."""
    adapter = get_adapter(evidence_type)
    result = await adapter.can_read(
        bad_id,
        actor=_SERVICE_ACTOR,
        project_id=uuid.uuid4(),
        db=pg_session,
    )
    assert result is False


@pytest.mark.parametrize("evidence_type", sorted(EXPECTED_EVIDENCE_TYPES))
@pytest.mark.parametrize("bad_id", _NON_UUID_TARGET_IDS)
async def test_locate_non_uuid_returns_none_without_dataerror(evidence_type, bad_id, pg_session):
    """locate() with a non-UUID target_id must return None — never raise DataError."""
    adapter = get_adapter(evidence_type)
    result = await adapter.locate(bad_id, db=pg_session)
    assert result is None


@pytest.mark.parametrize("evidence_type", sorted(EXPECTED_EVIDENCE_TYPES))
@pytest.mark.parametrize("bad_id", _NON_UUID_TARGET_IDS)
async def test_lock_for_update_non_uuid_returns_false_without_dataerror(evidence_type, bad_id, pg_session):
    """lock_for_update() with a non-UUID target_id must return False — never raise DataError."""
    adapter = get_adapter(evidence_type)
    result = await adapter.lock_for_update(bad_id, db=pg_session)
    assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# 10. workpaper_cell composite "{wp_id}::{item_id}" handling
# ─────────────────────────────────────────────────────────────────────────────


async def test_workpaper_cell_composite_valid_wp_bad_item_returns_none(pg_session):
    """Composite with a valid-UUID wp_id but nonexistent item resolves to None (not 500)."""
    adapter = WorkpaperCellAdapter()
    composite = f"{uuid.uuid4()}::{uuid.uuid4()}"  # well-formed composite, no matching row
    result = await adapter.resolve(
        composite,
        project_id=uuid.uuid4(),
        audit_year=2025,
        db=pg_session,
    )
    assert result is None


async def test_workpaper_cell_composite_non_uuid_wp_returns_none(pg_session):
    """Composite with a NON-UUID wp_id part must resolve to None — never raise DataError."""
    adapter = WorkpaperCellAdapter()
    result = await adapter.resolve(
        "wp-abc::item-1",
        project_id=uuid.uuid4(),
        audit_year=2025,
        db=pg_session,
    )
    assert result is None
    # locate + lock + can_read on the same composite are also clean
    assert await adapter.locate("wp-abc::item-1", db=pg_session) is None
    assert await adapter.lock_for_update("wp-abc::item-1", db=pg_session) is False
    assert (
        await adapter.can_read(
            "wp-abc::item-1",
            actor=_SERVICE_ACTOR,
            project_id=uuid.uuid4(),
            db=pg_session,
        )
        is False
    )


async def test_workpaper_cell_bare_uuid_nonexistent_returns_none(pg_session):
    """Bare-UUID (non-composite) cell target that matches nothing resolves to None."""
    adapter = WorkpaperCellAdapter()
    result = await adapter.resolve(
        str(uuid.uuid4()),
        project_id=uuid.uuid4(),
        audit_year=2025,
        db=pg_session,
    )
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 11. _as_uuid / _parse_cell_target unit coverage (no DB required)
# ─────────────────────────────────────────────────────────────────────────────

from app.services.evidence_governance.typed_adapters import (  # noqa: E402
    _as_uuid,
    _parse_cell_target,
)


@pytest.mark.parametrize(
    "value",
    ["probe-src-1", "uat05-src", "D2-1!B5", "wp::cell", "", "not-a-uuid", "12345", None],
)
def test_as_uuid_rejects_non_uuid(value):
    """_as_uuid returns None for any non-UUID input (screens UUID-column bindings)."""
    assert _as_uuid(value) is None


def test_as_uuid_accepts_and_normalizes_valid_uuid():
    """_as_uuid returns the canonical string form for a valid UUID."""
    u = uuid.uuid4()
    assert _as_uuid(str(u)) == str(u)
    assert _as_uuid(str(u).upper()) == str(u)  # normalized to lowercase canonical


def test_parse_cell_target_bare_uuid():
    """Bare UUID → (uuid, None)."""
    u = str(uuid.uuid4())
    assert _parse_cell_target(u) == (u, None)


def test_parse_cell_target_composite():
    """Composite {wp_id}::{item_id} with valid wp_id → (wp_uuid, item_id)."""
    wp = uuid.uuid4()
    parsed = _parse_cell_target(f"{wp}::J1-8-voucher-check")
    assert parsed == (str(wp), "J1-8-voucher-check")


@pytest.mark.parametrize(
    "value",
    ["D2-1!B5", "wp::cell", "probe-src-1", "", "wp-abc::item", f"{uuid.uuid4()}::"],
)
def test_parse_cell_target_rejects_bad(value):
    """Non-UUID / malformed-composite cell targets → None."""
    assert _parse_cell_target(value) is None
