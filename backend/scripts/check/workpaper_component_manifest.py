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

#: 已注册但**故意不接任何 wp_code** 的专属 componentType（兼容期保留）。
#:
#: 🔴 这不是"放宽阈值"，而是把一条既有裁决显式化：
#: `b22bDeficiencyEvaluation.spec.ts` 里记着**方案 A** —— `B22B` 的 wp_code 改指
#: 向控制矩阵登记册 `b22b-control-matrix`（致同源模板 B22B 的真实结构就是登记册），
#: 缺陷评价组件的文件与注册表条目**保留**（兼容期，历史底稿可能还在引用），但
#: `B22B` 不再路由它。于是它必然 0 个 wp_code 映射。
#:
#: 每条必须写明"为什么不接"。名单配**反向断言**（见
#: `tests/scripts/test_workpaper_component_manifest.py::
#: test_unrouted_allowlist_has_no_stale_entries`）：一旦某条真的接上了 wp_code，
#: 名单项即失效并打红，逼迫删除——避免名单变成藏缺陷的地方。
INTENTIONALLY_UNROUTED_COMPONENT_TYPES: dict[str, str] = {
    "b22b-deficiency-evaluation": (
        "方案 A：B22B wp_code 改指向 b22b-control-matrix（控制矩阵登记册），"
        "缺陷评价组件兼容期保留但不再被任何 wp_code 路由"
    ),
}
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


_SPREAD_RE = re.compile(r"\.\.\.\s*(\w+)\s*,")
_ENTRY_IMPORT_RE = re.compile(
    r"import\s*\{\s*(\w+)\s*\}\s*from\s*['\"]([^'\"]+)['\"]"
)


def _registry_list_source(source: str) -> str:
    """Return only REGISTRY_LIST, excluding type declarations and examples."""
    start = source.find("const REGISTRY_LIST")
    end = source.find("export const HTML_RENDERER_REGISTRY", start)
    if start < 0 or end <= start:
        raise ValueError("cannot locate htmlRendererRegistry REGISTRY_LIST")
    return source[start:end]


def _collect_registry_sources(path: Path) -> list[tuple[Path, str, str]]:
    """Return ``(file, full_source, entry_region)`` for every file holding entries.

    🔴 2026-09-28 修：注册表条目已按渲染器家族拆到
    ``./registry/entries/*.ts``，``REGISTRY_LIST`` 只剩 spread 装配::

        const REGISTRY_LIST: HtmlRendererEntry[] = [
          ...coreEntries, ...formsEntries, ...programsEntries,
          ...confirmationsEntries, ...reportsEntries, ...specializedEntries,
        ]

    原实现只读 ``const REGISTRY_LIST`` 到 ``export const HTML_RENDERER_REGISTRY``
    之间那 15 行 ⇒ 解析出 **0 条** entry，于是 91 个专属 componentType 全部被报成
    ``missingRegistryEntries``、``entryFile`` 全为 ``None``、``GtWpRenderer: 0``。
    `tests/scripts/test_workpaper_component_manifest.py` 4 条因此一直红
    —— 是**扫描器没跟上拆分**，不是真的注册漂移。

    这里**跟随 spread 名字解析 import 来源**而不是写死 6 个文件名：
    以后新增/改名家族会自动纳入；若某个 spread 找不到对应 import 或文件缺失，
    立即抛错（fail-closed），避免又回到"静默少扫一族"。
    """
    source = path.read_text(encoding="utf-8")
    list_source = _registry_list_source(source)
    spreads = _SPREAD_RE.findall(list_source)
    if not spreads:
        # 未拆分形态（条目直接内联在 REGISTRY_LIST 里）—— 兼容旧结构
        return [(path, source, list_source)]

    imports = {symbol: rel for symbol, rel in _ENTRY_IMPORT_RE.findall(source)}
    out: list[tuple[Path, str, str]] = []
    for symbol in spreads:
        rel = imports.get(symbol)
        if not rel:
            raise ValueError(
                f"REGISTRY_LIST 里 spread 了 {symbol!r} 但找不到对应 import ——"
                " 扫描器会静默少扫一族，请修正注册表或本扫描器"
            )
        candidate = _resolve_import_path(path, rel)
        entry_file = next(
            (p for p in (candidate, candidate.with_suffix(".ts"), candidate / "index.ts")
             if p.is_file()),
            None,
        )
        if entry_file is None:
            raise ValueError(f"{symbol}: 解析不到 entries 文件（{rel}）")
        entry_source = entry_file.read_text(encoding="utf-8")
        # 分域文件整篇就是 entries 数组，符号常量与条目同处一文件
        out.append((entry_file, entry_source, entry_source))
    return out


def parse_html_renderer_registry(path: Path = REGISTRY_PATH) -> dict[str, dict[str, str]]:
    """Parse literal registry entries and resolve each lazy Vue entry file.

    Both registry forms currently used by the project are supported:
    a named ``const Foo = defineAsyncComponent(...)`` and an inline
    ``component: defineAsyncComponent(...)``.  Dynamic entries are ignored;
    dedicated componentTypes are required to use literal registrations.
    """
    entries: dict[str, dict[str, str]] = {}

    for source_file, full_source, registry_source in _collect_registry_sources(path):
        symbol_imports = {
            symbol: import_path
            for symbol, import_path in _LAZY_CONST_RE.findall(full_source)
        }
        matches = list(_COMPONENT_TYPE_RE.finditer(registry_source))

        for index, match in enumerate(matches):
            component_type = match.group(1)
            segment_end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(registry_source)
            )
            segment = registry_source[match.start():segment_end]

            inline = _INLINE_IMPORT_RE.search(segment)
            if inline:
                import_path = inline.group(1)
            else:
                symbol_match = _COMPONENT_SYMBOL_RE.search(segment)
                import_path = (
                    symbol_imports.get(symbol_match.group(1), "") if symbol_match else ""
                )

            context_match = _CONTEXT_RE.search(segment)
            context_strategy = context_match.group(1) if context_match else "none"
            if context_strategy not in _CONTEXT_STRATEGIES:
                raise ValueError(
                    f"{component_type}: unknown contextProps strategy {context_strategy!r}"
                )
            if component_type in entries:
                raise ValueError(f"duplicate htmlRendererRegistry entry: {component_type}")

            # 相对 import 以**条目所在文件**为基准解析（分域后不再是注册表文件）
            entry_file = (
                _repo_relative(_resolve_import_path(source_file, import_path))
                if import_path
                else ""
            )
            entries[component_type] = {
                "entryFile": entry_file,
                "contextStrategy": context_strategy,
            }

    return entries


def parse_registry_component_types(path: Path = REGISTRY_PATH) -> frozenset[str]:
    """前端注册表里登记的全部 componentType（**唯一解析入口**）。

    🔴 2026-09-28 加：仓库里曾有 **4 份**手抄的 "找 `const REGISTRY_LIST` 到
    `export const HTML_RENDERER_REGISTRY` 之间的切片再正则 componentType" 副本
    （test_dedicated_component_registry_contract / test_k10_contract /
    test_k12_contract / test_k13_registration_contract）。注册表按渲染器家族拆到
    `registry/entries/*.ts` 之后，那个切片只剩 6 个 spread ⇒ 4 份副本**同时**解析出
    0 条，把"解析失败"表现成"91 个 componentType 全没注册"，全部恒红。

    任何需要这份集合的地方都必须调本函数，不要再手写切片解析
    （`tests/scripts/test_workpaper_component_manifest.py::
    test_no_handwritten_registry_slice_parser_remains` 会拦第五份副本）。
    """
    entries = parse_html_renderer_registry(path)
    if not entries:
        raise ValueError(
            f"{_repo_relative(path)} 解析出 0 个 componentType —— 这是解析失败，"
            "不是注册表为空；注册表结构可能又变了"
        )
    return frozenset(entries)


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
        if not wp_codes and component_type not in INTENTIONALLY_UNROUTED_COMPONENT_TYPES:
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
    # 豁免项显式写进产物，避免"名单静默吞掉缺陷"
    intentionally_unrouted = {
        name: reason
        for name, reason in sorted(INTENTIONALLY_UNROUTED_COMPONENT_TYPES.items())
        if name in dedicated_types
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
        "intentionallyUnrouted": intentionally_unrouted,
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
    for name, reason in manifest.get("intentionallyUnrouted", {}).items():
        print(f"  [豁免-无 wp_code] {name}: {reason}")
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
