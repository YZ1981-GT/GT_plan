#!/usr/bin/env python3
"""
check_coverage_ledger.py — CI_Drift_Guard：全局能力接线漂移守卫

扫描 coverage-ledger.json，检测"应接却未接"的底稿并根据模式阻断或报告。

判定逻辑（严格遵循 Req 2.4/2.5/2.7/2.8）：
  1. 枚举 wp_code_overrides.json 中全部 wp_code。
  2. 对每个 wp_code：
     - shellWrapped==true → auto-covered，放行（Req 2.7）
     - 已登记 exemption → 放行
     - 正向检出"应接却未接"（detected=false 但触发特征存在）且无豁免 → 阻断（fail-closed）
     - 无法判定接线状态（文件不可读/解析异常/不在 ledger 中）→ 放行（fail-open, Req 2.8）
  3. 输出漂移报告：{wp_code}: 应接 {capability} 未接线

零依赖（仅 stdlib）。显式 UTF-8 读写。

Usage:
    python check_coverage_ledger.py                # 报告模式（退出码恒 0）
    python check_coverage_ledger.py --strict       # 严格模式（有违规退出码 1）
    python check_coverage_ledger.py --check        # 同 --strict（CI 用）

Feature: platform-global-hardening, Task 3.5
Requirements: 2.4, 2.5, 2.7, 2.8
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ─── UTF-8 输出 ───────────────────────────────────────────────────────────────
try:
    sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, ValueError):
    pass

# ─── 路径 ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent  # GT_plan/

WP_CODE_OVERRIDES_PATH = PROJECT_ROOT / 'backend' / 'app' / 'data' / 'wp_code_overrides.json'
COVERAGE_LEDGER_PATH = (
    PROJECT_ROOT / 'audit-platform' / 'frontend' / 'src'
    / 'components' / 'workpaper' / 'coverage-ledger.json'
)
WORKPAPER_DIR = (
    PROJECT_ROOT / 'audit-platform' / 'frontend' / 'src'
    / 'components' / 'workpaper'
)

# ─── 能力清单 ──────────────────────────────────────────────────────────────────
CAPABILITIES = [
    'displayPrefs',
    'agingConfig',
    'version',
    'review',
    'ai',
    'importExport',
    'acnr',
]

# ─── "应接"触发特征（正则 heuristics）──────────────────────────────────────────
# 用于静态扫描主入口源码，判定某底稿"应当接入"某能力。
# 只有在触发特征命中且 detected=false 且无豁免时才阻断。
# 找不到触发特征 → 无法判定 → fail-open。

# displayPrefs: 含金额列（el-table 绑定 amount/金额/余额）或 fmtAmount 用法
TRIGGER_DISPLAY_PREFS = [
    re.compile(r'amount|金额|余额|balance|debit|credit', re.IGNORECASE),
    re.compile(r'el-table', re.IGNORECASE),
]

# agingConfig: 含账龄相关特征
TRIGGER_AGING_CONFIG = [
    re.compile(r'aging|账龄', re.IGNORECASE),
]

# 其余能力不做"应接"推断（无法静态判定是否"应"接），fail-open
# version / review / ai / importExport / acnr 的缺失不通过触发特征判定

# 能力→触发特征映射（仅列出有触发特征的能力）
TRIGGER_PATTERNS: dict[str, list[re.Pattern]] = {
    'displayPrefs': TRIGGER_DISPLAY_PREFS,
    'agingConfig': TRIGGER_AGING_CONFIG,
}

# ─── wp_code 提取 ──────────────────────────────────────────────────────────────
WP_ROOT_RE = re.compile(r'^([A-Z]\d+)')

# 跳过的 componentType（非结构化底稿，不存在接线概念）
SKIP_TYPES = {'skip', 'onlyoffice-sheet', 'word-template', 'redirect-materiality'}

# 主入口文件查找
MAIN_ENTRY_RE = re.compile(r'^Gt([A-Z]\d+(?:-\d+)?)\w*\.vue$')


def load_json_safe(path: Path) -> dict | None:
    """加载 JSON 文件，失败返回 None（fail-open）。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def get_root_codes_from_overrides(overrides: dict) -> set[str]:
    """从 wp_code_overrides.json 提取去重的根 wp_code。"""
    root_codes = set()
    for code, comp_type in overrides.items():
        if comp_type in SKIP_TYPES:
            continue
        m = WP_ROOT_RE.match(code)
        if m:
            root_codes.add(m.group(1))
    return root_codes


def find_main_entry(root_code: str) -> Path | None:
    """查找给定 root_code 的主入口 Vue 文件。"""
    if not WORKPAPER_DIR.exists():
        return None
    for f in WORKPAPER_DIR.iterdir():
        if not f.is_file():
            continue
        m = MAIN_ENTRY_RE.match(f.name)
        if m:
            entry_code = m.group(1)
            entry_root = WP_ROOT_RE.match(entry_code)
            if entry_root and entry_root.group(1) == root_code:
                return f
    return None


def read_source_safe(path: Path) -> str | None:
    """读取源文件内容，失败返回 None（fail-open）。"""
    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None


def has_trigger_features(source: str, capability: str) -> bool | None:
    """
    判定源码是否含有某能力的"应接"触发特征。

    返回:
      True  = 明确有触发特征（"应接"）
      False = 明确无触发特征（不应接）
      None  = 该能力没有触发特征定义，无法判定
    """
    patterns = TRIGGER_PATTERNS.get(capability)
    if patterns is None:
        # 无触发特征定义 → 无法判定 → fail-open
        return None
    return any(p.search(source) for p in patterns)


def check_violations(
    root_codes: set[str],
    ledger: dict,
) -> list[tuple[str, str]]:
    """
    检查所有 wp_code 的接线漂移。

    返回 [(wp_code, capability)] 违规列表（应接却未接且无豁免）。
    """
    violations: list[tuple[str, str]] = []
    entries = ledger.get('entries', {})

    for root_code in sorted(root_codes):
        entry = entries.get(root_code)

        # 不在 ledger 中 → 无法判定 → fail-open
        if entry is None:
            continue

        # shellWrapped → auto-covered → 放行 (Req 2.7)
        if entry.get('shellWrapped', False):
            continue

        # 有 exemption → 放行
        if entry.get('exemption'):
            continue

        # 非套壳、无豁免 → 检查各能力
        detected = entry.get('detected', {})

        # 需要读取主入口源码来判定触发特征
        main_entry = find_main_entry(root_code)
        if main_entry is None:
            # 找不到主入口 → 无法判定 → fail-open
            continue

        source = read_source_safe(main_entry)
        if source is None:
            # 源码不可读 → 无法判定 → fail-open
            continue

        for cap in CAPABILITIES:
            # 该能力已检出接入 → 无问题
            if detected.get(cap, False):
                continue

            # 判定是否"应接"
            trigger_result = has_trigger_features(source, cap)
            if trigger_result is None:
                # 无法判定该能力是否应接 → fail-open
                continue
            if trigger_result is False:
                # 不具备触发特征 → 不应接 → 无违规
                continue

            # 正向检出：有触发特征 + detected=false + 无 exemption → 违规
            violations.append((root_code, cap))

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description='CI_Drift_Guard：全局能力接线漂移守卫'
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='严格模式：检测到违规时退出码 1',
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='同 --strict（CI 用）',
    )
    args = parser.parse_args()
    strict = args.strict or args.check

    # 加载 wp_code_overrides.json
    overrides = load_json_safe(WP_CODE_OVERRIDES_PATH)
    if overrides is None:
        print('[WARN] 无法读取 wp_code_overrides.json，fail-open 放行')
        return 0

    # 加载 coverage-ledger.json
    ledger = load_json_safe(COVERAGE_LEDGER_PATH)
    if ledger is None:
        print('[WARN] 无法读取 coverage-ledger.json，fail-open 放行')
        return 0

    # 枚举全部根 wp_code
    root_codes = get_root_codes_from_overrides(overrides)
    if not root_codes:
        print('[INFO] 无可检查的 wp_code，跳过')
        return 0

    # 执行漂移检查
    violations = check_violations(root_codes, ledger)

    # 输出统计
    entries = ledger.get('entries', {})
    total = len(root_codes)
    in_ledger = sum(1 for c in root_codes if c in entries)
    shell_count = sum(
        1 for c in root_codes
        if entries.get(c, {}).get('shellWrapped', False)
    )
    exempt_count = sum(
        1 for c in root_codes
        if entries.get(c, {}).get('exemption')
    )

    print(f'[Coverage Drift Guard] 扫描 {total} 个 wp_code（'
          f'ledger 登记 {in_ledger}，shellWrapped {shell_count}，exemption {exempt_count}）')

    if not violations:
        print('[OK] 无漂移违规')
        return 0

    # 输出漂移报告
    print(f'\n检测到 {len(violations)} 处接线漂移：')
    print()
    for wp_code, cap in violations:
        print(f'  {wp_code}: 应接 {cap} 未接线')

    print()
    if strict:
        print('[FAIL] 存在应接未接且无豁免的底稿，构建失败。')
        print('修复方式：')
        print('  1. 套壳 GtWorkpaperShell（shellWrapped=true，自动接入全部能力）')
        print('  2. 在 coverage-ledger.json 对应条目添加 exemption 字段说明豁免原因')
        print('  3. 实际接入缺失的能力后重新运行 generate_coverage_ledger.py')
        return 1

    print('（报告模式：未阻断。加 --strict 后将 fail）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
