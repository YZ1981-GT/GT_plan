"""生成全部报表（IS/CFS/EQ/CFS附表/资产减值准备表）的公式预设。

BS 已由 generate_bs_formula_presets.py 生成。本脚本补齐其余报表。
逻辑同 BS：明细行 TB 取数 / 合计行 ROW 求和 / 标题行跳过。

Usage:
    python backend/scripts/seed/generate_all_report_formula_presets.py [--dry-run]
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# ── 利润表(IS)科目映射 ──
IS_ACCOUNT_MAP: dict[str, str] = {
    'IS-001': '6001',    # 营业收入
    'IS-002': '6401',    # 营业成本
    'IS-003': '6403',    # 税金及附加
    'IS-004': '6601',    # 销售费用
    'IS-005': '6602',    # 管理费用
    'IS-006': '6603',    # 研发费用
    'IS-007': '6604',    # 财务费用
    'IS-008': '6604A',   # 其中：利息费用
    'IS-009': '6604B',   # 利息收入
    'IS-010': '6051',    # 其他收益
    'IS-011': '6111',    # 投资收益
    'IS-012': '6111A',   # 其中：对联营/合营企业投资收益
    'IS-013': '6112',    # 以摊余成本计量的金融资产终止确认收益
    'IS-014': '6021',    # 净敞口套期收益
    'IS-015': '6031',    # 公允价值变动收益
    'IS-016': '6711',    # 信用减值损失
    'IS-017': '6701',    # 资产减值损失
    'IS-018': '6115',    # 资产处置收益
    'IS-020': '6301',    # 营业外收入
    'IS-021': '6302',    # 营业外支出
    'IS-023': '6801',    # 所得税费用
    'IS-025': '6901',    # 其他综合收益的税后净额
    'IS-030': '6998',    # 归属于母公司所有者的综合收益总额
    'IS-031': '6999',    # 归属于少数股东的综合收益总额
    'IS-032': '6801A',   # 基本每股收益
    'IS-033': '6801B',   # 稀释每股收益
}

# IS 合计行
IS_TOTAL_FORMULAS: dict[str, dict] = {
    'IS-019': {  # 营业利润
        'expression': "ROW('IS-001') - ROW('IS-002') - ROW('IS-003') - ROW('IS-004') - ROW('IS-005') - ROW('IS-006') - ROW('IS-007') + ROW('IS-010') + ROW('IS-011') + ROW('IS-014') + ROW('IS-015') - ROW('IS-016') - ROW('IS-017') + ROW('IS-018')",
        'description': '营业利润 = 营业收入 - 营业成本 - 三项费用 + 其他收益 + 投资收益 + 公允变动 - 减值损失 + 资产处置',
    },
    'IS-022': {  # 利润总额
        'expression': "ROW('IS-019') + ROW('IS-020') - ROW('IS-021')",
        'description': '利润总额 = 营业利润 + 营业外收入 - 营业外支出',
    },
    'IS-024': {  # 净利润
        'expression': "ROW('IS-022') - ROW('IS-023')",
        'description': '净利润 = 利润总额 - 所得税费用',
    },
    'IS-026': {  # 综合收益总额
        'expression': "ROW('IS-024') + ROW('IS-025')",
        'description': '综合收益总额 = 净利润 + 其他综合收益税后净额',
    },
}

IS_TITLE_ROWS = set()  # IS 无标题行

# ── 现金流量表(CFS)科目映射 ──
CFS_ACCOUNT_MAP: dict[str, str] = {
    'CFS-001': '6001C',   # 销售商品、提供劳务收到的现金
    'CFS-002': '6002C',   # 收到的税费返还
    'CFS-003': '6003C',   # 收到其他与经营活动有关的现金
    'CFS-005': '6005C',   # 购买商品、接受劳务支付的现金
    'CFS-006': '6006C',   # 支付给职工以及为职工支付的现金
    'CFS-007': '6007C',   # 支付的各项税费
    'CFS-008': '6008C',   # 支付其他与经营活动有关的现金
    'CFS-010': '6010C',   # 收回投资收到的现金
    'CFS-011': '6011C',   # 取得投资收益收到的现金
    'CFS-012': '6012C',   # 处置固定资产、无形资产和其他长期资产收回的现金净额
    'CFS-013': '6013C',   # 处置子公司及其他营业单位收到的现金净额
    'CFS-014': '6014C',   # 收到其他与投资活动有关的现金
    'CFS-016': '6016C',   # 购建固定资产、无形资产和其他长期资产支付的现金
    'CFS-017': '6017C',   # 投资支付的现金
    'CFS-018': '6018C',   # 取得子公司及其他营业单位支付的现金净额
    'CFS-019': '6019C',   # 支付其他与投资活动有关的现金
    'CFS-021': '6021C',   # 吸收投资收到的现金
    'CFS-022': '6022C',   # 其中：子公司吸收少数股东投资收到的现金
    'CFS-023': '6023C',   # 取得借款收到的现金
    'CFS-024': '6024C',   # 收到其他与筹资活动有关的现金
    'CFS-026': '6026C',   # 偿还债务支付的现金
    'CFS-027': '6027C',   # 分配股利、利润或偿付利息支付的现金
    'CFS-028': '6028C',   # 其中：子公司支付给少数股东的股利、利润
    'CFS-029': '6029C',   # 支付其他与筹资活动有关的现金
    'CFS-031': '6031C',   # 汇率变动对现金及现金等价物的影响
}

CFS_TOTAL_FORMULAS: dict[str, dict] = {
    'CFS-004': {  # 经营活动现金流入小计
        'expression': "ROW('CFS-001') + ROW('CFS-002') + ROW('CFS-003')",
        'description': '经营活动现金流入小计',
    },
    'CFS-009': {  # 经营活动现金流出小计
        'expression': "ROW('CFS-005') + ROW('CFS-006') + ROW('CFS-007') + ROW('CFS-008')",
        'description': '经营活动现金流出小计',
    },
    'CFS-004A': {  # 经营活动产生的现金流量净额（如果有的话用别的 code）
        'expression': "ROW('CFS-004') - ROW('CFS-009')",
        'description': '经营活动产生的现金流量净额 = 流入小计 - 流出小计',
    },
    'CFS-015': {  # 投资活动现金流入小计
        'expression': "ROW('CFS-010') + ROW('CFS-011') + ROW('CFS-012') + ROW('CFS-013') + ROW('CFS-014')",
        'description': '投资活动现金流入小计',
    },
    'CFS-020': {  # 投资活动现金流出小计
        'expression': "ROW('CFS-016') + ROW('CFS-017') + ROW('CFS-018') + ROW('CFS-019')",
        'description': '投资活动现金流出小计',
    },
    'CFS-025': {  # 筹资活动现金流入小计
        'expression': "ROW('CFS-021') + ROW('CFS-023') + ROW('CFS-024')",
        'description': '筹资活动现金流入小计',
    },
    'CFS-030': {  # 筹资活动现金流出小计
        'expression': "ROW('CFS-026') + ROW('CFS-027') + ROW('CFS-029')",
        'description': '筹资活动现金流出小计',
    },
}

CFS_TITLE_ROWS = set()


def load_report_rows(report_type: str) -> list[dict]:
    """Load rows for a given report type from report_config_seed.json (soe_standalone)."""
    with open('backend/data/report_config_seed.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    for d in data:
        if d['report_type'] == report_type and d['applicable_standard'] == 'soe_standalone':
            return d['rows']
    return []


def generate_presets_for_report(
    report_type: str,
    page_key: str,
    account_map: dict[str, str],
    total_formulas: dict[str, dict],
    title_rows: set[str],
) -> list[dict]:
    """Generate auto_calc presets for a single report type."""
    rows = load_report_rows(report_type)
    if not rows:
        print(f"  [WARN] No rows found for {report_type}/soe_standalone")
        return []

    presets = []
    for row in rows:
        code = row['row_code']
        name = row['row_name']

        # 标题行跳过
        if code in title_rows:
            continue

        # 合计行
        if code in total_formulas:
            tf = total_formulas[code]
            refs = [{"formula_ref": f"ROW('{m.group(1)}')"} for m in re.finditer(r"ROW\('([^']+)'\)", tf['expression'])]
            presets.append({
                "page_key": page_key,
                "target_cell": code,
                "expression": tf['expression'],
                "formula_type": "auto_calc",
                "refs": refs,
                "source": "report_preset_generator",
                "description": tf['description'],
            })
            continue

        # 明细行：从 TB 取数（损益类取发生额）
        if code in account_map:
            acct = account_map[code]
            # 损益类科目取发生额，资产/负债类取期末余额
            if report_type == 'income_statement':
                field = '发生额'
            elif report_type == 'cash_flow_statement':
                field = '发生额'
            else:
                field = '期末余额'
            expression = f"TB('{acct}', '{field}')"
            presets.append({
                "page_key": page_key,
                "target_cell": code,
                "expression": expression,
                "formula_type": "auto_calc",
                "refs": [{"formula_ref": f"TB('{acct}')"}],
                "source": "report_preset_generator",
                "description": f"{name} — 取试算表科目 {acct} {field}",
            })

    return presets


def main():
    dry_run = '--dry-run' in sys.argv

    all_presets = []

    # 利润表
    is_presets = generate_presets_for_report(
        'income_statement', 'report:income_statement',
        IS_ACCOUNT_MAP, IS_TOTAL_FORMULAS, IS_TITLE_ROWS,
    )
    all_presets.extend(is_presets)
    print(f"[IS] 生成 {len(is_presets)} 条利润表预设")

    # 现金流量表
    cfs_presets = generate_presets_for_report(
        'cash_flow_statement', 'report:cash_flow_statement',
        CFS_ACCOUNT_MAP, CFS_TOTAL_FORMULAS, CFS_TITLE_ROWS,
    )
    all_presets.extend(cfs_presets)
    print(f"[CFS] 生成 {len(cfs_presets)} 条现金流量表预设")

    # 权益变动表、现金流附表、减值准备表 — 这些结构较特殊，先看有没有行次
    for rt in ['equity_statement', 'cash_flow_supplement', 'impairment_provision']:
        rows = load_report_rows(rt)
        if rows:
            # 通用处理：只有明细行无科目映射也要至少生成 page_key 占位
            print(f"[{rt}] 有 {len(rows)} 行（结构特殊，暂不自动生成 TB 映射，需手工补齐）")
        else:
            print(f"[{rt}] 未在 soe_standalone 找到行次")

    print(f"\n[TOTAL] 本次生成 {len(all_presets)} 条预设（IS + CFS）")

    if dry_run:
        print("\n[dry-run] 不写入，打印前 3 条 IS + 前 3 条 CFS：")
        for p in is_presets[:3]:
            print(json.dumps(p, ensure_ascii=False, indent=2))
        for p in cfs_presets[:3]:
            print(json.dumps(p, ensure_ascii=False, indent=2))
        return

    # 写入 seed
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

    print(f"[OK] 追加 {new_count} 条新预设到 {seed_path}")
    print(f"     总预设数: {len(seed['presets'])}")


if __name__ == '__main__':
    main()
