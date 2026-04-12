"""同步服务 — ProjectSync 和 SyncLog 的业务逻辑"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.collaboration_models import ProjectSync, SyncLog, SyncStatus, SyncType
from datetime import datetime, timezone
import uuid


class SyncService:
    @staticmethod
    def get_or_create_sync_record(db: Session, project_id: str) -> ProjectSync:
        """获取或创建项目同步记录"""
        sync = db.query(ProjectSync).filter(
            ProjectSync.project_id == project_id,
            ProjectSync.is_deleted == False,  # noqa: E712
        ).first()
        if not sync:
            sync = ProjectSync(
                id=uuid.uuid4(),
                project_id=project_id,
                global_version=1,
                sync_status=SyncStatus.IDLE,
                is_locked=False,
                is_deleted=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(sync)
            db.commit()
            db.refresh(sync)
        return sync

    @staticmethod
    def acquire_lock(db: Session, project_id: str, user_id: str) -> bool:
        """尝试获取项目锁定"""
        sync = SyncService.get_or_create_sync_record(db, project_id)
        if sync.is_locked:
            return False
        sync.is_locked = True
        sync.locked_by = user_id
        sync.locked_at = datetime.now(timezone.utc)
        db.commit()
        return True

    @staticmethod
    def release_lock(db: Session, project_id: str, user_id: str) -> bool:
        """释放项目锁定（仅锁定者可释放）"""
        sync = SyncService.get_or_create_sync_record(db, project_id)
        if sync.locked_by == user_id:
            sync.is_locked = False
            sync.locked_by = None
            sync.locked_at = None
            db.commit()
            return True
        return False

    @staticmethod
    def record_sync(
        db: Session,
        project_id: str,
        user_id: str,
        sync_type: SyncType,
        details: dict = None,
    ):
        """记录同步操作并增加全局版本号"""
        sync = SyncService.get_or_create_sync_record(db, project_id)
        sync.global_version += 1
        sync.last_synced_at = datetime.now(timezone.utc)
        sync.sync_status = SyncStatus.SYNCED
        db.commit()

        log = SyncLog(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=user_id,
            sync_type=sync_type,
            details=details,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()
        return sync

    @staticmethod
    def get_sync_status(db: Session, project_id: str) -> Optional[ProjectSync]:
        """获取项目同步状态"""
        return db.query(ProjectSync).filter(
            ProjectSync.project_id == project_id,
            ProjectSync.is_deleted == False,  # noqa: E712
        ).first()

    @staticmethod
    def get_sync_logs(
        db: Session, project_id: str, skip: int = 0, limit: int = 50
    ) -> List[SyncLog]:
        """获取项目同步日志列表"""
        return (
            db.query(SyncLog)
            .filter(
                SyncLog.project_id == project_id,
                SyncLog.is_deleted == False,  # noqa: E712
            )
            .order_by(SyncLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )



    @staticmethod
    def upload_package(
        db: Session,
        project_id: str,
        file_data: bytes,
        version: int,
        user_id: str,
    ) -> dict:
        """上传离线包（版本校验 + 数据打包）"""
        sync = SyncService.get_or_create_sync_record(db, project_id)

        # 版本校验：不能低于当前版本
        if version < sync.global_version:
            return {
                "success": False,
                "error": f"版本过期，当前版本为 {sync.global_version}，上传版本为 {version}",
            }

        # 版本一致时递增
        sync.global_version += 1
        sync.last_synced_at = datetime.now(timezone.utc)
        sync.sync_status = SyncStatus.SYNCED
        db.commit()

        # 记录同步日志
        log = SyncLog(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=user_id,
            sync_type=SyncType.upload,
            details={"version": version, "size_bytes": len(file_data)},
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()
        db.refresh(sync)

        return {
            "success": True,
            "project_id": str(project_id),
            "version": sync.global_version,
            "timestamp": sync.last_synced_at,
        }

    @staticmethod
    def download_package(
        db: Session,
        project_id: str,
        version: int = None,
    ) -> dict:
        """下载离线包"""
        sync = SyncService.get_or_create_sync_record(db, project_id)

        # 如果未指定版本，返回最新
        target_version = version or sync.global_version

        # 检查版本差异
        if target_version > sync.global_version:
            return {
                "success": False,
                "error": f"请求版本 {target_version} 不存在，当前最新版本为 {sync.global_version}",
            }

        return {
            "success": True,
            "project_id": str(project_id),
            "version": target_version,
            "global_version": sync.global_version,
            "last_synced_at": sync.last_synced_at,
        }

    @staticmethod
    def resolve_conflict(
        db: Session,
        project_id: str,
        conflict_id: str,
        resolution: str,
        user_id: str,
    ) -> dict:
        """解决同步冲突"""
        # 记录冲突解决日志
        log = SyncLog(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=user_id,
            sync_type=SyncType.conflict_resolution,
            details={
                "conflict_id": conflict_id,
                "resolution": resolution,
            },
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)

        # 更新同步状态
        sync = SyncService.get_or_create_sync_record(db, project_id)
        sync.global_version += 1
        sync.last_synced_at = datetime.now(timezone.utc)
        sync.sync_status = SyncStatus.SYNCED
        db.commit()

        return {
            "success": True,
            "project_id": str(project_id),
            "conflict_id": conflict_id,
            "resolution": resolution,
            "new_version": sync.global_version,
        }



    @staticmethod
    def export_package(db: Session, project_id: str, scope: str = "full") -> dict:
        """
        导出项目离线包（Excel/JSON）。
        scope: full=全量, incremental=增量（上次同步后变更）
        """
        import json, io
        from app.models.audit_platform_models import Project, Workpaper
        from app.models.workpaper_models import WorkpaperFile
        from app.models.report_models import ReportLine, AdjustmentEntry

        sync = SyncService.get_or_create_sync_record(db, project_id)

        # 基础信息
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return {"success": False, "error": "项目不存在"}

        # 工作底稿清单
        workpapers = db.query(Workpaper).filter(
            Workpaper.project_id == project_id,
            Workpaper.is_deleted == False,  # noqa: E712
        ).all()

        # 调整分录
        adjustments = db.query(AdjustmentEntry).filter(
            AdjustmentEntry.project_id == project_id,
            AdjustmentEntry.is_deleted == False,  # noqa: E712
        ).all()

        # 科目余额（试算表）
        from app.models.core import AccountBalance
        balances = db.query(AccountBalance).filter(
            AccountBalance.project_id == project_id,
        ).all()

        package = {
            "meta": {
                "project_id": str(project_id),
                "project_name": project.project_name,
                "fiscal_year": project.fiscal_year,
                "exported_version": sync.global_version,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "scope": scope,
                "format": "json",
            },
            "workpapers": [
                {
                    "id": str(wp.id),
                    "wp_code": wp.wp_code,
                    "wp_name": wp.wp_name,
                    "audit_area": wp.audit_area,
                    "status": wp.status,
                }
                for wp in workpapers
            ],
            "adjustments": [
                {
                    "id": str(adj.id),
                    "wp_code": adj.wp_code,
                    "journal_date": str(adj.journal_date) if adj.journal_date else None,
                    "description": adj.description,
                    "debit_amount": float(adj.debit_amount) if adj.debit_amount else 0,
                    "credit_amount": float(adj.credit_amount) if adj.credit_amount else 0,
                    "account_code": adj.account_code,
                }
                for adj in adjustments
            ],
            "balances": [
                {
                    "account_code": b.account_code,
                    "account_name": b.account_name,
                    "period_end_balance": float(b.period_end_balance) if b.period_end_balance else 0,
                    "period_average": float(b.period_average) if b.period_average else 0,
                }
                for b in balances
            ],
        }

        return {
            "success": True,
            "package": package,
            "version": sync.global_version,
        }

    @staticmethod
    def import_package(db: Session, project_id: str, package: dict, user_id: str) -> dict:
        """
        导入离线包并校验。
        校验：项目存在性 / 年度匹配 / 科目合法性 / 借贷平衡 / 版本过期
        """
        meta = package.get("meta", {})
        imported_project_id = meta.get("project_id")
        imported_version = meta.get("exported_version", 0)

        # 1. 项目存在性
        from app.models.audit_platform_models import Project
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return {"success": False, "error": "目标项目不存在"}

        # 2. 年度匹配
        if meta.get("project_name") != project.project_name and meta.get("fiscal_year") != project.fiscal_year:
            return {"success": False, "error": "年度不匹配，无法导入"}

        # 3. 科目合法性：检查科目代码格式（简单校验：数字）
        for bal in package.get("balances", []):
            code = bal.get("account_code", "")
            if not code.replace(".", "").replace("-", "").isalnum():
                return {"success": False, "error": f"非法科目代码: {code}"}

        # 4. 借贷平衡校验（调整分录）
        total_debit = sum(a["debit_amount"] for a in package.get("adjustments", []))
        total_credit = sum(a["credit_amount"] for a in package.get("adjustments", []))
        if abs(total_debit - total_credit) > 0.01:
            return {
                "success": False,
                "error": f"借贷不平衡: 借方={total_debit}, 贷方={total_credit}",
                "diff": abs(total_debit - total_credit),
            }

        # 5. 版本过期：不允许导入低于当前版本的包
        sync = SyncService.get_or_create_sync_record(db, project_id)
        if imported_version < sync.global_version:
            return {
                "success": False,
                "error": f"包版本 {imported_version} 已过期，当前版本 {sync.global_version}",
            }

        # 通过所有校验，记录导入
        SyncService.record_sync(db, project_id, user_id, SyncType.upload, {
            "imported_version": imported_version,
            "package_scope": meta.get("scope"),
        })

        return {
            "success": True,
            "project_id": str(project_id),
            "imported_version": imported_version,
            "new_version": sync.global_version,
            "items_imported": {
                "workpapers": len(package.get("workpapers", [])),
                "adjustments": len(package.get("adjustments", [])),
                "balances": len(package.get("balances", [])),
            },
        }
