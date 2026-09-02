"""Generate the AC -> oracle -> task -> verification -> evidence coverage matrix.

spec: .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/
Wave 0 Task 8 - Requirements 1.8, 14.7, 14.13, 14.15 - Property 57

Requirement 14.15 turns "every AC has a Design oracle, an implementing task, an
*independent* verifying task and an evidence type" into an archival gate. This module
produces the per-AC expansion that gate reads. Everything in the matrix is parsed from
the three spec documents; the single human judgement lives in the reviewed overlay
``backend/data/workpaper_ac_evidence_overlay.json`` and is only the mapping from the
free-text ``Evidence type`` column of design.md's ``## Acceptance Oracle Matrix`` onto a
closed enum. The overlay cannot add, remove or exempt an AC: its schema has no field for
AC ids or defect codes, and unknown keys are rejected.

Why the parse is line-anchored rather than window-sliced: the three documents are
52KB/143KB/85KB and are edited by concurrent sessions. Character windows silently cut a
different span after any edit, so every boundary here is a line-start anchor plus an
assertion, and a mismatch raises instead of degrading.

Defect codes (each is a *fact*, never an exemption):

===========================  ====================================================
dangling_ac                  no task lists the AC under ``_Requirements:``
no_oracle_family             the AC is outside every row of the oracle matrix
no_property_oracle           no ``### Property N`` validates the AC
self_certified_single_task   exactly one task covers the AC (impl == verification)
no_dependency_edge           >=2 tasks cover it, but none depends on another
no_evidence_type             the AC's oracle family has no reviewed evidence class
===========================  ====================================================

Usage from the repository root::

    python backend/scripts/gen/generate_workpaper_ac_coverage_matrix.py --check
    python backend/scripts/gen/generate_workpaper_ac_coverage_matrix.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_SPEC_DIR = (
    _REPO
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
)
_REQUIREMENTS = _SPEC_DIR / "requirements.md"
_DESIGN = _SPEC_DIR / "design.md"
_TASKS = _SPEC_DIR / "tasks.md"
_OVERLAY = _REPO / "backend" / "data" / "workpaper_ac_evidence_overlay.json"
_MATRIX = _REPO / "backend" / "data" / "workpaper_ac_coverage_matrix.json"

#: Closed evidence vocabulary. The overlay may only pick from this set; a new class has
#: to be added here (and therefore reviewed) rather than invented inside the overlay.
_EVIDENCE_CLASSES: frozenset[str] = frozenset(
    {
        "source_ast_inventory",
        "contract_interlock",
        "db_integration",
        "filesystem_artifact",
        "dom_projection",
        "real_onlyoffice_browser",
        "security_trace",
        "mutation_four_state",
        "capacity_fault",
    }
)

#: Keys an overlay adjudication may carry. Anything else is refused, which is what keeps
#: the overlay from growing an exemption field.
_ADJUDICATION_KEYS: frozenset[str] = frozenset(
    {"evidence_classes", "design_evidence_text", "note"}
)
_OVERLAY_KEYS: frozenset[str] = frozenset(
    {"schema_version", "review_status", "spec", "task", "purpose", "adjudications"}
)

_AC_RE = re.compile(r"^(\d+)\.(\d+)\.\s+(?P<text>\S.*)$")
_REQ_HEAD_RE = re.compile(r"^### Requirement (\d+):\s*(?P<title>.*)$")
_PROP_HEAD_RE = re.compile(r"^### Property (\d+):\s*(?P<title>.*)$")
_VALIDATES_RE = re.compile(r"^\*\*Validates: Requirements ([0-9.,\s]+)\*\*$")
_TASK_RE = re.compile(r"^- \[(?P<state>[ x~\-])\] (?P<num>\d+)\.\s+(?P<title>.*)$")
_TASK_REQ_RE = re.compile(r"^\s+- _Requirements:\s*(?P<ids>[^_]+)_\s*$")
_PROPERTY_MENTION_RE = re.compile(r"Property (\d+)")
_AC_ID_RE = re.compile(r"^\d+\.\d+$")
#: The oracle-matrix range uses an EN DASH in design.md; accept the ASCII forms too so a
#: later editor fixing punctuation does not silently drop a row.
_RANGE_RE = re.compile(r"^(\d+)\.(\d+)\s*[\u2013\u2014-]\s*(\d+)\.(\d+)$")

_ORACLE_MATRIX_HEADING = "## Acceptance Oracle Matrix"
_ORACLE_MATRIX_HEADER_ROW = "| AC 范围 | Design oracle family | 核心判据 | Evidence type |"
_DEPENDENCY_HEADING = "## Task Dependency Graph"


class CoverageMatrixError(RuntimeError):
    """Raised when the spec documents or the reviewed overlay cannot be parsed."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stable_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _read_lines(path: Path) -> list[str]:
    if not path.is_file():
        raise CoverageMatrixError(f"missing spec document: {path}")
    return path.read_bytes().decode("utf-8").split("\n")


# --------------------------------------------------------------------------- parsing


def parse_acceptance_criteria(lines: list[str]) -> list[dict[str, Any]]:
    """Parse ``### Requirement N`` blocks and their ``N.M.`` acceptance criteria.

    The enclosing requirement number is asserted against each AC id: a copy-pasted block
    that keeps the previous requirement's numbering would otherwise produce a plausible
    but wrong matrix.
    """
    out: list[dict[str, Any]] = []
    current_req: int | None = None
    current_title = ""
    seen: set[str] = set()
    for index, line in enumerate(lines, start=1):
        head = _REQ_HEAD_RE.match(line)
        if head:
            current_req = int(head.group(1))
            current_title = head.group("title").strip()
            continue
        match = _AC_RE.match(line)
        if not match:
            continue
        req_num, ac_num = int(match.group(1)), int(match.group(2))
        ac_id = f"{req_num}.{ac_num}"
        if current_req is None:
            raise CoverageMatrixError(f"AC {ac_id} at L{index} precedes any requirement heading")
        if req_num != current_req:
            raise CoverageMatrixError(
                f"AC {ac_id} at L{index} sits under '### Requirement {current_req}'"
            )
        if ac_id in seen:
            raise CoverageMatrixError(f"duplicate AC id {ac_id} at L{index}")
        seen.add(ac_id)
        out.append(
            {
                "ac_id": ac_id,
                "requirement": req_num,
                "requirement_title": current_title,
                "line": index,
                "text_digest": _sha256(match.group("text").strip().encode("utf-8")),
            }
        )
    if not out:
        raise CoverageMatrixError("no acceptance criteria parsed - requirements.md format changed")
    for req_num in sorted({row["requirement"] for row in out}):
        indices = [int(r["ac_id"].split(".")[1]) for r in out if r["requirement"] == req_num]
        expected = list(range(1, len(indices) + 1))
        if sorted(indices) != expected:
            raise CoverageMatrixError(
                f"requirement {req_num} AC numbering is not contiguous: {sorted(indices)}"
            )
    return out


def parse_properties(lines: list[str]) -> list[dict[str, Any]]:
    """Parse ``### Property N`` plus the ``**Validates: Requirements X.Y**`` that follows.

    The Validates line must appear before the next ``### `` heading, matching the
    machine validation applied to spec markdown (integer property numbers, ``X.Y`` ids).
    """
    out: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    seen: set[int] = set()
    for index, line in enumerate(lines, start=1):
        head = _PROP_HEAD_RE.match(line)
        if head:
            if pending is not None:
                raise CoverageMatrixError(
                    f"Property {pending['property']} has no Validates line before L{index}"
                )
            number = int(head.group(1))
            if number in seen:
                raise CoverageMatrixError(f"duplicate Property {number} at L{index}")
            seen.add(number)
            pending = {
                "property": number,
                "title": head.group("title").strip(),
                "line": index,
                "validates": [],
            }
            continue
        if pending is None:
            continue
        validates = _VALIDATES_RE.match(line)
        if validates:
            ids = [chunk.strip() for chunk in validates.group(1).split(",") if chunk.strip()]
            bad = [i for i in ids if not _AC_ID_RE.match(i)]
            if bad:
                raise CoverageMatrixError(
                    f"Property {pending['property']} validates non 'X.Y' ids: {bad}"
                )
            pending["validates"] = ids
            out.append(pending)
            pending = None
        elif line.startswith("### ") or line.startswith("## "):
            raise CoverageMatrixError(
                f"Property {pending['property']} has no Validates line before L{index}"
            )
    if pending is not None:
        raise CoverageMatrixError(f"Property {pending['property']} has no Validates line")
    if not out:
        raise CoverageMatrixError("no properties parsed - design.md format changed")
    numbers = sorted(p["property"] for p in out)
    if numbers != list(range(1, len(numbers) + 1)):
        raise CoverageMatrixError(f"property numbering has holes: {numbers}")
    return out


def parse_oracle_families(lines: list[str]) -> list[dict[str, Any]]:
    """Parse the ``## Acceptance Oracle Matrix`` table (AC range -> family -> evidence).

    Boundaries are the heading line and the next ``## `` heading; the header row is
    asserted verbatim so a reordered column cannot be read as a different field.
    """
    try:
        start = lines.index(_ORACLE_MATRIX_HEADING)
    except ValueError as exc:
        raise CoverageMatrixError(f"design.md has no '{_ORACLE_MATRIX_HEADING}' section") from exc
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    block = lines[start:end]
    header_at = [i for i, line in enumerate(block) if line.strip() == _ORACLE_MATRIX_HEADER_ROW]
    if len(header_at) != 1:
        raise CoverageMatrixError(
            "oracle matrix header row not found verbatim (column order or wording changed)"
        )
    rows: list[dict[str, Any]] = []
    for offset, line in enumerate(block[header_at[0] + 2 :], start=header_at[0] + 2):
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            raise CoverageMatrixError(f"oracle matrix row at L{start + offset + 1} has {len(cells)} cells")
        span = _RANGE_RE.match(cells[0])
        if not span:
            raise CoverageMatrixError(f"unparsable AC range {cells[0]!r}")
        req_lo, ac_lo, req_hi, ac_hi = (int(span.group(i)) for i in (1, 2, 3, 4))
        if req_lo != req_hi or ac_lo > ac_hi:
            raise CoverageMatrixError(f"AC range {cells[0]!r} must stay inside one requirement")
        family = cells[1].strip("`")
        if not family:
            raise CoverageMatrixError(f"oracle matrix row {cells[0]!r} has an empty family")
        rows.append(
            {
                "family": family,
                "requirement": req_lo,
                "ac_first": ac_lo,
                "ac_last": ac_hi,
                "ac_ids": [f"{req_lo}.{n}" for n in range(ac_lo, ac_hi + 1)],
                "criteria": cells[2],
                "evidence_text": cells[3],
                "line": start + offset + 1,
                "row_digest": _sha256(line.encode("utf-8")),
            }
        )
    if not rows:
        raise CoverageMatrixError("oracle matrix has no rows")
    families = [row["family"] for row in rows]
    if len(set(families)) != len(families):
        raise CoverageMatrixError(f"duplicate oracle family in the matrix: {families}")
    return rows


def parse_tasks(lines: list[str]) -> list[dict[str, Any]]:
    """Parse tasks, their ``_Requirements:`` list and every ``Property N`` they verify."""
    out: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for index, line in enumerate(lines, start=1):
        head = _TASK_RE.match(line)
        if head:
            current = {
                "task": head.group("num"),
                "state": head.group("state"),
                "title": head.group("title").strip(),
                "line": index,
                "ac_ids": [],
                "properties": [],
                "requirements_lines": 0,
            }
            out.append(current)
            continue
        if current is None:
            continue
        if line.startswith("#") or line.startswith("- "):
            current = None
            continue
        req = _TASK_REQ_RE.match(line)
        if req:
            ids = [chunk.strip() for chunk in req.group("ids").split(",") if chunk.strip()]
            bad = [i for i in ids if not _AC_ID_RE.match(i)]
            if bad:
                raise CoverageMatrixError(f"task {current['task']} lists non 'X.Y' ids: {bad}")
            current["ac_ids"] = ids
            current["requirements_lines"] += 1
            continue
        if "Property" in line:
            current["properties"].extend(
                int(m.group(1)) for m in _PROPERTY_MENTION_RE.finditer(line)
            )
    if not out:
        raise CoverageMatrixError("no tasks parsed - tasks.md format changed")
    for task in out:
        task["properties"] = sorted(set(task["properties"]))
        if task["requirements_lines"] != 1:
            raise CoverageMatrixError(
                f"task {task['task']} has {task['requirements_lines']} '_Requirements:' lines"
            )
    numbers = sorted(int(task["task"]) for task in out)
    if numbers != list(range(1, len(numbers) + 1)):
        raise CoverageMatrixError(f"task numbering has holes: {numbers}")
    return out


def parse_dependency_graph(lines: list[str]) -> dict[str, Any]:
    """Parse the fenced JSON under ``## Task Dependency Graph`` (waves + dependencies)."""
    try:
        start = lines.index(_DEPENDENCY_HEADING)
    except ValueError as exc:
        raise CoverageMatrixError(f"tasks.md has no '{_DEPENDENCY_HEADING}' section") from exc
    fence = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == "```json"), -1)
    if fence < 0:
        raise CoverageMatrixError("dependency graph section has no ```json fence")
    close = next((i for i in range(fence + 1, len(lines)) if lines[i].strip() == "```"), -1)
    if close < 0:
        raise CoverageMatrixError("dependency graph fence is never closed")
    try:
        graph = json.loads("\n".join(lines[fence + 1 : close]))
    except json.JSONDecodeError as exc:
        raise CoverageMatrixError(f"dependency graph is not valid JSON: {exc}") from exc
    if "waves" not in graph or "dependencies" not in graph:
        raise CoverageMatrixError("dependency graph needs both 'waves' and 'dependencies'")
    return graph


# ------------------------------------------------------------------------ derivation


def _transitive_dependencies(dependencies: dict[str, list[str]]) -> dict[str, set[str]]:
    """Transitive closure of the dependency graph; a cycle raises rather than loops."""
    resolved: dict[str, set[str]] = {}

    def walk(task: str, stack: tuple[str, ...]) -> set[str]:
        if task in resolved:
            return resolved[task]
        if task in stack:
            raise CoverageMatrixError(f"dependency cycle: {' -> '.join((*stack, task))}")
        acc: set[str] = set()
        for parent in dependencies.get(task, []):
            if parent not in dependencies:
                raise CoverageMatrixError(f"task {task} depends on unknown task {parent}")
            acc.add(parent)
            acc |= walk(parent, (*stack, task))
        resolved[task] = acc
        return acc

    for task in dependencies:
        walk(task, ())
    return resolved


def _validate_overlay(overlay: dict[str, Any], families: list[dict[str, Any]]) -> None:
    if overlay.get("schema_version") != 1 or overlay.get("review_status") != "reviewed":
        raise CoverageMatrixError(
            "overlay must use schema_version=1 and review_status='reviewed'"
        )
    unknown_top = sorted(set(overlay) - _OVERLAY_KEYS)
    if unknown_top:
        raise CoverageMatrixError(
            f"overlay has unknown top-level keys {unknown_top}; it carries adjudications only, "
            "never exemptions"
        )
    adjudications = overlay.get("adjudications")
    if not isinstance(adjudications, dict) or not adjudications:
        raise CoverageMatrixError("overlay.adjudications must be a non-empty object")
    by_family = {row["family"]: row for row in families}
    for name, value in adjudications.items():
        if not isinstance(value, dict):
            raise CoverageMatrixError(f"adjudication must be an object: {name}")
        unknown = sorted(set(value) - _ADJUDICATION_KEYS)
        if unknown:
            raise CoverageMatrixError(
                f"adjudication {name} has unknown keys {unknown}; allowed: "
                f"{sorted(_ADJUDICATION_KEYS)}"
            )
        classes = value.get("evidence_classes")
        if not isinstance(classes, list) or not classes:
            raise CoverageMatrixError(f"adjudication {name} needs a non-empty evidence_classes")
        illegal = sorted(set(classes) - _EVIDENCE_CLASSES)
        if illegal:
            raise CoverageMatrixError(
                f"adjudication {name} uses unknown evidence classes {illegal}; "
                f"allowed: {sorted(_EVIDENCE_CLASSES)}"
            )
        if len(set(classes)) != len(classes):
            raise CoverageMatrixError(f"adjudication {name} repeats an evidence class")
        if not value.get("note"):
            raise CoverageMatrixError(f"adjudication {name} needs a note")
        row = by_family.get(name)
        if row is None:
            raise CoverageMatrixError(
                f"overlay adjudicates oracle family {name!r} that design.md no longer declares"
            )
        if value.get("design_evidence_text") != row["evidence_text"]:
            raise CoverageMatrixError(
                f"adjudication {name} pins evidence text that design.md changed:\n"
                f"  overlay: {value.get('design_evidence_text')!r}\n"
                f"  design : {row['evidence_text']!r}"
            )


def build_matrix(
    *,
    acs: list[dict[str, Any]],
    properties: list[dict[str, Any]],
    families: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    graph: dict[str, Any],
    overlay: dict[str, Any],
    sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    _validate_overlay(overlay, families)
    adjudications: dict[str, Any] = overlay["adjudications"]

    ac_ids = {row["ac_id"] for row in acs}
    property_numbers = {row["property"] for row in properties}
    task_ids = {task["task"] for task in tasks}

    dependencies = {str(k): [str(v) for v in vals] for k, vals in graph["dependencies"].items()}
    missing_dep_nodes = sorted(task_ids - set(dependencies), key=int)
    if missing_dep_nodes:
        raise CoverageMatrixError(f"dependency graph is missing tasks: {missing_dep_nodes}")
    ancestors = _transitive_dependencies(dependencies)
    wave_of: dict[str, int] = {}
    for wave in graph["waves"]:
        for task_id in wave["tasks"]:
            wave_of[str(task_id)] = int(wave["wave"])
    unwaved = sorted(task_ids - set(wave_of), key=int)
    if unwaved:
        raise CoverageMatrixError(f"tasks outside every wave: {unwaved}")

    # Cross-document reference integrity: a stale reference is a defect of the document,
    # never something the matrix may quietly drop.
    stale: dict[str, list[str]] = {
        "task_to_unknown_ac": sorted(
            {ac for task in tasks for ac in task["ac_ids"] if ac not in ac_ids}
        ),
        "task_to_unknown_property": sorted(
            {str(p) for task in tasks for p in task["properties"] if p not in property_numbers}
        ),
        "property_to_unknown_ac": sorted(
            {ac for prop in properties for ac in prop["validates"] if ac not in ac_ids}
        ),
        "oracle_family_to_unknown_ac": sorted(
            {ac for row in families for ac in row["ac_ids"] if ac not in ac_ids}
        ),
    }

    family_of: dict[str, dict[str, Any]] = {}
    duplicate_family_coverage: list[str] = []
    for row in families:
        for ac in row["ac_ids"]:
            if ac in family_of:
                duplicate_family_coverage.append(ac)
            family_of[ac] = row

    tasks_by_ac: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        for ac in task["ac_ids"]:
            tasks_by_ac[ac].append(task["task"])
    properties_by_ac: dict[str, list[int]] = defaultdict(list)
    for prop in properties:
        for ac in prop["validates"]:
            properties_by_ac[ac].append(prop["property"])
    tasks_by_property: dict[int, list[str]] = defaultdict(list)
    for task in tasks:
        for number in task["properties"]:
            tasks_by_property[number].append(task["task"])

    entries: list[dict[str, Any]] = []
    for row in acs:
        ac = row["ac_id"]
        covering = sorted(set(tasks_by_ac.get(ac, [])), key=int)
        pairs = sorted(
            (
                [impl, verifier]
                for verifier in covering
                for impl in covering
                if impl != verifier and impl in ancestors.get(verifier, set())
            ),
            key=lambda pair: (int(pair[1]), int(pair[0])),
        )
        family = family_of.get(ac)
        verdict = adjudications.get(family["family"]) if family else None
        evidence_classes = sorted(verdict["evidence_classes"]) if verdict else []
        defects: list[str] = []
        if not covering:
            defects.append("dangling_ac")
        if family is None:
            defects.append("no_oracle_family")
        if not properties_by_ac.get(ac):
            defects.append("no_property_oracle")
        if len(covering) == 1:
            defects.append("self_certified_single_task")
        elif covering and not pairs:
            defects.append("no_dependency_edge")
        if not evidence_classes:
            defects.append("no_evidence_type")
        entries.append(
            {
                "ac_id": ac,
                "requirement": row["requirement"],
                "requirement_title": row["requirement_title"],
                "requirements_line": row["line"],
                "text_digest": row["text_digest"],
                "oracle_family": family["family"] if family else None,
                "oracle_family_row_digest": family["row_digest"] if family else None,
                "design_oracle_properties": sorted(properties_by_ac.get(ac, [])),
                "covering_tasks": covering,
                "covering_task_waves": {t: wave_of[t] for t in covering},
                "earliest_wave": min((wave_of[t] for t in covering), default=None),
                "implementation_verification_pairs": pairs,
                "independent_verification_tasks": sorted(
                    {pair[1] for pair in pairs}, key=int
                ),
                "evidence_classes": evidence_classes,
                "defects": defects,
            }
        )

    property_entries = [
        {
            "property": prop["property"],
            "title": prop["title"],
            "design_line": prop["line"],
            "validates": prop["validates"],
            "verifying_tasks": sorted(set(tasks_by_property.get(prop["property"], [])), key=int),
            "defects": (
                [] if tasks_by_property.get(prop["property"]) else ["dangling_property"]
            ),
        }
        for prop in properties
    ]

    task_entries = [
        {
            "task": task["task"],
            "state": task["state"],
            "wave": wave_of[task["task"]],
            "title": task["title"],
            "tasks_line": task["line"],
            "ac_ids": task["ac_ids"],
            "verifies_properties": task["properties"],
            "depends_on": sorted(dependencies.get(task["task"], []), key=int),
        }
        for task in tasks
    ]

    defect_counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        for code in entry["defects"]:
            defect_counts[code] += 1
    for entry in property_entries:
        for code in entry["defects"]:
            defect_counts[code] += 1

    #: Wave attribution: a defect on an AC whose earliest covering task is already an
    #: in-flight wave is a live problem; one whose tasks all sit in later waves is a plan
    #: gap to fix before that wave starts. Both are reported, neither is suppressed.
    #: A dangling AC has no covering task and therefore no wave; it is bucketed under
    #: ``unassigned`` rather than dropped, and the sort key must survive that.
    defects_by_wave: dict[str, dict[str, int]] = {}
    for entry in entries:
        if not entry["defects"]:
            continue
        wave = entry["earliest_wave"]
        bucket = defects_by_wave.setdefault("unassigned" if wave is None else str(wave), {})
        for code in entry["defects"]:
            bucket[code] = bucket.get(code, 0) + 1

    matrix: dict[str, Any] = {
        "schema_version": 1,
        "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "task": "Wave 0 Task 8",
        "generated_by": "backend/scripts/gen/generate_workpaper_ac_coverage_matrix.py",
        "evidence_classes": sorted(_EVIDENCE_CLASSES),
        "defect_codes": [
            "dangling_ac",
            "no_oracle_family",
            "no_property_oracle",
            "self_certified_single_task",
            "no_dependency_edge",
            "no_evidence_type",
            "dangling_property",
        ],
        "sources": sources,
        "stale_references": stale,
        "duplicate_family_coverage": sorted(set(duplicate_family_coverage)),
        "oracle_families": [
            {
                "family": row["family"],
                "ac_range": f"{row['requirement']}.{row['ac_first']}-{row['requirement']}.{row['ac_last']}",
                "ac_ids": row["ac_ids"],
                "design_line": row["line"],
                "row_digest": row["row_digest"],
                "evidence_text": row["evidence_text"],
                "evidence_classes": sorted(
                    adjudications.get(row["family"], {}).get("evidence_classes", [])
                ),
            }
            for row in families
        ],
        "stats": {
            "ac_count": len(entries),
            "property_count": len(property_entries),
            "task_count": len(task_entries),
            "oracle_family_count": len(families),
            "ac_with_defects": sum(1 for e in entries if e["defects"]),
            "clean_ac_count": sum(1 for e in entries if not e["defects"]),
            "defect_counts": dict(sorted(defect_counts.items())),
            "defects_by_earliest_wave": {
                key: dict(sorted(value.items()))
                for key, value in sorted(
                    defects_by_wave.items(),
                    key=lambda kv: (kv[0] == "unassigned", kv[0].isdigit() and int(kv[0])),
                )
            },
            "stale_reference_count": sum(len(v) for v in stale.values()),
        },
        "acceptance_criteria": entries,
        "properties": property_entries,
        "tasks": task_entries,
    }
    matrix["overlay_digest"] = _sha256(_stable_json(overlay).encode("utf-8"))
    matrix["facts_digest"] = _sha256(
        _stable_json([entries, property_entries, task_entries]).encode("utf-8")
    )
    matrix["matrix_digest"] = _sha256(_stable_json(matrix).encode("utf-8"))
    return matrix


def collect_sources() -> dict[str, dict[str, Any]]:
    """Per-document digest so an edited spec with an unregenerated matrix fails closed."""
    out: dict[str, dict[str, Any]] = {}
    for path in (_REQUIREMENTS, _DESIGN, _TASKS):
        raw = path.read_bytes()
        out[path.relative_to(_REPO).as_posix()] = {
            "sha256": _sha256(raw),
            "bytes": len(raw),
            "lines": raw.decode("utf-8").count("\n") + 1,
        }
    return out


def generate() -> dict[str, Any]:
    requirements_lines = _read_lines(_REQUIREMENTS)
    design_lines = _read_lines(_DESIGN)
    tasks_lines = _read_lines(_TASKS)
    overlay = json.loads(_OVERLAY.read_text(encoding="utf-8")) if _OVERLAY.is_file() else {}
    if not overlay:
        raise CoverageMatrixError(f"missing reviewed overlay: {_OVERLAY}")
    return build_matrix(
        acs=parse_acceptance_criteria(requirements_lines),
        properties=parse_properties(design_lines),
        families=parse_oracle_families(design_lines),
        tasks=parse_tasks(tasks_lines),
        graph=parse_dependency_graph(tasks_lines),
        overlay=overlay,
        sources=collect_sources(),
    )


def render(matrix: dict[str, Any]) -> str:
    return json.dumps(matrix, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _print_summary(matrix: dict[str, Any]) -> None:
    stats = matrix["stats"]
    print(
        f"[MATRIX] ac={stats['ac_count']} property={stats['property_count']} "
        f"task={stats['task_count']} family={stats['oracle_family_count']} "
        f"clean_ac={stats['clean_ac_count']} defective_ac={stats['ac_with_defects']}"
    )
    print(f"[MATRIX] defects={stats['defect_counts']}")
    print(f"[MATRIX] defects_by_earliest_wave={stats['defects_by_earliest_wave']}")
    if stats["stale_reference_count"]:
        print(f"[MATRIX] stale_references={matrix['stale_references']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify the generated matrix")
    mode.add_argument("--apply", action="store_true", help="atomically regenerate the matrix")
    args = parser.parse_args(argv)

    matrix = generate()
    content = render(matrix)
    _print_summary(matrix)
    if args.check:
        if not _MATRIX.is_file():
            print(f"[FAIL] missing generated matrix: {_MATRIX.relative_to(_REPO)}")
            return 2
        if _MATRIX.read_text(encoding="utf-8") != content:
            print(
                "[FAIL] stale generated matrix: "
                f"{_MATRIX.relative_to(_REPO)} no longer matches the spec documents"
            )
            return 2
        print(f"[OK] matrix digest {matrix['matrix_digest']}")
        return 0
    _atomic_write(_MATRIX, content)
    print(f"[APPLIED] {_MATRIX.relative_to(_REPO)} sha256={_sha256(content.encode('utf-8'))[:16]}")
    print(f"[OK] matrix digest {matrix['matrix_digest']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CoverageMatrixError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
