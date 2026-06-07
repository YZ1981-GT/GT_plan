"""一键预设未匹配治理模块。

职责：
1. 从有余额科目与 seed 数据比对，输出未匹配清单（不静默跳过）
2. seed 升级刷新仅覆盖未确认 ai_suggested，保护 manual / reference_copied

Requirements: 5.4, 6.3
"""

from __future__ import annotations

from backend.app.services.balance_diagnostics.diagnostics_types import (
    UnmatchedAccount,
)


# ---------------------------------------------------------------------------
# mapping_source 常量（保护级别）
# ---------------------------------------------------------------------------

# 可被 seed 刷新覆盖的 source
OVERWRITABLE_SOURCES = {"ai_suggested"}

# 受保护的 source（不可被 seed 覆盖）
PROTECTED_SOURCES = {"manual", "reference_copied"}


# ---------------------------------------------------------------------------
# 8.1 获取未匹配科目
# ---------------------------------------------------------------------------


def get_unmatched_for_preset(
    accounts_with_balance: list[dict],
    seed_data: list[dict],
) -> list[UnmatchedAccount]:
    """从有余额科目与 seed 数据比对，返回 seed 中查不到行次的科目。

    有余额但 seed 查不到行次时不静默跳过，必须进入未匹配清单。

    Args:
        accounts_with_balance: 有余额的科目列表
            [{account_code, account_name, amount}]
        seed_data: seed 中当前维度的映射条目列表
            [{standard_account_code, report_line_code, ...}]

    Returns:
        UnmatchedAccount 列表（mapping_status=seed_missing）
    """
    seed_codes = {entry.get("standard_account_code", "") for entry in seed_data}

    unmatched: list[UnmatchedAccount] = []
    for acc in accounts_with_balance:
        code = acc.get("account_code", "")
        if not code:
            continue
        if code not in seed_codes:
            unmatched.append(UnmatchedAccount(
                account_code=code,
                account_name=acc.get("account_name"),
                amount=float(acc.get("amount", 0)),
                mapping_status="seed_missing",
            ))

    return unmatched


# ---------------------------------------------------------------------------
# 8.3 seed 升级刷新
# ---------------------------------------------------------------------------


def refresh_seed_mappings(
    project_id: str,
    new_seed: list[dict],
    existing_mappings: list[dict],
) -> list[dict]:
    """seed 升级刷新：仅覆盖 ai_suggested 映射，保护 manual / reference_copied。

    Args:
        project_id: 项目 ID（用于结果标注）
        new_seed: 新 seed 映射条目列表
            [{standard_account_code, report_line_code, report_line_name, ...}]
        existing_mappings: 项目现有映射列表
            [{account_code, report_line_code, mapping_source, ...}]

    Returns:
        更新后的映射列表，包含：
        - 保留不变的 manual / reference_copied 映射
        - 用新 seed 覆盖的原 ai_suggested 映射
        - 新 seed 中新增的映射（对无现有映射的科目）
    """
    # 索引现有映射：account_code → mapping dict
    existing_by_code: dict[str, dict] = {}
    for m in existing_mappings:
        code = m.get("account_code", "")
        if code:
            existing_by_code[code] = m

    # 索引新 seed：standard_account_code → seed entry
    seed_by_code: dict[str, dict] = {}
    for entry in new_seed:
        code = entry.get("standard_account_code", "")
        if code:
            seed_by_code[code] = entry

    result: list[dict] = []

    # 遍历现有映射，决定保留或覆盖
    for code, mapping in existing_by_code.items():
        source = mapping.get("mapping_source", "")
        if source in PROTECTED_SOURCES:
            # 保护：不覆盖
            result.append(mapping)
        elif source in OVERWRITABLE_SOURCES and code in seed_by_code:
            # 覆盖：用新 seed 替换
            seed_entry = seed_by_code[code]
            result.append({
                "account_code": code,
                "report_line_code": seed_entry.get("report_line_code", ""),
                "report_line_name": seed_entry.get("report_line_name", ""),
                "mapping_source": "ai_suggested",
                "project_id": project_id,
            })
        else:
            # 保留原样（source 不在 overwritable 也不在 protected）
            result.append(mapping)

    # 新 seed 中有但现有映射中没有的科目 → 新增
    for code, seed_entry in seed_by_code.items():
        if code not in existing_by_code:
            result.append({
                "account_code": code,
                "report_line_code": seed_entry.get("report_line_code", ""),
                "report_line_name": seed_entry.get("report_line_name", ""),
                "mapping_source": "ai_suggested",
                "project_id": project_id,
            })

    return result


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

__all__ = [
    "OVERWRITABLE_SOURCES",
    "PROTECTED_SOURCES",
    "get_unmatched_for_preset",
    "refresh_seed_mappings",
]
