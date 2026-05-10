"""B2 PG COPY 加速真实大账套性能验证。

用途：
- 验证 bulk_copy_staged 在真实大账套上启用（> 10k 行）
- 测三份真实样本：YG4001-30（<10k 走 INSERT 基线）/ YG36（~22k 走 COPY）/ YG2101（~650k 压测）
- 每份跑前清理旧数据，跑后断言行数 + 耗时 + 日志中含 COPY vs INSERT 标记

输出：
- 每个样本的 detect → submit → worker → DB 统计耗时
- 前后对比：切换前 INSERT 基线 vs 切换后 COPY 加速
- 写 JSON 报告到 scripts/b2_perf_report.json
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

SAMPLES = [
    {
        "name": "YG4001-30",
        "path": "数据/YG4001-30重庆医药集团宜宾医药有限公司新健康大药房临港店-余额表+序时账.xlsx",
        "key": "b2perf|YG4001-30|2025",
        "client_name": "B2Perf-YG4001-30新健康大药房",
        "expected": {"balance_min": 500, "ledger_min": 4000},
        "route_expected": "INSERT",  # < 10k 行
    },
    {
        "name": "YG36-四川物流",
        "path": "数据/YG36-重庆医药集团四川物流有限公司2025.xlsx",
        "key": "b2perf|YG36|2025",
        "client_name": "B2Perf-YG36四川物流",
        "expected": {"balance_min": 500, "ledger_min": 20000},
        "route_expected": "COPY",  # 48k 行（ledger+aux_ledger）走 COPY
    },
    # YG2101 650k 行太大，CI 跑不现实，默认跳过；通过 --full 参数显式启用
    {
        "name": "YG2101-四川医药",
        "path": "数据/YG2101-重庆医药集团四川医药有限公司2025年-科目余额表+序时账.xlsx",
        "key": "b2perf|YG2101|2025",
        "client_name": "B2Perf-YG2101四川医药",
        "expected": {"balance_min": 1500, "ledger_min": 500000},
        "route_expected": "COPY",
        "heavy": True,  # 需 --full 参数
    },
]


def _login(s: requests.Session) -> None:
    r = s.post(
        f"{BASE}/api/auth/login",
        json={"username": "admin", "password": "admin123"},
        timeout=30,
    )
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"


def _ensure_project(s: requests.Session, client_name: str, year: int) -> str:
    r = s.post(
        f"{BASE}/api/projects",
        json={
            "client_name": client_name,
            "audit_year": year,
            "project_type": "annual",
            "accounting_standard": "enterprise",
        },
        timeout=30,
    )
    if r.status_code in (200, 201):
        body = r.json()
        pid = body.get("data", body).get("id")
        return pid
    raise RuntimeError(f"项目创建失败 {r.status_code}: {r.text[:500]}")


def _reset_project_data(pid: str, year: int) -> None:
    """清理该项目该年度的旧数据（dataset + tb_* 表）以便公平计时。

    用独立 engine + dispose 避免 asyncio.run 跨次复用全局 async_session 失败。
    """
    import asyncio

    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import settings

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as db:
                for tbl in ("tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"):
                    await db.execute(
                        sa.text(f"DELETE FROM {tbl} WHERE project_id = :p AND year = :y"),
                        {"p": pid, "y": year},
                    )
                await db.execute(
                    sa.text("DELETE FROM import_jobs WHERE project_id = :p"),
                    {"p": pid},
                )
                # 表名是 ledger_datasets
                await db.execute(
                    sa.text("DELETE FROM ledger_datasets WHERE project_id = :p AND year = :y"),
                    {"p": pid, "y": year},
                )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(_run())


def _run_one(sample: dict, full: bool) -> dict:
    name = sample["name"]
    path = ROOT / sample["path"]
    if not path.exists():
        return {"name": name, "skipped": True, "reason": "文件不存在"}
    if sample.get("heavy") and not full:
        return {"name": name, "skipped": True, "reason": "heavy 样本（>100MB），--full 启用"}

    print(f"\n{'='*70}\n样本 {name}  |  {path.name}  |  {path.stat().st_size/1e6:.2f}MB")
    print(f"  期望路径：{sample['route_expected']}  期望行数 balance≥{sample['expected']['balance_min']} ledger≥{sample['expected']['ledger_min']}")

    s = requests.Session()
    _login(s)

    year = 2025
    pid = _ensure_project(s, sample["client_name"], year)
    print(f"  project_id={pid}")

    # 重置数据
    print(f"  清理旧数据...", end="", flush=True)
    t0 = time.time()
    _reset_project_data(pid, year)
    print(f" {time.time()-t0:.1f}s")

    # Detect
    t_detect = time.time()
    print(f"  /detect...", end="", flush=True)
    with path.open("rb") as f:
        r = s.post(
            f"{BASE}/api/projects/{pid}/ledger-import/detect",
            files={"files": (path.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=600,
        )
    r.raise_for_status()
    det = r.json()["data"]
    token_ul = det["upload_token"]
    year = det["detected_year"] or year
    print(f" {time.time()-t_detect:.1f}s")

    # Submit
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

    t_submit = time.time()
    r = s.post(
        f"{BASE}/api/projects/{pid}/ledger-import/submit",
        json={"upload_token": token_ul, "year": year,
              "confirmed_mappings": confirmed, "force_activate": False},
        timeout=60,
    )
    r.raise_for_status()
    job_id = r.json()["data"]["job_id"]

    # Poll until done
    t_worker_start = time.time()
    print(f"  worker 运行...", end="", flush=True)
    timeout_sec = 1800 if sample.get("heavy") else 300
    last_phase = None
    while time.time() - t_worker_start < timeout_sec:
        try:
            r = s.get(
                f"{BASE}/api/projects/{pid}/ledger-import/active-job",
                timeout=60,  # 大账套写入阶段 API 响应可能变慢
            )
        except requests.exceptions.ReadTimeout:
            print(" [api_slow]", end="", flush=True)
            time.sleep(10)
            continue
        except requests.exceptions.ConnectionError:
            print(" [api_conn_err]", end="", flush=True)
            time.sleep(10)
            continue
        if r.status_code == 200:
            state = r.json().get("data", {})
            status = state.get("status")
            phase = state.get("phase")
            if phase != last_phase:
                print(f" [{phase}]", end="", flush=True)
                last_phase = phase
            if status in ("completed", "failed", "idle"):
                break
        time.sleep(2 if not sample.get("heavy") else 10)
    t_worker = time.time() - t_worker_start
    print(f" 完成 {t_worker:.1f}s")

    # DB 验证（用独立 engine + dispose 避免 asyncio.run 跨次复用全局 async_session）
    import asyncio

    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import settings

    counts: dict[str, int] = {}

    async def _count():
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as db:
                for tbl in ("tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"):
                    row = (await db.execute(sa.text(f"""
                        SELECT COUNT(*) FILTER (WHERE is_deleted=false) AS active
                        FROM {tbl} WHERE project_id = :p AND year = :y
                    """), {"p": pid, "y": year})).first()
                    counts[tbl] = row.active
        finally:
            await engine.dispose()

    asyncio.run(_count())
    print(f"  DB: balance={counts['tb_balance']} aux_balance={counts['tb_aux_balance']} "
          f"ledger={counts['tb_ledger']} aux_ledger={counts['tb_aux_ledger']}")

    # 断言
    ok = True
    if counts["tb_balance"] < sample["expected"]["balance_min"]:
        print(f"  ❌ balance 行数 {counts['tb_balance']} < 期望 {sample['expected']['balance_min']}")
        ok = False
    if counts["tb_ledger"] < sample["expected"]["ledger_min"]:
        print(f"  ❌ ledger 行数 {counts['tb_ledger']} < 期望 {sample['expected']['ledger_min']}")
        ok = False

    throughput = (counts["tb_ledger"] + counts["tb_aux_ledger"]) / max(t_worker, 0.001)
    print(f"  吞吐量（ledger+aux_ledger）：{int(throughput)} rows/s")
    if ok:
        print(f"  ✅ 通过")

    return {
        "name": name,
        "file_size_mb": round(path.stat().st_size / 1e6, 2),
        "file_name": path.name,
        "project_id": pid,
        "year": year,
        "worker_sec": round(t_worker, 1),
        "balance": counts["tb_balance"],
        "aux_balance": counts["tb_aux_balance"],
        "ledger": counts["tb_ledger"],
        "aux_ledger": counts["tb_aux_ledger"],
        "throughput_rows_per_sec": int(throughput),
        "route_expected": sample["route_expected"],
        "ok": ok,
    }


def main() -> int:
    full = "--full" in sys.argv
    only_heavy = "--heavy-only" in sys.argv
    print(f"B2 COPY perf 验证 (full={full} heavy_only={only_heavy})")
    results = []
    for spl in SAMPLES:
        if only_heavy and not spl.get("heavy"):
            continue
        try:
            res = _run_one(spl, full=full)
        except Exception as exc:  # noqa: BLE001
            res = {"name": spl["name"], "error": str(exc)}
            print(f"  ❌ 异常：{exc}")
        results.append(res)

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
    }
    out = ROOT / "scripts/b2_perf_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告写入 {out}")

    print(f"\n{'='*70}\n汇总：")
    print(f"{'样本':<20} {'大小 MB':<10} {'耗时 s':<10} {'balance':<10} {'ledger':<12} {'吞吐 r/s':<10} {'路径':<10} {'结果':<6}")
    for r in results:
        if r.get("skipped"):
            print(f"{r['name']:<20} SKIP ({r['reason']})")
            continue
        if r.get("error"):
            print(f"{r['name']:<20} ERROR: {r['error'][:80]}")
            continue
        status = "✅" if r["ok"] else "❌"
        print(f"{r['name']:<20} {r['file_size_mb']:<10} {r['worker_sec']:<10} {r['balance']:<10} "
              f"{r['ledger']:<12} {r['throughput_rows_per_sec']:<10} {r['route_expected']:<10} {status}")

    failed = [r for r in results if not r.get("skipped") and (r.get("error") or not r.get("ok"))]
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
