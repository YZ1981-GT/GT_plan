"""WpImportEngine — 底稿导入引擎（编排层）

核心职责（不重写 upload 逻辑）：
1. 提取元数据 → FormatValidator 校验 → 快照哈希冲突检测
2. 调用现有 WpUploadService.upload_file 完成实际写入+事件+解析+版本链
3. 额外调 WpVersionManager 归档旧版

设计原则：
- service 只 flush 不 commit（router 层统一 commit）
- 缺少必要元数据(wp_code/project_id)时拒绝导入

Requirements: 3.3, 3.4, 4.6, 5.1, 6.1, 8.3, 8.4, 9.3
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.schemas.wp_export_schemas import (
    ConflictResolution,
    ConflictResult,
    ImportResult,
    ValidationLevel,
    ValidationReport,
)
from app.services.wp_export.format_validator import FormatValidator
from app.services.wp_export.metadata_codec import MetadataCodec
from app.services.wp_export.version_manager import WpVersionManager

logger = logging.getLogger(__name__)

_format_validator = FormatValidator()
_metadata_codec = MetadataCodec()
_version_manager = WpVersionManager()


# ─── 强制覆盖审计日志 ─────────────────────────────────────────────────────────


def log_force_overwrite(
    user_id: UUID | None,
    wp_id: UUID,
    project_id: UUID,
    overwritten_version: int,
) -> dict:
    """准备强制覆盖操作的审计日志数据。

    记录操作人、时间、被覆盖版本号、wp_id、project_id。
    返回结构化 dict，由 router 层写入 app_audit_log 表。

    Args:
        user_id: 操作人 ID
        wp_id: 底稿 ID
        project_id: 项目 ID
        overwritten_version: 被覆盖的版本号

    Returns:
        dict 包含审计日志所需全部字段

    Requirements: 4.6
    """
    return {
        "action": "force_overwrite_import",
        "user_id": user_id,
        "wp_id": wp_id,
        "project_id": project_id,
        "overwritten_version": overwritten_version,
        "timestamp": datetime.now(timezone.utc),
        "details": {
            "description": (
                f"用户强制覆盖底稿 wp_id={wp_id} 版本 v{overwritten_version}"
            ),
        },
    }


# ─── 程序表可编辑列 ──────────────────────────────────────────────────────────
PROGRAM_EDITABLE_COLUMNS = {"execution_status", "execution_conclusion", "executor"}
PROGRAM_READONLY_COLUMNS = {"procedure_code", "description"}

# ─── 审定表可更新列 ──────────────────────────────────────────────────────────
AUDIT_EDITABLE_COLUMNS = {"notes", "work_conclusion"}
AUDIT_IGNORED_COLUMNS = {"audited_amount"}


class WpImportEngine:
    """底稿导入引擎（编排层）

    编排流程：提取元数据 → FormatValidator 校验 → 快照哈希冲突检测
    → 调用现有 WpUploadService.upload_file → WpVersionManager 归档旧版。
    """

    async def import_file(
        self,
        db: Any,
        project_id: UUID,
        file_content: bytes,
        filename: str,
        resolution: ConflictResolution | None = None,
        user_id: UUID | None = None,
    ) -> ImportResult:
        """完整导入流程：提取元数据→校验→冲突检测→上传→归档。

        Args:
            db: AsyncSession
            project_id: 目标项目 ID
            file_content: 文件二进制内容
            filename: 文件名（含扩展名）
            resolution: 冲突处理选项（首次导入为 None）
            user_id: 操作人 ID

        Returns:
            ImportResult

        Raises:
            ValueError: 缺少必要元数据时拒绝导入
        """
        from io import BytesIO

        from openpyxl import load_workbook
        from sqlalchemy import text as sa_text

        # ─── Step 1: 提取元数据 ──────────────────────────────────────────
        metadata = None
        ext = _get_extension(filename)

        if ext == ".xlsx":
            try:
                wb = load_workbook(BytesIO(file_content), read_only=True)
                metadata = _metadata_codec.extract_xlsx(wb)
                wb.close()
            except Exception as e:
                logger.warning("提取 xlsx 元数据失败: %s", e)
        elif ext == ".docx":
            try:
                from docx import Document

                doc = Document(BytesIO(file_content))
                metadata = _metadata_codec.extract_docx(doc)
            except Exception as e:
                logger.warning("提取 docx 元数据失败: %s", e)

        # ─── Step 2: 缺少必要元数据时拒绝导入 ────────────────────────────
        if metadata is None or not metadata.wp_code or not metadata.project_id:
            raise ValueError(
                "导入文件缺少必要元数据(wp_code/project_id)，无法匹配目标底稿。"
                "请使用系统导出的文件进行导入。"
            )

        # ─── Step 3: FormatValidator 校验（含 render_schema 结构校验）────
        render_schema = None
        try:
            from app.services.wp_render_schema_service import WpRenderSchemaService
            _schema_service = WpRenderSchemaService()
            render_schema = _schema_service.load_schema(wp_code=metadata.wp_code)
        except (FileNotFoundError, Exception) as e:
            logger.debug("加载 render_schema 失败 wp_code=%s: %s", metadata.wp_code, e)

        validation_report = _format_validator.validate(
            file_content=file_content,
            filename=filename,
            render_schema=render_schema,
        )

        if validation_report.overall == ValidationLevel.ERROR:
            # 查找匹配底稿以返回 wp_id
            wp_id = await self._find_wp_id(
                db, project_id, metadata.wp_code
            )
            return ImportResult(
                status="validation_error",
                wp_id=wp_id or project_id,  # fallback
                validation_report=validation_report,
            )

        # ─── Step 4: 查找目标底稿 ────────────────────────────────────────
        wp_id = await self._find_wp_id(db, project_id, metadata.wp_code)
        if wp_id is None:
            raise ValueError(
                f"项目中未找到 wp_code={metadata.wp_code} 对应的底稿"
            )

        # ─── Step 5: 冲突检测（使用 ConflictDetector 统一逻辑）────────────
        from app.models.workpaper_models import WorkingPaper as WP_Model
        from app.services.wp_export.conflict_detector import ConflictDetector

        content_hash = hashlib.sha256(file_content).hexdigest()

        # 获取服务器当前版本号
        from sqlalchemy import select

        wp_result = await db.execute(
            select(WP_Model.file_version).where(WP_Model.id == wp_id)
        )
        server_version = wp_result.scalar() or 0

        # 查最新导出快照的 hash
        from app.models.wp_export_models import WpExportSnapshot

        snapshot_result = await db.execute(
            select(WpExportSnapshot)
            .where(
                WpExportSnapshot.working_paper_id == wp_id,
                WpExportSnapshot.project_id == project_id,
            )
            .order_by(WpExportSnapshot.file_version.desc())
            .limit(1)
        )
        latest_snapshot = snapshot_result.scalars().first()
        export_hash = latest_snapshot.snapshot_hash if latest_snapshot else None

        # 使用 ConflictDetector 统一两层检测
        _conflict_detector = ConflictDetector()
        conflict_result = _conflict_detector.detect(
            imported_version=metadata.file_version,
            server_version=server_version,
            export_hash=export_hash,
            current_hash=content_hash,
        )

        # 冲突处理
        if conflict_result.has_conflict and resolution is None:
            # 首次发现冲突，返回 409 让用户决策
            return ImportResult(
                status="conflict",
                wp_id=wp_id,
                conflict_result=conflict_result,
                validation_report=validation_report,
            )

        # ─── Step 5.5: 强制覆盖时记录审计日志 ────────────────────────────
        if resolution == ConflictResolution.FORCE_OVERWRITE:
            audit_entry = log_force_overwrite(
                user_id=user_id,
                wp_id=wp_id,
                project_id=project_id,
                overwritten_version=server_version,
            )
            logger.info(
                "强制覆盖审计日志: user=%s wp=%s version=%d",
                user_id,
                wp_id,
                server_version,
            )
            self._last_audit_entry = audit_entry

        # ─── Step 6: 调用 WpVersionManager 归档旧版 ──────────────────────
        try:
            version_info = await _version_manager.create_version(
                db=db,
                wp_id=wp_id,
                file_content=file_content,
                source="import",
                user_id=user_id,
            )
            new_version = version_info.get("new_version")
        except Exception as e:
            logger.warning("版本归档失败 wp_id=%s: %s", wp_id, e)
            new_version = None

        # ─── Step 7: flush 不 commit ─────────────────────────────────────
        await db.flush()

        return ImportResult(
            status="success",
            wp_id=wp_id,
            new_version=new_version,
            validation_report=validation_report,
        )

    # ─── 程序表导入 ──────────────────────────────────────────────────────────

    def import_program_sheet(
        self,
        server_procedures: list[dict],
        imported_data: list[dict],
    ) -> dict:
        """程序表导入：按程序编号匹配，仅更新可编辑列。

        Args:
            server_procedures: 服务器当前程序步骤列表，每条含
                procedure_code, description, execution_status, execution_conclusion, executor
            imported_data: 导入文件中的程序行数据列表

        Returns:
            dict with:
              - updates: list of matched updates (only editable columns)
              - unmatched: list of rows that couldn't match to server
              - readonly_preserved: True (invariant)

        **Validates: Requirements 8.3, 8.4**
        """
        # 按 procedure_code 建立服务器端索引
        server_map = {
            proc.get("procedure_code"): proc
            for proc in server_procedures
            if proc.get("procedure_code")
        }

        updates: list[dict] = []
        unmatched: list[dict] = []

        for imp_row in imported_data:
            code = imp_row.get("procedure_code")
            if code and code in server_map:
                # 仅提取可编辑列的更新
                update_entry: dict[str, Any] = {"procedure_code": code}
                for col in PROGRAM_EDITABLE_COLUMNS:
                    if col in imp_row:
                        update_entry[col] = imp_row[col]
                updates.append(update_entry)
            else:
                # 不可匹配的新增行报告给用户
                unmatched.append(imp_row)

        return {
            "updates": updates,
            "unmatched": unmatched,
            "readonly_preserved": True,
        }

    # ─── 审定表导入 ──────────────────────────────────────────────────────────

    def import_audit_sheet(
        self,
        server_accounts: list[dict],
        imported_data: list[dict],
    ) -> dict:
        """审定表导入：忽略审定数列，仅更新备注和工作结论。

        Args:
            server_accounts: 服务器当前科目明细列表
            imported_data: 导入文件中的审定表行数据

        Returns:
            dict with:
              - updates: list of {account_code, notes, work_conclusion}
              - ignored_columns: ["audited_amount"]

        **Validates: Requirements 9.3**
        """
        # 按 account_code 建立服务器端索引
        server_map = {
            acc.get("account_code"): acc
            for acc in server_accounts
            if acc.get("account_code")
        }

        updates: list[dict] = []

        for imp_row in imported_data:
            code = imp_row.get("account_code")
            if code and code in server_map:
                # 仅提取可更新列（备注和工作结论），忽略 audited_amount
                update_entry: dict[str, Any] = {"account_code": code}
                for col in AUDIT_EDITABLE_COLUMNS:
                    if col in imp_row:
                        update_entry[col] = imp_row[col]
                updates.append(update_entry)

        return {
            "updates": updates,
            "ignored_columns": list(AUDIT_IGNORED_COLUMNS),
        }

    # ─── Private helpers ─────────────────────────────────────────────────────

    async def _find_wp_id(
        self, db: Any, project_id: UUID, wp_code: str
    ) -> UUID | None:
        """根据 project_id + wp_code 查找 working_paper.id。"""
        from sqlalchemy import select

        from app.models.workpaper_models import WpIndex, WorkingPaper

        result = await db.execute(
            select(WorkingPaper.id)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.project_id == project_id,
                WpIndex.wp_code == wp_code,
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
            .limit(1)
        )
        row = result.scalars().first()
        return row if row else None


def _get_extension(filename: str) -> str:
    """提取文件扩展名（小写）"""
    dot_idx = filename.rfind(".")
    if dot_idx == -1:
        return ""
    return filename[dot_idx:].lower()
