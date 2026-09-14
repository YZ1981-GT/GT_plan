"""Generate the versioned component capability manifest from existing declarations.

The generator deliberately uses only the Python standard library and never imports
backend application modules.  Python declarations are read through ``ast``;
TypeScript declarations are parsed from comment-stripped, structurally bounded
source.  Any unsupported declaration shape fails closed instead of silently
omitting component types.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = PROJECT_ROOT / "backend" / "app" / "data" / "component_capabilities.json"
TYPESCRIPT_PROJECTION_PATH = (
    PROJECT_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "types"
    / "componentCapabilities.generated.ts"
)

SCHEMA_VERSION = 1
OWNER = "workpaper-rendering"
HOST_POLICIES = frozenset(
    {"skip", "redirect", "univer", "onlyoffice", "confirmation", "html", "unresolved"}
)
_COMPONENT_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


class SourceExtractionError(ValueError):
    """A declaration cannot be interpreted without making an unsafe assumption."""


@dataclass(frozen=True, slots=True)
class SourcePaths:
    """All authoritative source paths consumed by the generator."""

    classification: Path
    render_dispatch: Path
    html_registry: Path
    overrides: Path
    host_declarations: Path


DEFAULT_SOURCE_PATHS = SourcePaths(
    classification=PROJECT_ROOT / "backend" / "app" / "services" / "wp_classification_service.py",
    render_dispatch=PROJECT_ROOT / "backend" / "app" / "routers" / "wp_render_strategies" / "__init__.py",
    html_registry=(
        PROJECT_ROOT
        / "audit-platform"
        / "frontend"
        / "src"
        / "components"
        / "workpaper"
        / "registry"
        / "index.ts"
    ),
    overrides=PROJECT_ROOT / "backend" / "app" / "data" / "wp_code_overrides.json",
    host_declarations=PROJECT_ROOT / "backend" / "app" / "data" / "component_host_declarations.json",
)


@dataclass(frozen=True, slots=True)
class ObservedSources:
    """Immutable projections extracted independently from every existing source."""

    valid_component_types: frozenset[str]
    backend_renderer_types: frozenset[str]
    frontend_registry_types: frozenset[str]
    html_union_types: frozenset[str]
    override_value_types: frozenset[str]
    html_whitelist_types: frozenset[str]
    confirmation_types: frozenset[str]

    @property
    def all_component_types(self) -> frozenset[str]:
        return frozenset().union(
            self.valid_component_types,
            self.backend_renderer_types,
            self.frontend_registry_types,
            self.html_union_types,
            self.override_value_types,
            self.html_whitelist_types,
            self.confirmation_types,
        )

    def named_sets(self) -> tuple[tuple[str, frozenset[str]], ...]:
        return (
            ("VALID_COMPONENT_TYPES", self.valid_component_types),
            ("RENDERER_DISPATCH", self.backend_renderer_types),
            ("REGISTRY_LIST", self.frontend_registry_types),
            ("HtmlComponentType", self.html_union_types),
            ("wp_code_overrides", self.override_value_types),
            ("_ONLYOFFICE_HTML_WHITELIST", self.html_whitelist_types),
            ("_CONFIRMATION_COMPONENTS", self.confirmation_types),
        )


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SourceExtractionError(f"cannot read source {path}: {exc}") from exc


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return tuple(sorted(duplicates))


def _validate_component_types(values: Sequence[str], label: str) -> frozenset[str]:
    duplicates = _duplicates(values)
    if duplicates:
        raise SourceExtractionError(f"{label} contains duplicate component types: {duplicates}")
    invalid = sorted(value for value in values if not _COMPONENT_TYPE_RE.fullmatch(value))
    if invalid:
        raise SourceExtractionError(f"{label} contains invalid component types: {invalid}")
    return frozenset(values)


def _find_python_assignment(tree: ast.Module, variable_name: str, path: Path) -> ast.AST:
    matches: list[ast.AST] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == variable_name and node.value is not None:
                matches.append(node.value)
        elif isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == variable_name for target in node.targets):
                matches.append(node.value)
    if len(matches) != 1:
        raise SourceExtractionError(
            f"{path}: expected exactly one top-level assignment to {variable_name}, found {len(matches)}"
        )
    return matches[0]


def _parse_python(path: Path) -> ast.Module:
    source = _read_text(path)
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise SourceExtractionError(f"cannot parse Python source {path}: {exc}") from exc


def extract_python_string_set(path: Path, variable_name: str) -> frozenset[str]:
    """Extract a literal top-level ``set[str]`` without importing the module."""

    value = _find_python_assignment(_parse_python(path), variable_name, path)
    if not isinstance(value, ast.Set):
        raise SourceExtractionError(f"{path}: {variable_name} must be a literal set")
    values: list[str] = []
    for element in value.elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            raise SourceExtractionError(
                f"{path}: {variable_name} contains non-literal element at line {element.lineno}"
            )
        values.append(element.value)
    return _validate_component_types(values, f"{path}:{variable_name}")


def extract_python_dict_keys(path: Path, variable_name: str) -> frozenset[str]:
    """Extract literal string keys and reject ``**`` expansion or duplicate keys."""

    value = _find_python_assignment(_parse_python(path), variable_name, path)
    if not isinstance(value, ast.Dict):
        raise SourceExtractionError(f"{path}: {variable_name} must be a literal dict")
    keys: list[str] = []
    for key, item in zip(value.keys, value.values, strict=True):
        if key is None:
            raise SourceExtractionError(f"{path}: {variable_name} contains unsupported ** expansion")
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            raise SourceExtractionError(
                f"{path}: {variable_name} contains non-literal key at line {key.lineno}"
            )
        if not isinstance(item, (ast.Name, ast.Attribute)):
            raise SourceExtractionError(
                f"{path}: {variable_name}[{key.value!r}] has unsupported renderer expression"
            )
        keys.append(key.value)
    return _validate_component_types(keys, f"{path}:{variable_name}")


def _reject_duplicate_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SourceExtractionError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_override_value_types(path: Path) -> frozenset[str]:
    """Read strict string-to-string override JSON and return its observed values."""

    try:
        data = json.loads(_read_text(path), object_pairs_hook=_reject_duplicate_json_pairs)
    except json.JSONDecodeError as exc:
        raise SourceExtractionError(f"cannot parse JSON source {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceExtractionError(f"{path}: root must be an object")
    values: list[str] = []
    for key, value in data.items():
        if not isinstance(key, str) or not key:
            raise SourceExtractionError(f"{path}: override keys must be non-empty strings")
        if not isinstance(value, str):
            raise SourceExtractionError(f"{path}: override {key!r} must map to a string")
        values.append(value)
    return _validate_component_types(sorted(set(values)), f"{path}:values")


def strip_ts_comments(source: str) -> str:
    """Strip TypeScript comments while preserving strings, templates and newlines.

    Removed characters become spaces so declarations cannot be accidentally joined
    and diagnostics retain useful line positions.  Unterminated comments/strings fail
    closed.  The targeted declarations contain no regular-expression literals.
    """

    output: list[str] = []
    state = "code"
    quote = ""
    index = 0
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char in {"'", '"', "`"}:
                state = "string"
                quote = char
                output.append(char)
                index += 1
            elif char == "/" and nxt == "/":
                state = "line_comment"
                output.extend((" ", " "))
                index += 2
            elif char == "/" and nxt == "*":
                state = "block_comment"
                output.extend((" ", " "))
                index += 2
            else:
                output.append(char)
                index += 1
        elif state == "string":
            output.append(char)
            if char == "\\":
                if index + 1 >= len(source):
                    raise SourceExtractionError("unterminated escape in TypeScript string")
                output.append(source[index + 1])
                index += 2
            elif char == quote:
                state = "code"
                quote = ""
                index += 1
            else:
                index += 1
        elif state == "line_comment":
            if char in "\r\n":
                output.append(char)
                state = "code"
            else:
                output.append(" ")
            index += 1
        else:
            if char == "*" and nxt == "/":
                output.extend((" ", " "))
                index += 2
                state = "code"
            else:
                output.append(char if char in "\r\n" else " ")
                index += 1
    if state != "code":
        raise SourceExtractionError(f"unterminated TypeScript {state.replace('_', ' ')}")
    return "".join(output)


def _unique_match(source: str, pattern: str, label: str) -> re.Match[str]:
    matches = list(re.finditer(pattern, source, flags=re.MULTILINE))
    if len(matches) != 1:
        raise SourceExtractionError(f"expected exactly one {label} declaration, found {len(matches)}")
    return matches[0]


def _skip_space(source: str, index: int) -> int:
    while index < len(source) and source[index].isspace():
        index += 1
    return index


def _parse_ts_string(source: str, index: int) -> tuple[str, int]:
    if index >= len(source) or source[index] not in {"'", '"'}:
        raise SourceExtractionError(f"expected TypeScript string literal near offset {index}")
    quote = source[index]
    index += 1
    value: list[str] = []
    escapes = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", "'": "'", '"': '"'}
    while index < len(source):
        char = source[index]
        if char == quote:
            return "".join(value), index + 1
        if char == "\\":
            index += 1
            if index >= len(source):
                break
            escaped = source[index]
            value.append(escapes.get(escaped, escaped))
            index += 1
        else:
            value.append(char)
            index += 1
    raise SourceExtractionError("unterminated TypeScript string literal")


def _parse_entire_ts_string(source: str, label: str) -> str:
    index = _skip_space(source, 0)
    value, end = _parse_ts_string(source, index)
    if _skip_space(source, end) != len(source):
        raise SourceExtractionError(f"{label} must be a string literal")
    return value


def extract_ts_string_union(path: Path, type_name: str) -> frozenset[str]:
    """Extract an exported string-literal union using declaration boundaries."""

    source = strip_ts_comments(_read_text(path))
    match = _unique_match(
        source,
        rf"\bexport\s+type\s+{re.escape(type_name)}\s*=",
        f"TypeScript type {type_name}",
    )
    index = match.end()
    values: list[str] = []
    while True:
        index = _skip_space(source, index)
        if index < len(source) and source[index] == "|":
            index = _skip_space(source, index + 1)
        elif values:
            break
        if index >= len(source) or source[index] not in {"'", '"'}:
            raise SourceExtractionError(f"{path}: {type_name} must contain only string literals")
        value, index = _parse_ts_string(source, index)
        values.append(value)
        lookahead = _skip_space(source, index)
        if lookahead < len(source) and source[lookahead] == "|":
            index = lookahead
            continue
        index = lookahead
        break
    boundary = source[index : index + 32]
    if index < len(source) and not re.match(
        r"^(?:;\s*)?(?:export\b|const\b|interface\b|type\b|$)", boundary
    ):
        raise SourceExtractionError(f"{path}: unsupported trailing syntax in {type_name}")
    return _validate_component_types(values, f"{path}:{type_name}")


def _scan_balanced(source: str, start: int, opening: str, closing: str) -> int:
    if start >= len(source) or source[start] != opening:
        raise SourceExtractionError(f"expected {opening!r} near offset {start}")
    depth = 0
    index = start
    quote = ""
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                break
        index += 1
    raise SourceExtractionError(f"unbalanced TypeScript delimiter {opening}{closing}")


def _split_top_level(source: str, delimiter: str = ",") -> list[str]:
    parts: list[str] = []
    start = 0
    stack: list[str] = []
    pairs = {"(": ")", "[": "]", "{": "}"}
    quote = ""
    index = 0
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                raise SourceExtractionError(f"mismatched TypeScript delimiter near offset {index}")
        elif char == delimiter and not stack:
            part = source[start:index].strip()
            if part:
                parts.append(part)
            start = index + 1
        index += 1
    if quote or stack:
        raise SourceExtractionError("unterminated TypeScript expression")
    tail = source[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _extract_component_types_from_entry_file(path: Path) -> list[str]:
    """Extract ``componentType`` literals from an explicit domain entry array.

    Fail-closed on **element count**, not on "no literals at all": the exported
    ``xxxEntries: HtmlRendererEntry[]`` array is split into top-level elements and
    every element must resolve to exactly one ``componentType: '…'`` string
    literal. A derived form such as ``D_FORM_SUBTYPES.map((subtype) => ({
    componentType: subtype }))`` yields 0 literals for its element and is named
    in the error, instead of being silently dropped from the manifest.
    """

    source = strip_ts_comments(_read_text(path))
    match = _unique_match(
        source,
        r"\b(?:export\s+)?const\s+[A-Za-z_][A-Za-z0-9_]*Entries\s*"
        r"(?::\s*HtmlRendererEntry\s*\[\s*\]\s*)?=\s*(?=\[)",
        f"{path}:xxxEntries array",
    )
    start = _skip_space(source, match.end())
    end = _scan_balanced(source, start, "[", "]")
    elements = _split_top_level(source[start + 1 : end])
    if not elements:
        raise SourceExtractionError(f"{path}: domain entry array is empty")

    values: list[str] = []
    unresolved: list[str] = []
    for element in elements:
        literals = re.findall(r"\bcomponentType\s*:\s*'([^']+)'", element)
        if len(literals) == 1:
            values.append(literals[0])
        else:
            # 0 literals (derived/spread) or >1 (malformed element): name it.
            preview = " ".join(element.split())[:80]
            unresolved.append(f"[{len(literals)} literals] {preview}")
    if unresolved:
        raise SourceExtractionError(
            f"{path}: {len(unresolved)} entry element(s) without exactly one "
            f"componentType literal (derived/spread not supported): {unresolved}"
        )
    if len(values) != len(elements):
        raise SourceExtractionError(
            f"{path}: extracted {len(values)} componentType(s) from "
            f"{len(elements)} top-level element(s)"
        )
    return values


def _extract_domain_split_registry_types(path: Path, source: str) -> frozenset[str]:
    """Parse barrel REGISTRY_LIST that only spreads explicit ``*Entries`` domain arrays."""

    entries_dir = path.parent / "entries"
    if not entries_dir.is_dir():
        raise SourceExtractionError(
            f"{path}: domain-split REGISTRY_LIST requires sibling entries/ directory"
        )

    match = _unique_match(
        source,
        r"\b(?:export\s+)?const\s+REGISTRY_LIST\s*:\s*HtmlRendererEntry\s*\[\s*\]\s*=",
        "REGISTRY_LIST",
    )
    start = _skip_space(source, match.end())
    end = _scan_balanced(source, start, "[", "]")
    entries: list[str] = []
    consumed_files: list[Path] = []
    for element in _split_top_level(source[start + 1 : end]):
        stripped = element.strip()
        spread = re.fullmatch(r"\.\.\.([A-Za-z_][A-Za-z0-9_]*)", stripped)
        if not spread:
            raise SourceExtractionError(
                f"unknown REGISTRY_LIST spread (fail-closed): {stripped[:80]!r}"
            )
        export_name = spread.group(1)
        if not export_name.endswith("Entries"):
            raise SourceExtractionError(
                f"unknown REGISTRY_LIST spread (fail-closed): {stripped[:80]!r}"
            )
        domain = export_name[: -len("Entries")]
        entry_path = entries_dir / f"{domain}.ts"
        if not entry_path.is_file():
            raise SourceExtractionError(
                f"unknown REGISTRY_LIST spread (fail-closed): {stripped[:80]!r}"
            )
        entries.extend(_extract_component_types_from_entry_file(entry_path))
        consumed_files.append(entry_path)

    # Every entries/*.ts file must be consumed (prevents unconsumed domain dead files).
    on_disk = sorted(p for p in entries_dir.glob("*.ts") if p.is_file())
    missing = [p.name for p in on_disk if p not in consumed_files]
    if missing:
        raise SourceExtractionError(
            f"{entries_dir}: domain entry files not consumed by REGISTRY_LIST: {missing}"
        )
    return _validate_component_types(entries, f"{path}:REGISTRY_LIST")


def extract_html_registry_types(path: Path) -> frozenset[str]:
    """Parse domain-split REGISTRY_LIST (``...xxxEntries`` + ``entries/*.ts``).

    Legacy monolith ``D_FORM_SUBTYPES.map`` expansion is no longer supported — production
    and synthetic fixtures must use explicit domain entry arrays.
    """

    source = strip_ts_comments(_read_text(path))
    if (path.parent / "entries").is_dir():
        return _extract_domain_split_registry_types(path, source)

    # Fail closed: a lone file without entries/ is not a supported registry shape.
    raise SourceExtractionError(
        f"{path}: expected domain-split registry (sibling entries/ + ...*Entries spreads); "
        "D_FORM_SUBTYPES.map monolith is no longer accepted"
    )


def load_host_declaration_sets(path: Path) -> tuple[frozenset[str], frozenset[str]]:
    """Load confirmation + HTML whitelist declaration sets (not runtime adjudicators)."""

    try:
        data = json.loads(_read_text(path), object_pairs_hook=_reject_duplicate_json_pairs)
    except json.JSONDecodeError as exc:
        raise SourceExtractionError(f"cannot parse JSON source {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceExtractionError(f"{path}: root must be an object")
    required = {"schema_version", "confirmation_components", "onlyoffice_html_whitelist"}
    if not required.issubset(data):
        missing = sorted(required - set(data))
        raise SourceExtractionError(f"{path}: missing keys {missing}")
    confirmation = data["confirmation_components"]
    whitelist = data["onlyoffice_html_whitelist"]
    if not isinstance(confirmation, list) or not isinstance(whitelist, list):
        raise SourceExtractionError(f"{path}: confirmation/whitelist must be arrays")
    if any(not isinstance(item, str) for item in confirmation + whitelist):
        raise SourceExtractionError(f"{path}: declaration entries must be strings")
    return (
        _validate_component_types(confirmation, f"{path}:confirmation_components"),
        _validate_component_types(whitelist, f"{path}:onlyoffice_html_whitelist"),
    )


def extract_observed_sources(paths: SourcePaths = DEFAULT_SOURCE_PATHS) -> ObservedSources:
    """Extract all requested source projections without executing project code."""

    confirmation_types, html_whitelist_types = load_host_declaration_sets(paths.host_declarations)
    return ObservedSources(
        valid_component_types=extract_python_string_set(
            paths.classification, "VALID_COMPONENT_TYPES"
        ),
        backend_renderer_types=extract_python_dict_keys(
            paths.render_dispatch, "RENDERER_DISPATCH"
        ),
        frontend_registry_types=extract_html_registry_types(paths.html_registry),
        html_union_types=extract_ts_string_union(paths.html_registry, "HtmlComponentType"),
        override_value_types=load_override_value_types(paths.overrides),
        html_whitelist_types=html_whitelist_types,
        confirmation_types=confirmation_types,
    )


def adjudicate_host_policy(component_type: str, sources: ObservedSources) -> str:
    """投影 legacy 多 sheet host fate，供 planner 等价接管。

    顺序与旧 ``wp_render_config`` 完全一致：有后端 renderer 时先执行 renderer；
    无 renderer 时 confirmation 集合保留专属宿主；HTML 白名单保留 grid/HTML；
    其余 componentType 在多 sheet 场景降级到 OnlyOffice。前端注册本身不等于
    HTML host 授权，否则会把旧运行态从 OnlyOffice 静默改成 HTML。
    """

    if component_type == "skip":
        # Legacy 在多 sheet 中先做无 renderer host fallback，后做 skip 检查；
        # 因而 derive 得到 skip 时实际落到 OnlyOffice。单 sheet planner 不消费此 policy。
        return "onlyoffice"
    if component_type.startswith("redirect-"):
        return "redirect"
    if component_type == "univer":
        return "univer"
    if component_type in {"onlyoffice", "onlyoffice-sheet"}:
        return "onlyoffice"
    if component_type in sources.backend_renderer_types:
        return "html"
    if component_type in sources.confirmation_types:
        return "confirmation"
    if component_type in sources.html_whitelist_types:
        return "html"
    return "onlyoffice"


def _source_digest(sources: Sequence[str]) -> str:
    """Stable short digest of the source-name set a componentType appears in.

    Changing which sources declare a type changes the digest, so an on-disk
    exemption whose digest no longer matches is drift (fails ``--check``).
    """
    import hashlib

    joined = "|".join(sorted(sources))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def build_exemptions(
    observed: ObservedSources,
    components: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Derive an adjudication record for every intentional capability asymmetry.

    Req 1.5: a componentType that appears in only part of the true sources must be
    registered (not silently dropped from the denominator). We machine-derive one
    exemption per asymmetry so the set can never be hand-drifted, and Req 1.4 is
    enforced because a *new* asymmetry regenerates a *new* exemption ⇒ manifest
    drift ⇒ ``--check`` fails until re-applied and reviewed.

    Three asymmetry classes:
      * frontend_only  — has_frontend_component, no backend renderer
      * backend_only   — has_backend_renderer, no frontend component
      * manifest_only  — neither renderer nor frontend component (policy-only:
                         skip / redirect / hub host that no renderer/registry owns)
    """
    backend = set(observed.backend_renderer_types)
    frontend = set(observed.frontend_registry_types)
    exemptions: list[dict[str, str]] = []
    for component_type in sorted(components):
        entry = components[component_type]
        has_be = bool(entry["has_backend_renderer"])
        has_fe = bool(entry["has_frontend_component"])
        sources = tuple(entry.get("sources", ()))
        if has_be and has_fe:
            continue  # symmetric; no adjudication needed
        if has_fe and not has_be:
            klass = "frontend_only"
            reason = (
                "Pure frontend component with no backend renderer "
                "(RENDERER_DISPATCH absent); intentional asymmetry."
            )
        elif has_be and not has_fe:
            klass = "backend_only"
            reason = (
                "Backend renderer with no htmlRendererRegistry entry "
                "(host handled outside the HTML registry, e.g. univer/onlyoffice); "
                "intentional asymmetry."
            )
        else:
            klass = "manifest_only"
            reason = (
                "Policy-only host (skip / redirect / hub) owned by neither "
                "RENDERER_DISPATCH nor htmlRendererRegistry; intentional asymmetry."
            )
        _ = (backend, frontend)  # membership already reflected via entry flags
        exemptions.append(
            {
                "component_type": component_type,
                "owner": OWNER,
                "reason": f"[{klass}] {reason}",
                "source_digest": _source_digest(sources),
            }
        )
    return exemptions


def build_manifest(paths: SourcePaths = DEFAULT_SOURCE_PATHS) -> dict[str, Any]:
    """Build a deterministic manifest from the union of all observed declarations."""

    observed = extract_observed_sources(paths)
    components: dict[str, dict[str, Any]] = {}
    for component_type in sorted(observed.all_component_types):
        policy = adjudicate_host_policy(component_type, observed)
        if policy not in HOST_POLICIES:  # defensive invariant for future edits
            raise SourceExtractionError(f"invalid generated host policy: {policy}")
        entry_sources = [
            source_name
            for source_name, values in observed.named_sets()
            if component_type in values
        ]
        components[component_type] = {
            "owner": OWNER,
            "has_backend_renderer": component_type in observed.backend_renderer_types,
            "has_frontend_component": component_type in observed.frontend_registry_types,
            "override_allowed": component_type in observed.valid_component_types,
            "host_policy": policy,
            "status": "active",
            "sources": entry_sources,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "components": components,
        "exemptions": build_exemptions(observed, components),
    }


def render_manifest(manifest: Mapping[str, Any]) -> str:
    """Render canonical UTF-8 JSON with deterministic key ordering."""

    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_typescript_projection(manifest: Mapping[str, Any]) -> str:
    """Render the frontend component-type projection from the same manifest."""

    raw_components = manifest.get("components")
    if not isinstance(raw_components, Mapping):
        raise SourceExtractionError("manifest components must be an object")
    component_types = sorted(str(value) for value in raw_components)
    active_frontend_types = sorted(
        component_type
        for component_type, raw_entry in raw_components.items()
        if isinstance(raw_entry, Mapping)
        and raw_entry.get("status") == "active"
        and raw_entry.get("has_frontend_component") is True
    )

    def render_array(name: str, values: Sequence[str]) -> list[str]:
        return [
            f"export const {name} = [",
            *(f"  {json.dumps(value, ensure_ascii=False)}," for value in values),
            "] as const",
        ]

    lines = [
        "/* eslint-disable */",
        "// 此文件由 generate_component_capability_manifest.py 生成，禁止手工编辑。",
        f"export const COMPONENT_CAPABILITY_SCHEMA_VERSION = {SCHEMA_VERSION} as const",
        "",
        *render_array("COMPONENT_TYPES", component_types),
        "",
        "export type DeclaredWpComponentType = (typeof COMPONENT_TYPES)[number]",
        "// 运行态允许后端新增值；精确清单由 DeclaredWpComponentType 与 manifest 守卫承担。",
        "export type WpComponentType = string",
        "",
        *render_array("ACTIVE_FRONTEND_COMPONENT_TYPES", active_frontend_types),
        "",
        "export type ActiveFrontendComponentType =",
        "  (typeof ACTIVE_FRONTEND_COMPONENT_TYPES)[number]",
        "",
    ]
    return "\n".join(lines)


def apply_manifest(
    *,
    paths: SourcePaths = DEFAULT_SOURCE_PATHS,
    output_path: Path = MANIFEST_PATH,
    typescript_output_path: Path = TYPESCRIPT_PROJECTION_PATH,
) -> dict[str, Any]:
    manifest = build_manifest(paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_manifest(manifest), encoding="utf-8", newline="\n")
    typescript_output_path.parent.mkdir(parents=True, exist_ok=True)
    typescript_output_path.write_text(
        render_typescript_projection(manifest),
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def check_manifest(
    *,
    paths: SourcePaths = DEFAULT_SOURCE_PATHS,
    output_path: Path = MANIFEST_PATH,
    typescript_output_path: Path = TYPESCRIPT_PROJECTION_PATH,
) -> tuple[bool, str]:
    manifest = build_manifest(paths)
    expected_manifest = render_manifest(manifest)
    expected_typescript = render_typescript_projection(manifest)
    try:
        actual_manifest = output_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"cannot read manifest {output_path}: {exc}"
    if actual_manifest != expected_manifest:
        return False, f"manifest drift: run {Path(__file__).name} --apply"
    try:
        actual_typescript = typescript_output_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"cannot read TypeScript projection {typescript_output_path}: {exc}"
    if actual_typescript != expected_typescript:
        return False, f"TypeScript projection drift: run {Path(__file__).name} --apply"
    return True, f"manifest and TypeScript projection are current ({len(manifest['components'])} component types)"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true", help="regenerate the checked-in projections")
    mode.add_argument("--check", action="store_true", help="fail if a checked-in projection has drift")
    parser.add_argument("--output", type=Path, default=MANIFEST_PATH)
    parser.add_argument(
        "--typescript-output",
        type=Path,
        default=TYPESCRIPT_PROJECTION_PATH,
    )
    args = parser.parse_args(argv)

    try:
        if args.apply:
            manifest = apply_manifest(
                output_path=args.output,
                typescript_output_path=args.typescript_output,
            )
            print(
                f"[OK] wrote {args.output} and {args.typescript_output} "
                f"({len(manifest['components'])} component types)"
            )
            return 0
        current, detail = check_manifest(
            output_path=args.output,
            typescript_output_path=args.typescript_output,
        )
        print(f"[{'OK' if current else 'FAIL'}] {detail}")
        return 0 if current else 1
    except (SourceExtractionError, OSError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
