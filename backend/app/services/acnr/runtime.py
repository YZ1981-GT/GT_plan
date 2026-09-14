"""ACNR L3 RuntimeIndex — 自定义格运行时登记

register_custom() 在底稿保存后由 parsed_data 提交调用，
校验 project_id + wp 归属后将自定义格存入 L3 内存索引。

rebuild_runtime_for_wp() 按 wp_id 增量重建 L3（Req-5.1）——
仅重建该 wp 的条目，不清除同 project 其他 wp 的条目。

resolve_l3() 修复 L3 匹配逻辑（Req-5.3）——
精确匹配 或 startswith(target+"/")，多候选返回 ambiguous。

RuntimeCellEntry 仅存在于 L2/L3（runtime_only=true），
不写入全局 L1 种子（R24.2）。

Requirements: 23.3, 24.1, 24.2, Req-5
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


def clear_runtime_entries_for_wp(project_id: str, wp_id: str) -> int:
    """清除指定项目中特定 wp_id 的 L3 条目（Req-5.2 增量失效）。

    仅删除 wp_id 匹配的条目，其他 wp 的条目不受影响。

    Returns:
        被删除的条目数量
    """
    project_store = _l3_store.get(project_id)
    if not project_store:
        return 0

    keys_to_remove = [
        k for k, v in project_store.items() if v.wp_id == wp_id
    ]
    for k in keys_to_remove:
        del project_store[k]

    if not project_store:
        del _l3_store[project_id]

    return len(keys_to_remove)


# ─── L3 Matching (Req-5.3) ──────────────────────────────────────────────────


def resolve_l3(
    project_id: str,
    target: str,
) -> tuple[str, RuntimeCellEntry | None | list[RuntimeCellEntry]]:
    """L3 解析：精确匹配 or startswith(target+"/")，多候选 → ambiguous。

    修复原始 startswith(wp_code) 错格风险（Req-5.3）。
    例如 target="D2" 不应匹配 "D2-2/..." 或 "D20/..."，
    只应匹配精确 "D2" 或前缀 "D2/"。

    Returns:
        ("found", entry) — 唯一匹配
        ("ambiguous", [entries]) — 多候选
        ("miss", None) — 无匹配
    """
    project_store = _l3_store.get(project_id)
    if not project_store:
        return ("miss", None)

    # 精确匹配优先
    exact = project_store.get(target)
    if exact is not None:
        return ("found", exact)

    # 前缀匹配：target + "/"（避免 startswith 错格）
    prefix = target + "/"
    candidates = [
        entry for addr_id, entry in project_store.items()
        if addr_id.startswith(prefix)
    ]

    if len(candidates) == 0:
        return ("miss", None)
    elif len(candidates) == 1:
        return ("found", candidates[0])
    else:
        return ("ambiguous", candidates)


# ─── Incremental Rebuild (Req-5.1, Req-5.4) ─────────────────────────────────


async def rebuild_runtime_for_wp(
    db: AsyncSession,
    project_id: str,
    wp_id: str,
    parsed_data: list[dict[str, Any]],
    *,
    addr_profile: str = "runtime",
) -> list[RuntimeCellEntry]:
    """按 wp_id 增量重建 L3 RuntimeCell（Req-5.1）。

    1. 仅清除该 wp 的旧条目（不影响同 project 其他 wp）
    2. 从 parsed_data 重新创建 RuntimeCellEntry
    3. 支持冷启动/缓存失效后的确定性重建（Req-5.4）

    Args:
        db: 数据库会话（用于归属校验）
        project_id: 项目 ID
        wp_id: 底稿 ID
        parsed_data: 解析后的格数据列表，每项包含:
            - cell_address: str — 单元格地址
            - wp_code: str — 底稿编码
            - semantic_label: str | None — 语义标签（可选）
        addr_profile: 地址生成方案 ("runtime" | "custom_flat")

    Returns:
        重建后的 RuntimeCellEntry 列表
    """
    # Step 1: 仅清除该 wp 的旧条目
    removed = clear_runtime_entries_for_wp(project_id, wp_id)
    if removed > 0:
        logger.debug(
            "rebuild_runtime_for_wp: cleared %d old entries for wp=%s",
            removed, wp_id,
        )

    # Step 2: 用 parsed_data 重新注册
    if not parsed_data:
        return []

    return await register_custom(
        db, project_id, wp_id, parsed_data, addr_profile=addr_profile
    )


async def rebuild_from_db_parsed_data(
    db: AsyncSession,
    project_id: str,
    wp_id: str,
) -> list[RuntimeCellEntry]:
    """冷启动从 DB parsed_data 惰性重建 L3（Req-5.4）。

    当 L3 缓存为空（进程重启/首次访问）时，从数据库加载该 wp 的
    parsed_data 并确定性重建 RuntimeCellEntry。

    Returns:
        重建的条目列表（如果 DB 无数据则返回空列表）
    """
    # 查询 checklist_responses 中该 wp 的 parsed cells 数据
    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE :prefix "
            "ORDER BY item_id"
        ),
        {"wp_id": wp_id, "prefix": "runtime-cells-%"},
    )
    rows = result.fetchall()

    if not rows:
        # 尝试从 working_paper 的 meta 或 parsed_data 中获取
        result2 = await db.execute(
            sa.text(
                "SELECT wi.wp_code "
                "FROM working_paper wp "
                "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                "WHERE wp.id = :wp_id AND wp.project_id = :project_id "
                "AND wp.is_deleted = false "
                "LIMIT 1"
            ),
            {"wp_id": wp_id, "project_id": project_id},
        )
        row = result2.fetchone()
        if row is None:
            return []
        # 无持久化的 runtime cells，返回空
        return []

    import json
    parsed_data: list[dict[str, Any]] = []
    for row in rows:
        try:
            data = json.loads(row[0]) if row[0] else []
            if isinstance(data, list):
                parsed_data.extend(data)
        except (json.JSONDecodeError, TypeError):
            continue

    if not parsed_data:
        return []

    return await rebuild_runtime_for_wp(
        db, project_id, wp_id, parsed_data
    )


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
