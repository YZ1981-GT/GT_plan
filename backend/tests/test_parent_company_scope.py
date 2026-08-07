"""母公司口径 helper 守卫（Property 16 / 17 / 18 / 24）。

被测真源：``app/services/parent_company_scope.py``（spec Task 8 已落盘，本守卫**不改它**）。

四组判据：

1. **Property 16（需求 7.1 / 7.2）** 源码级断言两个 resolver 各自的 ``.where(`` 里
   ``company_code`` / ``audit_year`` / ``report_scope`` 三个条件齐备，且 scope 字面量
   直写不抽常量。判据必须先 ``_strip_comments()`` —— 该模块 docstring 与注释里大量
   提到这三个字段名（「缺 ``report_scope`` 与 ``audit_year`` 过滤」等），不剥会把说明
   文字数成真实条件 ⇒ 断言恒绿空转。配套三条**反向自检**（替身源码去掉某个条件必被判缺）。

2. **Property 17（需求 7.3 / 7.4）** 用替身 session（不连库）覆盖边界：入参 scope 不符 /
   无兄弟 / 同代码多条 / 定位字段缺失 / 反向 resolver 对称边界。替身会捕获实际下发的
   where 条件与参数，用于断言「非合并入参时压根没发查询」。

3. **Property 18（需求 7.5 / 7.6）** 与展示层 ``project_display.get_project_display_name``
   交叉锁死。该函数名**逐字为此**（不是 ``build_project_display_name``），故先用
   ``hasattr`` / ``inspect.getmembers`` 断言符号存在；它只吃 dict 列表、不连库，故交叉
   锁死时把 ORM ``Project`` 投影成 dict 再喂给它。

4. **Property 24（需求 8.6）** 模块 docstring 显式登记「不扩展 ``normalize_report_scope``
   取值域」的决定，且 ``parent_only`` 只出现在注释/docstring 里、不出现在代码路径。

Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 8.6
"""

from __future__ import annotations

import inspect
import logging
import re
import uuid
from pathlib import Path

import pytest

import app.services.parent_company_scope as pcs
from app.models.core import Project
from app.services import project_display
from app.services.note_section_catalog import normalize_report_scope
from app.services.parent_company_scope import (
    is_parent_company_project,
    resolve_consolidated_sibling,
    resolve_parent_standalone_project,
)

# ─────────────────────── 源码定位（不写死相对路径深度） ───────────────────────

_MODULE_FILE = inspect.getsourcefile(pcs)
assert _MODULE_FILE, "无法定位 parent_company_scope 源文件"
_MODULE_PATH = Path(_MODULE_FILE)
_SRC = _MODULE_PATH.read_text(encoding="utf-8")

assert _MODULE_PATH.name == "parent_company_scope.py", _MODULE_PATH
assert "resolve_parent_standalone_project" in _SRC, "读到的源码不含被测函数（路径解析失效）"


# ─────────────────────── 源码切片与判据（纯函数，供反向自检复用） ───────────────────────


def _strip_comments(src: str) -> str:
    """剥掉三引号串（含 docstring）与 ``#`` 行注释。

    该模块的说明文字里逐字写着 ``report_scope`` / ``audit_year`` / ``company_code``，
    不剥离会让「三条件齐备」断言恒绿。
    """
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    return re.sub(r"(?m)#.*$", "", out)


_TOP_DEF_RE = re.compile(r"(?m)^(?:async\s+)?def\s+")


def _func_body(src: str, name: str) -> str:
    """按「``async def X`` 到下一个顶层 ``def``/``async def``」切片。

    禁用「固定字符窗口」与「声明后第一个 ``{``」类启发式；切到空片段直接打红
    （防正则失效变成空转）。
    """
    head = re.search(rf"(?m)^(?:async\s+)?def\s+{re.escape(name)}\s*\(", src)
    if head is None:
        raise AssertionError(f"未在源码中找到顶层函数 {name}（切片判据失效）")
    nxt = _TOP_DEF_RE.search(src, head.end())
    body = src[head.start() : nxt.start() if nxt else len(src)]
    assert body.strip(), f"{name} 的函数体切片为空（正则失效）"
    assert len(body.splitlines()) > 3, f"{name} 的函数体切片过短：{body!r}"
    return body


def _where_clause(body: str, *, func_name: str) -> str:
    """取 ``.where(`` 的实参段（括号配对，不用固定窗口）。"""
    idx = body.find(".where(")
    assert idx != -1, f"{func_name} 的查询里找不到 `.where(` 调用"
    start = body.index("(", idx)
    depth = 0
    for pos in range(start, len(body)):
        ch = body[pos]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                clause = body[start + 1 : pos]
                assert clause.strip(), f"{func_name} 的 where 实参段为空"
                return clause
    raise AssertionError(f"{func_name} 的 `.where(` 括号未配对")


_COND_PATTERNS = {
    "company_code": r"Project\.company_code\s*==",
    "audit_year": r"Project\.audit_year\s*==",
    "report_scope": r"Project\.report_scope\s*==",
}


def _where_conditions(src: str, func_name: str) -> set[str]:
    """判据本体：该函数 where 里逐字显式出现的三个条件。"""
    clause = _where_clause(_func_body(_strip_comments(src), func_name), func_name=func_name)
    return {key for key, pat in _COND_PATTERNS.items() if re.search(pat, clause)}


def _where_conditions_raw(src: str, func_name: str) -> set[str]:
    """**不剥注释**的同款判据 —— 只供反向自检用，证明 `_strip_comments()` 不可省。"""
    clause = _where_clause(_func_body(src, func_name), func_name=func_name)
    return {key for key, pat in _COND_PATTERNS.items() if re.search(pat, clause)}


def _where_clause_of(src: str, func_name: str) -> str:
    return _where_clause(_func_body(_strip_comments(src), func_name), func_name=func_name)


def _where_call_count(src: str, func_name: str) -> int:
    """该函数体内 ``.where(`` 出现次数 —— 禁动态拼装（多次 where 链式追加）。"""
    return _func_body(_strip_comments(src), func_name).count(".where(")


# 替身源码（反向自检用）：形态与真实模块同构，各自缺一个条件。
_STUB_FULL = '''
async def resolve_parent_standalone_project(db, consol_project):
    """定位母公司单体项目（缺 report_scope 与 audit_year 过滤是缺陷）。"""
    if normalize_report_scope(consol_project.report_scope) != "consolidated":
        return None
    result = await db.execute(
        sa.select(Project).where(
            Project.company_code == consol_project.company_code,
            Project.audit_year == consol_project.audit_year,
            Project.report_scope == "standalone",
            Project.is_deleted == sa.false(),
        )
    )
    return result.scalars().first()


async def other_top_level(db):
    return None
'''

_STUB_NO_SCOPE = _STUB_FULL.replace(
    '            Project.report_scope == "standalone",\n', ""
)
_STUB_NO_YEAR = _STUB_FULL.replace(
    "            Project.audit_year == consol_project.audit_year,\n", ""
)
_STUB_NO_CODE = _STUB_FULL.replace(
    "            Project.company_code == consol_project.company_code,\n", ""
)

# 关键替身：条件被删、但 **where 实参段内部**留了一条提到它的注释。
# 不剥注释的判据会把注释文字数成真实条件 ⇒ 恒绿空转；剥注释后才判得出缺条件。
_STUB_NO_SCOPE_COMMENTED = _STUB_FULL.replace(
    '            Project.report_scope == "standalone",\n',
    '            # 本应有 Project.report_scope == "standalone"，此处故意省略\n',
)


# ─────────────────────── 替身 session（不连库） ───────────────────────


class _FakeScalars:
    def __init__(self, rows: list[Project]) -> None:
        self._rows = rows

    def all(self) -> list[Project]:
        return list(self._rows)

    def first(self) -> Project | None:
        return self._rows[0] if self._rows else None


class _FakeResult:
    def __init__(self, rows: list[Project]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)


class _RecordingSession:
    """捕获实际下发的 where 条件，并按这些条件在内存项目集合上过滤。

    ``forced_rows`` 用于构造「同代码多条 standalone」这类唯一索引理论上不可能的场景。
    """

    def __init__(
        self,
        projects: list[Project] | None = None,
        *,
        forced_rows: list[Project] | None = None,
    ) -> None:
        self.projects = list(projects or [])
        self.forced_rows = forced_rows
        self.statements: list[object] = []
        self.params: list[dict] = []
        self.sql: list[str] = []

    async def execute(self, stmt):  # noqa: ANN001 - 替身
        compiled = stmt.compile()
        self.statements.append(stmt)
        self.params.append(dict(compiled.params))
        self.sql.append(str(compiled))
        if self.forced_rows is not None:
            return _FakeResult(list(self.forced_rows))
        return _FakeResult(self._filter(dict(compiled.params)))

    def _filter(self, params: dict) -> list[Project]:
        """按**实际绑定参数**过滤（不按 SQL 文本 —— SELECT 列表里也含这些列名）。"""
        rows: list[Project] = []
        for proj in self.projects:
            if bool(proj.is_deleted):
                continue
            if "company_code_1" in params and proj.company_code != params["company_code_1"]:
                continue
            if "audit_year_1" in params and proj.audit_year != params["audit_year_1"]:
                continue
            if "report_scope_1" in params and proj.report_scope != params["report_scope_1"]:
                continue
            rows.append(proj)
        return rows


def _proj(
    *,
    code: str | None = "A01",
    year: int | None = 2025,
    scope: str | None = "standalone",
    name: str = "甲公司",
    deleted: bool = False,
) -> Project:
    return Project(
        id=uuid.uuid4(),
        name=name,
        client_name=name,
        company_code=code,
        audit_year=year,
        report_scope=scope,
        is_deleted=deleted,
    )


def _to_dict(proj: Project) -> dict:
    """ORM → dict 投影：``get_project_display_name`` 只吃 dict 列表、不连库。"""
    return {
        "id": str(proj.id),
        "name": proj.name,
        "client_name": proj.client_name,
        "company_code": proj.company_code,
        "audit_year": proj.audit_year,
        "report_scope": proj.report_scope,
        "is_deleted": bool(proj.is_deleted),
    }

# ════════════════════════ Property 16：三条件齐备（源码级） ════════════════════════


class TestProperty16WhereConditions:
    """`resolve_*` 的查询必须逐字含 company_code / audit_year / report_scope 三个条件。

    Validates: Requirements 7.1, 7.2
    """

    @pytest.mark.parametrize(
        "func_name",
        ["resolve_parent_standalone_project", "resolve_consolidated_sibling"],
    )
    def test_three_conditions_present(self, func_name: str) -> None:
        assert _where_conditions(_SRC, func_name) == {
            "company_code",
            "audit_year",
            "report_scope",
        }, f"{func_name} 的 where 缺条件"

    def test_scope_literals_written_inline(self) -> None:
        """scope 字面量直写、不抽常量、不动态拼装 —— 守卫按此形态断言。"""
        parent = _where_clause_of(_SRC, "resolve_parent_standalone_project")
        sibling = _where_clause_of(_SRC, "resolve_consolidated_sibling")
        assert re.search(r'Project\.report_scope\s*==\s*"standalone"', parent)
        assert re.search(r'Project\.report_scope\s*==\s*"consolidated"', sibling)

    def test_soft_delete_filter_present(self) -> None:
        """两个 resolver 都要排除软删项目，否则会定位到已删兄弟。"""
        for func_name in (
            "resolve_parent_standalone_project",
            "resolve_consolidated_sibling",
        ):
            clause = _where_clause_of(_SRC, func_name)
            assert re.search(r"Project\.is_deleted\s*==", clause), func_name

    # ── 反向自检：判据确实会打红 ──

    def test_reverse_selfcheck_missing_scope_detected(self) -> None:
        assert _where_conditions(_STUB_NO_SCOPE, "resolve_parent_standalone_project") == {
            "company_code",
            "audit_year",
        }

    def test_reverse_selfcheck_missing_year_detected(self) -> None:
        assert _where_conditions(_STUB_NO_YEAR, "resolve_parent_standalone_project") == {
            "company_code",
            "report_scope",
        }

    def test_reverse_selfcheck_missing_code_detected(self) -> None:
        assert _where_conditions(_STUB_NO_CODE, "resolve_parent_standalone_project") == {
            "audit_year",
            "report_scope",
        }

    def test_reverse_selfcheck_full_stub_passes(self) -> None:
        """正对照：完整替身必须被判为三条件齐备（证明判据不是恒红）。"""
        assert _where_conditions(_STUB_FULL, "resolve_parent_standalone_project") == {
            "company_code",
            "audit_year",
            "report_scope",
        }

    def test_reverse_selfcheck_strip_comments_is_required(self) -> None:
        """`_strip_comments()` 不可省：where 段内的注释会把缺失条件"凑齐"。

        同一份替身（scope 条件已删、只留一条提到它的注释）经两套判据：
        - **不剥注释** → 误判三条件齐备（恒绿空转，正是要防的形态）
        - **剥注释后** → 正确判出缺 scope
        """
        name = "resolve_parent_standalone_project"
        assert _where_conditions_raw(_STUB_NO_SCOPE_COMMENTED, name) == {
            "company_code",
            "audit_year",
            "report_scope",
        }, "不剥注释的判据本应被注释骗过；若这里不成立说明替身没构造对"
        assert _where_conditions(_STUB_NO_SCOPE_COMMENTED, name) == {
            "company_code",
            "audit_year",
        }, "剥注释后必须判出缺 report_scope"

    def test_strip_comments_still_hits_real_conditions(self) -> None:
        """防空转正对照：剥注释后仍能在真实模块里命中三个条件（不是把代码一起剥掉了）。"""
        for func_name in (
            "resolve_parent_standalone_project",
            "resolve_consolidated_sibling",
        ):
            clause = _where_clause_of(_SRC, func_name)
            assert "Project." in clause, f"{func_name} 剥注释后 where 段被清空"
            assert _where_conditions(_SRC, func_name), f"{func_name} 剥注释后判据为空"

    def test_single_where_call_no_dynamic_assembly(self) -> None:
        """每个 resolver 只许一个 `.where(`：链式追加/动态拼装会让源码级判据失效。"""
        for func_name in (
            "resolve_parent_standalone_project",
            "resolve_consolidated_sibling",
        ):
            assert _where_call_count(_SRC, func_name) == 1, (
                f"{func_name} 出现多个 `.where(`，与模块 docstring 的实现约定"
                f"「逐字显式写在各自的 where 里」不符"
            )

    def test_func_body_slicing_rejects_unknown_name(self) -> None:
        """切片判据失效时必须打红而不是返回空串。"""
        with pytest.raises(AssertionError):
            _func_body(_strip_comments(_SRC), "no_such_function_zzz")


# ════════════════════════ Property 17：边界行为 ════════════════════════


class TestProperty17ParentResolverBoundaries:
    """入参非 consolidated → None 且不发查询；无兄弟 → None 不抛。

    Validates: Requirements 7.3, 7.4
    """

    @pytest.mark.parametrize("scope", ["standalone", "parent_only", "", None, "PARENT_ONLY"])
    async def test_non_consolidated_returns_none_without_query(self, scope) -> None:
        session = _RecordingSession([_proj(scope="standalone")])
        got = await resolve_parent_standalone_project(session, _proj(scope=scope))
        assert got is None
        assert session.statements == [], f"scope={scope!r} 时不应下发任何查询"

    async def test_normalize_report_scope_treats_parent_only_as_standalone(self) -> None:
        """需求 8.6 的前提事实：`parent_only` 会被静默回退成 standalone。"""
        assert normalize_report_scope("parent_only") == "standalone"
        assert normalize_report_scope("consolidated") == "consolidated"

    async def test_no_sibling_returns_none_and_logs_info(self, caplog) -> None:
        consol = _proj(scope="consolidated")
        session = _RecordingSession([consol])  # 只有自己，无 standalone 兄弟
        with caplog.at_level(logging.INFO, logger=pcs.logger.name):
            got = await resolve_parent_standalone_project(session, consol)
        assert got is None
        assert len(session.statements) == 1, "应当真的发过一次查询"
        assert any(r.levelno == logging.INFO for r in caplog.records)
        assert not any(r.levelno >= logging.WARNING for r in caplog.records)

    async def test_sibling_found_returns_project(self) -> None:
        consol = _proj(scope="consolidated", name="甲集团")
        parent = _proj(scope="standalone", name="甲公司")
        session = _RecordingSession([consol, parent])
        got = await resolve_parent_standalone_project(session, consol)
        assert got is parent
        params = session.params[0]
        assert params["company_code_1"] == "A01"
        assert params["audit_year_1"] == 2025
        assert params["report_scope_1"] == "standalone"

    async def test_different_year_is_not_a_sibling(self) -> None:
        """audit_year 条件的价值：同代码但不同年度不构成兄弟。"""
        consol = _proj(scope="consolidated", year=2025)
        other_year = _proj(scope="standalone", year=2024)
        session = _RecordingSession([consol, other_year])
        assert await resolve_parent_standalone_project(session, consol) is None

    async def test_soft_deleted_sibling_is_ignored(self) -> None:
        consol = _proj(scope="consolidated")
        deleted = _proj(scope="standalone", deleted=True)
        session = _RecordingSession([consol, deleted])
        assert await resolve_parent_standalone_project(session, consol) is None

    async def test_multiple_standalone_raises_and_logs_error(self, caplog) -> None:
        consol = _proj(scope="consolidated")
        dupes = [_proj(scope="standalone"), _proj(scope="standalone")]
        session = _RecordingSession(forced_rows=dupes)
        with caplog.at_level(logging.ERROR, logger=pcs.logger.name):
            with pytest.raises(AssertionError):
                await resolve_parent_standalone_project(session, consol)
        assert any(r.levelno == logging.ERROR for r in caplog.records), "多条命中必须记 ERROR"

    @pytest.mark.parametrize("missing", ["code", "year"])
    async def test_missing_locator_field_returns_none_without_query(self, missing) -> None:
        kwargs = {"scope": "consolidated"}
        kwargs["code" if missing == "code" else "year"] = None
        session = _RecordingSession()
        got = await resolve_parent_standalone_project(session, _proj(**kwargs))
        assert got is None
        assert session.statements == [], "三元组不齐时不应下发查询"

    async def test_db_error_is_not_swallowed(self) -> None:
        """本模块不做 fail-open：DB 异常原样抛，fail-open 由调用方决定。"""

        class _Boom:
            async def execute(self, stmt):  # noqa: ANN001
                raise RuntimeError("db down")

        with pytest.raises(RuntimeError, match="db down"):
            await resolve_parent_standalone_project(_Boom(), _proj(scope="consolidated"))


class TestProperty17SiblingResolverBoundaries:
    """反向 resolver 的对称边界。

    Validates: Requirements 7.3, 7.4, 7.5
    """

    # 只有归一后 != "standalone" 的取值才属本用例覆盖面（其余取值一律被
    # `normalize_report_scope` 回退成 standalone、会真的发查询）→ 直接把参数收窄到
    # 大小写/空白三种合并写法，**不用 skip 凑绿**。
    @pytest.mark.parametrize("scope", ["consolidated", "CONSOLIDATED", " consolidated "])
    async def test_non_standalone_returns_none_without_query(self, scope) -> None:
        assert normalize_report_scope(scope) == "consolidated", "参数收窄前提被破坏"
        session = _RecordingSession([_proj(scope="consolidated")])
        got = await resolve_consolidated_sibling(session, _proj(scope=scope))
        assert got is None
        assert session.statements == []

    async def test_queries_for_consolidated_scope(self) -> None:
        standalone = _proj(scope="standalone")
        consol = _proj(scope="consolidated")
        session = _RecordingSession([standalone, consol])
        got = await resolve_consolidated_sibling(session, standalone)
        assert got is consol
        assert session.params[0]["report_scope_1"] == "consolidated"

    async def test_no_sibling_returns_none_and_logs_info(self, caplog) -> None:
        standalone = _proj(scope="standalone")
        session = _RecordingSession([standalone])
        with caplog.at_level(logging.INFO, logger=pcs.logger.name):
            assert await resolve_consolidated_sibling(session, standalone) is None
        assert any(r.levelno == logging.INFO for r in caplog.records)

    async def test_multiple_consolidated_raises(self) -> None:
        dupes = [_proj(scope="consolidated"), _proj(scope="consolidated")]
        session = _RecordingSession(forced_rows=dupes)
        with pytest.raises(AssertionError):
            await resolve_consolidated_sibling(session, _proj(scope="standalone"))

    @pytest.mark.parametrize("missing", ["code", "year"])
    async def test_missing_locator_field_returns_none(self, missing) -> None:
        kwargs = {"scope": "standalone"}
        kwargs["code" if missing == "code" else "year"] = None
        session = _RecordingSession()
        assert await resolve_consolidated_sibling(session, _proj(**kwargs)) is None
        assert session.statements == []


# ════════════════════════ Property 18：与展示层交叉锁死 ════════════════════════


class TestProperty18DisplayNameSymbolExists:
    """先断言符号存在 —— 按错名（``build_project_display_name``）写守卫会 0 命中空转。

    Validates: Requirements 7.6
    """

    def test_get_project_display_name_exists(self) -> None:
        assert hasattr(project_display, "get_project_display_name")
        members = dict(inspect.getmembers(project_display, inspect.isfunction))
        assert "get_project_display_name" in members
        assert "build_project_display_name" not in members, (
            "展示层函数名逐字为 get_project_display_name；出现 build_* 说明命名漂移，"
            "交叉锁死守卫需同步更新"
        )

    def test_signature_takes_dict_and_list(self) -> None:
        sig = inspect.signature(project_display.get_project_display_name)
        assert list(sig.parameters) == ["project", "all_projects"]

    def test_parent_suffix_literal(self) -> None:
        """后缀字面量锁死：判定口径依赖它。"""
        src = Path(inspect.getsourcefile(project_display)).read_text(encoding="utf-8")
        assert "（母公司）" in src
        assert "（合并）" in src


PARENT_SUFFIX = "（母公司）"


def _display_parent_set(projects: list[Project]) -> set[str]:
    """展示层判为母公司的集合（显示名以「（母公司）」结尾）。"""
    dicts = [_to_dict(p) for p in projects]
    out: set[str] = set()
    for proj, as_dict in zip(projects, dicts):
        name = project_display.get_project_display_name(as_dict, dicts)
        if name.endswith(PARENT_SUFFIX):
            out.add(str(proj.id))
    return out


async def _helper_parent_set(projects: list[Project]) -> set[str]:
    """helper 判为母公司的集合。"""
    session = _RecordingSession(projects)
    out: set[str] = set()
    for proj in projects:
        if await is_parent_company_project(session, proj):
            out.add(str(proj.id))
    return out


def _scenario_pair() -> list[Project]:
    """场景 ①：同代码同年度 consolidated + standalone 一对。"""
    return [
        _proj(code="A01", year=2025, scope="consolidated", name="甲集团"),
        _proj(code="A01", year=2025, scope="standalone", name="甲公司"),
    ]


def _scenario_lonely_standalone() -> list[Project]:
    """场景 ②：只有 standalone、无合并兄弟。"""
    return [_proj(code="B02", year=2025, scope="standalone", name="乙公司")]


def _scenario_different_year() -> list[Project]:
    """场景 ③：同代码但不同年度的 consolidated —— audit_year 条件的价值。"""
    return [
        _proj(code="C03", year=2024, scope="consolidated", name="丙集团2024"),
        _proj(code="C03", year=2025, scope="standalone", name="丙公司2025"),
    ]


def _scenario_mixed() -> list[Project]:
    """场景 ④：三组混合 + 一条软删合并兄弟。"""
    return [
        *_scenario_pair(),
        *_scenario_lonely_standalone(),
        *_scenario_different_year(),
        _proj(code="D04", year=2025, scope="consolidated", name="丁集团", deleted=True),
        _proj(code="D04", year=2025, scope="standalone", name="丁公司"),
    ]


_SCENARIOS = {
    "pair": _scenario_pair,
    "lonely_standalone": _scenario_lonely_standalone,
    "different_year": _scenario_different_year,
    "mixed": _scenario_mixed,
}


class TestProperty18CrossLock:
    """helper 与展示层判定口径必须逐项相等。

    Validates: Requirements 7.5, 7.6
    """

    @pytest.mark.parametrize("scenario", sorted(_SCENARIOS))
    async def test_sets_are_equal(self, scenario: str) -> None:
        projects = _SCENARIOS[scenario]()
        helper_set = await _helper_parent_set(projects)
        display_set = _display_parent_set(projects)
        assert helper_set == display_set, (
            f"场景 {scenario} 判定不一致：helper={helper_set} display={display_set}"
        )

    async def test_pair_scenario_marks_standalone_only(self) -> None:
        projects = _scenario_pair()
        consol, standalone = projects
        parents = await _helper_parent_set(projects)
        assert parents == {str(standalone.id)}
        assert str(consol.id) not in parents
        dicts = [_to_dict(p) for p in projects]
        assert project_display.get_project_display_name(dicts[0], dicts).endswith("（合并）")
        assert project_display.get_project_display_name(dicts[1], dicts).endswith(PARENT_SUFFIX)

    async def test_lonely_standalone_is_not_parent(self) -> None:
        projects = _scenario_lonely_standalone()
        assert await _helper_parent_set(projects) == set()
        assert _display_parent_set(projects) == set()

    async def test_different_year_consolidated_is_not_sibling(self) -> None:
        projects = _scenario_different_year()
        assert await _helper_parent_set(projects) == set()
        assert _display_parent_set(projects) == set()

    async def test_reverse_selfcheck_year_condition_matters(self) -> None:
        """反向自检：把不同年度改成同年度后，两侧必须同时翻为母公司。"""
        consol, standalone = _scenario_different_year()
        consol.audit_year = standalone.audit_year
        projects = [consol, standalone]
        assert await _helper_parent_set(projects) == {str(standalone.id)}
        assert _display_parent_set(projects) == {str(standalone.id)}


class TestProperty18NonCanonicalScopeDivergence:
    """交叉锁死的**已知边界**：`report_scope` 取非规范值时两侧口径分叉。

    成因（两侧对同一列的读法不同，均非本 spec 引入）：

    - helper 侧经 ``normalize_report_scope()`` 归一 —— ``None`` / ``parent_only``
      / 任意未知值一律**静默回退** ``standalone`` ⇒ 继续去找合并兄弟 ⇒ 判母公司。
    - 展示层 ``get_project_display_name`` 用**字面**比较 ``report_scope == "standalone"``
      ⇒ 非规范值不加「（母公司）」后缀。

    本用例把当前行为钉住（characterization），使这处分叉可见、不静默漂移；
    **不**把它塞进 ``_SCENARIOS``（那会让集合相等断言红在一个非本 spec 的既有分叉上）。

    真实库现状：8 个项目 ``report_scope`` 全为 ``standalone``、无 NULL、无
    ``consolidated`` ⇒ 该分叉当前为**潜伏态**，无活体实例。归属：``report_scope``
    列的取值域治理（非本 spec 半径），已在报告中登记。

    Validates: Requirements 7.5, 7.6
    """

    @pytest.mark.parametrize("odd_scope", [None, "parent_only", "combined"])
    async def test_helper_says_parent_but_display_does_not(self, odd_scope) -> None:
        consol = _proj(code="E05", year=2025, scope="consolidated", name="戊集团")
        odd = _proj(code="E05", year=2025, scope=odd_scope, name="戊公司")
        projects = [consol, odd]

        # 前提事实：该取值被静默回退成 standalone
        assert normalize_report_scope(odd_scope) == "standalone"

        helper_set = await _helper_parent_set(projects)
        display_set = _display_parent_set(projects)

        assert helper_set == {str(odd.id)}, "helper 侧经归一后判其为母公司"
        assert display_set == set(), "展示层字面比较，不加「（母公司）」后缀"
        assert helper_set != display_set, (
            "该分叉一旦被消除（两侧口径统一），本断言会打红 —— "
            "届时应把这些取值并入 _SCENARIOS 并删除本类"
        )

    async def test_canonical_scopes_do_not_diverge(self) -> None:
        """正对照：规范取值上两侧一致（证明上一条不是「两侧永远不等」）。"""
        projects = _scenario_pair()
        assert await _helper_parent_set(projects) == _display_parent_set(projects)


# ════════════════════════ Property 24：需求 8.6 处置已登记 ════════════════════════


class TestProperty24ScopeDecisionRegistered:
    """模块 docstring 登记「不扩展 normalize_report_scope 取值域」，代码路径无 parent_only。

    Validates: Requirements 8.6
    """

    def test_docstring_registers_decision(self) -> None:
        doc = inspect.getdoc(pcs) or ""
        assert doc, "parent_company_scope 缺模块 docstring"
        assert "normalize_report_scope" in doc
        assert "不扩展" in doc
        assert "parent_only" in doc, "需求 8.6 要求显式登记 parent_only 的处置"
        assert "8.6" in doc, "docstring 应标注对应需求编号，便于回溯"

    def test_parent_only_absent_from_code_path(self) -> None:
        code = _strip_comments(_SRC)
        assert "parent_only" not in code, (
            "parent_only 只许出现在 docstring/注释里说明为何不用它，"
            "不得出现在代码路径（附注层不表达该取值）"
        )

    def test_raw_source_mentions_it_for_the_record(self) -> None:
        """原文（未剥注释）必须含该说明 —— 与上一条共同区分「提到」与「使用」。"""
        assert "parent_only" in _SRC

    def test_reverse_selfcheck_code_usage_would_be_caught(self) -> None:
        """反向自检：把 parent_only 写进代码路径必被判红。"""
        bad = _SRC.replace(
            'Project.report_scope == "standalone"',
            'Project.report_scope == "parent_only"',
            1,
        )
        assert "parent_only" in _strip_comments(bad)

    def test_normalize_report_scope_domain_unchanged(self) -> None:
        """取值域未被扩展：只认 standalone / consolidated，其余回退 standalone。"""
        assert normalize_report_scope("standalone") == "standalone"
        assert normalize_report_scope("consolidated") == "consolidated"
        for other in ("parent_only", "combined", "unknown", None, ""):
            assert normalize_report_scope(other) == "standalone"

    def test_parent_only_code_path_allowlist(self) -> None:
        """`parent_only` 不出现在附注层取数路径 —— 全 ``app/`` 代码路径只许一处。

        判据 = 扫 ``backend/app/**/*.py``，**逐文件剥注释/docstring** 后仍含
        ``parent_only`` 的文件集合，必须恰等于登记清单（底稿层的 redirect 一处）。
        任何模块（尤其附注取数链路）把它写进代码路径都会打红。
        """
        app_dir = _MODULE_PATH.parent.parent  # services/ → app/
        assert app_dir.name == "app", app_dir
        allowlist = {"routers/wp_render_config.py"}

        scanned = 0
        hits: set[str] = set()
        for py in sorted(app_dir.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            scanned += 1
            if "parent_only" in _strip_comments(py.read_text(encoding="utf-8")):
                hits.add(py.relative_to(app_dir).as_posix())

        assert scanned > 300, f"扫描面异常（只扫到 {scanned} 个文件），判据可能失效"
        assert hits == allowlist, (
            f"`parent_only` 代码路径出现位置变化：多出 {sorted(hits - allowlist)}，"
            f"缺少 {sorted(allowlist - hits)}。附注层取数路径不得表达该取值"
            f"（需求 8.6 / Property 24）"
        )

    def test_allowlist_anchor_is_real(self) -> None:
        """锚点自检：登记的那处确实含该取值（防上一条在空集合上恒绿）。"""
        app_dir = _MODULE_PATH.parent.parent
        anchor = app_dir / "routers" / "wp_render_config.py"
        assert anchor.exists(), anchor
        assert "parent_only" in _strip_comments(anchor.read_text(encoding="utf-8"))
