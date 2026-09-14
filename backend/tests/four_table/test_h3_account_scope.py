"""H3 投资性房地产语义科目定位守卫。

钉死 2026-08-01 修掉的三个缺陷（详见 `four_table/h3_account_scope` docstring）：

1. 取错整个科目族（原写 ``1503``=可供出售金融资产 / ``1504``=债权投资）
2. 缺累计摊销与减值准备两个槽
3. 叶子判定缺点号边界（``15210`` 被当成 ``1521`` 的子科目）

并锁死「不写死标准码」——`account_mapping` 实证 ``1525`` 在不同项目映射到
``1521``（并入母科目）与 ``1525``（独立）两种粒度。

spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
      Requirements 2.1~2.3, 2.5 / Property 4
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.routers.wp_render_strategies._h3_investment_property import (
    build_h3_tb_values,
)
from app.services.four_table.h3_account_scope import (
    H3_ACCOUNT_SPEC,
    H3_SLOT_KEY_PREFIX,
)
from app.services.four_table.semantic_account_resolver import (
    ChartRow,
    RESOLVED_FROM_NONE,
    ResolvedSlot,
    SemanticAccountResult,
    match_slot_in_chart,
    resolve_semantic_accounts,
)

_STRATEGY = (
    Path(__file__).resolve().parents[2]
    / "app/routers/wp_render_strategies/_h3_investment_property.py"
)
_SCOPE = (
    Path(__file__).resolve().parents[2]
    / "app/services/four_table/h3_account_scope.py"
)

# 实证客户科目表（`account_chart source='client'`，6 个项目形态）
CLIENT_ROWS = [
    ChartRow("1521", "投资性房地产", "client", "debit"),
    ChartRow("1521.01", "投资性房地产_房屋建筑物", "client", "debit"),
    ChartRow("1521.02", "投资性房地产_土地使用权", "client", "debit"),
    ChartRow("1525", "投资性房地产累计折旧", "client", "debit"),
    ChartRow("1526", "投资性房地产累计摊销", "client", "debit"),
    ChartRow("1527", "投资性房地产减值准备", "client", "debit"),
    ChartRow("1527.01", "投资性房地产减值准备_房屋建筑物", "client", "debit"),
    # 干扰项：另两个循环的旧准则科目（原实现取的就是这两个）
    ChartRow("1503", "可供出售金融资产", "client", "debit"),
    ChartRow("1504", "债权投资", "client", "debit"),
    # 干扰项：损益侧同名科目
    ChartRow("6101.02", "公允价值变动损益_投资性房地产", "client", "credit"),
    ChartRow("6701.06", "资产减值损失_投资性房地产减值损失", "client", "debit"),
]


def _strip_comments(src: str) -> str:
    """剥 Python 注释与 docstring —— 踩坑说明里会写反例科目码，不剥必误判。"""
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    return re.sub(r"(?m)#.*$", "", out)


# ─────────────────────── 规格声明本身 ───────────────────────


class TestSpecDeclaration:
    def test_four_slots_declared(self):
        """H3 需要 4 个槽 —— 原实现只有 2 个（缺累计摊销与减值准备）。"""
        keys = [s.key for s in H3_ACCOUNT_SPEC.slots]
        assert keys == ["gross", "accum_dep", "accum_amort", "impairment"]

    def test_slot_key_prefix_covers_all_slots(self):
        assert set(H3_SLOT_KEY_PREFIX) == {s.key for s in H3_ACCOUNT_SPEC.slots}

    def test_existing_frontend_contract_prefixes_preserved(self):
        """``ip_*`` / ``dep_*`` 是既有前端契约，不得改名。"""
        assert H3_SLOT_KEY_PREFIX["gross"] == "ip"
        assert H3_SLOT_KEY_PREFIX["accum_dep"] == "dep"

    def test_report_row_code_is_bs_027(self):
        assert H3_ACCOUNT_SPEC.row_code == "BS-027"

    def test_provision_slots_flagged_explicitly(self):
        """🔴 `direction` 实证全为 debit（含累计折旧）→ 备抵只能显式声明，不可靠方向推断。"""
        by_key = {s.key: s for s in H3_ACCOUNT_SPEC.slots}
        assert by_key["gross"].is_provision is False
        for k in ("accum_dep", "accum_amort", "impairment"):
            assert by_key[k].is_provision is True

    def test_every_slot_has_exclusion_words(self):
        """每个槽都要有否决词或精确唯一名 —— 否则父子名包含关系会串味。"""
        for slot in H3_ACCOUNT_SPEC.slots:
            assert slot.names, f"{slot.key} 未声明科目名"
            if slot.key == "gross":
                assert slot.exclude_names, "原值槽必须有否决词（累计折旧含『投资性房地产』）"

    def test_gross_excludes_all_provision_keywords(self):
        gross = H3_ACCOUNT_SPEC.slots[0]
        for kw in ("累计折旧", "累计摊销", "减值准备"):
            assert kw in gross.exclude_names


# ─────────────────────── 匹配行为 ───────────────────────


class TestMatching:
    def test_gross_only_hits_1521(self):
        rows, exact = match_slot_in_chart(H3_ACCOUNT_SPEC.slots[0], CLIENT_ROWS)
        assert exact is True
        assert [r.account_code for r in rows] == ["1521"]

    def test_never_hits_other_cycles_accounts(self):
        """🔴 原实现取的 ``1503`` / ``1504`` 属 G6 / G4，任何槽都不得命中。"""
        forbidden = {"1503", "1504"}
        for slot in H3_ACCOUNT_SPEC.slots:
            rows, _ = match_slot_in_chart(slot, CLIENT_ROWS)
            assert not (forbidden & {r.account_code for r in rows}), (
                f"{slot.key} 命中了别循环科目"
            )

    def test_slots_are_disjoint(self):
        seen: dict[str, str] = {}
        for slot in H3_ACCOUNT_SPEC.slots:
            rows, _ = match_slot_in_chart(slot, CLIENT_ROWS)
            for r in rows:
                assert r.account_code not in seen, (
                    f"{r.account_code} 同时被 {seen.get(r.account_code)} 与 {slot.key} 命中"
                )
                seen[r.account_code] = slot.key

    def test_pl_side_lookalikes_excluded(self):
        """``公允价值变动损益_投资性房地产`` / ``资产减值损失_投资性房地产减值损失``
        是损益科目（且是二级），不得进任何资产槽。"""
        for slot in H3_ACCOUNT_SPEC.slots:
            rows, _ = match_slot_in_chart(slot, CLIENT_ROWS)
            codes = {r.account_code for r in rows}
            assert "6101.02" not in codes
            assert "6701.06" not in codes

    def test_reverse_check_gross_would_leak_without_exclusions(self):
        """反向自检：把否决词清空并用包含式名字，必须命中备抵 → 证明否决词有效。"""
        from app.services.four_table.semantic_account_resolver import (
            SemanticAccountSlot,
        )

        naked = SemanticAccountSlot(key="gross", names=("投资性房地产累",))
        rows, exact = match_slot_in_chart(naked, CLIENT_ROWS)
        assert exact is False
        assert {r.account_code for r in rows} == {"1525", "1526"}


# ─────────────────────── 金额聚合（纯函数）───────────────────────


def _tb(code, name, opening=0.0, closing=0.0, debit=0.0, credit=0.0):
    return {
        "account_code": code,
        "account_name": name,
        "opening_balance": opening,
        "closing_balance": closing,
        "debit_amount": debit,
        "credit_amount": credit,
        "closing_direction": "debit",
        "dataset_id": "ds1",
    }


def _result(**codes) -> SemanticAccountResult:
    slots = {}
    for key, (orig, std) in codes.items():
        slots[key] = ResolvedSlot(
            key=key,
            label=key,
            codes=list(orig),
            standard_codes=list(std),
            resolved_from="account_chart_client",
            exact=True,
        )
    return SemanticAccountResult(slots=slots, chart_available=True)


class TestBuildH3TbValues:
    def test_aggregates_leaves_only(self):
        """父科目行不得与子科目双算。"""
        rows = [
            _tb("1521", "投资性房地产", 300.0, 500.0),          # 父，非叶子
            _tb("1521.01", "房屋建筑物", 200.0, 300.0),
            _tb("1521.02", "土地使用权", 100.0, 200.0),
        ]
        got = build_h3_tb_values(_result(gross=(["1521"], ["1521"])), rows, [])
        assert got["ip_unadjusted_opening"] == 300.0
        assert got["ip_unadjusted_closing"] == 500.0

    def test_dot_boundary_prevents_sibling_family_leak(self):
        """🔴 原实现 ``c.startswith('1521')`` 会把 ``15210`` 算进来。"""
        rows = [
            _tb("1521", "投资性房地产", 0.0, 100.0),
            _tb("15210", "完全不同的科目", 0.0, 999.0),
        ]
        got = build_h3_tb_values(_result(gross=(["1521"], ["1521"])), rows, [])
        assert got["ip_unadjusted_closing"] == 100.0

    def test_all_four_slots_emit_keys(self):
        rows = [
            _tb("1521", "投资性房地产", 0.0, 1000.0),
            _tb("1525", "累计折旧", 0.0, 300.0),
            _tb("1526", "累计摊销", 0.0, 50.0),
            _tb("1527", "减值准备", 0.0, 20.0),
        ]
        accounts = _result(
            gross=(["1521"], ["1521"]),
            accum_dep=(["1525"], ["1525"]),
            accum_amort=(["1526"], ["1526"]),
            impairment=(["1527"], ["1527"]),
        )
        got = build_h3_tb_values(accounts, rows, [])
        assert got["ip_unadjusted_closing"] == 1000.0
        assert got["dep_unadjusted_closing"] == 300.0
        assert got["amort_unadjusted_closing"] == 50.0
        assert got["impair_unadjusted_closing"] == 20.0

    def test_missing_slot_emits_no_key_not_zero(self):
        """🔴 本项目无该科目 → **不产生键**，让前端能区分「无科目」与「余额 0」。"""
        rows = [_tb("1521", "投资性房地产", 0.0, 1000.0)]
        accounts = SemanticAccountResult(
            slots={
                "gross": ResolvedSlot(
                    key="gross", label="原值", codes=["1521"], standard_codes=["1521"]
                ),
                "accum_amort": ResolvedSlot(
                    key="accum_amort", label="累计摊销", resolved_from=RESOLVED_FROM_NONE
                ),
            },
            chart_available=True,
        )
        got = build_h3_tb_values(accounts, rows, [])
        assert "ip_unadjusted_closing" in got
        assert not any(k.startswith("amort_") for k in got)

    def test_trial_balance_matched_by_exact_standard_code(self):
        """🔴 原实现用 ``LIKE '1503%'``；改为标准码精确匹配，避免吃进兄弟科目族。"""
        trial = [
            {"standard_account_code": "1521", "unadjusted_amount": 900.0, "audited_amount": 950.0},
            {"standard_account_code": "15210", "unadjusted_amount": 777.0, "audited_amount": 777.0},
            {"standard_account_code": "1525", "unadjusted_amount": 300.0, "audited_amount": 310.0},
        ]
        accounts = _result(gross=(["1521"], ["1521"]), accum_dep=(["1525"], ["1525"]))
        got = build_h3_tb_values(accounts, [], trial)
        assert got["ip_unadjusted"] == 900.0
        assert got["ip_audited"] == 950.0
        assert got["dep_unadjusted"] == 300.0

    def test_merged_mapping_granularity_is_honoured(self):
        """实证：某项目把 ``1525 累计折旧`` 映射到标准码 ``1521``（并入母科目）。

        此时累计折旧槽的 `standard_codes` 应为 ``['1521']`` —— 若代码写死 ``1525``
        查 `trial_balance` 会取空。本测试锁死「按解析结果查」而非按字面量。
        """
        trial = [
            {"standard_account_code": "1521", "unadjusted_amount": 700.0, "audited_amount": 700.0},
        ]
        accounts = _result(accum_dep=(["1525"], ["1521"]))
        got = build_h3_tb_values(accounts, [], trial)
        assert got["dep_unadjusted"] == 700.0

    def test_empty_inputs_return_empty(self):
        assert build_h3_tb_values(SemanticAccountResult(), [], []) == {}


# ─────────────────────── 源码级：不得写死别循环科目码 ───────────────────────


class TestNoForeignAccountLiterals:
    """Property 4：render 源码不得出现属于其它循环的科目码字面量。"""

    #: H3 自己的科目族 + 平台通用（6051 其他业务收入用于租金勾稽）
    ALLOWED = {"1521", "1525", "1526", "1527", "6051"}
    #: 明确属于别循环、曾被 H3 误用的码
    FORBIDDEN = {"1501", "1502", "1503", "1504", "1505", "1506", "1507", "1519"}

    def test_strategy_source_readable(self):
        assert _STRATEGY.exists()
        assert len(_STRATEGY.read_text(encoding="utf-8")) > 2000

    def test_strategy_has_no_foreign_account_literals(self):
        src = _strip_comments(_STRATEGY.read_text(encoding="utf-8"))
        found = {c for c in self.FORBIDDEN if re.search(rf"['\"]{c}['\"]", src)}
        assert not found, f"H3 render 残留别循环科目码字面量：{sorted(found)}"

    def test_scope_module_only_declares_own_family(self):
        src = _strip_comments(_SCOPE.read_text(encoding="utf-8"))
        codes = set(re.findall(r"['\"](\d{4})['\"]", src))
        assert codes <= self.ALLOWED, f"scope 声明了非本族科目码：{sorted(codes - self.ALLOWED)}"

    def test_reverse_check_strip_comments_works(self):
        """反向自检：剥注释前源码确实含被禁码（docstring 里解释了 1503/1504）。"""
        raw = _STRATEGY.read_text(encoding="utf-8")
        assert "1503" in raw, "docstring 应保留缺陷说明（含 1503）"
        assert "1503" not in _strip_comments(raw)

    def test_reverse_check_regex_would_catch_a_planted_literal(self):
        planted = "x = '1506'\n"
        found = {c for c in self.FORBIDDEN if re.search(rf"['\"]{c}['\"]", planted)}
        assert found == {"1506"}


# ─────────────────────── 端到端（替身 session）───────────────────────


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, chart):
        self.chart = chart

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
        return _FakeResult([])


class _Ctx:
    def __init__(self, db):
        self.db = db
        self.project_id = "00000000-0000-0000-0000-000000000009"
        self.year = 2025


@pytest.mark.asyncio
class TestEndToEnd:
    async def test_resolves_all_four_slots_from_client_chart(self):
        got = await resolve_semantic_accounts(_Ctx(_FakeSession(CLIENT_ROWS)), H3_ACCOUNT_SPEC)
        assert got.codes_of("gross") == ["1521"]
        assert got.codes_of("accum_dep") == ["1525"]
        assert got.codes_of("accum_amort") == ["1526"]
        assert got.codes_of("impairment") == ["1527"]

    async def test_project_without_investment_property_returns_empty(self):
        chart = [ChartRow("1511", "长期股权投资", "client", "debit")]
        got = await resolve_semantic_accounts(_Ctx(_FakeSession(chart)), H3_ACCOUNT_SPEC)
        for key in H3_SLOT_KEY_PREFIX:
            assert got.slots[key].found is False
        assert build_h3_tb_values(got, [], []) == {}


# ─────────────── 裸名兜底导致跨循环串味（2026-08-04 真实库实证修复） ───────────────

#: standard 科目表实证形态：**没有** `1525/1526`，但有裸名 `累计折旧`(1602) 与 `累计摊销`(1702)。
#: 全库统计：裸名 `累计折旧` = 1602（standard 10 项目 / client 7 项目），
#: 裸名 `累计摊销` = 1702（standard 10 / client 8）；`1525/1526` 只在 4~5 个项目里有。
STANDARD_ROWS_WITHOUT_IP_PROVISIONS = [
    ChartRow("1521", "投资性房地产", "standard", "debit"),
    ChartRow("1601", "固定资产", "standard", "debit"),
    ChartRow("1602", "累计折旧", "standard", "debit"),
    ChartRow("1603", "固定资产减值准备", "standard", "debit"),
    ChartRow("1701", "无形资产", "standard", "debit"),
    ChartRow("1702", "累计摊销", "standard", "debit"),
]


class TestGenericNameDoesNotLeakAcrossCycles:
    """🔴 `累计折旧`/`累计摊销` 裸名属固定资产/无形资产，不得被投资性房地产认领。

    修复前实测三个项目的投资性房地产账面金额为负：
    `4f6dbc36` −21,601,944.08 / `df5b8403` −11,322,704.22 / `f064f5e4` −21,864,702.78。
    """

    def test_accum_dep_does_not_declare_bare_generic_name(self):
        by_key = {s.key: s for s in H3_ACCOUNT_SPEC.slots}
        assert "累计折旧" not in by_key["accum_dep"].names
        assert by_key["accum_dep"].names == ("投资性房地产累计折旧",)

    def test_accum_amort_does_not_declare_bare_generic_name(self):
        by_key = {s.key: s for s in H3_ACCOUNT_SPEC.slots}
        assert "累计摊销" not in by_key["accum_amort"].names
        assert by_key["accum_amort"].names == ("投资性房地产累计摊销",)

    def test_standard_chart_without_1525_yields_no_accum_dep(self):
        """科目表缺 1525 → accum_dep 无命中（而不是抓走固定资产的 1602）。"""
        by_key = {s.key: s for s in H3_ACCOUNT_SPEC.slots}
        rows, _ = match_slot_in_chart(
            by_key["accum_dep"], STANDARD_ROWS_WITHOUT_IP_PROVISIONS
        )
        assert rows == [], [r.account_code for r in rows]

    def test_standard_chart_without_1526_yields_no_accum_amort(self):
        by_key = {s.key: s for s in H3_ACCOUNT_SPEC.slots}
        rows, _ = match_slot_in_chart(
            by_key["accum_amort"], STANDARD_ROWS_WITHOUT_IP_PROVISIONS
        )
        assert rows == [], [r.account_code for r in rows]

    def test_gross_still_resolves_in_such_chart(self):
        """原值仍能定位到 1521 —— 修复只关掉备抵串味，不影响原值。"""
        rows, exact = match_slot_in_chart(
            H3_ACCOUNT_SPEC.slots[0], STANDARD_ROWS_WITHOUT_IP_PROVISIONS
        )
        assert exact is True
        assert [r.account_code for r in rows] == ["1521"]

    def test_client_chart_with_1525_1526_unchanged(self):
        """反向零回归：科目表有专名科目时，命中结果与修复前逐字相同。"""
        by_key = {s.key: s for s in H3_ACCOUNT_SPEC.slots}
        dep, dep_exact = match_slot_in_chart(by_key["accum_dep"], CLIENT_ROWS)
        amo, amo_exact = match_slot_in_chart(by_key["accum_amort"], CLIENT_ROWS)
        assert ([r.account_code for r in dep], dep_exact) == (["1525"], True)
        assert ([r.account_code for r in amo], amo_exact) == (["1526"], True)

    def test_reverse_selfcheck_bare_name_would_hit_1602(self):
        """反向自检：若把裸名加回去，accum_dep 必然精确命中 1602（证明本组断言非空转）。"""
        from dataclasses import replace

        by_key = {s.key: s for s in H3_ACCOUNT_SPEC.slots}
        regressed = replace(
            by_key["accum_dep"], names=("投资性房地产累计折旧", "累计折旧")
        )
        rows, exact = match_slot_in_chart(regressed, STANDARD_ROWS_WITHOUT_IP_PROVISIONS)
        assert exact is True
        assert [r.account_code for r in rows] == ["1602"], "裸名未命中 1602 → 前提失效"

    def test_h1_keeps_bare_generic_name_as_rightful_owner(self):
        """H1 保留裸名 `累计折旧` 是对的 —— 1602 本就是固定资产累计折旧。"""
        from app.services.four_table.h1_account_scope import H1_ACCOUNT_SPEC

        by_key = {s.key: s for s in H1_ACCOUNT_SPEC.slots}
        assert by_key["accum_dep"].names == ("累计折旧",)
        rows, exact = match_slot_in_chart(
            by_key["accum_dep"], STANDARD_ROWS_WITHOUT_IP_PROVISIONS
        )
        assert exact is True
        assert [r.account_code for r in rows] == ["1602"]

    def test_h8_bare_name_removed_but_behavior_unchanged_where_specific_exists(self):
        """H8 同款裸名已删（潜伏态）；有专名科目时命中不变。"""
        from app.services.four_table.h8_account_scope import H8_ACCOUNT_SPEC

        by_key = {s.key: s for s in H8_ACCOUNT_SPEC.slots}
        assert by_key["accum_dep"].names == ("使用权资产累计折旧",)
        rows, exact = match_slot_in_chart(
            by_key["accum_dep"],
            STANDARD_ROWS_WITHOUT_IP_PROVISIONS
            + [ChartRow("1652", "使用权资产累计折旧", "client", "debit")],
        )
        assert exact is True
        assert [r.account_code for r in rows] == ["1652"]

    def test_h5_keeps_bare_name_because_1632_is_its_own(self):
        """H5 保留裸名 `累计折耗` 是对的 —— 全库裸名 `累计折耗` 唯一对应 1632（油气资产）。"""
        from app.services.four_table.h5_account_scope import H5_ACCOUNT_SPEC

        by_key = {s.key: s for s in H5_ACCOUNT_SPEC.slots}
        assert "累计折耗" in by_key["accum_depletion"].names


    def test_h9_unearned_finance_requires_owner_prefix(self):
        """H9 同款：裸名 `未确认融资费用` 同时对应 2602(租赁负债) 与 2702(长期应付款)。

        DB 实证：`2702` 在 standard 侧 7 个项目 / client 侧 4 个项目都叫
        `未确认融资费用`（`df5b8403` client 侧直接叫「长期应付款未确认融资费用」），
        只按裸名定位会把 L5 的 contra 扣进租赁负债。当前 `2702` 全库余额为空 → 潜伏态。
        """
        from app.services.four_table.h9_account_scope import H9_ACCOUNT_SPEC

        by_key = {s.key: s for s in H9_ACCOUNT_SPEC.slots}
        slot = by_key["unearned_finance"]
        assert "未确认融资费用" not in slot.names, "裸名会串到长期应付款的 2702"
        assert slot.names == ("租赁负债未确认融资费用",)
        assert slot.fallback_standard_codes == ("2602",)

        rows = [
            ChartRow("2651", "租赁负债", "client", "credit"),
            ChartRow("2702", "未确认融资费用", "client", "credit"),
        ]
        hit, _ = match_slot_in_chart(slot, rows)
        assert hit == [], [r.account_code for r in hit]

    def test_h9_reverse_selfcheck_bare_name_would_hit_2702(self):
        """反向自检：裸名加回去必然命中 2702（证明上条断言非空转）。"""
        from dataclasses import replace

        from app.services.four_table.h9_account_scope import H9_ACCOUNT_SPEC

        by_key = {s.key: s for s in H9_ACCOUNT_SPEC.slots}
        regressed = replace(
            by_key["unearned_finance"], names=("未确认融资费用",), exclude_names=()
        )
        rows = [
            ChartRow("2651", "租赁负债", "client", "credit"),
            ChartRow("2702", "未确认融资费用", "client", "credit"),
        ]
        hit, exact = match_slot_in_chart(regressed, rows)
        assert exact is True
        assert [r.account_code for r in hit] == ["2702"]
