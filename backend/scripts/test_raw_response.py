# -*- coding: utf-8 -*-
import urllib.request, json

login_data = json.dumps({"username": "admin", "password": "admin123"}).encode()
req = urllib.request.Request("http://localhost:9980/api/auth/login", data=login_data, headers={"Content-Type": "application/json"})
r = urllib.request.urlopen(req)
d = json.loads(r.read())
token = d.get("data", d).get("token") or d.get("data", d).get("access_token")
print(f"token: {token[:20]}...")

pid = "6687b8ce-7a83-4816-bd4a-c2d173d4b683"

# Test aux-balance-paged raw response
req = urllib.request.Request(
    f"http://localhost:9980/api/projects/{pid}/ledger/aux-balance-paged?year=2025&page=1&page_size=2",
    headers={"Authorization": f"Bearer {token}"}
)
r = urllib.request.urlopen(req)
raw = r.read().decode()
print(f"\naux-balance-paged RAW ({len(raw)} bytes):")
print(raw[:300])

# Test aux-balance-summary raw response
req = urllib.request.Request(
    f"http://localhost:9980/api/projects/{pid}/ledger/aux-balance-summary?year=2025",
    headers={"Authorization": f"Bearer {token}"}
)
r = urllib.request.urlopen(req)
raw = r.read().decode()
print(f"\naux-balance-summary RAW ({len(raw)} bytes):")
print(raw[:300])
