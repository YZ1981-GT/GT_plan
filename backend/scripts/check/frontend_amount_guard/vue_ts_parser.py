"""
Lightweight Vue SFC / TypeScript parser for the amount display guard.

Extracts enough structure to identify:
- Template elements (tags, attributes, text interpolations)
- Script imports and function calls
- Component props bindings

This does NOT use a full AST parser – it operates on regex + simple
state-machine parsing, sufficient for the structural signals defined
in NUMERIC_CANDIDATE_RULES.

Design reference: §17 G6, §15 A8.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .rules import (
    EXPLICIT_KIND_COMPONENTS,
    KIND_PROP_COMPONENTS,
    RUNTIME_KIND_CALLEES,
    S2_NUMERIC_CALLS,
    S2_NUMERIC_CONSTRUCTORS,
    LEGACY_NUMERIC_FORMATTERS,
    NON_DISPLAY_ELEMENTS,
    NON_DISPLAY_ATTRS,
    S1_RIGHT_ALIGN_ATTRS,
    CORE_VIOLATION_CODES,
    VIOLATION_AMOUNT_FMT_ON_NON_AMOUNT,
    VIOLATION_GT_AMOUNT_CELL_WITH_UNIT,
    VIOLATION_V2_FIXED_PX_FONT,
)


@dataclass
class DisplayNode:
    """A single display node found by the analyzer."""
    file: str
    line: int
    tag_or_expr: str
    kind_source: str  # "explicit:amount", "explicit:declared", "signal:S1", etc.
    signals: list[str] = field(default_factory=list)
    amount_keyword_hit: bool = False
    violation_code: str | None = None

    @property
    def is_unknown_numeric(self) -> bool:
        """True if this is a numeric candidate without explicit kind."""
        return self.kind_source.startswith("signal:")


@dataclass
class ParseResult:
    """Result of parsing a single file."""
    file: str
    parsed: bool = True
    error: str | None = None
    display_nodes: list[DisplayNode] = field(default_factory=list)
    imports: dict[str, str] = field(default_factory=dict)  # local_name -> source


# ── SFC section extraction ──────────────────────────────────

_SFC_SCRIPT_RE = re.compile(
    r"<script\b[^>]*>(.*?)</script>",
    re.DOTALL | re.IGNORECASE,
)
_SFC_TEMPLATE_RE = re.compile(
    r"<template\b[^>]*>(.*?)</template>",
    re.DOTALL | re.IGNORECASE,
)


def _extract_sfc_sections(content: str) -> tuple[str, str]:
    """Return (script_content, template_content) from a .vue file."""
    script = ""
    template = ""
    m = _SFC_SCRIPT_RE.search(content)
    if m:
        script = m.group(1)
    m = _SFC_TEMPLATE_RE.search(content)
    if m:
        template = m.group(1)
    return script, template


# ── Import extraction ────────────────────────────────────────

_IMPORT_RE = re.compile(
    r"""import\s+\{([^}]+)\}\s+from\s+['"]([^'"]+)['"]""",
)
_IMPORT_DEFAULT_RE = re.compile(
    r"""import\s+(\w+)\s+from\s+['"]([^'"]+)['"]""",
)


def _extract_imports(script: str) -> dict[str, str]:
    """Extract named and default imports: local_name -> module_path."""
    imports: dict[str, str] = {}
    for m in _IMPORT_RE.finditer(script):
        names_str, source = m.group(1), m.group(2)
        for name_part in names_str.split(","):
            name_part = name_part.strip()
            if " as " in name_part:
                _, alias = name_part.split(" as ", 1)
                imports[alias.strip()] = source
            elif name_part:
                imports[name_part] = source
    for m in _IMPORT_DEFAULT_RE.finditer(script):
        imports[m.group(1)] = m.group(2)
    return imports


# ── Template analysis ────────────────────────────────────────

# Match opening tags (self-closing or not)
_TAG_RE = re.compile(
    r"<([\w-]+)(\s[^>]*)?\s*/?>",
    re.DOTALL,
)

_ATTR_RE = re.compile(
    r"""(?::?)([\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""",
)

_INTERPOLATION_RE = re.compile(
    r"\{\{(.+?)\}\}",
    re.DOTALL,
)

# Match px font-size in style objects, but only files that actually declare an el-table-v2 renderer are in scope.
# The old implementation applied this regex to every TS expression in every file, so ordinary dialog/notification/CSS
# styles were all mislabeled as v2 renderer violations (63 false positives on 2026-11-06).
_PX_FONT_RE = re.compile(
    r"""(?:fontSize|font-size)\s*:\s*['"]?\d+px['"]?""",
)
_V2_RENDERER_RE = re.compile(r"\b(?:cellRenderer|headerCellRenderer)\s*:")

# S2 calls in expressions
_S2_CALL_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in S2_NUMERIC_CALLS) + r")\s*\(",
)

_S2_CTOR_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in S2_NUMERIC_CONSTRUCTORS) + r")\s*[\(.]",
)

# S3 legacy formatter calls
_S3_FORMATTER_RE = re.compile(
    r"\b(" + "|".join(re.escape(f) for f in LEGACY_NUMERIC_FORMATTERS) + r")\s*\(",
)

# Amount formatter calls (for violation b detection)
_AMOUNT_FORMATTER_CALL_RE = re.compile(
    r"\b(GtAmountCell|displayAmount|fmtAmount)\b",
)


def _get_attrs(attr_str: str | None) -> dict[str, str]:
    """Parse attributes from a tag's attribute string."""
    if not attr_str:
        return {}
    result: dict[str, str] = {}
    for m in _ATTR_RE.finditer(attr_str):
        name = m.group(1)
        value = m.group(2) if m.group(2) is not None else m.group(3)
        result[name] = value
    return result


def _check_tag_for_signals(
    tag: str,
    attrs: dict[str, str],
    attr_str: str,
    line_content: str,
) -> tuple[str | None, list[str], str | None]:
    """
    Check a template tag for explicit kind sources and structural signals.

    Returns (kind_source, signals, violation_code).
    """
    signals: list[str] = []
    kind_source: str | None = None
    violation: str | None = None

    # Skip non-display elements
    if tag in NON_DISPLAY_ELEMENTS:
        return None, [], None

    # ① Explicit kind sources (highest priority)
    if tag in EXPLICIT_KIND_COMPONENTS:
        kind_source = f"explicit:{EXPLICIT_KIND_COMPONENTS[tag]}"
        # Check violation c: <GtAmountCell :unit> or <GtAmountCell unit>
        if "unit" in attrs or ":unit" in attrs:
            violation = VIOLATION_GT_AMOUNT_CELL_WITH_UNIT
        return kind_source, [], violation

    if tag in KIND_PROP_COMPONENTS:
        kind_val = attrs.get("kind") or attrs.get(":kind", "")
        if kind_val:
            kind_source = f"explicit:{kind_val}" if "." not in kind_val and "[" not in kind_val else "explicit:declared"
        else:
            kind_source = "explicit:declared"
        return kind_source, [], None

    # ② Structural signals
    # S1: right-aligned el-table-column
    if tag in ("el-table-column", "ElTableColumn"):
        for attr_name in S1_RIGHT_ALIGN_ATTRS:
            if attrs.get(attr_name) == "right" or attrs.get(f":{attr_name}") == "'right'":
                signals.append("S1")
                break

    # S4: GtColumn with type: 'number' – checked in script, not template
    # (see _check_script_for_signals)

    return kind_source, signals, violation


def _check_expression_signals(expr: str) -> list[str]:
    """Check an expression (interpolation or attribute binding) for signals."""
    signals: list[str] = []

    # S2: numeric calls
    if _S2_CALL_RE.search(expr) or _S2_CTOR_RE.search(expr):
        signals.append("S2")

    # S3: legacy formatter calls
    if _S3_FORMATTER_RE.search(expr):
        signals.append("S3")

    return signals


def parse_file(path: Path, content: str | None = None) -> ParseResult:
    """
    Parse a .vue or .ts file and identify display nodes.

    Returns a ParseResult with all found display nodes, their signals,
    and any violations.
    """
    rel = str(path)
    if content is None:
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return ParseResult(file=rel, parsed=False, error=str(e))

    result = ParseResult(file=rel)

    try:
        suffix = path.suffix.lower()
        if suffix == ".vue":
            script, template = _extract_sfc_sections(content)
            result.imports = _extract_imports(script)
            _analyze_template(template, result, content)
            _analyze_script_expressions(script, result, content)
        else:
            # .ts / .js / .tsx etc.
            result.imports = _extract_imports(content)
            _analyze_script_expressions(content, result, content)
    except Exception as e:
        result.parsed = False
        result.error = f"Parse error: {e}"

    return result


def _line_number(full_content: str, pos: int) -> int:
    """Get 1-based line number for a character position."""
    return full_content[:pos].count("\n") + 1


def _analyze_template(template: str, result: ParseResult, full_content: str) -> None:
    """Analyze a Vue template for display nodes."""
    for m in _TAG_RE.finditer(template):
        tag = m.group(1)
        attr_str = m.group(2) or ""
        attrs = _get_attrs(attr_str)
        line = _line_number(full_content, full_content.find(m.group(0)))

        kind_source, signals, violation = _check_tag_for_signals(
            tag, attrs, attr_str, m.group(0)
        )

        # Check for interpolations within context of this tag position
        # (simplified: we check the full attr_str for expression signals)
        expr_signals = _check_expression_signals(attr_str)
        signals.extend(expr_signals)

        if kind_source or signals:
            node = DisplayNode(
                file=result.file,
                line=line,
                tag_or_expr=tag,
                kind_source=kind_source or (f"signal:{signals[0]}" if signals else "unknown"),
                signals=signals,
                violation_code=violation,
            )
            result.display_nodes.append(node)

    # Also check interpolations for S2/S3 signals
    for m in _INTERPOLATION_RE.finditer(template):
        expr = m.group(1)
        signals = _check_expression_signals(expr)
        if signals:
            line = _line_number(full_content, full_content.find(m.group(0)))

            # Check for runtime kind callee
            kind_source = None
            for callee in RUNTIME_KIND_CALLEES:
                if callee in expr:
                    kind_source = "explicit:declared"
                    break

            result.display_nodes.append(DisplayNode(
                file=result.file,
                line=line,
                tag_or_expr=f"{{{{{expr.strip()[:60]}}}}}",
                kind_source=kind_source or f"signal:{signals[0]}",
                signals=signals,
            ))


def _analyze_script_expressions(
    script: str,
    result: ParseResult,
    full_content: str,
) -> None:
    """Analyze script section for S2/S3/S4 signals and formatter usage."""
    for m in _S3_FORMATTER_RE.finditer(script):
        func_name = m.group(1)
        line = _line_number(full_content, full_content.find(m.group(0)))
        result.display_nodes.append(DisplayNode(
            file=result.file,
            line=line,
            tag_or_expr=func_name,
            kind_source="signal:S3",
            signals=["S3"],
        ))

    # Check for v2 fixed px font-size (violation d). A file without a cellRenderer/headerCellRenderer
    # has an empty denominator and must not turn ordinary font styles into v2 violations.
    if _V2_RENDERER_RE.search(script):
        for m in _PX_FONT_RE.finditer(script):
            line = _line_number(full_content, full_content.find(m.group(0)))
            result.display_nodes.append(DisplayNode(
                file=result.file,
                line=line,
                tag_or_expr=m.group(0),
                kind_source="signal:v2_px",
                signals=["v2_px"],
                violation_code=VIOLATION_V2_FIXED_PX_FONT,
            ))
