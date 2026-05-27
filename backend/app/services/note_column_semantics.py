"""附注列语义识别引擎.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 1 Task 1.2
Design: D2 模板与绑定分离 - header_normalize.semantic 字段
Reqs:   R1.1 验收标准 2 - "列语义 ID 至少覆盖 20 个标准语义"

把 header 字面（"期末余额"/"1 年以内"/"本期增加" …）映射到 ≥ 20 个**标准
语义 ID**，供 `disclosure_engine._build_with_binding` / 模板 binding JSON
schema / `cleanup_note_templates.py` 共同消费。

设计要点
--------
1. **零副作用模块**：仅静态字典 + 纯函数，Import 不触发任何 IO，可被
   一次性脚本 / FastAPI service / pytest 共同 import。
2. **优先级（顺序敏感的 dict）**：从最具体到最宽泛排列，保证「本期增加
   （购置）」命中 `current_year_increase` 而非 `current_period_acquisition`。
3. **保守兜底**：完全无命中 → ``manual_text``（行标识列），不抛异常。
4. **常量 export**：``VALID_SEMANTICS`` 供 binding json schema 校验复用。

使用示例
--------
    >>> from backend.app.services.note_column_semantics import (
    ...     NoteColumnSemantics, VALID_SEMANTICS,
    ... )
    >>> NoteColumnSemantics.identify("期末账面价值")
    'closing_balance'
    >>> NoteColumnSemantics.identify("1 年以内")  # 全角空格也命中
    'aging_bucket_within_1y'
    >>> NoteColumnSemantics.identify("本期增加（购置）")  # 优先父语义
    'current_year_increase'
    >>> NoteColumnSemantics.identify_headers(["项目", "期末余额", "本期增加"])
    ['manual_text', 'closing_balance', 'current_year_increase']
    >>> "manual_text" in VALID_SEMANTICS
    True
"""

from __future__ import annotations

import re
from collections.abc import Iterator

# ---------------------------------------------------------------------------
# 标准语义关键词字典（顺序敏感 — 决定优先级）
# ---------------------------------------------------------------------------
#
# 优先级链（从最具体到最宽泛）：
#   1) 账龄分桶（最特殊，独立 5 桶）
#   2) provision_ratio（"计提比例"，与 current_year_provision 不冲突但更窄）
#   3) current_year_provision（"本期计提"，比 current_year_increase 更具体）
#   4) current_year_increase / decrease（变动表父列，**优先于** acquisition / disposal）
#   5) current_period_acquisition / disposal / writeoff / recover（具体动作子列）
#   6) closing_balance / opening_balance（含 "期末账面价值"，**优先于** carrying_value）
#   7) accumulated_depreciation（"累计折旧/摊销/减值"，**优先于** impairment_provision）
#   8) impairment_provision（"减值准备"）
#   9) original_value（"原值"）
#  10) carrying_value（"账面价值/净值"，仅在 6/7/8/9 都未命中时）
#  11) prior_year_value（"上年金额"）
#  12) cost / fair_value（存货/金融资产专用）
#  13) category_subtotal（"小计"）
#  14) formula_result（"公式计算"；"=" 前缀走 ``identify`` 顶部 fast-path）
#  15) manual_text（行标识列 "项目/名称"，也作完全无命中的兜底）
#
STANDARD_SEMANTICS: dict[str, list[str]] = {
    # ── 账龄分桶（5 桶）───────────────────────────────────────────────
    "aging_bucket_within_1y": ["1年以内", "1年内", "一年以内", "一年内"],
    "aging_bucket_1_2y": ["1-2年", "1至2年", "1~2年", "1—2年", "一至二年"],
    "aging_bucket_2_3y": ["2-3年", "2至3年", "2~3年", "2—3年", "二至三年"],
    "aging_bucket_3_5y": ["3-5年", "3至5年", "3~5年", "3—5年", "三至五年"],
    "aging_bucket_over_5y": ["5年以上", "五年以上", "超过5年", "5年及以上"],
    # ── 计提比例（在 current_year_provision 之前以保留 "计提比例" 词形）──
    "provision_ratio": ["计提比例", "坏账计提比例", "减值比例", "坏账比例"],
    # ── 本期计提（具体短语，先于通用 increase / decrease）───────────────
    "current_year_provision": ["本期计提坏账准备", "本期计提", "本年计提"],
    # ── 本期增减（变动表父列，优先于具体动作）────────────────────────
    "current_year_increase": ["本期增加", "本年增加", "期间增加"],
    "current_year_decrease": ["本期减少", "本年减少", "期间减少"],
    # ── 本期具体动作（子列，仅在 increase / decrease 未命中时）─────────
    "current_period_acquisition": ["本期购置", "本期购入", "购置", "购入"],
    "current_period_disposal": ["本期处置", "本期出售", "处置", "出售"],
    "current_period_writeoff": ["本期核销", "核销"],
    "current_period_recover": ["本期收回", "已收回", "收回"],
    # ── 期末 / 期初余额（含 "期末账面价值"，优先于 carrying_value）──────
    "closing_balance": [
        "期末余额",
        "期末数",
        "期末账面价值",
        "期末账面净值",
        "期末账面余额",
        "期末",
    ],
    "opening_balance": [
        "期初余额",
        "期初数",
        "期初账面价值",
        "期初账面净值",
        "期初账面余额",
        "期初",
    ],
    # ── 累计类（折旧 / 摊销 / 减值）─────────────────────────────────
    "accumulated_depreciation": ["累计折旧", "累计摊销", "累计减值"],
    # ── 减值准备（与 accumulated_depreciation 错峰：累计已先匹）──────
    "impairment_provision": ["减值准备", "减值损失累计", "减值损失"],
    # ── 原值（"账面原值/资产原值/原值"）─────────────────────────────
    "original_value": ["账面原值", "资产原值", "原值"],
    # ── 账面价值（仅在期末/期初/累计/原值都未命中时兜底）──────────
    "carrying_value": ["账面价值", "账面净值", "净值"],
    # ── 上年值 ────────────────────────────────────────────────────
    "prior_year_value": ["上年金额", "上年同期", "上年数", "上期金额", "上年"],
    # ── 成本 / 公允价值（存货 + 金融资产）────────────────────────
    "cost": ["账面成本", "成本"],
    "fair_value": ["公允价值", "重估价值"],
    # ── 小计 ──────────────────────────────────────────────────────
    "category_subtotal": ["分类小计", "小计"],
    # ── 公式计算（"=" 前缀走 fast-path，不在此处）──────────────────
    "formula_result": ["公式计算"],
    # ── 行标识列（默认兜底，也对 "项目/名称/类别" 主动命中）──────
    "manual_text": ["项目", "名称", "类别", "类型", "种类"],
}

# 所有合法 semantic_id 元组（供 binding JSON schema enum 校验复用）。
# 顺序与 ``STANDARD_SEMANTICS.keys()`` 一致，便于序列化稳定。
VALID_SEMANTICS: tuple[str, ...] = tuple(STANDARD_SEMANTICS.keys())

# 默认兜底语义（identify 完全无命中时返回）
DEFAULT_SEMANTIC: str = "manual_text"

assert DEFAULT_SEMANTIC in VALID_SEMANTICS, "default semantic must be valid"

# 全角 / 半角 / 制表符 / 换行 全部归一化为空（identify 内部使用）
_WHITESPACE_PATTERN = re.compile(r"[\s\u3000]+")


def _normalize(text: object) -> str:
    """全角空格 + 多空白归一，None / 非字符串 → 空串.

    例：``"1 年以内"`` → ``"1年以内"``；``"期末余额（无单位）"`` 保持不变。
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return _WHITESPACE_PATTERN.sub("", text).strip()


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------


class NoteColumnSemantics:
    """附注列语义识别引擎（无状态，全部为 classmethod）.

    与 design.md D2 的 ``header_normalize[*].semantic`` 字段对齐：
        {"text": "期末账面价值", "semantic": "closing_balance"}

    与 R1.1 验收标准 2 对齐：≥ 20 个标准语义，含期末/期初/本期增减/账龄
    5 桶/小计/计提比例/上年值/原值/累计折旧/减值准备/账面价值/购置处置
    核销收回/成本/公允价值/manual_text/formula_result。
    """

    # 模块级常量的对外别名（方便 NoteColumnSemantics.STANDARD_SEMANTICS 取）
    STANDARD_SEMANTICS = STANDARD_SEMANTICS
    VALID_SEMANTICS = VALID_SEMANTICS
    DEFAULT_SEMANTIC = DEFAULT_SEMANTIC

    @classmethod
    def identify(cls, header_text: object) -> str:
        """模糊匹配 header → 返回 semantic_id.

        匹配规则（顺序敏感）：
            1) 全角 / 多空白归一化
            2) 空串 / None → "manual_text"
            3) 以 "=" 开头 → "formula_result"
            4) 按 STANDARD_SEMANTICS 字典顺序遍历，命中关键词即返回 semantic_id
            5) 完全无命中 → "manual_text"

        Returns:
            合法 semantic_id 字符串，必属 ``VALID_SEMANTICS``。
        """
        norm = _normalize(header_text)
        if not norm:
            return DEFAULT_SEMANTIC

        # fast-path：公式起头列（"=" 在 identifier 中本就罕见，前缀更安全）
        if norm.startswith("="):
            return "formula_result"

        for semantic_id, keywords in STANDARD_SEMANTICS.items():
            for kw in keywords:
                kw_norm = _normalize(kw)
                if kw_norm and kw_norm in norm:
                    return semantic_id

        return DEFAULT_SEMANTIC

    @classmethod
    def identify_headers(cls, headers: list[object]) -> list[str]:
        """批量识别一组 headers，返回与输入等长的 semantic_id 列表."""
        if not isinstance(headers, list):
            raise TypeError(
                f"headers must be a list, got {type(headers).__name__}"
            )
        return [cls.identify(h) for h in headers]

    @classmethod
    def iter_synonyms(cls) -> Iterator[tuple[str, list[str]]]:
        """调试 / 文档生成用：迭代 (semantic_id, keywords) 对."""
        for semantic_id, keywords in STANDARD_SEMANTICS.items():
            yield semantic_id, list(keywords)

    @classmethod
    def is_valid(cls, semantic_id: object) -> bool:
        """判定 semantic_id 是否属于合法集合（供 schema 校验复用）."""
        return isinstance(semantic_id, str) and semantic_id in VALID_SEMANTICS


__all__ = [
    "DEFAULT_SEMANTIC",
    "NoteColumnSemantics",
    "STANDARD_SEMANTICS",
    "VALID_SEMANTICS",
]
