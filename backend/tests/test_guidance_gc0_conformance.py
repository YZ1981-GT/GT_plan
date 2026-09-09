"""Backend conformance + mutation self-checks for the G-C0 wire contract.

Validates Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6 (see
``.kiro/specs/workpaper-guidance-content-closure/requirements.md``) and
the Property 1 / Property 2 acceptance criteria in ``design.md §1``.

Layout
------
1. Property 1 — bundle integrity (schema == module constants).
2. Property 2 — fail-closed version guard (Req 1.5).
3. Req 1.4 — candidate vs finalized handoff discriminators.
4. Req 1.3 — organization-level evidence does not fabricate projectId/wpId.
5. All canonical fixtures ACCEPT through ``validate_contract_version``.
6. Digest stability — schema + every fixture sha256 matches the evidence
   envelope recorded digests.
7. Mutation self-checks M1..M5: mutate the on-disk artefact, run the
   corresponding assertion, classify RED/GREEN/ANCHOR-MISS/WRONG-TEST,
   and finally restore the original bytes.

Mutation classification is emitted as a pytest ``xpass`` marker so the
result is surfaced to the terminal without polluting pass/fail counts.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

import pytest

from app.services.guidance_gc0_contract import (
    GC0_CONTRACT_ID,
    GC0_CONTRACT_VERSION,
    GC0_DISCRIMINATORS,
    GC0_TOP_LEVEL_TYPES,
    ContractBundle,
    discover_local_dupes,  # noqa: F401  -- imported so module path is exercised
    load_bundle,
    schema_path,
    fixtures_dir,
    evidence_path,
    validate_contract_version,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = REPO_ROOT / "backend" / "data" / "guidance" / "contracts" / "gc0"
SCHEMA_PATH = BUNDLE_ROOT / "schema.json"
EVIDENCE_PATH = BUNDLE_ROOT / "evidence" / "gc0_evidence.json"
FIXTURES_DIR = BUNDLE_ROOT / "fixtures"


# ---------------------------------------------------------------------------
# Mutation anchors
#
# Anchors are regexes, not fixed-indentation strings. A string anchor that
# hardcodes indentation returns None (ANCHOR-MISS) the moment a file is
# reformatted — that is a HARNESS defect, not a guard verdict, and it silently
# turns a real guard into a permanent pass. The ``json.loads`` call in each
# mutator additionally rejects any hit that produced malformed JSON.
# ---------------------------------------------------------------------------

#: ``"topLevelTypes": [`` opener + one full entry line (the first entry, which
#: is ``CanonicalWorkpaperLocation``). Replaced by the opener alone, which drops
#: exactly one entry while keeping the array well-formed.
#:
#: Line breaks are ``[\r]?\n``, not bare ``\n``. This file is checked in as
#: CRLF, and ``Path.read_text()`` with default ``newline=None`` performs
#: universal-newline translation — so a bare-``\n`` anchor matches the
#: translated view but NOT the on-disk bytes. That mismatch is what turned
#: these anchors into permanent ANCHOR-MISS (a harness defect that masquerades
#: as a passing guard).
_DROP_FIRST_TOP_LEVEL_TYPE_RE = re.compile(
    r'(?P<open>"topLevelTypes"\s*:\s*\[\s*)'
    r'"[^"]+"\s*,\s*[\r]?\n\s*',
)

#: Anchors the EvidenceSubject discriminator opener (including the trailing
#: ``"operation"`` variant). Forward context guarantees this does not match
#: the identical value in the ``EvidenceArtifact.kind`` enum, which lives in
#: ``definitions`` — well before the ``discriminators`` object.
_DROP_OPERATION_VARIANT_RE = re.compile(
    r'"discriminators"\s*:\s*\{\s*"EvidenceSubject"\s*:\s*\{\s*'
    r'"property"\s*:\s*"kind",\s*"variants"\s*:\s*\[\s*'
    r'"contract",\s*"catalog_entry",\s*"runtime_entry",\s*'
    r'"operation"'
)


def _read_text_disk_faithful(path: Path) -> str:
    """Read UTF-8 text WITHOUT universal-newline translation.

    Mutation mutators operate on ``path.read_bytes()`` and write bytes back,
    so their anchors must be written against the same line endings that are on
    disk. ``read_text()`` alone translates CRLF → LF, which makes ``\\n``-tied
    anchors match the wrong view and either MISS or splice in the wrong bytes.
    """
    return path.read_bytes().decode("utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Property 1 — bundle integrity
# ---------------------------------------------------------------------------


def test_property1_bundle_loads_with_expected_identity() -> None:
    """Property 1.1 — ``load_bundle`` returns a populated bundle with G-C0 identity.

    **Validates: Requirements 1.1**

    Note: this test deliberately carries no parametrize decoration. An earlier
    draft used ``@pytest.mark.parametrize("requirement_ref", ...)`` on a test
    that never consumes the argument, which makes pytest abort at collection
    time ("function uses no argument 'requirement_ref'"). The requirement
    reference lives in the docstring / ``**Validates:**`` line instead, which
    the spec three-piece validator already reads.
    """
    bundle = load_bundle()
    assert isinstance(bundle, ContractBundle)
    assert bundle.contract_id == "G-C0"
    assert bundle.contract_version == "1.0"
    assert bundle.schema_sha256, "schema digest must not be empty"
    assert bundle.fixtures, "at least one canonical fixture is required"
    assert bundle.fixture_sha256, "each fixture must have a digest"


def test_property1_top_level_types_match_schema_exactly() -> None:
    """Property 1.2 — ``GC0_TOP_LEVEL_TYPES`` strictly equals ``schema.topLevelTypes``.

    **Validates: Requirements 1.1**
    """
    bundle = load_bundle()
    schema_types = list(bundle.schema["topLevelTypes"])
    module_types = list(GC0_TOP_LEVEL_TYPES)
    assert schema_types == module_types, (
        "The 8 C0 top-level types must match in BOTH content and order; "
        f"schema={schema_types!r} module={module_types!r}"
    )
    assert len(module_types) == 8
    # Fail-closed on any symbol missing from schema definitions.
    for sym in module_types:
        assert sym in bundle.schema.get("definitions", {}), (
            f"schema.definitions must declare top-level type '{sym}'"
        )


def test_property1_discriminators_match_schema_exactly() -> None:
    """Property 1.3 — ``GC0_DISCRIMINATORS`` strictly equals ``schema.discriminators``.

    Each union must expose both ``property`` and ``variants`` with identical
    contents and order.

    **Validates: Requirements 1.1**
    """
    bundle = load_bundle()
    schema_disc = bundle.schema["discriminators"]
    # Lock the KEY SET both ways: a union declared only in the schema, or only
    # in the module, is drift. Order-independent set comparison for keys
    # because JSON object key order is not normative.
    assert set(schema_disc) == set(GC0_DISCRIMINATORS), (
        "Discriminator key set mismatch; every C0 union must be declared in "
        f"BOTH places. module-only={set(GC0_DISCRIMINATORS) - set(schema_disc)} "
        f"schema-only={set(schema_disc) - set(GC0_DISCRIMINATORS)}"
    )
    for union_name, spec in GC0_DISCRIMINATORS.items():
        entry = schema_disc[union_name]
        assert entry.get("property") == spec["property"], (
            f"discriminator '{union_name}' property mismatch: "
            f"module='{spec['property']}' schema='{entry.get('property')}'"
        )
        assert tuple(entry.get("variants", ())) == spec["variants"], (
            f"discriminator '{union_name}' variants must match in content AND order; "
            f"module={spec['variants']!r} schema={entry.get('variants')!r}"
        )


# ---------------------------------------------------------------------------
# Property 2 — fail-closed compatibility guard (Req 1.5)
# ---------------------------------------------------------------------------


def _first_code(decision) -> str:
    return decision.reasons[0].code if decision.reasons else ""


@pytest.mark.parametrize(
    "payload,expected_outcome,expected_code,consumer_role",
    [
        # unknown major → BLOCKED fail-closed
        ({"contractVersion": "9.0"}, "BLOCKED", "unknown-major", "consumer"),
        ({"contractVersion": "2.0"}, "BLOCKED", "unknown-major", "consumer"),
        # unsupported minor → DEGRADED for consumer
        ({"contractVersion": "1.5"}, "DEGRADED", "unsupported-minor", "consumer"),
        # unsupported minor → BLOCKED for producer
        ({"contractVersion": "1.5"}, "BLOCKED", "unsupported-minor", "producer"),
        # missing identity → BLOCKED
        ({}, "BLOCKED", "identity-missing", "consumer"),
        # malformed identity → BLOCKED
        ({"contractVersion": "abc"}, "BLOCKED", "identity-malformed", "consumer"),
        ({"contractVersion": "1"}, "BLOCKED", "identity-malformed", "consumer"),
        ({"contractVersion": 100}, "BLOCKED", "identity-malformed", "consumer"),
    ],
)
def test_property2_fail_closed_version_matrix(
    payload: dict[str, Any],
    expected_outcome: str,
    expected_code: str,
    consumer_role: str,
) -> None:
    """Property 2 — every unknown/malformed/unsupported version fails closed.

    **Validates: Requirements 1.5**
    """
    decision = validate_contract_version(
        payload, consumer_role=consumer_role
    )
    assert decision.outcome == expected_outcome, (
        f"payload={payload!r} role={consumer_role!r} expected={expected_outcome} "
        f"got={decision.outcome} reasons={decision.reasons!r}"
    )
    assert _first_code(decision) == expected_code, (
        f"payload={payload!r} expected code={expected_code} got={_first_code(decision)}"
    )


def test_property2_missing_capability_rejects() -> None:
    """Property 2 — declared minor < required capability → REJECTED (Req 1.5).

    **Validates: Requirements 1.5**
    """
    decision = validate_contract_version(
        {"contractVersion": "1.0"}, required_minors=[1]
    )
    assert decision.outcome == "REJECTED"
    assert _first_code(decision) == "missing-capability"


def test_property2_baseline_accept() -> None:
    """Property 2 — matching version with no extras → ACCEPT (baseline).

    **Validates: Requirements 1.5**
    """
    decision = validate_contract_version({"contractVersion": "1.0"})
    assert decision.outcome == "ACCEPT"
    assert decision.negotiated_version == "1.0"


# ---------------------------------------------------------------------------
# Req 1.4 — candidate vs finalized handoff
# ---------------------------------------------------------------------------


def _read_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fixture_files() -> dict[str, dict[str, Any]]:
    return {
        "handoff_candidate": _read_fixture("handoff_candidate"),
        "handoff_finalized": _read_fixture("handoff_finalized"),
        "evidence_contract": _read_fixture("evidence_contract"),
        "evidence_catalog_entry": _read_fixture("evidence_catalog_entry"),
        "ack_accepted": _read_fixture("ack_accepted"),
        "ack_rejected": _read_fixture("ack_rejected"),
        "location_page": _read_fixture("location_page"),
        "location_sheet": _read_fixture("location_sheet"),
        "location_cell": _read_fixture("location_cell"),
        "location_whole_workbook": _read_fixture("location_whole_workbook"),
    }


def test_req1_4_candidate_handoff_shape(fixture_files) -> None:
    """Req 1.4 — candidate MUST NOT require finalizationId/confirmedBy/confirmedAt.

    **Validates: Requirements 1.4**
    """
    cand = fixture_files["handoff_candidate"]
    assert cand["phase"] == "candidate"
    # Top-level and authority-level: none of these may appear on a candidate.
    forbidden = {"finalizationId", "confirmedBy", "confirmedAt"}
    for field in forbidden:
        assert field not in cand, (
            f"candidate handoff MUST NOT carry '{field}' at top level "
            f"(Req 1.4); got {cand.get(field)!r}"
        )
        assert field not in cand["authority"], (
            f"candidate handoff.authority MUST NOT carry '{field}' "
            f"(Req 1.4); got {cand['authority'].get(field)!r}"
        )
    assert validate_contract_version(cand).outcome == "ACCEPT"


def test_req1_4_finalized_handoff_shape(fixture_files) -> None:
    """Req 1.4 — finalized handoff MUST carry finalizationId/confirmedBy/confirmedAt.

    **Validates: Requirements 1.4**
    """
    fin = fixture_files["handoff_finalized"]
    assert fin["phase"] == "finalized"
    required = {"finalizationId", "confirmedBy", "confirmedAt"}
    for field in required:
        assert field in fin, (
            f"finalized handoff MUST carry '{field}' at top level (Req 1.4)"
        )
    # authority.phase discriminator must match the top-level phase.
    assert fin["authority"]["phase"] == "finalized"
    assert validate_contract_version(fin).outcome == "ACCEPT"


# ---------------------------------------------------------------------------
# Req 1.3 — organization-level evidence does not fabricate projectId/wpId
# ---------------------------------------------------------------------------


def test_req1_3_contract_evidence_subject_never_fabricates_project_id(fixture_files) -> None:
    """Req 1.3 — ``subject.kind='contract'`` MUST NOT carry projectId/wpId.

    Organization-level evidence is a contract-level statement; fabricating a
    project/wp id would silently widen its scope. The wire schema enforces
    this via ``additionalProperties: false`` on ``_EvidenceSubject_contract``.

    **Validates: Requirements 1.3**
    """
    evidence = fixture_files["evidence_contract"]
    assert evidence["subject"]["kind"] == "contract"
    subject_keys = set(evidence["subject"].keys())
    for forbidden in ("projectId", "wpId", "entryId", "sheetUid"):
        assert forbidden not in subject_keys, (
            f"organization-level contract evidence MUST NOT carry '{forbidden}' "
            f"inside subject (Req 1.3); subject keys = {sorted(subject_keys)}"
        )


def test_req1_3_schema_blocks_additional_properties_on_contract_subject() -> None:
    """Req 1.3 — schema for ``_EvidenceSubject_contract`` denies extras.

    **Validates: Requirements 1.3**
    """
    bundle = load_bundle()
    subject = bundle.schema["definitions"]["_EvidenceSubject_contract"]
    assert subject.get("additionalProperties") is False, (
        "Contract evidence subject must have additionalProperties: false"
    )
    allowed_keys = set(subject.get("properties", {}).keys())
    for forbidden in ("projectId", "wpId", "entryId", "sheetUid"):
        assert forbidden not in allowed_keys, (
            f"schema must not declare '{forbidden}' on _EvidenceSubject_contract"
        )


# ---------------------------------------------------------------------------
# All fixtures must ACCEPT
# ---------------------------------------------------------------------------


def test_all_canonical_fixtures_accept_via_validate_contract_version(fixture_files) -> None:
    """Every fixture in ``fixtures/`` must pass the version gate."""
    for name, payload in fixture_files.items():
        decision = validate_contract_version(payload)
        assert decision.outcome == "ACCEPT", (
            f"fixture '{name}' failed gate: outcome={decision.outcome} "
            f"reasons={decision.reasons!r}"
        )


def test_fixture_file_count_matches_evidence_envelope() -> None:
    """10 canonical fixtures must be present on disk."""
    count = len(list(FIXTURES_DIR.glob("*.json")))
    assert count == 10, f"expected exactly 10 canonical fixtures, got {count}"


# ---------------------------------------------------------------------------
# Digest stability — bundle digests == evidence envelope digests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def evidence_envelope() -> dict[str, Any]:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def test_schema_sha256_matches_evidence_envelope(evidence_envelope) -> None:
    """Bundle schema sha256 must equal the digest recorded in the envelope."""
    bundle = load_bundle()
    envelope_schema_sha = evidence_envelope["sourceDigests"]["schema.json"]
    assert bundle.schema_sha256 == envelope_schema_sha, (
        f"schema.json digest mismatch: bundle={bundle.schema_sha256} "
        f"evidence={envelope_schema_sha}"
    )


def test_fixture_sha256s_match_evidence_envelope(evidence_envelope) -> None:
    """Every fixture's live digest must equal the digest recorded in the envelope."""
    bundle = load_bundle()
    expected: dict[str, str] = {
        k[len("fixtures/") :].removesuffix(".json"): v
        for k, v in evidence_envelope["sourceDigests"].items()
        if k.startswith("fixtures/")
    }
    # Every live fixture must have a matching envelope entry.
    for name, live_sha in bundle.fixture_sha256.items():
        assert name in expected, (
            f"fixture '{name}' digest missing from evidence envelope"
        )
        assert live_sha == expected[name], (
            f"fixture '{name}' digest drift: live={live_sha} "
            f"envelope={expected[name]}"
        )
    # No envelope entries may point at a fixture we no longer ship.
    for name in expected:
        assert name in bundle.fixture_sha256, (
            f"evidence envelope lists fixture '{name}' that is not on disk"
        )


# ---------------------------------------------------------------------------
# Property 1 — GC0 top-level symbols are exported and typed
# ---------------------------------------------------------------------------


def test_module_constants_are_stable() -> None:
    """Module-level constants must equal the wire schema identity."""
    assert GC0_CONTRACT_ID == "G-C0"
    assert GC0_CONTRACT_VERSION == "1.0"
    # All 8 symbols are non-empty strings.
    for sym in GC0_TOP_LEVEL_TYPES:
        assert isinstance(sym, str) and sym.isidentifier()


# ---------------------------------------------------------------------------
# Mutation self-checks M1..M5
# ---------------------------------------------------------------------------
#
# Each mutation test mutates an on-disk artefact, re-asserts the
# corresponding invariant, classifies the outcome (RED/GREEN/ANCHOR-MISS/
# WRONG-TEST), and restores the original bytes in a ``finally`` block.
#
# Classification rules
# --------------------
#   RED           — mutation caused the corresponding invariant to fail.
#                   This is the desired outcome for a good guard.
#   GREEN         — mutation passed silently. Guard has a blind spot.
#   ANCHOR-MISS   — the mutation script could not find its anchor (e.g.
#                   pattern did not match, so bytes were not changed).
#   WRONG-TEST    — a different assertion caught the mutation. Only recorded
#                   when the guard caught the wrong thing (usually still
#                   meaningful, but flagged).
#
# We do NOT use ``pytest.raises`` because the mutations are on-disk — the
# assertion must be re-evaluated by re-running the guard function on the
# mutated state, not by catching an exception from the guard itself.


class MutationOutcome:
    RED = "RED"
    GREEN = "GREEN"
    ANCHOR_MISS = "ANCHOR-MISS"
    WRONG_TEST = "WRONG-TEST"


def _assert_guard_catches(
    *,
    path: Path,
    mutate: Callable[[bytes], bytes | None],
    invariant: Callable[[], None],
    invariant_id: str,
    extra_invariants: dict[str, Callable[[], None]] | None = None,
) -> str:
    """Apply a byte-level mutation, evaluate an invariant, restore bytes.

    Returns one of :class:`MutationOutcome` values.
    """
    original = path.read_bytes()
    mutated = mutate(original)
    anchor_missed = mutated is None
    if not anchor_missed:
        path.write_bytes(mutated)
    try:
        if anchor_missed:
            return MutationOutcome.ANCHOR_MISS
        try:
            invariant()
        except AssertionError:
            # Primary invariant caught the mutation → RED.
            return MutationOutcome.RED
        # Primary invariant did NOT catch. Check secondary invariants to
        # distinguish GREEN (silent) from WRONG-TEST (other guard caught).
        if extra_invariants:
            for label, other in extra_invariants.items():
                try:
                    other()
                except AssertionError:
                    return MutationOutcome.WRONG_TEST
        return MutationOutcome.GREEN
    finally:
        path.write_bytes(original)
        # Verify restoration byte-for-byte.
        assert path.read_bytes() == original, (
            f"mutation test failed to restore bytes for {path}"
        )


def _log_outcome(name: str, outcome: str, note: str = "") -> None:
    """Emit a pytest log so the classification is visible in terminal output."""
    tag = "[gc0-mutation]"
    pytest.warns(
        UserWarning,
        match=None,
    ) if False else None  # placeholder for symmetry
    _MUTATION_RESULTS.append((name, outcome, note))
    print(f"{tag} {name}: {outcome}" + (f" — {note}" if note else ""))


# Records the outcome of each mutation for downstream reporting.
_MUTATION_RESULTS: list[tuple[str, str, str]] = []


def test_M1_schema_contract_version_bump_triggers_digest_drift() -> None:
    """M1 — schema.json ``contractVersion: 1.0`` → ``1.1`` must break digest stability.

    The mutation changes the digest, which trips ``test_schema_sha256_matches_evidence_envelope``.
    """
    def mutate(raw: bytes) -> bytes | None:
        if b'"contractVersion": "1.0"' not in raw:
            return None
        return raw.replace(b'"contractVersion": "1.0"', b'"contractVersion": "1.1"', 1)

    def invariant() -> None:
        bundle = load_bundle()
        envelope = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        assert bundle.schema_sha256 == envelope["sourceDigests"]["schema.json"], (
            "schema sha256 drifted after mutation"
        )

    outcome = _assert_guard_catches(
        path=SCHEMA_PATH,
        mutate=mutate,
        invariant=invariant,
        invariant_id="schema_sha256_matches_evidence_envelope",
    )
    _log_outcome("M1-schema-contractVersion-1.0->1.1", outcome)
    assert outcome == MutationOutcome.RED, (
        f"M1 expected RED (digest guard catches version bump), got {outcome}"
    )


def test_M2_delete_from_topLevelTypes_breaks_identity_consistency() -> None:
    """M2 — delete one entry from ``schema.topLevelTypes`` must break identity.

    The invariant is that ``schema.topLevelTypes == list(GC0_TOP_LEVEL_TYPES)``,
    so any entry removal turns it RED.
    """
    def mutate(raw: bytes) -> bytes | None:
        text = raw.decode("utf-8")
        # Drop the first ``topLevelTypes`` entry. Anchored on the array opener
        # immediately preceding the entry rather than on a fixed indentation,
        # because the anchor must survive reformatting — an indentation-tied
        # anchor produces ANCHOR-MISS (a script defect, not a guard verdict).
        # ``json.loads`` below rejects the edit if the regex hit the wrong spot.
        new_text, hits = _DROP_FIRST_TOP_LEVEL_TYPE_RE.subn(
            lambda m: m.group("open"), text, count=1
        )
        if hits != 1:
            return None
        json.loads(new_text)  # malformed edit → treat as anchor miss
        return new_text.encode("utf-8")

    def invariant() -> None:
        bundle = load_bundle()
        assert list(bundle.schema["topLevelTypes"]) == list(GC0_TOP_LEVEL_TYPES), (
            "schema.topLevelTypes drifted from module constant"
        )

    outcome = _assert_guard_catches(
        path=SCHEMA_PATH,
        mutate=mutate,
        invariant=invariant,
        invariant_id="top_level_types_match_schema_exactly",
    )
    _log_outcome("M2-delete-from-topLevelTypes", outcome)
    assert outcome == MutationOutcome.RED


def test_M3_add_projectId_to_contract_evidence_breaks_req1_3() -> None:
    """M3 — inject ``projectId`` into evidence_contract subject must break Req 1.3.

    Req 1.3 assertion: organization-level evidence subject MUST NOT carry
    projectId/wpId. Injecting projectId at subject level trips it.
    """
    evidence_file = FIXTURES_DIR / "evidence_contract.json"

    def mutate(raw: bytes) -> bytes | None:
        obj = json.loads(raw.decode("utf-8"))
        if "subject" not in obj or "kind" not in obj["subject"]:
            return None
        if obj["subject"]["kind"] != "contract":
            return None
        obj["subject"]["projectId"] = "fake-organizational-fabrication"
        return json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8")

    def invariant() -> None:
        # Mirror test_req1_3_contract_evidence_subject_never_fabricates_project_id.
        evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
        assert evidence["subject"]["kind"] == "contract"
        for forbidden in ("projectId", "wpId", "entryId", "sheetUid"):
            assert forbidden not in evidence["subject"], (
                f"subject MUST NOT carry '{forbidden}'"
            )

    outcome = _assert_guard_catches(
        path=evidence_file,
        mutate=mutate,
        invariant=invariant,
        invariant_id="req1_3_contract_evidence_subject_never_fabricates_project_id",
    )
    _log_outcome("M3-add-projectId-to-evidence-contract", outcome)
    assert outcome == MutationOutcome.RED


def test_M4_add_finalizationId_to_candidate_breaks_req1_4() -> None:
    """M4 — inject ``finalizationId`` into candidate handoff must break Req 1.4.

    Req 1.4 assertion: candidate MUST NOT carry finalizationId/confirmedBy/confirmedAt.
    """
    cand_file = FIXTURES_DIR / "handoff_candidate.json"

    def mutate(raw: bytes) -> bytes | None:
        obj = json.loads(raw.decode("utf-8"))
        if obj.get("phase") != "candidate":
            return None
        obj["finalizationId"] = "fake-candidate-fabrication"
        return json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8")

    def invariant() -> None:
        # Mirror test_req1_4_candidate_handoff_shape.
        cand = json.loads(cand_file.read_text(encoding="utf-8"))
        assert cand["phase"] == "candidate"
        for forbidden in ("finalizationId", "confirmedBy", "confirmedAt"):
            assert forbidden not in cand, (
                f"candidate MUST NOT carry '{forbidden}' at top level"
            )
            assert forbidden not in cand["authority"], (
                f"candidate.authority MUST NOT carry '{forbidden}'"
            )

    outcome = _assert_guard_catches(
        path=cand_file,
        mutate=mutate,
        invariant=invariant,
        invariant_id="req1_4_candidate_handoff_shape",
    )
    _log_outcome("M4-add-finalizationId-to-candidate", outcome)
    assert outcome == MutationOutcome.RED


def test_M5_remove_operation_variant_from_evidence_subject_breaks_discriminators() -> None:
    """M5 — remove 'operation' from EvidenceSubject variants must break discriminator equality.

    The invariant is that ``GC0_DISCRIMINATORS`` variants match the schema
    variants exactly; removing one schema variant makes the tuple differ.
    """
    def mutate(raw: bytes) -> bytes | None:
        text = raw.decode("utf-8")
        # The anchor matches from ``"discriminators": { "EvidenceSubject": { ...
        # "variants": [ "contract", "catalog_entry", "runtime_entry", "operation"``.
        # Replacing it with the same text minus ``"operation"`` (and the comma
        # that separated the two last variants) drops exactly that one variant
        # from the discriminator list. The EvidenceArtifact ``kind`` enum holds
        # the same literal, but it lives in ``definitions`` — far before the
        # ``discriminators`` object — so this forward context makes the hit
        # unique. ``json.loads`` rejects any malformed result.
        m = _DROP_OPERATION_VARIANT_RE.search(text)
        if m is None:
            return None
        new_full = m.group(0)[: -len('"operation"')]
        # Remove the trailing comma that separated "runtime_entry" and "operation".
        new_full = new_full.rstrip()
        if new_full.endswith(","):
            new_full = new_full[:-1]
        new_text = text[: m.start()] + new_full + text[m.end() :]
        json.loads(new_text)  # malformed edit → treat as anchor miss
        return new_text.encode("utf-8")

    def invariant() -> None:
        bundle = load_bundle()
        for union_name, spec in GC0_DISCRIMINATORS.items():
            entry = bundle.schema["discriminators"].get(union_name)
            if entry is None:
                raise AssertionError(f"missing discriminator '{union_name}'")
            assert tuple(entry.get("variants", ())) == spec["variants"], (
                f"discriminator '{union_name}' variants drifted"
            )

    outcome = _assert_guard_catches(
        path=SCHEMA_PATH,
        mutate=mutate,
        invariant=invariant,
        invariant_id="discriminators_match_schema_exactly",
    )
    _log_outcome("M5-remove-EvidenceSubject-operation-variant", outcome)
    assert outcome == MutationOutcome.RED


# ---------------------------------------------------------------------------
# Aggregate reporting: dump mutation outcomes to pytest terminal summary.
# ---------------------------------------------------------------------------


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print the mutation matrix at the end of the pytest session."""
    if not _MUTATION_RESULTS:
        return
    terminalreporter.section("G-C0 Mutation Self-Checks")
    for name, outcome, note in _MUTATION_RESULTS:
        suffix = f"  — {note}" if note else ""
        terminalreporter.write_line(f"  {name:<50} {outcome}{suffix}")
    # Every mutation must be RED; anything else means the guard has a gap.
    failures = [r for r in _MUTATION_RESULTS if r[1] != MutationOutcome.RED]
    if failures:
        terminalreporter.write_line(
            f"  NON-RED mutations: {[r[0] for r in failures]}"
        )
