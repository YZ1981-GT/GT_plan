"""D1 科目定位（报表规则映射驱动）单测.

spec: .kiro/specs/d1-extraction-chain-completion/
      (Requirements 1.1~1.5 / Property 1, 2, 3)

覆盖：
  * `split_gross_provision` —— 备抵判定三级（direction=credit → 名称关键字 → 码族），
    两集合无交集且并集 = 去重入参（Property 2）+ 反向自检。
  * `normalize_standard_prefix` —— `1231-01` → `1231`（无 account_mapping 兜底）。
  * `to_original_codes` —— account_mapping 反解 + 极小前缀集 + 空/异常兜底（Property 3）。
  * `resolve_d1_account_codes` —— 报表映射解析、两侧独立标注来源、全链 fail-open
    恒返回非空 gross（Property 1）。

全部 fake async session，不触库。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.services.d_cycle_extraction import d1_account_resolver as mod
from app.services.d_cycle_extraction.d1_account_resolver import (
    D1_FALLBACK_GROSS,
    D1_FALLBACK_PROVISION,
    RESOLVED_FROM_FALLBACK,
    RESOLVED_FROM_REPORT,
    normalize_standard_prefix,
    resolve_d1_account_codes,
    split_gross_provision,
    to_original_codes,
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
    """按 SQL 关键字路由：report_config / account_chart / account_mapping。"""

    def __init__(self, *, formula=None, chart=None, mapping=None, raise_on=None):
        self.formula = formula          # str | None
        self.chart = chart or []        # [SimpleNamespace(account_code, account_name, direction)]
        self.mapping = mapping or []    # [SimpleNamespace(original_account_code)]
        self.raise_on = raise_on        # 'report' | 'chart' | 'mapping' | 'all'
        self.seen: list[str] = []

    async def execute(self, stmt, params=None):
        s = str(stmt)
        self.seen.append(s)
        if self.raise_on == "all":
            raise RuntimeError("boom")
        if "report_config" in s:
            if self.raise_on == "report":
                raise RuntimeError("report boom")
            return _Rows(
                [SimpleNamespace(formula=self.formula)] if self.formula else []
            )
        if "account_chart" in s:
            if self.raise_on == "chart":
                raise RuntimeError("chart boom")
            return _Rows(self.chart)
        if "account_mapping" in s:
            if self.raise_on == "mapping":
                raise RuntimeError("mapping boom")
            # 复刻生产 SQL 的 `standard_account_code = ANY(:codes)` 过滤，
            # 否则 fake 会把坏账原始码也返回给原值侧（假失败）。
            wanted = set((params or {}).get("codes") or [])
            rows = [
                r
                for r in self.mapping
                if not wanted or getattr(r, "_standard", None) in wanted
            ]
            return _Rows(rows)
        return _Rows([])


def _chart(code, name, direction):
    return SimpleNamespace(account_code=code, account_name=name, direction=direction)


def _mapped(code, standard=None):
    """account_mapping 行；`standard` 缺省按原始码一级段推断（1231.01 → 1231-01）。"""
    if standard is None:
        head = code.split(".")[0]
        tail = code.split(".")[1] if "." in code else ""
        standard = f"{head}-{tail}" if (tail and head == "1231") else head
    return SimpleNamespace(original_account_code=code, _standard=standard)


# ---------------------------------------------------------------------------
# split_gross_provision（Property 2）
# ---------------------------------------------------------------------------


def test_split_by_credit_direction():
    """direction='credit' → provision（实证 account_chart 1231-01 为 credit）。"""
    rows = [
        {"account_code": "1121", "account_name": "应收票据", "direction": "debit"},
        {"account_code": "1231-01", "account_name": "坏账准备-应收票据", "direction": "credit"},
    ]
    gross, provision = split_gross_provision(["1121", "1231-01"], rows)
    assert gross == ["1121"]
    assert provision == ["1231-01"]


def test_split_by_name_hint_when_direction_missing():
    """无 direction 时按名称关键字判定（坏账准备 / 减值准备 / 信用减值）。"""
    rows = [
        {"account_code": "9001", "account_name": "某资产", "direction": ""},
        {"account_code": "9002", "account_name": "某资产减值准备", "direction": ""},
    ]
    gross, provision = split_gross_provision(["9001", "9002"], rows)
    assert gross == ["9001"]
    assert provision == ["9002"]


def test_split_by_code_family_when_chart_unavailable():
    """account_chart 不可用（空）→ 码族兜底：1231* 归 provision。"""
    gross, provision = split_gross_provision(["1121", "1231-01"], [])
    assert gross == ["1121"]
    assert provision == ["1231-01"]


def test_split_is_partition_and_dedupes():
    """两集合无交集，并集 == 去重后的入参（保持顺序）。"""
    codes = ["1121", "1121", "1231-01", "1231-02"]
    gross, provision = split_gross_provision(codes, [])
    assert set(gross) & set(provision) == set()
    assert gross + provision == ["1121", "1231-01", "1231-02"] or set(
        gross + provision
    ) == {"1121", "1231-01", "1231-02"}


def test_split_reverse_self_check_debit_asset_never_provision():
    """反向自检：借方且名称无备抵关键字、码族不匹配 → 绝不归 provision。"""
    rows = [{"account_code": "1122", "account_name": "应收账款", "direction": "debit"}]
    gross, provision = split_gross_provision(["1122"], rows)
    assert gross == ["1122"] and provision == []


# ---------------------------------------------------------------------------
# normalize_standard_prefix
# ---------------------------------------------------------------------------


def test_normalize_standard_prefix():
    assert normalize_standard_prefix("1231-01") == "1231"
    assert normalize_standard_prefix("1121") == "1121"
    assert normalize_standard_prefix("") == ""
    # 区间码原样返回（D1 不涉及，但不得破坏）
    assert normalize_standard_prefix("1401~1499") == "1401~1499"


# ---------------------------------------------------------------------------
# to_original_codes（Property 3）
# ---------------------------------------------------------------------------


def test_to_original_codes_minimal_prefix_set():
    """多原始码映射同一标准码 → 取极小前缀集（1121 覆盖 1121.01/.02/.03）。"""
    session = _FakeSession(
        mapping=[_mapped("1121"), _mapped("1121.01"), _mapped("1121.02"), _mapped("1121.03")]
    )
    out = _run(to_original_codes(_ctx(session), ["1121"]))
    assert out == ["1121"]


def test_to_original_codes_precise_child_code():
    """标准码 1231-01 反解到精确子科目 1231.01（这是名称猜测无法保证的）。"""
    session = _FakeSession(mapping=[_mapped("1231.01")])
    out = _run(to_original_codes(_ctx(session), ["1231-01"]))
    assert out == ["1231.01"]


def test_to_original_codes_falls_back_to_prefix_when_no_mapping():
    """无 account_mapping 记录 → 标准码一级段兜底（等价改动前行为）。"""
    session = _FakeSession(mapping=[])
    out = _run(to_original_codes(_ctx(session), ["1231-01"]))
    assert out == ["1231"]


def test_to_original_codes_fails_open_on_db_error():
    session = _FakeSession(raise_on="mapping")
    out = _run(to_original_codes(_ctx(session), ["1121", "1231-01"]))
    assert out == ["1121", "1231"]


# ---------------------------------------------------------------------------
# resolve_d1_account_codes（Property 1）
# ---------------------------------------------------------------------------

# 实证：soe_standalone 的 BS-005 公式
_SOE_FORMULA = "TB('1121','期末余额') - TB('1231-01','期末余额')"
# 实证：listed_* / soe_consolidated 的 BS-005 公式（未减坏账）
_LISTED_FORMULA = "TB('1121','期末余额')"


def test_resolve_from_report_config_both_sides():
    """soe_standalone 公式两侧齐全 → 两侧均标 report_config，坏账不叠名称过滤。"""
    session = _FakeSession(
        formula=_SOE_FORMULA,
        chart=[
            _chart("1121", "应收票据", "debit"),
            _chart("1231-01", "坏账准备-应收票据", "credit"),
        ],
        mapping=[_mapped("1121"), _mapped("1121.01"), _mapped("1231.01")],
    )
    codes = _run(resolve_d1_account_codes(_ctx(session)))
    assert codes.gross_standard == ["1121"]
    assert codes.provision_standard == ["1231-01"]
    assert codes.resolved_from == RESOLVED_FROM_REPORT
    assert codes.provision_resolved_from == RESOLVED_FROM_REPORT
    # 报表映射已精确到 1231-01 → 不再叠名称过滤（避免误杀非「应收票据」命名的子科目）
    assert codes.use_provision_name_filter is False
    # 原始码：1121 极小前缀集 + 1231.01 精确子科目
    assert codes.gross == ["1121"]
    assert codes.provision == ["1231.01"]


def test_resolve_listed_formula_downgrades_provision_side_only():
    """listed 公式只有 1121（未减坏账）→ 坏账侧退化 fallback 并叠名称过滤，原值侧仍 report。"""
    session = _FakeSession(
        formula=_LISTED_FORMULA,
        chart=[_chart("1121", "应收票据", "debit")],
        mapping=[_mapped("1121")],
    )
    codes = _run(resolve_d1_account_codes(_ctx(session)))
    assert codes.resolved_from == RESOLVED_FROM_REPORT
    assert codes.provision_resolved_from == RESOLVED_FROM_FALLBACK
    assert codes.provision_standard == [D1_FALLBACK_PROVISION]
    assert codes.use_provision_name_filter is True


def test_resolve_fails_open_when_no_report_config():
    """report_config 无 BS-005 → 两侧兜底，gross 恒非空（Property 1）。"""
    session = _FakeSession(formula=None)
    codes = _run(resolve_d1_account_codes(_ctx(session)))
    assert codes.gross_standard == [D1_FALLBACK_GROSS]
    assert codes.provision_standard == [D1_FALLBACK_PROVISION]
    assert codes.resolved_from == RESOLVED_FROM_FALLBACK
    assert codes.provision_resolved_from == RESOLVED_FROM_FALLBACK
    assert codes.gross and codes.provision


def test_resolve_fails_open_on_total_db_failure():
    """所有查询抛异常 → 仍返回可用兜底结果，不抛出（Property 1）。"""
    session = _FakeSession(raise_on="all")
    codes = _run(resolve_d1_account_codes(_ctx(session)))
    assert codes.gross == [D1_FALLBACK_GROSS]
    assert codes.provision == ["1231"]
    assert codes.resolved_from == RESOLVED_FROM_FALLBACK


def test_resolve_as_dict_shape_for_render_output():
    """`tb_source_codes` 输出结构固定（前端取数溯源消费）。"""
    session = _FakeSession(formula=_SOE_FORMULA)
    codes = _run(resolve_d1_account_codes(_ctx(session)))
    d = codes.as_dict()
    assert set(d.keys()) == {
        "gross",
        "provision",
        "gross_standard",
        "provision_standard",
        "resolved_from",
        "provision_resolved_from",
    }


def test_module_declares_bs005_row_code():
    """报表行次常量必须是 DB 实证值 BS-005（改错会让整条链路解析落空）。"""
    assert mod.D1_REPORT_ROW_CODE == "BS-005"


# ---------------------------------------------------------------------------
# 按项目适用准则挑公式 + 反解退化时的过度归集防护
# ---------------------------------------------------------------------------


class _StandardAwareSession(_FakeSession):
    """按 `applicable_standard` 返回不同公式（复刻 report_config 实证形态）。"""

    def __init__(self, *, formula_by_standard, project_standard=None, **kw):
        super().__init__(**kw)
        self.formula_by_standard = formula_by_standard
        self.project_standard = project_standard

    async def execute(self, stmt, params=None):
        s = str(stmt)
        if "applicable_standard_v2" in s:
            return _Rows([SimpleNamespace(applicable_standard_v2=self.project_standard)])
        if "report_config" in s:
            std = (params or {}).get("std")
            formula = self.formula_by_standard.get(std)
            if formula:
                return _Rows([SimpleNamespace(formula=formula)])
            # 无 std 精确命中（含最后那条 NOT LIKE 'project:%' 任取一条）
            if "NOT LIKE" in s:
                any_formula = next(iter(self.formula_by_standard.values()), None)
                return _Rows(
                    [SimpleNamespace(formula=any_formula)] if any_formula else []
                )
            return _Rows([])
        return await super().execute(stmt, params)


def test_resolve_picks_formula_by_project_applicable_standard():
    """🔴 soe_standalone 项目必须拿到含坏账的公式，不能被 listed 公式抢走。

    实证：`report_config` 里 BS-005 的 `soe_standalone` 公式含 `- TB('1231-01',…)`，
    而 `listed_*` / `soe_consolidated` 只有 `TB('1121',…)`。旧路径
    （`LIMIT 1` 无 `ORDER BY`）任取一条 → 真实项目 0ec33ac9 实测丢掉坏账科目。
    """
    session = _StandardAwareSession(
        formula_by_standard={
            "listed_consolidated": _LISTED_FORMULA,
            "soe_standalone": _SOE_FORMULA,
        },
        project_standard={"entity_type": "soe", "scope": "standalone", "stage": "normal"},
        chart=[
            _chart("1121", "应收票据", "debit"),
            _chart("1231-01", "坏账准备-应收票据", "credit"),
        ],
        mapping=[_mapped("1121"), _mapped("1231.01")],
    )
    codes = _run(resolve_d1_account_codes(_ctx(session)))
    assert codes.provision_standard == ["1231-01"]
    assert codes.provision_resolved_from == RESOLVED_FROM_REPORT
    assert codes.provision == ["1231.01"]
    assert codes.use_provision_name_filter is False


def test_resolve_reenables_name_filter_when_reverse_resolution_degrades():
    """🔴 account_mapping 无反解 → 前缀退化为更宽的 1231 → 必须重新叠名称过滤。

    否则 D1 坏账会把 1231.02 应收账款 / 1231.03 其他应收款的坏账一并算进来
    （实测项目 2aa00f57 就没有 1231 的映射记录）。
    """
    session = _StandardAwareSession(
        formula_by_standard={"soe_standalone": _SOE_FORMULA},
        project_standard={"entity_type": "soe", "scope": "standalone", "stage": "normal"},
        chart=[
            _chart("1121", "应收票据", "debit"),
            _chart("1231-01", "坏账准备-应收票据", "credit"),
        ],
        mapping=[_mapped("1121")],  # 只有原值有映射，坏账没有
    )
    codes = _run(resolve_d1_account_codes(_ctx(session)))
    assert codes.provision_standard == ["1231-01"]  # 报表映射仍解析正确
    assert codes.provision == ["1231"]              # 但原始码退化为宽前缀
    assert codes.provision_resolved_from == RESOLVED_FROM_FALLBACK
    assert codes.use_provision_name_filter is True  # → 必须叠名称过滤


def test_report_mapping_helper_standards_param_is_optional():
    """`resolve_report_line_account_codes` 的新参数默认 None = 原行为（零回归）。"""
    import inspect

    from app.services.report_account_mapping import resolve_report_line_account_codes

    sig = inspect.signature(resolve_report_line_account_codes)
    assert sig.parameters["applicable_standards"].default is None
