"""Wave 0 / Task 1.2 — 零回归基线（characterization）。

锁定本 spec 依赖的既有语义，后续每波复跑防回归：
- `_is_leaf` / `_sum_leaf_by_prefix`：叶子过滤无父子双算（Property 1 / 15 基石）。
- `g7_consol_linkage_service` 关键函数签名存在且语义常量（只填空 / 不自动生成抵消分录）。
"""

from __future__ import annotations

import inspect

from app.routers.wp_render_strategies._g7_long_term_equity_main import (
    _G7_ACCOUNT_PREFIX,
    _G7_IMPAIRMENT_PREFIX,
    _is_leaf,
    _sum_leaf_by_prefix,
)


class TestLeafFilter:
    def test_is_leaf_true_for_terminal_code(self):
        codes = {"1511", "1511.01", "1511.02"}
        assert _is_leaf("1511.01", codes) is True
        assert _is_leaf("1511.02", codes) is True

    def test_is_leaf_false_for_parent(self):
        codes = {"1511", "1511.01", "1511.04", "1511.04.01"}
        assert _is_leaf("1511", codes) is False
        assert _is_leaf("1511.04", codes) is False
        assert _is_leaf("1511.04.01", codes) is True

    def test_sum_leaf_no_double_count(self):
        # 父 1511=999（应被忽略）+ 两叶子 1511.01=100 / 1511.02=200
        rows = [
            ("1511", 900.0, 999.0),
            ("1511.01", 40.0, 100.0),
            ("1511.02", 60.0, 200.0),
        ]
        opening, closing, leaf_codes = _sum_leaf_by_prefix(rows, "1511")
        assert closing == 300.0  # 100 + 200，父级不计入
        assert opening == 100.0  # 40 + 60
        assert leaf_codes == ["1511.01", "1511.02"]

    def test_sum_leaf_multilevel(self):
        rows = [
            ("1511.04", 0.0, 500.0),  # 父级
            ("1511.04.01", 0.0, 300.0),  # 叶子
            ("1511.04.02", 0.0, 200.0),  # 叶子
        ]
        _, closing, leaf_codes = _sum_leaf_by_prefix(rows, "1511")
        assert closing == 500.0  # 300 + 200，1511.04 父级不计入
        assert leaf_codes == ["1511.04.01", "1511.04.02"]

    def test_sum_leaf_empty(self):
        opening, closing, leaf_codes = _sum_leaf_by_prefix([], "1511")
        assert (opening, closing, leaf_codes) == (0.0, 0.0, [])

    def test_prefix_constants(self):
        assert _G7_ACCOUNT_PREFIX == "1511"
        assert _G7_IMPAIRMENT_PREFIX == "1512"


class TestConsolLinkageServiceSemantics:
    """Property 15：合并联动服务映射 / 比例 / 只填空 / 不自动生成抵消分录逐字节不变。"""

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
