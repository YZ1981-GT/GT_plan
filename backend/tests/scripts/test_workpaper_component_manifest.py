"""Tests for the dedicated workpaper component manifest generator.

Validates: Requirements 1.1, 1.2
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check.workpaper_component_manifest import (
    DEDICATED_SOURCE_PATH,
    INTENTIONALLY_UNROUTED_COMPONENT_TYPES,
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


def test_registry_parser_follows_spread_assembled_domain_files(tmp_path: Path) -> None:
    """变异证明：条目拆到分域文件后仍必须被解析到（否则回到"静默 0 条"）。

    2026-09-28 修复的真实形态——`REGISTRY_LIST` 只剩 `...coreEntries` 之类的
    spread，条目本体在 `./registry/entries/*.ts`。旧扫描器只读 REGISTRY_LIST
    那十几行，解析出 0 条，于是把全部专属 componentType 报成未注册。
    """
    registry = tmp_path / "htmlRendererRegistry.ts"
    entries_dir = tmp_path / "registry" / "entries"
    entries_dir.mkdir(parents=True)
    # 相对 import 必须以**条目文件**为基准解析，不是注册表文件
    (tmp_path / "Split.vue").write_text("<template />", encoding="utf-8")
    (entries_dir / "core.ts").write_text(
        """
        export const coreEntries: HtmlRendererEntry[] = [
          { componentType: 'split-one', component: defineAsyncComponent(
              () => import('../../Split.vue')
            ), contextProps: 'standard' },
        ]
        """,
        encoding="utf-8",
    )
    registry.write_text(
        """
        import { coreEntries } from './registry/entries/core'
        const REGISTRY_LIST: HtmlRendererEntry[] = [
          ...coreEntries,
        ]
        export const HTML_RENDERER_REGISTRY = new Map()
        """,
        encoding="utf-8",
    )

    entries = parse_html_renderer_registry(registry)

    assert set(entries) == {"split-one"}
    assert entries["split-one"]["entryFile"].endswith("Split.vue")
    assert entries["split-one"]["contextStrategy"] == "standard"


def test_registry_parser_fails_closed_on_unresolvable_spread(tmp_path: Path) -> None:
    """spread 找不到 import 时必须抛错，不能静默少扫一族。"""
    registry = tmp_path / "htmlRendererRegistry.ts"
    registry.write_text(
        """
        const REGISTRY_LIST: HtmlRendererEntry[] = [
          ...ghostEntries,
        ]
        export const HTML_RENDERER_REGISTRY = new Map()
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ghostEntries"):
        parse_html_renderer_registry(registry)


def test_real_registry_resolves_every_dedicated_component_type() -> None:
    """真源回归：91 个专属 componentType 必须全部在注册表里解析到。"""
    registry = parse_html_renderer_registry()
    dedicated = load_dedicated_component_types()

    assert dedicated, "dedicated component types 不应为空"
    assert not (set(dedicated) - set(registry)), sorted(set(dedicated) - set(registry))
    assert all(registry[name]["entryFile"] for name in dedicated)


def test_unrouted_allowlist_has_no_stale_entries() -> None:
    """反向断言：豁免名单里的条目一旦真接上 wp_code，名单项即失效必须删除。

    没有这条，名单会变成"藏缺陷的地方"。
    """
    manifest = generate_component_manifest(generated_at="2026-07-14T00:00:00Z")
    dedicated = load_dedicated_component_types()

    for component_type, reason in INTENTIONALLY_UNROUTED_COMPONENT_TYPES.items():
        assert component_type in dedicated, (
            f"{component_type} 已不在 DEDICATED_COMPONENT_TYPES，豁免名单项失效请删除"
        )
        assert reason.strip(), f"{component_type} 豁免必须写明理由"
        assert manifest["entries"][component_type]["wpCodes"] == [], (
            f"{component_type} 已接上 wp_code "
            f"{manifest['entries'][component_type]['wpCodes']}，"
            "豁免名单项失效请删除"
        )
    assert manifest["intentionallyUnrouted"] == dict(
        sorted(INTENTIONALLY_UNROUTED_COMPONENT_TYPES.items())
    )


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
