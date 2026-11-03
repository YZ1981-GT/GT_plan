"""A16 智能模板选择 — 纯逻辑，无 DB 访问.

按项目分类 / 专项场景（``project_classification`` 单一解释）推荐 A16 声明书版本。
原先按 ``business_category`` 自由文本找关键词（IPO / 上市 / 新三板 / 企业债）；分类列只放质控分类码后，
同样的含义来自适用性标签（场景 + A1/A2/A7/B1 等细分类 + 上市公司报表模板）与 B2（债券发行）细分类。
"""

from __future__ import annotations

from app.services.project_classification import ProjectClassification, resolve

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

A16_CATEGORY_MAP: dict[str, str] = {
    "ipo": "A16-3",
    "listed": "A16-2",
    "neeq": "A16-5",
    "B2": "A16-6",
}
"""适用性标签（或细分类码 B2 债券发行）→ 推荐的 A16 版本；按键顺序优先。"""

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


def recommend_a16_version(project: ProjectClassification | str | None) -> str:
    """推荐 A16 变体 wp_code。``project`` 是项目分类（推荐）或分类列原值（按 ``resolve`` 解释）。

    匹配规则（按 A16_CATEGORY_MAP 键顺序优先）：
    - IPO（场景 ipo / 细分类 A2 / 迁移前残留的分类值 IPO）→ A16-3
    - 上市（场景 listed / 细分类 A1、A7 / 上市公司报表模板）→ A16-2
    - 新三板（场景 transfer / 细分类 B1）→ A16-5
    - 细分类 B2（债券发行）→ A16-6
    - 其他（含未填写）→ A16-1
    """
    classification = project if isinstance(project, ProjectClassification) else resolve(project)
    for key, version in A16_CATEGORY_MAP.items():
        if classification.has_tag(key) or classification.category_code == key:
            return version
    return A16_DEFAULT


def get_a16_label(wp_code: str) -> str:
    """获取 A16 变体的中文标签。未知编码返回空串。"""
    return A16_LABELS.get(wp_code, "")
