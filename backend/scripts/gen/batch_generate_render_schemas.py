"""batch_generate_render_schemas.py — 批量生成 render_schema YAML 提升覆盖率

目标：从 workpaper_template_analysis.json 全量输入源（349 模板 / 2602 sheet），
批量生成缺失的 render_schema YAML 文件，将覆盖率从 ~55% 提升到 ≥80%。

输入源：
  .kiro/specs/_archive/07-workpaper-slimdown/workpaper-html-renderer/workpaper_template_analysis.json

输出：
  backend/data/wp_render_schema/generated/{wp_code}.yaml

策略：
  1. 加载 analysis JSON，遍历所有 template → sheets
  2. 对每个 wp_code，检查是否已有 yaml（手写 or generated）
  3. 缺失的按 class_code/componentType 生成最小可用 yaml
  4. 生成的 yaml 包含：meta / sheets / component_type / functional_type

用法：
    # 预览缺失的 wp_code
    python backend/scripts/gen/batch_generate_render_schemas.py --dry-run

    # 实际生成
    python backend/scripts/gen/batch_generate_render_schemas.py

    # 仅生成特定循环
    python backend/scripts/gen/batch_generate_render_schemas.py --cycle D

    # 统计覆盖率
    python backend/scripts/gen/batch_generate_render_schemas.py --stats-only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# ─── 路径 ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ANALYSIS_JSON_CANDIDATES = [
    REPO_ROOT / ".kiro" / "specs" / "_archive" / "07-workpaper-slimdown" / "workpaper-html-renderer" / "workpaper_template_analysis.json",
    REPO_ROOT / ".kiro" / "specs" / "_archive" / "07-workpaper-slimdown" / "workpaper-editor-slimdown" / "workpaper_template_analysis.json",
    REPO_ROOT / ".kiro" / "specs" / "workpaper-html-renderer" / "workpaper_template_analysis.json",
]
SCHEMA_DIR = REPO_ROOT / "backend" / "data" / "wp_render_schema"
GENERATED_DIR = SCHEMA_DIR / "generated"

# ─── componentType → YAML 模板 ───────────────────────────────────────────────

YAML_TEMPLATES: dict[str, str] = {
    "d-form-table": """# Auto-generated render_schema for {wp_code}
meta:
  wp_code: "{wp_code}"
  component_type: "d-form-table"
  generated: true
  functional_type: "{functional_type}"
sheets:
{sheets_yaml}
""",
    "d-form-review": """# Auto-generated render_schema for {wp_code}
meta:
  wp_code: "{wp_code}"
  component_type: "d-form-review"
  generated: true
  functional_type: "{functional_type}"
sheets:
{sheets_yaml}
""",
    "d-form-paragraph": """# Auto-generated render_schema for {wp_code}
meta:
  wp_code: "{wp_code}"
  component_type: "d-form-paragraph"
  generated: true
  functional_type: "{functional_type}"
sheets:
{sheets_yaml}
""",
    "d-form-qa": """# Auto-generated render_schema for {wp_code}
meta:
  wp_code: "{wp_code}"
  component_type: "d-form-qa"
  generated: true
  functional_type: "{functional_type}"
sheets:
{sheets_yaml}
""",
    "d-form-confirmation": """# Auto-generated render_schema for {wp_code}
meta:
  wp_code: "{wp_code}"
  component_type: "d-form-confirmation"
  generated: true
  functional_type: "{functional_type}"
sheets:
{sheets_yaml}
""",
    "a-program-console": """# Auto-generated render_schema for {wp_code}
meta:
  wp_code: "{wp_code}"
  component_type: "a-program-console"
  generated: true
sheets:
{sheets_yaml}
""",
    "b-index": """# Auto-generated render_schema for {wp_code}
meta:
  wp_code: "{wp_code}"
  component_type: "b-index"
  generated: true
sheets:
{sheets_yaml}
""",
    "c-note-table": """# Auto-generated render_schema for {wp_code}
meta:
  wp_code: "{wp_code}"
  component_type: "c-note-table"
  generated: true
sheets:
{sheets_yaml}
""",
    "e-control-test": """# Auto-generated render_schema for {wp_code}
meta:
  wp_code: "{wp_code}"
  component_type: "e-control-test"
  generated: true
sheets:
{sheets_yaml}
""",
    "h-static-doc": """# Auto-generated render_schema for {wp_code}
meta:
  wp_code: "{wp_code}"
  component_type: "h-static-doc"
  generated: true
sheets:
{sheets_yaml}
""",
    "univer": """# Auto-generated render_schema for {wp_code} (Univer mode)
meta:
  wp_code: "{wp_code}"
  component_type: "univer"
  generated: true
sheets:
{sheets_yaml}
""",
}

DEFAULT_TEMPLATE = """# Auto-generated render_schema for {wp_code}
meta:
  wp_code: "{wp_code}"
  component_type: "{component_type}"
  generated: true
sheets:
{sheets_yaml}
"""


def load_analysis_json() -> dict | None:
    """加载 workpaper_template_analysis.json"""
    for path in ANALYSIS_JSON_CANDIDATES:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def get_existing_schemas() -> set[str]:
    """获取已有 render_schema 的 wp_code 集合"""
    existing = set()
    if SCHEMA_DIR.exists():
        for f in SCHEMA_DIR.glob("*.yaml"):
            # 从文件名提取 wp_code（去掉前缀如 D-, C-, E-）
            stem = f.stem
            existing.add(stem)
    if GENERATED_DIR.exists():
        for f in GENERATED_DIR.glob("*.yaml"):
            existing.add(f.stem)
    return existing


def infer_functional_type_from_sheets(sheets: list[dict]) -> str:
    """从 sheet 列表推断 functional_type"""
    from backend.scripts.seed.infer_functional_type import infer_functional_type as _infer
    for s in sheets:
        ft = _infer(s.get("wp_code", ""), s.get("sheet_name", ""), s.get("class_code"))
        if ft:
            return ft
    return ""


def generate_sheet_yaml(sheets: list[dict]) -> str:
    """生成 sheets 部分的 YAML"""
    lines = []
    for s in sheets:
        sheet_name = s.get("sheet_name", "Sheet1")
        component_type = s.get("render", s.get("class_code", "d-form-table"))
        lines.append(f'  "{sheet_name}":')
        lines.append(f'    component_type: "{component_type}"')
        lines.append(f'    skip: false')
    return "\n".join(lines) if lines else '  "Sheet1":\n    component_type: "d-form-table"\n    skip: false'


def generate_schema_for_wp_code(
    wp_code: str,
    sheets: list[dict],
    primary_component_type: str,
) -> str:
    """为单个 wp_code 生成 render_schema YAML 内容"""
    sheets_yaml = generate_sheet_yaml(sheets)

    # 尝试推断 functional_type
    functional_type = ""
    try:
        # 简化推断（不依赖 backend import）
        for s in sheets:
            sn = s.get("sheet_name", "")
            if "截止" in sn or "cutoff" in sn.lower():
                functional_type = "cutoff"
                break
            elif "账龄" in sn or "aging" in sn.lower():
                functional_type = "aging"
                break
            elif "月度" in sn or "monthly" in sn.lower():
                functional_type = "monthly_analysis"
                break
            elif "抽凭" in sn or "抽样" in sn.lower():
                functional_type = "sampling"
                break
            elif "合同" in sn:
                functional_type = "contract_ledger"
                break
    except Exception:
        pass

    template = YAML_TEMPLATES.get(primary_component_type, DEFAULT_TEMPLATE)
    return template.format(
        wp_code=wp_code,
        component_type=primary_component_type,
        functional_type=functional_type,
        sheets_yaml=sheets_yaml,
    )


def main():
    parser = argparse.ArgumentParser(
        description="批量生成 render_schema YAML 提升覆盖率到 ≥80%"
    )
    parser.add_argument("--dry-run", action="store_true", help="仅预览不生成文件")
    parser.add_argument("--cycle", type=str, default=None, help="仅处理特定循环（如 D/E/F）")
    parser.add_argument("--stats-only", action="store_true", help="仅输出覆盖率统计")
    args = parser.parse_args()

    # 加载分析数据
    data = load_analysis_json()
    if not data:
        print("[ERROR] 未找到 workpaper_template_analysis.json")
        print("  候选路径:")
        for p in ANALYSIS_JSON_CANDIDATES:
            print(f"    {p} {'✓' if p.exists() else '✗'}")
        sys.exit(1)

    templates = data.get("templates", [])
    total_wp_codes: set[str] = set()
    wp_code_sheets: dict[str, list[dict]] = {}
    wp_code_component: dict[str, str] = {}

    # 收集所有 wp_code 及其 sheet 信息
    for tmpl in templates:
        wp_codes = tmpl.get("wp_codes", [])
        sheets = tmpl.get("sheets", [])
        for wc in wp_codes:
            if args.cycle and not wc.startswith(args.cycle):
                continue
            total_wp_codes.add(wc)
            wp_code_sheets[wc] = sheets
            # 取第一个 sheet 的 render/class_code 作为主 componentType
            if sheets:
                wp_code_component[wc] = sheets[0].get("render", sheets[0].get("class_code", "d-form-table"))

    # 获取已有 schema
    existing = get_existing_schemas()

    # 计算缺失
    missing = total_wp_codes - existing
    covered = total_wp_codes & existing

    # 统计
    total = len(total_wp_codes)
    coverage_before = len(covered) / total * 100 if total else 0
    coverage_after = (len(covered) + len(missing)) / total * 100 if total else 0

    print(f"\n[统计] render_schema 覆盖率分析")
    print(f"  总 wp_code 数: {total}")
    print(f"  已有 schema: {len(covered)} ({coverage_before:.1f}%)")
    print(f"  缺失 schema: {len(missing)}")
    print(f"  生成后覆盖率: {coverage_after:.1f}%")

    if args.stats_only:
        # 按循环分组统计
        cycle_stats: dict[str, dict[str, int]] = {}
        for wc in total_wp_codes:
            prefix = wc[0] if wc else "?"
            if prefix not in cycle_stats:
                cycle_stats[prefix] = {"total": 0, "covered": 0, "missing": 0}
            cycle_stats[prefix]["total"] += 1
            if wc in covered:
                cycle_stats[prefix]["covered"] += 1
            else:
                cycle_stats[prefix]["missing"] += 1

        print(f"\n  按循环分布:")
        for prefix in sorted(cycle_stats.keys()):
            s = cycle_stats[prefix]
            pct = s["covered"] / s["total"] * 100 if s["total"] else 0
            print(f"    {prefix}: {s['covered']}/{s['total']} ({pct:.0f}%) 缺 {s['missing']}")
        return

    if not missing:
        print("\n[OK] 所有 wp_code 已有 render_schema，无需生成")
        return

    if args.dry_run:
        print(f"\n[DRY-RUN] 将生成 {len(missing)} 个 YAML 文件:")
        for wc in sorted(missing)[:20]:
            ct = wp_code_component.get(wc, "d-form-table")
            print(f"    {wc}.yaml (component_type={ct})")
        if len(missing) > 20:
            print(f"    ... 及其他 {len(missing) - 20} 个")
        return

    # 实际生成
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    generated_count = 0
    errors = []

    for wc in sorted(missing):
        sheets = wp_code_sheets.get(wc, [])
        ct = wp_code_component.get(wc, "d-form-table")
        try:
            content = generate_schema_for_wp_code(wc, sheets, ct)
            output_path = GENERATED_DIR / f"{wc}.yaml"
            output_path.write_text(content, encoding="utf-8")
            generated_count += 1
        except Exception as e:
            errors.append(f"{wc}: {e}")

    print(f"\n[OK] 生成完成: {generated_count} 个 YAML 文件")
    if errors:
        print(f"[WARN] {len(errors)} 个错误:")
        for err in errors[:10]:
            print(f"    {err}")

    # 最终覆盖率
    final_coverage = (len(covered) + generated_count) / total * 100 if total else 0
    print(f"\n[结果] 覆盖率: {coverage_before:.1f}% → {final_coverage:.1f}%")
    if final_coverage >= 80:
        print("  ✓ 达到 ≥80% 目标")
    else:
        print(f"  ✗ 未达 80% 目标（差 {80 - final_coverage:.1f}%）")


if __name__ == "__main__":
    main()
