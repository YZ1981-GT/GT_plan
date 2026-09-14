#!/usr/bin/env python
"""Domain boundary checker (stdlib only; no import-linter / grimp / dependency-cruiser).

Flow:
  1. path -> domain (glob ownership from docs/architecture/domain-boundaries.json)
  2. extract imports (Python stdlib AST; frontend regex / existing-style scan)
  3. resolve internal targets under backend/app and audit-platform/frontend/src
  4. cross-domain edges vs may_depend_on
  5. unowned production modules are violations
  6. exact identity diff vs baselines/domain-boundary-debt.json

Usage::

    python backend/scripts/check/check_domain_boundaries.py
    python backend/scripts/check/check_domain_boundaries.py --write-baseline
    python backend/scripts/check/check_domain_boundaries.py --root /tmp/synth --manifest ... --baseline ...

Debt shrink prints a hint to refresh the baseline; new identities fail closed.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = REPO_ROOT / "docs/architecture/domain-boundaries.json"
DEFAULT_BASELINE = REPO_ROOT / "backend/scripts/check/baselines/domain-boundary-debt.json"

BACKEND_APP_REL = "backend/app"
FRONTEND_SRC_REL = "audit-platform/frontend/src"

KIND_UNOWNED = "unowned"
KIND_FORBIDDEN = "forbidden_edge"
KIND_CYCLE = "cycle"

EXCLUDE_DIR_NAMES = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "migrations",
    "__tests__",
    "stories",
    "test",
}
EXCLUDE_FILE_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".spec.ts",
    ".spec.js",
    ".spec.tsx",
    ".test.ts",
    ".test.js",
    ".test.tsx",
    ".stories.ts",
    ".stories.vue",
)
PRODUCTION_SUFFIXES = {".py", ".ts", ".tsx", ".vue", ".js", ".jsx", ".mjs"}

# Frontend import forms (aligned with check_frontend_dangling_reference_gate style).
_FE_IMPORT_RE = re.compile(
    r"""(?:^|[;\n])\s*(?:import|export)\s+(?:type\s+)?(?:[\w*{}\s,]+?\s+from\s+)?['"]([^'"]+)['"]""",
    re.M,
)
_FE_SIDE_EFFECT_RE = re.compile(
    r"""(?:^|[;\n])\s*import\s+['"]([^'"]+)['"]""",
    re.M,
)
_FE_DYNAMIC_RE = re.compile(
    r"""(?:import|require)\s*\(\s*['"]([^'"]+)['"]\s*\)""",
)
_VUE_SCRIPT_RE = re.compile(
    r"<script\b[^>]*>(.*?)</script>",
    re.I | re.S,
)


@dataclass(frozen=True, order=True)
class Violation:
    identity: str
    kind: str
    detail: str

    def as_baseline_entry(self) -> dict[str, str]:
        return {"identity": self.identity, "kind": self.kind, "detail": self.detail}


@dataclass(frozen=True)
class DomainSpec:
    name: str
    owners: tuple[str, ...]
    paths: tuple[str, ...]
    may_depend_on: frozenset[str]


def normalize_repo_path(path: str | Path, root: str | Path | None = None) -> str:
    raw = str(path).replace("\\", "/")
    if root is None:
        return raw.lstrip("./")
    root_raw = str(root).replace("\\", "/").rstrip("/")
    if raw.casefold().startswith((root_raw + "/").casefold()):
        return raw[len(root_raw) + 1 :]
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except (OSError, ValueError):
        return raw.lstrip("./")


def _pattern_specificity(pattern: str) -> tuple[int, int, int]:
    """Higher score wins. Prefer more literals, fewer wildcards, longer patterns."""
    literals = sum(1 for ch in pattern if ch not in "*?[]")
    wildcards = sum(1 for ch in pattern if ch in "*?")
    return (literals, -wildcards, len(pattern))


def load_manifest(path: Path) -> dict[str, DomainSpec]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported schema_version: {data.get('schema_version')!r}")
    domains_raw = data.get("domains")
    if not isinstance(domains_raw, dict) or not domains_raw:
        raise ValueError("domains must be a non-empty object")
    domains: dict[str, DomainSpec] = {}
    for name, body in domains_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"domain {name!r} must be an object")
        owners = body.get("owners") or []
        paths = body.get("paths") or []
        may = body.get("may_depend_on") or []
        if not owners:
            raise ValueError(f"domain {name!r} missing owners")
        if not paths:
            raise ValueError(f"domain {name!r} missing paths")
        domains[name] = DomainSpec(
            name=name,
            owners=tuple(str(o) for o in owners),
            paths=tuple(str(p).replace("\\", "/") for p in paths),
            may_depend_on=frozenset(str(x) for x in may),
        )
    # Validate may_depend_on references.
    unknown: list[str] = []
    for spec in domains.values():
        for dep in spec.may_depend_on:
            if dep not in domains:
                unknown.append(f"{spec.name}->{dep}")
    if unknown:
        raise ValueError("unknown may_depend_on targets: " + ", ".join(sorted(unknown)))
    return domains


def resolve_domain(rel_path: str, domains: dict[str, DomainSpec]) -> str | None:
    rel = rel_path.replace("\\", "/")
    best: tuple[tuple[int, int, int], str] | None = None
    for name, spec in domains.items():
        for pattern in spec.paths:
            if fnmatch.fnmatch(rel, pattern):
                score = _pattern_specificity(pattern)
                if best is None or score > best[0]:
                    best = (score, name)
    return None if best is None else best[1]


def _is_excluded(rel_path: str) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    if any(part in EXCLUDE_DIR_NAMES for part in parts):
        return True
    name = parts[-1] if parts else ""
    lower = name.lower()
    return any(lower.endswith(suf) for suf in EXCLUDE_FILE_SUFFIXES)


def iter_production_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for scan_rel in (BACKEND_APP_REL, FRONTEND_SRC_REL):
        base = root / scan_rel
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in PRODUCTION_SUFFIXES:
                continue
            rel = normalize_repo_path(path, root)
            if _is_excluded(rel):
                continue
            files.append(path)
    return sorted(files)


def extract_python_imports(source: str) -> set[str]:
    """Return dotted module paths referenced by import / from-import (incl. nested)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
                # from app.services.foo import bar  - also record submodule if relative depth 0
            # relative imports: from .foo import bar
            if node.level and node.module:
                mods.add(("." * node.level) + node.module)
            elif node.level and not node.module:
                mods.add("." * node.level)
    return mods


def _strip_vue_scripts(source: str) -> str:
    blocks = _VUE_SCRIPT_RE.findall(source)
    return "\n".join(blocks) if blocks else source


def extract_frontend_imports(source: str, *, is_vue: bool) -> set[str]:
    text = _strip_vue_scripts(source) if is_vue else source
    # Drop block comments lightly to reduce false positives.
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(^|[^:])//[^\n]*", r"\1", text)
    specs: set[str] = set()
    for rx in (_FE_IMPORT_RE, _FE_SIDE_EFFECT_RE, _FE_DYNAMIC_RE):
        specs.update(m.group(1) for m in rx.finditer(text))
    return specs


def resolve_python_target(module: str, root: Path) -> str | None:
    """Map app.* import to repo-relative path under backend/app, if resolvable."""
    if module.startswith("."):
        return None  # relative - resolved with importer context below
    if not module.startswith("app."):
        return None
    parts = module.split(".")
    # app.services.foo -> backend/app/services/foo.py or .../foo/__init__.py
    rel_parts = parts[1:]  # drop 'app'
    base = root / BACKEND_APP_REL
    file_candidate = base.joinpath(*rel_parts).with_suffix(".py")
    init_candidate = base.joinpath(*rel_parts) / "__init__.py"
    if file_candidate.is_file():
        return normalize_repo_path(file_candidate, root)
    if init_candidate.is_file():
        return normalize_repo_path(init_candidate, root)
    # Truncate to package that exists (import of symbol from package).
    for i in range(len(rel_parts) - 1, 0, -1):
        pkg = base.joinpath(*rel_parts[:i])
        init = pkg / "__init__.py"
        py = pkg.with_suffix(".py")
        if init.is_file():
            return normalize_repo_path(init, root)
        if py.is_file():
            return normalize_repo_path(py, root)
    return None


def resolve_python_relative(module: str, importer_rel: str, root: Path) -> str | None:
    if not module.startswith("."):
        return resolve_python_target(module, root)
    importer = root / importer_rel
    package_dir = importer.parent
    level = len(module) - len(module.lstrip("."))
    rest = module.lstrip(".")
    cur = package_dir
    for _ in range(level - 1):
        cur = cur.parent
    if rest:
        target_base = cur.joinpath(*rest.split("."))
    else:
        target_base = cur
    for cand in (
        target_base.with_suffix(".py") if rest else target_base / "__init__.py",
        target_base / "__init__.py",
        Path(str(target_base) + ".py"),
    ):
        if cand.is_file():
            return normalize_repo_path(cand, root)
    return None


def resolve_frontend_target(spec: str, importer_rel: str, root: Path) -> str | None:
    fe_root = root / FRONTEND_SRC_REL
    if spec.startswith("@/"):
        base = fe_root / spec[2:]
    elif spec.startswith("."):
        base = (root / importer_rel).parent / spec
    else:
        return None  # external package
    base = base.resolve()
    try:
        base.relative_to((root / FRONTEND_SRC_REL).resolve())
    except ValueError:
        return None
    cands = [
        base,
        Path(str(base) + ".ts"),
        Path(str(base) + ".tsx"),
        Path(str(base) + ".vue"),
        Path(str(base) + ".js"),
        base / "index.ts",
        base / "index.vue",
        base / "index.js",
    ]
    for cand in cands:
        if cand.is_file():
            return normalize_repo_path(cand, root)
    return None


def collect_edges(
    root: Path,
    domains: dict[str, DomainSpec],
    files: Sequence[Path] | None = None,
) -> tuple[list[Violation], set[tuple[str, str]], dict[str, str]]:
    """Return (violations_without_baseline, domain_edges, path_to_domain)."""
    path_to_domain: dict[str, str] = {}
    unowned: list[Violation] = []
    prod_files = list(files) if files is not None else iter_production_files(root)

    for path in prod_files:
        rel = normalize_repo_path(path, root)
        domain = resolve_domain(rel, domains)
        if domain is None:
            unowned.append(
                Violation(
                    identity=f"{KIND_UNOWNED}:{rel}",
                    kind=KIND_UNOWNED,
                    detail=f"production module not owned by any domain: {rel}",
                )
            )
        else:
            path_to_domain[rel] = domain

    forbidden: list[Violation] = []
    domain_edges: set[tuple[str, str]] = set()

    for path in prod_files:
        rel = normalize_repo_path(path, root)
        src_domain = path_to_domain.get(rel)
        if src_domain is None:
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        targets: set[str] = set()
        if path.suffix.lower() == ".py":
            for mod in extract_python_imports(source):
                resolved = resolve_python_relative(mod, rel, root)
                if resolved:
                    targets.add(resolved)
        elif path.suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".vue"}:
            for spec in extract_frontend_imports(source, is_vue=path.suffix.lower() == ".vue"):
                resolved = resolve_frontend_target(spec, rel, root)
                if resolved:
                    targets.add(resolved)

        for tgt in sorted(targets):
            # Only internal production edges under scan roots.
            if not (tgt.startswith(BACKEND_APP_REL + "/") or tgt.startswith(FRONTEND_SRC_REL + "/")):
                continue
            if _is_excluded(tgt):
                continue
            dst_domain = path_to_domain.get(tgt)
            if dst_domain is None:
                # Target may be unowned (already reported) or outside scanned set.
                continue
            if dst_domain == src_domain:
                continue
            domain_edges.add((src_domain, dst_domain))
            allowed = domains[src_domain].may_depend_on
            if dst_domain not in allowed:
                identity = f"{KIND_FORBIDDEN}:{src_domain}->{dst_domain}:{rel}->{tgt}"
                forbidden.append(
                    Violation(
                        identity=identity,
                        kind=KIND_FORBIDDEN,
                        detail=f"{src_domain} may not depend on {dst_domain} ({rel} -> {tgt})",
                    )
                )

    cycle_violations = detect_domain_cycles(domain_edges)
    return unowned + forbidden + cycle_violations, domain_edges, path_to_domain


def detect_domain_cycles(edges: Iterable[tuple[str, str]]) -> list[Violation]:
    """Report domain dependency cycles as **strongly-connected components**.

    Identity is the sorted node set of each non-trivial SCC (size > 1), NOT a
    rotated full path string. Rationale (review §4): path-string identities
    combinatorially explode — a single edge add/remove rewrites the identity of
    every giant cycle passing through it, so the baseline shows dozens of
    "new"/"resolved" cycles for one real change (the observed 83-new/85-resolved
    churn for a net −2). An SCC identity only changes when the set of mutually
    reachable domains actually changes, which is the property we care about.
    """
    graph: dict[str, set[str]] = defaultdict(set)
    nodes: set[str] = set()
    for a, b in edges:
        graph[a].add(b)
        nodes.add(a)
        nodes.add(b)

    # Tarjan SCC (iterative, stdlib only).
    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    counter = 0
    sccs: list[list[str]] = []

    def strongconnect(root: str) -> None:
        nonlocal counter
        work = [(root, iter(sorted(graph.get(root, ()))))]
        index_of[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in index_of:
                    index_of[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(sorted(graph.get(nxt, ())))))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index_of[nxt])
            if advanced:
                continue
            if low[node] == index_of[node]:
                comp: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                sccs.append(comp)
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])

    for start in sorted(nodes):
        if start not in index_of:
            strongconnect(start)

    cycles: list[Violation] = []
    for comp in sccs:
        # Non-trivial SCC = a real cycle. Include single node only if it self-loops.
        if len(comp) > 1 or (comp and comp[0] in graph.get(comp[0], set())):
            members = ",".join(sorted(comp))
            cycles.append(
                Violation(
                    identity=f"{KIND_CYCLE}:{members}",
                    kind=KIND_CYCLE,
                    detail=f"domain dependency cycle among: {members}",
                )
            )
    return sorted(cycles)


def load_baseline(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    return {str(e["identity"]) for e in entries if isinstance(e, dict) and "identity" in e}


def save_baseline(path: Path, violations: Sequence[Violation]) -> None:
    payload = {
        "metadata": {
            "description": (
                "Exact domain-boundary debt identities. "
                "Checker fails on NEW identities only; shrink -> update this file."
            ),
            "count": len(violations),
        },
        "entries": [v.as_baseline_entry() for v in sorted(violations, key=lambda x: x.identity)],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def evaluate(
    root: Path,
    domains: dict[str, DomainSpec],
    baseline_ids: set[str],
    *,
    files: Sequence[Path] | None = None,
) -> tuple[list[Violation], list[Violation], list[Violation], list[Violation]]:
    """Return (all, new, resolved, known)."""
    all_v, _edges, _map = collect_edges(root, domains, files=files)
    current_ids = {v.identity for v in all_v}
    new_v = [v for v in all_v if v.identity not in baseline_ids]
    resolved = sorted(baseline_ids - current_ids)
    resolved_v = [
        Violation(identity=i, kind="resolved_debt", detail="baseline identity no longer present")
        for i in resolved
    ]
    known = [v for v in all_v if v.identity in baseline_ids]
    return all_v, new_v, resolved_v, known


def run_check(
    *,
    root: Path,
    manifest_path: Path,
    baseline_path: Path,
    write_baseline: bool = False,
    files: Sequence[Path] | None = None,
) -> int:
    domains = load_manifest(manifest_path)
    all_v, _edges, _map = collect_edges(root, domains, files=files)

    if write_baseline:
        save_baseline(baseline_path, all_v)
        print(f"Wrote baseline ({len(all_v)} identities) -> {baseline_path}")
        return 0

    baseline_ids = load_baseline(baseline_path)
    current_ids = {v.identity for v in all_v}
    new_v = [v for v in all_v if v.identity not in baseline_ids]
    resolved_ids = sorted(baseline_ids - current_ids)
    known = [v for v in all_v if v.identity in baseline_ids]

    print(f"Domain boundary check: files scanned under {BACKEND_APP_REL} + {FRONTEND_SRC_REL}")
    print(f"  domains={len(domains)} current_violations={len(all_v)} baseline={len(baseline_ids)}")
    print(f"  known_debt={len(known)} new={len(new_v)} resolved={len(resolved_ids)}")

    if resolved_ids:
        print(
            f"HINT: domain-boundary debt shrank by {len(resolved_ids)}; "
            f"update {normalize_repo_path(baseline_path, root)} with --write-baseline"
        )
        for identity in resolved_ids[:20]:
            print(f"  - resolved: {identity}")
        if len(resolved_ids) > 20:
            print(f"  … and {len(resolved_ids) - 20} more")

    if new_v:
        print(f"FAIL: {len(new_v)} new domain-boundary violation(s):")
        for v in sorted(new_v)[:50]:
            print(f"  [{v.kind}] {v.detail}")
        if len(new_v) > 50:
            print(f"  … and {len(new_v) - 50} more")
        return 1

    print("OK: no new domain-boundary violations")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check domain boundary policy + exact debt baseline")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository root")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Rewrite exact debt baseline from current violations (exit 0)",
    )
    args = parser.parse_args(argv)
    return run_check(
        root=args.root.resolve(),
        manifest_path=args.manifest.resolve(),
        baseline_path=args.baseline.resolve(),
        write_baseline=args.write_baseline,
    )


if __name__ == "__main__":
    raise SystemExit(main())
