"""E1 受限制货币资金的分类真源（跨变体共享，上市/国企同一套）。

**为什么需要按名称分类而不是写死科目码**

受限资金没有独立的标准科目 —— 它是货币资金（``1001``/``1002``/``1012``）里
「用途受限」的那一部分，客户各自用二级/三级子科目承载，命名千差万别：

- 有的挂在 ``1012 其他货币资金`` 下，叫「银行承兑汇票保证金」「信用证保证金」
- 有的挂在 ``1002 银行存款`` 下的定期户，叫「质押定期存款」「冻结存款」
- 也有完全不含受限关键字的（实证项目 ``df5b8403`` 的 ``1012`` 叶子全是支付渠道名：
  「金华支付宝」「微信小程序」「聚合收款」「AFO」「小桔有车」）

所以取数链路是：``BS-002`` 报表行解析 → ``account_mapping`` 反解出项目原始码前缀 →
``select_leaves`` 取叶子 → **逐叶子按名称分类**；命中不了的一律落 ``unclassified``
交审计师点选归类，**不臆造归属**（宁缺勿造铁律）。

**顺序即优先级**

``E1_RESTRICTED_BUCKETS`` 的声明顺序就是匹配优先级，含包含关系的必须先声明：

- 「信用证保证金」先于「银行承兑汇票保证金」与兜底桶 —— 三者都含「保证金」
- 「担保/质押/冻结」先于泛「定期存款/通知存款」
- 「结构性存款」是 ``pledged_deposit`` 的**否决词** —— 结构性存款不等于质押受限

守卫 ``test_e1_restricted_buckets.py`` 用打乱顺序的反向自检钉死这一点。

spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/
      Requirements 11.1~11.5 / Property 10, 15, 16
"""
from __future__ import annotations

from dataclasses import dataclass

#: 「标记为不受限」的哨兵值（人工归类 map 里用），非桶 key
UNRESTRICTED = "__unrestricted__"


@dataclass(frozen=True)
class E1RestrictedBucket:
    """受限资金分类桶（声明式，纯数据）。

    Attributes:
        key: 稳定标识（持久化人工归类 map 用，**不可改**）。
        label: 中文标签 —— 逐字取自源 xlsx，中文标签**只在此处一份**，前端从
            ``bucket_defs_payload()`` 取（避免前后端双真源漂移）。
        keywords: 名称命中词（任一命中即归入本桶）。
        exclude_keywords: 否决词（命中任一则**不**归入本桶，继续往后匹配）。
        source_ref: 源 xlsx 单元格引用，供 openpyxl 守卫反查标签是否逐字一致。
            ``None`` 表示平台补充桶（源模板无对应行）。
    """

    key: str
    label: str
    keywords: tuple[str, ...]
    exclude_keywords: tuple[str, ...] = ()
    #: **共现要求**：非空时，除命中 ``keywords`` 外还必须命中其中任一，否则不归本桶。
    #: 🔴 为「境外」桶而设：源模板 R21 是「放在境外**且资金汇回受到限制**的款项」——
    #: 光是境外并不等于受限（香港子公司基本户是境外但不受限），若只靠「境外」二字
    #: 归类会把正常境外账户误判成受限款项（**这是会改变披露结论的错**）。
    require_any_of: tuple[str, ...] = ()
    source_ref: str | None = None


#: 受限分类桶（**顺序即优先级**，改顺序会改语义 —— 守卫钉死）
#:
#: 前 5 桶逐字取自源 xlsx「附注披露信息(国企)」R17~R21；第 6 桶为平台补充兜底。
E1_RESTRICTED_BUCKETS: tuple[E1RestrictedBucket, ...] = (
    # 「信用证」必须先于「银行承兑」与兜底桶：三者名称都可能含「保证金」
    E1RestrictedBucket(
        key="letter_of_credit",
        label="信用证保证金",
        keywords=("信用证",),
        source_ref="附注披露信息(国企)!A18",
    ),
    E1RestrictedBucket(
        key="bank_acceptance",
        label="银行承兑汇票保证金",
        keywords=("银行承兑", "承兑汇票", "银承"),
        source_ref="附注披露信息(国企)!A17",
    ),
    E1RestrictedBucket(
        key="performance",
        label="履约保证金",
        keywords=("履约",),
        source_ref="附注披露信息(国企)!A19",
    ),
    # 🔴 「境外」必须先于「质押」：`境外冻结存款` 同时含「冻结」与「境外」，
    # 而上市规则要求「存放境外且汇回受限」**单独披露** → 境外优先级更高。
    # 同时要求共现受限指示词，避免把正常境外账户误判为受限。
    E1RestrictedBucket(
        key="overseas",
        label="放在境外且资金汇回受到限制的款项",
        keywords=("境外", "海外", "离岸"),
        require_any_of=("受限", "限制", "冻结", "管制", "汇回", "不可"),
        source_ref="附注披露信息(国企)!A21",
    ),
    # 「担保/质押/冻结」先于泛「定期存款」；「结构性存款」不算质押受限 → 否决。
    # 🔴 不放裸「保证」——「投标保证金」不是定期/通知存款，应落兜底桶而非本桶。
    E1RestrictedBucket(
        key="pledged_deposit",
        label="用于担保的定期存款或通知存款",
        keywords=("担保", "质押", "冻结", "定期存款", "通知存款"),
        exclude_keywords=("结构性",),
        source_ref="附注披露信息(国企)!A20",
    ),
    # 兜底桶：确属受限但归不进上面任一类（如投标保证金 / 专项监管专户）
    E1RestrictedBucket(
        key="other",
        label="其他受限资金",
        keywords=("保证金", "受限", "限制", "专户", "专项存款", "监管"),
        source_ref=None,
    ),
)

#: key → 桶（供人工归类 map 反查）
E1_RESTRICTED_BUCKET_BY_KEY: dict[str, E1RestrictedBucket] = {
    b.key: b for b in E1_RESTRICTED_BUCKETS
}


def classify_e1_restricted_leaf(name: str) -> str | None:
    """按科目名称判定受限桶；**未命中返回 ``None``**（宁缺勿造）。

    纯函数。名称优先 + 否决词否决 + 顺序即优先级。

    Args:
        name: ``tb_balance.account_name``（叶子科目名）。

    Returns:
        桶 ``key``，或 ``None`` 表示无法判定（应落 ``unclassified`` 交人工归类）。

    实证：项目 ``df5b8403`` 的货币资金叶子名全部返回 ``None`` —— 「金华招行基本户801」
    「金华结构性存款账户」「金华支付宝」「微信小程序」「聚合收款」「AFO」「小桔有车」
    都不含受限关键字，这是**设计如此**而非缺陷。
    """
    text = (name or "").strip()
    if not text:
        return None
    for bucket in E1_RESTRICTED_BUCKETS:
        if any(kw in text for kw in bucket.exclude_keywords):
            continue
        if not any(kw in text for kw in bucket.keywords):
            continue
        # 共现要求（目前只有「境外」桶用）：光命中主关键字不够
        if bucket.require_any_of and not any(
            kw in text for kw in bucket.require_any_of
        ):
            continue
        return bucket.key
    return None


def bucket_defs_payload() -> list[dict]:
    """下发前端的桶定义（中文标签的唯一来源，前端不再抄一份）。"""
    return [
        {
            "key": b.key,
            "label": b.label,
            "isPlatformExtra": b.source_ref is None,
        }
        for b in E1_RESTRICTED_BUCKETS
    ]
