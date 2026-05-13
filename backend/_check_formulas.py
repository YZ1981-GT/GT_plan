import json

with open('data/report_config_seed.json', encoding='utf-8') as f:
    data = json.load(f)

first = data[0]
print(f"Config: {first['report_type']} / {first['applicable_standard']}")
has_formula = sum(1 for r in first['rows'] if r.get('formula'))
print(f"Rows with formula: {has_formula} / {len(first['rows'])}")

# Show first 5 rows
for r in first['rows'][:5]:
    print(f"  {r['row_code']}: formula={r.get('formula')}, cat={r.get('formula_category')}, src={r.get('formula_source')}")

# Check report_excel_formulas.json
print("\n--- report_excel_formulas.json ---")
with open('data/report_excel_formulas.json', encoding='utf-8') as f:
    formulas = json.load(f)
if isinstance(formulas, list):
    print(f"Total: {len(formulas)}")
    for f in formulas[:3]:
        print(f"  {f}")
elif isinstance(formulas, dict):
    print(f"Keys: {list(formulas.keys())[:5]}")
    for k in list(formulas.keys())[:2]:
        v = formulas[k]
        if isinstance(v, list):
            print(f"  {k}: {len(v)} items, sample={v[0] if v else '?'}")
        elif isinstance(v, dict):
            print(f"  {k}: {list(v.keys())[:5]}")
