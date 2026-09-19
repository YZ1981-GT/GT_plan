"""Tests for the dedicated workpaper component manifest generator.

Validates: Requirements 1.1, 1.2
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.check.workpaper_component_manifest import (
    DEDICATED_SOURCE_PATH,
    MANIFEST_OUTPUT_PATH,
    OVERRIDES_PATH,
    REGISTRY_PATH,
    generate_component_manifest,
    load_dedicated_component_types,
    main,
    parse_html_renderer_registry,
)


def test_registry_parser_supports_named_inline_and_default_context(tmp_path: Path) -> None:
    registry = tmp_path / "htmlRendererRegistry.ts"
    (tmp_path / "Named.vue").write_text("<template />", encoding="utf-8")
    (tmp_path / "Inline.vue").write_text("<template />", encoding="utf-8")
    registry.write_text(
        """
        type Example = { componentType: 'type-only' }
        const Named = defineAsyncComponent(() => import('./Named.vue'))
        const REGISTRY_LIST = [
          { componentType: 'named', component: Named, contextProps: 'standard' },
          { componentType: 'inline', component: defineAsyncComponent(
              () => import('./Inline.vue')
            ) },
        ]
        export const HTML_RENDERER_REGISTRY = new Map()
        """,
        encoding="utf-8",
    )

    entries = parse_html_renderer_registry(registry)

    assert set(entries) == {"named", "inline"}
    assert entries["named"]["entryFile"].endswith("Named.vue")
    assert entries["named"]["contextStrategy"] == "standard"
    assert entries["inline"]["entryFile"].endswith("Inline.vue")
    assert entries["inline"]["contextStrategy"] == "none"


def test_manifest_exactly_enumerates_dedicated_source() -> None:
    manifest = generate_component_manifest(generated_at="2026-07-14T00:00:00Z")
    dedicated = load_dedicated_component_types()

    assert set(manifest["entries"]) == set(dedicated)
    assert manifest["isComplete"] is True, manifest["diagnostics"]
    assert manifest["diagnostics"] == {
        "missingRegistryEntries": [],
        "missingWpCodeMappings": [],
        "missingEntryFiles": [],
    }
    assert all(entry["viaGtWpRenderer"] for entry in manifest["entries"].values())


def test_manifest_reports_entry_file_context_and_wp_codes() -> None:
    manifest = generate_component_manifest(generated_at="2026-07-14T00:00:00Z")
    entries = manifest["entries"]

    assert entries["h1-fixed-assets"] == {
        "componentType": "h1-fixed-assets",
        "entryFile": (
            "audit-platform/frontend/src/components/workpaper/GtH1FixedAssets.vue"
        ),
        "wpCodes": entries["h1-fixed-assets"]["wpCodes"],
        "contextStrategy": "standard",
        "viaGtWpRenderer": True,
    }
    assert "H1" in entries["h1-fixed-assets"]["wpCodes"]
    assert entries["j1-employee-compensation"]["entryFile"].endswith(
        "components/workpaper/j1/GtJ1EmployeeCompensation.vue"
    )
    assert "J1" in entries["j1-employee-compensation"]["wpCodes"]
    assert entries["s33-ann14-bundle"]["entryFile"].endswith(
        "components/workpaper/s33-ann14-bundle/GtS33Bundle.vue"
    )


def test_manifest_records_all_three_authoritative_sources() -> None:
    manifest = generate_component_manifest(generated_at="2026-07-14T00:00:00Z")

    assert manifest["sources"] == {
        "htmlRendererRegistry": REGISTRY_PATH.relative_to(
            REGISTRY_PATH.parents[5]
        ).as_posix(),
        "wpCodeOverrides": OVERRIDES_PATH.relative_to(OVERRIDES_PATH.parents[3]).as_posix(),
        "dedicatedComponentTypes": DEDICATED_SOURCE_PATH.relative_to(
            DEDICATED_SOURCE_PATH.parents[3]
        ).as_posix(),
    }
    json.dumps(manifest, ensure_ascii=False)


def test_checked_in_manifest_matches_authoritative_sources() -> None:
    checked_in = json.loads(MANIFEST_OUTPUT_PATH.read_text(encoding="utf-8"))
    generated = generate_component_manifest(generated_at=checked_in["generatedAt"])

    assert checked_in == generated


def test_standalone_cli_strict_check_does_not_write(capsys) -> None:
    assert main(["--check", "--strict"]) == 0
    output = capsys.readouterr().out
    assert "专属 componentType" in output
    assert "GtWpRenderer" in output
    assert "预演模式" in output
