#!/usr/bin/env python3
"""
CI Guard: 检测新建的同构 FormData 网络实现和重复 checklist 网络实现。

Feature: workpaper-maintainability-convergence / Task 6.1
         workpaper-maintainability-convergence-followup / Task 7.1
Requirements: 5.1, 5.2, 5.3

两类违规模式：
1. 新建同构 FormData composable：在 composables/ 目录下创建新的 useXFormData.ts，
   包含自建 checklist-responses GET/PUT 网络调用，而未使用 createChecklistFormData 工厂
   或 useChecklistPersistence 适配器。
2. 重复 checklist 网络实现：在已迁移区域内（使用工厂或适配器的文件所在目录），
   直接调用 checklist-responses 端点。

运行: python backend/scripts/check/check_homogeneous_formdata.py [--strict]
- report 模式（默认）：输出全量报告，exit 0
- strict 模式：明确命中时 exit 1（Req 5.2: CI_Guard SHALL exit 1）
- strict 模式无违规时 exit 0（Req 5.3: CI_Guard SHALL exit 0）

零依赖：仅 stdlib。UTF-8 读取。
"""
import sys
import os
import re
from pathlib import Path
from dataclasses import dataclass, field

# ─── 配置 ────────────────────────────────────────────────────────────────────

# 从 backend/scripts/check/ 向上走 3 级到仓库根，再进 audit-platform/frontend/src
REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_ROOT = REPO_ROOT / 'audit-platform' / 'frontend' / 'src'
COMPOSABLES_DIR = FRONTEND_ROOT / 'components' / 'workpaper' / 'composables'

# 已知存量违规白名单（已迁移 + 待迁移但已登记的同构 FormData composable）
# 不在此白名单中的 useXFormData 文件若包含自建网络将被标记为 NEW 违规。
# 随着批次迁移推进，已迁移的文件将使用工厂（自动通过），白名单条目可逐步移除。
MIGRATED_ALLOWLIST = {
    # ── 已迁移（使用 createChecklistFormData 或 useChecklistPersistence）──
    'useD2FormData.ts',
    'useK5FormData.ts',
    # ── 待迁移存量（94 个同构 FormData 批次迁移基线）──
    'useA111FormData.ts',
    'useB22AFormData.ts',
    'useB22BFormData.ts',
    'useB23FormData.ts',
    'useB30FormData.ts',
    'useB50FormData.ts',
    'useD1FormData.ts',
    'useD3FormData.ts',
    'useD4FormData.ts',
    'useD5FormData.ts',
    'useD6FormData.ts',
    'useF1FormData.ts',
    'useF2FormData.ts',
    'useF2SpecialFormData.ts',
    'useF2StocktakeFormData.ts',
    'useF2ValuationFormData.ts',
    'useF3FormData.ts',
    'useF4AccPayFormData.ts',
    'useF4FormData.ts',
    'useF5CosSalFormData.ts',
    'useG10TraFinFormData.ts',
    'useG2IntRecFormData.ts',
    'useG3DivRecFormData.ts',
    'useG4BonEclFormData.ts',
    'useG4BonInvFormData.ts',
    'useG4BonSppFormData.ts',
    'useG5LonRecFormData.ts',
    'useG6BonEclFormData.ts',
    'useG6BonSppFormData.ts',
    'useG6OthBonFormData.ts',
    'useG7EquMaiFormData.ts',
    'useG7EquMetFormData.ts',
    'useG7EquSubFormData.ts',
}

# 使用工厂的文件不需要自建网络
FACTORY_PATTERNS = [
    r'createChecklistFormData\s*\(',
    r'useChecklistPersistence\s*\(',
]

# 自建网络的检测模式
SELF_NETWORK_PATTERNS = [
    # 直接调用 checklist-responses PUT
    (r"""api\.put\s*\(\s*[`'"]/api/workpapers/.*checklist-responses""", 'self-built PUT checklist-responses'),
    # 直接调用 checklist-responses GET
    (r"""api\.get\s*\(\s*[`'"]/api/workpapers/.*checklist-responses""", 'self-built GET checklist-responses'),
    # 使用 fetch 调用 checklist-responses
    (r"""fetch\s*\(\s*.*checklist-responses""", 'raw fetch checklist-responses'),
    # 自建 debounce timer（setTimeout + clearTimeout + checklist 写入组合）
    (r"""setTimeout\s*\(\s*\(\s*\)\s*=>\s*\{[^}]*(?:_doSave|saveImmediate|api\.put)""", 'self-built debounce save'),
]

# 命名模式：useXFormData / useXnFormData 等
FORMDATA_FILE_RE = re.compile(r'^use[A-Z]\w*FormData\.ts$')


@dataclass
class Violation:
    file: str
    line: int
    rule: str
    message: str


@dataclass
class Report:
    violations: list = field(default_factory=list)
    scanned: int = 0
    homogeneous_new: int = 0
    duplicate_network: int = 0


def uses_factory_or_adapter(content: str) -> bool:
    """检测文件是否已使用工厂或 Persistence Adapter。"""
    for pattern in FACTORY_PATTERNS:
        if re.search(pattern, content):
            return True
    return False


def scan_file(filepath: Path, report: Report) -> None:
    """扫描单个文件的违规模式。"""
    try:
        content = filepath.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        return

    report.scanned += 1
    rel_path = str(filepath.relative_to(FRONTEND_ROOT.parent.parent))
    filename = filepath.name

    # 规则 1：新建同构 FormData composable 检测
    if FORMDATA_FILE_RE.match(filename) and filename not in MIGRATED_ALLOWLIST:
        if not uses_factory_or_adapter(content):
            # 检查是否包含自建网络调用
            for pattern, desc in SELF_NETWORK_PATTERNS[:3]:  # 只检查网络模式
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pattern, line):
                        report.violations.append(Violation(
                            file=rel_path,
                            line=i,
                            rule='HOMOGENEOUS_FORMDATA',
                            message=f'同构 FormData 自建网络 ({desc})。'
                                    f'应使用 createChecklistFormData 工厂或 useChecklistPersistence 适配器。',
                        ))
                        report.homogeneous_new += 1
                        break  # 每个模式只报一次

    # 规则 2：重复 checklist 网络实现（非 FormData 文件也扫）
    # 仅当文件在已迁移区域附近且不是工厂/适配器本身
    factories_and_adapters = {
        'createChecklistFormData.ts',
        'createCycleFormData.ts',
        'useChecklistPersistence.ts',
    }
    if filename not in factories_and_adapters and filename not in MIGRATED_ALLOWLIST:
        # 在使用了工厂的目录中，不应有额外的 checklist-responses 直接调用
        # 这是 report 级的（不在 strict 中阻断），用于发现潜在待迁移目标
        pass  # Phase 1: 仅 homogeneous FormData 在 strict 模式阻断


def main() -> int:
    strict = '--strict' in sys.argv
    report = Report()

    if not COMPOSABLES_DIR.exists():
        print(f'[WARN] composables dir not found: {COMPOSABLES_DIR}')
        return 0

    # 扫描 composables 目录下所有 .ts 文件
    for filepath in sorted(COMPOSABLES_DIR.rglob('*.ts')):
        # 跳过 __tests__ 和 factories 目录中的文件
        rel = filepath.relative_to(COMPOSABLES_DIR)
        parts = rel.parts
        if '__tests__' in parts:
            continue
        if parts[0] == 'factories' and filepath.name != 'createCycleFormData.ts':
            continue
        scan_file(filepath, report)

    # 输出报告
    print(f'[check_homogeneous_formdata] Scanned {report.scanned} files')
    print(f'  Homogeneous FormData violations: {report.homogeneous_new}')
    print(f'  Duplicate network violations: {report.duplicate_network}')

    if report.violations:
        print()
        print('─── Violations ─────────────────────────────────────────')
        for v in report.violations:
            print(f'  {v.file}:{v.line} [{v.rule}]')
            print(f'    {v.message}')
        print()

    total = report.homogeneous_new + report.duplicate_network

    if strict and total > 0:
        print(f'[FAIL] {total} violation(s) in strict mode')
        return 1

    if total > 0:
        print(f'[REPORT] {total} violation(s) found (report mode, not blocking)')
    else:
        print('[OK] No homogeneous FormData violations detected')

    return 0


if __name__ == '__main__':
    sys.exit(main())
