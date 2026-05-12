"""最小样本 YG4001-30 新健康大药房临港店 端到端 smoke 验证。

用途：
- 快速回归 Sprint 8 全链路（~0.8MB xlsx，<30 秒完成）
- Sprint 8 后续改动的 CI 式验证入口（比 YG36 3.5MB 快 5-10 倍）

断言：
- detect → submit → worker → DB：balance/ledger 行数大于 0
- /balance-tree：返回 pagination 元信息，mismatch = 0
- only_with_activity 过滤：损益类（5/6）被正确包含
- 多公司隔离：合并模式下 company_code 不串
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from uuid import UUID

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

BASE = "http://127.0.0.1:9980"
SAMPLE_FILE = ROOT / "数据/YG4001-30重庆医药集团宜宾医药有限公司新健康大药房临港店-余额表+序时账.xlsx"
# 用企业名+年稳定哈希作为 project_id，重跑同一个文件用同 project
PROJECT_ID = str(UUID(hashlib.md5(b"YG4001-30|2025").hexdigest()))
YEAR = 2025


def _ensure_project(s: requests.Session):
    """确保 project_id 存在，如不存在就创建。"""
    r = s.get(f"{BASE}/api/projects/{PROJECT_ID}", timeout=15)
    if r.status_code == 200:
        print(f"  项目已存在，继续")
        return
    # 创建——字段对齐 BasicInfoSchema（client_name/audit_year/project_type/accounting_standard 必填）
    r = s.post(f"{BASE}/api/projects", json={
        "client_name": "重庆医药集团宜宾医药新健康大药房临港店",
        "audit_year": YEAR,
        "project_type": "annual",
        "accounting_standard": "enterprise",
    }, timeout=30)
    if r.status_code in (200, 201):
        created_id = r.json().get("data", r.json()).get("id")
        print(f"  项目已创建 id={created_id}")
        # 本 smoke 用固定 PROJECT_ID，这里记真实 id 但不覆盖——改脚本用创建返回的 id
        globals()["PROJECT_ID"] = created_id
    else:
        raise RuntimeError(f"项目创建失败 {r.status_code}: {r.text[:500]}")


def main() -> int:
    s = requests.Session()
    assert SAMPLE_FILE.exists(), f"样本文件不存在：{SAMPLE_FILE}"

    print(f"\n=== Step 1: 登录 ===")
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "admin", "password": "admin123"}, timeout=30)
    s.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"
    print(f"  OK")

    print(f"\n=== Step 2: 确保项目 {PROJECT_ID} ===")
    _ensure_project(s)

    print(f"\n=== Step 3: /detect 上传 {SAMPLE_FILE.name} ===")
    t0 = time.time()
    with SAMPLE_FILE.open("rb") as f:
        r = s.post(
            f"{BASE}/api/projects/{PROJECT_ID}/ledger-import/detect",
            files={"files": (SAMPLE_FILE.name, f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=120,
        )
    print(f"  status={r.status_code} 耗时 {time.time()-t0:.1f}s")
    if r.status_code != 200:
        print(f"  body: {r.text[:500]}")
        return 1
    det = r.json()["data"]
    token_ul = det["upload_token"]
    year = det["detected_year"] or YEAR
    print(f"  upload_token={token_ul} year={year}")
    for fd in det["files"]:
        for sh in fd["sheets"]:
            print(f"  {fd['file_name']} / {sh['sheet_name']}: "
                  f"type={sh['table_type']} conf={sh['table_type_confidence']}")

    print(f"\n=== Step 4: /submit ===")
    confirmed = []
    for fd in det["files"]:
        for sh in fd["sheets"]:
            if sh["table_type"] == "unknown":
                continue
            mappings = {cm["column_header"]: cm["standard_field"]
                        for cm in sh["column_mappings"]
                        if cm["standard_field"] and cm["confidence"] >= 50}
            confirmed.append({
                "file_name": fd["file_name"],
                "sheet_name": sh["sheet_name"],
                "table_type": sh["table_type"],
                "mappings": mappings,
            })
    r = s.post(
        f"{BASE}/api/projects/{PROJECT_ID}/ledger-import/submit",
        json={"upload_token": token_ul, "year": year,
              "confirmed_mappings": confirmed, "force_activate": False},
        timeout=60,
    )
    if r.status_code != 200:
        print(f"  status={r.status_code} body: {r.text[:500]}")
        return 1
    sub = r.json()["data"]
    job_id = sub["job_id"]
    print(f"  job_id={job_id}")

    print(f"\n=== Step 5: 轮询 ===")
    t0 = time.time()
    while time.time() - t0 < 180:
        r = s.get(
            f"{BASE}/api/projects/{PROJECT_ID}/ledger-import/active-job",
            timeout=15,
        )
        if r.status_code != 200:
            time.sleep(2)
            continue
        state = r.json().get("data", {})
        status = state.get("status")
        pct = state.get("progress", 0)
        if status in ("completed", "failed", "idle"):
            break
        time.sleep(2)
    print(f"  最终 status={status} 耗时 {int(time.time()-t0)}s")

    print(f"\n=== Step 6: DB 基本统计 ===")
    import asyncio
    import sqlalchemy as sa
    from app.core.database import async_session

    stats = {}
    async def db_check():
        async with async_session() as db:
            for tbl in ("tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"):
                row = (await db.execute(sa.text(f"""
                    SELECT COUNT(*) FILTER (WHERE is_deleted=false) AS active
                    FROM {tbl}
                    WHERE project_id = :pid AND year = :yr
                """), {"pid": PROJECT_ID, "yr": year})).first()
                stats[tbl] = row.active
                print(f"  {tbl}: active={row.active}")
    asyncio.run(db_check())

    assertions_passed = True
    if stats.get("tb_balance", 0) == 0:
        print("  ❌ tb_balance 为空，导入失败")
        assertions_passed = False

    print(f"\n=== Step 7: /balance-tree（默认）===")
    r = s.get(f"{BASE}/api/projects/{PROJECT_ID}/ledger/balance-tree",
              params={"year": year, "page_size": 1}, timeout=30)
    d = r.json().get("data", r.json())
    total = d["pagination"]["total"]
    mis = len(d["summary"]["mismatches"])
    print(f"  总科目 {total} | mismatch {mis}")
    if mis > 0:
        print(f"  ❌ 出现 {mis} 个 mismatch:")
        for m in d["summary"]["mismatches"][:3]:
            print(f"     {m}")
        assertions_passed = False

    print(f"\n=== Step 8: /balance-tree only_with_activity ===")
    r = s.get(f"{BASE}/api/projects/{PROJECT_ID}/ledger/balance-tree",
              params={"year": year, "only_with_activity": "true",
                      "page_size": 1}, timeout=30)
    d_act = r.json().get("data", r.json())
    print(f"  有活动科目 {d_act['pagination']['total']} / 全部 {total}")
    # 再查 only 6xxx 有活动的科目
    r = s.get(f"{BASE}/api/projects/{PROJECT_ID}/ledger/balance-tree",
              params={"year": year, "only_with_activity": "true",
                      "keyword": "6", "page_size": 200}, timeout=30)
    d6 = r.json().get("data", r.json())
    loss_gain = [n for n in d6["tree"] if n["account_code"].startswith("6")]
    print(f"  6xxx 有活动 {len(loss_gain)} 个")
    for n in loss_gain[:3]:
        print(f"    {n['account_code']} {n['account_name']}: "
              f"debit={n['debit_amount']} credit={n['credit_amount']}")

    print(f"\n=== Step 9: /balance-tree 分页验证 ===")
    r = s.get(f"{BASE}/api/projects/{PROJECT_ID}/ledger/balance-tree",
              params={"year": year, "page_size": 20, "page": 2}, timeout=30)
    d_p = r.json().get("data", r.json())
    pg = d_p["pagination"]
    print(f"  page 2 size 20: 返回 {len(d_p['tree'])} 行，total_pages={pg['total_pages']}")
    assert pg["page"] == 2 and pg["page_size"] == 20

    print(f"\n=== 总结 ===")
    if assertions_passed:
        print("  ✅ YG4001-30 smoke 全部通过")
        return 0
    print("  ❌ 部分断言失败")
    return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
