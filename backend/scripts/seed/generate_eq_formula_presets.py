"""生成权益变动表(EQ)全部33行的公式预设。

权益变动表的特殊性：
- 不像 BS/IS/CFS 那样每行对应一个 TB 科目
- 行次间是层级聚合关系（小计行=明细行之和，年末余额=年初+增减）
- 部分行取数来自其他报表（如"综合收益总额"= IS 的综合收益）
- 部分行取数来自本期权益类科目的变动额

公式类型：
- 合计/小计行：auto_calc，ROW() 求和
- 跨表取数行：auto_calc，引用其他报表 ROW()
- 权益科目变动行：auto_calc，TB 取变动额
- 标题行：无公式（跳过）

Usage:
    python backend/scripts/seed/generate_eq_formula_presets.py [--dry-run]
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# ── 权益变动表公式定义 ──
# 每行的公式（合计/小计/跨表引用/TB取变动额）
EQ_FORMULAS: dict[str, dict] = {
    # 二、本年年初余额 = 上年末余额 + 政策变更 + 差错更正 + 其他
    'EQ-005': {
        'expression': "ROW('EQ-001') + ROW('EQ-002') + ROW('EQ-003') + ROW('EQ-004')",
        'description': '本年年初余额 = 上年年末余额 + 会计政策变更 + 前期差错更正 + 其他',
    },
    # 三、本年增减变动 = 综合收益 + 投入/减少 + 专项储备 + 利润分配 + 内部结转
    'EQ-006': {
        'expression': "ROW('EQ-007') + ROW('EQ-008') + ROW('EQ-013') + ROW('EQ-016') + ROW('EQ-026')",
        'description': '本年增减变动金额 = 综合收益总额 + 所有者投入和减少资本 + 专项储备 + 利润分配 + 所有者权益内部结转',
    },
    # （一）综合收益总额 — 取自利润表 IS-026（综合收益总额）
    'EQ-007': {
        'expression': "ROW('IS-026')",
        'description': '综合收益总额 — 取自利润表综合收益总额（IS-026）',
    },
    # （二）所有者投入和减少资本 = 普通股 + 其他权益工具 + 股份支付 + 其他
    'EQ-008': {
        'expression': "ROW('EQ-009') + ROW('EQ-010') + ROW('EQ-011') + ROW('EQ-012')",
        'description': '所有者投入和减少资本 = 投入普通股 + 其他权益工具 + 股份支付 + 其他',
    },
    # （三）专项储备提取和使用 = 提取 - 使用
    'EQ-013': {
        'expression': "ROW('EQ-014') - ROW('EQ-015')",
        'description': '专项储备净额 = 提取专项储备 - 使用专项储备',
    },
    # （四）利润分配 = 提取盈余公积 + 提取一般风险准备 + 对所有者分配 + 其他
    'EQ-016': {
        'expression': "ROW('EQ-017') + ROW('EQ-023') + ROW('EQ-024') + ROW('EQ-025')",
        'description': '利润分配 = 提取盈余公积 + 提取一般风险准备 + 对所有者分配 + 其他',
    },
    # 1.提取盈余公积 = 法定 + 任意 + 储备基金 + 企业发展基金 + 利润归还投资
    'EQ-017': {
        'expression': "ROW('EQ-018') + ROW('EQ-019') + ROW('EQ-020') + ROW('EQ-021') + ROW('EQ-022')",
        'description': '提取盈余公积 = 法定公积金 + 任意公积金 + 储备基金 + 企业发展基金 + 利润归还投资',
    },
    # （五）所有者权益内部结转 = 资本公积转增 + 盈余公积转增 + 弥补亏损 + 设定受益 + 其他综合收益结转 + 其他
    'EQ-026': {
        'expression': "ROW('EQ-027') + ROW('EQ-028') + ROW('EQ-029') + ROW('EQ-030') + ROW('EQ-031') + ROW('EQ-032')",
        'description': '所有者权益内部结转 = 资本公积转增 + 盈余公积转增 + 弥补亏损 + 设定受益变动 + 其他综合收益结转 + 其他',
    },
    # 四、本年年末余额 = 年初余额 + 本年增减变动
    'EQ-033': {
        'expression': "ROW('EQ-005') + ROW('EQ-006')",
        'description': '本年年末余额 = 本年年初余额 + 本年增减变动金额',
    },
}

# 明细行：权益类科目变动额取数
EQ_TB_MAP: dict[str, tuple[str, str]] = {
    # (科目代码, 取数说明)
    'EQ-001': ('4001+4002+4101-4102+4103+4104+4201+4301+4401', '上年年末余额 — 取权益类科目上年审定合计'),
    'EQ-002': ('ADJ_POLICY', '会计政策变更 — 追溯调整额'),
    'EQ-003': ('ADJ_ERROR', '前期差错更正 — 更正金额'),
    'EQ-004': ('ADJ_OTHER', '其他调整'),
    'EQ-009': ('4001_CHG', '所有者投入的普通股 — 实收资本本期增加额'),
    'EQ-010': ('4002_CHG', '其他权益工具持有者投入资本 — 本期变动'),
    'EQ-011': ('4101_SBC', '股份支付计入所有者权益的金额'),
    'EQ-012': ('4001_OTH', '其他投入/减少'),
    'EQ-014': ('4104_ADD', '提取专项储备'),
    'EQ-015': ('4104_USE', '使用专项储备'),
    'EQ-018': ('4201A_CHG', '法定公积金 — 本期提取额'),
    'EQ-019': ('4201B_CHG', '任意公积金 — 本期提取额'),
    'EQ-020': ('4201C_CHG', '储备基金 — 本期提取额'),
    'EQ-021': ('4201D_CHG', '企业发展基金 — 本期提取额'),
    'EQ-022': ('4201E_CHG', '利润归还投资 — 本期提取额'),
    'EQ-023': ('4301_CHG', '提取一般风险准备 — 本期变动'),
    'EQ-024': ('4401_DIV', '对所有者（或股东）的分配 — 本期分红'),
    'EQ-025': ('4401_OTH', '其他利润分配'),
    'EQ-027': ('4101_TO_4001', '资本公积转增资本（或股本）'),
    'EQ-028': ('4201_TO_4001', '盈余公积转增资本（或股本）'),
    'EQ-029': ('4401_LOSS', '弥补亏损'),
    'EQ-030': ('4103_DB', '设定受益计划变动额结转留存收益'),
    'EQ-031': ('4103_OCI', '其他综合收益结转留存收益'),
    'EQ-032': ('4001_INTR', '其他内部结转'),
}


def generate_presets() -> list[dict]:
    presets = []

    with open('backend/data/report_config_seed.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    eq = None
    for d in data:
        if d['report_type'] == 'equity_statement' and d['applicable_standard'] == 'soe_standalone':
            eq = d
            break
    if not eq:
        print("[WARN] equity_statement/soe_standalone not found")
        return []

    for row in eq['rows']:
        code = row['row_code']
        name = row['row_name']

        # 合计/小计/跨表行
        if code in EQ_FORMULAS:
            tf = EQ_FORMULAS[code]
            refs = [{"formula_ref": f"ROW('{m.group(1)}')"} for m in re.finditer(r"ROW\('([^']+)'\)", tf['expression'])]
            presets.append({
                "page_key": "report:equity_statement",
                "target_cell": code,
                "expression": tf['expression'],
                "formula_type": "auto_calc",
                "refs": refs,
                "source": "eq_preset_generator",
                "description": tf['description'],
            })
            continue

        # 明细行：权益科目变动额
        if code in EQ_TB_MAP:
            acct, desc = EQ_TB_MAP[code]
            expression = f"TB('{acct}', '变动额')"
            presets.append({
                "page_key": "report:equity_statement",
                "target_cell": code,
                "expression": expression,
                "formula_type": "auto_calc",
                "refs": [{"formula_ref": f"TB('{acct}')"}],
                "source": "eq_preset_generator",
                "description": f"{name} — {desc}",
            })

    return presets


def main():
    dry_run = '--dry-run' in sys.argv
    presets = generate_presets()

    total_f = sum(1 for p in presets if p['target_cell'] in EQ_FORMULAS)
    total_tb = len(presets) - total_f
    print(f"[EQ] 生成 {len(presets)} 条权益变动表预设")
    print(f"  - 合计/小计/跨表行: {total_f}")
    print(f"  - 明细行(权益科目变动额): {total_tb}")

    if dry_run:
        print("\n[dry-run] 前 5 条：")
        for p in presets[:5]:
            print(json.dumps(p, ensure_ascii=False, indent=2))
        return

    seed_path = Path('backend/data/formula_presets/formula_presets_seed.json')
    with open(seed_path, 'r', encoding='utf-8') as f:
        seed = json.load(f)

    existing_keys = {(p['page_key'], p['target_cell']) for p in seed['presets']}
    new_count = 0
    for p in presets:
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
