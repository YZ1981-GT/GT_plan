"""报表映射规则驱动的科目定位 —— 共享件单测（Property 2, 3, 10）。

fixture 用 K1 的实证公式与科目关系（DB 只读核查）::

    BS-009 其他应收款
      soe_standalone : TB('1221','期末余额') - TB('1231-03','期末余额') + TB('1131','期末余额')
      listed_*       : TB('1221','期末余额')
    account_mapping : 1221 / 1221.11 / … → 1221 ；1231.03 → 1231-03 ；1131 → 1131

全部 fake async session，不触库。

spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/
      Requirements 1.1~1.6 / Property 2, 3, 10
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.four_table.report_line_accounts import (
    RESOLVED_FROM_FALLBACK,
    RESOLVED_FROM_REPORT,
    ReportLineAccountSpec,
    extract_signed_codes,
    minimal_prefix_set,
    normalize_standard_prefix,
    resolve_report_line_accounts,
    split_gross_provision,
)

K1_SOE_FORMULA = (
    "TB('1221','期末余额') - TB('1231-03','期末余额') + TB('1131','期末余额')"
)
K1_LISTED_FORMULA = "TB('1221','期末余额')"

K1_SPEC = ReportLineAccountSpec(
    row_code="BS-009",
    fallback_gross=("1221",),
    fallback_provision=("1231-03",),
    provision_name_filter="其他应收款",
    extra_standard_codes=("1131", "1132"),
)


def _run(coro):
    return asyncio.run(coro)


def _ctx(session):
    return SimpleNamespace(db=session, project_id=uuid4(), year=2025)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """按 SQL 关键字路由：projects / report_config / account_chart / account_mapping。"""

    def __init__(
        self,
        *,
        formula=None,
        chart=None,
        mapping=None,
        standard=None,
        raise_on=None,
    ):
        self.formula = formula
        self.chart = chart or []
        self.mapping = mapping or []            # [(original, standard), ...]
        self.standard = standard                # projects.applicable_standard_v2
        self.raise_on = raise_on                # 'projects'|'report'|'chart'|'mapping'|'all'

    async def execute(self, stmt, params=None):
        s = str(stmt)
        if self.raise_on == "all":
            raise RuntimeError("boom")
        if "projects" in s:
            if self.raise_on == "projects":
                raise RuntimeError("projects boom")
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
        return _Rows([])


def _chart(code, name, direction):
    return SimpleNamespace(account_code=code, account_name=name, direction=direction)


#: 实证：项目 0ec33ac9 的 account_chart 只有 1231-01（无 1231-03）→ 码族启发兜住
K1_CHART = [
    _chart("1221", "其他应收款", "debit"),
    _chart("1131", "应收股利", "debit"),
    _chart("1132", "应收利息", "debit"),
    _chart("1231-01", "坏账准备-应收票据", "credit"),
]

#: 同一份科目表的 dict 形态 —— 生产路径 `fetch_standard_chart_rows` 返回 dict，
#: 纯函数须两种形态都吃（本文件同时覆盖两条形态，防再踩 `'SimpleNamespace' has no get`）
K1_CHART_DICTS = [
    {"account_code": c.account_code, "account_name": c.account_name, "direction": c.direction}
    for c in K1_CHART
]

K1_MAPPING = [
    ("1221", "1221"),
    ("1221.11", "1221"),
    ("1221.12", "1221"),
    ("1221.13", "1221"),
    ("1221.13.01", "1221"),
    ("1231.01", "1231-01"),
    ("1231.02", "1231-02"),
    ("1231.03", "1231-03"),
    ("1131", "1131"),
    ("1132", "1132"),
]


# ── 纯函数：拆分优先级（Property 2） ─────────────────────────────────────────


def test_split_by_credit_direction():
    rows = [
        {"account_code": "1221", "account_name": "其他应收款", "direction": "debit"},
        {"account_code": "1231-03", "account_name": "坏账准备-其他应收款", "direction": "credit"},
    ]
    gross, provision = split_gross_provision(["1221", "1231-03"], rows)
    assert gross == ["1221"]
    assert provision == ["1231-03"]


def test_split_by_name_hint_when_direction_missing():
    rows = [{"account_code": "1231-03", "account_name": "坏账准备-其他应收款", "direction": ""}]
    gross, provision = split_gross_provision(["1221", "1231-03"], rows)
    assert gross == ["1221"]
    assert provision == ["1231-03"]


def test_split_by_code_family_when_chart_empty():
    """实证：account_chart 常缺 1231-03 行 → 码族前缀 1231 兜住。"""
    gross, provision = split_gross_provision(["1221", "1231-03", "1131"], [])
    assert gross == ["1221", "1131"]
    assert provision == ["1231-03"]


def test_split_partition_is_exhaustive_and_disjoint():
    codes = ["1221", "1231-03", "1131", "1221", ""]
    gross, provision = split_gross_provision(codes, K1_CHART_DICTS)
    assert set(gross) & set(provision) == set()
    assert set(gross) | set(provision) == {"1221", "1231-03", "1131"}


def test_split_reverse_selfcheck_chart_actually_used():
    """反向自检：把 1221 的方向改成 credit 后必须落入 provision（证明 chart 生效）。"""
    rows = [{"account_code": "1221", "account_name": "其他应收款", "direction": "credit"}]
    gross, provision = split_gross_provision(["1221"], rows)
    assert gross == []
    assert provision == ["1221"]


# ── 纯函数：前缀归一 / 极小前缀集 ────────────────────────────────────────────


@pytest.mark.parametrize(
    "code,expected",
    [("1231-03", "1231"), ("1221", "1221"), ("1401~1499", "1401~1499"), ("", ""), ("  ", "")],
)
def test_normalize_standard_prefix(code, expected):
    assert normalize_standard_prefix(code) == expected


def test_minimal_prefix_set_drops_covered_children():
    assert minimal_prefix_set(["1221", "1221.11", "1221.12", "1221.13.01"]) == ["1221"]
    assert minimal_prefix_set(["1221.11", "1221.12"]) == ["1221.11", "1221.12"]
    assert minimal_prefix_set(["", "  ", None]) == []


def test_minimal_prefix_set_keeps_sibling_branches():
    assert minimal_prefix_set(["1231.03", "1131"]) == ["1131", "1231.03"]


# ── 纯函数：公式符号（Property 10） ──────────────────────────────────────────


def test_extract_signed_codes_from_soe_formula():
    assert extract_signed_codes(K1_SOE_FORMULA) == [
        ("1221", 1),
        ("1231-03", -1),
        ("1131", 1),
    ]


def test_extract_signed_codes_listed_and_empty():
    assert extract_signed_codes(K1_LISTED_FORMULA) == [("1221", 1)]
    assert extract_signed_codes(None) == []
    assert extract_signed_codes("") == []


def test_extract_signed_codes_handles_sum_tb_and_dedup():
    f = "SUM_TB('1400~1499','期末余额') - TB('1471','期末余额') + TB('1471','期末余额')"
    assert extract_signed_codes(f) == [("1400~1499", 1), ("1471", -1)]


# ── 端到端解析（Property 2, 3） ──────────────────────────────────────────────


def test_resolve_soe_standalone_full_chain():
    """soe_standalone：原值 1221、备抵精确到原始码 1231.03、附加 1131/1132 单列。"""
    sess = _FakeSession(
        formula=K1_SOE_FORMULA,
        chart=K1_CHART,
        mapping=K1_MAPPING,
        standard={"entity_type": "soe", "scope": "standalone", "stage": "normal"},
    )
    acc = _run(resolve_report_line_accounts(_ctx(sess), K1_SPEC))

    assert acc.gross_standard == ["1221"]
    assert acc.provision_standard == ["1231-03"]
    assert acc.gross == ["1221"]
    assert acc.provision == ["1231.03"]
    # 附加科目不并入原值
    assert "1131" not in acc.gross_standard
    assert acc.extra == {"1131": ["1131"], "1132": ["1132"]}
    assert acc.resolved_from == RESOLVED_FROM_REPORT
    assert acc.provision_resolved_from == RESOLVED_FROM_REPORT
    assert acc.use_provision_name_filter is False
    assert acc.sign_of("1231-03") == -1
    assert acc.sign_of("1221") == 1
    assert acc.sign_of("1132") == 0
    assert acc.row_code == "BS-009"


def test_provision_excludes_other_receivable_types():
    """Property 2：备抵原始码集与应收票据/应收账款/长期应收款的坏账无交集。"""
    sess = _FakeSession(
        formula=K1_SOE_FORMULA, chart=K1_CHART, mapping=K1_MAPPING,
        standard={"entity_type": "soe", "scope": "standalone"},
    )
    acc = _run(resolve_report_line_accounts(_ctx(sess), K1_SPEC))
    assert set(acc.provision) & {"1231.01", "1231.02", "1231.05"} == set()
    assert set(acc.provision) == {"1231.03"}


def test_resolve_listed_formula_falls_back_on_provision_side():
    """listed 的 BS-009 公式不含坏账 → 备抵侧用兜底标准码，但反解仍精确。"""
    sess = _FakeSession(
        formula=K1_LISTED_FORMULA,
        chart=K1_CHART,
        mapping=K1_MAPPING,
        standard={"entity_type": "listed", "scope": "standalone"},
    )
    acc = _run(resolve_report_line_accounts(_ctx(sess), K1_SPEC))
    assert acc.gross_standard == ["1221"]
    assert acc.resolved_from == RESOLVED_FROM_REPORT
    assert acc.provision_standard == ["1231-03"]
    assert acc.provision == ["1231.03"]
    # 公式没引用备抵 → 该侧标注 fallback（保守口径，与 D1 既有行为一致）
    assert acc.provision_resolved_from == RESOLVED_FROM_FALLBACK
    assert acc.use_provision_name_filter is True
    # 但反解是精确的 → 需要精确判定的调用方读 provision_exact
    assert acc.provision_exact is True


def test_wide_prefix_degradation_requires_name_filter():
    """无 account_mapping 记录 → 退化为宽前缀 1231，必须叠名称过滤（Property 2 后半）。"""
    sess = _FakeSession(formula=K1_SOE_FORMULA, chart=K1_CHART, mapping=[])
    acc = _run(resolve_report_line_accounts(_ctx(sess), K1_SPEC))
    assert acc.provision == ["1231"]
    assert acc.provision_resolved_from == RESOLVED_FROM_FALLBACK
    assert acc.use_provision_name_filter is True
    assert acc.provision_exact is False


@pytest.mark.parametrize(
    "raise_on", [None, "projects", "report", "chart", "mapping", "all"]
)
def test_fail_open_never_raises_and_gross_non_empty(raise_on):
    """Property 3：任意依赖失败组合下都返回可用结果、gross 非空、不抛。"""
    sess = _FakeSession(
        formula=None if raise_on else K1_SOE_FORMULA,
        chart=K1_CHART,
        mapping=K1_MAPPING,
        raise_on=raise_on,
    )
    acc = _run(resolve_report_line_accounts(_ctx(sess), K1_SPEC))
    assert acc.gross, "gross 恒非空"
    assert acc.provision, "provision 恒非空"
    if raise_on:
        assert acc.resolved_from == RESOLVED_FROM_FALLBACK


def test_no_report_config_row_uses_spec_fallback():
    sess = _FakeSession(formula=None, chart=[], mapping=[])
    acc = _run(resolve_report_line_accounts(_ctx(sess), K1_SPEC))
    assert acc.gross_standard == ["1221"]
    assert acc.provision_standard == ["1231-03"]
    assert acc.gross == ["1221"]
    assert acc.provision == ["1231"]      # 宽前缀兜底
    assert acc.resolved_from == RESOLVED_FROM_FALLBACK
    assert acc.use_provision_name_filter is True
    assert acc.formula is None
    assert acc.signed_codes == []


def test_as_dict_shape_for_tb_source_codes():
    sess = _FakeSession(
        formula=K1_SOE_FORMULA, chart=K1_CHART, mapping=K1_MAPPING,
        standard={"entity_type": "soe", "scope": "standalone"},
    )
    acc = _run(resolve_report_line_accounts(_ctx(sess), K1_SPEC))
    d = acc.as_dict()
    assert d["row_code"] == "BS-009"
    assert d["gross"] == ["1221"]
    assert d["provision"] == ["1231.03"]
    assert d["extra"] == {"1131": ["1131"], "1132": ["1132"]}
    assert d["signed_codes"] == [["1221", 1], ["1231-03", -1], ["1131", 1]]
    assert d["use_provision_name_filter"] is False
    assert d["formula"] == K1_SOE_FORMULA


def test_extra_codes_removed_from_gross_even_if_formula_references_them():
    """1131 在 soe 公式里是 `+TB('1131')` → 会被解析进 codes，但必须摘出 gross。"""
    sess = _FakeSession(
        formula=K1_SOE_FORMULA, chart=K1_CHART, mapping=K1_MAPPING,
        standard={"entity_type": "soe", "scope": "standalone"},
    )
    acc = _run(resolve_report_line_accounts(_ctx(sess), K1_SPEC))
    assert "1131" not in acc.gross_standard
    assert "1131" in acc.extra
    # 反向自检：不声明 extra 时 1131 确实会留在 gross（证明摘除逻辑生效）
    spec_no_extra = ReportLineAccountSpec(
        row_code="BS-009",
        fallback_gross=("1221",),
        fallback_provision=("1231-03",),
    )
    sess2 = _FakeSession(
        formula=K1_SOE_FORMULA, chart=K1_CHART, mapping=K1_MAPPING,
        standard={"entity_type": "soe", "scope": "standalone"},
    )
    acc2 = _run(resolve_report_line_accounts(_ctx(sess2), spec_no_extra))
    assert "1131" in acc2.gross_standard
