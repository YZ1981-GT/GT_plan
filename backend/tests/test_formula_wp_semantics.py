"""Wave 5 守卫：``WP()`` 取数路径的语义一致性登记（``formula_wp_semantics``）。

spec: formula-management-runtime-closure Task 13（Requirements 5.1–5.4 / Property 17）；
formula-fetch-followup-defect-closure 6.5 按收敛后的现状改写。

1. 登记表的实参 / 数据源 / 取不到时的结果与源码相符（AST 交叉锁死，注释 / docstring 不算）；
2. 每处差异都已登记且带理由与归属 spec，未登记即打红；
3. 端到端：预填路径三参 WP 经「预载 → L1」得到锚点值、同一底稿两张表的同名锚点互不覆盖、未对齐报错不代 0。

🔴 改写原因：原文件以 ``prefill_engine._resolve_wp_formula`` 为一侧，该函数自 formula-execution-path-convergence 起已无
调用方、``2638b32fd`` 删除，本守卫 5 例红了却没人处理 —— 恰在那段时间预填改走 L1 ``_handle_wp``，三参的第三参被静默
忽略、已对齐锚点恒为 0。「修一份时另一份不会被忘掉」的设计目的正是在它红着的时候失效的，故第 3 组改为行为断言。
"""
from __future__ import annotations

import ast
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.formula_wp_semantics import (
    ENGINE_WP_IMPL,
    EXECUTOR_WP_IMPL,
    PREFILL_WP_IMPL,
    REGISTERED_DIFFERENCE_DIMENSIONS,
    WP_IMPLS,
    WP_KNOWN_DIFFERENCES,
    difference_of,
    impl_of,
)

BACKEND = Path(__file__).resolve().parents[1]
_IMPLS = (PREFILL_WP_IMPL, ENGINE_WP_IMPL, EXECUTOR_WP_IMPL)


def _impl_path(impl: str) -> Path:
    return BACKEND / impl.partition("::")[0]


def _func_def(impl: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """按 AST 取函数定义；``类名.方法名`` 只在该类里找（formula_engine 里有好几个 ``execute``）。"""
    _rel, _, qual = impl.partition("::")
    cls_name, _, fn = qual.rpartition(".")
    tree = ast.parse(_impl_path(impl).read_text(encoding="utf-8"))
    scopes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name] if cls_name else [tree]
    for scope in scopes:
        for node in (scope.body if cls_name else ast.walk(scope)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn:
                return node
    raise AssertionError(f"未找到函数定义: {impl}")


def _code(impl: str) -> str:
    """函数体代码（AST 反解析：注释与 docstring 都不在里面）。"""
    node = _func_def(impl)
    body = node.body[1:] if node.body and isinstance(node.body[0], ast.Expr) and isinstance(
        getattr(node.body[0], "value", None), ast.Constant) else node.body
    return "\n".join(ast.unparse(stmt) for stmt in body)


def _called_names(impl: str) -> set[str]:
    out = set()
    for node in ast.walk(_func_def(impl)):
        if isinstance(node, ast.Call):
            out.add(getattr(node.func, "id", None) or getattr(node.func, "attr", ""))
    return out


class TestExtractorSelfCheck:
    def test_impl_files_exist(self) -> None:
        for impl in _IMPLS:
            assert _impl_path(impl).exists(), f"路径错会让整份守卫零断言执行: {impl}"

    def test_ast_extractor_finds_all(self) -> None:
        for impl in _IMPLS:
            assert _func_def(impl).args.args, f"{impl} 实参抽取失败"

    def test_method_extractor_picks_the_class_method(self) -> None:
        """``WPExecutor.execute`` 不能误取到模块级 ``execute``（L1 入口）或别的类的同名方法。"""
        code = _code(EXECUTOR_WP_IMPL)
        assert "parsed_data" in code and "_execute_ast" not in code

    def test_extractor_raises_on_missing_function(self) -> None:
        with pytest.raises(AssertionError):
            _func_def("app/services/formula_engine.py::__no_such_function__")

    def test_code_view_drops_docstring(self) -> None:
        """反向自检：函数体视图不含 docstring（否则说明文字会骗过下面的「有 / 没有」断言）。"""
        assert "三参见下" not in _code(ENGINE_WP_IMPL)


class TestRegistryMatchesSource:
    """登记表 ↔ 源码交叉锁死（改实现不改登记即打红）。"""

    def test_prefill_loader_takes_three_formula_args(self) -> None:
        assert impl_of(PREFILL_WP_IMPL).positional_args == ("wp_code", "sheet_name", "cell_ref")
        code = _code(PREFILL_WP_IMPL)
        for part in ("ref_tuple[0]", "ref_tuple[1]", "ref_tuple[2]"):
            assert part in code, f"预填取数不再按三元组解包（缺 {part}），登记表需同步"

    def test_prefill_loader_reads_checklist_responses_via_anchor_map(self) -> None:
        assert "checklist_responses" in impl_of(PREFILL_WP_IMPL).data_source
        names = _called_names(PREFILL_WP_IMPL)
        assert {"resolve_anchor", "read_anchor_value"} <= names, "预填不再经声明式锚点映射取值 → 登记表需同步"
        assert "'cells'" not in _code(PREFILL_WP_IMPL), "预填回退到 parsed_data['cells']（全库 0 行的死链容器）"

    def test_loader_and_engine_share_the_three_arg_key(self) -> None:
        """三参键写法两侧一致：都是「表.strip()!锚点.strip()」（行为证明见 TestThreeArgEndToEnd）。"""
        assert "!{cell.strip()}" in _code(PREFILL_WP_IMPL) and "{sheet.strip()}!" in _code(PREFILL_WP_IMPL)
        assert "{str_args[1].strip()}!{str_args[2].strip()}" in _code(ENGINE_WP_IMPL)

    def test_engine_reads_ctx_wp_data_and_raises_on_missing_three_arg(self) -> None:
        code = _code(ENGINE_WP_IMPL)
        assert "ctx.wp_data" in code and "len(str_args) > 2" in code
        assert "raise FormulaColumnError" in code, "三参取不到不再报错 → 登记表 on_missing 需同步"
        assert "Decimal('0')" in code, "两参取不到不再返 0 → 登记表 on_missing 需同步"

    def test_executor_reads_parsed_data_and_returns_zero(self) -> None:
        code = _code(EXECUTOR_WP_IMPL)
        assert "parsed_data" in code and "D('0')" in code
        assert impl_of(EXECUTOR_WP_IMPL).on_missing.startswith("Decimal('0')")

    def test_on_missing_registry_matches(self) -> None:
        assert "报错" in impl_of(PREFILL_WP_IMPL).on_missing
        assert impl_of(ENGINE_WP_IMPL).on_missing.startswith("三参报错")

    def test_each_impl_measurement_is_dated(self) -> None:
        for spec in WP_IMPLS:
            assert "2026-" in spec.measured, f"{spec.impl} 实测状态缺日期"
            assert len(spec.measured) >= 30, f"{spec.impl} 实测状态过短（占位）"


# ---------------------------------------------------------------------------
# 端到端：预填路径三参 WP「预载 → L1」
# ---------------------------------------------------------------------------

_PID = uuid.UUID("dddd0000-0000-4000-8000-000000000001")
#: 锚点映射里 D4 两张明细表都有「全年收入合计」、D6 两张都有「期末合计」（同一底稿、不同 item_id）
_D4_MAIN = ("D4", "主营业务收入明细表D4-2", "全年收入合计")
_D4_OTHER = ("D4", "其他业务收入明细表D4-3", "全年收入合计")
_UNALIGNED = ("D1", "原值明细表（按类别）D1-2", "合计-期末未审数")


def _wp(args: tuple[str, str, str]) -> str:
    return "WP('{}','{}','{}')".format(*args)


@pytest_asyncio.fixture
async def db(monkeypatch) -> AsyncSession:
    """取值 SQL（PG 专用写法，真库连库测试在 test_prefill_wp_prev_resolution）替换成按 item_id 给值；
    锚点解析 / 预载 / L1 都是真实现。"""
    from app.services import prefill_anchor_map as pam
    from app.services.prefill_anchor_map import AnchorReadResult, AnchorReadStatus

    values = {"D4-2-rows": Decimal("1000.50"), "D4-3-rows": Decimal("20.25"), "D2-detail-rows": None}

    async def _fake_read(_db, _pid, _wp_code, spec):
        value = values.get(spec.item_id)
        return AnchorReadResult(AnchorReadStatus.HIT if value is not None else AnchorReadStatus.NO_ITEM, value)

    monkeypatch.setattr(pam, "read_anchor_value", _fake_read)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


class TestThreeArgEndToEnd:
    @pytest.mark.asyncio
    async def test_preload_and_l1_return_anchor_value(self, db) -> None:
        """同一批预载里两张表的同名锚点各取各的（原先按锚点存值会互相覆盖，L1 又按表名取 ⇒ 两格都是 0）。"""
        from app.services.formula_engine import execute
        from app.services.formula_preloader import preload

        formulas = [_wp(_D4_MAIN), _wp(_D4_OTHER)]
        ctx = await preload(db, _PID, 2025, formulas)
        main, other = (execute(f, ctx) for f in formulas)
        assert main.ok and main.value == Decimal("1000.50"), (main.value, main.errors)
        assert other.ok and other.value == Decimal("20.25"), (other.value, other.errors)

    @pytest.mark.asyncio
    async def test_user_formula_preview_entry(self, db) -> None:
        """用户公式预览入口（wp_user_formulas 只收三参 WP）同一结果。"""
        from app.services.prefill_engine import resolve_extended_formula

        assert await resolve_extended_formula(db, _PID, 2025, "WP", "'{}','{}','{}'".format(*_D4_MAIN)) == Decimal(
            "1000.50")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("args", [_UNALIGNED, ("D2", "明细表D2-2", "期末合计")])
    async def test_unaligned_or_empty_anchor_is_an_error_not_zero(self, db, args) -> None:
        """未对齐锚点 / 底稿未录入 ⇒ 报错、该格不写（不是 0）。"""
        from app.services.formula_engine import execute
        from app.services.formula_preloader import preload
        from app.services.prefill_engine import resolve_extended_formula

        result = execute(_wp(args), await preload(db, _PID, 2025, [_wp(args)]))
        assert not result.ok and "取不到数" in result.errors[0], (result.value, result.errors)
        assert await resolve_extended_formula(db, _PID, 2025, "WP", "'{}','{}','{}'".format(*args)) is None

    def test_two_arg_semantics_unchanged(self) -> None:
        """两参（报表 / 自定义公式路径，WPExecutor 预载）不变：按列名取，缺数 0（登记为已知差异）。"""
        from app.services.formula_engine import FormulaContext, execute

        ctx = FormulaContext(wp_data={"D2": {"审定数": Decimal("5")}})
        assert execute("WP('D2','审定数')", ctx).value == Decimal("5")
        missing = execute("WP('D2','期末余额')", ctx)
        assert missing.ok and missing.value == Decimal("0")


class TestKnownDifferencesRegistered:
    """Property 17：每处差异都要登记，且带理由与归属 spec。"""

    def test_all_three_dimensions_registered(self) -> None:
        assert REGISTERED_DIFFERENCE_DIMENSIONS == {"positional_arg_count", "on_missing_return", "data_source"}
        assert len(WP_KNOWN_DIFFERENCES) == 3

    def test_each_difference_has_reason_and_owner(self) -> None:
        for diff in WP_KNOWN_DIFFERENCES:
            assert len(diff.detail) >= 20, f"{diff.dimension} detail 过短"
            assert len(diff.reason) >= 20, f"{diff.dimension} 未写「为什么不在这里统一」"
            assert diff.owner_spec, f"{diff.dimension} 未登记归属 spec"

    def test_owner_spec_directory_exists(self) -> None:
        """归属 spec 必须真实存在（防写一个虚构的 spec 名把责任推空）。"""
        specs_dir = BACKEND.parent / ".kiro" / "specs"
        for diff in WP_KNOWN_DIFFERENCES:
            archived = specs_dir / "_archive"
            exists = (specs_dir / diff.owner_spec).exists() or (
                archived.exists() and any(p.name == diff.owner_spec for p in archived.rglob("*") if p.is_dir()))
            assert exists, f"归属 spec 不存在: {diff.owner_spec}"

    def test_arg_count_difference_matches_reality(self) -> None:
        """预填路径 3 个实参、WPExecutor 2 个：实参个数真相同了，这条差异应从登记表移出。"""
        assert len(impl_of(PREFILL_WP_IMPL).positional_args) == 3
        assert len(impl_of(EXECUTOR_WP_IMPL).positional_args) == 2
        assert [a.arg for a in _func_def(EXECUTOR_WP_IMPL).args.args][:4] == ["db", "project_id", "wp_code", "column"]
        diff = difference_of("positional_arg_count")
        assert diff is not None and "3" in diff.detail and "2" in diff.detail

    def test_unregistered_dimension_returns_none(self) -> None:
        assert difference_of("__not_a_dimension__") is None

    def test_impls_do_not_reference_the_registry(self) -> None:
        """登记与实现不得互相依赖（实现里引用登记模块 = 双真源）。"""
        for impl in _IMPLS:
            assert "formula_wp_semantics" not in _code(impl), f"{impl} 引用了语义登记模块"
