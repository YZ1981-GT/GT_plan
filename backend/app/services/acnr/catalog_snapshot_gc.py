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
import subprocess
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
            "deleted": list[str],
            "skipped_referenced": list[str],
            "skipped_protected": list[str],
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
    skipped_protected: list[str] = []

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

    T17 落库之前 projects 没有锁定列，引用集无从查证，故恒返回 None。进程内归档字典
    （immutability._project_registry_versions）冷启动为空、不跨进程，不作引用来源（RV13.1-01）。
    T19 在此补查库（projects.acnr_registry_version，含软删）；查库失败、没有可用会话仍须返回 None。
    """
    logger.info("catalog_snapshot_gc: projects 尚无目录版本锁定列（T17 前），引用集不可验证")
    return None


async def run_db_aware_gc(
    session: Any = None,
    *,
    keep_recent: int = 10,
    dry_run: bool = False,
) -> dict[str, Any]:
    """运行时快照清理入口：启动任务 `_task_acnr_catalog_snapshot_gc` 与 gc_snapshots.py 都走这里。

    两条保证（RV13.1-01，design §8.4）：
    1. fail-closed：引用集只认数据库（referenced_registry_versions）；返回 None 或抛错 → 一个都不删。
    2. 已提交进仓库的快照一律不删（committed_snapshot_versions）；判定不了哪些已提交 → 一个都不删。
       已提交快照的保留与删除只经生成器发布流程（git 提交，同时改两份登记）处理。
    其余（未提交的散落快照）在引用集已证实时按 keep_recent + 未被引用的规则清理。
    """
    sd = _get_snapshots_dir()
    try:
        refs = await referenced_registry_versions(session)
    except Exception as exc:  # noqa: BLE001 — 任何查库异常都按「不可验证」处理
        logger.warning("run_db_aware_gc: 查库取引用集失败 → fail-closed 不删除: %s", exc)
        refs = None

    committed = committed_snapshot_versions(sd) if refs is not None else None
    if committed is None:
        report = cleanup_stale_snapshots(
            keep_recent=keep_recent, snapshots_dir=sd, referenced_versions=None, dry_run=dry_run
        )
    else:
        report = cleanup_stale_snapshots(
            keep_recent=keep_recent, snapshots_dir=sd, referenced_versions=refs,
            protected_versions=committed, dry_run=dry_run,
        )
    report["committed_status"] = "verified" if committed is not None else "unverifiable"
    return report
