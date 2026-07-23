"""ACNR L2 ProjectOverlay — PG 持久化权威 + 内存 read-through 缓存

职责：
1. 持久化 overlay 到 PostgreSQL (acnr_project_overlay)
2. 内存 _overlay_cache 作为 read-through 缓存
3. invalidate 只清内存不删 PG
4. 归属校验修复 ORM JOIN 方向 (WorkingPaper.wp_index_id → WpIndex.id)
5. Single-flight 防护：同一 project 并发缓存冷启动只执行一次 DB 查询 (Req-13)

Requirements: Req-4 (Overlay 持久化与归属校验), Req-13 (Single-Flight 防护)
"""
from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─── Data Model ──────────────────────────────────────────────────────────────


@dataclass(slots=True)
class OverlayPatch:
    """单条项目级 overlay 补丁。"""

    project_id: str
    addr_id: str
    overrides: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    owner: str = ""
    expires_at: str | None = None  # ISO "YYYY-MM-DD"
    overlay_type: str = "cust"  # alias | cust | binding
    wp_id: str | None = None
    revision: int = 1  # V122: 乐观并发版本号（CAS 用）

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            return date.today() > date.fromisoformat(self.expires_at)
        except ValueError:
            return False


# ─── L2 Read-through Cache ───────────────────────────────────────────────────
# key: project_id → {addr_id → OverlayPatch}
# PG 是权威，内存仅派生缓存; invalidate 清内存不删 PG

_overlay_cache: dict[str, dict[str, OverlayPatch]] = {}
"""project_id → {addr_id → OverlayPatch} read-through cache"""

_cache_loaded: set[str] = set()
"""Track which projects have been loaded from PG."""

_flight_locks: dict[str, asyncio.Lock] = {}
"""Per-project asyncio.Lock for single-flight cache loading (Req-13)."""


def _get_flight_lock(project_id: str) -> asyncio.Lock:
    """Get or create per-project lock for single-flight cache loading."""
    if project_id not in _flight_locks:
        _flight_locks[project_id] = asyncio.Lock()
    return _flight_locks[project_id]


# ─── Cache Management ────────────────────────────────────────────────────────


def get_overlay(project_id: str, addr_id: str) -> OverlayPatch | None:
    """Get overlay from cache. Returns None if not cached (call load_cache first)."""
    return _overlay_cache.get(project_id, {}).get(addr_id)


def get_project_overlays(project_id: str) -> dict[str, OverlayPatch]:
    """Get all overlays from cache for a project."""
    return _overlay_cache.get(project_id, {})


def is_cache_loaded(project_id: str) -> bool:
    """Check if project overlays have been loaded from PG."""
    return project_id in _cache_loaded


def populate_cache(project_id: str, patches: dict[str, OverlayPatch]) -> None:
    """Populate cache with patches loaded from PG."""
    _overlay_cache[project_id] = patches
    _cache_loaded.add(project_id)


def set_overlay_in_cache(patch: OverlayPatch) -> None:
    """Write a single patch into the cache (after PG write succeeds)."""
    if patch.project_id not in _overlay_cache:
        _overlay_cache[patch.project_id] = {}
    _overlay_cache[patch.project_id][patch.addr_id] = patch
    _cache_loaded.add(patch.project_id)


def clear_project_overlays(project_id: str) -> None:
    """Clear in-memory cache for project (invalidation). Does NOT delete PG data."""
    _overlay_cache.pop(project_id, None)
    _cache_loaded.discard(project_id)


def clear_all_overlays() -> None:
    """Clear all caches (testing)."""
    _overlay_cache.clear()
    _cache_loaded.clear()
    _flight_locks.clear()


def remove_overlay_from_cache(project_id: str, addr_id: str) -> bool:
    """Remove single entry from cache."""
    project_patches = _overlay_cache.get(project_id, {})
    if addr_id in project_patches:
        del project_patches[addr_id]
        if not project_patches:
            _overlay_cache.pop(project_id, None)
        return True
    return False


# ─── Backward Compatibility Aliases ──────────────────────────────────────────
# These maintain the old module-level API used by existing code and tests.

def set_overlay(patch: OverlayPatch) -> None:
    """Alias for set_overlay_in_cache (backward compat)."""
    set_overlay_in_cache(patch)


def remove_overlay(project_id: str, addr_id: str) -> bool:
    """Alias for remove_overlay_from_cache (backward compat)."""
    return remove_overlay_from_cache(project_id, addr_id)


# ─── PG-backed Read-Through ──────────────────────────────────────────────────


async def load_project_overlays_from_pg(
    session: AsyncSession, project_id: str
) -> dict[str, OverlayPatch]:
    """Load overlays from PG and populate the cache. Returns cache dict."""
    from app.services.acnr.overlay_repository import get_overlays_for_project

    rows = await get_overlays_for_project(session, UUID(project_id))
    patches: dict[str, OverlayPatch] = {}
    for row in rows:
        addr_id = f"{row.parent_wp_code}/{row.sheet_code}"
        # R7.3: 读回治理字段，使 is_expired() 重启后按持久化 expires_at 判定
        patch = OverlayPatch(
            project_id=project_id,
            addr_id=addr_id,
            overrides=row.payload or {},
            overlay_type=row.overlay_type,
            wp_id=str(row.wp_id) if row.wp_id else None,
            reason=getattr(row, "reason", None) or "",
            owner=getattr(row, "owner", None) or "",
            expires_at=(
                row.expires_at.isoformat()
                if getattr(row, "expires_at", None) is not None
                else None
            ),
            revision=getattr(row, "revision", 1) or 1,
        )
        patches[addr_id] = patch

    populate_cache(project_id, patches)
    return patches


async def ensure_cache_loaded(session: AsyncSession, project_id: str) -> dict[str, OverlayPatch]:
    """Ensure cache is loaded for project; if not, read from PG."""
    if is_cache_loaded(project_id):
        return get_project_overlays(project_id)
    return await load_project_overlays_from_pg(session, project_id)


async def get_overlay_cached(
    project_id: str, session: AsyncSession
) -> dict[str, OverlayPatch]:
    """Single-flight cache loading for a project (Req-13).

    Guarantees:
    - Only ONE DB query per project during concurrent cache misses.
    - Other concurrent callers wait on the lock and receive the cached result.
    - Different projects are NOT blocked by each other (per-project lock).
    - DB exceptions release the lock without deadlock, preserving old cache if any.

    Flow:
      1. Fast path: cache hit → return immediately (no lock)
      2. Acquire per-project lock
      3. Double-check (二次检查): another coroutine may have populated it while waiting
      4. DB query → populate cache
      5. Release lock
      6. On DB exception → release lock + preserve old cache + re-raise
    """
    # 1. Fast path: cache hit (no lock needed)
    if is_cache_loaded(project_id):
        return get_project_overlays(project_id)

    # 2. Acquire per-project lock (single-flight)
    lock = _get_flight_lock(project_id)
    async with lock:
        # 3. Double-check after acquiring lock
        if is_cache_loaded(project_id):
            return get_project_overlays(project_id)

        # 4. DB query → populate cache
        try:
            return await load_project_overlays_from_pg(session, project_id)
        except Exception:
            # 6. DB exception: release lock (via async with), preserve old cache
            # Lock is released by context manager — no deadlock
            logger.warning(
                "single-flight DB query failed for project=%s, preserving old cache",
                project_id,
            )
            raise


# ─── ProjectOverlay 服务类 ───────────────────────────────────────────────────


class ProjectOverlay:
    """L2 ProjectOverlay — 项目级别名/补丁应用 (read-through cache)。"""

    def apply(self, project_id: str, entries: list[dict]) -> list[dict]:
        """Apply overlay patches from cache to catalog entries."""
        if not project_id or not entries:
            return entries

        project_patches = get_project_overlays(project_id)
        if not project_patches:
            return entries

        result: list[dict] = []
        for entry in entries:
            addr_id = entry.get("addr_id", "")
            patch = project_patches.get(addr_id)
            if patch and not patch.is_expired():
                patched = deepcopy(entry)
                self._apply_patch(patched, patch)
                result.append(patched)
            else:
                result.append(entry)
        return result

    def apply_to_single(self, project_id: str, entry: dict) -> dict:
        """Apply overlay to a single catalog entry."""
        if not project_id or not entry:
            return entry

        project_patches = get_project_overlays(project_id)
        if not project_patches:
            return entry

        addr_id = entry.get("addr_id", "")
        patch = project_patches.get(addr_id)
        if patch and not patch.is_expired():
            patched = deepcopy(entry)
            self._apply_patch(patched, patch)
            return patched
        return entry

    def get_project_aliases(self, project_id: str) -> dict[str, list[str]]:
        """Get project-level alias mappings (supplement L1 aliases)."""
        result: dict[str, list[str]] = {}
        project_patches = get_project_overlays(project_id)
        for addr_id, patch in project_patches.items():
            if patch.is_expired():
                continue
            alias_add = patch.overrides.get("sheet_name_alias_add", [])
            if alias_add:
                result[addr_id] = list(alias_add)
        return result

    def _apply_patch(self, entry: dict, patch: OverlayPatch) -> None:
        """Apply override fields from patch to entry."""
        overrides = patch.overrides
        for key, value in overrides.items():
            if key == "sheet_name_alias_add":
                existing = entry.get("sheet_name_aliases", [])
                new_aliases = [a for a in value if a not in existing]
                entry["sheet_name_aliases"] = existing + new_aliases
            elif key == "sheet_name_alias_remove":
                existing = entry.get("sheet_name_aliases", [])
                entry["sheet_name_aliases"] = [a for a in existing if a not in value]
            else:
                entry[key] = value


# ─── Ownership Validation (Fixed JOIN direction) ─────────────────────────────


class OverlayOwnershipError(Exception):
    """overlay 写入时归属校验失败。"""

    def __init__(self, project_id: str, addr_id: str, reason: str = "") -> None:
        self.project_id = project_id
        self.addr_id = addr_id
        msg = f"Overlay ownership check failed: project={project_id} addr_id={addr_id}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


async def validate_ownership(
    db: AsyncSession,
    project_id: str,
    wp_id_or_addr_id: str | None = None,
    parent_wp_code: str = "",
    sheet_code: str = "",
) -> bool:
    """校验 overlay 写入归属 (Req-4.3).

    Supports two call patterns:
    - Legacy (3 args): validate_ownership(db, project_id, addr_id)
      addr_id is parsed into parent_wp_code/sheet_code
    - New (5 args): validate_ownership(db, project_id, wp_id, parent_wp_code, sheet_code)

    修复 ORM JOIN 方向:
      正确: working_paper.wp_index_id = wp_index.id
      错误(旧): wp_index.wp_id = working_paper.id (不存在的列)
    """
    # Legacy 3-arg call: (db, project_id, addr_id)
    if wp_id_or_addr_id and not parent_wp_code:
        addr_id = wp_id_or_addr_id
        parts = addr_id.split("/")
        parent_wp_code = parts[0] if len(parts) >= 1 else ""
        sheet_code = parts[1] if len(parts) >= 2 else ""
        wp_id: str | None = None
    else:
        wp_id = wp_id_or_addr_id

    # 1. 验证项目存在
    project_result = await db.execute(
        sa.text(
            "SELECT 1 FROM projects "
            "WHERE id = :project_id AND is_deleted = false "
            "LIMIT 1"
        ),
        {"project_id": project_id},
    )
    if project_result.scalar_one_or_none() is None:
        raise OverlayOwnershipError(
            project_id, f"{parent_wp_code}/{sheet_code}",
            "project not found or deleted"
        )

    # 2. Single segment addr_id — only verify project exists
    if not sheet_code:
        return True

    # 3. 验证 wp_index 中存在该 wp_code 且属于该 project
    wi_result = await db.execute(
        sa.text(
            "SELECT wi.id FROM wp_index wi "
            "WHERE wi.project_id = :project_id "
            "AND wi.wp_code = :wp_code "
            "AND wi.is_deleted = false "
            "LIMIT 1"
        ),
        {"project_id": project_id, "wp_code": parent_wp_code},
    )
    if wi_result.scalar_one_or_none() is None:
        raise OverlayOwnershipError(
            project_id, f"{parent_wp_code}/{sheet_code}",
            f"wp_code={parent_wp_code} not found in project wp_index"
        )

    # 4. 如果提供了 wp_id，验证归属关系:
    #    working_paper.wp_index_id → wp_index.id (正确 JOIN 方向)
    if wp_id:
        wp_result = await db.execute(
            sa.text(
                "SELECT 1 FROM working_paper wp "
                "JOIN wp_index wi ON wp.wp_index_id = wi.id "
                "WHERE wp.id = :wp_id "
                "AND wp.project_id = :project_id "
                "AND wp.is_deleted = false "
                "AND wi.wp_code = :wp_code "
                "LIMIT 1"
            ),
            {"wp_id": wp_id, "project_id": project_id, "wp_code": parent_wp_code},
        )
        if wp_result.scalar_one_or_none() is None:
            raise OverlayOwnershipError(
                project_id, f"{parent_wp_code}/{sheet_code}",
                f"wp_id={wp_id} does not belong to project or wp_code mismatch"
            )

    return True


# ─── PG-backed Write (with ownership) ────────────────────────────────────────


async def write_overlay(
    db: AsyncSession,
    project_id: str,
    addr_id: str,
    overrides: dict[str, Any],
    reason: str = "",
    owner: str = "",
    expires_at: str | None = None,
    overlay_type: str = "cust",
    wp_id: str | None = None,
    expected_revision: int | None = None,
) -> OverlayPatch:
    """Write overlay to PG（含治理字段 + 可选 CAS）+ 清项目缓存（read-through 重载）。

    Req-4.1: 权威数据持久化到 PostgreSQL
    Req-4.3: 写入时校验 wp_id 属于 project 且经 WpIndex 确认全链归属
    R7.2: 治理字段 reason/owner/expires_at 持久化到 PG
    R8: expected_revision 提供时 CAS（冲突抛 OverlayRevisionConflict）
    R9: **清项目缓存**而非写缓存 —— read-through 从已提交 PG 重载，
        外层事务回滚不留脏缓存（flush ≠ commit）。
    """
    from app.services.acnr.overlay_repository import upsert_overlay

    parts = addr_id.split("/")
    parent_wp_code = parts[0] if len(parts) >= 1 else ""
    sheet_code = parts[1] if len(parts) >= 2 else parts[0]

    # Ownership validation (Req-4.3)
    await validate_ownership(db, project_id, wp_id, parent_wp_code, sheet_code)

    # Persist to PG — gracefully handle non-UUID project_ids (test scenarios)
    try:
        pg_project_id = UUID(project_id)
    except (ValueError, AttributeError):
        # Non-UUID project_id: skip PG persistence (legacy/test path)
        pg_project_id = None

    persisted_revision = 1
    if pg_project_id is not None:
        row = await upsert_overlay(
            db,
            project_id=pg_project_id,
            wp_id=UUID(wp_id) if wp_id else None,
            parent_wp_code=parent_wp_code,
            sheet_code=sheet_code,
            overlay_type=overlay_type,
            payload=overrides,
            reason=reason or None,
            owner=owner or None,
            expires_at=expires_at,
            expected_revision=expected_revision,
        )
        persisted_revision = getattr(row, "revision", 1) or 1

    # R9: 清项目缓存（不写缓存）→ 下次读经 read-through 从已提交 PG 重载。
    # 外层事务回滚 → PG 无新行 → 重载得旧状态，天然不留脏缓存。
    clear_project_overlays(project_id)

    logger.info(
        "overlay written (cache cleared): project=%s addr_id=%s type=%s owner=%s rev=%d",
        project_id, addr_id, overlay_type, owner, persisted_revision,
    )
    return OverlayPatch(
        project_id=project_id,
        addr_id=addr_id,
        overrides=overrides,
        reason=reason,
        owner=owner,
        expires_at=expires_at,
        overlay_type=overlay_type,
        wp_id=wp_id,
        revision=persisted_revision,
    )


# ─── 受控变更入口（R10）───────────────────────────────────────────────────
# 当前平台无 overlay 编辑 UI；这些服务层入口使加固后的写路径可达、可测、可审计。
# UI 接线为 spec 外后续项。

_OVERLAY_MUTATE_ROLES = frozenset({"admin", "partner", "signing_partner", "manager"})


def _actor_role(actor: Any) -> str:
    role = getattr(actor, "role", None)
    return role.value if hasattr(role, "value") else str(role or "")


async def apply_project_overlay(
    db: AsyncSession,
    project_id: str,
    addr_id: str,
    overrides: dict[str, Any],
    *,
    actor: Any,
    wp_id: str | None = None,
    reason: str = "",
    owner: str = "",
    expires_at: str | None = None,
    overlay_type: str = "cust",
    expected_revision: int | None = None,
) -> OverlayPatch:
    """受控 overlay 变更入口（R10）。

    1. capability 校验（manager/partner/signing_partner/admin）；不足 → HTTPException 403
    2. `write_overlay`（含 validate_ownership + 原子 upsert + 治理字段 + CAS + 清缓存）
    3. **同事务**写 Invalidation_Outbox（R11.2）—— overlay 写与失效信号原子提交
       （调用方 commit db）；dispatcher 后续至少一次投递（递增 epoch + 广播）。

    调用方负责 `await db.commit()`（overlay upsert / outbox enqueue 均 flush-only）。
    """
    from fastapi import HTTPException

    if _actor_role(actor) not in _OVERLAY_MUTATE_ROLES:
        raise HTTPException(status_code=403, detail="无权变更 overlay")

    patch = await write_overlay(
        db,
        project_id=project_id,
        addr_id=addr_id,
        overrides=overrides,
        reason=reason,
        owner=owner,
        expires_at=expires_at,
        overlay_type=overlay_type,
        wp_id=wp_id,
        expected_revision=expected_revision,
    )

    # R11.2: 同事务写 outbox（与 overlay 写原子提交）
    try:
        pg_project_id = UUID(project_id)
        from app.services.acnr.invalidation_outbox import enqueue as _outbox_enqueue

        await _outbox_enqueue(
            db, str(pg_project_id), wp_id=wp_id, domain="overlay"
        )
    except (ValueError, AttributeError):
        # 非 UUID project_id（测试/legacy 路径）跳过 outbox
        pass

    return patch


async def remove_project_overlay(
    db: AsyncSession,
    project_id: str,
    addr_id: str,
    *,
    actor: Any,
    overlay_type: str = "cust",
) -> bool:
    """受控 overlay 删除入口（R10）。capability + 删除 PG + 清缓存 + 同事务 outbox。"""
    from fastapi import HTTPException

    if _actor_role(actor) not in _OVERLAY_MUTATE_ROLES:
        raise HTTPException(status_code=403, detail="无权变更 overlay")

    parts = addr_id.split("/")
    parent_wp_code = parts[0] if len(parts) >= 1 else ""
    sheet_code = parts[1] if len(parts) >= 2 else parts[0]

    deleted = False
    try:
        pg_project_id = UUID(project_id)
    except (ValueError, AttributeError):
        pg_project_id = None

    if pg_project_id is not None:
        from app.services.acnr.overlay_repository import delete_overlay_by_identity

        deleted = await delete_overlay_by_identity(
            db,
            project_id=pg_project_id,
            parent_wp_code=parent_wp_code,
            sheet_code=sheet_code,
            overlay_type=overlay_type,
        )
        # R11.2: 同事务写 outbox
        from app.services.acnr.invalidation_outbox import enqueue as _outbox_enqueue

        await _outbox_enqueue(db, str(pg_project_id), domain="overlay")

    # R9: 清缓存 → read-through 重载已提交状态
    clear_project_overlays(project_id)
    logger.info(
        "overlay removed (cache cleared): project=%s addr_id=%s type=%s deleted=%s",
        project_id, addr_id, overlay_type, deleted,
    )
    return deleted


# ─── 模块级单例 ──────────────────────────────────────────────────────────────

_project_overlay = ProjectOverlay()


def get_project_overlay() -> ProjectOverlay:
    """获取全局 ProjectOverlay 实例。"""
    return _project_overlay
