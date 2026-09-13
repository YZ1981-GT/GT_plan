"""wp_template_finder 新增判据的纯逻辑守卫（不依赖真实模板库的当前内容）。

为什么单独一个文件：`test_wp_template_finder_d4_prefix.py` 是端到端判据（真实
`_index.json` + 真实磁盘），它只能观测到「当前数据下会发生的事」。本文件用构造数据
锁**判据本身**，覆盖两类当前数据观测不到但语义上必须成立的性质：

* :func:`_pick_by_tier` 的**同级内定序**：真实数据里 D4/F2 都先命中「审定」级，
  永远走不到「常规程序」级，于是端到端测试对「同级多命中时取哪个」恒绿 ——
  变异实测确认（去掉排序 ⇒ 端到端仍 3/3 绿）。而该级一旦被走到（D4 的
  「常规程序」级实有 4 个命中），不排序就会退回「索引/目录枚举顺序决定结果」，
  正是 D4 错配的机制本身。
* :func:`_is_whole_excel_template_name` 的边界：带空格形态、范围式拆分包。
"""

from __future__ import annotations

from pathlib import Path

from app.services import wp_template_finder as finder


# ---------------------------------------------------------------------------
# _pick_by_tier：级间优先 + 级内定序
# ---------------------------------------------------------------------------


def _pairs(*names: str) -> list[tuple[str, Path]]:
    return [(n, Path("/tpl") / n) for n in names]


def test_tier_order_puts_adjudication_above_regular_program() -> None:
    """「审定」必须严格高于「常规程序」，即使后者在列表里更靠前。"""
    picked = finder._pick_by_tier(
        _pairs(
            "D4-12 营业收入-合同检查（Leap-常规程序）.xlsx",
            "D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx",
        )
    )
    assert picked is not None
    assert "审定表" in picked.name


def test_tier_order_is_declared_not_incidental() -> None:
    """阶梯常量本身就是判据：调换顺序即语义反转，故锁死它的取值与次序。"""
    assert finder._PRIMARY_TEMPLATE_TIERS == ("审定", "常规程序")


def test_adjudication_matches_the_f2_detail_table_naming() -> None:
    """F2 的主表叫「审定**明细**表类」——判据必须是「审定」而非连续三字「审定表」。"""
    name = "F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx"
    assert "审定表" not in name
    picked = finder._pick_by_tier(
        _pairs("F2-16 存货及跌价准备-会计政策（Leap-常规程序）.xlsx", name)
    )
    assert picked is not None
    assert picked.name == name


def test_same_tier_is_ordered_by_length_then_name() -> None:
    """同级多命中时按 (名字长度, 名字) 定序 —— 不得取「遍历到的第一个」。

    🔴 这条是 D4「常规程序」级的真实形态（实有 4 个命中）。没有它，结果又回到
    依赖索引顺序；而端到端测试观测不到，因为 D4 先命中了「审定」级。
    """
    long_first = _pairs(
        "D4-21营业收入-关联方检查（Leap-常规程序）.xlsx",
        "D4-5 营业收入-会计政策（Leap-常规程序）.xlsx",
    )
    picked = finder._pick_by_tier(long_first)
    assert picked is not None
    # 更短的那个必须胜出，尽管它在输入里排第二
    assert picked.name == "D4-5 营业收入-会计政策（Leap-常规程序）.xlsx"

    # 同长度时按名字定序，保证跨平台/跨枚举顺序稳定
    same_len = _pairs("B1 甲（Leap-常规程序）.xlsx", "B1 乙（Leap-常规程序）.xlsx")
    assert len({len(n) for n, _ in same_len}) == 1
    picked_same = finder._pick_by_tier(same_len)
    assert picked_same is not None
    assert picked_same.name == min(n for n, _ in same_len)


def test_no_tier_hit_returns_none_so_caller_falls_through() -> None:
    """两级都不命中时返回 None，让调用方继续走「最短文件名」兜底。"""
    assert finder._pick_by_tier(_pairs("D4-33至D4-36 其他业务收入.xlsx")) is None
    assert finder._pick_by_tier([]) is None


# ---------------------------------------------------------------------------
# _is_whole_excel_template_name：整册合并本 vs 范围式拆分包
# ---------------------------------------------------------------------------


def test_whole_excel_accepts_code_plus_chinese_short_name() -> None:
    assert finder._is_whole_excel_template_name("D4收入底稿.xlsx")
    assert finder._is_whole_excel_template_name("F2存货.xlsx")


def test_whole_excel_rejects_range_split_packs() -> None:
    for name in (
        "D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx",
        "F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx",
        "D4-12 营业收入-合同检查（Leap-常规程序）.xlsx",
    ):
        assert not finder._is_whole_excel_template_name(name), name


def test_whole_excel_rejects_the_space_separated_variant() -> None:
    """``D4 收入底稿.xlsx``（编码后是空格）不算整册本。

    D 目录里同时存在带空格与不带空格两份，判据必须确定地只认一份；权威惯例是
    不带空格的 ``D4收入底稿.xlsx``（它才是入库的那份）。
    """
    assert not finder._is_whole_excel_template_name("D4 收入底稿.xlsx")
    assert finder._is_whole_excel_template_name("D4收入底稿.xlsx")


def test_whole_excel_handles_empty_and_extensionless() -> None:
    assert not finder._is_whole_excel_template_name("")
    # 无扩展名也按主干判断，不因缺 '.' 抛错
    assert finder._is_whole_excel_template_name("F2存货")


# ---------------------------------------------------------------------------
# 程序表码回落的两道收窄
# ---------------------------------------------------------------------------


def test_program_table_suffix_only_accepts_A() -> None:
    """只认 ``A`` 后缀：``H1F`` / ``G7L`` / ``G7E`` 是名字提取产物，不是 wp_code。"""
    assert finder._PROGRAM_TABLE_CODE_RE.match("D4A")
    assert finder._PROGRAM_TABLE_CODE_RE.match("K3A")
    assert finder._PROGRAM_TABLE_CODE_RE.match("M10A")
    for artifact in ("H1F", "G7L", "G7E", "B22B", "B22C"):
        assert not finder._PROGRAM_TABLE_CODE_RE.match(artifact), artifact


def test_codes_with_own_render_schema_are_excluded_from_fallback() -> None:
    """有独立 render schema 的码由配置真源指定模板，finder 不得再回落。"""
    assert finder._has_own_render_schema("D2A")
    assert not finder._has_own_render_schema("D4A")
    assert not finder._has_own_render_schema("")
