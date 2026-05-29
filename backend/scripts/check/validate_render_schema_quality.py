"""render_schema 质量验证脚本

验证 workpaper_template_analysis.json 中每个 sheet 的 render 字段
与对应 yaml 中 component_type 的一致性。

用法:
    python backend/scripts/_validate_render_schema_quality.py --cycle A
    python backend/scripts/_validate_render_schema_quality.py --cycle all
    python backend/scripts/_validate_render_schema_quality.py --cycle A --verbose

退出码:
    0 = 所有非 PENDING sheet 匹配
    1 = 存在真实 mismatch（非 PENDING）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ─── render 字段 → componentType 映射 ───────────────────────────────────────
RENDER_TO_COMPONENT: dict[str, str] = {
    "HTML 中控台": "a-program-console",
    "HTML 表单（编制信息+索引导航）": "b-index",
    "HTML 嵌套表（多级子表）": "c-note-table",
    "HTML 表单（表格型检查）": "d-form-table",
    "HTML 表单（专属子组件）": "d-form-confirmation",
    "HTML 表单（电子签）": "d-form-review",
    "HTML 段落型": "d-form-paragraph",
    "HTML 是否问答型": "d-form-qa",
    "HTML 表单": "e-control-test",
    "HTML stepper": "e-control-test",
    "保留 Univer": "univer",
    "保留 Univer（测算）": "univer",
    "跳过渲染": "skip",
    "PENDING-待人工归类": "pending",
    "静态展示": "h-static-doc",
}

# wp_code 提取正则（与 generate_wp_render_schema.py 一致）
# 支持多级子序号：A17-5-1, B22A-4-4-1, D2-1 等
_WP_CODE_PATTERN = re.compile(r"^([A-Z]\d+[A-Z]?(?:-\d+)*)")


def extract_wp_code_from_filename(filename: str) -> str | None:
    """从模板文件名提取完整 wp_code"""
    m = _WP_CODE_PATTERN.match(filename)
    if m:
        return m.group(1)
    return None


def load_analysis_json(json_path: Path) -> dict:
    """加载 workpaper_template_analysis.json"""
    return json.loads(json_path.read_text(encoding="utf-8"))


def load_all_yaml_schemas(schema_dir: Path) -> dict[str, dict]:
    """加载所有 yaml schema（手写优先于 generated）

    返回 {wp_code: {sheet_name: component_type}}
    """
    try:
        import yaml
    except ImportError:
        print("ERROR: PyYAML not installed. Run: pip install pyyaml")
        sys.exit(1)

    schemas: dict[str, dict] = {}

    # 1. 先加载 generated（低优先级）
    generated_dir = schema_dir / "generated"
    if generated_dir.exists():
        for yaml_path in sorted(generated_dir.glob("*.yaml")):
            _load_single_yaml(yaml_path, schemas, yaml)

    # 2. 再加载手写（高优先级，覆盖 generated）
    for yaml_path in sorted(schema_dir.glob("*.yaml")):
        _load_single_yaml(yaml_path, schemas, yaml)

    return schemas


def _load_single_yaml(yaml_path: Path, schemas: dict, yaml_module) -> None:
    """解析单个 yaml 文件，提取 sheets 的 component_type"""
    try:
        data = yaml_module.safe_load(yaml_path.read_text(encoding="utf-8"))
    except Exception:
        return

    if not data or not isinstance(data, dict):
        return

    wp_code = data.get("wp_code", yaml_path.stem)
    sheets_data = data.get("sheets", {})
    if not isinstance(sheets_data, dict):
        return

    sheet_map: dict[str, str] = {}
    for sheet_name, sheet_config in sheets_data.items():
        if isinstance(sheet_config, dict):
            ct = sheet_config.get("component_type", "")
            if ct:
                sheet_map[sheet_name] = ct

    if sheet_map:
        schemas[wp_code] = sheet_map


def validate_cycle(
    cycle_key: str,
    analysis_data: dict,
    yaml_schemas: dict[str, dict],
    verbose: bool = False,
) -> tuple[int, int, int, int, list[dict]]:
    """验证指定循环的所有 sheet

    Returns:
        (total_sheets, matches, mismatches, pending_count, mismatch_details)
    """
    cycle_data = analysis_data["cycles"].get(cycle_key)
    if not cycle_data:
        print(f"WARNING: cycle '{cycle_key}' not found in analysis JSON")
        return 0, 0, 0, 0, []

    total = 0
    matches = 0
    mismatches = 0
    pending = 0
    details: list[dict] = []

    for template in cycle_data["templates"]:
        filename = template["filename"]
        wp_code = extract_wp_code_from_filename(filename)
        if not wp_code:
            if verbose:
                print(f"  SKIP: cannot extract wp_code from '{filename}'")
            continue

        yaml_sheet_map = yaml_schemas.get(wp_code, {})

        for sheet in template["sheets"]:
            sheet_name = sheet["name"]
            render_value = sheet["render"]
            expected_ct = RENDER_TO_COMPONENT.get(render_value)

            if expected_ct is None:
                # Unknown render value
                details.append({
                    "wp_code": wp_code,
                    "sheet": sheet_name,
                    "render": render_value,
                    "expected": "UNKNOWN_MAPPING",
                    "actual": yaml_sheet_map.get(sheet_name, "NOT_IN_YAML"),
                    "status": "unknown_render",
                })
                mismatches += 1
                total += 1
                continue

            if expected_ct == "pending":
                pending += 1
                total += 1
                continue

            total += 1
            actual_ct = yaml_sheet_map.get(sheet_name)

            if actual_ct is None:
                # Sheet not found in yaml
                details.append({
                    "wp_code": wp_code,
                    "sheet": sheet_name,
                    "render": render_value,
                    "expected": expected_ct,
                    "actual": "NOT_IN_YAML",
                    "status": "missing",
                })
                mismatches += 1
            elif actual_ct == expected_ct:
                matches += 1
                if verbose:
                    print(f"  ✓ {wp_code}/{sheet_name}: {actual_ct}")
            else:
                details.append({
                    "wp_code": wp_code,
                    "sheet": sheet_name,
                    "render": render_value,
                    "expected": expected_ct,
                    "actual": actual_ct,
                    "status": "mismatch",
                })
                mismatches += 1

    return total, matches, mismatches, pending, details


def main():
    parser = argparse.ArgumentParser(description="验证 render_schema yaml 质量")
    parser.add_argument(
        "--cycle",
        default="A",
        help="要验证的循环代号（A/B/C/.../N/S/all），默认 A",
    )
    parser.add_argument(
        "--analysis-json",
        default=".kiro/specs/workpaper-editor-slimdown/workpaper_template_analysis.json",
        help="分析 JSON 文件路径",
    )
    parser.add_argument(
        "--schema-dir",
        default="backend/data/wp_render_schema",
        help="render_schema yaml 目录",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="显示每个匹配详情")
    args = parser.parse_args()

    # 确定项目根目录
    script_path = Path(__file__).resolve()
    # 脚本在 backend/scripts/ 下，项目根在上两级
    project_root = script_path.parent.parent.parent
    
    analysis_path = project_root / args.analysis_json
    schema_dir = project_root / args.schema_dir

    if not analysis_path.exists():
        print(f"ERROR: analysis JSON not found: {analysis_path}")
        sys.exit(1)
    if not schema_dir.exists():
        print(f"ERROR: schema dir not found: {schema_dir}")
        sys.exit(1)

    print(f"Loading analysis JSON: {analysis_path.name}")
    analysis_data = load_analysis_json(analysis_path)
    print(f"  Total templates: {analysis_data['meta']['total_xlsx']}")
    print(f"  Total sheets: {analysis_data['meta']['total_sheets']}")

    print(f"\nLoading yaml schemas from: {schema_dir}")
    yaml_schemas = load_all_yaml_schemas(schema_dir)
    print(f"  Loaded {len(yaml_schemas)} wp_code schemas")

    # 确定要验证的循环
    if args.cycle.lower() == "all":
        cycles_to_check = list(analysis_data["cycles"].keys())
    else:
        cycles_to_check = [args.cycle]

    print(f"\n{'='*60}")
    print(f"验证循环: {', '.join(cycles_to_check)}")
    print(f"{'='*60}")

    grand_total = 0
    grand_matches = 0
    grand_mismatches = 0
    grand_pending = 0
    all_details: list[dict] = []

    for cycle_key in cycles_to_check:
        total, matches, mismatches, pending, details = validate_cycle(
            cycle_key, analysis_data, yaml_schemas, verbose=args.verbose
        )
        grand_total += total
        grand_matches += matches
        grand_mismatches += mismatches
        grand_pending += pending
        all_details.extend(details)

        status_icon = "✓" if mismatches == 0 else "✗"
        print(f"\n  [{status_icon}] Cycle {cycle_key}: "
              f"{total} sheets checked | "
              f"{matches} matches | "
              f"{mismatches} mismatches | "
              f"{pending} pending")

    # 汇总
    print(f"\n{'='*60}")
    print(f"汇总结果:")
    print(f"  总 sheet 数（含 pending）: {grand_total + grand_pending}")
    print(f"  已检查（非 pending）: {grand_total}")
    print(f"  匹配: {grand_matches}")
    print(f"  不匹配: {grand_mismatches}")
    print(f"  PENDING（跳过）: {grand_pending}")
    if grand_total > 0:
        rate = grand_matches / grand_total * 100
        print(f"  匹配率: {rate:.1f}%")
    print(f"{'='*60}")

    # 输出 mismatch 详情
    if all_details:
        print(f"\n不匹配详情（共 {len(all_details)} 条）:")
        print(f"{'─'*80}")
        # 按状态分组
        missing_details = [d for d in all_details if d["status"] == "missing"]
        mismatch_details = [d for d in all_details if d["status"] == "mismatch"]
        unknown_details = [d for d in all_details if d["status"] == "unknown_render"]

        if mismatch_details:
            print(f"\n  类型不匹配（yaml 存在但 component_type 不对）: {len(mismatch_details)} 条")
            for d in mismatch_details[:20]:
                print(f"    {d['wp_code']}/{d['sheet']}")
                print(f"      render='{d['render']}' → expected={d['expected']}, actual={d['actual']}")

        if missing_details:
            print(f"\n  yaml 中缺失 sheet: {len(missing_details)} 条")
            for d in missing_details[:20]:
                print(f"    {d['wp_code']}/{d['sheet']}")
                print(f"      render='{d['render']}' → expected={d['expected']}")
            if len(missing_details) > 20:
                print(f"    ... 还有 {len(missing_details) - 20} 条未显示")

        if unknown_details:
            print(f"\n  未知 render 值: {len(unknown_details)} 条")
            for d in unknown_details[:10]:
                print(f"    {d['wp_code']}/{d['sheet']}: render='{d['render']}'")

    # 退出码
    if grand_mismatches > 0:
        print(f"\n❌ 验证失败: {grand_mismatches} 个非 PENDING sheet 不匹配")
        sys.exit(1)
    else:
        print(f"\n✅ 验证通过: 所有非 PENDING sheet 的 componentType 匹配正确")
        sys.exit(0)


if __name__ == "__main__":
    main()
