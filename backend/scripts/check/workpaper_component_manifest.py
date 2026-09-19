"""Build the dedicated workpaper componentType -> entry -> wp_code manifest.

The module intentionally uses only the standard library.  It reads the three
registration sources instead of importing the frontend runtime, so it is safe
for CI and can report registration drift without starting Vite or the backend.
"""
from __future__ import annotations

import argparse
import json
import re
import runpy
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
REGISTRY_PATH = (
    PROJECT_ROOT / "audit-platform" / "frontend" / "src" / "components"
    / "workpaper" / "htmlRendererRegistry.ts"
)
OVERRIDES_PATH = PROJECT_ROOT / "backend" / "app" / "data" / "wp_code_overrides.json"
DEDICATED_SOURCE_PATH = (
    PROJECT_ROOT / "backend" / "app" / "services" / "dedicated_component_types.py"
)
MANIFEST_OUTPUT_PATH = (
    PROJECT_ROOT / "audit-platform" / "frontend" / "src" / "components"
    / "workpaper" / "workpaper-component-manifest.json"
)

_CONTEXT_STRATEGIES = {"standard", "custom", "form-type", "none"}
_LAZY_CONST_RE = re.compile(
    r"\bconst\s+(\w+)\s*=\s*defineAsyncComponent\s*\(\s*\(\)\s*=>\s*"
    r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\)",
    re.MULTILINE,
)
_COMPONENT_TYPE_RE = re.compile(r"componentType\s*:\s*['\"]([^'\"]+)['\"]")
_INLINE_IMPORT_RE = re.compile(
    r"component\s*:\s*defineAsyncComponent\s*\(\s*\(\)\s*=>\s*"
    r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\)"
)
_COMPONENT_SYMBOL_RE = re.compile(r"component\s*:\s*([A-Za-z_$][\w$]*)")
_CONTEXT_RE = re.compile(r"contextProps\s*:\s*['\"]([^'\"]+)['\"]")

def _repo_relative(path: Path) -> str:
    """Return a stable repository-relative POSIX path."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _resolve_import_path(registry_path: Path, import_path: str) -> Path:
    return (registry_path.parent / import_path).resolve()


def _registry_list_source(source: str) -> str:
    """Return only REGISTRY_LIST, excluding type declarations and examples."""
    start = source.find("const REGISTRY_LIST")
    end = source.find("export const HTML_RENDERER_REGISTRY", start)
    if start < 0 or end <= start:
        raise ValueError("cannot locate htmlRendererRegistry REGISTRY_LIST")
    return source[start:end]


def parse_html_renderer_registry(path: Path = REGISTRY_PATH) -> dict[str, dict[str, str]]:
    """Parse literal registry entries and resolve each lazy Vue entry file.

    Both registry forms currently used by the project are supported:
    a named ``const Foo = defineAsyncComponent(...)`` and an inline
    ``component: defineAsyncComponent(...)``.  Dynamic entries are ignored;
    dedicated componentTypes are required to use literal registrations.
    """
    source = path.read_text(encoding="utf-8")
    registry_source = _registry_list_source(source)
    symbol_imports = {
        symbol: import_path for symbol, import_path in _LAZY_CONST_RE.findall(source)
    }
    matches = list(_COMPONENT_TYPE_RE.finditer(registry_source))
    entries: dict[str, dict[str, str]] = {}

    for index, match in enumerate(matches):
        component_type = match.group(1)
        segment_end = (
            matches[index + 1].start() if index + 1 < len(matches) else len(registry_source)
        )
        segment = registry_source[match.start():segment_end]

        inline = _INLINE_IMPORT_RE.search(segment)
        if inline:
            import_path = inline.group(1)
        else:
            symbol_match = _COMPONENT_SYMBOL_RE.search(segment)
            import_path = symbol_imports.get(symbol_match.group(1), "") if symbol_match else ""

        context_match = _CONTEXT_RE.search(segment)
        context_strategy = context_match.group(1) if context_match else "none"
        if context_strategy not in _CONTEXT_STRATEGIES:
            raise ValueError(
                f"{component_type}: unknown contextProps strategy {context_strategy!r}"
            )
        if component_type in entries:
            raise ValueError(f"duplicate htmlRendererRegistry entry: {component_type}")

        entry_file = (
            _repo_relative(_resolve_import_path(path, import_path)) if import_path else ""
        )
        entries[component_type] = {
            "entryFile": entry_file,
            "contextStrategy": context_strategy,
        }

    return entries


def load_wp_code_overrides(path: Path = OVERRIDES_PATH) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in data.items()
    ):
        raise ValueError("wp_code_overrides.json must be a string-to-string object")
    return data


def load_dedicated_component_types(path: Path = DEDICATED_SOURCE_PATH) -> frozenset[str]:
    namespace = runpy.run_path(str(path))
    values = namespace.get("DEDICATED_COMPONENT_TYPES")
    if not isinstance(values, frozenset) or not all(isinstance(value, str) for value in values):
        raise ValueError("dedicated component source must define frozenset[str]")
    return values


def _natural_key(value: str) -> list[tuple[int, Any]]:
    """Sort wp codes naturally (K2-2 before K2-10) and keep text keys stable."""
    return [
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", value)
        if part
    ]

def generate_component_manifest(
    *,
    registry_path: Path = REGISTRY_PATH,
    overrides_path: Path = OVERRIDES_PATH,
    dedicated_source_path: Path = DEDICATED_SOURCE_PATH,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Merge the three authoritative sources into a reproducible manifest."""
    registry = parse_html_renderer_registry(registry_path)
    overrides = load_wp_code_overrides(overrides_path)
    dedicated_types = load_dedicated_component_types(dedicated_source_path)

    wp_codes_by_type: dict[str, list[str]] = {value: [] for value in dedicated_types}
    for wp_code, component_type in overrides.items():
        if component_type in wp_codes_by_type:
            wp_codes_by_type[component_type].append(wp_code)

    missing_registry: list[str] = []
    missing_wp_codes: list[str] = []
    missing_entry_files: list[str] = []
    entries: dict[str, dict[str, Any]] = {}

    for component_type in sorted(dedicated_types):
        registry_entry = registry.get(component_type)
        wp_codes = sorted(wp_codes_by_type[component_type], key=_natural_key)
        entry_file = registry_entry["entryFile"] if registry_entry else ""
        context_strategy = registry_entry["contextStrategy"] if registry_entry else "unknown"

        if registry_entry is None:
            missing_registry.append(component_type)
        if not wp_codes:
            missing_wp_codes.append(component_type)
        if entry_file and not (PROJECT_ROOT / entry_file).is_file():
            missing_entry_files.append(component_type)

        entries[component_type] = {
            "componentType": component_type,
            "entryFile": entry_file or None,
            "wpCodes": wp_codes,
            "contextStrategy": context_strategy,
            # GtWpRenderer resolves every literal htmlRendererRegistry entry via
            # getRendererEntry(); missing registry entries are therefore not routed.
            "viaGtWpRenderer": registry_entry is not None,
        }

    diagnostics = {
        "missingRegistryEntries": missing_registry,
        "missingWpCodeMappings": missing_wp_codes,
        "missingEntryFiles": missing_entry_files,
    }
    return {
        "schemaVersion": 1,
        "generatedAt": generated_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {
            "htmlRendererRegistry": _repo_relative(registry_path),
            "wpCodeOverrides": _repo_relative(overrides_path),
            "dedicatedComponentTypes": _repo_relative(dedicated_source_path),
        },
        "entries": entries,
        "diagnostics": diagnostics,
        "isComplete": not any(diagnostics.values()),
    }


def write_component_manifest(manifest: dict[str, Any], path: Path = MANIFEST_OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def print_component_manifest_summary(manifest: dict[str, Any]) -> None:
    entries = manifest["entries"]
    diagnostics = manifest["diagnostics"]
    print(f"[Component Manifest] 专属 componentType: {len(entries)}")
    print(f"  GtWpRenderer: {sum(e['viaGtWpRenderer'] for e in entries.values())}")
    print(f"  context=standard: {sum(e['contextStrategy'] == 'standard' for e in entries.values())}")
    print(f"  wp_code 映射: {sum(len(e['wpCodes']) for e in entries.values())}")
    for name, values in diagnostics.items():
        if values:
            print(f"  [WARN] {name}: {', '.join(values)}")


def main(argv: list[str] | None = None) -> int:
    """Generate the manifest as a standalone CI/local command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=MANIFEST_OUTPUT_PATH)
    parser.add_argument("--check", action="store_true", help="scan without writing")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero when any authoritative source is incomplete",
    )
    args = parser.parse_args(argv)

    manifest = generate_component_manifest()
    print_component_manifest_summary(manifest)
    if args.check:
        print("[CHECK] 预演模式，未写入文件。")
    else:
        write_component_manifest(manifest, args.output)
        print(f"[OK] 已写入: {args.output}")
    if args.strict and not manifest["isComplete"]:
        print("[FAIL] component manifest 存在注册漂移。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
