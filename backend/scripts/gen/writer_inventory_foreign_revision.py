"""Writer inventory helpers: another aggregate's **own** revision counter is not a workpaper version.

Split out of ``generate_workpaper_writer_inventory.py`` (2026-11-04, line-count gate); the
generator keeps same-named thin wrappers, so its call sites and tests are unchanged. Both
functions are pure source facts: ``app/models`` ORM classes and one module's AST.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path


def foreign_revision_models(
    app_root: Path, version_attrs: frozenset[str]
) -> dict[str, frozenset[str]]:
    """ORM classes under ``app/models`` that declare their **own** workpaper-named version column.

    Returns ``{class name: {version attrs it declares}}`` for every class other than
    ``WorkingPaper`` whose class body declares an attribute in ``version_attrs`` (measured
    2026-11-03: ``Adjustment.content_revision``, the adjustment-entry group's CAS counter added
    by V235). Derived from source, not listed by hand, so a new aggregate with its own counter is
    picked up -- and so is a model that stops declaring one.

    Only **mapped** classes count (the class body declares ``__tablename__`` / ``__table__``).
    A request/response schema that merely carries a same-named field is not a persisted counter
    (measured 2026-11-04: pydantic ``AdjustmentGroupResponse.content_revision`` in
    ``audit_platform_schemas``), and letting it in would only blur the recorded owner.
    """
    owners: dict[str, frozenset[str]] = {}
    models_root = app_root / "models"
    for path in sorted(models_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name == "WorkingPaper":
                continue
            assigned = {
                target.id
                for statement in node.body
                for target in (
                    [statement.target] if isinstance(statement, ast.AnnAssign)
                    else statement.targets if isinstance(statement, ast.Assign)
                    else []
                )
                if isinstance(target, ast.Name)
            }
            if not assigned & {"__tablename__", "__table__"}:
                continue
            declared = assigned & version_attrs
            if declared:
                owners[node.name] = frozenset(declared)
    return owners


def module_foreign_version_owners(
    tree: ast.AST,
    import_bindings: Mapping[str, str],
    foreign_models: Mapping[str, frozenset[str]],
) -> dict[str, str]:
    """``{version attr: owning model}`` for attribute writes this module makes on another aggregate.

    🔴 The attribute predicate is receiver-agnostic: ``row.content_revision = n`` counts as a
    workpaper version write whatever ``row`` is. Measured false positive: the adjustment hall's
    ``AdjustmentService.update_entry`` advances ``Adjustment.content_revision`` (its own CAS
    counter) and was reported as a second workpaper revision domain.

    Deliberately conservative -- it only fires when the module **imports** a foreign model that
    declares that attribute from ``app.models`` **and** never mentions the workpaper at all (no
    ``WorkingPaper`` import, name, attribute or string, no ``working_paper`` string). A module
    that can reach a workpaper keeps every attribute write counted as a workpaper version write,
    so the rule cannot hide a real one behind an unrelated import.

    An ``import`` binding counts as a mention on its own: ``from ... import WorkingPaper`` is an
    ``ast.alias``, not an ``ast.Name``, so a module that imports the class but only reaches it
    through a helper would otherwise slip past the name check (caught by the four-way test).
    """
    imported = sorted(
        {
            origin.rsplit(".", 1)[-1]
            for origin in import_bindings.values()
            if origin.startswith("app.models.") and origin.rsplit(".", 1)[-1] in foreign_models
        }
    )
    if not imported:
        return {}
    for node in ast.walk(tree):
        if isinstance(node, ast.alias) and "WorkingPaper" in (
            node.name.rsplit(".", 1)[-1],
            node.asname or "",
        ):
            return {}
        if isinstance(node, ast.Name) and node.id == "WorkingPaper":
            return {}
        if isinstance(node, ast.Attribute) and node.attr == "WorkingPaper":
            return {}
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and (
            "WorkingPaper" in node.value or "working_paper" in node.value
        ):
            return {}
    owners: dict[str, list[str]] = defaultdict(list)
    for model in imported:
        for attr in foreign_models[model]:
            owners[attr].append(model)
    return {attr: "/".join(sorted(models)) for attr, models in owners.items()}
