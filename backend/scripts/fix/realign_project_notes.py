"""存量项目附注按现行种子对齐（spec disclosure-note-template-word-realignment Phase 3，design §4）。

仓库根执行（默认 dry-run：只读、事务回滚）::

    .venv\\Scripts\\python.exe backend/scripts/fix/realign_project_notes.py --all-targets
    .venv\\Scripts\\python.exe backend/scripts/fix/realign_project_notes.py --project <id> --apply
    .venv\\Scripts\\python.exe backend/scripts/fix/realign_project_notes.py --restore backend/backups/note_realign_x.json

``--apply``：每个项目每个年度一个事务 —— 锁行 → 备份到 ``--backup-dir`` → 执行 → 重算计划须为空 → 已有行正文 /
表格哈希逐行不变，任一不满足即回滚该项目。``--restore`` 按备份原样恢复（同样一个事务、恢复后逐字核对）。
完整报告（含每条动作与待人工项）写 ``--report``（默认 ``backend/backups/``，该目录不入库）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

#: 本 spec 的存量修复目标（和平药房 2aa00f57 走 Phase 6 重建，不在此列）
TARGETS: dict[str, str] = {
    "94a40b23-21a2-4d7a-a38d-9fd059d57717": "【测试】附注批量甲",
    "989cebf5-c53e-4643-a5b4-e4eef6d04c6d": "【测试】附注批量乙",
    "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49": "重药控股安徽",
    "52c04ed1-efcf-4b7c-9800-ce5a5e840d8d": "重庆医药集团医疗器械",
    "a7fc75e5-b67f-436d-a126-42423018b6ce": "陕西华氏医药",
    "c8621493-70aa-46a9-8285-e0674e4e1418": "宜宾新健康大药房临港店",
    "df5b8403-abbb-48af-b6a4-6fd44dfae5c9": "首汽租车（合并）",
}
DEFAULT_DIR = BACKEND / "backups"


async def _years(session_factory, project_id: uuid.UUID) -> list[int]:
    import sqlalchemy as sa

    async with session_factory() as db:
        return sorted((await db.execute(sa.text(
            "SELECT DISTINCT year FROM disclosure_notes WHERE project_id = :p"), {"p": project_id})).scalars().all())


async def _run_one(session_factory, project_id: uuid.UUID, year: int, *, apply: bool, backup_dir: Path,
                   stamp: str) -> dict:
    from app.services.note_project_realign_apply import RealignError, RealignSkipped, realign_project

    backup = backup_dir / f"note_realign_{project_id}_{year}_{stamp}.json" if apply else None
    async with session_factory() as db:
        try:
            report = await realign_project(db, project_id, year, apply=apply, backup_path=backup)
        except RealignSkipped as err:
            await db.rollback()
            return {"project_id": str(project_id), "year": year, "skipped": str(err)}
        except RealignError as err:
            await db.rollback()
            return {"project_id": str(project_id), "year": year, "error": str(err)}
        if apply:
            await db.commit()
        else:
            await db.rollback()
    report["applied"] = apply and "after" in report
    return report


def _summary(report: dict) -> str:
    name = TARGETS.get(report["project_id"], report["project_id"])
    if "skipped" in report:
        return f"- {name} {report['year']}：跳过（{report['skipped']}）"
    if "error" in report:
        return f"✗ {name} {report['year']}：{report['error']}"
    counts = report["plan"]["counts"]
    acts = {k: v for k, v in counts.items() if v}
    tail = f"；执行后 {report['after']}" if report.get("after") is not None else ""
    return (f"{'✓' if report.get('applied') else '·'} {name} {report['year']}（{report['template_type']}/"
            f"{report['report_scope']}，行 {report['active_rows']}/{report['rows']}，模板 {report['templates']}）"
            f"：{acts or '无差异'}{tail}")


async def main() -> int:
    parser = argparse.ArgumentParser(description="存量项目附注按现行种子对齐（默认 dry-run）")
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--project", action="append", help="项目 id（可多次）")
    who.add_argument("--all-targets", action="store_true", help="本 spec 的 7 个存量目标项目")
    who.add_argument("--restore", type=Path, help="按备份文件恢复")
    parser.add_argument("--year", type=int, help="只处理该年度（默认该项目有附注的全部年度）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="只出计划（默认）")
    mode.add_argument("--apply", action="store_true", help="备份后执行")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--report", type=Path, help="完整报告 JSON 路径")
    args = parser.parse_args()

    from app.core.database import async_session

    if args.restore:
        from app.services.note_project_realign_apply import restore_backup

        async with async_session() as db:
            result = await restore_backup(db, args.restore)
            await db.commit()
        print(f"已恢复：{result}")
        return 0

    ids = list(TARGETS) if args.all_targets else args.project
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports = []
    for pid_text in ids:
        pid = uuid.UUID(pid_text)
        for year in ([args.year] if args.year else await _years(async_session, pid)):
            report = await _run_one(async_session, pid, year, apply=args.apply, backup_dir=args.backup_dir,
                                    stamp=stamp)
            reports.append(report)
            print(_summary(report))
    out = args.report or args.backup_dir / f"note_realign_report_{'apply' if args.apply else 'dry'}_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reports, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"报告：{out}")
    return 1 if any("error" in r for r in reports) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
