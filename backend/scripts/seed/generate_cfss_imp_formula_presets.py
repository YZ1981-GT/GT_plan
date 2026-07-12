"""生成现金流附表(CFSS) + 资产减值准备表(IMP) 的公式预设。

现金流附表：间接法，从净利润调节为经营活动现金流量
- 净利润取自 IS
- 调整项取 TB 变动额
- 经营活动净额 = 净利润 + 各调整项（勾稽 CFS 经营净额）
- 现金净变动 = 期末 - 期初

资产减值准备表：各类减值准备余额
- 每项从 TB 对应减值准备科目取期末余额
- 合计 = 各行之和

Usage:
    python backend/scripts/seed/generate_cfss_imp_formula_presets.py [--dry-run]
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# ══════════════════════════════════════════════════════════════════════════════
# 现金流附表 (CFSS)
# ══════════════════════════════════════════════════════════════════════════════

CFSS_FORMULAS: dict[str, dict] = {
    # 净利润 — 取自利润表 IS-024
    'CFSS-002': {
        'expression': "ROW('IS-024')",
        'description': '净利润 — 取自利润表净利润（IS-024）',
    },
    # 各调整项 — TB 变动额
    'CFSS-003': {
        'expression': "TB('6701', '发生额')",
        'description': '加：资产减值损失 — 取损益科目 6701 发生额',
    },
    'CFSS-004': {
        'expression': "TB('6711', '发生额')",
        'description': '信用减值损失 — 取损益科目 6711 发生额',
    },
    'CFSS-005': {
        'expression': "TB('1602_DEP', '发生额')",
        'description': '固定资产折旧/油气资产折耗/生产性生物资产折旧 — 本期计提折旧额',
    },
    'CFSS-006': {
        'expression': "TB('1701_DEP', '发生额')",
        'description': '使用权资产折旧 — 本期计提折旧额',
    },
    'CFSS-007': {
        'expression': "TB('1702_AMO', '发生额')",
        'description': '无形资产摊销 — 本期摊销额',
    },
    'CFSS-008': {
        'expression': "TB('1801_AMO', '发生额')",
        'description': '长期待摊费用摊销 — 本期摊销额',
    },
    'CFSS-009': {
        'expression': "TB('6115_DISP', '发生额') * -1",
        'description': '处置固定资产/无形资产/其他长期资产的损失（收益为负）',
    },
    'CFSS-010': {
        'expression': "TB('6115_SCRAP', '发生额') * -1",
        'description': '固定资产报废损失（收益为负）',
    },
    'CFSS-011': {
        'expression': "TB('6031', '发生额') * -1",
        'description': '公允价值变动损失（收益为负）',
    },
    'CFSS-012': {
        'expression': "TB('6604', '发生额')",
        'description': '财务费用（收益为负）',
    },
    'CFSS-013': {
        'expression': "TB('6111', '发生额') * -1",
        'description': '投资损失（收益为负）',
    },
    'CFSS-014': {
        'expression': "TB('1811', '期初余额') - TB('1811', '期末余额')",
        'description': '递延所得税资产减少（增加为负）',
    },
    'CFSS-015': {
        'expression': "TB('2911', '期末余额') - TB('2911', '期初余额')",
        'description': '递延所得税负债增加（减少为负）',
    },
    'CFSS-016': {
        'expression': "TB('1401', '期初余额') - TB('1401', '期末余额')",
        'description': '存货的减少（增加为负）',
    },
    'CFSS-017': {
        'expression': "(TB('1122', '期初余额') - TB('1122', '期末余额')) + (TB('1123', '期初余额') - TB('1123', '期末余额')) + (TB('1231', '期初余额') - TB('1231', '期末余额'))",
        'description': '经营性应收项目的减少（增加为负）= 应收账款+预付+其他应收 期初-期末',
    },
    'CFSS-018': {
        'expression': "(TB('2202', '期末余额') - TB('2202', '期初余额')) + (TB('2205', '期末余额') - TB('2205', '期初余额')) + (TB('2241A', '期末余额') - TB('2241A', '期初余额'))",
        'description': '经营性应付项目的增加（减少为负）= 应付账款+合同负债+其他应付 期末-期初',
    },
    'CFSS-019': {
        'expression': "0",
        'description': '其他（通常为零，需手工调整）',
    },
    # 经营活动净额 = 净利润 + 全部调整项（勾稽 CFS 经营活动净额）
    'CFSS-020': {
        'expression': "ROW('CFSS-002') + ROW('CFSS-003') + ROW('CFSS-004') + ROW('CFSS-005') + ROW('CFSS-006') + ROW('CFSS-007') + ROW('CFSS-008') + ROW('CFSS-009') + ROW('CFSS-010') + ROW('CFSS-011') + ROW('CFSS-012') + ROW('CFSS-013') + ROW('CFSS-014') + ROW('CFSS-015') + ROW('CFSS-016') + ROW('CFSS-017') + ROW('CFSS-018') + ROW('CFSS-019')",
        'description': '经营活动产生的现金流量净额 = 净利润 + 全部调整项',
    },
    # 不涉及现金收支的投筹资活动（通常为备注性信息，公式取 TB 变动额）
    'CFSS-022': {
        'expression': "TB('DEBT_TO_EQUITY', '变动额')",
        'description': '债务转为资本',
    },
    'CFSS-023': {
        'expression': "TB('CONV_BOND_1Y', '变动额')",
        'description': '一年内到期的可转换公司债券',
    },
    'CFSS-024': {
        'expression': "TB('1701_NEW', '变动额')",
        'description': '新增使用权资产',
    },
    # 现金及现金等价物净变动
    'CFSS-026': {
        'expression': "TB('1001', '期末余额')",
        'description': '现金的期末余额 — 取货币资金科目 1001 期末',
    },
    'CFSS-027': {
        'expression': "TB('1001', '期初余额')",
        'description': '现金的期初余额 — 取货币资金科目 1001 期初',
    },
    'CFSS-028': {
        'expression': "TB('1002_EQ', '期末余额')",
        'description': '现金等价物的期末余额',
    },
    'CFSS-029': {
        'expression': "TB('1002_EQ', '期初余额')",
        'description': '现金等价物的期初余额',
    },
    'CFSS-030': {
        'expression': "ROW('CFSS-026') - ROW('CFSS-027') + ROW('CFSS-028') - ROW('CFSS-029')",
        'description': '现金及现金等价物净增加额 = (现金期末-期初) + (等价物期末-期初)',
    },
}

# 标题行（无公式）
CFSS_TITLE_ROWS = {'CFSS-001', 'CFSS-021', 'CFSS-025'}

# ══════════════════════════════════════════════════════════════════════════════
# 资产减值准备表 (IMP)
# ══════════════════════════════════════════════════════════════════════════════

IMP_ACCOUNT_MAP: dict[str, str] = {
    'IMP-001': '1231_IMP',    # 坏账准备（合计：应收账款+其他应收款+应收票据）
    'IMP-002': '1122_IMP',    # 其中：应收账款坏账准备
    'IMP-003': '1401_IMP',    # 存货跌价准备
    'IMP-004': '1141_IMP',    # 合同资产减值准备
    'IMP-005': '1142_IMP',    # 合同取得成本减值准备
    'IMP-006': '1143_IMP',    # 合同履约成本减值准备
    'IMP-007': '1481_IMP',    # 持有待售资产减值准备
    'IMP-008': '1503_IMP',    # 债权投资减值准备
    'IMP-009': '1521_IMP',    # 长期股权投资减值准备
    'IMP-010': '1601_IMP',    # 投资性房地产减值准备
    'IMP-011': '1604',        # 固定资产减值准备
    'IMP-012': '1604A_IMP',   # 在建工程减值准备
    'IMP-013': '1621_IMP',    # 生产性生物资产减值准备
    'IMP-014': '1631_IMP',    # 油气资产减值准备
    'IMP-015': '1701_IMP',    # 使用权资产减值准备
    'IMP-016': '1702_IMP',    # 无形资产减值准备
    'IMP-017': '1711_IMP',    # 商誉减值准备
    'IMP-018': '1999_IMP',    # 其他减值准备
}

IMP_TOTAL_FORMULAS: dict[str, dict] = {
    'IMP-019': {
        'expression': "ROW('IMP-001') + ROW('IMP-003') + ROW('IMP-004') + ROW('IMP-005') + ROW('IMP-006') + ROW('IMP-007') + ROW('IMP-008') + ROW('IMP-009') + ROW('IMP-010') + ROW('IMP-011') + ROW('IMP-012') + ROW('IMP-013') + ROW('IMP-014') + ROW('IMP-015') + ROW('IMP-016') + ROW('IMP-017') + ROW('IMP-018')",
        'description': '资产减值准备合计 = 各项减值准备之和',
    },
}


def build_refs(expression: str) -> list[dict]:
    """从 expression 提取 ROW/TB 引用。"""
    refs = []
    for m in re.finditer(r"ROW\('([^']+)'\)", expression):
        refs.append({"formula_ref": f"ROW('{m.group(1)}')"})
    for m in re.finditer(r"TB\('([^']+)'", expression):
        refs.append({"formula_ref": f"TB('{m.group(1)}')"})
    return refs


def generate_cfss_presets() -> list[dict]:
    """Generate CFSS presets."""
    presets = []
    with open('backend/data/report_config_seed.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    rows = []
    for d in data:
        if d['report_type'] == 'cash_flow_supplement' and d['applicable_standard'] == 'soe_standalone':
            rows = d['rows']
            break

    for row in rows:
        code = row['row_code']
        name = row['row_name']
        if code in CFSS_TITLE_ROWS:
            continue
        if code in CFSS_FORMULAS:
            tf = CFSS_FORMULAS[code]
            presets.append({
                "page_key": "report:cash_flow_supplement",
                "target_cell": code,
                "expression": tf['expression'],
                "formula_type": "auto_calc",
                "refs": build_refs(tf['expression']),
                "source": "cfss_preset_generator",
                "description": tf['description'],
            })

    return presets


def generate_imp_presets() -> list[dict]:
    """Generate IMP presets."""
    presets = []
    with open('backend/data/report_config_seed.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    rows = []
    for d in data:
        if d['report_type'] == 'impairment_provision' and d['applicable_standard'] == 'soe_standalone':
            rows = d['rows']
            break

    for row in rows:
        code = row['row_code']
        name = row['row_name']

        if code in IMP_TOTAL_FORMULAS:
            tf = IMP_TOTAL_FORMULAS[code]
            presets.append({
                "page_key": "report:impairment_provision",
                "target_cell": code,
                "expression": tf['expression'],
                "formula_type": "auto_calc",
                "refs": build_refs(tf['expression']),
                "source": "imp_preset_generator",
                "description": tf['description'],
            })
            continue

        if code in IMP_ACCOUNT_MAP:
            acct = IMP_ACCOUNT_MAP[code]
            expression = f"TB('{acct}', '期末余额')"
            presets.append({
                "page_key": "report:impairment_provision",
                "target_cell": code,
                "expression": expression,
                "formula_type": "auto_calc",
                "refs": [{"formula_ref": f"TB('{acct}')"}],
                "source": "imp_preset_generator",
                "description": f"{name} — 取减值准备科目 {acct} 期末余额",
            })

    return presets


def main():
    dry_run = '--dry-run' in sys.argv

    cfss = generate_cfss_presets()
    imp = generate_imp_presets()
    all_presets = cfss + imp

    print(f"[CFSS] 生成 {len(cfss)} 条现金流附表预设")
    print(f"[IMP]  生成 {len(imp)} 条资产减值准备表预设")
    print(f"[TOTAL] {len(all_presets)} 条")

    if dry_run:
        print("\n[dry-run] CFSS 前 3 条：")
        for p in cfss[:3]:
            print(json.dumps(p, ensure_ascii=False, indent=2))
        print("\n[dry-run] IMP 前 3 条：")
        for p in imp[:3]:
            print(json.dumps(p, ensure_ascii=False, indent=2))
        return

    seed_path = Path('backend/data/formula_presets/formula_presets_seed.json')
    with open(seed_path, 'r', encoding='utf-8') as f:
        seed = json.load(f)

    existing_keys = {(p['page_key'], p['target_cell']) for p in seed['presets']}
    new_count = 0
    for p in all_presets:
        key = (p['page_key'], p['target_cell'])
        if key not in existing_keys:
            seed['presets'].append(p)
            existing_keys.add(key)
            new_count += 1

    with open(seed_path, 'w', encoding='utf-8') as f:
        json.dump(seed, f, ensure_ascii=False, indent=2)

    print(f"[OK] 追加 {new_count} 条到 {seed_path}")
    print(f"     总预设数: {len(seed['presets'])}")


if __name__ == '__main__':
    main()
