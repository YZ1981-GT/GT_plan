"""Phase 16: 取证包完整性校验服务

对齐 v2 WP-ENT-06: manifest + SHA-256 + 签名摘要
"""
import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase16_models import EvidenceHashCheck
from app.services.trace_event_service import trace_event_service, generate_trace_id

logger = logging.getLogger(__name__)


class ExportIntegrityService:

    async def calc_hash(self, file_path: str) -> str:
        """计算文件 SHA-256（64KB 分块读取）"""
        h = hashlib.sha256()
        p = Path(file_path)
        if not p.exists():
            return ""
        with open(p, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    async def build_manifest(self, export_id: str, files: list[str]) -> dict:
        """构建 manifest：逐文件计算 hash"""
        file_checks = []
        for fp in files:
            sha = await self.calc_hash(fp)
            file_checks.append({"file_path": fp, "sha256": sha})

        manifest_json = json.dumps(file_checks, sort_keys=True)
        manifest_hash = hashlib.sha256(manifest_json.encode()).hexdigest()

        return {
            "export_id": export_id,
            "files": file_checks,
            "manifest_hash": manifest_hash,
        }

    async def persist_checks(
        self,
        db: AsyncSession,
        export_id: str,
        file_checks: list[dict],
    ) -> None:
        """批量写入 evidence_hash_checks"""
        import uuid as _uuid
        for fc in file_checks:
            check = EvidenceHashCheck(
                id=_uuid.uuid4(),
                export_id=_uuid.UUID(export_id) if isinstance(export_id, str) else export_id,
                file_path=fc["file_path"],
                sha256=fc["sha256"],
                check_status="passed",
            )
            db.add(check)
        await db.flush()

    # 别名：需求文档中引用为 persist_hash_checks
    async def persist_hash_checks(
        self,
        db: AsyncSession,
        export_id: str,
        file_checks: list[dict],
    ) -> None:
        """persist_checks 的别名，对齐需求文档命名。"""
        await self.persist_checks(db, export_id, file_checks)

    async def verify_package(self, db, export_id: str) -> dict:
        """校验导出包完整性：逐文件比对 hash"""
        from sqlalchemy import select
        stmt = select(EvidenceHashCheck).where(
            EvidenceHashCheck.export_id == export_id
        )
        result = await db.execute(stmt)
        checks = result.scalars().all()

        if not checks:
            return {"export_id": export_id, "check_status": "no_records", "file_checks": []}

        mismatched = []
        all_passed = True
        file_results = []

        for c in checks:
            current_hash = await self.calc_hash(c.file_path)
            status = "passed" if current_hash == c.sha256 else "failed"
            if status == "failed":
                all_passed = False
                mismatched.append(c.file_path)
                c.check_status = "failed"
            file_results.append({
                "file_path": c.file_path,
                "expected_sha256": c.sha256,
                "actual_sha256": current_hash,
                "check_status": status,
            })

        await db.flush()

        overall = "passed" if all_passed else "failed"

        # 失败时写 trace
        if not all_passed:
            try:
                trace_id = generate_trace_id()
                await trace_event_service.write(
                    db=db,
                    project_id=checks[0].export_id,  # 用 export_id 代替
                    event_type="integrity_check_failed",
                    object_type="export",
                    object_id=checks[0].export_id,
                    actor_id=checks[0].export_id,
                    action=f"verify_package:failed:{len(mismatched)}_files",
                    decision="block",
                    trace_id=trace_id,
                )
            except Exception:
                pass

        return {
            "export_id": export_id,
            "check_status": overall,
            "file_checks": file_results,
            "mismatched_files": mismatched,
        }


export_integrity_service = ExportIntegrityService()
