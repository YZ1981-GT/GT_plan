"""Bulk Tab Import/Export — 项目级底稿批量导入导出编排层。"""

from app.services.bulk_tab.single_tab_adapter import (
    AdapterSpec,
    ConflictStrategy,
    IE_ADAPTER_REGISTRY,
    TabImportResult,
    export_tab,
    import_tab,
    register_adapter,
)
from app.services.bulk_tab.conflict_resolver import (
    ConflictRejected,
    has_non_empty_data,
    is_field_empty,
    is_row_empty,
    resolve_conflict,
)
from app.services.bulk_tab.snapshot_guard import (
    AtomicityMode,
    SnapshotGuard,
    SnapshotRecord,
)
from app.services.bulk_tab.workflow_gate import (
    ClassifiedItem,
    WorkflowClassification,
    WorkflowGate,
)
from app.services.bulk_tab.zip_handler import (
    ZipAssembler,
    ZipIntegrityError,
    ZipManifestMissing,
    ZipReader,
    ZipSizeLimitExceeded,
    check_no_secrets,
)
from app.services.bulk_tab.bulk_import_service import (
    FatalImportError,
    ImportPlan,
    ImportReport,
    SheetReport,
    align,
    dry_run,
    run,
)

# Task 2.2: 注册 D 循环 adapter（d1~d7），模块导入即注册
import app.services.bulk_tab._d_cycle_adapters  # noqa: F401

# Task 8.1: 注册 K/F/G/H 循环 adapter，模块导入即注册
import app.services.bulk_tab._kfgh_cycle_adapters  # noqa: F401

__all__ = [
    "AdapterSpec",
    "AtomicityMode",
    "ClassifiedItem",
    "ConflictRejected",
    "ConflictStrategy",
    "FatalImportError",
    "IE_ADAPTER_REGISTRY",
    "ImportPlan",
    "ImportReport",
    "SheetReport",
    "SnapshotGuard",
    "SnapshotRecord",
    "TabImportResult",
    "WorkflowClassification",
    "WorkflowGate",
    "ZipAssembler",
    "ZipIntegrityError",
    "ZipManifestMissing",
    "ZipReader",
    "ZipSizeLimitExceeded",
    "align",
    "check_no_secrets",
    "dry_run",
    "export_tab",
    "has_non_empty_data",
    "import_tab",
    "is_field_empty",
    "is_row_empty",
    "register_adapter",
    "resolve_conflict",
    "run",
]
