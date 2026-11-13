"""清理 tb_ledger 中由「辅助明细账 sheet」镜像写入的重复分录行。

成因：导入管线对序时账 sheet 与辅助明细账 sheet 都往主表 tb_ledger 写行；辅助明细账 sheet 转出的
主表行（raw_extra 为 SQL NULL，而序时账 sheet 的行经 JSON 序列化后是 JSON null）与序时账 sheet 的行
重复，序时账查询、合计、凭证穿透都会看到同一分录两份。管线已改为「已有序时账 sheet 时辅助明细 sheet 只写
辅助表」，本脚本只处理修复前落库的存量。

只删满足全部条件的行（保守）：
  1. raw_extra IS NULL；
  2. 同数据集下存在 raw_extra IS NOT NULL 的同分录行（日期/凭证号/科目/借/贷/摘要/公司一致）；
  3. 同数据集的 tb_aux_ledger 里也有这条分录（确认它确实是辅助明细 sheet 的镜像）。

用法：
  python backend/scripts/fix/dedupe_ledger_aux_mirror_rows.py --project <uuid>            # 只预演
  python backend/scripts/fix/dedupe_ledger_aux_mirror_rows.py --all                       # 全库逐项目预演
  python backend/scripts/fix/dedupe_ledger_aux_mirror_rows.py --project <uuid> --apply --confirm
  python backend/scripts/fix/dedupe_ledger_aux_mirror_rows.py --all --apply --confirm
备份：``--apply`` 前整行写到 ``backend/backups/ledger_aux_mirror_<时间戳>.json``。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa  # noqa: E402

BACKUP_DIR = ROOT / "backups"

_KEY = """
    {a}.dataset_id IS NOT DISTINCT FROM {b}.dataset_id
    AND {a}.voucher_date IS NOT DISTINCT FROM {b}.voucher_date
    AND {a}.voucher_no IS NOT DISTINCT FROM {b}.voucher_no
    AND {a}.account_code = {b}.account_code
    AND {a}.company_code IS NOT DISTINCT FROM {b}.company_code
    AND coalesce({a}.debit_amount, 0) = coalesce({b}.debit_amount, 0)
    AND coalesce({a}.credit_amount, 0) = coalesce({b}.credit_amount, 0)
    AND coalesce({a}.summary, '') = coalesce({b}.summary, '')
"""

_SELECT = f"""
SELECT m.id
FROM tb_ledger m
WHERE m.project_id = :pid AND m.raw_extra IS NULL AND m.is_deleted = false
  AND EXISTS (SELECT 1 FROM tb_ledger r WHERE r.project_id = m.project_id AND r.is_deleted = false
              AND r.raw_extra IS NOT NULL AND r.id <> m.id AND {_KEY.format(a="r", b="m")})
  AND EXISTS (SELECT 1 FROM tb_aux_ledger x WHERE x.project_id = m.project_id AND x.is_deleted = false
              AND {_KEY.format(a="x", b="m")})
"""


async def _all_projects() -> list[str]:
    """有辅助明细账行的项目（只有这些项目才可能存在镜像行）。"""
    from app.core.database import async_session

    async with async_session() as db:
        rows = await db.execute(sa.text(
            "SELECT DISTINCT project_id FROM tb_aux_ledger WHERE is_deleted = false"))
        return [str(r[0]) for r in rows.all()]


async def _run_many(projects: list[str], apply: bool) -> int:
    print(f"待检查项目 {len(projects)} 个")
    for pid in projects:
        await _run(pid, apply)
    return 0


async def _run(project: str, apply: bool) -> int:
    from app.core.database import async_session
    from app.services.ledger_cache_invalidate import invalidate_ledger_caches

    async with async_session() as db:
        # 容器 /dev/shm 默认只有 64MB，并行 hash 半连接会 DiskFullError；本事务内关闭并行
        await db.execute(sa.text("SET LOCAL max_parallel_workers_per_gather = 0"))
        ids = [str(r[0]) for r in (await db.execute(sa.text(_SELECT), {"pid": project})).all()]
        total = (await db.execute(
            sa.text("SELECT count(*) FROM tb_ledger WHERE project_id = :pid AND is_deleted = false"),
            {"pid": project},
        )).scalar()
        print(f"项目 {project}：tb_ledger 共 {total} 行，待清理镜像行 {len(ids)} 条，清理后剩 {total - len(ids)} 行")
        if not ids or not apply:
            if ids:
                print("[DRY RUN] 没有改任何数据。确认后加 --apply --confirm 执行。")
            return 0

        full = (await db.execute(
            sa.text("SELECT row_to_json(t) FROM tb_ledger t WHERE t.id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": ids},
        )).all()
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        path = BACKUP_DIR / f"ledger_aux_mirror_{datetime.now():%Y%m%d_%H%M%S}.json"
        path.write_text(json.dumps([x[0] for x in full], ensure_ascii=False, default=str), encoding="utf-8")
        print(f"已备份 {len(full)} 行 → {path}")
        res = await db.execute(
            sa.text("DELETE FROM tb_ledger WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": ids},
        )
        await db.commit()
        print(f"已删除 {res.rowcount} 行；清理缓存键 {await invalidate_ledger_caches(project)} 个")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="项目 UUID")
    ap.add_argument("--all", action="store_true", help="全库逐项目处理")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args()
    if bool(a.project) == bool(a.all):
        print("--project 与 --all 二选一")
        return 2
    if a.apply and not a.confirm:
        print("--apply 必须同时加 --confirm")
        return 2

    async def _main() -> int:
        return await _run_many(await _all_projects() if a.all else [a.project], a.apply)

    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
