"""Entry readiness 三层投影单元测试。"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.workpaper_sync import entry_readiness as R
from app.services.workpaper_sync.entry_profile import extract_entry_profile

ENTRY = "xlsx/test-entry"
WP = uuid.uuid4()
PROJECT = uuid.uuid4()
REP = uuid.uuid4()
BUNDLE = uuid.uuid4()
RUN = uuid.uuid4()
DIGEST = "a" * 64
PROFILE_DIGEST = "b" * 64


def entry(*, capability="bidirectional", state="terminal", adapter_id="test.adapter"):
    row = {
        "entry_id": ENTRY,
        "effective_entry_id": ENTRY,
        "independent_entry": True,
        "parent_entry_id": None,
        "capability": capability,
        "adjudication_state": state,
        "html_counterpart_verdict": "exists",
        "html_counterpart_source_refs": ["test.vue"],
        "adapter_id": adapter_id,
        "editability": "editable",
        "room_model": "shared",
        "scenario_profile": {
            "profile_id": "xlsx.editable.shared.single.room_service_wired.v1",
            "schema_version": 1,
        },
    }
    if capability is None:
        row.update({
            "capability_verdict_stage": "definition_producer_pending",
            "capability_target": "bidirectional",
            "capability_target_blocked_by": ["bundle"],
        })
    return row


def manifest(row):
    return {"manifest_digest": "m" * 64, "source_digest": DIGEST, "entries": [row]}


@pytest.fixture(autouse=True)
def clear_cache():
    R.clear_entry_readiness_cache()
    yield
    R.clear_entry_readiness_cache()


@pytest.mark.asyncio
async def test_pending_is_blocked_without_touching_runtime():
    read_representation = AsyncMock(side_effect=AssertionError("must not query DB"))
    result = await R.evaluate_entry_readiness(
        session=object(), registry=object(), project_id=PROJECT, wp_id=WP,
        entry_id=ENTRY, manifest=manifest(entry(capability=None, state="pending", adapter_id=None)),
        read_representation=read_representation,
    )
    assert result.runtime.ready is False
    assert result.can_claim_bidirectional is False
    assert result.reason and result.reason.code == "ENTRY_UNADJUDICATED"
    read_representation.assert_not_awaited()


@pytest.mark.asyncio
async def test_single_html_needs_no_adapter_or_representation():
    row = entry(capability="single_html", adapter_id=None)
    result = await R.evaluate_entry_readiness(
        session=object(), registry=object(), project_id=PROJECT, wp_id=WP,
        entry_id=ENTRY, manifest=manifest(row),
        read_representation=AsyncMock(side_effect=AssertionError("must not query DB")),
    )
    assert result.allowed_modes == ("html",)
    assert result.runtime.ready is True
    assert result.acceptance.state == "not_applicable"


@pytest.mark.asyncio
async def test_bidirectional_without_representation_is_fail_visible():
    """尚无首版：如实报未就绪 + 原因，但放行 oo —— 首版在首次进入在线编辑时按需发布。

    旧口径只放行 html ⇒ 入口被藏、桥也拒绝，首版永远发不出来（死锁）。
    """
    result = await R.evaluate_entry_readiness(
        session=object(), registry=object(), project_id=PROJECT, wp_id=WP,
        entry_id=ENTRY, manifest=manifest(entry()),
        read_representation=AsyncMock(return_value=None),
    )
    assert result.allowed_modes == ("html", "oo")
    assert result.runtime.ready is False
    assert result.can_claim_bidirectional is False
    assert result.reason and result.reason.code == "REPRESENTATION_MISSING"


def representation():
    return R.RepresentationFacts(
        representation_id=REP,
        generation=3,
        definition_bundle_id=BUNDLE,
        definition_bundle_sha256=DIGEST,
    )


def registration():
    bundle = SimpleNamespace(
        bundle_id=BUNDLE,
        bundle_sha256=DIGEST,
        authority_model=SimpleNamespace(value="projection_contract"),
        typed_slot_inventory=(
            ("template", "definition", "1" * 64),
            ("instrumentation", "definition", "2" * 64),
            ("contract", "definition", "3" * 64),
        ),
    )
    return SimpleNamespace(bundle=bundle, adapter_id="test.adapter")


async def evaluate(*, acceptance=None, bind=None):
    return await R.evaluate_entry_readiness(
        session=object(), registry=object(), project_id=PROJECT, wp_id=WP,
        entry_id=ENTRY, manifest=manifest(entry()),
        read_representation=AsyncMock(return_value=representation()),
        read_acceptance=AsyncMock(return_value=acceptance),
        prepare_registration=AsyncMock(return_value=True),
        bind_registration=bind or AsyncMock(return_value=registration()),
    )


def acceptance(*, result="passed", source=DIGEST, bundle=DIGEST):
    profile = extract_entry_profile(entry()).scenario_profile.digest
    return R.AcceptanceFacts(
        run_id=RUN,
        aggregate_result=result,
        manifest_source_digest=source,
        scenario_profile_digest=profile,
        definition_bundle_sha256=bundle,
        required_scenario_set_digest="c" * 64,
    )


@pytest.mark.asyncio
async def test_runtime_ready_but_evidence_missing_is_not_misreported_as_failure():
    result = await evaluate()
    assert result.runtime.ready is True
    assert result.can_claim_bidirectional is True
    assert result.allowed_modes == ("html", "oo")
    assert result.acceptance.state == "missing"
    assert result.reason and result.reason.code == "EVIDENCE_MISSING"


@pytest.mark.asyncio
async def test_current_passed_evidence_is_verified():
    result = await evaluate(acceptance=acceptance())
    assert result.runtime.ready is True
    assert result.acceptance.state == "verified"
    assert result.acceptance.stale is False
    assert result.reason is None


@pytest.mark.asyncio
async def test_identity_drift_marks_passed_evidence_stale():
    result = await evaluate(acceptance=acceptance(source="d" * 64))
    assert result.runtime.ready is True
    assert result.acceptance.state == "stale"
    assert result.acceptance.stale is True
    assert result.reason and result.reason.code == "EVIDENCE_STALE"


@pytest.mark.asyncio
async def test_registration_failure_is_typed_and_keeps_html_exit():
    from app.services.workpaper_sync.adapters.registry import AdapterNotRegisteredError

    bind = AsyncMock(side_effect=AdapterNotRegisteredError("not registered"))
    result = await evaluate(bind=bind)
    assert result.runtime.ready is False
    assert result.allowed_modes == ("html",)
    assert result.can_claim_bidirectional is False
    assert result.reason and result.reason.code == "ADAPTER_NOT_READY"


@pytest.mark.asyncio
async def test_cache_key_includes_latest_run_identity():
    bind = AsyncMock(return_value=registration())
    first = await evaluate(acceptance=acceptance(), bind=bind)
    second = await evaluate(acceptance=acceptance(), bind=bind)
    assert first == second
    assert bind.await_count == 1


def test_registry_has_no_entry_specific_capability_bypass() -> None:
    from pathlib import Path

    source = Path(
        "app/services/workpaper_sync/adapters/registry.py"
    ).read_text(encoding="utf-8")
    assert "_REG_CANARY_BYPASS" not in source
    assert "_CANARY_BYPASS" not in source
    assert "TEMP: bypass" not in source
