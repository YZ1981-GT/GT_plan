"""历史数据符号约定 dry-run 脚本。

读取余额行，应用方向推导规则，分类为：
- safe_auto_fix: 可进入 allowlist 自动修正
- manual_review_required: 需人工复核
- no_change: 已符合约定或不改写

输出 JSON 报告，不写入数据库（除非传入 allowlist）。

Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

# 确保 backend 包可被导入
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.ledger_import.direction_derivation import (
    CONTRA_ASSET_PATTERNS,
    NORMAL_DIRECTION_BY_CATEGORY,
    derive_balance_direction,
)
from app.services.ledger_import.sign_convention_types import (
    MigrationSafetyLevel,
)


__all__ = [
    "DryRunItem",
    "DryRunReport",
    "run_dry_run",
    "classify_safety_level",
]


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class DryRunItem:
    """单条 dry-run 建议项。"""

    project_id: str
    dataset_id: str
    account_code: str
    account_name: str
    old_closing_balance: str
    suggested_closing_balance: str
    reason: str
    risk: str  # MigrationSafetyLevel
    direction_source: str


@dataclass
class DryRunReport:
    """dry-run 报告。"""

    items: list[DryRunItem] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        """输出 JSON 字符串。"""
        return json.dumps(
            {
                "items": [asdict(item) for item in self.items],
                "summary": self.summary,
            },
            ensure_ascii=False,
            indent=2,
        )


# ---------------------------------------------------------------------------
# 安全等级分类
# ---------------------------------------------------------------------------


def classify_safety_level(
    direction_source: str,
    has_direction_conflict: bool,
    account_code: str = "",
    category: Optional[str] = None,
) -> str:
    """确定迁移安全等级。

    Rules:
    - explicit_direction 或 split_columns 证据冲突 → safe_auto_fix
    - 仅 account_category_inferred 推断 → manual_review_required
    - account_category_inferred_low_confidence → manual_review_required
    - 无冲突 → no_change
    - 特殊科目 (2221 等) 即使有冲突也 → manual_review_required
    """
    if not has_direction_conflict:
        return "no_change"

    # 特殊科目：负债类但经常有借方余额（税费留抵等）
    ALWAYS_MANUAL_PREFIXES = ("2221", "2241", "2171")
    code = str(account_code).strip()
    if any(code.startswith(p) for p in ALWAYS_MANUAL_PREFIXES):
        return "manual_review_required"

    # 根据方向来源判断
    if direction_source in ("explicit_direction", "split_columns"):
        return "safe_auto_fix"

    # 仅靠推断的，不自动改写
    return "manual_review_required"


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------


def run_dry_run(
    rows: list[dict[str, Any]],
    category_map: Optional[dict[str, dict[str, Any]]] = None,
    project_id: str = "",
    dataset_id: str = "",
    allowlist: Optional[set[str]] = None,
) -> DryRunReport:
    """执行 dry-run 分析。

    Args:
        rows: 余额行列表 (dict)
        category_map: 科目编码 → 元数据 dict
        project_id: 项目 ID
        dataset_id: 数据集 ID
        allowlist: 允许自动修正的科目编码集合。None 表示纯 dry-run 不写。

    Returns:
        DryRunReport 包含每行分析结果和摘要统计。
    """
    if category_map is None:
        category_map = {}

    items: list[DryRunItem] = []
    counts = {"safe_auto_fix": 0, "manual_review_required": 0, "no_change": 0}

    for row in rows:
        account_code = str(row.get("account_code", "")).strip()
        if not account_code:
            continue

        account_name = str(row.get("account_name", "")).strip() or ""
        meta = category_map.get(account_code, {})

        # 推导方向
        result = derive_balance_direction(row, meta)

        # 确定当前存储的净额符号
        balance = row.get("closing_balance")
        if balance is None:
            balance = row.get("opening_balance")
        if balance is None:
            counts["no_change"] += 1
            continue

        try:
            balance_dec = Decimal(str(balance))
        except Exception:
            counts["no_change"] += 1
            continue

        if balance_dec == 0:
            counts["no_change"] += 1
            continue

        # 判断是否有方向冲突
        current_sign_direction = "debit" if balance_dec > 0 else "credit"
        expected = result.direction

        if expected == "unknown" or expected == current_sign_direction:
            # 无冲突
            counts["no_change"] += 1
            items.append(DryRunItem(
                project_id=project_id,
                dataset_id=dataset_id,
                account_code=account_code,
                account_name=account_name,
                old_closing_balance=str(balance_dec),
                suggested_closing_balance=str(balance_dec),
                reason="no_conflict",
                risk="no_change",
                direction_source=result.direction_source,
            ))
            continue

        # 有冲突 → 分类安全等级
        category = meta.get("account_category")
        safety = classify_safety_level(
            result.direction_source,
            has_direction_conflict=True,
            account_code=account_code,
            category=category,
        )
        counts[safety] += 1

        # 建议金额
        suggested = str(-balance_dec) if safety == "safe_auto_fix" else str(balance_dec)

        items.append(DryRunItem(
            project_id=project_id,
            dataset_id=dataset_id,
            account_code=account_code,
            account_name=account_name,
            old_closing_balance=str(balance_dec),
            suggested_closing_balance=suggested,
            reason=f"{result.direction_source}_{expected}_expected",
            risk=safety,
            direction_source=result.direction_source,
        ))

    report = DryRunReport(items=items, summary=counts)
    return report


# ---------------------------------------------------------------------------
# CLI 入口（仅 dry-run，不执行写入）
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("sign_convention_dry_run: 请通过测试或 pipeline 调用 run_dry_run()。")
    print("此脚本不直接连接数据库，仅作为逻辑模块使用。")
