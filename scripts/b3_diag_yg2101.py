"""B3 深度诊断：本进程直接跑 execute_pipeline(YG2101)，拿 perf 打点日志。

用法：python scripts/b3_diag_yg2101.py
目的：找出 434s 中那神秘 140s 到底花在哪。
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# 启用 INFO 日志到 stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
# 抑制噪声
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)


async def main() -> int:
    from app.core.config import settings
    from app.services.ledger_import.pipeline import execute_pipeline

    sample_path = ROOT / "数据/YG2101-重庆医药集团四川医药有限公司2025年-科目余额表+序时账.xlsx"
    assert sample_path.exists(), f"样本不存在：{sample_path}"

    # 找一个已存在的 project（不走 API）
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        row = (await db.execute(
            sa.text("SELECT id FROM projects WHERE client_name LIKE 'B2Perf-YG2101%' LIMIT 1")
        )).first()
        if row:
            project_id = row.id
            print(f"复用 project {project_id}")
        else:
            row = (await db.execute(sa.text("SELECT id FROM projects LIMIT 1"))).first()
            project_id = row.id
            print(f"借用 project {project_id}")

        year = 2099  # 避免与真实年度冲突
        # 清理旧数据
        for tbl in ("tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"):
            await db.execute(
                sa.text(f"DELETE FROM {tbl} WHERE project_id=:p AND year=:y"),
                {"p": project_id, "y": year},
            )
        await db.execute(
            sa.text("DELETE FROM ledger_datasets WHERE project_id=:p AND year=:y"),
            {"p": project_id, "y": year},
        )
        await db.commit()

        # 先建一个 ImportJob 让 ledger_datasets FK 通过
        job_id = uuid.uuid4()
        await db.execute(sa.text("""
            INSERT INTO import_jobs (id, project_id, year, status, created_at, version, retry_count, max_retries)
            VALUES (:id, :p, :y, 'running', now(), 1, 0, 3)
        """), {"id": job_id, "p": project_id, "y": year})
        await db.commit()
    await engine.dispose()

    async def _progress(pct, msg):
        pass  # 不打印避免混淆日志

    async def _cancel():
        return False

    t_start = time.time()
    print(f"\n=== 开始 execute_pipeline for YG2101 ({sample_path.stat().st_size/1e6:.1f}MB) ===")

    result = await execute_pipeline(
        job_id=job_id,
        project_id=project_id,
        year=year,
        custom_mapping=None,
        created_by=None,
        file_sources=[(sample_path.name, sample_path)],
        force_activate=True,  # 跳过校验 blocking，只关心性能
        progress_cb=_progress,
        cancel_check=_cancel,
    )

    elapsed = time.time() - t_start
    print(f"\n=== 完成 ===")
    print(f"总耗时: {elapsed:.1f}s")
    print(f"结果: success={result.success} balance={result.balance_rows} "
          f"aux_balance={result.aux_balance_rows} ledger={result.ledger_rows} "
          f"aux_ledger={result.aux_ledger_rows}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(asyncio.run(main()))
