# -*- coding: utf-8 -*-
import urllib.request, json
from pathlib import Path

login_data = json.dumps({"username": "admin", "password": "admin123"}).encode()
req = urllib.request.Request("http://localhost:9980/api/auth/login", data=login_data, headers={"Content-Type": "application/json"})
r = urllib.request.urlopen(req)
d = json.loads(r.read())
token = d.get("data", d).get("token") or d.get("data", d).get("access_token")

pid = "6687b8ce-7a83-4816-bd4a-c2d173d4b683"
base = Path(__file__).resolve().parent.parent.parent / "数据"

# Upload balance file for preview
import http.client
import mimetypes

filepath = base / "科目余额表-重庆和平药房连锁有限责任公司2025.xlsx"
with open(filepath, "rb") as f:
    file_data = f.read()

boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="{filepath.name}"\r\n'
    f"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

req = urllib.request.Request(
    f"http://localhost:9980/api/projects/{pid}/account-chart/preview",
    data=body,
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    },
)
try:
    r = urllib.request.urlopen(req, timeout=60)
    raw = r.read().decode()
    result = json.loads(raw)
    data = result.get("data", result)
    sheets = data.get("sheets", [])
    print(f"sheets: {len(sheets)}")
    for s in sheets:
        print(f"  {s['sheet_name']}: {s.get('header_count', '?')} header rows, {len(s.get('rows', []))} data rows")
        print(f"  headers: {s['headers'][:5]}")
        print(f"  mapping: {dict(list(s.get('column_mapping', {}).items())[:5])}")
        if s.get("rows"):
            print(f"  first row: {dict(list(s['rows'][0].items())[:3])}")
except urllib.request.HTTPError as e:
    print(f"ERROR {e.code}: {e.read().decode()[:200]}")
except Exception as e:
    print(f"ERROR: {e}")
