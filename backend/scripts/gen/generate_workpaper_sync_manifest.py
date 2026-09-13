"""Generate the workpaper HTML/OnlyOffice entry manifest from source AST facts.

The Node helper discovers physical Vue mounts and the dynamic word-template dispatcher.
This generator combines those facts with the reviewed overlay. It never guesses that an
entry is bidirectional and never writes adapter/business capability data back to the overlay.

Usage from repository root::

    python backend/scripts/gen/generate_workpaper_sync_manifest.py --check
    python backend/scripts/gen/generate_workpaper_sync_manifest.py --apply
"""

from __future__ import annotations

import argparse
import copy
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]

# Requirement 1.2 profile derivation lives in production code so the same facts feed both
# this generator and the consumption-side cross-checks (RG-15/16/17). Import failures are
# fail closed on purpose: a swallowed import would silently drop the three source-backed
# fields and re-open the exact debt this generator is supposed to close.
if str(_REPO / "backend") not in sys.path:
    sys.path.insert(0, str(_REPO / "backend"))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import entry_source_facts as _facts  # noqa: E402
_FRONTEND = _REPO / "audit-platform" / "frontend"
_DISCOVERER = _FRONTEND / "scripts" / "discover-workpaper-sync-mounts.mjs"
_OVERLAY = _REPO / "backend" / "data" / "workpaper_sync_entry_overlay.json"
_MANIFEST = _REPO / "backend" / "data" / "workpaper_sync_entry_manifest.json"
_FRONTEND_TARGET = (
    _FRONTEND
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "workpaperSyncManifest.generated.ts"
)
_WORKPAPER_PREFIX = "audit-platform/frontend/src/components/workpaper/"
_CAPABILITIES = {"bidirectional", "single_html", "single_onlyoffice", "unreachable"}
_REQUIRED_ENTRY_FIELDS = {
    "entry_id",
    "mounts",
    "parent_entry_id",
    "wp_match",
    "document_type",
    "html_store",
    "canonical_resolver",
    "adapter_id",
    "capability",
    "migration_state",
    "evidence",
    # Requirement 1.2: the three source-backed profile fields plus their provenance.
    # They are listed here so a missing field fails the build closed instead of silently
    # vanishing from the manifest again (that is exactly how the Task 1 debt happened).
    "editability",
    "room_model",
    "scenario_profile",
    "profile_source",
}
#: Reviewed per-component profile expectation keys (overlay side of the two-way lock).
_EXPECTED_PROFILE_FIELDS = ("editability", "room_model", "scenario_profile_ids")

#: Curated entries declare their own migration_state (there is no discoverable mount to
#: derive one from). Kept disjoint from discovery migration_states so a curated entry can
#: never masquerade as a discovered one.
_CURATED_MIGRATION_STATES = {
    "curated_bidirectional",
    "curated_single_html",
    "curated_single_onlyoffice",
}

#: Required keys on every `curated_entries[]` declaration. Unknown keys are rejected and
#: any missing key fails the build closed (design §3.1 / §2.2).
_REQUIRED_CURATED_FIELDS = {
    "entry_id",
    "host_path",
    "curated_reason",
    "document_type",
    "wp_match",
    "html_store",
    "canonical_resolver",
    "adapter_id",
    "capability",
    "migration_state",
    "expected_profile",
    "profile",
    "evidence",
}


class ManifestGenerationError(RuntimeError):
    """Raised when source facts or reviewed overlay are incomplete."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stable_json(value: Any, *, indent: int | None = None) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
        separators=(",", ":") if indent is None else None,
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestGenerationError(f"required file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestGenerationError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ManifestGenerationError(f"JSON root must be an object: {path}")
    return value


def discover_source() -> dict[str, Any]:
    if not _DISCOVERER.is_file():
        raise ManifestGenerationError(f"source discoverer does not exist: {_DISCOVERER}")
    completed = subprocess.run(
        ["node", str(_DISCOVERER), "--json"],
        cwd=_FRONTEND,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ManifestGenerationError(f"mount discovery failed ({completed.returncode}): {detail}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ManifestGenerationError(f"mount discoverer returned invalid JSON: {exc}") from exc
    if result.get("schemaVersion") != 1:
        raise ManifestGenerationError(f"unsupported discovery schema: {result.get('schemaVersion')!r}")
    mounts = result.get("mounts")
    dispatchers = result.get("dispatchers")
    if not isinstance(mounts, list) or not mounts:
        raise ManifestGenerationError("source discovery returned an empty mount denominator")
    if not isinstance(dispatchers, list) or not dispatchers:
        raise ManifestGenerationError("source discovery returned no dynamic dispatcher facts")
    mount_ids = [item.get("mountId") for item in mounts]
    if len(set(mount_ids)) != len(mount_ids) or any(not item for item in mount_ids):
        raise ManifestGenerationError("physical mount_id values must be non-empty and unique")
    return result


def _kebab(value: str) -> str:
    first = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", value)
    second = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", first)
    return re.sub(r"[^a-zA-Z0-9]+", "-", second).strip("-").lower()


def _entry_id(document_type: str, source_file: str) -> str:
    if not source_file.startswith(_WORKPAPER_PREFIX):
        raise ManifestGenerationError(f"mount is outside workpaper source root: {source_file}")
    relative = source_file[len(_WORKPAPER_PREFIX) :]
    if relative.endswith(".vue"):
        relative = relative[:-4]
    segments = [_kebab(segment) for segment in relative.split("/")]
    if not all(segments):
        raise ManifestGenerationError(f"cannot derive stable entry id from {source_file}")
    return f"{document_type}/{'/'.join(segments)}"


def _matches(rule: dict[str, Any], *, file: str, component: str) -> bool:
    pattern = rule.get("file_glob")
    expected_component = rule.get("component")
    return (
        isinstance(pattern, str)
        and fnmatch.fnmatchcase(file, pattern)
        and (expected_component is None or expected_component == component)
    )


def _single_matching_rule(
    rules: list[dict[str, Any]], *, file: str, component: str, label: str
) -> dict[str, Any] | None:
    hits = [rule for rule in rules if _matches(rule, file=file, component=component)]
    if len(hits) > 1:
        raise ManifestGenerationError(
            f"{label} rules overlap for {file} [{component}]: "
            f"{[rule.get('file_glob') for rule in hits]}"
        )
    return hits[0] if hits else None


def _source_match(group: list[dict[str, Any]], component: str) -> dict[str, Any]:
    source_file = group[0]["file"]
    literals: set[str] = set()
    expressions: set[str] = set()
    codes: set[str] = set()
    for mount in group:
        raw_expression = mount.get("sheetExpression")
        if isinstance(raw_expression, str) and raw_expression:
            expressions.add(raw_expression)
        for attribute in mount.get("attributes") or []:
            name = str(attribute.get("argument") or attribute.get("name") or "").lower()
            if name not in {"sheet-name", "sheetname"}:
                continue
            if attribute.get("kind") == "attribute" and isinstance(attribute.get("expression"), str):
                literals.add(attribute["expression"])
    for value in [*literals, Path(source_file).stem]:
        codes.update(
            match.upper()
            for match in re.findall(r"[A-Z][0-9]+(?:-[0-9]+)*(?:[A-Z])?", value, re.I)
        )
    component_types: list[str] = []
    if component == "WorkpaperWordEditor" and any(
        mount.get("sourceKind") == "registry_ast" for mount in group
    ):
        component_types.append("word-template")
    if component == "GtOnlyOfficeSheet" and Path(source_file).name == "GtWpRenderer.vue":
        component_types.append("onlyoffice-sheet")
    return {
        "wp_code_patterns": sorted(codes),
        "component_types": component_types,
        "sheet_literals": sorted(literals),
        "sheet_expressions": sorted(expressions),
        "source_host": source_file,
    }


def _merge_override(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key in ("html_store", "canonical_resolver", "adapter_id", "capability", "migration_state"):
        if key in override:
            result[key] = copy.deepcopy(override[key])
    patch = override.get("evidence_patch")
    if patch is not None:
        if not isinstance(patch, dict):
            raise ManifestGenerationError("evidence_patch must be an object")
        result.setdefault("evidence", {}).update(copy.deepcopy(patch))
    return result


def _group_source_facts(discovery: dict[str, Any]) -> list[list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for fact in [*discovery["mounts"], *discovery["dispatchers"]]:
        file = fact.get("file")
        component = fact.get("component")
        if not isinstance(file, str) or not isinstance(component, str):
            raise ManifestGenerationError("every source fact needs file and component")
        groups[(file, component)].append(fact)
    return [
        sorted(items, key=lambda item: (item.get("sourceSpan", {}).get("startLine", 0), item["mountId"]))
        for _, items in sorted(groups.items())
    ]


def _assert_profile_in_expected(
    *,
    entry_id: str,
    profile_values: dict[str, tuple[str, str]],
    expectation: Any,
    origin: str,
    label: str,
) -> None:
    """Shared two-way profile lock: reviewed `expectation` vs a concrete profile value set.

    `profile_values` maps each `_EXPECTED_PROFILE_FIELDS` key to a `(actual, provenance)`
    pair. The discovery path passes source-derived values (provenance = the source fact);
    the curated path passes reviewer-declared values (provenance = the declared block). In
    both cases the actual value MUST appear in the reviewed `expectation[field]` list, so
    the overlay can never downgrade/rot a required scenario and neither side drifts silently.

    This is a pure structural check with no dependency on how the values were obtained, so
    the discovery caller stays byte-identical after the extraction.
    """
    if not isinstance(expectation, dict):
        raise ManifestGenerationError(
            f"entry {entry_id}: overlay {origin} has no reviewed expected_profile object; "
            "the source-backed profile must be reviewed, not inferred silently"
        )
    unknown = sorted(set(expectation) - set(_EXPECTED_PROFILE_FIELDS) - {"review_note"})
    if unknown:
        raise ManifestGenerationError(f"overlay {origin}.expected_profile has unknown keys: {unknown}")
    for field in _EXPECTED_PROFILE_FIELDS:
        if field not in expectation:
            raise ManifestGenerationError(f"overlay {origin}.expected_profile misses {field!r}")
    for field in _EXPECTED_PROFILE_FIELDS:
        actual, fact = profile_values[field]
        approved = expectation[field]
        if not isinstance(approved, list) or not approved or any(
            not isinstance(item, str) or not item for item in approved
        ):
            raise ManifestGenerationError(
                f"overlay {origin}.expected_profile.{field} must be a non-empty string array"
            )
        if actual not in approved:
            raise ManifestGenerationError(
                f"entry {entry_id} ({label}): {field}={actual!r} "
                f"via {fact}, which is not in the reviewed set {sorted(approved)} - review the "
                "source diff instead of widening the reviewed set"
            )


def _assert_expected_profile(
    *,
    entry_id: str,
    component: str,
    derived: Any,
    expectation: Any,
    origin: str,
) -> None:
    """Reviewed expectation vs derived source fact - a two-way lock, not a fallback.

    The overlay records what the reviewer approved for a component; the generator still
    derives every value from source. A mismatch is an error, so the overlay can never
    downgrade a required scenario (Requirement 1.2 forbids free text / drifting booleans
    from deciding the profile), and the reviewed side can never silently rot either.

    Delegates the membership logic to `_assert_profile_in_expected` so discovery and curated
    entries validate profile-vs-expected through the same code (design §3.2 step 6).
    """
    _assert_profile_in_expected(
        entry_id=entry_id,
        profile_values={
            "editability": (
                derived.editability.value,
                derived.profile_source["editability_fact"],
            ),
            "room_model": (
                derived.room_model.value,
                derived.profile_source["room_model_fact"],
            ),
            "scenario_profile_ids": (derived.scenario_profile_id, "scenario_profile"),
        },
        expectation=expectation,
        origin=origin,
        label=component,
    )


def _build_curated_entries(
    overlay: dict[str, Any],
    *,
    discovered_host_paths: set[str],
    discovery_entry_ids: set[str],
) -> list[dict[str, Any]]:
    """Emit synthetic manifest entries from the reviewed `overlay.curated_entries` section.

    Additive facility (design §3.2): a single dynamic host (e.g. GtD4OperatingRevenue.vue)
    can back several logical sheets, but discovery derives exactly one entry per host. A
    curated entry lets a reviewer declare an extra logical entry that rides on a real host.

    Every gate is fail-closed and raises `ManifestGenerationError`; a partial or guessed
    curated entry is never emitted. Curated entries hold to the SAME capability discipline
    as discovery entries — a curated entry can never silently claim `bidirectional`.
    """
    curated = overlay.get("curated_entries")
    if curated is None:
        return []
    if not isinstance(curated, list) or any(not isinstance(item, dict) for item in curated):
        raise ManifestGenerationError("overlay.curated_entries must be an array of objects")

    entries: list[dict[str, Any]] = []
    seen_curated_ids: set[str] = set()
    for declaration in curated:
        keys = set(declaration)
        missing = _REQUIRED_CURATED_FIELDS - keys
        if missing:
            raise ManifestGenerationError(
                f"curated entry misses required fields: {sorted(missing)}"
            )
        unknown = sorted(keys - _REQUIRED_CURATED_FIELDS)
        if unknown:
            raise ManifestGenerationError(
                f"curated entry {declaration.get('entry_id')!r} has unknown keys: {unknown}"
            )

        entry_id = declaration["entry_id"]
        if not isinstance(entry_id, str) or not entry_id:
            raise ManifestGenerationError("curated entry_id must be a non-empty string")
        # Requirement 1.4: curated ids disjoint from discovery ids and from each other.
        if entry_id in discovery_entry_ids:
            raise ManifestGenerationError(
                f"curated entry_id collides with a discovery entry_id: {entry_id}"
            )
        if entry_id in seen_curated_ids:
            raise ManifestGenerationError(f"duplicate curated entry_id: {entry_id}")
        seen_curated_ids.add(entry_id)

        # Requirement 1.5: a curated entry must ride a real discovered host.
        host_path = declaration["host_path"]
        if not isinstance(host_path, str) or host_path not in discovered_host_paths:
            raise ManifestGenerationError(
                f"curated entry {entry_id} references host_path not produced by discovery: "
                f"{host_path!r}"
            )

        document_type = declaration["document_type"]
        if document_type not in {"xlsx", "docx"}:
            raise ManifestGenerationError(
                f"curated entry {entry_id} has invalid document_type: {document_type!r}"
            )

        migration_state = declaration["migration_state"]
        if migration_state not in _CURATED_MIGRATION_STATES:
            raise ManifestGenerationError(
                f"curated entry {entry_id} migration_state must be one of "
                f"{sorted(_CURATED_MIGRATION_STATES)}: {migration_state!r}"
            )

        # Requirement 2.1: capability comes from the reviewed overlay, never inferred.
        capability = declaration["capability"]
        if capability not in _CAPABILITIES:
            raise ManifestGenerationError(
                f"curated entry {entry_id} has invalid capability: {capability!r}"
            )

        evidence = declaration["evidence"]
        if not isinstance(evidence, dict):
            raise ManifestGenerationError(f"curated entry {entry_id} evidence must be an object")
        # Requirement 2.4: an unreviewed curated declaration fails closed.
        if not evidence.get("review_status"):
            raise ManifestGenerationError(
                f"curated entry {entry_id} is not reviewed (evidence.review_status empty)"
            )

        adapter_id = declaration["adapter_id"]
        html_store = declaration["html_store"]
        # Requirement 2.2: a curated entry cannot silently claim bidirectional.
        if capability == "bidirectional":
            if not adapter_id:
                raise ManifestGenerationError(
                    f"curated bidirectional entry {entry_id} requires a non-empty adapter_id"
                )
            if not html_store or html_store == "unresolved":
                raise ManifestGenerationError(
                    f"curated bidirectional entry {entry_id} requires a resolved html_store"
                )
            if not evidence.get("contract_test"):
                raise ManifestGenerationError(
                    f"curated bidirectional entry {entry_id} requires evidence.contract_test"
                )

        # Requirement 2.3: declared profile validated against reviewed expected_profile using
        # the SAME membership logic as discovery entries (shared _assert_profile_in_expected).
        profile = declaration["profile"]
        if not isinstance(profile, dict):
            raise ManifestGenerationError(f"curated entry {entry_id} profile must be an object")
        for field in ("editability", "room_model", "scenario_profile_id"):
            if not isinstance(profile.get(field), str) or not profile.get(field):
                raise ManifestGenerationError(
                    f"curated entry {entry_id} profile.{field} must be a non-empty string"
                )
        _assert_profile_in_expected(
            entry_id=entry_id,
            profile_values={
                "editability": (profile["editability"], "curated profile.editability"),
                "room_model": (profile["room_model"], "curated profile.room_model"),
                "scenario_profile_ids": (
                    profile["scenario_profile_id"],
                    "curated profile.scenario_profile_id",
                ),
            },
            expectation=declaration["expected_profile"],
            origin=f"curated_entries[{entry_id}]",
            label="curated",
        )

        wp_match = declaration["wp_match"]
        if not isinstance(wp_match, dict):
            raise ManifestGenerationError(f"curated entry {entry_id} wp_match must be an object")

        # Mirror the discovery-entry schema so registry/frontend treat both uniformly. Curated
        # entries carry no template_ast mounts (mounts=[]), so they never contribute to the
        # `manifest_mount_ids == source_mount_ids` check (that check filters template_ast).
        entry = {
            "entry_id": entry_id,
            "host_path": host_path,
            "mounts": [],
            "independent_entry": True,
            "parent_entry_id": None,
            "wp_match": copy.deepcopy(wp_match),
            "document_type": document_type,
            "html_store": html_store,
            "canonical_resolver": declaration["canonical_resolver"],
            "adapter_id": adapter_id,
            "capability": capability,
            "migration_state": migration_state,
            "evidence": copy.deepcopy(evidence),
            # source-backed profile fields, mirrored from the reviewed declared profile block.
            "editability": profile["editability"],
            "room_model": profile["room_model"],
            "scenario_profile": {"profile_id": profile["scenario_profile_id"]},
            "profile_source": {"curated_reason": declaration["curated_reason"]},
        }
        missing_fields = _REQUIRED_ENTRY_FIELDS - entry.keys()
        if missing_fields:
            raise ManifestGenerationError(
                f"curated entry {entry_id} misses fields: {sorted(missing_fields)}"
            )
        entries.append(entry)
    return entries


def build_manifest(discovery: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    # Fail closed before deriving anything: if the derivation ever starts reading capability
    # (or any other reviewed business field), RG-15/16/17 degrade into tautologies that can
    # never detect drift again.
    try:
        _facts.assert_derivation_ignores_business_adjudication()
    except _facts.EntrySourceFactError as exc:
        raise ManifestGenerationError(str(exc)) from exc
    if overlay.get("schema_version") != 1 or overlay.get("review_status") != "reviewed":
        raise ManifestGenerationError("overlay must use schema_version=1 and review_status='reviewed'")
    approved_source_digest = overlay.get("approved_source_digest")
    if approved_source_digest != discovery.get("sourceDigest"):
        raise ManifestGenerationError(
            "source mounts changed since the reviewed overlay: "
            f"approved={approved_source_digest!r} current={discovery.get('sourceDigest')!r}; "
            "review the mount diff before updating approved_source_digest"
        )
    defaults = overlay.get("defaults_by_component")
    if not isinstance(defaults, dict):
        raise ManifestGenerationError("overlay.defaults_by_component must be an object")
    parent_rules = overlay.get("parent_rules") or []
    unreachable_rules = overlay.get("unreachable_rules") or []
    overrides = overlay.get("overrides") or []
    for name, value in (
        ("parent_rules", parent_rules),
        ("unreachable_rules", unreachable_rules),
        ("overrides", overrides),
    ):
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ManifestGenerationError(f"overlay.{name} must be an array of objects")

    entries: list[dict[str, Any]] = []
    matched_rule_ids: Counter[tuple[str, int]] = Counter()
    seen_entry_ids: set[str] = set()
    used_expectations: dict[str, dict[str, set[str]]] = {}
    for group in _group_source_facts(discovery):
        source_file = group[0]["file"]
        component = group[0]["component"]
        document_types = {item.get("documentType") for item in group}
        if len(document_types) != 1 or document_types.pop() not in {"xlsx", "docx"}:
            raise ManifestGenerationError(f"inconsistent document type for {source_file} [{component}]")
        document_type = group[0]["documentType"]
        default = defaults.get(component)
        if not isinstance(default, dict):
            raise ManifestGenerationError(f"overlay has no reviewed default for {component}")

        entry_id = _entry_id(document_type, source_file)
        if entry_id in seen_entry_ids:
            raise ManifestGenerationError(f"stable entry_id collision: {entry_id}")
        seen_entry_ids.add(entry_id)

        parent_rule = _single_matching_rule(
            parent_rules, file=source_file, component=component, label="parent"
        )
        unreachable_rule = _single_matching_rule(
            unreachable_rules, file=source_file, component=component, label="unreachable"
        )
        if parent_rule and unreachable_rule:
            raise ManifestGenerationError(f"entry cannot be both parent duplicate and unreachable: {entry_id}")

        value = copy.deepcopy(default)
        matching_overrides = [
            (index, item)
            for index, item in enumerate(overrides)
            if _matches(item, file=source_file, component=component)
        ]
        if len(matching_overrides) > 1:
            raise ManifestGenerationError(f"overrides overlap for {entry_id}")
        if matching_overrides:
            index, override = matching_overrides[0]
            matched_rule_ids[("overrides", index)] += 1
            value = _merge_override(value, override)

        independent = True
        parent_entry_id = None
        if parent_rule:
            index = parent_rules.index(parent_rule)
            matched_rule_ids[("parent_rules", index)] += 1
            independent = False
            parent_entry_id = parent_rule.get("parent_entry_id")
            value["adapter_id"] = None
            value["migration_state"] = "parent_duplicate"
            value.setdefault("evidence", {})["parent_reason"] = parent_rule.get("reason")
        if unreachable_rule:
            index = unreachable_rules.index(unreachable_rule)
            matched_rule_ids[("unreachable_rules", index)] += 1
            independent = False
            value["adapter_id"] = None
            value["capability"] = "unreachable"
            value["migration_state"] = "unreachable_pending_delete"
            value.setdefault("evidence", {})["unreachable_reason"] = unreachable_rule.get("reason")

        capability = value.get("capability")
        if capability not in _CAPABILITIES:
            raise ManifestGenerationError(f"invalid capability for {entry_id}: {capability!r}")
        evidence = value.get("evidence")
        if not isinstance(evidence, dict) or not evidence.get("review_status"):
            raise ManifestGenerationError(f"entry evidence is not reviewed: {entry_id}")

        entry = {
            "entry_id": entry_id,
            "host_path": source_file,
            "mounts": copy.deepcopy(group),
            "independent_entry": independent,
            "parent_entry_id": parent_entry_id,
            "wp_match": _source_match(group, component),
            "document_type": document_type,
            "html_store": value.get("html_store"),
            "canonical_resolver": value.get("canonical_resolver"),
            "adapter_id": value.get("adapter_id"),
            "capability": capability,
            "migration_state": value.get("migration_state"),
            "evidence": evidence,
        }
        # Requirement 1.2: derive editability / room_model / scenario_profile from source
        # facts only. The derivation signature carries no business adjudication field, so
        # capability stays an independent cross-check (RG-15) instead of a tautology.
        try:
            host_facts = _facts.host_source_facts(
                entry_id=entry_id,
                host_path=source_file,
                document_type=document_type,
                mounts=group,
            )
            derived = _facts.derive_entry_profile(host_facts)
        except _facts.EntrySourceFactError as exc:
            raise ManifestGenerationError(f"entry {entry_id}: {exc}") from exc
        entry.update(derived.as_entry_fields())
        if bool(unreachable_rule) != (not host_facts.host_reachable):
            raise ManifestGenerationError(
                f"entry {entry_id}: reviewed unreachable_rule={bool(unreachable_rule)} but "
                f"source inbound references={len(host_facts.inbound_references)} "
                f"({host_facts.inbound_references[:3]}); the reviewed adjudication and the "
                "source reachability fact must agree (Requirement 1.7)"
            )
        _assert_expected_profile(
            entry_id=entry_id,
            component=component,
            derived=derived,
            expectation=(unreachable_rule or default).get("expected_profile"),
            origin="unreachable_rules" if unreachable_rule else f"defaults_by_component.{component}",
        )
        origin_key = "unreachable_rules" if unreachable_rule else component
        seen = used_expectations.setdefault(origin_key, {field: set() for field in _EXPECTED_PROFILE_FIELDS})
        seen["editability"].add(derived.editability.value)
        seen["room_model"].add(derived.room_model.value)
        seen["scenario_profile_ids"].add(derived.scenario_profile_id)
        missing = _REQUIRED_ENTRY_FIELDS - entry.keys()
        if missing:
            raise ManifestGenerationError(f"entry {entry_id} misses fields: {sorted(missing)}")
        entries.append(entry)

    for section_name, rules in (
        ("parent_rules", parent_rules),
        ("unreachable_rules", unreachable_rules),
        ("overrides", overrides),
    ):
        stale = [
            rule.get("file_glob")
            for index, rule in enumerate(rules)
            if matched_rule_ids[(section_name, index)] == 0
        ]
        if stale:
            raise ManifestGenerationError(f"stale overlay {section_name}: {stale}")

    # Every reviewed profile value must actually be derived by at least one entry, mirroring
    # the stale-rule gate above: an approved value nobody derives any more is a review
    # statement about a source shape that no longer exists.
    for origin, declared in _declared_expectations(overlay).items():
        used = used_expectations.get(origin) or {}
        for field, values in declared.items():
            stale_values = sorted(set(values) - used.get(field, set()))
            if stale_values:
                raise ManifestGenerationError(
                    f"stale reviewed expected_profile.{field} for {origin}: {stale_values} "
                    f"(derived from source: {sorted(used.get(field, set()))})"
                )

    # Curated entries (design §3.3): appended AFTER the discovery loop and AFTER the
    # stale-rule gates so the discovery path is entirely unchanged. Each rides on a real
    # discovered host and holds to the same fail-closed capability discipline. The builder
    # gates entry_id collision itself; we re-assert disjointness at merge as defense-in-depth
    # (Requirement 1.4, redundant with the builder's own check).
    discovered_host_paths = {entry["host_path"] for entry in entries}
    discovery_entry_ids = set(seen_entry_ids)
    curated_entries = _build_curated_entries(
        overlay,
        discovered_host_paths=discovered_host_paths,
        discovery_entry_ids=discovery_entry_ids,
    )
    if curated_entries:
        curated_ids = {entry["entry_id"] for entry in curated_entries}
        collisions = curated_ids & discovery_entry_ids
        if collisions:
            raise ManifestGenerationError(
                f"curated entry_ids collide with discovery entry_ids at merge: {sorted(collisions)}"
            )
        # A curated entry has no discoverable second mount to derive `room_service_state`
        # from, but the manifest requires exactly ONE global `room_service_state` across all
        # entries. So each curated entry adopts the single global source fact derived from the
        # discovery entries (their profile_id already encodes the same `room_service_wired`
        # state). This keeps the single-global invariant true and gives render_frontend the
        # field it reads. Deriving it from discovery (not the declaration) means a curated
        # entry can never introduce a second global service state.
        global_room_service_states = {
            entry["scenario_profile"]["room_service_state"] for entry in entries
        }
        if len(global_room_service_states) != 1:
            raise ManifestGenerationError(
                "cannot stamp curated entries: discovery room_service_state is not a single "
                f"global fact, got {sorted(global_room_service_states)}"
            )
        global_room_service_state = next(iter(global_room_service_states))
        for entry in curated_entries:
            entry["scenario_profile"]["room_service_state"] = global_room_service_state
        entries.extend(curated_entries)

    by_id = {entry["entry_id"]: entry for entry in entries}
    for entry in entries:
        parent_id = entry["parent_entry_id"]
        if parent_id is None:
            continue
        parent = by_id.get(parent_id)
        if parent is None:
            raise ManifestGenerationError(f"parent entry does not exist: {entry['entry_id']} -> {parent_id}")
        if not parent["independent_entry"]:
            raise ManifestGenerationError(f"parent entry is not independent: {parent_id}")
        if parent["document_type"] != entry["document_type"]:
            raise ManifestGenerationError(f"parent document type mismatch: {entry['entry_id']}")

    physical_mounts = discovery["mounts"]
    source_mount_ids = {item["mountId"] for item in physical_mounts}
    manifest_mount_ids = {
        item["mountId"]
        for entry in entries
        for item in entry["mounts"]
        if item.get("sourceKind") == "template_ast"
    }
    if manifest_mount_ids != source_mount_ids:
        raise ManifestGenerationError(
            "manifest/source mount sets differ: "
            f"missing={sorted(source_mount_ids - manifest_mount_ids)} "
            f"extra={sorted(manifest_mount_ids - source_mount_ids)}"
        )

    capability_counts = Counter(entry["capability"] for entry in entries)
    editability_counts = Counter(entry["editability"] for entry in entries)
    room_model_counts = Counter(entry["room_model"] for entry in entries)
    profile_counts = Counter(entry["scenario_profile"]["profile_id"] for entry in entries)
    room_service_states = {
        entry["scenario_profile"]["room_service_state"] for entry in entries
    }
    if len(room_service_states) != 1:
        raise ManifestGenerationError(
            f"room_service_state must be one global source fact, got {sorted(room_service_states)}"
        )
    stats = {
        "host_count": len({item["file"] for item in physical_mounts}),
        "mount_count": len(physical_mounts),
        "dispatcher_count": len(discovery["dispatchers"]),
        "entry_count": len(entries),
        "independent_entry_count": sum(entry["independent_entry"] for entry in entries),
        "parent_duplicate_count": sum(entry["parent_entry_id"] is not None for entry in entries),
        "unreachable_count": capability_counts["unreachable"],
        "unadjudicated_count": sum(
            entry["html_store"] == "unresolved" for entry in entries if entry["independent_entry"]
        ),
        "legacy_fake_bidirectional_count": sum(
            entry["migration_state"] == "legacy_fake_bidirectional" for entry in entries
        ),
        "capability_counts": dict(sorted(capability_counts.items())),
        "editability_counts": dict(sorted(editability_counts.items())),
        "room_model_counts": dict(sorted(room_model_counts.items())),
        "scenario_profile_counts": dict(sorted(profile_counts.items())),
        "room_service_state": sorted(room_service_states)[0],
        "by_component": discovery["stats"]["byComponent"],
    }
    # Requirement 3.3 / design §3.4: expose how many curated entries were emitted. Curated
    # entries already count toward entry_count / independent_entry_count / capability_counts /
    # editability / room_model / scenario_profile counts above because they are in `entries`.
    # But `curated_entry_count` is ONLY added when non-zero: including it as 0 would change the
    # pre-facility baseline bytes and violate the Requirement 1.3 "byte-identical to current
    # output" invariant (same omit-when-zero treatment as curated_source_digest).
    if curated_entries:
        stats["curated_entry_count"] = len(curated_entries)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "source_digest": discovery["sourceDigest"],
        # `_overlay_digest` normalizes an empty/absent `curated_entries` out of the overlay so
        # `[]` and absent both hash to the pre-facility overlay bytes (Requirement 1.3 byte-
        # identity). A non-empty curated list stays in and is also locked via curated_source_digest.
        "overlay_digest": _overlay_digest(overlay),
        # Requirement 1.2 / design: the source-backed profile fields AND their provenance
        # digest both participate in `manifest_digest`. `source_digest` stays the reviewed
        # mount inventory digest so the overlay's `approved_source_digest` gate is untouched.
        "profile_source_digest": _profile_source_digest(entries),
        "stats": stats,
        "entries": sorted(entries, key=lambda item: item["entry_id"]),
    }
    # Requirement 3.1: the reviewed curated declarations participate in `manifest_digest`.
    # Requirement 1.3 / design §3.4: the key is ONLY added when curated is non-empty, so the
    # empty/absent case stays byte-identical to the pre-facility manifest.
    if curated_entries:
        manifest["curated_source_digest"] = _curated_source_digest(
            overlay.get("curated_entries") or []
        )
    manifest["manifest_digest"] = _sha256_bytes(_stable_json(manifest).encode("utf-8"))
    return manifest


def _declared_expectations(overlay: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    declared: dict[str, dict[str, list[str]]] = {}
    for component, default in (overlay.get("defaults_by_component") or {}).items():
        expectation = (default or {}).get("expected_profile") or {}
        declared[component] = {
            field: list(expectation.get(field) or []) for field in _EXPECTED_PROFILE_FIELDS
        }
    merged: dict[str, list[str]] = {field: [] for field in _EXPECTED_PROFILE_FIELDS}
    for rule in overlay.get("unreachable_rules") or []:
        expectation = (rule or {}).get("expected_profile") or {}
        for field in _EXPECTED_PROFILE_FIELDS:
            merged[field].extend(expectation.get(field) or [])
    if any(merged.values()):
        declared["unreachable_rules"] = merged
    return declared


def _curated_source_digest(curated: list[dict[str, Any]]) -> str:
    """sha256 over the stable-JSON of the sorted reviewed curated declarations.

    Locks the reviewed curated section into `manifest_digest` (Requirement 3.1): adding,
    removing, or editing a declaration changes this digest deterministically (Property 4).
    Sorting by `entry_id` makes the digest order-independent so a pure reorder of the
    overlay array does not spuriously churn the manifest. The empty case is handled by the
    caller (the key is omitted when `curated` is empty) so byte-identity holds (Requirement
    1.3); this function is only ever called with a non-empty list.
    """
    payload = sorted(curated, key=lambda item: item.get("entry_id") or "")
    return _sha256_bytes(_stable_json(payload).encode("utf-8"))


def _overlay_digest(overlay: dict[str, Any]) -> str:
    """`overlay_digest` over the overlay with an empty/absent `curated_entries` normalized out.

    `overlay_digest` covers the whole reviewed overlay so drift in any reviewed field is
    detected. But the curated facility is additive: an empty (or absent) `curated_entries`
    MUST leave the manifest byte-identical to the pre-facility output (Requirement 1.3 /
    Property 1). Since `overlay_digest` feeds `manifest_digest`, a literal `curated_entries: []`
    would otherwise change the digest and break byte-identity. So we drop an empty curated
    list before hashing: absent and `[]` both hash to the exact pre-facility overlay bytes.
    A non-empty curated list stays in the overlay bytes AND is separately locked via
    `curated_source_digest`, so real declarations still participate in the digest.
    """
    curated = overlay.get("curated_entries")
    if curated:
        return _sha256_bytes(_stable_json(overlay).encode("utf-8"))
    normalized = {key: value for key, value in overlay.items() if key != "curated_entries"}
    return _sha256_bytes(_stable_json(normalized).encode("utf-8"))


def _profile_source_digest(entries: list[dict[str, Any]]) -> str:
    payload = [
        {
            "entry_id": entry["entry_id"],
            "editability": entry["editability"],
            "room_model": entry["room_model"],
            "scenario_profile": entry["scenario_profile"],
            "profile_source": entry["profile_source"],
        }
        for entry in sorted(entries, key=lambda item: item["entry_id"])
    ]
    return _sha256_bytes(_stable_json(payload).encode("utf-8"))


def render_manifest(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _ts_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def render_frontend(manifest: dict[str, Any]) -> str:
    projection = []
    for entry in manifest["entries"]:
        evidence = entry["evidence"]
        projection.append(
            {
                "entryId": entry["entry_id"],
                "hostPath": entry["host_path"],
                "documentType": entry["document_type"],
                "capability": entry["capability"],
                "migrationState": entry["migration_state"],
                "independentEntry": entry["independent_entry"],
                "parentEntryId": entry["parent_entry_id"],
                "wpMatch": entry["wp_match"],
                # Requirement 1.2: the source-backed profile must reach the frontend too,
                # so the UI cannot claim a room protocol / editability the source does not have.
                "editability": entry["editability"],
                "roomModel": entry["room_model"],
                "scenarioProfileId": entry["scenario_profile"]["profile_id"],
                "roomServiceState": entry["scenario_profile"]["room_service_state"],
                "reasonCodes": evidence.get("legacy_reasons") or [],
                "hasContractEvidence": bool(evidence.get("contract_test")),
                "hasBrowserEvidence": bool(evidence.get("browser_case")),
            }
        )
    projection_json = json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True)
    stats_json = json.dumps(manifest["stats"], ensure_ascii=False, indent=2, sort_keys=True)
    return f"""/**
 * 本文件由 `backend/scripts/gen/generate_workpaper_sync_manifest.py` 生成，请勿手工编辑。
 * 业务裁决真源：`backend/data/workpaper_sync_entry_overlay.json`。
 * 源码事实真源：Vue template AST + htmlRendererRegistry 的 word-template dispatcher。
 */

export type WorkpaperSyncCapability =
  | 'bidirectional'
  | 'single_html'
  | 'single_onlyoffice'
  | 'unreachable'

/** source-backed，与 V151 `working_paper_sync_test_run.editability` 的 CHECK 同域。 */
export type WorkpaperSyncEditability = 'editable' | 'readonly' | 'unreachable'

/** source-backed，与 V151 `working_paper_sync_test_run.room_model` 的 CHECK 同域。 */
export type WorkpaperSyncRoomModel = 'shared' | 'exclusive' | 'none'

export interface WorkpaperSyncManifestEntry {{
  entryId: string
  hostPath: string
  documentType: 'xlsx' | 'docx'
  capability: WorkpaperSyncCapability
  migrationState: string
  independentEntry: boolean
  parentEntryId: string | null
  wpMatch: {{
    wp_code_patterns: string[]
    component_types: string[]
    sheet_literals: string[]
    sheet_expressions: string[]
    source_host: string
  }}
  editability: WorkpaperSyncEditability
  roomModel: WorkpaperSyncRoomModel
  scenarioProfileId: string
  roomServiceState: string
  reasonCodes: string[]
  hasContractEvidence: boolean
  hasBrowserEvidence: boolean
}}

export const WORKPAPER_SYNC_MANIFEST_DIGEST = {_ts_string(manifest['manifest_digest'])}

export const WORKPAPER_SYNC_PROFILE_SOURCE_DIGEST = {_ts_string(manifest['profile_source_digest'])}

export const WORKPAPER_SYNC_MANIFEST_STATS = {stats_json} as const

export const WORKPAPER_SYNC_MANIFEST = {projection_json} as const satisfies readonly WorkpaperSyncManifestEntry[]
"""


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _print_stats(label: str, manifest: dict[str, Any]) -> None:
    stats = manifest["stats"]
    print(
        f"[{label}] hosts={stats['host_count']} mounts={stats['mount_count']} "
        f"dispatchers={stats['dispatcher_count']} entries={stats['entry_count']} "
        f"independent={stats['independent_entry_count']} "
        f"parent_duplicates={stats['parent_duplicate_count']} "
        f"unadjudicated={stats['unadjudicated_count']} "
        f"unreachable={stats['unreachable_count']}"
    )
    print(f"[{label}] by_component={stats['by_component']}")
    print(
        f"[{label}] editability={stats['editability_counts']} room_model={stats['room_model_counts']} "
        f"room_service={stats['room_service_state']}"
    )
    print(f"[{label}] scenario_profiles={stats['scenario_profile_counts']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify both generated artifacts")
    mode.add_argument("--apply", action="store_true", help="atomically regenerate both artifacts")
    args = parser.parse_args(argv)

    discovery = discover_source()
    overlay = _read_json(_OVERLAY)
    manifest = build_manifest(discovery, overlay)
    manifest_content = render_manifest(manifest)
    frontend_content = render_frontend(manifest)
    _print_stats("SOURCE", manifest)

    expected = ((_MANIFEST, manifest_content), (_FRONTEND_TARGET, frontend_content))
    if args.check:
        failures = []
        for path, content in expected:
            if not path.is_file():
                failures.append(f"missing: {path.relative_to(_REPO)}")
            elif path.read_text(encoding="utf-8") != content:
                failures.append(f"stale: {path.relative_to(_REPO)}")
        if failures:
            print("[FAIL] generated artifacts do not match reviewed source facts:")
            for failure in failures:
                print(f"  - {failure}")
            return 2
        _print_stats("CHECKED", manifest)
        print(f"[OK] manifest digest {manifest['manifest_digest']}")
        return 0

    for path, content in expected:
        _atomic_write(path, content)
        print(f"[APPLIED] {path.relative_to(_REPO)} sha256={_sha256_bytes(content.encode('utf-8'))[:16]}")
    _print_stats("GENERATED", manifest)
    print(f"[OK] manifest digest {manifest['manifest_digest']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManifestGenerationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
