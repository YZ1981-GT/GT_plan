"""ACNR Catalog 快照生命周期管理（GC）

职责：
- 保留最近 N 个版本快照 + 所有被项目锁定引用的版本
- 清理无引用的旧版本快照
- 拒绝删除仍被引用的快照并记录 warning
- 运行时入口 run_db_aware_gc：引用集不能从数据库证实即不删；已提交进仓库的快照不删（RV13.1-01）

Requirements: Req-16.1, Req-16.2, Req-16.3

Feature: acnr-runtime-convergence, Task 19
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── 快照目录路径 ─────────────────────────────────────────────────────────────
_CATALOG_SNAPSHOTS_DIR = Path(__file__).resolve().parents[3] / "data" / "acnr" / "catalog_snapshots"
# 与 catalog_contract / Project 模型的版本形态一致；GC 只管理这种明确属于 ACNR 的快照。
# 目录里的说明 JSON、符号链接或临时文件一律不碰，避免名字排序挤占最近 N 份并越过删除边界。
_SNAPSHOT_VERSION_RE = re.compile(r"^\d{14}$")


def _get_snapshots_dir() -> Path:
    """获取快照目录（支持环境变量覆盖，方便测试）。"""
    env_path = os.environ.get("ACNR_SNAPSHOTS_DIR")
    if env_path:
        return Path(env_path)
    return _CATALOG_SNAPSHOTS_DIR


def list_snapshot_versions(snapshots_dir: Path | None = None) -> list[str]:
    """列出快照目录下所有版本号（按字典序降序=最近优先）。

    版本号 = 文件名去掉 .json 后缀（如 "20260715120000"）。
    只包含目录直属、非符号链接、文件名为 14 位时间戳的 .json；说明 JSON / 临时文件不是
    GC 管辖的快照，既不计入最近 N 份，也绝不删除。
    """
    sd = snapshots_dir or _get_snapshots_dir()
    if not sd.exists():
        return []

    versions: list[str] = []
    for f in sd.iterdir():
        if (
            f.suffix == ".json"
            and _SNAPSHOT_VERSION_RE.fullmatch(f.stem)
            and not f.is_symlink()
            and f.is_file()
        ):
            versions.append(f.stem)

    # 降序排列（最新版本在前）
    versions.sort(reverse=True)
    return versions


def compute_versions_to_delete(
    all_versions: list[str],
    referenced_versions: set[str] | None,
    keep_recent: int = 10,
) -> list[str]:
    """计算应被删除的版本列表。

    策略（Req-16.1, Req-16.2, Req-16.3 fail-closed）：
    - 引用集合不可验证（None）→ 返回空列表，不删除任何版本
    - 保留最近 keep_recent 个版本（按字典序降序排列）
    - 保留所有被项目引用的版本
    - 其余版本可安全删除

    Args:
        all_versions: 全部版本列表（降序排列）
        referenced_versions: 被项目锁定引用的版本集合；None 表示不可验证 → fail-closed
        keep_recent: 保留最近版本数（默认 10）

    Returns:
        可删除的版本列表（引用不可验证时恒为空）
    """
    # fail-closed：无法验证引用关系时绝不删除任何快照（Req-16.3）
    if referenced_versions is None:
        return []

    if keep_recent < 0:
        keep_recent = 0

    # 最近 N 个版本（已降序排列取前 N）
    recent_versions = set(all_versions[:keep_recent])

    to_delete: list[str] = []
    for version in all_versions:
        if version in recent_versions:
            continue
        if version in referenced_versions:
            continue
        to_delete.append(version)

    return to_delete


def cleanup_stale_snapshots(
    keep_recent: int = 10,
    *,
    snapshots_dir: Path | None = None,
    referenced_versions: set[str] | None = None,
    protected_versions: frozenset[str] | set[str] = frozenset(),
    dry_run: bool = False,
) -> dict[str, Any]:
    """清理过期快照。

    主入口函数。生成新版本后由 Generator 自动调用。

    Requirements:
        Req-16.1 — 保留最近 N + 被引用版本
        Req-16.2 — 引用计数为 0 且不在最近 N 的快照被安全删除
        Req-16.3 — 被引用版本拒绝删除 + warning

    Args:
        keep_recent: 保留最近版本数（默认 10）
        snapshots_dir: 快照目录路径（默认使用内部路径）
        referenced_versions: 被引用版本集合（None = 不可验证 → fail-closed 不删）
        protected_versions: 无论引用与保留规则如何都不删的版本（运行时清理传「已提交进仓库」的快照，
            见 run_db_aware_gc）；默认空集
        dry_run: 仅计算不实际删除

    Returns:
        清理报告 dict:
        {
            "total_snapshots": int,
            "keep_recent": int,
            "referenced_count": int,
            "deleted": list[str],              # dry-run 时兼容表示 would-delete
            "would_delete": list[str],           # 仅 dry-run 非空
            "already_absent": list[str],
            "failed": list[{version, error}],
            "skipped_referenced": list[str],
            "skipped_protected": list[str],
            "dry_run": bool,
        }
    """
    sd = snapshots_dir or _get_snapshots_dir()
    all_versions = list_snapshot_versions(sd)

    # 调用方必须显式给出经数据库证实的引用集合。None 表示不可验证，fail-closed；
    # 纯文件生成器不会暗中退回旧同步来源。
    refs = referenced_versions
    reference_status = "unverifiable" if refs is None else "verified"

    # 计算应删除的版本（refs 为 None 时恒为空，不删除任何快照）
    to_delete = compute_versions_to_delete(all_versions, refs, keep_recent)

    # 安全校验：再次确认不删除被引用版本（Req-16.3 防御层）
    actually_deleted: list[str] = []
    skipped_referenced: list[str] = []
    skipped_protected: list[str] = []
    already_absent: list[str] = []
    failed: list[dict[str, str]] = []

    for version in to_delete:
        if version in protected_versions:
            skipped_protected.append(version)
            continue
        if refs is not None and version in refs:
            # 不应发生（compute_versions_to_delete 已排除），但作为安全守卫
            logger.warning(
                "catalog_snapshot_gc: 拒绝删除仍被引用的快照 version=%s",
                version,
            )
            skipped_referenced.append(version)
            continue

        if dry_run:
            actually_deleted.append(version)  # 兼容既有报告：dry-run 的 deleted 表示 would-delete
            continue

        snapshot_path = sd / f"{version}.json"
        try:
            snapshot_path.unlink()
        except FileNotFoundError:
            # 另一进程已清理同一散落文件：不是失败，也不能谎报本进程删除成功。
            already_absent.append(version)
        except OSError as exc:
            # 单文件失败不让后续候选失去清理机会；报告必须把失败逐项暴露，禁止部分完成却报全成功。
            logger.error("catalog_snapshot_gc: 删除快照失败 version=%s error=%s", version, exc)
            failed.append({"version": version, "error": f"{type(exc).__name__}: {exc}"})
        else:
            actually_deleted.append(version)
            logger.info("catalog_snapshot_gc: 已删除快照 version=%s", version)

    if reference_status == "unverifiable":
        logger.warning(
            "catalog_snapshot_gc: 引用集合不可验证 → fail-closed，本次不删除任何快照 "
            "(total=%d, keep_recent=%d)",
            len(all_versions), keep_recent,
        )

    report = {
        "total_snapshots": len(all_versions),
        "keep_recent": keep_recent,
        "referenced_count": len(refs) if refs is not None else 0,
        "reference_status": reference_status,
        "deleted": actually_deleted,
        "would_delete": list(actually_deleted) if dry_run else [],
        "already_absent": already_absent,
        "failed": failed,
        "skipped_referenced": skipped_referenced,
        "skipped_protected": skipped_protected,
        "dry_run": dry_run,
    }

    logger.info(
        "catalog_snapshot_gc: total=%d keep_recent=%d referenced=%s deleted=%d skipped=%d dry_run=%s",
        len(all_versions),
        keep_recent,
        len(refs) if refs is not None else "unverifiable",
        len(actually_deleted),
        len(skipped_referenced),
        dry_run,
    )

    return report


# ─── 运行时清理入口（启动任务 / gc_snapshots.py 共用；RV13.1-01 起 fail-closed）────────

#: 会把 git 指向别的仓库 / 索引的环境变量：判「是否已提交」前一律去掉，只按快照目录所在仓库判。
_GIT_REDIRECT_ENV = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


def committed_snapshot_versions(snapshots_dir: Path) -> frozenset[str] | None:
    """快照目录里已登记进仓库（git 索引里有）的快照版本号；判定不了返回 None。

    已提交的快照属于生成器的发布历史：不可变登记（test_catalog_index_fail_closed
    ._SNAPSHOT_CONTENT_SHA256）与已取代清单（test_catalog_schema_single_source）只能登记已提交的
    快照，二者都是测试常量、生产代码不能读，故运行时以 git 索引为准（守卫断言这两份登记都在其中）。
    不在 git 仓库里、没有 git、git 出错或超时 → None，调用方必须当作「全部已登记」一个都不删。
    """
    env = {k: v for k, v in os.environ.items() if k not in _GIT_REDIRECT_ENV}
    try:
        proc = subprocess.run(
            ["git", "-C", str(snapshots_dir), "ls-files", "-z", "--", "."],
            capture_output=True, timeout=10, env=env, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("catalog_snapshot_gc: 无法确认哪些快照已提交进仓库（%s）", exc)
        return None
    if proc.returncode != 0:
        logger.warning(
            "catalog_snapshot_gc: 无法确认哪些快照已提交进仓库（git 退出码 %d）", proc.returncode
        )
        return None
    names = proc.stdout.decode("utf-8", "replace").split("\0")
    return frozenset(n[: -len(".json")] for n in names if n.endswith(".json") and "/" not in n)


async def referenced_registry_versions(db: Any | None) -> set[str] | None:
    """从数据库取被项目锁定的目录版本集合；不能从数据库证实时返回 None（调用方 fail-closed 不删）。

    引用集**只认数据库**（`projects.acnr_registry_version`，V216 落库，T19）：
    - **含软删项目**（不加 `is_deleted` 过滤）—— 软删只是回收站，项目恢复后还要按锁定版本解析，
      它引用的快照现在就不能删。
    - 没有可用会话、查库失败、列还不存在（迁移没跑）→ 返回 None，调用方一个都不删。
      宁可留着多余快照，也不能删掉某个归档项目唯一的解析依据（RV13.1-01）。

    进程内归档字典不作引用来源：它冷启动为空、不跨进程，拿它当引用集等于冷启动时「没有任何引用」。
    """
    if db is None:
        logger.info("catalog_snapshot_gc: 没有可用数据库会话，引用集不可验证 → 不删除")
        return None

    import sqlalchemy as sa

    from app.models.core import Project

    rows = (
        await db.execute(
            sa.select(Project.acnr_registry_version)
            .where(Project.acnr_registry_version.is_not(None))
            .distinct()
        )
    ).all()
    versions = {row[0] for row in rows if row[0]}
    logger.info(
        "catalog_snapshot_gc: 引用集已从数据库证实，%d 个版本被项目锁定", len(versions)
    )
    return versions


async def _referenced_versions_with_own_session(
    operation: Callable[[Any], Awaitable[dict[str, Any]]] | None = None,
) -> set[str] | None | dict[str, Any]:
    """自开短会话，并让可选 ``operation`` 在同一会话生命周期内完成。

    无 ``operation`` 时只返回引用集（保留既有测试 / 诊断入口）。运行时 GC 会传入完整操作，确保
    advisory xact lock 从「查项目引用」一直持有到「删除快照」结束；不能查完引用就先关闭会话，
    否则归档事务可在两步之间写入新锁，形成 TOCTOU。

    开会话、拿锁、查库或执行操作任一步失败都返回 None；调用方据此 fail-closed，一个文件都不删。
    """
    from app.core.database import async_session

    try:
        async with async_session() as db:
            if operation is not None:
                return await operation(db)
            return await referenced_registry_versions(db)
    except Exception as exc:  # noqa: BLE001 — 自开会话失败同样按「不可验证」处理
        logger.warning("catalog_snapshot_gc: 自开短会话执行 DB-aware GC 失败（%s）→ 不删除", exc)
        return None


async def run_db_aware_gc(
    session: Any = None,
    *,
    keep_recent: int = 10,
    dry_run: bool = False,
) -> dict[str, Any]:
    """运行时快照清理入口：启动任务与 CLI 共用。

    三条保证（RV13.1-01 + Task 19 并发复核）：
    1. 引用集只认数据库；查库或锁状态不可验证时 fail-closed，一个文件都不删。
    2. 已提交进仓库的快照一律不删；git 状态判定不了也不删。
    3. 归档写版本锁与本函数共用 PostgreSQL advisory xact lock，并在**同一会话生命周期**内完成
       「取锁 → 查引用 → 判候选 → 删除」。因此不存在查完引用、关会话后才删文件的 TOCTOU。
    """
    from app.services.acnr.snapshot_lifecycle_lock import try_acquire_snapshot_lifecycle_lock

    sd = _get_snapshots_dir()

    def _fail_closed(lock_status: str) -> dict[str, Any]:
        report = cleanup_stale_snapshots(
            keep_recent=keep_recent,
            snapshots_dir=sd,
            referenced_versions=None,
            dry_run=dry_run,
        )
        report["committed_status"] = "unverifiable"
        report["lifecycle_lock_status"] = lock_status
        return report

    async def _within_session(db: Any) -> dict[str, Any]:
        lock_status = await try_acquire_snapshot_lifecycle_lock(db)
        if lock_status not in {"acquired", "not_required"}:
            logger.warning(
                "run_db_aware_gc: 快照生命周期锁状态=%s → fail-closed 不删除",
                lock_status,
            )
            return _fail_closed(lock_status)

        try:
            refs = await referenced_registry_versions(db)
        except Exception as exc:  # noqa: BLE001 — 查询失败不能退化成「已证实无引用」
            logger.warning("run_db_aware_gc: 查库取引用集失败 → fail-closed 不删除: %s", exc)
            refs = None

        committed = committed_snapshot_versions(sd) if refs is not None else None
        if committed is None:
            report = cleanup_stale_snapshots(
                keep_recent=keep_recent,
                snapshots_dir=sd,
                referenced_versions=None,
                dry_run=dry_run,
            )
        else:
            report = cleanup_stale_snapshots(
                keep_recent=keep_recent,
                snapshots_dir=sd,
                referenced_versions=refs,
                protected_versions=committed,
                dry_run=dry_run,
            )
        report["committed_status"] = "verified" if committed is not None else "unverifiable"
        report["lifecycle_lock_status"] = lock_status
        return report

    try:
        if session is not None:
            return await _within_session(session)
        result = await _referenced_versions_with_own_session(_within_session)
        return result if isinstance(result, dict) else _fail_closed("unverifiable")
    except Exception as exc:  # noqa: BLE001 — 任何生命周期异常都按「不可验证」处理
        logger.warning("run_db_aware_gc: 生命周期检查失败 → fail-closed 不删除: %s", exc)
        return _fail_closed("unverifiable")
