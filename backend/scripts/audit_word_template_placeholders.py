"""审计 word-template 底稿占位符覆盖率.

扫描所有注册为 word-template 的底稿模板文件，
解析占位符数量，标注哪些模板缺少占位符（结构化视图会退化为空）。

Usage:
    python -m scripts.audit_word_template_placeholders
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 项目根目录
BACKEND_ROOT = Path(__file__).resolve().parent.parent
WP_TEMPLATES_DIR = BACKEND_ROOT / "wp_templates"
OVERRIDES_FILE = BACKEND_ROOT / "app" / "data" / "wp_code_overrides.json"


def find_word_template_codes() -> list[str]:
    """从 wp_code_overrides.json 找所有映射为 word-template 的 wp_code."""
    with open(OVERRIDES_FILE, encoding="utf-8") as f:
        overrides = json.load(f)
    return [code for code, ct in overrides.items() if ct == "word-template"]


def find_template_file(wp_code: str) -> Path | None:
    """按 wp_code 查找对应的 docx 模板文件."""
    # 模板目录结构: wp_templates/{cycle}/{filename}.docx
    # cycle 取 wp_code 首字母(如 A/B/D)
    cycle = wp_code[0].upper()
    cycle_dir = WP_TEMPLATES_DIR / cycle
    if not cycle_dir.exists():
        return None

    # 尝试精确匹配文件名包含 wp_code
    for f in cycle_dir.rglob("*.docx"):
        if f.name.startswith("~"):
            continue  # skip temp files
        # 文件名可能是 "A8-1 管理层书面声明.docx" 或 "向治理层通报内控缺陷函.docx"
        if wp_code.replace("-", "") in f.stem.replace("-", "").replace(" ", ""):
            return f

    # 宽松匹配：按 wp_code 后缀部分匹配
    code_suffix = wp_code.split("-")[-1] if "-" in wp_code else wp_code
    for f in cycle_dir.rglob("*.docx"):
        if f.name.startswith("~"):
            continue
        if code_suffix in f.stem:
            return f

    return None


def count_placeholders(docx_path: Path) -> int:
    """解析 docx 文件，返回占位符数量."""
    try:
        sys.path.insert(0, str(BACKEND_ROOT))
        from app.services.wp_docx_template_parser import parse_template
        result = parse_template(str(docx_path))
        return len(result.placeholders) if result else 0
    except Exception as e:
        return -1  # parse error


def main():
    codes = find_word_template_codes()
    print(f"找到 {len(codes)} 个 word-template 底稿\n")
    print(f"{'wp_code':<12} {'占位符数':<8} {'模板文件':<50} {'状态'}")
    print("-" * 90)

    no_file = []
    no_placeholder = []
    ok = []

    for code in sorted(codes):
        path = find_template_file(code)
        if not path:
            print(f"{code:<12} {'—':<8} {'(模板文件未找到)':<50} ⚠️ 缺失")
            no_file.append(code)
            continue

        count = count_placeholders(path)
        rel_path = str(path.relative_to(BACKEND_ROOT))

        if count < 0:
            print(f"{code:<12} {'ERR':<8} {rel_path:<50} ❌ 解析失败")
            no_placeholder.append(code)
        elif count == 0:
            print(f"{code:<12} {count:<8} {rel_path:<50} ⚠️ 无占位符")
            no_placeholder.append(code)
        else:
            print(f"{code:<12} {count:<8} {rel_path:<50} ✅")
            ok.append(code)

    print("\n" + "=" * 90)
    print(f"汇总: ✅ 有占位符={len(ok)}, ⚠️ 无占位符={len(no_placeholder)}, 缺模板文件={len(no_file)}")
    if no_placeholder:
        print(f"\n需要补充占位符的模板:")
        for c in no_placeholder:
            print(f"  - {c}")
    if no_file:
        print(f"\n需要确认模板文件路径:")
        for c in no_file:
            print(f"  - {c}")


if __name__ == "__main__":
    main()
