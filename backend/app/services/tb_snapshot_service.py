"""Trial Balance Snapshot Service — 试算表版本时光机核心服务"""
import hashlib
import json
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import TrialBalanceSnapshot


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal values."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)


class TbSnapshotService:
    """试算表版本快照服务"""

    async def create_snapshot(
        self,
        db: AsyncSession,
        project_id: str,
        year: int,
        trigger: str,
        actor_id: Optional[str] = None,
        detail_rows: Optional[list] = None,
        summary_rows: Optional[list] = None,
    ) -> dict:
        """Create a snapshot of current trial_balance state.

        If content_hash matches the latest snapshot, returns {created: False, existing_version: N} (dedup).
        """
        # Build snapshot data
        snapshot_data = {
            "detail_rows": detail_rows or [],
            "summary_rows": summary_rows or [],
        }

        # Compute content hash for dedup
        content_hash = self._compute_content_hash(snapshot_data)

        # Check dedup: if latest snapshot has same hash, skip
        latest = await self._get_latest_snapshot(db, project_id, year)
        if latest and latest.content_hash == content_hash:
            return {"created": False, "existing_version": latest.version_no}

        # Get next version number
        version_no = await self._next_version_no(db, project_id, year)

        # Calculate stats
        all_rows = (detail_rows or []) + (summary_rows or [])
        row_count = len(detail_rows or [])
        audited_total = sum(
            float(r.get("audited_amount") or r.get("audited") or 0)
            for r in all_rows
            if r.get("audited_amount") or r.get("audited")
        )

        # Create snapshot record
        snapshot = TrialBalanceSnapshot(
            id=uuid.uuid4(),
            project_id=uuid.UUID(project_id) if isinstance(project_id, str) else project_id,
            year=year,
            version_no=version_no,
            trigger=trigger,
            actor_id=uuid.UUID(actor_id) if actor_id else None,
            content_hash=content_hash,
            snapshot_data=snapshot_data,
            row_count=row_count,
            audited_total=Decimal(str(audited_total)) if audited_total else None,
        )
        db.add(snapshot)
        await db.flush()

        return {
            "created": True,
            "version_no": version_no,
            "content_hash": content_hash,
            "row_count": row_count,
        }

    async def list_snapshots(
        self, db: AsyncSession, project_id: str, year: int, limit: int = 50
    ) -> list[dict]:
        """List snapshots for a project+year, ordered by version_no descending."""
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = (
            select(TrialBalanceSnapshot)
            .where(TrialBalanceSnapshot.project_id == pid)
            .where(TrialBalanceSnapshot.year == year)
            .order_by(desc(TrialBalanceSnapshot.version_no))
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "version_no": r.version_no,
                "trigger": r.trigger,
                "actor_id": str(r.actor_id) if r.actor_id else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "content_hash": r.content_hash,
                "row_count": r.row_count,
                "audited_total": float(r.audited_total) if r.audited_total else None,
            }
            for r in rows
        ]

    async def get_snapshot(
        self, db: AsyncSession, project_id: str, year: int, version_no: int
    ) -> Optional[dict]:
        """Get full snapshot by version number."""
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = (
            select(TrialBalanceSnapshot)
            .where(TrialBalanceSnapshot.project_id == pid)
            .where(TrialBalanceSnapshot.year == year)
            .where(TrialBalanceSnapshot.version_no == version_no)
        )
        result = await db.execute(stmt)
        r = result.scalar_one_or_none()
        if not r:
            return None
        return {
            "version_no": r.version_no,
            "trigger": r.trigger,
            "actor_id": str(r.actor_id) if r.actor_id else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "content_hash": r.content_hash,
            "row_count": r.row_count,
            "audited_total": float(r.audited_total) if r.audited_total else None,
            "snapshot_data": r.snapshot_data,
        }

    async def _get_latest_snapshot(
        self, db: AsyncSession, project_id: str, year: int
    ) -> Optional[TrialBalanceSnapshot]:
        """Get the latest snapshot for dedup comparison."""
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = (
            select(TrialBalanceSnapshot)
            .where(TrialBalanceSnapshot.project_id == pid)
            .where(TrialBalanceSnapshot.year == year)
            .order_by(desc(TrialBalanceSnapshot.version_no))
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _next_version_no(self, db: AsyncSession, project_id: str, year: int) -> int:
        """Get next version number (MAX + 1), with retry on conflict."""
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(func.max(TrialBalanceSnapshot.version_no)).where(
            TrialBalanceSnapshot.project_id == pid,
            TrialBalanceSnapshot.year == year,
        )
        result = await db.execute(stmt)
        max_no = result.scalar()
        return (max_no or 0) + 1

    async def restore_snapshot(
        self, db: AsyncSession, project_id: str, year: int, version_no: int, actor_id: Optional[str] = None
    ) -> dict:
        """Restore trial_balance to a historical snapshot state.

        1. Create snapshot of current state (trigger='restore') preserving audit trail
        2. Get target snapshot data
        3. Overwrite trial_balance rows from snapshot
        4. Return new version_no created by the restore
        """
        from app.models.audit_platform_models import TrialBalance

        # Get target snapshot
        target = await self.get_snapshot(db, project_id, year, version_no)
        if not target:
            raise ValueError(f"Snapshot version {version_no} not found")

        # First: snapshot current state before overwriting (Property 3: preserve trail)
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        current_rows_stmt = select(TrialBalance).where(
            TrialBalance.project_id == pid,
            TrialBalance.year == year,
        )
        current_result = await db.execute(current_rows_stmt)
        current_rows = current_result.scalars().all()

        current_detail = [
            {
                "standard_account_code": r.standard_account_code,
                "unadjusted_amount": str(r.unadjusted_amount) if r.unadjusted_amount else None,
                "aje_adjustment": str(r.aje_adjustment) if r.aje_adjustment else None,
                "rje_adjustment": str(r.rje_adjustment) if r.rje_adjustment else None,
                "audited_amount": str(r.audited_amount) if r.audited_amount else None,
            }
            for r in current_rows
        ]

        await self.create_snapshot(
            db, project_id, year, trigger="restore", actor_id=actor_id,
            detail_rows=current_detail,
        )

        # Now overwrite trial_balance with target snapshot data
        target_details = target["snapshot_data"].get("detail_rows", [])

        # Delete existing rows and insert from snapshot
        from sqlalchemy import delete
        await db.execute(
            delete(TrialBalance).where(
                TrialBalance.project_id == pid,
                TrialBalance.year == year,
            )
        )

        for row_data in target_details:
            tb_row = TrialBalance(
                project_id=pid,
                year=year,
                standard_account_code=row_data.get("standard_account_code"),
                unadjusted_amount=row_data.get("unadjusted_amount"),
                aje_adjustment=row_data.get("aje_adjustment"),
                rje_adjustment=row_data.get("rje_adjustment"),
                audited_amount=row_data.get("audited_amount"),
            )
            db.add(tb_row)

        await db.flush()

        return {"restored_to_version": version_no, "rows_restored": len(target_details)}

    async def diff_snapshots(
        self, db: AsyncSession, project_id: str, year: int, v1: int, v2: int
    ) -> dict:
        """Compare two snapshots, return changed/added/removed rows + stats."""
        snap1 = await self.get_snapshot(db, project_id, year, v1)
        snap2 = await self.get_snapshot(db, project_id, year, v2)

        if not snap1 or not snap2:
            raise ValueError("One or both snapshots not found")

        # Build maps by row identifier (standard_account_code or row_code)
        def _build_map(snapshot_data: dict) -> dict:
            result = {}
            for row in snapshot_data.get("detail_rows", []):
                key = row.get("standard_account_code") or row.get("row_code", "")
                if key:
                    result[key] = row
            for row in snapshot_data.get("summary_rows", []):
                key = row.get("row_code", "")
                if key:
                    result[f"sum:{key}"] = row
            return result

        map1 = _build_map(snap1["snapshot_data"])
        map2 = _build_map(snap2["snapshot_data"])

        all_keys = set(map1.keys()) | set(map2.keys())
        changed = []
        added = []  # in v2 but not v1
        removed = []  # in v1 but not v2

        for key in sorted(all_keys):
            in1 = key in map1
            in2 = key in map2
            if in1 and not in2:
                removed.append({"key": key, "row": map1[key]})
            elif in2 and not in1:
                added.append({"key": key, "row": map2[key]})
            else:
                r1 = map1[key]
                r2 = map2[key]
                aud1 = float(r1.get("audited_amount") or r1.get("audited") or 0)
                aud2 = float(r2.get("audited_amount") or r2.get("audited") or 0)
                if abs(aud2 - aud1) > 0.005:
                    changed.append({
                        "key": key,
                        "v1_audited": aud1,
                        "v2_audited": aud2,
                        "diff": aud2 - aud1,
                    })

        total_diff = sum(c["diff"] for c in changed)
        max_diff = max((abs(c["diff"]) for c in changed), default=0)

        return {
            "v1": v1,
            "v2": v2,
            "changed": changed,
            "added": added,
            "removed": removed,
            "stats": {
                "changed_count": len(changed),
                "added_count": len(added),
                "removed_count": len(removed),
                "total_audited_delta": total_diff,
                "max_single_row_delta": max_diff,
            },
        }

    @staticmethod
    def _compute_content_hash(snapshot_data: dict) -> str:
        """Deterministic SHA-256 of snapshot content for dedup."""
        # Sort keys for determinism
        canonical = json.dumps(snapshot_data, sort_keys=True, cls=DecimalEncoder)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
