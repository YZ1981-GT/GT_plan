"""Guards for the AC coverage matrix generator and the Requirement 14.15 archival gate.

spec: .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/
Wave 0 Task 8 - Requirements 1.8, 14.7, 14.13, 14.15 - Property 57

Two kinds of judgement live here and they are deliberately separated:

* **Structural facts about the real spec documents** - every AC is in the matrix, the
  oracle families tile the ACs exactly once, nothing references a document element that
  does not exist. These must hold today.
* **Behaviour of the defect detectors** - fed synthetic documents, does the generator
  actually report a dangling AC, a self-certified AC, a missing dependency edge, a missing
  evidence type? These are the assertions a mutation has to be able to kill.

What is deliberately *not* asserted: the current counts of ``no_property_oracle`` (101) and
``self_certified_single_task`` (8). Freezing today's number as a baseline would lock a
defect in as the expected value, and would turn any real improvement into a red test. The
gate owns those counts and stays red while they are non-zero; here we only assert that the
detector reports exactly the ACs an independent scan says are affected.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "scripts" / "gen"))
sys.path.insert(0, str(REPO / "backend" / "scripts" / "check"))

import check_workpaper_ac_coverage_gate as gate  # noqa: E402
from generate_workpaper_ac_coverage_matrix import (  # noqa: E402
    _MATRIX,
    _OVERLAY,
    _sha256,
    _stable_json,
    CoverageMatrixError,
    build_matrix,
    collect_sources,
    generate,
    parse_acceptance_criteria,
    parse_dependency_graph,
    parse_oracle_families,
    parse_properties,
    parse_tasks,
    render,
)

SPEC_DIR = REPO / ".kiro" / "specs" / "workpaper-html-onlyoffice-bidirectional-writeback-closure"


def _doc(name: str) -> list[str]:
    return SPEC_DIR.joinpath(name).read_bytes().decode("utf-8").split("\n")


@pytest.fixture(scope="module")
def matrix() -> dict[str, Any]:
    return json.loads(_MATRIX.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def overlay() -> dict[str, Any]:
    return json.loads(_OVERLAY.read_text(encoding="utf-8"))


# --------------------------------------------------------------- synthetic factories


def _ac(ac_id: str) -> dict[str, Any]:
    req, num = ac_id.split(".")
    return {
        "ac_id": ac_id,
        "requirement": int(req),
        "requirement_title": f"R{req}",
        "line": 10 + int(num),
        "text_digest": _sha256(ac_id.encode("utf-8")),
    }


def _family(name: str, requirement: int, first: int, last: int, evidence: str) -> dict[str, Any]:
    return {
        "family": name,
        "requirement": requirement,
        "ac_first": first,
        "ac_last": last,
        "ac_ids": [f"{requirement}.{n}" for n in range(first, last + 1)],
        "criteria": "synthetic",
        "evidence_text": evidence,
        "line": 100,
        "row_digest": _sha256(name.encode("utf-8")),
    }


def _task(task_id: str, ac_ids: list[str], properties: list[int] | None = None) -> dict[str, Any]:
    return {
        "task": task_id,
        "state": " ",
        "title": f"task {task_id}",
        "line": 200 + int(task_id),
        "ac_ids": ac_ids,
        "properties": properties or [],
        "requirements_lines": 1,
    }


def _overlay(families: list[str], evidence: str, classes: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "review_status": "reviewed",
        "adjudications": {
            name: {
                "design_evidence_text": evidence,
                "evidence_classes": classes or ["db_integration"],
                "note": "synthetic adjudication for the guard",
            }
            for name in families
        },
    }


def _build(
    *,
    acs: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    dependencies: dict[str, list[str]],
    properties: list[dict[str, Any]] | None = None,
    families: list[dict[str, Any]] | None = None,
    overlay: dict[str, Any] | None = None,
    waves: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence = "synthetic evidence"
    fam = families if families is not None else [_family("SynthOracle", 1, 1, len(acs), evidence)]
    return build_matrix(
        acs=acs,
        properties=properties or [],
        families=fam,
        tasks=tasks,
        graph={
            "waves": waves or [{"wave": 0, "tasks": sorted(dependencies, key=int)}],
            "dependencies": dependencies,
        },
        overlay=overlay
        if overlay is not None
        else _overlay([f["family"] for f in fam], evidence),
        sources={},
    )


def _defects(built: dict[str, Any], ac_id: str) -> list[str]:
    return next(e["defects"] for e in built["acceptance_criteria"] if e["ac_id"] == ac_id)


# ------------------------------------------------- A. generated artifact fail-closed


def test_matrix_on_disk_matches_the_spec_documents() -> None:
    """Source digest fail-closed: an edited spec with a stale matrix must be visible."""
    assert _MATRIX.read_text(encoding="utf-8") == render(generate()), (
        "the stored matrix no longer matches requirements.md / design.md / tasks.md; "
        "rerun generate_workpaper_ac_coverage_matrix.py --apply"
    )


def test_matrix_pins_a_digest_of_every_spec_document(matrix: dict[str, Any]) -> None:
    """Each of the three documents is pinned by its own sha256, not just the overall one."""
    sources = matrix["sources"]
    assert set(sources) == set(collect_sources()), "the pinned document set changed"
    for rel, meta in sources.items():
        raw = (REPO / rel).read_bytes()
        assert meta["sha256"] == _sha256(raw), f"{rel} changed after the matrix was generated"
        assert meta["bytes"] == len(raw)


def test_hand_edited_matrix_is_rejected_by_self_consistency(matrix: dict[str, Any]) -> None:
    """`matrix_digest` covers the whole body, so editing any field invalidates it."""
    body = {k: v for k, v in matrix.items() if k != "matrix_digest"}
    assert matrix["matrix_digest"] == _sha256(_stable_json(body).encode("utf-8"))
    tampered = json.loads(json.dumps(body))
    tampered["stats"]["defect_counts"] = {}
    assert matrix["matrix_digest"] != _sha256(_stable_json(tampered).encode("utf-8"))


# ------------------------------------------------------- B. parser vs independent scan


def test_every_acceptance_criterion_in_requirements_is_in_the_matrix(
    matrix: dict[str, Any],
) -> None:
    scanned = {
        m.group(1)
        for line in _doc("requirements.md")
        if (m := re.match(r"^(\d+\.\d+)\.\s+\S", line))
    }
    listed = {entry["ac_id"] for entry in matrix["acceptance_criteria"]}
    assert scanned, "the independent scan found no AC - the guard would be vacuous"
    assert listed == scanned, (
        f"matrix misses {sorted(scanned - listed)} / invents {sorted(listed - scanned)}"
    )


def test_every_design_property_is_in_the_matrix(matrix: dict[str, Any]) -> None:
    scanned = {
        int(m.group(1))
        for line in _doc("design.md")
        if (m := re.match(r"^### Property (\d+):", line))
    }
    listed = {entry["property"] for entry in matrix["properties"]}
    assert scanned and listed == scanned, (
        f"matrix misses {sorted(scanned - listed)} / invents {sorted(listed - scanned)}"
    )


def test_task_requirement_references_and_covering_tasks_agree(matrix: dict[str, Any]) -> None:
    """Both directions: task -> AC from tasks.md, AC -> task from the matrix."""
    forward: dict[str, set[str]] = {}
    for entry in matrix["tasks"]:
        for ac in entry["ac_ids"]:
            forward.setdefault(ac, set()).add(entry["task"])
    for entry in matrix["acceptance_criteria"]:
        assert set(entry["covering_tasks"]) == forward.get(entry["ac_id"], set()), (
            f"AC {entry['ac_id']} covering_tasks disagrees with the task list"
        )


def test_oracle_families_tile_every_ac_exactly_once(matrix: dict[str, Any]) -> None:
    covered: list[str] = [ac for row in matrix["oracle_families"] for ac in row["ac_ids"]]
    listed = {entry["ac_id"] for entry in matrix["acceptance_criteria"]}
    assert not matrix["duplicate_family_coverage"], "an AC belongs to two oracle families"
    assert len(covered) == len(set(covered)), "an oracle family range overlaps another"
    assert set(covered) == listed, (
        f"oracle matrix misses {sorted(listed - set(covered))} / "
        f"names unknown {sorted(set(covered) - listed)}"
    )


def test_no_stale_cross_document_reference(matrix: dict[str, Any]) -> None:
    assert matrix["stale_references"] == {
        "task_to_unknown_ac": [],
        "task_to_unknown_property": [],
        "property_to_unknown_ac": [],
        "oracle_family_to_unknown_ac": [],
    }, f"stale references: {matrix['stale_references']}"


def test_no_dangling_ac_or_property(matrix: dict[str, Any]) -> None:
    """These two must be zero today; both are also independently re-derived here."""
    dangling_ac = [
        e["ac_id"] for e in matrix["acceptance_criteria"] if not e["covering_tasks"]
    ]
    dangling_prop = [
        e["property"] for e in matrix["properties"] if not e["verifying_tasks"]
    ]
    assert dangling_ac == [], f"AC referenced by no task: {dangling_ac}"
    assert dangling_prop == [], f"Property verified by no task: {dangling_prop}"
    counts = matrix["stats"]["defect_counts"]
    assert counts.get("dangling_ac", 0) == 0 and counts.get("dangling_property", 0) == 0


def test_reported_no_property_oracle_matches_an_independent_derivation(
    matrix: dict[str, Any],
) -> None:
    """The count is not frozen; the *set* must equal what the design links imply."""
    validated = {ac for entry in matrix["properties"] for ac in entry["validates"]}
    expected = {
        e["ac_id"] for e in matrix["acceptance_criteria"] if e["ac_id"] not in validated
    }
    reported = {
        e["ac_id"]
        for e in matrix["acceptance_criteria"]
        if "no_property_oracle" in e["defects"]
    }
    assert reported == expected, (
        f"detector disagrees with the design links; only in report {sorted(reported - expected)}, "
        f"only in derivation {sorted(expected - reported)}"
    )
    assert matrix["stats"]["defect_counts"].get("no_property_oracle", 0) == len(expected)


def test_reported_self_certification_matches_an_independent_derivation(
    matrix: dict[str, Any],
) -> None:
    expected = {
        e["ac_id"] for e in matrix["acceptance_criteria"] if len(e["covering_tasks"]) == 1
    }
    reported = {
        e["ac_id"]
        for e in matrix["acceptance_criteria"]
        if "self_certified_single_task" in e["defects"]
    }
    assert reported == expected


# ------------------------------------------------------- C. defect detectors behave


def test_ac_without_any_task_is_reported_as_dangling() -> None:
    built = _build(
        acs=[_ac("1.1"), _ac("1.2")],
        tasks=[_task("1", ["1.1"]), _task("2", ["1.1"])],
        dependencies={"1": [], "2": ["1"]},
    )
    assert "dangling_ac" in _defects(built, "1.2")
    assert "dangling_ac" not in _defects(built, "1.1")


def test_single_covering_task_is_reported_as_self_certified() -> None:
    built = _build(acs=[_ac("1.1")], tasks=[_task("1", ["1.1"])], dependencies={"1": []})
    assert "self_certified_single_task" in _defects(built, "1.1")
    assert built["acceptance_criteria"][0]["independent_verification_tasks"] == []


def test_two_tasks_without_a_dependency_edge_are_not_independent_verification() -> None:
    """Wave 0 constraint 4: a second task only verifies if it depends on the first."""
    built = _build(
        acs=[_ac("1.1")],
        tasks=[_task("1", ["1.1"]), _task("2", ["1.1"])],
        dependencies={"1": [], "2": []},
    )
    assert "no_dependency_edge" in _defects(built, "1.1")
    assert built["acceptance_criteria"][0]["implementation_verification_pairs"] == []


def test_dependency_edge_may_be_transitive() -> None:
    built = _build(
        acs=[_ac("1.1")],
        tasks=[_task("1", ["1.1"]), _task("2", []), _task("3", ["1.1"])],
        dependencies={"1": [], "2": ["1"], "3": ["2"]},
        properties=[{"property": 1, "title": "p", "line": 5, "validates": ["1.1"]}],
    )
    entry = built["acceptance_criteria"][0]
    assert entry["defects"] == [], f"unexpected defects {entry['defects']}"
    assert entry["implementation_verification_pairs"] == [["1", "3"]]
    assert entry["independent_verification_tasks"] == ["3"]


def test_ac_without_a_design_property_is_reported() -> None:
    linked = _build(
        acs=[_ac("1.1")],
        tasks=[_task("1", ["1.1"]), _task("2", ["1.1"])],
        dependencies={"1": [], "2": ["1"]},
        properties=[{"property": 1, "title": "p", "line": 5, "validates": ["1.1"]}],
    )
    assert "no_property_oracle" not in _defects(linked, "1.1")
    unlinked = _build(
        acs=[_ac("1.1")],
        tasks=[_task("1", ["1.1"]), _task("2", ["1.1"])],
        dependencies={"1": [], "2": ["1"]},
        properties=[{"property": 1, "title": "p", "line": 5, "validates": ["1.2"]}],
    )
    assert "no_property_oracle" in _defects(unlinked, "1.1")


def test_ac_whose_family_is_unadjudicated_has_no_evidence_type() -> None:
    families = [
        _family("Adjudicated", 1, 1, 1, "e1"),
        _family("Unadjudicated", 1, 2, 2, "e2"),
    ]
    built = _build(
        acs=[_ac("1.1"), _ac("1.2")],
        tasks=[_task("1", ["1.1", "1.2"]), _task("2", ["1.1", "1.2"])],
        dependencies={"1": [], "2": ["1"]},
        families=families,
        overlay=_overlay(["Adjudicated"], "e1"),
    )
    assert "no_evidence_type" in _defects(built, "1.2")
    assert "no_evidence_type" not in _defects(built, "1.1")


def test_ac_outside_every_family_range_is_reported() -> None:
    built = _build(
        acs=[_ac("1.1"), _ac("2.1")],
        tasks=[_task("1", ["1.1", "2.1"]), _task("2", ["1.1", "2.1"])],
        dependencies={"1": [], "2": ["1"]},
        families=[_family("OnlyOne", 1, 1, 1, "e")],
        overlay=_overlay(["OnlyOne"], "e"),
    )
    assert "no_oracle_family" in _defects(built, "2.1")
    assert "no_evidence_type" in _defects(built, "2.1")


def test_stale_references_are_recorded_not_dropped() -> None:
    built = _build(
        acs=[_ac("1.1")],
        tasks=[_task("1", ["1.1"], properties=[9]), _task("2", ["1.1", "9.9"])],
        dependencies={"1": [], "2": ["1"]},
        properties=[{"property": 1, "title": "p", "line": 5, "validates": ["7.7"]}],
    )
    assert built["stale_references"]["task_to_unknown_ac"] == ["9.9"]
    assert built["stale_references"]["task_to_unknown_property"] == ["9"]
    assert built["stale_references"]["property_to_unknown_ac"] == ["7.7"]
    assert built["stats"]["stale_reference_count"] == 3


# ------------------------------------------------- D. overlay is adjudication only


def test_real_overlay_adjudicates_every_oracle_family(
    matrix: dict[str, Any], overlay: dict[str, Any]
) -> None:
    families = {row["family"] for row in matrix["oracle_families"]}
    assert set(overlay["adjudications"]) == families
    for row in matrix["oracle_families"]:
        assert row["evidence_classes"], f"{row['family']} has no evidence class"


def test_real_overlay_pins_the_design_evidence_text_verbatim(
    matrix: dict[str, Any], overlay: dict[str, Any]
) -> None:
    for row in matrix["oracle_families"]:
        assert (
            overlay["adjudications"][row["family"]]["design_evidence_text"]
            == row["evidence_text"]
        ), f"{row['family']} pins evidence text that design.md no longer has"


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda o: o.update(review_status="draft"), "review_status"),
        (lambda o: o.update(schema_version=2), "schema_version"),
        (lambda o: o.update(exempt_acs=["1.1"]), "unknown top-level keys"),
        (lambda o: o.update(adjudications={}), "non-empty object"),
        (
            lambda o: o["adjudications"]["SynthOracle"].update(waived_defects=["dangling_ac"]),
            "unknown keys",
        ),
        (
            lambda o: o["adjudications"]["SynthOracle"].update(evidence_classes=["telepathy"]),
            "unknown evidence classes",
        ),
        (
            lambda o: o["adjudications"]["SynthOracle"].update(evidence_classes=[]),
            "non-empty evidence_classes",
        ),
        (lambda o: o["adjudications"]["SynthOracle"].update(note=""), "needs a note"),
        (
            lambda o: o["adjudications"]["SynthOracle"].update(design_evidence_text="drifted"),
            "design.md changed",
        ),
        (
            lambda o: o["adjudications"].update(GhostOracle=dict(o["adjudications"]["SynthOracle"])),
            "no longer declares",
        ),
    ],
)
def test_overlay_validation_is_fail_closed(mutate, expected: str) -> None:
    """The overlay may only carry adjudications; every other shape is refused."""
    overlay = _overlay(["SynthOracle"], "synthetic evidence")
    mutate(overlay)
    with pytest.raises(CoverageMatrixError, match=expected):
        _build(
            acs=[_ac("1.1")],
            tasks=[_task("1", ["1.1"]), _task("2", ["1.1"])],
            dependencies={"1": [], "2": ["1"]},
            overlay=overlay,
        )


# ---------------------------------------------------------------- E. graph integrity


def test_dependency_cycle_is_refused() -> None:
    with pytest.raises(CoverageMatrixError, match="cycle"):
        _build(
            acs=[_ac("1.1")],
            tasks=[_task("1", ["1.1"]), _task("2", ["1.1"])],
            dependencies={"1": ["2"], "2": ["1"]},
        )


def test_dependency_on_unknown_task_is_refused() -> None:
    with pytest.raises(CoverageMatrixError, match="unknown task"):
        _build(
            acs=[_ac("1.1")],
            tasks=[_task("1", ["1.1"]), _task("2", ["1.1"])],
            dependencies={"1": [], "2": ["99"]},
        )


def test_task_missing_from_the_dependency_graph_is_refused() -> None:
    with pytest.raises(CoverageMatrixError, match="missing tasks"):
        _build(
            acs=[_ac("1.1")],
            tasks=[_task("1", ["1.1"]), _task("2", ["1.1"])],
            dependencies={"1": []},
            waves=[{"wave": 0, "tasks": ["1", "2"]}],
        )


def test_task_outside_every_wave_is_refused() -> None:
    with pytest.raises(CoverageMatrixError, match="outside every wave"):
        _build(
            acs=[_ac("1.1")],
            tasks=[_task("1", ["1.1"]), _task("2", ["1.1"])],
            dependencies={"1": [], "2": ["1"]},
            waves=[{"wave": 0, "tasks": ["1"]}],
        )


def test_real_dependency_graph_only_points_backwards(matrix: dict[str, Any]) -> None:
    """tasks.md states every dependency targets an earlier wave or a smaller number."""
    wave_of = {entry["task"]: entry["wave"] for entry in matrix["tasks"]}
    offenders: list[str] = []
    for entry in matrix["tasks"]:
        for parent in entry["depends_on"]:
            same_wave = wave_of[parent] == entry["wave"]
            forward = wave_of[parent] > entry["wave"] or (
                same_wave and int(parent) >= int(entry["task"])
            )
            if forward:
                offenders.append(f"{entry['task']} -> {parent}")
    assert not offenders, f"forward dependencies: {offenders}"


# ------------------------------------------------------------------- F. gate behaviour


def test_gate_is_red_while_any_defect_remains() -> None:
    code, lines = gate.evaluate()
    report = "\n".join(lines)
    if code == 0:
        assert "[OK]" in report
        return
    assert code == 1, f"unexpected gate exit {code}:\n{report}"
    assert "[RED] Requirement 14.15 blockers remain:" in report
    assert "[WAVE]" in report, "the wave attribution must stay in the report"


def test_gate_explains_every_defect_code_the_generator_can_emit(
    matrix: dict[str, Any],
) -> None:
    assert set(matrix["defect_codes"]) == set(gate._REASONS), (
        "a defect code without a reason would be printed as a bare count"
    )
    for code, reason in gate._REASONS.items():
        assert len(reason) > 20, f"{code} has a placeholder reason"


def test_gate_is_green_only_when_there_are_no_defects(monkeypatch) -> None:
    clean = _build(
        acs=[_ac("1.1")],
        tasks=[_task("1", ["1.1"]), _task("2", ["1.1"], properties=[1])],
        dependencies={"1": [], "2": ["1"]},
        properties=[{"property": 1, "title": "p", "line": 5, "validates": ["1.1"]}],
    )
    monkeypatch.setattr(gate, "generate", lambda: clean)
    monkeypatch.setattr(gate, "_stored_text", lambda: render(clean))
    code, lines = gate.evaluate()
    assert code == 0, "\n".join(lines)
    assert any("[OK]" in line for line in lines)


def test_gate_reports_stale_before_counting_defects(monkeypatch) -> None:
    """A stale matrix outranks the defect count: exit 2, not 1."""
    monkeypatch.setattr(gate, "_stored_text", lambda: '{"matrix_digest": "stale"}')
    code, lines = gate.evaluate()
    assert code == 2
    assert any("[STALE]" in line for line in lines)


def test_gate_refuses_defect_codes_it_cannot_explain(monkeypatch) -> None:
    built = _build(
        acs=[_ac("1.1")],
        tasks=[_task("1", ["1.1"]), _task("2", ["1.1"])],
        dependencies={"1": [], "2": ["1"]},
        properties=[{"property": 1, "title": "p", "line": 5, "validates": ["1.1"]}],
    )
    built["acceptance_criteria"][0]["defects"] = ["brand_new_code"]
    monkeypatch.setattr(gate, "generate", lambda: built)
    monkeypatch.setattr(gate, "_stored_text", lambda: render(built))
    code, lines = gate.evaluate()
    assert code == 2 and any("cannot explain" in line for line in lines)


# ------------------------------------------------------- G. parser hardening (anchors)


def test_ac_under_a_mismatched_requirement_heading_is_refused() -> None:
    with pytest.raises(CoverageMatrixError, match="sits under"):
        parse_acceptance_criteria(
            ["### Requirement 1: a", "#### Acceptance Criteria", "", "2.1. wrong block"]
        )


def test_non_contiguous_ac_numbering_is_refused() -> None:
    with pytest.raises(CoverageMatrixError, match="not contiguous"):
        parse_acceptance_criteria(["### Requirement 1: a", "1.1. first", "1.3. skipped"])


def test_property_without_a_validates_line_is_refused() -> None:
    with pytest.raises(CoverageMatrixError, match="no Validates line"):
        parse_properties(["### Property 1: a", "body", "### Property 2: b"])


def test_property_validating_a_non_ac_shaped_id_is_refused() -> None:
    with pytest.raises(CoverageMatrixError, match="non 'X.Y' ids"):
        parse_properties(["### Property 1: a", "**Validates: Requirements 1**"])


def test_oracle_matrix_header_must_match_verbatim() -> None:
    with pytest.raises(CoverageMatrixError, match="header row not found verbatim"):
        parse_oracle_families(
            [
                "## Acceptance Oracle Matrix",
                "| AC | family | evidence |",
                "|---|---|---|",
                "| 1.1-1.2 | `X` | e |",
                "## next",
            ]
        )


def test_oracle_matrix_range_across_requirements_is_refused() -> None:
    lines = _doc("design.md")
    header = lines.index("| AC 范围 | Design oracle family | 核心判据 | Evidence type |")
    block = [
        "## Acceptance Oracle Matrix",
        lines[header],
        "|---|---|---|---|",
        "| 1.1\u20132.3 | `X` | c | e |",
        "## next",
    ]
    with pytest.raises(CoverageMatrixError, match="one requirement"):
        parse_oracle_families(block)


def test_task_without_a_requirements_line_is_refused() -> None:
    with pytest.raises(CoverageMatrixError, match="'_Requirements:' lines"):
        parse_tasks(["- [ ] 1. only a title", "  - a bullet"])


def test_dependency_graph_needs_the_fenced_json() -> None:
    with pytest.raises(CoverageMatrixError, match="```json fence"):
        parse_dependency_graph(["## Task Dependency Graph", "no fence here"])


def test_real_documents_parse_without_a_single_exception() -> None:
    """The whole point of line anchors: the real 52KB/143KB/85KB documents parse cleanly."""
    acs = parse_acceptance_criteria(_doc("requirements.md"))
    properties = parse_properties(_doc("design.md"))
    families = parse_oracle_families(_doc("design.md"))
    tasks = parse_tasks(_doc("tasks.md"))
    graph = parse_dependency_graph(_doc("tasks.md"))
    assert len(acs) == len({a["ac_id"] for a in acs})
    assert len(properties) == len({p["property"] for p in properties})
    assert len(families) >= 1 and len(tasks) >= 1
    assert set(graph) >= {"waves", "dependencies"}
