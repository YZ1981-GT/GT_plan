"""九家样本批量上传验证脚本（永久保留，非一次性）。

功能：登录 → 逐企业上传 /detect → /submit → 轮询至完成/失败 → 打印汇总表

触发场景：
- 账表导入引擎改动后的全量回归验证
- 新样本加入后的兼容性验证
- 部署前 smoke test

前置：
- 后端运行在 9980
- admin/admin123 可登录
- 数据/ 目录存在且含 9 家企业样本
- PROJECT_ID 对应的项目存在

用法：
    python scripts/e2e_9_companies_batch.py           # 跳过慢样本
    python scripts/e2e_9_companies_batch.py --all     # 包含慢样本（>100MB）
    python scripts/e2e_9_companies_batch.py --project-id <uuid>
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import NamedTuple

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "数据"

BASE = "http://127.0.0.1:9980"
DEFAULT_PROJECT_ID = "f4b778ad-23b3-49ab-b3c8-ee62a5f82226"

TIMEOUT_NORMAL = 600   # 10 min
TIMEOUT_SLOW = 1200    # 20 min


class Company(NamedTuple):
    name: str
    paths: list[Path]
    slow: bool


def discover_companies() -> list[Company]:
    """定义 9 家企业及其文件路径。"""
    companies = []

    # 1. YG36 (single xlsx)
    companies.append(Company(
        name="YG36 四川物流",
        paths=[DATA_DIR / "YG36-重庆医药集团四川物流有限公司2025.xlsx"],
        slow=False,
    ))

    # 2. YG4001 (single xlsx)
    companies.append(Company(
        name="YG4001 宜宾大药房",
        paths=[DATA_DIR / "YG4001-30重庆医药集团宜宾医药有限公司新健康大药房临港店-余额表+序时账.xlsx"],
        slow=False,
    ))

    # 3. YG2101 (single xlsx, 128MB — slow)
    companies.append(Company(
        name="YG2101 四川医药",
        paths=[DATA_DIR / "YG2101-重庆医药集团四川医药有限公司2025年-科目余额表+序时账.xlsx"],
        slow=True,
    ))

    # 4. 安徽骨科 (single xlsx)
    companies.append(Company(
        name="安徽骨科",
        paths=[DATA_DIR / "余额表+序时账-安徽-骨科.xlsx"],
        slow=False,
    ))

    # 5. 和平物流 (single xlsx)
    companies.append(Company(
        name="和平物流",
        paths=[DATA_DIR / "和平物流25加工账-药品批发.xlsx"],
        slow=False,
    ))

    # 6. 辽宁卫生 (directory with 2 xlsx files)
    liaoning_dir = DATA_DIR / "辽宁卫生服务有限公司"
    companies.append(Company(
        name="辽宁卫生",
        paths=sorted(liaoning_dir.glob("*.xlsx")) if liaoning_dir.exists() else [],
        slow=False,
    ))

    # 7. 医疗器械 (directory with 2 xlsx files)
    qixie_dir = DATA_DIR / "重庆医药集团医疗器械有限公司-医疗设备"
    companies.append(Company(
        name="医疗器械",
        paths=sorted(qixie_dir.glob("*.xlsx")) if qixie_dir.exists() else [],
        slow=False,
    ))

    # 8. 和平药房 (directory: 1 xlsx + 2 csv, slow due to 392MB CSV)
    hpyf_dir = DATA_DIR / "和平药房"
    if hpyf_dir.exists():
        hpyf_files = sorted(
            list(hpyf_dir.glob("*.xlsx")) + list(hpyf_dir.glob("*.csv"))
        )
    else:
        hpyf_files = []
    companies.append(Company(
        name="和平药房",
        paths=hpyf_files,
        slow=True,
    ))

    # 9. 陕西华氏 (directory: 13+ files per year, slow)
    shaanxi_dir = DATA_DIR / "陕西华氏医药有限公司-需加工24和25年的AUD文件"
    shaanxi_files: list[Path] = []
    if shaanxi_dir.exists():
        for year_dir in sorted(shaanxi_dir.iterdir()):
            if year_dir.is_dir():
                shaanxi_files.extend(sorted(
                    list(year_dir.glob("*.xlsx")) + list(year_dir.glob("*.csv"))
                ))
    companies.append(Company(
        name="陕西华氏",
        paths=shaanxi_files,
        slow=True,
    ))

    return companies


def get_mime_type(path: Path) -> str:
    """根据扩展名返回 MIME type。"""
    ext = path.suffix.lower()
    if ext == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif ext == ".xls":
        return "application/vnd.ms-excel"
    elif ext == ".csv":
        return "text/csv"
    return "application/octet-stream"


def run_company(
    session: requests.Session,
    project_id: str,
    company: Company,
) -> dict:
    """对单个企业执行 detect → submit → poll 全流程。"""
    result = {
        "name": company.name,
        "status": "skipped",
        "rows": 0,
        "duration": 0.0,
        "error": "",
    }

    # 检查文件是否存在
    missing = [p for p in company.paths if not p.exists()]
    if missing:
        result["status"] = "missing_files"
        result["error"] = f"缺失: {[p.name for p in missing[:3]]}"
        return result

    if not company.paths:
        result["status"] = "no_files"
        result["error"] = "无文件"
        return result

    timeout = TIMEOUT_SLOW if company.slow else TIMEOUT_NORMAL
    t_start = time.time()

    # --- Step 1: /detect (multipart, all files at once) ---
    files_payload = []
    total_size_mb = 0.0
    for p in company.paths:
        total_size_mb += p.stat().st_size / (1024 * 1024)
        files_payload.append(
            ("files", (p.name, p.open("rb"), get_mime_type(p)))
        )

    print(f"  📤 上传 {len(company.paths)} 个文件 ({total_size_mb:.1f} MB)...")

    try:
        r = session.post(
            f"{BASE}/api/projects/{project_id}/ledger-import/detect",
            files=files_payload,
            timeout=300,
        )
    finally:
        # 关闭打开的文件句柄
        for _, (_, fh, _) in files_payload:
            fh.close()

    if r.status_code != 200:
        result["status"] = "detect_failed"
        result["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
        result["duration"] = time.time() - t_start
        return result

    det = r.json().get("data", r.json())
    upload_token = det.get("upload_token")
    year = det.get("detected_year")
    print(f"  🔍 识别完成: year={year}, token={upload_token}")

    # 打印每个 sheet 的识别结果
    for fd in det.get("files", []):
        for sh in fd.get("sheets", []):
            print(f"     {fd['file_name']}/{sh['sheet_name']}: "
                  f"type={sh['table_type']} conf={sh['table_type_confidence']}")

    # --- Step 2: /submit (auto-confirm mappings with confidence >= 50) ---
    confirmed_mappings = []
    for fd in det.get("files", []):
        for sh in fd.get("sheets", []):
            if sh.get("table_type") == "unknown":
                continue
            mappings = {
                cm["column_header"]: cm["standard_field"]
                for cm in sh.get("column_mappings", [])
                if cm.get("standard_field") and cm.get("confidence", 0) >= 50
            }
            confirmed_mappings.append({
                "file_name": fd["file_name"],
                "sheet_name": sh["sheet_name"],
                "table_type": sh["table_type"],
                "mappings": mappings,
            })

    r = session.post(
        f"{BASE}/api/projects/{project_id}/ledger-import/submit",
        json={
            "upload_token": upload_token,
            "year": year,
            "confirmed_mappings": confirmed_mappings,
            "force_activate": False,
            "force_submit": True,
        },
        timeout=60,
    )

    if r.status_code != 200:
        result["status"] = "submit_failed"
        result["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
        result["duration"] = time.time() - t_start
        return result

    sub = r.json().get("data", r.json())
    job_id = sub.get("job_id")
    print(f"  🚀 提交成功: job_id={job_id}")

    # --- Step 3: Poll until completed/failed ---
    poll_start = time.time()
    last_pct = -1
    final_status = "timeout"

    while time.time() - poll_start < timeout:
        try:
            r = session.get(
                f"{BASE}/api/projects/{project_id}/ledger-import/active-job",
                timeout=15,
            )
        except requests.RequestException:
            time.sleep(3)
            continue

        if r.status_code != 200:
            time.sleep(3)
            continue

        state = r.json().get("data", {})
        status = state.get("status", "")
        pct = state.get("progress", 0)

        if pct != last_pct:
            elapsed = int(time.time() - t_start)
            print(f"     [{elapsed}s] {status} {pct}% {state.get('message', '')}")
            last_pct = pct

        if status in ("completed", "failed", "idle"):
            final_status = status
            break

        time.sleep(3)

    result["duration"] = time.time() - t_start

    if final_status == "completed":
        result["status"] = "completed"
        # 获取 diagnostics 拿行数
        try:
            r = session.get(
                f"{BASE}/api/projects/{project_id}/ledger-import/jobs/{job_id}/diagnostics",
                timeout=15,
            )
            if r.status_code == 200:
                diag = r.json().get("data", {})
                summary = diag.get("result_summary", {})
                rows = (
                    summary.get("tb_balance", 0)
                    + summary.get("tb_ledger", 0)
                    + summary.get("tb_aux_balance", 0)
                    + summary.get("tb_aux_ledger", 0)
                )
                result["rows"] = rows
        except Exception:
            pass
    elif final_status == "failed":
        result["status"] = "failed"
        try:
            r = session.get(
                f"{BASE}/api/projects/{project_id}/ledger-import/jobs/{job_id}/diagnostics",
                timeout=15,
            )
            if r.status_code == 200:
                diag = r.json().get("data", {})
                result["error"] = diag.get("error_message", "")[:200]
        except Exception:
            result["error"] = "unknown failure"
    else:
        result["status"] = "timeout"
        result["error"] = f"超时 {timeout}s"

    return result


def main():
    parser = argparse.ArgumentParser(
        description="九家样本批量上传验证脚本"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="包含慢样本（YG2101 128MB / 和平药房 392MB / 陕西华氏 13+ 文件）",
    )
    parser.add_argument(
        "--project-id",
        default=DEFAULT_PROJECT_ID,
        help=f"项目 ID (default: {DEFAULT_PROJECT_ID})",
    )
    args = parser.parse_args()

    companies = discover_companies()

    # --- Login ---
    print("=" * 60)
    print("九家样本批量上传验证")
    print("=" * 60)
    print(f"\n🔑 登录...")
    s = requests.Session()
    r = s.post(
        f"{BASE}/api/auth/login",
        json={"username": "admin", "password": "admin123"},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"  ❌ 登录失败: {r.status_code} {r.text[:200]}")
        return 1
    token = r.json()["data"]["access_token"]
    s.headers["Authorization"] = f"Bearer {token}"
    print(f"  ✅ 登录成功")

    # --- Run each company ---
    results: list[dict] = []
    skipped_slow = 0

    for i, company in enumerate(companies, 1):
        print(f"\n{'─' * 50}")
        slow_tag = " [SLOW]" if company.slow else ""
        print(f"[{i}/9] {company.name}{slow_tag}")

        if company.slow and not args.all:
            print(f"  ⏭️  跳过（使用 --all 包含慢样本）")
            skipped_slow += 1
            results.append({
                "name": company.name,
                "status": "skipped_slow",
                "rows": 0,
                "duration": 0.0,
                "error": "使用 --all 运行",
            })
            continue

        result = run_company(s, args.project_id, company)
        results.append(result)

        status_icon = {
            "completed": "✅",
            "failed": "❌",
            "timeout": "⏰",
            "detect_failed": "❌",
            "submit_failed": "❌",
            "missing_files": "⚠️",
            "no_files": "⚠️",
        }.get(result["status"], "❓")
        print(f"  {status_icon} {result['status']} "
              f"({result['duration']:.0f}s, {result['rows']} rows)")
        if result["error"]:
            print(f"     错误: {result['error'][:150]}")

    # --- Summary table ---
    print(f"\n{'═' * 60}")
    print("汇总")
    print(f"{'═' * 60}")
    print(f"{'企业':<16} {'状态':<14} {'行数':>10} {'耗时':>8} {'备注'}")
    print(f"{'─' * 16} {'─' * 14} {'─' * 10} {'─' * 8} {'─' * 20}")

    success_count = 0
    fail_count = 0
    total_rows = 0
    total_duration = 0.0

    for r in results:
        name = r["name"][:15]
        status = r["status"]
        rows = r["rows"]
        dur = f"{r['duration']:.0f}s" if r["duration"] > 0 else "-"
        note = r["error"][:20] if r["error"] else ""

        print(f"{name:<16} {status:<14} {rows:>10} {dur:>8} {note}")

        if status == "completed":
            success_count += 1
            total_rows += rows
            total_duration += r["duration"]
        elif status not in ("skipped_slow",):
            fail_count += 1

    print(f"{'─' * 60}")
    print(f"成功: {success_count} | 失败: {fail_count} | "
          f"跳过: {skipped_slow} | 总行数: {total_rows:,} | "
          f"总耗时: {total_duration:.0f}s")

    if fail_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
