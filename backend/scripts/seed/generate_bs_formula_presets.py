"""生成资产负债表全部 129 行的公式预设（auto_calc）。

逻辑：
- 标题行（如"流动资产："/"非流动资产："等）：无公式（skip）
- 明细行：TB('{科目代码}', '期末余额') — 从试算表取审定数
- 合计行：SUM 对应区间明细行
- 平衡勾稽：资产总计 = 负债合计 + 所有者权益合计

科目映射参考 trial_balance 标准科目代码（致同 2025 修订版）。
输出追加到 formula_presets_seed.json 的 presets 数组。

Usage:
    python backend/scripts/seed/generate_bs_formula_presets.py [--dry-run]
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# ── 科目代码映射：BS row_code → 标准科目代码（致同2025修订版） ──
# 明细行取 TB('科目代码', '期末余额')；无科目的行（特殊标记△▲#*）跳过
BS_ACCOUNT_MAP: dict[str, str] = {
    'BS-002': '1001',    # 货币资金
    'BS-003': '1011',    # 结算备付金
    'BS-004': '1021',    # 拆出资金
    'BS-005': '1101',    # 交易性金融资产
    'BS-006': '1105',    # 衍生金融资产
    'BS-007': '1121',    # 应收票据
    'BS-008': '1122',    # 应收账款
    'BS-009': '1124',    # 应收款项融资
    'BS-010': '1123',    # 预付款项
    'BS-011': '1201',    # 应收保费
    'BS-012': '1211',    # 应收分保账款
    'BS-013': '1212',    # 应收分保合同准备金
    'BS-014': '1221',    # 应收资金集中管理款
    'BS-015': '1231',    # 其他应收款
    'BS-016': '1131',    # 应收股利（其他应收款子项，展示用）
    'BS-017': '1202',    # 买入返售金融资产
    'BS-018': '1401',    # 存货
    'BS-019': '1403',    # 原材料（存货子项）
    'BS-020': '1406',    # 库存商品/产成品（存货子项）
    'BS-021': '1141',    # 合同资产
    'BS-022': '1301',    # 保险合同资产
    'BS-023': '1302',    # 分出再保险合同资产
    'BS-024': '1481',    # 持有待售资产
    'BS-025': '1305',    # 一年内到期的非流动资产
    'BS-026': '1499',    # 其他流动资产
    # 非流动资产
    'BS-029': '1501',    # 发放贷款和垫款
    'BS-030': '1503',    # 债权投资
    'BS-031': '1504',    # 其他债权投资
    'BS-032': '1511',    # 长期应收款
    'BS-033': '1511A',   # 长期股权投资（用 1511 或 1521，此处 1521）
    'BS-034': '1522',    # 其他权益工具投资
    'BS-035': '1524',    # 其他非流动金融资产
    'BS-036': '1601',    # 投资性房地产
    'BS-037': '1601A',   # 固定资产（净额=原价-折旧-减值）
    'BS-038': '1602',    # 固定资产原价（子项）
    'BS-039': '1603',    # 累计折旧（子项）
    'BS-040': '1604',    # 固定资产减值准备（子项）
    'BS-041': '1604A',   # 在建工程
    'BS-042': '1621',    # 生产性生物资产
    'BS-043': '1631',    # 油气资产
    'BS-044': '1701',    # 使用权资产
    'BS-045': '1702',    # 无形资产
    'BS-046': '1703',    # 开发支出
    'BS-047': '1711',    # 商誉
    'BS-048': '1801',    # 长期待摊费用
    'BS-049': '1811',    # 递延所得税资产
    'BS-050': '1901',    # 其他非流动资产
    'BS-051': '1902',    # 特准储备物资（子项）
    # 流动负债
    'BS-055': '2001',    # 短期借款
    'BS-056': '2011',    # 向中央银行借款
    'BS-057': '2021',    # 拆入资金
    'BS-058': '2101',    # 交易性金融负债
    'BS-059': '2105',    # 衍生金融负债
    'BS-060': '2201',    # 应付票据
    'BS-061': '2202',    # 应付账款
    'BS-062': '2203',    # 预收款项
    'BS-063': '2205',    # 合同负债
    'BS-064': '2211',    # 卖出回购金融资产款
    'BS-065': '2221',    # 吸收存款及同业存放
    'BS-066': '2231',    # 代理买卖证券款
    'BS-067': '2232',    # 代理承销证券款
    'BS-068': '2241',    # 预收保费
    'BS-069': '2211A',   # 应付职工薪酬
    'BS-070': '2211B',   # 应付工资（子项）
    'BS-071': '2211C',   # 应付福利费（子项）
    'BS-072': '2211D',   # 职工奖励及福利基金（子项）
    'BS-073': '2221A',   # 应交税费
    'BS-074': '2221B',   # 应交税金（子项）
    'BS-075': '2241A',   # 其他应付款
    'BS-076': '2241B',   # 应付股利（子项）
    'BS-077': '2251',    # 应付手续费及佣金
    'BS-078': '2261',    # 应付分保账款
    'BS-079': '2281',    # 持有待售负债
    'BS-080': '2501',    # 一年内到期的非流动负债
    'BS-081': '2299',    # 其他流动负债
    # 非流动负债
    'BS-084': '2601',    # 保险合同准备金
    'BS-085': '2501A',   # 长期借款
    'BS-086': '2601A',   # 应付债券
    'BS-087': '2602',    # 优先股（子项）
    'BS-088': '2603',    # 永续债（子项）
    'BS-089': '2611',    # 保险合同负债
    'BS-090': '2612',    # 分出再保险合同负债
    'BS-091': '2701',    # 租赁负债
    'BS-092': '2801',    # 长期应付款
    'BS-093': '2802',    # 长期应付职工薪酬
    'BS-094': '2901',    # 预计负债
    'BS-095': '2711',    # 递延收益
    'BS-096': '2911',    # 递延所得税负债
    'BS-097': '2999',    # 其他非流动负债
    'BS-098': '2998',    # 特准储备基金（子项）
    # 所有者权益
    'BS-102': '4001',    # 实收资本
    'BS-103': '4001A',   # 国家资本（子项）
    'BS-104': '4001B',   # 国有法人资本（子项）
    'BS-105': '4001C',   # 集体资本（子项）
    'BS-106': '4001D',   # 民营资本（子项）
    'BS-107': '4001E',   # 外商资本（子项）
    'BS-108': '4001F',   # 已归还投资（子项）
    'BS-109': '4001G',   # 实收资本净额
    'BS-110': '4002',    # 其他权益工具
    'BS-111': '4002A',   # 优先股（子项）
    'BS-112': '4002B',   # 永续债（子项）
    'BS-113': '4101',    # 资本公积
    'BS-114': '4102',    # 库存股
    'BS-115': '4103',    # 其他综合收益
    'BS-116': '4103A',   # 外币报表折算差额（子项）
    'BS-117': '4104',    # 专项储备
    'BS-118': '4201',    # 盈余公积
    'BS-119': '4201A',   # 法定公积金（子项）
    'BS-120': '4201B',   # 任意公积金（子项）
    'BS-121': '4201C',   # 储备基金（子项）
    'BS-122': '4201D',   # 企业发展基金（子项）
    'BS-123': '4201E',   # 利润归还投资（子项）
    'BS-124': '4301',    # 一般风险准备
    'BS-125': '4401',    # 未分配利润
    'BS-127': '4501',    # 少数股东权益
}

# ── 合计行公式定义 ──
# 合计行 = 其下属明细行的 ROW() 之和
TOTAL_FORMULAS: dict[str, dict] = {
    'BS-027': {  # 流动资产合计
        'expression': "ROW('BS-002') + ROW('BS-003') + ROW('BS-004') + ROW('BS-005') + ROW('BS-006') + ROW('BS-007') + ROW('BS-008') + ROW('BS-009') + ROW('BS-010') + ROW('BS-011') + ROW('BS-012') + ROW('BS-013') + ROW('BS-014') + ROW('BS-015') + ROW('BS-017') + ROW('BS-018') + ROW('BS-021') + ROW('BS-022') + ROW('BS-023') + ROW('BS-024') + ROW('BS-025') + ROW('BS-026')",
        'description': '流动资产合计 = 货币资金 + 结算备付金 + … + 其他流动资产',
    },
    'BS-052': {  # 非流动资产合计
        'expression': "ROW('BS-029') + ROW('BS-030') + ROW('BS-031') + ROW('BS-032') + ROW('BS-033') + ROW('BS-034') + ROW('BS-035') + ROW('BS-036') + ROW('BS-037') + ROW('BS-041') + ROW('BS-042') + ROW('BS-043') + ROW('BS-044') + ROW('BS-045') + ROW('BS-046') + ROW('BS-047') + ROW('BS-048') + ROW('BS-049') + ROW('BS-050')",
        'description': '非流动资产合计 = 发放贷款和垫款 + 债权投资 + … + 其他非流动资产',
    },
    'BS-053': {  # 资产总计
        'expression': "ROW('BS-027') + ROW('BS-052')",
        'description': '资产总计 = 流动资产合计 + 非流动资产合计',
    },
    'BS-082': {  # 流动负债合计
        'expression': "ROW('BS-055') + ROW('BS-056') + ROW('BS-057') + ROW('BS-058') + ROW('BS-059') + ROW('BS-060') + ROW('BS-061') + ROW('BS-062') + ROW('BS-063') + ROW('BS-064') + ROW('BS-065') + ROW('BS-066') + ROW('BS-067') + ROW('BS-068') + ROW('BS-069') + ROW('BS-073') + ROW('BS-075') + ROW('BS-077') + ROW('BS-078') + ROW('BS-079') + ROW('BS-080') + ROW('BS-081')",
        'description': '流动负债合计 = 短期借款 + … + 其他流动负债',
    },
    'BS-099': {  # 非流动负债合计
        'expression': "ROW('BS-084') + ROW('BS-085') + ROW('BS-086') + ROW('BS-089') + ROW('BS-090') + ROW('BS-091') + ROW('BS-092') + ROW('BS-093') + ROW('BS-094') + ROW('BS-095') + ROW('BS-096') + ROW('BS-097')",
        'description': '非流动负债合计 = 保险合同准备金 + 长期借款 + … + 其他非流动负债',
    },
    'BS-100': {  # 负债合计
        'expression': "ROW('BS-082') + ROW('BS-099')",
        'description': '负债合计 = 流动负债合计 + 非流动负债合计',
    },
    'BS-126': {  # 归属于母公司所有者权益合计
        'expression': "ROW('BS-102') + ROW('BS-110') + ROW('BS-113') - ROW('BS-114') + ROW('BS-115') + ROW('BS-117') + ROW('BS-118') + ROW('BS-124') + ROW('BS-125')",
        'description': '归属母公司权益 = 实收资本 + 其他权益工具 + 资本公积 - 库存股 + 其他综合收益 + 专项储备 + 盈余公积 + 一般风险准备 + 未分配利润',
    },
    'BS-128': {  # 所有者权益合计
        'expression': "ROW('BS-126') + ROW('BS-127')",
        'description': '所有者权益合计 = 归属母公司权益 + 少数股东权益',
    },
    'BS-129': {  # 负债和所有者权益总计
        'expression': "ROW('BS-100') + ROW('BS-128')",
        'description': '负债和所有者权益总计 = 负债合计 + 所有者权益合计',
    },
}

# ── 标题/标签行（无公式，跳过） ──
TITLE_ROWS = {'BS-001', 'BS-028', 'BS-054', 'BS-083', 'BS-101'}

# ── 子项行（数据来自父科目明细，展示用，取 TB 子科目） ──
# 已在 BS_ACCOUNT_MAP 中映射

def generate_presets():
    """生成 BS 全部行次的 auto_calc 预设。"""
    presets = []

    with open('backend/data/report_config_seed.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    bs = next(d for d in data if d['report_type'] == 'balance_sheet' and d['applicable_standard'] == 'soe_standalone')

    for row in bs['rows']:
        code = row['row_code']
        name = row['row_name']

        # 标题行跳过
        if code in TITLE_ROWS:
            continue

        # 合计行
        if code in TOTAL_FORMULAS:
            tf = TOTAL_FORMULAS[code]
            # 提取引用
            refs = []
            import re
            for m in re.finditer(r"ROW\('([^']+)'\)", tf['expression']):
                refs.append({"formula_ref": f"ROW('{m.group(1)}')"})
            presets.append({
                "page_key": "report:balance_sheet",
                "target_cell": code,
                "expression": tf['expression'],
                "formula_type": "auto_calc",
                "refs": refs,
                "source": "bs_preset_generator",
                "description": tf['description'],
            })
            continue

        # 明细行：从 TB 取数
        if code in BS_ACCOUNT_MAP:
            acct = BS_ACCOUNT_MAP[code]
            expression = f"TB('{acct}', '期末余额')"
            presets.append({
                "page_key": "report:balance_sheet",
                "target_cell": code,
                "expression": expression,
                "formula_type": "auto_calc",
                "refs": [{"formula_ref": f"TB('{acct}')"}],
                "source": "bs_preset_generator",
                "description": f"{name} — 取试算表科目 {acct} 期末余额",
            })
        # else: 无映射的行（可能是子项展示行），暂跳过

    return presets


def main():
    dry_run = '--dry-run' in sys.argv
    presets = generate_presets()

    print(f"[bs_preset_generator] 生成 {len(presets)} 条 BS 预设公式")
    print(f"  - auto_calc (合计行): {sum(1 for p in presets if p['target_cell'] in TOTAL_FORMULAS)}")
    print(f"  - auto_calc (明细行 TB取数): {sum(1 for p in presets if p['target_cell'] not in TOTAL_FORMULAS)}")

    if dry_run:
        print("\n[dry-run] 不写入文件，打印前 5 条：")
        for p in presets[:5]:
            print(json.dumps(p, ensure_ascii=False, indent=2))
        return

    # 写入 seed 文件
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

    print(f"[OK] 追加 {new_count} 条新预设到 {seed_path}")
    print(f"     总预设数: {len(seed['presets'])}")


if __name__ == '__main__':
    main()
