"""项目锁定的 ACNR 地址目录版本 —— 落库的版本锁（T17 / design §8.3 / 需求 7.1~7.2）。

为什么要落库：原先锁定只记在 `immutability._project_registry_versions`（进程内字典），
进程一重启就全丢，归档项目在目录升级后会按**新**目录解析，归档时的底稿地址对不回去。
段四审计据此把「resolver 支持版本锁定」与「归档项目已可复现」分开判：前者成立、后者不成立。
本模块把锁写进 `projects.acnr_registry_version` / `acnr_registry_locked_at`（V214）。

三条口径：

1. **锁之前先验快照**：版本号就是快照文件名，锁上了却找不到快照 = 归档项目再也解析不出地址，
   而那时已经晚了。所以 `lock_project_registry` 先确认快照存在、内容自洽（文件名与内里的
   `registry_version` 一致），锁当前版本时还要与报告 `release.catalog_sha256` 对上；
   任一条不成立就抛 `RegistryLockError`，**不落库**（归档路由据此回滚，见 T18）。
2. **幂等**：重复锁同一版本直接返回，不重写时间戳。已锁到**别的**版本则拒绝 ——
   换锁必须先 `unlock_project_registry`（取消归档会做），否则就是静默改写历史锁。
3. **不伪造**：存量项目一律 NULL（未锁定），按当前目录解析。归档时没记过版本，编不出真实值。

`RegistryLockError` 继承 `CatalogLoadError`（**不**继承 ValueError）：归档路由对 ValueError
有一层 400 的兜底处理，会把它抢先吃掉；目录类错误要走 §8 的 409 映射（R2-N4）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from app.services.acnr import reasons
from app.services.acnr.catalog import CatalogLoadError, get_catalog
from app.services.acnr.catalog_integrity import content_sha256

logger = logging.getLogger(__name__)

#: 版本号形态（与 `catalog_contract.REGISTRY_VERSION_PATTERN`、模型层校验同一形态；
#: 三处一致由 `backend/tests/acnr/test_project_registry_lock_schema.py` 逐字比对）
_VERSION_RE = r"^\d{14}$"

#: `db.info` 里缓存已查过的锁的键前缀（请求级记忆：同一请求内多次解析不重复查库）
_MEMO_KEY = "acnr_locked_version"


class RegistryLockError(CatalogLoadError):
    """版本锁写不下去 / 锁定的版本不可用。

    `code` ∈ ``snapshot_missing`` / ``snapshot_invalid`` / ``lock_failed``，
    与 `app/main.py` 的 409 映射一一对应；`message` 是面向用户的中文说明。
    """

    def __init__(self, code: str, message: str, *, version: str | None = None) -> None:
        self.code = code
        self.message = message
        self.version = version
        super().__init__(message)


def _snapshots_dir() -> Path:
    """快照目录（与快照清理同一入口，支持 ACNR_SNAPSHOTS_DIR 覆盖，便于测试）。"""
    from app.services.acnr.catalog_snapshot_gc import _get_snapshots_dir

    return _get_snapshots_dir()


def _release_catalog_sha256() -> str | None:
    """当前报告 release 段登记的目录内容哈希；没有报告或没有该字段时返回 None。"""
    report = _snapshots_dir().parent / "catalog_report.json"
    try:
        data = json.loads(report.read_bytes().decode("utf-8"))
    except (OSError, ValueError):
        return None
    value = (data.get("release") or {}).get("catalog_sha256")
    return value if isinstance(value, str) and value else None


def verify_snapshot(version: str) -> None:
    """确认该版本的快照可用；不可用即抛 `RegistryLockError`（不写库）。

    判三件事：文件在、内容能解析且文件名与内里版本号一致、锁当前版本时与报告哈希对上。
    """
    import re

    if not version or not re.fullmatch(_VERSION_RE, str(version).strip()):
        raise RegistryLockError(
            "lock_failed",
            reasons.REGISTRY_LOCK_FAILED.format(
                detail=f"版本号 {version!r} 不是 14 位 UTC 时间戳"
            ),
            version=version,
        )

    path = _snapshots_dir() / f"{version}.json"
    if not path.is_file():
        raise RegistryLockError(
            "snapshot_missing",
            reasons.REGISTRY_SNAPSHOT_MISSING.format(version=version),
            version=version,
        )

    raw = path.read_bytes()
    try:
        snapshot = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RegistryLockError(
            "snapshot_invalid",
            reasons.REGISTRY_SNAPSHOT_INVALID.format(version=version, detail=f"无法解析（{exc}）"),
            version=version,
        ) from exc

    inner = snapshot.get("registry_version")
    if inner != version:
        raise RegistryLockError(
            "snapshot_invalid",
            reasons.REGISTRY_SNAPSHOT_INVALID.format(
                version=version, detail=f"快照内记的版本是 {inner!r}，与文件名不一致"
            ),
            version=version,
        )

    # 锁的是当前版本时，再与报告登记的目录哈希对一次：快照必须就是这一版发布出去的那份目录
    try:
        current = get_catalog().registry_version
    except CatalogLoadError:
        current = None
    if current and version == current:
        expected = _release_catalog_sha256()
        actual = content_sha256(raw)
        if expected and expected != actual:
            raise RegistryLockError(
                "snapshot_invalid",
                reasons.REGISTRY_SNAPSHOT_INVALID.format(
                    version=version,
                    detail=f"内容哈希与报告登记不一致（报告 {expected[:12]}…，快照 {actual[:12]}…）",
                ),
                version=version,
            )


async def lock_project_registry(
    db: Any,
    project_id: str | UUID,
    *,
    version: str | None = None,
) -> str:
    """把项目锁定到某一目录版本并落库（幂等）。返回锁定的版本号。

    - `version` 缺省 = 当前目录版本。
    - 锁之前先验快照；验不过抛 `RegistryLockError`，**不写库**（调用方据此回滚整个归档）。
    - 已锁到同一版本 → 直接返回，不重写时间戳。
    - 已锁到别的版本 → 抛 `lock_failed`（换锁必须先解锁，避免静默改写历史锁）。

    只 flush 不 commit：由路由在同一事务里统一提交。
    """
    from app.models.core import Project

    target = (version or "").strip() or None
    if target is None:
        try:
            target = get_catalog().registry_version
        except CatalogLoadError as exc:
            raise RegistryLockError(
                "lock_failed",
                reasons.REGISTRY_LOCK_FAILED.format(detail=f"当前目录不可用（{exc}）"),
            ) from exc

    verify_snapshot(target)

    pid = str(project_id)
    row = (
        await db.execute(
            sa.select(Project.acnr_registry_version).where(Project.id == _as_uuid(pid))
        )
    ).first()
    if row is None:
        raise RegistryLockError(
            "lock_failed",
            reasons.REGISTRY_LOCK_FAILED.format(detail=f"项目 {pid} 不存在"),
            version=target,
        )

    existing = row[0]
    if existing:
        if existing == target:
            _memo(db)[pid] = target  # 幂等：不重写时间戳
            return target
        raise RegistryLockError(
            "lock_failed",
            reasons.REGISTRY_LOCK_FAILED.format(
                detail=f"项目已锁定到版本 {existing}，换锁请先取消归档（解锁）"
            ),
            version=target,
        )

    await db.execute(
        sa.update(Project)
        .where(Project.id == _as_uuid(pid))
        .values(
            acnr_registry_version=target,
            acnr_registry_locked_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    _memo(db)[pid] = target
    logger.info("acnr 版本锁：项目 %s 锁定到目录版本 %s", pid, target)
    return target


async def unlock_project_registry(db: Any, project_id: str | UUID) -> str | None:
    """清掉项目的版本锁（两列同清），返回原先锁定的版本号；本来没锁返回 None。

    取消归档时在同一事务里调用；只 flush 不 commit。
    """
    from app.models.core import Project

    pid = str(project_id)
    row = (
        await db.execute(
            sa.select(Project.acnr_registry_version).where(Project.id == _as_uuid(pid))
        )
    ).first()
    previous = row[0] if row is not None else None

    if previous:
        await db.execute(
            sa.update(Project)
            .where(Project.id == _as_uuid(pid))
            .values(acnr_registry_version=None, acnr_registry_locked_at=None)
        )
        await db.flush()
        logger.info("acnr 版本锁：项目 %s 解锁（原锁定 %s）", pid, previous)

    _memo(db)[pid] = None
    return previous


async def get_locked_version(db: Any, project_id: str | UUID) -> str | None:
    """项目锁定的目录版本号；未锁定返回 None。

    请求级记忆：结果缓存在 `db.info`，同一请求内多次解析不重复查库。
    数据库读不出来时**不**伪装成「未锁定」—— 异常上抛，由调用方决定（design §8.3：
    宁可报错也不要按当前目录解析一个归档项目）。
    """
    from app.models.core import Project

    pid = str(project_id)
    memo = _memo(db)
    if pid in memo:
        return memo[pid]

    row = (
        await db.execute(
            sa.select(Project.acnr_registry_version).where(Project.id == _as_uuid(pid))
        )
    ).first()
    value = row[0] if row is not None else None
    memo[pid] = value or None
    return memo[pid]


def _memo(db: Any) -> dict[str, str | None]:
    """`db.info` 里的请求级缓存（会话没有 info 时退化为一次性字典）。"""
    info = getattr(db, "info", None)
    if not isinstance(info, dict):
        return {}
    return info.setdefault(_MEMO_KEY, {})


def _as_uuid(value: str) -> Any:
    """项目 id 统一按 UUID 绑定。

    原生 SQL 里按 `str(uuid)` 绑定在 SQLite 上匹配不到（存的是 32 位十六进制），
    所以这里走 SQLAlchemy 表达式 + UUID 对象，让方言各自转换。
    """
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return value


__all__ = [
    "RegistryLockError",
    "get_locked_version",
    "lock_project_registry",
    "unlock_project_registry",
    "verify_snapshot",
]
