"""Generate the workpaper writer / resolver / version-domain migration inventory.

Every row in the generated inventory comes from a real Python AST walk over
``backend/app`` plus a test-reference scan over ``backend/tests``. Nothing here is a
hand-written list: the discovery predicate is structural (which content/version
attributes a function assigns, which commit receivers it invokes, which canonical
resolver symbols it reaches, which artifact it writes), so deleting a call or
renaming a receiver changes the generated facts.

Only one field is a human judgement and therefore lives in the reviewed overlay
``backend/data/workpaper_writer_domain_overlay.json``: the ``domain`` a writer belongs
to. Every other column -- read/written version fields, commit points, orchestrator
usage, side effects, canonical resolver, characterization tests -- is derived. A
discovered writer with no reviewed domain is reported as ``unadjudicated`` and keeps
the unified revision gate red; the generator never invents an adjudication.

Usage from repository root::

    python backend/scripts/gen/generate_workpaper_writer_inventory.py --check
    python backend/scripts/gen/generate_workpaper_writer_inventory.py --apply
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from collections.abc import Mapping
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_APP_ROOT = _REPO / "backend" / "app"
_TEST_ROOT = _REPO / "backend" / "tests"
_OVERLAY = _REPO / "backend" / "data" / "workpaper_writer_domain_overlay.json"
_INVENTORY = _REPO / "backend" / "data" / "workpaper_writer_inventory.json"

# ─── Version domain vocabulary ──────────────────────────────────────────────
# `content_revision` is the Wave 1 target column. It is listed here on purpose: while it
# does not exist yet the generator reports zero writers for it, and the moment Task 9
# introduces it the inventory starts tracking it without a generator change.
_VERSION_ATTRS: frozenset[str] = frozenset({"file_version", "content_revision"})
_CONTENT_ATTRS: frozenset[str] = frozenset({"parsed_data", "file_path"})
#: Requirement 2.1 lists these as explicitly *not* business content and *not* a version.
#: They are recorded as side effects so the huge `mark_stale` fan-in does not masquerade
#: as a content writer.
_NON_CONTENT_ATTRS: frozenset[str] = frozenset({"prefill_stale", "updated_at", "updated_by"})
_PARSED_DATA_VERSION_KEYS: frozenset[str] = frozenset(
    {"_version", "schema_version", "content_revision", "file_version", "_migrated_at"}
)
#: Persisted workpaper business-content stores and the columns that carry that content.
#: `checklist_responses` is here because the F2-22/F2-23 Word sync endpoints and the
#: version-trail rollback keep workpaper business content there, completely outside the
#: `working_paper` version domain -- exactly the Requirement 9.11 second-authority split
#: this inventory has to surface.
_CONTENT_STORES: dict[str, frozenset[str]] = {
    "working_paper": frozenset(
        {"parsed_data", "file_version", "file_path", "content_revision"}
    ),
    "checklist_responses": frozenset({"remark", "conclusion"}),
}
#: `working_paper` columns whose mutation means "business content or its version moved".
_TRACKED_SQL_COLUMNS: frozenset[str] = _CONTENT_STORES["working_paper"]

#: The single unified commit boundary this spec migrates every writer onto (Task 15).
#: Absent from the tree during Wave 0, which is exactly why the gate is red.
_UNIFIED_COMMIT_MARKERS: tuple[str, ...] = (
    "ContentMutationService",
    "content_mutation_service",
)

#: Canonical / competing resolver symbols for the workpaper physical file.
_RESOLVER_SYMBOLS: frozenset[str] = frozenset(
    {
        "resolve_wp_file",
        "find_template_file_any",
        "find_template_file",
        "_resolve_wp_file",
        "_resolve_custom_wp_file",
        "_resolve_docx_template",
        "_resolve_template_path",
        "_onlyoffice_storage_dir",
        "_onlyoffice_dir",
    }
)
#: The one resolver Requirement 9.11 designates as the canonical entry point.
_CANONICAL_RESOLVER = "resolve_wp_file"

#: Directory names that root a workpaper artifact path. A `<expr> / "<root>"` construction
#: is the second-authority shape Requirement 9.11 wants surfaced.
_WORKPAPER_PATH_ROOTS: frozenset[str] = frozenset(
    {"storage", "workpapers", "excel_html", "wp_storage", "wp_templates"}
)

_ARTIFACT_WRITE_ATTRS: frozenset[str] = frozenset(
    {"write_bytes", "write_text", "copy2", "copyfile", "copyfileobj", "replace"}
)
#: Directory segments that make an artifact write a **snapshot of already-committed
#: bytes** instead of a write to the workpaper's authoritative artifact.
#:
#: Task 20 needs this distinction because `WpStorageService.save_version` copies the
#: *current* file into `.versions/` and changes zero content: it has no business content
#: to put through the unified commit, so `bypasses_unified_commit` can never legitimately
#: reach zero on that row. The category is derived from the destination expression, not
#: adjudicated -- an artifact write whose destination cannot be traced to one of these
#: namespaces stays `unclassified` and keeps the bypass verdict.
_SNAPSHOT_DIR_LITERALS: frozenset[str] = frozenset({".versions", ".upgrade-candidates"})
_SIDE_EFFECT_ATTRS: frozenset[str] = frozenset({"publish", "broadcast_raw"})

#: Calls that stage / register a *non-current* representation upgrade candidate
#: (Task 17). Property 4 forbids that lane from moving the business content revision, so
#: the lane needs a source-backed denominator of its own: it is invisible in `entries`
#: (the upgrader writes no content attribute, no tracked SQL column and resolves no
#: workpaper path), and a criterion evaluated over an empty denominator is a tautology.
_UPGRADE_CANDIDATE_CALLS: frozenset[str] = frozenset(
    {"stage_upgrade_candidate", "create_upgrade_candidate"}
)
#: The one method allowed to advance the unified business counter (Task 9/15).
_REVISION_BUMP_CALLS: frozenset[str] = frozenset({"bump_content_revision"})

#: Lane vocabulary. It is a **floor, not a ceiling** (the gate's `_REQUIRED_DOMAINS` is a proper
#: subset: a lane dropping to zero rows means the discovery predicate went blind on a whole lane).
#:
#: 🔴 A lane label never changes a verdict. Every blocking verdict
#: (`bypasses_unified_commit`, `owns_direct_commit`, ...) is derived from source, so adding a lane
#: cannot excuse a row -- the only criteria an adjudication can clear are `unadjudicated_writer`
#: and `unadjudicated_resolver`, and that equivalence is asserted behaviourally by
#: `test_task74_domain_adjudication.py::test_adjudicating_clears_exactly_two_criteria`.
_DOMAINS: frozenset[str] = frozenset(
    {
        "html_save",
        "dedicated_router",
        "upload_import",
        "wopi",
        "oo_callback",
        "custom",
        "f2_word_sync",
        "rollback",
        "history_restore",
        "export_storage_resolver",
        "orchestrator_side_effect",
        "template_provisioning",
        "checklist_response_store",
        # Task 74 additions. Both name a lane that already existed in the measured rows and had
        # no honest label, so the alternative was mislabelling the row and telling the truth only
        # in prose:
        #   * `unified_commit_substrate` -- the unified protocol's own write primitive
        #     (`WorkpaperSyncRepository.bump_content_revision`), i.e. the function
        #     `ContentMutationService.commit()` calls to advance the one sanctioned counter. Task
        #     20's evidence README section 4.2 registered its `bypasses_unified_commit` verdict as
        #     a predicate layering defect; the label records the lane and leaves the verdict alone.
        #   * `read_only_evaluation` -- a row the AST discovers because it assigns a content
        #     attribute on an in-memory object (a QC dry-run sample / context) with no session, no
        #     SQL and no artifact write. "No measured persistence" is not a proof of no
        #     persistence, so these rows keep every derived verdict they had.
        "unified_commit_substrate",
        "read_only_evaluation",
    }
)

_SQL_ASSIGN_RE = re.compile(r"([a-z_][a-z0-9_]*)\s*=", re.I)


def _sql_update_re(table: str) -> re.Pattern[str]:
    return re.compile(rf"update\s+{table}\s+set\s+(.+?)(?:\s+where\b|$)", re.I | re.S)


def _sql_insert_re(table: str) -> re.Pattern[str]:
    return re.compile(rf"insert\s+into\s+{table}\s*\(([^)]*)\)", re.I | re.S)


def _sql_delete_re(table: str) -> re.Pattern[str]:
    return re.compile(rf"delete\s+from\s+{table}\b", re.I)


class WriterInventoryError(RuntimeError):
    """Raised when source facts or the reviewed overlay are incomplete."""


# ─── small helpers ──────────────────────────────────────────────────────────


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WriterInventoryError(f"required file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WriterInventoryError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WriterInventoryError(f"JSON root must be an object: {path}")
    return value


def dotted_name(node: ast.AST) -> str:
    """Render an attribute/name/call chain as dotted text, or '' when not expressible.

    Used for receiver identity only (``db``, ``self.db``, ``sa.update``). Never used as a
    membership test against raw file text, so renaming a symbol changes the output.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return dotted_name(node.func)
    if isinstance(node, ast.Subscript):
        return dotted_name(node.value)
    return ""


def _constant_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _subscript_root(node: ast.AST) -> str:
    """Return the identifier a subscript chain is rooted at (``parsed_data['a']['b']``)."""
    current = node
    while isinstance(current, ast.Subscript):
        current = current.value
    return dotted_name(current)


# ─── per-function fact extraction ───────────────────────────────────────────


class _FunctionFacts:
    """Structural facts collected for one function body (excluding nested functions)."""

    def __init__(self) -> None:
        self.version_fields_written: set[str] = set()
        self.version_fields_read: set[str] = set()
        self.content_fields_written: set[str] = set()
        self.sql_update_columns: set[str] = set()
        self.commit_receivers: set[str] = set()
        self.flush_receivers: set[str] = set()
        self.after_save_calls: set[str] = set()
        self.unified_commit_calls: set[str] = set()
        self.resolver_calls: set[str] = set()
        self.ad_hoc_paths: list[dict[str, Any]] = []
        self.artifact_writes: set[str] = set()
        self.artifact_write_targets: list[dict[str, Any]] = []
        self.representation_candidate_calls: set[str] = set()
        self.revision_bump_calls: set[str] = set()
        self.side_effects: set[str] = set()
        self.swallowed_exception_lines: list[int] = []
        self.called_symbols: set[str] = set()
        self.called_dotted: set[str] = set()
        #: Local names bound to a snapshot destination path. Populated before the main
        #: walk so an artifact write can be classified against it; never serialised.
        self.snapshot_path_names: set[str] = set()

    def as_dict(self) -> dict[str, Any]:
        return {
            "version_fields_written": sorted(self.version_fields_written),
            "version_fields_read": sorted(self.version_fields_read),
            "content_fields_written": sorted(self.content_fields_written),
            "sql_update_columns": sorted(self.sql_update_columns),
            "commit_receivers": sorted(self.commit_receivers),
            "flush_receivers": sorted(self.flush_receivers),
            "after_save_calls": sorted(self.after_save_calls),
            "unified_commit_calls": sorted(self.unified_commit_calls),
            "resolver_calls": sorted(self.resolver_calls),
            "ad_hoc_paths": sorted(
                self.ad_hoc_paths, key=lambda item: (item["line"], item["literal"])
            ),
            "artifact_writes": sorted(self.artifact_writes),
            # Every artifact-write call site, with its destination classified. A call
            # whose destination cannot be traced is recorded as `unclassified` on
            # purpose: "snapshot-only" must be falsifiable by a single untraceable write.
            "artifact_write_targets": sorted(
                self.artifact_write_targets,
                key=lambda item: (item["line"], item["attr"], item["target"]),
            ),
            "representation_candidate_calls": sorted(self.representation_candidate_calls),
            "revision_bump_calls": sorted(self.revision_bump_calls),
            "side_effects": sorted(self.side_effects),
            "swallowed_exception_lines": sorted(self.swallowed_exception_lines),
        }


def _iter_own_nodes(function: ast.AST):
    """Yield nodes belonging to this function, not to nested function definitions.

    Nested functions are separate inventory rows, so their commits and writes must not be
    attributed to the enclosing function (``wopi_service.put_file._auto_parse`` commits on
    its own session).
    """
    stack: list[ast.AST] = list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _record_target(facts: _FunctionFacts, target: ast.AST) -> None:
    if isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            _record_target(facts, element)
        return
    if isinstance(target, ast.Attribute):
        if target.attr in _VERSION_ATTRS:
            facts.version_fields_written.add(target.attr)
        elif target.attr in _CONTENT_ATTRS:
            facts.content_fields_written.add(target.attr)
        elif target.attr in _NON_CONTENT_ATTRS:
            facts.side_effects.add(f"<sets {target.attr}>")
        return
    if isinstance(target, ast.Subscript):
        root = _subscript_root(target)
        leaf = root.rsplit(".", 1)[-1]
        key = _constant_key(target.slice)
        if leaf in _CONTENT_ATTRS or leaf == "parsed_data":
            if key is not None and key in _PARSED_DATA_VERSION_KEYS:
                facts.version_fields_written.add(f"parsed_data.{key}")
            elif key is not None:
                facts.content_fields_written.add(f"parsed_data[{key!r}]")
            else:
                facts.content_fields_written.add("parsed_data[<dynamic>]")


def _record_sql_text(facts: _FunctionFacts, call: ast.Call) -> None:
    """Capture raw ``text('UPDATE/INSERT/DELETE <content store> ...')`` mutations.

    ``wp_migration_service`` writes ``parsed_data`` and the F2/version-trail paths write
    ``checklist_responses`` through raw SQL, so an AST-only attribute scan would miss them.
    The SQL string is still reached through the AST (the literal argument of a ``text()``
    call), not through a whole-file text search.
    """
    if dotted_name(call.func).rsplit(".", 1)[-1] != "text":
        return
    for argument in call.args:
        literal = _constant_key(argument)
        if literal is None:
            continue
        for table, columns in _CONTENT_STORES.items():
            for body in _sql_update_re(table).findall(literal):
                for column in _SQL_ASSIGN_RE.findall(body):
                    lowered = column.lower()
                    if lowered in columns:
                        facts.sql_update_columns.add(f"{table}.{lowered}")
                    elif lowered in _NON_CONTENT_ATTRS:
                        facts.side_effects.add(f"<sets {table}.{lowered}>")
            for body in _sql_insert_re(table).findall(literal):
                for column in re.split(r"[,\s]+", body):
                    if column.strip().lower() in columns:
                        facts.sql_update_columns.add(f"{table}.{column.strip().lower()}")
            if _sql_delete_re(table).search(literal):
                facts.sql_update_columns.add(f"{table}.<delete>")


def _record_sql_update_values(facts: _FunctionFacts, call: ast.Call) -> None:
    """Capture ``sa.update(WorkingPaper)...values(parsed_data=..., ...)`` mutations."""
    if dotted_name(call.func).rsplit(".", 1)[-1] != "values":
        return
    chain: ast.AST = call.func
    mentions_working_paper = False
    while isinstance(chain, (ast.Attribute, ast.Call)):
        if isinstance(chain, ast.Call):
            for argument in chain.args:
                if dotted_name(argument).rsplit(".", 1)[-1] == "WorkingPaper":
                    mentions_working_paper = True
            chain = chain.func
        else:
            chain = chain.value
    if not mentions_working_paper:
        return
    for keyword in call.keywords:
        if not keyword.arg:
            continue
        lowered = keyword.arg.lower()
        if lowered in _TRACKED_SQL_COLUMNS:
            facts.sql_update_columns.add(f"working_paper.{lowered}")
        elif lowered in _NON_CONTENT_ATTRS:
            facts.side_effects.add(f"<sets working_paper.{lowered}>")


def _artifact_destination(call: ast.Call, attr: str) -> ast.AST | None:
    """Return the AST node the artifact write lands on, or None when it is not a path.

    Per-attribute, because the destination is not in the same syntactic position:
    ``shutil.copy2(src, dst)`` carries it in the second argument, ``path.write_bytes(b)``
    in the receiver, ``tmp.replace(target)`` in the first argument. ``copyfileobj`` takes
    open file objects and therefore has no resolvable destination path at all -- returning
    None keeps it `unclassified` instead of guessing.
    """
    if attr in {"copy2", "copyfile"}:
        return call.args[1] if len(call.args) > 1 else None
    if attr in {"write_bytes", "write_text"}:
        return call.func.value if isinstance(call.func, ast.Attribute) else None
    if attr == "replace":
        return call.args[0] if call.args else None
    return None


def _mentions_snapshot(node: ast.AST, snapshot_names: set[str]) -> bool:
    """True when this expression is built from a snapshot namespace or a bound snapshot."""
    for inner in ast.walk(node):
        if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
            if inner.value in _SNAPSHOT_DIR_LITERALS:
                return True
        elif isinstance(inner, (ast.Name, ast.Attribute)):
            if dotted_name(inner) in snapshot_names:
                return True
    return False


def _snapshot_bound_names(function: ast.AST) -> set[str]:
    """Names bound to a snapshot destination, resolved to a fixed point.

    ``version_dir = file_path.parent / '.versions' / stem`` then
    ``version_path = version_dir / version_name``: the second binding is only a snapshot
    once the first is known, so a single pass in source order is not enough (and
    ``_iter_own_nodes`` does not walk in source order).
    """
    assignments: list[tuple[str, ast.AST]] = []
    for node in _iter_own_nodes(function):
        if isinstance(node, ast.Assign) and node.value is not None:
            for target in node.targets:
                name = dotted_name(target)
                if name:
                    assignments.append((name, node.value))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            name = dotted_name(node.target)
            if name:
                assignments.append((name, node.value))
    bound: set[str] = set()
    for _ in range(len(assignments) + 1):
        grew = False
        for name, value in assignments:
            if name in bound:
                continue
            if _mentions_snapshot(value, bound):
                bound.add(name)
                grew = True
        if not grew:
            break
    return bound


def _record_call(facts: _FunctionFacts, call: ast.Call) -> None:
    dotted = dotted_name(call.func)
    leaf = dotted.rsplit(".", 1)[-1]
    receiver = dotted.rsplit(".", 1)[0] if "." in dotted else ""
    if leaf:
        facts.called_symbols.add(leaf)
    if dotted:
        facts.called_dotted.add(dotted)

    if any(marker in dotted for marker in _UNIFIED_COMMIT_MARKERS):
        facts.unified_commit_calls.add(dotted)
    if leaf == "commit":
        facts.commit_receivers.add(receiver or "<bare>")
    elif leaf == "flush":
        facts.flush_receivers.add(receiver or "<bare>")
    elif leaf == "after_save":
        facts.after_save_calls.add(dotted)
    elif leaf in _ARTIFACT_WRITE_ATTRS:
        facts.artifact_writes.add(leaf)
        destination = _artifact_destination(call, leaf)
        target = (
            "snapshot"
            if destination is not None
            and _mentions_snapshot(destination, facts.snapshot_path_names)
            else "unclassified"
        )
        facts.artifact_write_targets.append(
            {"line": call.lineno, "attr": leaf, "target": target}
        )
    elif leaf in _SIDE_EFFECT_ATTRS:
        facts.side_effects.add(dotted)

    if leaf in _RESOLVER_SYMBOLS:
        facts.resolver_calls.add(leaf)
    if leaf in _UPGRADE_CANDIDATE_CALLS:
        facts.representation_candidate_calls.add(leaf)
    if leaf in _REVISION_BUMP_CALLS:
        facts.revision_bump_calls.add(dotted)

    _record_sql_text(facts, call)
    _record_sql_update_values(facts, call)


def _record_ad_hoc_path(
    facts: _FunctionFacts,
    node: ast.BinOp,
    *,
    path_root_names: Mapping[str, str] | None = None,
) -> None:
    """Record ``Path('storage') / ...`` style workpaper path construction.

    A second authority path (``storage/projects/{pid}/excel_html/{stem}.xlsx``) is exactly
    the Requirement 9.11 divergence this inventory has to surface, and it never calls a
    resolver symbol.
    """
    if not isinstance(node.op, ast.Div):
        return
    literals: list[str] = []
    for side in (node.left, node.right):
        key = _constant_key(side)
        if key is not None:
            literals.append(key)
            continue
        if isinstance(side, ast.Call):
            for argument in side.args:
                inner = _constant_key(argument)
                if inner is not None:
                    literals.append(inner)
            continue
        # `TEMPLATES_DIR / relative`: the literal lives in the module-level
        # binding, not lexically inside this function body.
        if path_root_names:
            referenced = dotted_name(side).rsplit(".", 1)[-1]
            bound = path_root_names.get(referenced)
            if bound is not None:
                literals.append(bound)
    for literal in literals:
        lowered = literal.lower()
        if lowered in _WORKPAPER_PATH_ROOTS:
            facts.ad_hoc_paths.append({"line": node.lineno, "literal": literal})
            return


def _module_path_root_names(tree: ast.AST) -> dict[str, str]:
    """Map module-level path-root constants to the root they resolve to.

    Only module scope, and only the <expr> / literal shape -- the same shape
    _record_ad_hoc_path recognises inline. Two passes let one intermediate constant
    chain through, so a second hop does not reintroduce the blind spot.

    Why this exists: the predicate used to fire only on a literal lexically inside
    the function body, so the d1262c80 file split -- which moved two wp_template_finder
    resolvers next to a hoisted TEMPLATES_DIR constant -- silently dropped both from
    the denominator. Their overlay rows then read as no-longer-in-source, surfacing as
    a stale-overlay hard failure that was really a detector blind spot. Pure code
    movement must not change the denominator.
    """
    bound: dict[str, str] = {}
    for _ in range(2):
        for node in getattr(tree, 'body', []):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if not names or node.value is None:
                continue
            value = node.value
            if not isinstance(value, ast.BinOp) or not isinstance(value.op, ast.Div):
                continue
            for side in (value.left, value.right):
                literal = _constant_key(side)
                if literal is None and isinstance(side, ast.Call):
                    for argument in side.args:
                        literal = literal or _constant_key(argument)
                if literal is None:
                    literal = bound.get(dotted_name(side).rsplit('.', 1)[-1])
                if literal is None:
                    continue
                if literal.lower() in _WORKPAPER_PATH_ROOTS:
                    for name in names:
                        bound[name] = literal
    return bound

def _collect_facts(
    function: ast.AST, *, path_root_names: Mapping[str, str] | None = None
) -> _FunctionFacts:
    facts = _FunctionFacts()
    # Destination bindings first: `_record_call` classifies each artifact write against
    # them, and the walk below does not visit statements in source order.
    facts.snapshot_path_names = _snapshot_bound_names(function)
    for node in _iter_own_nodes(function):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                _record_target(facts, target)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            _record_target(facts, node.target)
        elif isinstance(node, ast.Attribute):
            if isinstance(node.ctx, ast.Load) and node.attr in _VERSION_ATTRS:
                facts.version_fields_read.add(node.attr)
        elif isinstance(node, ast.Subscript):
            if isinstance(node.ctx, ast.Load):
                leaf = _subscript_root(node).rsplit(".", 1)[-1]
                key = _constant_key(node.slice)
                if leaf == "parsed_data" and key in _PARSED_DATA_VERSION_KEYS:
                    facts.version_fields_read.add(f"parsed_data.{key}")
        elif isinstance(node, ast.Call):
            _record_call(facts, node)
            if dotted_name(node.func).rsplit(".", 1)[-1] == "get":
                key = _constant_key(node.args[0]) if node.args else None
                root = dotted_name(node.func).rsplit(".", 1)[0]
                if key in _PARSED_DATA_VERSION_KEYS and root.rsplit(".", 1)[-1] in {
                    "parsed_data",
                    "prop_map",
                }:
                    facts.version_fields_read.add(f"parsed_data.{key}")
        elif isinstance(node, ast.BinOp):
            _record_ad_hoc_path(facts, node, path_root_names=path_root_names)
        elif isinstance(node, ast.ExceptHandler):
            has_raise = any(isinstance(inner, ast.Raise) for inner in ast.walk(node))
            if not has_raise:
                facts.swallowed_exception_lines.append(node.lineno)
    return facts


def _iter_functions(tree: ast.AST):
    """Yield ``(qualname, node)`` for every function, including nested and methods."""
    stack: list[tuple[str, ast.AST]] = [("", tree)]
    while stack:
        prefix, parent = stack.pop()
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}{child.name}"
                yield qualname, child
                stack.append((f"{qualname}.", child))
            elif isinstance(child, ast.ClassDef):
                stack.append((f"{prefix}{child.name}.", child))
            else:
                stack.append((prefix, child))


# ─── characterization test discovery ────────────────────────────────────────


def _module_path(path: Path) -> str:
    relative = path.relative_to(_REPO / "backend").with_suffix("")
    return ".".join(relative.parts)


def _resolved_calls_in_test(tree: ast.AST) -> set[str]:
    """Return ``module::qualname`` for every call this test file actually *invokes*.

    🔴 Task 20 tightened this predicate. Until Task 19 it credited a writer whenever a
    test file mentioned its module **and** any part of its qualified name anywhere -- as
    an attribute, a bare name, a docstring-adjacent identifier or a monkeypatch target
    string. Two measured false credits came out of that:

    * a Task 19 guard that only *mentions* ``wp_storage_service`` credited the untouched
      sibling ``WpStorageService.list_versions`` as tested;
    * ``WpMigrationService.rollback`` was credited to a property test that simulates the
      rollback with ``copy.deepcopy`` and never calls the method.

    Both are the same fail-open shape: the judgement never reached a call site. So the
    evidence is now an *invocation* resolved through a binding:

    * ``from <module> import <symbol>`` then ``symbol(...)``          -> ``module::symbol``
    * ``import <module>`` / ``from <pkg> import <mod>`` then ``mod.f(...)``
    * ``Cls.method(...)``, ``Cls(...).method(...)`` and ``name.method(...)`` where
      ``name`` (or ``self.name``) was bound from ``Cls(...)``          -> ``module::Cls.method``

    Deliberately conservative in three ways, all of which under-credit rather than
    over-credit (a gate must fail closed):

    * a writer exercised only through an HTTP route (``client.post("/api/...")``) is not
      credited: there is no call site naming it;
    * a call reached through a fixture, ``getattr``, a helper defined in another test
      module or a relative import is not credited;
    * patching a target (``monkeypatch.setattr("app.x.y", ...)``) is not an invocation.
    """
    # name -> "module.symbol" for `from module import symbol [as name]`
    symbol_bindings: dict[str, tuple[str, str]] = {}
    # name -> module for `import module [as name]`
    module_bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_bindings[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
                module_bindings[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                bound = alias.asname or alias.name
                symbol_bindings[bound] = (node.module, alias.name)
                # `from app.services import wp_storage_service` binds a *module*.
                module_bindings[bound] = f"{node.module}.{alias.name}"

    # name -> (module, Cls) for `x = Cls(...)` / `self.x = Cls(...)`
    instance_bindings: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            targets = [node.optional_vars]
        if not targets:
            continue
        value = node.value if not isinstance(node, ast.withitem) else node.context_expr
        if not isinstance(value, ast.Call):
            continue
        constructor = value.func
        if not isinstance(constructor, ast.Name):
            continue
        origin = symbol_bindings.get(constructor.id)
        if origin is None:
            continue
        for target in targets:
            name = dotted_name(target)
            if name:
                instance_bindings[name] = origin

    def _receiver_origin(node: ast.AST) -> tuple[str, str] | None:
        """Resolve a call receiver to ``(module, Cls)`` when it is a bound class."""
        if isinstance(node, ast.Call):
            return _receiver_origin(node.func)
        if isinstance(node, ast.Await):
            return _receiver_origin(node.value)
        name = dotted_name(node)
        if not name:
            return None
        if name in instance_bindings:
            return instance_bindings[name]
        return symbol_bindings.get(name)

    invoked: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            origin = symbol_bindings.get(func.id)
            if origin is not None:
                invoked.add(f"{origin[0]}::{origin[1]}")
            continue
        if not isinstance(func, ast.Attribute):
            continue
        method = func.attr
        receiver = func.value
        receiver_name = dotted_name(receiver)
        module = module_bindings.get(receiver_name)
        if module is not None:
            invoked.add(f"{module}::{method}")
        origin = _receiver_origin(receiver)
        if origin is not None:
            invoked.add(f"{origin[0]}::{origin[1]}.{method}")
    return invoked


def discover_characterization_tests() -> dict[str, list[str]]:
    """Map ``module::qualname`` to the test files that **call** that function."""
    by_key: dict[str, set[str]] = defaultdict(set)
    if not _TEST_ROOT.is_dir():
        raise WriterInventoryError(f"test root does not exist: {_TEST_ROOT}")
    for path in sorted(_TEST_ROOT.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        relative = str(path.relative_to(_REPO)).replace("\\", "/")
        for key in _resolved_calls_in_test(tree):
            by_key[key].add(relative)
    return {key: sorted(value) for key, value in by_key.items()}


def _tests_for(
    test_index: dict[str, list[str]], module: str, qualname: str
) -> list[str]:
    """Tests that invoke this exact writer.

    Nested functions (``outer.inner``) are only credited when the test reaches the inner
    callable itself, which a test practically never can -- another intentional
    under-credit rather than inheriting the enclosing function's evidence.
    """
    return sorted(test_index.get(f"{module}::{qualname}", []))


# ─── inventory assembly ─────────────────────────────────────────────────────


def _is_production_source(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return not ({"tests", "test", "__pycache__", "migrations"} & parts)


def _module_import_targets(tree: ast.AST) -> dict[str, str]:
    """Map locally bound names to their ``module.symbol`` origin for ImportFrom nodes."""
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return bindings


def _writes_content_directly(facts: _FunctionFacts) -> bool:
    return bool(
        facts.version_fields_written
        or facts.content_fields_written
        or facts.sql_update_columns
        or facts.after_save_calls
    )


def _propagate_content_writers(
    functions: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Find callers that are one resolvable hop away from a direct content writer.

    Task 3 needs the *entry points* that write workpaper content -- the F2 sync endpoints
    delegating to ``_save_fields``, the rollback router delegating to
    ``VersionTrailService.rollback_to_snapshot``. It does not need the full transitive
    closure: following the call graph to a fixed point pulls in every orchestration layer
    that eventually touches a workpaper and drowns the inventory (measured: 349 rows
    instead of the single-hop denominator).

    Resolution is deliberately conservative -- a call edge is only followed when the
    callee is defined in the same module, is an explicitly imported symbol, or is a method
    reached through an explicitly imported class. Bare leaf-name matching across the whole
    tree would manufacture edges (five modules define ``_save_html_data``), which is the
    false-positive class this inventory must not have.
    """
    by_module: dict[str, dict[str, str]] = defaultdict(dict)
    by_qualified: dict[str, str] = {}
    for item in functions:
        leaf = item["qualname"].rsplit(".", 1)[-1]
        by_module[item["module"]][leaf] = item["writer_id"]
        by_qualified[f"{item['module']}.{item['qualname']}"] = item["writer_id"]
        by_qualified[f"{item['module']}.{leaf}"] = item["writer_id"]

    direct = {
        item["writer_id"]
        for item in functions
        if _writes_content_directly(item["facts_obj"])
    }

    delegated: dict[str, list[str]] = {}
    for item in functions:
        if item["writer_id"] in direct:
            continue
        facts = item["facts_obj"]
        imports = item["import_bindings"]
        own = by_module[item["module"]]
        targets: set[str] = set()
        for symbol in facts.called_symbols:
            candidate = own.get(symbol)
            if candidate and candidate != item["writer_id"]:
                targets.add(candidate)
            origin = imports.get(symbol)
            if origin and origin in by_qualified:
                targets.add(by_qualified[origin])
        for dotted in facts.called_dotted:
            if "." not in dotted:
                continue
            receiver_root, leaf = dotted.split(".")[0], dotted.rsplit(".", 1)[-1]
            origin = imports.get(receiver_root)
            if origin and f"{origin}.{leaf}" in by_qualified:
                targets.add(by_qualified[f"{origin}.{leaf}"])
        hits = sorted(targets & direct)
        if hits:
            delegated[item["writer_id"]] = hits
    return delegated


def collect_source_rows() -> list[dict[str, Any]]:
    """Walk ``backend/app`` and return every structurally discovered writer/resolver.

    Thin wrapper over :func:`collect_source_facts` for callers that only need the
    classified rows. Prefer :func:`collect_source_facts` when the reviewed overlay carries
    ``retired_adjudications``: verifying a retirement needs the facts of a function that
    is deliberately *absent* from these rows, and re-scanning the tree to get them costs a
    second full AST walk.
    """
    return collect_source_facts()[0]


def collect_source_facts() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Walk ``backend/app`` once and return ``(classified rows, facts of every function)``.

    The second element is the denominator retirement verification needs: a writer that has
    been migrated out of the writer set no longer appears in ``rows``, and "absent from
    rows" is satisfied equally by "migrated" and by "deleted". Keeping every function's
    structural facts lets :func:`build_inventory` tell those two apart.
    """
    if not _APP_ROOT.is_dir():
        raise WriterInventoryError(f"application root does not exist: {_APP_ROOT}")
    test_index = discover_characterization_tests()
    functions: list[dict[str, Any]] = []
    scanned_files = 0
    for path in sorted(_APP_ROOT.rglob("*.py")):
        if not _is_production_source(path):
            continue
        # utf-8-sig: at least one production module is BOM-prefixed on disk, and a BOM is
        # an unparseable non-printable character for `ast.parse`.
        source = path.read_text(encoding="utf-8-sig")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            raise WriterInventoryError(f"cannot parse production source {path}: {exc}") from exc
        scanned_files += 1
        module = _module_path(path)
        relative = str(path.relative_to(_REPO)).replace("\\", "/")
        import_bindings = _module_import_targets(tree)
        path_root_names = _module_path_root_names(tree)
        for qualname, function in _iter_functions(tree):
            functions.append(
                {
                    "writer_id": f"{module}::{qualname}",
                    "module": module,
                    "source_path": relative,
                    "qualname": qualname,
                    "line": function.lineno,
                    "is_async": isinstance(function, ast.AsyncFunctionDef),
                    "facts_obj": _collect_facts(
                        function, path_root_names=path_root_names
                    ),
                    "import_bindings": import_bindings,
                }
            )
    if scanned_files == 0:
        raise WriterInventoryError("scanned zero production source files")

    function_facts = {
        item["writer_id"]: item["facts_obj"].as_dict() for item in functions
    }
    delegated = _propagate_content_writers(functions)
    rows: list[dict[str, Any]] = []
    for item in functions:
        facts = item["facts_obj"]
        chain = delegated.get(item["writer_id"], [])
        classification = _classify(facts, delegates_to=chain)
        if classification is None:
            continue
        rows.append(
            {
                "writer_id": item["writer_id"],
                "module": item["module"],
                "source_path": item["source_path"],
                "qualname": item["qualname"],
                "line": item["line"],
                "is_async": item["is_async"],
                "kind": classification,
                "delegates_to_content_writer": chain,
                "facts": facts.as_dict(),
                "characterization_tests": _tests_for(
                    test_index, item["module"], item["qualname"]
                ),
            }
        )
    if not rows:
        raise WriterInventoryError("writer discovery produced an empty denominator")
    return rows, function_facts


def _classify(facts: _FunctionFacts, *, delegates_to: list[str]) -> str | None:
    """Return the row kind, or None when the function is neither writer nor resolver.

    Writer: mutates workpaper business content/version state (attribute, ``parsed_data``
    key, or a tracked content-store SQL column), delegates to the save orchestrator,
    delegates to another discovered content writer, or writes a workpaper artifact while
    resolving a workpaper path.
    Resolver: reaches a workpaper file resolver symbol or builds a workpaper path itself.
    """
    resolves = bool(facts.resolver_calls) or bool(facts.ad_hoc_paths)
    writes_artifact = bool(facts.artifact_writes) and resolves
    is_writer = _writes_content_directly(facts) or writes_artifact or bool(delegates_to)
    if is_writer and resolves:
        return "writer_resolver"
    if is_writer:
        return "writer"
    if resolves:
        return "resolver"
    return None


def _resolver_identities(facts: dict[str, Any]) -> list[str]:
    identities = list(facts["resolver_calls"])
    if facts["ad_hoc_paths"]:
        identities.append("<ad_hoc_path_construction>")
    return sorted(set(identities))


def _build_retired_writers(
    retired: dict[str, Any],
    *,
    discovered_ids: set[str],
    function_facts: dict[str, dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Verify every retirement against source and return the audit ledger rows.

    A migrated writer leaves the writer set, so "it is not in ``entries`` any more" is the
    *expected* end state -- and that is exactly why it cannot be the judgement. Three
    independent outcomes have to stay distinguishable:

    * the function came back to writing content/version state (source regressed) -> error;
    * the function is gone entirely (deleted, not migrated) -> error, because a deletion
      would otherwise inherit the migration's green verdict;
    * the function is still there and the facts the retirement claims to have emptied are
      really empty -> recorded here with its measured facts.

    The third case is what makes gates able to assert the retirement positively instead of
    inferring it from an absent row (an unreachable-branch false green).
    """
    if not retired:
        return []
    if function_facts is None:
        raise WriterInventoryError(
            "overlay carries retired_adjudications but no per-function facts were supplied: "
            "call collect_source_facts() and pass function_facts, otherwise a retirement "
            "would be accepted without ever looking at the source"
        )

    ledger: list[dict[str, Any]] = []
    for writer_id, value in sorted(retired.items()):
        if not isinstance(value, dict):
            raise WriterInventoryError(f"retired adjudication must be an object: {writer_id}")
        domain = value.get("domain")
        if domain not in _DOMAINS:
            raise WriterInventoryError(
                f"retired adjudication {writer_id} has unknown domain {domain!r}; "
                f"allowed: {sorted(_DOMAINS)}"
            )
        for required in ("retired_by_task", "retired_reason", "version_domain_note"):
            if not value.get(required):
                raise WriterInventoryError(
                    f"retired adjudication {writer_id} has no {required}"
                )
        expected_empty = value.get("expected_empty_facts")
        if not isinstance(expected_empty, list) or not expected_empty:
            raise WriterInventoryError(
                f"retired adjudication {writer_id} must list a non-empty "
                "expected_empty_facts: a retirement with nothing to assert is not falsifiable"
            )

        if writer_id in discovered_ids:
            raise WriterInventoryError(
                f"retired adjudication {writer_id} is discovered as a writer/resolver again "
                "-- the source regressed to writing content/version state, or the "
                "retirement was premature; move it back into `adjudications`"
            )
        facts = function_facts.get(writer_id)
        if facts is None:
            if value.get("must_still_exist"):
                raise WriterInventoryError(
                    f"retired adjudication {writer_id} claims must_still_exist=true but no "
                    "such function exists in backend/app -- it was deleted or renamed, "
                    "which is not the same thing as being migrated out of the writer set"
                )
            ledger.append(
                {
                    "writer_id": writer_id,
                    **value,
                    "source_state": "absent",
                    "facts": None,
                    "verified_empty_facts": [],
                }
            )
            continue

        unknown = sorted(set(expected_empty) - set(facts))
        if unknown:
            raise WriterInventoryError(
                f"retired adjudication {writer_id} lists unknown fact keys {unknown}; "
                f"available: {sorted(facts)}"
            )
        still_populated = {key: facts[key] for key in sorted(expected_empty) if facts[key]}
        if still_populated:
            raise WriterInventoryError(
                f"retired adjudication {writer_id} claims these facts are empty but source "
                f"says otherwise: {still_populated}"
            )
        ledger.append(
            {
                "writer_id": writer_id,
                **value,
                "source_state": "present_and_clean",
                "facts": facts,
                "verified_empty_facts": sorted(expected_empty),
            }
        )
    return ledger


def _build_representation_upgrade_lane(
    function_facts: dict[str, dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Source-backed denominator for Property 4's representation-upgrade obligation.

    The upgrader (`ExcelInstrumentationUpgrader.stage_and_register_candidate`) is **not**
    an `entries` row: it writes no content attribute, no tracked SQL column and resolves
    no workpaper path, so a criterion evaluated over `entries` would be a tautology --
    zero rows, zero violations, forever green. This section lists every function that
    stages or registers a non-current upgrade candidate, together with the version-domain
    facts Property 4 forbids it from having, so the gate can judge a real denominator and
    fail closed when the denominator disappears.
    """
    if not function_facts:
        return []
    lane: list[dict[str, Any]] = []
    for function_id, facts in sorted(function_facts.items()):
        if not facts.get("representation_candidate_calls"):
            continue
        lane.append(
            {
                "function_id": function_id,
                "candidate_calls": facts["representation_candidate_calls"],
                "version_fields_written": facts["version_fields_written"],
                "revision_bump_calls": facts["revision_bump_calls"],
                "sql_update_columns": facts["sql_update_columns"],
                "commit_receivers": facts["commit_receivers"],
            }
        )
    return lane


def build_inventory(
    rows: list[dict[str, Any]],
    overlay: dict[str, Any],
    function_facts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if overlay.get("schema_version") != 1 or overlay.get("review_status") != "reviewed":
        raise WriterInventoryError(
            "overlay must use schema_version=1 and review_status='reviewed'"
        )
    adjudications = overlay.get("adjudications")
    if not isinstance(adjudications, dict):
        raise WriterInventoryError("overlay.adjudications must be an object")
    for writer_id, value in adjudications.items():
        if not isinstance(value, dict):
            raise WriterInventoryError(f"adjudication must be an object: {writer_id}")
        domain = value.get("domain")
        if domain not in _DOMAINS:
            raise WriterInventoryError(
                f"adjudication {writer_id} has unknown domain {domain!r}; "
                f"allowed: {sorted(_DOMAINS)}"
            )
        if not value.get("version_domain_note"):
            raise WriterInventoryError(f"adjudication {writer_id} has no version_domain_note")

    retired = overlay.get("retired_adjudications") or {}
    if not isinstance(retired, dict):
        raise WriterInventoryError("overlay.retired_adjudications must be an object")
    both = sorted(set(adjudications) & set(retired))
    if both:
        raise WriterInventoryError(
            f"writers are both active and retired adjudications: {both} -- a writer is "
            "either still carrying debt or has been migrated out, never both"
        )

    discovered_ids = {row["writer_id"] for row in rows}
    stale = sorted(set(adjudications) - discovered_ids)
    if stale:
        raise WriterInventoryError(
            f"overlay adjudicates writers that no longer exist in source: {stale}"
        )
    retired_writers = _build_retired_writers(
        retired, discovered_ids=discovered_ids, function_facts=function_facts
    )

    entries: list[dict[str, Any]] = []
    for row in rows:
        facts = row["facts"]
        adjudication = adjudications.get(row["writer_id"])
        resolvers = _resolver_identities(facts)
        is_writer = row["kind"] in {"writer", "writer_resolver"}
        stores = sorted(
            {column.split(".", 1)[0] for column in facts["sql_update_columns"]}
            | (
                {"working_paper"}
                if facts["version_fields_written"] or facts["content_fields_written"]
                else set()
            )
        )
        # Business content this row persists, from source only. It has exactly two
        # consumers: the `artifact_snapshot_only` category below, and that category's
        # own obligations in the gate (`artifact_snapshot_writer_not_verifiable`).
        #
        # 🔴 It deliberately does **not** participate in `bypasses_unified_commit`, and
        # that is not an oversight. "No business content facts" is a *measurement*
        # outcome, not a semantic claim: the 14 writer rows that reach it do so only
        # because their artifact destinations could not be traced -- every one of them
        # has `artifact_write_targets` entirely `unclassified` (e.g.
        # `wp_template_init_service::init_workpaper_from_template`, which provisions the
        # authoritative workpaper file, and `excel_html::save_edits`). When the
        # destination is untraceable there is no evidence the row holds no authoritative
        # content, so excusing it from the unified commit would be a fail-open exemption
        # -- exactly the shape `artifact_snapshot_only` avoids by deriving the category
        # from the destination expression instead of from the absence of facts. Locked by
        # `test_task20_writer_gate.py::test_the_bypass_verdict_does_not_consult_writes_business_content`
        # and mutation M21.
        writes_business_content = bool(
            stores
            or facts["version_fields_written"]
            or facts["content_fields_written"]
            or facts["sql_update_columns"]
            or facts["after_save_calls"]
            or row["delegates_to_content_writer"]
        )
        artifact_targets = facts["artifact_write_targets"]
        # Positive category, not an exemption: **every** artifact write in the function
        # must land in a snapshot namespace (one untraceable destination is enough to
        # lose the category) and the function must persist no business content at all.
        # The moment such a writer starts writing content or a version field, it becomes
        # a plain writer again and the bypass verdict comes back -- see the gate's
        # `artifact_snapshot_writer_not_verifiable` criterion for its own obligations.
        artifact_snapshot_only = bool(
            is_writer
            and artifact_targets
            and all(item["target"] == "snapshot" for item in artifact_targets)
            and not writes_business_content
        )
        writes_legacy_version_field = bool(
            {"file_version", "parsed_data._version"} & set(facts["version_fields_written"])
        )
        writes_unified_content_revision = (
            "content_revision" in facts["version_fields_written"]
            or "working_paper.content_revision" in facts["sql_update_columns"]
        )
        entry = {
            **row,
            "adjudication": (
                {"status": "adjudicated", **adjudication}
                if adjudication
                else {"status": "unadjudicated", "domain": None}
            ),
            "canonical_resolver": _CANONICAL_RESOLVER if _CANONICAL_RESOLVER in resolvers else None,
            "resolver_identities": resolvers,
            "content_stores_written": stores,
            "verdicts": {
                # `writes_business_content` is intentionally absent from this formula:
                # an untraceable artifact destination cannot prove the row holds no
                # authoritative content, so "no measured content facts" must not buy a
                # way out of the unified commit. Only the destination-derived
                # `artifact_snapshot_only` category does, and it carries obligations.
                "bypasses_unified_commit": bool(
                    is_writer
                    and not facts["unified_commit_calls"]
                    and not artifact_snapshot_only
                ),
                "artifact_snapshot_only": artifact_snapshot_only,
                "writes_business_content": bool(is_writer and writes_business_content),
                # Property 4 / Property 61 regression shape: a writer that reaches the
                # unified boundary **and** keeps a private write path next to it. Any of
                # the three is one revision domain too many -- its own legacy counter,
                # its own `content_revision` bump, or its own transaction boundary.
                "keeps_legacy_write_path_beside_unified_commit": bool(
                    facts["unified_commit_calls"]
                    and (
                        writes_legacy_version_field
                        or writes_unified_content_revision
                        or facts["commit_receivers"]
                    )
                ),
                "owns_direct_commit": bool(facts["commit_receivers"]),
                "uses_save_orchestrator": bool(facts["after_save_calls"]),
                "writes_legacy_version_field": writes_legacy_version_field,
                "writes_unified_content_revision": writes_unified_content_revision,
                "delegates_content_write": bool(row["delegates_to_content_writer"]),
                "multi_resolver": len(resolvers) > 1,
                "non_canonical_resolver_only": bool(resolvers)
                and _CANONICAL_RESOLVER not in resolvers,
                "has_characterization_test": bool(row["characterization_tests"]),
                "swallows_exceptions": bool(facts["swallowed_exception_lines"]),
            },
        }
        entries.append(entry)

    entries.sort(key=lambda item: item["writer_id"])
    representation_upgrade_lane = _build_representation_upgrade_lane(function_facts)
    stats = _build_stats(entries, retired_writers)
    inventory: dict[str, Any] = {
        "schema_version": 1,
        "canonical_resolver": _CANONICAL_RESOLVER,
        "unified_commit_markers": list(_UNIFIED_COMMIT_MARKERS),
        "domains": sorted(_DOMAINS),
        "content_stores": {
            table: sorted(columns) for table, columns in sorted(_CONTENT_STORES.items())
        },
        # Retired rows participate in the source digest on purpose: they are absent from
        # `entries`, so without them a change to a retired function's body would leave the
        # digest untouched and the freshness check would call a moved source "current".
        "source_digest": _sha256(
            _stable_json(
                [
                    [
                        row["writer_id"],
                        row["kind"],
                        row["delegates_to_content_writer"],
                        row["facts"],
                    ]
                    for row in rows
                ]
                + [
                    ["<retired>", item["writer_id"], item["source_state"], item["facts"]]
                    for item in retired_writers
                ]
                # Same reason as the retired ledger: the upgrade lane lives outside
                # `entries`, so without it a version bump appearing inside the upgrader
                # would leave the source digest untouched.
                + [["<upgrade_lane>", item] for item in representation_upgrade_lane]
            ).encode("utf-8")
        ),
        "overlay_digest": _sha256(_stable_json(overlay).encode("utf-8")),
        "stats": stats,
        "entries": entries,
        "retired_writers": retired_writers,
        "representation_upgrade_lane": representation_upgrade_lane,
    }
    inventory["inventory_digest"] = _sha256(_stable_json(inventory).encode("utf-8"))
    return inventory


def _build_stats(
    entries: list[dict[str, Any]], retired_writers: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    writers = [entry for entry in entries if entry["kind"] in {"writer", "writer_resolver"}]
    resolvers = [entry for entry in entries if entry["kind"] in {"resolver", "writer_resolver"}]
    unadjudicated = [
        entry for entry in entries if entry["adjudication"]["status"] == "unadjudicated"
    ]
    retired_writers = retired_writers or []
    return {
        "retired_writer_count": len(retired_writers),
        "retired_by_domain": dict(
            sorted(Counter(item["domain"] for item in retired_writers).items())
        ),
        "row_count": len(entries),
        "writer_count": len(writers),
        "resolver_count": len(resolvers),
        "unadjudicated_count": len(unadjudicated),
        "unadjudicated_writer_count": sum(
            1 for entry in unadjudicated if entry["kind"] in {"writer", "writer_resolver"}
        ),
        "bypasses_unified_commit_count": sum(
            1 for entry in writers if entry["verdicts"]["bypasses_unified_commit"]
        ),
        "artifact_snapshot_only_count": sum(
            1 for entry in writers if entry["verdicts"]["artifact_snapshot_only"]
        ),
        "keeps_legacy_write_path_beside_unified_commit_count": sum(
            1
            for entry in writers
            if entry["verdicts"]["keeps_legacy_write_path_beside_unified_commit"]
        ),
        "writes_unified_content_revision_count": sum(
            1 for entry in writers if entry["verdicts"]["writes_unified_content_revision"]
        ),
        "legacy_version_field_writer_count": sum(
            1 for entry in writers if entry["verdicts"]["writes_legacy_version_field"]
        ),
        "direct_commit_writer_count": sum(
            1 for entry in writers if entry["verdicts"]["owns_direct_commit"]
        ),
        "save_orchestrator_writer_count": sum(
            1 for entry in writers if entry["verdicts"]["uses_save_orchestrator"]
        ),
        "multi_resolver_count": sum(1 for entry in entries if entry["verdicts"]["multi_resolver"]),
        "non_canonical_resolver_only_count": sum(
            1 for entry in resolvers if entry["verdicts"]["non_canonical_resolver_only"]
        ),
        "writer_without_characterization_test_count": sum(
            1 for entry in writers if not entry["verdicts"]["has_characterization_test"]
        ),
        "swallowing_writer_count": sum(
            1 for entry in writers if entry["verdicts"]["swallows_exceptions"]
        ),
        "by_content_store": dict(
            sorted(
                Counter(
                    store or "<artifact_or_delegated_only>"
                    for entry in writers
                    for store in (entry["content_stores_written"] or [""])
                ).items()
            )
        ),
        "by_domain": dict(
            sorted(
                Counter(
                    entry["adjudication"]["domain"] or "unadjudicated" for entry in entries
                ).items()
            )
        ),
        "by_kind": dict(sorted(Counter(entry["kind"] for entry in entries).items())),
        "version_field_write_histogram": dict(
            sorted(
                Counter(
                    field
                    for entry in entries
                    for field in entry["facts"]["version_fields_written"]
                ).items()
            )
        ),
    }


def recompute_inventory_digest(inventory: dict[str, Any]) -> str:
    """Recompute ``inventory_digest`` over the *stored* content of an inventory.

    Comparing only the stored digest fields against the regenerated ones is fail-open: a
    row can be deleted from ``entries`` while the digests still look correct. Consumers
    must verify self-consistency with this helper as well as freshness.
    """
    body = {key: value for key, value in inventory.items() if key != "inventory_digest"}
    return _sha256(_stable_json(body).encode("utf-8"))


def render_inventory(inventory: dict[str, Any]) -> str:
    return json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _print_stats(label: str, inventory: dict[str, Any]) -> None:
    stats = inventory["stats"]
    print(
        f"[{label}] rows={stats['row_count']} writers={stats['writer_count']} "
        f"resolvers={stats['resolver_count']} unadjudicated={stats['unadjudicated_count']} "
        f"(writers={stats['unadjudicated_writer_count']}) "
        f"bypass_unified_commit={stats['bypasses_unified_commit_count']} "
        f"unified_content_revision={stats['writes_unified_content_revision_count']}"
    )
    print(
        f"[{label}] legacy_version_writers={stats['legacy_version_field_writer_count']} "
        f"direct_commit={stats['direct_commit_writer_count']} "
        f"orchestrator={stats['save_orchestrator_writer_count']} "
        f"multi_resolver={stats['multi_resolver_count']} "
        f"non_canonical_resolver_only={stats['non_canonical_resolver_only_count']} "
        f"writer_without_test={stats['writer_without_characterization_test_count']}"
    )
    print(
        f"[{label}] artifact_snapshot_only={stats['artifact_snapshot_only_count']} "
        "legacy_path_beside_unified_commit="
        f"{stats['keeps_legacy_write_path_beside_unified_commit_count']} "
        f"representation_upgrade_lane={len(inventory['representation_upgrade_lane'])}"
    )
    print(f"[{label}] by_domain={stats['by_domain']}")
    print(
        f"[{label}] retired_writers={stats['retired_writer_count']} "
        f"retired_by_domain={stats['retired_by_domain']}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify the generated inventory")
    mode.add_argument("--apply", action="store_true", help="atomically regenerate the inventory")
    args = parser.parse_args(argv)

    rows, function_facts = collect_source_facts()
    overlay = _read_json(_OVERLAY)
    inventory = build_inventory(rows, overlay, function_facts)
    content = render_inventory(inventory)
    _print_stats("SOURCE", inventory)

    if args.check:
        if not _INVENTORY.is_file():
            print(f"[FAIL] missing generated inventory: {_INVENTORY.relative_to(_REPO)}")
            return 2
        if _INVENTORY.read_text(encoding="utf-8") != content:
            print(
                "[FAIL] stale generated inventory: "
                f"{_INVENTORY.relative_to(_REPO)} no longer matches source facts"
            )
            return 2
        print(f"[OK] inventory digest {inventory['inventory_digest']}")
        return 0

    _atomic_write(_INVENTORY, content)
    print(
        f"[APPLIED] {_INVENTORY.relative_to(_REPO)} "
        f"sha256={_sha256(content.encode('utf-8'))[:16]}"
    )
    print(f"[OK] inventory digest {inventory['inventory_digest']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WriterInventoryError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
