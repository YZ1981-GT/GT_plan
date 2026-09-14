"""G 循环语义科目定位规格守卫。

钉死 2026-08-01 实证的映射真源错误与循环间科目串味：

- `report_config` 4 处错码（`BS-022`/`BS-025`/`BS-026` 连续偏移、`IS-016`↔`IS-017` 互换）
- G4 main 用 `1504` 而 ecl/sppi 写 `1501`；G6 main 用 `1505` 而 service 写 `1503`
- 损益类循环取数口径必须是本期发生额

spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
      Requirements 1, 2 / Property 4, 5
"""
from __future__ import annotations

import pytest

from app.services.four_table.g_cycle_specs import (
    G_CYCLE_SPECS,
    G_PL_CYCLES,
    spec_of,
)
from app.services.four_table.semantic_account_resolver import (
    ChartRow,
    match_slot_in_chart,
    normalize_account_name,
    resolve_semantic_accounts,
)

# ─── 实证科目表（`account_chart`，2026-08-01 只读）──────────────────────────
# 标准科目表：投资族只在 6 个项目里，`1519` 只在 4 个
STANDARD_ROWS = [
    ChartRow("1101", "交易性金融资产", "standard", "debit"),
    ChartRow("1131", "应收股利", "standard", "debit"),
    ChartRow("1132", "应收利息", "standard", "debit"),
    ChartRow("1501", "持有至到期投资", "standard", "debit"),
    ChartRow("1502", "持有至到期投资减值准备", "standard", "debit"),
    ChartRow("1503", "可供出售金融资产", "standard", "debit"),
    ChartRow("1504", "债权投资", "standard", "debit"),
    ChartRow("1505", "债权投资减值准备", "standard", "debit"),
    ChartRow("1506", "其他债权投资", "standard", "debit"),
    ChartRow("1507", "其他权益工具投资", "standard", "debit"),
    ChartRow("1511", "长期股权投资", "standard", "debit"),
    ChartRow("1512", "长期股权投资减值准备", "standard", "debit"),
    ChartRow("1519", "其他非流动金融资产", "standard", "debit"),
    ChartRow("1521", "投资性房地产", "standard", "debit"),
    ChartRow("1531", "长期应收款", "standard", "debit"),
    ChartRow("2101", "交易性金融负债", "standard", "credit"),
    ChartRow("2102", "短期应付债券", "standard", "credit"),
    ChartRow("6101", "公允价值变动损益", "standard", "credit"),
    ChartRow("6103", "净敞口套期收益", "standard", "credit"),
    ChartRow("6111", "投资收益", "standard", "credit"),
    ChartRow("6115", "资产处置损益", "standard", "credit"),
    ChartRow("6701", "资产减值损失", "standard", "debit"),
    ChartRow("6702", "信用减值损失", "standard", "debit"),
]

#: 各循环期望命中的标准码（`account_chart` + `trial_balance.account_name` 双向实证）
EXPECTED_GROSS = {
    "G1": "1101",
    "G2": "1132",
    "G3": "1131",
    "G4": "1504",
    "G5": "1531",
    "G6": "1506",   # 🔴 report_config 的 BS-022 写 1505（= 债权投资减值准备）
    "G7": "1511",
    "G8": "1507",   # 🔴 BS-025 写 1506（= 其他债权投资）
    "G9": "1519",   # 🔴 BS-026 写 1507（= 其他权益工具投资）
    "G10": "2101",
    "G11": "6111",
    "G12": "6103",
    "G13": "6101",
    "G14": "6702",  # 🔴 IS-016 写 6701（= 资产减值损失），与 IS-017 互换
}

#: 属于**其它**循环 / 旧准则的码 —— 该循环的**任何**槽都不得命中。
#: 注意：本循环自己的备抵码不算外来（如 G4 的 `1505 债权投资减值准备` 归 G4.provision）。
FOREIGN_CODES = {
    "G4": {"1501", "1503", "1506", "1507"},  # 旧准则 + G6/G8 的科目
    "G6": {"1503", "1504", "1505", "1507"},  # 旧准则 + G4 原值与备抵 + G8
    "G8": {"1506", "1519"},                  # 其他债权投资(G6) / 其他非流动金融资产(G9)
    "G9": {"1506", "1507"},                  # G6 / G8 的科目
    "G12": {"6115", "6111", "6101"},         # 资产处置损益(H10) / 投资收益(G11) / G13
    "G14": {"6701"},                         # 资产减值损失（K11 的科目）
}

#: 实证**任何项目科目表都不存在**的码 —— 不得作为兜底码
#: （给了兜底只会在「科目表不可用」降级路径里产出查不到数据的假前缀）
ABSENT_CODES = {"1102"}


class TestRegistry:
    def test_all_fourteen_cycles_registered(self):
        assert sorted(G_CYCLE_SPECS) == sorted(
            ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9",
             "G10", "G11", "G12", "G13", "G14"]
        )

    def test_spec_of_is_case_insensitive(self):
        assert spec_of("g6") is G_CYCLE_SPECS["G6"]
        assert spec_of(" G14 ") is G_CYCLE_SPECS["G14"]
        assert spec_of("G99") is None
        assert spec_of("") is None

    def test_every_slot_has_names_and_stable_key(self):
        for cyc, spec in G_CYCLE_SPECS.items():
            keys = [s.key for s in spec.slots]
            assert keys, f"{cyc} 未声明任何槽"
            assert len(keys) == len(set(keys)), f"{cyc} 槽 key 重复"
            for slot in spec.slots:
                assert slot.names, f"{cyc}.{slot.key} 未声明科目名"
                assert slot.display_label, f"{cyc}.{slot.key} 无展示名"

    def test_pl_cycles_are_the_four_income_statement_ones(self):
        assert G_PL_CYCLES == {"G11", "G12", "G13", "G14"}

    def test_pl_cycles_reference_income_statement_rows(self):
        for cyc in G_PL_CYCLES:
            assert G_CYCLE_SPECS[cyc].row_code.startswith("IS-")

    def test_g2_g3_declare_no_report_row(self):
        """🔴 `BS-015` 是「流动资产合计」（ROW 派生行）、listed 侧 `BS-016` 是
        「一年内到期的非流动资产」→ 不得认领，否则溯源面板展示错公式。"""
        assert G_CYCLE_SPECS["G2"].row_code is None
        assert G_CYCLE_SPECS["G3"].row_code is None


class TestNameMatchingAgainstRealChart:
    @pytest.mark.parametrize("cyc", sorted(EXPECTED_GROSS))
    def test_gross_slot_hits_expected_standard_code(self, cyc):
        spec = G_CYCLE_SPECS[cyc]
        gross = spec.slots[0]
        rows, exact = match_slot_in_chart(gross, STANDARD_ROWS)
        assert exact is True, f"{cyc} 原值槽未精确命中（走了包含匹配）"
        assert [r.account_code for r in rows] == [EXPECTED_GROSS[cyc]]

    @pytest.mark.parametrize("cyc", sorted(FOREIGN_CODES))
    def test_no_slot_hits_foreign_codes(self, cyc):
        """任何槽都不得命中属于其它循环 / 旧准则的科目码。"""
        spec = G_CYCLE_SPECS[cyc]
        forbidden = FOREIGN_CODES[cyc]
        for slot in spec.slots:
            rows, _ = match_slot_in_chart(slot, STANDARD_ROWS)
            hit = forbidden & {r.account_code for r in rows}
            assert not hit, f"{cyc}.{slot.key} 命中外来科目 {sorted(hit)}"

    def test_g4_gross_excludes_other_debt_investment(self):
        """`其他债权投资` **包含** `债权投资` → G4 原值槽必须排除它。"""
        rows, _ = match_slot_in_chart(G_CYCLE_SPECS["G4"].slots[0], STANDARD_ROWS)
        assert [r.account_code for r in rows] == ["1504"]

    def test_g4_provision_hits_its_own_provision_only(self):
        rows, exact = match_slot_in_chart(G_CYCLE_SPECS["G4"].slots[1], STANDARD_ROWS)
        assert exact is True
        assert [r.account_code for r in rows] == ["1505"]

    def test_g7_provision_hits_1512(self):
        rows, exact = match_slot_in_chart(G_CYCLE_SPECS["G7"].slots[1], STANDARD_ROWS)
        assert exact is True
        assert [r.account_code for r in rows] == ["1512"]

    def test_g14_excludes_asset_impairment_loss(self):
        """🔴 `资产减值损失`(6701) 与 `信用减值损失`(6702) 只差两字，必须靠否决词分开。"""
        rows, _ = match_slot_in_chart(G_CYCLE_SPECS["G14"].slots[0], STANDARD_ROWS)
        assert [r.account_code for r in rows] == ["6702"]

    def test_g13_accepts_both_account_and_report_line_naming(self):
        """科目名是「公允价值变动损益」、报表行名是「…收益」→ 两个名都要认。"""
        gross = G_CYCLE_SPECS["G13"].slots[0]
        assert "公允价值变动损益" in gross.names
        assert "公允价值变动收益" in gross.names
        rows, exact = match_slot_in_chart(gross, STANDARD_ROWS)
        assert exact is True and [r.account_code for r in rows] == ["6101"]

    def test_slots_within_a_cycle_are_disjoint(self):
        for cyc, spec in G_CYCLE_SPECS.items():
            seen: dict[str, str] = {}
            for slot in spec.slots:
                rows, _ = match_slot_in_chart(slot, STANDARD_ROWS)
                for r in rows:
                    assert r.account_code not in seen, (
                        f"{cyc}: {r.account_code} 同时被 {seen[r.account_code]}"
                        f" 与 {slot.key} 命中"
                    )
                    seen[r.account_code] = slot.key

    def test_no_two_cycles_claim_the_same_account(self):
        """🔴 跨循环互斥 —— 这条正是抓住「G6/G8/G9 错位链」的断言。"""
        owner: dict[str, str] = {}
        for cyc, spec in G_CYCLE_SPECS.items():
            for slot in spec.slots:
                rows, _ = match_slot_in_chart(slot, STANDARD_ROWS)
                for r in rows:
                    prev = owner.get(r.account_code)
                    assert prev is None, (
                        f"{r.account_code}({r.account_name}) 被 {prev} 与 {cyc} 同时认领"
                    )
                    owner[r.account_code] = cyc

    def test_absent_accounts_resolve_to_nothing(self):
        """实证不存在的科目（衍生金融资产 / 衍生金融负债）必须返空，不得静默取 0。"""
        for cyc, key in (("G1", "derivative"), ("G10", "derivative")):
            slot = next(s for s in G_CYCLE_SPECS[cyc].slots if s.key == key)
            rows, _ = match_slot_in_chart(slot, STANDARD_ROWS)
            assert rows == [], f"{cyc}.{key} 不该命中任何科目"

    def test_legacy_standard_accounts_not_absorbed(self):
        """旧准则 `1501`/`1503` 不得被任何槽自动吸收（需 SPPI 人工判断）。"""
        for cyc, spec in G_CYCLE_SPECS.items():
            for slot in spec.slots:
                rows, _ = match_slot_in_chart(slot, STANDARD_ROWS)
                codes = {r.account_code for r in rows}
                assert "1501" not in codes, f"{cyc}.{slot.key} 吸收了持有至到期投资"
                assert "1503" not in codes, f"{cyc}.{slot.key} 吸收了可供出售金融资产"


class TestFallbackCodes:
    @pytest.mark.parametrize("cyc", sorted(EXPECTED_GROSS))
    def test_gross_fallback_matches_evidence(self, cyc):
        """兜底码必须与实证真值一致（G6/G8/G9/G14 曾抄了 report_config 的错值）。"""
        gross = G_CYCLE_SPECS[cyc].slots[0]
        if cyc == "G1":
            assert gross.fallback_standard_codes == ("1101",)
            return
        assert EXPECTED_GROSS[cyc] in gross.fallback_standard_codes, (
            f"{cyc} 兜底码 {gross.fallback_standard_codes} 不含实证真值"
            f" {EXPECTED_GROSS[cyc]}"
        )

    def test_no_fallback_uses_a_foreign_code(self):
        for cyc, spec in G_CYCLE_SPECS.items():
            forbidden = FOREIGN_CODES.get(cyc, set())
            for slot in spec.slots:
                bad = forbidden & set(slot.fallback_standard_codes)
                assert not bad, f"{cyc}.{slot.key} 兜底码含外来科目 {sorted(bad)}"

    def test_no_fallback_uses_an_absent_code(self):
        """🔴 实证不存在的科目（`1102`）不得作兜底码 —— 否则「科目表不可用」降级路径
        会拿一个查不到任何数据的假前缀去取数，把「本项目无衍生金融工具」掩盖成 0。"""
        for cyc, spec in G_CYCLE_SPECS.items():
            for slot in spec.slots:
                bad = ABSENT_CODES & set(slot.fallback_standard_codes)
                assert not bad, f"{cyc}.{slot.key} 兜底码含实证不存在的科目 {sorted(bad)}"

    def test_derivative_slots_have_no_fallback(self):
        """G1 衍生金融资产 / G10 衍生金融负债 实证均无对应科目 → 一律不给兜底码。"""
        for cyc in ("G1", "G10"):
            slot = next(s for s in G_CYCLE_SPECS[cyc].slots if s.key == "derivative")
            assert slot.fallback_standard_codes == (), f"{cyc}.derivative 不应有兜底码"


class TestProvisionFlags:
    def test_only_provision_slots_flagged(self):
        expected = {("G4", "provision"), ("G7", "provision")}
        got = {
            (cyc, s.key)
            for cyc, spec in G_CYCLE_SPECS.items()
            for s in spec.slots
            if s.is_provision
        }
        assert got == expected

    def test_provision_slots_exclude_pl_impairment_accounts(self):
        """备抵槽不得命中损益侧的「减值损失」科目。"""
        for cyc, key in (("G4", "provision"), ("G7", "provision")):
            slot = next(s for s in G_CYCLE_SPECS[cyc].slots if s.key == key)
            rows, _ = match_slot_in_chart(slot, STANDARD_ROWS)
            codes = {r.account_code for r in rows}
            assert "6701" not in codes and "6702" not in codes


# ─────────────────────── 端到端（替身 session）───────────────────────


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """按 SQL 分派；`report_config` 返回**实证的错误公式**以验证冲突检测。"""

    def __init__(self, chart, formula=None, mapping_reverse=None):
        self.chart = chart
        self.formula = formula
        self.mapping_reverse = mapping_reverse or []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "account_chart" in sql:
            from types import SimpleNamespace

            return _FakeResult(
                [
                    SimpleNamespace(
                        account_code=r.account_code,
                        account_name=r.account_name,
                        direction=r.direction,
                        source=r.source,
                    )
                    for r in self.chart
                ]
            )
        if "DISTINCT original_account_code" in sql:
            return _FakeResult(self.mapping_reverse)
        if "report_config" in sql and self.formula:
            from types import SimpleNamespace

            return _FakeResult([SimpleNamespace(formula=self.formula)])
        return _FakeResult([])


class _Ctx:
    def __init__(self, db):
        self.db = db
        self.project_id = "00000000-0000-0000-0000-0000000000g6".replace("g", "0")
        self.year = 2025


@pytest.mark.asyncio
class TestEndToEndConflictDetection:
    @pytest.mark.parametrize(
        ("cyc", "wrong_formula", "wrong_code", "right_code"),
        [
            ("G6", "TB('1505','期末余额')", "1505", "1506"),
            ("G8", "TB('1506','期末余额')", "1506", "1507"),
            ("G9", "TB('1507','期末余额')", "1507", "1519"),
            ("G14", "TB('6701','本期发生额')", "6701", "6702"),
        ],
    )
    async def test_wrong_report_config_is_overridden_and_flagged(
        self, cyc, wrong_formula, wrong_code, right_code
    ):
        """🔴 核心：`report_config` 给错码时，以科目名定位结果为准并暴露冲突。"""
        db = _FakeSession(STANDARD_ROWS, formula=wrong_formula)
        got = await resolve_semantic_accounts(_Ctx(db), G_CYCLE_SPECS[cyc])
        assert got.standard_codes_of("gross") == [right_code], (
            f"{cyc} 应按科目名取 {right_code}，实得 {got.standard_codes_of('gross')}"
        )
        assert got.report_config_codes == [wrong_code]
        assert ("gross", wrong_code, right_code) in got.conflicts

    async def test_correct_report_config_yields_no_conflict(self):
        db = _FakeSession(STANDARD_ROWS, formula="TB('1504','期末余额')")
        got = await resolve_semantic_accounts(_Ctx(db), G_CYCLE_SPECS["G4"])
        assert got.standard_codes_of("gross") == ["1504"]
        # 备抵槽的 1505 不在公式里 → 会被记为冲突，属预期（公式只引用原值）
        assert ("gross", "1504", "1504") not in got.conflicts

    async def test_project_without_investment_accounts_returns_empty(self):
        chart = [ChartRow("1001", "库存现金", "client", "debit")]
        db = _FakeSession(chart)
        for cyc in ("G4", "G6", "G8", "G9"):
            got = await resolve_semantic_accounts(_Ctx(db), G_CYCLE_SPECS[cyc])
            assert got.slots["gross"].found is False, f"{cyc} 应返空"

    async def test_legacy_project_surfaces_unmapped_candidates(self):
        """客户只有旧准则科目 → 提示人工按 SPPI 映射，不自动归槽。"""
        chart = [
            ChartRow("1501", "持有至到期投资", "client", "debit"),
            ChartRow("1503", "可供出售金融资产", "client", "debit"),
        ]
        db = _FakeSession(chart)
        got = await resolve_semantic_accounts(_Ctx(db), G_CYCLE_SPECS["G6"])
        assert got.slots["gross"].found is False
        names = {n for _c, n in got.unmapped_candidates}
        assert "可供出售金融资产" in names
        assert "持有至到期投资" in names

    async def test_client_chart_preferred_over_standard(self):
        """客户科目表命中时优先用它（客户真实在用的科目）。"""
        chart = STANDARD_ROWS + [
            ChartRow("1511", "长期股权投资", "client", "debit"),
        ]
        db = _FakeSession(chart)
        got = await resolve_semantic_accounts(_Ctx(db), G_CYCLE_SPECS["G7"])
        assert got.slots["gross"].resolved_from == "account_chart_client"
        assert got.codes_of("gross") == ["1511"]


class TestNormalizationSanity:
    def test_expected_codes_and_names_are_consistent(self):
        """自检：fixture 里每个期望码的科目名确实与该循环槽名匹配（防 fixture 腐化）。"""
        by_code = {r.account_code: r.account_name for r in STANDARD_ROWS}
        for cyc, code in EXPECTED_GROSS.items():
            assert code in by_code, f"fixture 缺 {code}"
            names = {normalize_account_name(n) for n in G_CYCLE_SPECS[cyc].slots[0].names}
            assert normalize_account_name(by_code[code]) in names, (
                f"{cyc}: 科目 {code}({by_code[code]}) 不在槽声明的名称集合里"
            )
