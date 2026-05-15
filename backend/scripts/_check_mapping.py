"""Check wp_account_mapping data to see if account_codes is populated"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

s = requests.Session()
r = s.post('http://localhost:9980/api/auth/login', json={'username':'admin','password':'admin123'})
body = r.json()
token = body.get('data', body).get('access_token', '')
headers = {'Authorization': f'Bearer {token}'}

pid = '005a6f2d-cecd-4e30-bcbd-9fb01236c194'

# Check mappings (correct path)
r1 = s.get(f'http://localhost:9980/api/projects/{pid}/wp-mapping/all', headers=headers)
print(f"Mappings: status={r1.status_code}")
if r1.status_code == 200:
    data = r1.json()
    items = data.get('data', data) if isinstance(data, dict) else data
    if isinstance(items, dict) and 'items' in items:
        items = items['items']
    if not isinstance(items, list):
        items = [items] if items else []
    print(f"  Total: {len(items)}")
    # Show account_codes for first 10
    has_codes = 0
    empty_codes = 0
    for m in items:
        codes = m.get('account_codes', [])
        if codes:
            has_codes += 1
        else:
            empty_codes += 1
    print(f"  With account_codes: {has_codes}")
    print(f"  Empty account_codes: {empty_codes}")
    # Show some examples
    for m in items[:5]:
        print(f"    {m.get('wp_code'):8s} codes={m.get('account_codes')} cycle={m.get('cycle')}")
else:
    print(f"  Error: {r1.text[:200]}")

# Check balance with year
r2 = s.get(f'http://localhost:9980/api/projects/{pid}/ledger/balance', headers=headers, params={'year': 2025})
print(f"\nBalance (year=2025): status={r2.status_code}")
if r2.status_code == 200:
    data2 = r2.json()
    items2 = data2.get('data', data2) if isinstance(data2, dict) else data2
    if isinstance(items2, dict) and 'items' in items2:
        items2 = items2['items']
    elif isinstance(items2, dict) and 'rows' in items2:
        items2 = items2['rows']
    if not isinstance(items2, list):
        items2 = []
    print(f"  Total rows: {len(items2)}")
    codes_set = set()
    for row in items2:
        code = row.get('account_code', row.get('standard_account_code', ''))
        if code:
            codes_set.add(code)
    print(f"  Unique codes: {len(codes_set)}")
    for row in items2[:5]:
        code = row.get('account_code', row.get('standard_account_code', '?'))
        print(f"    {code} {row.get('account_name', '?')}")
else:
    print(f"  Error: {r2.text[:200]}")
