"""交付物快照统一封装 — 三件套 tb_hash 对齐与过时检测"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase13_models import WordExportTask
from app.services.report_snapshot_service import ReportSnapshotService

logger = logging.getLogger(__name__)

STANDARD_TRIO = ("audit_report", "financial_report", "disclosure_notes")


@dataclass
class SnapshotRef:
    snapshot_id: str | None
    tb_hash: str
    doc_type: str
    year: int
    captured_at: str


@dataclass
class TrioConsistencyResult:
    consistent: bool
    tb_hashes: dict[str, str | None]
    message: str | None = None


@dataclass
class StaleCheckResult:
    stale: bool
    bound_tb_hash: str | None
    current_tb_hash: str | None
    message: str | None = None


class DeliverableSnapshotService:
    """统一快照封装层 — 以 trial_balance MD5 为三类对齐基准"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._snap_svc = ReportSnapshotService(db)

    async def capture_snapshot_ref(
        self, project_id: UUID, year: int, doc_type: str
    ) -> SnapshotRef:
        tb_hash = await self._snap_svc._compute_trial_balance_hash(project_id, year)
        snapshot_id: str | None = None

        if doc_type in ("financial_report", "financial_report_unadjusted"):
            from app.models.phase13_models import ReportSnapshot

            snap_row = await self.db.execute(
                sa.select(ReportSnapshot.id)
                .where(
                    ReportSnapshot.project_id == project_id,
                    ReportSnapshot.year == year,
                )
                .order_by(ReportSnapshot.generated_at.desc())
                .limit(1)
            )
            sid = snap_row.scalar_one_or_none()
            if sid:
                snapshot_id = str(sid)

        return SnapshotRef(
            snapshot_id=snapshot_id,
            tb_hash=tb_hash,
            doc_type=doc_type,
            year=year,
            captured_at=datetime.now(timezone.utc).isoformat(),
        )

    def snapshot_ref_to_dict(self, ref: SnapshotRef) -> dict:
        return {
            "snapshot_id": ref.snapshot_id,
            "tb_hash": ref.tb_hash,
            "doc_type": ref.doc_type,
            "year": ref.year,
            "captured_at": ref.captured_at,
        }

    async def capture_snapshot_refs(
        self, project_id: UUID, year: int, doc_type: str
    ) -> dict:
        """兼容 DeliverableService 调用签名"""
        ref = await self.capture_snapshot_ref(project_id, year, doc_type)
        return self.snapshot_ref_to_dict(ref)

    async def check_trio_consistency(
        self, project_id: UUID, year: int
    ) -> TrioConsistencyResult:
        """校验三件套最新版本是否绑定同一 tb_hash"""
        hashes: dict[str, str | None] = {}

        for doc_type in STANDARD_TRIO:
            task_row = await self.db.execute(
                sa.select(WordExportTask)
                .where(
                    WordExportTask.project_id == project_id,
                    WordExportTask.doc_type == doc_type,
                )
                .order_by(WordExportTask.updated_at.desc())
                .limit(1)
            )
            task = task_row.scalar_one_or_none()
            if task is None:
                hashes[doc_type] = None
                continue

            refs = task.source_snapshot_refs
            if isinstance(refs, dict):
                hashes[doc_type] = refs.get("tb_hash")
            else:
                hashes[doc_type] = None

        present = [h for h in hashes.values() if h]
        if len(present) < 2:
            return TrioConsistencyResult(
                consistent=True,
                tb_hashes=hashes,
                message="三件套尚未全部生成，暂不判定不一致",
            )

        unique = set(present)
        if len(unique) == 1:
            return TrioConsistencyResult(consistent=True, tb_hashes=hashes)

        return TrioConsistencyResult(
            consistent=False,
            tb_hashes=hashes,
            message="三件套绑定的数据快照不一致，请重新生成滞后的交付物",
        )

    async def check_stale(
        self, task: WordExportTask, year: int
    ) -> StaleCheckResult:
        """对比任务绑定 tb_hash 与当前底层数据"""
        refs = task.source_snapshot_refs
        if not isinstance(refs, dict) or not refs.get("tb_hash"):
            return StaleCheckResult(
                stale=False,
                bound_tb_hash=None,
                current_tb_hash=None,
                message="交付物未绑定快照引用",
            )

        bound_hash = refs["tb_hash"]
        current_ref = await self.capture_snapshot_ref(
            task.project_id, year, task.doc_type
        )
        current_hash = current_ref.tb_hash

        if bound_hash != current_hash:
            return StaleCheckResult(
                stale=True,
                bound_tb_hash=bound_hash,
                current_tb_hash=current_hash,
                message="底层数据已更新，交付物可能已与最新源数据不一致，建议重新导出",
            )

        return StaleCheckResult(
            stale=False,
            bound_tb_hash=bound_hash,
            current_tb_hash=current_hash,
        )
