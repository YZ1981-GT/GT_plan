"""批量验证 9 家真实账套的 v2 pipeline 端到端入库能力。

测试范围：
1. YG36 四川物流（单 xlsx 多 sheet）
2. YG2101 四川医药（单 xlsx）
3. YG4001 宜宾大药房（单 xlsx）
4. 和平药房（1 余额 xlsx + 2 csv 序时账）
5. 和平物流（单 xlsx）
6. 安徽骨科（单 xlsx）
7. 辽宁卫生（2 xlsx 分开）
8. 医疗器械（2 xlsx 分开）
9. 陕西华氏 2024（1 余额 + 12 月度序时）
10. 陕西华氏 2025（1 余额 + 12 月度序时）

每家使用唯一 project_id（基于企业名哈希），跑完打印 4 张表行数 + 维度 TOP 5。
输出汇总表格对比通过率。

用完即删。
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

DATA_ROOT = ROOT / "数据"


@dataclass
class CompanyCase:
    """一家企业一年账套的测试用例。"""
    name: str
    year: int
    files: list[Path] = field(default_factory=list)
    # 结果
    status: str = "pending"  # success | partial | failed
    balance_rows: int = 0
    aux_balance_rows: int = 0
    ledger_rows: int = 0
    aux_ledger_rows: int = 0
    aux_top5: str = ""
    error: str = ""

    @property
    def project_id(self) -> UUID:
        # 基于名+年稳定哈希，确保每次运行用同一个 project_id
        h = hashlib.md5(f"{self.name}|{self.year}".encode()).hexdigest()
        return UUID(h)


def build_cases() -> list[CompanyCase]:
    """组装 10 个测试用例（9 家企业，陕西华氏拆 2024/2025）。"""
    cases = []

    # 1. YG36 四川物流
    p = DATA_ROOT / "YG36-重庆医药集团四川物流有限公司2025.xlsx"
    if p.exists():
        cases.append(CompanyCase("YG36 四川物流", 2025, [p]))

    # 2. YG2101 四川医药
    p = DATA_ROOT / "YG2101-重庆医药集团四川医药有限公司2025年-科目余额表+序时账.xlsx"
    if p.exists():
        cases.append(CompanyCase("YG2101 四川医药", 2025, [p]))

    # 3. YG4001 宜宾大药房
    p = DATA_ROOT / "YG4001-30重庆医药集团宜宾医药有限公司新健康大药房临港店-余额表+序时账.xlsx"
    if p.exists():
        cases.append(CompanyCase("YG4001 宜宾大药房", 2025, [p]))

    # 4. 和平药房 (1 xlsx 余额 + 2 csv 序时)
    hp_dir = DATA_ROOT / "和平药房"
    if hp_dir.exists():
        files = sorted(hp_dir.glob("*.xlsx")) + sorted(hp_dir.glob("*.csv"))
        cases.append(CompanyCase("和平药房", 2025, files))

    # 5. 和平物流
    p = DATA_ROOT / "和平物流25加工账-药品批发.xlsx"
    if p.exists():
        cases.append(CompanyCase("和平物流", 2025, [p]))

    # 6. 安徽骨科
    p = DATA_ROOT / "余额表+序时账-安徽-骨科.xlsx"
    if p.exists():
        cases.append(CompanyCase("安徽骨科", 2025, [p]))

    # 7. 辽宁卫生 (2 xlsx)
    ln_dir = DATA_ROOT / "辽宁卫生服务有限公司"
    if ln_dir.exists():
        files = sorted(ln_dir.glob("*.xlsx"))
        cases.append(CompanyCase("辽宁卫生", 2025, files))

    # 8. 医疗器械 (2 xlsx)
    qx_dir = DATA_ROOT / "重庆医药集团医疗器械有限公司-医疗设备"
    if qx_dir.exists():
        files = sorted(qx_dir.glob("*.xlsx"))
        cases.append(CompanyCase("医疗器械", 2025, files))

    # 9. 陕西华氏 2024 (1 余额 + 12 月)
    sx24 = DATA_ROOT / "陕西华氏医药有限公司-需加工24和25年的AUD文件" / "2024"
    if sx24.exists():
        files = sorted(sx24.glob("*.xlsx"))
        cases.append(CompanyCase("陕西华氏 2024", 2024, files))

    # 10. 陕西华氏 2025
    sx25 = DATA_ROOT / "陕西华氏医药有限公司-需加工24和25年的AUD文件" / "2025"
    if sx25.exists():
        files = sorted(sx25.glob("*.xlsx"))
        cases.append(CompanyCase("陕西华氏 2025", 2025, files))

    return cases


async def run_case(case: CompanyCase) -> None:
    """对单个 CompanyCase 跑完整 pipeline + 验证数据库。"""
    import sqlalchemy as sa
    from app.core.database import async_session
    from app.models.audit_platform_models import (
        TbAuxBalance, TbAuxLedger, TbBalance, TbLedger,
    )
    from app.models.dataset_models import ImportJob, JobStatus
    from app.services.ledger_import.pipeline import execute_pipeline

    pid = case.project_id
    yr = case.year

    # Step 0: 确保 Project 存在（首次批量测试需预建）
    # 用 raw SQL 避免触发 Project ORM 关系映射（需全量 model import）
    async with async_session() as db:
        r = await db.execute(
            sa.text("SELECT 1 FROM projects WHERE id = :pid"),
            {"pid": str(pid)},
        )
        if r.first() is None:
            await db.execute(sa.text("""
                INSERT INTO projects (id, name, client_name, status, version, consol_level, is_deleted)
                VALUES (:pid, :name, :client, 'created', 1, 1, false)
            """), {
                "pid": str(pid),
                "name": f"[批量测试] {case.name} {case.year}",
                "client": case.name,
            })
            await db.commit()

    # Step 1: 清理历史数据（避免重复跑污染）
    async with async_session() as db:
        for model in (TbBalance, TbLedger, TbAuxBalance, TbAuxLedger):
            tbl = model.__table__
            await db.execute(
                sa.delete(tbl).where(
                    tbl.c.project_id == pid,
                    tbl.c.year == yr,
                )
            )
        await db.commit()

    # Step 2: 预创建 ImportJob（外键约束要求）
    job_id = uuid4()
    async with async_session() as db:
        db.add(ImportJob(
            id=job_id,
            project_id=pid,
            year=yr,
            status=JobStatus.running,
            options={"batch_test": True, "company": case.name},
        ))
        await db.commit()

    # Step 3: 跑 pipeline
    file_sources = [(f.name, f) for f in case.files]

    async def noop_progress(_pct: int, _msg: str):
        pass

    async def no_cancel() -> bool:
        return False

    try:
        result = await execute_pipeline(
            job_id=job_id,
            project_id=pid,
            year=yr,
            custom_mapping=None,
            created_by=None,
            file_sources=file_sources,
            force_activate=False,
            progress_cb=noop_progress,
            cancel_check=no_cancel,
        )
        case.balance_rows = result.balance_rows
        case.aux_balance_rows = result.aux_balance_rows
        case.ledger_rows = result.ledger_rows
        case.aux_ledger_rows = result.aux_ledger_rows
        if result.success:
            case.status = "success"
        else:
            case.status = "partial"
            case.error = f"blocking={result.blocking_findings}"
    except Exception as exc:
        case.status = "failed"
        case.error = f"{type(exc).__name__}: {str(exc)[:200]}"
        return

    # Step 4: 查维度 TOP 5
    async with async_session() as db:
        r = await db.execute(sa.text("""
            SELECT aux_type, COUNT(*) AS cnt
            FROM tb_aux_ledger
            WHERE project_id = :pid AND year = :yr AND is_deleted = false
            GROUP BY aux_type ORDER BY cnt DESC LIMIT 5
        """), {"pid": str(pid), "yr": yr})
        tops = [f"{row.aux_type}({row.cnt})" for row in r.all() if row.aux_type]
        case.aux_top5 = " / ".join(tops) if tops else "无"


async def main():
    cases = build_cases()

    # 可选：跳过耗时大的用例（默认跑全部）
    if "--skip-slow" in sys.argv:
        cases = [c for c in cases if c.name not in ("陕西华氏 2024", "陕西华氏 2025")]
        print("[skip-slow] 已跳过陕西华氏 2024/2025")

    # 可选：只跑指定家
    only_names = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    if only_names:
        cases = [c for c in cases if any(n in c.name for n in only_names)]
        print(f"[filter] 只跑: {[c.name for c in cases]}")

    # 按文件总大小从小到大排序（快的先跑，便于快速暴露问题）
    def total_size(c: CompanyCase) -> int:
        return sum(f.stat().st_size for f in c.files if f.exists())
    cases.sort(key=total_size)

    print(f"\n==== 将测试 {len(cases)} 家企业-年度 ====")
    for c in cases:
        print(f"  - {c.name} ({c.year}) : {len(c.files)} 文件")
    print()

    for i, case in enumerate(cases, 1):
        import time
        t0 = time.time()
        print(f"\n[{i}/{len(cases)}] 运行 {case.name} ({case.year}) ...", flush=True)
        try:
            await asyncio.wait_for(run_case(case), timeout=3600)  # 单 case 1 小时
        except asyncio.TimeoutError:
            case.status = "failed"
            case.error = "timeout: 超过 20 分钟"
        except Exception as exc:
            case.status = "failed"
            case.error = f"outer: {type(exc).__name__}: {str(exc)[:200]}"

        elapsed = time.time() - t0
        print(f"  [耗时 {elapsed:.0f}s] 状态={case.status} | "
              f"balance={case.balance_rows} "
              f"aux_balance={case.aux_balance_rows} "
              f"ledger={case.ledger_rows} "
              f"aux_ledger={case.aux_ledger_rows}", flush=True)
        if case.aux_top5:
            print(f"  维度 TOP 5: {case.aux_top5}", flush=True)
        if case.error:
            print(f"  ERROR: {case.error}", flush=True)

    # 汇总表格
    print("\n\n" + "=" * 100)
    print("汇总结果")
    print("=" * 100)
    print(f"{'企业':<20} {'年度':<6} {'状态':<10} {'balance':>8} {'aux_bal':>8} "
          f"{'ledger':>8} {'aux_ledg':>8}")
    print("-" * 100)
    success = 0
    for case in cases:
        print(f"{case.name:<20} {case.year:<6} {case.status:<10} "
              f"{case.balance_rows:>8} {case.aux_balance_rows:>8} "
              f"{case.ledger_rows:>8} {case.aux_ledger_rows:>8}")
        if case.status == "success":
            success += 1
    print("-" * 100)
    print(f"通过率: {success}/{len(cases)} = {success/len(cases)*100:.0f}%")
    return 0 if success == len(cases) else 1


if __name__ == "__main__":
    # 让 stdout 实时 flush（PowerShell 管道/重定向有缓冲问题）
    import os
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(line_buffering=True, encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(asyncio.run(main()))
