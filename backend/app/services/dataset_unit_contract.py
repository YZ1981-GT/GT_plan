"""
数据集单位合同分类器。

将 LedgerDataset.source_summary 归一为三类：
- normalized_v1: 存在 unit_normalization 且包含有效 contract（含 contract_digest 且为 64 位十六进制）
- legacy_declared: 有 amount_unit 声明但没有 unit_normalization
- legacy_unknown: 其余情况，包括 unit_normalization 存在但合同无效的 fail-closed 场景

阶段 A 后端只产出两类 legacy（真正的 normalized_v1 分支由阶段 B 任务 8 的严格合同解析接入）。
"""

from __future__ import annotations

import re
from typing import Literal

DatasetUnitClass = Literal["normalized_v1", "legacy_declared", "legacy_unknown"]

# 64 位小写十六进制正则
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def classify_dataset_unit(source_summary: dict | None) -> DatasetUnitClass:
    """将 source_summary 归一为三类数据集单位状态。

    Parameters
    ----------
    source_summary:
        LedgerDataset 的 source_summary JSONB 字段，可以为 None 或任意 dict。

    Returns
    -------
    DatasetUnitClass
        - ``'normalized_v1'``: unit_normalization 存在且 contract 有效
        - ``'legacy_declared'``: 有 amount_unit 但没有 unit_normalization
        - ``'legacy_unknown'``: 其余（含 unit_normalization 无效的 fail-closed）
    """
    if not source_summary or not isinstance(source_summary, dict):
        return "legacy_unknown"

    normalization = source_summary.get("unit_normalization")

    if normalization is not None:
        # 有 unit_normalization —— 检查 contract 是否有效
        if isinstance(normalization, dict):
            contract = normalization.get("contract")
            if isinstance(contract, dict) and _is_valid_contract(contract):
                return "normalized_v1"
        # unit_normalization 存在但合同无效 → fail-closed
        return "legacy_unknown"

    # 没有 unit_normalization —— 检查旧的 amount_unit 声明
    amount_unit = source_summary.get("amount_unit")
    if amount_unit and isinstance(amount_unit, str) and amount_unit.strip():
        return "legacy_declared"

    return "legacy_unknown"


def _is_valid_contract(contract: dict) -> bool:
    """校验 contract 是否含有效的 contract_digest（64 位小写十六进制）。"""
    digest = contract.get("contract_digest")
    if not isinstance(digest, str):
        return False
    return bool(_DIGEST_RE.match(digest))
