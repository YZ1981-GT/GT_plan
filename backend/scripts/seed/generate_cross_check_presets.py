"""生成报表↔附注 + 报表↔底稿 表间审核公式预设（logic_check）。

致同标准：报表每个主要科目的审定数 = 附注对应章节合计 = 底稿审定表审定数。
三方一致是审计最基本的勾稽要求。

Usage:
    python backend/scripts/seed/generate_cross_check_presets.py [--dry-run]
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# ── 报表 ↔ 附注 勾稽映射 ──
# (BS/IS 行次, 附注章节 note_section, 科目中文名)
REPORT_NOTE_CHECKS = [
    # 资产类
    ('BS-002', '五、1', '货币资金'),
    ('BS-005', '五、2', '交易性金融资产'),
    ('BS-007', '五、3', '应收票据'),
    ('BS-008', '五、4', '应收账款'),
    ('BS-009', '五、5', '应收款项融资'),
    ('BS-010', '五、6', '预付款项'),
    ('BS-015', '五、7', '其他应收款'),
    ('BS-018', '五、8', '存货'),
    ('BS-021', '五、9', '合同资产'),
    ('BS-025', '五、10', '一年内到期的非流动资产'),
    ('BS-026', '五、11', '其他流动资产'),
    ('BS-032', '五、12', '长期应收款'),
    ('BS-033', '五、13', '长期股权投资'),
    ('BS-034', '五、14', '其他权益工具投资'),
    ('BS-035', '五、15', '其他非流动金融资产'),
    ('BS-036', '五、16', '投资性房地产'),
    ('BS-037', '五、17', '固定资产'),
    ('BS-041', '五、18', '在建工程'),
    ('BS-044', '五、19', '使用权资产'),
    ('BS-045', '五、20', '无形资产'),
    ('BS-047', '五、21', '商誉'),
    ('BS-048', '五、22', '长期待摊费用'),
    ('BS-049', '五、23', '递延所得税资产'),
    ('BS-050', '五、24', '其他非流动资产'),
    # 负债类
    ('BS-055', '五、25', '短期借款'),
    ('BS-060', '五、26', '应付票据'),
    ('BS-061', '五、27', '应付账款'),
    ('BS-063', '五、28', '合同负债'),
    ('BS-069', '五、29', '应付职工薪酬'),
    ('BS-073', '五、30', '应交税费'),
    ('BS-075', '五、31', '其他应付款'),
    ('BS-080', '五、32', '一年内到期的非流动负债'),
    ('BS-081', '五、33', '其他流动负债'),
    ('BS-085', '五、34', '长期借款'),
    ('BS-086', '五、35', '应付债券'),
    ('BS-091', '五、36', '租赁负债'),
    ('BS-092', '五、37', '长期应付款'),
    ('BS-094', '五、38', '预计负债'),
    ('BS-095', '五、39', '递延收益'),
    ('BS-096', '五、40', '递延所得税负债'),
    ('BS-097', '五、41', '其他非流动负债'),
    # 权益类
    ('BS-102', '五、42', '实收资本'),
    ('BS-113', '五、43', '资本公积'),
    ('BS-115', '五、44', '其他综合收益'),
    ('BS-118', '五、45', '盈余公积'),
    ('BS-125', '五、46', '未分配利润'),
    # 损益类 (IS)
    ('IS-001', '五、47', '营业收入'),
    ('IS-002', '五、48', '营业成本'),
    ('IS-003', '五、49', '税金及附加'),
    ('IS-004', '五、50', '销售费用'),
    ('IS-005', '五、51', '管理费用'),
    ('IS-006', '五、52', '研发费用'),
    ('IS-007', '五、53', '财务费用'),
    ('IS-010', '五、54', '其他收益'),
    ('IS-011', '五、55', '投资收益'),
    ('IS-016', '五、56', '信用减值损失'),
    ('IS-017', '五、57', '资产减值损失'),
    ('IS-018', '五、58', '资产处置收益'),
    ('IS-020', '五、59', '营业外收入'),
    ('IS-021', '五、60', '营业外支出'),
    ('IS-023', '五、61', '所得税费用'),
]

# ── 报表 ↔ 底稿 勾稽映射 ──
# (BS/IS 行次, 底稿 wp_code, sheet_code, 科目中文名)
REPORT_WP_CHECKS = [
    ('BS-002', 'E1', 'E1-1', '货币资金'),
    ('BS-007', 'D1', 'D1-1', '应收票据'),
    ('BS-008', 'D2', 'D2-1', '应收账款'),
    ('BS-009', 'D5', 'D5-1', '应收款项融资'),
    ('BS-010', 'D3', 'D3-1', '预付款项'),
    ('BS-015', 'D6', 'D6-1', '其他应收款'),
    ('BS-018', 'F2', 'F2-1', '存货'),
    ('BS-021', 'D7', 'D7-1', '合同资产'),
    ('BS-033', 'J1', 'J1-1', '长期股权投资'),
    ('BS-036', 'I4', 'I4-1', '投资性房地产'),
    ('BS-037', 'H1', 'H1-1', '固定资产'),
    ('BS-041', 'H2', 'H2-1', '在建工程'),
    ('BS-045', 'I1', 'I1-1', '无形资产'),
    ('BS-047', 'I3', 'I3-1', '商誉'),
    ('BS-055', 'K1', 'K1-1', '短期借款'),
    ('BS-060', 'F1', 'F1-1', '应付票据/应付账款'),
    ('BS-069', 'L1', 'L1-1', '应付职工薪酬'),
    ('BS-085', 'K2', 'K2-1', '长期借款'),
    ('BS-102', 'M1', 'M1-1', '实收资本'),
    ('IS-001', 'D4', 'D4-1', '营业收入'),
    ('IS-002', 'K8', 'K8-1', '营业成本'),
    ('IS-004', 'K9', 'K9-1', '销售费用'),
    ('IS-005', 'K10', 'K10-1', '管理费用'),
    ('IS-007', 'K11', 'K11-1', '财务费用'),
    ('IS-023', 'N5', 'N5-1', '所得税费用'),
]


def generate_presets():
    presets = []
    seq = 10  # 从 10 开始编号避免与已有 1-7 冲突

    # 报表 ↔ 附注
    for row_code, note_section, name in REPORT_NOTE_CHECKS:
        presets.append({
            "page_key": "report:cross_check",
            "target_cell": f"report-cross-check-rn-{seq}",
            "expression": f"ABS(ROUND(ROW('{row_code}') - NOTE('{note_section}', '合计'), 2)) <= 1",
            "formula_type": "logic_check",
            "refs": [
                {"formula_ref": f"ROW('{row_code}')"},
                {"formula_ref": f"NOTE('{note_section}')"},
            ],
            "source": "cross_check_generator",
            "source_domain": "report",
            "target_domain": "note",
            "description": f"{name}：报表 {row_code} = 附注{note_section}合计",
        })
        seq += 1

    # 报表 ↔ 底稿
    for row_code, wp_code, sheet_code, name in REPORT_WP_CHECKS:
        presets.append({
            "page_key": "report:cross_check",
            "target_cell": f"report-cross-check-rw-{seq}",
            "expression": f"ABS(ROUND(ROW('{row_code}') - WP('{wp_code}', '{sheet_code}', '审定数'), 2)) <= 1",
            "formula_type": "logic_check",
            "refs": [
                {"formula_ref": f"ROW('{row_code}')"},
                {"formula_ref": f"WP('{wp_code}', '{sheet_code}', '审定数')"},
            ],
            "source": "cross_check_generator",
            "source_domain": "report",
            "target_domain": "wp",
            "description": f"{name}：报表 {row_code} = {wp_code} {sheet_code} 审定数",
        })
        seq += 1

    return presets


def main():
    dry_run = '--dry-run' in sys.argv
    presets = generate_presets()

    rn_count = sum(1 for p in presets if p['target_domain'] == 'note')
    rw_count = sum(1 for p in presets if p['target_domain'] == 'wp')
    print(f"[cross_check] 生成 {len(presets)} 条表间审核预设")
    print(f"  - 报表 ↔ 附注: {rn_count} 条")
    print(f"  - 报表 ↔ 底稿: {rw_count} 条")

    if dry_run:
        print("\n[dry-run] 前 3 条报表↔附注 + 前 3 条报表↔底稿：")
        for p in [x for x in presets if x['target_domain'] == 'note'][:3]:
            print(json.dumps(p, ensure_ascii=False, indent=2))
        for p in [x for x in presets if x['target_domain'] == 'wp'][:3]:
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
