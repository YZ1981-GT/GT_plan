# -*- coding: utf-8 -*-
import urllib.request, json

login_data = json.dumps({"username": "admin", "password": "admin123"}).encode()
req = urllib.request.Request("http://localhost:9980/api/auth/login", data=login_data, headers={"Content-Type": "application/json"})
r = urllib.request.urlopen(req)
d = json.loads(r.read())
token = d.get("data", d).get("token") or d.get("data", d).get("access_token")
print(f"token: {token[:20]}...")

pid = "6687b8ce-7a83-4816-bd4a-c2d173d4b683"

# Test wizard state
try:
    req = urllib.request.Request(
        f"http://localhost:9980/api/projects/{pid}/wizard",
        headers={"Authorization": f"Bearer {token}"}
    )
    r = urllib.request.urlopen(req)
    print(f"wizard OK: {r.read().decode()[:200]}")
except urllib.request.HTTPError as e:
    print(f"wizard ERROR {e.code}: {e.read().decode()[:200]}")

# Test standard chart
try:
    req = urllib.request.Request(
        f"http://localhost:9980/api/account-chart/standard",
        headers={"Authorization": f"Bearer {token}"}
    )
    r = urllib.request.urlopen(req)
    print(f"standard chart OK: {len(r.read())} bytes")
except urllib.request.HTTPError as e:
    print(f"standard chart ERROR {e.code}: {e.read().decode()[:200]}")

# Test client chart
try:
    req = urllib.request.Request(
        f"http://localhost:9980/api/account-chart/client/{pid}",
        headers={"Authorization": f"Bearer {token}"}
    )
    r = urllib.request.urlopen(req)
    print(f"client chart OK: {len(r.read())} bytes")
except urllib.request.HTTPError as e:
    print(f"client chart ERROR {e.code}: {e.read().decode()[:200]}")
