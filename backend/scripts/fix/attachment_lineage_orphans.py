#!/usr/bin/env python
"""附件溯源 ``attachment_lineage`` 的孤儿与未回填行：默认只读逐行列出，``--apply`` 先备份再修复。

spec formula-hub-integrity-closure（需求 7.1，ADR-FHIC-13，D9）。迁移 V227 给 ``attachment_lineage`` 加了可空列
``project_id`` 并按 ``attachments.project_id`` 回填；查询只认本项目的 ``project_id``，下面两类行对任何项目都不可见：

- 孤儿：附件已不存在。回收站的永久删除、批量删除、清空回收站与项目级联删除会物理删除 ``attachments`` 行，
  ``attachment_lineage`` 没有外键，关联行留了下来。回填之后才被删的附件，其孤儿行 ``project_id`` 可能不为空。
- 未回填：附件存在而 ``project_id`` 为空（迁移之后、新代码上线之前由旧代码写入）。

用法（目标库 = ``settings.DATABASE_URL``，与应用同一来源，输出第一行打印库名）::

    python backend/scripts/fix/attachment_lineage_orphans.py                    # 只读，逐行列出
    python backend/scripts/fix/attachment_lineage_orphans.py --json out.json    # 另存完整报告
    python backend/scripts/fix/attachment_lineage_orphans.py --apply            # 备份后回填 / 删孤儿

``--apply`` 在一个事务里：锁定待处理行（``FOR UPDATE``）→ 把这些行的原文（``row_to_json``）写入
``backend/backups/attachment_lineage_orphans_<时间>.json``（写完并落盘才继续，写失败整次不改）→ 回填可归属的行 →
删除孤儿 → 提交。可重复执行：第二次待处理 0 行、不再写备份。

退出码：0 完成；1 修复失败（已回滚）；2 库不是 PostgreSQL 或 ``project_id`` 列未就绪（先执行迁移 V227）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.services.attachment_lineage_schema import (  # noqa: E402
    MIGRATION_VERSION,
    lineage_project_column_ready,
)

TOOL = "attachment_lineage_orphans"
REASON_ORPHAN = "孤儿"
REASON_UNFILLED = "未回填"
DEFAULT_BACKUP_DIR = _BACKEND_ROOT / "backups"

_SCAN_SQL = """
SELECT al.id AS lineage_id,
       al.attachment_id,
       al.project_id,
       al.target_type,
       al.target_ref,
       a.id IS NULL AS orphan,
       row_to_json(al)::text AS original
  FROM attachment_lineage al
  LEFT JOIN attachments a ON a.id = al.attachment_id
 WHERE a.id IS NULL OR al.project_id IS NULL
 ORDER BY al.created_at, al.id
"""
_BACKFILL_SQL = text(
    "UPDATE attachment_lineage al SET project_id = a.project_id FROM attachments a "
    "WHERE a.id = al.attachment_id AND al.project_id IS NULL AND al.id = ANY(:ids)"
)
_DELETE_ORPHANS_SQL = text(
    "DELETE FROM attachment_lineage al WHERE al.id = ANY(:ids) "
    "AND NOT EXISTS (SELECT 1 FROM attachments a WHERE a.id = al.attachment_id)"
)


class ColumnNotReady(RuntimeError):
    """``attachment_lineage.project_id`` 列不存在：先执行迁移 V227。"""


class RepairMismatch(RuntimeError):
    """实际改动行数与锁定时列出的不一致（调用方回滚）。"""


@dataclass(frozen=True)
class LineageProblem:
    lineage_id: uuid.UUID
    attachment_id: uuid.UUID
    reason: str
    project_id: uuid.UUID | None
    target_type: str
    target_ref: str | None
    original: dict[str, Any]

    def as_row(self) -> dict[str, Any]:
        return {
            "lineage_id": str(self.lineage_id),
            "attachment_id": str(self.attachment_id),
            "reason": self.reason,
            "project_id": str(self.project_id) if self.project_id else None,
            "target_type": self.target_type,
            "target_ref": self.target_ref,
        }


async def require_column(db: Any) -> None:
    if not await lineage_project_column_ready(db):
        raise ColumnNotReady(f"attachment_lineage.project_id 列不存在：先执行迁移 {MIGRATION_VERSION}")


async def scan(db: Any, *, lock: bool = False) -> list[LineageProblem]:
    """孤儿（附件不存在）与未回填（附件存在、project_id 为空）的行；``lock`` ⇒ 锁定这些行。"""
    sql = _SCAN_SQL + (" FOR UPDATE OF al" if lock else "")
    rows = (await db.execute(text(sql))).mappings().all()
    return [
        LineageProblem(
            lineage_id=row["lineage_id"],
            attachment_id=row["attachment_id"],
            reason=REASON_ORPHAN if row["orphan"] else REASON_UNFILLED,
            project_id=row["project_id"],
            target_type=row["target_type"],
            target_ref=row["target_ref"],
            original=json.loads(row["original"]),
        )
        for row in rows
    ]


async def _total_rows(db: Any) -> int:
    return int((await db.execute(text("SELECT count(*) FROM attachment_lineage"))).scalar_one())


def _report(mode: str, database: str, total: int, problems: list[LineageProblem]) -> dict[str, Any]:
    return {
        "tool": TOOL,
        "mode": mode,
        "database": database,
        "migration": MIGRATION_VERSION,
        "total_rows": total,
        "pending": len(problems),
        "orphans": sum(1 for p in problems if p.reason == REASON_ORPHAN),
        "unfilled": sum(1 for p in problems if p.reason == REASON_UNFILLED),
        "rows": [p.as_row() for p in problems],
        "backup": None,
        "backfilled": 0,
        "deleted": 0,
    }


async def dry_run(db: Any, *, database: str) -> dict[str, Any]:
    """只读：列出待处理行，不加锁、不写入。"""
    await require_column(db)
    problems = await scan(db)
    return _report("dry-run", database, await _total_rows(db), problems)


def write_backup(problems: list[LineageProblem], backup_dir: Path, *, database: str, now: datetime) -> Path:
    """把待处理行的原文写入备份文件（独占新建 + 落盘），返回路径；失败即抛，调用方不得继续修改。"""
    backup_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "tool": TOOL,
        "created_at": now.isoformat(timespec="seconds"),
        "database": database,
        "migration": MIGRATION_VERSION,
        "rows": [{**p.as_row(), "original": p.original} for p in problems],
    }
    data = json.dumps(payload, ensure_ascii=False, indent=1)
    stamp = now.strftime("%Y%m%d_%H%M%S")
    for attempt in range(100):
        path = backup_dir / f"{TOOL}_{stamp}{'' if attempt == 0 else f'_{attempt}'}.json"
        try:
            with path.open("x", encoding="utf-8") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
        except FileExistsError:
            continue
        return path
    raise RuntimeError(f"备份文件名冲突：{backup_dir} 下 {TOOL}_{stamp}*.json 已有 100 个")


async def apply_repairs(
    db: Any, *, backup_dir: Path, database: str, now: datetime | None = None
) -> dict[str, Any]:
    """锁定 → 备份 → 回填 → 删孤儿（在调用方的事务里执行，提交 / 回滚由调用方负责）。"""
    await require_column(db)
    problems = await scan(db, lock=True)
    report = _report("apply", database, await _total_rows(db), problems)
    if not problems:
        return report
    path = write_backup(problems, backup_dir, database=database, now=now or datetime.now())
    unfilled = [p.lineage_id for p in problems if p.reason == REASON_UNFILLED]
    orphans = [p.lineage_id for p in problems if p.reason == REASON_ORPHAN]
    backfilled = (await db.execute(_BACKFILL_SQL, {"ids": unfilled})).rowcount if unfilled else 0
    deleted = (await db.execute(_DELETE_ORPHANS_SQL, {"ids": orphans})).rowcount if orphans else 0
    if (backfilled, deleted) != (len(unfilled), len(orphans)):
        raise RepairMismatch(
            f"回填 {backfilled}/{len(unfilled)} 行、删除 {deleted}/{len(orphans)} 行，与锁定时列出的不一致（备份 {path}）"
        )
    report.update(backup=str(path), backfilled=backfilled, deleted=deleted)
    return report


def _database_label(url: str) -> str:
    parsed = make_url(url)
    return f"{parsed.database}（{parsed.host}:{parsed.port or 5432}）"


async def _run(*, apply: bool, backup_dir: Path) -> tuple[int, dict[str, Any]]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    url = str(settings.DATABASE_URL)
    if make_url(url).get_backend_name() != "postgresql":
        return 2, {"tool": TOOL, "error": f"只支持 PostgreSQL：{make_url(url).get_backend_name()}"}
    database = _database_label(url)
    engine = create_async_engine(
        url, poolclass=NullPool, connect_args={"ssl": False} if settings.DB_DISABLE_SSL else {}
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            try:
                if apply:
                    report = await apply_repairs(session, backup_dir=backup_dir, database=database)
                    await session.commit()
                else:
                    report = await dry_run(session, database=database)
                    await session.rollback()
            except ColumnNotReady as exc:
                await session.rollback()
                return 2, {"tool": TOOL, "database": database, "error": str(exc)}
            except Exception as exc:  # noqa: BLE001 —— 修复失败整次回滚，原因进报告
                await session.rollback()
                return 1, {"tool": TOOL, "database": database, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await engine.dispose()
    return 0, report


def _print(code: int, report: dict[str, Any]) -> None:
    if "error" in report:
        print(f"[{TOOL}] 库 {report.get('database', '?')}：{report['error']}（退出码 {code}，未做任何修改）")
        return
    mode = "--apply（已提交）" if report["mode"] == "apply" else "只读（不写入）"
    print(f"[{TOOL}] 库 {report['database']}；模式 {mode}；project_id 列已就绪（{report['migration']}）")
    print(f"[{TOOL}] attachment_lineage 共 {report['total_rows']} 行；待处理 {report['pending']} 行"
          f"（{REASON_ORPHAN} {report['orphans']}、{REASON_UNFILLED} {report['unfilled']}）")
    for row in report["rows"]:
        print(f"[{TOOL}]   lineage_id={row['lineage_id']} attachment_id={row['attachment_id']} "
              f"原因={row['reason']} project_id={row['project_id']} "
              f"target={row['target_type']} {row['target_ref']}")
    if report["mode"] == "apply":
        print(f"[{TOOL}] 备份 {report['backup'] or '无（没有待处理行）'}；"
              f"回填 {report['backfilled']} 行、删除孤儿 {report['deleted']} 行")


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows 控制台默认 gbk，中文与 ✓ 类字符会抛
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="附件溯源孤儿 / 未回填行：默认只读列出，--apply 先备份再修复")
    parser.add_argument("--apply", action="store_true", help="锁定 → 备份 → 回填可归属的行 → 删除孤儿 → 提交")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR,
                        help=f"备份目录（默认 {DEFAULT_BACKUP_DIR}）")
    parser.add_argument("--json", type=Path, default=None, help="完整报告另存路径")
    args = parser.parse_args(argv)
    code, report = asyncio.run(_run(apply=bool(args.apply), backup_dir=args.backup_dir))
    if args.json is not None:
        args.json.write_text(json.dumps({**report, "exit_code": code}, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    _print(code, report)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
