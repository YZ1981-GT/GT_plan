"""F5 营业成本 —— 成本分段分类桶单一真源（主营业务成本 / 其他业务成本）。

**报表行真源**（`report_config` DB 实证，四准则一致）::

    IS-002 减：营业成本 = SUM_TB('6401~6499','本期发生额')

原实现 `_f5_cost_of_sales.py` 用裸 SQL ``standard_account_code LIKE '6401%'``，
**漏掉全部其他业务成本**（`6402` / `6404`）→ F5-1「试算平衡表数」少算，
「差异数」行常亮假告警。

**为什么按名称归类而不是按编码**

`account_chart` 只读实证（10 个在册项目）::

    6401  主营业务成本（5 个项目） / 营业成本（7 个项目）
    6402  其他业务成本（6 个项目） / 其他业务支出（1 个项目 df5b8403）
    6404  其他业务成本（1 个项目）          ← 同一项目里 6402 是「其他业务支出」

即「其他业务成本」在不同项目分别编在 `6402` 与 `6404`，且 `6402` 在某项目是
「其他业务支出」（源模板 F5-3 提示第 2 条明确「除主营业务活动以外的其他经营活动发生
的相关税费在营业税金及附加科目核算」，故「其他业务支出」与「其他业务成本」同义）。
→ 与存货 `14xx`、税金及附加 `6403` 同款，**不存在一组写死就对的编码**。

**否决词是必需的**：``其他业务成本`` 含子串「业务成本」，若 ``main`` 段的关键字里有
「业务成本」会把它吃掉；故 ``main`` 必须声明 ``exclude_keywords=('其他业务',)``。

**损益类取数口径**（Requirement 3.2 / Property 6）

`tb_balance` 的损益类科目在含年末结转损益的全年账上 ``debit_amount ==
credit_amount``，实证项目 `2aa00f57` 的 `6401` 四行 ``debit − credit`` **全为 0.00**::

    6401         营业成本            dr 403,902,148.13  cr 403,902,148.13  net 0.00
    6401.12      营业成本_零售        dr 403,902,148.13  cr 403,902,148.13  net 0.00
    6401.12.01   零售_货物成本        dr 404,670,957.97  cr 404,670,957.97  net 0.00
    6401.12.02   零售_成本差异        dr    −768,809.84  cr    −768,809.84  net 0.00

正确口径 = **叶子的 `debit_amount` 之和**（保留符号）：
404,670,957.97 − 768,809.84 = 403,902,148.13 = 父科目借方 ✓

spec: .kiro/specs/f-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 3.1~3.3 / Property 4, 6
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .leaf_aggregation import LeafRow


@dataclass(frozen=True)
class F5Segment:
    """一个成本分段的声明（纯数据）。

    Attributes:
        key: 分段键，与前端 `useF5Adjudication` 的两段存储键一致。
        label: 中文标签，只在此处声明一份。
        keywords: 名称匹配关键字。
        exclude_keywords: 否决词（``main`` 必须排除「其他业务」）。
        source_ref: 源 xlsx 单元格。
        is_catchall: 兜底段。
    """

    key: str
    label: str
    keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    source_ref: str = ""
    is_catchall: bool = False


#: 成本分段。**顺序即优先级** —— ``other`` 必须先于 ``main``（双保险：即便
#: ``main`` 的否决词被误删，``other`` 先命中仍能正确归类；反向自检会验证这一点）。
F5_SEGMENTS: tuple[F5Segment, ...] = (
    F5Segment(
        key="other",
        label="其他业务成本",
        # 「其他业务支出」是同义命名（实证项目 df5b8403 的 6402）
        keywords=("其他业务成本", "其他业务支出", "其他业务"),
        source_ref="营业务成本审定表F5-1!A19",
    ),
    F5Segment(
        key="main",
        label="主营业务成本",
        keywords=("主营业务成本", "主营业务", "营业成本"),
        exclude_keywords=("其他业务",),
        source_ref="营业务成本审定表F5-1!A7",
    ),
)

#: 🔴 **未命中名称的叶子不归入任何段**（宁缺勿造），进 ``unmapped`` 由溯源面板列出。
#:
#: 这条设计是被数据逼出来的：`report_config` 的 ``IS-002 = SUM_TB('6401~6499')``
#: 区间**过宽**，会把 ``6403 税金及附加``（独立报表行 ``IS-003``）一并纳入。若给一个
#: 兜底段把未命中叶子塞进「主营业务成本」，营业成本会虚增整个税金及附加
#: （实证 `0ec33ac9` 虚增 3,231,580.11）。
#:
#: 「未命中即丢弃」的正确性由 DB 只读实证背书 —— 按名称归类后的合计与
#: `trial_balance` 的 ``6401 + 6402 + 6404`` **分文不差**（9 个项目里 6 个精确相等，
#: 另 3 个的差异已定位为 `trial_balance` 侧陈旧数据，见 spec 的 Notes G1/G2）::
#:
#:     0ec33ac9  810,247,087.22 == 810,247,087.22   （排除 6403 的 3,231,580.11）
#:     52c04ed1  1,406,164,798.37 == 1,406,164,798.37
#:     a7fc75e5  6,341,450,080.45 == 6,341,450,080.45
#:     b39809ed  192,563,214.60 == 192,563,214.60
#:     c8621493  9,769,616.62 == 9,769,616.62
#:     12c15a96  810,247,087.22 == 810,247,087.22
F5_UNMAPPED_KEY = ""

#: 源模板行序（主营在前，其他在后）
F5_DISPLAY_ORDER: tuple[str, ...] = ("main", "other")


def _matches(seg: F5Segment, name: str) -> bool:
    if any(x in name for x in seg.exclude_keywords):
        return False
    return any(k in name for k in seg.keywords)


def classify_f5_leaf(account_name: str, account_code: str = "") -> str:
    """把 `6401~6499` 区间的一个叶子归入成本分段，返回 ``key``。

    只按名称判定（编码语义项目间冲突，见模块 docstring）。
    **未命中返回空串** :data:`F5_UNMAPPED_KEY` —— 不塞兜底段，见该常量的实证说明。
    """
    name = str(account_name or "")
    for seg in F5_SEGMENTS:
        if _matches(seg, name):
            return seg.key
    return F5_UNMAPPED_KEY


def f5_segment_payload() -> list[dict]:
    """下发前端的分段定义（中文标签只此一份，按源模板行序）。"""
    by_key = {s.key: s for s in F5_SEGMENTS}
    return [
        {
            "key": k,
            "label": by_key[k].label,
            "source_ref": by_key[k].source_ref,
            "keywords": list(by_key[k].keywords),
        }
        for k in F5_DISPLAY_ORDER
        if k in by_key
    ]


@dataclass(frozen=True)
class F5LeafSegment:
    """一个叶子科目的分段归类结果（供溯源面板逐叶子展示）。"""

    code: str
    name: str
    bucket: str
    bucket_label: str
    #: 损益类取**借方发生额**（保留符号），不取余额
    debit: float = 0.0
    matched_buckets: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ambiguous(self) -> bool:
        return len(self.matched_buckets) > 1

    @property
    def unmatched(self) -> bool:
        """名称未命中任何分段 —— **不进任何段**，由溯源面板列出供审计师复核。

        实测这一类主要是 ``6403 税金及附加``（`IS-002` 区间过宽把它圈进来了），
        属于报表行 `IS-003`，不应计入营业成本。
        """
        return not self.bucket

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "bucket": self.bucket,
            "bucket_label": self.bucket_label,
            "debit": round(self.debit, 2),
            "ambiguous": self.ambiguous,
            "unmatched": self.unmatched,
            "matched_buckets": list(self.matched_buckets),
        }


_LABEL_BY_KEY = {s.key: s.label for s in F5_SEGMENTS}


def _all_matched(name: str) -> tuple[str, ...]:
    return tuple(s.key for s in F5_SEGMENTS if _matches(s, name))


def build_f5_leaf_segments(leaves: list[LeafRow]) -> list[F5LeafSegment]:
    """逐叶子归类（纯函数）。

    🔴 只读 ``debit``，**绝不用 ``debit - credit``** —— 含年末结转损益的全年账上
    该差恒为 0（模块 docstring 有四行实证）。若实现改回相减，
    `test_f5_cost_segments.py` 的结转账 fixture 必红。
    """
    out: list[F5LeafSegment] = []
    for row in leaves or []:
        key = classify_f5_leaf(row.account_name, row.account_code)
        out.append(
            F5LeafSegment(
                code=row.account_code,
                name=row.account_name,
                bucket=key,
                bucket_label=_LABEL_BY_KEY.get(key, key),
                debit=row.debit,
                matched_buckets=_all_matched(row.account_name),
            )
        )
    return out


def build_f5_segment_prefill(segments: list[F5LeafSegment]) -> dict[str, dict]:
    """按分段聚合为 F5-1 预填（**未命中名称的叶子不计入**）。

    损益借方科目：正数 = 发生额，**不取绝对值**（负借方 = 冲减，如
    `6401.12.02 成本差异 = −768,809.84` 是合法冲减，翻正会让合计虚增）。

    Returns:
        ``{key: {"amount","label","codes"}}``；只含实际出现的分段。
    """
    out: dict[str, dict] = {}
    for s in segments or []:
        if s.unmatched:
            continue
        bucket = out.setdefault(
            s.bucket, {"amount": 0.0, "label": s.bucket_label, "codes": []}
        )
        bucket["amount"] += s.debit
        bucket["codes"].append(s.code)
    for bucket in out.values():
        bucket["amount"] = round(bucket["amount"], 2)
        bucket["codes"] = sorted(set(bucket["codes"]))
    return out


def build_f5_unmapped(segments: list[F5LeafSegment]) -> list[dict]:
    """未归类叶子清单（供溯源面板展示「已排除的科目」，绝不静默丢弃）。

    典型内容 = ``6403 税金及附加`` 各子科目（报表行 `IS-003`，不属营业成本）。
    """
    return [s.as_dict() for s in segments or [] if s.unmatched]


__all__ = [
    "F5_DISPLAY_ORDER",
    "F5_SEGMENTS",
    "F5_UNMAPPED_KEY",
    "F5LeafSegment",
    "F5Segment",
    "build_f5_leaf_segments",
    "build_f5_segment_prefill",
    "build_f5_unmapped",
    "classify_f5_leaf",
    "f5_segment_payload",
]
