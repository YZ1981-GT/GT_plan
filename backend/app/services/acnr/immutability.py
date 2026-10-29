"""ACNR addr_id 不可变、重命名与弃用政策。

项目目录版本锁已持久化到 ``projects.acnr_registry_version``，统一由
``project_registry_lock`` 读写。本模块不再保存任何进程内项目版本状态。

Requirements: 19.1, 19.2, 19.3
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)


# ─── Exceptions ──────────────────────────────────────────────────────────────


class AddrIdImmutabilityError(Exception):
    """addr_id 不可变政策违规错误。"""

    def __init__(self, violations: list[dict[str, Any]]) -> None:
        self.violations = violations
        msgs = "; ".join(
            f"{v['type']}: {v['addr_id']}" for v in violations
        )
        super().__init__(f"addr_id immutability violations: {msgs}")


# ─── R19.1: addr_id 不可变校验 ───────────────────────────────────────────────


def validate_addr_id_immutable(
    old_catalog: dict[str, Any],
    new_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    """校验新 catalog 未违反 addr_id 不可变政策。

    规则（R19.1）：
    - 已有 addr_id 不可从新 catalog 中消失（除非标记 deprecated）
    - 已有 addr_id 对应的 canonical 值（parent_wp_code/sheet_code/cell_address）不可变更

    Args:
        old_catalog: 旧版 global_catalog.json 内容
        new_catalog: 新版 global_catalog.json 内容

    Returns:
        违规列表（空列表 = 校验通过）。每条违规：
        {type: "removed"|"value_changed", addr_id: str, detail: str}

    Raises:
        AddrIdImmutabilityError: 如果存在违规（调用方可选是否 raise）
    """
    violations: list[dict[str, Any]] = []

    # 构建旧 catalog 索引
    old_sheets = {s["addr_id"]: s for s in old_catalog.get("sheets", []) if "addr_id" in s}
    old_cells = {c["addr_id"]: c for c in old_catalog.get("cells", []) if "addr_id" in c}

    # 构建新 catalog 索引
    new_sheets = {s["addr_id"]: s for s in new_catalog.get("sheets", []) if "addr_id" in s}
    new_cells = {c["addr_id"]: c for c in new_catalog.get("cells", []) if "addr_id" in c}

    # 检查 sheet 级 addr_id
    for addr_id, old_entry in old_sheets.items():
        # deprecated 条目允许后续版本移除
        if old_entry.get("deprecated"):
            continue

        if addr_id not in new_sheets:
            violations.append({
                "type": "removed",
                "addr_id": addr_id,
                "detail": f"sheet entry '{addr_id}' removed from catalog without deprecation",
            })
            continue

        # 校验不可变字段未被修改
        new_entry = new_sheets[addr_id]
        immutable_fields = ("parent_wp_code", "sheet_code")
        for fld in immutable_fields:
            old_val = old_entry.get(fld)
            new_val = new_entry.get(fld)
            if old_val is not None and new_val is not None and old_val != new_val:
                violations.append({
                    "type": "value_changed",
                    "addr_id": addr_id,
                    "detail": f"field '{fld}' changed from '{old_val}' to '{new_val}'",
                })

    # 检查 cell 级 addr_id
    for addr_id, old_entry in old_cells.items():
        if old_entry.get("deprecated"):
            continue

        if addr_id not in new_cells:
            violations.append({
                "type": "removed",
                "addr_id": addr_id,
                "detail": f"cell entry '{addr_id}' removed from catalog without deprecation",
            })
            continue

        # 校验不可变字段
        new_entry = new_cells[addr_id]
        immutable_fields = ("parent_addr_id", "cell_address")
        for fld in immutable_fields:
            old_val = old_entry.get(fld)
            new_val = new_entry.get(fld)
            if old_val is not None and new_val is not None and old_val != new_val:
                violations.append({
                    "type": "value_changed",
                    "addr_id": addr_id,
                    "detail": f"field '{fld}' changed from '{old_val}' to '{new_val}'",
                })

    return violations


def check_addr_id_immutable(
    old_catalog: dict[str, Any],
    new_catalog: dict[str, Any],
) -> None:
    """校验 + 违规时抛出异常。供生成器管线调用。

    Args:
        old_catalog: 旧版 catalog
        new_catalog: 新版 catalog

    Raises:
        AddrIdImmutabilityError: 存在违规
    """
    violations = validate_addr_id_immutable(old_catalog, new_catalog)
    if violations:
        raise AddrIdImmutabilityError(violations)


# ─── R19.2: 重命名政策 ──────────────────────────────────────────────────────


def rename_sheet(
    catalog: dict[str, Any],
    addr_id: str,
    new_sheet_name: str,
) -> dict[str, Any]:
    """重命名 sheet 的权威名，旧名进入 aliases，addr_id 不变。

    规则（R19.2）：
    - sheet 权威名变更时，旧名写入 sheet_name_aliases
    - addr_id 本身永远不变
    - 返回修改后的 catalog（深拷贝，不影响原始数据）

    Args:
        catalog: global_catalog.json 内容
        addr_id: 要重命名的 sheet 条目 addr_id
        new_sheet_name: 新的 sheet 权威名

    Returns:
        修改后的 catalog dict

    Raises:
        ValueError: addr_id 不存在或不是 sheet 级条目
    """
    result = deepcopy(catalog)

    sheets = result.get("sheets", [])
    target: dict[str, Any] | None = None
    for s in sheets:
        if s.get("addr_id") == addr_id:
            target = s
            break

    if target is None:
        raise ValueError(f"sheet addr_id '{addr_id}' not found in catalog")

    old_name = target.get("sheet_name", "")
    if old_name == new_sheet_name:
        return result  # 无变化

    # 旧名追加到 aliases（去重）
    aliases: list[str] = target.get("sheet_name_aliases", [])
    if old_name and old_name not in aliases:
        aliases.append(old_name)
    target["sheet_name_aliases"] = aliases

    # 更新权威名
    target["sheet_name"] = new_sheet_name

    logger.info(
        "sheet renamed: addr_id=%s old_name=%r new_name=%r",
        addr_id, old_name, new_sheet_name,
    )
    return result


# ─── R19.3: 弃用政策 ────────────────────────────────────────────────────────


def deprecate_entry(
    catalog: dict[str, Any],
    addr_id: str,
    registry_version: str,
) -> dict[str, Any]:
    """标记条目为弃用（deprecated），保留至少一个 registry_version。

    规则（R19.3）：
    - 标记 deprecated: true
    - 记录 deprecated_at_version 用于后续清理判断
    - 条目保留在 catalog 中至少一个 registry_version

    Args:
        catalog: global_catalog.json 内容
        addr_id: 要弃用的条目 addr_id
        registry_version: 当前 registry_version

    Returns:
        修改后的 catalog dict

    Raises:
        ValueError: addr_id 不存在
    """
    result = deepcopy(catalog)

    # 在 sheets 和 cells 中查找
    target: dict[str, Any] | None = None
    for s in result.get("sheets", []):
        if s.get("addr_id") == addr_id:
            target = s
            break
    if target is None:
        for c in result.get("cells", []):
            if c.get("addr_id") == addr_id:
                target = c
                break

    if target is None:
        raise ValueError(f"addr_id '{addr_id}' not found in catalog (sheets or cells)")

    if target.get("deprecated"):
        # 已经标记为 deprecated，跳过
        return result

    target["deprecated"] = True
    target["deprecated_at_version"] = registry_version

    logger.info(
        "entry deprecated: addr_id=%s at_version=%s",
        addr_id, registry_version,
    )
    return result


def is_safe_to_remove(
    entry: dict[str, Any],
    current_version: str,
) -> bool:
    """判断 deprecated 条目是否已保留足够版本可安全移除。

    CI 清理脚本可用此判断弃用条目是否满足最小保留期。
    规则：deprecated_at_version < current_version 即至少跨了 1 个版本。

    Args:
        entry: catalog 条目
        current_version: 当前 registry_version

    Returns:
        True 如果可安全移除
    """
    if not entry.get("deprecated"):
        return False

    deprecated_at = entry.get("deprecated_at_version", "")
    if not deprecated_at:
        # 无记录版本，保守不移除
        return False

    # registry_version 为时间戳字符串（如 "20260710102744"），
    # 字典序比较即可判断版本先后
    return deprecated_at < current_version
