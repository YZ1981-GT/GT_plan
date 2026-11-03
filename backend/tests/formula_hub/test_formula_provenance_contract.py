from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services import formula_inputs
from app.services.formula_provenance import (
    InputAtom,
    ProvenanceEnvelopeV1,
    build_attempt,
    definition_identity,
    canonical_json,
    input_digest,
    input_summary,
    note_definition_identity,
    push_rule_identity,
    report_definition_identity,
)


RUN_ID = UUID("00000000-0000-0000-0000-000000000001")


def test_input_digest_is_order_independent_but_duplicate_and_value_sensitive():
    first = [
        InputAtom(kind="TB", key="1001|期末余额", value="1.00"),
        InputAtom(kind="ROW", key="BS-001", value="2.00"),
    ]
    reordered = list(reversed(first))
    assert input_digest(first) == input_digest(reordered)
    assert input_digest(first + [first[0]]) != input_digest(first)
    changed = [first[0], InputAtom(kind="ROW", key="BS-001", value="3.00")]
    assert input_digest(first) != input_digest(changed)


def test_decimal_and_float_are_canonical_fixed_point_text():
    assert canonical_json(Decimal("1.2300")) == '"1.2300"'
    assert canonical_json(1.23) == '"1.23"'
    with pytest.raises(ValueError):
        canonical_json(float("nan"))


def test_nested_collectors_receive_inner_emits_without_deduplication():
    with formula_inputs.collect() as outer:
        formula_inputs.emit("TB", "1001", Decimal("1.00"))
        with formula_inputs.collect() as inner:
            formula_inputs.emit("ROW", "BS-001", Decimal("2.00"))
        formula_inputs.emit("TB", "1001", Decimal("1.00"))

    assert [item.kind for item in outer] == ["TB", "ROW", "TB"]
    assert [item.kind for item in inner] == ["ROW"]


def test_summary_counts_full_inputs_and_limits_display_list():
    inputs = [InputAtom(kind="TB", key=str(i), value=str(i)) for i in range(3)]
    displayed, count, truncated, digest = input_summary(inputs, limit=2)
    assert len(displayed) == 2
    assert count == 3
    assert truncated is True
    assert len(digest) == 64


def test_report_identity_uses_effective_metadata_when_present():
    config = SimpleNamespace(
        formula="TB('1001','期末余额')",
        aje_formula=None,
        rje_formula=None,
        formula_category="auto_calc",
        formula_version=3,
        effective_definition_version=7,
        effective_definition_layer="project",
        effective_source_id="project-row",
        applicable_standard="soe",
    )
    identity = report_definition_identity(config)
    assert identity.version == 7
    assert identity.layer == "project"
    assert identity.source_id == "project-row"
    assert len(identity.definition_hash) == 64


def test_note_identity_uses_local_record_for_project_layer():
    slot = SimpleNamespace(
        layer="project",
        definition={"formula": "TB('1001','期末余额')", "category": "auto_calc"},
        local=SimpleNamespace(version=4, row_id=UUID("00000000-0000-0000-0000-000000000004")),
        upstream=SimpleNamespace(version=2, row_id=UUID("00000000-0000-0000-0000-000000000002")),
    )
    identity = note_definition_identity(slot)
    assert identity.version == 4
    assert identity.layer == "project"
    assert identity.source_id.endswith("0004")


@dataclass(frozen=True)
class FakeRule:
    rule_id: str
    version: int
    expression: str


def test_push_identity_includes_ruleset_hash():
    rule = FakeRule("E1.amount", 2, "TB('1001','期末余额')")
    left = push_rule_identity(rule, "a" * 64)
    right = push_rule_identity(rule, "b" * 64)
    assert left.version == 2
    assert left.layer == "system"
    assert left.definition_hash != right.definition_hash


def test_build_attempt_matches_contract():
    identity = definition_identity(
        version=1,
        layer="global",
        kind="report_config",
        source_id="formula-1",
        snapshot={"formula": "TB('1001','期末余额')"},
    )
    envelope = build_attempt(
        domain="report",
        identity=identity,
        run_id=RUN_ID,
        computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        computed_by=None,
        calc_version="report:229",
        inputs=[{"kind": "TB", "key": "1001", "value": Decimal("1.00")}],
        calculated_value=Decimal("1.00"),
        calculation_status="succeeded",
    )
    assert isinstance(envelope, ProvenanceEnvelopeV1)
    assert envelope.run_id == RUN_ID
    assert envelope.inputs[0].value == "1.00"
    assert envelope.input_count == 1
    assert envelope.definition_ref == {"kind": "report_config", "id": "formula-1"}
    assert len(envelope.model_dump(mode="json")["input_digest"]) == 64
