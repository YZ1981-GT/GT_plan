"""Wave 5 守卫：两份 ``WP()`` 实现的语义一致性登记。

spec: formula-management-runtime-closure Task 13
  (Requirements 5.1, 5.2, 5.3, 5.4 / Property 17)

**本守卫不验证取值正确性**（死链修复归 `prefill-wp-prev-resolution-repair`），
只保证「修一份时另一份不会被忘掉」：

1. 登记表里的实参/数据源/on_missing **与源码实测逐条相符**（交叉锁死）；
2. 两者的**每一处差异都已登记且带理由与归属 spec**，未登记即打红；
3. 任一实现被改动（实参个数变化 / on_missing 变化）→ 本守卫打红，
   逼改动方同步更新登记 —— 这正是 R5.3 要的「打红提醒同步另一份」。

🔴 **Property 17 的判据不是「实参个数一致」**：2026-08-07 实证两者
分别是 3 个与 2 个（design 首版写「同」是错的），按「一致」写会打红且红得没意义。
正确判据 = 「差异已登记」+「登记与源码相符」。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from app.services.formula_wp_semantics import (
    ENGINE_WP_IMPL,
    PREFILL_WP_IMPL,
    REGISTERED_DIFFERENCE_DIMENSIONS,
    WP_IMPLS,
    WP_KNOWN_DIFFERENCES,
    difference_of,
    impl_of,
)

BACKEND = Path(__file__).resolve().parents[1]


def _impl_path(impl: str) -> Path:
    rel, _, _fn = impl.partition("::")
    return BACKEND / rel


def _func_def(impl: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """按 AST 取到函数定义（比正则稳，且能拿到真实实参名）。"""
    rel, _, fn = impl.partition("::")
    tree = ast.parse(_impl_path(impl).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn:
            return node
    raise AssertionError(f"未找到函数定义: {impl}")


def _func_src(impl: str) -> str:
    node = _func_def(impl)
    src = _impl_path(impl).read_text(encoding="utf-8").splitlines()
    end = node.end_lineno or node.lineno
    return "\n".join(src[node.lineno - 1 : end])


class TestExtractorSelfCheck:
    def test_both_impl_files_exist(self) -> None:
        for impl in (PREFILL_WP_IMPL, ENGINE_WP_IMPL):
            p = _impl_path(impl)
            assert p.exists(), f"路径错会让整份守卫零断言执行: {p}"

    def test_ast_extractor_finds_both(self) -> None:
        for impl in (PREFILL_WP_IMPL, ENGINE_WP_IMPL):
            node = _func_def(impl)
            assert node.args.args, f"{impl} 实参抽取失败"

    def test_extractor_raises_on_missing_function(self) -> None:
        try:
            _func_def("app/services/formula_engine.py::__no_such_function__")
        except AssertionError:
            return
        raise AssertionError("提取器对不存在的函数必须抛错，否则断言会空转")


class TestRegistryMatchesSource:
    """登记表 ↔ 源码交叉锁死（改实现不改登记即打红）。"""

    def test_prefill_impl_takes_three_formula_args(self) -> None:
        """prefill 侧 resolver 签名是 ``(db, project_id, year, args)``，

        公式实参在 ``args`` 列表里按位置解包 —— 判据落在解包语句上。
        """
        spec = impl_of(PREFILL_WP_IMPL)
        assert spec is not None
        assert spec.positional_args == ("wp_code", "sheet_name", "cell_ref")
        src = _func_src(PREFILL_WP_IMPL)
        # 三元解包 + 长度门槛，两者都在才算「真的取三个实参」
        assert re.search(
            r"wp_code,\s*sheet_name,\s*cell_ref\s*=\s*args\[0\],\s*args\[1\],\s*args\[2\]",
            src,
        ), "prefill 侧实参解包形态变了，登记表需同步"
        assert re.search(r"if\s+len\(args\)\s*<\s*3\s*:", src), (
            "prefill 侧实参个数门槛变了，登记表需同步"
        )

    def test_engine_impl_takes_two_formula_args(self) -> None:
        spec = impl_of(ENGINE_WP_IMPL)
        assert spec is not None
        assert spec.positional_args == ("wp_code", "col_name")
        src = _func_src(ENGINE_WP_IMPL)
        assert "str_args[0] if str_args else" in src
        assert "str_args[1] if len(str_args) > 1 else" in src
        # 🔴 反向锁死：engine 侧**没有** sheet 维度。哪天有了必须更新登记。
        assert "sheet" not in src.lower(), (
            "engine 侧新增了 sheet 维度 → formula_wp_semantics 登记表必须同步"
        )

    def test_prefill_reads_checklist_responses_via_anchor_map(self) -> None:
        """prefill 侧数据源 = ``checklist_responses`` + 声明式中文锚点映射。

        🔴 **本断言的历史**：2026-08-07 首版判据是「读 ``parsed_data['cells']``」——
        那是死链形态（全库 0 行）。并发 spec ``prefill-wp-prev-resolution-repair``
        修好后本断言按设计打红（R5.3「修一份时另一份不会被忘掉」），登记表已同步。
        现判据锁死**修好后**的形态，并反向禁止回退到 ``cells``。
        """
        spec = impl_of(PREFILL_WP_IMPL)
        assert spec is not None
        assert "checklist_responses" in spec.data_source
        src = _func_src(PREFILL_WP_IMPL)
        # 经声明式锚点映射解析中文 cell_ref，禁字符串启发式
        assert "resolve_anchor(" in src, (
            "prefill 侧不再经 prefill_anchor_map.resolve_anchor 解析锚点 → 登记表需同步"
        )
        assert "read_anchor_value(" in src, (
            "prefill 侧不再经 prefill_anchor_map.read_anchor_value 取值 → 登记表需同步"
        )
        # 🔴 反向锁死：不得回退到死链容器 parsed_data['cells']
        assert 'get("cells"' not in src and "get('cells'" not in src, (
            "prefill 侧回退到 parsed_data['cells']（全库 0 行的死链容器）"
        )

    def test_engine_reads_ctx_wp_data(self) -> None:
        spec = impl_of(ENGINE_WP_IMPL)
        assert spec is not None
        assert "ctx.wp_data" in spec.data_source
        src = _func_src(ENGINE_WP_IMPL)
        assert "ctx.wp_data" in src

    def test_on_missing_returns_match_source(self) -> None:
        prefill_src = _func_src(PREFILL_WP_IMPL)
        engine_src = _func_src(ENGINE_WP_IMPL)
        # prefill：取不到 → None
        assert re.search(r"return\s+None", prefill_src)
        # engine：取不到 → Decimal("0")（默认值形态）
        assert re.search(r'Decimal\(\s*"0"\s*\)', engine_src)
        assert impl_of(PREFILL_WP_IMPL).on_missing.startswith("None")  # type: ignore[union-attr]
        assert impl_of(ENGINE_WP_IMPL).on_missing.startswith("Decimal('0')")  # type: ignore[union-attr]

    def test_each_impl_measurement_is_dated(self) -> None:
        for spec in WP_IMPLS:
            assert "2026-" in spec.measured, f"{spec.impl} 实测状态缺日期"
            assert len(spec.measured) >= 30, f"{spec.impl} 实测状态过短（占位）"


class TestKnownDifferencesRegistered:
    """Property 17：每处差异都要登记，且带理由与归属 spec。"""

    def test_all_three_dimensions_registered(self) -> None:
        assert REGISTERED_DIFFERENCE_DIMENSIONS == {
            "positional_arg_count",
            "on_missing_return",
            "data_source",
        }
        assert len(WP_KNOWN_DIFFERENCES) == 3

    def test_each_difference_has_reason_and_owner(self) -> None:
        for diff in WP_KNOWN_DIFFERENCES:
            assert len(diff.detail) >= 20, f"{diff.dimension} detail 过短"
            assert len(diff.reason) >= 20, f"{diff.dimension} 未写「为什么不在本 spec 修」"
            assert diff.owner_spec, f"{diff.dimension} 未登记归属 spec"

    def test_owner_spec_directory_exists(self) -> None:
        """归属 spec 必须真实存在（防写一个虚构的 spec 名把责任推空）。"""
        specs_dir = BACKEND.parent / ".kiro" / "specs"
        for diff in WP_KNOWN_DIFFERENCES:
            owner = specs_dir / diff.owner_spec
            archived = specs_dir / "_archive"
            exists = owner.exists() or (
                archived.exists()
                and any(p.name == diff.owner_spec for p in archived.rglob("*") if p.is_dir())
            )
            assert exists, f"归属 spec 不存在: {diff.owner_spec}"

    def test_arg_count_difference_matches_reality(self) -> None:
        """差异登记与实测一致：3 vs 2（design 首版写「同」是错的）。"""
        prefill = impl_of(PREFILL_WP_IMPL)
        engine = impl_of(ENGINE_WP_IMPL)
        assert prefill is not None and engine is not None
        assert len(prefill.positional_args) != len(engine.positional_args), (
            "两者实参个数若真的相同了，positional_arg_count 差异应从登记表移出"
        )
        diff = difference_of("positional_arg_count")
        assert diff is not None
        assert "3" in diff.detail and "2" in diff.detail

    def test_unregistered_dimension_returns_none(self) -> None:
        assert difference_of("__not_a_dimension__") is None

    def test_this_spec_does_not_modify_impls(self) -> None:
        """R5.4：本 spec 只建守卫，两份实现的取值逻辑不得由本 spec 改动。

        判据 = 两个函数体里**不得**出现本 spec 的模块名
        （出现即说明有人把语义登记塞进了实现，属双真源）。
        """
        for impl in (PREFILL_WP_IMPL, ENGINE_WP_IMPL):
            src = _func_src(impl)
            assert "formula_wp_semantics" not in src, (
                f"{impl} 引用了语义登记模块 → 登记与实现互相依赖，形成双真源"
            )
