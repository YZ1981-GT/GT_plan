"""Fix fine rule files that use 'sheets' instead of 'sheet_rules'"""
import json
from pathlib import Path

files = [
    'f4_payable.json',
    'j1_employee_compensation.json', 
    'k1_other_receivable.json',
    'l1_short_term_loan.json',
    'n2_tax_payable.json',
]
rules_dir = Path(__file__).resolve().parent.parent / 'data' / 'wp_fine_rules'

for fname in files:
    fp = rules_dir / fname
    if not fp.exists():
        print(f"SKIP {fname}: not found")
        continue
    data = json.loads(fp.read_text(encoding='utf-8'))
    if 'sheets' in data and 'sheet_rules' not in data:
        data['sheet_rules'] = data.pop('sheets')
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        sr = data['sheet_rules']
        print(f"Fixed {fname}: sheets -> sheet_rules ({len(sr)} rules)")
    else:
        has_sr = 'sheet_rules' in data
        has_s = 'sheets' in data
        print(f"Skip {fname}: sheet_rules={has_sr}, sheets={has_s}")
