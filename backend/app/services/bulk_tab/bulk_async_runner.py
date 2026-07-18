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
import logging
from pathlib import Path
from uuid import UUID

from app.core.database import async_session as async_session_factory
from app.models.core import User
from app.services.bulk_tab.bulk_progress import bulk_progress_service
from app.services.bulk_tab.snapshot_guard import AtomicityMode

logger = logging.getLogger(__name__)

# 异步导出 ZIP 落地目录
BULK_EXPORT_DIR = Path("storage") / "bulk_exports"

# 持有后台 task 强引用，避免 asyncio.create_task 的 task 被 GC 回收
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task | None:
    """调度后台协程并登记强引用；无 running loop（测试环境）时同步失败返回 None。"""
    try:
        task = asyncio.create_task(coro)
    except RuntimeError:
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


def schedule_import(
    *,
    project_id: UUID,
    zip_bytes: bytes,
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
    _spawn(
        _run_import(
            task.task_id,
            project_id=project_id,
            zip_bytes=zip_bytes,
            strategy=strategy,
            atomicity=atomicity,
            user_id=user_id,
            username=username,
            role_value=role_value,
        )
    )
    return task.task_id


async def _run_import(
    task_id: str,
    *,
    project_id: UUID,
    zip_bytes: bytes,
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

            _reader = ZipReader.from_bytes(zip_bytes)
            _files = _reader.manifest.get("files", [])
            bulk_progress_service.set_total(task_id, len(_files))
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
