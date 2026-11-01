"""BulkAsyncRunner — 大项目异步批量导出/导入后台任务（Req 6.1, 6.2, 4.2）

Task 9.1：大项目批量导出/导入改为「触发即返回 task_id → 后台跑 → SSE 推进度」，
避免大项目在请求线程内长时间阻塞 asyncpg pool。

连接铁律（呼应 memory「SSE 不占 asyncpg pool」+ consol_refresh_job_service 范式）：
  - 后台 worker 用**自己的 db session**（``async_session_factory()``），
    绝不复用请求 session（请求返回 task_id 后其 session 已关闭）。
  - 进度经 ``bulk_progress_service``（内存状态 + SSE 队列 fan-out），不持有数据库连接。
  - ``asyncio.create_task`` 的 task 引用存入模块级集合，避免被 GC 回收（已知陷阱）。

结果落地：
  - 导出：ZIP 写到 ``storage/bulk_exports/{task_id}.zip``，经 GET /export/{task_id}/download 下载。
  - 导入：ImportReport 存内存 task.result，经 GET /import/{task_id}/result 查询；
    all-or-nothing 由 ``AtomicityMode`` 控制（Req 4.2）。

Requirements: 6.1, 6.2, 4.2
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile

from app.core.database import async_session as async_session_factory
from app.models.core import User
from app.services.bulk_tab.bulk_progress import bulk_progress_service
from app.services.bulk_tab.snapshot_guard import AtomicityMode

logger = logging.getLogger(__name__)

# 异步导出/导入文件目录
BULK_EXPORT_DIR = Path("storage") / "bulk_exports"
BULK_IMPORT_DIR = Path("storage") / "bulk_imports"

# 单 worker 的临时 admission control。批 B 会迁移为跨进程 durable job 配额；在此之前，
# 先阻止同一进程无限接收 500MB spool。每个上传线程只保留一个 1MiB chunk。
BULK_IMPORT_COPY_CHUNK_BYTES = 1024 * 1024
BULK_IMPORT_GLOBAL_LIMIT = max(1, int(os.getenv("BULK_IMPORT_GLOBAL_LIMIT", "4")))
BULK_IMPORT_USER_LIMIT = max(1, int(os.getenv("BULK_IMPORT_USER_LIMIT", "2")))
BULK_IMPORT_PROJECT_LIMIT = max(1, int(os.getenv("BULK_IMPORT_PROJECT_LIMIT", "2")))
BULK_IMPORT_SPOOL_BUDGET_BYTES = max(
    500 * 1024 * 1024,
    int(os.getenv("BULK_IMPORT_SPOOL_BUDGET_BYTES", str(2 * 1024**3))),
)
BULK_IMPORT_RETRY_AFTER_SECONDS = max(
    1, int(os.getenv("BULK_IMPORT_RETRY_AFTER_SECONDS", "15"))
)


@dataclass(frozen=True)
class _ImportReservation:
    project_id: UUID
    user_id: UUID
    reserved_bytes: int
    created_at: float = field(default_factory=time.perf_counter)


_IMPORT_RESERVATIONS: dict[Path, _ImportReservation] = {}
_IMPORT_ADMISSION_LOCK = asyncio.Lock()

try:
    from prometheus_client import Gauge
except ImportError:  # pragma: no cover
    class Gauge:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass


BULK_IMPORT_ACTIVE = Gauge(
    "bulk_import_active_spools",
    "Accepted bulk imports still uploading or executing in this worker",
)
BULK_IMPORT_RESERVED_BYTES = Gauge(
    "bulk_import_reserved_spool_bytes",
    "Conservative spool bytes reserved by active bulk imports",
)
BULK_IMPORT_OLDEST_AGE_SECONDS = Gauge(
    "bulk_import_oldest_active_age_seconds",
    "Age of the oldest active bulk import in this worker",
)


def _refresh_import_metrics() -> None:
    active = list(_IMPORT_RESERVATIONS.values())
    now = time.perf_counter()
    BULK_IMPORT_ACTIVE.set(len(active))
    BULK_IMPORT_RESERVED_BYTES.set(sum(item.reserved_bytes for item in active))
    BULK_IMPORT_OLDEST_AGE_SECONDS.set(
        max((now - item.created_at for item in active), default=0.0)
    )

# 持有后台 task 强引用，避免 asyncio.create_task 的 task 被 GC 回收
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task | None:
    """调度后台协程并登记强引用；无 running loop（测试环境）时同步失败返回 None。"""
    try:
        task = asyncio.create_task(coro)
    except RuntimeError:
        close = getattr(coro, "close", None)
        if close is not None:
            close()
        logger.warning("bulk async task scheduled outside event loop")
        return None
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


# ---------------------------------------------------------------------------
# 异步导出
# ---------------------------------------------------------------------------


def schedule_export(
    *,
    project_id: UUID,
    cycles: list[str] | None,
    mode: str,
    only_with_data: bool,
    exported_by: str,
    platform_version: str,
    audit_year: int,
    user_id: str,
    filename: str,
    password: str | None = None,
    incremental: bool = False,
) -> str:
    """创建导出任务并调度后台 worker，立即返回 task_id（Req 6.1）。"""
    task = bulk_progress_service.create_task(
        project_id=str(project_id),
        user_id=str(user_id),
        operation=f"export-{mode}",
        total=0,
    )
    _spawn(
        _run_export(
            task.task_id,
            project_id=project_id,
            cycles=cycles,
            mode=mode,
            only_with_data=only_with_data,
            exported_by=exported_by,
            platform_version=platform_version,
            audit_year=audit_year,
            filename=filename,
            user_id=str(user_id),
            password=password,
            incremental=incremental,
        )
    )
    return task.task_id


async def _run_export(
    task_id: str,
    *,
    project_id: UUID,
    cycles: list[str] | None,
    mode: str,
    only_with_data: bool,
    exported_by: str,
    platform_version: str,
    audit_year: int,
    filename: str,
    user_id: str | None = None,
    password: str | None = None,
    incremental: bool = False,
) -> None:
    """后台 worker：用自有 session 跑 bulk_export_service.export，进度经 SSE 推。

    Task 10（Req 8.16 / 16.17）：worker 在 **实际执行时** 用自有 session 重新 gate（re-gate），
    manifest 仅由此刻可见集构建；排队期间被撤权则不可见底稿不进入导出。
    """
    from sqlalchemy import select

    from app.services.bulk_tab import bulk_export_service
    from app.services.bulk_tab.manifest_builder import build_manifest
    from app.services.wp_visibility.entry_integration import make_bulk_visible_filter

    try:
        async with async_session_factory() as db:
            # worker 自有 session：重载 User 以在执行时 re-gate（请求 session 已关闭）
            _user = None
            if user_id:
                _user = (
                    await db.execute(select(User).where(User.id == UUID(user_id)))
                ).scalar_one_or_none()
            visible_filter = (
                make_bulk_visible_filter(db, _user, entry_kind="worker")
                if _user is not None
                else None
            )
            # 预建 manifest 以获知 total（ACNR 内存目录读取，代价低）
            try:
                manifest = await build_manifest(
                    db=db,
                    project_id=project_id,
                    cycles=cycles,
                    mode=mode,  # type: ignore[arg-type]
                    exported_by=exported_by,
                    platform_version=platform_version,
                    audit_year=audit_year,
                )
                bulk_progress_service.set_total(task_id, len(manifest.exportable()))
                # Task 4（R3 · Req 8.16）：记录本次导出的可见底稿 wp_id 集合，供下载端 re-gate。
                # manifest 只由可见集构建（bulk_export_service.export 应用 visible_filter）；此处
                # 以同一 visible_filter 复核，得到实际进入 ZIP 的可见 wp 集合。
                _exportable = manifest.exportable()
                if visible_filter is not None:
                    _visible_ids = [
                        f.wp_id for f in _exportable
                        if f.wp_id and await visible_filter(f.wp_id, None)
                    ]
                else:
                    _visible_ids = [f.wp_id for f in _exportable if f.wp_id]
                bulk_progress_service.set_wp_ids(task_id, _visible_ids)
            except Exception:
                # total 仅用于进度显示，失败不阻断导出
                logger.debug("bulk async export: manifest 预建计数失败", exc_info=True)

            progress = bulk_progress_service.make_progress_callback(task_id)
            zip_buffer = await bulk_export_service.export(
                db=db,
                project_id=project_id,
                cycles=cycles,
                mode=mode,  # type: ignore[arg-type]
                only_with_data=only_with_data,
                exported_by=exported_by,
                platform_version=platform_version,
                audit_year=audit_year,
                progress=progress,
                visible_filter=visible_filter,
                password=password,
                incremental=incremental,
            )

        # 写盘（会话已关闭，纯 IO）
        BULK_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = BULK_EXPORT_DIR / f"{task_id}.zip"
        zip_buffer.seek(0)
        out_path.write_bytes(zip_buffer.read())

        bulk_progress_service.set_result_path(task_id, str(out_path), filename)
        bulk_progress_service.complete(task_id, "导出完成")
        logger.info("bulk async export 完成 task=%s file=%s", task_id, out_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("bulk async export 失败 task=%s", task_id)
        bulk_progress_service.fail(task_id, str(exc))


# ---------------------------------------------------------------------------
# 异步导入
# ---------------------------------------------------------------------------


def _capacity_error(reason: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={"reason": reason, "message": message},
        headers={"Retry-After": str(BULK_IMPORT_RETRY_AFTER_SECONDS)},
    )


def _orphan_spool_bytes(root: Path, reserved_paths: set[Path]) -> int:
    """统计不属于本进程活动 reservation 的残留 ZIP。"""
    total = 0
    if not root.exists():
        return total
    for path in root.rglob("*.zip"):
        if path in reserved_paths:
            continue
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


async def _reserve_import_spool(
    path: Path,
    *,
    project_id: UUID,
    user_id: UUID,
    reserved_bytes: int,
) -> None:
    """原子检查全局/用户/项目槽位及 spool 预算并占位。"""
    async with _IMPORT_ADMISSION_LOCK:
        active = list(_IMPORT_RESERVATIONS.values())
        if len(active) >= BULK_IMPORT_GLOBAL_LIMIT:
            raise _capacity_error(
                "bulk_import_global_limit",
                "批量导入任务已满，请稍后重试",
            )
        if sum(item.user_id == user_id for item in active) >= BULK_IMPORT_USER_LIMIT:
            raise _capacity_error(
                "bulk_import_user_limit",
                "您已有过多批量导入任务，请等待现有任务完成后重试",
            )
        if (
            sum(item.project_id == project_id for item in active)
            >= BULK_IMPORT_PROJECT_LIMIT
        ):
            raise _capacity_error(
                "bulk_import_project_limit",
                "当前项目已有过多批量导入任务，请稍后重试",
            )

        reserved_total = sum(item.reserved_bytes for item in active)
        orphan_bytes = await asyncio.to_thread(
            _orphan_spool_bytes,
            BULK_IMPORT_DIR,
            set(_IMPORT_RESERVATIONS),
        )
        if (
            orphan_bytes + reserved_total + reserved_bytes
            > BULK_IMPORT_SPOOL_BUDGET_BYTES
        ):
            raise _capacity_error(
                "bulk_import_spool_budget",
                "批量导入暂存空间不足，请稍后重试",
            )

        _IMPORT_RESERVATIONS[path] = _ImportReservation(
            project_id=project_id,
            user_id=user_id,
            reserved_bytes=reserved_bytes,
        )
        _refresh_import_metrics()


def _release_import_reservation_now(path: Path) -> None:
    """仅供同步调度失败出口释放尚未交给 worker 的占位。"""
    _IMPORT_RESERVATIONS.pop(path, None)
    _refresh_import_metrics()


async def release_import_reservation(path: Path) -> None:
    """spool 已交给 DB 耐久任务后，仅释放本进程上传 admission，不删文件。"""
    async with _IMPORT_ADMISSION_LOCK:
        _IMPORT_RESERVATIONS.pop(path, None)
        _refresh_import_metrics()


async def cleanup_import_spool(path: Path) -> None:
    """删除 spool 并释放 admission 占位；所有终态出口共用。"""
    try:
        await asyncio.to_thread(path.unlink, missing_ok=True)
    finally:
        async with _IMPORT_ADMISSION_LOCK:
            _IMPORT_RESERVATIONS.pop(path, None)
            _refresh_import_metrics()


def get_import_capacity_snapshot() -> dict[str, int | float]:
    """返回单 worker admission 状态，供指标/健康检查采集。"""
    active = list(_IMPORT_RESERVATIONS.values())
    now = time.perf_counter()
    return {
        "active": len(active),
        "oldest_active_age_seconds": max(
            (now - item.created_at for item in active),
            default=0.0,
        ),
        "global_limit": BULK_IMPORT_GLOBAL_LIMIT,
        "copy_chunk_bytes": BULK_IMPORT_COPY_CHUNK_BYTES,
        "max_copy_memory_bytes": BULK_IMPORT_GLOBAL_LIMIT
        * BULK_IMPORT_COPY_CHUNK_BYTES,
        "reserved_spool_bytes": sum(item.reserved_bytes for item in active),
        "spool_budget_bytes": BULK_IMPORT_SPOOL_BUDGET_BYTES,
    }


def hash_spool_file(path: Path) -> tuple[str, int]:
    """流式计算 spool 摘要，幂等重放和 worker 防篡改共用。"""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(BULK_IMPORT_COPY_CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _copy_upload_to_spool(source, temporary: Path, final: Path, max_bytes: int) -> int:
    """在线程中流式复制 UploadFile.file；不把完整 ZIP 读入 Python bytes。"""
    size = 0
    prefix = b""
    try:
        with temporary.open("wb") as target:
            while True:
                chunk = source.read(BULK_IMPORT_COPY_CHUNK_BYTES)
                if not chunk:
                    break
                if not prefix:
                    prefix = bytes(chunk[:4])
                size += len(chunk)
                if size > max_bytes:
                    raise OverflowError(size)
                target.write(chunk)
        if size == 0:
            raise ValueError("上传文件为空")
        if not prefix.startswith(b"PK"):
            raise ValueError("上传文件不是有效 ZIP")
        temporary.replace(final)
        return size
    except BaseException:
        temporary.unlink(missing_ok=True)
        final.unlink(missing_ok=True)
        raise


async def spool_import_upload(file: UploadFile, *, project_id: UUID, user_id: UUID) -> Path:
    """把异步导入上传流落到受控 spool，任务只捕获路径。"""
    from app.services.bulk_tab.zip_handler import DEFAULT_MAX_TOTAL_ZIP_SIZE

    root = BULK_IMPORT_DIR / str(project_id)
    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
    token = f"{user_id}-{uuid4().hex}"
    final = root / f"{token}.zip"
    temporary = root / f".{token}.tmp"
    try:
        await _reserve_import_spool(
            final,
            project_id=project_id,
            user_id=user_id,
            reserved_bytes=DEFAULT_MAX_TOTAL_ZIP_SIZE,
        )
        await file.seek(0)
        await asyncio.to_thread(
            _copy_upload_to_spool,
            file.file,
            temporary,
            final,
            DEFAULT_MAX_TOTAL_ZIP_SIZE,
        )
    except OverflowError as exc:
        await cleanup_import_spool(final)
        raise HTTPException(status_code=413, detail="ZIP 文件超过 500MB 限制") from exc
    except ValueError as exc:
        await cleanup_import_spool(final)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        await cleanup_import_spool(final)
        raise
    except Exception as exc:
        await cleanup_import_spool(final)
        raise HTTPException(status_code=400, detail=f"文件读取失败: {exc}") from exc
    finally:
        await file.close()
    return final


def schedule_import(
    *,
    project_id: UUID,
    zip_bytes: bytes | Path,
    strategy: str,
    atomicity: AtomicityMode,
    user_id: UUID,
    username: str,
    role_value: str,
) -> str:
    """创建导入任务并调度后台 worker，立即返回 task_id（Req 6.1, 4.2）。"""
    task = bulk_progress_service.create_task(
        project_id=str(project_id),
        user_id=str(user_id),
        operation="import",
        total=0,
    )
    worker = _run_import(
        task.task_id,
        project_id=project_id,
        zip_bytes=zip_bytes,
        strategy=strategy,
        atomicity=atomicity,
        user_id=user_id,
        username=username,
        role_value=role_value,
    )
    if _spawn(worker) is None:
        if isinstance(zip_bytes, Path):
            try:
                zip_bytes.unlink(missing_ok=True)
            except OSError:
                logger.warning(
                    "bulk import spool cleanup failed after scheduling failure: %s",
                    zip_bytes,
                    exc_info=True,
                )
            finally:
                _release_import_reservation_now(zip_bytes)
        bulk_progress_service.fail(task.task_id, "后台导入任务调度失败")
    return task.task_id


async def _run_import(
    task_id: str,
    *,
    project_id: UUID,
    zip_bytes: bytes | Path,
    strategy: str,
    atomicity: AtomicityMode,
    user_id: UUID,
    username: str,
    role_value: str,
) -> None:
    """后台 worker：用自有 session 跑 bulk_import_service.run，成功后 commit。"""
    from sqlalchemy import select

    from app.services.bulk_tab import bulk_import_service

    try:
        # 预读 ZIP manifest 以获知 total（不占 asyncpg，纯内存解析）
        try:
            from app.services.bulk_tab.zip_handler import ZipReader

            _reader = (
                ZipReader.from_path(zip_bytes)
                if isinstance(zip_bytes, Path)
                else ZipReader.from_bytes(zip_bytes)
            )
            try:
                _files = _reader.manifest.get("files", [])
                bulk_progress_service.set_total(task_id, len(_files))
            finally:
                _reader.close()
        except Exception:
            logger.debug("bulk async import: manifest 预读计数失败", exc_info=True)

        async with async_session_factory() as db:
            # worker 自有 session，需重新加载 User（请求 session 已关闭）
            user = (
                await db.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()
            if user is None:
                bulk_progress_service.fail(task_id, "用户不存在")
                return

            progress = bulk_progress_service.make_progress_callback(task_id)
            # Task 10（Req 8.16 / 16.17）：worker 执行时 re-gate 每个目标底稿；排队期间被撤权 →
            # preflight 抛 ExternalNotFound（副作用前）→ 本 worker 捕获 → 任务失败（排队任务被拒）。
            from app.services.wp_visibility.entry_integration import make_bulk_preflight

            preflight = make_bulk_preflight(db, user, entry_kind="worker")
            report = await bulk_import_service.run(
                db=db,
                project_id=str(project_id),
                zip_bytes=zip_bytes,
                strategy=strategy,  # type: ignore[arg-type]
                user=user,
                atomicity=atomicity,
                progress=progress,
                preflight=preflight,
            )
            # service 只 flush 不 commit → worker 负责 commit
            await db.commit()

        bulk_progress_service.set_result(task_id, report.to_dict())
        bulk_progress_service.complete(task_id, "导入完成")
        logger.info(
            "bulk async import 完成 task=%s summary=%s", task_id, report.summary
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("bulk async import 失败 task=%s", task_id)
        bulk_progress_service.fail(task_id, str(exc))
    finally:
        if isinstance(zip_bytes, Path):
            await cleanup_import_spool(zip_bytes)
