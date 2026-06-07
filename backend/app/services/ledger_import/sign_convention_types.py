"""符号约定与方向来源类型定义。

定义 DirectionSource、SignConventionVersion、SignAnomaly 和 MigrationSafetyLevel，
前后端共享枚举值，前端对应 TypeScript 类型见 sign-convention.ts。

Requirements: 1.1, 1.3, 2.2
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# DirectionSource — 方向来源枚举
# ---------------------------------------------------------------------------

DirectionSource = Literal[
    "explicit_direction",                    # 原始文件有方向列（借/贷/D/C）
    "split_columns",                         # 借贷分列计算得出
    "account_category_inferred",             # 按 Account_Category 推断
    "account_category_inferred_low_confidence",  # 低置信度前缀推断
    "user_override",                         # 用户手动覆盖
    "legacy_inferred",                       # 历史数据推断（迁移前）
    "unknown",                               # 无法判定
]

# 枚举值列表，用于一致性测试 fixture
DIRECTION_SOURCE_VALUES: list[str] = [
    "explicit_direction",
    "split_columns",
    "account_category_inferred",
    "account_category_inferred_low_confidence",
    "user_override",
    "legacy_inferred",
    "unknown",
]

# ---------------------------------------------------------------------------
# SignConventionVersion — 符号约定版本
# ---------------------------------------------------------------------------

SignConventionVersion = Literal[
    "v1_net_debit_positive",  # 净额借方为正、贷方为负
]

SIGN_CONVENTION_VERSION_VALUES: list[str] = [
    "v1_net_debit_positive",
]

# 当前生效的符号约定常量
CURRENT_SIGN_CONVENTION: SignConventionVersion = "v1_net_debit_positive"

# ---------------------------------------------------------------------------
# MigrationSafetyLevel — 迁移安全等级
# ---------------------------------------------------------------------------

MigrationSafetyLevel = Literal[
    "safe_auto_fix",           # 可进入 allowlist 自动修
    "manual_review_required",  # 不自动改写，需人工复核
    "no_change",               # 不改写
]

MIGRATION_SAFETY_LEVEL_VALUES: list[str] = [
    "safe_auto_fix",
    "manual_review_required",
    "no_change",
]

# ---------------------------------------------------------------------------
# SignAnomaly — 符号异常记录
# ---------------------------------------------------------------------------


class SignAnomaly(BaseModel):
    """符号异常记录：方向与 Account_Category 正常方向冲突时生成。"""

    account_code: str
    account_name: str | None = None
    expected_direction: str  # "debit" | "credit"
    actual_direction: str    # "debit" | "credit" | "unknown"
    balance_amount: float
    category: str            # Account_Category
    reason: str              # 具体异常原因


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

__all__ = [
    "DirectionSource",
    "DIRECTION_SOURCE_VALUES",
    "SignConventionVersion",
    "SIGN_CONVENTION_VERSION_VALUES",
    "CURRENT_SIGN_CONVENTION",
    "MigrationSafetyLevel",
    "MIGRATION_SAFETY_LEVEL_VALUES",
    "SignAnomaly",
]
