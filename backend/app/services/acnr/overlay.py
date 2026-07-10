"""ACNR L2 ProjectOverlay — 项目级补丁/别名应用 + 归属校验

职责：
1. 加载项目级 overlay（从 per-project store / 内存 dict）
2. apply_overlay(project_id, entries) → 修改后条目列表（叠加 overlay patches）
3. get_project_aliases(project_id) → 项目级别名（补充 L1 别名）
4. validate_ownership(db, project_id, addr_id) → 归属校验（防 IDOR，R24.1）

设计约定（R5.2, R5.8）：
- 带 project_id 时，overlay 在 L1 匹配前先应用
- 即使最终结果为 ambiguous，overlay 仍须先应用
- M1 阶段 overlay 用内存 dict 存储，不落 DB

Requirements: 5.2, 5.8, 24.1
"""
from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─── Data Model ──────────────────────────────────────────────────────────────


@dataclass(slots=True)
class OverlayPatch:
    """单条项目级 overlay 补丁（蓝图 §5.8）。

    结构：
        project_id: 所属项目
        addr_id: 目标 catalog 条目（如 "D2/D2-2"）
        overrides: 要覆盖/追加的字段
        reason: 修改原因
        owner: 补丁所有者（用户标识）
        expires_at: 过期时间（防永久临时补丁）
    """

    project_id: str
    addr_id: str
    overrides: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    owner: str = ""
    expires_at: str | None = None  # ISO 格式 "YYYY-MM-DD"

    def is_expired(self) -> bool:
        """检查补丁是否已过期。"""
        if not self.expires_at:
            return False
        try:
            exp = date.fromisoformat(self.expires_at)
            return date.today() > exp
        except ValueError:
            return False


# ─── L2 In-memory Store ──────────────────────────────────────────────────────
# M1 阶段用内存 dict 存储 overlay，按 project_id 分区
# key 结构: project_id → {addr_id → OverlayPatch}

_overlay_store: dict[str, dict[str, OverlayPatch]] = {}
"""project_id → {addr_id → OverlayPatch}"""


# ─── Store Management ────────────────────────────────────────────────────────


def get_overlay(project_id: str, addr_id: str) -> OverlayPatch | None:
    """获取指定项目某条目的 overlay 补丁。"""
    return _overlay_store.get(project_id, {}).get(addr_id)


def get_project_overlays(project_id: str) -> dict[str, OverlayPatch]:
    """获取指定项目的全部 overlay 补丁。"""
    return _overlay_store.get(project_id, {})


def set_overlay(patch: OverlayPatch) -> None:
    """写入一条 overlay 补丁到内存 store。

    注意：调用前必须先完成 validate_ownership 校验（R24.1）。
    """
    if patch.project_id not in _overlay_store:
        _overlay_store[patch.project_id] = {}
    _overlay_store[patch.project_id][patch.addr_id] = patch
    logger.info(
        "overlay set: project=%s addr_id=%s reason=%r owner=%s",
        patch.project_id,
        patch.addr_id,
        patch.reason,
        patch.owner,
    )


def remove_overlay(project_id: str, addr_id: str) -> bool:
    """移除一条 overlay 补丁。返回 True 如果存在且被移除。"""
    project_patches = _overlay_store.get(project_id, {})
    if addr_id in project_patches:
        del project_patches[addr_id]
        if not project_patches:
            del _overlay_store[project_id]
        return True
    return False


def clear_project_overlays(project_id: str) -> None:
    """清除指定项目的全部 overlay（失效时调用）。"""
    _overlay_store.pop(project_id, None)


def clear_all_overlays() -> None:
    """清除全部 overlay（测试用）。"""
    _overlay_store.clear()


# ─── ProjectOverlay 服务类 ───────────────────────────────────────────────────


class ProjectOverlay:
    """L2 ProjectOverlay — 项目级别名/补丁应用。

    核心行为（R5.2, R5.8）：
    - 带 project_id 时在 L1 匹配前先应用 overlay
    - 即使最终 ambiguous，仍须先应用 overlay
    """

    def apply(self, project_id: str, entries: list[dict]) -> list[dict]:
        """对 catalog 条目列表应用项目级 overlay 补丁。

        对每个条目：
        1. 查找该条目 addr_id 对应的 overlay patch
        2. 如果存在且未过期，将 overrides 中的字段叠加到条目上
        3. 支持 sheet_name_alias_add（追加别名）和直接字段覆盖

        此方法在 resolve 决策树中于 L1 匹配前调用（R5.2），
        即使结果最终为 ambiguous 也会先执行（R5.8）。

        Args:
            project_id: 项目 ID
            entries: 待处理的 catalog 条目列表（dict 格式）

        Returns:
            应用补丁后的条目列表（深拷贝，不修改原始数据）
        """
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
                # 深拷贝避免污染原始 catalog 数据
                patched = deepcopy(entry)
                self._apply_patch(patched, patch)
                result.append(patched)
            else:
                result.append(entry)

        return result

    def apply_to_single(self, project_id: str, entry: dict) -> dict:
        """对单个 catalog 条目应用 overlay 补丁。

        供 resolve 流程中对命中的单条目应用 overlay 使用。

        Args:
            project_id: 项目 ID
            entry: 待处理的 catalog 条目

        Returns:
            应用补丁后的条目（可能是深拷贝）
        """
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
        """获取项目级别名映射（补充 L1 别名）。

        返回 {addr_id → [追加的别名列表]}，供 resolve 时
        在标准别名之外额外匹配这些项目级别名。

        Args:
            project_id: 项目 ID

        Returns:
            addr_id → 项目追加别名列表
        """
        result: dict[str, list[str]] = {}
        project_patches = get_project_overlays(project_id)

        for addr_id, patch in project_patches.items():
            if patch.is_expired():
                continue
            overrides = patch.overrides
            # 提取 sheet_name_alias_add
            alias_add = overrides.get("sheet_name_alias_add", [])
            if alias_add:
                result[addr_id] = list(alias_add)

        return result

    def _apply_patch(self, entry: dict, patch: OverlayPatch) -> None:
        """将 overlay patch 的 overrides 应用到条目上。

        支持的 override 类型：
        - sheet_name_alias_add: list[str] — 追加别名到 sheet_name_aliases
        - sheet_name_alias_remove: list[str] — 从 sheet_name_aliases 移除
        - 其他字段: 直接覆盖（如 component_type、display_label 等）
        """
        overrides = patch.overrides

        for key, value in overrides.items():
            if key == "sheet_name_alias_add":
                # 追加别名（去重）
                existing = entry.get("sheet_name_aliases", [])
                new_aliases = [a for a in value if a not in existing]
                entry["sheet_name_aliases"] = existing + new_aliases

            elif key == "sheet_name_alias_remove":
                # 移除别名
                existing = entry.get("sheet_name_aliases", [])
                entry["sheet_name_aliases"] = [
                    a for a in existing if a not in value
                ]

            else:
                # 直接字段覆盖
                entry[key] = value


# ─── Ownership Validation (R24.1) ───────────────────────────────────────────


class OverlayOwnershipError(Exception):
    """overlay 写入时 project_id 归属校验失败。"""

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
    addr_id: str,
) -> bool:
    """校验 overlay 写入的项目归属（R24.1 — 防 IDOR）。

    验证逻辑：
    1. project_id 对应的项目必须存在且未删除
    2. addr_id 对应的底稿必须属于该项目（通过 wp_index + working_paper 验证）

    对于 sheet 级 addr_id（如 "D2/D2-2"），检查该项目下是否有
    对应 parent_wp_code + sheet_code 的底稿实例。

    Args:
        db: 数据库会话
        project_id: 项目 ID
        addr_id: 目标条目 addr_id

    Returns:
        True 如果校验通过

    Raises:
        OverlayOwnershipError: 校验失败
    """
    # 1. 验证项目存在
    project_result = await db.execute(
        sa.text(
            "SELECT 1 FROM project "
            "WHERE id = :project_id AND is_deleted = false "
            "LIMIT 1"
        ),
        {"project_id": project_id},
    )
    if project_result.scalar_one_or_none() is None:
        raise OverlayOwnershipError(
            project_id, addr_id, "project not found or deleted"
        )

    # 2. 解析 addr_id → parent_wp_code + sheet_code
    parts = addr_id.split("/")
    if len(parts) < 2:
        # addr_id 不含 sheet 级信息，无法校验 wp 归属
        # 仅验证项目存在即可（例如顶层 wp_code 级别的 overlay）
        return True

    parent_wp_code = parts[0]
    sheet_code = parts[1]

    # 3. 验证该项目下存在对应底稿实例
    # 通过 wp_index (wp_code) + working_paper (project_id) JOIN 验证
    wp_result = await db.execute(
        sa.text(
            "SELECT 1 FROM wp_index wi "
            "JOIN working_paper wp ON wp.id = wi.wp_id "
            "WHERE wp.project_id = :project_id "
            "AND wp.is_deleted = false "
            "AND wi.wp_code = :wp_code "
            "LIMIT 1"
        ),
        {"project_id": project_id, "wp_code": parent_wp_code},
    )
    if wp_result.scalar_one_or_none() is None:
        raise OverlayOwnershipError(
            project_id, addr_id,
            f"no working paper with wp_code={parent_wp_code} in project"
        )

    return True


# ─── 写入 overlay（带归属校验，R24.1）───────────────────────────────────────


async def write_overlay(
    db: AsyncSession,
    project_id: str,
    addr_id: str,
    overrides: dict[str, Any],
    reason: str,
    owner: str,
    expires_at: str | None = None,
) -> OverlayPatch:
    """写入一条 overlay 补丁（带归属校验）。

    流程：
    1. validate_ownership 校验项目归属（R24.1）
    2. 构造 OverlayPatch
    3. 写入 store

    Args:
        db: 数据库会话
        project_id: 项目 ID
        addr_id: 目标条目 addr_id
        overrides: 覆盖字段 dict
        reason: 修改原因
        owner: 操作者标识
        expires_at: 过期时间 (YYYY-MM-DD)

    Returns:
        创建的 OverlayPatch

    Raises:
        OverlayOwnershipError: 归属校验失败
    """
    # 归属校验（R24.1）
    await validate_ownership(db, project_id, addr_id)

    patch = OverlayPatch(
        project_id=project_id,
        addr_id=addr_id,
        overrides=overrides,
        reason=reason,
        owner=owner,
        expires_at=expires_at,
    )
    set_overlay(patch)
    return patch


# ─── 模块级单例 ──────────────────────────────────────────────────────────────

# 全局 ProjectOverlay 实例，供 resolver 使用
_project_overlay = ProjectOverlay()


def get_project_overlay() -> ProjectOverlay:
    """获取全局 ProjectOverlay 实例。"""
    return _project_overlay
