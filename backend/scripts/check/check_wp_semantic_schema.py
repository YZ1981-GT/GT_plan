"""底稿语义 schema 校验脚本.

扫描 production schema YAML 和 D1/D2 语义注册表，检查：
1. sheet_type 枚举合法性 (6.2)
2. field_sources.source_ref 可解析 (6.3)
3. generated schema 不得被引用为生产真源 (6.4)
4. 缺失 sheet_type 的历史 schema 输出 warning 不阻断 (6.5)
5. D1/D2 迁移报告 (6.6)

用法:
    python backend/scripts/check/check_wp_semantic_schema.py
    python backend/scripts/check/check_wp_semantic_schema.py --strict

退出码:
    P0 模式 (默认): 总是 exit 0 (warning-only)
    --strict (P2): 关键 schema 缺失 sheet_type 时 exit 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    # 兼容无 PyYAML 环境
    yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 合法的 SheetContentType 枚举值
VALID_SHEET_TYPES = frozenset([
    "control_panel",
    "audit_sheet",
    "detail_table",
    "analysis",
    "procedure",
    "control_understanding",
    "control_test",
    "confirmation_summary",
    "disclosure",
    "adjustment",
    "conclusion",
    "legacy",
    "unknown",
])

# 合法的 FieldSourceType 枚举值
VALID_SOURCE_TYPES = frozenset([
    "trial_balance",
    "formula",
    "manual",
    "linked",
    "ai_generated",
])

# Schema 根目录 (生产 schema)
SCHEMA_ROOT = Path("backend/data/ledger_adapters/wp_render_schema")
# Generated 子目录
GENERATED_DIR = SCHEMA_ROOT / "generated"
# 语义注册表
REGISTRY_PATH = SCHEMA_ROOT / "d1_d2_semantic_registry.json"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict[str, Any] | None:
    """加载 YAML 文件，返回 dict 或 None (解析失败)."""
    if yaml is None:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
        return None
    except Exception:
        return None


def _load_json(path: Path) -> dict[str, Any] | None:
    """加载 JSON 文件."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 校验逻辑
# ---------------------------------------------------------------------------

def check_sheet_type_validity(sheet_type: str, context: str) -> list[dict[str, str]]:
    """检查 sheet_type 是否在合法枚举内 (6.2)."""
    errors: list[dict[str, str]] = []
    if sheet_type not in VALID_SHEET_TYPES:
        errors.append({
            "level": "error",
            "check": "sheet_type_enum",
            "context": context,
            "message": f"Invalid sheet_type '{sheet_type}'. Valid: {sorted(VALID_SHEET_TYPES)}",
        })
    return errors


def check_field_sources(field_sources: dict[str, Any], context: str) -> list[dict[str, str]]:
    """检查 field_sources 的 source_ref 可解析 (6.3)."""
    errors: list[dict[str, str]] = []
    if not isinstance(field_sources, dict):
        errors.append({
            "level": "error",
            "check": "field_sources_format",
            "context": context,
            "message": "field_sources must be a dict",
        })
        return errors

    for field_id, contract in field_sources.items():
        if not isinstance(contract, dict):
            errors.append({
                "level": "error",
                "check": "field_source_entry",
                "context": f"{context}.{field_id}",
                "message": "field_source entry must be a dict",
            })
            continue

        source_ref = contract.get("source_ref")
        if source_ref is None:
            errors.append({
                "level": "error",
                "check": "source_ref_missing",
                "context": f"{context}.{field_id}",
                "message": "source_ref is missing",
            })
        elif not isinstance(source_ref, dict):
            errors.append({
                "level": "error",
                "check": "source_ref_not_dict",
                "context": f"{context}.{field_id}",
                "message": f"source_ref must be a dict, got {type(source_ref).__name__}",
            })
        elif "module" not in source_ref:
            errors.append({
                "level": "error",
                "check": "source_ref_no_module",
                "context": f"{context}.{field_id}",
                "message": "source_ref dict must contain 'module' key",
            })

    return errors


def check_no_generated_ref(schema_ref: str, context: str) -> list[dict[str, str]]:
    """检查 schema_ref 不指向 generated/*.yaml (6.4)."""
    errors: list[dict[str, str]] = []
    if schema_ref and "generated/" in schema_ref.replace("\\", "/"):
        errors.append({
            "level": "error",
            "check": "generated_as_production",
            "context": context,
            "message": f"schema_ref '{schema_ref}' points to generated/ directory. "
                       "Generated schemas must not be used as production source.",
        })
    return errors


# ---------------------------------------------------------------------------
# 主扫描
# ---------------------------------------------------------------------------

def scan_production_schemas() -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """扫描根目录生产 schema YAML 文件.

    Returns:
        (issues, schema_summaries)
    """
    issues: list[dict[str, str]] = []
    summaries: list[dict[str, Any]] = []

    if not SCHEMA_ROOT.exists():
        issues.append({
            "level": "warning",
            "check": "schema_root_missing",
            "context": str(SCHEMA_ROOT),
            "message": f"Schema root directory not found: {SCHEMA_ROOT}",
        })
        return issues, summaries

    yaml_files = sorted(SCHEMA_ROOT.glob("*.yaml"))
    for yaml_path in yaml_files:
        data = _load_yaml(yaml_path)
        if data is None:
            issues.append({
                "level": "warning",
                "check": "yaml_parse_failed",
                "context": yaml_path.name,
                "message": f"Failed to parse YAML: {yaml_path.name}",
            })
            continue

        summary: dict[str, Any] = {
            "file": yaml_path.name,
            "wp_code": data.get("wp_code", ""),
            "has_sheet_type": False,
            "sheet_type": None,
        }

        # 根级 sheet_type
        root_sheet_type = data.get("sheet_type")
        if root_sheet_type:
            summary["has_sheet_type"] = True
            summary["sheet_type"] = root_sheet_type
            issues.extend(check_sheet_type_validity(root_sheet_type, yaml_path.name))
        else:
            # 6.5: 缺失 sheet_type 输出 warning，不阻断
            issues.append({
                "level": "warning",
                "check": "missing_sheet_type",
                "context": yaml_path.name,
                "message": f"missing sheet_type, heuristic will be used",
            })

        # 检查 field_sources (如果在根级)
        root_field_sources = data.get("field_sources")
        if root_field_sources:
            issues.extend(check_field_sources(root_field_sources, yaml_path.name))

        # 检查 sheets 内部
        sheets = data.get("sheets")
        if isinstance(sheets, dict):
            for sheet_name, sheet_data in sheets.items():
                if not isinstance(sheet_data, dict):
                    continue
                sheet_field_sources = sheet_data.get("field_sources")
                if sheet_field_sources:
                    issues.extend(
                        check_field_sources(sheet_field_sources, f"{yaml_path.name}/{sheet_name}")
                    )

        summaries.append(summary)

    return issues, summaries


def scan_registry() -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """扫描 D1/D2 语义注册表.

    Returns:
        (issues, registry_summaries)
    """
    issues: list[dict[str, str]] = []
    summaries: list[dict[str, Any]] = []

    if not REGISTRY_PATH.exists():
        issues.append({
            "level": "warning",
            "check": "registry_missing",
            "context": str(REGISTRY_PATH),
            "message": f"Registry file not found: {REGISTRY_PATH}",
        })
        return issues, summaries

    registry = _load_json(REGISTRY_PATH)
    if registry is None:
        issues.append({
            "level": "error",
            "check": "registry_parse_failed",
            "context": str(REGISTRY_PATH),
            "message": "Failed to parse registry JSON",
        })
        return issues, summaries

    sheets = registry.get("sheets", {})
    if not isinstance(sheets, dict):
        issues.append({
            "level": "error",
            "check": "registry_sheets_format",
            "context": str(REGISTRY_PATH),
            "message": "registry.sheets must be a dict",
        })
        return issues, summaries

    for sheet_name, sheet_data in sheets.items():
        if not isinstance(sheet_data, dict):
            continue

        context = f"registry/{sheet_name}"
        summary: dict[str, Any] = {
            "sheet_name": sheet_name,
            "wp_code": sheet_data.get("wp_code", ""),
            "has_sheet_type": False,
            "sheet_type": None,
        }

        # 6.2: sheet_type 合法性
        sheet_type = sheet_data.get("sheet_type")
        if sheet_type:
            summary["has_sheet_type"] = True
            summary["sheet_type"] = sheet_type
            issues.extend(check_sheet_type_validity(sheet_type, context))
        else:
            issues.append({
                "level": "warning",
                "check": "missing_sheet_type",
                "context": context,
                "message": "missing sheet_type, heuristic will be used",
            })

        # 6.3: field_sources 检查
        field_sources = sheet_data.get("field_sources")
        if field_sources:
            issues.extend(check_field_sources(field_sources, context))

        # 6.4: schema_ref 不得指向 generated/
        schema_ref = sheet_data.get("schema_ref", "")
        if schema_ref:
            issues.extend(check_no_generated_ref(schema_ref, context))

        summaries.append(summary)

    return issues, summaries


def build_migration_report(
    schema_summaries: list[dict[str, Any]],
    registry_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    """构建 D1/D2 迁移报告 (6.6)."""
    # 统计
    total_schemas = len(schema_summaries)
    total_registry = len(registry_summaries)

    schemas_with_type = sum(1 for s in schema_summaries if s.get("has_sheet_type"))
    schemas_without_type = total_schemas - schemas_with_type

    registry_with_type = sum(1 for s in registry_summaries if s.get("has_sheet_type"))
    registry_without_type = total_registry - registry_with_type

    # 合并统计
    all_items = schema_summaries + registry_summaries
    total = len(all_items)
    has_explicit = sum(1 for s in all_items if s.get("has_sheet_type"))
    relies_on_heuristic = total - has_explicit

    # D1/D2 专项
    d1_items = [s for s in all_items if str(s.get("wp_code", "")).startswith("D1") or s.get("wp_code") == "D1" or "D1" in str(s.get("wp_code", ""))]
    d2_items = [s for s in all_items if str(s.get("wp_code", "")).startswith("D2") or s.get("wp_code") == "D2" or "D2" in str(s.get("wp_code", ""))]
    other_items = [s for s in all_items if s not in d1_items and s not in d2_items]

    d1_with_type = sum(1 for s in d1_items if s.get("has_sheet_type"))
    d2_with_type = sum(1 for s in d2_items if s.get("has_sheet_type"))
    other_with_type = sum(1 for s in other_items if s.get("has_sheet_type"))

    return {
        "summary": {
            "total_sheets": total,
            "has_explicit_sheet_type": has_explicit,
            "relies_on_heuristic": relies_on_heuristic,
            "unknown": 0,
        },
        "production_schemas": {
            "total": total_schemas,
            "with_sheet_type": schemas_with_type,
            "without_sheet_type": schemas_without_type,
        },
        "registry": {
            "total": total_registry,
            "with_sheet_type": registry_with_type,
            "without_sheet_type": registry_without_type,
        },
        "d1_d2_breakdown": {
            "d1": {"total": len(d1_items), "with_sheet_type": d1_with_type},
            "d2": {"total": len(d2_items), "with_sheet_type": d2_with_type},
            "other": {"total": len(other_items), "with_sheet_type": other_with_type},
        },
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def run_check(strict: bool = False) -> dict[str, Any]:
    """执行全部校验，返回 JSON 报告."""
    all_issues: list[dict[str, str]] = []

    # 1. 扫描生产 schema
    schema_issues, schema_summaries = scan_production_schemas()
    all_issues.extend(schema_issues)

    # 2. 扫描注册表
    registry_issues, registry_summaries = scan_registry()
    all_issues.extend(registry_issues)

    # 3. 构建迁移报告
    migration_report = build_migration_report(schema_summaries, registry_summaries)

    # 4. 分类统计
    errors = [i for i in all_issues if i["level"] == "error"]
    warnings = [i for i in all_issues if i["level"] == "warning"]

    report: dict[str, Any] = {
        "status": "pass",
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "migration_report": migration_report,
        "schemas_scanned": len(schema_summaries),
        "registry_entries_scanned": len(registry_summaries),
    }

    # 判定退出状态
    if errors:
        report["status"] = "fail"
    elif warnings:
        report["status"] = "warn"

    # strict 模式: 缺失 sheet_type 的 warning 升级为阻断
    if strict:
        missing_type_warnings = [
            w for w in warnings if w["check"] == "missing_sheet_type"
        ]
        if missing_type_warnings:
            report["status"] = "fail"
            report["strict_blocked"] = True
            report["strict_block_reason"] = (
                f"{len(missing_type_warnings)} schema(s) missing sheet_type "
                "(strict mode blocks on missing sheet_type for critical schemas)"
            )

    return report


def main() -> int:
    """CLI 入口."""
    parser = argparse.ArgumentParser(
        description="底稿语义 schema 校验 (check_wp_semantic_schema)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="P2 strict 模式：缺失 sheet_type 时 exit 1",
    )
    args = parser.parse_args()

    report = run_check(strict=args.strict)

    # 输出 JSON 报告到 stdout
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # 退出码
    if args.strict and report.get("status") == "fail":
        return 1
    # P0 模式总是 exit 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
