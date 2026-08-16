"""K 循环科目声明单一真源的**结构性**守卫。

与 :mod:`test_k_cycle_row_code_evidence` 的分工（两者判据不同，不是双真源）：

- 本文件：**不连库**，只校验声明表自身的结构自洽（字段齐备 / 分流正确 /
  ``spec_for`` 行为 / 源码不得出现误用码）+ 留痕完备性。可进 CI 而无需 DB。
- 那个文件：**连库**按 ``row_name`` 反查 ``report_config``，是「声明值对不对」的
  唯一判据（Property 1 明确要求禁静态冻结表）。

🔴 **本文件曾把错误的 row_code 冻结成「实证表」**（2026-08-09 前的 ``_EXPECTED_ROWS``
把 K9 soe 记成 ``IS-023``=所得税费用、K6 soe 记成 ``BS-024``=长期股权投资、K4 soe 记成
``BS-081``=实收资本），并有一条 ``两套准则行号必须不同`` 的断言 —— 而实测 K 类正确落点
**绝大多数是两准则同号**。那条断言与真相直接冲突，是「守卫在保护错误值」的典型形态。

本轮按连库实证诚实改写：**删除静态 row_code 冻结表**，行号正确性一律交给连库守卫；
本文件只保留与 DB 无关的结构性判据。

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 1.11, 1.12, 2.x, 3.1；Property 7, 53
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.four_table.k_cycle_specs import (
    CYCLES_EXEMPT_FROM_ACCOUNT_SPEC,
    EMPTY_REASON_NO_ACCOUNT,
    EMPTY_REASON_NOT_IN_PROJECT,
    K6_LIABILITY_ROW_CODE,
    K6_PROVISION_ROW_CODE,
    K_CYCLE_SPECS,
    MISUSED_ACCOUNT_CODES,
    NONEXISTENT_ACCOUNT_CODES,
    SEVERITY_ACTIVE_WRONG,
    SEVERITY_VALUES,
    SEVERITY_SILENT_EMPTY,
    SEVERITY_TRACE_ONLY,
    balance_cycle_codes,
    credit_side_cycle_codes,
    get_k_cycle_spec,
    liability_spec_for,
    no_account_cycle_codes,
    pl_cycle_codes,
    severity_of,
)
from app.services.four_table.pl_occurrence import AccountNature

_STRATEGY_DIR = Path("backend/app/routers/wp_render_strategies")

#: 声明表应覆盖的循环（K0 是函证循环、无科目余额 ⇒ 显式豁免）
_EXPECTED_CYCLES: tuple[str, ...] = (
    "K1",
    "K2",
    "K3",
    "K4",
    "K5",
    "K6",
    "K7",
    "K8",
    "K9",
    "K10",
    "K11",
    "K12",
    "K13",
)


# ─────────────────────────────────────────────────────────────────────────────
# Property 7：覆盖面
# ─────────────────────────────────────────────────────────────────────────────


def test_all_k_cycles_declared():
    """K1~K13 十三个循环全部登记，无遗漏无多余（K0 走豁免）。"""
    assert set(K_CYCLE_SPECS) == set(_EXPECTED_CYCLES)
    assert len(K_CYCLE_SPECS) == 13


def test_k0_is_explicitly_exempt():
    """K0 显式豁免且写明理由（不得静默缺席）。"""
    assert "K0" in CYCLES_EXEMPT_FROM_ACCOUNT_SPEC
    reason = CYCLES_EXEMPT_FROM_ACCOUNT_SPEC["K0"]
    assert len(reason) >= 20, f"豁免理由过短：{reason!r}"
    assert "函证" in reason
    assert "K0" not in K_CYCLE_SPECS


def test_k1_k2_are_in_single_source():
    """Requirement 3.1：K1/K2 已收进真源（此前各写私有 spec）。"""
    for wp in ("K1", "K2"):
        assert wp in K_CYCLE_SPECS, f"{wp} 未纳入 K_CYCLE_SPECS"


def test_k1_keeps_its_semantics():
    """Property 9：K1 的既有语义（备抵行 + 附加科目）不得丢。"""
    spec = K_CYCLE_SPECS["K1"]
    # 🔴 K1 的备抵 `1231-03` 由 `BS-009` 的 soe_standalone 公式**直接解析出**
    #    （`TB('1221') - TB('1231-03') + TB('1131')`）⇒ 不需要独立备抵报表行；
    #    真正不可丢的是名称过滤（反解退化为宽前缀 1231 时防串应收账款坏账）。
    assert spec.provision_row_code is None, (
        "K1 不应声明 provision_row_code —— 备抵码在 BS-009 公式内，"
        f"声明独立备抵行会让解析多跑一趟且语义重复（实际 {spec.provision_row_code!r}）"
    )
    assert spec.provision_name_filter, "K1 备抵名称过滤丢失（宽前缀 1231 会串科目）"
    assert "1131" in spec.extra_standard_codes, "K1 应收股利 1131 丢失"
    assert "1132" in spec.extra_standard_codes, "K1 应收利息 1132 丢失"


def test_k2_keeps_its_semantics():
    """Property 9：K2 保留兜底码 1901。"""
    spec = K_CYCLE_SPECS["K2"]
    assert spec.fallback_standard == "1901"


# ─────────────────────────────────────────────────────────────────────────────
# Property 53：改正留痕完备性
# ─────────────────────────────────────────────────────────────────────────────

_VALID_SEVERITIES = {SEVERITY_ACTIVE_WRONG, SEVERITY_SILENT_EMPTY, SEVERITY_TRACE_ONLY}


#: row_code 形态（`BS-081` / `IS-023` / `IMP-007` / `CFSS-016`）
_ROW_CODE_RE = re.compile(r"\b(?:BS|IS|IMP|CFS|CFSS|EQ)-\d{3}\b")

#: 「引出一个名称」的分隔符/引号（不含窗口，见 `_states_what_the_old_code_points_to`）
_NAME_SEPARATOR_RE = re.compile(r"(?:=|实为|实指|实际指向|是|（|\(|「|『)")

#: CJK 统一汉字（注意：全角标点 `：`U+FF1A / `、`U+3001 / `（`U+FF08 **不在**此区间）
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

#: 一段留痕里「构成一个科目名」所需的最少汉字数。
#:
#: 取 4 的依据：要挡住的是 `BS-081（已改正）` 这类「提了码但没说它是什么」
#: （`已改正` 3 字）；而真实科目名 + 分隔词普遍 ≥4（`实为股本` / `预计负债` /
#: `流动资产合计`）。代价：若有人写成 `BS-058（股本）`（纯 2 字名 + 括注）会被
#: 误判为缺失 —— 已在反向自检里显式登记该边界，届时应改写留痕而非放宽阈值。
_MIN_NAME_CJK = 4


def _states_what_the_old_code_points_to(evidence: str) -> bool:
    """留痕是否写明了「该原值码实际指向哪个科目/报表行」。

    判据取**形态**，且**完全不用字符窗口**：把留痕按 row_code 切段，
    对每个 row_code 之后（下一个 row_code 之前）的片段，要求同时满足

    1. 出现分隔符或引号（`=` / `实为` / `（` / `「` …），且
    2. 该分隔符**之后**存在汉字，且
    3. 该片段汉字总数 ≥ :data:`_MIN_NAME_CJK`。

    这样下列真实写法全部放行：

    - `BS-081 实为**实收资本（或股本）**`（分隔词 + markdown 强调）
    - `IS-023 = **减：所得税费用**`（`=` + 名称第 2 字就是全角冒号）
    - `BS-015（**流动资产合计**，ROW() 派生行）`（括注）
    - `IS-022（**三、利润总额**，ROW(...)+... 派生行）`（名称含全角顿号）
    - `IS-043（listed 侧「4. 其他债权投资…」/ soe 侧「减： 营业外支出」）`
      （名称在引号内、前面还有 `listed 侧` 与序号 `4. ` 噪声）

    而「只提了个码、没说它是什么」仍被打红。

    🔴 两条设计要点都是踩过的坑（勿改回去）：

    - **不用固定字符窗口**。旧判据写 `row_code + [^\\n]{0,12}? + 分隔符`，
      实测 K12 的 `IS-041（listed 侧「（一）基本每股收益…` 在 12 字窗口内
      **恰好**命中 `（一` 而通过，而完全同构的 K13
      `IS-043（listed 侧「4. 其他债权投资…` 因名称前多了 `4. ` 三个字符
      落到窗口外被打红 ⇒ 判据把「写法差异」误判成「留痕缺失」，
      于是看起来像是声明表少写了东西（实际是判据不完备）。
    - **不要求连续 N 个汉字**。真实报表行名普遍在第 2 个字符处就出现全角标点
      （`减：所得税费用` / `三、利润总额` / `（一）基本每股收益`），
      写 `[\\u4e00-\\u9fff]{2,}` 会把这三条真实留痕全部误判成缺失。
    """
    ev = str(evidence or "")
    codes = list(_ROW_CODE_RE.finditer(ev))
    if not codes:
        return False  # 连 row_code 都没提，不可能写明它指向什么
    for idx, m in enumerate(codes):
        end = codes[idx + 1].start() if idx + 1 < len(codes) else len(ev)
        segment = ev[m.end():end]
        sep = _NAME_SEPARATOR_RE.search(segment)
        if not sep:
            continue
        if not _CJK_RE.search(segment[sep.end():]):
            continue  # 分隔符之后没有汉字（如 ` / soe=` 后接的是拉丁字母）
        if len(_CJK_RE.findall(segment)) < _MIN_NAME_CJK:
            continue  # 汉字太少，构不成一个科目名（如 `（已改正）`）
        return True
    return False


def test_evidence_judge_accepts_real_forms_and_rejects_bare_code():
    """反向自检：判据对真实留痕形态放行、对「只提码不说名」打红。

    ⚠️ 无条件执行（不参数化）—— 参数化集合为空会让整条 SKIP、判据静默空转。
    """
    # 平台里真实出现过的写法都应放行
    assert _states_what_the_old_code_points_to(
        "原值 listed=BS-058 / soe=BS-081；BS-081 实为**实收资本（或股本）**"
    )
    assert _states_what_the_old_code_points_to(
        "soe 原值 IS-023 = **减：所得税费用** TB('6801','本期发生额')"
    )
    assert _states_what_the_old_code_points_to(
        "原值 listed=BS-015（**流动资产合计**，ROW() 派生行）"
    )
    # 🔴 名称第 2 个字符就是全角标点的形态（`减：` / `三、`）。
    #    这一条钉死「要求连续 N 个汉字」缺陷 —— 真实报表行名普遍如此。
    punct_form = (
        "soe 原值 IS-022（**三、利润总额**，ROW('IS-019')+ROW('IS-020')"
        "−ROW('IS-021') 派生行）⇒ TRACE_ONLY"
    )
    assert _states_what_the_old_code_points_to(punct_form)
    # 🔴 「码 + 括注 + 引号 + 序号噪声 + 中文名」形态（K12/K13 真实写法）。
    #    这一条钉死「固定字符窗口」缺陷：名称前若有 `4. ` 之类序号，
    #    12 字窗口的旧判据会把它误判成「未写明」。
    k13_form = (
        "soe 原值 IS-043（listed 侧「4. 其他债权投资信用减值准备」"
        "/ soe 侧「减： 营业外支出」，两侧 formula 均 NULL）⇒ TRACE_ONLY"
    )
    assert _states_what_the_old_code_points_to(k13_form)
    assert _states_what_the_old_code_points_to(
        "soe 原值 IS-041（listed 侧「（一）基本每股收益（元/股）」"
        "/ soe 侧「加： 营业外收入」，两侧 formula 均 NULL）⇒ TRACE_ONLY"
    )

    # ── 反向证明两个旧判据形态确实会误杀上面的真实写法 ──────────────────
    # 这两条不是装饰：它们把「为什么改判据」钉死在测试里，防下个会话
    # 看到判据比"直觉写法"复杂就改回去（改回去会让 K8/K12/K13 三条假红）。
    _legacy_window_re = re.compile(
        r"\b(?:BS|IS|IMP|CFS|CFSS|EQ)-\d{3}\b"
        r"[^\n]{0,12}?"
        r"(?:=|实为|实指|实际指向|是|（|\()"
        r"\s*\**"
        r"[\u4e00-\u9fff]"
    )
    assert not _legacy_window_re.search(k13_form), (
        "旧的 12 字窗口判据本应对 K13 形态落空（这是本轮改判据的理由之一）；"
        "若此断言失败说明窗口写法已被改动，请重新核对判据设计"
    )
    _legacy_consecutive_cjk_re = re.compile(
        r"(?:=|实为|实指|实际指向|是|（|\(|「|『)"
        r"\s*\**\s*"
        r"[\u4e00-\u9fff]{2,}"
    )
    assert not _legacy_consecutive_cjk_re.search(punct_form), (
        "「分隔符后须连续 ≥2 汉字」的旧判据本应对 `三、利润总额` 落空"
        "（名称第 2 字是全角顿号）；这是本轮改判据的理由之二"
    )

    # ── 应打红的形态 ────────────────────────────────────────────────
    # 只提码、不说它指向什么 → 必须打红
    assert not _states_what_the_old_code_points_to(
        "原值 listed=BS-015 / soe=BS-024，两者都错，已改正"
    )
    # 码后只有英文/公式、无中文名 → 必须打红
    assert not _states_what_the_old_code_points_to(
        "原值 soe=IS-023 = TB('6801','amount')"
    )
    # 中文名出现在码**之前**（无从判断该码指向什么）→ 必须打红
    assert not _states_what_the_old_code_points_to("其他应收款的原值是 BS-009")
    # 分隔符后汉字太少、构不成科目名 → 必须打红
    assert not _states_what_the_old_code_points_to("原值 soe=IS-023（已改）")
    # 连码都没提 → 必须打红
    assert not _states_what_the_old_code_points_to("原值写错了，已按 DB 改正")
    # 空留痕 → 打红
    assert not _states_what_the_old_code_points_to("")


def test_every_corrected_cycle_carries_three_part_evidence():
    """Requirement 1.12：每条改正必须留「原值 / 原值实指科目 / 后果分级」三段。"""
    problems: list[str] = []
    for wp, spec in K_CYCLE_SPECS.items():
        ev = spec.row_code_evidence or ""
        if not ev:
            continue  # 未改正的循环无需留痕
        # 🔴 「新纳入真源」不是「改正 row_code」—— K1/K2 此前 render 各写私有 spec、
        #    声明表里压根没有它们的旧值，故无「原值」可留、也**没有错位后果可分级**。
        #    要求它们留三段会逼人编造一个不存在的「原值」与不存在的「后果」。
        #    判据改为：必须写明「为何无原值」，且**不得**标后果分级（分级只属改正类）。
        if "新纳入" in ev:
            if not any(k in ev for k in ("无原值", "非改正")):
                problems.append(
                    f"{wp}: 新纳入类留痕须写明「无原值可留痕 / 非改正」，"
                    f"否则与改正类不可区分：{ev!r}"
                )
            leaked = [s for s in _VALID_SEVERITIES if s in ev]
            if leaked:
                problems.append(
                    f"{wp}: 新纳入类不得标后果分级（本轮无 row_code 错位，"
                    f"标了会让 severity_of 报出不存在的缺陷）：命中 {leaked}"
                )
            continue
        if "原值" not in ev:
            problems.append(f"{wp}: 留痕缺「原值」段")
        # 「该原值实际指向什么」有多种等价写法 —— 判据取**形态**而非固定词表。
        # 固定词表会逼人把留痕写成模板套话；而 `IS-023 = **减：所得税费用**`
        # 已经把「码 → 名」的映射表达得比任何一个词都清楚。
        if not _states_what_the_old_code_points_to(ev):
            problems.append(
                f"{wp}: 留痕未写明「该原值实际指向哪个科目/报表行」 —— "
                f"须出现「row_code + 分隔符/括注 + 科目名」形态"
                f"（如 `BS-081 实为**实收资本**` 或 `IS-023 = **减：所得税费用**`）："
                f"{ev!r}"
            )
        if not any(s in ev for s in _VALID_SEVERITIES):
            problems.append(
                f"{wp}: 留痕缺后果分级（须含 {sorted(_VALID_SEVERITIES)} 之一）：{ev!r}"
            )
    assert not problems, "\n".join(problems)


def test_severity_values_are_the_three_grades():
    """后果分级取值域恰为三档（防新增未定义等级）。"""
    assert _VALID_SEVERITIES == set(SEVERITY_VALUES)
    assert _VALID_SEVERITIES == {"ACTIVE_WRONG", "SILENT_EMPTY", "TRACE_ONLY"}, (
        "后果分级取值域应恰为三档英文常量（声明表里 row_code_evidence 直接内插常量，"
        "写中文会与 severity_of() 的抽取逻辑不一致）"
    )


@pytest.mark.parametrize(
    ("wp", "grade"),
    [
        ("K6", SEVERITY_ACTIVE_WRONG),
        ("K9", SEVERITY_ACTIVE_WRONG),
        ("K4", SEVERITY_SILENT_EMPTY),
        ("K3", SEVERITY_TRACE_ONLY),
        ("K8", SEVERITY_TRACE_ONLY),
    ],
)
def test_severity_of_returns_expected_grade(wp: str, grade: str):
    """分级函数与实证结论一致（K6/K9 活错数、K4 恒空、其余仅溯源）。"""
    assert severity_of(wp) == grade


def test_severity_of_unknown_returns_none():
    assert severity_of("K99") is None
    assert severity_of("") is None


def test_docstring_no_longer_carries_the_debunked_table():
    """Property 53：声明表 docstring 不得再出现被推翻的旧「实证表」形态。

    旧表特征 = ``BS-094`` 与「预计负债」同现于表格行、``2245`` 与「三表零命中」同现。
    """
    src = Path("backend/app/services/four_table/k_cycle_specs.py").read_text("utf-8")
    head = src[: src.find("from __future__")] if "from __future__" in src else src[:8000]
    # 旧表把 BS-094 当 K5 的 soe 落点列在表格里
    bad_rows = [
        ln
        for ln in head.splitlines()
        if "BS-094" in ln and "预计负债" in ln and "|" not in ln and ln.strip().startswith("K5")
    ]
    assert not bad_rows, f"docstring 仍含旧实证表行：{bad_rows}"
    # 旧表称 2245 三表零命中 —— 实测 client 侧存在
    for ln in head.splitlines():
        if "2245" in ln and "零命中" in ln:
            pytest.fail(f"docstring 仍称 2245 零命中（实测 client 侧存在）：{ln.strip()!r}")


def test_docstring_states_db_is_the_judge():
    """docstring 必须写明「判据在 DB、禁信静态表」。"""
    src = Path("backend/app/services/four_table/k_cycle_specs.py").read_text("utf-8")
    head = src[:8000]
    assert "判据在 DB" in head, "docstring 未写明「判据在 DB」"
    assert "实证表" in head, "docstring 未写明禁止再写实证表"
    assert "report_config" in head


# ─────────────────────────────────────────────────────────────────────────────
# Property 5 / 6：方向声明
# ─────────────────────────────────────────────────────────────────────────────


def test_credit_side_cycles_are_k3_k4_k5_k7():
    """负债类循环（原值贷方）恰为 K3/K4/K5/K7。"""
    assert sorted(credit_side_cycle_codes(), key=lambda c: int(c[1:])) == [
        "K3",
        "K4",
        "K5",
        "K7",
    ]


@pytest.mark.parametrize("wp", ["K3", "K4", "K5", "K7"])
def test_credit_side_cycles_declare_direction(wp: str):
    """负债类必须声明方向，否则原值被判成备抵、gross 变空。"""
    spec = K_CYCLE_SPECS[wp]
    assert spec.is_liability or spec.gross_direction == "credit", (
        f"{wp}（{spec.account_name}）未声明负债方向"
    )


def test_credit_direction_propagates_to_report_line_spec():
    """方向声明必须透传到 `ReportLineAccountSpec`（否则声明了也没用）。"""
    for wp in ("K3", "K4", "K5", "K7"):
        rls = K_CYCLE_SPECS[wp].spec_for(["soe_standalone"])
        assert rls.is_liability or rls.gross_direction == "credit", (
            f"{wp} 的方向声明未透传到 ReportLineAccountSpec"
        )


def test_asset_side_cycles_do_not_declare_credit():
    """反向：资产类（K1/K2/K6 资产侧）不得声明 credit（会关掉备抵拆分）。"""
    for wp in ("K1", "K2", "K6"):
        spec = K_CYCLE_SPECS[wp]
        assert not spec.is_liability, f"{wp} 是资产类，不应 is_liability=True"
        assert spec.gross_direction != "credit", f"{wp} 是资产类，不应 gross_direction=credit"


def test_k6_liability_spec_declares_credit_but_asset_does_not():
    """Property 5：K6 一个循环两个方向 —— 资产侧 debit、负债侧 credit。"""
    spec = K_CYCLE_SPECS["K6"]
    asset = spec.spec_for(["soe_standalone"])
    assert not asset.is_liability and asset.gross_direction != "credit"
    liab = liability_spec_for(["soe_standalone"])
    assert liab.is_liability or liab.gross_direction == "credit"


# ─────────────────────────────────────────────────────────────────────────────
# Property 4：宁缺勿造（逐循环实证结论，非设计偏好）
# ─────────────────────────────────────────────────────────────────────────────


def test_only_k4_is_no_account():
    """🔴 实测只有 K4 的宁缺勿造成立 —— K6 的三个科目在 client 侧确实存在。

    旧守卫断言 ``== ["K4", "K6"]``，那是把错误记载冻结成了判据。
    """
    assert no_account_cycle_codes() == ["K4"]


def test_k4_declares_empty_fallback():
    """宁缺勿造的循环不得有兜底码（有兜底码就会去取不存在的科目）。"""
    spec = K_CYCLE_SPECS["K4"]
    assert spec.has_account is False
    assert spec.fallback_standard == ""
    assert spec.spec_for(["soe_standalone"]).fallback_gross == ()


def test_k6_has_account_and_carries_fallbacks():
    """K6 改为 `has_account=True` 并带上三个真实存在的科目码。"""
    spec = K_CYCLE_SPECS["K6"]
    assert spec.has_account is True
    assert spec.fallback_standard == "1481", "K6 资产侧兜底应为 1481 持有待售资产"
    assert spec.provision_row_code == K6_PROVISION_ROW_CODE
    assert K6_LIABILITY_ROW_CODE == "BS-051"


def test_two_empty_reasons_are_distinct_layers():
    """🔴「标准科目表没这科目」与「本项目没用它」是两层，文案不得混用。"""
    assert EMPTY_REASON_NO_ACCOUNT != EMPTY_REASON_NOT_IN_PROJECT
    assert "手工录入" in EMPTY_REASON_NO_ACCOUNT
    assert "宁缺勿造" in EMPTY_REASON_NO_ACCOUNT
    assert "本项目" in EMPTY_REASON_NOT_IN_PROJECT


def test_nonexistent_codes_registry_excludes_k6_codes():
    """🔴 1481/1482/2245 已从「不存在的码」移出（实测 client 侧存在）。"""
    for code in ("1481", "1482", "2245"):
        assert code not in NONEXISTENT_ACCOUNT_CODES, (
            f"{code} 在 account_chart client 侧确实存在，不得当作不存在的码"
        )


def test_nonexistent_codes_registry_keeps_真_nonexistent():
    """真正零命中的码仍在登记表内（2301/2605/2331/2911）。"""
    for code in ("2301", "2605", "2331", "2911"):
        assert code in NONEXISTENT_ACCOUNT_CODES


def test_misused_code_registry_documents_why():
    """反向自检：误用码登记表说明 2701 的真实科目名。"""
    assert MISUSED_ACCOUNT_CODES["2701"] == "长期应付款"


@pytest.mark.parametrize("wp", sorted(_EXPECTED_CYCLES, key=lambda c: int(c[1:])))
def test_no_spec_uses_misused_or_nonexistent_codes(wp: str):
    """任何循环的兜底码都不得是误用码或不存在的码。"""
    fb = K_CYCLE_SPECS[wp].fallback_standard
    if not fb:
        return
    assert fb not in MISUSED_ACCOUNT_CODES
    assert fb not in NONEXISTENT_ACCOUNT_CODES


def test_k5_fallback_is_provisions_not_long_term_payables():
    """🔴 K5 兜底码必须是 2801 预计负债，绝不是 2701 长期应付款。"""
    spec = K_CYCLE_SPECS["K5"]
    assert spec.fallback_standard == "2801"
    assert spec.account_name == "预计负债"


# ─────────────────────────────────────────────────────────────────────────────
# 损益 / 余额分流
# ─────────────────────────────────────────────────────────────────────────────


def test_pl_cycles_are_k8_to_k13():
    assert sorted(pl_cycle_codes(), key=lambda c: int(c[1:])) == [
        "K8",
        "K9",
        "K10",
        "K11",
        "K12",
        "K13",
    ]


def test_balance_cycles_are_k1_to_k7():
    """余额类含新纳入的 K1/K2（旧守卫写 K3~K7，是 K1/K2 未纳入真源时的状态）。"""
    assert sorted(balance_cycle_codes(), key=lambda c: int(c[1:])) == [
        "K1",
        "K2",
        "K3",
        "K4",
        "K5",
        "K6",
        "K7",
    ]


@pytest.mark.parametrize(
    ("wp_code", "nature"),
    [
        ("K8", AccountNature.EXPENSE),
        ("K9", AccountNature.EXPENSE),
        ("K10", AccountNature.INCOME),
        ("K11", AccountNature.EXPENSE),
        ("K12", AccountNature.INCOME),
        ("K13", AccountNature.EXPENSE),
    ],
)
def test_pl_nature_matches_account_direction(wp_code, nature):
    """费用/减值/营业外支出走借方；其他收益/营业外收入走贷方。"""
    assert K_CYCLE_SPECS[wp_code].nature is nature


@pytest.mark.parametrize("wp_code", ["K1", "K2", "K3", "K4", "K5", "K6", "K7"])
def test_balance_cycles_have_no_nature(wp_code):
    """资产负债类不经损益模块，nature 必须为 None。"""
    assert K_CYCLE_SPECS[wp_code].nature is None
    assert K_CYCLE_SPECS[wp_code].is_pl is False


# ─────────────────────────────────────────────────────────────────────────────
# spec_for（按准则选行号）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "standards",
    [
        ["listed_standalone", "listed", "standalone"],
        ["soe_standalone", "soe", "standalone"],
        ["listed_consolidated"],
        ["soe_consolidated"],
        [],
        None,
    ],
)
def test_spec_for_k5_is_bs065_under_every_standard(standards):
    """🔴 K5 在四变体下都是 `BS-065`（两准则同号）。

    旧守卫期望 soe 分支返 `BS-094`（该行 formula 为 NULL ⇒ 必退兜底、溯源谎报），
    并另有一条「两侧必须不同」的断言 —— 两者都是把缺陷冻结成判据。
    """
    assert K_CYCLE_SPECS["K5"].spec_for(standards).row_code == "BS-065"


def test_spec_for_carries_fallback():
    spec = K_CYCLE_SPECS["K5"].spec_for(["soe_standalone"])
    assert spec.fallback_gross == ("2801",)
    assert spec.fallback_provision == ()


def test_spec_for_k3_carries_extra_interest_payable():
    """Requirement 1.3：K3 的 `BS-050` 在 standalone 下含 2231 应付利息。"""
    spec = K_CYCLE_SPECS["K3"].spec_for(["soe_standalone"])
    assert spec.row_code == "BS-050"
    assert "2231" in spec.extra_standard_codes


def test_spec_for_k1_carries_provision_row_and_extras():
    spec = K_CYCLE_SPECS["K1"].spec_for(["soe_standalone"])
    assert spec.row_code == "BS-009"
    assert spec.provision_name_filter, "K1 名称过滤未透传到 ReportLineAccountSpec"
    assert "1131" in spec.extra_standard_codes
    assert "1132" in spec.extra_standard_codes


def test_get_k_cycle_spec_is_case_insensitive():
    assert get_k_cycle_spec("k5") is K_CYCLE_SPECS["K5"]
    assert get_k_cycle_spec(" K13 ") is K_CYCLE_SPECS["K13"]
    assert get_k_cycle_spec("K99") is None
    assert get_k_cycle_spec("") is None


def test_no_row_code_is_a_derived_row():
    """Property 3 声明侧：不得指向已知的 `ROW()` 派生行。"""
    derived = {"BS-015", "BS-069", "IS-022", "BS-039", "BS-070"}
    for wp, spec in K_CYCLE_SPECS.items():
        for attr in ("row_code_listed", "row_code_soe"):
            rc = getattr(spec, attr)
            if not rc:
                continue
            if rc in derived:
                assert not spec.trust_report_config, (
                    f"{wp}.{attr} = {rc} 是派生行，必须 trust_report_config=False 或改指非派生行"
                )


# ─────────────────────────────────────────────────────────────────────────────
# 源码守卫
# ─────────────────────────────────────────────────────────────────────────────


def _strip_comments(src: str) -> str:
    """去掉 Python 注释与三引号 docstring（踩坑说明里会写反例字样）。"""
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = re.sub(r"'''(?:.|\n)*?'''", "", src)
    return re.sub(r"#[^\n]*", "", src)


_STRATEGY_FILES: dict[str, str] = {
    "K1": "_k1_other_receivables.py",
    "K2": "_k2_other_current_assets.py",
    "K3": "_k3_other_payables.py",
    "K4": "_k4_other_current_liabilities.py",
    "K5": "_k5_provisions.py",
    "K6": "_k6_held_for_sale.py",
    "K7": "_k7_deferred_income.py",
    "K8": "_k8_selling_expenses.py",
    "K9": "_k9_admin_expenses.py",
    "K10": "_k10_other_income.py",
    "K11": "_k11_asset_impairment_loss.py",
    "K12": "_k12_non_operating_income.py",
    "K13": "_k13_non_operating_expense.py",
}


def test_strategy_files_exist():
    """反向自检：文件名映射有效，否则下面的源码断言全是空转。"""
    for wp_code, fn in _STRATEGY_FILES.items():
        assert (_STRATEGY_DIR / fn).exists(), f"{wp_code} 策略文件不存在: {fn}"


def test_strip_comments_actually_strips():
    """反向自检：`_strip_comments` 确实生效（否则源码断言恒不触发）。"""
    sample = '"""docstring 里提到 debit - credit 反例"""\nx = 1  # 注释里也提 2701\n'
    stripped = _strip_comments(sample)
    assert "debit - credit" not in stripped
    assert "2701" not in stripped
    assert "x = 1" in stripped


@pytest.mark.parametrize("wp_code", sorted(_STRATEGY_FILES, key=lambda c: int(c[1:])))
def test_no_pl_net_difference_in_strategy_source(wp_code):
    """取数源码不得出现 `debit - credit` 形态（含年末结转损益的账上恒零）。"""
    src = _strip_comments((_STRATEGY_DIR / _STRATEGY_FILES[wp_code]).read_text("utf-8"))
    patterns = [
        r"debit\s*-\s*credit",
        r"debit_amount\s*-\s*credit_amount",
        r'\["debit"\]\s*-\s*\w+\["credit"\]',
        r"credit\s*-\s*debit",
        r"credit_amount\s*-\s*debit_amount",
        r'\["credit"\]\s*-\s*\w+\["debit"\]',
    ]
    for pat in patterns:
        assert not re.search(pat, src), f"{wp_code} 源码含损益净额表达式: {pat}"


def test_k4_source_has_no_nonexistent_codes():
    """Property 4 源码侧：K4（唯一宁缺勿造循环）不得出现不存在的科目码。"""
    src = _strip_comments((_STRATEGY_DIR / _STRATEGY_FILES["K4"]).read_text("utf-8"))
    for code in NONEXISTENT_ACCOUNT_CODES:
        assert f'"{code}"' not in src, f"K4 源码含不存在的科目码 {code}"
        assert f"'{code}'" not in src, f"K4 源码含不存在的科目码 {code}"


def test_k5_source_has_no_long_term_payable_code():
    """Property 3 源码侧：K5 源码不得出现 2701（长期应付款）。"""
    src = _strip_comments((_STRATEGY_DIR / _STRATEGY_FILES["K5"]).read_text("utf-8"))
    assert '"2701"' not in src
    assert "'2701'" not in src


def test_semantic_bridge_is_withdrawn_and_stays_withdrawn():
    """Task 10 撤回：`to_semantic_spec`/`semantic_spec_of` 已删除且不得重新引入。

    撤回理由见 `k_cycle_specs` 的 `SEMANTIC_BRIDGE_WITHDRAWAL_REASON`。
    """
    from app.services.four_table import k_cycle_specs as mod

    assert not hasattr(mod, "to_semantic_spec"), (
        "语义桥接已按 Task 10 撤回；若要重新引入必须先按 Requirement 5.4 给出"
        "「K 循环科目码在项目间是否一致」的对账实证"
    )
    assert not hasattr(mod, "semantic_spec_of")
    reason = getattr(mod, "SEMANTIC_BRIDGE_WITHDRAWAL_REASON", "")
    assert len(reason) >= 40, f"撤回理由过短或缺失：{reason!r}"
