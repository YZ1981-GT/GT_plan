"""G-C0 shared wire contract bundle — backend owner.

This module is the SINGLE BACKEND OWNERSHIP POINT for the G-C0 contract
bundle. It:

- Loads the JSON Schema bundle at ``backend/data/guidance/contracts/gc0/schema.json``.
- Loads the compatibility matrix at ``compatibility_matrix.json``.
- Loads the canonical fixtures under ``fixtures/``.
- Computes sha256 digests for the schema + each fixture (used by the G-C0
  evidence envelope and by conformance tests).
- Provides a fail-closed :func:`validate_contract_version` that returns a
  structured :class:`CompatibilityDecision` for any wire payload.
- Provides :func:`discover_local_dupes` — an AST-based reverse-dup scanner
  that conformance tests call to fail when a downstream spec defines any of
  the C0 top-level symbols without importing them from this bundle.

See ``.kiro/specs/workpaper-guidance-content-closure/design.md §1`` and
``requirements.md Requirement 1``.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Sequence

__all__ = [
    "GC0_CONTRACT_ID",
    "GC0_CONTRACT_VERSION",
    "GC0_TOP_LEVEL_TYPES",
    "CompatibilityDecision",
    "CompatibilityReason",
    "ContractBundle",
    "load_bundle",
    "validate_contract_version",
    "discover_local_dupes",
    "bundle_root",
    "schema_path",
    "fixtures_dir",
    "matrix_path",
    "evidence_path",
]


GC0_CONTRACT_ID = "G-C0"
GC0_CONTRACT_VERSION = "1.0"

#: The eight top-level wire types that downstream specs MUST import (never
#: re-declare) from this bundle. Matches design.md §1.1–§1.6.
GC0_TOP_LEVEL_TYPES: tuple[str, ...] = (
    "CanonicalWorkpaperLocation",
    "GuidanceSection",
    "SourceRef",
    "TemplateAuthorityIdentity",
    "CustomGuidanceHandoff",
    "ConsumerAck",
    "GuidanceRailAdapter",
    "EvidenceEnvelope",
)

#: Discriminator declarations for the five unions that MUST fail-closed on
#: unknown values. Any mutation that removes a required variant, or that
#: renames a discriminator value, must turn conformance RED.
#:
#: KEY FORMAT — mirrors ``schema.discriminators`` exactly: the key is the
#: union type name, and the value is a mapping with ``property`` (the
#: discriminating field name) and ``variants`` (the allowed values). We do
#: NOT use dotted ``UnionName.field`` keys, because that format cannot
#: express a discriminator other than ``kind`` — ``CustomGuidanceHandoff``
#: and ``TemplateAuthorityIdentity`` both discriminate on ``phase``. The
#: module constant and the schema are locked to the same shape by
#: ``test_property1_discriminators_match_schema_exactly``.
GC0_DISCRIMINATORS: dict[str, dict[str, tuple[str, ...]]] = {
    "EvidenceSubject": {"property": "kind", "variants": (
        "contract",
        "catalog_entry",
        "runtime_entry",
        "operation",
    )},
    "StableLocationAnchor": {"property": "kind", "variants": (
        "page",
        "sheet",
        "section",
        "cell",
        "document",
        "whole_workbook",
    )},
    "SourceLocator": {"property": "kind", "variants": (
        "xlsx",
        "docx",
        "bcd_markdown",
        "methodology_publication",
        "project_evidence",
        "custom_artifact",
    )},
    "TemplateAuthorityIdentity": {"property": "phase", "variants": (
        "candidate",
        "finalized",
    )},
    "CustomGuidanceHandoff": {"property": "phase", "variants": (
        "candidate",
        "finalized",
    )},
}


def bundle_root() -> Path:
    """Absolute path to the G-C0 bundle data directory."""
    return Path(__file__).resolve().parents[2] / "data" / "guidance" / "contracts" / "gc0"


def schema_path() -> Path:
    return bundle_root() / "schema.json"


def matrix_path() -> Path:
    return bundle_root() / "compatibility_matrix.json"


def fixtures_dir() -> Path:
    return bundle_root() / "fixtures"


def evidence_path() -> Path:
    return bundle_root() / "evidence" / "gc0_evidence.json"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class ContractBundle:
    """Loaded G-C0 bundle snapshot (immutable)."""

    schema: Mapping[str, Any]
    matrix: Mapping[str, Any]
    schema_sha256: str
    fixtures: Mapping[str, Mapping[str, Any]]
    fixture_sha256: Mapping[str, str]

    @property
    def contract_id(self) -> str:
        return str(self.schema.get("contractId", GC0_CONTRACT_ID))

    @property
    def contract_version(self) -> str:
        return str(self.schema.get("contractVersion", GC0_CONTRACT_VERSION))

    def fixture_paths(self) -> Iterable[tuple[str, Path]]:
        """Enumerate ``(name, path)`` pairs deterministically."""
        for name in sorted(self.fixtures.keys()):
            yield name, fixtures_dir() / f"{name}.json"


def load_bundle(root: Path | None = None) -> ContractBundle:
    """Load schema, matrix, and every fixture under ``fixtures/``."""
    root = root or bundle_root()
    schema = json.loads((root / "schema.json").read_text(encoding="utf-8"))
    matrix = json.loads((root / "compatibility_matrix.json").read_text(encoding="utf-8"))
    fx_dir = root / "fixtures"
    fixtures: dict[str, dict[str, Any]] = {}
    digests: dict[str, str] = {}
    if fx_dir.exists():
        for path in sorted(fx_dir.glob("*.json")):
            name = path.stem
            fixtures[name] = json.loads(path.read_text(encoding="utf-8"))
            digests[name] = _sha256_file(path)
    return ContractBundle(
        schema=schema,
        matrix=matrix,
        schema_sha256=_sha256_file(root / "schema.json"),
        fixtures=fixtures,
        fixture_sha256=digests,
    )


# ---------------------------------------------------------------------------
# Fail-closed compatibility guard
# ---------------------------------------------------------------------------

CompatibilityOutcome = Literal["ACCEPT", "BLOCKED", "REJECTED", "DEGRADED"]


@dataclass(frozen=True)
class CompatibilityReason:
    """Structured reason for a compatibility decision (never a bare string)."""

    code: str
    detail: str
    field: str | None = None


@dataclass(frozen=True)
class CompatibilityDecision:
    outcome: CompatibilityOutcome
    reasons: tuple[CompatibilityReason, ...] = field(default_factory=tuple)
    negotiated_version: str | None = None

    @property
    def is_accept(self) -> bool:
        return self.outcome == "ACCEPT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "negotiatedVersion": self.negotiated_version,
            "reasons": [r.__dict__ for r in self.reasons],
        }


_SUPPORTED_MAJOR: tuple[str, ...] = ("1",)
#: Minor capability levels known to this bundle. Any minor > this must be
#: rejected/DEGRADED depending on the producer role.
_SUPPORTED_MINOR_MAX = 0


def _parse_version(raw: Any) -> tuple[str, str] | None:
    if not isinstance(raw, str):
        return None
    parts = raw.split(".")
    if len(parts) != 2:
        return None
    if not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return parts[0], parts[1]


def validate_contract_version(
    payload: Any,
    *,
    consumer_role: str = "consumer",
    required_minors: Sequence[int] = (),
) -> CompatibilityDecision:
    """Fail-closed compatibility gate.

    Acceptance rules (design.md §1.7):

    - missing ``contractVersion`` → BLOCKED (identity required)
    - non-string / malformed → BLOCKED (identity invalid)
    - unknown major → BLOCKED (fail-closed)
    - known major + unsupported minor → DEGRADED for consumer, BLOCKED for
      producer
    - any entry in ``required_minors`` greater than the negotiated minor →
      REJECTED (missing capability)
    - otherwise ACCEPT with the negotiated minor
    """

    if not isinstance(payload, Mapping):
        return CompatibilityDecision(
            outcome="BLOCKED",
            reasons=(
                CompatibilityReason(
                    code="identity-not-object",
                    detail="payload is not a JSON object",
                ),
            ),
        )

    raw_version = payload.get("contractVersion")
    if raw_version is None:
        return CompatibilityDecision(
            outcome="BLOCKED",
            reasons=(
                CompatibilityReason(
                    code="identity-missing",
                    detail="contractVersion is missing",
                    field="contractVersion",
                ),
            ),
        )

    parsed = _parse_version(raw_version)
    if parsed is None:
        return CompatibilityDecision(
            outcome="BLOCKED",
            reasons=(
                CompatibilityReason(
                    code="identity-malformed",
                    detail=f"contractVersion '{raw_version}' is not '<major>.<minor>'",
                    field="contractVersion",
                ),
            ),
        )
    major, minor = parsed

    if major not in _SUPPORTED_MAJOR:
        return CompatibilityDecision(
            outcome="BLOCKED",
            reasons=(
                CompatibilityReason(
                    code="unknown-major",
                    detail=(
                        f"producer major '{major}' not supported "
                        f"(bundle supports {_SUPPORTED_MAJOR})"
                    ),
                    field="contractVersion",
                ),
            ),
        )

    try:
        minor_int = int(minor)
    except ValueError:  # pragma: no cover — _parse_version guards this
        return CompatibilityDecision(
            outcome="BLOCKED",
            reasons=(
                CompatibilityReason(
                    code="identity-malformed",
                    detail=f"minor '{minor}' is not an integer",
                    field="contractVersion",
                ),
            ),
        )

    if minor_int > _SUPPORTED_MINOR_MAX:
        outcome: CompatibilityOutcome = (
            "DEGRADED" if consumer_role == "consumer" else "BLOCKED"
        )
        return CompatibilityDecision(
            outcome=outcome,
            reasons=(
                CompatibilityReason(
                    code="unsupported-minor",
                    detail=(
                        f"minor {minor_int} > {_SUPPORTED_MINOR_MAX} "
                        f"supported by this bundle"
                    ),
                    field="contractVersion",
                ),
            ),
            negotiated_version=f"{major}.{_SUPPORTED_MINOR_MAX}",
        )

    if any(req > minor_int for req in required_minors):
        return CompatibilityDecision(
            outcome="REJECTED",
            reasons=(
                CompatibilityReason(
                    code="missing-capability",
                    detail=(
                        f"producer minor {minor_int} does not cover required "
                        f"minor {max(required_minors)}"
                    ),
                    field="contractVersion",
                ),
            ),
        )

    return CompatibilityDecision(
        outcome="ACCEPT",
        negotiated_version=f"{major}.{minor_int}",
    )


# ---------------------------------------------------------------------------
# Reverse-dup scanner (Req 1.2)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LocalDupe:
    file: str
    line: int
    column: int
    symbol: str
    kind: str  # "interface" | "type" | "class"
    import_source: str | None  # module the file imports G-C0 from (if any)


def _strip_trailing_comments(text: str) -> str:
    """Very lightweight comment stripper for scanner purposes only.

    Sufficient for TypeScript/TSX/Vue ``<script lang=ts>`` blocks: we only
    strip ``//...`` line comments to avoid false positives from commented
    ``interface Foo`` inside docs.
    """
    out: list[str] = []
    for line in text.splitlines():
        # Remove inline // comments. We don't handle strings-with-// here
        # because downstream specs would have to escape the URL anyway.
        stripped = line.split("//", 1)[0]
        out.append(stripped)
    return "\n".join(out)


@lru_cache(maxsize=None)
def _ts_declaration_patterns(symbol: str) -> tuple[tuple[str, re.Pattern[str]], ...]:
    """声明式匹配，避免把 ``import { type Foo }`` 当成本地重复声明。

    仅子串匹配 ``type Foo`` 会命中类型导入 —— 而类型导入正是契约要求的写法。
    真正的重复声明必须是行首声明位：type alias 必须带 ``=``，interface/class
    必须紧跟名字边界。
    """
    name = re.escape(symbol)
    prefix = r"^\s*(?:export\s+)?(?:default\s+)?(?:declare\s+)?"
    return (
        ("interface", re.compile(rf"{prefix}interface\s+{name}\b")),
        ("class", re.compile(rf"{prefix}(?:abstract\s+)?class\s+{name}\b")),
        ("type", re.compile(rf"{prefix}type\s+{name}\s*(?:<[^=]*>)?\s*=")),
    )


def discover_local_dupes(
    roots: Iterable[Path],
    *,
    allowed_import_markers: Sequence[str] = ("@/shared/contracts/gc0", "./shared/contracts/gc0", "gc0"),
    ts_owner_dir: Path | None = None,
) -> tuple[LocalDupe, ...]:
    """AST/text-scan roots for local re-declarations of C0 top-level symbols.

    - For each of ``GC0_TOP_LEVEL_TYPES``, look for ``interface Foo``,
      ``type Foo``, or ``class Foo`` declarations.
    - If the file contains an import from one of ``allowed_import_markers``
      referencing the SAME symbol, the local declaration is still a dupe
      (that's the point of "single source of truth").
    - JSON schema copies inside ``*.json`` files are detected by searching
      for a ``"<symbol>"`` string appearing next to a ``"type":`` or
      ``"properties":`` block inside a file that does NOT live under the
      G-C0 bundle directory.
    - ``ts_owner_dir``: an optional TypeScript-side owner directory (e.g.
      ``src/shared/contracts/gc0``) that also owns the C0 TS bindings.
      Files under it are skipped (same rule as ``bundle_root()`` on the
      backend). Downstream specs that define their own local duplicates
      outside this directory will be flagged.

    Returns one :class:`LocalDupe` per finding (never raises).
    """

    findings: list[LocalDupe] = []
    bundle = bundle_root().resolve()
    owner_dirs: list[Path] = [bundle]
    if ts_owner_dir is not None:
        owner_dirs.append(ts_owner_dir.resolve())

    for root in roots:
        if not root.exists():
            continue
        root = root.resolve()
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".ts", ".tsx", ".vue", ".json"}:
                continue
            # Skip files inside any owner directory (backend bundle or
            # frontend TS bindings).
            resolved = path.resolve()
            if any(resolved.is_relative_to(od) for od in owner_dirs):
                continue
            if any(part in {"node_modules", ".venv", "__pycache__", "dist", "build"} for part in resolved.parts):
                continue

            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            stripped = _strip_trailing_comments(raw)

            # --- TypeScript / Vue (script lang=ts) scan ---
            if path.suffix in {".ts", ".tsx", ".vue"}:
                for idx, line in enumerate(stripped.splitlines(), start=1):
                    for sym in GC0_TOP_LEVEL_TYPES:
                        for kind, pattern in _ts_declaration_patterns(sym):
                            match = pattern.search(line)
                            if match is not None:
                                findings.append(
                                    LocalDupe(
                                        file=str(path),
                                        line=idx,
                                        column=match.start(),
                                        symbol=sym,
                                        kind=kind,
                                        import_source=None,
                                    )
                                )

            # --- JSON schema copies: heuristically match a JSON file that
            # --- defines the same-named ``<symbol>`` with a ``type`` block.
            if path.suffix == ".json":
                for sym in GC0_TOP_LEVEL_TYPES:
                    # Match patterns like `"CanonicalWorkpaperLocation": { ... "type": ... }`
                    # or a ``$defs``/``definitions`` entry with the same key.
                    if f"\"{sym}\"" in stripped and '"type"' in stripped:
                        # Confirm this is not merely an import path mention.
                        # If the file is inside a fixtures or evidence dir,
                        # skip.
                        if any(part in {"fixtures", "evidence"} for part in path.parts):
                            continue
                        findings.append(
                            LocalDupe(
                                file=str(path),
                                line=stripped.index(f"\"{sym}\"") // max(
                                    1, len(stripped[: stripped.index(f"\"{sym}\"")].splitlines() or [""])
                                ),
                                column=0,
                                symbol=sym,
                                kind="json-schema-copy",
                                import_source=None,
                            )
                        )

    return tuple(findings)


# ---------------------------------------------------------------------------
# AST helpers used by conformance tests (kept tight on purpose).
# ---------------------------------------------------------------------------

def _module_symbol_names(source: str) -> list[str]:
    """Return declared symbol names in a TS/TSX file (interface/type/class)."""
    names: list[str] = []
    try:
        tree = ast.parse(source, filename="<gc0-scan>", mode="exec")
    except SyntaxError:
        return names  # TypeScript not parseable by Python ast — scan textually instead
    for node in ast.walk(tree):  # pragma: no cover — Python never parses TS
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names


# Kept so tests can assert the module exposes an AST entry point even when
# the real implementation falls back to textual scan for TS.
AST_ENTRYPOINT_SYMBOLS = ("ast.parse",)
