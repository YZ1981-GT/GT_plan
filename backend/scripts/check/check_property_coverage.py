"""Property 覆盖率双向核验工具

扫描 spec design.md 的 Property 列表与对应集成测试文件的 docstring `Validates: Property X`，
输出未覆盖清单 + 反向匹配漏报。

支持两种模式：
  1. 单 spec 模式：python check_property_coverage.py {spec_id}
  2. 全量模式：python check_property_coverage.py --all

输出：
  - design.md 列出的 Property → 测试文件 docstring（前向核验）
  - 测试文件 docstring 引用的 Property → design.md 是否存在（反向核验）
  - 输出 markdown 表格 + 退出码 0/1（OK / 有漏覆盖未在 design.md 标注）

Validates 标签格式（与本 spec 实施约定一致）：
  - design.md: `**Coverage: [Tested: test_xxx]**` 或 `**Coverage: [Pending: TD-N]**` 或 `**Coverage: [Skipped: 可选]**`
  - test docstring: `Validates: Property X (...)` 或 `Validates: Property X / Requirement Y`

CI 卡点策略：
  - design.md 中标 `[Tested: test_xxx]` 但实测 docstring 未引用 → FAIL
  - design.md 中无 Coverage 标签 → WARN（建议补全）
  - test docstring 引用 Property X 但 design.md 无该 Property → FAIL（编号错位）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Windows console GBK 兼容
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
SPECS_DIR = REPO_ROOT / ".kiro" / "specs"
TESTS_DIR = BACKEND_DIR / "tests"


# ─── 解析 design.md 的 Property 区块 ─────────────────────────────────────
# 格式：### Property N: <title>
# 后续行可能包含 **Coverage: [Tested: test_xxx]** 或 **Coverage: [Pending: TD-N]**
PROPERTY_RE = re.compile(r"^###\s+Property\s+(\d+):\s*(.+?)$", re.MULTILINE)
COVERAGE_RE = re.compile(
    r"\*\*Coverage:\s*\[(Tested|Pending|Skipped):\s*([^\]]+)\]\*\*"
)


def parse_design_properties(design_path: Path) -> dict[int, dict]:
    """从 design.md 提取 Property 编号 + 标题 + Coverage 标签。"""
    if not design_path.exists():
        return {}
    text = design_path.read_text(encoding="utf-8")
    properties: dict[int, dict] = {}

    # 找出所有 Property 区块（通过下个 Property 或末尾切分）
    matches = list(PROPERTY_RE.finditer(text))
    for i, m in enumerate(matches):
        prop_num = int(m.group(1))
        prop_title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        cov_match = COVERAGE_RE.search(block)
        if cov_match:
            cov_kind = cov_match.group(1)  # Tested / Pending / Skipped
            cov_value = cov_match.group(2).strip()  # test_xxx 或 TD-N
        else:
            cov_kind = None
            cov_value = None
        properties[prop_num] = {
            "title": prop_title,
            "coverage_kind": cov_kind,
            "coverage_value": cov_value,
        }
    return properties


# ─── 解析测试文件 docstring 引用的 Property ──────────────────────────────
# 格式：Validates: Property X (...) 或 Validates: Property X / Requirement Y
VALIDATES_RE = re.compile(r"Validates:\s*(?:[^\n]*?)Property\s+(\d+)")
# 函数定义识别（async def / def）
FUNC_RE = re.compile(r"^(?:async\s+)?def\s+(test_\w+)\s*\(", re.MULTILINE)


def parse_test_validates(test_files: list[Path]) -> dict[str, list[int]]:
    """扫描测试文件 docstring，返回 {test_func_name: [property_num, ...]}。"""
    result: dict[str, list[int]] = {}
    for tf in test_files:
        if not tf.exists():
            continue
        text = tf.read_text(encoding="utf-8")
        for fm in FUNC_RE.finditer(text):
            func_name = fm.group(1)
            # 取函数体头部 30 行作为 docstring 搜索范围
            start = fm.end()
            sample = text[start:start + 2000]
            # docstring 区分（"""..."""）
            ds_match = re.search(r'"""(.+?)"""', sample, flags=re.DOTALL)
            if not ds_match:
                continue
            docstring = ds_match.group(1)
            props = [int(p) for p in VALIDATES_RE.findall(docstring)]
            if props:
                result[func_name] = props
    return result


# ─── 核验主逻辑 ─────────────────────────────────────────────────────────
def verify_spec(spec_id: str, test_globs: list[str] | None = None) -> int:
    spec_dir = SPECS_DIR / spec_id
    design_path = spec_dir / "design.md"
    if not design_path.exists():
        print(f"[SKIP] {spec_id}: design.md 不存在")
        return 0

    properties = parse_design_properties(design_path)
    if not properties:
        print(f"[SKIP] {spec_id}: design.md 中无 Property 区块")
        return 0

    # 扫描相关测试文件（默认 backend/tests/test_*{spec_id}*.py，可显式传入）
    if test_globs:
        test_files = []
        for pattern in test_globs:
            test_files += list(TESTS_DIR.glob(pattern))
    else:
        # 默认按 spec_id 包含的关键词模糊匹配（如 template_library / audit_chain）
        # 取 spec_id 第一段作为关键词
        keyword = spec_id.split("-")[0]
        test_files = list(TESTS_DIR.glob(f"test_*{keyword}*.py"))
        # 加上集成测试目录
        integration_dir = TESTS_DIR / "integration"
        if integration_dir.exists():
            test_files += list(integration_dir.glob(f"test_*{keyword}*.py"))

    if not test_files:
        print(f"[WARN] {spec_id}: 未找到匹配的测试文件（关键词 '{keyword}'）")
        # 仍然展示 Property 清单
        test_validates: dict[str, list[int]] = {}
    else:
        test_validates = parse_test_validates(test_files)

    # 反向构建：Property X → [test_xxx, ...]
    actual_coverage: dict[int, list[str]] = {}
    for func, props in test_validates.items():
        for p in props:
            actual_coverage.setdefault(p, []).append(func)

    print(f"\n## Property 覆盖核验：{spec_id}")
    print(f"design.md: {design_path.relative_to(REPO_ROOT)}")
    print(f"扫描测试文件: {[str(t.relative_to(REPO_ROOT)) for t in test_files]}\n")

    print("| Property | Title | design.md 标记 | 实测 docstring | 状态 |")
    print("|---|---|---|---|---|")

    fail_count = 0
    warn_count = 0
    ok_count = 0

    for num in sorted(properties.keys()):
        info = properties[num]
        title = info["title"][:40]
        cov_kind = info["coverage_kind"]
        cov_value = info["coverage_value"]
        actual = actual_coverage.get(num, [])

        # 判定状态
        if cov_kind is None:
            status = "⚠ WARN"
            note = "design.md 无 Coverage 标签"
            warn_count += 1
        elif cov_kind == "Tested":
            # design.md 声称已测，实测 docstring 必须引用
            # 三轮复盘 P1.5 升级：cov_value 可能是逗号分隔多测试名 (如 "test_a, test_b")
            # 拆分后逐个匹配，至少一个实测命中即视为 OK
            declared_tests = [t.strip() for t in cov_value.split(",") if t.strip()]
            if not actual:
                status = "✗ FAIL"
                note = f"design.md 声称 [Tested: {cov_value}] 但无 docstring 引用 Property {num}"
                fail_count += 1
            else:
                # 检查每个声称的测试名是否存在于实测列表
                missing = [t for t in declared_tests if t not in actual and not any(t in a for a in actual)]
                if not missing:
                    status = "✓ OK"
                    note = f"匹配 {actual}（声称 {len(declared_tests)} 个测试全部存在）"
                    ok_count += 1
                elif len(missing) < len(declared_tests):
                    # 部分匹配：至少一个测试存在
                    status = "⚠ WARN"
                    note = f"声称 {len(declared_tests)} 个测试中 {len(missing)} 个未在 docstring 找到: {missing}（实测 {actual}）"
                    warn_count += 1
                else:
                    # 全部声称的测试都不在 docstring 中
                    status = "⚠ WARN"
                    note = f"声称的测试 {declared_tests} 与实测不符（实测 {actual}）"
                    warn_count += 1
        elif cov_kind in ("Pending", "Skipped"):
            # 不要求实测
            status = "○ Pending"
            note = f"[{cov_kind}: {cov_value}]"
            if actual:
                # design.md 标 pending 但实测有覆盖 → 反向漏报
                status = "⚠ WARN"
                note = f"design.md 标 {cov_kind} 但实测 {actual} 已覆盖，应升级为 [Tested]"
                warn_count += 1
            else:
                ok_count += 1
        else:
            status = "?"
            note = ""

        cov_display = f"[{cov_kind}: {cov_value}]" if cov_kind else "—"
        actual_display = ",".join(actual) if actual else "—"
        print(f"| {num} | {title} | {cov_display} | {actual_display} | {status} |")
        if note:
            print(f"|  | _{note}_ |  |  |  |")

    # 反向核验：测试 docstring 引用了 design.md 没有的 Property
    print("\n## 反向核验：测试 docstring 引用未在 design.md 定义的 Property")
    orphan_found = False
    for func, props in test_validates.items():
        for p in props:
            if p not in properties:
                print(f"  ✗ FAIL: {func} 引用 Property {p}，但 design.md 无该编号")
                fail_count += 1
                orphan_found = True
    if not orphan_found:
        print("  ✓ 全部引用编号正确")

    print("\n## 汇总")
    print(f"  ✓ OK    : {ok_count}")
    print(f"  ⚠ WARN  : {warn_count}")
    print(f"  ✗ FAIL  : {fail_count}")
    total_props = len(properties)
    tested = sum(1 for p in properties.values() if p["coverage_kind"] == "Tested")
    print(f"\n  覆盖率：{tested}/{total_props} = {tested * 100 // total_props if total_props else 0}%")

    if fail_count > 0:
        print("\n  ✗ 存在 FAIL — Property 编号错位 / design.md 声称已测但 docstring 缺引用")
        return 1
    if warn_count > 0:
        print("\n  ⚠ 存在 WARN — 建议补全 Coverage 标签或调整 docstring")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Property 覆盖率双向核验")
    parser.add_argument("spec_id", nargs="?", help="spec 目录名")
    parser.add_argument("--all", action="store_true", help="核验全部 spec")
    parser.add_argument(
        "--test-glob",
        action="append",
        default=None,
        help="自定义测试文件 glob（可多次指定，相对 backend/tests/）",
    )
    args = parser.parse_args()

    if args.all:
        worst = 0
        for sub in sorted(SPECS_DIR.glob("*/design.md")):
            spec_id = sub.parent.name
            print("\n" + "=" * 80)
            print(f"# {spec_id}")
            print("=" * 80)
            code = verify_spec(spec_id, args.test_glob)
            worst = max(worst, code)
        return worst

    if not args.spec_id:
        parser.print_help()
        return 2

    return verify_spec(args.spec_id, args.test_glob)


if __name__ == "__main__":
    sys.exit(main())
