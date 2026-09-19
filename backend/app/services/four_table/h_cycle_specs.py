"""H 类循环科目规格注册表（10 个循环统一入口）。

各循环的详细声明与依据见各自的 `h{n}_account_scope.py`。
本文件只做汇总注册，供守卫与 render 按 wp_code 前缀查找。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSpec

from .h1_account_scope import H1_ACCOUNT_SPEC, H1_SLOT_KEY_PREFIX
from .h2_account_scope import H2_ACCOUNT_SPEC, H2_SLOT_KEY_PREFIX
from .h3_account_scope import H3_ACCOUNT_SPEC, H3_SLOT_KEY_PREFIX
from .h4_account_scope import H4_ACCOUNT_SPEC, H4_SLOT_KEY_PREFIX
from .h5_account_scope import H5_ACCOUNT_SPEC, H5_SLOT_KEY_PREFIX
from .h6_account_scope import H6_ACCOUNT_SPEC, H6_SLOT_KEY_PREFIX
from .h7_account_scope import H7_ACCOUNT_SPEC, H7_SLOT_KEY_PREFIX
from .h8_account_scope import H8_ACCOUNT_SPEC, H8_SLOT_KEY_PREFIX
from .h9_account_scope import H9_ACCOUNT_SPEC, H9_SLOT_KEY_PREFIX
from .h10_account_scope import H10_ACCOUNT_SPEC, H10_SLOT_KEY_PREFIX, H10_IS_OCCURRENCE

#: 循环标识 → 科目规格
H_CYCLE_SPECS: dict[str, SemanticAccountSpec] = {
    "H1": H1_ACCOUNT_SPEC,
    "H2": H2_ACCOUNT_SPEC,
    "H3": H3_ACCOUNT_SPEC,
    "H4": H4_ACCOUNT_SPEC,
    "H5": H5_ACCOUNT_SPEC,
    "H6": H6_ACCOUNT_SPEC,
    "H7": H7_ACCOUNT_SPEC,
    "H8": H8_ACCOUNT_SPEC,
    "H9": H9_ACCOUNT_SPEC,
    "H10": H10_ACCOUNT_SPEC,
}

#: 循环标识 → 槽键→前端键前缀映射
H_CYCLE_SLOT_PREFIXES: dict[str, dict[str, str]] = {
    "H1": H1_SLOT_KEY_PREFIX,
    "H2": H2_SLOT_KEY_PREFIX,
    "H3": H3_SLOT_KEY_PREFIX,
    "H4": H4_SLOT_KEY_PREFIX,
    "H5": H5_SLOT_KEY_PREFIX,
    "H6": H6_SLOT_KEY_PREFIX,
    "H7": H7_SLOT_KEY_PREFIX,
    "H8": H8_SLOT_KEY_PREFIX,
    "H9": H9_SLOT_KEY_PREFIX,
    "H10": H10_SLOT_KEY_PREFIX,
}

#: 损益类循环（取本期发生额而非余额）
H_CYCLE_OCCURRENCE: set[str] = {"H10"}

__all__ = [
    "H_CYCLE_SPECS",
    "H_CYCLE_SLOT_PREFIXES",
    "H_CYCLE_OCCURRENCE",
    # 各循环单独导出（方便 render 直接引用）
    "H1_ACCOUNT_SPEC", "H1_SLOT_KEY_PREFIX",
    "H2_ACCOUNT_SPEC", "H2_SLOT_KEY_PREFIX",
    "H3_ACCOUNT_SPEC", "H3_SLOT_KEY_PREFIX",
    "H4_ACCOUNT_SPEC", "H4_SLOT_KEY_PREFIX",
    "H5_ACCOUNT_SPEC", "H5_SLOT_KEY_PREFIX",
    "H6_ACCOUNT_SPEC", "H6_SLOT_KEY_PREFIX",
    "H7_ACCOUNT_SPEC", "H7_SLOT_KEY_PREFIX",
    "H8_ACCOUNT_SPEC", "H8_SLOT_KEY_PREFIX",
    "H9_ACCOUNT_SPEC", "H9_SLOT_KEY_PREFIX",
    "H10_ACCOUNT_SPEC", "H10_SLOT_KEY_PREFIX",
    "H10_IS_OCCURRENCE",
]
