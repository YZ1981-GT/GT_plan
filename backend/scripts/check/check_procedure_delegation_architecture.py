#!/usr/bin/env python
"""Procedure delegation architecture debt guard (stdlib only).

The guard fingerprints structured Python AST nodes and normalized Vue/TypeScript
blocks. Existing debt must match the baseline exactly; new, stale, duplicated, or
changed debt fails in ``--strict`` mode.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASELINE = REPO_ROOT / "backend/scripts/check/baselines/procedure_delegation_debt.json"
# Task 2 landed the feature migration. V105 is now the canonical, allowed migration; the
# guard only rejects *non-canonical* V105 variants (duplicate / wrong-name). Current head
# advances to 105.
CANONICAL_V105_FILENAME = "V105__procedure_row_tasks.sql"
NEXT_MIGRATION_FILENAME = CANONICAL_V105_FILENAME
CURRENT_MIGRATION_VERSION = 105

RULE_INSTANCE_ID_AS_ROW_TASK = "procedure-instance-id-as-row-task"
RULE_GET_RENDER_DOMAIN_WRITE = "get-render-procedure-domain-write"
RULE_PARSED_DATA_RMW = "parsed-data-procedure-state-rmw"
RULE_STATE_BYPASS = "procedure-state-transition-bypass"
RULE_PARALLEL_TASK_PAGE = "parallel-my-procedure-tasks-page-route"
RULE_FORBIDDEN_V105 = "forbidden-v105-migration"
BASELINE_RULES = frozenset({
    RULE_INSTANCE_ID_AS_ROW_TASK,
    RULE_GET_RENDER_DOMAIN_WRITE,
    RULE_PARSED_DATA_RMW,
    RULE_STATE_BYPASS,
    RULE_PARALLEL_TASK_PAGE,
})
ALL_RULES = BASELINE_RULES | {RULE_FORBIDDEN_V105}


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    symbol: str
    rule: str
    fingerprint: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.path, self.symbol, self.rule)


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ast_fingerprint(node: ast.AST) -> str:
    return _sha256(ast.dump(node, annotate_fields=True, include_attributes=False))


def _normalized_fingerprint(text: str) -> str:
    # Comments and insignificant whitespace do not make frontend debt drift.
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(^|\s)//[^\r\n]*", r"\1", text)
    return _sha256(re.sub(r"\s+", " ", text).strip())


def normalize_repo_path(path: str | Path, root: str | Path | None = None) -> str:
    """Return a slash-normalized repository-relative path, including Windows input."""
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


def _qualname(stack: Sequence[str], name: str) -> str:
    return ".".join([*stack, name])


def _decorator_method(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    for dec in node.decorator_list:
        call = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(call, ast.Attribute) and call.attr.lower() in {
            "get", "post", "put", "patch", "delete"
        }:
            return call.attr.lower()
    return None


def _is_transition_service(path: str, stack: Sequence[str]) -> bool:
    return (
        path == "backend/app/services/procedure_task_transition_service.py"
        and "ProcedureTaskTransitionService" in stack
    )


def _string_literals(node: ast.AST) -> set[str]:
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)
    }


def _has_assignment_to_attr(node: ast.AST, attrs: set[str]) -> bool:
    for item in ast.walk(node):
        targets: list[ast.AST] = []
        if isinstance(item, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            if isinstance(item, ast.Assign):
                targets.extend(item.targets)
            else:
                targets.append(item.target)
        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr in attrs:
                return True
    return False


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts = [func.attr]
        value = func.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return ""


_ROW_TASK_STATE_ATTRS = {"workflow_status", "applicability_status"}
_PROCEDURE_MUTATION_METHODS = {
    "materialize",
    "bind_working_paper",
    "rebuild",
    "trim",
    "revert",
    "save_trim",
    "update_procedure_status",
    "transition",
    "assign",
    "reassign",
    "ack",
    "acknowledge",
    "start",
    "submit",
    "request_changes",
    "review",
    "cancel",
    "reopen",
}
_DISTINCTIVE_PROCEDURE_MUTATIONS = {
    "bind_working_paper",
    "save_trim",
    "update_procedure_status",
}
_PROCEDURE_CALL_MARKERS = (
    "procedure",
    "row_task",
    "rowtask",
    "task_transition",
    "tasktransition",
    "task_materialization",
    "taskmaterialization",
    "trim_engine",
)


def _updates_model_state(node: ast.AST, model: str, attrs: set[str]) -> bool:
    """Detect SQLAlchemy ``update(Model).values(...)`` for selected state fields."""
    has_model_update = any(
        isinstance(call, ast.Call)
        and _call_name(call).split(".")[-1] == "update"
        and any(model in _names(arg) for arg in call.args)
        for call in ast.walk(node)
    )
    if not has_model_update:
        return False
    return any(
        isinstance(call, ast.Call)
        and _call_name(call).split(".")[-1] == "values"
        and (
            any(kw.arg in attrs for kw in call.keywords)
            or bool(_names(call).intersection(attrs))
        )
        for call in ast.walk(node)
    )


def _is_pi_state_update(node: ast.AST) -> bool:
    """Detect SQLAlchemy ProcedureInstance state updates and direct field writes."""
    names = _names(node)
    if "ProcedureInstance" not in names:
        return False
    return _has_assignment_to_attr(node, {"status", "execution_status"}) or _updates_model_state(
        node, "ProcedureInstance", {"status", "execution_status"}
    )


def _is_row_task_state_update(node: ast.AST) -> bool:
    """Detect future ProcedureRowTask workflow/applicability writes before V105 lands."""
    names = _names(node)
    if _updates_model_state(node, "ProcedureRowTask", _ROW_TASK_STATE_ATTRS):
        return True
    if not _has_assignment_to_attr(node, _ROW_TASK_STATE_ATTRS):
        return False
    if "ProcedureRowTask" in names:
        return True
    for item in ast.walk(node):
        targets: list[ast.AST] = []
        if isinstance(item, ast.Assign):
            targets.extend(item.targets)
        elif isinstance(item, (ast.AnnAssign, ast.AugAssign)):
            targets.append(item.target)
        for target in targets:
            if not isinstance(target, ast.Attribute) or target.attr not in _ROW_TASK_STATE_ATTRS:
                continue
            owners = {name.casefold() for name in _names(target.value)}
            if owners.intersection({"task", "row_task", "procedure_task"}) or any(
                "procedure" in owner and "task" in owner for owner in owners
            ):
                return True
    return False


def _is_procedure_state_update(node: ast.AST) -> bool:
    return _is_pi_state_update(node) or _is_row_task_state_update(node)


def _has_procedure_mutation_service_call(node: ast.AST) -> bool:
    """Detect calls into known procedure-domain command services from read paths."""
    node_context = " ".join(sorted(_names(node))).casefold()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        full_name = _call_name(item).casefold()
        leaf = full_name.split(".")[-1]
        if leaf not in _PROCEDURE_MUTATION_METHODS:
            continue
        if leaf in _DISTINCTIVE_PROCEDURE_MUTATIONS:
            return True
        call_context = f"{full_name} {node_context}"
        if any(marker in call_context for marker in _PROCEDURE_CALL_MARKERS):
            return True
    return False


def _has_parsed_state_rmw(node: ast.AST) -> bool:
    literals = _string_literals(node)
    if not literals.intersection({"procedure_status", "trimming_metadata"}):
        return False
    return _has_assignment_to_attr(node, {"parsed_data"})


def _is_domain_write(node: ast.AST) -> bool:
    names = _names(node)
    literals = _string_literals(node)
    if _has_assignment_to_attr(node, {"parsed_data"}):
        return True
    if _is_procedure_state_update(node) or _has_procedure_mutation_service_call(node):
        return True
    for item in ast.walk(node):
        if isinstance(item, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)):
            dump = ast.dump(item, include_attributes=False)
            if any(term in dump for term in ("procedure_status", "trimming_metadata", "task_events")):
                return True
        if not isinstance(item, ast.Call):
            continue
        call_name = _call_name(item).split(".")[-1]
        call_dump = ast.dump(item, include_attributes=False)
        if call_name in {"update", "insert", "delete"} and any(
            term in call_dump for term in ("ProcedureInstance", "ProcedureRowTask", "TaskEvent", "task_events")
        ):
            return True
        if call_name == "execute" and any(
            re.search(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:procedure_instances|procedure_row_tasks|task_events)\b", literal, re.I)
            or (
                re.search(r"\bUPDATE\s+working_papers\b", literal, re.I)
                and "parsed_data" in literal.lower()
            )
            for literal in literals
        ):
            return True
        if call_name == "publish" and "task_event_bus" in names:
            return True
        if call_name == "add" and names.intersection({"ProcedureInstance", "ProcedureRowTask", "TaskEvent"}):
            return True
    return False


def _uses_instance_as_task(node: ast.AST) -> bool:
    name = getattr(node, "name", "").lower()
    names = _names(node)
    literals = _string_literals(node)
    if "ProcedureInstance" not in names:
        return False
    for item in ast.walk(node):
        if isinstance(item, ast.Dict):
            for key, value in zip(item.keys, item.values):
                if isinstance(key, ast.Constant) and key.value in {"task_id", "row_task_id"}:
                    if isinstance(value, ast.Attribute) and value.attr == "id":
                        return True
    if "task" in name:
        exposes_instance = any(
            (isinstance(item, ast.Attribute) and item.attr == "id")
            or (isinstance(item, ast.Call) and _call_name(item).split(".")[-1] == "_to_dict")
            for item in ast.walk(node)
        )
        if exposes_instance:
            return True
    return bool(literals.intersection({"task_id", "row_task_id"}) and "id" in names)


def scan_python_file(path: Path, root: Path) -> list[Finding]:
    rel = normalize_repo_path(path, root)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    findings: list[Finding] = []

    def visit(body: Iterable[ast.stmt], stack: list[str]) -> None:
        for item in body:
            if isinstance(item, ast.ClassDef):
                visit(item.body, [*stack, item.name])
                continue
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            symbol = _qualname(stack, item.name)
            allowed = _is_transition_service(rel, stack)
            if _uses_instance_as_task(item):
                findings.append(Finding(rel, symbol, RULE_INSTANCE_ID_AS_ROW_TASK, _ast_fingerprint(item)))
            method = _decorator_method(item)
            is_get_render = method == "get" or item.name == "render" or item.name.startswith("render_")
            if is_get_render and _is_domain_write(item):
                findings.append(Finding(rel, symbol, RULE_GET_RENDER_DOMAIN_WRITE, _ast_fingerprint(item)))
            parsed_rmw = _has_parsed_state_rmw(item)
            state_update = _is_procedure_state_update(item)
            if parsed_rmw and not allowed:
                findings.append(Finding(rel, symbol, RULE_PARSED_DATA_RMW, _ast_fingerprint(item)))
            if (state_update or parsed_rmw) and not allowed:
                findings.append(Finding(rel, symbol, RULE_STATE_BYPASS, _ast_fingerprint(item)))
            visit(item.body, [*stack, item.name])

    visit(tree.body, [])
    return findings


def _find_matching_brace(text: str, open_at: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    i = open_at
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if line_comment:
            if ch in "\r\n":
                line_comment = False
        elif block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 1
        elif quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
        elif ch == "/" and nxt == "/":
            line_comment = True
            i += 1
        elif ch == "/" and nxt == "*":
            block_comment = True
            i += 1
        elif ch in "'\"`":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(text) - 1


_TS_FUNCTION = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*\([^)]*\)[^{]*\{"
)
_TS_ARROW = re.compile(
    r"(?:export\s+)?const\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?"
    r"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{"
)


def _ts_function_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = sorted([*_TS_FUNCTION.finditer(text), *_TS_ARROW.finditer(text)], key=lambda m: m.start())
    for match in matches:
        open_at = text.find("{", match.start(), match.end())
        end = _find_matching_brace(text, open_at)
        yield match.group("name"), text[match.start() : end + 1]


def _scan_ts_instance_task(rel: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for symbol, block in _ts_function_blocks(text):
        lower = symbol.lower()
        structured_alias = bool(re.search(
            r"\b(?:task_id|taskId|row_task_id|rowTaskId|id)\s*:\s*(?:row|p|proc|procedure)\.id\b",
            block,
        ))
        aggregates_instances = "task" in lower and "getProcedures(" in block
        trim_as_task = (
            rel == "audit-platform/frontend/src/views/MyProcedureTasks.vue"
            and "updateProcedureTrim(" in block
            and structured_alias
        )
        if (structured_alias and ("task" in lower or trim_as_task)) or aggregates_instances:
            findings.append(Finding(rel, symbol, RULE_INSTANCE_ID_AS_ROW_TASK, _normalized_fingerprint(block)))
    return findings


def _route_objects(text: str) -> Iterable[str]:
    for match in re.finditer(r"\{\s*path\s*:\s*['\"]", text):
        end = _find_matching_brace(text, match.start())
        yield text[match.start() : end + 1]


def _scan_parallel_task_surface(rel: str, path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    if path.suffix.lower() == ".vue":
        looks_task_page = bool(
            re.search(r"ProcedureTasks?|程序任务|我的审计程序|getMyProcedureTasks", text, re.I)
        )
        canonical = rel == "audit-platform/frontend/src/views/MyProcedureTasks.vue"
        if looks_task_page and not canonical:
            findings.append(Finding(
                rel, f"component:{path.stem}", RULE_PARALLEL_TASK_PAGE,
                _normalized_fingerprint(text),
            ))
    if path.suffix.lower() == ".ts":
        canonical_seen = 0
        for block in _route_objects(text):
            candidate = block.split("children:", 1)[0]
            procedure_route = bool(re.search(
                r"MyProcedureTasks|my[-_/]procedures?|ProcedureTask", candidate, re.I
            ))
            if not procedure_route:
                continue
            canonical = bool(
                rel == "audit-platform/frontend/src/router/index.ts"
                and re.search(r"path\s*:\s*['\"]my-procedures['\"]", candidate)
                and re.search(r"name\s*:\s*['\"]MyProcedureTasks['\"]", candidate)
                and re.search(r"import\(['\"]@/views/MyProcedureTasks\.vue['\"]\)", candidate)
            )
            if canonical:
                canonical_seen += 1
            if not canonical or canonical_seen > 1:
                name = re.search(r"name\s*:\s*['\"]([^'\"]+)", block)
                symbol = f"route:{name.group(1) if name else '<anonymous>'}"
                findings.append(Finding(rel, symbol, RULE_PARALLEL_TASK_PAGE, _normalized_fingerprint(block)))
    return findings


def scan_frontend_file(path: Path, root: Path) -> list[Finding]:
    rel = normalize_repo_path(path, root)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return _scan_ts_instance_task(rel, text) + _scan_parallel_task_surface(rel, path, text)


def scan_repository(root: str | Path) -> list[Finding]:
    root_path = Path(root).resolve()
    findings: list[Finding] = []
    app_root = root_path / "backend/app"
    if app_root.is_dir():
        for path in sorted(app_root.rglob("*.py")):
            findings.extend(scan_python_file(path, root_path))
    frontend_root = root_path / "audit-platform/frontend/src"
    if frontend_root.is_dir():
        for path in sorted(frontend_root.rglob("*")):
            if path.suffix.lower() in {".ts", ".vue"}:
                findings.extend(scan_frontend_file(path, root_path))
    migrations = root_path / "backend/migrations"
    if migrations.is_dir():
        for path in sorted(migrations.rglob("*")):
            # Only *non-canonical* V105 files are forbidden now that the feature migration
            # has landed. A duplicate or misnamed V105 would be silently skipped by the
            # runner's version dedup, so it must still fail the guard.
            if (
                path.is_file()
                and re.fullmatch(r"V105__.+\.sql", path.name, re.I)
                and path.name.casefold() != CANONICAL_V105_FILENAME.casefold()
            ):
                rel = normalize_repo_path(path, root_path)
                findings.append(Finding(
                    rel,
                    f"migration:{path.name}",
                    RULE_FORBIDDEN_V105,
                    _sha256(path.read_bytes().hex()),
                ))
    return sorted(set(findings))


def _validate_baseline_document(data: object) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return [], ["baseline root must be an object"]
    unknown_top = set(data) - {"metadata", "entries"}
    missing_top = {"metadata", "entries"} - set(data)
    if unknown_top:
        errors.append(f"baseline unknown top-level fields: {sorted(unknown_top)}")
    if missing_top:
        errors.append(f"baseline missing top-level fields: {sorted(missing_top)}")

    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("baseline metadata must be an object")
        metadata = {}
    unknown_meta = set(metadata) - {"debt_ceiling"}
    missing_meta = {"debt_ceiling"} - set(metadata)
    if unknown_meta:
        errors.append(f"baseline metadata unknown fields: {sorted(unknown_meta)}")
    if missing_meta:
        errors.append("baseline metadata missing debt_ceiling")
    ceiling = metadata.get("debt_ceiling")
    if not isinstance(ceiling, int) or isinstance(ceiling, bool) or ceiling < 0:
        errors.append("baseline metadata.debt_ceiling must be a non-negative integer")

    entries = data.get("entries")
    if not isinstance(entries, list):
        return [], [*errors, "baseline entries must be an array"]
    valid: list[dict] = []
    expected = {"path", "symbol", "rule", "fingerprint", "reason"}
    seen: set[tuple[str, str, str]] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"baseline entry[{index}] must be an object")
            continue
        unknown = set(entry) - expected
        missing = expected - set(entry)
        if unknown:
            errors.append(f"baseline entry[{index}] unknown fields: {sorted(unknown)}")
        if missing:
            errors.append(f"baseline entry[{index}] missing fields: {sorted(missing)}")
            continue
        if any(not isinstance(entry[field], str) or not entry[field].strip() for field in expected):
            errors.append(f"baseline entry[{index}] fields must be non-empty strings")
            continue
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", entry["fingerprint"]):
            errors.append(f"baseline entry[{index}] fingerprint must be sha256:<64 lowercase hex>")
        if entry["rule"] not in BASELINE_RULES:
            errors.append(f"baseline entry[{index}] unknown or non-baselineable rule: {entry['rule']}")
        key = (normalize_repo_path(entry["path"]), entry["symbol"], entry["rule"])
        if key in seen:
            errors.append(f"baseline duplicate entry: {key}")
        seen.add(key)
        normalized = dict(entry)
        normalized["path"] = key[0]
        valid.append(normalized)
    if isinstance(ceiling, int) and len(valid) > ceiling:
        errors.append(f"baseline debt count {len(valid)} exceeds debt_ceiling {ceiling}")
    return valid, errors


def load_baseline(path: str | Path) -> tuple[list[dict], int, list[str]]:
    baseline_path = Path(path)
    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], 0, [f"baseline not found: {baseline_path}"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [], 0, [f"baseline unreadable: {exc}"]
    entries, errors = _validate_baseline_document(data)
    metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
    ceiling = metadata.get("debt_ceiling", 0) if isinstance(metadata, dict) else 0
    return entries, ceiling if isinstance(ceiling, int) else 0, errors


def compare_with_baseline(
    findings: Sequence[Finding], entries: Sequence[dict], debt_ceiling: int
) -> list[str]:
    errors: list[str] = []
    actual = {finding.key: finding for finding in findings if finding.rule in BASELINE_RULES}
    expected = {
        (entry["path"], entry["symbol"], entry["rule"]): entry for entry in entries
    }
    for key in sorted(expected.keys() - actual.keys()):
        errors.append(f"stale baseline entry: path={key[0]} symbol={key[1]} rule={key[2]}")
    for key in sorted(actual.keys() - expected.keys()):
        finding = actual[key]
        errors.append(
            f"new unbaselined debt: path={finding.path} symbol={finding.symbol} "
            f"rule={finding.rule} fingerprint={finding.fingerprint}"
        )
    for key in sorted(actual.keys() & expected.keys()):
        finding = actual[key]
        fingerprint = expected[key]["fingerprint"]
        if finding.fingerprint != fingerprint:
            errors.append(
                f"fingerprint drift: path={finding.path} symbol={finding.symbol} "
                f"rule={finding.rule} expected={fingerprint} actual={finding.fingerprint}"
            )
    if len(actual) > debt_ceiling:
        errors.append(f"actual debt count {len(actual)} exceeds debt_ceiling {debt_ceiling}")
    for finding in findings:
        if finding.rule == RULE_FORBIDDEN_V105:
            errors.append(
                f"non-canonical V105 migration: remove {finding.path}; the only allowed "
                f"V105 file is {CANONICAL_V105_FILENAME} (duplicate/misnamed V105 would be "
                f"silently skipped by the runner's version dedup)"
            )
    return errors


def _write_candidate(path: Path, findings: Sequence[Finding]) -> None:
    entries = [
        {**asdict(finding), "reason": "TODO: explain why this historical debt remains"}
        for finding in findings
        if finding.rule in BASELINE_RULES
    ]
    document = {"metadata": {"debt_ceiling": len(entries)}, "entries": entries}
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Procedure delegation architecture guard")
    parser.add_argument("--strict", action="store_true", help="fail on any architecture/baseline violation")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="inject repository root")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE, help="inject debt baseline JSON")
    parser.add_argument("--write-candidate", type=Path, help="write scanner findings with TODO reasons")
    args = parser.parse_args(argv)

    findings = scan_repository(args.root)
    for finding in findings:
        print(
            f"path={finding.path} symbol={finding.symbol} rule={finding.rule} "
            f"fingerprint={finding.fingerprint}"
        )
    if args.write_candidate:
        _write_candidate(args.write_candidate, findings)
        print(f"candidate baseline written: {args.write_candidate}")

    entries, ceiling, validation_errors = load_baseline(args.baseline)
    comparison_errors = compare_with_baseline(findings, entries, ceiling) if not validation_errors else []
    errors = [*validation_errors, *comparison_errors]
    print(
        f"summary findings={len(findings)} debt={sum(f.rule in BASELINE_RULES for f in findings)} "
        f"baseline={len(entries)} ceiling={ceiling} errors={len(errors)}"
    )
    for error in errors:
        print(f"[FAIL] {error}")
    if errors and args.strict:
        return 1
    if errors:
        print("[REPORT] violations found; use --strict to fail")
    else:
        print("[OK] procedure delegation architecture baseline matches exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
