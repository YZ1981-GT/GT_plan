"""
Formula Runtime Convergence — 完成度真实性守卫

检查内容:
1. tasks.md 18 个叶子任务全部 [x]
2. PG integration 测试文件存在且非空
3. Playwright E2E 测试文件存在且非空
4. 禁止默认 skip / catch-swallow-ignore / 空断言反模式
5. single-kernel consumer drift 守卫（无新增绕过单一内核的 evaluator）

用法:
    python backend/scripts/check/check_formula_runtime_completion.py --strict

--strict: 全部检查通过返回 exit 0，任一失败返回 exit 1
无 --strict: 输出报告但始终 exit 0（报告模式）
"""
import sys
import os
import re
from pathlib import Path

# Windows GBK console 兼容
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ─── 路径常量 ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[3]  # GT_plan 根目录
SPEC_DIR = ROOT / ".kiro" / "specs" / "formula-runtime-convergence"
TASKS_MD = SPEC_DIR / "tasks.md"

# 证据文件
PG_INTEGRATION_DIR = ROOT / "backend" / "tests" / "formula_runtime" / "integration"
PG_INTEGRATION_CONFTEST = PG_INTEGRATION_DIR / "conftest.py"
PG_INTEGRATION_TEST = PG_INTEGRATION_DIR / "test_formula_runtime_roundtrip.py"
PLAYWRIGHT_E2E = ROOT / "audit-platform" / "frontend" / "tests" / "e2e" / "draft-refresh-regression.spec.ts"

# single-kernel 守卫扫描路径
BACKEND_APP = ROOT / "backend" / "app"
ENGINE_FILE = BACKEND_APP / "services" / "formula_management" / "engine.py"

# ─── 检查结果收集 ──────────────────────────────────────────────────────────────

failures: list[str] = []
warnings: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


# ─── 检查 1: 叶子任务全部 [x] ─────────────────────────────────────────────────

def check_all_tasks_complete() -> None:
    """验证 tasks.md 中 18 个顶层任务全部标记为 [x]。"""
    if not TASKS_MD.exists():
        fail(f"tasks.md 不存在: {TASKS_MD}")
        return

    content = TASKS_MD.read_text(encoding="utf-8")
    # 匹配顶层任务行: "- [x] N." 或 "- [ ] N." 或 "- [-] N."
    task_pattern = re.compile(r"^- \[(.)\] (\d+)\.", re.MULTILINE)
    matches = task_pattern.findall(content)

    if not matches:
        fail("tasks.md 中未找到任何顶层任务标记")
        return

    task_numbers = set()
    incomplete_tasks = []
    for mark, num in matches:
        task_numbers.add(int(num))
        if mark != "x":
            incomplete_tasks.append(f"Task {num} (mark='{mark}')")

    # 验证找到 18 个任务
    expected_count = 18
    if len(task_numbers) < expected_count:
        fail(f"tasks.md 中只找到 {len(task_numbers)} 个任务（预期 {expected_count}）: {sorted(task_numbers)}")

    if incomplete_tasks:
        fail(f"以下任务未完成: {', '.join(incomplete_tasks)}")
    else:
        print(f"  [OK] 全部 {len(task_numbers)} 个顶层任务已标记 [x]")


# ─── 检查 2: PG integration 证据 ──────────────────────────────────────────────

def check_pg_integration_evidence() -> None:
    """验证 PostgreSQL integration 测试文件存在且有实质内容。"""
    if not PG_INTEGRATION_DIR.exists():
        fail(f"PG integration 目录不存在: {PG_INTEGRATION_DIR}")
        return

    missing = []
    for f in [PG_INTEGRATION_CONFTEST, PG_INTEGRATION_TEST]:
        if not f.exists():
            missing.append(str(f.relative_to(ROOT)))
        elif f.stat().st_size < 100:
            missing.append(f"{f.relative_to(ROOT)} (文件过小，疑似空壳)")

    if missing:
        fail(f"PG integration 证据缺失: {missing}")
    else:
        # 检查 test 文件中是否有真实断言
        test_content = PG_INTEGRATION_TEST.read_text(encoding="utf-8")
        assert_count = test_content.count("assert ")
        if assert_count < 3:
            fail(f"PG integration 测试断言不足 (仅 {assert_count} 处 assert)")
        else:
            print(f"  [OK] PG integration 测试存在且含 {assert_count} 处断言")


# ─── 检查 3: Playwright E2E 证据 ──────────────────────────────────────────────

def check_playwright_evidence() -> None:
    """验证 Playwright E2E 测试文件存在且有实质内容。"""
    if not PLAYWRIGHT_E2E.exists():
        fail(f"Playwright E2E 文件不存在: {PLAYWRIGHT_E2E}")
        return

    content = PLAYWRIGHT_E2E.read_text(encoding="utf-8")
    if len(content) < 200:
        fail(f"Playwright E2E 文件过小 ({len(content)} bytes)，疑似空壳")
        return

    # 检查是否有真实 test/expect
    test_count = len(re.findall(r"\btest\s*\(", content))
    expect_count = content.count("expect(") + content.count("expect (")

    if test_count < 1:
        fail("Playwright E2E 文件中未找到 test() 定义")
    elif expect_count < 2:
        fail(f"Playwright E2E 断言不足 (仅 {expect_count} 处 expect)")
    else:
        print(f"  [OK] Playwright E2E 存在且含 {test_count} 个 test、{expect_count} 处 expect")


# ─── 检查 4: 禁止默认 skip / 吞错 / 空断言 ──────────────────────────────────

# 禁止模式
FORBIDDEN_PATTERNS = [
    # 默认 skip / fixme
    (re.compile(r"\.skip\s*\(", re.MULTILINE), "默认 .skip()"),
    (re.compile(r"test\.fixme\s*\(", re.MULTILINE), "test.fixme()"),
    # catch 吞错 (空 catch 块)
    (re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}", re.MULTILINE), "空 catch 块 (吞错)"),
    (re.compile(r"\.catch\s*\(\s*\(\s*\)\s*=>\s*\{\s*\}\s*\)", re.MULTILINE), ".catch(() => {}) 吞错"),
    # 空断言 (test 函数体无 assert/expect)
    (re.compile(r"def test_\w+\([^)]*\):\s*\n\s*pass\b", re.MULTILINE), "空 test 函数体 (pass)"),
]

SCAN_FILES = [
    PG_INTEGRATION_TEST,
    PLAYWRIGHT_E2E,
]


def check_forbidden_patterns() -> None:
    """扫描证据文件中的禁止模式。"""
    violations = []

    for filepath in SCAN_FILES:
        if not filepath.exists():
            continue
        content = filepath.read_text(encoding="utf-8")
        rel_path = filepath.relative_to(ROOT)

        for pattern, description in FORBIDDEN_PATTERNS:
            matches = pattern.findall(content)
            if matches:
                violations.append(f"  {rel_path}: {description} ({len(matches)} 处)")

    if violations:
        fail("检测到禁止模式:\n" + "\n".join(violations))
    else:
        print("  [OK] 证据文件无默认 skip / 吞错 / 空断言")


# ─── 检查 5: single-kernel consumer drift ─────────────────────────────────────

# 对齐 test_single_kernel_guard.py 的逻辑：
# 保护的是低级求值原语 formula_parse_utils.evaluate_formula 和 FormulaEvaluator，
# 不是 report_engine.evaluate_formula（那是合法的高层函数）。

# 允许直接导入低级求值的文件（唯一合法消费者）
_KERNEL_ALLOWED_FILES = {
    "formula_management/engine.py",
    "services/formula_engine.py",
    "services/formula_parse_utils.py",
}

# 保护的 import 模式（从 formula_parse_utils 导入 evaluate_formula / FormulaEvaluator）
_PROTECTED_IMPORT_PATTERNS = [
    re.compile(r"from\s+[\w.]*formula_parse_utils\s+import\s+.*\bevaluate_formula\b", re.IGNORECASE),
    re.compile(r"from\s+[\w.]*\s+import\s+.*\bFormulaEvaluator\b", re.IGNORECASE),
    re.compile(r"import\s+[\w.]*formula_parse_utils\b", re.IGNORECASE),
]


def check_single_kernel_drift() -> None:
    """
    扫描 backend/app/ 下是否有新增直接导入 formula_parse_utils.evaluate_formula
    或 FormulaEvaluator 的文件（绕过 single kernel 入口 engine.py）。

    对齐 test_single_kernel_guard.py 的白名单逻辑。
    """
    if not BACKEND_APP.exists():
        warn("backend/app/ 目录不存在，跳过 single-kernel 检查")
        return

    violations = []
    for py_file in BACKEND_APP.rglob("*.py"):
        # 跳过 __pycache__
        if "__pycache__" in str(py_file):
            continue

        rel_path = py_file.relative_to(BACKEND_APP).as_posix()

        # 跳过允许的文件
        if any(rel_path.endswith(allowed) for allowed in _KERNEL_ALLOWED_FILES):
            continue

        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern in _PROTECTED_IMPORT_PATTERNS:
                if pattern.search(stripped):
                    violations.append(f"  {py_file.relative_to(ROOT)}:{i} → {stripped[:100]}")
                    break

    if violations:
        fail(f"single-kernel consumer drift: 发现 {len(violations)} 处新增绕过 engine.py 的低级求值导入:\n" + "\n".join(violations))
    else:
        print("  [OK] single-kernel: 无新增绕过 engine.py 的低级求值导入")


# ─── 主函数 ────────────────────────────────────────────────────────────────────

def main() -> int:
    strict = "--strict" in sys.argv

    print("=" * 60)
    print("Formula Runtime Convergence — 完成度真实性守卫")
    print("=" * 60)
    print()

    print("[1/5] 检查叶子任务完成度...")
    check_all_tasks_complete()
    print()

    print("[2/5] 检查 PG integration 证据...")
    check_pg_integration_evidence()
    print()

    print("[3/5] 检查 Playwright E2E 证据...")
    check_playwright_evidence()
    print()

    print("[4/5] 检查禁止模式 (skip/吞错/空断言)...")
    check_forbidden_patterns()
    print()

    print("[5/5] 检查 single-kernel consumer drift...")
    check_single_kernel_drift()
    print()

    # ─── 结果汇总 ──────────────────────────────────────────────────────────────
    print("=" * 60)
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ⚠ {w}")
        print()

    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f_msg in failures:
            print(f"  ✗ {f_msg}")
        print()
        print("结论: 未通过完成度真实性检查")
        if strict:
            return 1
        else:
            print("(报告模式，不阻断)")
            return 0
    else:
        print("结论: 全部通过 ✓")
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main())
