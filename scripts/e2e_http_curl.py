"""E2E HTTP 链路验证（用 requests，避开 httpx 502 问题）。用完即删。"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

BASE = "http://127.0.0.1:9980"
PROJECT_ID = "f4b778ad-23b3-49ab-b3c8-ee62a5f82226"
YG36_FILE = ROOT / "数据/YG36-重庆医药集团四川物流有限公司2025.xlsx"


def main():
    s = requests.Session()

    # Step 1: Login
    print("\n=== Step 1: 登录 ===")
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "admin", "password": "admin123"}, timeout=30)
    token = r.json()["data"]["access_token"]
    s.headers["Authorization"] = f"Bearer {token}"
    print(f"  token OK")

    # Step 2: detect (上传 + 识别)
    print(f"\n=== Step 2: /detect 上传 {YG36_FILE.name} ===")
    t0 = time.time()
    with YG36_FILE.open("rb") as f:
        r = s.post(
            f"{BASE}/api/projects/{PROJECT_ID}/ledger-import/detect",
            files={"files": (YG36_FILE.name, f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=300,
        )
    print(f"  status={r.status_code} 耗时 {time.time()-t0:.1f}s")
    if r.status_code != 200:
        print(f"  body: {r.text[:500]}")
        return 1
    det = r.json()["data"]
    token_ul = det["upload_token"]
    print(f"  upload_token: {token_ul}")
    year = det["detected_year"]
    print(f"  detected_year: {year}")
    for fd in det["files"]:
        for sh in fd["sheets"]:
            print(f"  {fd['file_name']} / {sh['sheet_name']}: "
                  f"type={sh['table_type']} conf={sh['table_type_confidence']}")

    # Step 3: /submit 提交
    print(f"\n=== Step 3: /submit ===")
    confirmed_mappings = []
    for fd in det["files"]:
        for sh in fd["sheets"]:
            if sh["table_type"] == "unknown":
                continue
            mappings = {cm["column_header"]: cm["standard_field"]
                        for cm in sh["column_mappings"]
                        if cm["standard_field"] and cm["confidence"] >= 50}
            confirmed_mappings.append({
                "file_name": fd["file_name"],
                "sheet_name": sh["sheet_name"],
                "table_type": sh["table_type"],
                "mappings": mappings,
            })

    r = s.post(
        f"{BASE}/api/projects/{PROJECT_ID}/ledger-import/submit",
        json={
            "upload_token": token_ul,
            "year": year,
            "confirmed_mappings": confirmed_mappings,
            "force_activate": False,
        },
        timeout=60,
    )
    print(f"  status={r.status_code}")
    if r.status_code != 200:
        print(f"  body: {r.text[:800]}")
        return 1
    sub = r.json()["data"]
    job_id = sub["job_id"]
    print(f"  job_id: {job_id} status={sub['status']}")

    # Step 4: 轮询 active-job
    print(f"\n=== Step 4: 轮询 ===")
    t0 = time.time()
    last_msg = None
    while time.time() - t0 < 300:  # 5 分钟足够 YG36 小文件
        r = s.get(
            f"{BASE}/api/projects/{PROJECT_ID}/ledger-import/active-job",
            timeout=15,
        )
        if r.status_code != 200:
            print(f"  active-job {r.status_code}: {r.text[:200]}")
            time.sleep(2)
            continue
        state = r.json().get("data", {})
        status = state.get("status")
        pct = state.get("progress", 0)
        msg = state.get("message", "")
        if msg != last_msg or status != "processing":
            print(f"  [{int(time.time()-t0)}s] {status} {pct}% {msg}")
            last_msg = msg
        if status in ("completed", "failed", "idle"):
            break
        time.sleep(2)
    print(f"  最终 status={status} 耗时 {int(time.time()-t0)}s")

    # Step 5: diagnostics
    print(f"\n=== Step 5: /diagnostics ===")
    r = s.get(
        f"{BASE}/api/projects/{PROJECT_ID}/ledger-import/jobs/{job_id}/diagnostics",
        timeout=15,
    )
    if r.status_code == 200:
        diag = r.json().get("data", {})
        print(f"  status: {diag.get('status')}")
        print(f"  current_phase: {diag.get('current_phase')}")
        print(f"  error_message: {diag.get('error_message')}")
        print(f"  result_summary: {json.dumps(diag.get('result_summary'), ensure_ascii=False, indent=2)[:800]}")
    else:
        print(f"  diagnostics {r.status_code}: {r.text[:300]}")

    # Step 6: DB 验证
    print(f"\n=== Step 6: DB 验证 ===")
    import asyncio
    import sqlalchemy as sa
    from app.core.database import async_session

    async def db_check():
        async with async_session() as db:
            for tbl in ("tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"):
                row = (await db.execute(sa.text(f"""
                    SELECT COUNT(*) FILTER (WHERE is_deleted=false) AS active,
                           COUNT(*) FILTER (WHERE is_deleted=true) AS staged
                    FROM {tbl}
                    WHERE project_id = :pid AND year = :yr
                """), {"pid": PROJECT_ID, "yr": year})).first()
                print(f"  {tbl}: active={row.active} staged={row.staged}")

    asyncio.run(db_check())
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
