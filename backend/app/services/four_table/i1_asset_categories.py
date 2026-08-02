"""I1 无形资产：叶子科目 → 资产类别 的**单一真源**（纯数据 + 纯函数，零 IO）。

**类别真源在源模板哪里**

I1 源模板 `底稿目录!A8` 逐字写着「无形资产类别设置（以下内容请根据实际情况修改）：」，
`A9:A19` 是 11 个类别、`A20` 是 `……`（动态扩行标记）。这批类别在两个披露 sheet 里
分别以**列**和**行**出现：

- `附注披露信息（上市公司）!B10:L10` 逐格是 ``=底稿目录!A9`` … ``=底稿目录!A19``
  （`K10` 例外，写死「数据资源」），`M10` 是「合计」→ **类别作列（列转置）**
- `附注披露信息（国有企业）!A9:A20` 是「其中：土地使用权」…「其他」「……」，
  四层（原价 / 累计摊销 / 减值准备 / 账面价值）各重复一遍 → **类别作行**

所以「类别」是**项目级可配置项**，不是平台写死的枚举。本模块给的是**默认序列 + 归类规则**，
运行态以项目配置为准（前端 `i1CategoryScope.ts` 消费 :func:`category_defs_payload`）。

**为什么只能按科目名称归类**

`1701` 的二级子科目编码是客户自定义的（`account_chart` 里 `source='standard'` 只有一级
`1701`/`1702`/`1703`）。实证某客户是 `.01 土地使用权 / .02 软件 / .03 专利权 /
.04 非专利技术 / .05 商标权 / .06 特许经营权` —— 换一家客户编码顺序就变（平台已有 `6403`
税种编码跨客户冲突、`1405/1406` 存货编码两版并存的实证）。故编码不作判定依据。

**归类顺序铁律**

``非专利技术`` 必须先于 ``专利权``（后者是前者的子串）；``住房使用权`` 与 ``土地使用权``
各用完整词而非「使用权」；``其他`` 作宽兜底放最后。打乱 :data:`I1_ASSET_CATEGORIES` 顺序
时守卫会红（反向自检）。

spec: .kiro/specs/i-cycle-four-table-extraction-and-disclosure-alignment/
      Requirements 4.1 / 4.2 / 7.1 / 7.2，Property 5
"""
from __future__ import annotations

from dataclasses import dataclass

#: 源模板 sheet 名（守卫解析 ``source_ref`` 用；与源 xlsx tab 名逐字一致）
SHEET_INDEX = "底稿目录"
SHEET_DISCLOSURE_LISTED = "附注披露信息（上市公司）"
SHEET_DISCLOSURE_SOE = "附注披露信息（国有企业）"

#: 未命中任何类别时的归属桶键（调用方同时把该叶子记入 `unmapped`，见 R4.2）
CATEGORY_OTHER = "other"


@dataclass(frozen=True)
class I1Category:
    """一个无形资产类别的声明。

    Attributes:
        key: 稳定键（英文）。前后端、持久化、列 key 全用它 —— **不用中文 label 作键**
            （用户可改名，改名后 label 会变）。
        label: 默认中文标签，逐字取自源模板（见 ``source_ref``）。
        source_ref: ``('sheet名!单元格', ...)``；守卫用 openpyxl 直读，要求 ``label``
            在其中任一单元格文本（去空白与「其中：」前缀后）命中。
        name_keywords: 科目名称命中词（任一命中即归本类）。
        exclude_keywords: 名称否决词（命中任一即跳过本类）。
        priority: 判定顺序，数字小者先判（先具体后泛化）。
        seq: 默认序号，决定披露表列序 / 行序（与源模板 A9..A19 的行序一致）。
    """

    key: str
    label: str
    source_ref: tuple[str, ...]
    name_keywords: tuple[str, ...]
    exclude_keywords: tuple[str, ...] = ()
    priority: int = 0
    seq: int = 0


#: 🔴 唯一真源。改标签 / 加类别只改这里；守卫会要求 ``source_ref`` 能回溯到源模板。
#: ``seq`` 与源模板 `底稿目录!A9:A19` 行序一致（上市列序 B..L、国企行序 R9..R19）。
I1_ASSET_CATEGORIES: tuple[I1Category, ...] = (
    I1Category(
        key="patent_free_tech",
        label="非专利技术",
        source_ref=(f"{SHEET_INDEX}!A12", f"{SHEET_DISCLOSURE_SOE}!A12"),
        name_keywords=("非专利技术",),
        # 「非专利技术」含「专利」→ 必须先于 patent 判定，否则被 patent 吃掉
        priority=10,
        seq=4,
    ),
    I1Category(
        key="land_use_right",
        label="土地使用权",
        # 上市 sheet 的 B10 是公式 `=底稿目录!A9`（非字面量），故不作 source_ref
        source_ref=(f"{SHEET_INDEX}!A9", f"{SHEET_DISCLOSURE_SOE}!A9"),
        name_keywords=("土地使用权", "土地"),
        priority=20,
        seq=1,
    ),
    I1Category(
        key="housing_use_right",
        label="住房使用权",
        source_ref=(f"{SHEET_INDEX}!A10", f"{SHEET_DISCLOSURE_SOE}!A10"),
        name_keywords=("住房使用权", "住房"),
        priority=30,
        seq=2,
    ),
    I1Category(
        key="patent",
        label="专利权",
        source_ref=(f"{SHEET_INDEX}!A11", f"{SHEET_DISCLOSURE_SOE}!A11"),
        name_keywords=("专利权", "专利"),
        exclude_keywords=("非专利",),
        priority=40,
        seq=3,
    ),
    I1Category(
        key="trademark",
        label="商标权",
        source_ref=(f"{SHEET_INDEX}!A13", f"{SHEET_DISCLOSURE_SOE}!A13"),
        name_keywords=("商标权", "商标"),
        priority=50,
        seq=5,
    ),
    I1Category(
        key="copyright",
        label="著作权",
        source_ref=(f"{SHEET_INDEX}!A14", f"{SHEET_DISCLOSURE_SOE}!A14"),
        name_keywords=("著作权", "版权"),
        priority=60,
        seq=6,
    ),
    I1Category(
        key="franchise",
        label="特许经营权",
        source_ref=(f"{SHEET_INDEX}!A15", f"{SHEET_DISCLOSURE_SOE}!A15"),
        name_keywords=("特许经营权", "特许"),
        priority=70,
        seq=7,
    ),
    I1Category(
        key="software",
        label="软件",
        source_ref=(f"{SHEET_INDEX}!A16", f"{SHEET_DISCLOSURE_SOE}!A16"),
        name_keywords=("软件", "系统"),
        priority=80,
        seq=8,
    ),
    I1Category(
        key="mining_right",
        label="矿产权",
        source_ref=(f"{SHEET_INDEX}!A17", f"{SHEET_DISCLOSURE_SOE}!A17"),
        name_keywords=("矿产权", "采矿权", "探矿权", "矿权"),
        priority=90,
        seq=9,
    ),
    I1Category(
        key="data_resource",
        label="数据资源",
        source_ref=(
            f"{SHEET_INDEX}!A18",
            f"{SHEET_DISCLOSURE_SOE}!A18",
            f"{SHEET_DISCLOSURE_LISTED}!K10",
        ),
        name_keywords=("数据资源", "数据"),
        priority=100,
        seq=10,
    ),
    I1Category(
        key=CATEGORY_OTHER,
        label="其他",
        source_ref=(f"{SHEET_INDEX}!A19", f"{SHEET_DISCLOSURE_SOE}!A19"),
        name_keywords=("其他",),
        # 宽兜底放最后：只有前面全不命中才用它
        priority=999,
        seq=11,
    ),
)

#: 三大段（原值 / 累计摊销 / 减值准备）的段键 —— 与 render 的 `adjudication_prefill` 对应
SEGMENT_COST = "cost"
SEGMENT_AMORTIZATION = "amortization"
SEGMENT_IMPAIRMENT = "impairment"

#: 段键 → 源模板国企 sheet 的层标题（守卫交叉比对用）
SEGMENT_SOURCE_REF: dict[str, str] = {
    SEGMENT_COST: f"{SHEET_DISCLOSURE_SOE}!A8",           # 一、原价合计
    SEGMENT_AMORTIZATION: f"{SHEET_DISCLOSURE_SOE}!A21",  # 二、累计摊销合计
    SEGMENT_IMPAIRMENT: f"{SHEET_DISCLOSURE_SOE}!A34",    # 三、无形资产减值准备合计
}

_BY_KEY: dict[str, I1Category] = {c.key: c for c in I1_ASSET_CATEGORIES}
_ORDERED: tuple[I1Category, ...] = tuple(
    sorted(I1_ASSET_CATEGORIES, key=lambda c: c.priority)
)
_BY_SEQ: tuple[I1Category, ...] = tuple(
    sorted(I1_ASSET_CATEGORIES, key=lambda c: c.seq)
)


def category_def(key: str) -> I1Category | None:
    """按类别键取声明；未知键返 ``None``。"""
    return _BY_KEY.get((key or "").strip())


def category_label(key: str) -> str:
    """按类别键取默认中文标签；未知键返键本身（不编造）。"""
    c = category_def(key)
    return c.label if c else (key or "")


def classify_i1_leaf(name: str, code: str = "") -> str | None:
    """把一个叶子科目归入资产类别。**只按名称**，纯函数。

    判定按 :attr:`I1Category.priority` 升序，首个「命中 ``name_keywords`` 且不命中
    ``exclude_keywords``」的类别胜出。

    Args:
        name: `tb_balance.account_name`，形如 ``无形资产_土地使用权`` /
            ``累计摊销_软件`` / ``无形资产减值准备_非专利技术``。
        code: 科目码，仅用于日志与 ``unmapped`` 回溯，**不参与判定**（客户自定义编码
            跨项目冲突，见模块 docstring）。

    Returns:
        类别键；无法归类返回 ``None`` —— 调用方须归入 :data:`CATEGORY_OTHER`
        **并同时记入 `unmapped`**（R4.2），不得静默丢弃。

    实证样本（`tb_balance` 全库）::

        无形资产_土地使用权          → land_use_right
        无形资产_软件                → software
        无形资产_专利权              → patent
        无形资产_非专利技术          → patent_free_tech   ← 不是 patent
        无形资产_商标权              → trademark
        无形资产_特许经营权          → franchise
        累计摊销_土地使用权          → land_use_right
        无形资产减值准备_非专利技术  → patent_free_tech
        无形资产（仅父级、无子科目）  → None（归 other 且进 unmapped）
    """
    nm = (name or "").strip()
    if not nm:
        return None
    for c in _ORDERED:
        if c.exclude_keywords and any(k in nm for k in c.exclude_keywords):
            continue
        if any(k in nm for k in c.name_keywords):
            return c.key
    return None


def default_category_keys() -> list[str]:
    """默认类别键序列（按 ``seq``，与源模板 `底稿目录!A9:A19` 行序一致）。"""
    return [c.key for c in _BY_SEQ]


def category_defs_payload() -> list[dict]:
    """供 render 下发前端的类别声明（前端**不再抄一份中文标签**）。

    只透出前端需要的字段：键 / 标签 / 序号；关键字与 ``source_ref`` 是后端判定与
    守卫用的实现细节，不外泄。
    """
    return [{"key": c.key, "label": c.label, "seq": c.seq} for c in _BY_SEQ]


__all__ = [
    "CATEGORY_OTHER",
    "I1Category",
    "I1_ASSET_CATEGORIES",
    "SEGMENT_AMORTIZATION",
    "SEGMENT_COST",
    "SEGMENT_IMPAIRMENT",
    "SEGMENT_SOURCE_REF",
    "SHEET_DISCLOSURE_LISTED",
    "SHEET_DISCLOSURE_SOE",
    "SHEET_INDEX",
    "category_def",
    "category_defs_payload",
    "category_label",
    "classify_i1_leaf",
    "default_category_keys",
]
