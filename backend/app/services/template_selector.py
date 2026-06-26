"""A16 智能模板选择 — 纯逻辑，无 DB 访问.

根据 business_category 关键词推荐 A16 声明书版本。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

A16_CATEGORY_MAP: dict[str, str] = {
    "IPO": "A16-3",
    "上市": "A16-2",
    "listed": "A16-2",
    "新三板": "A16-5",
    "企业债": "A16-6",
    "债券": "A16-6",
}
"""keyword → recommended A16 version code."""

A16_DEFAULT = "A16-1"
"""当 business_category 为空或无匹配关键词时的默认版本。"""

A16_ALWAYS_REQUIRED: list[str] = ["A16-7"]
"""无论 business_category 如何，始终必需的 A16 文档。"""

A16_ALL_VERSIONS: list[str] = [
    "A16-1",
    "A16-2",
    "A16-3",
    "A16-4",
    "A16-5",
    "A16-6",
    "A16-7",
]
"""所有 A16 变体编码（完整列表）。"""

A16_LABELS: dict[str, str] = {
    "A16-1": "一般财报（企业会计准则）",
    "A16-2": "整合审计",
    "A16-3": "IPO申报报表审计",
    "A16-4": "IPO季度财务报表审阅",
    "A16-5": "新三板申报报表审计",
    "A16-6": "企业债（企业会计准则）",
    "A16-7": "管理层关联交易声明书",
}
"""wp_code → Chinese label。"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def recommend_a16_version(business_category: str | None) -> str:
    """根据 business_category 推荐 A16 变体 wp_code。

    匹配规则（按 A16_CATEGORY_MAP 键顺序优先）：
    - 含 "IPO" → A16-3
    - 含 "上市" 或 "listed" → A16-2
    - 含 "新三板" → A16-5
    - 含 "企业债" 或 "债券" → A16-6
    - 其他（含 None/空串）→ A16-1
    """
    if not business_category:
        return A16_DEFAULT
    for keyword, version in A16_CATEGORY_MAP.items():
        if keyword in business_category:
            return version
    return A16_DEFAULT


def get_a16_label(wp_code: str) -> str:
    """获取 A16 变体的中文标签。未知编码返回空串。"""
    return A16_LABELS.get(wp_code, "")
