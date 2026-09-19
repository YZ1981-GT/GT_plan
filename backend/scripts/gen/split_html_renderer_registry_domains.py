#!/usr/bin/env python3
"""
PAC Task 20 — one-time split of htmlRendererRegistry.ts into explicit domain entry arrays.

Parses REGISTRY_LIST object literals, partitions by explicit membership rules (generation-time
only), writes registry/entries/*.ts, updates registry/index.ts barrel, and replaces
htmlRendererRegistry.ts with a thin re-export facade.

Runtime registry code must NOT use startsWith classifiers.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # GT_plan
FRONTEND = ROOT / "audit-platform" / "frontend"
SRC_REG = FRONTEND / "src" / "components" / "workpaper" / "htmlRendererRegistry.ts"
SRC_BAK = FRONTEND / "src" / "components" / "workpaper" / "htmlRendererRegistry.monolithic.bak.ts"
ENTRIES_DIR = FRONTEND / "src" / "components" / "workpaper" / "registry" / "entries"
BARREL_PATH = FRONTEND / "src" / "components" / "workpaper" / "registry" / "index.ts"
GOLDEN_PATH = (
    FRONTEND
    / "src"
    / "components"
    / "workpaper"
    / "__tests__"
    / "fixtures"
    / "registry-entries.golden.json"
)

CORE_EXPLICIT = frozenset(
    {
        "a1-dashboard",
        "a2-adjustment-console",
        "a3-consolidation-console",
        "b-index",
        "c-note-table",
        "audit-sheet",
        "bad-debt-sheet",
        "cf-verification",
        "custom",
        "h-static-doc",
        "checklist-table",
        "analytical-review",
        "independence-signing",
        "wp-popup-signing",
        "review-checklist",
        "review-bundle",
    }
)

REPORTS_EXPLICIT = frozenset(
    {
        "report-analysis",
        "segment-report",
        "misstatement-summary",
        "misstatement-workpaper",
        "word-template",
        "audit-legend",
    }
)

FORMS_KNOWN = frozenset(
    {
        "d-form-table",
        "d-form-paragraph",
        "d-form-qa",
        "d-form-confirmation",
        "d-form-review",
    }
)

D_FORM_ICONS = {
    "d-form-table": "📑",
    "d-form-paragraph": "📄",
    "d-form-qa": "❓",
    "d-form-confirmation": "✉️",
    "d-form-review": "✍️",
}


def split_top_level_objects(body: str) -> list[str]:
    objs: list[str] = []
    depth = 0
    start = -1
    in_str: str | None = None
    escape = False
    for i, ch in enumerate(body):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                objs.append(body[start : i + 1])
                start = -1
    return objs


def parse_const_imports(src: str) -> dict[str, str]:
    """Map GtFoo -> './path/to/Foo.vue' (raw import arg including quotes)."""
    out: dict[str, str] = {}
    for m in re.finditer(
        r"const\s+(\w+)\s*=\s*defineAsyncComponent\(\(\)\s*=>\s*import\(([^)]+)\)\)",
        src,
    ):
        out[m.group(1)] = m.group(2).strip()
    return out


def extract_component_type(obj: str) -> str:
    m = re.search(r"componentType:\s*'([^']+)'", obj)
    if not m:
        raise ValueError(f"no componentType in {obj[:120]!r}")
    return m.group(1)


def rewrite_import_path(import_arg: str) -> str:
    """Adjust ./ relative imports for registry/entries/ depth."""
    raw = import_arg.strip()
    q = raw[0] if raw and raw[0] in "'\"" else "'"
    inner = raw.strip("'\"")
    if inner.startswith("./"):
        inner = "../../" + inner[2:]
    elif not inner.startswith("@/") and not inner.startswith("/"):
        inner = "../../" + inner
    return f"{q}{inner}{q}"


def normalize_entry_object(obj: str, const_imports: dict[str, str]) -> tuple[str, str]:
    """
    Return (componentType, rewritten object source) with defineAsyncComponent inline
    and import paths adjusted for entries/*.ts.
    """
    ct = extract_component_type(obj)

    # Inline defineAsyncComponent(() => import(...))
    def repl_inline(m: re.Match[str]) -> str:
        arg = rewrite_import_path(m.group(1))
        return f"defineAsyncComponent(() => import({arg}))"

    rewritten = re.sub(
        r"defineAsyncComponent\(\(\)\s*=>\s*import\(([^)]+)\)\)",
        repl_inline,
        obj,
    )

    # Named component refs: component: GtFoo,
    def repl_named(m: re.Match[str]) -> str:
        name = m.group(1)
        if name == "defineAsyncComponent":
            return m.group(0)
        if name not in const_imports:
            raise KeyError(f"unknown component ref {name} for {ct}")
        arg = rewrite_import_path(const_imports[name])
        return f"component: defineAsyncComponent(() => import({arg})),"

    rewritten = re.sub(r"component:\s*([A-Za-z_][A-Za-z0-9_]*)\s*,", repl_named, rewritten)
    # Entry arrays type as HtmlRendererEntry[] — drop `as const` from contextProps.
    rewritten = re.sub(r"(contextProps:\s*'[^']+')\s+as\s+const", r"\1", rewritten)
    return ct, rewritten


def expand_d_form_entries(const_imports: dict[str, str]) -> list[tuple[str, str]]:
    """Explicit d-form-* entries (replaces D_FORM_SUBTYPES.map spread).

    Uses shared GtDForm ref (same AsyncComponentWrapper) like the monolithic registry.
    """
    out: list[tuple[str, str]] = []
    for subtype in (
        "d-form-table",
        "d-form-paragraph",
        "d-form-qa",
        "d-form-confirmation",
        "d-form-review",
    ):
        short = subtype.replace("d-form-", "")
        icon = D_FORM_ICONS[subtype]
        obj = (
            "{\n"
            f"    componentType: '{subtype}',\n"
            "    component: GtDForm,\n"
            f"    icon: '{icon}',\n"
            f"    label: 'D 检查表 ({short})',\n"
            "    emits: ['save'],\n"
            "    contextProps: 'form-type',\n"
            "  }"
        )
        out.append((subtype, obj))
    return out


def assign_domain(ct: str) -> str:
    """Generation-time partition — result is baked into files; not used at runtime."""
    if ct.startswith("confirmation-") or ct == "confirmation-hub":
        return "confirmations"
    if ct.startswith("d-form-") or ct in FORMS_KNOWN:
        return "forms"
    if (
        "program" in ct
        or ct == "a-program-console"
        or ct == "procedure-table"
        or ct == "c-control-test"
        or ct == "e-control-test"
        or (ct.endswith("-bundle") and (ct.startswith("a") or ct.startswith("b")))
    ):
        return "programs"
    if "report" in ct or ct in REPORTS_EXPLICIT:
        return "reports"
    if ct in CORE_EXPLICIT or ct.startswith("a1-") or ct.startswith("a17-"):
        return "core"
    return "specialized"


def emit_entry_file(domain: str, entries: list[tuple[str, str]]) -> None:
    lines = [
        "import { defineAsyncComponent } from 'vue'",
        "import type { HtmlRendererEntry } from '../types'",
        "",
        "/**",
        f" * Explicit HtmlRendererEntry[] for domain: {domain}",
        " * Membership is the array itself — no startsWith classifier.",
        " */",
    ]
    if domain == "forms":
        dform_arg = "'./GtDForm/GtDForm.vue'"
        # Prefer path from monolithic const map when regenerating
        lines.append("")
        lines.append(
            "/** Shared lazy GtDForm — all d-form-* subtypes reuse one AsyncComponentWrapper. */"
        )
        lines.append(
            f"const GtDForm = defineAsyncComponent(() => import({rewrite_import_path(dform_arg)}))"
        )
        lines.append("")
    lines.append(f"export const {domain}Entries: HtmlRendererEntry[] = [")
    for _ct, obj in entries:
        body = obj.strip()
        if not body.endswith(","):
            body = body + ","
        # Ensure 2-space indent on the opening brace line
        parts = body.splitlines()
        if parts and parts[0].lstrip().startswith("{"):
            parts[0] = "  " + parts[0].lstrip()
        body = "\n".join(parts)
        lines.append(body)
    lines.append("]")
    lines.append("")
    path = ENTRIES_DIR / f"{domain}.ts"
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)} ({len(entries)} entries)")


def extract_html_component_type_union(src: str) -> str:
    start = src.index("export type HtmlComponentType =")
    # ends before ContextPropsStrategy or HtmlRendererEntry interface
    end_markers = [
        "export type ContextPropsStrategy",
        "export interface HtmlRendererEntry",
        "const Gt",
        "// ───",
    ]
    end = len(src)
    for marker in end_markers:
        idx = src.find(marker, start + 10)
        if idx != -1:
            end = min(end, idx)
    block = src[start:end].rstrip()
    if not block.endswith("\n"):
        block += "\n"
    return block


def write_barrel(html_component_type_block: str) -> None:
    barrel = f'''/**
 * Registry Barrel — explicit domain entry arrays + sync assembly
 *
 * - Concatenate domain HtmlRendererEntry[] arrays
 * - Collision check BEFORE Map construction
 * - Every domain array must be imported and consumed
 * - getRendererEntry remains synchronous
 *
 * @see platform-architecture-convergence Task 20
 */
import type {{ Component }} from 'vue'
import type {{ HtmlRendererEntry, ContextPropsStrategy }} from './types'
export type {{ HtmlRendererEntry, ContextPropsStrategy }} from './types'

import {{ coreEntries }} from './entries/core'
import {{ formsEntries }} from './entries/forms'
import {{ programsEntries }} from './entries/programs'
import {{ confirmationsEntries }} from './entries/confirmations'
import {{ reportsEntries }} from './entries/reports'
import {{ specializedEntries }} from './entries/specialized'

/** All domain entry arrays — must each appear in REGISTRY_LIST concat below. */
export const DOMAIN_ENTRY_ARRAYS = {{
  core: coreEntries,
  forms: formsEntries,
  programs: programsEntries,
  confirmations: confirmationsEntries,
  reports: reportsEntries,
  specialized: specializedEntries,
}} as const

export type RegistryDomain = keyof typeof DOMAIN_ENTRY_ARRAYS

/** Explicit domain arrays consumed into the registry (unconsumed → test RED). */
export const REGISTRY_LIST: HtmlRendererEntry[] = [
  ...coreEntries,
  ...formsEntries,
  ...programsEntries,
  ...confirmationsEntries,
  ...reportsEntries,
  ...specializedEntries,
]

export function assertUniqueRegistryComponentTypes(
  entries: readonly Pick<HtmlRendererEntry, 'componentType'>[],
): void {{
  const seen = new Set<string>()
  const duplicates = new Set<string>()
  for (const entry of entries) {{
    if (seen.has(entry.componentType)) duplicates.add(entry.componentType)
    seen.add(entry.componentType)
  }}
  if (duplicates.size > 0) {{
    throw new Error(
      `htmlRendererRegistry componentType 重复声明: ${{[...duplicates].sort().join(', ')}}`,
    )
  }}
}}

export function assertAllDomainArraysConsumed(
  consumed: readonly HtmlRendererEntry[][],
  domainArrays: typeof DOMAIN_ENTRY_ARRAYS,
): void {{
  const missing: string[] = []
  for (const [name, arr] of Object.entries(domainArrays)) {{
    if (!consumed.includes(arr)) missing.push(name)
  }}
  if (missing.length > 0) {{
    throw new Error(`registry domain arrays not consumed by barrel: ${{missing.join(', ')}}`)
  }}
}}

assertAllDomainArraysConsumed(
  [coreEntries, formsEntries, programsEntries, confirmationsEntries, reportsEntries, specializedEntries],
  DOMAIN_ENTRY_ARRAYS,
)

// 必须在 Map 构造前检查；Map values 已无法观察被覆盖的重复 key。
assertUniqueRegistryComponentTypes(REGISTRY_LIST)

{html_component_type_block}
/**
 * 上下文 props 策略：声明组件需要哪些上下文信息。
 * GtWpRenderer 根据此声明自动透传，新增 componentType 无需修改 if 链。
 *
 * - 'standard'  → {{ wp-id, project-id, wp-code, year }}（绝大多数 HTML 组件）
 * - 'custom'    → {{ wp-generated, project-id, wp-code, year }}（自定义/程序表）
 * - 'form-type' → {{ form-type: componentType }}（D 子模式）
 * - 'none'      → {{}}（纯展示，无需额外上下文）
 */

/** 注册表 Map（O(1) 查找） */
export const HTML_RENDERER_REGISTRY: ReadonlyMap<HtmlComponentType, HtmlRendererEntry> = new Map(
  REGISTRY_LIST.map((e) => [e.componentType as HtmlComponentType, e]),
)

/** placeholder 类型（univer/skip）的图标，渲染走 GtWpRenderer 内部 fallback */
export const PLACEHOLDER_ICONS: Readonly<Record<string, string>> = {{
  univer: '📊',
  skip: '⏭️',
}}

export const HTML_COMPONENT_TYPE_SET: ReadonlySet<HtmlComponentType> = new Set(
  REGISTRY_LIST.map((e) => e.componentType as HtmlComponentType),
)

export const HTML_RENDERER_ROUTE_SET: ReadonlySet<string> = new Set([
  ...HTML_COMPONENT_TYPE_SET,
  'skip',
  'confirmation-hub',
])

export function isHtmlComponentType(ct: string): ct is HtmlComponentType {{
  return HTML_COMPONENT_TYPE_SET.has(ct as HtmlComponentType)
}}

export function getRendererEntry(ct: string): HtmlRendererEntry | undefined {{
  return HTML_RENDERER_REGISTRY.get(ct as HtmlComponentType)
}}

export function getSheetIcon(ct: string): string {{
  return getRendererEntry(ct)?.icon ?? PLACEHOLDER_ICONS[ct] ?? '📄'
}}

export function getContextPropsStrategy(ct: string): ContextPropsStrategy {{
  const entry = getRendererEntry(ct)
  return entry?.contextProps ?? 'none'
}}

export function validateRegistryUniqueness(entries: Iterable<HtmlRendererEntry>): {{
  valid: boolean
  duplicates: string[]
}} {{
  const seen = new Set<string>()
  const duplicates: string[] = []
  for (const entry of entries) {{
    if (seen.has(entry.componentType)) {{
      duplicates.push(entry.componentType)
    }}
    seen.add(entry.componentType)
  }}
  return {{ valid: duplicates.length === 0, duplicates }}
}}

export function getAllComponentTypes(): ReadonlySet<string> {{
  return new Set([...HTML_RENDERER_REGISTRY.keys()])
}}

export function getAllEntries(): readonly HtmlRendererEntry[] {{
  return [...HTML_RENDERER_REGISTRY.values()]
}}

export function getEntriesByDomain(domain: RegistryDomain): HtmlRendererEntry[] {{
  return [...DOMAIN_ENTRY_ARRAYS[domain]]
}}

// Keep Component import referenced for type consumers that re-export patterns
void 0 as unknown as Component
'''
    BARREL_PATH.write_text(barrel, encoding="utf-8", newline="\n")
    print(f"wrote {BARREL_PATH.relative_to(ROOT)}")


def write_facade() -> None:
    facade = '''/**
 * htmlRendererRegistry — thin facade over registry barrel (PAC Task 20)
 *
 * Public API preserved for existing callers. Entry arrays live in
 * `registry/entries/*.ts`; assembly + collision checks live in `registry/index.ts`.
 */
export type { HtmlRendererEntry, ContextPropsStrategy } from './registry/types'
export type { HtmlComponentType, RegistryDomain } from './registry'

export {
  REGISTRY_LIST,
  DOMAIN_ENTRY_ARRAYS,
  HTML_RENDERER_REGISTRY,
  HTML_COMPONENT_TYPE_SET,
  HTML_RENDERER_ROUTE_SET,
  PLACEHOLDER_ICONS,
  assertUniqueRegistryComponentTypes,
  assertAllDomainArraysConsumed,
  validateRegistryUniqueness,
  isHtmlComponentType,
  getRendererEntry,
  getSheetIcon,
  getContextPropsStrategy,
  getAllComponentTypes,
  getAllEntries,
  getEntriesByDomain,
} from './registry'
'''
    SRC_REG.write_text(facade, encoding="utf-8", newline="\n")
    print(f"wrote thin facade {SRC_REG.relative_to(ROOT)}")


def write_golden(entries: list[tuple[str, str]], domains: dict[str, str]) -> None:
    import json

    rows = []
    for ct, obj in entries:
        icon_m = re.search(r"icon:\s*'((?:\\'|[^'])*)'", obj)
        label_m = re.search(r"label:\s*'((?:\\'|[^'])*)'", obj)
        emits_m = re.search(r"emits:\s*\[([\s\S]*?)\]", obj)
        ctx_m = re.search(r"contextProps:\s*'([^']+)'", obj)
        import_m = re.search(r"import\(([^)]+)\)", obj)
        emits = re.findall(r"'([^']*)'", emits_m.group(1)) if emits_m else []
        import_path = import_m.group(1).strip().strip("'\"") if import_m else ""
        # Normalize to original ./ relative for golden comparison stability
        if import_path.startswith("../../"):
            import_path = "./" + import_path[6:]
        rows.append(
            {
                "componentType": ct,
                "importPath": import_path,
                "icon": icon_m.group(1) if icon_m else "",
                "label": (label_m.group(1).replace("\\'", "'") if label_m else ""),
                "emits": emits,
                "contextProps": ctx_m.group(1) if ctx_m else None,
                "domain": domains[ct],
            }
        )
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {GOLDEN_PATH.relative_to(ROOT)}")


def main() -> int:
    source_path = SRC_REG
    if SRC_REG.exists() and "const REGISTRY_LIST" not in SRC_REG.read_text(encoding="utf-8"):
        if SRC_BAK.exists():
            source_path = SRC_BAK
            print(f"using backup {SRC_BAK}")
        else:
            print(
                "htmlRendererRegistry.ts has no REGISTRY_LIST and no backup — abort",
                file=sys.stderr,
            )
            return 1
    if not source_path.exists():
        print(f"missing {source_path}", file=sys.stderr)
        return 1
    src = source_path.read_text(encoding="utf-8")
    if "const REGISTRY_LIST" not in src:
        print("source has no REGISTRY_LIST", file=sys.stderr)
        return 1

    # Preserve monolithic source for re-runs
    if source_path == SRC_REG:
        SRC_BAK.write_text(src, encoding="utf-8", newline="\n")
        print(f"backed up monolithic → {SRC_BAK.relative_to(ROOT)}")

    const_imports = parse_const_imports(src)
    html_component_type_block = extract_html_component_type_union(src)

    list_marker = "const REGISTRY_LIST: HtmlRendererEntry[] = ["
    list_start = src.index(list_marker) + len(list_marker)
    assert_at = src.index("assertUniqueRegistryComponentTypes(REGISTRY_LIST)", list_start)
    before = src[list_start:assert_at]
    last_bracket = before.rfind("]")
    list_body = before[:last_bracket]

    # Replace D_FORM spread with placeholder so object splitter sees only real objects
    list_body_clean, n_sub = re.subn(
        r"// D 子模式[\s\S]*?\}\)\),",
        "/* __D_FORM_EXPANDED__ */",
        list_body,
        count=1,
    )
    if n_sub != 1:
        print("WARN: D_FORM spread replacement count =", n_sub, file=sys.stderr)

    raw_objs = split_top_level_objects(list_body_clean)
    print(f"parsed object literals (excl d-form spread): {len(raw_objs)}")

    normalized: list[tuple[str, str]] = []
    for obj in raw_objs:
        normalized.append(normalize_entry_object(obj, const_imports))

    # Insert expanded d-form entries after c-note-table (original order)
    d_forms = expand_d_form_entries(const_imports)
    insert_at = next(i for i, (ct, _) in enumerate(normalized) if ct == "c-note-table") + 1
    all_entries = normalized[:insert_at] + d_forms + normalized[insert_at:]

    # Uniqueness
    seen: set[str] = set()
    for ct, _ in all_entries:
        if ct in seen:
            raise SystemExit(f"duplicate componentType: {ct}")
        seen.add(ct)

    domains = {ct: assign_domain(ct) for ct, _ in all_entries}
    by_domain: dict[str, list[tuple[str, str]]] = {
        d: [] for d in ("core", "forms", "programs", "confirmations", "reports", "specialized")
    }
    for ct, obj in all_entries:
        by_domain[domains[ct]].append((ct, obj))

    counts = {d: len(v) for d, v in by_domain.items()}
    total = sum(counts.values())
    print("domain counts:", counts)
    print("total unique:", total)
    if total != len(all_entries):
        raise SystemExit("partition size mismatch")
    for d, arr in by_domain.items():
        if not arr:
            raise SystemExit(f"domain {d} is empty — partition rules too aggressive?")

    ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
    for d in ("core", "forms", "programs", "confirmations", "reports", "specialized"):
        emit_entry_file(d, by_domain[d])

    write_barrel(html_component_type_block)
    write_facade()
    write_golden(all_entries, domains)
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
