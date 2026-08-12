# -*- coding: utf-8 -*-
"""完整性敏感清单项目级覆盖（`B50-T3-cscope-{cycle}`）守卫。

Feature: procedure-trimming-and-delegation-intelligence — Task 14
Requirements: 5.5, 5.6, 5.7

═══ 断言分两类（同 Wave 1 范式）═══

- **类 A = 独立口径判据**：本文件自己算出的事实（前缀单一真源、读写两侧 SQL 交叉锁死、
  真实库键盘存、cscope 行对 `load_b50_accounts()` 的零影响、剥注释与截函数体自检）。
- **类 B = 被测实现**：`ProcedureTrimService` 三个方法 + router 三个端点的行为。
  Task 14 的实现已落地，故本文件类 B **现在就应全绿**；若打红即为真实缺陷。

═══ 本文件的第一判据（tasks.md 明文要求）═══

「`B50-T3-cscope-*` 行不改变 `load_b50_accounts()` 任何输出（既不产生科目项也不改既有
字段）」。落法 = **复用** `test_b50_reader_extension.py` 里 Task 1 冻结的
`_LEGACY_ROWS` / `_LEGACY_EXPECTED` 快照与 `_FakeSession`（按文件路径 importlib 加载，
不抄第二份）—— 抄一份会让「快照被改」与「实现回归」不可区分，两边各自全绿。

🔴 禁在模块顶层 import 生产模块 —— 顶层 import 失败会让整个文件 collection error、
零断言执行，那时"全红"既可能是功能没做也可能是守卫写坏。改为测试内 try-import 后
`pytest.fail`（不是 skip）。
"""
from __future__ import annotations

import ast
import asyncio
import importlib.util
import io
import re
import tokenize
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]  # backend/
_SVC_PATH = _BACKEND / "app" / "services" / "procedure_trim_service.py"
_ROUTER_PATH = _BACKEND / "app" / "routers" / "procedure_trim.py"
_CTX_PATH = _BACKEND / "app" / "services" / "trim_decision_context.py"
_SIBLING_GUARD = _HERE.parent / "test_b50_reader_extension.py"

#: 前缀真源期望值（**只在本常量出现一次**；其余判据一律从生产常量派生）。
_EXPECTED_PREFIX = "B50-T3-cscope-"

#: 平台默认清单覆盖的 11 个循环（与前端 `COMPLETENESS_CYCLE_RULES` 同集合）。
_CYCLES = ("D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N")


# ═══════════════════════════════════════════════════════════════════════════
# 测试内 import（失败 fail 而非 skip —— skip 会让「模块根本 import 不进来」静默通过）
# ═══════════════════════════════════════════════════════════════════════════
def _svc_mod():
    try:
        from app.services import procedure_trim_service as mod
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import app.services.procedure_trim_service: {e!r}")
    return mod


def _router_mod():
    try:
        from app.routers import procedure_trim as mod
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import app.routers.procedure_trim: {e!r}")
    return mod


def _ctx_mod():
    try:
        from app.services import trim_decision_context as mod
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import app.services.trim_decision_context: {e!r}")
    return mod


def _sibling():
    """按**文件路径**加载 Task 1 的守卫模块，取它冻结的快照与替身。

    🔴 为什么用 importlib 而不是 `from tests.procedure_trim... import`：本目录无
    `__init__.py`，包名随 pytest 的 import 模式与 rootdir 变化（从 repo 根跑与从
    `backend/` 跑得到的包名不同）。按路径加载与运行目录无关。
    """
    if not _SIBLING_GUARD.exists():
        pytest.fail(f"Task 1 守卫文件不存在，快照无从复用: {_SIBLING_GUARD}")
    spec = importlib.util.spec_from_file_location("_t14_sibling_b50_guard", _SIBLING_GUARD)
    if spec is None or spec.loader is None:  # pragma: no cover
        pytest.fail(f"无法为 {_SIBLING_GUARD} 建 import spec")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"加载 Task 1 守卫模块失败: {e!r}")
    for name in ("_FakeSession", "_row", "_load", "_by_account", "_LEGACY_ROWS", "_LEGACY_EXPECTED"):
        if not hasattr(mod, name):
            pytest.fail(
                f"Task 1 守卫已不再导出 {name} —— 本文件的第一判据依赖它复用冻结快照；"
                "请同步更新，不要在此另抄一份快照（抄了两边都会全绿）"
            )
    return mod


# ═══════════════════════════════════════════════════════════════════════════
# 剥注释 / 截函数体 helper（判据必须落在**代码**上，不能被注释里的说明文字骗）
# ═══════════════════════════════════════════════════════════════════════════
def _strip_py_comments(src: str) -> str:
    """只剥 `#` 注释，**保留**普通字符串字面量（SQL 就在三引号里，剥掉判据全废）。"""
    spans: list[tuple[int, int]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                spans.append((tok.start[0], tok.start[1]))
    except tokenize.TokenError:  # pragma: no cover
        return src
    lines = src.splitlines()
    for row, col in spans:
        if 1 <= row <= len(lines):
            lines[row - 1] = lines[row - 1][:col]
    return "\n".join(lines)


def _code_only(src: str) -> str:
    """剥 `#` 注释**与全部 docstring**，保留普通字符串字面量。

    🔴 为什么必须剥 docstring：本 spec 的生产代码 docstring **有意**写着
    `B50-T3-cscope-{cycle}` 作为设计留痕，裸 `"B50-T3-cscope-" in src` 会把这些
    **说明文字**数成第二份字面量真源 ⇒ 判据在正确实现上打红（平台已登记的同族坑）。
    """
    no_comment = _strip_py_comments(src)
    try:
        tree = ast.parse(no_comment)
    except SyntaxError:  # pragma: no cover
        return no_comment
    lines = no_comment.splitlines()
    blank: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None) or []
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                blank.add(ln)
    return "\n".join("" if (i + 1) in blank else ln for i, ln in enumerate(lines))


def _func_src(src: str, name: str) -> str:
    """按缩进截取函数体；先用**圆括号配对**跳过参数列表。

    🔴 多行签名的 `) -> X:` 那行缩进可能 ≤ def 缩进，按「首个缩进 ≤ def 缩进的行即
    结束」会在签名处提前中断，截出来只有签名 ⇒ `assert 'xxx' in body` 恒假红。
    """
    m = re.search(rf"^([ \t]*)(?:async\s+def|def)\s+{re.escape(name)}\s*\(", src, re.M)
    assert m, f"未找到函数声明 {name}（守卫解析失效，不是实现缺陷）"
    indent = len(m.group(1))
    i = src.index("(", m.start())
    depth = 0
    while i < len(src):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body_start = src.index("\n", i) + 1
    out: list[str] = []
    for ln in src[body_start:].splitlines():
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent:
            break
        out.append(ln)
    return "\n".join(out)


# ── helper 自检（三条，均为反向：故意构造会骗过朴素写法的输入）────────────────
def test_strip_comments_keeps_sql_literal_self_check():
    src = 'X = """SELECT 1 FROM t -- inline"""  # real comment\nY = 2\n'
    out = _strip_py_comments(src)
    assert "real comment" not in out, "未剥掉 # 注释"
    assert "SELECT 1 FROM t" in out, "误剥了字符串字面量（SQL 在三引号里，剥掉判据全废）"


def test_code_only_strips_docstring_but_keeps_string_self_check():
    sample = (
        '"""模块 docstring 提到 B50-T3-cscope- 作为设计留痕。"""\n'
        'SQL = "item_id LIKE \'B50-T3-cscope-%\'"\n'
        "\n\ndef f():\n"
        '    """函数 docstring 也提到 B50-T3-cscope-。"""\n'
        "    return SQL\n"
    )
    code = _code_only(sample)
    assert code.count(_EXPECTED_PREFIX) == 1, (
        f"docstring 未被剥净（剩 {code.count(_EXPECTED_PREFIX)} 处）—— 说明文字会被数成真实字面量"
    )
    assert "item_id LIKE" in code, "普通字符串字面量被误剥"
    assert sample.count(_EXPECTED_PREFIX) == 3, "自检样本本身已变，请同步更新"


def test_func_src_self_check_multiline_signature():
    """🔴 自检样本的两个 def **必须同缩进**（模拟同一 class 内的两个方法）。

    首版写成 `async def f` 顶格 + `def g` 缩进 4，于是「缩进 ≤ def 缩进即结束」永不
    触发、`def g` 被截进函数体 ⇒ 断言以「越界截到了下一个函数」的形态**假红**（那是
    样本缺陷不是 helper 缺陷）。留此注释防后续会话按原样改回去。
    """
    src = (
        "    async def f(\n        self,\n        db,\n    ) -> dict:\n"
        '        """doc"""\n        return {"a": 1}\n\n'
        "    def g(self):\n        pass\n"
    )
    body = _func_src(src, "f")
    assert 'return {"a": 1}' in body, f"多行签名截断失败: {body!r}"
    assert "def g" not in body, "越界截到了下一个函数"
    # 反向：顶格函数同样要能截对（两种缩进形态都覆盖）
    top = _func_src('def h(a,\n      b):\n    return a + b\n\ndef i():\n    pass\n', "h")
    assert "return a + b" in top and "def i" not in top


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-1：前缀单一真源 + 读写两侧交叉锁死
# ═══════════════════════════════════════════════════════════════════════════
def test_prefix_constant_value_and_public_alias():
    ctx = _ctx_mod()
    assert hasattr(ctx, "COMPLETENESS_SCOPE_ITEM_PREFIX"), (
        "trim_decision_context 缺公开别名 COMPLETENESS_SCOPE_ITEM_PREFIX —— "
        "跨模块引用只剩私有名 _CSCOPE_PREFIX 可用，那种引用会在重命名时静默断裂"
    )
    assert ctx.COMPLETENESS_SCOPE_ITEM_PREFIX == _EXPECTED_PREFIX
    assert ctx._CSCOPE_PREFIX is ctx.COMPLETENESS_SCOPE_ITEM_PREFIX, "别名与私有名不是同一对象"


def test_write_side_imports_prefix_and_has_no_second_literal():
    """写入侧必须 import 读取侧的常量，且**代码里**不得再出现该前缀字面量。

    两侧各写一份字面量时，两侧单测各用自己的前缀构造样本 ⇒ 都全绿，只有真实往返
    （写进去再读出来）才暴露漂移。故判据落在「有没有第二份字面量」上。
    """
    raw = _SVC_PATH.read_text(encoding="utf-8")
    code = _code_only(raw)
    assert "from app.services.trim_decision_context import" in code, (
        "写入侧未从读取侧 import 前缀常量"
    )
    assert "COMPLETENESS_SCOPE_ITEM_PREFIX" in code, "写入侧未引用公开别名"
    assert _EXPECTED_PREFIX not in code, (
        f"写入侧代码里出现了第二份前缀字面量 {_EXPECTED_PREFIX!r} —— "
        "必须一律用 import 进来的常量拼接"
    )
    # 反向自检：原文（含注释/docstring）确实提到过该前缀 ⇒ 上一条不是「扫描面为空」的空转
    assert _EXPECTED_PREFIX in raw, (
        "写入侧连说明文字里都不再提该前缀 —— 剥 docstring 这层防护已无对象可防，"
        "请确认上一条断言是否已退化成空转"
    )


def test_read_side_sql_pattern_is_cross_locked_to_constant():
    """读取侧 SQL 的 LIKE 字面量必须 == 常量 + '%'。

    读取侧把 pattern 内联进 SQL 文本（`item_id LIKE 'B50-T3-cscope-%'`）而写入侧用
    常量拼 item_id：常量一改，写入落到新键、读取仍查旧键 ⇒ 「写进去的覆盖读不出来」，
    且两侧各自的替身单测都不会打红。故这条交叉锁死是唯一能挡住它的判据。
    """
    ctx = _ctx_mod()
    code = _code_only(_CTX_PATH.read_text(encoding="utf-8"))
    body = _func_src(code, "_load_completeness_override")
    assert "checklist_responses" in body, "读取侧函数体未截到（守卫解析失效）"
    expected_pattern = ctx.COMPLETENESS_SCOPE_ITEM_PREFIX + "%"
    m = re.search(r"item_id\s+LIKE\s+'([^']+)'", body)
    assert m, f"读取侧未找到 item_id LIKE 字面量，函数体片段: {body[:400]!r}"
    assert m.group(1) == expected_pattern, (
        f"读取侧 LIKE 字面量 {m.group(1)!r} 与常量派生值 {expected_pattern!r} 不一致 —— "
        "写入侧按常量落键、读取侧按旧字面量查，覆盖会写得进读不出"
    )


def test_write_side_item_id_is_prefix_plus_normalized_cycle():
    """写入的 item_id 形态 = 常量 + 大写 cycle（两个方法都必须如此）。"""
    code = _code_only(_SVC_PATH.read_text(encoding="utf-8"))
    for fn in ("set_completeness_scope_override", "clear_completeness_scope_override"):
        body = _func_src(code, fn)
        assert "strip().upper()" in body, f"{fn} 未把 cycle 归一为大写（'l' 与 'L' 会落成两行）"
        assert "_CSCOPE_ITEM_PREFIX" in body, f"{fn} 未用 import 进来的前缀常量拼 item_id"


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-2：**第一判据** —— cscope 行不改变 load_b50_accounts() 任何输出
#
# 复用 Task 1 冻结的 `_LEGACY_ROWS` / `_LEGACY_EXPECTED` 与 `_FakeSession`。
# ═══════════════════════════════════════════════════════════════════════════
def _cscope_rows(sib, cycles=_CYCLES):
    """构造一批 cscope 行；`conclusion` 走 Y/N，`remark` 放理由（与生产写入同形态）。"""
    out = []
    for idx, c in enumerate(cycles):
        out.append(sib._row(
            f"{_EXPECTED_PREFIX}{c}",
            conclusion="Y" if idx % 2 == 0 else "N",
            remark=f"{c} 循环覆盖理由第 {idx} 条",
        ))
    return out


def test_cscope_rows_do_not_change_frozen_legacy_output():
    """注入全部 11 个循环的 cscope 行后，`load_b50_accounts()` 输出**逐字段不变**。

    与 Task 1 已有的 `test_cscope_key_is_silently_skipped_by_all_branches` 的区别：
    那条只断言「不多出科目项」，这条按**冻结快照做全量深比对** —— 「既不产生科目项」
    与「也不改既有字段」是两个独立后果，只查前者会让「cscope 行把某个 cell 的 rmm
    覆盖掉」这类污染整条漏过去。
    """
    sib = _sibling()
    baseline = sib._load(list(sib._LEGACY_ROWS))
    polluted = sib._load(list(sib._LEGACY_ROWS) + _cscope_rows(sib))
    assert polluted == baseline, (
        "注入 cscope 行改变了 load_b50_accounts() 的输出 —— "
        f"基线 {baseline!r} / 实得 {polluted!r}"
    )
    # 同时验证冻结快照本身仍成立（否则「两边一致」也可能是两边一起坏了）
    got = sib._by_account(baseline)
    assert set(got) == set(sib._LEGACY_EXPECTED), f"科目集合漂移: {sorted(got)}"
    for name, exp in sib._LEGACY_EXPECTED.items():
        for key, val in exp.items():
            assert got[name][key] == val, (
                f"{name}.{key}: 冻结快照期望 {val!r} 实得 {got[name][key]!r}"
            )


def test_deep_comparison_is_sensitive_reverse_self_check():
    """反向自检：注入一条**矩阵**行必须让上一条的比对方式察觉差异。

    若深比对写成了恒真（例如只比 `len()` 或只比科目名集合），本条会打红 ⇒
    上一条的"通过"就是空转。
    """
    sib = _sibling()
    baseline = sib._load(list(sib._LEGACY_ROWS))
    with_matrix = sib._load(list(sib._LEGACY_ROWS) + [
        sib._row("B50-T3-matrix-应收账款-cutoff-RMM", conclusion="H"),
    ])
    assert with_matrix != baseline, (
        "注入矩阵行后输出仍相等 ⇒ 深比对无分辨力，上一条断言是空转"
    )
    # 差异必须落在既有科目的 cells 上（证明比对深度真的到了字段级）
    a = sib._by_account(baseline)["应收账款"]["cells"]
    b = sib._by_account(with_matrix)["应收账款"]["cells"]
    assert "cutoff" not in a and "cutoff" in b, f"差异形态异常: {sorted(a)} vs {sorted(b)}"


def test_cscope_only_rows_produce_no_accounts():
    """只有 cscope 行时返回空列表（不产生任何科目项）。"""
    sib = _sibling()
    assert sib._load(_cscope_rows(sib)) == []


@pytest.mark.parametrize("cycle", _CYCLES)
def test_every_cycle_key_is_rejected_by_matrix_parser(cycle):
    """11 个循环的 cscope 键逐个不被矩阵解析器接受（含末段恰为单字母的边界）。"""
    try:
        from app.services import b50_risk_reader as reader
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import app.services.b50_risk_reader: {e!r}")
    assert reader._parse_matrix_item_id(f"{_EXPECTED_PREFIX}{cycle}") is None


def test_cscope_key_that_mimics_matrix_tail_is_still_rejected():
    """构造一个末两段恰为合法 assertion+suffix 的 cscope 形态键，仍不得被接受。

    `B50-T3-cscope-完整性-completeness-RMM` 能穿透 suffix / assertion 两道白名单闸，
    唯一挡住它的是前缀锚定闸。这类键不会由 UI 产生，但它是「前缀锚定闸是否承重」在
    cscope 键空间上的对应样本 —— 有它在，后续若有人放宽前缀判据本条会打红。
    """
    try:
        from app.services import b50_risk_reader as reader
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import app.services.b50_risk_reader: {e!r}")
    assert reader._parse_matrix_item_id(f"{_EXPECTED_PREFIX}完整性-completeness-RMM") is None


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-3：真实库键盘存（全库 `B50-T3-cscope-*` 为 0 行 ⇒ 判据按「查询可执行且返回 0」）
# ═══════════════════════════════════════════════════════════════════════════
_LIVE_SQL = """
SELECT
  count(*) FILTER (WHERE item_id LIKE :cscope)  AS cscope_rows,
  count(*) FILTER (WHERE item_id LIKE 'B50-T3-%') AS all_t3_rows,
  count(*)                                      AS total_rows
FROM checklist_responses
"""


def _live_counts():
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")

    ctx = _ctx_mod()
    pattern = ctx.COMPLETENESS_SCOPE_ITEM_PREFIX + "%"

    async def _run():
        # 🔴 专用 NullPool 引擎 + 同一 loop 内 dispose：连接池绑定首个事件循环，
        #    借共享池会与其它测试双向污染（第二个起报 Event loop is closed）。
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                row = (await conn.execute(sa.text(_LIVE_SQL), {"cscope": pattern})).one()
                return dict(row._mapping)
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"真实库不可达（本条为连库判据）: {e!r}")


def test_live_cscope_count_query_is_executable():
    """真实库上按前缀常量做的计数查询**真跑一次**：列名与 LIKE 形态可执行。

    🔴 判据是「查询可执行且返回 ≥ 0」而不是「必须有数据」—— 全库 `B50-T3-*` 目前
    为 0 行（B50 从未被填写过），要求有数据会让本条恒红。真正要防的是列名写错
    （`checklist_responses` 的底稿外键是 `wp_id` 不是 `workpaper_id`）这类只有真跑
    才暴露的问题。
    """
    counts = _live_counts()
    assert counts["cscope_rows"] >= 0
    assert counts["cscope_rows"] <= counts["all_t3_rows"], (
        f"cscope 行数 {counts['cscope_rows']} 超过全部 B50-T3-* 行数 {counts['all_t3_rows']} —— "
        "前缀模式写错（cscope 键必是 B50-T3-* 的子集）"
    )
    assert counts["all_t3_rows"] <= counts["total_rows"]


def test_live_wp_id_column_exists_not_workpaper_id():
    """`checklist_responses` 的底稿外键列名真跑一次确认。"""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                rows = (await conn.execute(sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'checklist_responses'"
                ))).fetchall()
                return {r[0] for r in rows}
        finally:
            await engine.dispose()

    try:
        cols = asyncio.run(_run())
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"真实库不可达（本条为连库判据）: {e!r}")
    if not cols:
        pytest.skip("information_schema 未返回 checklist_responses（表不存在）")
    for need in ("wp_id", "item_id", "conclusion", "remark", "updated_by", "updated_at"):
        assert need in cols, f"checklist_responses 缺列 {need}（实有: {sorted(cols)}）"
    assert "workpaper_id" not in cols, "出现了 workpaper_id —— 写入 SQL 若用它会全部失败"


# ═══════════════════════════════════════════════════════════════════════════
# 写入路径替身（记录全部 SQL 与参数，按 SQL 文本分流）
# ═══════════════════════════════════════════════════════════════════════════
class _Res:
    def __init__(self, *, rows=None, scalar=None, rowcount=0):
        self._rows = rows or []
        self._scalar = scalar
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._scalar

    def first(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _WriteSession:
    """只实现写入路径真实走到的四条查询，按 SQL 文本分流并记录参数。

    🔴 必须分流：同一替身要区分「定位 B50 wp_id」「查既有行」「INSERT」「UPDATE/DELETE」，
    不分流会让其中一条拿到另一条的结果而**不报错**（表现为恒走 INSERT 分支）。
    """

    def __init__(self, *, wp_id="b50-wp-uuid", existing=None, list_rows=None, delete_rowcount=1):
        self.wp_id = wp_id
        self.existing = existing
        self.list_rows = list_rows or []
        self.delete_rowcount = delete_rowcount
        self.calls: list[tuple[str, dict]] = []
        self.flushed = 0

    async def execute(self, stmt, params=None):  # noqa: ANN001
        sql = " ".join(str(stmt).split())
        self.calls.append((sql, dict(params or {})))
        up = sql.upper()
        if "WP_INDEX" in up:
            return _Res(scalar=self.wp_id)
        if up.startswith("SELECT ID, CONCLUSION FROM CHECKLIST_RESPONSES"):
            return _Res(rows=[self.existing] if self.existing is not None else [])
        if up.startswith("SELECT CR.ITEM_ID"):
            return _Res(rows=self.list_rows)
        if up.startswith("INSERT"):
            return _Res(rowcount=1)
        if up.startswith("UPDATE"):
            return _Res(rowcount=1)
        if up.startswith("DELETE"):
            return _Res(rowcount=self.delete_rowcount)
        raise AssertionError(f"替身收到未预期的 SQL: {sql[:160]}")

    async def flush(self):
        self.flushed += 1

    def sqls(self, verb: str) -> list[tuple[str, dict]]:
        return [(s, p) for s, p in self.calls if " ".join(s.split()).upper().startswith(verb)]


def _svc(session):
    mod = _svc_mod()
    return mod.ProcedureTrimService(session)


def _run(coro):
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-1：写入行为（R5.5 理由必填 + 留痕 + Y/N 都算已表态）
# ═══════════════════════════════════════════════════════════════════════════
def test_service_exposes_three_methods():
    mod = _svc_mod()
    for name in (
        "set_completeness_scope_override",
        "clear_completeness_scope_override",
        "list_completeness_scope_overrides",
    ):
        assert hasattr(mod.ProcedureTrimService, name), f"ProcedureTrimService 缺 {name}"


@pytest.mark.parametrize("reason", ["", "   ", "\t\n ", None])
def test_blank_reason_is_rejected_before_any_write(reason):
    """理由必填：空白理由直接 400，且**一条写 SQL 都不发**（不留半条脏记录）。"""
    from fastapi import HTTPException

    sess = _WriteSession()
    with pytest.raises(HTTPException) as ei:
        _run(_svc(sess).set_completeness_scope_override(
            "p-1", cycle="L", sensitive=True, actor_user_id="u-1", reason=reason,
        ))
    assert ei.value.status_code == 400
    assert "理由" in str(ei.value.detail), f"400 提示未说明是理由缺失: {ei.value.detail!r}"
    assert sess.sqls("INSERT") == [] and sess.sqls("UPDATE") == [], (
        "校验未通过却已发出写 SQL —— 会留下无理由的覆盖记录"
    )


def test_blank_cycle_is_rejected():
    from fastapi import HTTPException

    sess = _WriteSession()
    with pytest.raises(HTTPException) as ei:
        _run(_svc(sess).set_completeness_scope_override(
            "p-1", cycle="  ", sensitive=True, actor_user_id="u-1", reason="理由",
        ))
    assert ei.value.status_code == 400


@pytest.mark.parametrize("sensitive,expected", [(True, "Y"), (False, "N")])
def test_both_y_and_n_are_written_as_statements(sensitive, expected):
    """`Y`/`N` **都算已表态**：`sensitive=False` 必须写 `N`，不得删行或写空串。"""
    sess = _WriteSession()
    out = _run(_svc(sess).set_completeness_scope_override(
        "p-1", cycle="l", sensitive=sensitive, actor_user_id="u-1", reason="本项目判断理由",
    ))
    assert out == {"cycle": "L", "sensitive": sensitive, "created": True, "updated": False}
    ins = sess.sqls("INSERT")
    assert len(ins) == 1, f"应恰好一条 INSERT，实得 {len(ins)}"
    _, params = ins[0]
    assert params["conclusion"] == expected
    assert params["item_id" if "item_id" in params else "item"] == f"{_EXPECTED_PREFIX}L"
    assert params["remark"] == "本项目判断理由"
    assert sess.sqls("DELETE") == [], "sensitive=False 走了删行 —— 那会让「已确认不敏感」退化成「未覆盖」"


def test_write_records_actor_and_timestamp():
    """留痕：INSERT 必须带 `updated_by` 与 `updated_at`（复用既有列，不新建表）。"""
    sess = _WriteSession()
    _run(_svc(sess).set_completeness_scope_override(
        "p-1", cycle="L", sensitive=True, actor_user_id="u-42", reason="理由",
    ))
    sql, params = sess.sqls("INSERT")[0]
    for col in ("updated_by", "updated_at"):
        assert col in sql, f"INSERT 未写 {col} —— 覆盖动作无操作人/时间留痕（R5.5）"
    assert params["actor"] == "u-42"
    assert params.get("ts"), "未传时间戳"


def test_existing_row_is_updated_not_duplicated():
    """已有行走 UPDATE（不产生第二行），并同样刷新留痕两列。"""
    sess = _WriteSession(existing=SimpleNamespace(id="row-1", conclusion="Y"))
    out = _run(_svc(sess).set_completeness_scope_override(
        "p-1", cycle="L", sensitive=False, actor_user_id="u-9", reason="改判理由",
    ))
    assert out == {"cycle": "L", "sensitive": False, "created": False, "updated": True}
    assert sess.sqls("INSERT") == [], "已有行仍走 INSERT —— 同一循环会出现两行覆盖"
    sql, params = sess.sqls("UPDATE")[0]
    assert params["conclusion"] == "N" and params["remark"] == "改判理由"
    for col in ("updated_by", "updated_at"):
        assert col in sql, f"UPDATE 未刷新 {col}"


def test_clear_deletes_row_and_never_writes_blank():
    """撤销走 DELETE 删行，不得改成写空 `conclusion`。"""
    sess = _WriteSession(delete_rowcount=1)
    out = _run(_svc(sess).clear_completeness_scope_override("p-1", cycle="l"))
    assert out == {"cycle": "L", "deleted": 1}
    dels = sess.sqls("DELETE")
    assert len(dels) == 1
    assert dels[0][1]["item"] == f"{_EXPECTED_PREFIX}L"
    assert sess.sqls("UPDATE") == [], (
        "撤销走了 UPDATE —— 留一行空 conclusion 会让「未覆盖」多出一条脏记录"
    )


def test_write_path_touches_only_cscope_item_id():
    """写入路径的每条写 SQL 只打 `B50-T3-cscope-*` 这一个键。

    R5.5 的零污染要求：不得顺手改 B50 的矩阵 / cycle / plan 三类键。
    """
    for coro_factory in (
        lambda s: _svc(s).set_completeness_scope_override(
            "p-1", cycle="L", sensitive=True, actor_user_id="u-1", reason="r"),
        lambda s: _svc(s).clear_completeness_scope_override("p-1", cycle="L"),
    ):
        sess = _WriteSession()
        _run(coro_factory(sess))
        for sql, params in sess.calls:
            up = " ".join(sql.split()).upper()
            if not up.startswith(("INSERT", "UPDATE", "DELETE")):
                continue
            assert "CHECKLIST_RESPONSES" in up, f"写入打到了别的表: {sql[:120]}"
            keys = [v for k, v in params.items() if isinstance(v, str) and v.startswith("B50-T3-")]
            for k in keys:
                assert k.startswith(_EXPECTED_PREFIX), f"写入路径打到了非 cscope 键: {k}"
            for bad in ("B50-T3-MATRIX-", "B50-T3-CYCLE-", "B50-T3-PLAN-"):
                assert bad not in up, f"写入 SQL 里出现 {bad}"


def test_missing_b50_workpaper_returns_409_with_actionable_hint():
    """B50 底稿未建 → 409 且提示可操作的下一步（不是 500，也不是静默成功）。"""
    from fastapi import HTTPException

    sess = _WriteSession(wp_id=None)
    with pytest.raises(HTTPException) as ei:
        _run(_svc(sess).set_completeness_scope_override(
            "p-1", cycle="L", sensitive=True, actor_user_id="u-1", reason="r",
        ))
    assert ei.value.status_code == 409
    assert "B50" in str(ei.value.detail)


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-2：读回行为（理由 + 留痕 + 与读取侧同判据）
# ═══════════════════════════════════════════════════════════════════════════
def _list_row(item_id, conclusion, remark="r", updated_at=None, updated_by_name="张三"):
    return SimpleNamespace(
        item_id=item_id, conclusion=conclusion, remark=remark,
        updated_at=updated_at, updated_by_name=updated_by_name,
    )


def test_list_returns_reason_and_trace():
    sess = _WriteSession(list_rows=[
        _list_row(f"{_EXPECTED_PREFIX}L", "Y", remark="本期暂估多"),
        _list_row(f"{_EXPECTED_PREFIX}E", "N", remark="已确认不敏感"),
    ])
    out = _run(_svc(sess).list_completeness_scope_overrides("p-1"))
    got = {o["cycle"]: o for o in out["overrides"]}
    assert set(got) == {"L", "E"}
    assert got["L"]["sensitive"] is True and got["L"]["reason"] == "本期暂估多"
    assert got["E"]["sensitive"] is False and got["E"]["reason"] == "已确认不敏感"
    for o in out["overrides"]:
        assert "updated_by_name" in o and "updated_at" in o, "读回缺留痕字段，面板无法回显谁改的"


@pytest.mark.parametrize("bad", ["", "  ", "on", "true", "1", None])
def test_list_skips_non_yn_conclusion_same_as_reader(bad):
    """非 `Y`/`N` 视为未覆盖 —— 与决策内核读取侧同判据（否则面板与判据结论会分叉）。"""
    sess = _WriteSession(list_rows=[_list_row(f"{_EXPECTED_PREFIX}L", bad)])
    out = _run(_svc(sess).list_completeness_scope_overrides("p-1"))
    assert out["overrides"] == [], f"conclusion={bad!r} 被当成已表态"


def test_list_skips_rows_without_cycle_suffix():
    sess = _WriteSession(list_rows=[
        _list_row(_EXPECTED_PREFIX, "Y"),          # 空 cycle
        _list_row("B50-T3-cycle-货币资金", "Y"),    # 前缀不符（LIKE 理论上不会返回，防御）
    ])
    assert _run(_svc(sess).list_completeness_scope_overrides("p-1"))["overrides"] == []


def test_list_without_b50_workpaper_returns_empty_not_error():
    """读回侧 B50 未建 → 空列表（读是只读路径，不该因未建底稿而报错）。"""
    sess = _WriteSession(wp_id=None)
    assert _run(_svc(sess).list_completeness_scope_overrides("p-1")) == {"overrides": []}


def test_list_and_reader_agree_on_same_rows():
    """同一批行经「面板读回」与「决策内核读取」得到一致的 `{cycle: sensitive}`。

    两者是不同函数（一个要理由与留痕、一个只要布尔），故必须有一条断言钉死它们
    在判据上不分叉 —— 分叉时面板会说「已确认」而裁剪判据仍按平台默认。
    """
    ctx = _ctx_mod()
    rows = [
        _list_row(f"{_EXPECTED_PREFIX}L", "Y"),
        _list_row(f"{_EXPECTED_PREFIX}E", "N"),
        _list_row(f"{_EXPECTED_PREFIX}F", "maybe"),
    ]
    panel = _run(_svc(_WriteSession(list_rows=rows)).list_completeness_scope_overrides("p-1"))
    panel_map = {o["cycle"]: o["sensitive"] for o in panel["overrides"]}

    class _CtxSession:
        async def execute(self, stmt, params=None):  # noqa: ANN001
            sql = str(stmt)
            if "wp_index" in sql:
                return _Res(scalar="b50-wp-uuid")
            return _Res(rows=rows)

    # 🔴 读取侧返回 `(override, degradations)` 二元组、只收 2 个位置参数 —— 首版按
    #    `(db, pid, degradations)` 三参调用，得 TypeError。这类形参错配正是本文件
    #    `TestRouterServiceKwargAgreement` 要在生产代码上防的同一类问题。
    reader_map, degradations = _run(ctx._load_completeness_override(_CtxSession(), "p-1"))
    assert degradations == [], f"正常读取路径不应记降级: {degradations!r}"
    assert reader_map == panel_map, (
        f"面板读回 {panel_map!r} 与决策内核读取 {reader_map!r} 判据分叉"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-3：router ↔ service 契约（AST）
# ═══════════════════════════════════════════════════════════════════════════
def _router_svc_calls() -> list[tuple[str, str, set[str], int]]:
    """抽取 router 里所有 `svc.X(...)` 调用 → (路由函数名, 方法名, kwargs, 位置参数个数)。"""
    tree = ast.parse(_ROUTER_PATH.read_text(encoding="utf-8"))
    out: list[tuple[str, str, set[str], int]] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "svc":
                kw = {k.arg for k in node.keywords if k.arg}
                out.append((fn.name, f.attr, kw, len(node.args)))
    return out


class TestRouterServiceKwargAgreement:
    """router 传给 service 的每个关键字都必须是该方法的真形参（反之必填的也不能漏）。

    🔴 这条守卫的由来：`reject_suggestions` 曾在 pydantic 模型写 `wp_codes`、而前端与
    service 用 `wp_index_codes`。两个后果都不在编译期报错 —— ① pydantic 默认忽略未知键
    ⇒ 前端传的键被丢掉、驳回恒 0 条；② router 用错名调 service ⇒ 运行时 TypeError。
    """

    def test_scan_face_is_not_empty(self):
        calls = _router_svc_calls()
        assert len(calls) >= 6, f"只抽到 {len(calls)} 个 svc 调用 —— AST 抽取失效（守卫空转）"
        assert {"set_completeness_scope_override", "clear_completeness_scope_override",
                "list_completeness_scope_overrides"} <= {c[1] for c in calls}, (
            "Task 14 的三个 service 方法未全部被 router 调用 —— 端点缺失或调错方法名"
        )

    def test_every_kwarg_exists_on_service_method(self):
        import inspect

        mod = _svc_mod()
        for route, method, kwargs, npos in _router_svc_calls():
            fnobj = getattr(mod.ProcedureTrimService, method, None)
            assert fnobj is not None, f"router 的 {route} 调了不存在的 service 方法 {method}"
            sig = inspect.signature(fnobj)
            names = {p for p in sig.parameters if p != "self"}
            unknown = kwargs - names
            assert not unknown, (
                f"{route} → {method} 传了不存在的关键字 {sorted(unknown)}；"
                f"该方法形参为 {sorted(names)}（运行时 TypeError → 500）"
            )

    def test_required_kwonly_params_are_all_supplied(self):
        import inspect

        mod = _svc_mod()
        for route, method, kwargs, npos in _router_svc_calls():
            sig = inspect.signature(getattr(mod.ProcedureTrimService, method))
            required = {
                name for name, p in sig.parameters.items()
                if p.kind is inspect.Parameter.KEYWORD_ONLY and p.default is inspect.Parameter.empty
            }
            missing = required - kwargs
            assert not missing, (
                f"{route} → {method} 漏传必填关键字 {sorted(missing)}（运行时 TypeError → 500）"
            )

    def test_body_attribute_access_matches_pydantic_fields(self):
        """路由函数里每个 `body.X` 都必须是其请求模型的真字段。

        pydantic 默认**忽略**未知键：模型少一个字段时，前端传的值被静默丢掉、
        `body.X` 取默认值 ⇒ 功能恒空转而无任何报错。
        """
        rmod = _router_mod()
        tree = ast.parse(_ROUTER_PATH.read_text(encoding="utf-8"))
        checked = 0
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            model_name = None
            for arg in list(fn.args.args) + list(fn.args.kwonlyargs):
                if arg.arg == "body" and isinstance(arg.annotation, ast.Name):
                    model_name = arg.annotation.id
            if not model_name:
                continue
            model = getattr(rmod, model_name, None)
            assert model is not None, f"{fn.name} 的 body 标注 {model_name} 不在 router 模块内"
            fields = set(getattr(model, "model_fields", {}))
            used = {
                n.attr for n in ast.walk(fn)
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "body"
            }
            unknown = used - fields
            assert not unknown, (
                f"{fn.name} 访问了 {model_name} 上不存在的字段 {sorted(unknown)}；"
                f"该模型字段为 {sorted(fields)}（pydantic 静默忽略未知键 ⇒ 恒空转）"
            )
            checked += 1
        assert checked >= 5, f"只校验了 {checked} 个 body 模型 —— AST 抽取失效（守卫空转）"


class TestCompletenessScopeEndpoints:
    """三个端点齐备 + 全部挂项目级 Delegator 守卫（fail-closed）。"""

    def _routes(self):
        rmod = _router_mod()
        return [
            (r.path, sorted(m for m in r.methods if m != "HEAD"), r)
            for r in rmod.router.routes
            if "completeness-scope" in getattr(r, "path", "")
        ]

    def test_three_methods_registered(self):
        got = {(p, tuple(m)) for p, m, _ in self._routes()}
        base = "/api/projects/{pid}/procedure-trim/completeness-scope"
        assert (base, ("GET",)) in got, f"缺 GET 端点，实有 {sorted(got)}"
        assert (base, ("PUT",)) in got, f"缺 PUT 端点，实有 {sorted(got)}"
        assert (base + "/{cycle}", ("DELETE",)) in got, f"缺 DELETE 端点，实有 {sorted(got)}"

    def test_all_three_have_delegator_guard(self):
        """守卫必须以依赖形式挂上 —— 三个端点都写库/读项目数据，缺一个就是越权入口。"""
        import inspect

        from app.services.procedure_authorization import require_project_delegator_pid

        for path, methods, route in self._routes():
            params = inspect.signature(route.endpoint).parameters
            deps = [
                p.default.dependency for p in params.values()
                if p.default is not inspect.Parameter.empty
                and hasattr(p.default, "dependency")
            ]
            assert require_project_delegator_pid in deps, (
                f"{methods} {path} 未挂 require_project_delegator_pid（fail-closed 403 守卫）"
            )

    def test_request_model_requires_reason(self):
        """请求模型层面理由必填（`min_length=1`）—— 与 service 的空白判断构成两道。"""
        rmod = _router_mod()
        model = rmod.CompletenessScopeOverrideRequest
        assert set(model.model_fields) == {"cycle", "sensitive", "reason"}
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            model(cycle="L", sensitive=True, reason="")
        ok = model(cycle="L", sensitive=True, reason="理由")
        assert ok.reason == "理由"

    def test_write_endpoints_commit_and_rollback(self):
        """写端点必须 `db.commit()`，且异常路径 `db.rollback()` 后重抛。"""
        code = _code_only(_ROUTER_PATH.read_text(encoding="utf-8"))
        for fn in ("trim_set_completeness_scope", "trim_clear_completeness_scope"):
            body = _func_src(code, fn)
            assert "await db.commit()" in body, f"{fn} 未 commit —— service 只 flush，改动不落库"
            assert "await db.rollback()" in body, f"{fn} 异常路径未 rollback"
            assert "raise" in body, f"{fn} 吞掉了异常（fail-open：前端会显示保存成功）"

    def test_read_endpoint_does_not_write(self):
        """GET 端点不得出现 commit / 写调用（只读路径）。"""
        code = _code_only(_ROUTER_PATH.read_text(encoding="utf-8"))
        body = _func_src(code, "trim_list_completeness_scope")
        assert "commit" not in body, "只读端点出现 commit"
        for verb in ("set_completeness_scope_override", "clear_completeness_scope_override"):
            assert verb not in body, f"只读端点调用了写方法 {verb}"


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-4：连库真写往返（2026-08-12 Task 26 浏览器实测暴露的缺陷 → 补此守卫）
#
# 🔴 为什么本文件此前 56 例全绿而 `PUT` 端点在真实库上恒 500：
#    写入行为的 9 例全部走 `_WriteSession` **替身**，而替身不做参数编码 ——
#    `CAST(:ts AS timestamptz)` 配 `now.isoformat()` 这个组合在替身里只是
#    「SQL 里有 updated_at、params 里有 ts」，两条断言都成立。
#    真实 asyncpg 才会报 `DataError: expected a datetime.date or datetime.datetime
#    instance, got 'str'` —— 因为写了 CAST 后该参数的推断类型即 timestamptz，
#    asyncpg 遂要求 datetime 对象。UUID 侧恰好相反（CAST 了就该传 str）。
#
#    ⇒ 「替身单测 + 源码级断言」这两层对**参数编码**类缺陷结构性无效，
#      必须有一条真跑。本组即那条，并配一条反向自检钉死上述 asyncpg 行为事实。
# ═══════════════════════════════════════════════════════════════════════════
#: 哨兵 cycle：不可能与任何真实覆盖冲突；且全程 rollback ⇒ 零写库。
_LIVE_SENTINEL_CYCLE = "ZZLIVETEST"


def _live_engine():
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")
    return create_async_engine(settings.DATABASE_URL, poolclass=NullPool)


_FIND_PROJECT_WITH_B50_SQL = """
SELECT wp.project_id
FROM working_paper wp
JOIN wp_index wi ON wp.wp_index_id = wi.id
WHERE wi.wp_code = 'B50'
LIMIT 1
"""


def test_live_write_roundtrip_insert_update_list_delete():
    """真实库上把三个 service 方法**真跑一遍**（末尾 rollback，零写库）。

    覆盖 INSERT / UPDATE / list 读回 / DELETE 四条路径。任一条的参数编码写错都会在
    这里抛 `DataError` 或 `ProgrammingError`，而替身单测与源码级断言都看不出来。

    🔴 事务全程不提交：末尾无条件 `rollback()`。守卫不得改动真实库 —— 但 rollback
    **不削弱**本条的判据强度：asyncpg 的参数编码发生在 `execute` 时刻（SQL 已发到 PG
    并执行），rollback 只撤销数据行，不撤销「编码是否合法」这个事实。
    """
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")

    mod = _svc_mod()
    ctx = _ctx_mod()
    item_id = ctx.COMPLETENESS_SCOPE_ITEM_PREFIX + _LIVE_SENTINEL_CYCLE

    async def _run():
        engine = _live_engine()
        try:
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with Session() as db:
                pid = (await db.execute(sa.text(_FIND_PROJECT_WITH_B50_SQL))).scalar_one_or_none()
                if pid is None:
                    return {"skip": "真实库中没有任何项目建过 B50 底稿"}
                actor = (await db.execute(sa.text(
                    "SELECT id FROM users ORDER BY created_at LIMIT 1"
                ))).scalar_one_or_none()
                if actor is None:
                    return {"skip": "真实库中没有任何用户（updated_by 外键无值可用）"}

                svc = mod.ProcedureTrimService(db)
                out: dict = {"pid": str(pid)}
                try:
                    # ① INSERT 路径
                    out["created"] = await svc.set_completeness_scope_override(
                        pid, cycle=_LIVE_SENTINEL_CYCLE, sensitive=False,
                        actor_user_id=actor, reason="[守卫] 连库真写往返，事务不提交",
                    )
                    # ② 同 cycle 再写一次 → UPDATE 路径
                    out["updated"] = await svc.set_completeness_scope_override(
                        pid, cycle=_LIVE_SENTINEL_CYCLE, sensitive=True,
                        actor_user_id=actor, reason="[守卫] 改判为敏感，验 UPDATE 分支",
                    )
                    # ③ 读回（真实 SQL + JOIN users）
                    listed = await svc.list_completeness_scope_overrides(pid)
                    out["listed"] = [
                        o for o in listed["overrides"]
                        if o["cycle"] == _LIVE_SENTINEL_CYCLE
                    ]
                    # ④ DELETE 路径
                    out["deleted"] = await svc.clear_completeness_scope_override(
                        pid, cycle=_LIVE_SENTINEL_CYCLE,
                    )
                    # ⑤ 事务内独立重读：确认删净（同事务可见性）
                    out["residual"] = (await db.execute(sa.text(
                        "SELECT count(*) FROM checklist_responses WHERE item_id = :i"
                    ), {"i": item_id})).scalar_one()
                finally:
                    await db.rollback()
                return out
        finally:
            await engine.dispose()

    try:
        res = _run_live(_run)
    except Exception as e:  # noqa: BLE001
        pytest.fail(
            f"连库真写往返抛异常 —— 这正是替身单测查不出的那类缺陷（参数编码 / 列名 / "
            f"外键）。原异常: {e!r}"
        )
    if "skip" in res:
        pytest.skip(res["skip"])

    assert res["created"] == {
        "cycle": _LIVE_SENTINEL_CYCLE, "sensitive": False,
        "created": True, "updated": False,
    }, f"INSERT 路径返回值异常: {res['created']!r}"
    assert res["updated"] == {
        "cycle": _LIVE_SENTINEL_CYCLE, "sensitive": True,
        "created": False, "updated": True,
    }, f"UPDATE 路径未命中（同 cycle 第二次写应走 UPDATE）: {res['updated']!r}"
    assert len(res["listed"]) == 1, f"读回未拿到哨兵行: {res['listed']!r}"
    got = res["listed"][0]
    assert got["sensitive"] is True, "读回的值不是 UPDATE 后的 Y —— 写读不同源"
    assert "改判为敏感" in (got["reason"] or ""), f"读回理由不对: {got['reason']!r}"
    assert got["updated_at"], "读回缺 updated_at —— 留痕列未真正写入"
    assert res["deleted"] == {"cycle": _LIVE_SENTINEL_CYCLE, "deleted": 1}, (
        f"DELETE 未删到那一行: {res['deleted']!r}"
    )
    assert res["residual"] == 0, f"删后仍有 {res['residual']} 行残留"


def _run_live(coro_factory):
    """跑连库协程；库不可达时 skip，其它异常原样抛（交由调用方 fail）。"""
    try:
        return asyncio.run(coro_factory())
    except Exception as e:  # noqa: BLE001
        text = repr(e)
        if any(k in text for k in (
            "could not connect", "Connect call failed", "does not exist",
            "password authentication", "Connection refused", "OperationalError",
        )):
            pytest.skip(f"真实库不可达（本条为连库判据）: {e!r}")
        raise


def test_live_timestamptz_cast_rejects_isoformat_string_reverse_self_check():
    """反向自检：`CAST($n AS timestamptz)` 传 **字符串** 必须被 asyncpg 拒绝。

    这条钉死上一条守卫赖以成立的**行为事实**。若哪天 asyncpg / SQLAlchemy 放宽了
    这个限制，本条会打红 ⇒ 提醒后续会话「那条连库守卫已不再针对原缺陷」，而不是让
    它悄悄退化成一条只验证 SQL 语法的空转断言。

    同时它也是对生产代码修法的说明：**写了 CAST 就必须传 datetime**。
    """
    from datetime import datetime, timezone

    async def _run():
        engine = _live_engine()
        try:
            async with engine.connect() as conn:
                # 正向：datetime 对象可编码
                ok = (await conn.execute(
                    sa.text("SELECT CAST(:ts AS timestamptz) AS v"),
                    {"ts": datetime.now(timezone.utc)},
                )).scalar_one()
                # 反向：isoformat 字符串必须抛
                err: str | None = None
                try:
                    await conn.execute(
                        sa.text("SELECT CAST(:ts AS timestamptz) AS v"),
                        {"ts": datetime.now(timezone.utc).isoformat()},
                    )
                except Exception as e:  # noqa: BLE001
                    err = repr(e)
                return {"ok": ok is not None, "err": err}
        finally:
            await engine.dispose()

    res = _run_live(_run)
    assert res["ok"], "datetime 对象都无法作为 timestamptz 参数 —— 连库环境异常"
    assert res["err"] is not None, (
        "`CAST(:ts AS timestamptz)` 竟接受了 isoformat 字符串 —— 驱动行为已变，"
        "上一条连库守卫不再针对原缺陷（原缺陷：写了 CAST 却传字符串导致 PUT 恒 500）"
    )
    assert "datetime" in res["err"] or "DataError" in res["err"], (
        f"报错形态与预期不符，请人工确认判据是否仍成立: {res['err']}"
    )


def test_write_side_passes_datetime_object_not_isoformat_string():
    """源码级：写入侧的 `ts` 参数**不得**是 `.isoformat()` 的结果。

    这一条与上面两条连库判据形成互补 —— 连库判据在库不可达时会 skip，本条不依赖库。
    但它单独不足以替代连库判据（它只查这一个已知形态；换成 `str(now)` 同样会炸而本条
    看不出）⇒ 三条并存，不删任何一条。
    """
    code = _code_only(_SVC_PATH.read_text(encoding="utf-8"))
    for fn in ("set_completeness_scope_override",):
        body = _func_src(code, fn)
        assert "CAST(:ts AS timestamptz)" in body, (
            f"{fn} 不再对时间戳参数显式 CAST —— 本条判据的前提已变，请同步更新"
        )
        assert 'now.isoformat()' not in body, (
            f"{fn} 又把 isoformat() 字符串传给 CAST(:ts AS timestamptz) —— "
            "asyncpg 会 DataError，端点恒 500（2026-08-12 已实测过一次）"
        )
        assert re.search(r'"ts"\s*:\s*now\s*,', body), (
            f"{fn} 的 ts 参数不是裸 datetime 对象（期望 `\"ts\": now,`）；"
            f"函数体片段: {body[:600]!r}"
        )
