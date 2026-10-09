"""合并统一上下文协议测试。"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.audit_platform_schemas import EventPayload, EventType
from app.schemas.consol_context import ConsolContext
from app.services.event_bus import deserialize_payload_from_stream, serialize_payload_for_stream
from app.services.consol_context_service import validate_context


PROJECT_ID = uuid4()
RUN_ID = uuid4()


def _context() -> ConsolContext:
    return ConsolContext(
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        year=2025,
        node_key="G:consol",
        node_keys=("G:consol", "G:consol_elim"),
        template_type="soe",
        report_scope="consolidated",
        period_end=date(2025, 12, 31),
        tree_fingerprint="tree-v1",
        source_version="tb-batch-7",
        formula_version="formula-v3",
        template_version="v2025-R5",
    )


def test_context_round_trip_preserves_typed_identity_and_versions():
    context = _context()

    restored = ConsolContext.from_dict(context.to_dict())

    assert restored == context
    assert restored.project_id == PROJECT_ID
    assert restored.period_end == date(2025, 12, 31)
    assert restored.identity_dict()["node_key"] == "G:consol"
    assert restored.identity_dict()["node_keys"] == ["G:consol", "G:consol_elim"]


def test_context_is_frozen_and_rejects_invalid_node_scope():
    context = _context()

    with pytest.raises(ValidationError):
        context.node_key = "G:parent"  # type: ignore[misc]

    with pytest.raises(ValidationError, match="必须属于"):
        context.with_resolution(node_key="G:parent")

    with pytest.raises(ValidationError, match="不能包含重复"):
        ConsolContext(
            project_id=PROJECT_ID,
            year=2025,
            node_keys=("G:consol", "G:consol"),
        )


def test_for_target_keeps_run_lineage_but_clears_target_specific_resolution():
    context = _context()
    target_project_id = uuid4()

    target = context.for_target(target_project_id)

    assert target.project_id == target_project_id
    assert target.year == 2025
    assert target.run_id == RUN_ID
    assert target.context_id == context.context_id
    assert target.node_key is None
    assert target.node_keys == ()
    assert target.template_type is None
    assert target.report_scope is None
    assert target.tree_fingerprint is None
    assert target.source_version is None
    assert target.formula_version is None
    assert target.template_version is None

    resolved = target.with_resolution(
        node_key="P:consol",
        node_keys=("P:consol",),
        template_type="listed",
        report_scope="consolidated",
        tree_fingerprint="target-tree-v2",
        source_version="target-batch-3",
    )
    assert resolved.node_key == "P:consol"
    assert resolved.template_type == "listed"
    assert resolved.tree_fingerprint == "target-tree-v2"
    assert resolved.project_id == target_project_id


def test_legacy_context_has_no_fake_version_and_is_marked():
    context = ConsolContext.legacy(PROJECT_ID, 2025, node_key="G:consol")

    assert context.is_legacy is True
    assert context.node_key == "G:consol"
    assert context.tree_fingerprint is None
    assert context.source_version is None
    assert context.formula_version is None
    assert context.template_version is None


def test_event_payload_round_trip_carries_context():
    context = _context()
    payload = EventPayload(
        event_type=EventType.TRIAL_BALANCE_UPDATED,
        project_id=PROJECT_ID,
        year=2025,
        context=context,
        account_codes=["1001"],
    )

    restored = EventPayload.model_validate_json(payload.model_dump_json())

    assert restored.context == context
    assert restored.resolved_context() == context
    assert restored.project_id == PROJECT_ID
    assert restored.year == 2025


def test_event_payload_rejects_context_project_or_year_mismatch():
    context = _context()

    with pytest.raises(ValidationError, match="项目"):
        EventPayload(
            event_type=EventType.TRIAL_BALANCE_UPDATED,
            project_id=uuid4(),
            year=2025,
            context=context,
        )

    with pytest.raises(ValidationError, match="年度"):
        EventPayload(
            event_type=EventType.TRIAL_BALANCE_UPDATED,
            project_id=PROJECT_ID,
            year=2024,
            context=context,
        )


def test_legacy_flat_event_payload_remains_valid_without_context():
    payload = EventPayload(
        event_type=EventType.TRIAL_BALANCE_UPDATED,
        project_id=PROJECT_ID,
        year=2025,
        extra={"source": "legacy"},
    )

    assert payload.context is None
    assert payload.resolved_context() is None


def test_event_stream_round_trip_preserves_context_and_legacy_flat_entry_downgrades():
    context = _context()
    payload = EventPayload(
        event_type=EventType.TRIAL_BALANCE_UPDATED,
        project_id=PROJECT_ID,
        year=2025,
        context=context,
        extra={"source": "typed"},
    )

    restored = deserialize_payload_from_stream({
        "payload_json": serialize_payload_for_stream(payload),
    })
    legacy = deserialize_payload_from_stream({
        "event_type": EventType.TRIAL_BALANCE_UPDATED.value,
        "project_id": str(PROJECT_ID),
        "year": "2025",
        "account_codes": "[]",
    })

    assert restored.context == context
    assert restored.extra == {"source": "typed"}
    assert legacy.context is None
    assert legacy.extra == {}


def test_typed_context_requires_top_level_year_for_event_boundary():
    with pytest.raises(ValidationError, match="年度"):
        EventPayload(
            event_type=EventType.TRIAL_BALANCE_UPDATED,
            project_id=PROJECT_ID,
            context=_context(),
        )


def test_validate_context_rejects_project_year_and_tree_boundary_mutations():
    from app.services.consol_context_service import context_from_tree

    tree = SimpleNamespace(
        project_id=PROJECT_ID,
        company_code="G",
        node_key="G:consol",
        role="consol",
        kind="aggregate",
        host_project_id=None,
        report_scope="consolidated",
        children=[],
    )
    context = context_from_tree(PROJECT_ID, 2025, tree)

    with pytest.raises(ValueError, match="项目"):
        validate_context(context, uuid4(), 2025, tree=tree)
    with pytest.raises(ValueError, match="年度"):
        validate_context(context, PROJECT_ID, 2024, tree=tree)

    changed_tree = SimpleNamespace(**{**vars(tree), "node_key": "G:parent"})
    with pytest.raises(ValueError, match="树指纹"):
        validate_context(context, PROJECT_ID, 2025, tree=changed_tree)
