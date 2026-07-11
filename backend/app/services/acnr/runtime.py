"""ACNR L3 RuntimeIndex — 自定义格运行时登记

register_custom() 在底稿保存后由 parsed_data 提交调用，
校验 project_id + wp 归属后将自定义格存入 L3 内存索引。

RuntimeCellEntry 仅存在于 L2/L3（runtime_only=true），
不写入全局 L1 种子（R24.2）。

Requirements: 23.3, 24.1, 24.2
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─── Data Model ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RuntimeCellEntry:
    """L3 运行时格条目（蓝图 §5.4）。

    addr_id 格式: runtime/{project_id}/{wp_id}/{sheet_or_code}/{cell}
    uri_profile: custom_flat
    formula_ref: WP('{wp_code}','{cell}') — 2 参
    runtime_only: true — 永不进入全局 L1 种子
    """

    addr_id: str
    domain: str = "wp"
    origin: str = "custom"
    uri_profile: str = "custom_flat"
    uri: str = ""
    formula_ref: str = ""
    runtime_only: bool = True
    # 附加元数据
    project_id: str = ""
    wp_id: str = ""
    cell_address: str = ""
    semantic_label: str = ""
    wp_code: str = ""


# ─── L3 In-memory Store ──────────────────────────────────────────────────────
# 按 project_id 分区的内存字典，key = addr_id → RuntimeCellEntry
# 设计：L3 数据仅在进程生命周期内有效，重启后从 parsed_data 重建

_l3_store: dict[str, dict[str, RuntimeCellEntry]] = {}
"""project_id → {addr_id → RuntimeCellEntry}"""


def get_runtime_entries(project_id: str) -> dict[str, RuntimeCellEntry]:
    """获取指定项目的 L3 运行时条目。

    供 resolve() 在决策树第 6 步访问 L3 数据。
    """
    return _l3_store.get(project_id, {})


def get_runtime_entry(project_id: str, addr_id: str) -> RuntimeCellEntry | None:
    """按 addr_id 精确查找指定项目的 L3 条目。"""
    return _l3_store.get(project_id, {}).get(addr_id)


def clear_runtime_entries(project_id: str) -> None:
    """清除指定项目的 L3 缓存（失效时调用）。"""
    _l3_store.pop(project_id, None)


def clear_all_runtime_entries() -> None:
    """清除全部 L3 缓存（测试用）。"""
    _l3_store.clear()


# ─── Ownership Validation (R24.1) ───────────────────────────────────────────


class WpOwnershipError(Exception):
    """wp_id 不属于指定 project_id 时抛出。"""

    def __init__(self, project_id: str, wp_id: str) -> None:
        self.project_id = project_id
        self.wp_id = wp_id
        super().__init__(
            f"wp_id={wp_id} does not belong to project_id={project_id}"
        )


async def _validate_wp_ownership(
    db: AsyncSession,
    project_id: str,
    wp_id: str,
) -> None:
    """校验 wp_id 属于 project_id（防 IDOR，R24.1）。

    通过查询 working_paper 表验证 (project_id, wp_id) 对应关系。
    如果不匹配则抛出 WpOwnershipError。
    """
    result = await db.execute(
        sa.text(
            "SELECT 1 FROM working_paper "
            "WHERE id = :wp_id AND project_id = :project_id "
            "AND is_deleted = false "
            "LIMIT 1"
        ),
        {"wp_id": wp_id, "project_id": project_id},
    )
    if result.scalar_one_or_none() is None:
        raise WpOwnershipError(project_id, wp_id)


# ─── register_custom (R23.3, R24.1, R24.2) ──────────────────────────────────


def _build_addr_id(project_id: str, wp_id: str, wp_code: str, cell_address: str) -> str:
    """构造 RuntimeCellEntry 的 addr_id。

    格式: runtime/{project_id}/{wp_id}/{wp_code}/{cell_address}
    """
    return f"runtime/{project_id}/{wp_id}/{wp_code}/{cell_address}"


def _build_uri(wp_code: str, cell_address: str) -> str:
    """构造 custom_flat URI。

    格式: wp://{wp_code}/{cell_address}
    """
    return f"wp://{wp_code}/{cell_address}"


def _build_formula_ref(wp_code: str, cell_address: str) -> str:
    """构造 2 参 WP() 公式引用。

    格式: WP('{wp_code}','{cell_address}')
    """
    return f"WP('{wp_code}','{cell_address}')"


# ─── custom_flat profile (grammar_v1) ────────────────────────────────────────
# 供 address_registry._build_custom_wp_cell_entries 使用，使自定义格可经
# full_resolve(formula_ref=WP('wp','wp','cell')) round-trip 回同一 addr_id。


def _build_custom_flat_addr_id(wp_code: str, cell_address: str) -> str:
    """构造 custom_flat addr_id（grammar_v1 custom_flat profile）。

    格式: {wp_code}/{wp_code}/{cell_address}

    与 catalog._formula_ref_to_addr_id(WP('wp','wp','cell')) 的 fallback 输出一致，
    使 full_resolve 决策树 Step 6（L3 精确匹配）可命中。
    """
    return f"{wp_code}/{wp_code}/{cell_address}"


def _build_custom_flat_formula_ref(wp_code: str, cell_address: str) -> str:
    """构造 3 参 custom_flat WP() 公式引用（grammar_v1）。

    格式: WP('{wp_code}','{wp_code}','{cell_address}')
    """
    return f"WP('{wp_code}','{wp_code}','{cell_address}')"


async def register_custom(
    db: AsyncSession,
    project_id: str,
    wp_id: str,
    cells: list[dict[str, Any]],
    *,
    addr_profile: str = "runtime",
) -> list[RuntimeCellEntry]:
    """登记自定义格到 L3 运行时索引（parsed_data 保存后调用）。

    1. 校验 project_id + wp 归属（R24.1 — 防 IDOR）
    2. 为每个 cell 创建 RuntimeCellEntry
    3. 存入 L3 内存（按 project_id 分区，不落全局 L1，R24.2）
    4. 使其可被 resolve() 搜索（通过 get_runtime_entries）

    Args:
        db: 数据库会话（用于归属校验）
        project_id: 项目 ID
        wp_id: 底稿 ID（必须属于该 project）
        cells: 待登记格列表，每项包含:
            - cell_address: str — 单元格 A1 地址（必填）
            - semantic_label: str | None — 语义标签（可选）
            - wp_code: str — 底稿编码（必填）
        addr_profile: addr_id / formula_ref 生成方案：
            - "runtime"（默认）: addr_id=runtime/{pid}/{wp_id}/{wp_code}/{cell}，
              formula_ref=WP('{wp_code}','{cell}')（2 参，向后兼容既有调用/测试）
            - "custom_flat": addr_id={wp_code}/{wp_code}/{cell}，
              formula_ref=WP('{wp_code}','{wp_code}','{cell}')（3 参，grammar_v1
              custom_flat profile，使 full_resolve 可 round-trip 命中，供
              address_registry 自定义格接入使用）

    Returns:
        创建的 RuntimeCellEntry 列表

    Raises:
        WpOwnershipError: wp_id 不属于 project_id
        ValueError: cells 参数无效
    """
    if not cells:
        return []

    # 1. 校验 project_id + wp 归属（R24.1）
    await _validate_wp_ownership(db, project_id, wp_id)

    # 2. 创建 RuntimeCellEntry 实例
    entries: list[RuntimeCellEntry] = []
    for cell in cells:
        cell_address = cell.get("cell_address", "").strip()
        wp_code = cell.get("wp_code", "").strip()

        if not cell_address or not wp_code:
            logger.warning(
                "register_custom: 跳过无效 cell (cell_address=%r, wp_code=%r)",
                cell_address,
                wp_code,
            )
            continue

        semantic_label = (cell.get("semantic_label") or "").strip()
        if addr_profile == "custom_flat":
            addr_id = _build_custom_flat_addr_id(wp_code, cell_address)
            formula_ref = _build_custom_flat_formula_ref(wp_code, cell_address)
        else:
            addr_id = _build_addr_id(project_id, wp_id, wp_code, cell_address)
            formula_ref = _build_formula_ref(wp_code, cell_address)

        entry = RuntimeCellEntry(
            addr_id=addr_id,
            uri=_build_uri(wp_code, cell_address),
            formula_ref=formula_ref,
            project_id=project_id,
            wp_id=wp_id,
            cell_address=cell_address,
            semantic_label=semantic_label,
            wp_code=wp_code,
        )
        entries.append(entry)

    # 3. 存入 L3 内存索引（按 project_id 分区）
    if project_id not in _l3_store:
        _l3_store[project_id] = {}

    project_store = _l3_store[project_id]
    for entry in entries:
        project_store[entry.addr_id] = entry

    logger.info(
        "register_custom: project=%s wp=%s registered %d cells (L3 total=%d)",
        project_id,
        wp_id,
        len(entries),
        len(project_store),
    )

    return entries
