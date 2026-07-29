"""存量 reference 关联回填权威链表（attachment_working_paper）。

spec: attachment-workpaper-linkage-convergence Task 2.3

扫描 ``attachments.reference_type='working_paper'`` 且 ``reference_id`` 非空的行，
幂等调用 ``ensure_wp_link`` 补入权威链表（已存在则跳过）。

用法：
  cd backend
  python -m scripts.backfill_attachment_wp_reference_links --dry-run    # 默认，只报计数
  python -m scripts.backfill_attachment_wp_reference_links --reconcile  # 对账缺口
  python -m scripts.backfill_attachment_wp_reference_links --apply      # 写库 + 备份表
  python -m scripts.backfill_attachment_wp_reference_links --rollback   # 按备份表删补入的链行

幂等：重跑 ``--apply`` 时已有链行跳过；备份表仅记录本轮新插入的 (attachment_id, wp_id)。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services.attachment_service import AttachmentService  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

BACKUP_TABLE = "bak_awp_reference_backfill_v1"

_CREATE_BACKUP = f"""
CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
    attachment_id UUID NOT NULL,
    wp_id UUID NOT NULL,
    backfilled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (attachment_id, wp_id)
)
"""

_CREATE_BACKUP_SQLITE = f"""
CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
    attachment_id TEXT NOT NULL,
    wp_id TEXT NOT NULL,
    backfilled_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (attachment_id, wp_id)
)
"""


def _dialect_name(db: AsyncSession) -> str:
    try:
        return db.get_bind().dialect.name
    except Exception:
        bind = getattr(db, "bind", None)
        if bind is not None:
            return bind.dialect.name
    return "postgresql"


async def _candidates(db: AsyncSession) -> list[tuple[UUID, UUID]]:
    from app.models.attachment_models import Attachment

    rows = (
        await db.execute(
            sa.select(Attachment.id, Attachment.reference_id).where(
                Attachment.reference_type == "working_paper",
                Attachment.reference_id.is_not(None),
                Attachment.is_deleted == sa.false(),
            )
        )
    ).all()
    out: list[tuple[UUID, UUID]] = []
    for att_id, wp_id in rows:
        if att_id is None or wp_id is None:
            continue
        out.append((UUID(str(att_id)), UUID(str(wp_id))))
    return out


async def _link_exists(db: AsyncSession, attachment_id: UUID, wp_id: UUID) -> bool:
    from app.models.attachment_models import AttachmentWorkingPaper

    cnt = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(AttachmentWorkingPaper)
            .where(
                AttachmentWorkingPaper.attachment_id == attachment_id,
                AttachmentWorkingPaper.wp_id == wp_id,
            )
        )
    ).scalar()
    return int(cnt or 0) > 0


async def run_dry(db: AsyncSession) -> dict[str, int]:
    cands = await _candidates(db)
    need = 0
    for att_id, wp_id in cands:
        if not await _link_exists(db, att_id, wp_id):
            need += 1
    return {"candidates": len(cands), "would_insert": need, "already_linked": len(cands) - need}


async def run_apply(db: AsyncSession) -> dict[str, int]:
    dialect = _dialect_name(db)
    await db.execute(sa.text(_CREATE_BACKUP_SQLITE if dialect == "sqlite" else _CREATE_BACKUP))

    svc = AttachmentService(db)
    cands = await _candidates(db)
    inserted = 0
    skipped = 0
    for att_id, wp_id in cands:
        if await _link_exists(db, att_id, wp_id):
            skipped += 1
            continue
        await svc.ensure_wp_link(att_id, wp_id, association_type="evidence", notes="backfill:reference")
        if dialect == "sqlite":
            await db.execute(
                sa.text(
                    f"INSERT OR IGNORE INTO {BACKUP_TABLE} (attachment_id, wp_id) VALUES (:a, :w)"
                ),
                {"a": str(att_id), "w": str(wp_id)},
            )
        else:
            await db.execute(
                sa.text(
                    f"INSERT INTO {BACKUP_TABLE} (attachment_id, wp_id) "
                    "VALUES (:a, :w) ON CONFLICT DO NOTHING"
                ),
                {"a": str(att_id), "w": str(wp_id)},
            )
        inserted += 1
    await db.commit()
    return {"candidates": len(cands), "inserted": inserted, "skipped": skipped}


async def run_rollback(db: AsyncSession) -> dict[str, int]:
    dialect = _dialect_name(db)
    if dialect == "sqlite":
        exists = (
            await db.execute(
                sa.text(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type='table' AND name=:t"
                ),
                {"t": BACKUP_TABLE},
            )
        ).scalar()
    else:
        exists = (
            await db.execute(
                sa.text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_name = :t"
                ),
                {"t": BACKUP_TABLE},
            )
        ).scalar()

    if not exists:
        logger.warning("备份表 %s 不存在，无回滚可做", BACKUP_TABLE)
        return {"deleted": 0}

    rows = (
        await db.execute(
            sa.text(f"SELECT attachment_id, wp_id FROM {BACKUP_TABLE}")
        )
    ).all()
    deleted = 0
    from app.models.attachment_models import AttachmentWorkingPaper

    for att_id, wp_id in rows:
        res = await db.execute(
            sa.delete(AttachmentWorkingPaper).where(
                AttachmentWorkingPaper.attachment_id == UUID(str(att_id)),
                AttachmentWorkingPaper.wp_id == UUID(str(wp_id)),
            )
        )
        deleted += res.rowcount or 0
    await db.execute(sa.text(f"DELETE FROM {BACKUP_TABLE}"))
    await db.commit()
    return {"deleted": deleted, "backup_rows": len(rows)}


async def run_reconcile(db: AsyncSession) -> dict[str, int | float]:
    """对账：reference-only / 权威链表 / 两边都有 / 缺口比例。

    供运维 dry-run 之外的健康度看板；只读。
    """
    from app.models.attachment_models import Attachment, AttachmentWorkingPaper

    ref_rows = (
        await db.execute(
            sa.select(Attachment.id, Attachment.reference_id).where(
                Attachment.reference_type == "working_paper",
                Attachment.reference_id.is_not(None),
                Attachment.is_deleted == sa.false(),
            )
        )
    ).all()
    ref_pairs = {(UUID(str(a)), UUID(str(w))) for a, w in ref_rows if a and w}

    link_rows = (
        await db.execute(
            sa.select(
                AttachmentWorkingPaper.attachment_id,
                AttachmentWorkingPaper.wp_id,
            )
        )
    ).all()
    link_pairs = {(UUID(str(a)), UUID(str(w))) for a, w in link_rows if a and w}

    both = ref_pairs & link_pairs
    ref_only = ref_pairs - link_pairs
    link_only = link_pairs - ref_pairs
    gap_pct = (
        round(100.0 * len(ref_only) / len(ref_pairs), 2) if ref_pairs else 0.0
    )
    return {
        "reference_pairs": len(ref_pairs),
        "authority_pairs": len(link_pairs),
        "both": len(both),
        "reference_only_gap": len(ref_only),
        "authority_only": len(link_only),
        "gap_pct_of_reference": gap_pct,
    }


async def main_async(args: argparse.Namespace) -> int:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        if args.rollback:
            stats = await run_rollback(db)
            logger.info("rollback done: %s", stats)
        elif args.apply:
            stats = await run_apply(db)
            logger.info("apply done: %s", stats)
        elif args.reconcile:
            stats = await run_reconcile(db)
            logger.info("reconcile: %s", stats)
        else:
            stats = await run_dry(db)
            logger.info("dry-run: %s", stats)
    await engine.dispose()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="回填 reference→attachment_working_paper")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True, help="只读诊断（默认）")
    g.add_argument("--apply", action="store_true", help="执行回填并写备份表")
    g.add_argument("--rollback", action="store_true", help="按备份表删除本轮补入的链行")
    g.add_argument("--reconcile", action="store_true", help="对账 reference vs 权威链表缺口")
    args = parser.parse_args()
    if args.apply or args.rollback or args.reconcile:
        args.dry_run = False
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
