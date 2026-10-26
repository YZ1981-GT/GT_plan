"""存量底稿文件梳理报告（spec procedure-chain-hardening-and-java-contracts R14）。

仓库根执行（默认 dry-run：只读，输出分类计数 JSON）::

    .venv\\Scripts\\python.exe backend/scripts/fix/report_workpaper_file_backlog.py [--project-id <id>] [--out report.json]
    .venv\\Scripts\\python.exe backend/scripts/fix/report_workpaper_file_backlog.py --project-id <id> --apply --confirm

分类：本底稿自己的文件 / 没有文件路径 / 旧占位路径 / 指向共享模板目录 / 文件缺失（只报告）/ 路径越界（只报告）。
``--apply --confirm --project-id``（须用户放行，一次一个项目）：先把要处理的底稿原 ``file_path`` 备份到 ``--backup-dir``，再一个事务处理
「没有文件路径 / 旧占位路径 / 指向共享模板目录」三类（本底稿存储位置已有文件只回写路径，否则落文件），
条件更新、期间被改过的不覆盖。核心逻辑见 ``app/services/workpaper_file_backlog.py``。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
DEFAULT_BACKUP_DIR = BACKEND / "backups"


async def run(args: argparse.Namespace) -> dict:
    from app.core.database import async_session
    from app.services import workpaper_file_backlog as backlog
    from app.services.wp_code_override_loader import load_wp_code_overrides
    from app.services.wp_generate_file import load_generation_scenario

    skip_codes = frozenset(code for code, ct in load_wp_code_overrides().items() if ct == "skip")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    async with async_session() as db:
        rows = await backlog.scan_backlog(db, args.project_id)
        report = {"mode": "apply" if args.apply else "dry-run", "stamp": stamp,
                  "project_id": str(args.project_id) if args.project_id else None,
                  **backlog.summarize(rows, skip_codes=skip_codes)}
        await db.rollback()
        if not args.apply:
            return report
        todo = [r for r in rows if r.category in backlog.FIXABLE]
        backup = args.backup_dir / f"workpaper_file_backlog_{stamp}.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(json.dumps([{"wp_id": str(r.wp_id), "project_id": str(r.project_id), "wp_code": r.wp_code,
                                       "category": r.category, "file_path": r.file_path} for r in todo],
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        report["backup"] = str(backup)
        applied: dict[str, dict] = {}
        for pid in sorted({r.project_id for r in todo}, key=str):
            async def _scenario(project_id, _db=db):
                return await load_generation_scenario(_db, project_id)

            applied[str(pid)] = await backlog.apply_backlog(
                db, [r for r in todo if r.project_id == pid], scenario_of=_scenario)
            await db.commit()
        report["applied"] = applied
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="存量底稿文件梳理报告（默认 dry-run，只读）")
    parser.add_argument("--project-id", type=uuid.UUID, help="只看一个项目（缺省全部项目）")
    parser.add_argument("--out", type=Path, help="报告 JSON 另存到文件")
    parser.add_argument("--apply", action="store_true", help="处理可处理的三类（须同时带 --confirm）")
    parser.add_argument("--confirm", action="store_true", help="确认写库（真库写入须用户放行）")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    args = parser.parse_args()
    if args.apply and not args.confirm:
        parser.error("--apply 须同时带 --confirm（真库写入，须用户放行）")
    if args.apply and args.project_id is None:
        parser.error("--apply 须指定 --project-id（一次只处理一个项目，缩小误操作范围）")
    os.chdir(BACKEND)  # 相对路径按后端服务同一工作目录解析
    report = asyncio.run(run(args))
    text = json.dumps(report, ensure_ascii=False, indent=1, default=str)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
