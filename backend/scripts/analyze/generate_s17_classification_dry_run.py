"""Generate S17 sheet-classification candidates without touching the database.

The production seed path scans the xlsx analysis JSON, so the legacy scanner never
sees the S17 ``.xls`` workbook.  This tool deliberately uses the existing xlrd
read path, applies the S9/S10 classification convention, and emits a deterministic
JSON report.  It has no database imports and no apply/write mode.

Usage (from repository root)::

    python backend/scripts/analyze/generate_s17_classification_dry_run.py \
      --output .agents/tasks/s-cycle-p0-impl-2026-10-25/s17_classification_dry_run.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
DEFAULT_TEMPLATE = BACKEND_ROOT / "wp_templates" / "S" / "S17 非经常性损益.xls"
DEFAULT_REFERENCE = BACKEND_ROOT / "data" / "acnr" / "sources" / "classification_cache.json"


# These are the existing S9/S10 class-code conventions, not database writes.
_CLASS_RULES: tuple[tuple[str, str, str], ...] = (
    ("表头（请先填写）", "I-占位", "header_placeholder_analogy"),
    ("审计程序S17", "A-S 议题程序", "s_topic_program"),
    ("审定表S17-1", "F-审定表", "adjudication_table"),
    ("审核表（合并）S17-2", "D-检查表", "consolidated_check_table"),
    ("审核表（个别报表）S17-3", "D-检查表", "standalone_check_table"),
    ("提示（供参考，不打印）", "H-辅助说明", "reference_note"),
    ("与营业外收支等核对表S17-11", "D-检查表", "reconciliation_check_table"),
    ("非经常性损益项目的所得税影响S17-21", "D-检查表", "tax_impact_check_table"),
)


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _load_reference(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict) and isinstance(value.get("rows"), list):
        return [row for row in value["rows"] if isinstance(row, dict)]
    return []


def _reference_examples(records: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    examples: dict[str, dict[str, str]] = {}
    for row in records:
        wp_code = str(row.get("wp_code", ""))
        if wp_code not in {"S9", "S10"}:
            continue
        class_code = str(row.get("class_code", ""))
        if class_code and class_code not in examples:
            examples[class_code] = {
                "wp_code": wp_code,
                "sheet": str(row.get("sheet_name", "")),
                "class_code": class_code,
            }
    return examples


def _classify_template_sheet(sheet_name: str) -> tuple[str | None, str, str]:
    """Return ``(class_code, rule_id, basis)`` from the actual S17 tab name."""
    compact = _normalized(sheet_name)
    for expected_name, class_code, rule_id in _CLASS_RULES:
        if compact == _normalized(expected_name):
            return class_code, rule_id, "S17 .xls 模板语义 + S9/S10 class_code 约定"
    return None, "unmapped_template_sheet", "模板存在但没有安全的候选分类规则"


def _xls_features(sheet: Any, xlrd_module: Any) -> dict[str, Any]:
    """Extract only features consumed by the existing name-rule classifier."""
    formula_type = getattr(xlrd_module, "XL_CELL_FORMULA", 2)
    formula_cells = 0
    has_step_words = False
    for row_index in range(min(sheet.nrows, 200)):
        for col_index in range(min(sheet.ncols, 30)):
            cell = sheet.cell(row_index, col_index)
            value = cell.value
            if cell.ctype == formula_type:
                formula_cells += 1
            if value not in (None, "") and any(
                token in str(value) for token in ("步骤一", "步骤二")
            ):
                has_step_words = True
    return {
        "formula_cells": formula_cells,
        "has_step_words": has_step_words,
    }


def _load_legacy_classifier() -> tuple[Callable[..., Any] | None, str | None]:
    """Load the existing xlsx name-rule classifier for conflict reporting only."""
    backend_text = str(BACKEND_ROOT)
    if backend_text not in sys.path:
        sys.path.insert(0, backend_text)
    try:
        from scripts.analyze.analyze_wp_templates import classify_sheet
    except (ImportError, OSError, SystemExit) as exc:
        return None, f"既有 xlsx 分类器不可用: {type(exc).__name__}: {exc}"
    return classify_sheet, None


def build_dry_run(
    template_path: Path = DEFAULT_TEMPLATE,
    reference_path: Path = DEFAULT_REFERENCE,
) -> dict[str, Any]:
    """Read the S17 workbook and build a no-write, deterministic report."""
    if template_path.suffix.lower() != ".xls":
        raise ValueError(f"S17 classification requires an .xls template: {template_path}")
    if not template_path.exists():
        raise FileNotFoundError(template_path)

    try:
        import xlrd
    except ImportError as exc:  # pragma: no cover - exercised in dependency-blocked envs
        raise RuntimeError(
            "读取 S17 .xls 需要 xlrd；当前环境未安装，请安装项目允许的 xlrd 2.x 依赖"
        ) from exc

    reader_version = str(getattr(xlrd, "__version__", "unknown"))
    reference_records = _load_reference(reference_path)
    examples = _reference_examples(reference_records)
    legacy_classifier, legacy_error = _load_legacy_classifier()
    candidates: list[dict[str, Any]] = []
    legacy_conflicts: list[dict[str, str]] = []

    book = xlrd.open_workbook(str(template_path), formatting_info=False)
    for sheet in book.sheets():
        class_code, rule_id, basis = _classify_template_sheet(sheet.name)
        features = _xls_features(sheet, xlrd)
        conflicts: list[dict[str, str]] = []

        legacy_result: dict[str, str] | None = None
        if legacy_classifier is not None:
            inferred_code, inferred_reason = legacy_classifier(sheet.name, features)
            legacy_result = {
                "class_code": str(inferred_code),
                "reason": str(inferred_reason),
                "scope": "existing xlsx name-rule classifier; comparison only",
            }
            if class_code != inferred_code:
                conflict = {
                    "kind": "legacy_xlsx_classifier_mismatch",
                    "candidate": str(class_code),
                    "legacy": str(inferred_code),
                    "reason": str(inferred_reason),
                }
                conflicts.append(conflict)
                legacy_conflicts.append({"sheet": sheet.name, **conflict})
        elif legacy_error:
            legacy_result = {"error": legacy_error}

        if class_code is None:
            conflicts.append({
                "kind": "unmapped_template_sheet",
                "reason": "未生成候选 class_code，必须人工裁决后才可进入 seed",
            })

        reference_example = examples.get(class_code or "")
        source = {
            "template": _relative(template_path),
            "reader": "xlrd",
            "reader_version": reader_version,
            "template_sha256": _sha256(template_path),
            "rule_id": rule_id,
            "basis": basis,
            "reference_example": reference_example,
        }
        candidates.append({
            "wp_code": "S17",
            "sheet_name": sheet.name,
            "class_code": class_code,
            "source": source,
            "conflict": conflicts,
            "dimensions": {"rows": sheet.nrows, "columns": sheet.ncols},
            "legacy_classifier": legacy_result,
        })

    existing_s17 = [
        row for row in reference_records if str(row.get("wp_code", "")) == "S17"
    ]
    candidate_sheet_names = {row["sheet_name"] for row in candidates}
    exact_existing_s17 = [
        row for row in existing_s17 if str(row.get("sheet_name", "")) in candidate_sheet_names
    ]
    parent_only_s17 = [
        row for row in existing_s17 if str(row.get("sheet_name", "")) not in candidate_sheet_names
    ]
    return {
        "report_version": 1,
        "mode": "dry-run",
        "candidate_count": len(candidates),
        "writes_shared_database": False,
        "shared_database_accessed": False,
        "template": {
            "path": _relative(template_path),
            "format": "xls",
            "reader": "xlrd",
            "reader_version": reader_version,
            "sha256": _sha256(template_path),
        },
        "classification_schema": {
            "table": "workpaper_sheet_classification",
            "candidate_columns": ["wp_code", "sheet_name", "class_code"],
            "source_is_offline_cache": _relative(reference_path),
        },
        "reference_classification": {
            "path": _relative(reference_path),
            "s9_s10_examples": len(examples),
            "existing_s17_rows": len(existing_s17),
            "exact_candidate_rows": len(exact_existing_s17),
            "parent_only_rows": parent_only_s17,
            "conflict": (
                "离线快照有父级 S17 行但没有这 8 个 sheet 行；正式 seed 的 .xlsx 分析路径不会发现该 .xls，数据库未查询。"
                if parent_only_s17 and not exact_existing_s17
                else "离线快照没有 S17 行；正式 seed 的 .xlsx 分析路径不会发现该 .xls，数据库未查询。"
                if not existing_s17
                else "离线快照已有候选 sheet 行，需逐行对比后再审批；数据库未查询。"
            ),
        },
        "conflicts": {
            "legacy_classifier_available": legacy_classifier is not None,
            "legacy_classifier_error": legacy_error,
            "legacy_xlsx_classifier_mismatches": legacy_conflicts,
            "summary": (
                f"{len(legacy_conflicts)} 个候选与既有 xlsx 名称/特征规则不一致；"
                "这是 .xls 新通路的待审批冲突，不自动写库。"
                if legacy_conflicts
                else "未发现既有名称规则冲突。"
            ),
        },
        "candidates": candidates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="从 S17 .xls 模板生成 workpaper_sheet_classification 候选（始终只读）"
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, help="可选：写入离线 JSON 报告，不写数据库")
    parser.add_argument(
        "--dry-run", action="store_true", help="显式声明只 dry-run；工具没有写库模式"
    )
    args = parser.parse_args(argv)

    report = build_dry_run(args.template, args.reference)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(f"[DRY-RUN] report={args.output}")
    else:
        print(encoded, end="")
    print(
        f"[DRY-RUN] candidates={report['candidate_count']} "
        f"writes_shared_database={report['writes_shared_database']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
