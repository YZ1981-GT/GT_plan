"""Task 15：报表侧「公司（母公司个别）」列口径守卫。

覆盖 Property 25~27：

- **Property 25** `_load_parent_row_index` 改用共享 helper、不再引用 `parent_company_code`
- **Property 26** 反向自检 —— 同代码同年度同时存在 consolidated 与 standalone 两条项目时，
  旧实现取到**合并项目**（复现即打红）、新实现取到**单体项目**
- **Property 27** fail-open 与 `:parent` 占位 / `current_parent` 坐标语义不变

🔴 两条判据写法上的坑（各踩过一次，勿"简化"回去）
------------------------------------------------
1. **`parent_company_code` 的断言必须剥 docstring**。Task 14 实测该函数内
   *代码级* 0 处、*docstring* 3 处 —— 那 3 处是需求 9.1 要求写明的「同代码
   standalone 兄弟 ≠ 上级公司」对比说明，裸 `src.count("parent_company_code")`
   会把说明文字数成真实引用而误红。故先剥注释与字符串再断言，并配一条
   「docstring 里确实还留着那 3 处说明」的正向断言防说明被顺手删掉。
2. **旧行为复现必须真跑一遍旧查询**，不能只源码级断言「新实现引用了 helper」。
   源码断言挡不住「引用了 helper 但把结果丢掉」这种形态。
"""

from __future__ import annotations

import ast
import inspect
import re
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.core import Project
from app.services.parent_company_scope import resolve_parent_standalone_project
from app.services.report_excel_exporter import ReportExcelExporter

# 内存 SQLite（与 `test_financial_template_cell_mapping.py` 同款范式）——
# 本文件的行为断言只需 `projects` 表，不连真实库。
_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
_async_session = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _async_session() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORTER_PATH = (
    REPO_ROOT / "backend" / "app" / "services" / "report_excel_exporter.py"
)
EXPORTER_SRC = EXPORTER_PATH.read_text(encoding="utf-8")


# ──────────────────────────── 源码判据工具 ────────────────────────────


def _string_literal_lines(src: str) -> set[int]:
    """整份源码里被字符串字面量（含 docstring）占据的行号集合。

    🔴 必须对**整份文件**做一次 AST 解析后再按行号裁切 —— 对「缩进的方法片段」单独
    `ast.parse` 会 `SyntaxError`（缩进 + 多行签名），那正是本文件首版踩的坑。
    """
    tree = ast.parse(src)
    drop: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.end_lineno is None:
                continue
            drop.update(range(node.lineno, node.end_lineno + 1))
    return drop


_EXPORTER_STR_LINES = _string_literal_lines(EXPORTER_SRC)


def _strip_docstrings_and_comments(src: str, *, str_lines: set[int] | None = None,
                                   offset: int = 0) -> str:
    """按预先算好的字符串行号集合剥掉 docstring/注释。

    `str_lines` 缺省时对 `src` 自身解析（要求 `src` 是可独立解析的完整源码，
    仅供自检 fixture 用）；生产判据一律传整份文件的行号集合 + 起始行 `offset`。
    """
    if str_lines is None:
        str_lines = _string_literal_lines(src)
        offset = 0
    out: list[str] = []
    for i, line in enumerate(src.splitlines(), 1):
        if (i + offset) in str_lines:
            continue
        out.append(line.split("#", 1)[0])
    return "\n".join(out)


def _func_span(name: str) -> tuple[int, int]:
    """某方法在 `report_excel_exporter.py` 里的 `(起始行, 结束行)`（1-based，含端点）。"""
    tree = ast.parse(EXPORTER_SRC)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            assert node.end_lineno is not None
            return node.lineno, node.end_lineno
    raise AssertionError(f"未找到方法 {name}（已改名？判据将空转）")


def _func_src(name: str) -> str:
    """按 AST 精确截取某方法的源码（含 docstring）。"""
    a, b = _func_span(name)
    return "\n".join(EXPORTER_SRC.splitlines()[a - 1 : b])


def _func_code(name: str) -> str:
    """某方法剥掉 docstring/注释后的可执行代码。"""
    a, _b = _func_span(name)
    return _strip_docstrings_and_comments(
        _func_src(name), str_lines=_EXPORTER_STR_LINES, offset=a - 1
    )


class TestSourceJudgeToolsSelfCheck:
    """判据工具自检 —— 防「剥注释器失效 ⇒ 断言恒绿」。"""

    def test_func_src_raises_on_unknown_name(self) -> None:
        with pytest.raises(AssertionError):
            _func_src("_load_parent_row_index_DOES_NOT_EXIST")

    def test_stripper_removes_docstring_but_keeps_code(self) -> None:
        sample = (
            "def f():\n"
            '    """doc 里提到 parent_company_code 三次：'
            'parent_company_code parent_company_code"""\n'
            "    # 注释里也提到 parent_company_code\n"
            "    x = 1\n"
        )
        stripped = _strip_docstrings_and_comments(sample)
        assert "parent_company_code" not in stripped, "剥注释器失效 ⇒ Property 25 断言会误红"
        assert "x = 1" in stripped, "剥注释器把代码也删了 ⇒ 断言会空转"

    def test_stripper_keeps_real_code_reference(self) -> None:
        """反向：真的在代码里引用时必须留下来（否则 Property 25 抓不到回退）。"""
        sample = (
            "def f(project):\n"
            '    """doc"""\n'
            "    return project.parent_company_code\n"
        )
        assert "parent_company_code" in _strip_docstrings_and_comments(sample)


# ──────────────────────── Property 25：改用共享 helper ────────────────────────


class TestProperty25UsesSharedHelper:
    def test_imports_shared_helper(self) -> None:
        assert "from app.services.parent_company_scope import" in EXPORTER_SRC
        assert "resolve_parent_standalone_project" in EXPORTER_SRC

    def test_calls_helper_inside_loader(self) -> None:
        body = _func_src("_load_parent_row_index")
        assert re.search(
            r"await\s+resolve_parent_standalone_project\(\s*self\.db\s*,\s*project\s*\)",
            body,
        ), "未真实 await 共享 helper（引用了但没用 = 源码断言的盲区）"

    def test_no_code_level_parent_company_code_reference(self) -> None:
        """代码级不得再引用 `parent_company_code`（那是**上级公司**，不是母公司单体）。"""
        code = _func_code("_load_parent_row_index")
        assert "parent_company_code" not in code, (
            "报表母公司列又按上级公司定位了（旧错口径回退）"
        )

    def test_docstring_still_explains_the_distinction(self) -> None:
        """正向：需求 9.1 要求的「同代码 standalone 兄弟 ≠ 上级公司」说明必须还在。

        这条与上一条互为对照 —— 上一条剥掉 docstring 后为 0，本条要求 docstring 里
        仍有说明；两条同时成立才证明「剥注释器有效」且「说明未被顺手删掉」。
        """
        body = _func_src("_load_parent_row_index")
        assert body.count("parent_company_code") >= 3, (
            "docstring 里的口径对比说明被删了（后来者会重新犯同一个错）"
        )
        assert "上级公司" in body

    def test_query_conditions_are_delegated_not_reimplemented(self) -> None:
        """不得在本层重写三条件查询（口径必须单一真源）。"""
        code = _func_code("_load_parent_row_index")
        assert "report_scope" not in code, "本层重写了 report_scope 过滤 ⇒ 双真源"
        assert "select(Project)" not in code, "本层重写了项目查询 ⇒ 双真源"

    def test_helper_itself_has_three_conditions(self) -> None:
        """交叉锁死：被委托的 helper 里三个条件齐备（缺一即旧缺口复活）。

        用 `textwrap.dedent` 把方法源码拉回顶层再解析（`inspect.getsource` 返回的是
        缩进后的模块级函数体，本例该 helper 是模块级函数故 dedent 即可）。
        """
        import textwrap

        src = textwrap.dedent(inspect.getsource(resolve_parent_standalone_project))
        code = _strip_docstrings_and_comments(src)
        for cond in ("company_code", "audit_year", "report_scope"):
            assert cond in code, f"helper 查询缺 {cond} 条件"


# ─────────────────── Property 26：旧行为复现必打红（真跑查询） ───────────────────


async def _mk(db, *, company_code, scope, audit_year=2024, parent_code=None) -> Project:
    proj = Project(
        id=uuid.uuid4(),
        name=f"{company_code}-{scope}",
        client_name=company_code,
        template_type="soe",
        report_scope=scope,
        company_code=company_code,
        parent_company_code=parent_code,
        audit_year=audit_year,
    )
    db.add(proj)
    await db.flush()
    return proj


async def _legacy_lookup(db, project: Project) -> Project | None:
    """复现旧实现：按 `parent_company_code` 定位，且**不过滤** scope / year。"""
    result = await db.execute(
        sa.select(Project).where(
            Project.company_code == project.parent_company_code,
            Project.is_deleted == sa.false(),
        )
    )
    return result.scalars().first()


@pytest.mark.asyncio
class TestProperty26OldBehaviourReproduced:
    async def test_new_impl_picks_standalone_sibling(self, db_session) -> None:
        consol = await _mk(db_session, company_code="RP01", scope="consolidated")
        standalone = await _mk(db_session, company_code="RP01", scope="standalone")
        got = await resolve_parent_standalone_project(db_session, consol)
        assert got is not None
        assert got.id == standalone.id, "新实现应取同代码同年度的 standalone 兄弟"
        assert got.id != consol.id

    async def test_old_impl_would_pick_upper_level_company(self, db_session) -> None:
        """旧口径按 `parent_company_code` 会取到**上级公司**（另一家公司）。"""
        upper = await _mk(db_session, company_code="RP02UP", scope="standalone")
        consol = await _mk(
            db_session, company_code="RP02", scope="consolidated", parent_code="RP02UP"
        )
        await _mk(db_session, company_code="RP02", scope="standalone")

        legacy = await _legacy_lookup(db_session, consol)
        assert legacy is not None and legacy.id == upper.id, (
            "旧查询复现失败 ⇒ 本条反向自检空转"
        )

        new = await resolve_parent_standalone_project(db_session, consol)
        assert new is not None and new.id != upper.id, (
            "新实现取到了上级公司 = 旧错口径回退"
        )
        assert new.company_code == "RP02"

    async def test_old_impl_missing_scope_filter_could_pick_consolidated(
        self, db_session
    ) -> None:
        """旧查询无 scope 过滤 ⇒ 同代码有合并项目时可能把**合并数**当母公司个别数。"""
        consol = await _mk(
            db_session, company_code="RP03", scope="consolidated", parent_code="RP03"
        )
        await _mk(db_session, company_code="RP03", scope="standalone")

        # 旧查询的候选集里合并项目在册（`.first()` 无 ORDER BY ⇒ 可能命中它）
        result = await db_session.execute(
            sa.select(Project).where(
                Project.company_code == consol.parent_company_code,
                Project.is_deleted == sa.false(),
            )
        )
        candidates = list(result.scalars().all())
        assert any(p.id == consol.id for p in candidates), (
            "旧查询候选集不含合并项目 ⇒ 本条反向自检空转"
        )

        new = await resolve_parent_standalone_project(db_session, consol)
        assert new is not None
        assert new.id != consol.id, "新实现取到了合并项目自身"
        assert new.report_scope == "standalone"

    async def test_year_filter_prevents_cross_year_mixing(self, db_session) -> None:
        """兄弟项目年度不同 ⇒ 必须留空（旧查询缺 audit_year 会跨年度串数）。"""
        consol = await _mk(
            db_session, company_code="RP04", scope="consolidated", audit_year=2024
        )
        await _mk(
            db_session, company_code="RP04", scope="standalone", audit_year=2023
        )
        assert await resolve_parent_standalone_project(db_session, consol) is None


# ─────────────────── Property 27：fail-open 与占位语义不变 ───────────────────


class _NoDbExporter(ReportExcelExporter):
    """只用来调 `_load_parent_row_index`，不触库。"""

    def __init__(self) -> None:  # noqa: D107 - 故意不调 super
        self.db = None


@pytest.mark.asyncio
class TestProperty27FailOpenAndPlaceholders:
    async def test_none_project_returns_empty_dict(self) -> None:
        assert await _NoDbExporter()._load_parent_row_index(None, 2024, ["balance_sheet"]) == {}

    async def test_helper_exception_is_failed_open(self, monkeypatch) -> None:
        """helper 抛异常 → 返回空 dict、该列留空、**不崩**（需求 9.3）。"""
        import app.services.report_excel_exporter as mod

        async def _boom(db, project):  # noqa: ANN001
            raise RuntimeError("db down")

        monkeypatch.setattr(mod, "resolve_parent_standalone_project", _boom)

        class _P:
            id = uuid.uuid4()
            audit_year = 2024

        out = await _NoDbExporter()._load_parent_row_index(_P(), 2024, ["balance_sheet"])
        assert out == {}

    async def test_helper_assertion_error_is_also_caught(self, monkeypatch) -> None:
        """helper 对「同代码多条 standalone」抛 AssertionError，本层也须兜住。

        `except Exception` 覆盖 AssertionError；若被改成
        `except (RuntimeError, SQLAlchemyError)` 之类窄捕获，导出会整体 500。
        """
        import app.services.report_excel_exporter as mod

        async def _assert_boom(db, project):  # noqa: ANN001
            raise AssertionError("多条 standalone")

        monkeypatch.setattr(mod, "resolve_parent_standalone_project", _assert_boom)

        class _P:
            id = uuid.uuid4()
            audit_year = 2024

        assert await _NoDbExporter()._load_parent_row_index(
            _P(), 2024, ["balance_sheet"]
        ) == {}

    async def test_year_mismatch_leaves_blank(self, monkeypatch) -> None:
        """导出年度与项目 audit_year 分歧 → 留空（宁可留空不写错年度的数）。"""
        import app.services.report_excel_exporter as mod

        calls: list[int] = []

        async def _spy(db, project):  # noqa: ANN001
            calls.append(1)
            return None

        monkeypatch.setattr(mod, "resolve_parent_standalone_project", _spy)

        class _P:
            id = uuid.uuid4()
            audit_year = 2023

        assert await _NoDbExporter()._load_parent_row_index(
            _P(), 2024, ["balance_sheet"]
        ) == {}
        assert not calls, "年度分歧时不应再去定位兄弟项目"

class TestProperty27PlaceholderSemantics:
    """占位符/坐标语义（同步断言，与上面的 async fail-open 分开以免 asyncio 标记警告）。"""

    def test_parent_placeholder_pattern_unchanged(self) -> None:
        """`{{row:CODE:current:parent}}` 占位语义不变（Property 27 后半）。"""
        from app.services.report_excel_exporter import _ROW_PLACEHOLDER_RE

        m = _ROW_PLACEHOLDER_RE.fullmatch("{{row:BS-002:current:parent}}")
        assert m is not None
        assert m.group(1) == "BS-002"
        assert m.group(2) == "current"
        assert m.group(3) == "parent"

        m2 = _ROW_PLACEHOLDER_RE.fullmatch("{{row:BS-002:prior}}")
        assert m2 is not None and m2.group(3) is None

    def test_current_parent_coordinate_key_unchanged(self) -> None:
        """`cell_mapping.json` 的 `current_parent` / `prior_parent` 键仍被消费。"""
        src = _func_src("_fill_by_cell_mapping")
        assert 'info.get("current_parent")' in src
        assert 'info.get("prior_parent")' in src

    def test_parent_row_index_still_threaded_through(self) -> None:
        """`parent_row_index` 仍从 export 传到两条填充路径（接线未断）。

        方法名逐字为 `_fill_by_placeholders` / `_fill_by_cell_mapping`（本文件首版
        按 `_fill_inline_placeholders` 写 → `_func_src` 直接打红，正是「按错名写守卫
        会 0 命中」的护栏起了作用）。
        """
        assert EXPORTER_SRC.count("parent_row_index") >= 6
        for name in ("_fill_template", "_fill_by_placeholders", "_fill_by_cell_mapping"):
            assert "parent_row_index" in _func_src(name), f"{name} 丢了 parent_row_index"
