"""G5 长期应收款性质分类桶 — 叶子子科目按名称归类.

源模板 `backend/wp_templates/G/G5 长期应收款.xlsx` 「附注披露信息」sheet
性质分类行（两版一致）：
  R9  融资租赁款（其中：未实现融资收益）
  R11/R12 分期收款销售商品（其中：未实现融资收益）
  R13 分期收款提供劳务
  R16 其他（兜底）
  R17 小  计 / R18 减：1年内到期 / R19 合  计

活体 tb_balance 叶子名：
  1531.01 = 押金 / 应收融资租赁款
  1531.02 = 借款 / 长期保证金 / 应收长期借款
  1531.03 = 担保
  1531.11 = 分期收款销售商品
  1531.99 = 一年内到期的长期应收款（扣减行）

设计与 F1 (1123→五性质桶) / G7 (1511→投资分类) 同模式。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class G5NatureBucket:
    """性质分类桶定义."""

    key: str
    label: str
    keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    source_ref: str = ''


# 顺序即优先级：先长匹配后短匹配，兜底 `other` 必须最后
G5_NATURE_BUCKETS: list[G5NatureBucket] = [
    G5NatureBucket(
        key='one_year_due',
        label='1年内到期的长期应收款',
        keywords=('一年内到期', '1年内到期'),
        source_ref='R18/R20',
    ),
    G5NatureBucket(
        key='finance_lease',
        label='融资租赁款',
        keywords=('融资租赁',),
        source_ref='R9/R10',
    ),
    G5NatureBucket(
        key='installment_goods',
        label='分期收款销售商品',
        keywords=('分期收款销售',),
        exclude_keywords=('劳务',),
        source_ref='R11/R12',
    ),
    G5NatureBucket(
        key='installment_service',
        label='分期收款提供劳务',
        keywords=('分期收款提供劳务', '分期收款劳务', '分期劳务'),
        source_ref='R13',
    ),
    G5NatureBucket(
        key='deposit',
        label='押金保证金',
        keywords=('押金', '保证金'),
        exclude_keywords=('融资',),
        source_ref='R16:deposit',
    ),
    G5NatureBucket(
        key='loan',
        label='借款',
        keywords=('借款',),
        exclude_keywords=('融资',),
        source_ref='R16:loan',
    ),
    G5NatureBucket(
        key='guarantee',
        label='担保',
        keywords=('担保',),
        source_ref='R16:guarantee',
    ),
    G5NatureBucket(
        key='other',
        label='其他',
        keywords=(),  # 兜底桶无关键词
        source_ref='R16',
    ),
]


def classify_g5_leaf(name: str, code: str = '') -> str:
    """将叶子科目按名称归入性质桶.

    Args:
        name: 科目名称（可能带前缀 `长期应收款_`）
        code: 科目编码（如 `1531.01`）

    Returns:
        桶 key（如 `finance_lease`）
    """
    # 清洗名称
    cleaned = name.replace('长期应收款_', '').replace('长期应收款', '').strip()
    if not cleaned:
        cleaned = name.strip()

    for bucket in G5_NATURE_BUCKETS:
        if not bucket.keywords:
            continue  # 跳过兜底桶
        # 否决词检查
        if bucket.exclude_keywords and any(
            ew in cleaned for ew in bucket.exclude_keywords
        ):
            continue
        # 关键词匹配
        if any(kw in cleaned for kw in bucket.keywords):
            return bucket.key

    # 编码后缀兜底
    suffix = code.replace('1531', '').lstrip('.')
    if suffix == '99' or suffix.startswith('99'):
        return 'one_year_due'

    return 'other'


def bucket_defs_payload() -> list[dict]:
    """下发前端的桶定义列表（中文标签只一份）."""
    return [
        {'key': b.key, 'label': b.label}
        for b in G5_NATURE_BUCKETS
        if b.key != 'one_year_due'  # 一年内到期是扣减行，不在性质表展示
    ]
