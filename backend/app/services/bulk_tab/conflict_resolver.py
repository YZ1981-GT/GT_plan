"""ConflictResolver — 导入冲突策略解析器（Req 8.1–8.4）

三策略：
- overwrite（默认）：全量替换 item_id 行数据（等同现有单表 import 语义）。
- fill-empty：读现有 checklist_responses → 仅对空字段/行写入 → 不覆盖非空。
- reject：目标 item_id 已有非空数据 → 该 sheet 抛 ConflictRejected，不部分写入。

策略对整包统一，回显于报告（Req 8.4）。

本模块为纯逻辑组件，不直接访问数据库。调用方（SingleTabIeAdapter / BulkImportService）
负责提供 existing_data 和 incoming_data，由本模块决定最终写入内容。

数据模型约定：
- existing_data: dict[str, dict[str, Any]] — 按 item_id 索引的现有行数据
  例: {"D2-vc-row-1": {"conclusion": "Y", "remark": "已核", "wp_ref": None}, ...}
- incoming_data: dict[str, dict[str, Any]] — 按 item_id 索引的待导入行数据
  例: {"D2-vc-row-1": {"conclusion": "N", "remark": "重新核实", "wp_ref": "D2-1"}, ...}
- resolved_data: dict[str, dict[str, Any]] — 最终写入的行数据

Requirements: 8.1, 8.2, 8.3, 8.4
"""
from __future__ import annotations

from typing import Any

from app.services.bulk_tab.single_tab_adapter import ConflictStrategy


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConflictRejected(Exception):
    """reject 策略下目标 item_id 已有非空数据时抛出。

    该 sheet 不部分写入，整体标记为 conflict_rejected。
    调用方应捕获此异常并在 ImportReport 中记录。

    Attributes:
        sheet_code: 冲突所在的 sheet 编码。
        conflicting_item_ids: 存在非空数据的 item_id 列表。
    """

    def __init__(
        self,
        sheet_code: str,
        conflicting_item_ids: list[str] | None = None,
    ) -> None:
        self.sheet_code = sheet_code
        self.conflicting_item_ids = conflicting_item_ids or []
        items_str = ", ".join(self.conflicting_item_ids[:5])
        if len(self.conflicting_item_ids) > 5:
            items_str += f" ... (共 {len(self.conflicting_item_ids)} 条)"
        super().__init__(
            f"sheet '{sheet_code}' 存在非空数据的 item_id [{items_str}]，"
            f"reject 策略拒绝写入"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_field_empty(value: Any) -> bool:
    """判断单个字段是否为"空"。

    空的定义（宽松）：
    - None
    - 空字符串 ""
    - 仅空白字符组成的字符串

    非空：任何其他值（包括 0、False 等有业务语义的值）。
    """
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def is_row_empty(row: dict[str, Any]) -> bool:
    """判断一整行是否全为空。

    全部字段都满足 is_field_empty → 行为空。
    """
    if not row:
        return True
    return all(is_field_empty(v) for v in row.values())


def has_non_empty_data(existing_data: dict[str, dict[str, Any]]) -> list[str]:
    """检查 existing_data 中哪些 item_id 有非空数据。

    Returns:
        有非空数据的 item_id 列表。
    """
    non_empty_ids: list[str] = []
    for item_id, row in existing_data.items():
        if not is_row_empty(row):
            non_empty_ids.append(item_id)
    return non_empty_ids


# ---------------------------------------------------------------------------
# Core resolver
# ---------------------------------------------------------------------------


def resolve_conflict(
    existing_data: dict[str, dict[str, Any]],
    incoming_data: dict[str, dict[str, Any]],
    strategy: ConflictStrategy,
    *,
    sheet_code: str = "",
) -> dict[str, dict[str, Any]]:
    """根据冲突策略合并 existing 与 incoming 数据。

    Args:
        existing_data: 库中已有数据（按 item_id 索引）。
        incoming_data: 待导入数据（按 item_id 索引）。
        strategy: 冲突策略 "overwrite"/"fill-empty"/"reject"。
        sheet_code: sheet 编码，用于 reject 异常消息。

    Returns:
        最终应写入的数据（按 item_id 索引）。

    Raises:
        ConflictRejected: reject 策略下存在非空的 existing item_id 时抛出。
    """
    if strategy == "overwrite":
        return _resolve_overwrite(existing_data, incoming_data)
    elif strategy == "fill-empty":
        return _resolve_fill_empty(existing_data, incoming_data)
    elif strategy == "reject":
        return _resolve_reject(existing_data, incoming_data, sheet_code)
    else:
        # 防御性：未知策略回退 overwrite
        return _resolve_overwrite(existing_data, incoming_data)


def _resolve_overwrite(
    existing_data: dict[str, dict[str, Any]],
    incoming_data: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """overwrite 策略：全量替换。

    incoming_data 中有的 item_id 完全以 incoming 为准（全量替换）。
    existing_data 中有但 incoming 中没有的 item_id 不动（不删除）。

    Req 8.1: 以 ZIP 为准，全量替换该 item_id 的行数据。
    """
    # 直接返回 incoming_data 的深拷贝作为写入目标
    # 调用方负责：对 incoming 中出现的 item_id 做 upsert
    return {item_id: dict(row) for item_id, row in incoming_data.items()}


def _resolve_fill_empty(
    existing_data: dict[str, dict[str, Any]],
    incoming_data: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """fill-empty 策略：仅填空位，不覆盖非空。

    对 incoming 中每个 item_id：
    - 若 existing 中无此 item_id → 全量写入 incoming 行
    - 若 existing 中有此 item_id → 逐字段合并：
      - existing 字段非空 → 保留 existing 值
      - existing 字段为空 → 使用 incoming 值

    Req 8.2: 仅写入库中为空的字段/行，不覆盖已有编制内容。
    """
    resolved: dict[str, dict[str, Any]] = {}

    for item_id, incoming_row in incoming_data.items():
        existing_row = existing_data.get(item_id)

        if existing_row is None or is_row_empty(existing_row):
            # existing 无此行或行全空 → 全量写入 incoming
            resolved[item_id] = dict(incoming_row)
        else:
            # 逐字段合并：existing 非空字段保留，空字段用 incoming 填充
            merged = dict(existing_row)
            for field_key, incoming_value in incoming_row.items():
                if field_key in merged and not is_field_empty(merged[field_key]):
                    # existing 非空 → 保留不覆盖
                    continue
                else:
                    # existing 空或无此字段 → 填入 incoming 值
                    merged[field_key] = incoming_value
            resolved[item_id] = merged

    return resolved


def _resolve_reject(
    existing_data: dict[str, dict[str, Any]],
    incoming_data: dict[str, dict[str, Any]],
    sheet_code: str,
) -> dict[str, dict[str, Any]]:
    """reject 策略：目标有非空数据则拒绝整个 sheet。

    检查 incoming 中的 item_id 在 existing 中是否有非空数据：
    - 若存在任何一个非空 → 抛 ConflictRejected（该 sheet 不写入）
    - 若全部为空 → 等同 overwrite 写入

    Req 8.3: 目标 item_id 已有非空数据 → 该 sheet 不部分写入。
    """
    # 只检查 incoming 中涉及的 item_id
    conflicting_ids: list[str] = []
    for item_id in incoming_data:
        existing_row = existing_data.get(item_id)
        if existing_row is not None and not is_row_empty(existing_row):
            conflicting_ids.append(item_id)

    if conflicting_ids:
        raise ConflictRejected(
            sheet_code=sheet_code,
            conflicting_item_ids=conflicting_ids,
        )

    # 无冲突 → 全量写入（等同 overwrite）
    return {item_id: dict(row) for item_id, row in incoming_data.items()}
