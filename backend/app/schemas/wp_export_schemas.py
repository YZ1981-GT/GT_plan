"""底稿统一导入导出 DTO/Schema 定义

对应 design.md「DTO / Schema 定义」章节。
供 Export_Engine、Import_Engine、ConflictDetector、FormatValidator、
BatchPackager、TemplateCopier 等服务层使用。

Requirements: 3.1, 3.2, 4.3, 4.4, 5.6, 6.2
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


# ─── 元数据 ──────────────────────────────────────────────────────────────────


class MetadataBundle(BaseModel):
    """导出文件嵌入的元数据包

    嵌入 xlsx Custom Properties / docx core+custom properties。
    导入时提取用于匹配目标底稿和版本冲突检测。
    """

    wp_code: str
    project_id: UUID
    file_version: int
    export_timestamp: datetime
    preparer: str | None = None
    reviewer: str | None = None
    review_status: str | None = None


# ─── 导出结果 ─────────────────────────────────────────────────────────────────


class ExportResult(BaseModel):
    """单底稿导出结果

    file_content 实际通过 StreamingResponse 传输，schema 层仅作类型标注。
    """

    file_content: bytes
    filename: str
    file_format: str  # xlsx | docx
    snapshot_hash: str
    metadata: MetadataBundle


# ─── 冲突检测 ─────────────────────────────────────────────────────────────────


class ConflictResolution(str, Enum):
    """冲突处理选项"""

    FORCE_OVERWRITE = "force_overwrite"
    PARALLEL_VERSION = "parallel_version"
    CANCEL = "cancel"


class ConflictResult(BaseModel):
    """冲突检测结果

    has_conflict=True 时包含冲突详情；is_substantive 区分版本号冲突与内容实质冲突。
    """

    has_conflict: bool
    conflict_type: str | None = None  # version | content | both
    server_version: int
    imported_version: int
    last_modifier: str | None = None
    last_modified_at: datetime | None = None
    is_substantive: bool = False


# ─── 格式校验 ─────────────────────────────────────────────────────────────────


class ValidationLevel(str, Enum):
    """校验结果级别"""

    PASSED = "passed"
    WARNING = "warning"
    ERROR = "error"


class ValidationItem(BaseModel):
    """单条校验结果项"""

    level: ValidationLevel
    location: str  # e.g. "Sheet1!B5" or "core_properties.wp_code"
    message: str
    field: str | None = None


class ValidationReport(BaseModel):
    """结构化校验报告

    overall 取所有 items 中最严重级别；三类计数与 items 分区一致。
    """

    overall: ValidationLevel
    items: list[ValidationItem] = Field(default_factory=list)
    passed_count: int = 0
    warning_count: int = 0
    error_count: int = 0


# ─── 导入结果 ─────────────────────────────────────────────────────────────────


class ImportResult(BaseModel):
    """导入操作结果

    status 标识最终状态：success（导入成功）/ conflict（需用户决策）/
    validation_error（校验未通过）。
    """

    status: str  # success | conflict | validation_error
    wp_id: UUID
    new_version: int | None = None
    validation_report: ValidationReport | None = None
    conflict_result: ConflictResult | None = None


# ─── 批量导出 ─────────────────────────────────────────────────────────────────


class BatchExportResult(BaseModel):
    """批量打包导出结果

    zip_content 实际通过 StreamingResponse 传输。
    manifest 对应 ZIP 根目录 manifest.json 内容。
    """

    zip_content: bytes
    manifest: dict
    total_files: int
    failed_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ─── 模板复制 ─────────────────────────────────────────────────────────────────


class CopyResult(BaseModel):
    """模板复制单项结果"""

    source_wp_code: str
    target_wp_id: UUID | None = None
    status: str  # copied | skipped | overwritten | failed
    message: str | None = None
