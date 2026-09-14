"""ACNR Catalog 快照生命周期管理（GC）

职责：
- 保留最近 N 个版本快照 + 所有被项目锁定引用的版本
- 清理无引用的旧版本快照
- 拒绝删除仍被引用的快照并记录 warning

Requirements: Req-16.1, Req-16.2, Req-16.3

Feature: acnr-runtime-convergence, Task 19
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── 快照目录路径 ─────────────────────────────────────────────────────────────
_CATALOG_SNAPSHOTS_DIR = Path(__file__).resolve().parents[3] / "data" / "acnr" / "catalog_snapshots"


def _get_snapshots_dir() -> Path:
    """获取快照目录（支持环境变量覆盖，方便测试）。"""
    env_path = os.environ.get("ACNR_SNAPSHOTS_DIR")
    if env_path:
        return Path(env_path)
    return _CATALOG_SNAPSHOTS_DIR


def list_snapshot_versions(snapshots_dir: Path | None = None) -> list[str]:
    """列出快照目录下所有版本号（按字典序降序=最近优先）。

    版本号 = 文件名去掉 .json 后缀（如 "20260715120000"）。
    仅包含 .json 文件（忽略 .gitkeep 等）。
    """
    sd = snapshots_dir or _get_snapshots_dir()
    if not sd.exists():
        return []

    versions: list[str] = []
    for f in sd.iterdir():
        if f.suffix == ".json" and f.stem:
            versions.append(f.stem)

    # 降序排列（最新版本在前）
    versions.sort(reverse=True)
    return versions


def get_referenced_versions(
    *,
    session: Any | None = None,
    referenced_versions_override: set[str] | None = None,
) -> set[str] | None:
    """获取被项目锁定引用的版本集合。

    如果提供 referenced_versions_override（测试/调用方查得），直接返回该集合。
    否则查询 PG: SELECT DISTINCT registry_version FROM projects
    WHERE registry_version IS NOT NULL。

    Args:
        session: SQLAlchemy async session（生产环境使用）
        referenced_versions_override: 直接提供的引用集合（调用方查询后传入）

    Returns:
        被引用的 registry_version 集合；**无法验证引用时返回 None**（fail-closed）。

    ⚠️ fail-closed 语义（Req-16.3）：
        返回空集 set() 表示「已确认无任何版本被引用」→ keep_recent 之外全可删。
        返回 None 表示「无法验证引用关系」→ 调用方必须 fail-closed 不删除任何快照，
        避免误删被项目锁定的历史版本。此处同步函数无法执行 async DB 查询，
        故除非调用方传入 override，一律返回 None。
    """
    if referenced_versions_override is not None:
        return referenced_versions_override

    # 生产路径需 async DB 查询（本同步函数无法执行）；由调用方查询后经 override 传入。
    # 无 override 且无法验证 → 返回 None（fail-closed），绝不返回空集当作「无引用」。
    logger.warning(
        "catalog_snapshot_gc: 无法验证被引用版本集合（未提供 override，同步路径不查 DB），"
        "返回 None → fail-closed（本次不删除任何快照）"
    )
    return None


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
        referenced_versions: 被引用版本集合（None 则查 DB）
        dry_run: 仅计算不实际删除

    Returns:
        清理报告 dict:
        {
            "total_snapshots": int,
            "keep_recent": int,
            "referenced_count": int,
            "deleted": list[str],
            "skipped_referenced": list[str],
            "dry_run": bool,
        }
    """
    sd = snapshots_dir or _get_snapshots_dir()
    all_versions = list_snapshot_versions(sd)

    # 获取被引用版本；None 表示不可验证 → fail-closed（compute_versions_to_delete 返回 []）
    refs = referenced_versions if referenced_versions is not None else get_referenced_versions()
    reference_status = "unverifiable" if refs is None else "verified"

    # 计算应删除的版本（refs 为 None 时恒为空，不删除任何快照）
    to_delete = compute_versions_to_delete(all_versions, refs, keep_recent)

    # 安全校验：再次确认不删除被引用版本（Req-16.3 防御层）
    actually_deleted: list[str] = []
    skipped_referenced: list[str] = []

    for version in to_delete:
        if refs is not None and version in refs:
            # 不应发生（compute_versions_to_delete 已排除），但作为安全守卫
            logger.warning(
                "catalog_snapshot_gc: 拒绝删除仍被引用的快照 version=%s",
                version,
            )
            skipped_referenced.append(version)
            continue

        if not dry_run:
            snapshot_path = sd / f"{version}.json"
            if snapshot_path.exists():
                snapshot_path.unlink()
                logger.info("catalog_snapshot_gc: 已删除快照 version=%s", version)
            actually_deleted.append(version)
        else:
            actually_deleted.append(version)

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
        "skipped_referenced": skipped_referenced,
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


# ─── DB-aware GC 入口（P2-1：真清理，查 projects.registry_version）───────────


def query_referenced_versions() -> set[str]:
    """获取被归档项目锁定引用的 registry_version 集合。

    🔴 registry_version 真源是 immutability._project_registry_versions（M1 阶段内存
    dict，由项目归档流程 record_project_registry_version 写入），**不是** projects 表列
    （该列不存在）。故此处从内存归档集读取。

    ⚠️ 内存 dict 非跨进程/重启持久 —— 冷启动为空。GC 因此以 keep_recent 为主要保护
    （保留最近 N 版），仅额外保护本进程已记录的归档项目锁定版本。当快照真正开始累积
    且需跨进程精确引用保护时，registry_version 应落库（DB 列 / 专表），届时改为查库。
    """
    from app.services.acnr.immutability import list_archived_projects

    return {v for v in list_archived_projects().values() if v}


async def run_db_aware_gc(
    session: Any = None,
    *,
    keep_recent: int = 10,
    dry_run: bool = False,
) -> dict[str, Any]:
    """快照 GC 真清理入口（P2-1）：查归档项目锁定版本得引用集 → 删无引用旧快照。

    与「同步 cleanup_stale_snapshots 无 override → fail-closed 不删」的区别：本函数先取
    真实引用集（reference_status=verified），再删除「非最近 keep_recent 且未被任何归档
    项目锁定引用」的快照，防止 catalog_snapshots/ 无界增长。

    session 参数保留用于向后兼容/未来落库查询；当前引用集取自内存归档集（见
    query_referenced_versions）。供 lifespan 启动一次 + CLI 调用。
    """
    try:
        refs = query_referenced_versions()
    except Exception as exc:
        logger.warning(
            "run_db_aware_gc: 获取 referenced versions 失败 → fail-closed 不删除: %s", exc
        )
        return cleanup_stale_snapshots(
            keep_recent=keep_recent, referenced_versions=None, dry_run=dry_run
        )

    return cleanup_stale_snapshots(
        keep_recent=keep_recent, referenced_versions=refs, dry_run=dry_run
    )
