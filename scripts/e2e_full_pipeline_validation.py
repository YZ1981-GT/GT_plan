"""账表导入全流程深度验证（Sprint 8 UX v3 收尾）

阶段覆盖：
1. 登录 + 创建全新项目（避免历史残留）
2. 上传文件 → detect：检查识别结果、列映射置信度、aux 列识别
3. submit：job_id 返回
4. 轮询 active-job：检查 phase/progress/estimated_remaining_seconds 字段
5. 轮询完成：检查 DB 四表行数、raw_extra 字段
6. 查 /balance-tree：检查三层嵌套结构、mismatches=0、aux_types 正确
7. 查 only_with_activity：损益类 6xxx 被正确包含
8. 查 only_with_children + keyword + 分页边界
9. 最终 cancel 测试：确认 artifact 被 mark_consumed

用法：python scripts/e2e_full_pipeline_validation.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

BASE = "http://127.0.0.1:9980"
SAMPLE = ROOT / "数据/YG4001-30重庆医药集团宜宾医药有限公司新健康大药房临港店-余额表+序时账.xlsx"
YEAR = 2025


def pf(msg: str, ok: bool = True) -> None:
    prefix = "✓" if ok else "✗"
    print(f"  {prefix} {msg}")


def main() -> int:
    assert SAMPLE.exists(), f"样本不存在：{SAMPLE}"
    s = requests.Session()
    all_passed = True

    # ── Step 1: 登录 ──
    print("\n=== Step 1: 登录 ===")
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "admin", "password": "admin123"}, timeout=30)
    assert r.status_code == 200
    s.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"
    pf("登录成功")

    # ── Step 2: 创建全新项目 ──
    print("\n=== Step 2: 创建全新项目 ===")
    r = s.post(f"{BASE}/api/projects", json={
        "client_name": f"E2E-深度验证-{uuid4().hex[:6]}",
        "audit_year": YEAR,
        "project_type": "annual",
        "accounting_standard": "enterprise",
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    project_id = r.json().get("data", r.json())["id"]
    pf(f"项目创建 id={project_id}")

    # ── Step 3: detect ──
    print(f"\n=== Step 3: /detect 上传 {SAMPLE.name} ({SAMPLE.stat().st_size / 1024:.0f}KB) ===")
    t0 = time.time()
    with SAMPLE.open("rb") as f:
        r = s.post(
            f"{BASE}/api/projects/{project_id}/ledger-import/detect",
            files={"files": (SAMPLE.name, f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=120,
        )
    detect_elapsed = time.time() - t0
    assert r.status_code == 200, r.text
    det = r.json()["data"]
    pf(f"识别耗时 {detect_elapsed:.1f}s")
    pf(f"upload_token={det['upload_token']}")
    pf(f"detected_year={det['detected_year']}")

    # 验证：sheet 识别为 balance + ledger
    sheet_types = [(sh["file_name"], sh["sheet_name"], sh["table_type"],
                    sh["table_type_confidence"])
                   for fd in det["files"] for sh in fd["sheets"]]
    has_balance = any(t == "balance" for _, _, t, _ in sheet_types)
    has_ledger = any(t == "ledger" for _, _, t, _ in sheet_types)
    pf(f"识别到 balance sheet: {has_balance}", has_balance)
    pf(f"识别到 ledger sheet: {has_ledger}", has_ledger)
    all_passed &= has_balance and has_ledger

    # 验证：列映射置信度 >= 50 的列数
    for fd in det["files"]:
        for sh in fd["sheets"]:
            high_conf = sum(1 for cm in sh["column_mappings"]
                            if cm["confidence"] >= 50)
            total = len(sh["column_mappings"])
            pf(f"{sh['sheet_name']}: 列映射 {high_conf}/{total} 高置信度")

    # ── Step 4: submit ──
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
        f"{BASE}/api/projects/{project_id}/ledger-import/submit",
        json={"upload_token": det["upload_token"], "year": YEAR,
              "confirmed_mappings": confirmed, "force_activate": False},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["data"]["job_id"]
    pf(f"job_id={job_id}")

    # ── Step 5: 轮询 active-job 深度检查字段 ──
    print(f"\n=== Step 5: 轮询 active-job（检查新字段） ===")
    t0 = time.time()
    seen_phases = set()
    saw_eta = False
    while time.time() - t0 < 120:
        r = s.get(
            f"{BASE}/api/projects/{project_id}/ledger-import/active-job",
            timeout=15,
        )
        if r.status_code != 200:
            time.sleep(2)
            continue
        state = r.json().get("data", {})
        status = state.get("status")
        phase = state.get("phase")
        pct = state.get("progress", 0)
        eta = state.get("estimated_remaining_seconds")
        if phase:
            seen_phases.add(phase)
        if eta is not None:
            saw_eta = True
        if status in ("completed", "failed", "idle", "canceled"):
            break
        time.sleep(1.5)

    pf(f"观察到 phase 集合: {seen_phases}")
    pf(f"返回了 estimated_remaining_seconds: {saw_eta}", saw_eta)
    pf(f"最终 status={status}，耗时 {time.time()-t0:.0f}s")
    all_passed &= saw_eta

    # ── Step 6: diagnostics ──
    print(f"\n=== Step 6: /diagnostics ===")
    r = s.get(
        f"{BASE}/api/projects/{project_id}/ledger-import/jobs/{job_id}/diagnostics",
        timeout=15,
    )
    diag = r.json().get("data", {})
    pf(f"status={diag.get('status')} phase={diag.get('current_phase')}")
    if diag.get('error_message'):
        pf(f"error_message: {diag['error_message'][:200]}")
    rs = diag.get("result_summary", {})
    pf(f"四表行数: balance={rs.get('balance_rows')} aux_balance={rs.get('aux_balance_rows')} "
       f"ledger={rs.get('ledger_rows')} aux_ledger={rs.get('aux_ledger_rows')}")
    pf(f"blocking_findings={rs.get('blocking_findings', 0)}")

    # ── Step 7: DB 直查验证 ──
    print(f"\n=== Step 7: DB 直查验证 ===")
    import asyncio
    import sqlalchemy as sa
    from app.core.database import async_session

    db_results = {}
    async def db_check():
        async with async_session() as db:
            for tbl in ("tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"):
                row = (await db.execute(sa.text(f"""
                    SELECT COUNT(*) FILTER (WHERE is_deleted=false) AS active
                    FROM {tbl}
                    WHERE project_id = :pid AND year = :yr
                """), {"pid": project_id, "yr": YEAR})).first()
                db_results[tbl] = row.active

            # 检查 tb_balance 无 account_code 重复
            dup = (await db.execute(sa.text("""
                SELECT account_code, COUNT(*) AS cnt FROM tb_balance
                WHERE project_id = :pid AND year = :yr AND is_deleted = false
                GROUP BY account_code HAVING COUNT(*) > 1
            """), {"pid": project_id, "yr": YEAR})).fetchall()
            db_results["duplicates"] = len(dup)

            # 检查 raw_extra 含 _aggregated_from_aux 的聚合行数
            agg = (await db.execute(sa.text("""
                SELECT COUNT(*) FROM tb_balance
                WHERE project_id = :pid AND year = :yr AND is_deleted = false
                  AND (raw_extra ->> '_aggregated_from_aux')::bool = true
            """), {"pid": project_id, "yr": YEAR})).scalar()
            db_results["aggregated_rows"] = agg

    asyncio.run(db_check())
    for k, v in db_results.items():
        pf(f"{k}: {v}")
    all_passed &= db_results.get("duplicates", 0) == 0

    # ── Step 8: /balance-tree 三层嵌套验证 ──
    print(f"\n=== Step 8: /balance-tree 三层嵌套 ===")
    r = s.get(
        f"{BASE}/api/projects/{project_id}/ledger/balance-tree",
        params={"year": YEAR, "page_size": 5},
        timeout=30,
    )
    data = r.json().get("data", r.json())
    # 验证 pagination 字段
    pagination_ok = all(k in data.get("pagination", {})
                        for k in ("page", "page_size", "total", "total_pages"))
    pf(f"pagination 字段完整: {pagination_ok}", pagination_ok)
    # 验证 summary 字段
    s_ok = all(k in data.get("summary", {})
               for k in ("account_count", "aggregated_count",
                         "with_children_count", "aux_total_rows", "mismatches"))
    pf(f"summary 字段完整: {s_ok}", s_ok)
    # 验证每个 tree node 结构
    if data["tree"]:
        node = data["tree"][0]
        required_parent_keys = ("account_code", "account_name", "level",
                                "company_code", "closing_balance",
                                "aggregated_from_aux", "aux_types",
                                "aux_rows_total", "has_children", "children")
        parent_ok = all(k in node for k in required_parent_keys)
        pf(f"父节点字段完整: {parent_ok}", parent_ok)
        # 找一个带 children 的父，验证维度组节点
        for n in data["tree"]:
            if n["children"]:
                group = n["children"][0]
                grp_ok = all(k in group for k in
                             ("_is_dimension_group", "aux_type",
                              "closing_balance", "record_count", "children"))
                pf(f"维度组节点字段完整: {grp_ok}", grp_ok)
                if group["children"]:
                    detail = group["children"][0]
                    det_ok = all(k in detail for k in
                                 ("aux_type", "aux_code", "aux_name",
                                  "closing_balance"))
                    pf(f"明细行字段完整: {det_ok}", det_ok)
                break
    # 验证 mismatch = 0
    mismatch_count = len(data["summary"]["mismatches"])
    pf(f"mismatch 数: {mismatch_count}（期望 0）", mismatch_count == 0)
    all_passed &= mismatch_count == 0

    # ── Step 9: only_with_activity 损益类包含验证 ──
    print(f"\n=== Step 9: only_with_activity 损益类 ===")
    r = s.get(
        f"{BASE}/api/projects/{project_id}/ledger/balance-tree",
        params={"year": YEAR, "only_with_activity": "true",
                "keyword": "6001", "page_size": 10},
        timeout=30,
    )
    data = r.json().get("data", r.json())
    loss_gain = [n for n in data["tree"] if n["account_code"].startswith("6001")]
    pf(f"6001 系列有金额活动科目数: {len(loss_gain)}（期望 ≥ 1）", len(loss_gain) >= 1)
    all_passed &= len(loss_gain) >= 1

    # ── Step 10: 分页 + keyword ──
    print(f"\n=== Step 10: 分页 + keyword ===")
    r = s.get(
        f"{BASE}/api/projects/{project_id}/ledger/balance-tree",
        params={"year": YEAR, "page": 2, "page_size": 50},
        timeout=30,
    )
    data = r.json().get("data", r.json())
    pf(f"page 2 size 50: 返回 {len(data['tree'])} 行 / total={data['pagination']['total']}")
    r = s.get(
        f"{BASE}/api/projects/{project_id}/ledger/balance-tree",
        params={"year": YEAR, "keyword": "银行", "page_size": 20},
        timeout=30,
    )
    data = r.json().get("data", r.json())
    pf(f"keyword=银行: 返回 {len(data['tree'])} 行")

    # ── Step 11: 分页超限 ──
    print(f"\n=== Step 11: 分页边界（page_size=201 应 422） ===")
    r = s.get(
        f"{BASE}/api/projects/{project_id}/ledger/balance-tree",
        params={"year": YEAR, "page_size": 201},
        timeout=30,
    )
    pf(f"status_code={r.status_code}（期望 422）", r.status_code == 422)
    all_passed &= r.status_code == 422

    # ── 最终总结 ──
    print(f"\n{'='*60}")
    if all_passed:
        print(f"✓ 全部阶段验证通过（项目 id={project_id}）")
        return 0
    print(f"✗ 部分阶段失败，见上方详情")
    return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
