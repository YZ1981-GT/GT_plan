# -*- coding: utf-8 -*-
import urllib.request, json

# Login
login_data = json.dumps({"username": "admin", "password": "admin123"}).encode()
req = urllib.request.Request("http://localhost:9980/api/auth/login", data=login_data, headers={"Content-Type": "application/json"})
r = urllib.request.urlopen(req)
d = json.loads(r.read())
token = d.get("data", d).get("token") or d.get("data", d).get("access_token")
print(f"token: {token[:20]}...")

pid = "6687b8ce-7a83-4816-bd4a-c2d173d4b683"
base = f"http://localhost:9980/api/projects/{pid}/ledger"

def get(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    r = urllib.request.urlopen(req)
    d = json.loads(r.read())
    return d.get("data", d)

# 1. opening-balance
print("\n1. opening-balance/1002:")
print(get(f"{base}/opening-balance/1002?year=2025"))

# 2. stats
print("\n2. stats:")
print(get(f"{base}/stats?year=2025"))

# 3. entries with total
print("\n3. entries/1002 (limit=5):")
result = get(f"{base}/entries/1002?year=2025&limit=5")
print(f"  total={result.get('total')}, items={len(result.get('items', []))}, has_more={result.get('has_more')}")
if result.get("items"):
    print(f"  first: {result['items'][0].get('voucher_date')} {result['items'][0].get('voucher_no')}")
