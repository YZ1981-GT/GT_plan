"""语义驱动逐项目科目定位守卫。

数据全部来自 2026-08-01 的 DB 只读实证（见 spec
`g-cycle-extraction-mapping-and-disclosure-alignment` 的 Notes）：

- `account_mapping` 同一原始码在不同项目映射到不同标准码
  （`1532`→`1532` vs →`1541`；`1525`→`1521` vs →`1525`）
- 平台标准科目表各项目不一致（4 个有 `1519` / 2 个只到 `1507` / 4 个完全没有）
- 客户科目表里压根没有 1504~1507/1519，唯一有投资类科目的项目用旧准则 `1501`/`1503`
- `report_config` 有 4 行错码（`BS-022`/`BS-025`/`BS-026` 连续偏移、`IS-016`↔`IS-017` 互换）

spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
      Requirements 1, 2 / Property 1~5
"""
from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.four_table.semantic_account_resolver import (
    RESOLVED_FROM_CLIENT_CHART,
    RESOLVED_FROM_FALLBACK,
    RESOLVED_FROM_NONE,
    RESOLVED_FROM_REPORT_CONFIG,
    RESOLVED_FROM_STANDARD_CHART,
    ChartRow,
    SemanticAccountSlot,
    SemanticAccountSpec,
    build_conflicts,
    extract_formula_codes,
    find_legacy_candidates,
    is_top_level_code,
    match_slot_in_chart,
    normalize_account_name,
    resolve_semantic_accounts,
    to_chart_rows,
)

# ─────────────────────────── 实证 fixture ───────────────────────────
# H3 投资性房地产：客户科目表（实证 6 个项目形态）
H3_CLIENT_ROWS = [
    ChartRow("1521", "投资性房地产", "client", "debit"),
    ChartRow("1521.01", "投资性房地产_房屋建筑物", "client", "debit"),
    ChartRow("1521.02", "投资性房地产_土地使用权", "client", "debit"),
    ChartRow("1525", "投资性房地产累计折旧", "client", "debit"),
    ChartRow("1526", "投资性房地产累计摊销", "client", "debit"),
    ChartRow("1527", "投资性房地产减值准备", "client", "debit"),
    ChartRow("1527.01", "投资性房地产减值准备_房屋建筑物", "client", "debit"),
    ChartRow("6101.02", "公允价值变动损益_投资性房地产", "client", "credit"),
    ChartRow("6701.06", "资产减值损失_投资性房地产减值损失", "client", "debit"),
]

# 旧准则项目（实证 df5b8403）：只有 1501/1502/1503，无 1504~1507
LEGACY_CLIENT_ROWS = [
    ChartRow("1501", "持有至到期投资", "client", "debit"),
    ChartRow("1502", "持有至到期投资减值准备", "client", "debit"),
    ChartRow("1503", "可供出售金融资产", "client", "debit"),
    ChartRow("1511", "长期股权投资", "client", "debit"),
]

H3_SLOTS = (
    SemanticAccountSlot(
        key="gross",
        names=("投资性房地产",),
        exclude_names=("累计折旧", "累计摊销", "减值准备", "公允价值变动", "减值损失"),
        fallback_standard_codes=("1521",),
        label="投资性房地产原值",
    ),
    SemanticAccountSlot(
        key="accum_dep",
        names=("投资性房地产累计折旧",),
        fallback_standard_codes=("1525",),
        label="累计折旧",
        is_provision=True,
    ),
    SemanticAccountSlot(
        key="accum_amort",
        names=("投资性房地产累计摊销",),
        fallback_standard_codes=("1526",),
        label="累计摊销",
        is_provision=True,
    ),
    SemanticAccountSlot(
        key="impairment",
        names=("投资性房地产减值准备",),
        exclude_names=("减值损失",),
        fallback_standard_codes=("1527",),
        label="减值准备",
        is_provision=True,
    ),
)


# ─────────────────────── 纯函数：名称归一 ───────────────────────


class TestNormalizeAccountName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("投资性房地产", "投资性房地产"),
            ("投资性房地产_房屋建筑物", "投资性房地产房屋建筑物"),
            ("其他应收款（其他）", "其他应收款其他"),
            ("项  目", "项目"),
            ("应收账款 - 关联方", "应收账款关联方"),
            ("　全角空格　", "全角空格"),
            ("ABC１２３", "abc123"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_normalizes(self, raw, expected):
        assert normalize_account_name(raw) == expected

    def test_parent_and_child_names_do_not_collapse(self):
        """🔴 归一不得把父子名合并 —— 否则精确匹配失效、原值槽会吃掉子科目。"""
        assert normalize_account_name("投资性房地产") != normalize_account_name(
            "投资性房地产_房屋建筑物"
        )
        assert normalize_account_name("投资性房地产") != normalize_account_name(
            "投资性房地产累计折旧"
        )


class TestIsTopLevelCode:
    @pytest.mark.parametrize(
        ("code", "expected"),
        [("1521", True), ("1521.01", False), ("1521.01.02", False), ("", False), (None, False)],
    )
    def test_top_level(self, code, expected):
        assert is_top_level_code(code) is expected


# ─────────────────────── 纯函数：槽匹配 ───────────────────────


class TestMatchSlotInChart:
    def test_exact_match_wins(self):
        rows, exact = match_slot_in_chart(H3_SLOTS[0], H3_CLIENT_ROWS)
        assert exact is True
        assert [r.account_code for r in rows] == ["1521"]

    def test_exclusion_prevents_provision_leaking_into_gross(self):
        """🔴 核心：`投资性房地产累计折旧` **包含** `投资性房地产`。

        无否决词时原值槽会把累计折旧 / 累计摊销 / 减值准备一并纳入 → 原值虚增。
        """
        rows, _ = match_slot_in_chart(H3_SLOTS[0], H3_CLIENT_ROWS)
        codes = {r.account_code for r in rows}
        assert codes == {"1521"}
        assert "1525" not in codes
        assert "1526" not in codes
        assert "1527" not in codes

    def test_reverse_check_without_exclusion_leaks(self):
        """反向自检：去掉否决词后**必须**泄漏 —— 证明上一条不是空断言。"""
        naked = SemanticAccountSlot(key="gross", names=("投资性房地产",))
        rows, exact = match_slot_in_chart(naked, H3_CLIENT_ROWS)
        codes = {r.account_code for r in rows}
        # 精确匹配仍只命中 1521（这是第二道防线），故显式验证包含匹配会泄漏
        assert exact is True and codes == {"1521"}
        loose = SemanticAccountSlot(key="gross", names=("投资性房地产累",))
        loose_rows, loose_exact = match_slot_in_chart(loose, H3_CLIENT_ROWS)
        assert loose_exact is False
        assert {r.account_code for r in loose_rows} == {"1525", "1526"}

    def test_only_top_level_accounts_matched(self):
        """子科目名很随意（`1531.01 押金`），按名称匹配子科目会误命中 → 只匹配一级。"""
        rows, _ = match_slot_in_chart(
            SemanticAccountSlot(key="x", names=("投资性房地产_房屋建筑物",)),
            H3_CLIENT_ROWS,
        )
        assert rows == []

    def test_provision_slots_match_exactly(self):
        for slot, expected in (
            (H3_SLOTS[1], "1525"),
            (H3_SLOTS[2], "1526"),
            (H3_SLOTS[3], "1527"),
        ):
            rows, exact = match_slot_in_chart(slot, H3_CLIENT_ROWS)
            assert exact is True
            assert [r.account_code for r in rows] == [expected]

    def test_impairment_excludes_loss_account(self):
        """`资产减值损失_投资性房地产减值损失` 是损益科目，不得进减值准备槽。"""
        rows, _ = match_slot_in_chart(H3_SLOTS[3], H3_CLIENT_ROWS)
        assert [r.account_code for r in rows] == ["1527"]

    def test_no_match_returns_empty(self):
        rows, exact = match_slot_in_chart(H3_SLOTS[0], LEGACY_CLIENT_ROWS)
        assert rows == [] and exact is False

    def test_empty_names_returns_empty(self):
        rows, exact = match_slot_in_chart(
            SemanticAccountSlot(key="x", names=()), H3_CLIENT_ROWS
        )
        assert rows == [] and exact is False


# ─────────────────────── 纯函数：公式码提取与冲突 ───────────────────────


class TestExtractFormulaCodes:
    @pytest.mark.parametrize(
        ("formula", "expected"),
        [
            ("TB('1521','期末余额')", ["1521"]),
            (
                "TB('1521','期末余额') - TB('1525','期末余额') - TB('1526','期末余额')",
                ["1521", "1525", "1526"],
            ),
            ("SUM_TB('1401~1499','期末余额')", ["1401~1499"]),
            ("ROW('BS-002') + ROW('BS-003')", []),
            (None, []),
            ("", []),
        ],
    )
    def test_extracts(self, formula, expected):
        assert extract_formula_codes(formula) == expected


class TestBuildConflicts:
    def test_detects_report_config_off_by_one(self):
        """实证 `BS-025 其他权益工具投资 = TB('1506')` 而 1506 实为「其他债权投资」。"""
        from app.services.four_table.semantic_account_resolver import ResolvedSlot

        slots = {
            "gross": ResolvedSlot(
                key="gross", label="其他权益工具投资", standard_codes=["1507"]
            )
        }
        conflicts = build_conflicts(slots, ["1506"])
        assert conflicts == [("gross", "1506", "1507")]

    def test_no_conflict_when_report_code_matches(self):
        from app.services.four_table.semantic_account_resolver import ResolvedSlot

        slots = {"gross": ResolvedSlot(key="gross", label="x", standard_codes=["1521"])}
        assert build_conflicts(slots, ["1521", "1525"]) == []

    def test_no_conflict_when_report_codes_empty(self):
        from app.services.four_table.semantic_account_resolver import ResolvedSlot

        slots = {"gross": ResolvedSlot(key="gross", label="x", standard_codes=["1521"])}
        assert build_conflicts(slots, []) == []

    def test_slot_without_standard_codes_is_skipped(self):
        from app.services.four_table.semantic_account_resolver import ResolvedSlot

        slots = {"gross": ResolvedSlot(key="gross", label="x")}
        assert build_conflicts(slots, ["1506"]) == []


class TestFindLegacyCandidates:
    def test_flags_old_standard_accounts_for_manual_mapping(self):
        """客户仍用旧准则 `1503 可供出售金融资产` → 提示人工映射，不自动归槽。"""
        spec = SemanticAccountSpec(
            row_code="BS-022",
            slots=(SemanticAccountSlot(key="gross", names=("其他债权投资",)),),
            legacy_standard_names=("可供出售金融资产", "持有至到期投资"),
        )
        got = find_legacy_candidates(spec, LEGACY_CLIENT_ROWS, resolved_codes=set())
        assert ("1501", "持有至到期投资") in got
        assert ("1503", "可供出售金融资产") in got

    def test_already_consumed_codes_not_flagged(self):
        spec = SemanticAccountSpec(
            row_code=None,
            slots=(),
            legacy_standard_names=("可供出售金融资产",),
        )
        got = find_legacy_candidates(spec, LEGACY_CLIENT_ROWS, resolved_codes={"1503"})
        assert got == []

    def test_no_legacy_names_declared_returns_empty(self):
        spec = SemanticAccountSpec(row_code=None, slots=())
        assert find_legacy_candidates(spec, LEGACY_CLIENT_ROWS, set()) == []


# ─────────────────────── to_chart_rows ───────────────────────


class TestToChartRows:
    def test_accepts_dicts_and_objects(self):
        from types import SimpleNamespace

        rows = to_chart_rows(
            [
                {"account_code": "1521", "account_name": "投资性房地产", "source": "client"},
                SimpleNamespace(
                    account_code=" 1525 ",
                    account_name=" 投资性房地产累计折旧 ",
                    source="client",
                    direction="debit",
                ),
                {"account_code": "", "account_name": "丢弃"},
            ]
        )
        assert [r.account_code for r in rows] == ["1521", "1525"]
        assert rows[1].account_name == "投资性房地产累计折旧"


# ─────────────────────── 端到端（替身 session）───────────────────────


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """按 SQL 关键字分派的替身。

    🔴 必须按 SQL **区分同一张表的多次查询**（account_mapping 既被反解也被正向查），
    否则两次返回同一批行会让测试变成噪声（D1 曾踩过这个坑）。
    """

    def __init__(self, *, chart, mapping_reverse=None, mapping_forward=None, formula=None):
        self.chart = chart
        self.mapping_reverse = mapping_reverse or []
        self.mapping_forward = mapping_forward or []
        self.formula = formula
        self.seen: list[str] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.seen.append(sql)
        if "account_chart" in sql:
            return _FakeResult(self.chart)
        if "original_account_code" in sql and "DISTINCT original_account_code" in sql:
            return _FakeResult(self.mapping_reverse)
        if "DISTINCT standard_account_code" in sql:
            return _FakeResult(self.mapping_forward)
        if "report_config" in sql:
            return _FakeResult(self.formula)
        if "applicable_standard_v2" in sql:
            return _FakeResult([])
        return _FakeResult([])


class _Ctx:
    def __init__(self, db):
        self.db = db
        self.project_id = "00000000-0000-0000-0000-000000000001"
        self.year = 2025


def _row(**kw):
    from types import SimpleNamespace

    return SimpleNamespace(**kw)


def _chart_payload(rows: list[ChartRow]):
    return [
        _row(
            account_code=r.account_code,
            account_name=r.account_name,
            direction=r.direction,
            source=r.source,
        )
        for r in rows
    ]


H3_SPEC = SemanticAccountSpec(
    row_code="BS-027",
    slots=H3_SLOTS,
    legacy_standard_names=("可供出售金融资产", "持有至到期投资"),
)


@pytest.mark.asyncio
class TestResolveSemanticAccounts:
    async def test_client_chart_hit_maps_forward_to_standard(self):
        db = _FakeSession(
            chart=_chart_payload(H3_CLIENT_ROWS),
            mapping_forward=[_row(standard_account_code="1521")],
            formula=[_row(formula="TB('1521','期末余额') - TB('1525','期末余额')")],
        )
        got = await resolve_semantic_accounts(_Ctx(db), H3_SPEC)
        assert got.chart_available is True
        gross = got.slots["gross"]
        assert gross.resolved_from == RESOLVED_FROM_CLIENT_CHART
        assert gross.exact is True
        assert gross.codes == ["1521"]
        assert gross.found is True
        assert got.row_code == "BS-027"
        assert got.report_config_codes == ["1521", "1525"]

    async def test_all_four_h3_slots_resolve_independently(self):
        """H3 需要 4 个槽（原值 / 累计折旧 / 累计摊销 / 减值准备），不是二元 gross/provision。"""
        db = _FakeSession(chart=_chart_payload(H3_CLIENT_ROWS))
        got = await resolve_semantic_accounts(_Ctx(db), H3_SPEC)
        assert got.codes_of("gross") == ["1521"]
        assert got.codes_of("accum_dep") == ["1525"]
        assert got.codes_of("accum_amort") == ["1526"]
        assert got.codes_of("impairment") == ["1527"]
        # 四个槽的码互不重叠
        buckets = [got.codes_of(k) for k in ("gross", "accum_dep", "accum_amort", "impairment")]
        flat = [c for b in buckets for c in b]
        assert len(flat) == len(set(flat))

    async def test_provision_flag_is_carried_to_output(self):
        db = _FakeSession(chart=_chart_payload(H3_CLIENT_ROWS))
        got = await resolve_semantic_accounts(_Ctx(db), H3_SPEC)
        assert got.slots["gross"].is_provision is False
        assert got.slots["accum_dep"].is_provision is True
        assert got.slots["impairment"].is_provision is True

    async def test_missing_account_returns_not_found_not_zero(self):
        """🔴 本项目确实没有该科目 → `found=False` + 空码，**不是**默默取 0。"""
        db = _FakeSession(chart=_chart_payload(LEGACY_CLIENT_ROWS))
        got = await resolve_semantic_accounts(_Ctx(db), H3_SPEC)
        for key in ("gross", "accum_dep", "accum_amort", "impairment"):
            assert got.slots[key].found is False
            assert got.slots[key].resolved_from == RESOLVED_FROM_NONE
            assert got.codes_of(key) == []

    async def test_legacy_accounts_surface_as_unmapped_candidates(self):
        db = _FakeSession(chart=_chart_payload(LEGACY_CLIENT_ROWS))
        got = await resolve_semantic_accounts(_Ctx(db), H3_SPEC)
        assert ("1503", "可供出售金融资产") in got.unmapped_candidates
        assert ("1501", "持有至到期投资") in got.unmapped_candidates

    async def test_standard_chart_fallback_reverse_maps_to_original(self):
        """客户表无命中 → 平台标准表命中 → 反解回本项目原始码。"""
        standard_only = [
            ChartRow("1521", "投资性房地产", "standard", "debit"),
            ChartRow("1525", "投资性房地产累计折旧", "standard", "debit"),
        ]
        db = _FakeSession(
            chart=_chart_payload(standard_only),
            mapping_reverse=[_row(original_account_code="1521.01")],
        )
        got = await resolve_semantic_accounts(_Ctx(db), H3_SPEC)
        gross = got.slots["gross"]
        assert gross.resolved_from == RESOLVED_FROM_STANDARD_CHART
        assert gross.standard_codes == ["1521"]
        assert gross.codes == ["1521.01"]

    async def test_report_config_code_used_only_when_present_in_chart(self):
        """报表公式给的码要**在本项目科目表里存在**才用（否则取空是正确行为）。"""
        chart = [ChartRow("1521", "某客户自定义名称", "client", "debit")]
        db = _FakeSession(
            chart=_chart_payload(chart),
            formula=[_row(formula="TB('1521','期末余额')")],
            mapping_forward=[_row(standard_account_code="1521")],
        )
        spec = SemanticAccountSpec(
            row_code="BS-027",
            slots=(SemanticAccountSlot(key="gross", names=("投资性房地产",)),),
        )
        got = await resolve_semantic_accounts(_Ctx(db), spec)
        assert got.slots["gross"].resolved_from == RESOLVED_FROM_REPORT_CONFIG
        assert got.codes_of("gross") == ["1521"]

    async def test_report_config_code_absent_from_chart_is_not_used(self):
        """实证形态：`BS-026` 引 `1507`，但很多项目科目表里没有这一族 → 必须取空。"""
        chart = [ChartRow("1511", "长期股权投资", "client", "debit")]
        db = _FakeSession(
            chart=_chart_payload(chart),
            formula=[_row(formula="TB('1507','期末余额')")],
        )
        spec = SemanticAccountSpec(
            row_code="BS-026",
            slots=(
                SemanticAccountSlot(
                    key="gross",
                    names=("其他非流动金融资产",),
                    fallback_standard_codes=("1519",),
                ),
            ),
        )
        got = await resolve_semantic_accounts(_Ctx(db), spec)
        assert got.slots["gross"].found is False
        assert got.slots["gross"].resolved_from == RESOLVED_FROM_NONE

    # ── 🔴 报表公式兜底层（层③）只对**单槽**规格生效 ──────────────────────────
    #
    # 报表公式给的是**整条报表行**的科目集（`BS-002 货币资金` = 1001+1002+1012）。
    # 单槽规格下「该行就这些科目」成立；多槽规格下把整份分给某个未命中的子项槽
    # = 该子项拿到**整行金额**，属数字级错误。E1 真实 DB 实测两处：
    #   ① `finance_co`/`digital`（`fallback=()`，准则解释15号「可增设」）各自拿到
    #      `['1001','1002','1012']` → 两行都等于货币资金全额；
    #   ② 项目 `2aa00f57` 无「库存现金」→ `cash` 拿到 `['1002','1012']`
    #      → `total = cash+bank+other` 把 1002/1012 算两遍，合计虚增一倍
    #      （8,935,072.24 vs 真值 4,467,536.12）。
    # G1/G10 的 `derivative`、G4/G7 的 `provision`、H3 的三个备抵槽是同款潜伏态
    # （层③排在层④之前 → own fallback 用不上，备抵会拿到**原值科目码**）。

    async def test_report_config_tier_skipped_for_multi_slot_spec(self):
        """多槽规格：未按名命中且无自有兜底码的槽 → `found=False`，不得吃报表行科目集。"""
        chart = [
            ChartRow("1001", "库存现金", "client", "debit"),
            ChartRow("1002", "银行存款", "client", "debit"),
            ChartRow("1012", "其他货币资金", "client", "debit"),
        ]
        db = _FakeSession(
            chart=_chart_payload(chart),
            formula=[
                _row(
                    formula="TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')"
                )
            ],
            mapping_forward=[_row(standard_account_code="1001")],
        )
        spec = SemanticAccountSpec(
            row_code="BS-002",
            slots=(
                SemanticAccountSlot(key="cash", names=("库存现金",), fallback_standard_codes=("1001",)),
                SemanticAccountSlot(key="bank", names=("银行存款",), fallback_standard_codes=("1002",)),
                # 「可增设」项目：本项目没有 → 必须返空
                SemanticAccountSlot(key="digital", names=("数字货币",)),
            ),
        )
        got = await resolve_semantic_accounts(_Ctx(db), spec)
        assert got.slots["cash"].found is True
        assert got.slots["bank"].found is True
        digital = got.slots["digital"]
        assert digital.found is False, "多槽规格下未命中槽不得吃报表行科目集"
        assert digital.codes == []
        assert digital.standard_codes == []
        assert digital.resolved_from == RESOLVED_FROM_NONE

    async def test_multi_slot_missing_slot_does_not_double_count(self):
        """多槽：某槽科目本项目不存在 → 该槽返空，其余槽互不重叠（合计不会翻倍）。"""
        chart = [
            ChartRow("1002", "银行存款", "client", "debit"),
            ChartRow("1012", "其他货币资金", "client", "debit"),
        ]
        db = _FakeSession(
            chart=_chart_payload(chart),
            formula=[
                _row(
                    formula="TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')"
                )
            ],
        )
        spec = SemanticAccountSpec(
            row_code="BS-002",
            slots=(
                SemanticAccountSlot(
                    key="cash",
                    names=("库存现金", "现金"),
                    exclude_names=("银行", "其他货币"),
                    fallback_standard_codes=("1001",),
                ),
                SemanticAccountSlot(key="bank", names=("银行存款",), fallback_standard_codes=("1002",)),
                SemanticAccountSlot(key="other", names=("其他货币资金",), fallback_standard_codes=("1012",)),
            ),
        )
        got = await resolve_semantic_accounts(_Ctx(db), spec)
        assert got.slots["cash"].found is False, "本项目无库存现金 → 返空而不是吃 1002/1012"
        assert got.codes_of("bank") == ["1002"]
        assert got.codes_of("other") == ["1012"]
        # 参与合计的槽两两无交集 → 不会重复计算
        claimed = [set(got.codes_of(k)) for k in ("cash", "bank", "other")]
        for i in range(len(claimed)):
            for j in range(i + 1, len(claimed)):
                assert not (claimed[i] & claimed[j]), "参与合计的槽科目码不得重叠"

    async def test_multi_slot_provision_never_inherits_gross_report_code(self):
        """多槽：备抵槽未按名命中时不得从层③拿到**原值**科目码（否则备抵 == 原值）。"""
        chart = [ChartRow("1521", "投资性房地产", "client", "debit")]
        db = _FakeSession(
            chart=_chart_payload(chart),
            formula=[_row(formula="TB('1521','期末余额')")],
            mapping_forward=[_row(standard_account_code="1521")],
        )
        spec = SemanticAccountSpec(
            row_code="BS-027",
            slots=(
                SemanticAccountSlot(key="gross", names=("投资性房地产",), fallback_standard_codes=("1521",)),
                SemanticAccountSlot(
                    key="impairment",
                    names=("投资性房地产减值准备",),
                    fallback_standard_codes=("1527",),
                    is_provision=True,
                ),
            ),
        )
        got = await resolve_semantic_accounts(_Ctx(db), spec)
        assert got.codes_of("gross") == ["1521"]
        assert got.slots["impairment"].found is False
        assert "1521" not in got.codes_of("impairment"), "备抵槽绝不能拿到原值科目码"

    async def test_report_config_tier_still_active_for_single_slot(self):
        """反向自检：单槽规格下层③**仍然生效**（否则本次收窄改动过度、G2/G5 等会回退）。"""
        chart = [ChartRow("1531", "客户自定义名", "client", "debit")]
        db = _FakeSession(
            chart=_chart_payload(chart),
            formula=[_row(formula="TB('1531','期末余额')")],
            mapping_forward=[_row(standard_account_code="1531")],
        )
        spec = SemanticAccountSpec(
            row_code="BS-023",
            slots=(SemanticAccountSlot(key="gross", names=("长期应收款",)),),
        )
        got = await resolve_semantic_accounts(_Ctx(db), spec)
        assert got.slots["gross"].resolved_from == RESOLVED_FROM_REPORT_CONFIG
        assert got.codes_of("gross") == ["1531"]

    async def test_conflict_reported_when_report_config_points_elsewhere(self):
        """`report_config` 错码时以名称结果为准，并暴露冲突供溯源告警。"""
        chart = [ChartRow("1507", "其他权益工具投资", "client", "debit")]
        db = _FakeSession(
            chart=_chart_payload(chart),
            formula=[_row(formula="TB('1506','期末余额')")],
            mapping_forward=[_row(standard_account_code="1507")],
        )
        spec = SemanticAccountSpec(
            row_code="BS-025",
            slots=(
                SemanticAccountSlot(
                    key="gross",
                    names=("其他权益工具投资",),
                    fallback_standard_codes=("1507",),
                ),
            ),
        )
        got = await resolve_semantic_accounts(_Ctx(db), spec)
        assert got.codes_of("gross") == ["1507"]
        assert got.conflicts == [("gross", "1506", "1507")]

    async def test_chart_unavailable_degrades_to_bare_fallback(self):
        """科目表整体不可用（未导入 / 查询失败）→ 允许裸兜底码，并标 `chart_available=False`。"""
        db = _FakeSession(chart=[])
        got = await resolve_semantic_accounts(_Ctx(db), H3_SPEC)
        assert got.chart_available is False
        assert got.slots["gross"].resolved_from == RESOLVED_FROM_FALLBACK
        assert got.codes_of("gross") == ["1521"]

    async def test_db_exception_does_not_break_render(self):
        class _Boom:
            async def execute(self, *a, **k):
                raise RuntimeError("db down")

        got = await resolve_semantic_accounts(_Ctx(_Boom()), H3_SPEC)
        assert got.chart_available is False
        assert got.slots["gross"].resolved_from == RESOLVED_FROM_FALLBACK

    async def test_no_row_code_skips_formula_lookup(self):
        db = _FakeSession(chart=_chart_payload(H3_CLIENT_ROWS))
        spec = SemanticAccountSpec(row_code=None, slots=H3_SLOTS)
        got = await resolve_semantic_accounts(_Ctx(db), spec)
        assert got.formula is None
        assert got.report_config_codes == []
        assert got.conflicts == []
        assert not any("report_config" in s for s in db.seen)

    async def test_as_dict_is_json_serializable(self):
        import json

        db = _FakeSession(
            chart=_chart_payload(H3_CLIENT_ROWS),
            formula=[_row(formula="TB('1521','期末余额')")],
        )
        got = await resolve_semantic_accounts(_Ctx(db), H3_SPEC)
        payload = got.as_dict()
        json.dumps(payload, ensure_ascii=False)
        assert payload["slots"]["gross"]["codes"] == ["1521"]
        assert payload["slots"]["accum_dep"]["is_provision"] is True
        assert payload["chart_available"] is True


# ─────────────────────── Property-based ───────────────────────


_NAME_CHARS = st.sampled_from(list("投资性房地产累计折旧摊销减值准备其他应收款项目"))
_names = st.text(alphabet=_NAME_CHARS, min_size=1, max_size=12)
_codes = st.text(alphabet=st.sampled_from(list("0123456789")), min_size=4, max_size=4)


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.tuples(_codes, _names), min_size=0, max_size=8))
def test_property_exclusion_never_returns_excluded_names(pairs):
    """Property：命中行的科目名**永不**含否决词（无论科目表长什么样）。"""
    rows = [ChartRow(c, n, "client", "debit") for c, n in pairs]
    slot = SemanticAccountSlot(
        key="gross",
        names=("投资性房地产",),
        exclude_names=("累计折旧", "累计摊销", "减值准备"),
    )
    got, _ = match_slot_in_chart(slot, rows)
    for r in got:
        norm = normalize_account_name(r.account_name)
        assert "累计折旧" not in norm
        assert "累计摊销" not in norm
        assert "减值准备" not in norm


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.tuples(_codes, _names), min_size=0, max_size=8))
def test_property_only_top_level_codes_returned(pairs):
    """Property：命中行恒为一级科目（码内无点号）。"""
    rows = [ChartRow(c, n, "client", "debit") for c, n in pairs] + [
        ChartRow("1521.01", "投资性房地产", "client", "debit")
    ]
    slot = SemanticAccountSlot(key="gross", names=("投资性房地产",))
    got, _ = match_slot_in_chart(slot, rows)
    assert all(is_top_level_code(r.account_code) for r in got)


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(_codes, min_size=0, max_size=6), st.lists(_codes, min_size=0, max_size=6))
def test_property_conflicts_only_when_disjoint(report_codes, actual_codes):
    """Property：仅当报表码集与实际码集**无交集**且两者都非空时才报冲突。"""
    from app.services.four_table.semantic_account_resolver import ResolvedSlot

    slots = {"g": ResolvedSlot(key="g", label="x", standard_codes=list(actual_codes))}
    got = build_conflicts(slots, list(report_codes))
    if not report_codes or not actual_codes:
        assert got == []
    elif set(report_codes) & set(actual_codes):
        assert got == []
    else:
        assert len(got) == 1 and got[0][0] == "g"


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.tuples(_codes, _names), min_size=1, max_size=8))
def test_property_exact_match_implies_normalized_equality(pairs):
    """Property：`exact=True` 时命中行的归一名必等于某个候选名。"""
    rows = [ChartRow(c, n, "client", "debit") for c, n in pairs]
    slot = SemanticAccountSlot(key="g", names=("投资性房地产", "其他应收款"))
    got, exact = match_slot_in_chart(slot, rows)
    if exact:
        wanted = {normalize_account_name(n) for n in slot.names}
        assert all(normalize_account_name(r.account_name) in wanted for r in got)
