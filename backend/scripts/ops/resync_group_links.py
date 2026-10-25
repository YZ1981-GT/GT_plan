"""按三码重算项目派生链接 parent_project_id（spec consol-tree-three-code-autobuild 任务 6.4 / 需求 7.6）。

``parent_project_id`` 是派生值（ADR-CTREE-001）：由同年度各项目的企业代码、上级代码、最终控制方代码
与「与上级关系」推导。正常写路径都会自动重算；本工具用于存量数据一次性更正与排查。

用法（cwd=backend）：
    python scripts/ops/resync_group_links.py                # 全部审计年度逐年重算并提交
    python scripts/ops/resync_group_links.py --year 2025    # 只算一个年度
    python scripts/ops/resync_group_links.py --dry-run      # 只列出将更正的项目，不落库

输出每个年度将更正（或已更正）的项目：名称、报表类型、旧链接 → 新链接。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import pkgutil
import sys
from pathlib import Path
from uuid import UUID

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import sqlalchemy as sa  # noqa: E402

import app.models  # noqa: E402
from app.core.database import async_session  # noqa: E402
from app.models.core import Project  # noqa: E402
from app.services.consol_group_tree import derive_parent_links, load_year_records  # noqa: E402
from app.services.group_links import sync_group_links  # noqa: E402

# 与应用启动一致：导入全部模型子模块（外键目标表要在 metadata 里）
for _m in pkgutil.walk_packages(app.models.__path__, "app.models."):
    importlib.import_module(_m.name)


def _label(names: dict[UUID, str], pid: UUID | None) -> str:
    if pid is None:
        return "（无）"
    return names.get(pid, str(pid))


async def _years(db) -> list[int]:
    rows = await db.execute(
        sa.select(Project.audit_year)
        .where(Project.is_deleted == sa.false(), Project.audit_year.isnot(None))
        .distinct()
    )
    return sorted(int(r[0]) for r in rows.all())


async def run(year: int | None, dry_run: bool) -> int:
    out = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)
    total = 0
    async with async_session() as db:
        years = [year] if year is not None else await _years(db)
        for y in years:
            records = await load_year_records(db, y)
            links = derive_parent_links(records, y)
            names = {r.id: f"{r.client_name}（{'合并' if r.report_scope == 'consolidated' else '单户'}）" for r in records}
            changes = [(r, links.get(r.id)) for r in records if links.get(r.id) != r.parent_project_id]
            out.write(f"{y} 年度：项目 {len(records)} 个，需更正链接 {len(changes)} 个\n")
            for rec, new in sorted(changes, key=lambda c: names[c[0].id]):
                out.write(f"  {names[rec.id]}：{_label(names, rec.parent_project_id)} → {_label(names, new)}\n")
            total += len(changes)
            if changes and not dry_run:
                await sync_group_links(db, y)
        if dry_run:
            await db.rollback()
            out.write(f"试运行：共 {total} 个项目需更正，未落库\n")
        else:
            await db.commit()
            out.write(f"已提交：共更正 {total} 个项目\n")
    out.flush()
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="按三码重算项目派生链接 parent_project_id")
    parser.add_argument("--year", type=int, default=None, help="只重算该审计年度（默认全部年度）")
    parser.add_argument("--dry-run", action="store_true", help="只列出将更正的项目，不落库")
    args = parser.parse_args()
    asyncio.run(run(args.year, args.dry_run))


if __name__ == "__main__":
    main()
