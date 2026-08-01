"""F2 存货分类归类规则（**按科目名称**，零依赖纯函数）。

═══════════════════════════════════════════════════════════════════════════════
为什么必须按名称而不是按编码
═══════════════════════════════════════════════════════════════════════════════

postgres 只读实证（``account_chart`` 表 ``source='standard'``，9 个真实项目，
2026-08-01）：库内**并存两个互不兼容的标准存货科目表变体**，冲突恰好落在 F2
最核心的几个科目上：

===========  ==========================  ==========================
科目码        变体 A（3 个项目）            变体 B（5 个项目）
===========  ==========================  ==========================
``1405``     自制半成品                    **库存商品**
``1406``     **库存商品**                  发出商品
``1407``     发出商品                      **商品进销差价**
``1408``     **商品进销差价**              委托加工物资
``1409``     周转材料                      ——
``1411``     委托加工物资                  **周转材料**
``1416``     **存货跌价准备**（5 项目）     ——
``1451``     包装物                        损余物资
``1461``     ——                           **存货跌价准备**（6 项目）
===========  ==========================  ==========================

变体 B 是 CAS 2006 官方口径；变体 A 是本地化改编。

→ **不存在一组「写死就对」的存货科目编码**。同一个 ``1406`` 在一半项目是
「库存商品」、另一半是「发出商品」。故 F2-1 审定表的分类归集必须以**科目名称**为判据。

这不是新范式，平台已有两处同款先例：

- ``_n4_taxes_and_surcharges._classify_n4_subaccount(name)`` —— ``6403`` 子科目编码
  语义客户间冲突（``6403.02`` 既是「城市维护建设税」也是「车船税」）；
- ``_f1_prepayment.classify_f1_nature(name)`` —— ``1123`` 叶子名带业务语义。

spec: .kiro/specs/f2-inventory-account-mapping-and-linkage/ (Task 1.1)
"""

from __future__ import annotations

import re

#: 未命中任何关键字的兜底桶（不丢科目 —— Property 1 要求桶之和 == 全集）。
F2_CATEGORY_DEFAULT = "other"

#: 备抵（跌价准备）桶 rowKey —— 与 `_f2_inventory_main.F2_CATEGORIES` 逐字一致。
F2_IMPAIRMENT_ROW_KEY = "impairment-provision"

#: 归类规则：``(rowKey, 关键字元组)``，**顺序即优先级**。
#:
#: 🔴 每条顺序都对应一次实测冲突，改动前请读注释：
#:
#: 1. ``跌价准备`` / ``减值准备`` **必须最先** —— 客户子科目名实测有
#:    ``存货跌价准备_库存商品`` / ``存货跌价准备_原材料`` / ``存货跌价准备_周转材料``
#:    / ``存货跌价准备_自制半成品``。若先命中「库存商品」，备抵（全库期末
#:    −4,149,232.42）会被算进原值反向抵减。
#: 2. ``合同履约成本`` / ``合同取得成本`` 先于任何含「成本」的泛词。
#: 3. ``材料采购`` / ``在途物资`` 先于 ``原材料`` —— 「材料采购」含「材料」。
#: 4. ``自制半成品`` 组含 ``在产品`` / ``生产成本``（客户把在产品挂 5001 生产成本时
#:    仍归本桶，与审定表「自制半成品/在产品」行同义）。
#: 5. ``库存商品`` 组放最后作宽兜底。
F2_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # ── 备抵（最高优先级，见注释 1）────────────────────────────────────────
    (F2_IMPAIRMENT_ROW_KEY, ("跌价准备", "减值准备")),
    # ── 有限定词的具体类别（见注释 2）──────────────────────────────────────
    ("price-difference", ("进销差价",)),
    ("contract-performance", ("合同履约成本", "合同取得成本", "合同成本")),
    ("consumable-bio", ("消耗性生物资产", "生物资产")),
    ("dev-products", ("开发产品",)),
    ("dev-costs", ("开发成本",)),
    ("goods-in-transit", ("发出商品",)),
    ("semi-finished", ("自制半成品", "半成品", "在产品", "生产成本")),
    ("outsourced-processing", ("委托加工",)),
    ("revolving-materials", ("周转材料", "低值易耗品", "包装物", "损余物资")),
    # ── 材料类（见注释 3）──────────────────────────────────────────────────
    ("material-in-transit", ("材料采购", "在途物资")),
    ("raw-materials", ("原材料", "材料成本差异")),
    # ── 宽兜底（见注释 5）──────────────────────────────────────────────────
    ("finished-goods", ("库存商品", "产成品", "商品", "贵金属", "抵债资产")),
)

#: 全部合法 rowKey（含兜底桶），供守卫做闭集断言。
F2_CATEGORY_ROW_KEYS: tuple[str, ...] = tuple(
    dict.fromkeys([r for r, _ in F2_CATEGORY_RULES] + [F2_CATEGORY_DEFAULT])
)


def _norm(name: str | None) -> str:
    """去空白归一（客户科目名常带全/半角空格与下划线分隔）。"""
    return re.sub(r"\s+", "", str(name or ""))


def classify_f2_category(account_name: str | None) -> str:
    """按**科目名称**把存货科目归入 F2-1 审定表分类 rowKey。

    Args:
        account_name: 科目名称（一级或子科目均可）。

    Returns:
        rowKey；未命中任何关键字返回 :data:`F2_CATEGORY_DEFAULT`（``"other"``）。

    Examples:
        >>> classify_f2_category("库存商品")
        'finished-goods'
        >>> classify_f2_category("存货跌价准备_库存商品")   # 备抵优先于原值
        'impairment-provision'
        >>> classify_f2_category("材料采购")               # 不是原材料
        'material-in-transit'
        >>> classify_f2_category("修复件")                 # 纯客户命名 → 兜底
        'other'
    """
    name = _norm(account_name)
    if not name:
        return F2_CATEGORY_DEFAULT
    for row_key, hints in F2_CATEGORY_RULES:
        if any(h in name for h in hints):
            return row_key
    return F2_CATEGORY_DEFAULT


def classify_f2_leaf(
    leaf_name: str | None, parent_name: str | None = None
) -> str:
    """叶子科目归类：先按叶子自身名，未命中时回退**父级一级科目名**。

    客户账套里叶子名可能是纯业务命名而不带类别词（实证 ``1405.03 修复件`` /
    ``1405.01 新车`` / ``1405.02 旧车``，父级是「自制半成品」）→ 只看叶子名会
    整段落进 ``other``。

    父级名也未命中时归 ``other``（**不臆造** —— 由溯源面板列出科目码供人工判断）。

    Examples:
        >>> classify_f2_leaf("修复件", "自制半成品")
        'semi-finished'
        >>> classify_f2_leaf("修复件", None)
        'other'
        >>> classify_f2_leaf("库存商品_外购商品（零售）", "库存商品")
        'finished-goods'
    """
    own = classify_f2_category(leaf_name)
    if own != F2_CATEGORY_DEFAULT:
        return own
    if parent_name:
        return classify_f2_category(parent_name)
    return F2_CATEGORY_DEFAULT


def is_f2_impairment_category(row_key: str | None) -> bool:
    """该分类是否为备抵（跌价准备）—— 聚合时需取绝对值。"""
    return str(row_key or "") == F2_IMPAIRMENT_ROW_KEY


def top_level_code(account_code: str | None) -> str:
    """取一级科目段（首个 ``.`` 之前），用于查父级科目名。"""
    return str(account_code or "").strip().split(".", 1)[0]
