#!/usr/bin/env python3
"""
FormData 工厂迁移脚本：将同构 FormData composable 替换为 createChecklistFormData 工厂调用。

Feature: workpaper-maintainability-convergence-followup
Task: 5.1 — 脚本骨架
Requirements: 4.1, 4.6

职责：
- 扫描 composables/ 目录中 useXFormData.ts 文件
- 按 FORMDATA_MIGRATION_MAP 配置逐个生成 createChecklistFormData 调用模板
- 跳过 SKIP_LIST 中的非同构文件
- 支持 --dry-run（默认）/ --apply / --cycle K 过滤

零依赖：仅 Python stdlib，UTF-8 显式编码。
"""
import sys
import os
import re
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

# ─── 路径计算 ─────────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[1]  # backend/scripts/migration -> backend
_FRONTEND_ROOT = _PROJECT_ROOT.parent / 'audit-platform' / 'frontend' / 'src'
COMPOSABLES_DIR = _FRONTEND_ROOT / 'components' / 'workpaper' / 'composables'

# ─── FORMDATA_MIGRATION_MAP ──────────────────────────────────────────────────
# 94 个同构 composable 的配置：prefix/label/componentType/accountCodes
# 从实际源文件中提取。

FORMDATA_MIGRATION_MAP: Dict[str, dict] = {
    # ─── D 循环（收入/应收/合同） ─────────────────────────────────────────
    'useD3FormData': {'prefix': 'D3-', 'label': 'D3', 'componentType': 'd3-prepaid-accounts', 'accountCodes': ['1123']},
    'useD4FormData': {'prefix': 'D4-', 'label': 'D4', 'componentType': 'd4-operating-revenue', 'accountCodes': ['6001']},
    'useD5FormData': {'prefix': 'D5-', 'label': 'D5', 'componentType': 'd5-receivables-financing', 'accountCodes': ['1132']},
    'useD6FormData': {'prefix': 'D6-', 'label': 'D6', 'componentType': 'd6-contract-assets', 'accountCodes': ['1411']},
    'useD7FormData': {'prefix': 'D7-', 'label': 'D7', 'componentType': 'd7-contract-liabilities', 'accountCodes': ['2205']},
    # ─── F 循环（存货/应付） ──────────────────────────────────────────────
    'useF1FormData': {'prefix': 'F1-', 'label': 'F1', 'componentType': 'f1-prepayment', 'accountCodes': ['1123']},
    'useF2ValuationFormData': {'prefix': 'F2-', 'label': 'F2-Valuation', 'componentType': 'f2-inventory-valuation-impairment', 'accountCodes': ['1405']},
    'useF3FormData': {'prefix': 'F3-', 'label': 'F3', 'componentType': 'f3-notes-payable', 'accountCodes': ['2201']},
    'useF4FormData': {'prefix': 'F4-', 'label': 'F4', 'componentType': 'f4-accounts-payable', 'accountCodes': ['2202']},
    # ─── G 循环（投资） ───────────────────────────────────────────────────
    'useG1TraFinFormData': {'prefix': 'G1-', 'label': 'G1-TraFin', 'componentType': 'g1-trading-financial-assets', 'accountCodes': ['1101']},
    'useG3FormData': {'prefix': 'G3-', 'label': 'G3', 'componentType': 'g3-dividend-receivable', 'accountCodes': ['1131']},
    'useG4EclFormData': {'prefix': 'G4-ECL-', 'label': 'G4-ECL', 'componentType': 'g4-bond-investment-ecl', 'accountCodes': ['1501']},
    'useG5FormData': {'prefix': 'G5-', 'label': 'G5', 'componentType': 'g5-long-term-receivable', 'accountCodes': ['1531']},
    'useG6EclFormData': {'prefix': 'G6-ECL-', 'label': 'G6-ECL', 'componentType': 'g6-other-bond-investment-ecl', 'accountCodes': ['1503']},
    'useG6MainFormData': {'prefix': 'G6-', 'label': 'G6-Main', 'componentType': 'g6-other-bond-investment-main', 'accountCodes': ['1503']},
    'useG6SppiFormData': {'prefix': 'G6-SPPI-', 'label': 'G6-SPPI', 'componentType': 'g6-other-bond-investment-sppi', 'accountCodes': ['1503']},
    'useG7FormData': {'prefix': 'G7-', 'label': 'G7', 'componentType': 'g7-long-term-equity-main', 'accountCodes': ['1511']},
    'useG7EquityMethodFormData': {'prefix': 'G7-EQ-', 'label': 'G7-EqMethod', 'componentType': 'g7-long-term-equity-method', 'accountCodes': ['1511']},
    'useG7SubFormData': {'prefix': 'G7-SUB-', 'label': 'G7-Sub', 'componentType': 'g7-long-term-equity-subsidiary', 'accountCodes': ['1511']},
    'useG8FormData': {'prefix': 'G8-', 'label': 'G8', 'componentType': 'g8-other-equity-instruments', 'accountCodes': ['1521']},
    'useG9FormData': {'prefix': 'G9-', 'label': 'G9', 'componentType': 'g9-other-noncurrent-financial', 'accountCodes': ['1521']},
    'useG10FormData': {'prefix': 'G10-', 'label': 'G10', 'componentType': 'g10-trading-financial-liabilities', 'accountCodes': ['2101']},
    'useG11FormData': {'prefix': 'G11-', 'label': 'G11', 'componentType': 'g11-investment-income', 'accountCodes': ['6111']},
    'useG12FormData': {'prefix': 'G12-', 'label': 'G12', 'componentType': 'g12-net-hedge-gains', 'accountCodes': ['6111']},
    'useG13FormData': {'prefix': 'G13-', 'label': 'G13', 'componentType': 'g13-fair-value-changes', 'accountCodes': ['6101']},
    'useG14FormData': {'prefix': 'G14-', 'label': 'G14', 'componentType': 'g14-credit-impairment-loss', 'accountCodes': ['6702']},
    # ─── H 循环（固定资产/无形） ──────────────────────────────────────────
    'useH1FormData': {'prefix': 'H1-', 'label': 'H1', 'componentType': 'h1-fixed-assets', 'accountCodes': ['1601', '1602']},
    'useH2FormData': {'prefix': 'H2-', 'label': 'H2', 'componentType': 'h2-construction-in-progress', 'accountCodes': ['1604']},
    'useH3FormData': {'prefix': 'H3-', 'label': 'H3', 'componentType': 'h3-investment-property', 'accountCodes': ['1503', '1504']},
    'useH4FormData': {'prefix': 'H4-', 'label': 'H4', 'componentType': 'h4-engineering-materials', 'accountCodes': ['1605']},
    'useH5FormData': {'prefix': 'H5-', 'label': 'H5', 'componentType': 'h5-oil-gas-assets', 'accountCodes': ['1631', '1632']},
    'useH6FormData': {'prefix': 'H6-', 'label': 'H6', 'componentType': 'h6-asset-disposal-clearing', 'accountCodes': ['1606']},
    'useH7FormData': {'prefix': 'H7-', 'label': 'H7', 'componentType': 'h7-biological-assets', 'accountCodes': ['1621']},
    'useH8FormData': {'prefix': 'H8-', 'label': 'H8', 'componentType': 'h8-right-of-use-assets', 'accountCodes': ['1901', '1902']},
    'useH9FormData': {'prefix': 'H9-', 'label': 'H9', 'componentType': 'h9-lease-liabilities', 'accountCodes': ['2205', '1802']},
    'useH10FormData': {'prefix': 'H10-', 'label': 'H10', 'componentType': 'h10-asset-disposal-income', 'accountCodes': ['6115']},
    # ─── I 循环（无形资产/开发） ──────────────────────────────────────────
    'useI1FormData': {'prefix': 'I1-', 'label': 'I1', 'componentType': 'i1-intangible-assets', 'accountCodes': ['1701', '1702', '1703']},
    'useI2FormData': {'prefix': 'I2-', 'label': 'I2', 'componentType': 'i2-development-expenditure', 'accountCodes': ['1717']},
    'useI3FormData': {'prefix': 'I3-', 'label': 'I3', 'componentType': 'i3-goodwill', 'accountCodes': ['1711']},
    'useI4FormData': {'prefix': 'I4-', 'label': 'I4', 'componentType': 'i4-long-term-prepaid', 'accountCodes': ['1801']},
    'useI5FormData': {'prefix': 'I5-', 'label': 'I5', 'componentType': 'i5-other-noncurrent-assets', 'accountCodes': ['1911']},
    'useI6FormData': {'prefix': 'I6-', 'label': 'I6', 'componentType': 'i6-research-development-expense', 'accountCodes': ['6602']},
    # ─── K 循环（其他/损益） ──────────────────────────────────────────────
    'useK1FormData': {'prefix': 'K1-', 'label': 'K1', 'componentType': 'k1-other-receivables', 'accountCodes': ['1221', '1231']},
    'useK2FormData': {'prefix': 'K2-', 'label': 'K2', 'componentType': 'k2-other-current-assets', 'accountCodes': ['1231']},
    'useK3FormData': {'prefix': 'K3-', 'label': 'K3', 'componentType': 'k3-other-payables', 'accountCodes': ['2241']},
    'useK4FormData': {'prefix': 'K4-', 'label': 'K4', 'componentType': 'k4-other-current-liabilities', 'accountCodes': ['2245']},
    'useK5FormData': {'prefix': 'K5-', 'label': 'K5', 'componentType': 'k5-provisions', 'accountCodes': ['2701']},
    'useK6FormData': {'prefix': 'K6-', 'label': 'K6', 'componentType': 'k6-held-for-sale', 'accountCodes': ['1481', '2605']},
    'useK7FormData': {'prefix': 'K7-', 'label': 'K7', 'componentType': 'k7-deferred-income', 'accountCodes': ['2401']},
    'useK8FormData': {'prefix': 'K8-', 'label': 'K8', 'componentType': 'k8-selling-expenses', 'accountCodes': ['6601']},
    'useK9FormData': {'prefix': 'K9-', 'label': 'K9', 'componentType': 'k9-admin-expenses', 'accountCodes': ['6602']},
    'useK10FormData': {'prefix': 'K10-', 'label': 'K10', 'componentType': 'k10-other-income', 'accountCodes': ['6117']},
    'useK11FormData': {'prefix': 'K11-', 'label': 'K11', 'componentType': 'k11-asset-impairment-loss', 'accountCodes': ['6701']},
    'useK12FormData': {'prefix': 'K12-', 'label': 'K12', 'componentType': 'k12-non-operating-income', 'accountCodes': ['6301']},
    'useK13FormData': {'prefix': 'K13-', 'label': 'K13', 'componentType': 'k13-non-operating-expense', 'accountCodes': ['6711']},
    # ─── L 循环（借款/负债） ──────────────────────────────────────────────
    'useL2FormData': {'prefix': 'L2-', 'label': 'L2', 'componentType': 'l2-interest-payable', 'accountCodes': ['2231']},
    'useL3FormData': {'prefix': 'L3-', 'label': 'L3', 'componentType': 'l3-long-term-loans', 'accountCodes': ['2501']},
    'useL4FormData': {'prefix': 'L4-', 'label': 'L4', 'componentType': 'l4-bonds-payable', 'accountCodes': ['2502']},
    'useL5FormData': {'prefix': 'L5-', 'label': 'L5', 'componentType': 'l5-long-term-payables', 'accountCodes': ['2701', '2702']},
    'useL6FormData': {'prefix': 'L6-', 'label': 'L6', 'componentType': 'l6-special-payables', 'accountCodes': ['2601']},
    'useL7FormData': {'prefix': 'L7-', 'label': 'L7', 'componentType': 'l7-other-noncurrent-liabilities', 'accountCodes': ['2801']},
    'useL8FormData': {'prefix': 'L8-', 'label': 'L8', 'componentType': 'l8-financial-expenses', 'accountCodes': ['6603']},
    # ─── M 循环（权益） ───────────────────────────────────────────────────
    'useM1FormData': {'prefix': 'M1-', 'label': 'M1', 'componentType': 'm1-dividends-payable', 'accountCodes': ['2232']},
    'useM2FormData': {'prefix': 'M2-', 'label': 'M2', 'componentType': 'm2-paid-in-capital', 'accountCodes': ['4001']},
    'useM3FormData': {'prefix': 'M3-', 'label': 'M3', 'componentType': 'm3-treasury-stock', 'accountCodes': ['4002']},
    'useM4FormData': {'prefix': 'M4-', 'label': 'M4', 'componentType': 'm4-capital-reserve', 'accountCodes': ['4002']},
    'useM5FormData': {'prefix': 'M5-', 'label': 'M5', 'componentType': 'm5-surplus-reserve', 'accountCodes': ['4101']},
    'useM6FormData': {'prefix': 'M6-', 'label': 'M6', 'componentType': 'm6-retained-earnings', 'accountCodes': ['4104']},
    'useM7FormData': {'prefix': 'M7-', 'label': 'M7', 'componentType': 'm7-special-reserve', 'accountCodes': ['4201']},
    'useM8FormData': {'prefix': 'M8-', 'label': 'M8', 'componentType': 'm8-general-risk-reserve', 'accountCodes': ['4104']},
    'useM9FormData': {'prefix': 'M9-', 'label': 'M9', 'componentType': 'm9-other-comprehensive-income', 'accountCodes': ['4103']},
    'useM10FormData': {'prefix': 'M10-', 'label': 'M10', 'componentType': 'm10-other-equity-instruments', 'accountCodes': ['4003']},
    # ─── N 循环（税费/递延） ──────────────────────────────────────────────
    'useN1FormData': {'prefix': 'N1-', 'label': 'N1', 'componentType': 'n1-deferred-tax-assets', 'accountCodes': ['1811']},
    'useN2FormData': {'prefix': 'N2-', 'label': 'N2', 'componentType': 'n2-taxes-payable', 'accountCodes': ['2221']},
    'useN3FormData': {'prefix': 'N3-', 'label': 'N3', 'componentType': 'n3-deferred-tax-liabilities', 'accountCodes': ['2901']},
    'useN4FormData': {'prefix': 'N4-', 'label': 'N4', 'componentType': 'n4-taxes-and-surcharges', 'accountCodes': ['6403']},
    'useN5FormData': {'prefix': 'N5-', 'label': 'N5', 'componentType': 'n5-income-tax-expense', 'accountCodes': ['6801']},
}

# ─── SKIP_LIST ────────────────────────────────────────────────────────────────
# 非同构文件：包含复杂业务逻辑（htmlData 解析/特殊 DualMode/ECL 引擎/多子表 orchestration）
# 超越简单 checklist 持久化模式，不适合工厂化迁移。

SKIP_LIST: Set[str] = {
    # D 循环 — 复杂业务逻辑
    'useD1FormData',       # D1 应收票据: 多科目 selfLoad + htmlData 复杂解析
    'useD2FormData',       # D2 应收账款: 复杂 ECL/账龄联动/事件总线
    # D4-D7 已在迁移列表中但有 componentType，保留
    # F 循环 — 多子表/特殊模式
    'useF2FormData',       # F2 存货主表: 多子模块 orchestration + 盘点/估值/特殊联动
    'useF2InvMaiFormData', # F2 存货主入口: 有独立 DualMode
    'useF2InvSpeFormData', # F2 存货特殊: 独立 DualMode + FormulaEngine
    'useF2InvValFormData', # F2 存货估值: 独立 DualMode + FormulaEngine
    'useF2SpecialFormData',  # F2 存货特殊: 独立 componentType + 特殊逻辑
    'useF2StocktakeFormData',  # F2 盘点: 独立 DualMode + OCR
    'useF3NotPayFormData',  # F3 应付票据子: 独立 DualMode
    'useF4AccPayFormData',  # F4 应付账款子: 独立 DualMode
    'useF5CosSalFormData',  # F5 营业成本: 独立模式
    # G 循环 — ECL/SPPI/子模块
    'useG4EclFormData',    # G4 债权 ECL: 复杂 ECL 三阶段引擎
    'useG4BonEclFormData', # G4 债券 ECL 子表
    'useG4BonInvFormData', # G4 债券投资子表: 独立 DualMode + FormulaEngine
    'useG4BonSppFormData', # G4 债券 SPPI 子表
    'useG5LonRecFormData', # G5 长期应收子表
    'useG5LonTerFormData', # G5 长期待收子表: 独立 DualMode + FormulaEngine
    'useG6BonEclFormData', # G6 其他债权 ECL 子表
    'useG6BonSppFormData', # G6 其他债权 SPPI 子表
    'useG6OthBonFormData', # G6 其他债权子表: 独立 DualMode + FormulaEngine
    'useG7EquMaiFormData', # G7 权益主投资子表
    'useG7EquMetFormData', # G7 权益法子表
    'useG7EquSubFormData', # G7 子公司投资子表
    'useG7LonTerFormData', # G7 长期股权子表: 独立 DualMode + FormulaEngine
    'useG9OthNcfFormData', # G9 其他非流动子表
    'useG10TraFinFormData',  # G10 交易性子表: 独立 DualMode + FormulaEngine
    'useG11InvIncFormData',  # G11 投资收益子表: 独立 DualMode + FormulaEngine
    'useG12NetHedFormData',  # G12 套期净敞口子表: 独立 DualMode + FormulaEngine
    'useG13FaiValFormData',  # G13 公允价值子表: 独立 DualMode + FormulaEngine
    'useG14CreImpFormData',  # G14 信用减值子表: 独立 DualMode + FormulaEngine
    'useG2IntRecFormData',   # G2 应收利息子表: 独立 DualMode + FormulaEngine
    'useG3DivRecFormData',   # G3 应收股利子表: 独立 DualMode + FormulaEngine
    # A/B 循环 — 非 D~N 实质性底稿
    'useA111FormData',     # A111 声明书: 非 checklist 模式
    'useB22AFormData',     # B22A 控制矩阵: 非 checklist 模式
    'useB22BFormData',     # B22B 缺陷: 非 checklist 模式
    'useB23FormData',      # B23 流程控制: 非 checklist 模式
    'useB30FormData',      # B30 组审计: 非 checklist 模式
    'useB50FormData',      # B50 风险矩阵: 非 checklist 模式
}

# ─── 循环前缀映射（用于 --cycle 过滤） ────────────────────────────────────────

CYCLE_PREFIX_MAP = {
    'D': 'D',
    'E': 'E',
    'F': 'F',
    'G': 'G',
    'H': 'H',
    'I': 'I',
    'K': 'K',
    'L': 'L',
    'M': 'M',
    'N': 'N',
}


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def extract_cycle(composable_name: str) -> str:
    """从 composable 名称中提取循环字母（如 useK1FormData → K）"""
    m = re.match(r'use([A-Z])', composable_name)
    return m.group(1) if m else ''


def find_composable_files() -> List[Path]:
    """扫描 composables 目录，找到所有 useXFormData.ts 文件"""
    if not COMPOSABLES_DIR.exists():
        print(f'[ERROR] composables 目录不存在: {COMPOSABLES_DIR}', file=sys.stderr)
        sys.exit(1)

    pattern = re.compile(r'^use[A-Z].*FormData\.ts$')
    files = []
    for f in sorted(COMPOSABLES_DIR.iterdir()):
        if f.is_file() and pattern.match(f.name):
            files.append(f)
    return files


def is_already_migrated(file_path: Path) -> bool:
    """检查文件是否已使用 createChecklistFormData 工厂"""
    try:
        content = file_path.read_text(encoding='utf-8')
        return 'createChecklistFormData' in content or 'useChecklistPersistence' in content
    except (OSError, UnicodeDecodeError):
        return False


def extract_hooks(file_path: Path) -> dict:
    """
    从原始 composable 文件中提取 normalizeResponse/afterSave 钩子。

    扫描规则：
    - normalizeResponse: 寻找对 response 进行规范化/兼容双层 JSON 的逻辑
      标志模式: `JSON.parse(`, `normalizeResponse`, `unwrap` + response 处理
    - afterSave / onAfterSave: 寻找保存后回调钩子
      标志模式: `onAfterSave`, `afterSave`, `opts.onAfterSave?.()`

    返回 dict:
      {
        'has_normalize_response': bool,
        'has_after_save': bool,
        'normalize_response_hint': str | None,  # 描述用途
        'after_save_hint': str | None,           # 描述用途
      }
    """
    result = {
        'has_normalize_response': False,
        'has_after_save': False,
        'normalize_response_hint': None,
        'after_save_hint': None,
    }

    try:
        content = file_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return result

    # ─── 检测 normalizeResponse 模式 ─────────────────────────────────────
    # 同构文件中的 normalizeResponse 通常表现为:
    #   - JSON.parse 双层兼容解析
    #   - remark 字段的 JSON.parse 包装
    normalize_patterns = [
        re.compile(r'normalizeResponse'),
        re.compile(r'JSON\.parse\s*\(\s*(?:r|resp|response)\.remark'),
        re.compile(r'_unwrapDoubleJson|unwrapRemark|parseRemark'),
    ]

    for pat in normalize_patterns:
        if pat.search(content):
            result['has_normalize_response'] = True
            result['normalize_response_hint'] = 'historical double-JSON unwrap compatibility'
            break

    # ─── 检测 afterSave / onAfterSave 模式 ────────────────────────────────
    # 同构文件中的 afterSave 通常表现为:
    #   - opts.onAfterSave?.() 回调
    #   - scheduleAutoSnapshot / 版本快照调度
    #   - EventBus publish 附注刷新
    after_save_patterns = [
        re.compile(r'onAfterSave'),
        re.compile(r'afterSave'),
        re.compile(r'scheduleAutoSnapshot'),
    ]

    for pat in after_save_patterns:
        if pat.search(content):
            result['has_after_save'] = True
            # 判断具体用途
            if 'scheduleAutoSnapshot' in content:
                result['after_save_hint'] = 'version snapshot scheduling'
            elif 'EventBus' in content or 'eventBus' in content:
                result['after_save_hint'] = 'EventBus notification'
            else:
                result['after_save_hint'] = 'post-save callback'
            break

    return result


def generate_migration_template(composable_name: str, config: dict, hooks: Optional[dict] = None) -> str:
    """
    生成迁移后的文件内容模板。

    Task 5.2: 完整的模板生成逻辑——
    1. 读取原始文件提取 normalizeResponse/afterSave 钩子（通过 extract_hooks）
    2. 生成替换内容：import factory + 导出同名函数 + 返回 createChecklistFormData(config)
    3. 保持文件编码 UTF-8，保持相同 export 函数签名

    模板格式对齐 design.md §3 迁移模板规格。
    """
    prefix = config['prefix']
    label = config['label']
    component_type = config['componentType']
    account_codes = config['accountCodes']

    # 从 composable 名称提取函数名
    func_name = composable_name

    codes_str = ', '.join(f"'{c}'" for c in account_codes)

    # ─── 构建 config 对象字符串 ────────────────────────────────────────────
    config_lines = [
        '    wpId,',
        '    projectId,',
        '    year,',
        f"    itemPrefix: '{prefix}',",
        f"    label: '{label}',",
        f"    forceComponentType: '{component_type}',",
        f"    accountCodes: [{codes_str}],",
    ]

    # 如有钩子，追加 normalizeResponse / afterSave 占位注释
    if hooks and hooks.get('has_normalize_response'):
        hint = hooks.get('normalize_response_hint') or 'response normalization'
        config_lines.append(f"    // normalizeResponse: {hint} — inherit from factory default")

    if hooks and hooks.get('has_after_save'):
        hint = hooks.get('after_save_hint') or 'post-save callback'
        config_lines.append(f"    // afterSave: {hint} — handled by factory (scheduleAutoSnapshot via persistence)")

    config_block = '\n'.join(config_lines)

    template = f"""/**
 * {func_name} — {label} checklist 持久化（工厂化迁移）
 *
 * 迁移自同构自建网络实现 → createChecklistFormData 工厂调用。
 * 保留相同的导出 API，消费组件无需修改。
 */
import {{ createChecklistFormData, type ChecklistFormDataReturn }} from '../factories/createChecklistFormData'
import {{ ref, type Ref }} from 'vue'

export function {func_name}(wpId: Ref<string>, projectId: Ref<string>, year?: Ref<number | undefined>): ChecklistFormDataReturn {{
  return createChecklistFormData({{
{config_block}
  }})
}}

export default {func_name}
"""
    return template


# ─── 迁移报告 ─────────────────────────────────────────────────────────────────

@dataclass
class MigrationReport:
    """迁移执行报告"""
    total_scanned: int = 0
    eligible: int = 0
    skipped: int = 0
    already_migrated: int = 0
    migrated: int = 0
    failed: int = 0
    skipped_names: List[str] = field(default_factory=list)
    migrated_names: List[str] = field(default_factory=list)
    failed_names: List[str] = field(default_factory=list)
    not_in_map: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            '',
            '═══════════════════════════════════════════════════════════════',
            '  FormData Factory Migration Report',
            '═══════════════════════════════════════════════════════════════',
            f'  Total scanned:     {self.total_scanned}',
            f'  Eligible:          {self.eligible}',
            f'  Already migrated:  {self.already_migrated}',
            f'  Skipped (complex): {self.skipped}',
            f'  Not in map:        {len(self.not_in_map)}',
            f'  Migrated:          {self.migrated}',
            f'  Failed:            {self.failed}',
            '───────────────────────────────────────────────────────────────',
        ]
        if self.skipped_names:
            lines.append('  Skipped files:')
            for name in self.skipped_names[:10]:
                lines.append(f'    - {name}')
            if len(self.skipped_names) > 10:
                lines.append(f'    ... and {len(self.skipped_names) - 10} more')
        if self.not_in_map:
            lines.append('  Not in migration map:')
            for name in self.not_in_map[:10]:
                lines.append(f'    - {name}')
            if len(self.not_in_map) > 10:
                lines.append(f'    ... and {len(self.not_in_map) - 10} more')
        if self.migrated_names:
            lines.append('  Migrated:')
            for name in self.migrated_names:
                lines.append(f'    [OK] {name}')
        if self.failed_names:
            lines.append('  Failed:')
            for name in self.failed_names:
                lines.append(f'    [FAIL] {name}')
        lines.append('═══════════════════════════════════════════════════════════════')
        lines.append('')
        return '\n'.join(lines)


# ─── 主逻辑 ───────────────────────────────────────────────────────────────────

def run_migration(
    *,
    apply: bool = False,
    cycle_filter: Optional[str] = None,
) -> MigrationReport:
    """
    执行 FormData 工厂迁移。

    Args:
        apply: True=写入文件, False=dry-run 仅报告
        cycle_filter: 可选循环过滤（如 'K' 仅处理 K 循环）
    """
    report = MigrationReport()

    # 1. 扫描文件
    all_files = find_composable_files()
    report.total_scanned = len(all_files)

    for file_path in all_files:
        composable_name = file_path.stem  # e.g. "useK1FormData"

        # 2. 循环过滤
        if cycle_filter:
            file_cycle = extract_cycle(composable_name)
            if file_cycle != cycle_filter:
                continue

        # 3. 检查是否在 SKIP_LIST
        if composable_name in SKIP_LIST:
            report.skipped += 1
            report.skipped_names.append(composable_name)
            continue

        # 4. 检查是否已迁移
        if is_already_migrated(file_path):
            report.already_migrated += 1
            continue

        # 5. 检查是否在迁移 MAP 中
        if composable_name not in FORMDATA_MIGRATION_MAP:
            report.not_in_map.append(composable_name)
            continue

        # 6. 标记为 eligible
        report.eligible += 1
        config = FORMDATA_MIGRATION_MAP[composable_name]

        # 7. 提取原始文件中的钩子（normalizeResponse/afterSave）
        hooks = extract_hooks(file_path)

        # 8. 生成迁移模板
        try:
            new_content = generate_migration_template(composable_name, config, hooks)
        except Exception as e:
            report.failed += 1
            report.failed_names.append(f'{composable_name}: {e}')
            continue

        # 9. 写入或报告
        if apply:
            try:
                file_path.write_text(new_content, encoding='utf-8')
                report.migrated += 1
                report.migrated_names.append(composable_name)
            except OSError as e:
                report.failed += 1
                report.failed_names.append(f'{composable_name}: {e}')
        else:
            # dry-run: 报告将要迁移的内容
            report.migrated += 1
            hook_info = ''
            if hooks.get('has_normalize_response') or hooks.get('has_after_save'):
                hook_parts = []
                if hooks.get('has_normalize_response'):
                    hook_parts.append('normalizeResponse')
                if hooks.get('has_after_save'):
                    hook_parts.append('afterSave')
                hook_info = f' [hooks: {"+".join(hook_parts)}]'
            report.migrated_names.append(f'{composable_name} (dry-run){hook_info}')

    return report


# ─── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='FormData 工厂迁移脚本：将同构 composable 替换为 createChecklistFormData 调用',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python migrate_formdata_factory.py --dry-run              # 仅报告，不修改文件
  python migrate_formdata_factory.py --apply                # 执行迁移写入
  python migrate_formdata_factory.py --dry-run --cycle K    # 仅报告 K 循环
  python migrate_formdata_factory.py --apply --cycle G      # 仅迁移 G 循环
        """,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--apply',
        action='store_true',
        default=False,
        help='执行迁移，写入文件（默认 dry-run）',
    )
    mode.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='仅报告，不修改文件（默认）',
    )
    parser.add_argument(
        '--cycle',
        type=str,
        default=None,
        metavar='LETTER',
        help='按循环字母过滤（D/F/G/H/I/K/L/M/N）',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # 验证 cycle 参数
    if args.cycle:
        cycle = args.cycle.upper()
        if cycle not in CYCLE_PREFIX_MAP:
            print(f'[ERROR] 无效循环: {args.cycle}，有效值: {", ".join(sorted(CYCLE_PREFIX_MAP.keys()))}', file=sys.stderr)
            sys.exit(1)
    else:
        cycle = None

    mode_label = 'APPLY (写入文件)' if args.apply else 'DRY-RUN (仅报告)'
    cycle_label = f' [cycle={cycle}]' if cycle else ' [all cycles]'
    print(f'FormData Factory Migration — {mode_label}{cycle_label}')
    print(f'Composables dir: {COMPOSABLES_DIR}')
    print()

    report = run_migration(apply=args.apply, cycle_filter=cycle)
    print(report.summary())

    # exit code: 0 成功, 1 有失败
    sys.exit(1 if report.failed > 0 else 0)


if __name__ == '__main__':
    main()
