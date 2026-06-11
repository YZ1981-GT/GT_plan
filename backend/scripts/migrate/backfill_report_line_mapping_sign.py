"""存量 report_line_mapping.mapping_sign 回填 — 备抵科目补 subtract。

背景：递减项(contra)机制(2026-06-10)新增 mapping_sign 列，但只在 ai_suggest_mappings
运行时赋值；已确认(is_confirmed)的存量映射 ai_suggest 会跳过(`if not force_refresh and
existing.is_confirmed: continue`)，导致存量备抵科目(累计折旧/摊销/各类减值/跌价/坏账/
折耗/库存股)的 mapping_sign 仍为默认 'add'，报表行次聚合时不会被减去 → 净值虚增。

本脚本按 direction_resolver 判定(名称命中备抵正则=contra_account)给存量映射回填
mapping_sign，幂等(已正确的跳过)，支持 --dry-run / --project 过滤。

科目名称取自 account_chart(优先) → trial_balance(兜底)。

用法(Windows，仓库根 cwd 用 .venv\\Scripts\\python.exe，backend cwd 用 ..\\.venv\\...)：
    python backend/scripts/migrate/backfill_report_line_mapping_sign.py --dry-run
    python backend/scripts/migrate/backfill_report_line_mapping_sign.py
    python backend/scripts/migrate/backfill_report_line_mapping_sign.py --project <uuid>
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import sqlalchemy as sa  # noqa: E402
from app.core.database import async_session  # noqa: E402
from app.services.ledger_import.direction_resolver import (  # noqa: E402
    resolve_account_direction,
)


async def _build_code_name_map(db, project_id: str) -> dict[str, str]:
    """科目编码→名称：account_chart 优先，trial_balance 兜底。"""
    name_map: dict[str, str] = {}
    # trial_balance 兜底（先填，后被 account_chart 覆盖）
    tb = await db.execute(sa.text(
        "SELECT DISTINCT standard_account_code, account_name FROM trial_balance "
        "WHERE project_id = :pid AND is_deleted = false "
        "  AND standard_account_code IS NOT NULL"
    ), {"pid": project_id})
    for code, name in tb.fetchall():
        if code and name:
            name_map[code] = name
    # account_chart 优先
    ac = await db.execute(sa.text(
        "SELECT account_code, account_name FROM account_chart "
        "WHERE project_id = :pid AND is_deleted = false"
    ), {"pid": project_id})
    for code, name in ac.fetchall():
        if code and name:
            name_map[code] = name
    return name_map


async def backfill(project_id: str | None, dry_run: bool) -> dict:
    stats = {"projects": 0, "rows_scanned": 0, "to_subtract": 0, "to_add": 0, "updated": 0}
    async with async_session() as db:
        # 待处理 project 列表
        if project_id:
            project_ids = [project_id]
        else:
            r = await db.execute(sa.text(
                "SELECT DISTINCT project_id FROM report_line_mapping WHERE is_deleted = false"
            ))
            project_ids = [str(row[0]) for row in r.fetchall()]

        for pid in project_ids:
            stats["projects"] += 1
            name_map = await _build_code_name_map(db, pid)

            rows = await db.execute(sa.text(
                "SELECT id, standard_account_code, mapping_sign "
                "FROM report_line_mapping "
                "WHERE project_id = :pid AND is_deleted = false"
            ), {"pid": pid})
            for rid, code, cur_sign in rows.fetchall():
                stats["rows_scanned"] += 1
                name = name_map.get(code, "")
                _dir, source = resolve_account_direction(code or "", name)
                want = "subtract" if source == "contra_account" else "add"
                if want == "subtract":
                    stats["to_subtract"] += 1
                else:
                    stats["to_add"] += 1
                # 幂等：仅当与现值不同才更新
                if want != (cur_sign or "add"):
                    if not dry_run:
                        await db.execute(sa.text(
                            "UPDATE report_line_mapping SET mapping_sign = :s, "
                            "updated_at = now() WHERE id = :id"
                        ), {"s": want, "id": str(rid)})
                    stats["updated"] += 1

        if not dry_run:
            await db.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="回填 report_line_mapping.mapping_sign 备抵减项")
    parser.add_argument("--project", default=None, help="仅处理指定 project_id")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = parser.parse_args()

    stats = asyncio.run(backfill(args.project, args.dry_run))
    mode = "DRY-RUN（未写库）" if args.dry_run else "已执行"
    print(f"=== mapping_sign 回填 [{mode}] ===")
    print(f"项目数: {stats['projects']}")
    print(f"扫描行: {stats['rows_scanned']}")
    print(f"判定 subtract: {stats['to_subtract']} / add: {stats['to_add']}")
    print(f"需更新(与现值不同): {stats['updated']}")


if __name__ == "__main__":
    main()
