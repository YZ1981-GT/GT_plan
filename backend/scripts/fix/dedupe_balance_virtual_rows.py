"""清理 tb_balance 里「同科目既有真实汇总行、又有辅助聚合虚拟行」的重复行。

成因：导入管线按 sheet 分别转换并写入主表；「辅助余额表」sheet 会为同一科目再聚合出一条
``raw_extra._aggregated_from_aux`` 虚拟汇总行，与「科目余额表」sheet 的真实行并存，
导致科目余额表出现重复行、下游 SUM 翻倍。管线已改为跨 sheet 去重（真实行优先），
本脚本只处理修复前已落库的存量。

只删「虚拟行」且同 (project, year, dataset, company, account_code) 下确有真实行的组合；
没有真实行的虚拟行（仅有辅助明细的科目）保留。

用法：
  python backend/scripts/fix/dedupe_balance_virtual_rows.py                    # 只预演（默认）
  python backend/scripts/fix/dedupe_balance_virtual_rows.py --project <uuid>
  python backend/scripts/fix/dedupe_balance_virtual_rows.py --apply --confirm
备份：``--apply`` 前把要删的行整行写到 ``backend/backups/balance_virtual_dups_<时间戳>.json``。
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

_SELECT = """
SELECT v.id, v.project_id, v.year, v.dataset_id, v.company_code, v.account_code
FROM tb_balance v
WHERE coalesce((v.raw_extra->>'_aggregated_from_aux')::bool, false) = true
  AND EXISTS (
    SELECT 1 FROM tb_balance r
    WHERE r.project_id = v.project_id AND r.year = v.year
      AND r.dataset_id IS NOT DISTINCT FROM v.dataset_id
      AND r.company_code = v.company_code AND r.account_code = v.account_code
      AND r.id <> v.id
      AND coalesce((r.raw_extra->>'_aggregated_from_aux')::bool, false) = false
  )
  {project_filter}
"""


async def _run(project: str | None, apply: bool) -> int:
    from app.core.database import async_session

    flt = "AND v.project_id = :pid" if project else ""
    params = {"pid": project} if project else {}
    sql = _SELECT.format(project_filter=flt)

    async with async_session() as db:
        rows = (await db.execute(sa.text(sql), params)).mappings().all()
        by_proj: dict[str, int] = {}
        for r in rows:
            by_proj[str(r["project_id"])] = by_proj.get(str(r["project_id"]), 0) + 1
        print(f"待清理的重复虚拟行 {len(rows)} 条，涉及项目 {len(by_proj)} 个")
        for pid, n in by_proj.items():
            print(f"  {pid}: {n} 条")
        if not rows:
            return 0
        if not apply:
            print("\n[DRY RUN] 没有改任何数据。确认后加 --apply --confirm 执行。")
            return 0

        ids = [str(r["id"]) for r in rows]
        full = (await db.execute(
            sa.text("SELECT row_to_json(t) AS j FROM tb_balance t WHERE t.id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": ids},
        )).all()
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        path = BACKUP_DIR / f"balance_virtual_dups_{datetime.now():%Y%m%d_%H%M%S}.json"
        path.write_text(json.dumps([x[0] for x in full], ensure_ascii=False, default=str), encoding="utf-8")
        print(f"已备份 {len(full)} 行 → {path}")

        res = await db.execute(
            sa.text("DELETE FROM tb_balance WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": ids},
        )
        await db.commit()
        print(f"已删除 {res.rowcount} 行")
    from app.services.ledger_cache_invalidate import invalidate_ledger_caches

    cleared = sum([await invalidate_ledger_caches(pid) for pid in by_proj])
    print(f"已清理账簿缓存键 {cleared} 个")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="只处理指定项目 UUID")
    ap.add_argument("--apply", action="store_true", help="真的删除（需同时加 --confirm）")
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args()
    if a.apply and not a.confirm:
        print("--apply 必须同时加 --confirm")
        return 2
    return asyncio.run(_run(a.project, a.apply))


if __name__ == "__main__":
    raise SystemExit(main())
