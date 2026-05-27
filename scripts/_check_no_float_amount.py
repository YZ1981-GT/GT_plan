"""扫描 backend/app/services/ 下含 amount/balance/debit/credit 关键字的 float() 调用。

V3 Spec Req 2 金额 Decimal 化 — Task 2.5 CI baseline 卡点脚本。

用法:
    python scripts/_check_no_float_amount.py             # 使用 baselines.json 中的 baseline
    python scripts/_check_no_float_amount.py --baseline 50  # 显式指定 baseline
    python scripts/_check_no_float_amount.py --update    # 用当前实测值更新 baselines.json

退出码:
    0 = 达标 (count <= baseline)
    1 = 超标 (count > baseline)

约束:
    - baseline "只减不增" — 实施过程中持续下降，CI 卡点防回退
    - 跳过 _ 前缀文件（_decimal_helpers / 一次性脚本）
    - 跳过测试文件（services 目录下不应有 test_ 文件，但保险起见）
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

# 匹配 float(... amount|balance|debit|credit|tax|cost|price ...)
# 关键字必须在 float() 括号内出现，使用 \b 保证整词匹配
PATTERN = re.compile(
    r'float\s*\(\s*[^)]*\b(amount|balance|debit|credit|tax|cost|price)\b[^)]*\)'
)

SERVICES_DIR = pathlib.Path('backend/app/services')
BASELINES_FILE = pathlib.Path('.github/workflows/baselines.json')
BASELINE_KEY = 'no-amount-without-decimal-services'


def scan() -> list[tuple[str, int, str]]:
    """Return list of (file, line_no, line_content) matches."""
    matches: list[tuple[str, int, str]] = []
    if not SERVICES_DIR.exists():
        print(f"⚠️  目录不存在: {SERVICES_DIR}", file=sys.stderr)
        return matches

    for py_file in sorted(SERVICES_DIR.rglob('*.py')):
        # 跳过 _ 前缀文件（_decimal_helpers / __init__ / 一次性脚本）
        if py_file.name.startswith('_'):
            continue
        # 跳过测试文件（保险起见）
        if py_file.name.startswith('test_'):
            continue
        try:
            with open(py_file, encoding='utf-8') as f:
                for line_no, line in enumerate(f, 1):
                    if PATTERN.search(line):
                        matches.append((str(py_file).replace('\\', '/'), line_no, line.strip()))
        except (OSError, UnicodeDecodeError) as e:
            print(f"⚠️  跳过 {py_file}: {e}", file=sys.stderr)
    return matches


def read_baseline() -> int:
    """从 baselines.json 读取 baseline；缺失或 <TBD> 时返回 sys.maxsize（本次不卡）。"""
    if not BASELINES_FILE.exists():
        return sys.maxsize
    try:
        with open(BASELINES_FILE, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️  无法读取 {BASELINES_FILE}: {e}", file=sys.stderr)
        return sys.maxsize

    v3_rules = data.get('_v3_eslint_rules', {})
    raw = v3_rules.get(BASELINE_KEY, '<TBD>')
    if raw == '<TBD>' or raw is None:
        return sys.maxsize
    try:
        return int(raw)
    except (TypeError, ValueError):
        print(f"⚠️  baseline 字段非整数: {raw!r}", file=sys.stderr)
        return sys.maxsize


def update_baseline(count: int) -> None:
    """将实测 count 写回 baselines.json 的 _v3_eslint_rules 节。"""
    if not BASELINES_FILE.exists():
        print(f"❌ {BASELINES_FILE} 不存在，无法更新", file=sys.stderr)
        sys.exit(2)
    with open(BASELINES_FILE, encoding='utf-8') as f:
        data = json.load(f)
    data.setdefault('_v3_eslint_rules', {})[BASELINE_KEY] = count
    with open(BASELINES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f"✅ 已写入 {BASELINES_FILE} 的 _v3_eslint_rules.{BASELINE_KEY} = {count}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description='扫描 backend/app/services/ 下含 amount/balance/debit/credit 关键字的 float() 调用'
    )
    parser.add_argument(
        '--baseline',
        type=int,
        default=None,
        help='显式指定 baseline 阈值；未指定则读取 baselines.json',
    )
    parser.add_argument(
        '--update',
        action='store_true',
        help='将当前实测值写回 baselines.json（仅初始化或显式刷新时使用）',
    )
    parser.add_argument(
        '--show',
        type=int,
        default=20,
        help='超标时显示前 N 条匹配（默认 20）',
    )
    args = parser.parse_args()

    matches = scan()
    count = len(matches)

    print(f"📊 backend/app/services/ 含金额关键字的 float() 调用数: {count}")

    if args.update:
        update_baseline(count)
        print(f"\n✅ baseline 已初始化为实测值 {count}")
        return 0

    baseline = args.baseline if args.baseline is not None else read_baseline()
    if baseline == sys.maxsize:
        print(f"⚠️  baseline 未配置（_v3_eslint_rules.{BASELINE_KEY} = <TBD>），本次不卡点")
        print(f"   首次初始化请运行: python scripts/_check_no_float_amount.py --update")
        return 0

    print(f"📋 baseline (只减不增): {baseline}")

    if count > baseline:
        print(f"\n❌ FAIL: 当前 {count} > baseline {baseline}（新增了 {count - baseline} 处 float 金额）")
        print(f"   前 {min(args.show, count)} 条匹配:")
        for f, ln, line in matches[: args.show]:
            print(f"     {f}:{ln}: {line}")
        print(f"\n   修复指引: 用 backend/app/services/_decimal_helpers.py 的 to_decimal() 替换 float()")
        return 1

    if count < baseline:
        print(f"\n✅ PASS: 当前 {count} < baseline {baseline}（已削减 {baseline - count} 处，请用 --update 收紧 baseline）")
    else:
        print(f"\n✅ PASS: 当前 {count} == baseline {baseline}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
