"""K2 其他流动资产 —— 四表取数科目口径守卫（Property 1~4, 8, 11）。

🔴 本文件锁死的是一条**实测出来的取错科目族**缺陷：

原实现 `_K2_ACCOUNT_PREFIXES = {"1231": "其他流动资产(借方/资产类)"}`，但 `1231` 是
**应收款项的坏账准备**（贷方备抵科目），与其他流动资产毫无关系。`report_config` 实证
`BS-014 其他流动资产 = TB('1901','期末余额')`（`listed_standalone` 另加 `TB('1131')`）。

活体 render-config 实测（改动前）：项目 `0ec33ac9` / wp `919e3387` 的
`tb_values.other_current_audited = 28,464,225.16`，`adjudication_prefill` 建出三行
「坏账准备_应收账款 26,401,719.77 / 坏账准备_应收票据 1,162,288.03 /
坏账准备_其他应收款 900,217.36」—— 把别的循环的备抵科目当资产列示，且与 D1/D2/K1
重复计入。这三个数字在本文件里作**反向断言**：修复后 K2 不得再出现。

全部 fake async session，不触库。

spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/
      Requirements 1.1~1.6, 2.6, 4.1 / Property 1, 2, 3, 4, 8, 11
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.routers.wp_render_strategies._k2_other_current_assets import (
    K2_ACCOUNT_SPEC,
    K2_DISCLOSURE_SHEET_LISTED,
    K2_DISCLOSURE_SHEET_SOE,
    K2_DIVIDEND_STANDARD,
    K2_FALLBACK_GROSS,
    K2_REPORT_ROW_CODE,
    K2_SHEETS,
    build_adjudication_prefill,
    build_tb_values,
    fetch_tb_balance_leaves,
    fetch_trial_balance_amounts,
    render,
)
from app.services.four_table.leaf_aggregation import (
    LeafRow,
    filter_by_prefixes,
    select_leaves,
)
from app.services.four_table.report_line_accounts import (
    RESOLVED_FROM_FALLBACK,
    RESOLVED_FROM_REPORT,
    ReportLineAccounts,
    resolve_report_line_accounts,
)

# ── 实证公式（DB 只读核查 report_config，四准则） ─────────────────────────────

K2_SOE_FORMULA = "TB('1901','期末余额')"
K2_LISTED_STANDALONE_FORMULA = "TB('1901','期末余额') + TB('1131','期末余额')"

#: 改动前的错误金额（项目 0ec33ac9），用作反向断言
BAD_DEBT_AR = 26401719.77          # 1231.02 坏账准备_应收账款
BAD_DEBT_NOTES = 1162288.03        # 1231.01 坏账准备_应收票据
BAD_DEBT_OTHER = 900217.36         # 1231.03 坏账准备_其他应收款
WRONG_K2_TOTAL = 28464225.16       # 三者之和 = 原 tb_values.other_current_audited


def _run(coro):
    return asyncio.run(coro)


def _ctx(session):
    return SimpleNamespace(db=session, project_id=uuid4(), wp_id=uuid4(), year=2025)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """按 SQL 关键字路由：projects / report_config / account_chart / account_mapping /
    trial_balance / checklist_responses / working_paper / tb_balance(select)。"""

    def __init__(
        self,
        *,
        formula=None,
        chart=None,
        mapping=None,
        standard=None,
        tb_rows=None,
        balance_rows=None,
        raise_on=None,
    ):
        self.formula = formula
        self.chart = chart or []
        self.mapping = mapping or []
        self.standard = standard
        self.tb_rows = tb_rows or []            # trial_balance 行
        self.balance_rows = balance_rows or []  # tb_balance 行（ORM select 路径）
        self.raise_on = raise_on
        self.rolled_back = False

    async def rollback(self):
        self.rolled_back = True

    async def execute(self, stmt, params=None):
        s = str(stmt)
        if self.raise_on == "all":
            raise RuntimeError("boom")
        if "projects" in s and "report_config" not in s:
            if self.raise_on == "projects":
                raise RuntimeError("projects boom")
            if "client_name" in s:  # _load_project_context 的 JOIN 查询
                return _Rows(
                    [SimpleNamespace(client_name="甲公司", audit_year=2025, business_category="制造业")]
                )
            return _Rows([SimpleNamespace(applicable_standard_v2=self.standard)])
        if "report_config" in s:
            if self.raise_on == "report":
                raise RuntimeError("report boom")
            return _Rows([SimpleNamespace(formula=self.formula)] if self.formula else [])
        if "account_chart" in s:
            if self.raise_on == "chart":
                raise RuntimeError("chart boom")
            return _Rows(self.chart)
        if "account_mapping" in s:
            if self.raise_on == "mapping":
                raise RuntimeError("mapping boom")
            wanted = set((params or {}).get("codes") or [])
            return _Rows(
                [
                    SimpleNamespace(original_account_code=orig)
                    for orig, std in self.mapping
                    if not wanted or std in wanted
                ]
            )
        if "trial_balance" in s:
            if self.raise_on == "trial_balance":
                raise RuntimeError("tb boom")
            return _Rows(self.tb_rows)
        if "checklist_responses" in s:
            if self.raise_on == "responses":
                raise RuntimeError("responses boom")
            return _Rows([])
        if "tb_balance" in s:
            if self.raise_on == "tb_balance":
                raise RuntimeError("balance boom")
            return _Rows(self.balance_rows)
        return _Rows([])


def _chart(code, name, direction):
    return {"account_code": code, "account_name": name, "direction": direction}


K2_CHART = [
    _chart("1901", "待处理财产损溢", "debit"),
    _chart("1131", "应收股利", "debit"),
    _chart("1231-01", "坏账准备-应收票据", "credit"),
    _chart("1231-03", "坏账准备-其他应收款", "credit"),
]

K2_MAPPING = [
    ("1901", "1901"),
    ("1901.01", "1901"),
    ("1131", "1131"),
    ("1231.01", "1231-01"),
    ("1231.02", "1231-02"),
    ("1231.03", "1231-03"),
]

#: 实测 tb_balance 形态：1901 族（本库全为 0）+ 三个坏账准备叶子（旧口径命中的就是它们）
K2_LEAVES = [
    LeafRow(account_code="1901.01", account_name="待处理流动资产损溢", opening=0.0, closing=0.0),
    LeafRow(account_code="1901.02", account_name="待处理固定资产损溢", opening=0.0, closing=0.0),
    LeafRow(account_code="1231.01", account_name="坏账准备_应收票据", opening=0.0, closing=BAD_DEBT_NOTES),
    LeafRow(account_code="1231.02", account_name="坏账准备_应收账款", opening=0.0, closing=BAD_DEBT_AR),
    LeafRow(account_code="1231.03", account_name="坏账准备_其他应收款", opening=0.0, closing=BAD_DEBT_OTHER),
]


def _accounts(formula=K2_SOE_FORMULA, mapping=K2_MAPPING, chart=None, standard=None):
    sess = _FakeSession(
        formula=formula,
        chart=K2_CHART if chart is None else chart,
        mapping=mapping,
        standard=standard or {"entity_type": "soe", "scope": "standalone"},
    )
    return _run(resolve_report_line_accounts(_ctx(sess), K2_ACCOUNT_SPEC))


# ── Property 1：科目集不含坏账准备族 ────────────────────────────────────────


def test_spec_declares_bs014_not_bad_debt():
    assert K2_REPORT_ROW_CODE == "BS-014"
    assert K2_ACCOUNT_SPEC.row_code == "BS-014"
    assert K2_FALLBACK_GROSS == "1901"
    assert K2_ACCOUNT_SPEC.fallback_gross == ("1901",)
    # 其他流动资产**无备抵科目** → 兜底备抵必须为空（不许写 1231）
    assert K2_ACCOUNT_SPEC.fallback_provision == ()
    assert K2_DIVIDEND_STANDARD == "1131"
    assert K2_ACCOUNT_SPEC.extra_standard_codes == ("1131",)


def test_resolved_scope_excludes_bad_debt_family():
    """Property 1：解析出的原值科目集与 1231 族无交集。"""
    acc = _accounts()
    bad = {"1231", "1231-01", "1231-02", "1231-03", "1231-05", "1231.01", "1231.02", "1231.03"}
    assert set(acc.gross_standard) & bad == set()
    assert set(acc.gross) & bad == set()
    assert acc.gross_standard == ["1901"]
    assert acc.gross == ["1901"]
    assert acc.provision == []
    assert acc.provision_standard == []
    assert acc.resolved_from == RESOLVED_FROM_REPORT


def test_reverse_selfcheck_old_prefix_would_hit_bad_debt():
    """反向自检：旧口径（宽前缀 1231）确实会命中三行坏账准备 —— 证明上条断言不空转。"""
    old_scope = filter_by_prefixes(K2_LEAVES, ["1231"])
    assert {r.account_code for r in old_scope} == {"1231.01", "1231.02", "1231.03"}
    assert sum(r.closing for r in old_scope) == pytest.approx(WRONG_K2_TOTAL, abs=0.01)
    # 新口径一行都不命中
    new_scope = filter_by_prefixes(K2_LEAVES, _accounts().gross)
    assert {r.account_code for r in new_scope} == {"1901.01", "1901.02"}


def test_tb_values_never_equals_wrong_total():
    """Property 1：修复后 tb_values 不得再出现 28,464,225.16。"""
    acc = _accounts()
    tb = build_tb_values(K2_LEAVES, acc, {})
    assert tb["other_current_unadjusted_closing"] == pytest.approx(0.0)
    for v in tb.values():
        assert v != pytest.approx(WRONG_K2_TOTAL, abs=0.01)


# ── Property 2：附加科目不并入原值 ──────────────────────────────────────────


def test_dividend_code_is_extra_not_gross():
    """listed_standalone 公式引用 1131，但它已属 BS-009（K1）→ 只能进 extra。"""
    acc = _accounts(
        formula=K2_LISTED_STANDALONE_FORMULA,
        standard={"entity_type": "listed", "scope": "standalone"},
    )
    assert acc.gross_standard == ["1901"]
    assert "1131" not in acc.gross_standard
    assert "1131" not in acc.gross
    assert acc.extra == {"1131": ["1131"]}
    assert acc.sign_of("1131") == 1


def test_tb_values_exclude_extra_amounts():
    """Property 2：`other_current_*` 只累加 gross_standard，1131 的金额不进来。"""
    acc = _accounts(
        formula=K2_LISTED_STANDALONE_FORMULA,
        standard={"entity_type": "listed", "scope": "standalone"},
    )
    tb_amounts = {
        "1901": {"unadjusted": 1000.0, "audited": 1200.0},
        "1131": {"unadjusted": 21000000.0, "audited": 21000000.0},
    }
    tb = build_tb_values(K2_LEAVES, acc, tb_amounts)
    assert tb["other_current_unadjusted"] == pytest.approx(1000.0)
    assert tb["other_current_audited"] == pytest.approx(1200.0)


# ── Property 3：叶子口径与点号边界 ──────────────────────────────────────────


def test_prefix_boundary_requires_dot():
    """`1901` 不得命中 `19010`（不同科目）。"""
    rows = [
        LeafRow(account_code="1901", closing=10.0),
        LeafRow(account_code="19010", closing=999.0),
        LeafRow(account_code="1901.01", closing=5.0),
    ]
    picked = {r.account_code for r in filter_by_prefixes(rows, ["1901"])}
    assert picked == {"1901", "1901.01"}
    assert "19010" not in picked


def test_leaf_only_no_parent_double_count():
    """叶子口径：父行不参与聚合，叶子之和 == 父行金额。"""
    rows = [
        LeafRow(account_code="1901", closing=15.0),
        LeafRow(account_code="1901.01", closing=10.0),
        LeafRow(account_code="1901.02", closing=5.0),
    ]
    leaves = select_leaves(rows)
    assert {r.account_code for r in leaves} == {"1901.01", "1901.02"}
    acc = _accounts()
    tb = build_tb_values(leaves, acc, {})
    assert tb["other_current_unadjusted_closing"] == pytest.approx(15.0)


def test_trial_balance_longest_prefix_attribution():
    """Property 3：trial_balance 父子并存时按最长前缀归属，不双计。"""
    sess = _FakeSession(
        tb_rows=[
            SimpleNamespace(standard_account_code="1901", unadjusted_amount=100, audited_amount=110),
            SimpleNamespace(standard_account_code="1901-01", unadjusted_amount=40, audited_amount=44),
            SimpleNamespace(standard_account_code="1131", unadjusted_amount=7, audited_amount=8),
            SimpleNamespace(standard_account_code="2202", unadjusted_amount=999, audited_amount=999),
        ]
    )
    got = _run(fetch_trial_balance_amounts(_ctx(sess), ["1901", "1131"]))
    # 1901 与 1901-01 都归 1901（最长前缀里只有 1901 是目标码）；2202 不在目标集
    assert got["1901"]["unadjusted"] == pytest.approx(140.0)
    assert got["1131"]["unadjusted"] == pytest.approx(7.0)
    assert set(got.keys()) == {"1901", "1131"}


def test_trial_balance_prefers_longest_target_code():
    """两个目标码互为前缀时归属更长者（1901-01 优先于 1901）。"""
    sess = _FakeSession(
        tb_rows=[
            SimpleNamespace(standard_account_code="1901-01", unadjusted_amount=40, audited_amount=44),
        ]
    )
    got = _run(fetch_trial_balance_amounts(_ctx(sess), ["1901", "1901-01"]))
    assert got["1901-01"]["unadjusted"] == pytest.approx(40.0)
    assert got["1901"]["unadjusted"] == pytest.approx(0.0)


def test_trial_balance_empty_codes_short_circuits():
    sess = _FakeSession(tb_rows=[SimpleNamespace(standard_account_code="1901", unadjusted_amount=1, audited_amount=1)])
    assert _run(fetch_trial_balance_amounts(_ctx(sess), [])) == {}
    assert _run(fetch_trial_balance_amounts(_ctx(sess), ["", "  "])) == {}


def test_trial_balance_fail_open_rolls_back():
    sess = _FakeSession(raise_on="trial_balance")
    got = _run(fetch_trial_balance_amounts(_ctx(sess), ["1901"]))
    assert got == {"1901": {"unadjusted": 0.0, "audited": 0.0}}
    assert sess.rolled_back is True


# ── Property 4：fail-open ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raise_on", [None, "projects", "report", "chart", "mapping", "all"]
)
def test_resolve_fail_open_gross_non_empty(raise_on):
    sess = _FakeSession(
        formula=None if raise_on else K2_SOE_FORMULA,
        chart=K2_CHART,
        mapping=K2_MAPPING,
        raise_on=raise_on,
    )
    acc = _run(resolve_report_line_accounts(_ctx(sess), K2_ACCOUNT_SPEC))
    assert acc.gross, "gross 恒非空（Property 4）"
    assert acc.gross == ["1901"]
    if raise_on:
        assert acc.resolved_from == RESOLVED_FROM_FALLBACK
    # 无备抵科目 → provision 为空是**合法态**（不得像 K1 那样恒非空）
    assert acc.provision == []


def test_leaves_fetch_fail_open():
    sess = _FakeSession(raise_on="all")
    assert _run(fetch_tb_balance_leaves(_ctx(sess))) == []


def test_render_fail_open_and_shape():
    """render 在依赖全挂时不抛，键集齐备，account_codes 是 1901 而不是 1231。"""
    sess = _FakeSession(raise_on="all")
    out = _run(render(_ctx(sess)))
    assert out is not None
    assert out["component_type"] == "k2-other-current-assets"
    assert out["account_codes"] == ["1901"]
    assert out["adjudication_prefill"] == []
    assert out["prefix"] == "K2"
    assert out["tb_source_codes"]["row_code"] == "BS-014"
    assert out["tb_source_codes"]["gross"] == ["1901"]
    assert out["tb_source_codes"]["provision"] == []
    assert out["sheets"] == K2_SHEETS
    # tb_values 键名不变（前端已在读）
    for key in (
        "other_current_unadjusted",
        "other_current_audited",
        "other_current_unadjusted_opening",
        "other_current_unadjusted_closing",
    ):
        assert key in out["tb_values"]


def test_render_account_codes_not_bad_debt():
    """反向断言：render 输出的 account_codes 不再是 `["1231"]`。"""
    sess = _FakeSession(
        formula=K2_SOE_FORMULA, chart=K2_CHART, mapping=K2_MAPPING,
        standard={"entity_type": "soe", "scope": "standalone"},
    )
    out = _run(render(_ctx(sess)))
    assert out["account_codes"] != ["1231"]
    assert out["account_codes"] == ["1901"]


# ── Property 8：宁缺勿造 ───────────────────────────────────────────────────


def test_prefill_is_empty_when_no_matching_leaves():
    """1901 全为 0（本库现状）→ 不建任何行，且绝不出现坏账准备行。"""
    acc = _accounts()
    rows = build_adjudication_prefill(K2_LEAVES, acc)
    assert rows == []


def test_prefill_never_contains_bad_debt_names():
    """反向自检：若把 gross 换成 1231（旧口径）就会建出三行坏账准备。"""
    wrong = ReportLineAccounts(gross=["1231"], gross_standard=["1231"])
    wrong_rows = build_adjudication_prefill(K2_LEAVES, wrong)
    assert [r["name"] for r in wrong_rows] == [
        "坏账准备_应收账款", "坏账准备_应收票据", "坏账准备_其他应收款",
    ]
    # 正确口径下一行都没有
    assert build_adjudication_prefill(K2_LEAVES, _accounts()) == []


def test_prefill_builds_rows_from_real_leaves():
    leaves = [
        LeafRow(account_code="1901.01", account_name="待摊费用", opening=100.0, closing=250.0),
        LeafRow(account_code="1901.02", account_name="待抵扣进项税", opening=0.0, closing=80.0),
        LeafRow(account_code="1901.03", account_name="", opening=1.0, closing=2.0),      # 无名跳过
        LeafRow(account_code="1901.04", account_name="预缴其他税费", opening=0.0, closing=0.0),  # 双零跳过
    ]
    rows = build_adjudication_prefill(leaves, _accounts())
    assert [r["name"] for r in rows] == ["待摊费用", "待抵扣进项税"]
    assert rows[0] == {
        "name": "待摊费用",
        "code": "1901.01",
        "opening_balance": 100.0,
        "closing_balance": 250.0,
    }
    # 按期末绝对值降序（负数也按绝对值排）
    assert abs(rows[0]["closing_balance"]) >= abs(rows[1]["closing_balance"])


def test_prefill_no_fallback_other_row():
    """旧实现「未匹配一律塞进 other 行」已删除：无科目就是空清单。"""
    empty = ReportLineAccounts(gross=[], gross_standard=[])
    assert build_adjudication_prefill(K2_LEAVES, empty) == []


# ── Property 11：sheet 名 ──────────────────────────────────────────────────


def test_disclosure_sheet_names_use_full_width_and_guoqi():
    """源 xlsx tab 名逐字：国企侧是「国企」而非「国有企业」，括号全角。"""
    assert K2_DISCLOSURE_SHEET_LISTED == "附注披露信息（上市公司）"
    assert K2_DISCLOSURE_SHEET_SOE == "附注披露信息（国企）"
    assert "国有企业" not in K2_DISCLOSURE_SHEET_SOE
    assert "(" not in K2_DISCLOSURE_SHEET_SOE and ")" not in K2_DISCLOSURE_SHEET_SOE
    names = [s["sheet_name"] for s in K2_SHEETS]
    assert K2_DISCLOSURE_SHEET_LISTED in names
    assert K2_DISCLOSURE_SHEET_SOE in names
    assert not any("国有企业" in n for n in names)


def test_k2_sheets_cover_all_workpaper_codes():
    names = " ".join(s["sheet_name"] for s in K2_SHEETS)
    for code in ("K2A", "K2-1", "K2-2", "K2-3", "K2-4", "K2-5", "K2-6"):
        assert code in names
    assert all(s["component_type"] == "k2-other-current-assets" for s in K2_SHEETS)
