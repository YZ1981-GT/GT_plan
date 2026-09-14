# -*- coding: utf-8 -*-
"""底稿已录入批量探测守卫。

Feature: procedure-trimming-and-delegation-intelligence — Task 10
Requirements: 9.1, 9.2, 9.4, 9.5
Validates: Property 15（部分：探测侧）, Property 36

═══ 断言分两类（同 Wave 1 范式）═══

- **类 A = 独立口径判据**：本文件自己算出的事实（真实库键盘存、朴素判据与本模块判据的
  量化差距、批量化的源码结构、剥注释自检）。**现在就应全绿**。
- **类 B = 被测实现**：`probe_workpaper_entries` / `_detailed` 的行为。

🔴 禁在模块顶层 import 生产模块 —— 顶层 import 失败会让整个文件 collection error、
零断言执行，那时"全红"既可能是功能没做也可能是守卫写坏。改为测试内 try-import 后
`pytest.fail`（不是 skip）。
"""
from __future__ import annotations

import ast
import asyncio
import io
import re
import tokenize
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]  # backend/
_PROBE_PATH = _BACKEND / "app" / "services" / "workpaper_entry_probe.py"
_CTX_PATH = _BACKEND / "app" / "services" / "trim_decision_context.py"


def _probe_mod():
    """测试内 import；失败 fail 而非 skip（skip 会让缺陷静默）。"""
    try:
        from app.services import workpaper_entry_probe as mod
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import app.services.workpaper_entry_probe: {e!r}")
    return mod


# ═══════════════════════════════════════════════════════════════════════════
# 剥注释 helper（判据必须落在**代码**上，不能被 docstring / 注释里的说明文字骗）
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
    """剥 `#` 注释 **与全部 docstring**，保留普通字符串字面量（SQL 在三引号里）。

    🔴 为什么必须剥 docstring：本模块的 docstring **有意**写着「不是 ``workpaper_id``」
    「不走 ``procedure_instances.wp_id``」作为设计留痕，裸 `"workpaper_id" in src` 会把
    这些**说明文字**数成真实使用 ⇒ 判据在正确实现上打红（平台已登记的同族坑：守卫注释里
    的反例被数成真实调用）。

    普通字符串字面量**不剥** —— `_PROBE_SQL` 就是三引号字符串，剥掉判据全废。区分办法：
    只把「作为语句独占一行的字符串表达式」（即 docstring）当注释处理。
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
    return "\n".join(
        "" if (i + 1) in blank else ln for i, ln in enumerate(lines)
    )


def test_code_only_strips_docstrings_but_keeps_sql_literal():
    """🔴 `_code_only` 自检（双向）：剥掉 docstring、保留普通字符串字面量。"""
    sample = '''
"""模块 docstring 提到 workpaper_id 与 procedure_instances 作为反例留痕。"""
SQL = """
SELECT cr.wp_id FROM checklist_responses cr
"""


def f():
    """函数 docstring 也提到 workpaper_id。"""
    return SQL
'''
    code = _code_only(sample)
    # docstring 里的说明文字被剥掉
    assert "workpaper_id" not in code, "docstring 未被剥除 —— 说明文字会被数成真实使用"
    assert "procedure_instances" not in code
    # 普通字符串字面量（SQL）保留
    assert "cr.wp_id" in code, "普通字符串字面量被误剥 —— SQL 判据会全部失效"
    assert "checklist_responses" in code
    # 反向：原文里这些字样确实存在（证明扫描面非空、不是正则失效导致的空转）
    assert "workpaper_id" in sample and "procedure_instances" in sample


def test_probe_source_mentions_forbidden_names_only_in_prose():
    """反向自检：raw 侧必须有命中、code 侧必须无命中。

    若哪天 docstring 不再提这两个反例，本条会打红 —— 提醒「剥 docstring」这层防护
    已无对象可防，此时应确认另两条判据是否退化成空转。
    """
    raw = _PROBE_PATH.read_text(encoding="utf-8")
    code = _code_only(raw)
    for name in ("workpaper_id", "procedure_instances"):
        assert name in raw, (
            f"{name} 已不在源码文字中 —— 剥 docstring 的防护无对象可防，"
            "请确认列名/关联链判据仍有效（否则它们已成空转）"
        )
        assert name not in code, f"{name} 出现在**代码**里，不只是说明文字"


def _func_src(src: str, name: str) -> str:
    """按缩进截取函数体。

    🔴 先用**圆括号配对**跳过参数列表 —— 多行签名的 `) -> X:` 那行缩进为 0，
    按「首个缩进 ≤ def 缩进的行即结束」会在签名处提前中断，截出来只有签名，
    于是 `assert 'xxx' in body` 恒假红（平台已登记的同族坑）。
    """
    m = re.search(rf"^([ \t]*)(?:async\s+def|def)\s+{re.escape(name)}\s*\(", src, re.M)
    assert m, f"未找到函数声明 {name}（守卫解析失效，不是实现缺陷）"
    indent = len(m.group(1))
    # 圆括号配对跳过参数列表
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
    lines = src[body_start:].splitlines()
    out: list[str] = []
    for ln in lines:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent:
            break
        out.append(ln)
    return "\n".join(out)


def test_strip_comments_self_check():
    """反向自检：剥注释必须真剥掉 `#`，且**不得**剥掉字符串里的 SQL。"""
    src = 'X = """SELECT 1 -- inline"""  # real comment\nY = 2\n'
    out = _strip_py_comments(src)
    assert "real comment" not in out, "未剥掉 # 注释"
    assert "SELECT 1" in out, "误剥了字符串字面量（SQL 在三引号里，剥掉判据全废）"


def test_func_src_self_check_multiline_signature():
    """反向自检：多行签名不得让函数体截断成空。"""
    src = (
        "async def f(\n"
        "    db,\n"
        "    x: int,\n"
        ") -> dict:\n"
        '    """doc"""\n'
        "    return {'a': 1}\n"
        "\n"
        "def g():\n"
        "    pass\n"
    )
    body = _func_src(src, "f")
    assert "return {'a': 1}" in body, f"多行签名截断失败: {body!r}"
    assert "def g" not in body, "越界截到了下一个函数"


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-1：批量化（Property 36 / Requirement 9.4）
# ═══════════════════════════════════════════════════════════════════════════
def test_probe_issues_exactly_one_execute_at_source_level():
    """源码级：`_detailed` 函数体内 `db.execute(` 恰好出现一次。"""
    src = _strip_py_comments(_PROBE_PATH.read_text(encoding="utf-8"))
    body = _func_src(src, "probe_workpaper_entries_detailed")
    hits = re.findall(r"\bdb\.execute\s*\(", body)
    assert len(hits) == 1, f"期望恰好一次 db.execute，实为 {len(hits)} 次"


def test_probe_has_no_per_code_query_loop():
    """源码级：不存在「按 wp_code 循环发查询」的结构（Property 36）。

    判据 = 函数体内任何 `for` 之后不得再出现 `await db.execute` / `sa.text(`。
    """
    src = _strip_py_comments(_PROBE_PATH.read_text(encoding="utf-8"))
    body = _func_src(src, "probe_workpaper_entries_detailed")
    for m in re.finditer(r"^\s*for\s+", body, re.M):
        tail = body[m.start():]
        assert "db.execute" not in tail, "for 循环内出现 db.execute = 按码逐个查询"
        assert "sa.text(" not in tail, "for 循环内构造 SQL = 按码逐个查询"


def test_probe_sql_uses_expanding_bindparam_not_string_interpolation():
    """SQL 注入面：wp_code 清单必须走 expanding bindparam，禁字符串拼接。"""
    src = _strip_py_comments(_PROBE_PATH.read_text(encoding="utf-8"))
    assert 'expanding=True' in src, "wp_codes 未用 expanding bindparam"
    body = _func_src(src, "probe_workpaper_entries_detailed")
    assert not re.search(r'IN\s*\(\s*["\'].*\{', body), "疑似把 codes 拼进 SQL 字面量"


def test_checklist_criterion_requires_nonblank_content():
    """🔴 checklist 侧必须要求**内容非空**，不能「有行即有录入」（变异 M2 曾全绿逃逸）。

    真实库 `checklist_responses` 1,034,515 行里 **1,033,820 行 `conclusion`/`remark` 双空**
    （其中 1,033,230 行集中在一张 `C24` 底稿、仅 10 行有内容）⇒ 退化成「有行即有录入」
    会让 131 张有 checklist 行的底稿**全部**误判成已录入，底稿已录入保护随之把智能裁剪吃掉。

    判据落在 **code**（剥 docstring/注释）上，且同时钉死两个词 —— 只钉 `btrim` 会被
    「保留 btrim 但删掉 `<> ''` 比较」绕过。
    """
    code = _code_only(_PROBE_PATH.read_text(encoding="utf-8"))
    assert "checklist_responses" in code, "探测未查 checklist_responses"
    for token in ("btrim", "coalesce", "<> ''"):
        assert token in code, (
            f"checklist 判据缺少 {token!r} —— 疑似退化为「有行即有录入」，"
            "真实库会让 131 张底稿全部误判成已录入"
        )
    # 两个内容列都要参与判定（只判 conclusion 会漏掉只填 remark 的录入）
    assert "cr.conclusion" in code and "cr.remark" in code, (
        "conclusion / remark 必须都参与判定"
    )


def test_blank_only_checklist_rows_do_not_count_as_entry():
    """行为级：只有空白 checklist 行的底稿必须判 `False`（M2 的行为侧判据）。

    与上一条互补 —— 源码级断言挡「删掉谓词」，本条挡「谓词还在但语义写反」。
    """
    probe = _probe_mod()
    # 替身：SQL 已由被测模块构造，故这里改为直接验证 SQL 谓词对空白行不成立。
    # 用真实库上一个「有 checklist 行但全空白」的底稿做端到端判据（不可达时 skip）。
    snap = _live_blank_only_probe()
    if snap is None:
        pytest.skip("真实库不可达或无「仅空白 checklist 行」样本（本条为连库判据）")
    wp_code, has_entry, parsed_stripped_empty = snap
    if not parsed_stripped_empty:
        pytest.skip(
            f"样本 {wp_code} 的 parsed_data 剥系统键后非空，"
            "该底稿由 parsed_data 判为已录入，测不到 checklist 侧语义"
        )
    assert has_entry is False, (
        f"底稿 {wp_code} 只有空白 checklist 行且 parsed_data 剥空，"
        "却被判「已有录入」—— checklist 判据退化为「有行即有录入」"
    )


def test_probe_sql_avoids_correlated_exists_on_checklist():
    """🔴 实测 331 码的相关 EXISTS 在 C24（103 万行）上 30s 超时 ⇒ 必须用分组聚合。"""
    src = _strip_py_comments(_PROBE_PATH.read_text(encoding="utf-8"))
    assert "GROUP BY cr.wp_id" in src, "checklist 侧未用 GROUP BY 聚合"
    assert not re.search(r"EXISTS\s*\(\s*SELECT[^)]*checklist_responses", src, re.S), (
        "checklist_responses 上出现相关 EXISTS —— 实测在 C24 上会超时"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-2：真实列名（`checklist_responses` 的底稿外键是 `wp_id` 不是 `workpaper_id`）
#
# 🔴 这两条判据**必须剥 docstring**，不能只剥 `#` 注释：被测模块的 docstring 有意写着
#    「不是 ``workpaper_id``」「不走 ``procedure_instances.wp_id``」作设计留痕，裸
#    `in src` 会把这些**说明文字**数成真实用法 ⇒ 守卫在正确实现上假红，逼人删掉正是
#    下个会话需要的记载（平台已登记的同族坑）。
#    故用 `_code_only()`（tokenize 剥 `#` + AST 剥全部 docstring，**保留**普通字符串
#    字面量 —— `_PROBE_SQL` 就是普通字符串，是真正要扫的对象）。
# ═══════════════════════════════════════════════════════════════════════════
def test_probe_sql_uses_wp_id_not_workpaper_id():
    code = _code_only(_PROBE_PATH.read_text(encoding="utf-8"))
    assert "cr.wp_id" in code, "未使用 checklist_responses.wp_id"
    assert "workpaper_id" not in code, (
        "出现 workpaper_id —— checklist_responses 无此列，"
        "写错列名会抛 UndefinedColumnError 并被 fail-open 吞成「都没录入」"
    )


def test_probe_sql_casts_project_id_to_uuid():
    """asyncpg 按 VARCHAR 传参 ⇒ `uuid = character varying` 必炸，须显式 CAST。"""
    code = _code_only(_PROBE_PATH.read_text(encoding="utf-8"))
    assert re.search(r"CAST\s*\(\s*:pid\s+AS\s+uuid\s*\)", code, re.I), (
        "project_id 未显式 CAST 为 uuid"
    )


def test_probe_does_not_use_procedure_instances_wp_id():
    """`procedure_instances.wp_id` 实测仅 26/452 行非空 ⇒ 不得作为关联链。"""
    code = _code_only(_PROBE_PATH.read_text(encoding="utf-8"))
    assert "procedure_instances" not in code, (
        "走了 procedure_instances.wp_id —— 该列填充率 26/452，会让绝大多数底稿探测不到"
    )


def test_code_only_strips_docstrings_but_keeps_sql_string_literals():
    """判据本身的双向自检（防 `_code_only` 失效让上面三条变成空转）。

    正向：docstring 里的字样必须被剥掉；反向：普通字符串字面量（SQL）必须保留。
    """
    sample = (
        'def f():\n'
        '    """说明：不是 workpaper_id，也不走 procedure_instances。"""\n'
        '    # 注释里也提到 workpaper_id\n'
        '    return "SELECT cr.wp_id FROM checklist_responses"\n'
    )
    code = _code_only(sample)
    assert "workpaper_id" not in code, "_code_only 未剥掉 docstring/注释 —— 判据会假红"
    assert "procedure_instances" not in code
    assert "cr.wp_id" in code, "_code_only 误剥普通字符串字面量 —— 判据会空转"
    assert "checklist_responses" in code

    # 反向：真把列名写错时必须打红（证明判据不是恒真）
    bad = 'SQL = "SELECT cr.workpaper_id FROM checklist_responses"\n'
    assert "workpaper_id" in _code_only(bad), "真实错误列名未被判据捕获"


def test_probe_module_docstring_retains_column_name_warning():
    """反向锚定：被测模块的**原始**源码里必须仍有那两处留痕说明。

    上面三条改用 `_code_only` 后不再看 docstring ⇒ 若有人顺手把留痕删掉，判据不会红。
    本条把留痕本身钉死（它是下个会话不再踩同一坑的唯一依据）。
    """
    raw = _PROBE_PATH.read_text(encoding="utf-8")
    assert "workpaper_id" in raw, "模块 docstring 丢失「不是 workpaper_id」留痕"
    assert "procedure_instances" in raw, "模块 docstring 丢失「不走 procedure_instances」留痕"
    # 且它们只出现在 docstring/注释里（code 侧为零）——与上面三条互为镜像
    code = _code_only(raw)
    assert "workpaper_id" not in code
    assert "procedure_instances" not in code


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-3：系统副产键清单是判据真源（钉死 + 反向自检）
# ═══════════════════════════════════════════════════════════════════════════
# 真实库 parsed_data 键盘存（2026-08-09 实测，2798 行未软删）
_LIVE_PARSED_KEY_CENSUS: dict[str, int] = {
    "audit_checks": 341,
    "audit_checks_at": 341,
    "html_data": 73,
    "wp_code": 63,
    "generated_at": 63,
    "procedure_status": 15,
    "last_modified_by": 8,
    "changed_sheets_last_save": 8,
    "_version": 8,
    "last_modified_at": 8,
    "schema_version": 8,
}


def test_system_keys_cover_top_census_keys():
    """占比最大的系统副产键必须全在剥除清单内。"""
    mod = _probe_mod()
    declared = set(mod.SYSTEM_PARSED_DATA_KEYS)
    kept = set(mod.DELIBERATELY_KEPT_PARSED_DATA_KEYS)
    for key, rows in _LIVE_PARSED_KEY_CENSUS.items():
        if key in kept:
            continue
        assert key in declared, (
            f"系统副产键 {key!r}（真实库 {rows} 行）不在 SYSTEM_PARSED_DATA_KEYS ⇒ "
            f"该形态会被误判成「已录入」"
        )


def test_html_data_is_deliberately_kept_not_stripped():
    """`html_data` 是真录入落点 ⇒ 有意保留（方向安全的假阳性），不得进剥除清单。"""
    mod = _probe_mod()
    assert "html_data" in mod.DELIBERATELY_KEPT_PARSED_DATA_KEYS
    assert "html_data" not in mod.SYSTEM_PARSED_DATA_KEYS, (
        "html_data 被剥除 ⇒ grid / 自定义底稿的真实录入会被判成「无录入」而被裁"
    )


def test_system_keys_and_kept_keys_are_disjoint():
    mod = _probe_mod()
    overlap = set(mod.SYSTEM_PARSED_DATA_KEYS) & set(
        mod.DELIBERATELY_KEPT_PARSED_DATA_KEYS
    )
    assert not overlap, f"同一键既剥又留: {overlap}"


def test_system_keys_are_referenced_by_sql():
    """清单必须真的参与 SQL（否则是死常量、剥除从未发生）。"""
    src = _strip_py_comments(_PROBE_PATH.read_text(encoding="utf-8"))
    assert "SYSTEM_PARSED_DATA_KEYS" in _func_src(src, "probe_workpaper_entries_detailed"), (
        "SYSTEM_PARSED_DATA_KEYS 未在探测函数体内使用 = 死常量"
    )
    assert "parsed_data - string_to_array" in src, "SQL 未做键剥除"


# ═══════════════════════════════════════════════════════════════════════════
# 替身（按 SQL marker 分流，不靠表名 —— 该查询同时含三张表名）
# ═══════════════════════════════════════════════════════════════════════════
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows=None, *, raise_it: bool = False):
        self.rows = rows if rows is not None else []
        self.raise_it = raise_it
        self.calls: list[dict] = []

    async def execute(self, stmt, params=None):  # noqa: ANN001
        self.calls.append({"sql": str(stmt), "params": params or {}})
        if self.raise_it:
            raise RuntimeError("injected probe failure")
        return _FakeResult(self.rows)


def _r(wp_code, has_entry):
    return SimpleNamespace(wp_code=wp_code, has_entry=has_entry)


def _run(session, codes, pid="p-1"):
    mod = _probe_mod()
    return asyncio.run(mod.probe_workpaper_entries_detailed(session, pid, codes))


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-1：契约形态
# ═══════════════════════════════════════════════════════════════════════════
def test_every_requested_code_gets_explicit_boolean():
    """Requirement 9.1：未命中的 wp_code 必须显式补 False，不得缺键。

    缺键会让调用方无法区分「没有这张底稿」与「探测没覆盖到它」。
    """
    res = _run(_FakeSession([_r("D1", True)]), ["D1", "D2", "E1"])
    assert res.entries == {"D1": True, "D2": False, "E1": False}
    assert res.degraded is False


def test_single_execute_call_regardless_of_code_count():
    """Property 36：查询次数与 wp_code 数无关。"""
    mod = _probe_mod()
    for n in (1, 5, 50):
        sess = _FakeSession([])
        asyncio.run(
            mod.probe_workpaper_entries_detailed(sess, "p-1", [f"W{i}" for i in range(n)])
        )
        assert len(sess.calls) == 1, f"{n} 个 code 发了 {len(sess.calls)} 次查询"


def test_empty_codes_issues_no_query_and_is_not_degraded():
    sess = _FakeSession([])
    res = _run(sess, [])
    assert res.entries == {}
    assert res.degraded is False, "目标为空不是降级（调用方另行判断是否标注）"
    assert sess.calls == [], "空清单仍发了查询"


def test_codes_are_deduped_and_trimmed():
    sess = _FakeSession([])
    res = _run(sess, [" D1 ", "D1", "", None, "D2"])
    assert set(res.entries) == {"D1", "D2"}
    assert sess.calls[0]["params"]["codes"] == ["D1", "D2"]


def test_thin_wrapper_returns_plain_dict():
    mod = _probe_mod()
    out = asyncio.run(
        mod.probe_workpaper_entries(_FakeSession([_r("D1", True)]), "p-1", ["D1", "D2"])
    )
    assert out == {"D1": True, "D2": False}
    assert isinstance(out, dict)


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-2：失败兜底（Requirement 9.5）
# ═══════════════════════════════════════════════════════════════════════════
def test_query_failure_returns_all_true_and_degraded():
    """查询失败 → 全部 True（保守保留）+ degraded=True + reason 非空。"""
    res = _run(_FakeSession(raise_it=True), ["D1", "D2", "E1"])
    assert res.entries == {"D1": True, "D2": True, "E1": True}, (
        "失败时未保守保留 ⇒ 审计师已录入的底稿会被裁"
    )
    assert res.degraded is True
    assert res.reason and len(res.reason) >= 8


def test_failure_direction_is_conservative_not_permissive():
    """反向自检：若把兜底改成全 False，本条断言必须能抓到（钉死方向）。"""
    res = _run(_FakeSession(raise_it=True), ["D1"])
    assert all(res.entries.values()), "失败兜底方向反了（全 False = 全都可被裁）"


def test_sys_keys_param_is_passed_as_comma_joined_list():
    mod = _probe_mod()
    sess = _FakeSession([])
    asyncio.run(mod.probe_workpaper_entries_detailed(sess, "p-1", ["D1"]))
    sent = sess.calls[0]["params"]["sys_keys"].split(",")
    assert sent == list(mod.SYSTEM_PARSED_DATA_KEYS), "sys_keys 传参与常量不一致"


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-3：取数装配层接线（Task 9 的钩子已接上）
# ═══════════════════════════════════════════════════════════════════════════
def test_context_calls_detailed_variant_not_thin_wrapper():
    """🔴 装配层必须用 `_detailed` —— 薄壳丢弃 `degraded`，探测失败会被当成「都有录入」。"""
    src = _strip_py_comments(_CTX_PATH.read_text(encoding="utf-8"))
    body = _func_src(src, "_load_workpaper_entry")
    assert "probe_workpaper_entries_detailed" in body, (
        "装配层未调用 _detailed 变体 ⇒ 探测失败时 degradation 丢失"
    )


def test_context_records_degradation_when_probe_degraded():
    """探测降级时装配层必须记一条 degradation（否则前端不可区分）。"""
    src = _strip_py_comments(_CTX_PATH.read_text(encoding="utf-8"))
    body = _func_src(src, "_load_workpaper_entry")
    assert "degraded" in body, "装配层未消费 degraded 标记"
    assert "DIM_WORKPAPER_ENTRY" in body, "装配层未记 workpaper_entry 维度的 degradation"


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-4：连库判据（现在应绿）
#
# 🔴 一次 asyncio.run 取完全部快照 + 专用 NullPool 引擎：连接池绑定首个事件循环，
#    每个测试各自 async 会让第二个起报 "Event loop is closed"；借共享池会双向污染。
# ═══════════════════════════════════════════════════════════════════════════
_LIVE_SQL = """
SELECT
  count(*)                                                        AS wp_rows,
  count(*) FILTER (WHERE parsed_data IS NOT NULL
                     AND parsed_data <> '{}'::jsonb)              AS naive_nonempty,
  count(*) FILTER (WHERE (parsed_data - string_to_array(:sys,',')) <> '{}'::jsonb)
                                                                  AS after_strip
FROM working_paper WHERE is_deleted = false
"""


def _live():
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")

    mod = _probe_mod()
    sys_keys = ",".join(mod.SYSTEM_PARSED_DATA_KEYS)

    async def _run_live():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                row = (await conn.execute(sa.text(_LIVE_SQL), {"sys": sys_keys})).one()
                return dict(row._mapping)
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run_live())
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"真实库不可达（本条为连库判据）: {e!r}")


_LIVE_BLANK_ONLY_SQL = """
WITH cr AS (
  SELECT wp_id,
         count(*)                                                        AS n,
         count(*) FILTER (
           WHERE coalesce(btrim(conclusion), '') <> ''
              OR coalesce(btrim(remark), '')     <> ''
         )                                                               AS n_content
  FROM checklist_responses
  WHERE wp_id IS NOT NULL
  GROUP BY wp_id
)
SELECT w.id::text                                                        AS wp_id,
       coalesce(w.wp_code, '')                                           AS wp_code,
       w.project_id::text                                                AS project_id,
       ((w.parsed_data - string_to_array(:sys, ',')) = '{}'::jsonb)       AS parsed_stripped_empty
FROM cr
JOIN working_paper w ON w.id = cr.wp_id
WHERE cr.n > 0 AND cr.n_content = 0
  AND w.is_deleted = false
  AND ((w.parsed_data - string_to_array(:sys, ',')) = '{}'::jsonb)
LIMIT 1
"""


def _live_blank_only_probe():
    """真实库取一个「有 checklist 行但全空白 + parsed_data 剥空」的底稿，真跑探测。

    返回 ``(wp_code, has_entry, parsed_stripped_empty)``；样本不存在或库不可达返回
    ``None``（调用方 skip）。

    🔴 判据必须**真跑被测函数**而不是自己复算 SQL —— 自己复算等于拿守卫的实现证明
       守卫的实现（同族于平台已记的「不拿被测函数证明自己」，方向相反但同样无效）。
       这里的做法是：用独立 SQL **只负责找样本**，然后把样本喂给
       `probe_workpaper_entries`，断言它返回 False。

    🔴 专用 NullPool 引擎 + 同一 loop 内 dispose：不借共享连接池（避免
       `Event loop is closed` 双向污染），与 `_live()` 同款。
    """
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
    except Exception:  # noqa: BLE001
        return None

    mod = _probe_mod()
    sys_keys = ",".join(mod.SYSTEM_PARSED_DATA_KEYS)

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                row = (
                    await conn.execute(sa.text(_LIVE_BLANK_ONLY_SQL), {"sys": sys_keys})
                ).first()
            if row is None:
                return None
            m = dict(row._mapping)
            # 真跑被测函数（独立 session，同一 engine 同一 loop）
            async with AsyncSession(engine) as session:
                result = await mod.probe_workpaper_entries(
                    session, m["project_id"], [m["wp_code"]]
                )
            return (
                m["wp_code"],
                bool(result.get(m["wp_code"], False)),
                bool(m["parsed_stripped_empty"]),
            )
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception:  # noqa: BLE001
        return None


def test_live_strip_query_is_executable():
    """键剥除 SQL 在真实库可执行（真跑一次，异常即 skip 而非静默通过）。"""
    c = _live()
    assert c["wp_rows"] >= 0
    assert c["after_strip"] >= 0
    print(f"[live] parsed_data: {c}")


def test_live_strip_materially_narrows_naive_criterion():
    """🔴 量化证据：剥系统副产键后「已录入」数必须**显著少于**朴素判据。

    实测 410 → 86。若两者相等，说明剥除清单失效（或库中系统副产键形态已变），
    此时底稿已录入保护会退化成「几乎全部 keep」而无人察觉。
    """
    c = _live()
    if c["naive_nonempty"] == 0:
        pytest.skip("库中无非空 parsed_data，本条量化判据暂不可验证（⚠️ 不等于可省掉剥除）")
    assert c["after_strip"] < c["naive_nonempty"], (
        f"剥除未产生任何收窄（naive={c['naive_nonempty']} after={c['after_strip']}）⇒ "
        f"系统副产键清单可能已失效"
    )
