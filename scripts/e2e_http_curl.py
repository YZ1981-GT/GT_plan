"""真实 YG36 端到端验证脚本（常驻回归工具，非一次性）。

功能：登录 → /detect 上传 → /submit → 轮询 → /diagnostics → DB 验证
+ Layer 3 断言（tb_balance 无重复 + 辅助和=主表 + /balance-tree 端点校验）

触发场景：Worker/orchestrator/converter/pipeline 改动后必须先跑此脚本。

前置：
- 后端运行在 9980
- admin/admin123 可登录
- YG36 样本在 数据/ 目录
- PROJECT_ID 存在

用法：
    python scripts/e2e_http_curl.py
"""
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

    assertions_passed = True

    async def db_check():
        nonlocal assertions_passed
        async with async_session() as db:
            # B' 架构：获取 active dataset_id，所有查询按 dataset_id 过滤
            active_ds_row = (await db.execute(sa.text("""
                SELECT id FROM ledger_datasets
                WHERE project_id = :pid AND year = :yr AND status = 'active'
                ORDER BY activated_at DESC NULLS LAST LIMIT 1
            """), {"pid": PROJECT_ID, "yr": year})).first()
            active_ds_id = str(active_ds_row.id) if active_ds_row else None
            ds_filter = "AND dataset_id = :ds_id" if active_ds_id else ""
            params = {"pid": PROJECT_ID, "yr": year, "ds_id": active_ds_id}
            print(f"  active dataset_id: {active_ds_id}")

            for tbl in ("tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"):
                row = (await db.execute(sa.text(f"""
                    SELECT COUNT(*) FILTER (WHERE is_deleted=false) AS active,
                           COUNT(*) FILTER (WHERE is_deleted=true) AS staged
                    FROM {tbl}
                    WHERE project_id = :pid AND year = :yr {ds_filter}
                """), params)).first()
                print(f"  {tbl}: active={row.active} staged={row.staged}")

            # ── Layer 3 去重断言 ──
            print(f"\n  [Layer 3 断言] tb_balance 主表去重正确性")

            # (a) tb_balance 无 account_code 重复
            dup = (await db.execute(sa.text(f"""
                SELECT account_code, company_code, COUNT(*) AS cnt
                FROM tb_balance
                WHERE project_id = :pid AND year = :yr AND is_deleted = false {ds_filter}
                GROUP BY account_code, company_code
                HAVING COUNT(*) > 1
            """), params)).fetchall()
            if dup:
                print(f"    ❌ tb_balance 主表存在 {len(dup)} 个重复 account_code:")
                for r in dup[:5]:
                    print(f"       {r.account_code} x {r.cnt}")
                assertions_passed = False
            else:
                print(f"    ✅ tb_balance 所有 account_code 唯一（按 company+code 分组）")

            # (b) 1002 银行存款 closing 不翻倍（有则 ≈ 辅助和）
            bank = (await db.execute(sa.text(f"""
                SELECT company_code, account_code, account_name, closing_balance,
                       (raw_extra ->> '_aggregated_from_aux')::bool AS agg,
                       (raw_extra ->> '_aux_row_count')::int AS aux_cnt
                FROM tb_balance
                WHERE project_id = :pid AND year = :yr AND is_deleted = false {ds_filter}
                  AND account_code = '1002'
            """), params)).fetchall()
            if not bank:
                print(f"    ⚠️  未找到 1002 银行存款（YG36 可能使用其他科目编码）")
            else:
                for r in bank:
                    print(f"    1002/{r.company_code}: {r.account_name or ''} "
                          f"closing={r.closing_balance} aggregated={r.agg} aux_cnt={r.aux_cnt}")

                # 辅助和 = 主表值（按 aux_type 分组，多维度场景每个维度类型合计=主表）
                aux_sum = (await db.execute(sa.text(f"""
                    SELECT company_code, aux_type, SUM(closing_balance) AS s,
                           COUNT(*) AS cnt
                    FROM tb_aux_balance
                    WHERE project_id = :pid AND year = :yr AND is_deleted = false {ds_filter}
                      AND account_code = '1002'
                    GROUP BY company_code, aux_type
                """), params)).fetchall()
                for aux in aux_sum:
                    parent = next((b for b in bank if b.company_code == aux.company_code), None)
                    if parent is None:
                        continue
                    diff = abs(float(aux.s or 0) - float(parent.closing_balance or 0))
                    tag = "✅" if diff < 1.0 else "❌"
                    print(f"    {tag} 1002/{aux.company_code}/{aux.aux_type} 辅助和={aux.s} "
                          f"(n={aux.cnt}) 主表={parent.closing_balance} 差={diff:.2f}")
                    if diff >= 1.0:
                        assertions_passed = False

            # (c) 聚合行统计
            agg_count = (await db.execute(sa.text(f"""
                SELECT COUNT(*) AS c
                FROM tb_balance
                WHERE project_id = :pid AND year = :yr AND is_deleted = false {ds_filter}
                  AND (raw_extra ->> '_aggregated_from_aux')::bool = true
            """), params)).scalar()
            print(f"    ℹ️  聚合生成的主表行: {agg_count}（Excel 中无汇总行仅有明细的科目）")

    asyncio.run(db_check())

    # Step 7: /balance-tree 端点验证
    print(f"\n=== Step 7: /balance-tree 端点 ===")
    r = s.get(
        f"{BASE}/api/projects/{PROJECT_ID}/ledger/balance-tree",
        params={"year": year},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"  ❌ {r.status_code}: {r.text[:300]}")
        assertions_passed = False
    else:
        tree_data = r.json().get("data", r.json())
        summary = tree_data["summary"]
        print(f"  科目数: {summary['account_count']}")
        print(f"  含辅助: {summary['with_children_count']}")
        print(f"  辅助行总: {summary['aux_total_rows']}")
        print(f"  聚合行: {summary['aggregated_count']}")
        print(f"  差异（子和≠父）: {len(summary['mismatches'])}")
        if summary["mismatches"]:
            for m in summary["mismatches"][:5]:
                print(f"    ⚠️  {m['account_code']}: 父={m['parent_closing']} "
                      f"子和={m['children_sum']} 差={m['diff']:.2f}")

        # 找 1002 看 children
        n1002 = [n for n in tree_data["tree"] if n["account_code"] == "1002"]
        if n1002:
            node = n1002[0]
            print(f"  1002 节点: children={len(node['children'])} "
                  f"closing={node['closing_balance']} has_children={node['has_children']}")
            if node["has_children"]:
                for c in node["children"][:5]:
                    # 后端返回 code/name 而非 aux_code/aux_name
                    code = c.get('aux_code') or c.get('code') or '?'
                    name = c.get('aux_name') or c.get('name') or '?'
                    aux_type = c.get('aux_type') or c.get('type') or '?'
                    print(f"    └─ {aux_type}:{code} {name} "
                          f"closing={c.get('closing_balance')}")

    print(f"\n=== 总结 ===")
    if assertions_passed:
        print("  ✅ 所有 Layer 3 断言通过：tb_balance 去重正确 + 辅助和=主表")
        return 0
    else:
        print("  ❌ 部分断言失败，见上方详情")
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
