"""G-ID registry / stable identity 守卫。

Feature: workpaper-guidance-content-closure
Validates: Requirements 2.1, 2.3, 5.3, 5.4, 5.5, 8.2, 8.3, 15.2
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.guidance_gid import (
    DEFAULT_SOURCE_REF_REGISTRY,
    FORBIDDEN_LIFECYCLE_KIND_NAMES,
    GID_CONTRACT_ID,
    GID_CONTRACT_VERSION,
    SUPPORTED_LOCATOR_KINDS,
    SourceRefRegistry,
    build_default_registry,
    build_gid_evidence_payload,
    sheet_identity_from_authority,
    validate_source_ref_via_registry,
)
from app.services.guidance_gc0_contract import discover_local_dupes
from app.services.guidance_source_refs import (
    SourceRefContext,
    TemplateAuthority,
    file_sha256,
    validate_source_ref,
)


def _ctx(repo: Path, *, visible: frozenset[str] | None = None) -> SourceRefContext:
    del visible
    return SourceRefContext(
        target_wp_code="D0",
        template_authorities=(),
        repo_root=repo,
        template_root=repo / "backend" / "wp_templates",
    )


def test_registry_registers_all_six_kinds() -> None:
    reg = build_default_registry()
    assert reg.registered_kinds == SUPPORTED_LOCATOR_KINDS


def test_unknown_kind_fail_closed() -> None:
    ctx = SourceRefContext(target_wp_code="D0", template_authorities=())
    result = validate_source_ref_via_registry({"kind": "unknown_gadget", "path": "x"}, ctx)
    assert result.valid is False
    assert result.status == "invalid"
    assert any(i.code == "kind_unknown" for i in result.issues)


def test_lifecycle_name_as_kind_fail_closed() -> None:
    ctx = SourceRefContext(target_wp_code="D0", template_authorities=())
    for name in sorted(FORBIDDEN_LIFECYCLE_KIND_NAMES):
        result = validate_source_ref({"kind": name}, ctx)
        assert result.valid is False
        assert any(i.code == "kind_is_lifecycle_not_locator" for i in result.issues)


def test_cannot_register_lifecycle_or_unknown_kind() -> None:
    reg = SourceRefRegistry()

    class Bad:
        kind = "custom_candidate"

        def validate(self, raw, context):  # noqa: ANN001
            raise AssertionError("unreachable")

        def fingerprint(self, raw, context):  # noqa: ANN001
            return "x"

    with pytest.raises(ValueError):
        reg.register(Bad())

    class Unknown:
        kind = "totally_new"

        def validate(self, raw, context):  # noqa: ANN001
            raise AssertionError("unreachable")

        def fingerprint(self, raw, context):  # noqa: ANN001
            return "x"

    with pytest.raises(ValueError):
        reg.register(Unknown())


def test_bcd_markdown_unique_heading(tmp_path: Path) -> None:
    md = tmp_path / "note.md"
    md.write_text("# Intro\n\n## Steps\n\nbody\n", encoding="utf-8")
    digest = __import__("hashlib").sha256(md.read_text(encoding="utf-8").encode()).hexdigest()
    ctx = SourceRefContext(
        target_wp_code="D0",
        template_authorities=(),
        repo_root=tmp_path,
        template_root=tmp_path / "backend" / "wp_templates",
    )
    (tmp_path / "backend" / "wp_templates").mkdir(parents=True)
    result = validate_source_ref_via_registry(
        {
            "kind": "bcd_markdown",
            "path": "note.md",
            "headingPath": ["Steps"],
            "anchor": "Steps",
            "digest": digest,
        },
        ctx,
    )
    assert result.valid is True


def test_methodology_publication_requires_lookup() -> None:
    ctx = SourceRefContext(target_wp_code="D0", template_authorities=())
    result = validate_source_ref_via_registry(
        {
            "kind": "methodology_publication",
            "publicationId": "pub-1",
            "version": 1,
            "sectionKey": "purpose",
        },
        ctx,
    )
    assert result.valid is False
    assert any(i.code == "publication_lookup_unavailable" for i in result.issues)


def test_methodology_publication_with_lookup_accepts_active() -> None:
    ctx = SimpleNamespace(
        target_wp_code="D0",
        template_authorities=(),
        target_sheet_code=None,
        target_sheet_name=None,
        repo_root=Path("."),
        template_root=Path("."),
        publication_lookup=lambda _id, _ver: {"status": "published"},
    )
    result = validate_source_ref_via_registry(
        {
            "kind": "methodology_publication",
            "publicationId": "pub-1",
            "version": 2,
            "sectionKey": "steps",
        },
        ctx,  # type: ignore[arg-type]
    )
    assert result.valid is True


def test_project_evidence_visibility_gate() -> None:
    ctx = SimpleNamespace(
        target_wp_code="D0",
        template_authorities=(),
        target_sheet_code=None,
        target_sheet_name=None,
        repo_root=Path("."),
        template_root=Path("."),
        visible_project_ids=frozenset({"proj-a"}),
    )
    ok = validate_source_ref_via_registry(
        {
            "kind": "project_evidence",
            "projectId": "proj-a",
            "evidenceId": "ev-1",
            "revision": "r1",
        },
        ctx,  # type: ignore[arg-type]
    )
    assert ok.valid is True
    denied = validate_source_ref_via_registry(
        {
            "kind": "project_evidence",
            "projectId": "proj-secret",
            "evidenceId": "ev-1",
            "revision": "r1",
        },
        ctx,  # type: ignore[arg-type]
    )
    assert denied.valid is False
    assert any(i.code == "project_not_visible" for i in denied.issues)


def test_custom_artifact_rejects_physical_path() -> None:
    ctx = SourceRefContext(target_wp_code="D0", template_authorities=())
    sha = "a" * 64
    bad = validate_source_ref_via_registry(
        {
            "kind": "custom_artifact",
            "authorityId": "auth-1",
            "artifactSha256": sha,
            "sheetUid": "s1",
            "locator": "range:A1",
            "path": "/tmp/secret.xlsx",
        },
        ctx,
    )
    assert bad.valid is False
    assert any(i.code == "physical_path_forbidden" for i in bad.issues)
    good = validate_source_ref_via_registry(
        {
            "kind": "custom_artifact",
            "authorityId": "auth-1",
            "artifactSha256": sha,
            "sheetUid": "s1",
            "locator": "region:header",
        },
        ctx,
    )
    assert good.valid is True


def test_sheet_identity_null_reason_when_uid_missing() -> None:
    ident = sheet_identity_from_authority(
        wp_code="D0",
        sheet_uid=None,
        sheet_code="D0-1",
        snapshot=None,
    )
    assert ident.sheet_uid is None
    assert ident.null_reason == "sheet_uid_unavailable"
    assert ident.wp_code == "D0"
    assert "D0" in ident.catalog_key


def test_gc0_no_local_guidance_section_dupes() -> None:
    roots = [
        Path(__file__).resolve().parents[2] / ".." / "audit-platform" / "frontend" / "src",
    ]
    ts_owner = roots[0] / "shared" / "contracts" / "gc0"
    dupes = discover_local_dupes(roots, ts_owner_dir=ts_owner)
    guidance_dupes = [d for d in dupes if d.symbol == "GuidanceSection"]
    assert guidance_dupes == [], guidance_dupes


def test_gid_evidence_payload_pass() -> None:
    payload = build_gid_evidence_payload()
    assert payload["subject"]["contractId"] == GID_CONTRACT_ID
    assert payload["contractVersions"][GID_CONTRACT_ID] == GID_CONTRACT_VERSION
    assert payload["verdict"] == "PASS"
    assert set(payload["registeredKinds"]) == SUPPORTED_LOCATOR_KINDS


def test_default_registry_singleton_complete() -> None:
    assert DEFAULT_SOURCE_REF_REGISTRY.registered_kinds == SUPPORTED_LOCATOR_KINDS
