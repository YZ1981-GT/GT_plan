"""Property-Based Test PBT-2: D 销售循环 sheet 名归一化幂等性

Validates: Requirements F2 (D 销售循环 spec — D2/D4 多文件 sheet 归一化合并去重)
ADR: D2 (sheet 名归一化算法 — 三档判定)
Property: P2 - normalize(normalize(name)) == normalize(name) 对任意输入字符串成立

属性测试覆盖 4 个不变量（与 design.md §四 + ADR D2 对齐）:

  P2.1 幂等：normalize(normalize(s)) == normalize(s)
  P2.2 GT_Custom 收敛：任意含 "GT_Custom" 的字符串 → 归一化为 "GT_Custom"
  P2.3 底稿目录收敛：任意含 "底稿目录" 的字符串 → 归一化为 "底稿目录"
  P2.4 中英圆括号等价：将 "（" → "(" 和 "）" → ")" 替换后归一化结果不变

max_examples=50（spec design.md §四 P0 关键属性规约）
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_template_init_service import _normalize_sheet_name


# ---------------------------------------------------------------------------
# 字符策略：覆盖中文 / 英文 / 圆括号变体 / GT_Custom / 底稿目录 前缀 / 空白
# ---------------------------------------------------------------------------

# 任意 unicode 文本（含 \r\n\t 全角空格 / 中英文括号 / 中文汉字 / ASCII / emoji）
_arbitrary_text = st.text(
    alphabet=st.characters(
        # 不排除控制字符，但排除 surrogate（hypothesis 默认即如此）
        blacklist_categories=("Cs",),
    ),
    min_size=0,
    max_size=80,
)

# 显式覆盖 sheet 名典型字符（中英文圆括号 / 横杠 / GT 前缀 / 底稿前缀）
_sheet_chars = st.text(
    alphabet=st.sampled_from(
        list("应收账款审定表GT_Custom底稿目录明细分析程序D-12345678 \t　（）()_×"),
    ),
    min_size=0,
    max_size=40,
)

# GT_Custom 变体：前后任意拼接
_gt_custom_variant = st.builds(
    lambda prefix, suffix: f"{prefix}GT_Custom{suffix}",
    prefix=st.text(min_size=0, max_size=10),
    suffix=st.text(min_size=0, max_size=10),
)

# 底稿目录变体
_index_variant = st.builds(
    lambda prefix, suffix: f"{prefix}底稿目录{suffix}",
    prefix=st.text(min_size=0, max_size=10),
    suffix=st.text(min_size=0, max_size=10),
)

# 含中文圆括号的样本（用于成对替换等价性测试）
_with_chinese_paren = st.builds(
    lambda left, mid, right: f"{left}（{mid}）{right}",
    left=st.text(min_size=0, max_size=10),
    mid=st.text(min_size=0, max_size=10),
    right=st.text(min_size=0, max_size=10),
)

# 综合策略：任意类别字符串 + sheet 字符 + 三类变体的并集
_any_input = st.one_of(
    _arbitrary_text,
    _sheet_chars,
    _gt_custom_variant,
    _index_variant,
    _with_chinese_paren,
)


# ---------------------------------------------------------------------------
# P2.1 幂等：normalize 是 idempotent 函数
# ---------------------------------------------------------------------------


@given(s=_any_input)
@settings(max_examples=50, deadline=None)
def test_property_p2_1_normalize_idempotent(s: str) -> None:
    """对任意输入字符串 s，`normalize(normalize(s)) == normalize(s)`。

    Validates: Property P2 (sheet 名归一化幂等)
    """
    once = _normalize_sheet_name(s)
    twice = _normalize_sheet_name(once)
    assert once == twice, (
        f"normalize 非幂等：input={s!r}, once={once!r}, twice={twice!r}"
    )


# ---------------------------------------------------------------------------
# P2.2 GT_Custom 收敛：任何包含 "GT_Custom" 的字符串 → "GT_Custom"
# ---------------------------------------------------------------------------


@given(s=_gt_custom_variant)
@settings(max_examples=50, deadline=None)
def test_property_p2_2_gt_custom_collapsed(s: str) -> None:
    """任意包含 `GT_Custom` 的字符串归一化为字面量 "GT_Custom"。

    ADR D2 规则 2：多文件 GT_Custom 内部 sheet 视为同名。

    Validates: Property P2 (sheet 名归一化幂等 — GT_Custom 收敛分支)
    """
    # 前置：构造保证 s 含 "GT_Custom"
    assert "GT_Custom" in s
    assert _normalize_sheet_name(s) == "GT_Custom", (
        f"含 GT_Custom 的输入未归一化为 'GT_Custom'：input={s!r}, "
        f"output={_normalize_sheet_name(s)!r}"
    )


# ---------------------------------------------------------------------------
# P2.3 底稿目录收敛：任何包含 "底稿目录" 的字符串 → "底稿目录"
# ---------------------------------------------------------------------------


@given(s=_index_variant)
@settings(max_examples=50, deadline=None)
def test_property_p2_3_index_sheet_collapsed(s: str) -> None:
    """任意包含 `底稿目录` 的字符串归一化为字面量 "底稿目录"。

    ADR D2 规则 3：多文件底稿目录视为同名。

    Validates: Property P2 (sheet 名归一化幂等 — 底稿目录收敛分支)
    """
    assert "底稿目录" in s
    # 注意：含 "GT_Custom" 优先级高于 "底稿目录"（ADR D2 规则顺序）
    if "GT_Custom" in s:
        assert _normalize_sheet_name(s) == "GT_Custom"
    else:
        assert _normalize_sheet_name(s) == "底稿目录", (
            f"含 底稿目录 的输入未归一化为 '底稿目录'：input={s!r}, "
            f"output={_normalize_sheet_name(s)!r}"
        )


# ---------------------------------------------------------------------------
# P2.4 中英圆括号等价：成对替换中文括号后归一化结果不变
# ---------------------------------------------------------------------------


@given(s=_any_input)
@settings(max_examples=50, deadline=None)
def test_property_p2_4_chinese_english_paren_equivalent(s: str) -> None:
    """对任意输入 s，先把 `（→(`、`）→)` 成对替换再归一化，结果应等于直接归一化。

    ADR D2 规则 1：中英文圆括号视为等价。

    Validates: Property P2 (sheet 名归一化幂等 — 中英圆括号等价分支)
    """
    s_english = s.replace("（", "(").replace("）", ")")
    assert _normalize_sheet_name(s) == _normalize_sheet_name(s_english), (
        f"中英文圆括号成对替换后归一化结果不一致："
        f"original={s!r}→{_normalize_sheet_name(s)!r}, "
        f"english={s_english!r}→{_normalize_sheet_name(s_english)!r}"
    )
