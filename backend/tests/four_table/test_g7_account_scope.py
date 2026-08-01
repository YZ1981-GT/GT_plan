"""G7 科目定位 + 取数口径守卫（禁硬编码 / 报表映射单一真源）。

DB 只读实证的链路（本文件 fixture 逐字照抄）::

    report_config
      BS-024 长期股权投资            = TB('1511','期末余额')      ← 四准则完全一致
      IMP-009 八、长期股权投资减值准备 = TB('1512','期末余额')      ← 仅 soe_standalone 有公式
                                                                  soe_consolidated 为 NULL
                                                                  listed_* 无该行
    account_mapping  1511 / 1511.01 / 1511.03 / 1511.04.01 … → 1511 ；1512 → 1512
    tb_balance       1511(父) / 1511.01 / 1511.02 / 1511.03 / 1511.04 → .04.01 / .04.02 / 1512

活体金额（项目 `2aa00f57`）::

    1511.01 期初 53,218,583.61  1511.03 期初 −12,759,523.01  → 合 40,459,060.60 = 父额
    1512    期初 −2,840,032.97  贷 1,950,000.00  期末 −4,790,032.97（负值存储）

spec: g7-four-table-extraction-and-disclosure-alignment
      Requirements 1.1~1.8 / 2.1~2.4 / 4.4 / 11.2，Property 1~7 / 14 / 15
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import openpyxl
import pytest

from app.routers.wp_render_strategies import _g7_long_term_equity_main as g7
from app.services.four_table.g7_investment_buckets import (
    BUCKET_ASSOCIATE,
    BUCKET_IMPAIRMENT,
    BUCKET_JV,
    BUCKET_OTHER,
    BUCKET_SUBSIDIARY,
    MOVEMENT_NATURE_BUCKETS,
)
from app.services.four_table.leaf_aggregation import LeafRow, select_leaves
from app.services.four_table.report_line_accounts import (
    RESOLVED_FROM_FALLBACK,
    RESOLVED_FROM_REPORT,
    resolve_report_line_accounts,
)

_SOURCE_XLSX = "backend/wp_templates/G/G7 长期股权投资.xlsx"

BS_024_FORMULA = "TB('1511','期末余额')"
IMP_009_FORMULA = "TB('1512','期末余额')"

#: 活体 account_mapping（9 项目一致）
G7_MAPPING = [
    ("1511", "1511"),
    ("1511.01", "1511"),
    ("1511.02", "1511"),
    ("1511.03", "1511"),
    ("1511.04", "1511"),
    ("1511.04.01", "1511"),
    ("1511.04.02", "1511"),
    ("1512", "1512"),
]

#: 活体 account_chart（source='standard' 只有一级科目 —— 这正是分类不能靠标准科目表的原因）
G7_CHART = [
    SimpleNamespace(account_code="1511", account_name="长期股权投资", direction="debit"),
    SimpleNamespace(
        account_code="1512", account_name="长期股权投资减值准备", direction="credit"
    ),
]


def _run(coro):
    return asyncio.run(coro)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """按 SQL 关键字 + `params['rc']` 路由（G7 需要 BS-024 / IMP-009 两套公式）。"""

    def __init__(self, *, formulas=None, chart=None, mapping=None, standard=None, raise_on=None):
        self.formulas = formulas if formulas is not None else {}
        self.chart = chart if chart is not None else list(G7_CHART)
        self.mapping = mapping if mapping is not None else list(G7_MAPPING)
        self.standard = standard or {"scope": "standalone", "stage": "normal", "entity_type": "soe"}
        self.raise_on = raise_on
        self.report_calls: list[str] = []

    async def execute(self, stmt, params=None):
        s = str(stmt)
        p = params or {}
        if self.raise_on == "all":
            raise RuntimeError("boom")
        if "projects" in s:
            if self.raise_on == "projects":
                raise RuntimeError("projects boom")
            return _Rows([SimpleNamespace(applicable_standard_v2=self.standard)])
        if "report_config" in s:
            if self.raise_on == "report":
                raise RuntimeError("report boom")
            rc = str(p.get("rc") or "")
            std = str(p.get("std") or "")
            self.report_calls.append(f"{rc}|{std}")
            by_std = self.formulas.get(rc)
            if by_std is None:
                return _Rows([])
            if isinstance(by_std, str):
                return _Rows([SimpleNamespace(formula=by_std)])
            hit = by_std.get(std)
            return _Rows([SimpleNamespace(formula=hit)] if hit else [])
        if "account_chart" in s:
            if self.raise_on == "chart":
                raise RuntimeError("chart boom")
            return _Rows(self.chart)
        if "account_mapping" in s:
            if self.raise_on == "mapping":
                raise RuntimeError("mapping boom")
            wanted = set(p.get("codes") or [])
            return _Rows(
                [
                    SimpleNamespace(original_account_code=orig)
                    for orig, std in self.mapping
                    if not wanted or std in wanted
                ]
            )
        return _Rows([])


def _ctx(session):
    return SimpleNamespace(db=session, project_id=uuid4(), year=2025)


def _leaf(code, name="", opening=0.0, closing=0.0, debit=0.0, credit=0.0) -> LeafRow:
    return LeafRow(
        account_code=code,
        account_name=name,
        opening=opening,
        closing=closing,
        debit=debit,
        credit=credit,
    )


#: 叶子集 fixture（项目 `2aa00f57` 的数值形态；`1511` 父级已被 select_leaves 排除）
#:
#: ⚠️ 该项目 `tb_balance` 存在多个 dataset 版本，**active dataset** 里只有
#: `1511` / `1511.01` / `1512`（活体直跑实证）。这里额外放入 `1511.03 损益调整`
#: 与其对应的 `1511.01` 期初 53,218,583.61 —— 取自另一 dataset 版本，
#: 用来构造「父额 = 正数叶子 + 负数叶子」这一真实存在的形态，
#: 验证「原值侧不做方向翻正」。两个叶子之和仍等于父额 40,459,060.60。
LIVE_LEAVES = [
    _leaf("1511.01", "长期股权投资_对子公司的投资", 53218583.61, 40459060.60, credit=12759523.01),
    _leaf("1511.03", "长期股权投资_损益调整", -12759523.01, 0.0, debit=12759523.01),
    _leaf("1512", "长期股权投资减值准备", -2840032.97, -4790032.97, credit=1950000.00),
]
LIVE_ALL_ROWS = [
    _leaf("1511", "长期股权投资", 40459060.60, 40459060.60),
    *LIVE_LEAVES,
]


# ─────────────────────────────────────────────────────────────────────────────
# 1) 报表映射解析（BS-024 原值 + IMP-009 备抵独立行）
# ─────────────────────────────────────────────────────────────────────────────


class TestAccountResolution:
    def test_resolves_gross_and_provision_from_report_rows(self):
        db = _FakeSession(
            formulas={"BS-024": BS_024_FORMULA, "IMP-009": IMP_009_FORMULA}
        )
        acc = _run(resolve_report_line_accounts(_ctx(db), g7.G7_ACCOUNT_SPEC))
        assert acc.gross_standard == ["1511"]
        assert acc.provision_standard == ["1512"]
        assert acc.resolved_from == RESOLVED_FROM_REPORT
        assert acc.provision_resolved_from == RESOLVED_FROM_REPORT
        assert acc.provision_row_code == "IMP-009"
        assert acc.provision_formula == IMP_009_FORMULA
        # account_mapping 反解为极小前缀集（1511.01 等被 1511 覆盖）
        assert acc.gross == ["1511"]
        assert acc.provision == ["1512"]
        assert acc.provision_exact is True

    def test_provision_falls_back_when_imp_row_absent(self):
        """listed 侧无 IMP-009 行 → 回退兜底标准码，provision_resolved_from=fallback。"""
        db = _FakeSession(formulas={"BS-024": BS_024_FORMULA})
        acc = _run(resolve_report_line_accounts(_ctx(db), g7.G7_ACCOUNT_SPEC))
        assert acc.provision_standard == ["1512"]
        assert acc.provision_resolved_from == RESOLVED_FROM_FALLBACK
        assert acc.provision_row_code == ""
        assert acc.provision_formula is None

    def test_provision_row_queried_by_applicable_standard(self):
        """IMP-009 只在 soe_standalone 有公式 → 必须按准则精确匹配才命中。"""
        db = _FakeSession(
            formulas={
                "BS-024": BS_024_FORMULA,
                "IMP-009": {"soe_standalone": IMP_009_FORMULA},
            }
        )
        acc = _run(resolve_report_line_accounts(_ctx(db), g7.G7_ACCOUNT_SPEC))
        assert acc.provision_standard == ["1512"]
        assert any(c.startswith("IMP-009|soe_standalone") for c in db.report_calls)

    def test_gross_falls_back_when_no_config(self):
        """report_config 全空 → 两侧都回退兜底码，gross 恒非空（Property 3）。"""
        acc = _run(resolve_report_line_accounts(_ctx(_FakeSession()), g7.G7_ACCOUNT_SPEC))
        assert acc.gross_standard == ["1511"]
        assert acc.provision_standard == ["1512"]
        assert acc.resolved_from == RESOLVED_FROM_FALLBACK

    @pytest.mark.parametrize("raise_on", ["projects", "report", "chart", "mapping", "all"])
    def test_fail_open_on_every_db_failure(self, raise_on):
        """任一环 DB 异常一律 fail-open（Property 7），gross 仍非空。"""
        db = _FakeSession(
            formulas={"BS-024": BS_024_FORMULA, "IMP-009": IMP_009_FORMULA},
            raise_on=raise_on,
        )
        acc = _run(resolve_report_line_accounts(_ctx(db), g7.G7_ACCOUNT_SPEC))
        assert acc.gross, "gross 恒非空"
        assert acc.provision

    def test_spec_declares_report_rows_not_prefixes(self):
        """🔴 R11.2：科目由报表行声明，旧常量前缀必须已删。"""
        assert g7.G7_ACCOUNT_SPEC.row_code == "BS-024"
        assert g7.G7_ACCOUNT_SPEC.provision_row_code == "IMP-009"
        assert not hasattr(g7, "_G7_ACCOUNT_PREFIX")
        assert not hasattr(g7, "_G7_IMPAIRMENT_PREFIX")


# ─────────────────────────────────────────────────────────────────────────────
# 2) 叶子聚合口径（活体金额 / 点号边界 / abs 归一）
# ─────────────────────────────────────────────────────────────────────────────


class TestLeafAggregation:
    def _acc(self):
        db = _FakeSession(formulas={"BS-024": BS_024_FORMULA, "IMP-009": IMP_009_FORMULA})
        return _run(resolve_report_line_accounts(_ctx(db), g7.G7_ACCOUNT_SPEC))

    def test_leaf_sum_equals_parent_amount(self):
        """🔴 Property 1：叶子和 == 父科目行金额（活体逐分相等）。"""
        acc = self._acc()
        tb = g7.build_g7_tb_values(acc, LIVE_ALL_ROWS, LIVE_LEAVES)
        assert tb["opening"] == pytest.approx(40459060.60)
        assert tb["closing"] == pytest.approx(40459060.60)
        src = g7.build_g7_source_codes(acc, LIVE_ALL_ROWS, LIVE_LEAVES)
        assert src["parent_check"]["diff"] == 0.0

    def test_provision_absolute(self):
        """🔴 Property 3：备抵负值存储 → 输出为正。"""
        tb = g7.build_g7_tb_values(self._acc(), LIVE_ALL_ROWS, LIVE_LEAVES)
        assert tb["impairment_opening"] == pytest.approx(2840032.97)
        assert tb["impairment"] == pytest.approx(4790032.97)

    def test_debit_leaf_negative_value_not_flipped(self):
        """原值侧不做方向翻正：`1511.03` 期初 −12,759,523.01 保留符号，

        否则 `+ABS()` 会让叶子和变 65,978,106.62 ≠ 父额 40,459,060.60。
        """
        acc = self._acc()
        tb = g7.build_g7_tb_values(acc, LIVE_ALL_ROWS, LIVE_LEAVES)
        assert tb["opening"] == pytest.approx(40459060.60)
        assert tb["opening"] != pytest.approx(53218583.61 + 12759523.01)

    def test_select_leaves_excludes_parent(self):
        assert {r.account_code for r in select_leaves(LIVE_ALL_ROWS)} == {
            "1511.01",
            "1511.03",
            "1512",
        }

    def test_prefix_dot_boundary_reverse_check(self):
        """🔴 Property 2 + 反向自检：旧 `startswith` 口径会把 `15110` 算进来。"""
        acc = self._acc()
        rows = [_leaf("1511", closing=100.0), _leaf("15110", closing=999.0)]
        tb = g7.build_g7_tb_values(acc, rows, rows)
        assert tb["closing"] == pytest.approx(100.0)
        # 反证：无点号边界时会多算 999
        naive = sum(r.closing for r in rows if r.account_code.startswith("1511"))
        assert naive == pytest.approx(1099.0)


# ─────────────────────────────────────────────────────────────────────────────
# 3) 审定表未审数预填（宁缺勿造 / 变动性质不摊入类别）
# ─────────────────────────────────────────────────────────────────────────────


class TestAdjudicationPrefill:
    def _acc(self):
        db = _FakeSession(formulas={"BS-024": BS_024_FORMULA, "IMP-009": IMP_009_FORMULA})
        return _run(resolve_report_line_accounts(_ctx(db), g7.G7_ACCOUNT_SPEC))

    def test_live_shape(self):
        out = g7.build_g7_adjudication_prefill(self._acc(), LIVE_LEAVES)
        assert set(out) == {"gross", "impairment"}
        # 该项目只有「对子公司投资」这一类别 → 合营 / 联营键**不出现**（宁缺勿造）
        assert set(out["gross"]) == {BUCKET_SUBSIDIARY, BUCKET_OTHER}
        assert BUCKET_JV not in out["gross"]
        assert BUCKET_ASSOCIATE not in out["gross"]
        assert out["gross"][BUCKET_SUBSIDIARY]["opening"] == pytest.approx(53218583.61)
        assert out["gross"][BUCKET_SUBSIDIARY]["decrease"] == pytest.approx(12759523.01)
        assert out["gross"][BUCKET_SUBSIDIARY]["closing"] == pytest.approx(40459060.60)
        assert out["gross"][BUCKET_SUBSIDIARY]["roll_forward_ok"] is True

    def test_movement_nature_goes_to_other_only(self):
        """🔴 Property 6：损益调整不摊入子公司/合营/联营，只进 other 桶。"""
        out = g7.build_g7_adjudication_prefill(self._acc(), LIVE_LEAVES)
        other = out["gross"][BUCKET_OTHER]
        assert other["opening"] == pytest.approx(-12759523.01)
        assert other["increase"] == pytest.approx(12759523.01)
        assert other["closing"] == pytest.approx(0.0)
        assert other["from_buckets"] == ["equity_profit"]
        assert other["codes"] == ["1511.03"]
        # 类别桶金额里不含损益调整
        assert out["gross"][BUCKET_SUBSIDIARY]["codes"] == ["1511.01"]

    def test_other_bucket_is_exact_sum_of_nature_buckets(self):
        """other 桶金额 == 变动性质桶之和（不重不漏）。"""
        acc = self._acc()
        leaves = [
            _leaf("1511.01", "长期股权投资_对子公司的投资", 100.0, 100.0),
            _leaf("1511.03", "长期股权投资_损益调整", 10.0, 11.0),
            _leaf("1511.04.01", "长期股权投资_其他权益变动_属于其他综合收益", 20.0, 22.0),
            _leaf("1511.04.02", "长期股权投资_其他权益变动_不属于其他综合收益", 30.0, 33.0),
        ]
        cats = g7.build_g7_leaf_categories(acc, leaves)
        out = g7.build_g7_adjudication_prefill(acc, leaves)
        nature_sum = sum(
            cats["buckets"][b]["closing"] for b in MOVEMENT_NATURE_BUCKETS if b in cats["buckets"]
        )
        assert out["gross"][BUCKET_OTHER]["closing"] == pytest.approx(nature_sum)
        assert out["gross"][BUCKET_OTHER]["closing"] == pytest.approx(66.0)
        assert sorted(out["gross"][BUCKET_OTHER]["from_buckets"]) == [
            "equity_profit",
            "oci",
            "other_equity",
        ]

    def test_impairment_total_only(self):
        out = g7.build_g7_adjudication_prefill(self._acc(), LIVE_LEAVES)
        assert set(out["impairment"]) == {"total"}
        assert out["impairment"]["total"]["opening"] == pytest.approx(2840032.97)
        assert out["impairment"]["total"]["closing"] == pytest.approx(4790032.97)

    def test_provision_increase_comes_from_credit_side(self):
        """🔴 备抵是贷方科目：`credit_amount` 是**计提（增加）**，不是减少。

        活体实证（项目 `2aa00f57` 的 `1512`）：期初 2,840,032.97 + 计提 1,950,000.00
        = 期末 4,790,032.97。照原值侧口径（credit→decrease）会让 roll-forward 不平
        —— 这是本 spec 用真实数据跑出来的缺陷，守卫钉死方向。
        """
        row = g7.build_g7_adjudication_prefill(self._acc(), LIVE_LEAVES)["impairment"]["total"]
        assert row["increase"] == pytest.approx(1950000.00)
        assert row["decrease"] == pytest.approx(0.0)
        assert row["roll_forward_ok"] is True

    def test_gross_increase_comes_from_debit_side(self):
        """原值是借方科目：`debit_amount` 是增加、`credit_amount` 是减少（与备抵相反）。"""
        acc = self._acc()
        leaves = [
            _leaf(
                "1511.01", "长期股权投资_对子公司的投资",
                opening=100.0, closing=130.0, debit=50.0, credit=20.0,
            )
        ]
        row = g7.build_g7_adjudication_prefill(acc, leaves)["gross"][BUCKET_SUBSIDIARY]
        assert (row["increase"], row["decrease"]) == (pytest.approx(50.0), pytest.approx(20.0))
        assert row["roll_forward_ok"] is True

    def test_roll_forward_mismatch_exposed_not_hidden(self):
        """closing ≠ opening+增−减 → roll_forward_ok=False 且 closing 保留原值。"""
        acc = self._acc()
        leaves = [_leaf("1511.01", "长期股权投资_对子公司的投资", 100.0, 999.0, debit=1.0)]
        out = g7.build_g7_adjudication_prefill(acc, leaves)
        row = out["gross"][BUCKET_SUBSIDIARY]
        assert row["roll_forward_ok"] is False
        assert row["closing"] == pytest.approx(999.0)

    def test_empty_returns_empty_dict(self):
        """无叶子 → {}（不塞 0 骨架）。"""
        assert g7.build_g7_adjudication_prefill(self._acc(), []) == {}
        assert g7.build_g7_adjudication_prefill(None, LIVE_LEAVES) == {}

    def test_unmapped_only_yields_no_rows(self):
        """全部叶子都无法归类 → gross 为空，返回 {}（不编造）。"""
        acc = self._acc()
        leaves = [_leaf("1511.99", "长期股权投资_待分配", 1.0, 2.0)]
        assert g7.build_g7_adjudication_prefill(acc, leaves) == {}
        cats = g7.build_g7_leaf_categories(acc, leaves)
        assert [u["code"] for u in cats["unmapped"]] == ["1511.99"]


# ─────────────────────────────────────────────────────────────────────────────
# 4) 溯源载荷形态 + sheetName 与源 xlsx 一致
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceCodesShape:
    def test_keys(self):
        db = _FakeSession(formulas={"BS-024": BS_024_FORMULA, "IMP-009": IMP_009_FORMULA})
        acc = _run(resolve_report_line_accounts(_ctx(db), g7.G7_ACCOUNT_SPEC))
        src = g7.build_g7_source_codes(acc, LIVE_ALL_ROWS, LIVE_LEAVES)
        # 🔴 键名逐字对齐平台共享视图模型 `composables/shared/tbSourceCodes.ts`
        #    （报表行次是 `row_code`，不得再造 `report_row` 这类第二名字）
        assert set(src) == {
            "row_code",
            "gross_standard",
            "provision_standard",
            "gross",
            "provision",
            "extra",
            "signed_codes",
            "resolved_from",
            "provision_resolved_from",
            "provision_exact",
            "use_provision_name_filter",
            "formula",
            "provision_row_code",
            "provision_formula",
            "parent_check",
        }
        assert src["row_code"] == "BS-024"
        assert src["gross"] == ["1511.01", "1511.03"]
        assert src["provision"] == ["1512"]
        assert src["signed_codes"] == [["1511", 1]]

    def test_empty_without_accounts(self):
        assert g7.build_g7_source_codes(None, [], []) == {}


class TestSheetNamesMatchSourceXlsx:
    def test_every_sheet_name_is_verbatim(self):
        """🔴 Property 14：render 下发的 sheetName 必须逐字等于源 xlsx tab 名。

        旧值 `审定表G7-1` 缺科目前缀，与公式预设的 `长期股权投资审定表G7-1` 分叉。
        """
        wb = openpyxl.load_workbook(_SOURCE_XLSX, data_only=True)
        tabs = set(wb.sheetnames)
        for sheet in g7.G7_MAIN_SHEETS:
            assert sheet["sheetName"] in tabs, (
                f"sheetName {sheet['sheetName']!r} 不在源 xlsx tab 名集合中"
            )

    def test_adjudication_sheet_name_has_account_prefix(self):
        by_code = {s["code"]: s["sheetName"] for s in g7.G7_MAIN_SHEETS}
        assert by_code["G7-1"] == "长期股权投资审定表G7-1"


class TestBucketDefsPayload:
    def test_render_payload_includes_other_bucket(self):
        """前端只读 render 下发的 bucket_defs，不再抄一份中文标签（R11.3）。"""
        defs = g7.bucket_defs_payload()
        keys = [d["bucket"] for d in defs]
        assert BUCKET_OTHER in keys
        assert BUCKET_IMPAIRMENT in keys
        assert all(d["label"] for d in defs), "每个桶都要有中文标签"


# ─────────────────────────────────────────────────────────────────────────────
# 5) 反硬编码守卫：_G7_ACCOUNT_PREFIX 不得再被 render 用作输出值
# ─────────────────────────────────────────────────────────────────────────────


class TestNoHardcodedPrefixInRenderOutput:
    """🔴 R11.8 / Task 6.6：`_G7_ACCOUNT_PREFIX` 已删，render 输出的 account_code
    必须来自报表映射解析结果而非常量前缀。

    读源码断言 render 函数里不引用 `_G7_ACCOUNT_PREFIX` / `_G7_IMPAIRMENT_PREFIX`。
    必须先 stripComments() 再判 —— 解释性注释会提到旧常量名。
    """

    @staticmethod
    def _strip_comments(src: str) -> str:
        """去掉 Python 行注释 + 多行字符串（docstring 也视为注释）。"""
        import re
        # 去掉 # 开头行注释
        src = re.sub(r'#[^\n]*', '', src)
        # 去掉三引号多行字符串/docstring
        src = re.sub(r'"""[\s\S]*?"""', '', src)
        src = re.sub(r"'''[\s\S]*?'''", '', src)
        return src

    def test_render_source_does_not_reference_prefix_constants(self):
        """render 函数体（去注释后）不得引用已删除的旧前缀常量。"""
        import inspect
        source = inspect.getsource(g7.render)
        stripped = self._strip_comments(source)
        assert "_G7_ACCOUNT_PREFIX" not in stripped, (
            "render 函数仍引用 _G7_ACCOUNT_PREFIX —— "
            "account_code 应来自 resolve_report_line_accounts 的结果，不是常量"
        )
        assert "_G7_IMPAIRMENT_PREFIX" not in stripped, (
            "render 函数仍引用 _G7_IMPAIRMENT_PREFIX —— "
            "impairment_account_code 应来自解析结果，不是常量"
        )

    def test_reverse_self_check_render_does_output_account_code(self):
        """反向自检：render 确实输出 account_code 键（如果不输出，上面的断言空转）。"""
        import inspect
        source = inspect.getsource(g7.render)
        assert "account_code" in source, "render 应含 account_code 输出"
        assert "resolved_account_code" in source or "accounts.gross" in source, (
            "render 应从 resolve_report_line_accounts 结果取科目码"
        )

    def test_module_level_no_prefix_constants(self):
        """模块级也不得再有这两个常量（Wave 1 已删，防复活）。"""
        assert not hasattr(g7, "_G7_ACCOUNT_PREFIX"), (
            "_G7_ACCOUNT_PREFIX 复活了！科目码由 G7_ACCOUNT_SPEC + 报表映射解析获得"
        )
        assert not hasattr(g7, "_G7_IMPAIRMENT_PREFIX"), (
            "_G7_IMPAIRMENT_PREFIX 复活了！"
        )
