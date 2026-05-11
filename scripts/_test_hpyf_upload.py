"""一次性：测试和平药房 432MB 上传"""
import requests, time, sys
from pathlib import Path

s = requests.Session()
r = s.post('http://127.0.0.1:9980/api/auth/login', json={'username':'admin','password':'admin123'})
s.headers['Authorization'] = 'Bearer ' + r.json()['data']['access_token']

f = Path(r'D:\GT_plan\数据\和平药房')
all_files = sorted(list(f.glob('*.xlsx')) + list(f.glob('*.csv')))
total_mb = sum(p.stat().st_size for p in all_files) / 1024 / 1024
print(f'Uploading {len(all_files)} files ({total_mb:.1f} MB)...')

payload = []
for p in all_files:
    mime = 'text/csv' if p.suffix == '.csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    payload.append(('files', (p.name, p.open('rb'), mime)))

t0 = time.time()
try:
    r2 = s.post('http://127.0.0.1:9980/api/projects/f4b778ad-23b3-49ab-b3c8-ee62a5f82226/ledger-import/detect',
                files=payload, timeout=600)
    elapsed = time.time() - t0
    print(f'status={r2.status_code} elapsed={elapsed:.1f}s')
    if r2.status_code == 200:
        d = r2.json()['data']
        print(f'year={d.get("detected_year")} files={len(d.get("files",[]))}')
        for fd in d.get('files', []):
            for sh in fd.get('sheets', []):
                print(f'  {fd["file_name"][:40]} / {sh["sheet_name"]}: '
                      f'type={sh["table_type"]} rows~{sh["row_count_estimate"]}')
    else:
        print(r2.text[:500])
except Exception as e:
    print(f'ERROR: {e}')
finally:
    for _, (_, fh, _) in payload:
        fh.close()
