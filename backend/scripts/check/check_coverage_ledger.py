#!/usr/bin/env python3
"""
check_coverage_ledger.py — Capability Ledger v2 全量覆盖率与漂移守卫

分别判定 Runtime Boundary 自动覆盖、Legacy Provider、业务直接覆盖、明确缺失、
能力级豁免和不确定状态。report 输出全部能力槽位覆盖率；strict 仅在明确缺失
或 Ledger 漂移时阻断，不确定状态保持 fail-open。

兼容读取 platform-global-hardening 的旧 shellWrapped/detected/exemption JSON；旧数据
按原正向特征规则判定，但新 v2 数据严格执行 status/evidence/exemption 契约。

零依赖（仅 stdlib）。显式 UTF-8 读写。

Usage:
    python check_coverage_ledger.py                # 报告模式（退出码恒 0）
    python check_coverage_ledger.py --strict       # 严格模式（有违规退出码 1）
    python check_coverage_ledger.py --check        # 同 --strict（CI 用）

Feature: workpaper-maintainability-convergence, Task 1.3
Requirements: 1.4, 5.5
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple, TextIO

# 兼容直接执行和测试通过 spec_from_file_location 动态导入。
_SCRIPT_MODULE_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_MODULE_DIR))

from capability_ledger import (  # noqa: E402
    CAPABILITIES,
    RUNTIME_CAPABILITIES,
    STATUSES,
    infer_legacy_exemption_capability,
)

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

# ─── 能力清单由 capability_ledger.py 单一维护 ────────────────────────────────

# Runtime Boundary 能力集合与合法状态由 capability_ledger.py 单一维护。
RUNTIME_BOUNDARY_CAPABILITIES = RUNTIME_CAPABILITIES

STATE_RUNTIME_BOUNDARY = 'runtime-boundary'
STATE_LEGACY_PROVIDER = 'legacy-provider'
STATE_COVERED = 'covered'
STATE_EXEMPT = 'exempt'
STATE_MISSING = 'missing'
STATE_UNKNOWN = 'unknown'
COVERED_STATES = {
    STATE_RUNTIME_BOUNDARY, STATE_LEGACY_PROVIDER, STATE_COVERED,
}
VALID_V2_STATUSES = STATUSES

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

        # v2 已有显式状态，不再回退到源码启发式；unknown 必须 fail-open。
        capability_records = entry.get('capabilities')
        if isinstance(capability_records, dict):
            for cap in CAPABILITIES:
                raw = capability_records.get(cap)
                if isinstance(raw, dict) and raw.get('status') == STATE_MISSING:
                    violations.append((root_code, cap))
            continue

        # shellWrapped → auto-covered → 放行 (Req 2.7)
        if entry.get('shellWrapped', False):
            continue

        # v1 entry exemption 仅在理由能唯一归属时豁免该 capability。
        legacy_exempt_capability = infer_legacy_exemption_capability(
            entry.get('exemption')
        )

        # 非套壳 → 检查各能力
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
            if cap == legacy_exempt_capability:
                continue
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


class CapabilityFinding(NamedTuple):
    """单个 wp_code × capability 的可解释判定。"""

    wp_code: str
    capability: str
    state: str
    evidence: tuple[str, ...] = ()
    detail: str = ''


class LedgerDrift(NamedTuple):
    """Ledger 结构或声明与证据契约之间的明确漂移。"""

    wp_code: str
    capability: str
    detail: str


class LedgerEvaluation:
    def __init__(
        self,
        findings: list[CapabilityFinding],
        drifts: list[LedgerDrift],
        schema_version: int,
    ) -> None:
        self.findings = findings
        self.drifts = drifts
        self.schema_version = schema_version

    @property
    def missing(self) -> list[CapabilityFinding]:
        return [f for f in self.findings if f.state == STATE_MISSING]

    @property
    def unknown(self) -> list[CapabilityFinding]:
        return [f for f in self.findings if f.state == STATE_UNKNOWN]

    @property
    def legacy_providers(self) -> list[CapabilityFinding]:
        return [f for f in self.findings if f.state == STATE_LEGACY_PROVIDER]

    @property
    def should_block(self) -> bool:
        """strict 只阻断明确 missing 或 Ledger drift。"""
        return bool(self.missing or self.drifts)

    def counts(self) -> Counter[str]:
        return Counter(f.state for f in self.findings)

    def coverage(self) -> tuple[int, int, int, float, float]:
        """返回 covered, total, applicable, full_rate, applicable_rate。"""
        counts = self.counts()
        covered = sum(counts[state] for state in COVERED_STATES)
        total = len(self.findings)
        applicable = total - counts[STATE_EXEMPT]
        full_rate = (covered / total * 100.0) if total else 100.0
        applicable_rate = (covered / applicable * 100.0) if applicable else 100.0
        return covered, total, applicable, full_rate, applicable_rate


def _normalize_evidence(raw: object) -> tuple[str, ...]:
    """把 v2 evidence 规范为可比较文本；非法值留空并由调用方标 drift。"""
    if raw is None:
        return ()
    values = raw if isinstance(raw, list) else [raw]
    normalized: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            normalized.append(value.strip())
        elif isinstance(value, dict):
            path = value.get('file') or value.get('path') or value.get('source')
            symbol = value.get('symbol') or value.get('kind')
            text = ':'.join(str(part) for part in (path, symbol) if part)
            if not text:
                text = json.dumps(value, ensure_ascii=False, sort_keys=True)
            normalized.append(text)
    return tuple(normalized)


def _is_runtime_boundary_evidence(evidence: tuple[str, ...]) -> bool:
    compact = ' '.join(evidence).lower()
    compact = re.sub(r'[^a-z0-9]+', '', compact)
    return 'runtimeboundary' in compact or 'gtwprenderer' in compact


def _valid_exemption(raw: object) -> bool:
    return isinstance(raw, dict) and bool(str(raw.get('reason', '')).strip())


def _evaluate_v2_capability(
    wp_code: str,
    capability: str,
    raw: object,
) -> tuple[CapabilityFinding, list[LedgerDrift]]:
    drifts: list[LedgerDrift] = []
    if not isinstance(raw, dict):
        return (
            CapabilityFinding(wp_code, capability, STATE_UNKNOWN),
            [LedgerDrift(wp_code, capability, 'capability 记录不是对象')],
        )

    status = str(raw.get('status', '')).strip().lower()
    raw_evidence = raw.get('evidence')
    evidence = _normalize_evidence(raw_evidence)
    if raw_evidence is not None and not isinstance(raw_evidence, list):
        drifts.append(LedgerDrift(
            wp_code, capability, 'evidence 必须是字符串数组',
        ))
    elif isinstance(raw_evidence, list) and any(
        not isinstance(item, str) or not item.strip() for item in raw_evidence
    ):
        drifts.append(LedgerDrift(
            wp_code, capability, 'evidence 含空值或非字符串项',
        ))
    if status not in VALID_V2_STATUSES:
        return (
            CapabilityFinding(wp_code, capability, STATE_UNKNOWN, evidence),
            [LedgerDrift(wp_code, capability, f'非法或缺失 status: {status or "<empty>"}')],
        )

    exemption = raw.get('exemption')
    if status != STATE_EXEMPT and exemption is not None:
        drifts.append(LedgerDrift(
            wp_code,
            capability,
            f'{status} 状态不允许携带 exemption',
        ))

    if status == 'covered':
        if not evidence:
            return (
                CapabilityFinding(wp_code, capability, STATE_UNKNOWN),
                [LedgerDrift(wp_code, capability, 'covered 缺少可复现 evidence')],
            )
        if _is_runtime_boundary_evidence(evidence):
            if capability not in RUNTIME_BOUNDARY_CAPABILITIES:
                drifts.append(LedgerDrift(
                    wp_code,
                    capability,
                    '该能力不由 Runtime Boundary 自动提供',
                ))
                return CapabilityFinding(
                    wp_code, capability, STATE_COVERED, evidence,
                    'Runtime Boundary 证据不适用于该业务能力',
                ), drifts
            return CapabilityFinding(
                wp_code, capability, STATE_RUNTIME_BOUNDARY, evidence,
                '由 Runtime Boundary 自动覆盖',
            ), drifts
        if capability in RUNTIME_BOUNDARY_CAPABILITIES:
            return CapabilityFinding(
                wp_code, capability, STATE_LEGACY_PROVIDER, evidence,
                '由主入口 Legacy Provider/本地接线覆盖',
            ), drifts
        return CapabilityFinding(
            wp_code, capability, STATE_COVERED, evidence,
            '由业务组件直接接线覆盖',
        ), drifts

    if evidence:
        drifts.append(LedgerDrift(
            wp_code,
            capability,
            f'{status} 状态不应携带覆盖 evidence',
        ))

    if status == 'missing':
        return CapabilityFinding(
            wp_code, capability, STATE_MISSING, evidence,
            'Ledger 明确声明缺失',
        ), drifts
    if status == 'exempt':
        if not _valid_exemption(raw.get('exemption')):
            drifts.append(LedgerDrift(
                wp_code, capability, 'exempt 缺少能力级 exemption.reason',
            ))
        return CapabilityFinding(
            wp_code, capability, STATE_EXEMPT, evidence,
            '能力级豁免',
        ), drifts
    return CapabilityFinding(
        wp_code, capability, STATE_UNKNOWN, evidence,
        '证据不足，fail-open',
    ), drifts


def _evaluate_v1_entry(
    wp_code: str,
    entry: dict,
) -> list[CapabilityFinding]:
    """旧 Ledger 兼容读取；保持原正向检出/fail-open 语义。"""
    findings: list[CapabilityFinding] = []
    detected = entry.get('detected', {})
    if not isinstance(detected, dict):
        detected = {}
    shell_wrapped = bool(entry.get('shellWrapped', False))
    legacy_exemption = entry.get('exemption')
    exempt_capability = infer_legacy_exemption_capability(legacy_exemption)

    source: str | None = None
    main_entry = find_main_entry(wp_code)
    if main_entry is not None:
        source = read_source_safe(main_entry)

    for capability in CAPABILITIES:
        evidence = (f'{main_entry.name}:legacy-detection',) if (
            main_entry is not None and detected.get(capability, False)
        ) else ()
        if shell_wrapped and capability in RUNTIME_BOUNDARY_CAPABILITIES:
            findings.append(CapabilityFinding(
                wp_code, capability, STATE_RUNTIME_BOUNDARY,
                ('legacy:shellWrapped',), '旧 Ledger 自动覆盖兼容',
            ))
        elif detected.get(capability, False):
            state = (
                STATE_LEGACY_PROVIDER
                if capability in RUNTIME_BOUNDARY_CAPABILITIES
                else STATE_COVERED
            )
            findings.append(CapabilityFinding(
                wp_code, capability, state, evidence, '旧 Ledger detected 兼容',
            ))
        elif capability == exempt_capability:
            findings.append(CapabilityFinding(
                wp_code, capability, STATE_EXEMPT, (),
                '旧 entry 豁免已按理由归属到单一 capability',
            ))
        elif source is None:
            findings.append(CapabilityFinding(
                wp_code, capability, STATE_UNKNOWN, (), '源码不可读，fail-open',
            ))
        else:
            triggered = has_trigger_features(source, capability)
            state = STATE_MISSING if triggered is True else STATE_UNKNOWN
            detail = '正向特征明确命中但未接线' if triggered is True else '无法明确判定，fail-open'
            findings.append(CapabilityFinding(
                wp_code, capability, state, (), detail,
            ))
    return findings


def evaluate_ledger(root_codes: set[str], ledger: dict) -> LedgerEvaluation:
    """统一判定 v2 Ledger，并兼容读取旧 JSON。"""
    findings: list[CapabilityFinding] = []
    drifts: list[LedgerDrift] = []
    raw_version = ledger.get('schemaVersion', 1)
    schema_version = raw_version if isinstance(raw_version, int) else 0
    entries = ledger.get('entries', {})
    if not isinstance(entries, dict):
        entries = {}
        drifts.append(LedgerDrift('*', '*', 'entries 不是对象'))

    if schema_version not in (1, 2):
        drifts.append(LedgerDrift('*', '*', f'不支持的 schemaVersion: {raw_version!r}'))

    for wp_code in sorted(root_codes):
        entry = entries.get(wp_code)
        if not isinstance(entry, dict):
            drifts.append(LedgerDrift(wp_code, '*', 'wp_code 未登记或 entry 非对象'))
            findings.extend(
                CapabilityFinding(wp_code, cap, STATE_UNKNOWN, (), 'Ledger 未登记')
                for cap in CAPABILITIES
            )
            continue

        is_v2_entry = schema_version == 2 or isinstance(entry.get('capabilities'), dict)
        if not is_v2_entry:
            findings.extend(_evaluate_v1_entry(wp_code, entry))
            continue

        capability_records = entry.get('capabilities')
        if not isinstance(capability_records, dict):
            drifts.append(LedgerDrift(wp_code, '*', 'v2 entry 缺少 capabilities 对象'))
            capability_records = {}
        if 'exemption' in entry:
            drifts.append(LedgerDrift(
                wp_code, '*', 'v2 Ledger 禁止 entry 级 exemption',
            ))
        for unknown_capability in sorted(set(capability_records) - set(CAPABILITIES)):
            drifts.append(LedgerDrift(
                wp_code,
                unknown_capability,
                'v2 Ledger 包含未知 capability',
            ))
        for capability in CAPABILITIES:
            if capability not in capability_records:
                drifts.append(LedgerDrift(wp_code, capability, 'v2 Ledger 缺少能力记录'))
                findings.append(CapabilityFinding(
                    wp_code, capability, STATE_UNKNOWN, (), '能力记录缺失',
                ))
                continue
            finding, capability_drifts = _evaluate_v2_capability(
                wp_code, capability, capability_records[capability],
            )
            findings.append(finding)
            drifts.extend(capability_drifts)

    for stale_code in sorted(set(entries) - root_codes):
        drifts.append(LedgerDrift(stale_code, '*', 'Ledger 存在已不在注册真源中的 entry'))

    return LedgerEvaluation(findings, drifts, schema_version)


def print_report(evaluation: LedgerEvaluation, stream: TextIO = sys.stdout) -> None:
    """输出全量覆盖率及四类关键判定明细。"""
    counts = evaluation.counts()
    covered, total, applicable, full_rate, applicable_rate = evaluation.coverage()
    print(
        f'[Coverage Ledger] schema v{evaluation.schema_version}; '
        f'全量能力槽位 {total}',
        file=stream,
    )
    print(
        f'  全量覆盖率: {full_rate:.2f}% ({covered}/{total})',
        file=stream,
    )
    print(
        f'  适用项覆盖率: {applicable_rate:.2f}% ({covered}/{applicable}; '
        f'豁免 {counts[STATE_EXEMPT]})',
        file=stream,
    )
    print(
        '  分类: '
        f'Runtime Boundary={counts[STATE_RUNTIME_BOUNDARY]}, '
        f'Legacy Provider={counts[STATE_LEGACY_PROVIDER]}, '
        f'业务直连={counts[STATE_COVERED]}, '
        f'明确缺失={counts[STATE_MISSING]}, '
        f'不确定={counts[STATE_UNKNOWN]}, '
        f'豁免={counts[STATE_EXEMPT]}, '
        f'Ledger 漂移={len(evaluation.drifts)}',
        file=stream,
    )

    detail_groups = (
        ('Legacy Provider（迁移期允许）', evaluation.legacy_providers),
        ('明确缺失', evaluation.missing),
        ('不确定（fail-open）', evaluation.unknown),
    )
    for title, rows in detail_groups:
        if not rows:
            continue
        print(f'\n[{title}] {len(rows)}', file=stream)
        for row in rows:
            print(f'  {row.wp_code}.{row.capability}: {row.detail}', file=stream)

    if evaluation.drifts:
        print(f'\n[Ledger 漂移] {len(evaluation.drifts)}', file=stream)
        for drift in evaluation.drifts:
            print(
                f'  {drift.wp_code}.{drift.capability}: {drift.detail}',
                file=stream,
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Capability Ledger 全量覆盖率与漂移守卫'
    )
    parser.add_argument(
        '--mode',
        choices=('report', 'strict'),
        default='report',
        help='report=输出全量覆盖率且不阻断；strict=仅 missing/drift 阻断',
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='严格模式（兼容旧 CLI）',
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='同 --strict（CI 兼容）',
    )
    args = parser.parse_args()
    strict = args.mode == 'strict' or args.strict or args.check

    overrides = load_json_safe(WP_CODE_OVERRIDES_PATH)
    if overrides is None:
        print('[WARN] 无法读取 wp_code_overrides.json，状态不确定，fail-open 放行')
        return 0

    ledger = load_json_safe(COVERAGE_LEDGER_PATH)
    if ledger is None:
        print('[WARN] 无法读取 coverage-ledger.json，状态不确定，fail-open 放行')
        return 0

    root_codes = get_root_codes_from_overrides(overrides)
    if not root_codes:
        print('[INFO] 无可检查的 wp_code，跳过')
        return 0

    evaluation = evaluate_ledger(root_codes, ledger)
    print_report(evaluation)

    if strict and evaluation.should_block:
        print(
            f'\n[FAIL] strict 阻断：明确缺失 {len(evaluation.missing)}，'
            f'Ledger 漂移 {len(evaluation.drifts)}。'
        )
        return 1

    if evaluation.should_block:
        print('\n[REPORT] 已报告明确缺失/Ledger 漂移；report 模式不阻断。')
    elif evaluation.unknown:
        print('\n[OK] 无明确缺失或 Ledger 漂移；不确定项按 fail-open 放行。')
    else:
        print('\n[OK] 无明确缺失或 Ledger 漂移。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
