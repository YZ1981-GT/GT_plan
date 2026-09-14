"""storage 根目录解析 —— 备份与备份校验的单一真源。

## 为什么需要这个模块（2026-09-04 实测）

发现一处**备份扫描面与运行时落点不一致**的缺口：

* 后端进程的 cwd 是 ``backend/``（``start-dev.bat``：``cd /d "%BACKEND_DIR%"``），
  而 ``Settings.STORAGE_ROOT`` 默认 ``"./storage"`` 是**相对路径** ⇒ 运行时产物落在
  ``backend/storage/``（实测 2308 个文件 / 655 个子目录，最近写入当天）。
* ``scripts/ops/backup.py`` 的用法是 ``python backend/scripts/ops/backup.py``
  （从仓库根跑）⇒ 同一个 ``"./storage"`` 解析成 ``<repo>/storage``
  （实测 281 个文件，最近写入 2026-09-01，是早年从仓库根启动后端时留下的陈旧目录）。
* ``scripts/check/verify_backup.py`` 更硬编码 ``Path("storage")``，连 ``STORAGE_ROOT``
  都不读。

于是备份**每天都"成功"，备的却是错的目录**，退出码 0。两个脚本各自还有 fail-open
分支把这件事盖住：根不存在 → ``skipped`` 不计入失败；备份里没有 storage 目录 →
``passed: True``。

把根解析收敛到本模块，两个脚本共用，避免第二份口径漂移。

## 为什么不放 ``backend/app/**``

放进 app 会让 ``generate_workpaper_writer_inventory.py`` 等生成器的 freshness
判据连带打红（见 5-lane 分工书规则 3）。备份是运维面而非请求面，脚本共用模块
放 ``backend/scripts/`` 下（既有惯例：``_census_lock.py`` / ``_ensure_custom_query_tables.py``
/ ``_mutation_kit/``）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: ``backend/`` —— 本文件在 ``backend/scripts/`` 下，上两级即后端根。
BACKEND_DIR: Final[Path] = Path(__file__).resolve().parent.parent

#: 仓库根。
REPO_ROOT: Final[Path] = BACKEND_DIR.parent

#: ``Settings.STORAGE_ROOT`` 的默认值，与 ``backend/app/core/config.py`` 保持一致。
#: 这里不 import Settings —— 备份脚本必须能在不加载 app 的环境下跑。
DEFAULT_STORAGE_ROOT: Final[str] = "./storage"


class StorageRootResolutionError(RuntimeError):
    """根解析失败。

    🔴 不设 fail-open：解析不出任何存在的根时必须响亮失败，而不是"跳过文件备份"。
    备份脚本 ``skipped`` 且退出码 0 正是这个缺口能长期无声存在的原因。
    """


@dataclass(frozen=True)
class StorageRoot:
    """一个需要纳入备份扫描面的 storage 根。"""

    path: Path
    #: 备份目录内的子目录名，必须两两不同（否则 copytree 会互相覆盖）。
    label: str
    #: 该根是怎么推导出来的，写进 manifest 便于事后追溯。
    origin: str

    @property
    def exists(self) -> bool:
        return self.path.is_dir()

    def file_count(self) -> int:
        if not self.exists:
            return 0
        return sum(1 for p in self.path.rglob("*") if p.is_file())


def runtime_storage_root() -> Path:
    """后端进程**实际**写入的 storage 根。

    ``STORAGE_ROOT`` 为相对路径时相对 :data:`BACKEND_DIR` 解析 —— 因为后端的 cwd
    是 ``backend/``。这是本模块存在的全部理由，改这一行等于改备份口径。
    """
    raw = os.environ.get("STORAGE_ROOT", DEFAULT_STORAGE_ROOT)
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return (BACKEND_DIR / candidate).resolve()


def legacy_storage_root() -> Path:
    """早年从仓库根启动后端时留下的 storage 根。

    仍含真实历史产物（实测 281 个文件），恢复演练要能拿到，故一并纳入扫描面。
    """
    raw = os.environ.get("STORAGE_ROOT", DEFAULT_STORAGE_ROOT)
    candidate = Path(raw)
    if candidate.is_absolute():
        # 显式给了绝对路径时没有"仓库根相对"这一说，返回同一个路径，由去重摘掉。
        return candidate.resolve()
    return (REPO_ROOT / candidate).resolve()


def _dedupe_and_drop_nested(roots: list[StorageRoot]) -> list[StorageRoot]:
    """去掉重复根与被其它根包含的根。

    ``backend/storage/storage/`` 这类嵌套已在 ``backend/storage/`` 的递归面内，
    单列会导致同一批文件备份两份。
    """
    unique: list[StorageRoot] = []
    seen: set[Path] = set()
    for root in roots:
        if root.path in seen:
            continue
        seen.add(root.path)
        unique.append(root)

    kept: list[StorageRoot] = []
    for root in unique:
        nested_in_other = any(
            other.path != root.path and _is_within(root.path, other.path)
            for other in unique
        )
        if not nested_in_other:
            kept.append(root)
    return kept


def _is_within(child: Path, ancestor: Path) -> bool:
    """``child`` 是否落在 ``ancestor`` 的递归面内（含相等）。"""
    try:
        child.relative_to(ancestor)
    except ValueError:
        return False
    return True


def backup_scan_roots(*, require_existing: bool = True) -> list[StorageRoot]:
    """备份应当扫描的全部 storage 根。

    :param require_existing: 为真时过滤掉不存在的根；全部不存在则抛
        :class:`StorageRootResolutionError`（不 fail-open 成"跳过"）。
    """
    candidates = [
        StorageRoot(
            path=runtime_storage_root(),
            label="storage",
            origin="STORAGE_ROOT relative to backend/ (backend process cwd)",
        ),
        StorageRoot(
            path=legacy_storage_root(),
            label="storage_repo_root_legacy",
            origin="STORAGE_ROOT relative to repo root (legacy产物, 仍需可恢复)",
        ),
    ]
    roots = _dedupe_and_drop_nested(candidates)
    if not require_existing:
        return roots

    existing = [r for r in roots if r.exists]
    if not existing:
        tried = ", ".join(str(r.path) for r in roots)
        raise StorageRootResolutionError(
            f"没有任何 storage 根存在，备份扫描面为空。已尝试：{tried}。"
            "这不是可以跳过的情形 —— 要么 STORAGE_ROOT 配错，要么在错误的机器上跑。"
        )
    return existing


def path_is_covered(target: Path, roots: list[StorageRoot] | None = None) -> bool:
    """``target`` 是否落在备份扫描面内。

    供判据使用：覆盖层根 ``OVERRIDE_ROOT`` 必须为真，否则覆盖层会在恢复时静默丢失。
    """
    scan_roots = roots if roots is not None else backup_scan_roots(require_existing=False)
    resolved = target.resolve()
    return any(_is_within(resolved, root.path) for root in scan_roots)


def describe_scan_roots() -> str:
    """人读的扫描面摘要，供脚本打印与 manifest 记录。"""
    lines = []
    for root in backup_scan_roots(require_existing=False):
        state = "exists" if root.exists else "MISSING"
        lines.append(f"  {root.label}: {root.path} [{state}] ({root.origin})")
    return "\n".join(lines)


__all__ = [
    "BACKEND_DIR",
    "REPO_ROOT",
    "DEFAULT_STORAGE_ROOT",
    "StorageRoot",
    "StorageRootResolutionError",
    "runtime_storage_root",
    "legacy_storage_root",
    "backup_scan_roots",
    "path_is_covered",
    "describe_scan_roots",
]
