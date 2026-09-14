"""F2 存货审定表取数公式锚点注册表.

锚点格式：F2-1-{block}-{rowKey}-{field}
block ∈ {gross, impairment}
field ∈ {opening, increase, decrease}
"""
from __future__ import annotations

# 原值 12 类 rowKey
_GROSS_ROW_KEYS = (
    "raw-materials", "material-in-transit", "revolving-materials",
    "semi-finished", "outsourced-processing", "finished-goods",
    "goods-in-transit", "dev-products", "dev-costs",
    "contract-performance", "consumable-bio", "price-difference",
)

# 跌价 rowKey
_IMPAIRMENT_ROW_KEYS = ("impairment-provision",)

_FIELDS = ("opening", "increase", "decrease")

# 39 项锚点集合
F2_ANCHORS: frozenset[str] = frozenset(
    f"F2-1-{block}-{row_key}-{field}"
    for block, row_keys in [("gross", _GROSS_ROW_KEYS), ("impairment", _IMPAIRMENT_ROW_KEYS)]
    for row_key in row_keys
    for field in _FIELDS
)


def is_known_anchor(anchor: str) -> bool:
    """校验 anchor 是否属于 F2-1 真实锚点集合."""
    return anchor in F2_ANCHORS


def seed_field(anchor: str) -> str | None:
    """返回该锚点在 checklist_responses 中的存储字段名.

    F2-1 所有锚点值存 conclusion 字段（前端 loadField 读 .conclusion）。
    未知锚点返回 None。
    """
    if anchor in F2_ANCHORS:
        return "conclusion"
    return None
