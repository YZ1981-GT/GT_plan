"""component capability manifest 的生成、加载与反向自检契约。"""
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.services.component_capability_registry import (
    ComponentCapabilityManifestError,
    DEFAULT_MANIFEST_PATH,
    load_component_capability_registry,
)
from scripts.gen.generate_component_capability_manifest import (
    DEFAULT_SOURCE_PATHS,
    TYPESCRIPT_PROJECTION_PATH,
    SourceExtractionError,
    build_manifest,
    check_manifest,
    extract_html_registry_types,
    extract_observed_sources,
    render_manifest,
    render_typescript_projection,
)


def _entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "owner": "workpaper-rendering",
        "has_backend_renderer": True,
        "has_frontend_component": True,
        "override_allowed": True,
        "host_policy": "html",
        "status": "active",
        "sources": [
            "VALID_COMPONENT_TYPES",
            "RENDERER_DISPATCH",
            "REGISTRY_LIST",
        ],
    }
    entry.update(overrides)
    return entry


def _write_manifest(path: Path, *, entry: dict[str, object] | None = None) -> None:
    payload = {
        "schema_version": 1,
        "components": {"sample-component": entry or _entry()},
        "exemptions": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_domain_split_registry(
    tmp_path: Path,
    *,
    domain_files: dict[str, str],
    spreads: list[str] | None = None,
    comments: str = "",
) -> Path:
    """Synthetic domain-split registry (entries/*.ts + barrel spreads)."""

    registry_dir = tmp_path / "registry"
    entries_dir = registry_dir / "entries"
    entries_dir.mkdir(parents=True)
    for domain, body in domain_files.items():
        (entries_dir / f"{domain}.ts").write_text(body, encoding="utf-8")
    if spreads is None:
        spreads = [f"...{name}Entries" for name in domain_files]
    barrel = registry_dir / "index.ts"
    barrel.write_text(
        f"""
export type HtmlComponentType = 'alpha' | 'd-form-table' | 'd-form-qa'
{comments}
export const REGISTRY_LIST: HtmlRendererEntry[] = [
  {", ".join(spreads)},
]
""",
        encoding="utf-8",
    )
    return barrel


def test_checked_in_manifest_is_canonical_and_current() -> None:
    current, detail = check_manifest()
    assert current, detail
    on_disk = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert on_disk == build_manifest()
def test_every_observed_source_type_is_in_manifest_with_orthogonal_flags() -> None:
    observed = extract_observed_sources(DEFAULT_SOURCE_PATHS)
    registry = load_component_capability_registry()

    assert registry.component_types == observed.all_component_types
    assert registry.backend_renderer_types == observed.backend_renderer_types
    assert registry.frontend_component_types == observed.frontend_registry_types
    assert registry.override_allowed_types == observed.valid_component_types

    for source_name, component_types in observed.named_sets():
        for component_type in component_types:
            assert source_name in registry.require(component_type).sources


def test_d_form_entries_are_projected_from_domain_split_registry() -> None:
    """Production formsEntries must surface all five d-form-* types (no D_FORM map)."""
    observed = extract_observed_sources()
    expected = {
        "d-form-table",
        "d-form-paragraph",
        "d-form-qa",
        "d-form-confirmation",
        "d-form-review",
    }
    assert expected <= observed.frontend_registry_types
    for component_type in expected:
        capability = load_component_capability_registry().require(component_type)
        assert capability.has_frontend_component is True
        assert "REGISTRY_LIST" in capability.sources


def test_monolith_registry_without_entries_dir_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "registry.ts"
    source.write_text(
        """
const D_FORM_SUBTYPES = ['d-form-table'] as const
const REGISTRY_LIST: HtmlRendererEntry[] = [
  ...D_FORM_SUBTYPES.map((subtype) => ({ componentType: subtype })),
]
""",
        encoding="utf-8",
    )
    with pytest.raises(SourceExtractionError, match="D_FORM_SUBTYPES.map monolith is no longer accepted"):
        extract_html_registry_types(source)


def test_unknown_registry_spread_fails_closed(tmp_path: Path) -> None:
    source = _write_domain_split_registry(
        tmp_path,
        domain_files={
            "core": "export const coreEntries = [{ componentType: 'alpha', component: Alpha }]\n",
        },
        spreads=["...coreEntries", "...OTHER_ENTRIES"],
    )

    with pytest.raises(SourceExtractionError, match="unknown REGISTRY_LIST spread"):
        extract_html_registry_types(source)


def test_comment_fake_component_is_ignored(tmp_path: Path) -> None:
    comments = """
// { componentType: 'comment-fake-one' }
/* { componentType: 'comment-fake-two' } */
"""
    source = _write_domain_split_registry(
        tmp_path,
        domain_files={
            "core": (
                "export const coreEntries = [\n"
                "  { componentType: 'alpha', component: Alpha },\n"
                "  // { componentType: 'comment-fake-inline' }\n"
                "]\n"
            ),
            "forms": (
                "export const formsEntries = [\n"
                "  { componentType: 'd-form-table', component: Form },\n"
                "  { componentType: 'd-form-qa', component: Form },\n"
                "]\n"
            ),
        },
        comments=comments,
    )

    result = extract_html_registry_types(source)
    assert result == frozenset({"alpha", "d-form-table", "d-form-qa"})
    assert not any(value.startswith("comment-fake") for value in result)


def test_duplicate_registry_component_fails_before_map_construction(tmp_path: Path) -> None:
    source = _write_domain_split_registry(
        tmp_path,
        domain_files={
            "core": "export const coreEntries = [{ componentType: 'alpha', component: Alpha }]\n",
            "forms": "export const formsEntries = [{ componentType: 'alpha', component: Again }]\n",
        },
    )

    with pytest.raises(SourceExtractionError, match="duplicate component types"):
        extract_html_registry_types(source)


def test_derived_map_element_in_entry_file_fails_on_count(tmp_path: Path) -> None:
    """A ``.map(...)`` element inside an entry array must be named, not dropped.

    Regression guard: the previous extractor scanned the whole file for
    ``componentType: '…'`` literals, so a derived element yielding 0 literals was
    silently absent from the manifest (only surfaced far downstream as a fuzzy
    "manifest drift"). Now every top-level element must resolve to exactly one
    literal or the file is named.
    """

    source = _write_domain_split_registry(
        tmp_path,
        domain_files={
            "core": "export const coreEntries = [{ componentType: 'alpha', component: Alpha }]\n",
            "forms": (
                "const D_FORM_SUBTYPES = ['d-form-table', 'd-form-qa'] as const\n"
                "export const formsEntries = [\n"
                "  { componentType: 'd-form-review', component: Form },\n"
                "  ...D_FORM_SUBTYPES.map((s) => ({ componentType: s, component: Form })),\n"
                "]\n"
            ),
        },
    )

    with pytest.raises(SourceExtractionError, match="without exactly one"):
        extract_html_registry_types(source)


def test_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"schema_version":1,"schema_version":1,"components":{},"exemptions":[]}',
        encoding="utf-8",
    )

    with pytest.raises(ComponentCapabilityManifestError, match="JSON 重复键"):
        load_component_capability_registry(path)


@pytest.mark.parametrize(
    "entry, message",
    [
        (_entry(owner=""), "owner 必须为非空字符串"),
        (_entry(has_backend_renderer="true"), "has_backend_renderer 必须为 bool"),
        (_entry(host_policy="mystery"), "host_policy 非法"),
        (_entry(status="unknown"), "status 非法"),
        (_entry(sources=["VALID_COMPONENT_TYPES"]), "RENDERER_DISPATCH 与能力布尔值不一致"),
        (
            _entry(sources=["VALID_COMPONENT_TYPES", "RENDERER_DISPATCH", "REGISTRY_LIST", "REGISTRY_LIST"]),
            "sources 存在重复值",
        ),
    ],
)
def test_loader_rejects_invalid_or_self_contradictory_entries(
    tmp_path: Path,
    entry: dict[str, object],
    message: str,
) -> None:
    path = tmp_path / "manifest.json"
    _write_manifest(path, entry=entry)

    with pytest.raises(ComponentCapabilityManifestError, match=message):
        load_component_capability_registry(path)


def test_loader_rejects_unknown_fields_and_bad_exemptions(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    entry = _entry(extra_field=True)
    _write_manifest(path, entry=entry)
    with pytest.raises(ComponentCapabilityManifestError, match="字段不等于契约"):
        load_component_capability_registry(path)

    payload = {
        "schema_version": 1,
        "components": {"sample-component": _entry()},
        "exemptions": [
            {
                "component_type": "missing-component",
                "owner": "platform",
                "reason": "intentional",
                "source_digest": "sha256:abc",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ComponentCapabilityManifestError, match="未登记 componentType"):
        load_component_capability_registry(path)


def test_registry_is_immutable_and_projects_each_capability_independently() -> None:
    registry = load_component_capability_registry()
    html_type = next(iter(registry.frontend_component_types))
    capability = registry.require(html_type)

    assert capability.component_type == html_type
    assert html_type in registry.component_types
    assert registry.by_host_policy(capability.host_policy)
    with pytest.raises(TypeError):
        registry.components["injected"] = capability  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        capability.owner = "mutated"  # type: ignore[misc]
    with pytest.raises(KeyError, match="未登记 componentType"):
        registry.require("not-registered")
    with pytest.raises(ValueError, match="未知 host policy"):
        registry.by_host_policy("not-a-policy")


def test_typescript_projection_is_generated_from_manifest_not_wp_renderer_union() -> None:
    manifest = build_manifest()
    generated = TYPESCRIPT_PROJECTION_PATH.read_text(encoding="utf-8")

    assert generated == render_typescript_projection(manifest)
    assert "export type DeclaredWpComponentType = (typeof COMPONENT_TYPES)[number]" in generated
    assert "export type WpComponentType = string" in generated
    assert "export const ACTIVE_FRONTEND_COMPONENT_TYPES" in generated
    assert all(
        "WpComponentType" not in entry["sources"]
        for entry in manifest["components"].values()
    )


def test_typescript_projection_drift_is_detected_bidirectionally(
    tmp_path: Path,
) -> None:
    manifest = build_manifest()
    manifest_path = tmp_path / "component_capabilities.json"
    typescript_path = tmp_path / "componentCapabilities.generated.ts"
    manifest_path.write_text(render_manifest(manifest), encoding="utf-8")
    typescript_path.write_text(
        render_typescript_projection(manifest).replace(
            '  "h-static-doc",',
            '  "mutated-static-doc",',
            1,
        ),
        encoding="utf-8",
    )

    current, detail = check_manifest(
        output_path=manifest_path,
        typescript_output_path=typescript_path,
    )

    assert current is False
    assert "TypeScript projection drift" in detail


def test_manifest_host_policy_matches_legacy_multisheet_fate_for_all_components() -> None:
    """切换 planner 前，manifest 对全部 220 项的 host fate 必须与 legacy 零差。"""
    from scripts.gen.generate_component_capability_manifest import (
        DEFAULT_SOURCE_PATHS,
        extract_observed_sources,
    )
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    observed = extract_observed_sources(DEFAULT_SOURCE_PATHS)
    registry = load_component_capability_registry()
    special = {
        "skip": "skip",
        "univer": "univer",
        "onlyoffice": "onlyoffice",
        "onlyoffice-sheet": "onlyoffice",
    }
    differences: list[tuple[str, str, str]] = []
    for component_type, capability in registry.components.items():
        if component_type in special:
            expected = "onlyoffice" if component_type == "skip" else special[component_type]
        elif component_type.startswith("redirect-"):
            expected = "redirect"
        elif component_type in RENDERER_DISPATCH:
            expected = "html"
        elif component_type in observed.confirmation_types:
            expected = "confirmation"
        elif component_type in observed.html_whitelist_types:
            expected = "html"
        else:
            expected = "onlyoffice"
        if capability.host_policy != expected:
            differences.append(
                (component_type, expected, capability.host_policy)
            )

    assert differences == []


def test_every_capability_asymmetry_is_registered_as_an_exemption() -> None:
    """Req 1.5: a componentType present in only part of the sources must be
    adjudicated (exemption with owner/reason/source_digest), never silently
    dropped from the denominator."""
    observed = extract_observed_sources()
    manifest = build_manifest()
    backend = set(observed.backend_renderer_types)
    frontend = set(observed.frontend_registry_types)
    asymmetric = {
        ct
        for ct, e in manifest["components"].items()
        if bool(e["has_backend_renderer"]) != bool(e["has_frontend_component"])
        or (not e["has_backend_renderer"] and not e["has_frontend_component"])
    }
    exempted = {e["component_type"] for e in manifest["exemptions"]}
    assert asymmetric == exempted, (
        "asymmetries must be exactly the exemption set: "
        f"missing={sorted(asymmetric - exempted)} extra={sorted(exempted - asymmetric)}"
    )
    # every exemption has the full adjudication schema
    for e in manifest["exemptions"]:
        assert set(e) == {"component_type", "owner", "reason", "source_digest"}
        assert e["owner"] and e["reason"] and e["source_digest"]
        assert e["reason"].startswith(("[frontend_only]", "[backend_only]", "[manifest_only]"))
    # symmetric types are NOT exempted (no over-adjudication)
    symmetric = set(manifest["components"]) - asymmetric
    assert symmetric.isdisjoint(exempted)
    _ = (backend, frontend)


def test_source_digest_changes_when_sources_change() -> None:
    """source_digest must track which sources declare a type (drift detector)."""
    from scripts.gen.generate_component_capability_manifest import _source_digest

    base = _source_digest(["REGISTRY_LIST", "HtmlComponentType"])
    assert base == _source_digest(["HtmlComponentType", "REGISTRY_LIST"])  # order-stable
    assert base != _source_digest(["REGISTRY_LIST"])  # membership-sensitive
    assert len(base) == 16


def test_checker_has_zero_unadjudicated_asymmetry_on_production_manifest() -> None:
    """Req 1.4: the shipped manifest must have every asymmetry adjudicated."""
    from scripts.check import check_component_capabilities as checker

    assert checker.unadjudicated_asymmetries() == []


def test_checker_flags_unadjudicated_asymmetry_when_exemption_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mutation: drop one exemption → the asymmetry it covered becomes
    unadjudicated (Req 1.4). Guards against the checker only *printing*
    asymmetries. Patches only the manifest read, not global read_text."""
    import json as _json

    from scripts.check import check_component_capabilities as checker

    manifest_path = checker.BACKEND_ROOT / "app" / "data" / "component_capabilities.json"
    real = _json.loads(manifest_path.read_text(encoding="utf-8"))
    dropped = real["exemptions"][0]["component_type"]
    mutated_payload = {**real, "exemptions": real["exemptions"][1:]}
    mutated_json = _json.dumps(mutated_payload, ensure_ascii=False)

    orig_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):  # noqa: ANN001
        if Path(self) == manifest_path:
            return mutated_json
        return orig_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    unadjudicated = checker.unadjudicated_asymmetries()
    assert dropped in unadjudicated, (
        f"removing exemption for {dropped} must surface it as unadjudicated"
    )
