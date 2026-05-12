"""合并报表增强服务 — Phase 10 Task 7.1-7.3"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project

logger = logging.getLogger(__name__)


class ConsolLockService:
    """合并锁定同步"""

    async def lock_project(
        self, db: AsyncSession, project_id: UUID, locked_by: UUID,
    ) -> dict[str, Any]:
        """锁定单体试算表"""
        await db.execute(sa.text(
            "UPDATE projects SET consol_lock = true, consol_lock_by = :by, "
            "consol_lock_at = :at WHERE id = :pid"
        ), {"by": str(locked_by), "at": datetime.now(timezone.utc), "pid": str(project_id)})
        await db.flush()
        return {"locked": True, "project_id": str(project_id)}

    async def unlock_project(
        self, db: AsyncSession, project_id: UUID,
    ) -> dict[str, Any]:
        """解锁"""
        await db.execute(sa.text(
            "UPDATE projects SET consol_lock = false, consol_lock_by = NULL, "
            "consol_lock_at = NULL WHERE id = :pid"
        ), {"pid": str(project_id)})
        await db.flush()
        return {"locked": False, "project_id": str(project_id)}

    async def check_lock(
        self, db: AsyncSession, project_id: UUID,
    ) -> dict[str, Any]:
        """检查锁定状态"""
        result = await db.execute(sa.text(
            "SELECT consol_lock, consol_lock_by, consol_lock_at "
            "FROM projects WHERE id = :pid"
        ), {"pid": str(project_id)})
        row = result.first()
        if not row:
            return {"locked": False}
        return {
            "locked": bool(row.consol_lock) if row.consol_lock else False,
            "locked_by": str(row.consol_lock_by) if row.consol_lock_by else None,
            "locked_at": row.consol_lock_at.isoformat() if row.consol_lock_at else None,
        }


class ExternalReportImportService:
    """外部单位报表导入"""

    async def import_external_report(
        self, db: AsyncSession, project_id: UUID, data: dict[str, Any],
    ) -> dict[str, Any]:
        """导入其他审计师审计的单位报表

        解析上传的 Excel 文件，提取试算表数据写入 trial_balance。
        """
        import logging
        _logger = logging.getLogger(__name__)

        try:
            # 实际实现：从上传文件解析试算表数据
            # 这里提供框架，具体解析逻辑依赖文件格式
            from sqlalchemy import text

            # 检查项目是否存在
            proj_check = await self.db.execute(
                text("SELECT id FROM projects WHERE id = :pid"),
                {"pid": str(project_id)}
            )
            if not proj_check.fetchone():
                return {
                    "project_id": str(project_id),
                    "imported": False,
                    "message": "项目不存在",
                }

            # 如果有 file_content（bytes），解析 Excel
            file_content = kwargs.get("file_content")
            if file_content:
                import openpyxl
                from io import BytesIO

                wb = openpyxl.load_workbook(BytesIO(file_content), data_only=True)
                ws = wb.active
                imported_count = 0

                for row in ws.iter_rows(min_row=2, values_only=True):
                    if not row or not row[0]:
                        continue
                    account_code = str(row[0]).strip()
                    amount = float(row[1] or 0) if len(row) > 1 else 0

                    # 写入或更新 trial_balance
                    await self.db.execute(text("""
                        INSERT INTO trial_balance (id, project_id, year, standard_account_code, unadjusted_amount, audited_amount, is_deleted, created_at, updated_at)
                        VALUES (gen_random_uuid(), :pid, :year, :code, :amt, :amt, false, NOW(), NOW())
                        ON CONFLICT (project_id, year, standard_account_code)
                        DO UPDATE SET unadjusted_amount = :amt, audited_amount = :amt, updated_at = NOW()
                    """), {"pid": str(project_id), "year": year, "code": account_code, "amt": amount})
                    imported_count += 1

                wb.close()
                await self.db.flush()

                _logger.info(f"[CONSOL] external report imported: project={project_id} company={company_code} rows={imported_count}")
                return {
                    "project_id": str(project_id),
                    "company_code": company_code,
                    "imported": True,
                    "imported_count": imported_count,
                    "message": f"外部报表导入成功，{imported_count} 行数据",
                }

            return {
                "project_id": str(project_id),
                "imported": False,
                "message": "未提供文件内容（file_content 参数缺失）",
            }
        except Exception as e:
            _logger.error(f"[CONSOL] external report import failed: {e}")
            return {
                "project_id": str(project_id),
                "imported": False,
                "message": f"导入失败: {str(e)[:200]}",
            }


class IndependentModuleService:
    """独立模块使用"""

    async def create_temp_project(
        self, db: AsyncSession, module: str, user_id: UUID,
    ) -> dict[str, Any]:
        """创建临时项目（仅合并/报告复核/排版模块）"""
        valid_modules = {"consolidation", "report_review", "report_format"}
        if module not in valid_modules:
            raise ValueError(f"不支持的模块: {module}")
        project = Project(
            name=f"临时项目-{module}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}",
            client_name="临时",
            manager_id=user_id,
        )
        # 标记为自动创建
        project.wizard_state = {"auto_created": True, "module": module}
        db.add(project)
        await db.flush()
        return {"project_id": str(project.id), "module": module, "auto_created": True}
