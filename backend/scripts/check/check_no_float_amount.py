"""float 金额防退化卡点（pre-commit hook）。

扫描底稿相关 service 中的 float() 调用，防止金额精度退化。
已有 float() 调用记录为 baseline，新增超过 baseline 则阻断。

策略：
- 扫描 backend/app/services/wp_*.py + workpaper_*.py
- 排除安全模式：JSON 序列化 / 日志 / 字符串格式化 / 注释 / 类型注解
- baseline 记录在 backend/scripts/check/float_amount_baseline.txt
- 新增违规 > baseline 则 exit 1

用法：
    python backend/scripts/check/check_no_float_amount.py [--init]

    --init  首次运行定 baseline（输出当前违规数并写入 baseline 文件）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICES_DIR = ROOT / "backend" / "app" / "services"
BASELINE_FILE = Path(__file__).resolve().parent / "float_amount_baseline.txt"

# 匹配 float( 调用（非注释行）
FLOAT_CALL_RE = re.compile(r"\bfloat\s*\(")

# 安全模式排除正则（这些 float() 用法不涉及金额精度风险）
SAFE_PATTERNS = [
    # JSON 序列化上下文
    re.compile(r"json\.dumps|json_serializable|jsonable_encoder"),
    # 日志 / print / debug
    re.compile(r"\b(log(ger)?|print|debug|info|warning|error)\b.*float\s*\("),
    # 字符串格式化
    re.compile(r'(f"|f\'|\.format\(|%[sdf]).*float\s*\('),
    re.compile(r'float\s*\(.*?(f"|f\'|\.format\(|%[sdf])'),
    # 类型注解 / isinstance / typing
    re.compile(r"(isinstance|Union|Optional|->|:\s*)(.*?)float"),
    # round() 包裹（通常是显示格式化）
    re.compile(r"round\s*\(\s*float\s*\("),
    # 注释行
    re.compile(r"^\s*#"),
]


def is_safe_usage(line: str) -> bool:
    """判断该行的 float() 是否属于安全模式（不涉及金额精度风险）。"""
    for pattern in SAFE_PATTERNS:
        if pattern.search(line):
            return True
    return False


def scan_file(filepath: Path) -> list[tuple[int, str]]:
    """扫描单个文件，返回违规行列表 [(行号, 行内容)]。"""
    violations: list[tuple[int, str]] = []
    try:
        lines = filepath.read_text(encoding="utf-8").splitlines()
    except Exception:
        return violations

    for i, line in enumerate(lines, 1):
        # 跳过注释行
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # 跳过字符串中的 float（docstring 等）
        if stripped.startswith(('"""', "'''")):
            continue

        if FLOAT_CALL_RE.search(line):
            if not is_safe_usage(line):
                violations.append((i, line.rstrip()))

    return violations


def get_target_files() -> list[Path]:
    """获取需要扫描的目标文件列表。"""
    if not SERVICES_DIR.exists():
        return []

    targets: list[Path] = []
    for f in SERVICES_DIR.iterdir():
        if not f.is_file() or f.suffix != ".py":
            continue
        name = f.name
        if name.startswith("wp_") or name.startswith("workpaper_"):
            targets.append(f)

    return sorted(targets)


def load_baseline() -> int:
    """读取 baseline 文件中的违规数。"""
    if not BASELINE_FILE.exists():
        return -1  # 无 baseline 文件 = 首次运行
    try:
        text = BASELINE_FILE.read_text(encoding="utf-8").strip()
        return int(text)
    except (ValueError, OSError):
        return -1


def save_baseline(count: int) -> None:
    """保存 baseline。"""
    BASELINE_FILE.write_text(str(count) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="float 金额防退化卡点")
    parser.add_argument("--init", action="store_true",
                        help="首次运行：定 baseline 并写入文件")
    args = parser.parse_args(argv)

    targets = get_target_files()
    if not targets:
        print("未找到目标文件（wp_*.py / workpaper_*.py）", file=sys.stderr)
        return 0

    all_violations: list[tuple[str, int, str]] = []
    for f in targets:
        violations = scan_file(f)
        for lineno, line in violations:
            rel_path = str(f.relative_to(ROOT)).replace("\\", "/")
            all_violations.append((rel_path, lineno, line))

    total = len(all_violations)

    if args.init:
        # 首次运行：输出所有违规 + 写 baseline
        print(f"扫描 {len(targets)} 个文件，发现 {total} 处 float() 金额调用：")
        for path, lineno, line in all_violations:
            print(f"  {path}:{lineno}: {line.strip()}")
        save_baseline(total)
        print(f"\nBaseline 已写入: {BASELINE_FILE} (值={total})")
        return 0

    # 正常运行：对比 baseline
    baseline = load_baseline()
    if baseline < 0:
        print("⚠️  未找到 baseline 文件，请先运行 --init 定基线", file=sys.stderr)
        print(f"   当前违规数: {total}", file=sys.stderr)
        # 无 baseline 不阻断，仅警告
        return 0

    if total > baseline:
        print(f"❌ float() 金额调用退化: {total} > baseline {baseline}", file=sys.stderr)
        print(f"   新增 {total - baseline} 处违规：", file=sys.stderr)
        for path, lineno, line in all_violations:
            print(f"   {path}:{lineno}: {line.strip()}", file=sys.stderr)
        return 1

    # 通过（可能减少了，但不更新 baseline——只增不减由人工决定）
    if total < baseline:
        print(f"✅ float() 金额调用减少: {total} < baseline {baseline}（可考虑更新 baseline）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
