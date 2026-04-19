# -*- coding: utf-8 -*-
import urllib.request, json

# Login
login_data = json.dumps({"username": "admin", "password": "admin123"}).encode()
req = urllib.request.Request("http://localhost:9980/api/auth/login", data=login_data, headers={"Content-Type": "application/json"})
r = urllib.request.urlopen(req)
d = json.loads(r.read())
token = d.get("data", d).get("token") or d.get("data", d).get("access_token")

def get(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    r = urllib.request.urlopen(req)
    d = json.loads(r.read())
    return d.get("data", d)

# Capacity
print("=== 容量统计 ===")
result = get("http://localhost:9980/api/data-lifecycle/capacity")
print(f"总计: {result.get('total_rows', 0):,} 行, {result.get('total_size_mb', 0):.0f} MB")
for tbl, info in result.get("tables", {}).items():
    print(f"  {tbl}: {info['rows']:,} 行, {info['size_mb']} MB")
for p in result.get("projects", []):
    print(f"  项目 {p.get('client_name') or p.get('name')}: {p['total_rows']:,} 行")

# Import queue
print("\n=== 导入队列 ===")
result = get("http://localhost:9980/api/data-lifecycle/import-queue")
print(f"活跃任务: {len(result.get('active', []))}")
