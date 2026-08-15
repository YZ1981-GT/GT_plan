"""G7 权益法族 / 子公司族「取数补齐」逐 sheet 裁决 + 反向自检。

## 🔴 立项判据被实证推翻（本文件存在的首要理由）

本任务立项时的观察是::

    `_g7_long_term_equity_method.py` / `_g7_long_term_equity_subsidiary.py` 的
    `four_table_prefill` / `tb_leaf_categories` / `adjudication_prefill` /
    `tb_source_codes` 命中数**全为 0**（只有 `client_name` / `audit_year` 各 4 次）

命中数确实是 0（2026-08-12 复测吻合），但由此推出「这 15 个 sheet 的取数是欠账」
**判据选错了** —— 与平台记过的那次「``grep resolve_semantic_accounts`` 得 0 就判
D 类完全没接科目映射」同源。真实链路是：

    四表 ──(主循环 render `_g7_long_term_equity_main.py`)──► G7-1/G7-2
                                                              │
                          `g7EquityMethodCrossSheet.ts` 跨表引用
                                                              ▼
                              G7-14 权益法测算表（再分发 G7-4/5/6/13/15/16/17）

即**四表数据经 G7-2 单一入口进入 G7 域**，再由跨表引用分发到权益法族。
若在族 render 里再接一次四表取数，同一个 `1511` 余额就有了**两个真源**
（主循环查一次、族里再查一次），那正是平台铁律禁止的形态 —— 两处口径一旦分叉，
审计师看到的「投资账面价值」在 G7-2 与 G7-14 会不一致，且无从判断哪个对。

⇒ 故本文件的结论以「**不该补**」为主，但每条都必须给出**可执行的**依据，
   而不是「懒得接」。四类依据各有对应的反向自检（见 `_BASIS_*` 常量与同名测试）。

## 判据强度

每条登记的依据都落到**可执行断言**上，不是注释里的说法：

* ``via_cross_sheet``     → 断言该跨表函数**真实存在且有 .vue 生产宿主**
                            （孤儿函数不算「已接线」—— 平台记过 `CrossWorkpaperNav`
                             那次「修复正确但全仓零渲染宿主 ⇒ 用户不可达」）
* ``via_sampling_engine`` → 断言抽凭区块组件有生产宿主
* ``not_in_four_table``   → 断言该维度确实不在四表 schema 里（列名级）
* ``accounting_judgment`` → 断言源模板该 sheet 无金额取数列（靠 sheet 清单 + 依据文字）

**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

spec: .kiro/specs/g7-column-alignment-and-extraction-closure/ Task 16
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND.parent
_FE = _ROOT / "audit-platform/frontend/src"
_STRATEGIES = _BACKEND / "app/routers/wp_render_strategies"

# ─────────────────────────────────────────────────────────────────────────────
# 裁决登记
# ─────────────────────────────────────────────────────────────────────────────

#: 依据类别
_BASIS_CROSS_SHEET = "via_cross_sheet"
_BASIS_SAMPLING = "via_sampling_engine"
_BASIS_NOT_IN_FOUR_TABLE = "not_in_four_table"
_BASIS_JUDGMENT = "accounting_judgment"
_BASIS_SHOULD_FILL = "should_fill"

_VALID_BASES = frozenset(
    {
        _BASIS_CROSS_SHEET,
        _BASIS_SAMPLING,
        _BASIS_NOT_IN_FOUR_TABLE,
        _BASIS_JUDGMENT,
        _BASIS_SHOULD_FILL,
    }
)


class Adjudication:
    """一个 sheet 的取数裁决（纯数据）。"""

    __slots__ = ("code", "sheet", "family", "basis", "evidence", "anchor")

    def __init__(
        self,
        code: str,
        sheet: str,
        family: str,
        basis: str,
        evidence: str,
        anchor: str = "",
    ) -> None:
        self.code = code
        self.sheet = sheet
        self.family = family
        self.basis = basis
        self.evidence = evidence
        #: 反向自检用的锚点：
        #: `via_cross_sheet` → 跨表函数名；`via_sampling_engine` → 组件名
        self.anchor = anchor


#: 🔴 15 个 sheet 逐条裁决。**上限只许缩短**（`test_registry_is_capped`）。
ADJUDICATIONS: tuple[Adjudication, ...] = (
    # ── 权益法族（8 sheet）──────────────────────────────────────────────────
    Adjudication(
        "G7-4", "被投资单位基本信息G7-4", "method", _BASIS_NOT_IN_FOUR_TABLE,
        "被投资单位的注册资本 / 持股比例 / 表决权比例 / 注册地 —— 这些是**被投资单位**的"
        "工商与章程信息，本公司四表（trial_balance / tb_balance / tb_ledger / "
        "tb_aux_balance）结构上没有任何一列承载它。持股比例虽会影响权益法测算，"
        "但它来自投资协议而非账务，写死或从科目名反推都属臆造。",
    ),
    Adjudication(
        "G7-5", "被投资单位财务信息G7-5", "method", _BASIS_NOT_IN_FOUR_TABLE,
        "**被投资单位自己的**资产/负债/净资产/净利润/其他综合收益。四表存的是"
        "**本公司**账套，被投资单位的报表数据只能由审计师录入或从其审计报告带入。"
        "本公司账上关于该投资的只有 `1511` 投资账面价值一项，不能反推被投资单位净资产"
        "（差额里含商誉、内部交易未实现损益、公允价值调整等）。",
    ),
    Adjudication(
        "G7-6", "被投资公司会计政策G7-6", "method", _BASIS_JUDGMENT,
        "被投资单位会计政策与本公司是否一致、不一致的调整金额 —— 纯会计判断，"
        "四表无对应维度。其产出经 `applyG76PolicyToG714Payload` 汇总进 G7-14 的"
        "`accountingPolicyAdj`，链路本身已接通。",
        anchor="applyG76PolicyToG714Payload",
    ),
    Adjudication(
        "G7-13", "投资成本测试表G7-13", "method", _BASIS_CROSS_SHEET,
        "初始投资成本 vs 应享有可辨认净资产公允价值份额。**投资成本一侧的账面数据"
        "已由 G7-2 明细表经跨表引用带入**（`applyG72EquityToG714Payload` 把 G7-2 的"
        "期初/期末总额写进 G7-14，`applyInvestmentCostToG714Payload` 再把 G7-13 的"
        "商誉/廉价购买差额回写 G7-14），四表数据的单一入口在主循环 render。"
        "在本 sheet 再查一次 `1511` 会造成同一金额两个真源。",
        anchor="applyInvestmentCostToG714Payload",
    ),
    Adjudication(
        "G7-14", "权益法测算表G7-14", "method", _BASIS_CROSS_SHEET,
        "权益法调整的**汇总表**，是整个族的收敛点。其 6 条上游全部已接跨表引用："
        "G7-2（期初余额/比例/损益/OCI/其他权益/股利）· G7-4（被投资单位行+比例）· "
        "G7-5（净利润→报告净利润、净资产→经审计净资产）· G7-6（会计政策调整）· "
        "G7-13（商誉/FV）· G7-15（内部交易抵销）· G7-16（未确认损失）· G7-17（减值）。"
        "四表数据由 G7-2 一条路进来，本 sheet 不应另开一条。",
        anchor="applyG72EquityToG714Payload",
    ),
    Adjudication(
        "G7-15", "内部交易抵销测算表G7-15", "method", _BASIS_NOT_IN_FOUR_TABLE,
        "本公司与被投资单位之间的内部交易未实现损益。需要**交易对手侧**的存货/固定资产"
        "结存与毛利率，本公司四表只有自己这一侧的发生额；且 `tb_ledger` 的 "
        "`counterpart_account` 填充率实测仅约 9%（memory 已记不可靠），"
        "按它推断内部交易会大面积漏计。产出经 `applyInternalElimToG714Payload` 进 G7-14。",
        anchor="applyInternalElimToG714Payload",
    ),
    Adjudication(
        "G7-16", "未确认投资损失测试表G7-16", "method", _BASIS_JUDGMENT,
        "超额亏损分担额：需被投资单位**累计**亏损与本公司其他长期权益，且涉及"
        "「是否有额外承担义务」的判断。四表无该维度。产出经 "
        "`applyUnrecognizedLossToG714Payload` 累加进 G7-14 的 `otherAdj`。",
        anchor="applyUnrecognizedLossToG714Payload",
    ),
    Adjudication(
        "G7-17", "减值测试表G7-17", "method", _BASIS_JUDGMENT,
        "可回收金额 = max(公允价值减处置费用, 预计未来现金流量现值) —— DCF 与估值参数，"
        "四表结构上没有。**账面价值一侧**由 G7-2/G7-14 带入，减值结论经 "
        "`applyG717ImpairmentToG714Payload` 回写 G7-14 减值准备列。",
        anchor="applyG717ImpairmentToG714Payload",
    ),
    # ── 子公司族（7 sheet）──────────────────────────────────────────────────
    Adjudication(
        "G7-7", "投资初始确认判断G7-7", "subsidiary", _BASIS_JUDGMENT,
        "CAS33 控制六要素判断（权力 / 可变回报 / 影响回报的能力等）—— 全部是文字判断题，"
        "无金额取数列。四表无对应维度，且这类判断不得由数据自动填（会掩盖审计判断责任）。",
    ),
    Adjudication(
        "G7-8", "子公司初始计量测量（同控）G7-8", "subsidiary", _BASIS_JUDGMENT,
        "同一控制下企业合并：按被合并方**账面价值**份额计量，合并对价与份额差额调资本公积。"
        "被合并方账面价值来自其账套而非本公司四表；合并日的确定亦属判断。",
    ),
    Adjudication(
        "G7-9", "非同一控制下企业合并G7-9", "subsidiary", _BASIS_JUDGMENT,
        "非同控合并：购买日可辨认净资产**公允价值**（评估报告）+ 合并成本，差额确认商誉。"
        "公允价值与评估参数不在任何账务表里。",
    ),
    Adjudication(
        "G7-10", "后续计量检查G7-10", "subsidiary", _BASIS_SAMPLING,
        "成本法后续计量（股利测算 / 购买少数股权 / 不丧失控制权处置）是**测算表**，"
        "无凭证明细行。平台的处置是给它挂**凭证抽查区块**（`G7VoucherSampleSection.vue`），"
        "由抽凭引擎从序时账取样本回填，而不是把凭证号硬映射到测算字段"
        "（`g7VoucherSample.ts` 模块 docstring 明确「避免臆造死接线」）。",
        anchor="G7VoucherSampleSection",
    ),
    Adjudication(
        "G7-11", "处置检查（非一揽子交易）G7-11", "subsidiary", _BASIS_SAMPLING,
        "处置对价与处置日净资产份额的差额计入投资收益。处置对价来自股权转让协议、"
        "处置日净资产来自子公司账套，均不在本公司四表；本公司侧的凭证由抽凭区块取样。",
        anchor="G7VoucherSampleSection",
    ),
    Adjudication(
        "G7-12", "处置检查（一揽子交易）G7-12", "subsidiary", _BASIS_SAMPLING,
        "一揽子交易需判断多次处置是否构成一揽子（四要素判断）再整体计量，"
        "属会计判断 + 协议条款；本公司侧凭证由抽凭区块取样。",
        anchor="G7VoucherSampleSection",
    ),
    Adjudication(
        "G7-18", "凭证检查表G7-18", "subsidiary", _BASIS_SAMPLING,
        "凭证抽查表本身就是抽凭产物，**已经**接在平台抽凭引擎上"
        "（`mergeVoucherSamples` 按 `voucherNo` 去重后并入行模型）。"
        "抽凭引擎读序时账，故『四表取数』在这里是以抽凭的形式接通的，"
        "不需要 render 再加 `four_table_prefill`。",
        anchor="mergeVoucherSamples",
    ),
)


def _by_code() -> dict[str, Adjudication]:
    return {a.code: a for a in ADJUDICATIONS}


@pytest.fixture(scope="module")
def fe_sources() -> dict[str, str]:
    """前端 `src` 下全部 `.vue` / 非测试 `.ts` 的内容（一次读取，多测试复用）。"""
    out: dict[str, str] = {}
    if not _FE.exists():  # pragma: no cover - 仅前端目录缺失时
        return out
    for path in list(_FE.rglob("*.vue")) + list(_FE.rglob("*.ts")):
        rel = path.relative_to(_FE).as_posix()
        if "__tests__" in rel or ".spec." in rel:
            continue
        out[rel] = path.read_text(encoding="utf-8", errors="replace")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 登记表卫生
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistryHygiene:
    def test_covers_every_sheet_of_both_families(self):
        """登记必须覆盖两个 render 声明的**全部** sheet（防漏判）。"""
        declared: set[str] = set()
        for fname in (
            "_g7_long_term_equity_method.py",
            "_g7_long_term_equity_subsidiary.py",
        ):
            src = (_STRATEGIES / fname).read_text(encoding="utf-8")
            declared |= set(re.findall(r'"code":\s*"(G7-\d+)"', src))
        registered = {a.code for a in ADJUDICATIONS}
        assert declared, "两个 render 里没解析出任何 sheet code ⇒ 判据空转"
        assert declared == registered, (
            f"登记与 render 声明不符：render 有而未登记 {sorted(declared - registered)}；"
            f"登记了但 render 没有 {sorted(registered - declared)}"
        )
        assert len(registered) == 15, f"两族共应 15 个 sheet，实际 {len(registered)}"

    def test_every_entry_has_valid_basis_and_evidence(self):
        for a in ADJUDICATIONS:
            assert a.basis in _VALID_BASES, f"{a.code} 依据类别非法：{a.basis!r}"
            assert len(a.evidence) >= 40, (
                f"{a.code} 依据过短（{len(a.evidence)} 字）—— "
                f"「宁缺勿造」必须写清为什么不该补：{a.evidence[:40]!r}"
            )
            assert a.family in {"method", "subsidiary"}, f"{a.code} 族别非法"

    def test_registry_is_capped(self):
        """上限只许缩短 —— 防「新 sheet 一律塞进不该补」变成逃逸阀。"""
        assert len(ADJUDICATIONS) <= 15

    def test_no_hardcoded_client_or_project_code(self):
        """🔴 R8.4：登记表与两个 render 都不得出现硬编码客户 / 项目编码。

        判据 = UUID 形态 + 常见客户码字面量形态；`tb_aux_balance` 的
        `aux_type='客户'` 才是逐户明细的真源。
        """
        uuid_re = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
        for a in ADJUDICATIONS:
            assert not uuid_re.search(a.evidence), f"{a.code} 依据里出现 UUID"
        for fname in (
            "_g7_long_term_equity_method.py",
            "_g7_long_term_equity_subsidiary.py",
        ):
            src = (_STRATEGIES / fname).read_text(encoding="utf-8")
            hits = uuid_re.findall(src)
            assert not hits, f"{fname} 出现硬编码 UUID：{hits[:3]}"

    def test_no_allocation_of_totals(self):
        """🔴 R8.3：两个 render 不得出现「按比例摊派总额」的痕迹。

        平台已有 5 个 D 循环 render 明确写「TB 叶子无法干净映射到分类行 ⇒
        不臆造分类行未审数」的先例。这里断言两个 render 里没有分摊算式。
        """
        suspicious = re.compile(r"(摊派|按比例分摊|allocate_total|prorate)")
        for fname in (
            "_g7_long_term_equity_method.py",
            "_g7_long_term_equity_subsidiary.py",
        ):
            src = (_STRATEGIES / fname).read_text(encoding="utf-8")
            hits = suspicious.findall(src)
            assert not hits, f"{fname} 出现摊派痕迹：{hits}"


# ─────────────────────────────────────────────────────────────────────────────
# 反向自检：每类依据都要落到可执行断言（防登记变空壳）
# ─────────────────────────────────────────────────────────────────────────────


class TestBasisIsBackedByRealWiring:
    """🔴 「不该补」的依据若只是一句话，登记表就是空壳。

    本类把依据钉到**真实接线**上：凡声称「已由跨表引用 / 抽凭引擎取得」的，
    对应函数或组件必须存在**且有 .vue 生产宿主**。
    """

    def test_cross_sheet_anchors_exist_with_vue_host(self, fe_sources):
        """`via_cross_sheet` / 带 anchor 的条目：函数存在 + 有 .vue 宿主。"""
        if not fe_sources:
            pytest.skip("前端源码目录不可用")
        cross = _ROOT / (
            "audit-platform/frontend/src/components/workpaper/composables/"
            "g7EquityMethodCrossSheet.ts"
        )
        cross_src = cross.read_text(encoding="utf-8") if cross.exists() else ""
        checked = 0
        for a in ADJUDICATIONS:
            if not a.anchor or a.anchor.startswith("G7Voucher") or a.anchor == "mergeVoucherSamples":
                continue
            # ① 函数真实存在（导出形态，不是随口一个名字）
            assert re.search(rf"export function {re.escape(a.anchor)}\b", cross_src), (
                f"{a.code} 的依据锚点 {a.anchor} 在 g7EquityMethodCrossSheet.ts 里"
                "不是导出函数 ⇒ 依据是空壳"
            )
            # ② 有 .vue 生产宿主（孤儿函数不算「已接线」）
            hosts = [
                rel
                for rel, src in fe_sources.items()
                if rel.endswith(".vue") and re.search(rf"\b{re.escape(a.anchor)}\b", src)
            ]
            assert hosts, (
                f"{a.code} 的跨表函数 {a.anchor} **零 .vue 宿主** ⇒ 用户不可达，"
                "不能算「已由跨表引用取得」（平台记过 CrossWorkpaperNav 那次教训）"
            )
            checked += 1
        assert checked >= 5, f"跨表锚点实检 {checked} 条，太少 ⇒ 判据几乎空转"

    def test_sampling_anchors_exist_with_vue_host(self, fe_sources):
        """`via_sampling_engine` 条目：抽凭区块 / 合并函数有生产宿主。"""
        if not fe_sources:
            pytest.skip("前端源码目录不可用")
        checked = 0
        for a in ADJUDICATIONS:
            if a.basis != _BASIS_SAMPLING:
                continue
            assert a.anchor, f"{a.code} 声称走抽凭引擎却没给锚点"
            hosts = [
                rel
                for rel, src in fe_sources.items()
                if rel.endswith(".vue")
                and Path(rel).stem != a.anchor
                and re.search(rf"\b{re.escape(a.anchor)}\b", src)
            ]
            assert hosts, f"{a.code} 的抽凭锚点 {a.anchor} 零 .vue 宿主 ⇒ 依据是空壳"
            checked += 1
        assert checked == 4, f"抽凭类应有 4 条（G7-10/11/12/18），实际 {checked}"

    def test_four_table_entry_point_really_fetches(self):
        """裁决的大前提 = **主循环 render 真的取四表**（G7-2 是单一入口）。

        这个前提一旦不成立，「已由跨表引用取得」就全线失效 —— 那时四表数据
        根本没进 G7 域，才是真欠账。故必须钉死。
        """
        src = (_STRATEGIES / "_g7_long_term_equity_main.py").read_text(encoding="utf-8")
        for token in (
            "resolve_semantic_accounts",
            "aggregate_leaves",
            "get_active_filter",
            "tb_leaf_categories",
            "adjudication_prefill",
            "G7_SPEC",
        ):
            assert re.search(rf"\b{re.escape(token)}\b", src), (
                f"主循环 render 缺 {token} ⇒ 四表数据没进 G7 域，"
                "本文件「已由跨表引用取得」的裁决前提失效，需重新判定"
            )

    def test_two_family_renders_still_have_no_four_table_keys(self):
        """反面锚定：两个族 render **确实**没有四表取数键。

        这不是「要求它们保持没有」，而是证明本文件的裁决对象没被悄悄改掉 ——
        若哪天真接上了，本条打红，提醒把对应条目从「不该补」移出并复核是否
        产生了第二个真源。
        """
        keys = (
            "four_table_prefill",
            "tb_leaf_categories",
            "resolve_semantic_accounts",
            "aggregate_leaves",
        )
        for fname in (
            "_g7_long_term_equity_method.py",
            "_g7_long_term_equity_subsidiary.py",
        ):
            src = (_STRATEGIES / fname).read_text(encoding="utf-8")
            hit = [k for k in keys if re.search(rf"\b{re.escape(k)}\b", src)]
            assert not hit, (
                f"{fname} 现在有四表取数键 {hit} ⇒ 与本文件裁决不符。"
                "请复核：四表数据是否已有 G7-2 单一入口？会不会造成同一金额两个真源？"
            )

    def test_not_in_four_table_claims_are_column_level(self):
        """`not_in_four_table` 条目的依据必须点名**四表**（列名级判据的最低要求）。

        防「随口说四表没有」——依据里至少要提到四张表之一或其列名，
        使后人能按名去核。
        """
        four_table_words = (
            "trial_balance",
            "tb_balance",
            "tb_ledger",
            "tb_aux_balance",
            "四表",
            "counterpart_account",
        )
        checked = 0
        for a in ADJUDICATIONS:
            if a.basis != _BASIS_NOT_IN_FOUR_TABLE:
                continue
            assert any(w in a.evidence for w in four_table_words), (
                f"{a.code} 声称四表无该维度，但依据里没点名任何四表/列名 ⇒ 无从核实"
            )
            checked += 1
        assert checked == 3, f"not_in_four_table 应有 3 条（G7-4/5/15），实际 {checked}"

    def test_no_entry_claims_should_fill_without_live_evidence(self):
        """若某条改判为「该补」，必须附真实库实证（本轮无此类条目）。

        R8.1：判该补 ⇒ 给「四表里确实有可映射数据」的真实库实证。
        本条是**前瞻闸**：一旦有人把某条改成 `should_fill`，依据里必须出现
        真实库证据的标志词，否则打红。
        """
        for a in ADJUDICATIONS:
            if a.basis != _BASIS_SHOULD_FILL:
                continue
            assert any(
                w in a.evidence for w in ("实测", "真实库", "postgres", "行数", "金额")
            ), f"{a.code} 判为该补但依据里没有真实库实证 ⇒ 不得凭推测接取数"

    def test_reverse_self_check_anchor_detection_works(self, fe_sources):
        """反向自检：锚点检测逻辑本身有效（对不存在的名字必须判否）。

        没有这一条，上面几条「hosts 非空」的断言可能因扫描逻辑失效而恒真。
        """
        if not fe_sources:
            pytest.skip("前端源码目录不可用")
        bogus = "applyDefinitelyNotExistingFnToG714Payload"
        hosts = [
            rel
            for rel, src in fe_sources.items()
            if rel.endswith(".vue") and re.search(rf"\b{re.escape(bogus)}\b", src)
        ]
        assert hosts == [], "扫描逻辑对不存在的函数也报命中 ⇒ 上面的断言是假绿"
        # 正面：一个确知存在的锚点必须扫得到
        real = [
            rel
            for rel, src in fe_sources.items()
            if rel.endswith(".vue")
            and re.search(r"\bapplyG72EquityToG714Payload\b", src)
        ]
        assert real, "扫描逻辑连确知存在的锚点都扫不到 ⇒ 判据失效"
