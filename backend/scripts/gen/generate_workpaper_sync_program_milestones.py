"""Generate the cross-spec HTML/OnlyOffice sync program milestone registry.

The output is a deterministic projection.  It reads reviewed milestone definitions, the
line-start primary tasks and dependency graph of the eight participating specs, the
source-backed entry manifest, the writer revision gate, production symbols, a transaction-level
read-only database schema probe and digest-bound evidence.  It never upgrades a milestone from
prose, a single checked task, or manifest ``capability`` alone.

Usage from the repository root::

    python backend/scripts/gen/generate_workpaper_sync_program_milestones.py --check
    python backend/scripts/gen/generate_workpaper_sync_program_milestones.py --apply
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

_REPO = Path(__file__).resolve().parents[3]
_DEFINITIONS_PATH = _REPO / "backend" / "data" / "workpaper_sync_program_milestone_definitions.json"
_TARGET_PATH = _REPO / "backend" / "data" / "workpaper_sync_program_milestones.json"
_SPECS_ROOT = _REPO / ".kiro" / "specs"
_MANIFEST_PATH = _REPO / "backend" / "data" / "workpaper_sync_entry_manifest.json"
_MANIFEST_GENERATOR_PATH = _REPO / "backend" / "scripts" / "gen" / "generate_workpaper_sync_manifest.py"
_WRITER_GATE_PATH = _REPO / "backend" / "scripts" / "check" / "check_workpaper_writer_revision_gate.py"
_WRITER_INVENTORY_PATH = _REPO / "backend" / "data" / "workpaper_writer_inventory.json"
_MASTER_CONTROL_PATH = (
    _REPO / "docs" / "operations" / "workpaper-html-onlyoffice-bidirectional-writeback-master-control.md"
)
_WP_SYNC_ROUTER_PATH = _REPO / "backend" / "app" / "routers" / "wp_sync_router.py"
_CALLBACK_ROUTE_PATH = (
    _REPO / "backend" / "app" / "services" / "workpaper_sync" / "callback_route.py"
)
_SYNC_DOMAIN_MODELS_PATH = (
    _REPO / "backend" / "app" / "services" / "workpaper_sync" / "models.py"
)
_SYNC_RETENTION_PATH = (
    _REPO / "backend" / "app" / "services" / "workpaper_sync" / "retention.py"
)

_DEFINITION_SCHEMA = "workpaper-sync-program-milestone-definitions/v1"
_OUTPUT_SCHEMA = "workpaper-sync-program-milestones/v1"
_HOST_PATH_MILESTONE_ID = "HOST-CONSUMES-UNIFIED-PATH"
_HOST_PATH_STATE_POLICY = "host-consumes-unified-path/v1"
_HOST_PATH_INDEX_SCHEMA = "host-unified-path-evidence-index/v1"
_HOST_PATH_FACTS = (
    "user_sync_prefix_request",
    "no_legacy_bypass",
    "callback_url_bound",
    "application_applied",
    "operation_terminal_bound",
    "onlyoffice_content_version",
    "no_secondary_revision_domain",
    "server_computed_capability",
)
_HOST_PATH_CHANNEL_SCHEMAS = {
    "network": "host-unified-path-network-evidence/v1",
    "editor_config": "host-unified-path-editor-config-evidence/v1",
    "database": "host-unified-path-database-evidence/v1",
}
_HOST_PATH_ENTRY_STATES = (
    "BLOCKED",
    "REQUEST_PATH_LEGACY",
    "REQUEST_PATH_VERIFIED",
    "ONLYOFFICE_VERIFIED",
    "STALE",
)
_STATE_ORDER = {
    "BLOCKED": 0,
    "IMPLEMENTED": 1,
    "REQUEST_PATH_VERIFIED": 2,
    "ONLYOFFICE_VERIFIED": 3,
    "CLOSED": 4,
}
_ALLOWED_STATES = set(_STATE_ORDER) | {"STALE"}
_ALLOWED_RESULTS = {"pass", "fail", "blocked", "stale", "unverifiable"}
_ALLOWED_PREDICATE_TYPES = {
    "manifest_integrity",
    "writer_gate_issue_zero",
    "python_symbols",
    "database_readonly_schema",
    "evidence_bundle",
    "runtime_evidence_required",
    "declared_blocker",
    "host_path_entry_fact",
}
_DATABASE_PROBE_SCHEMA = "workpaper-sync-program-database-probe/v1"
_DATABASE_PROBE_STATUSES = {"ok", "database_unavailable", "query_failed"}
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_DATABASE_CONTROL_SQL = {
    "set_read_only": "SET TRANSACTION READ ONLY",
    "verify_read_only": "SHOW transaction_read_only",
}
_DATABASE_FACT_SQL = {
    "relations": (
        "SELECT c.relname AS table_name "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
        "AND c.relname LIKE 'working_paper%' ORDER BY c.relname"
    ),
    "columns": (
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name LIKE 'working_paper%' "
        "ORDER BY table_name, ordinal_position"
    ),
    "constraints": (
        "SELECT c.relname AS table_name, con.conname AS constraint_name "
        "FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname LIKE 'working_paper%' "
        "ORDER BY c.relname, con.conname"
    ),
}
_TASK_RE = re.compile(
    r"^\s*-\s*\[([ xX~\-])\]\*?\s+([0-9]+(?:\.[0-9]+)*)(?:\.\s+|\s+)(.+?)\s*$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONSUMER_REF_RE = re.compile(r"^(?P<spec>[^:]+):[A-Za-z]*(?P<task>[0-9]+(?:\.[0-9]+)?)$")


class ProgramMilestoneError(RuntimeError):
    """Raised when the reviewed program graph cannot be projected safely."""


def _stable_json(value: Any, *, indent: int | None = None) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
        separators=(",", ":") if indent is None else None,
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except FileNotFoundError as exc:
        raise ProgramMilestoneError(f"required input does not exist: {_relative(path)}") from exc


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(_REPO.resolve()).as_posix()
    except ValueError as exc:
        raise ProgramMilestoneError(f"path escapes repository root: {path}") from exc


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramMilestoneError(f"required JSON does not exist: {_relative(path)}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramMilestoneError(f"invalid JSON {_relative(path)}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProgramMilestoneError(f"JSON root must be an object: {_relative(path)}")
    return value


def _record_input(inputs: dict[str, str], path: Path) -> str:
    relative = _relative(path)
    digest = _sha256_file(path)
    previous = inputs.setdefault(relative, digest)
    if previous != digest:
        raise ProgramMilestoneError(f"input changed while generating: {relative}")
    return digest


def _assert_inputs_unchanged(inputs: Mapping[str, str]) -> None:
    changed = [
        path
        for path, digest in sorted(inputs.items())
        if not (_REPO / path).is_file() or _sha256_file(_REPO / path) != digest
    ]
    if changed:
        raise ProgramMilestoneError(f"inputs_changed_during_generation: {changed}")


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProgramMilestoneError(f"cannot load Python module: {_relative(path)}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # import is a structural gate; never downgrade it to an empty fact set
        raise ProgramMilestoneError(
            f"cannot import {_relative(path)} ({type(exc).__name__})"
        ) from exc
    return module


def _validate_database_probe_definitions(
    definitions: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    probes = definitions.get("database_probes")
    if not isinstance(probes, list) or not probes:
        raise ProgramMilestoneError("definitions.database_probes must be a non-empty array")
    normalized: dict[str, dict[str, Any]] = {}
    for probe in probes:
        if not isinstance(probe, dict):
            raise ProgramMilestoneError("every database probe must be an object")
        probe_id = probe.get("id")
        if not isinstance(probe_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", probe_id):
            raise ProgramMilestoneError(f"invalid database probe id: {probe_id!r}")
        if probe_id in normalized:
            raise ProgramMilestoneError(f"duplicate database probe id: {probe_id}")
        relations = probe.get("relations")
        if not isinstance(relations, dict) or not relations:
            raise ProgramMilestoneError(f"database probe {probe_id} must declare relations")
        normalized_relations: dict[str, dict[str, list[str]]] = {}
        for table_name, requirement in relations.items():
            if not isinstance(table_name, str) or not _IDENTIFIER_RE.fullmatch(table_name):
                raise ProgramMilestoneError(
                    f"database probe {probe_id} has invalid relation {table_name!r}"
                )
            if not isinstance(requirement, dict):
                raise ProgramMilestoneError(
                    f"database probe {probe_id}/{table_name} requirement must be an object"
                )
            columns = requirement.get("columns")
            constraints = requirement.get("constraints", [])
            for label, values in (("columns", columns), ("constraints", constraints)):
                if not isinstance(values, list) or (label == "columns" and not values):
                    raise ProgramMilestoneError(
                        f"database probe {probe_id}/{table_name} must declare {label}[]"
                    )
                if any(
                    not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value)
                    for value in values
                ):
                    raise ProgramMilestoneError(
                        f"database probe {probe_id}/{table_name} has invalid {label}"
                    )
                if len(values) != len(set(values)):
                    raise ProgramMilestoneError(
                        f"database probe {probe_id}/{table_name} has duplicate {label}"
                    )
            normalized_relations[table_name] = {
                "columns": sorted(columns),
                "constraints": sorted(constraints),
            }
        normalized[probe_id] = {
            "id": probe_id,
            "relations": dict(sorted(normalized_relations.items())),
        }
    return normalized


def _validate_host_path_definition(definitions: Mapping[str, Any]) -> None:
    """锁死 G0-4 的显式分母、八项事实和无 grant 负例门。"""
    milestones = definitions.get("milestones") or []
    host_rows = [
        item
        for item in milestones
        if isinstance(item, Mapping) and item.get("id") == _HOST_PATH_MILESTONE_ID
    ]
    if len(host_rows) != 1:
        raise ProgramMilestoneError(
            f"definitions must contain exactly one {_HOST_PATH_MILESTONE_ID} milestone"
        )
    host = host_rows[0]
    if host.get("scope") != "per_entry":
        raise ProgramMilestoneError(f"{_HOST_PATH_MILESTONE_ID}: scope must be per_entry")

    projection = host.get("entry_projection")
    if not isinstance(projection, Mapping):
        raise ProgramMilestoneError(
            f"{_HOST_PATH_MILESTONE_ID}: entry_projection must be an object"
        )
    if projection.get("state_policy") != _HOST_PATH_STATE_POLICY:
        raise ProgramMilestoneError(
            f"{_HOST_PATH_MILESTONE_ID}: state_policy must be {_HOST_PATH_STATE_POLICY}"
        )
    denominator = projection.get("denominator")
    if (
        not isinstance(denominator, list)
        or not denominator
        or any(not isinstance(item, str) or not item.strip() for item in denominator)
        or len(denominator) != len(set(denominator))
    ):
        raise ProgramMilestoneError(
            f"{_HOST_PATH_MILESTONE_ID}: denominator must be a unique non-empty entry-id array"
        )
    raw_index = projection.get("evidence_index")
    if not isinstance(raw_index, str) or not raw_index.strip() or Path(raw_index).is_absolute():
        raise ProgramMilestoneError(
            f"{_HOST_PATH_MILESTONE_ID}: evidence_index must be repository-relative"
        )
    index_path = (_REPO / raw_index).resolve()
    try:
        index_path.relative_to(_REPO.resolve())
    except ValueError as exc:
        raise ProgramMilestoneError(
            f"{_HOST_PATH_MILESTONE_ID}: evidence_index escapes repository root"
        ) from exc

    predicates = host.get("predicates")
    if not isinstance(predicates, list) or len(predicates) != len(_HOST_PATH_FACTS):
        raise ProgramMilestoneError(
            f"{_HOST_PATH_MILESTONE_ID}: exactly {len(_HOST_PATH_FACTS)} predicates are required"
        )
    facts: list[str] = []
    for predicate in predicates:
        if not isinstance(predicate, Mapping) or predicate.get("type") != "host_path_entry_fact":
            raise ProgramMilestoneError(
                f"{_HOST_PATH_MILESTONE_ID}: every predicate must use host_path_entry_fact"
            )
        if "grants_state" in predicate:
            raise ProgramMilestoneError(
                f"{_HOST_PATH_MILESTONE_ID}/{predicate.get('id')}: grants_state is forbidden"
            )
        facts.append(str(predicate.get("fact") or ""))
    if Counter(facts) != Counter(_HOST_PATH_FACTS):
        raise ProgramMilestoneError(
            f"{_HOST_PATH_MILESTONE_ID}: predicates must cover every reviewed fact exactly once"
        )

    for milestone in milestones:
        if not isinstance(milestone, Mapping) or milestone.get("id") == _HOST_PATH_MILESTONE_ID:
            continue
        if any(
            isinstance(predicate, Mapping)
            and predicate.get("type") == "host_path_entry_fact"
            for predicate in milestone.get("predicates") or []
        ):
            raise ProgramMilestoneError(
                "host_path_entry_fact is sealed to HOST-CONSUMES-UNIFIED-PATH"
            )


def load_definitions(path: Path = _DEFINITIONS_PATH) -> dict[str, Any]:
    definitions = _read_json(path)
    if definitions.get("schema_version") != _DEFINITION_SCHEMA:
        raise ProgramMilestoneError(
            f"unsupported definitions schema: {definitions.get('schema_version')!r}"
        )
    if definitions.get("review_status") != "reviewed":
        raise ProgramMilestoneError("milestone definitions must have review_status='reviewed'")

    specs = definitions.get("specs")
    if not isinstance(specs, list) or len(specs) != 8 or any(not isinstance(item, str) for item in specs):
        raise ProgramMilestoneError("definitions.specs must contain the eight named spec directories")
    if len(set(specs)) != len(specs):
        raise ProgramMilestoneError("definitions.specs contains duplicates")

    work_package = definitions.get("work_package")
    required_package_fields = {
        "id",
        "owner",
        "modified_files",
        "input_gates",
        "output_artifact",
        "targeted_tests",
        "real_scenarios",
        "rollback",
        "evidence_path",
    }
    if not isinstance(work_package, dict) or not required_package_fields <= work_package.keys():
        raise ProgramMilestoneError(
            f"work_package must define {sorted(required_package_fields)} before it can start"
        )

    database_probes = _validate_database_probe_definitions(definitions)

    milestones = definitions.get("milestones")
    if not isinstance(milestones, list) or not milestones:
        raise ProgramMilestoneError("definitions.milestones must be a non-empty array")
    ids = [item.get("id") for item in milestones if isinstance(item, dict)]
    if len(ids) != len(milestones) or any(not isinstance(item, str) or not item for item in ids):
        raise ProgramMilestoneError("every milestone must have a non-empty string id")
    if len(set(ids)) != len(ids):
        raise ProgramMilestoneError("milestone ids must be unique")

    for milestone in milestones:
        if milestone.get("scope") not in {"global", "per_entry"}:
            raise ProgramMilestoneError(f"{milestone['id']}: invalid scope")
        producers = milestone.get("producers")
        consumers = milestone.get("consumers")
        predicates = milestone.get("predicates")
        if not isinstance(producers, list) or not isinstance(consumers, list):
            raise ProgramMilestoneError(f"{milestone['id']}: producers/consumers must be arrays")
        if not isinstance(predicates, list) or not predicates:
            raise ProgramMilestoneError(f"{milestone['id']}: predicates must be non-empty")
        predicate_ids: list[str] = []
        for predicate in predicates:
            if not isinstance(predicate, dict):
                raise ProgramMilestoneError(f"{milestone['id']}: predicate must be an object")
            predicate_id = predicate.get("id")
            predicate_type = predicate.get("type")
            if not isinstance(predicate_id, str) or not predicate_id:
                raise ProgramMilestoneError(f"{milestone['id']}: predicate id is required")
            if predicate_type not in _ALLOWED_PREDICATE_TYPES:
                raise ProgramMilestoneError(
                    f"{milestone['id']}: unsupported predicate type {predicate_type!r}"
                )
            if (
                predicate_type == "database_readonly_schema"
                and predicate.get("probe_id") not in database_probes
            ):
                raise ProgramMilestoneError(
                    f"{milestone['id']}/{predicate_id}: unknown database probe "
                    f"{predicate.get('probe_id')!r}"
                )
            grant = predicate.get("grants_state")
            if grant is not None and grant not in _STATE_ORDER:
                raise ProgramMilestoneError(
                    f"{milestone['id']}/{predicate_id}: invalid grants_state {grant!r}"
                )
            predicate_ids.append(predicate_id)
        if len(set(predicate_ids)) != len(predicate_ids):
            raise ProgramMilestoneError(f"{milestone['id']}: predicate ids must be unique")
    _validate_host_path_definition(definitions)
    return definitions


def parse_tasks(text: str, *, source: str = "tasks.md") -> dict[str, dict[str, Any]]:
    """Parse only line-start primary task checkboxes; nested prose never changes the denominator."""
    tasks: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _TASK_RE.match(line)
        if not match:
            continue
        state = match.group(1).lower()
        task_id = match.group(2)
        if task_id in tasks:
            raise ProgramMilestoneError(f"{source}: duplicate primary task {task_id}")
        tasks[task_id] = {
            "state": state,
            "line": line_number,
            "title": match.group(3).strip(),
        }
    if not tasks:
        raise ProgramMilestoneError(f"{source}: no line-start primary tasks were parsed")
    return tasks


def parse_dependency_graph(text: str, *, source: str = "tasks.md") -> dict[str, Any]:
    lines = text.splitlines()
    try:
        heading = next(index for index, line in enumerate(lines) if line.strip() == "## Task Dependency Graph")
    except StopIteration as exc:
        raise ProgramMilestoneError(f"{source}: missing Task Dependency Graph") from exc
    fence = next(
        (index for index in range(heading + 1, len(lines)) if lines[index].strip() == "```json"),
        -1,
    )
    if fence < 0:
        raise ProgramMilestoneError(f"{source}: dependency graph has no JSON fence")
    close = next(
        (index for index in range(fence + 1, len(lines)) if lines[index].strip() == "```"),
        -1,
    )
    if close < 0:
        raise ProgramMilestoneError(f"{source}: dependency graph fence is not closed")
    try:
        graph = json.loads("\n".join(lines[fence + 1 : close]))
    except json.JSONDecodeError as exc:
        raise ProgramMilestoneError(f"{source}: dependency graph is invalid JSON: {exc}") from exc
    if not isinstance(graph, dict) or not isinstance(graph.get("waves"), list):
        raise ProgramMilestoneError(f"{source}: dependency graph must contain waves[]")
    return graph


def _task_id(value: Any, *, source: str) -> str:
    if isinstance(value, bool):
        raise ProgramMilestoneError(f"{source}: boolean is not a task id")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        return value
    raise ProgramMilestoneError(f"{source}: invalid task id {value!r}")


def _task_order_key(value: str) -> tuple[int, ...]:
    """按任务号的数值层级比较同 Wave 依赖顺序。"""
    return tuple(int(part) for part in value.split("."))


def _find_cycle(nodes: Iterable[str], dependencies: Mapping[str, Iterable[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    trail: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in visiting:
            start = trail.index(node)
            return trail[start:] + [node]
        if node in visited:
            return None
        visiting.add(node)
        trail.append(node)
        for dependency in sorted(set(dependencies.get(node, ()))):
            cycle = visit(dependency)
            if cycle:
                return cycle
        trail.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in sorted(set(nodes)):
        cycle = visit(node)
        if cycle:
            return cycle
    return None


def normalize_dependency_graph(
    graph: dict[str, Any], tasks: Mapping[str, Any], *, source: str
) -> dict[str, Any]:
    task_ids = set(tasks)
    wave_of: dict[str, int] = {}
    normalized_waves: list[dict[str, Any]] = []
    for raw_wave in graph["waves"]:
        if not isinstance(raw_wave, dict) or not isinstance(raw_wave.get("tasks"), list):
            raise ProgramMilestoneError(f"{source}: each wave needs tasks[]")
        wave_id = raw_wave.get("wave")
        if not isinstance(wave_id, int):
            raise ProgramMilestoneError(f"{source}: wave id must be an integer")
        normalized_tasks = [_task_id(item, source=source) for item in raw_wave["tasks"]]
        for task in normalized_tasks:
            if task in wave_of:
                raise ProgramMilestoneError(f"{source}: task {task} appears in multiple waves")
            wave_of[task] = wave_id
        normalized_waves.append(
            {
                "wave": wave_id,
                "name": str(raw_wave.get("name") or ""),
                "tasks": normalized_tasks,
                "depends_on": list(raw_wave.get("depends_on") or []),
            }
        )

    unknown_wave_tasks = sorted(set(wave_of) - task_ids)
    missing_wave_tasks = sorted(task_ids - set(wave_of))
    if unknown_wave_tasks or missing_wave_tasks:
        raise ProgramMilestoneError(
            f"{source}: wave/task denominator differs; unknown={unknown_wave_tasks}, "
            f"missing={missing_wave_tasks}"
        )

    dependencies_raw = graph.get("dependencies")
    if dependencies_raw is None:
        dependencies_raw = graph.get("hard_dependencies") or {}
    if not isinstance(dependencies_raw, dict):
        raise ProgramMilestoneError(f"{source}: dependencies/hard_dependencies must be an object")
    dependencies: dict[str, list[str]] = {task: [] for task in task_ids}
    for raw_task, raw_dependencies in dependencies_raw.items():
        task = _task_id(raw_task, source=source)
        if task not in task_ids:
            raise ProgramMilestoneError(f"{source}: dependency key references unknown task {task}")
        if not isinstance(raw_dependencies, list):
            raise ProgramMilestoneError(f"{source}: dependencies for task {task} must be an array")
        refs = [_task_id(item, source=source) for item in raw_dependencies]
        unknown = sorted(set(refs) - task_ids)
        if unknown:
            raise ProgramMilestoneError(f"{source}: task {task} depends on unknown tasks {unknown}")
        future = sorted(ref for ref in refs if wave_of[ref] > wave_of[task])
        if future:
            raise ProgramMilestoneError(f"{source}: task {task} depends on future-wave tasks {future}")
        same_wave_non_earlier = sorted(
            (
                ref
                for ref in refs
                if wave_of[ref] == wave_of[task]
                and _task_order_key(ref) >= _task_order_key(task)
            ),
            key=_task_order_key,
        )
        if same_wave_non_earlier:
            raise ProgramMilestoneError(
                f"{source}: task {task} depends on same-wave non-earlier tasks "
                f"{same_wave_non_earlier}"
            )
        dependencies[task] = sorted(set(refs))

    cycle = _find_cycle(task_ids, dependencies)
    if cycle:
        raise ProgramMilestoneError(f"{source}: dependency cycle {' -> '.join(cycle)}")
    external = graph.get("external_dependencies") or {"consumes": [], "produces": []}
    if not isinstance(external, dict):
        raise ProgramMilestoneError(f"{source}: external_dependencies must be an object")
    return {
        "waves": sorted(normalized_waves, key=lambda item: item["wave"]),
        "dependencies": dict(sorted(dependencies.items())),
        "external_dependencies": copy.deepcopy(external),
    }


def collect_spec_facts(
    definitions: Mapping[str, Any], inputs: dict[str, str]
) -> dict[str, dict[str, Any]]:
    facts: dict[str, dict[str, Any]] = {}
    for spec_name in definitions["specs"]:
        path = _SPECS_ROOT / spec_name / "tasks.md"
        digest = _record_input(inputs, path)
        text = path.read_text(encoding="utf-8")
        tasks = parse_tasks(text, source=_relative(path))
        graph = normalize_dependency_graph(
            parse_dependency_graph(text, source=_relative(path)),
            tasks,
            source=_relative(path),
        )
        counts = Counter(item["state"] for item in tasks.values())
        facts[spec_name] = {
            "path": _relative(path),
            "source_digest": digest,
            "task_count": len(tasks),
            "state_counts": {
                "completed": counts["x"],
                "partial": counts["~"],
                "blocked": counts["-"],
                "pending": counts[" "],
            },
            "task_states": {task: value["state"] for task, value in sorted(tasks.items())},
            "task_lines": {task: value["line"] for task, value in sorted(tasks.items())},
            "graph": graph,
        }
    return facts


def _diagnostic(code: str, *, severity: str = "blocker", **details: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, **details}


def _normalize_consumer_ref(value: str) -> tuple[str, str] | None:
    match = _CONSUMER_REF_RE.match(value)
    if not match:
        return None
    return match.group("spec"), match.group("task")


def validate_program_dag(
    definitions: Mapping[str, Any], spec_facts: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    milestones = {item["id"]: item for item in definitions["milestones"]}
    nodes = {
        f"{spec}:{task}"
        for spec, facts in spec_facts.items()
        for task in facts["task_states"]
    }
    dependencies: dict[str, set[str]] = {node: set() for node in nodes}
    for spec, facts in spec_facts.items():
        for task, refs in facts["graph"]["dependencies"].items():
            dependencies[f"{spec}:{task}"].update(f"{spec}:{ref}" for ref in refs)

    diagnostics: list[dict[str, Any]] = []
    cross_edges: set[tuple[str, str, str]] = set()
    for milestone in definitions["milestones"]:
        producer_nodes: list[str] = []
        for producer in milestone["producers"]:
            spec = producer.get("spec")
            tasks = producer.get("tasks")
            if spec not in spec_facts or not isinstance(tasks, list):
                raise ProgramMilestoneError(f"{milestone['id']}: invalid producer {producer!r}")
            if not tasks:
                diagnostics.append(
                    _diagnostic(
                        "producer_tasks_missing",
                        milestone=milestone["id"],
                        spec=spec,
                    )
                )
            for raw_task in tasks:
                task = _task_id(raw_task, source=f"{milestone['id']} producer")
                node = f"{spec}:{task}"
                if node not in nodes:
                    raise ProgramMilestoneError(
                        f"{milestone['id']}: producer task does not exist: {node}"
                    )
                producer_nodes.append(node)
        for consumer in milestone["consumers"]:
            spec = consumer.get("spec")
            tasks = consumer.get("tasks")
            required_state = consumer.get("required_state")
            if spec not in spec_facts or not isinstance(tasks, list):
                raise ProgramMilestoneError(f"{milestone['id']}: invalid consumer {consumer!r}")
            if required_state not in _STATE_ORDER:
                raise ProgramMilestoneError(
                    f"{milestone['id']}: invalid consumer required_state {required_state!r}"
                )
            for raw_task in tasks:
                task = _task_id(raw_task, source=f"{milestone['id']} consumer")
                consumer_node = f"{spec}:{task}"
                if consumer_node not in nodes:
                    raise ProgramMilestoneError(
                        f"{milestone['id']}: consumer task does not exist: {consumer_node}"
                    )
                for producer_node in producer_nodes:
                    dependencies[consumer_node].add(producer_node)
                    cross_edges.add((producer_node, consumer_node, milestone["id"]))

    for spec, facts in spec_facts.items():
        external = facts["graph"]["external_dependencies"]
        consumes = external.get("consumes") or []
        produces = external.get("produces") or []
        if not isinstance(consumes, list) or not isinstance(produces, list):
            raise ProgramMilestoneError(f"{spec}: external consumes/produces must be arrays")
        for item in consumes:
            if not isinstance(item, dict) or item.get("milestone") not in milestones:
                raise ProgramMilestoneError(f"{spec}: orphan external consumer {item!r}")
            milestone = milestones[item["milestone"]]
            expected_specs = {producer["spec"] for producer in milestone["producers"]}
            if item.get("producer_system"):
                diagnostics.append(
                    _diagnostic(
                        "natural_language_producer_placeholder",
                        milestone=item["milestone"],
                        consumer_spec=spec,
                        producer_system=item["producer_system"],
                    )
                )
            producer_spec = item.get("producer_spec")
            if producer_spec is not None and producer_spec not in expected_specs:
                diagnostics.append(
                    _diagnostic(
                        "external_producer_mismatch",
                        milestone=item["milestone"],
                        consumer_spec=spec,
                        declared=producer_spec,
                        expected=sorted(expected_specs),
                    )
                )
            for raw_task in item.get("required_by_tasks") or []:
                task = _task_id(raw_task, source=f"{spec} external consumer")
                if task not in facts["task_states"]:
                    raise ProgramMilestoneError(
                        f"{spec}: milestone {item['milestone']} references unknown consumer task {task}"
                    )
        for item in produces:
            if not isinstance(item, dict) or item.get("milestone") not in milestones:
                raise ProgramMilestoneError(f"{spec}: orphan external producer {item!r}")
            task = _task_id(item.get("task"), source=f"{spec} external producer")
            expected = {
                (producer["spec"], producer_task)
                for producer in milestones[item["milestone"]]["producers"]
                for producer_task in producer["tasks"]
            }
            if (spec, task) not in expected:
                diagnostics.append(
                    _diagnostic(
                        "external_producer_task_mismatch",
                        milestone=item["milestone"],
                        declared=f"{spec}:{task}",
                        expected=[f"{owner}:{owner_task}" for owner, owner_task in sorted(expected)],
                    )
                )
            for raw_ref in item.get("consumers") or []:
                parsed = _normalize_consumer_ref(str(raw_ref))
                if parsed is None or f"{parsed[0]}:{parsed[1]}" not in nodes:
                    raise ProgramMilestoneError(
                        f"{spec}: invalid external consumer reference {raw_ref!r}"
                    )

    core = spec_facts["workpaper-html-onlyoffice-bidirectional-writeback-closure"]
    archive_dependencies = set(core["graph"]["dependencies"].get("72") or [])
    if "74" not in archive_dependencies:
        diagnostics.append(
            _diagnostic(
                "archive_bypasses_writer_debt",
                spec="workpaper-html-onlyoffice-bidirectional-writeback-closure",
                task="72",
                missing_dependency="74",
            )
        )

    cycle = _find_cycle(nodes, dependencies)
    if cycle:
        raise ProgramMilestoneError(f"combined program dependency cycle: {' -> '.join(cycle)}")
    return (
        {
            "node_count": len(nodes),
            "internal_edge_count": sum(
                len(facts["graph"]["dependencies"][task])
                for facts in spec_facts.values()
                for task in facts["graph"]["dependencies"]
            ),
            "cross_spec_edge_count": len(cross_edges),
            "cross_spec_edges": [
                {"producer": producer, "consumer": consumer, "milestone": milestone}
                for producer, consumer, milestone in sorted(cross_edges)
            ],
            "acyclic": True,
        },
        diagnostics,
    )


def collect_manifest_facts(
    inputs: dict[str, str], *, reviewed_entry_ids: Iterable[str] = ()
) -> dict[str, Any]:
    _record_input(inputs, _MANIFEST_PATH)
    _record_input(inputs, _MANIFEST_GENERATOR_PATH)
    module = _load_module("workpaper_sync_manifest_generator_for_program", _MANIFEST_GENERATOR_PATH)
    manifest = _read_json(_MANIFEST_PATH)
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ProgramMilestoneError("workpaper sync manifest has an empty entry denominator")
    entry_ids = [entry.get("entry_id") for entry in entries if isinstance(entry, dict)]
    if len(entry_ids) != len(entries) or any(not isinstance(item, str) or not item for item in entry_ids):
        raise ProgramMilestoneError("workpaper sync manifest contains an entry without entry_id")
    if len(set(entry_ids)) != len(entry_ids):
        raise ProgramMilestoneError("workpaper sync manifest entry_id values are not unique")

    entry_by_id = {str(entry["entry_id"]): entry for entry in entries}
    reviewed = tuple(dict.fromkeys(str(item) for item in reviewed_entry_ids))
    missing_reviewed = sorted(set(reviewed) - set(entry_by_id))
    if missing_reviewed:
        raise ProgramMilestoneError(
            f"reviewed host-path entries are absent from manifest: {missing_reviewed}"
        )
    reviewed_entries = {
        entry_id: {
            key: copy.deepcopy(entry_by_id[entry_id].get(key))
            for key in (
                "entry_id",
                "adapter_id",
                "canonical_resolver",
                "capability",
                "document_type",
                "editability",
                "host_path",
                "html_store",
                "independent_entry",
                "migration_state",
            )
        }
        for entry_id in reviewed
    }

    payload = copy.deepcopy(manifest)
    stored_digest = payload.pop("manifest_digest", None)
    recomputed_digest = module._sha256_bytes(  # type: ignore[attr-defined]
        module._stable_json(payload).encode("utf-8")  # type: ignore[attr-defined]
    )
    self_consistent = stored_digest == recomputed_digest
    profile_digest = module._profile_source_digest(entries)  # type: ignore[attr-defined]
    profile_consistent = profile_digest == manifest.get("profile_source_digest")

    source_current = False
    source_reason = "manifest_projection_differs_from_source"
    try:
        discovery = module.discover_source()
        overlay_path = Path(module._OVERLAY)  # type: ignore[attr-defined]
        _record_input(inputs, overlay_path)
        discoverer = Path(module._DISCOVERER)  # type: ignore[attr-defined]
        _record_input(inputs, discoverer)
        overlay = module._read_json(overlay_path)  # type: ignore[attr-defined]
        expected = module.build_manifest(discovery, overlay)
        source_current = expected == manifest
    except Exception as exc:
        message = str(exc)
        source_reason = (
            "reviewed_overlay_source_digest_stale"
            if "source mounts changed" in message
            else f"manifest_source_derivation_failed:{type(exc).__name__}"
        )
    return {
        "manifest_digest": stored_digest,
        "entry_count": len(entries),
        "independent_entry_count": manifest.get("stats", {}).get("independent_entry_count"),
        "capability_counts": manifest.get("stats", {}).get("capability_counts") or {},
        "reviewed_entries": reviewed_entries,
        "self_consistent": self_consistent,
        "profile_consistent": profile_consistent,
        "source_current": source_current,
        "source_reason": None if source_current else source_reason,
    }


def collect_writer_gate_facts(inputs: dict[str, str]) -> dict[str, Any]:
    _record_input(inputs, _WRITER_GATE_PATH)
    _record_input(inputs, _WRITER_INVENTORY_PATH)
    gate = _load_module("workpaper_writer_revision_gate_for_program", _WRITER_GATE_PATH)
    inventory = gate.load_inventory()
    source_current = True
    source_reason: str | None = None
    try:
        gate.assert_inventory_is_current(inventory)
    except Exception as exc:
        source_current = False
        source_reason = f"writer_inventory_source_check_failed:{type(exc).__name__}"
    issues = gate.evaluate_gate(inventory)
    if not isinstance(issues, dict):
        raise ProgramMilestoneError("writer gate returned a non-object issue map")
    return {
        "inventory_digest": inventory.get("inventory_digest"),
        "source_digest": inventory.get("source_digest"),
        "source_current": source_current,
        "source_reason": source_reason,
        "issue_counts": {name: len(values) for name, values in sorted(issues.items())},
        "issue_samples": {name: list(values[:5]) for name, values in sorted(issues.items()) if values},
    }


class DatabaseProbeReadError(RuntimeError):
    """Stable failure classification for the mandatory read-only database probe."""

    def __init__(self, status: str, phase: str, code: str) -> None:
        super().__init__(f"{status}:{phase}:{code}")
        self.status = status
        self.phase = phase
        self.code = code


def _database_query_set_digest(definitions: Mapping[str, Any]) -> str:
    requirements = _validate_database_probe_definitions(definitions)
    return _sha256_bytes(
        _stable_json(
            {
                "schema_version": _DATABASE_PROBE_SCHEMA,
                "control_sql": _DATABASE_CONTROL_SQL,
                "fact_sql": _DATABASE_FACT_SQL,
                "requirements": requirements,
            }
        ).encode("utf-8")
    )


def recompute_database_probe_digest(facts: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(facts))
    payload.pop("probe_digest", None)
    return _sha256_bytes(_stable_json(payload).encode("utf-8"))


def database_probe_failure_facts(
    definitions: Mapping[str, Any],
    *,
    status: str,
    failure_phase: str,
    failure_code: str,
) -> dict[str, Any]:
    if status not in _DATABASE_PROBE_STATUSES - {"ok"}:
        raise ProgramMilestoneError(f"invalid database failure status: {status!r}")
    requirements = _validate_database_probe_definitions(definitions)
    result = "blocked" if status == "database_unavailable" else "fail"
    facts: dict[str, Any] = {
        "schema_version": _DATABASE_PROBE_SCHEMA,
        "status": status,
        "read_only_requested": True,
        "read_only_verified": False,
        "query_set_digest": _database_query_set_digest(definitions),
        "relation_denominator": sum(
            len(probe["relations"]) for probe in requirements.values()
        ),
        "column_denominator": sum(
            len(relation["columns"])
            for probe in requirements.values()
            for relation in probe["relations"].values()
        ),
        "constraint_denominator": sum(
            len(relation["constraints"])
            for probe in requirements.values()
            for relation in probe["relations"].values()
        ),
        "probes": {
            probe_id: {
                "result": result,
                "reason_code": status,
                "missing_relations": None,
                "missing_columns": None,
                "missing_constraints": None,
            }
            for probe_id in sorted(requirements)
        },
        "failure": {"phase": failure_phase, "code": failure_code},
    }
    facts["probe_digest"] = recompute_database_probe_digest(facts)
    return facts


def build_database_probe_facts(
    definitions: Mapping[str, Any],
    *,
    observed_relations: Iterable[str],
    observed_columns: Mapping[str, Iterable[str]],
    observed_constraints: Mapping[str, Iterable[str]],
    read_only_verified: bool,
) -> dict[str, Any]:
    requirements = _validate_database_probe_definitions(definitions)
    relation_set = set(observed_relations)
    column_sets = {name: set(values) for name, values in observed_columns.items()}
    constraint_sets = {name: set(values) for name, values in observed_constraints.items()}
    probes: dict[str, Any] = {}
    all_required_relations: set[str] = set()
    all_required_columns: set[tuple[str, str]] = set()
    all_required_constraints: set[tuple[str, str]] = set()

    for probe_id, probe in sorted(requirements.items()):
        required_relations = set(probe["relations"])
        all_required_relations.update(required_relations)
        missing_relations = sorted(required_relations - relation_set)
        missing_columns: dict[str, list[str]] = {}
        missing_constraints: dict[str, list[str]] = {}
        for table_name, requirement in probe["relations"].items():
            required_columns = set(requirement["columns"])
            required_constraints = set(requirement["constraints"])
            all_required_columns.update((table_name, name) for name in required_columns)
            all_required_constraints.update(
                (table_name, name) for name in required_constraints
            )
            absent_columns = sorted(required_columns - column_sets.get(table_name, set()))
            absent_constraints = sorted(
                required_constraints - constraint_sets.get(table_name, set())
            )
            if absent_columns:
                missing_columns[table_name] = absent_columns
            if absent_constraints:
                missing_constraints[table_name] = absent_constraints
        passed = bool(read_only_verified) and not (
            missing_relations or missing_columns or missing_constraints
        )
        probes[probe_id] = {
            "result": "pass" if passed else "fail",
            "reason_code": None if passed else "database_schema_requirements_missing",
            "relation_denominator": len(required_relations),
            "column_denominator": sum(
                len(item["columns"]) for item in probe["relations"].values()
            ),
            "constraint_denominator": sum(
                len(item["constraints"]) for item in probe["relations"].values()
            ),
            "missing_relations": missing_relations,
            "missing_columns": dict(sorted(missing_columns.items())),
            "missing_constraints": dict(sorted(missing_constraints.items())),
        }

    observed_required_relations = all_required_relations & relation_set
    observed_required_columns = {
        item for item in all_required_columns if item[1] in column_sets.get(item[0], set())
    }
    observed_required_constraints = {
        item
        for item in all_required_constraints
        if item[1] in constraint_sets.get(item[0], set())
    }
    facts: dict[str, Any] = {
        "schema_version": _DATABASE_PROBE_SCHEMA,
        "status": "ok" if read_only_verified else "query_failed",
        "read_only_requested": True,
        "read_only_verified": bool(read_only_verified),
        "query_set_digest": _database_query_set_digest(definitions),
        "relation_denominator": len(all_required_relations),
        "observed_relation_count": len(observed_required_relations),
        "column_denominator": len(all_required_columns),
        "observed_column_count": len(observed_required_columns),
        "constraint_denominator": len(all_required_constraints),
        "observed_constraint_count": len(observed_required_constraints),
        "probes": probes,
        "failure": None,
    }
    facts["probe_digest"] = recompute_database_probe_digest(facts)
    return facts


async def _collect_database_catalog() -> dict[str, Any]:
    backend_path = str(_REPO / "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    phase = "import_database"
    try:
        import sqlalchemy as sa

        from app.core.database import async_session, engine

        relations: set[str] = set()
        columns: dict[str, set[str]] = defaultdict(set)
        constraints: dict[str, set[str]] = defaultdict(set)
        # collect_database_probe_facts 每次调用都 asyncio.run（自建并关闭事件循环），
        # 但 app.core.database.engine 是模块级常驻连接池，asyncpg 连接绑定在创建它的
        # 循环上。若不在同一循环内 dispose，下一次探测会取到上一循环的连接，在
        # phase="connect" 抛 RuntimeError('Event loop is closed')，表现为「隔次失败」
        # → 同一棵树两次运行给出两份不同 projection。谁开循环谁清池。
        try:
            async with async_session() as session:
                phase = "connect"
                await session.connection()
                try:
                    phase = "set_read_only"
                    await session.execute(sa.text(_DATABASE_CONTROL_SQL["set_read_only"]))
                    phase = "verify_read_only"
                    read_only = (
                        await session.execute(sa.text(_DATABASE_CONTROL_SQL["verify_read_only"]))
                    ).scalar_one()
                    if str(read_only).strip().lower() not in {"on", "true", "1"}:
                        raise RuntimeError("transaction_read_only_not_enabled")

                    phase = "query:relations"
                    rows = (
                        await session.execute(sa.text(_DATABASE_FACT_SQL["relations"]))
                    ).mappings().all()
                    relations = {str(row["table_name"]) for row in rows}

                    phase = "query:columns"
                    rows = (
                        await session.execute(sa.text(_DATABASE_FACT_SQL["columns"]))
                    ).mappings().all()
                    for row in rows:
                        columns[str(row["table_name"])].add(str(row["column_name"]))

                    phase = "query:constraints"
                    rows = (
                        await session.execute(sa.text(_DATABASE_FACT_SQL["constraints"]))
                    ).mappings().all()
                    for row in rows:
                        constraints[str(row["table_name"])].add(
                            str(row["constraint_name"])
                        )
                finally:
                    await session.rollback()
        finally:
            try:
                await engine.dispose()
            except Exception:
                phase = "dispose"
                raise
    except Exception as exc:
        status = "database_unavailable" if phase == "connect" else "query_failed"
        raise DatabaseProbeReadError(status, phase, type(exc).__name__) from exc
    return {
        "relations": relations,
        "columns": columns,
        "constraints": constraints,
        "read_only_verified": True,
    }


def collect_database_probe_facts(definitions: Mapping[str, Any]) -> dict[str, Any]:
    try:
        catalog = asyncio.run(_collect_database_catalog())
    except DatabaseProbeReadError as exc:
        return database_probe_failure_facts(
            definitions,
            status=exc.status,
            failure_phase=exc.phase,
            failure_code=exc.code,
        )
    return build_database_probe_facts(
        definitions,
        observed_relations=catalog["relations"],
        observed_columns=catalog["columns"],
        observed_constraints=catalog["constraints"],
        read_only_verified=bool(catalog["read_only_verified"]),
    )


def _validate_database_probe_facts(
    definitions: Mapping[str, Any], facts: Mapping[str, Any]
) -> dict[str, Any]:
    value = copy.deepcopy(dict(facts))
    expected_ids = set(_validate_database_probe_definitions(definitions))
    if value.get("schema_version") != _DATABASE_PROBE_SCHEMA:
        raise ProgramMilestoneError("database probe facts use the wrong schema")
    if value.get("status") not in _DATABASE_PROBE_STATUSES:
        raise ProgramMilestoneError("database probe facts use an invalid status")
    if value.get("query_set_digest") != _database_query_set_digest(definitions):
        raise ProgramMilestoneError("database probe query set is stale")
    probes = value.get("probes")
    if not isinstance(probes, dict) or set(probes) != expected_ids:
        raise ProgramMilestoneError("database probe facts do not cover the reviewed probe set")
    if value.get("status") == "ok" and value.get("read_only_verified") is not True:
        raise ProgramMilestoneError("database probe claims ok without read-only verification")
    if value.get("probe_digest") != recompute_database_probe_digest(value):
        raise ProgramMilestoneError("database probe digest is not self-consistent")
    return value


def _python_symbols(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=_relative(path))
    except SyntaxError as exc:
        raise ProgramMilestoneError(f"invalid Python syntax in {_relative(path)}: {exc}") from exc
    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.add(node.name)
        elif isinstance(node, ast.ClassDef):
            symbols.add(node.name)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.add(f"{node.name}.{child.name}")
    return symbols


def _source_ref(path: str, digest: str) -> dict[str, str]:
    return {"path": path, "sha256": digest}


def _repo_input_path(raw_path: str) -> Path:
    if not raw_path or Path(raw_path).is_absolute():
        raise ProgramMilestoneError(f"reviewed input path must be repository-relative: {raw_path!r}")
    path = (_REPO / raw_path).resolve()
    try:
        path.relative_to(_REPO.resolve())
    except ValueError as exc:
        raise ProgramMilestoneError(f"reviewed input path escapes repository root: {raw_path}") from exc
    return path


def recompute_host_path_index_digest(document: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(document))
    payload.pop("index_digest", None)
    return _sha256_bytes(_stable_json(payload).encode("utf-8"))


def _python_module_tree(path: Path) -> ast.Module:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=_relative(path))
    except SyntaxError as exc:
        raise ProgramMilestoneError(f"invalid Python syntax in {_relative(path)}: {exc}") from exc


def _python_assigned_literal(path: Path, name: str) -> Any:
    tree = _python_module_tree(path)
    for node in tree.body:
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                value = node.value
        if value is not None:
            try:
                return ast.literal_eval(value)
            except (ValueError, TypeError) as exc:
                raise ProgramMilestoneError(
                    f"{_relative(path)}::{name} must be a literal"
                ) from exc
    raise ProgramMilestoneError(f"{_relative(path)}::{name} is missing")


def _python_string_constant(path: Path, name: str) -> str:
    value = _python_assigned_literal(path, name)
    if not isinstance(value, str) or not value:
        raise ProgramMilestoneError(f"{_relative(path)}::{name} must be a non-empty string")
    return value


def _python_string_tuple(path: Path, name: str) -> tuple[str, ...]:
    value = _python_assigned_literal(path, name)
    if (
        not isinstance(value, tuple)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise ProgramMilestoneError(f"{_relative(path)}::{name} must be a unique string tuple")
    return value


def _python_enum_values(path: Path, class_name: str) -> set[str]:
    tree = _python_module_tree(path)
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        values: set[str] = set()
        for child in node.body:
            if not isinstance(child, ast.Assign) or len(child.targets) != 1:
                continue
            if not isinstance(child.targets[0], ast.Name):
                continue
            if isinstance(child.value, ast.Constant) and isinstance(child.value.value, str):
                values.add(child.value.value)
        if values:
            return values
    raise ProgramMilestoneError(f"{_relative(path)}::{class_name} enum values are missing")


def _python_function(path: Path, function_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = _python_module_tree(path)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return node
    raise ProgramMilestoneError(f"{_relative(path)}::{function_name} is missing")


def _call_name(node: ast.Call) -> str:
    value: ast.expr = node.func
    parts: list[str] = []
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


def _function_calls(path: Path, function_name: str, expected_call: str) -> bool:
    function = _python_function(path, function_name)
    return any(
        _call_name(node) == expected_call or _call_name(node).endswith(f".{expected_call}")
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
    )


def _function_returns_literal_true(
    path: Path, function_name: str, response_key: str
) -> bool:
    function = _python_function(path, function_name)
    for node in ast.walk(function):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant)
                and key.value == response_key
                and isinstance(value, ast.Constant)
                and value.value is True
            ):
                return True
    return False


def _append_source_ref(
    source_refs: list[dict[str, str]], path: Path, digest: str
) -> None:
    value = _source_ref(_relative(path), digest)
    if value not in source_refs:
        source_refs.append(value)


def _validate_host_source_bindings(
    document: Mapping[str, Any],
    *,
    inputs: dict[str, str],
    source_refs: list[dict[str, str]],
    stale_reasons: list[str],
    label: str,
) -> None:
    bindings = document.get("source_bindings")
    if not isinstance(bindings, list) or not bindings:
        stale_reasons.append(f"{label}:source_bindings_missing")
        return
    seen: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, Mapping):
            stale_reasons.append(f"{label}:source_binding_not_object")
            continue
        raw_path = binding.get("path")
        expected_digest = binding.get("sha256")
        literals = binding.get("required_literals")
        if not isinstance(raw_path, str) or raw_path in seen:
            stale_reasons.append(f"{label}:source_binding_path_invalid")
            continue
        seen.add(raw_path)
        if not isinstance(expected_digest, str) or not _SHA256_RE.fullmatch(expected_digest):
            stale_reasons.append(f"{label}:source_binding_digest_invalid:{raw_path}")
            continue
        if not isinstance(literals, list) or any(not isinstance(item, str) for item in literals):
            stale_reasons.append(f"{label}:required_literals_invalid:{raw_path}")
            continue
        path = _repo_input_path(raw_path)
        if not path.is_file():
            stale_reasons.append(f"{label}:source_missing:{raw_path}")
            continue
        actual_digest = _record_input(inputs, path)
        _append_source_ref(source_refs, path, actual_digest)
        if actual_digest != expected_digest:
            stale_reasons.append(f"{label}:source_digest_mismatch:{raw_path}")
        text = path.read_text(encoding="utf-8")
        for literal in literals:
            if literal not in text:
                stale_reasons.append(f"{label}:required_literal_missing:{raw_path}")


def collect_host_path_evidence(
    milestone: Mapping[str, Any],
    *,
    inputs: dict[str, str],
    manifest_facts: Mapping[str, Any],
) -> dict[str, Any]:
    """加载 digest-bound G0-4 bundle；静态证据只能证明负例，不能授予正向状态。"""
    projection = milestone["entry_projection"]
    denominator = tuple(str(item) for item in projection["denominator"])
    index_path = _repo_input_path(str(projection["evidence_index"]))
    index_digest = _record_input(inputs, index_path)
    index = _read_json(index_path)
    common_stale: list[str] = []
    if index.get("schema_version") != _HOST_PATH_INDEX_SCHEMA:
        common_stale.append("index_schema_mismatch")
    if index.get("milestone") != _HOST_PATH_MILESTONE_ID:
        common_stale.append("index_milestone_mismatch")
    if index.get("state_policy") != _HOST_PATH_STATE_POLICY:
        common_stale.append("index_state_policy_mismatch")
    review_status = index.get("review_status")
    if review_status not in {
        "reviewed_negative_baseline",
        "reviewed_positive_runtime",
    }:
        common_stale.append("index_review_status_invalid")
    positive_review = review_status == "reviewed_positive_runtime"
    if index.get("index_digest") != recompute_host_path_index_digest(index):
        common_stale.append("index_digest_mismatch")
    if index.get("denominator") != list(denominator):
        common_stale.append("index_denominator_mismatch")
    run_id = index.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        common_stale.append("index_run_id_missing")
        run_id = ""

    raw_entries = index.get("entries")
    if not isinstance(raw_entries, list):
        raise ProgramMilestoneError("host-path evidence index entries must be an array")
    entry_rows = {
        str(row.get("entry_id")): row
        for row in raw_entries
        if isinstance(row, Mapping) and isinstance(row.get("entry_id"), str)
    }
    if len(entry_rows) != len(raw_entries) or set(entry_rows) != set(denominator):
        common_stale.append("index_entry_denominator_mismatch")

    global_refs: list[dict[str, str]] = [_source_ref(_relative(index_path), index_digest)]
    for path in (
        _WP_SYNC_ROUTER_PATH,
        _CALLBACK_ROUTE_PATH,
        _SYNC_DOMAIN_MODELS_PATH,
        _SYNC_RETENTION_PATH,
    ):
        digest = _record_input(inputs, path)
        _append_source_ref(global_refs, path, digest)
    user_sync_prefix = _python_string_constant(_WP_SYNC_ROUTER_PATH, "USER_SYNC_PREFIX")
    callback_query_keys = _python_string_tuple(_CALLBACK_ROUTE_PATH, "URL_BOUND_PARAMS")
    operation_states = _python_enum_values(_SYNC_DOMAIN_MODELS_PATH, "OperationState")
    in_flight_states = set(
        _python_string_tuple(_SYNC_RETENTION_PATH, "_IN_FLIGHT_OPERATION_STATES")
    )
    terminal_states = operation_states - in_flight_states
    if not terminal_states or "error" in terminal_states:
        raise ProgramMilestoneError("operation terminal-state derivation is not fail-closed")

    entries: dict[str, Any] = {}
    reviewed_manifest = manifest_facts.get("reviewed_entries") or {}
    for entry_id in denominator:
        stale_reasons = list(common_stale)
        source_refs = copy.deepcopy(global_refs)
        row = entry_rows.get(entry_id)
        if not isinstance(row, Mapping):
            row = {}
            stale_reasons.append(f"entry_missing:{entry_id}")
        identity = row.get("identity")
        if not isinstance(identity, Mapping):
            identity = {}
            stale_reasons.append(f"identity_missing:{entry_id}")
        manifest_row = reviewed_manifest.get(entry_id)
        if not isinstance(manifest_row, Mapping):
            stale_reasons.append(f"manifest_reviewed_entry_missing:{entry_id}")
            manifest_row = {}
        for identity_key, manifest_key in (
            ("manifest_entry_id", "entry_id"),
            ("adapter_id", "adapter_id"),
            ("host_path", "host_path"),
        ):
            if identity.get(identity_key) != manifest_row.get(manifest_key):
                stale_reasons.append(f"identity_manifest_mismatch:{identity_key}")

        artifact_refs = row.get("artifacts")
        if not isinstance(artifact_refs, list):
            artifact_refs = []
            stale_reasons.append(f"artifact_refs_missing:{entry_id}")
        channels: dict[str, Mapping[str, Any]] = {}
        seen_channels: set[str] = set()
        for artifact_ref in artifact_refs:
            if not isinstance(artifact_ref, Mapping):
                stale_reasons.append(f"artifact_ref_not_object:{entry_id}")
                continue
            channel = artifact_ref.get("channel")
            raw_path = artifact_ref.get("path")
            expected_digest = artifact_ref.get("sha256")
            if channel not in _HOST_PATH_CHANNEL_SCHEMAS or channel in seen_channels:
                stale_reasons.append(f"artifact_channel_invalid:{channel}")
                continue
            seen_channels.add(str(channel))
            if not isinstance(raw_path, str) or not isinstance(expected_digest, str):
                stale_reasons.append(f"artifact_binding_missing:{channel}")
                continue
            if not _SHA256_RE.fullmatch(expected_digest):
                stale_reasons.append(f"artifact_digest_invalid:{channel}")
                continue
            artifact_path = _repo_input_path(raw_path)
            if not artifact_path.is_file():
                stale_reasons.append(f"artifact_missing:{channel}")
                continue
            actual_digest = _record_input(inputs, artifact_path)
            _append_source_ref(source_refs, artifact_path, actual_digest)
            if actual_digest != expected_digest:
                stale_reasons.append(f"artifact_digest_mismatch:{channel}")
            document = _read_json(artifact_path)
            channels[str(channel)] = document
            if document.get("schema_version") != _HOST_PATH_CHANNEL_SCHEMAS[channel]:
                stale_reasons.append(f"artifact_schema_mismatch:{channel}")
            if document.get("run_id") != run_id:
                stale_reasons.append(f"artifact_run_id_mismatch:{channel}")
            if document.get("entry_id") != entry_id:
                stale_reasons.append(f"artifact_entry_id_mismatch:{channel}")
            _validate_host_source_bindings(
                document,
                inputs=inputs,
                source_refs=source_refs,
                stale_reasons=stale_reasons,
                label=str(channel),
            )
            if positive_review and channel in {"network", "editor_config"}:
                if not _host_positive_capture(document):
                    stale_reasons.append(f"{channel}:positive_capture_incomplete")
            if positive_review and channel == "database" and not _host_database_completed(document):
                stale_reasons.append("database:positive_runtime_incomplete")
        if seen_channels != set(_HOST_PATH_CHANNEL_SCHEMAS):
            stale_reasons.append("artifact_channel_coverage_incomplete")

        network = channels.get("network") or {}
        editor_config = channels.get("editor_config") or {}
        database = channels.get("database") or {}
        if not isinstance(network.get("requests"), list):
            stale_reasons.append("network_requests_invalid")
        if not isinstance(editor_config.get("observed_query_keys"), list):
            stale_reasons.append("editor_query_keys_invalid")
        for key in ("applications", "operations", "content_versions"):
            if not isinstance(database.get(key), list):
                stale_reasons.append(f"database_{key}_invalid")

        source_checks = row.get("source_checks")
        if not isinstance(source_checks, Mapping):
            source_checks = {}
            stale_reasons.append("source_checks_missing")
        secondary = source_checks.get("secondary_revision_domain")
        capability = source_checks.get("capability")
        secondary_call_present: bool | None = None
        capability_literal_true: bool | None = None
        server_computed_call_present: bool | None = None
        for label, check in (("secondary_revision_domain", secondary), ("capability", capability)):
            if not isinstance(check, Mapping):
                stale_reasons.append(f"source_check_missing:{label}")
                continue
            raw_path = check.get("path")
            expected_digest = check.get("sha256")
            if not isinstance(raw_path, str) or not isinstance(expected_digest, str):
                stale_reasons.append(f"source_check_binding_invalid:{label}")
                continue
            source_path = _repo_input_path(raw_path)
            if not source_path.is_file():
                stale_reasons.append(f"source_check_missing_file:{label}")
                continue
            actual_digest = _record_input(inputs, source_path)
            _append_source_ref(source_refs, source_path, actual_digest)
            if actual_digest != expected_digest:
                stale_reasons.append(f"source_check_digest_mismatch:{label}")
            try:
                if label == "secondary_revision_domain":
                    secondary_call_present = _function_calls(
                        source_path,
                        str(check.get("function") or ""),
                        str(check.get("forbidden_call") or ""),
                    )
                else:
                    function_name = str(check.get("function") or "")
                    capability_literal_true = _function_returns_literal_true(
                        source_path,
                        function_name,
                        str(check.get("response_key") or ""),
                    )
                    server_call = check.get("server_computed_call")
                    server_computed_call_present = (
                        _function_calls(source_path, function_name, server_call)
                        if isinstance(server_call, str) and server_call
                        else False
                    )
            except ProgramMilestoneError:
                stale_reasons.append(f"source_check_unreadable:{label}")

        entries[entry_id] = {
            "entry_id": entry_id,
            "identity": copy.deepcopy(dict(identity)),
            "manifest": copy.deepcopy(dict(manifest_row)),
            "run_id": run_id,
            "network": copy.deepcopy(dict(network)),
            "editor_config": copy.deepcopy(dict(editor_config)),
            "database": copy.deepcopy(dict(database)),
            "user_sync_prefix": user_sync_prefix,
            "required_callback_query_keys": list(callback_query_keys),
            "operation_terminal_states": sorted(terminal_states),
            "secondary_revision_call_present": secondary_call_present,
            "capability_literal_true": capability_literal_true,
            "server_computed_call_present": server_computed_call_present,
            "stale_reasons": sorted(set(stale_reasons)),
            "source_refs": sorted(source_refs, key=lambda item: item["path"]),
        }
    return {
        "state_policy": _HOST_PATH_STATE_POLICY,
        "denominator": list(denominator),
        "index_path": _relative(index_path),
        "index_digest": index_digest,
        "entries": entries,
    }


def _route_template_pattern(template: str) -> re.Pattern[str]:
    pattern = re.escape(template)
    for placeholder, replacement in (
        ("{project_id}", r"[^/]+"),
        ("{wp_id}", r"[^/]+"),
        ("{entry_id:path}", r".+"),
    ):
        pattern = pattern.replace(re.escape(placeholder), replacement)
    return re.compile(f"^{pattern}(?:/|$)")


def _host_network_observations(entry: Mapping[str, Any]) -> dict[str, list[str]]:
    network = entry.get("network") or {}
    requests = network.get("requests") or []
    urls = [
        str(item.get("url") or item.get("url_template"))
        for item in requests
        if isinstance(item, Mapping) and (item.get("url") or item.get("url_template"))
    ]
    callback = str((entry.get("editor_config") or {}).get("callback_url") or (
        entry.get("editor_config") or {}
    ).get("callback_url_template") or "")
    all_urls = urls + ([callback] if callback else [])
    prefix_pattern = _route_template_pattern(str(entry.get("user_sync_prefix") or ""))
    unified = [url for url in urls if prefix_pattern.match(urlsplit(url).path)]
    legacy = []
    for url in all_urls:
        path = urlsplit(url).path
        if "/d2-sync/" in path or re.search(
            r"/api/workpapers/[^/]+/sheets/[^/]+/onlyoffice-callback$", path
        ):
            legacy.append(url)
    return {"requests": urls, "unified": unified, "legacy": legacy}


def _host_positive_capture(document: Mapping[str, Any]) -> bool:
    return bool(
        document.get("execution_status") == "COMPLETED"
        and document.get("positive_state_eligible") is True
        and document.get("complete_for_positive_assertion") is True
    )


def _host_database_completed(document: Mapping[str, Any]) -> bool:
    return bool(
        document.get("execution_status") == "COMPLETED"
        and document.get("scenario_executed") is True
        and document.get("read_only_capture") is True
    )


def evaluate_host_path_entry_fact(
    entry: Mapping[str, Any], fact: str
) -> dict[str, Any]:
    if fact not in _HOST_PATH_FACTS:
        raise ProgramMilestoneError(f"unknown host-path fact: {fact}")
    source_refs = copy.deepcopy(list(entry.get("source_refs") or []))
    stale_reasons = list(entry.get("stale_reasons") or [])
    if stale_reasons:
        return _result(
            fact,
            "stale",
            reason_code="host_path_evidence_stale",
            source_refs=source_refs,
            details={"stale_reasons": stale_reasons},
        )

    network = entry.get("network") or {}
    editor = entry.get("editor_config") or {}
    database = entry.get("database") or {}
    observations = _host_network_observations(entry)
    negative_network_complete = bool(network.get("complete_for_negative_assertion") is True)

    if fact == "user_sync_prefix_request":
        if observations["unified"] and _host_positive_capture(network):
            result, reason = "pass", None
        elif negative_network_complete and not observations["unified"]:
            result, reason = "fail", "user_sync_prefix_request_absent"
        else:
            result, reason = "unverifiable", "runtime_network_capture_required"
        return _result(
            fact,
            result,
            reason_code=reason,
            source_refs=source_refs,
            details={"unified_request_count": len(observations["unified"])},
        )

    if fact == "no_legacy_bypass":
        if observations["legacy"]:
            result, reason = "fail", "legacy_bypass_request_observed"
        elif _host_positive_capture(network):
            result, reason = "pass", None
        else:
            result, reason = "unverifiable", "complete_runtime_network_capture_required"
        return _result(
            fact,
            result,
            reason_code=reason,
            source_refs=source_refs,
            details={"legacy_requests": observations["legacy"]},
        )

    if fact == "callback_url_bound":
        required = set(entry.get("required_callback_query_keys") or [])
        observed = set(editor.get("observed_query_keys") or [])
        missing = sorted(required - observed)
        if missing and editor.get("complete_for_negative_assertion") is True:
            result, reason = "fail", "callback_url_binding_missing"
        elif (
            not missing
            and (editor.get("callback_url") or editor.get("callback_url_template"))
            and _host_positive_capture(editor)
        ):
            result, reason = "pass", None
        else:
            result, reason = "unverifiable", "runtime_editor_config_capture_required"
        return _result(
            fact,
            result,
            reason_code=reason,
            source_refs=source_refs,
            details={"required_query_keys": sorted(required), "missing_query_keys": missing},
        )

    if fact in {
        "application_applied",
        "operation_terminal_bound",
        "onlyoffice_content_version",
    } and not _host_database_completed(database):
        return _result(
            fact,
            "unverifiable",
            reason_code="runtime_database_evidence_not_run",
            source_refs=source_refs,
            details={
                "execution_status": database.get("execution_status"),
                "scenario_executed": database.get("scenario_executed"),
            },
        )

    entry_id = str(entry.get("entry_id") or "")
    applications = [
        item
        for item in database.get("applications") or []
        if isinstance(item, Mapping) and item.get("entry_id") == entry_id
    ]
    applied = [item for item in applications if item.get("state") == "applied"]
    applied_ids = {str(item.get("id")) for item in applied if item.get("id")}

    if fact == "application_applied":
        passed = len(applications) == 1 and len(applied) == 1
        return _result(
            fact,
            "pass" if passed else "fail",
            reason_code=None if passed else "exact_entry_applied_application_missing",
            source_refs=source_refs,
            details={"matching_application_count": len(applications), "applied_count": len(applied)},
        )

    terminal_states = set(entry.get("operation_terminal_states") or [])
    operations = [
        item
        for item in database.get("operations") or []
        if isinstance(item, Mapping) and item.get("entry_id") == entry_id
    ]
    valid_operations = [
        item
        for item in operations
        if item.get("application_id")
        and str(item.get("application_id")) in applied_ids
        and item.get("state") in terminal_states
        and item.get("state") != "error"
    ]
    valid_operation_ids = {
        str(item.get("id")) for item in valid_operations if item.get("id")
    }

    if fact == "operation_terminal_bound":
        passed = len(valid_operations) == 1
        return _result(
            fact,
            "pass" if passed else "fail",
            reason_code=None if passed else "exact_entry_terminal_operation_not_bound",
            source_refs=source_refs,
            details={
                "matching_operation_count": len(operations),
                "valid_bound_terminal_count": len(valid_operations),
            },
        )

    if fact == "onlyoffice_content_version":
        versions = [
            item
            for item in database.get("content_versions") or []
            if isinstance(item, Mapping)
            and item.get("source") == "onlyoffice"
            and item.get("operation_id")
            and str(item.get("operation_id")) in valid_operation_ids
        ]
        passed = len(versions) == 1
        return _result(
            fact,
            "pass" if passed else "fail",
            reason_code=None if passed else "onlyoffice_version_operation_link_missing",
            source_refs=source_refs,
            details={"valid_onlyoffice_version_count": len(versions)},
        )

    if fact == "no_secondary_revision_domain":
        if entry.get("secondary_revision_call_present") is True:
            return _result(
                fact,
                "fail",
                reason_code="secondary_revision_domain_used",
                source_refs=source_refs,
            )
        if not _host_database_completed(database):
            return _result(
                fact,
                "unverifiable",
                reason_code="runtime_database_evidence_not_run",
                source_refs=source_refs,
            )
        delta = database.get("oo_content_revision_delta") or {}
        passed = bool(
            isinstance(delta, Mapping)
            and delta.get("observed") is False
            and delta.get("used_as_correctness_basis") is False
        )
        return _result(
            fact,
            "pass" if passed else "fail",
            reason_code=None if passed else "secondary_revision_domain_observed_or_unresolved",
            source_refs=source_refs,
        )

    if fact == "server_computed_capability":
        if entry.get("capability_literal_true") is True:
            result, reason = "fail", "literal_bidirectional_capability"
        elif (
            entry.get("server_computed_call_present") is True
            and _host_positive_capture(network)
        ):
            # 正例：源码证明现算调用 + 同 run 真实 network capture（非静态字面量）。
            result, reason = "pass", None
        elif entry.get("server_computed_call_present") is True:
            result, reason = "unverifiable", "runtime_capability_capture_required"
        else:
            result, reason = "fail", "server_computed_capability_not_proven"
        return _result(fact, result, reason_code=reason, source_refs=source_refs)

    raise ProgramMilestoneError(f"unhandled host-path fact: {fact}")


def derive_host_path_entry_state(
    facts: Iterable[Mapping[str, Any]], entry: Mapping[str, Any]
) -> str:
    by_fact = {str(item.get("fact") or item.get("id")): str(item["result"]) for item in facts}
    if set(by_fact) != set(_HOST_PATH_FACTS):
        raise ProgramMilestoneError("host-path entry state requires all eight facts exactly once")
    if "stale" in by_fact.values():
        return "STALE"
    if _host_network_observations(entry)["legacy"]:
        return "REQUEST_PATH_LEGACY"
    if all(result == "pass" for result in by_fact.values()):
        return "ONLYOFFICE_VERIFIED"
    path_and_policy = {
        "user_sync_prefix_request",
        "no_legacy_bypass",
        "callback_url_bound",
        "no_secondary_revision_domain",
        "server_computed_capability",
    }
    runtime = {"application_applied", "operation_terminal_bound", "onlyoffice_content_version"}
    if (
        all(by_fact[fact] == "pass" for fact in path_and_policy)
        and all(by_fact[fact] in {"pass", "unverifiable"} for fact in runtime)
        and any(by_fact[fact] == "unverifiable" for fact in runtime)
    ):
        return "REQUEST_PATH_VERIFIED"
    return "BLOCKED"


def build_host_path_entry_projection(
    milestone: Mapping[str, Any], context: Mapping[str, Any]
) -> dict[str, Any]:
    per_entry: list[dict[str, Any]] = []
    aggregate_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    predicate_by_fact = {str(item["fact"]): item for item in milestone["predicates"]}
    for entry_id in context["denominator"]:
        entry = context["entries"][entry_id]
        facts: list[dict[str, Any]] = []
        for fact in _HOST_PATH_FACTS:
            result = evaluate_host_path_entry_fact(entry, fact)
            result["id"] = str(predicate_by_fact[fact]["id"])
            result["fact"] = fact
            facts.append(result)
            aggregate_rows[fact].append(result)
        state = derive_host_path_entry_state(facts, entry)
        per_entry.append(
            {
                "entry_id": entry_id,
                "identity": copy.deepcopy(entry["identity"]),
                "manifest": copy.deepcopy(entry["manifest"]),
                "state": state,
                "facts": facts,
                "blockers": _milestone_blockers(facts),
                "evidence_refs": sorted(
                    {
                        ref["path"]
                        for fact in facts
                        for ref in fact.get("source_refs") or []
                        if "/evidence/" in ref["path"]
                    }
                ),
            }
        )

    severity = {"pass": 0, "unverifiable": 1, "blocked": 2, "fail": 3, "stale": 4}
    aggregate_predicates: list[dict[str, Any]] = []
    for fact in _HOST_PATH_FACTS:
        rows = aggregate_rows[fact]
        aggregate_result = max((row["result"] for row in rows), key=lambda item: severity[item])
        source_refs = sorted(
            {
                (ref["path"], ref["sha256"])
                for row in rows
                for ref in row.get("source_refs") or []
            }
        )
        aggregate_predicates.append(
            _result(
                str(predicate_by_fact[fact]["id"]),
                aggregate_result,
                reason_code=None
                if aggregate_result == "pass"
                else "host_path_entry_fact_not_universally_passing",
                source_refs=[_source_ref(path, digest) for path, digest in source_refs],
                details={
                    "fact": fact,
                    "entries": [
                        {
                            "entry_id": entry_id,
                            "result": row["result"],
                            "reason_code": row.get("reason_code"),
                        }
                        for entry_id, row in zip(context["denominator"], rows)
                    ],
                },
            )
        )

    counts = Counter(item["state"] for item in per_entry)
    return {
        "state_policy": _HOST_PATH_STATE_POLICY,
        "entry_denominator": list(context["denominator"]),
        "entries": per_entry,
        "entry_state_counts": {state: counts[state] for state in _HOST_PATH_ENTRY_STATES},
        "machine_predicates": aggregate_predicates,
    }


def _result(
    predicate_id: str,
    result: str,
    *,
    reason_code: str | None = None,
    source_refs: list[dict[str, str]] | None = None,
    details: dict[str, Any] | None = None,
    grants_state: str | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    if result not in _ALLOWED_RESULTS:
        raise ProgramMilestoneError(f"invalid predicate result {result!r}")
    value: dict[str, Any] = {
        "id": predicate_id,
        "result": result,
        "reason_code": reason_code,
        "source_refs": source_refs or [],
    }
    if details:
        value["details"] = details
    if grants_state is not None:
        value["grants_state"] = grants_state
    if observed_at is not None:
        value["observed_at"] = observed_at
    return value


def evaluate_task_predicate(
    milestone: Mapping[str, Any], spec_facts: Mapping[str, Any]
) -> dict[str, Any]:
    pending: list[dict[str, str]] = []
    source_refs: dict[str, str] = {}
    producer_count = 0
    for producer in milestone["producers"]:
        spec = producer["spec"]
        source_refs[spec_facts[spec]["path"]] = spec_facts[spec]["source_digest"]
        for task in producer["tasks"]:
            producer_count += 1
            state = spec_facts[spec]["task_states"][task]
            if state != "x":
                pending.append({"spec": spec, "task": task, "state": state})
    if producer_count == 0:
        return _result(
            "producer-tasks",
            "blocked",
            reason_code="producer_tasks_missing",
            source_refs=[_source_ref(path, digest) for path, digest in sorted(source_refs.items())],
        )
    return _result(
        "producer-tasks",
        "pass" if not pending else "blocked",
        reason_code=None if not pending else "producer_tasks_incomplete",
        source_refs=[_source_ref(path, digest) for path, digest in sorted(source_refs.items())],
        details={"producer_task_count": producer_count, "incomplete": pending},
    )


def _resolve_evidence_artifact(raw_path: str, producer_spec: str | None) -> Path | None:
    normalized = raw_path.replace("\\", "/").lstrip("./")
    roots = [_REPO]
    if producer_spec:
        roots.append(_SPECS_ROOT / producer_spec)
    roots.append(_REPO / "audit-platform" / "frontend" / "src")
    candidates: list[Path] = []
    for root in roots:
        candidate = (root / normalized).resolve()
        try:
            candidate.relative_to(_REPO.resolve())
        except ValueError:
            continue
        if candidate.is_file() and candidate not in candidates:
            candidates.append(candidate)
    return candidates[0] if len(candidates) == 1 else None


def _evidence_identity(document: Mapping[str, Any]) -> str | None:
    subject = document.get("subject")
    if isinstance(subject, dict) and isinstance(subject.get("contractId"), str):
        return subject["contractId"]
    for key in ("milestone", "contractId", "contract_id"):
        if isinstance(document.get(key), str):
            return str(document[key])
    return None


def _evidence_producer(document: Mapping[str, Any]) -> tuple[str | None, str | None]:
    spec = document.get("producerSpec") or document.get("producer_spec") or document.get("spec")
    task = document.get("producerTask") or document.get("producer_task") or document.get("task")
    normalized_task: str | None = None
    if task is not None:
        try:
            normalized_task = _task_id(task, source="evidence producer")
        except ProgramMilestoneError:
            normalized_task = None
    return (str(spec) if isinstance(spec, str) else None, normalized_task)


def _evidence_consumers(document: Mapping[str, Any]) -> set[tuple[str, str]]:
    consumers = document.get("consumers")
    if not isinstance(consumers, list):
        return set()
    parsed: set[tuple[str, str]] = set()
    for value in consumers:
        if isinstance(value, str):
            item = _normalize_consumer_ref(value)
            if item:
                parsed.add(item)
    return parsed


def evaluate_evidence_bundle(
    milestone: Mapping[str, Any],
    predicate: Mapping[str, Any],
    inputs: dict[str, str],
) -> dict[str, Any]:
    paths = predicate.get("paths")
    if not isinstance(paths, list) or not paths:
        raise ProgramMilestoneError(f"{milestone['id']}/{predicate['id']}: evidence paths missing")
    documents: list[tuple[Path, dict[str, Any]]] = []
    source_refs: list[dict[str, str]] = []
    for raw_path in paths:
        path = _REPO / str(raw_path)
        digest = _record_input(inputs, path)
        source_refs.append(_source_ref(_relative(path), digest))
        documents.append((path, _read_json(path)))

    stale_reasons: list[str] = []
    verdict_results: list[str] = []
    observed: list[str] = []
    producer_specs = {producer["spec"] for producer in milestone["producers"]}
    producer_pairs = {
        (producer["spec"], task)
        for producer in milestone["producers"]
        for task in producer["tasks"]
    }
    expected_consumers = {
        (consumer["spec"], task)
        for consumer in milestone["consumers"]
        for task in consumer["tasks"]
    }
    artifact_rows = 0
    valid_artifact_rows = 0

    for evidence_path, document in documents:
        identity = _evidence_identity(document)
        if identity != milestone["id"]:
            stale_reasons.append(f"milestone_identity_mismatch:{_relative(evidence_path)}")
        raw_verdict = str(document.get("verdict") or "").upper()
        if raw_verdict in {"PASS", "VERIFIED", "CLOSED"}:
            verdict_results.append("pass")
        elif raw_verdict in {"PARTIAL", "BLOCKED"}:
            verdict_results.append("blocked")
        elif raw_verdict == "STALE":
            verdict_results.append("stale")
        elif raw_verdict == "UNVERIFIABLE":
            verdict_results.append("unverifiable")
        else:
            verdict_results.append("fail")
        timestamp = document.get("recordedAt") or document.get("recorded_at") or document.get("observed_at")
        if isinstance(timestamp, str) and timestamp:
            observed.append(timestamp)

        producer = _evidence_producer(document)
        if predicate.get("require_producer_binding"):
            if producer[0] is None or producer[1] is None:
                stale_reasons.append(f"producer_binding_missing:{_relative(evidence_path)}")
            elif producer not in producer_pairs:
                stale_reasons.append(
                    f"producer_binding_mismatch:{producer[0]}:{producer[1]}"
                )
            elif producer[0] not in producer_specs:
                stale_reasons.append(f"producer_spec_mismatch:{producer[0]}")

        if predicate.get("require_consumer_binding"):
            consumers = _evidence_consumers(document)
            if not consumers:
                stale_reasons.append(f"consumer_binding_missing:{_relative(evidence_path)}")
            elif consumers != expected_consumers:
                stale_reasons.append("consumer_binding_mismatch")

        source_digests = document.get("sourceDigests") or document.get("source_digests")
        if source_digests is not None:
            if not isinstance(source_digests, dict):
                stale_reasons.append(f"source_digests_not_object:{_relative(evidence_path)}")
            else:
                for key, digest in source_digests.items():
                    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
                        stale_reasons.append(f"invalid_source_digest:{key}")

        artifacts = document.get("artifacts")
        if artifacts is not None and not isinstance(artifacts, list):
            stale_reasons.append(f"artifacts_not_array:{_relative(evidence_path)}")
            artifacts = []
        for artifact in artifacts or []:
            artifact_rows += 1
            if not isinstance(artifact, dict):
                stale_reasons.append("artifact_not_object")
                continue
            raw_artifact_path = artifact.get("path") or artifact.get("uri")
            digest = artifact.get("digest") or artifact.get("sha256")
            if not isinstance(raw_artifact_path, str) or not isinstance(digest, str):
                stale_reasons.append("artifact_path_or_digest_missing")
                continue
            if not _SHA256_RE.fullmatch(digest):
                stale_reasons.append(f"artifact_digest_invalid:{raw_artifact_path}")
                continue
            producer_spec = next(iter(producer_specs)) if len(producer_specs) == 1 else None
            resolved = _resolve_evidence_artifact(raw_artifact_path, producer_spec)
            if resolved is None:
                stale_reasons.append(f"artifact_path_unresolved:{raw_artifact_path}")
                continue
            actual = _record_input(inputs, resolved)
            source_refs.append(_source_ref(_relative(resolved), actual))
            if actual != digest:
                stale_reasons.append(f"artifact_digest_mismatch:{raw_artifact_path}")
                continue
            valid_artifact_rows += 1

    if predicate.get("require_artifact_digests") and (
        artifact_rows == 0 or valid_artifact_rows != artifact_rows
    ):
        stale_reasons.append("artifact_digest_coverage_incomplete")

    if stale_reasons or "stale" in verdict_results:
        result = "stale"
        reason = "evidence_stale_or_incomplete"
    elif "fail" in verdict_results:
        result = "fail"
        reason = "evidence_failed"
    elif "blocked" in verdict_results:
        result = "blocked"
        reason = "evidence_partial_or_blocked"
    elif "unverifiable" in verdict_results:
        result = "unverifiable"
        reason = "evidence_unverifiable"
    else:
        result = "pass"
        reason = None
    return _result(
        str(predicate["id"]),
        result,
        reason_code=reason,
        source_refs=sorted(source_refs, key=lambda item: item["path"]),
        details={
            "evidence_files": [_relative(path) for path, _ in documents],
            "artifact_rows": artifact_rows,
            "valid_artifact_rows": valid_artifact_rows,
            "stale_reasons": sorted(set(stale_reasons)),
        },
        grants_state=str(predicate["grants_state"]) if result == "pass" else None,
        observed_at=max(observed) if observed else None,
    )


def evaluate_predicate(
    milestone: Mapping[str, Any],
    predicate: Mapping[str, Any],
    *,
    inputs: dict[str, str],
    manifest_facts: Mapping[str, Any],
    writer_facts: Mapping[str, Any],
    database_facts: Mapping[str, Any],
    symbol_cache: dict[str, set[str]],
    host_path_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    predicate_type = predicate["type"]
    predicate_id = str(predicate["id"])
    if predicate_type == "manifest_integrity":
        source_refs = [_source_ref(_relative(_MANIFEST_PATH), inputs[_relative(_MANIFEST_PATH)])]
        structurally_valid = bool(
            manifest_facts["self_consistent"] and manifest_facts["profile_consistent"]
        )
        if not structurally_valid:
            return _result(
                predicate_id,
                "fail",
                reason_code="manifest_digest_or_profile_invalid",
                source_refs=source_refs,
                details=dict(manifest_facts),
            )
        if not manifest_facts["source_current"]:
            return _result(
                predicate_id,
                "stale",
                reason_code=str(manifest_facts["source_reason"]),
                source_refs=source_refs,
                details=dict(manifest_facts),
            )
        return _result(predicate_id, "pass", source_refs=source_refs, details=dict(manifest_facts))

    if predicate_type == "writer_gate_issue_zero":
        issue = predicate.get("issue")
        counts = writer_facts["issue_counts"]
        if issue not in counts:
            raise ProgramMilestoneError(f"{milestone['id']}/{predicate_id}: unknown writer issue {issue!r}")
        source_refs = [
            _source_ref(_relative(_WRITER_INVENTORY_PATH), inputs[_relative(_WRITER_INVENTORY_PATH)])
        ]
        details = {
            "issue": issue,
            "count": counts[issue],
            "sample": writer_facts["issue_samples"].get(issue, []),
            "inventory_digest": writer_facts["inventory_digest"],
        }
        if not writer_facts["source_current"]:
            return _result(
                predicate_id,
                "stale",
                reason_code=str(writer_facts["source_reason"]),
                source_refs=source_refs,
                details=details,
            )
        return _result(
            predicate_id,
            "pass" if counts[issue] == 0 else "blocked",
            reason_code=None if counts[issue] == 0 else f"writer_gate_{issue}_nonzero",
            source_refs=source_refs,
            details=details,
        )

    if predicate_type == "python_symbols":
        missing: list[str] = []
        source_refs: list[dict[str, str]] = []
        for requirement in predicate.get("required_symbols") or []:
            path = _REPO / requirement["path"]
            digest = _record_input(inputs, path)
            source_refs.append(_source_ref(_relative(path), digest))
            symbols = symbol_cache.setdefault(_relative(path), _python_symbols(path))
            missing.extend(
                f"{_relative(path)}::{symbol}"
                for symbol in requirement.get("symbols") or []
                if symbol not in symbols
            )
        return _result(
            predicate_id,
            "pass" if not missing else "fail",
            reason_code=None if not missing else "production_symbols_missing",
            source_refs=source_refs,
            details={"missing": sorted(missing)},
        )

    if predicate_type == "database_readonly_schema":
        probe_id = predicate.get("probe_id")
        probe = database_facts["probes"].get(probe_id)
        if probe is None:
            raise ProgramMilestoneError(
                f"{milestone['id']}/{predicate_id}: database probe {probe_id!r} is absent"
            )
        details = {
            "probe_id": probe_id,
            "probe_digest": database_facts["probe_digest"],
            "query_set_digest": database_facts["query_set_digest"],
            "read_only_verified": database_facts["read_only_verified"],
            **copy.deepcopy(probe),
        }
        if database_facts["status"] == "database_unavailable":
            return _result(
                predicate_id,
                "blocked",
                reason_code="database_unavailable",
                details=details,
            )
        if database_facts["status"] != "ok" or not database_facts["read_only_verified"]:
            return _result(
                predicate_id,
                "fail",
                reason_code="database_query_or_read_only_verification_failed",
                details=details,
            )
        return _result(
            predicate_id,
            "pass" if probe["result"] == "pass" else "fail",
            reason_code=None
            if probe["result"] == "pass"
            else "database_schema_requirements_missing",
            details=details,
        )

    if predicate_type == "host_path_entry_fact":
        if milestone.get("id") != _HOST_PATH_MILESTONE_ID:
            raise ProgramMilestoneError("host_path_entry_fact is sealed to HOST-CONSUMES-UNIFIED-PATH")
        if host_path_context is None:
            raise ProgramMilestoneError("host path context is required")
        fact = str(predicate.get("fact") or "")
        rows = []
        for entry_id in host_path_context["denominator"]:
            entry = host_path_context["entries"][entry_id]
            result = evaluate_host_path_entry_fact(entry, fact)
            result["id"] = predicate_id
            result["fact"] = fact
            result["entry_id"] = entry_id
            rows.append(result)
        worst = max(rows, key=lambda item: {"pass": 0, "unverifiable": 1, "blocked": 2, "fail": 3, "stale": 4}[item["result"]])
        return _result(predicate_id, worst["result"], reason_code=worst.get("reason_code"), source_refs=worst.get("source_refs"), details={"fact": fact, "entries": rows})

    if predicate_type == "evidence_bundle":
        return evaluate_evidence_bundle(milestone, predicate, inputs)

    if predicate_type == "runtime_evidence_required":
        return _result(
            predicate_id,
            "unverifiable",
            reason_code=str(predicate.get("reason_code") or "runtime_evidence_missing"),
        )

    if predicate_type == "declared_blocker":
        return _result(
            predicate_id,
            "blocked",
            reason_code=str(predicate.get("reason_code") or "declared_blocker"),
            details={"detail": predicate.get("detail")},
        )

    raise ProgramMilestoneError(f"unsupported predicate type: {predicate_type}")


def derive_milestone_state(predicates: Iterable[Mapping[str, Any]]) -> str:
    """Derive cumulative state; a task checkbox alone can never advance past IMPLEMENTED."""
    values = list(predicates)
    results = {str(item["result"]) for item in values}
    if not results <= _ALLOWED_RESULTS:
        raise ProgramMilestoneError(f"invalid predicate results: {sorted(results - _ALLOWED_RESULTS)}")
    if "stale" in results:
        return "STALE"
    if "fail" in results or "blocked" in results:
        return "BLOCKED"

    state = "IMPLEMENTED"
    if "unverifiable" in results:
        return state
    grants = [
        str(item["grants_state"])
        for item in values
        if item.get("result") == "pass" and item.get("grants_state") in _STATE_ORDER
    ]
    if grants:
        state = max(grants, key=lambda item: _STATE_ORDER[item])
    return state


def _milestone_blockers(predicates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "predicate_id": item["id"],
            "result": item["result"],
            "reason_code": item.get("reason_code"),
        }
        for item in predicates
        if item["result"] != "pass"
    ]


def build_program_registry(
    definitions: dict[str, Any] | None = None,
    *,
    database_probe_facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    inputs: dict[str, str] = {}
    if definitions is None:
        definitions = load_definitions()
        _record_input(inputs, _DEFINITIONS_PATH)
    else:
        definitions = copy.deepcopy(definitions)
        # Validation also protects unit-test callers that inject a mutated definition object.
        temporary = definitions
        if temporary.get("schema_version") != _DEFINITION_SCHEMA:
            raise ProgramMilestoneError("injected definitions use the wrong schema")
        # Reuse the complete validator without writing a temporary file.
        milestones = temporary.get("milestones")
        if not isinstance(milestones, list):
            raise ProgramMilestoneError("injected definitions have no milestones")
        ids = [item.get("id") for item in milestones if isinstance(item, dict)]
        if len(ids) != len(milestones) or len(ids) != len(set(ids)):
            raise ProgramMilestoneError("injected milestone ids must be present and unique")
        for item in milestones:
            for predicate in item.get("predicates") or []:
                if predicate.get("type") not in _ALLOWED_PREDICATE_TYPES:
                    raise ProgramMilestoneError(
                        f"{item.get('id')}: unsupported predicate type {predicate.get('type')!r}"
                    )

    database_probe_definitions = _validate_database_probe_definitions(definitions)
    for item in definitions["milestones"]:
        for predicate in item.get("predicates") or []:
            if (
                predicate.get("type") == "database_readonly_schema"
                and predicate.get("probe_id") not in database_probe_definitions
            ):
                raise ProgramMilestoneError(
                    f"{item.get('id')}/{predicate.get('id')}: unknown database probe "
                    f"{predicate.get('probe_id')!r}"
                )

    _record_input(inputs, _MASTER_CONTROL_PATH)
    spec_facts = collect_spec_facts(definitions, inputs)
    dag, diagnostics = validate_program_dag(definitions, spec_facts)

    host_definition = next(item for item in definitions["milestones"] if item["id"] == _HOST_PATH_MILESTONE_ID)
    host_denominator = host_definition["entry_projection"]["denominator"]
    manifest_facts = collect_manifest_facts(inputs, reviewed_entry_ids=host_denominator)
    host_path_context = collect_host_path_evidence(host_definition, inputs=inputs, manifest_facts=manifest_facts)
    writer_facts = collect_writer_gate_facts(inputs)
    database_facts = (
        collect_database_probe_facts(definitions)
        if database_probe_facts is None
        else _validate_database_probe_facts(definitions, database_probe_facts)
    )
    symbol_cache: dict[str, set[str]] = {}
    milestones: list[dict[str, Any]] = []
    for milestone_definition in definitions["milestones"]:
        predicates = [evaluate_task_predicate(milestone_definition, spec_facts)]
        predicates.extend(
            evaluate_predicate(
                milestone_definition,
                predicate,
                inputs=inputs,
                manifest_facts=manifest_facts,
                writer_facts=writer_facts,
                database_facts=database_facts,
                symbol_cache=symbol_cache,
                host_path_context=host_path_context,
            )
            for predicate in milestone_definition["predicates"]
        )
        if milestone_definition["id"] == _HOST_PATH_MILESTONE_ID:
            host_projection = build_host_path_entry_projection(host_definition, host_path_context)
            host_entry_states = host_projection["entry_state_counts"]
            entry_total = sum(int(host_entry_states.get(state) or 0) for state in _HOST_PATH_ENTRY_STATES)
            if int(host_entry_states.get("STALE") or 0) > 0:
                predicates.append(
                    _result(
                        "host-entry-projection",
                        "stale",
                        reason_code="host_path_entry_evidence_stale",
                        details=host_projection,
                    )
                )
            elif (
                entry_total > 0
                and int(host_entry_states.get("ONLYOFFICE_VERIFIED") or 0) == entry_total
            ):
                predicates.append(
                    _result(
                        "host-entry-projection",
                        "pass",
                        grants_state="ONLYOFFICE_VERIFIED",
                        details=host_projection,
                    )
                )
            elif int(host_entry_states.get("REQUEST_PATH_LEGACY") or 0) > 0:
                predicates.append(
                    _result(
                        "host-entry-projection",
                        "blocked",
                        reason_code="host_path_entry_legacy_or_unverified",
                        details=host_projection,
                    )
                )
            elif (
                entry_total > 0
                and int(host_entry_states.get("REQUEST_PATH_VERIFIED") or 0) == entry_total
            ):
                predicates.append(
                    _result(
                        "host-entry-projection",
                        "pass",
                        grants_state="REQUEST_PATH_VERIFIED",
                        details=host_projection,
                    )
                )
            else:
                predicates.append(
                    _result(
                        "host-entry-projection",
                        "blocked",
                        reason_code="host_path_entry_legacy_or_unverified",
                        details=host_projection,
                    )
                )
        else:
            host_projection = None
            host_entry_states = None
        state = derive_milestone_state(predicates)
        observed = [item["observed_at"] for item in predicates if item.get("observed_at")]
        milestones.append(
            {
                "id": milestone_definition["id"],
                "scope": milestone_definition["scope"],
                "producers": copy.deepcopy(milestone_definition["producers"]),
                "consumers": copy.deepcopy(milestone_definition["consumers"]),
                "state": state,
                "machine_predicates": predicates,
                "blockers": _milestone_blockers(predicates),
                "evidence_refs": sorted(
                    {
                        ref["path"]
                        for predicate in predicates
                        for ref in predicate.get("source_refs") or []
                        if "/evidence/" in ref["path"] or ref["path"].startswith("backend/data/guidance/")
                    }
                ),
                "observed_at": max(observed) if observed else None,
                **({"entry_projection": host_projection, "entry_state_counts": host_entry_states} if host_projection is not None else {}),
            }
        )

    diagnostics = sorted(
        diagnostics,
        key=lambda item: (
            item.get("code", ""),
            item.get("milestone", ""),
            item.get("spec", ""),
            item.get("consumer_spec", ""),
        ),
    )
    state_counts = Counter(item["state"] for item in milestones)
    task_counts = Counter(
        state
        for facts in spec_facts.values()
        for state in facts["task_states"].values()
    )
    if state_counts["STALE"]:
        program_state = "STALE"
    elif state_counts["BLOCKED"] or any(item["severity"] == "blocker" for item in diagnostics):
        program_state = "BLOCKED"
    elif state_counts["CLOSED"] == len(milestones):
        program_state = "CLOSED"
    else:
        program_state = "IMPLEMENTED"

    definition_digest = _sha256_bytes(_stable_json(definitions).encode("utf-8"))
    database_probe_digest = str(database_facts["probe_digest"])
    source_digest = _sha256_bytes(
        _stable_json(
            {
                "file_inputs": dict(sorted(inputs.items())),
                "database_probe_digest": database_probe_digest,
            }
        ).encode("utf-8")
    )
    registry: dict[str, Any] = {
        "schema_version": _OUTPUT_SCHEMA,
        "program_id": definitions["program_id"],
        "program_state": program_state,
        "generated_at": None,
        "source_commit": None,
        "source_state": "digest_bound_without_common_commit",
        "definition_digest": definition_digest,
        "source_digest": source_digest,
        "manifest_digest": manifest_facts["manifest_digest"],
        "work_package": copy.deepcopy(definitions["work_package"]),
        "inputs": dict(sorted(inputs.items())),
        "specs": {
            spec: {
                "path": facts["path"],
                "source_digest": facts["source_digest"],
                "task_count": facts["task_count"],
                "state_counts": facts["state_counts"],
                "task_states": facts["task_states"],
                "dependencies": facts["graph"]["dependencies"],
            }
            for spec, facts in sorted(spec_facts.items())
        },
        "dag": dag,
        "manifest_facts": manifest_facts,
        "writer_gate_facts": writer_facts,
        "database_probe_digest": database_probe_digest,
        "database_probe_facts": database_facts,
        "milestones": sorted(milestones, key=lambda item: item["id"]),
        "diagnostics": diagnostics,
        "stats": {
            "spec_count": len(spec_facts),
            "task_count": sum(facts["task_count"] for facts in spec_facts.values()),
            "task_state_counts": {
                "completed": task_counts["x"],
                "partial": task_counts["~"],
                "blocked": task_counts["-"],
                "pending": task_counts[" "],
            },
            "milestone_count": len(milestones),
            "milestone_state_counts": {
                state: state_counts[state]
                for state in ["BLOCKED", "IMPLEMENTED", "REQUEST_PATH_VERIFIED", "ONLYOFFICE_VERIFIED", "CLOSED", "STALE"]
            },
            "diagnostic_count": len(diagnostics),
            "blocking_diagnostic_count": sum(item["severity"] == "blocker" for item in diagnostics),
        },
    }
    registry["program_digest"] = recompute_program_digest(registry)
    _assert_inputs_unchanged(inputs)
    return registry


def recompute_program_digest(registry: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(registry))
    payload.pop("program_digest", None)
    return _sha256_bytes(_stable_json(payload).encode("utf-8"))


def render_registry(registry: Mapping[str, Any]) -> str:
    return json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
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


def _print_summary(registry: Mapping[str, Any], label: str) -> None:
    stats = registry["stats"]
    print(
        f"[{label}] program={registry['program_state']} specs={stats['spec_count']} "
        f"tasks={stats['task_count']} milestones={stats['milestone_count']} "
        f"states={stats['milestone_state_counts']} diagnostics={stats['diagnostic_count']}"
    )
    print(f"[{label}] digest={registry['program_digest']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify the generated projection")
    mode.add_argument("--apply", action="store_true", help="atomically regenerate the projection")
    args = parser.parse_args(argv)

    registry = build_program_registry()
    content = render_registry(registry)
    _print_summary(registry, "SOURCE")
    database_facts = registry["database_probe_facts"]
    if database_facts["status"] != "ok" or not database_facts["read_only_verified"]:
        failure = database_facts.get("failure") or {}
        print(
            "[FAIL] mandatory database probe did not complete read-only: "
            f"status={database_facts['status']} phase={failure.get('phase')} "
            f"code={failure.get('code')}"
        )
        return 2
    if args.check:
        if not _TARGET_PATH.is_file():
            print(f"[FAIL] missing: {_relative(_TARGET_PATH)}")
            return 2
        if _TARGET_PATH.read_text(encoding="utf-8") != content:
            print(f"[FAIL] stale: {_relative(_TARGET_PATH)}")
            return 2
        on_disk = _read_json(_TARGET_PATH)
        if on_disk.get("program_digest") != recompute_program_digest(on_disk):
            print("[FAIL] on-disk program_digest is not self-consistent")
            return 2
        _print_summary(registry, "CHECKED")
        return 0

    _atomic_write(_TARGET_PATH, content)
    print(f"[APPLIED] {_relative(_TARGET_PATH)} sha256={_sha256_bytes(content.encode('utf-8'))[:16]}")
    _print_summary(registry, "GENERATED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProgramMilestoneError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
