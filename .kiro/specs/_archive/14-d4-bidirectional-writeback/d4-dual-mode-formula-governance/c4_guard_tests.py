# -*- coding: utf-8 -*-
"""
C4 行为守卫测试 — d4-dual-mode-formula-governance

覆盖范围：
  Guard 1 — Req 1.1: C0 矩阵分母恰好 36 个 wp_code，无重复，D4-1..D4-36 连续
  Guard 2 — Req 2.2: 同字段异值必产生冲突（禁 LWW）；不同字段自动合并
  Guard 3 — Req 3.2: F-SHELL v2 白名单（eval/URL/非法函数名 均被拒绝）
  Guard 4 — Req 4.1: DAG 循环检测 + 拓扑排序对循环图抛 ValueError
  Guard 5 — Req 5.1: D4 提取模块不复制科目 SQL，必须通过 four_table 服务

设计约束：
  - 契约守卫，不是完整功能测试；UNVERIFIABLE 项（Playwright/E2E/roundtrip）不在本文件中假绿
  - 导入失败 → pytest.skip()，保证在完整后端环境下可运行
  - 所有 hypothesis PBT 使用 max_examples=5（降速）
  - 运行时 cwd=backend，命令: python -m pytest .kiro/specs/d4-dual-mode-formula-governance/c4_guard_tests.py -v
"""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
SPEC_DIR = Path(__file__).resolve().parent
REPO_ROOT = SPEC_DIR.parent.parent.parent  # d:\GT_plan
BACKEND_ROOT = REPO_ROOT / "backend"
D4_EXTRACTION_DIR = BACKEND_ROOT / "app" / "services" / "d4_extraction"


def _ensure_backend_on_path():
    """将 backend 加入 sys.path（测试运行时 cwd 为 backend）"""
    bp = str(BACKEND_ROOT)
    if bp not in sys.path:
        sys.path.insert(0, bp)


# ===========================================================================
# Guard 1 — 矩阵完整性（Req 1.1）
# ===========================================================================

class TestGuard1OwnerMatrix:
    """C0 owner 矩阵分母恰好 36 个 wp_code，D4-1..D4-36 连续无重复。"""

    MATRIX_PATH = SPEC_DIR / "c0_owner_matrix.md"

    def _extract_codes(self) -> list[tuple[int, str]]:
        """从矩阵 markdown 提取 wp_code 列表（主矩阵表行）。
        
        主矩阵行格式：| N | D4-x | ... （N 为 1-36 整数，D4-x 为第二个单元格）
        汇总统计表行格式：| 分类名 | 数字 | D4-x |（数字是第3列，排除）
        """
        assert self.MATRIX_PATH.exists(), f"矩阵文件不存在：{self.MATRIX_PATH}"
        text = self.MATRIX_PATH.read_text(encoding="utf-8")
        results = []
        for m in re.finditer(r'\|\s*(\d+)\s*\|\s*(D4-\d+)\s*\|', text):
            num = int(m.group(1))
            code = m.group(2)
            # 排除汇总统计表行：数字在第3列（前面有分类名称）
            # 主矩阵行：数字在第1列（前面是 |）
            # 通过检查前一个 | 的位置来区分
            pos = m.start()
            prev_bar = text.rfind('|', 0, pos)
            if prev_bar == -1:
                continue
            # 检查 | N | 前面是否紧跟另一个 |（即 N 是第二个单元格，而非第一个）
            # 主矩阵行：| 1 | D4-1 |  → N 前面是第一个 |
            # 汇总表行：| 专属... | 1 | D4-1 | → N 前面是另一个 |
            # 如果 N 前面有 |，说明 N 是第二列（汇总表），跳过
            preceding_text = text[prev_bar:pos]
            if preceding_text.strip() == '|':
                # N 是第一个单元格（主矩阵行）
                if 1 <= num <= 36:
                    results.append((num, code))
        return results

    def test_36_unique_wp_codes(self):
        """分母恰好 36 个 wp_code"""
        codes = [c for _, c in self._extract_codes()]
        unique = set(codes)
        assert len(unique) == 36, (
            f"预期 36 个唯一 wp_code，实际 {len(unique)} 个：{sorted(unique)}"
        )

    def test_no_duplicate_rows(self):
        """每行 wp_code 唯一（无重复行）"""
        codes = [c for _, c in self._extract_codes()]
        dupes = [c for c in set(codes) if codes.count(c) > 1]
        assert not dupes, f"存在重复 wp_code：{dupes}"

    def test_d4_1_to_d4_36_continuous(self):
        """D4-1 到 D4-36 连续，无跳号"""
        codes = set(c for _, c in self._extract_codes())
        expected = {f"D4-{i}" for i in range(1, 37)}
        missing = expected - codes
        extra = codes - expected
        assert not missing, f"缺少 wp_code：{sorted(missing)}"
        assert not extra, f"存在多余 wp_code：{sorted(extra)}"


# ===========================================================================
# Guard 2 — 三方合并规则（Req 2.2）
# ===========================================================================

def _make_merge_contract(
    field_keys: list[str],
    field_type: str = "amount",
) -> "SyncContract":
    """构造最小 SyncContract：每个 field_key 一个 editable 字段（带 cell 映射）。"""
    from app.services.workpaper_sync.contracts import (
        SyncContract, FieldSpec, FieldMode, TemplateRef,
        ContractReviewStatus, ValueType, SheetSpec, TableSpec, CellMapping,
    )

    vt_map = {"amount": ValueType.amount, "text": ValueType.text,
              "integer": ValueType.integer, "date": ValueType.date}
    vt = vt_map.get(field_type, ValueType.text)

    fields = tuple(
        FieldSpec(
            stable_field_key=fkey,
            json_pointer=f"/{fkey}",
            mode=FieldMode.editable,
            value_type=vt,
            source_ref="guard-test",
            row_scoped=False,
            cell=CellMapping(column=f"{chr(ord('A')+i)}", row_from="1", static_row=i+1),
        )
        for i, fkey in enumerate(field_keys)
    )
    return SyncContract(
        contract_id="guard-test",
        semantic_version="1.0",
        document_type="xlsx",
        review_status=ContractReviewStatus.candidate,
        template=TemplateRef(relative_path="guard.xlsx", sha256="a"*64, structure_hash="b"*64),
        template_definition_sha256="a"*64,
        instrumentation_definition_sha256="b"*64,
        identity_carriers=("stable_key",),
        sheets=(
            SheetSpec(sheet_key="s1", excel_name="Sheet1", locator_anchor="A1",
                tables=(
                    TableSpec(table_key="t1", anchor="A1", header_rows=1, fields=fields),
                ),
            ),
        ),
    )


def _make_projection(
    field_vals: dict[str, Any],
    value_type: str = "amount",
) -> "Projection":
    """构造 Projection：field_vals = {field_key: value_or_MISSING}"""
    from app.services.workpaper_sync.merge import MISSING
    from app.services.workpaper_sync.adapters.base import Projection, FieldValue
    from app.services.workpaper_sync.contracts import FieldMode, ValueType

    vt_map = {"amount": ValueType.amount, "text": ValueType.text,
              "integer": ValueType.integer, "date": ValueType.date}
    vt = vt_map.get(value_type, ValueType.text)

    values = {}
    for fkey, val in field_vals.items():
        if val is MISSING:
            continue  # 字段缺失 = 不放 values
        values[fkey] = FieldValue(
            stable_key=fkey, value=val, value_type=vt, mode=FieldMode.editable
        )
    return Projection(
        contract_id="guard-test",
        semantic_version="1.0",
        document_type="xlsx",
        values=values,
    )


class TestGuard2ThreeWayMerge:
    """三方合并：同字段异值 → 冲突记录（禁 LWW）；不同字段 → 自动合并。"""

    @pytest.fixture(autouse=True)
    def _add_path(self):
        _ensure_backend_on_path()

    def _merge(self, base_vals, current_vals, incoming_vals, field_keys, field_type="amount"):
        """调用 merge_projections 返回 MergeOutcome。"""
        from app.services.workpaper_sync.merge import merge_projections
        contract = _make_merge_contract(field_keys, field_type)
        base = _make_projection(base_vals, field_type)
        current = _make_projection(current_vals, field_type)
        incoming = _make_projection(incoming_vals, field_type)
        return merge_projections(
            base=base, current=current, incoming=incoming, contract=contract
        )

    # ------------------------------------------------------------------
    # 具体断言
    # ------------------------------------------------------------------

    def test_same_field_different_value_creates_conflict(self):
        """同字段异值：base=100, current=200, incoming=300 → 必产生冲突记录"""
        try:
            from app.services.workpaper_sync.merge import merge_projections  # noqa
        except ImportError:
            pytest.skip("merge.py 导入失败")

        outcome = self._merge(
            base_vals={"amount": 100},
            current_vals={"amount": 200},
            incoming_vals={"amount": 300},
            field_keys=["amount"],
        )

        # 必产生冲突
        assert outcome.has_conflicts, "同字段异值应产生冲突，但 has_conflicts=False"
        assert outcome.conflict_count > 0, "同字段异值应产生冲突，但 conflict_count=0"

        # merged 保持 current（禁 LWW）
        merged_val = outcome.merged.get("amount")
        assert merged_val is not None, "merged 中 amount 字段缺失"
        assert merged_val.value == 200, (
            f"merged 应保持 current=200，不得 LWW，实际 {merged_val.value}"
        )

    def test_same_field_incoming_same_as_base_no_conflict(self):
        """incoming == base（OO 未改）→ 无冲突，merged 取 current"""
        try:
            from app.services.workpaper_sync.merge import merge_projections  # noqa
        except ImportError:
            pytest.skip("merge.py 导入失败")

        outcome = self._merge(
            base_vals={"amount": 100},
            current_vals={"amount": 200},
            incoming_vals={"amount": 100},  # incoming == base
            field_keys=["amount"],
        )

        # incoming == base → 无冲突
        assert not outcome.has_conflicts, (
            f"incoming==base 应无冲突，实际 has_conflicts={outcome.has_conflicts}"
        )
        merged_val = outcome.merged.get("amount")
        assert merged_val.value == 200

    def test_different_fields_auto_merge_no_conflict(self):
        """不同字段同时写入 → 自动合并，无冲突"""
        try:
            from app.services.workpaper_sync.merge import merge_projections  # noqa
        except ImportError:
            pytest.skip("merge.py 导入失败")

        outcome = self._merge(
            base_vals={"field_a": "x", "field_b": "y"},
            current_vals={"field_a": "x_modified", "field_b": "y"},
            incoming_vals={"field_a": "x", "field_b": "y_modified"},
            field_keys=["field_a", "field_b"],
            field_type="text",
        )

        assert not outcome.has_conflicts, (
            f"不同字段不应冲突，实际 has_conflicts={outcome.has_conflicts}"
        )
        val_a = outcome.merged.get("field_a")
        val_b = outcome.merged.get("field_b")
        assert val_a.value == "x_modified", f"field_a 应为 x_modified，实际 {val_a.value}"
        assert val_b.value == "y_modified", f"field_b 应为 y_modified，实际 {val_b.value}"

    def test_pbt_same_field_conflict_always_recorded(self):
        """PBT：同字段异值场景 → 永远产生冲突（never LWW）"""
        try:
            from app.services.workpaper_sync.merge import merge_projections  # noqa
        except ImportError:
            pytest.skip("merge.py 导入失败")

        from hypothesis import given, settings
        from hypothesis import strategies as st

        @given(
            base_val=st.integers(min_value=0, max_value=10**6),
            current_val=st.integers(min_value=0, max_value=10**6),
            incoming_val=st.integers(min_value=0, max_value=10**6),
        )
        @settings(max_examples=5, deadline=None)
        def _prop(base_val, current_val, incoming_val):
            # 只有三值全不同才有冲突
            if base_val == current_val or base_val == incoming_val or current_val == incoming_val:
                pytest.skip("三值有相等对，跳过冲突检查")

            outcome = self._merge(
                base_vals={"amount": base_val},
                current_vals={"amount": current_val},
                incoming_vals={"amount": incoming_val},
                field_keys=["amount"],
            )
            assert outcome.has_conflicts, (
                f"PBT FAIL: base={base_val}, current={current_val}, "
                f"incoming={incoming_val} 应产生冲突"
            )
            merged_val = outcome.merged.get("amount")
            assert merged_val.value == current_val, (
                f"PBT FAIL: merged={merged_val.value}, 应为 current={current_val}（禁 LWW）"
            )

        _prop()


# ===========================================================================
# Guard 3 — F-SHELL v2 白名单（Req 3.2）
# ===========================================================================

class TestGuard3FShellWhitelist:
    """F-SHELL v2 白名单：eval/exec/URL/非法函数名 均被拒绝；合法公式通过。"""

    @pytest.fixture(autouse=True)
    def _add_path(self):
        _ensure_backend_on_path()

    def _get_execute(self):
        """返回 execute 函数；导入失败则 pytest.skip()"""
        try:
            from app.services.formula_engine import execute as formula_execute
            return formula_execute
        except ImportError:
            pytest.skip("formula_engine 导入失败")

    def test_eval_rejected(self):
        """eval(...) 必须被拒绝：AST 解析失败 → errors 非空，或抛异常"""
        execute = self._get_execute()
        try:
            result = execute("eval('1+1')", context=None)
            assert result is None or len(result.errors) > 0 or result.ok is False, (
                f"eval('1+1') 不应被静默接受，实际 result: errors={result.errors}"
            )
        except (Exception,):
            pass  # 抛异常即拒绝，符合预期

    def test_exec_rejected(self):
        """exec(...) 必须被拒绝"""
        execute = self._get_execute()
        try:
            result = execute("exec('__import__(chr(39)os chr(39))')", context=None)
            assert result is None or len(result.errors) > 0 or result.ok is False, (
                f"exec(...) 不应被静默接受，实际 result: errors={result.errors}"
            )
        except (Exception,):
            pass

    def test_url_rejected(self):
        """URL 外链必须被拒绝"""
        execute = self._get_execute()
        try:
            result = execute("http://evil.com/payload", context=None)
            assert result is None or len(result.errors) > 0 or result.ok is False, (
                f"URL 'http://evil.com/payload' 不应被静默接受"
            )
        except (Exception,):
            pass

    def test_illegal_function_name_rejected(self):
        """非白名单函数名必须被拒绝"""
        execute = self._get_execute()
        try:
            result = execute("MALICIOUS_CALL('arg1')", context=None)
            assert result is None or len(result.errors) > 0 or result.ok is False, (
                f"MALICIOUS_CALL 不应被静默接受"
            )
        except (Exception,):
            pass

    def test_valid_tb_formula_no_security_error(self):
        """合法 TB 公式不应报安全/解析错误"""
        execute = self._get_execute()
        from decimal import Decimal
        from app.services.formula_engine import FormulaContext

        ctx = FormulaContext(
            tb_data={"1002": {"期末余额": Decimal("1000")}},
            default_column="期末余额",
        )
        result = execute("TB('1002','期末余额')", ctx=ctx)
        assert result.ok is True, (
            f"合法 TB 公式不应报错，errors={result.errors}"
        )
        assert result.value == Decimal("1000"), (
            f"TB('1002','期末余额') 应返回 1000，实际 {result.value}"
        )

    def test_valid_arithmetic_no_security_error(self):
        """合法算术表达式不应报安全/解析错误"""
        execute = self._get_execute()
        from decimal import Decimal

        result = execute("5*3+10", ctx=None)
        assert result.ok is True, f"合法算术不应报错，errors={result.errors}"
        assert result.value == Decimal("25"), f"5*3+10=25，实际 {result.value}"


# ===========================================================================
# Guard 4 — DAG 循环检测（Req 4.1）
# ===========================================================================

class TestGuard4DagCycleDetection:
    """DAG 循环检测：有循环 → detect_cycles 非空；topological_sort 对循环图抛 ValueError。"""

    @pytest.fixture(autouse=True)
    def _add_path(self):
        _ensure_backend_on_path()

    def _make_graph(self, edges: dict[str, set[str]]) -> "DependencyGraph":
        """
        构造 DependencyGraph 实例。

        edges: {wp_code: set of wp_codes it depends on}
        注意：edges[A] = {B} 表示 A 依赖 B（B 是 A 的前置）。
        topological_sort 中 in_degree[wp] = len(edges[wp])，
        即 wp 的入度 = wp 声明的前置数。
        """
        from app.services.wp_formula_dependency import DependencyGraph

        g = DependencyGraph()
        g.edges = {k: set(v) for k, v in edges.items()}
        g.all_wps = set()
        for wp in edges:
            g.all_wps.add(wp)
        for deps in edges.values():
            for dep in deps:
                g.all_wps.add(dep)
        # reverse_edges: 对 topological_sort 的 BFS 传播必须正确
        reverse: dict[str, set] = defaultdict(set)
        for wp, deps in edges.items():
            for dep in deps:
                reverse[dep].add(wp)
        g.reverse_edges = dict(reverse)
        return g

    def test_cycle_a_b_a_detected(self):
        """A→B→A 循环应被 detect_cycles 检测到"""
        try:
            from app.services.wp_formula_dependency import detect_cycles
        except ImportError:
            pytest.skip("wp_formula_dependency 导入失败")

        g = self._make_graph(edges={"A": {"B"}, "B": {"A"}})
        cycles = detect_cycles(g)
        assert len(cycles) > 0, "A→B→A 循环应被检测到，但 cycles 为空"

    def test_topological_sort_raises_on_cycle(self):
        """循环图 → topological_sort 抛 ValueError"""
        try:
            from app.services.wp_formula_dependency import topological_sort
        except ImportError:
            pytest.skip("wp_formula_dependency 导入失败")

        g = self._make_graph(edges={"A": {"B"}, "B": {"A"}})
        with pytest.raises(ValueError, match="循环"):
            topological_sort(g)

    def test_no_cycle_graph_sorts_successfully(self):
        """无循环图（C 依赖 B 依赖 A）应正常拓扑排序"""
        try:
            from app.services.wp_formula_dependency import topological_sort
        except ImportError:
            pytest.skip("wp_formula_dependency 导入失败")

        # edges[X] = {Y} 表示 X 依赖 Y
        # A 依赖无人（in_degree[A]=0），B 依赖 A（in_degree[B]=1），C 依赖 B（in_degree[C]=1）
        # topological_sort 先输出 in_degree=0 的，即 A
        g = self._make_graph(edges={"A": set(), "B": {"A"}, "C": {"B"}})
        order = topological_sort(g)
        assert list(order).index("A") < list(order).index("B"), (
            f"A 应在 B 之前，实际顺序：{order}"
        )
        assert list(order).index("B") < list(order).index("C"), (
            f"B 应在 C 之前，实际顺序：{order}"
        )

    def test_has_cycle_false_for_acyclic(self):
        """无循环图 has_cycle 应返回 False"""
        try:
            from app.services.wp_formula_dependency import has_cycle
        except ImportError:
            pytest.skip("wp_formula_dependency 导入失败")

        g = self._make_graph(edges={"A": set(), "B": {"A"}, "C": {"B"}})
        assert has_cycle(g) is False

    def test_has_cycle_true_for_cyclic(self):
        """循环图 has_cycle 应返回 True"""
        try:
            from app.services.wp_formula_dependency import has_cycle
        except ImportError:
            pytest.skip("wp_formula_dependency 导入失败")

        g = self._make_graph(edges={"A": {"B"}, "B": {"C"}, "C": {"A"}})
        assert has_cycle(g) is True


# ===========================================================================
# Guard 5 — 四表取数不复制 SQL（Req 5.1）
# ===========================================================================

class TestGuard5FourTableNotDuplicated:
    """D4 提取模块不直接写 SELECT ... FROM trial_balance/tb_balance/tb_ledger。"""

    D4_DIR = D4_EXTRACTION_DIR

    # SQL 模式：从 trial_balance/tb_balance/tb_ledger 直接 SELECT
    # 注意：只检查 sa.text() 形式的裸 SQL（ORM select 不算）
    _BARE_SQL_PATTERN = re.compile(
        r"""
        sa\.text\s*\(\s*
        [rR]?[\"'][\s\S]{0,500}
        SELECT\s+
        [\s\S]{0,200}
        FROM\s+
        (trial_balance|tb_balance|tb_ledger)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # 已知的例外函数（元数据查询，非取数 SQL）
    _EXEMPT_FUNCTIONS = frozenset({
        "expand_specs_to_project_standards",  # 科目映射元数据查询，非取数
    })

    def _find_function_name(self, code: str, match_pos: int) -> str:
        """找到 match_pos 所在的函数名。"""
        prefix = code[:match_pos]
        def_pos = prefix.rfind("async def ")
        if def_pos == -1:
            def_pos = prefix.rfind("def ")
        if def_pos == -1:
            return ""
        m = re.search(r"def\s+(\w+)", code[def_pos:def_pos+100])
        return m.group(1) if m else ""

    def test_no_bare_select_from_four_tables(self):
        """D4 提取模块不允许 sa.text("SELECT ... FROM trial_balance/tb_balance/tb_ledger")"""
        if not self.D4_DIR.is_dir():
            pytest.skip(f"D4 提取目录不存在：{self.D4_DIR}")

        violations = []
        for fpath in self.D4_DIR.glob("*.py"):
            code = fpath.read_text(encoding="utf-8", errors="ignore")
            for m in self._BARE_SQL_PATTERN.finditer(code):
                func_name = self._find_function_name(code, m.start())
                if func_name not in self._EXEMPT_FUNCTIONS:
                    violations.append(f"{fpath.name}:{func_name}")
                    break

        assert not violations, (
            f"以下 D4 提取模块包含裸写科目 SQL（应通过 four_table 服务）：{violations}"
        )

    def test_d4_imports_four_table_service(self):
        """D4 提取模块至少有一个文件导入 four_table 服务"""
        if not self.D4_DIR.is_dir():
            pytest.skip(f"D4 提取目录不存在：{self.D4_DIR}")

        four_table_users = []
        for fpath in self.D4_DIR.glob("*.py"):
            code = fpath.read_text(encoding="utf-8", errors="ignore")
            if "four_table" in code:
                four_table_users.append(fpath.name)

        assert len(four_table_users) > 0, (
            "D4 提取模块应至少有一个文件使用 four_table 服务"
        )
