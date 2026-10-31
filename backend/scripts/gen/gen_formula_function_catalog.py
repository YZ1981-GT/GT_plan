"""生成前端公式函数目录 ``formulaFunctionCatalog.ts``（S1 ADR-FGR-01）。

用法::

    python backend/scripts/gen/gen_formula_function_catalog.py          # 写文件
    python backend/scripts/gen/gen_formula_function_catalog.py --check   # 只比对，不写

输出无时间戳，``--check`` 有差异时退出码 2 并列出差异行。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # 仓库根
BACKEND = ROOT / "backend"
OUTPUT = ROOT / "audit-platform" / "frontend" / "src" / "generated" / "formulaFunctionCatalog.ts"

sys.path.insert(0, str(BACKEND))


def _generate() -> str:
    from app.services.formula_function_catalog import FUNCTIONS, OPERATORS

    lines: list[str] = [
        "// @generated DO NOT EDIT — 由 gen_formula_function_catalog.py 生成",
        "// spec: formula-grammar-resolver-unification · S1 ADR-FGR-01",
        "",
        "export type FormulaEngine = 'l1' | 'note' | 'cell'",
        "",
        "export interface FunctionSpec {",
        "  name: string",
        "  arityMin: number",
        "  arityMax: number | null",
        "  engines: readonly FormulaEngine[]",
        "  category: string",
        "  syntax: string",
        "  description: string",
        "}",
        "",
        "export const FUNCTIONS: readonly FunctionSpec[] = [",
    ]

    for f in FUNCTIONS:
        engines_str = ", ".join(f"'{e}'" for e in sorted(f.engines))
        max_str = "null" if f.arity_max is None else str(f.arity_max)
        lines.append(
            f"  {{ name: '{f.name}', arityMin: {f.arity_min}, arityMax: {max_str}, "
            f"engines: [{engines_str}], category: '{f.category}', "
            f"syntax: '{_escape(f.syntax)}', description: '{_escape(f.description)}' }},"
        )

    lines.append("] as const")
    lines.append("")

    # 按引擎的函数名集合
    lines.append("/** 按引擎取函数名集合 */")
    lines.append("export const FUNCTION_NAMES_BY_ENGINE: Record<FormulaEngine, ReadonlySet<string>> = {")
    for engine in ("l1", "note", "cell"):
        names = sorted(f.name for f in FUNCTIONS if engine in f.engines)
        names_str = ", ".join(f"'{n}'" for n in names)
        lines.append(f"  {engine}: new Set([{names_str}]),")
    lines.append("}")
    lines.append("")

    # 按引擎的参数范围
    lines.append("/** 按引擎取参数范围 [min, max] */")
    lines.append("export const ARITY_BY_ENGINE: Record<FormulaEngine, Record<string, [number, number | null]>> = {")
    for engine in ("l1", "note", "cell"):
        lines.append(f"  {engine}: {{")
        for f in sorted(FUNCTIONS, key=lambda x: x.name):
            if engine in f.engines:
                max_str = "null" if f.arity_max is None else str(f.arity_max)
                lines.append(f"    {f.name}: [{f.arity_min}, {max_str}],")
        lines.append("  },")
    lines.append("}")
    lines.append("")

    # 运算符
    lines.append("/** 按引擎取运算符集合 */")
    lines.append("export const OPERATORS_BY_ENGINE: Record<FormulaEngine, ReadonlySet<string>> = {")
    for engine in ("l1", "note", "cell"):
        ops = sorted(o.symbol for o in OPERATORS if engine in o.engines)
        ops_str = ", ".join(f"'{o}'" for o in ops)
        lines.append(f"  {engine}: new Set([{ops_str}]),")
    lines.append("}")
    lines.append("")

    # 函数提示（按引擎分组）
    lines.append("/** 函数提示列表（用于自动补全） */")
    lines.append("export const FUNCTION_HINTS_BY_ENGINE: Record<FormulaEngine, readonly { name: string; minArgs: number; maxArgs: number | null; description: string }[]> = {")
    for engine in ("l1", "note", "cell"):
        lines.append(f"  {engine}: [")
        for f in sorted(FUNCTIONS, key=lambda x: x.name):
            if engine in f.engines:
                max_str = "null" if f.arity_max is None else str(f.arity_max)
                lines.append(
                    f"    {{ name: '{f.name}', minArgs: {f.arity_min}, maxArgs: {max_str}, "
                    f"description: \"{_escape_dq(f.syntax)}\" }},"
                )
        lines.append("  ],")
    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def _escape(s: str) -> str:
    """转义单引号和反斜杠。"""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _escape_dq(s: str) -> str:
    """转义双引号和反斜杠。"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def main() -> None:
    parser = argparse.ArgumentParser(description="生成前端公式函数目录")
    parser.add_argument("--check", action="store_true", help="只比对，不写文件")
    args = parser.parse_args()

    content = _generate()

    if args.check:
        if not OUTPUT.exists():
            print(f"ERROR: {OUTPUT} 不存在", file=sys.stderr)
            sys.exit(2)
        existing = OUTPUT.read_text(encoding="utf-8")
        if existing == content:
            print(f"✓ {OUTPUT.name} 与目录一致")
            sys.exit(0)
        else:
            # 找差异行
            old_lines = existing.split("\n")
            new_lines = content.split("\n")
            diffs = []
            for i, (o, n) in enumerate(zip(old_lines, new_lines)):
                if o != n:
                    diffs.append(f"  L{i+1}: -{o}")
                    diffs.append(f"  L{i+1}: +{n}")
            if len(old_lines) != len(new_lines):
                diffs.append(f"  行数: {len(old_lines)} -> {len(new_lines)}")
            print(f"ERROR: {OUTPUT.name} 与目录不一致（{len(diffs)} 处差异）：", file=sys.stderr)
            for d in diffs[:20]:
                print(d, file=sys.stderr)
            sys.exit(2)
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(content, encoding="utf-8")
        print(f"✓ 已写入 {OUTPUT}（{len(content)} 字节）")


if __name__ == "__main__":
    main()
