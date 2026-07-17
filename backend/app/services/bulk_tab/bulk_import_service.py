"""BulkImportService — 批量导入编排层（Req 2.1–2.9, 4.1–4.2, 9.1–9.3）

职责：
  - dry_run(): 校验 manifest / 文件完整性 / 工作流状态门禁，不写库，返回逐文件预检报告
  - run(): align → WorkflowGate 分类 → SnapshotGuard 快照 → 按拓扑顺序逐 sheet import_tab
           → 汇总 ImportReport → 审计日志；失败按策略回滚

核心铁律：
  - service 只 flush 不 commit
  - 复用 wp_bulk_tab_export.list_import_sheets 获取拓扑顺序
  - 单 sheet 失败不整包失败（fail-soft），除非 all-or-nothing 模式
  - 成功 sheet 由单表 import 内部 WORKPAPER_SAVED 触发联动重算

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 4.1, 4.2
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User
from app.services.bulk_tab.single_tab_adapter import (
    ConflictStrategy,
    TabImportResult,
    import_tab,
)
from app.services.bulk_tab.snapshot_guard import (
    AtomicityMode,
    SnapshotGuard,
    SnapshotRecord,
)
from app.services.bulk_tab.workflow_gate import WorkflowGate
from app.services.bulk_tab.zip_handler import (
    ZipIntegrityError,
    ZipManifestMissing,
    ZipReader,
    ZipSizeLimitExceeded,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FatalImportError(Exception):
    """导入过程中不可恢复的严重错误，触发全量回滚。"""

    def __init__(self, message: str = "导入过程中发生严重错误") -> None:
        super().__init__(message)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

SheetStatus = Literal[
    "success",
    "partial",
    "failed",
    "blocked_by_status",
    "missing",
    "unlisted",
    "conflict_rejected",
    "skipped",
]


@dataclass
class SheetReport:
    """单个 sheet 的导入报告。"""

    sheet_code: str
    status: SheetStatus
    rows: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"sheet_code": self.sheet_code, "status": self.status}
        if self.rows > 0:
            d["rows"] = self.rows
        if self.warnings:
            d["warnings"] = self.warnings
        if self.errors:
            d["errors"] = self.errors
        if self.reason:
            d["reason"] = self.reason
        return d


@dataclass
class ImportReport:
    """批量导入汇总报告。"""

    import_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    strategy: ConflictStrategy = "overwrite"
    dry_run: bool = False
    snapshots: list[dict[str, str]] = field(default_factory=list)
    sheets: list[SheetReport] = field(default_factory=list)
    rolled_back: bool = False

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {
            "success": 0,
            "partial": 0,
            "failed": 0,
            "blocked": 0,
            "missing": 0,
            "unlisted": 0,
            "conflict_rejected": 0,
            "skipped": 0,
        }
        for s in self.sheets:
            if s.status == "blocked_by_status":
                counts["blocked"] += 1
            elif s.status in counts:
                counts[s.status] += 1
        return {k: v for k, v in counts.items() if v > 0}

    def to_dict(self) -> dict[str, Any]:
        return {
            "import_id": self.import_id,
            "strategy": self.strategy,
            "dry_run": self.dry_run,
            "snapshots": self.snapshots,
            "sheets": [s.to_dict() for s in self.sheets],
            "summary": self.summary,
            "rolled_back": self.rolled_back,
        }

    def mark(self, sheet_code: str, status: SheetStatus, reason: str | None = None) -> None:
        self.sheets.append(SheetReport(sheet_code=sheet_code, status=status, reason=reason))

    def merge(self, sheet_code: str, result: TabImportResult) -> None:
        self.sheets.append(
            SheetReport(
                sheet_code=sheet_code,
                status=result.status,
                rows=result.rows_imported,
                warnings=result.warnings,
                errors=result.errors,
            )
        )

    def mark_all_rolled_back(self) -> None:
        self.rolled_back = True


# ---------------------------------------------------------------------------
# Internal: align manifest entries with available sheets
# ---------------------------------------------------------------------------


@dataclass
class AlignedItem:
    """align() 对齐后的单个条目。"""

    sheet_code: str
    wp_id: str
    api_prefix: str
    zip_path: str
    status: str  # wp 当前工作流 status
    blocked: bool = False
    block_reason: str | None = None
    missing: bool = False  # manifest 中有但 ZIP 无文件
    unlisted: bool = False  # ZIP 中有但 manifest 中无
    import_order: int = 999


@dataclass
class ImportPlan:
    """对齐后的导入计划。"""

    items: list[AlignedItem] = field(default_factory=list)
    unlisted_paths: list[str] = field(default_factory=list)

    @property
    def writable_wp_ids(self) -> list[uuid.UUID]:
        """需要写入的底稿 ID 列表（去重）。"""
        seen: set[str] = set()
        result: list[uuid.UUID] = []
        for item in self.items:
            if item.blocked or item.missing:
                continue
            if item.wp_id not in seen:
                seen.add(item.wp_id)
                result.append(uuid.UUID(item.wp_id))
        return result

    def topo_order(self) -> list[AlignedItem]:
        """按导入顺序返回条目（已由 list_import_sheets 排好拓扑序）。"""
        return self.items


def align(
    manifest_files: list[dict[str, Any]],
    topo_sheets: list[dict[str, Any]],
    zip_file_list: list[str],
) -> ImportPlan:
    """对齐 manifest 条目与 ZIP 实际文件列表。

    - manifest 中有但 ZIP 中无对应文件 → missing（Req 2.8）
    - ZIP 中有 xlsx 但 manifest 未登记 → unlisted（Req 2.9）
    - 返回的 items 按 topo_sheets 顺序排列（Req 2.2）

    Args:
        manifest_files: manifest.json 中的 files[] 列表
        topo_sheets: list_import_sheets 返回的拓扑排序后条目
        zip_file_list: ZIP 中实际文件路径列表

    Returns:
        ImportPlan
    """
    # 构建 sheet_code → manifest entry 映射
    manifest_by_code: dict[str, dict[str, Any]] = {}
    for mf in manifest_files:
        code = mf.get("sheet_code", "")
        if code:
            manifest_by_code[code] = mf

    # 构建 sheet_code → topo entry 映射
    topo_by_code: dict[str, dict[str, Any]] = {}
    for ts in topo_sheets:
        code = ts.get("sheet_code", "")
        if code:
            topo_by_code[code] = ts

    # ZIP 中实际有的 xlsx 文件路径集
    zip_xlsx_set = {p for p in zip_file_list if p.endswith(".xlsx")}
    # manifest 中登记的 zip_path 集合
    manifest_zip_paths: set[str] = set()

    items: list[AlignedItem] = []

    # 按拓扑顺序遍历（保证导入顺序）
    for ts in topo_sheets:
        code = ts.get("sheet_code", "")
        mf = manifest_by_code.get(code)

        if not mf:
            # topo_sheets 中有但 manifest 中无 — 跳过（manifest 不含此 sheet）
            continue

        zip_path = mf.get("zip_path", "")
        manifest_zip_paths.add(zip_path)
        wp_id = mf.get("wp_id", "") or ts.get("wp_id", "")

        is_missing = bool(zip_path and zip_path not in zip_xlsx_set)

        items.append(
            AlignedItem(
                sheet_code=code,
                wp_id=str(wp_id),
                api_prefix=mf.get("api_prefix", "") or ts.get("api_prefix", ""),
                zip_path=zip_path,
                status="",  # 将由 WorkflowGate 填充
                missing=is_missing,
                import_order=mf.get("import_order", 999),
            )
        )

    # 检测 unlisted 文件（ZIP 中有但 manifest 中未登记的 xlsx）
    unlisted_paths: list[str] = []
    for zp in zip_xlsx_set:
        if zp not in manifest_zip_paths:
            unlisted_paths.append(zp)

    return ImportPlan(items=items, unlisted_paths=unlisted_paths)


# ---------------------------------------------------------------------------
# Internal: query workpaper statuses
# ---------------------------------------------------------------------------


async def _get_wp_statuses(
    db: AsyncSession, wp_ids: list[str]
) -> dict[str, str]:
    """查询底稿的工作流状态。

    Args:
        db: 数据库会话
        wp_ids: 底稿 UUID 字符串列表

    Returns:
        wp_id → status 映射
    """
    if not wp_ids:
        return {}

    from sqlalchemy import select
    from app.models.workpaper_models import WorkingPaper

    unique_ids = list(set(wp_ids))
    uuid_list = []
    for wid in unique_ids:
        try:
            uuid_list.append(uuid.UUID(wid))
        except (ValueError, TypeError):
            continue

    if not uuid_list:
        return {}

    stmt = select(WorkingPaper.id, WorkingPaper.status).where(
        WorkingPaper.id.in_(uuid_list)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return {str(row[0]): row[1].value if hasattr(row[1], "value") else str(row[1]) for row in rows}


# ---------------------------------------------------------------------------
# Internal: audit log
# ---------------------------------------------------------------------------


async def _write_import_audit_log(
    db: AsyncSession,
    user: User,
    project_id: str,
    report: ImportReport,
) -> None:
    """写入导入审计日志。"""
    try:
        from app.services.audit_log_helper import append_audit_log

        await append_audit_log(
            db,
            {
                "user_id": user.id,
                "project_id": uuid.UUID(project_id) if isinstance(project_id, str) else project_id,
                "action": "bulk_tab_import",
                "resource_type": "project",
                "resource_id": str(project_id),
                "details": {
                    "event_type": "bulk_tab_import",
                    "import_id": report.import_id,
                    "strategy": report.strategy,
                    "dry_run": report.dry_run,
                    "summary": report.summary,
                    "sheet_count": len(report.sheets),
                    "rolled_back": report.rolled_back,
                },
            },
        )
    except Exception:
        # 审计日志写入失败不阻断主流程（fail-soft）
        logger.warning(
            "BulkImport: 审计日志写入失败 project_id=%s",
            project_id,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Public API: dry_run
# ---------------------------------------------------------------------------


async def dry_run(
    db: AsyncSession,
    project_id: str,
    zip_bytes: bytes,
    strategy: ConflictStrategy = "overwrite",
    *,
    preflight: Callable[[str, str | None], Any] | None = None,
) -> ImportReport:
    """校验 manifest / 文件完整性 / 工作流状态门禁；不写库（Req 2.3）。

    步骤：
      1. ZipReader 解析 ZIP（manifest 存在性 + 大小上限）
      2. SHA256 完整性校验
      3. 从 list_import_sheets 获取拓扑顺序 sheet 列表
      4. align() 对齐 manifest 与 ZIP 实际文件
      5. 查询各底稿工作流状态 → WorkflowGate 分类
      6. 汇总逐文件预检报告

    Args:
        db: 数据库会话（不写库）
        project_id: 项目 UUID
        zip_bytes: 上传的 ZIP 文件字节流
        strategy: 冲突策略

    Returns:
        ImportReport（dry_run=True），逐 sheet 报告状态
    """
    report = ImportReport(strategy=strategy, dry_run=True)

    # ① ZipReader 解析（manifest + 大小上限校验）
    try:
        reader = ZipReader.from_bytes(zip_bytes)
    except (ZipSizeLimitExceeded, ZipManifestMissing) as e:
        report.mark("__zip__", "failed", reason=str(e))
        return report
    except Exception as e:
        report.mark("__zip__", "failed", reason=f"ZIP 解析失败: {e}")
        return report

    # ② SHA256 完整性校验
    try:
        reader.verify_integrity()
    except ZipIntegrityError as e:
        report.mark("__integrity__", "failed", reason=str(e))
        return report

    manifest = reader.manifest
    manifest_files = manifest.get("files", [])

    # ③ 获取拓扑顺序 sheet 列表
    from app.services.wp_bulk_tab_export import list_import_sheets

    # manifest 中的 cycles 信息（可能含多个循环）
    cycles = manifest.get("cycles", [])
    topo_sheets: list[dict[str, Any]] = []
    for cycle in cycles:
        sheets = await list_import_sheets(db, project_id, cycle)
        topo_sheets.extend(sheets)

    # 若无 cycles 字段，尝试从文件路径推断
    if not topo_sheets and not cycles:
        # fallback: 从 manifest files 收集 cycles
        inferred_cycles: set[str] = set()
        for mf in manifest_files:
            zp = mf.get("zip_path", "")
            if "/" in zp:
                inferred_cycles.add(zp.split("/")[0])
        for cycle in sorted(inferred_cycles):
            try:
                sheets = await list_import_sheets(db, project_id, cycle)
                topo_sheets.extend(sheets)
            except Exception:
                pass

    # ④ align
    zip_file_list = reader.list_files()
    plan = align(manifest_files, topo_sheets, zip_file_list)

    # ④.5 Task 10 逐资源 gate preflight（Req 8.13/8.14/9）：显式任一资源被拒 → 抛
    # ExternalNotFound（404），整请求失败且不泄露存在性；dry_run 亦不得据存在性推断。
    if preflight is not None:
        for item in plan.items:
            if item.missing or not item.wp_id:
                continue
            await preflight(item.wp_id, item.sheet_code)

    # ⑤ 查询底稿状态 + WorkflowGate 分类
    wp_ids = [item.wp_id for item in plan.items if item.wp_id]
    statuses = await _get_wp_statuses(db, wp_ids)

    gate = WorkflowGate()
    gate_items = [
        {"wp_id": uuid.UUID(item.wp_id), "status": statuses.get(item.wp_id, "")}
        for item in plan.items
        if item.wp_id
    ]
    classifications = gate.classify(gate_items)

    # ⑥ 汇总报告
    for item in plan.items:
        if item.missing:
            report.mark(item.sheet_code, "missing", reason="ZIP 中缺少对应文件")
            continue

        wp_uuid = uuid.UUID(item.wp_id) if item.wp_id else None
        if wp_uuid and wp_uuid in classifications:
            cls = classifications[wp_uuid]
            if cls.classification == "blocked":
                report.mark(item.sheet_code, "blocked_by_status", reason=cls.reason)
                continue

        # 正常可写 → dry_run 中标记为 success（预检通过）
        report.mark(item.sheet_code, "success")

    # unlisted 文件
    for path in plan.unlisted_paths:
        report.sheets.append(
            SheetReport(sheet_code=path, status="unlisted", reason="ZIP 中存在但 manifest 未登记")
        )

    reader.close()
    return report


# ---------------------------------------------------------------------------
# Public API: run
# ---------------------------------------------------------------------------


async def run(
    db: AsyncSession,
    project_id: str,
    zip_bytes: bytes,
    strategy: ConflictStrategy = "overwrite",
    user: User | None = None,
    *,
    atomicity: AtomicityMode = AtomicityMode.PER_SHEET,
    progress: Any | None = None,
    preflight: Callable[[str, str | None], Any] | None = None,
) -> ImportReport:
    """正式批量导入：align → 门禁 → 快照 → 逐 sheet import → 报告 → 审计日志。

    Args:
        db: 数据库会话（service 只 flush 不 commit）
        project_id: 项目 UUID
        zip_bytes: 上传的 ZIP 文件字节流
        strategy: 冲突策略 "overwrite" / "fill-empty" / "reject"
        user: 操作用户（用于权限判断和审计日志）
        atomicity: 原子性策略 per-sheet / all-or-nothing
        progress: 可选进度回调（SSE 等）

    Returns:
        ImportReport（dry_run=False）

    Requirements: 2.1, 2.2, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 4.1, 4.2
    """
    report = ImportReport(strategy=strategy, dry_run=False)

    # ① ZipReader 解析
    try:
        reader = ZipReader.from_bytes(zip_bytes)
    except (ZipSizeLimitExceeded, ZipManifestMissing) as e:
        report.mark("__zip__", "failed", reason=str(e))
        return report
    except Exception as e:
        report.mark("__zip__", "failed", reason=f"ZIP 解析失败: {e}")
        return report

    # ② SHA256 完整性校验
    try:
        reader.verify_integrity()
    except ZipIntegrityError as e:
        report.mark("__integrity__", "failed", reason=str(e))
        reader.close()
        return report

    manifest = reader.manifest
    manifest_files = manifest.get("files", [])

    # ③ 获取拓扑顺序 sheet 列表（Req 2.2）
    from app.services.wp_bulk_tab_export import list_import_sheets

    cycles = manifest.get("cycles", [])
    topo_sheets: list[dict[str, Any]] = []
    for cycle in cycles:
        sheets = await list_import_sheets(db, project_id, cycle)
        topo_sheets.extend(sheets)

    if not topo_sheets and not cycles:
        inferred_cycles: set[str] = set()
        for mf in manifest_files:
            zp = mf.get("zip_path", "")
            if "/" in zp:
                inferred_cycles.add(zp.split("/")[0])
        for cycle in sorted(inferred_cycles):
            try:
                sheets = await list_import_sheets(db, project_id, cycle)
                topo_sheets.extend(sheets)
            except Exception:
                pass

    # ④ align — 对齐 manifest 与 ZIP（Req 2.8 / 2.9）
    zip_file_list = reader.list_files()
    plan = align(manifest_files, topo_sheets, zip_file_list)

    # ④.5 Task 10 逐资源 gate preflight（Req 8.13/8.14/8.16/9）：在任何副作用（快照/写入）之前
    # 逐资源过 gate；显式任一资源被拒 → 抛 ExternalNotFound（404）→ 整请求失败（原子），
    # 不 fail-soft 跳过、不泄露存在性。worker re-gate 复用此路径（撤权后排队任务被拒）。
    if preflight is not None:
        for item in plan.items:
            if item.missing or not item.wp_id:
                continue
            await preflight(item.wp_id, item.sheet_code)

    # ⑤ 查询底稿状态 + WorkflowGate 分类（Req 9.1）
    wp_ids = [item.wp_id for item in plan.items if item.wp_id]
    statuses = await _get_wp_statuses(db, wp_ids)

    gate = WorkflowGate()
    gate_items = [
        {"wp_id": uuid.UUID(item.wp_id), "status": statuses.get(item.wp_id, "")}
        for item in plan.items
        if item.wp_id
    ]
    classifications = gate.classify(gate_items)

    # 标记 blocked 状态
    for item in plan.items:
        wp_uuid = uuid.UUID(item.wp_id) if item.wp_id else None
        if wp_uuid and wp_uuid in classifications:
            cls = classifications[wp_uuid]
            if cls.classification == "blocked":
                item.blocked = True
                item.block_reason = cls.reason
            item.status = cls.status

    # ⑥ SnapshotGuard 快照（Req 2.4）
    user_id = user.id if user else uuid.UUID(int=0)
    project_uuid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id

    snapshots: list[SnapshotRecord] = []
    writable_wp_ids = plan.writable_wp_ids
    if writable_wp_ids:
        snapshots = await SnapshotGuard.snapshot(
            db,
            writable_wp_ids,
            project_id=project_uuid,
            user_id=user_id,
        )
        report.snapshots = [
            {"wp_id": str(s.wp_id), "snapshot_id": str(s.snapshot_id)}
            for s in snapshots
        ]

    # ⑦ 按拓扑顺序逐 sheet 导入（Req 2.1, 2.2）
    try:
        for item in plan.topo_order():
            # missing 文件跳过（Req 2.8）
            if item.missing:
                report.mark(item.sheet_code, "missing", reason="ZIP 中缺少对应文件")
                if progress:
                    _tick_progress(progress)
                continue

            # blocked 底稿跳过（Req 9.1）
            if item.blocked:
                report.mark(
                    item.sheet_code,
                    "blocked_by_status",
                    reason=item.block_reason,
                )
                if progress:
                    _tick_progress(progress)
                continue

            # under_review → 尝试回退为编制中（Req 4.3 / 9.2）
            wp_uuid = uuid.UUID(item.wp_id) if item.wp_id else None
            if wp_uuid and wp_uuid in classifications:
                cls = classifications[wp_uuid]
                if cls.classification == "revert_needed" and user:
                    reverted = await gate.revert_if_under_review(db, wp_uuid, user)
                    if not reverted:
                        # 无编制权限 → 不改状态不写入（Req 9.3）
                        report.mark(
                            item.sheet_code,
                            "blocked_by_status",
                            reason="under_review_no_permission",
                        )
                        if progress:
                            _tick_progress(progress)
                        continue

            # 从 ZIP 中读取 xlsx
            try:
                xlsx_bytes = reader.get_file(item.zip_path)
            except KeyError:
                report.mark(item.sheet_code, "missing", reason=f"ZIP 中无文件: {item.zip_path}")
                if progress:
                    _tick_progress(progress)
                continue

            # 调用 import_tab（Req 2.1）
            try:
                result = await import_tab(
                    db,
                    item.wp_id,
                    item.api_prefix,
                    item.sheet_code,
                    xlsx_bytes,
                    strategy,
                )
                report.merge(item.sheet_code, result)

                # 失败处理
                if result.status == "failed":
                    if atomicity == AtomicityMode.ALL_OR_NOTHING:
                        # all-or-nothing → 全量回滚
                        raise FatalImportError(
                            f"sheet '{item.sheet_code}' 导入失败（all-or-nothing 模式）"
                        )
                    else:
                        # per-sheet → 回滚该 wp 的快照
                        _snap = _find_snapshot(snapshots, item.wp_id)
                        if _snap:
                            await SnapshotGuard.rollback_single(
                                db,
                                _snap,
                                project_id=project_uuid,
                                user_id=user_id,
                            )

            except FatalImportError:
                raise  # 重新抛出触发回滚

            except KeyError as e:
                # api_prefix 未注册（no_adapter）
                report.mark(item.sheet_code, "skipped", reason=f"no_adapter: {e}")

            except Exception as e:
                # 单 sheet 失败记入报告（fail-soft, Req 2.7）
                logger.warning(
                    "BulkImport: sheet %s import failed: %s",
                    item.sheet_code,
                    e,
                    exc_info=True,
                )
                report.sheets.append(
                    SheetReport(
                        sheet_code=item.sheet_code,
                        status="failed",
                        errors=[str(e)],
                    )
                )

                if atomicity == AtomicityMode.ALL_OR_NOTHING:
                    raise FatalImportError(
                        f"sheet '{item.sheet_code}' 导入异常（all-or-nothing 模式）"
                    ) from e
                else:
                    # per-sheet → 回滚该 wp 的快照
                    _snap = _find_snapshot(snapshots, item.wp_id)
                    if _snap:
                        await SnapshotGuard.rollback_single(
                            db,
                            _snap,
                            project_id=project_uuid,
                            user_id=user_id,
                        )

            if progress:
                _tick_progress(progress)

    except FatalImportError:
        # 回滚到导入前快照（Req 2.4 / 6.2）
        if snapshots:
            await SnapshotGuard.rollback(
                db,
                snapshots,
                project_id=project_uuid,
                user_id=user_id,
            )
        report.mark_all_rolled_back()

    # unlisted 文件记入报告（Req 2.9）
    for path in plan.unlisted_paths:
        report.sheets.append(
            SheetReport(sheet_code=path, status="unlisted", reason="ZIP 中存在但 manifest 未登记")
        )

    # ⑧ 审计日志（Req 4.2）
    if user:
        await _write_import_audit_log(db, user, project_id, report)

    await db.flush()
    reader.close()
    return report


# ---------------------------------------------------------------------------
# Helper: find snapshot by wp_id
# ---------------------------------------------------------------------------


def _find_snapshot(
    snapshots: list[SnapshotRecord], wp_id: str
) -> SnapshotRecord | None:
    """根据 wp_id 查找对应的快照记录。"""
    try:
        wp_uuid = uuid.UUID(wp_id)
    except (ValueError, TypeError):
        return None
    for snap in snapshots:
        if snap.wp_id == wp_uuid:
            return snap
    return None


# ---------------------------------------------------------------------------
# Helper: progress tick
# ---------------------------------------------------------------------------


def _tick_progress(progress: Any) -> None:
    """安全调用进度回调。"""
    try:
        if callable(getattr(progress, "tick", None)):
            progress.tick()
    except Exception:
        pass
