# -*- coding: utf-8 -*-
"""逐一测试辅助余额表所有 API 端点的前后端联动"""
import urllib.request, json

# Login
login_data = json.dumps({"username": "admin", "password": "admin123"}).encode()
req = urllib.request.Request("http://localhost:9980/api/auth/login", data=login_data, headers={"Content-Type": "application/json"})
r = urllib.request.urlopen(req)
d = json.loads(r.read())
token = d.get("data", d).get("token") or d.get("data", d).get("access_token")

pid = "6687b8ce-7a83-4816-bd4a-c2d173d4b683"
base = f"http://localhost:9980/api/projects/{pid}/ledger"

def get(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    r = urllib.request.urlopen(req)
    d = json.loads(r.read())
    return d.get("data", d)

print("=" * 60)
print("辅助余额表 API 联动测试")
print("=" * 60)

# 1. aux-balance-summary（树形视图+维度标签用）
print("\n1. aux-balance-summary")
result = get(f"{base}/aux-balance-summary?year=2025")
print(f"   dim_types: {len(result.get('dim_types', []))} 种")
for dt in result.get("dim_types", [])[:3]:
    print(f"     {dt['type']}: {dt['total_records']} 条, {dt['group_count']} 组")
print(f"   rows: {result.get('total', 0)} 条汇总")

# 2. aux-balance-summary 按维度筛选
print("\n2. aux-balance-summary?dim_type=客户")
result = get(f"{base}/aux-balance-summary?year=2025&dim_type=%E5%AE%A2%E6%88%B7")
print(f"   rows: {result.get('total', 0)} 条")
if result.get("rows"):
    r = result["rows"][0]
    print(f"   first: {r.get('account_code')} {r.get('aux_code')} {r.get('aux_name')} closing={r.get('closing_balance')}")

# 3. aux-balance-paged（扁平视图用）
print("\n3. aux-balance-paged?dim_type=客户&page=1")
result = get(f"{base}/aux-balance-paged?year=2025&dim_type=%E5%AE%A2%E6%88%B7&page=1&page_size=5")
print(f"   total: {result.get('total', 0)}, page rows: {len(result.get('rows', []))}")
if result.get("rows"):
    r = result["rows"][0]
    print(f"   first: {r.get('account_code')} {r.get('aux_code')} {r.get('aux_name')}")

# 4. aux-balance-paged 搜索
print("\n4. aux-balance-paged?search=和平药房")
result = get(f"{base}/aux-balance-paged?year=2025&search=%E5%92%8C%E5%B9%B3%E8%8D%AF%E6%88%BF&page=1&page_size=5")
print(f"   total: {result.get('total', 0)}, page rows: {len(result.get('rows', []))}")

# 5. aux-balance-detail（展开明细用）
print("\n5. aux-balance-detail?account_code=1122.01&dim_type=客户&aux_code=00000015")
result = get(f"{base}/aux-balance-detail?year=2025&account_code=1122.01&dim_type=%E5%AE%A2%E6%88%B7&aux_code=00000015")
print(f"   detail rows: {len(result) if isinstance(result, list) else 0}")
if isinstance(result, list) and result:
    r = result[0]
    print(f"   first: {r.get('aux_name')} raw={str(r.get('aux_dimensions_raw', ''))[:60]}")

# 6. export-aux-balance（导出用）
print("\n6. export-aux-balance (检查端点存在)")
try:
    req = urllib.request.Request(
        f"{base}/export-aux-balance?year=2025&dim_type=%E5%AE%A2%E6%88%B7",
        headers={"Authorization": f"Bearer {token}"}
    )
    r = urllib.request.urlopen(req)
    print(f"   status: {r.status}, content-type: {r.headers.get('Content-Type', '')[:40]}")
    print(f"   size: {len(r.read())} bytes")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n✅ 全部测试完成")
