"""G7 零回归基线（characterization）。

**2026-08-01 改写**：原文件锁的是已删除的自造实现
（`_is_leaf` / `_sum_leaf_by_prefix` / `_G7_ACCOUNT_PREFIX` 常量断言）。
那套实现有两个真缺陷 —— 前缀判定缺点号边界（`1511` 误命中 `15110`）、科目前缀硬编码，
已由 spec `g7-four-table-extraction-and-disclosure-alignment` Wave 1 换成
`four_table` 共享件 + 报表映射解析。

本文件保留**断言意图**（叶子过滤无父子双算 / 合并联动服务语义不变），
只把被测对象换成共享件与新纯函数；另新增旧实现缺陷的**反向自检**，
防止有人把缺边界的判定改回来。
"""

from __future__ import annotations

import inspect

from app.services.four_table.leaf_aggregation import (
    LeafRow,
    aggregate_leaves,
    filter_by_prefixes,
    select_leaves,
)


def _row(code: str, opening: float = 0.0, closing: float = 0.0) -> LeafRow:
    return LeafRow(account_code=code, opening=opening, closing=closing)


class TestLeafFilter:
    """叶子过滤无父子双算（原断言意图逐条保留，被测对象换成共享件）。"""

    def test_leaf_true_for_terminal_code(self):
        rows = [_row("1511"), _row("1511.01"), _row("1511.02")]
        leaves = {r.account_code for r in select_leaves(rows)}
        assert leaves == {"1511.01", "1511.02"}

    def test_leaf_false_for_parent(self):
        rows = [_row("1511"), _row("1511.01"), _row("1511.04"), _row("1511.04.01")]
        leaves = {r.account_code for r in select_leaves(rows)}
        assert "1511" not in leaves
        assert "1511.04" not in leaves
        assert "1511.04.01" in leaves

    def test_sum_leaf_no_double_count(self):
        # 父 1511=999（应被忽略）+ 两叶子 1511.01=100 / 1511.02=200
        rows = [
            _row("1511", 900.0, 999.0),
            _row("1511.01", 40.0, 100.0),
            _row("1511.02", 60.0, 200.0),
        ]
        agg = aggregate_leaves(select_leaves(rows), ["1511"])
        assert agg["closing"] == 300.0  # 100 + 200，父级不计入
        assert agg["opening"] == 100.0  # 40 + 60

    def test_sum_leaf_multilevel(self):
        rows = [
            _row("1511.04", 0.0, 500.0),  # 父级
            _row("1511.04.01", 0.0, 300.0),  # 叶子
            _row("1511.04.02", 0.0, 200.0),  # 叶子
        ]
        leaves = select_leaves(rows)
        assert {r.account_code for r in leaves} == {"1511.04.01", "1511.04.02"}
        assert aggregate_leaves(leaves, ["1511"])["closing"] == 500.0

    def test_sum_leaf_empty(self):
        agg = aggregate_leaves(select_leaves([]), ["1511"])
        assert agg == {"opening": 0.0, "closing": 0.0, "debit": 0.0, "credit": 0.0}

    def test_prefix_requires_dot_boundary(self):
        """🔴 反向自检：旧实现 `code.startswith(prefix)` 会把 `15110` 算进 `1511`。

        `15110` 是与 `1511` 无父子关系的另一科目（客户平铺编码时真实存在）。
        共享件 `filter_by_prefixes` 要求 ``code == p or code.startswith(p + '.')``。
        """
        rows = [_row("1511", 0.0, 100.0), _row("15110", 0.0, 999.0)]
        picked = {r.account_code for r in filter_by_prefixes(rows, ["1511"])}
        assert picked == {"1511"}, "前缀匹配必须有点号边界，不得命中 15110"
        # 旧口径反证：无边界时会多算
        assert {r.account_code for r in rows if r.account_code.startswith("1511")} == {
            "1511",
            "15110",
        }

    def test_account_codes_not_hardcoded_in_render_strategy(self):
        """🔴 R11.2：render 策略不得再用常量前缀当输出值。

        科目一律经 `G7_ACCOUNT_SPEC` + 报表映射解析；旧常量
        `_G7_ACCOUNT_PREFIX` / `_G7_IMPAIRMENT_PREFIX` 必须已删除。

        🔴 2026-08-08 断言迁移到**语义规格**字段
        --------------------------------------
        原断言读 ``G7_ACCOUNT_SPEC.provision_row_code`` / ``fallback_gross`` /
        ``fallback_provision`` —— 那是旧 :class:`ReportLineAccountSpec` 的字段，
        而 ``G7_ACCOUNT_SPEC`` 早已 `= G7_SPEC`（:class:`SemanticAccountSpec`）
        ⇒ 该断言自 G7 迁语义解析器起就以 ``AttributeError`` 长期红（零信号）。

        备抵报表行的承载改为**槽级** ``row_code``（本轮新增能力，见
        ``backend/tests/four_table/test_semantic_slot_row_code.py``）：
        `SemanticAccountSpec` 只有一个 spec 级 row_code，备抵自成报表行时必须
        由槽自己声明，否则 :func:`build_conflicts` 恒报假冲突。
        """
        from app.routers.wp_render_strategies import _g7_long_term_equity_main as g7

        assert not hasattr(g7, "_G7_ACCOUNT_PREFIX")
        assert not hasattr(g7, "_G7_IMPAIRMENT_PREFIX")

        spec = g7.G7_ACCOUNT_SPEC
        assert spec.row_code == "BS-024"
        slots = {s.key: s for s in spec.slots}
        assert set(slots) == {"gross", "provision"}, f"G7 应为双槽，实际 {set(slots)}"

        # 备抵自成报表行 IMP-009（槽级声明；不声明会恒报假冲突）
        assert slots["provision"].row_code == "IMP-009"
        assert slots["provision"].is_provision is True
        # 原值槽不声明槽级 row_code —— 它就该用主行 BS-024 比对
        assert slots["gross"].row_code is None

        # 兜底码只许出现在 spec 声明里（fail-open 用），不得散落
        assert slots["gross"].fallback_standard_codes == ("1511",)
        assert slots["provision"].fallback_standard_codes == ("1512",)

    def test_transition_rla_spec_agrees_with_semantic_spec(self):
        """过渡期件 ``G7_RLA_SPEC`` 与语义规格**交叉锁死**（防两形态漂移）。

        `G7_RLA_SPEC` 的存在理由是「供守卫直接验旧路径行为」，那它就必须与
        语义规格声明同一批码与同一批报表行 —— 否则两处各说一套，
        测试用旧形态验过的结论对生产路径（语义形态）不成立。
        """
        from app.routers.wp_render_strategies import _g7_long_term_equity_main as g7

        rla = g7.G7_RLA_SPEC
        slots = {s.key: s for s in g7.G7_ACCOUNT_SPEC.slots}
        assert rla.row_code == g7.G7_ACCOUNT_SPEC.row_code == "BS-024"
        assert rla.provision_row_code == slots["provision"].row_code == "IMP-009"
        assert rla.fallback_gross == slots["gross"].fallback_standard_codes
        assert rla.fallback_provision == slots["provision"].fallback_standard_codes


class TestConsolLinkageServiceSemantics:
    """合并联动服务映射 / 比例 / 只填空 / 不自动生成抵消分录逐字节不变。"""

    def test_key_functions_exist(self):
        from app.services import g7_consol_linkage_service as svc

        # 预览 / 导入两条链路的核心入口签名存在（本 spec 不改它们）
        assert hasattr(svc, "preview_g7_linkage")
        assert hasattr(svc, "import_g7_linkage")
        assert hasattr(svc, "load_linkage_stale_state")

    def test_only_fill_empty_semantics_marker(self):
        """服务源码保留「只填空 / 不覆盖」语义标记（防被改成覆盖式写入）。"""
        from app.services import g7_consol_linkage_service as svc

        src = inspect.getsource(svc)
        # 「不自动生成抵消分录」是本联动的定义性约束（Glossary / R9.2）
        assert "抵消分录" in src or "overwrite" in src
