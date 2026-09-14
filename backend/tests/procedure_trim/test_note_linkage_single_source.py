"""Task 21 守卫：程序裁剪 → 附注「本期不适用」反向联动的**单一真源**约束。

## 本文件要钉死的那一条

tasks.md 的守卫 bullet：「源码级断言不存在第二套不适用标注字段（只写 ``is_empty``，
判定只调既有共享 helper）」。这是本任务最承重的一条 —— 附注侧的"本期不适用"已由
``disclosure_notes.is_empty`` + ``note_content_utils.note_has_data`` 收敛为单一真源
（归档 spec ``disclosure-notes-selective-generation`` Req2 当初就是为消除「附注树标记
≠ Word 导出结果」的漂移）。本联动若新建第二个字段或第二份判定，漂移会立刻回来，
而且**两边各自的单测都会全绿** —— 只有交付件（Word）与界面（附注树）对不上才暴露，
那时已经出给客户了。

## 判据一律落在结构上，不落在"字符是否出现"

生产模块的 docstring **有意**写着 ``NoteSectionInstance.status`` / ``is_deleted`` /
``_render_as`` 等字样，用来记录"为什么不复用 ``note_trim_service``"。任何
``"is_deleted" not in src`` 形态的判据都会被这些**说明文字**打红（那是守卫缺陷不是
代码缺陷）⇒ 全部"必须不含"类断言先 ``_code_only()``，并配一条反向自检断言
raw 侧命中数 > clean 侧（剥注释哪天失效就打红）。

Spec: .kiro/specs/procedure-trimming-and-delegation-intelligence/ Task 21
Requirements: 13.1 13.2 13.3 13.4 13.5 13.6 13.7
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

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "backend"
LINKAGE_PY = BACKEND / "app" / "services" / "procedure_trim_note_linkage.py"
ROUTER_PY = BACKEND / "app" / "routers" / "procedure_trim.py"
CONTENT_UTILS_PY = BACKEND / "app" / "services" / "note_content_utils.py"
TRIM_SVC_PY = BACKEND / "app" / "services" / "procedure_trim_service.py"
MIGRATIONS = BACKEND / "migrations"


def _mod():
    """测试内 import；失败 ``fail`` 而非 ``skip``。

    顶层 import 失败会让整个文件 collection error、零断言执行 —— 那时"全红"既可能是
    功能没做也可能是守卫写坏，两者不可区分。
    """
    try:
        from app.services import procedure_trim_note_linkage as m
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"procedure_trim_note_linkage 无法 import: {exc!r}")
    return m


def _router_mod():
    try:
        from app.routers import procedure_trim as m
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"routers.procedure_trim 无法 import: {exc!r}")
    return m


# ═══════════════════════════════════════════════════════════════════════════
# 剥注释 / 截函数体 helper（与本目录既有守卫同实现，行为已被那边的自检覆盖）
# ═══════════════════════════════════════════════════════════════════════════
def _strip_py_comments(src: str) -> str:
    """只剥 ``#`` 注释，**保留**普通字符串字面量（SQL 就在引号里，剥掉判据全废）。"""
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
    """剥 ``#`` 注释**与全部 docstring**，保留普通字符串字面量。"""
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

    🔴 多行签名的 ``) -> X:`` 那行缩进可能 ≤ def 缩进，按「首个缩进 ≤ def 缩进的行即
    结束」会在签名处提前中断，截出来只有签名 ⇒ ``assert 'x' in body`` 恒假红。
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


def _raw() -> str:
    assert LINKAGE_PY.exists(), f"生产模块不存在：{LINKAGE_PY}"
    return LINKAGE_PY.read_text(encoding="utf-8")


def _code() -> str:
    return _code_only(_raw())


# ── helper 自检（4 条，均为"会骗过朴素写法"的构造输入）─────────────────────────
def test_selfcheck_strip_comments_keeps_sa_text_sql():
    """剥注释**不得**剥掉 ``sa.text`` 里的 SQL —— 本守卫多条断言就靠那段 SQL。"""
    src = (
        'q = sa.text(\n    "SELECT audit_cycle FROM procedure_instances "  # trailing note\n'
        '    "WHERE is_deleted = false"\n)\n'
    )
    out = _strip_py_comments(src)
    assert "trailing note" not in out, "未剥掉 # 注释"
    assert "procedure_instances" in out and "is_deleted = false" in out, (
        "误剥了字符串字面量 —— SQL 在引号里，剥掉后所有 SQL 类判据都会空转"
    )


def test_selfcheck_code_only_strips_docstring_but_keeps_strings():
    sample = (
        '"""模块 docstring 提到 NoteSectionInstance.status 作为设计留痕。"""\n'
        'SQL = "status = \'not_applicable\'"\n\n\ndef f():\n'
        '    """函数 docstring 也提到 NoteSectionInstance.status。"""\n'
        "    return SQL\n"
    )
    code = _code_only(sample)
    assert code.count("NoteSectionInstance") == 0, "docstring 未剥净 —— 说明文字会被数成真实引用"
    assert "status = 'not_applicable'" in code, "普通字符串字面量被误剥"
    assert sample.count("NoteSectionInstance") == 2, "自检样本已变，请同步更新"


def test_selfcheck_func_src_multiline_signature():
    src = (
        "def f(\n    a,\n    b,\n) -> dict:\n"
        '    """doc"""\n    return {"x": 1}\n\n'
        "def g():\n    pass\n"
    )
    body = _func_src(src, "f")
    assert 'return {"x": 1}' in body, f"多行签名截断失败: {body!r}"
    assert "def g" not in body, "越界截到了下一个函数"


def test_selfcheck_scan_surface_is_not_empty():
    """扫描面非空自检：正则/路径失效时下面所有"必须不含"类断言会静默恒绿。"""
    code = _code()
    assert len(code) > 3000, f"code-only 文本过短（{len(code)}）—— 疑似剥注释把代码剥掉了"
    assert "def resolve_linkage_plan" in code
    assert "async def apply_note_linkage" in code


# ═══════════════════════════════════════════════════════════════════════════
# 判据 A：不适用字段**单一真源** —— 只写 is_empty（本任务最承重的一条）
# ═══════════════════════════════════════════════════════════════════════════
def _assigned_attributes(code: str) -> set[str]:
    """模块里所有"被赋值的属性名"（``x.attr = ...`` 的 ``attr``）。"""
    tree = ast.parse(code)
    out: set[str] = set()
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Attribute):
                out.add(t.attr)
    return out


def test_a1_only_is_empty_and_lineage_are_ever_assigned():
    """**冻结**被赋值属性集合为恰三项。

    这是"不存在第二套不适用字段"的主判据：新增任何 ``note.xxx = ...`` 都会让集合变大
    ⇒ 打红。比 ``"not_applicable" not in src`` 强得多 —— 后者只要把字段起个别的名字
    （``na_by_trim`` / ``trim_excluded``）就绕过了。
    """
    got = _assigned_attributes(_code())
    expected = {
        "is_empty",          # 唯一的"不适用"持久化字段（附注侧既有真源）
        "template_lineage",  # provenance 面包屑，非判定字段（见 判据 C）
        "cycles_fully_trimmed",  # 分类结果 dataclass 的字段，与附注无关
    }
    assert got == expected, (
        f"被赋值属性集合变了：实得 {sorted(got)} / 冻结 {sorted(expected)}。\n"
        "新增字段即第二套不适用真源 —— 附注树标记与 Word 导出会漂移。"
    )


def test_a2_note_targeted_assignments_are_exactly_two():
    """具体到 ``note`` 这个变量上：只允许 ``is_empty`` 与 ``template_lineage``。"""
    tree = ast.parse(_code())
    on_note: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if (
                isinstance(t, ast.Attribute)
                and isinstance(t.value, ast.Name)
                and t.value.id == "note"
            ):
                on_note.add(t.attr)
    assert on_note == {"is_empty", "template_lineage"}, (
        f"对 note 的赋值集合 {sorted(on_note)} 不是恰 is_empty + template_lineage"
    )


def test_a3_does_not_use_note_trim_service_deleting_or_replacing_paths():
    """不得走 ``note_trim_service`` 的删章节 / 替段落 / 另一张状态表三条路（R13.2）。

    🔴 ``is_deleted`` 不能用裸 "must not contain"：它在**查询过滤**里有合法用途
    （``WHERE is_deleted = false`` / ``DisclosureNote.is_deleted == sa.false()``），
    首版那么写直接被自己的 SQL 打红 —— 那是判据缺陷不是代码缺陷。判据必须区分
    「读它做过滤」与「写它删章节」，故此处只禁**赋值形态**，赋值集合本身另由
    ``test_a1`` 冻结。
    """
    code = _code()
    for token in ("_render_as", "no_business_paragraph", "NoteSectionInstance"):
        assert token not in code, (
            f"代码里出现 {token!r} —— 那是 note_trim_service 的替段落/另一状态表路径，"
            "本联动只允许写 is_empty（R13.2 要求保留可恢复性）"
        )
    assert not re.search(r"\w+\s*\.\s*is_deleted\s*=[^=]", code), (
        "出现了 is_deleted 的赋值 —— 那会删章节，R13.2 明确禁止"
    )
    # 反向：确实用它做了过滤（否则会把已软删的章节也标注）
    assert "sa.false()" in code, "读取侧未过滤软删章节"
    assert "is_deleted = false" in code, "粗裁快照查询未过滤软删程序实例"


def test_a3_reverse_selfcheck_raw_mentions_forbidden_tokens():
    """反向自检：raw 侧**必须**提到那三个词（docstring 里记着"为什么不复用"）。

    否则上一条就是在空扫描面上恒绿 —— 剥注释这层防护无对象可防时必须被察觉。
    首版跑出 ``_render_as`` 在 raw 里也是 0：那时生产 docstring 只写了 ``is_deleted``
    一条路，自检如实报了"扫描面为空"。修法是把三条路都写进 docstring（后续会话最可能
    伸手去拿的正是那三个），而不是把自检的清单删短。
    """
    raw = _raw()
    code = _code()
    for token in ("is_deleted", "_render_as", "NoteSectionInstance"):
        assert raw.count(token) > code.count(token), (
            f"{token!r} 在 raw 与 code-only 里命中数相同（raw={raw.count(token)}）—— "
            "剥注释未生效或 docstring 里已不再记录设计理由，上一条断言已退化为空转"
        )


def test_a4_orm_has_no_second_not_applicable_column():
    """``DisclosureNote`` 上不得出现第二个"不适用"语义列（本任务零迁移）。"""
    from app.models.report_models import DisclosureNote

    cols = {c.name for c in DisclosureNote.__table__.columns}
    assert "is_empty" in cols, "附注真源列 is_empty 不存在（模型被改坏）"
    bad = {
        c for c in cols
        if re.search(r"not_applicable|procedure_trim|trim_excluded|trimmed", c)
    }
    assert not bad, (
        f"disclosure_notes 出现疑似第二套不适用列 {sorted(bad)} —— "
        "Task 21 要求复用 is_empty，不新建字段、不加迁移"
    )


def test_a5_no_migration_adds_not_applicable_column_to_disclosure_notes():
    """迁移目录里不得有给 ``disclosure_notes`` 加"不适用"列的语句。"""
    assert MIGRATIONS.exists(), f"迁移目录不存在：{MIGRATIONS}"
    files = sorted(MIGRATIONS.glob("V*.sql"))
    assert len(files) > 100, f"迁移文件数异常（{len(files)}）—— 扫描面可疑"
    pat = re.compile(
        r"ALTER\s+TABLE\s+disclosure_notes\s+ADD\s+COLUMN(?:\s+IF\s+NOT\s+EXISTS)?\s+(\w+)",
        re.I,
    )
    for f in files:
        for col in pat.findall(f.read_text(encoding="utf-8", errors="replace")):
            assert not re.search(r"not_applicable|procedure_trim|trim_excluded", col, re.I), (
                f"{f.name} 给 disclosure_notes 加了不适用类列 {col!r}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 B：判定**只调**既有共享 helper（不自己遍历 table_data）
# ═══════════════════════════════════════════════════════════════════════════
def test_b1_imports_and_calls_the_shared_helper():
    code = _code()
    assert "from app.services.note_content_utils import note_has_data" in code, (
        "未从 note_content_utils import 共享判定 helper —— 那是与 "
        "NoteWordExporter._has_content 收敛的单一真源"
    )
    body = _func_src(code, "note_has_manual_content")
    assert "note_has_data(" in body, "内容判定未调用共享 helper"


def test_b2_does_not_use_the_other_emptiness_modules():
    """不得引入另外三个"空判定"模块 —— 它们是不同概念，混用即第二份判据。

    - ``note_is_empty_calc``：带数值阈值的 *material* 判空，只服务 auto_trim_v2
    - ``note_empty_table_detector``：**投影后单表**判空，服务表级折叠
    - ``note_word_dynamic_styles``：Word 导出侧的 skip 判定（自带第三个 is_empty_table）
    """
    code = _code()
    for mod_name in (
        "note_is_empty_calc",
        "note_empty_table_detector",
        "note_word_dynamic_styles",
        "is_section_empty",
        "is_table_data_empty",
        "is_empty_table",
    ):
        assert mod_name not in code, (
            f"代码里引用了 {mod_name!r} —— 那是另一套判空口径，与 note_has_data 不同语义"
        )


def test_b3_no_own_table_data_traversal():
    """本模块不得出现自己遍历 ``table_data`` 的结构（那就是复制了一份判定）。"""
    code = _code()
    for token in ('"_tables"', '"cells"', '"rows"', "manual_value", "get(\"values\""):
        assert token not in code, (
            f"代码里出现 {token!r} —— 遍历 table_data 属 note_has_data 的职责，"
            "自己走一遍就是第二份判定口径"
        )


def test_b4_content_probe_bypasses_the_is_empty_short_circuit():
    """内容判定必须构造 ``is_empty=False`` 的投影再调 helper。

    ``note_has_data`` 首句是 ``if note.is_empty: return False``（对附注树是正确行为）。
    直接传真实 note 会让**已被本联动标过**的章节恒判"无内容" ⇒ 「标注后审计师又录了
    内容」永远发现不了，下一轮继续把它压在导出之外。
    """
    body = _func_src(_code(), "note_has_manual_content")
    assert re.search(r"is_empty\s*=\s*False", body), (
        "内容判定未把 is_empty 投影为 False —— helper 的短路会让判据自指、永远返回无内容"
    )


def test_b4_behavioural_marked_note_with_text_still_reports_content():
    """行为级：``is_empty=True`` 但有正文 → 必须判"有内容"（源码断言的独立证据）。"""
    m = _mod()
    note = SimpleNamespace(
        is_empty=True,
        text_content="审计师在标注之后补录的披露文字",
        table_data=None,
        template_lineage=None,
    )
    assert m.note_has_manual_content(note) is True
    blank = SimpleNamespace(is_empty=False, text_content="  ", table_data={"rows": []})
    assert m.note_has_manual_content(blank) is False


def test_b5_zero_and_dash_cells_are_not_content():
    """全 0 / ``-`` 的骨架不算内容（口径由共享 helper 决定，此处只锁行为）。"""
    m = _mod()
    note = SimpleNamespace(
        is_empty=False,
        text_content=None,
        table_data={"rows": [{"values": [0, "0", "-", None]}]},
    )
    assert m.note_has_manual_content(note) is False
    real = SimpleNamespace(
        is_empty=False, text_content=None, table_data={"rows": [{"values": [0, 123.45]}]}
    )
    assert m.note_has_manual_content(real) is True


# ═══════════════════════════════════════════════════════════════════════════
# 判据 C：provenance 面包屑**不是**不适用判据
# ═══════════════════════════════════════════════════════════════════════════
def test_c1_lineage_key_absent_from_the_pure_decision_function():
    """``resolve_linkage_plan``（唯一的"是否不适用"判定）不得引用面包屑。"""
    body = _func_src(_code(), "resolve_linkage_plan")
    assert "LINEAGE_KEY" not in body and "template_lineage" not in body, (
        "纯判定函数引用了 provenance —— 那会把「谁标的」变成「是否不适用」的判据，"
        "等于第二套不适用字段"
    )
    assert "was_marked_by_linkage" not in body, "纯判定函数引用了 provenance 读取器"


def test_c2_provenance_reader_used_only_on_the_revoke_side():
    """``was_marked_by_linkage`` 只能出现在撤销分支，不得参与标注决策。

    🔴 判据用 **AST** 定位 ``if v.verdict == "not_applicable":`` 这个 If 节点，断言
    provenance 读取器不在它的 body 里。首版用字符串下标排序，锚点之一
    (``verdict == applicable``) 只存在于**注释**里，而 ``_code_only`` 正好把注释剥掉
    ⇒ ``ValueError: substring not found``。判据锚在注释上就是判据缺陷。
    """
    code = _code()
    assert "was_marked_by_linkage" not in _func_src(code, "note_has_manual_content")
    classify = _func_src(code, "_classify")
    assert "was_marked_by_linkage" in classify, "撤销侧未做归属判断（会误撤审计师手工标注）"

    tree = ast.parse(_code())
    target: ast.If | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        cmp_ = node.test
        left, ops, rights = cmp_.left, cmp_.ops, cmp_.comparators
        if (
            isinstance(left, ast.Attribute) and left.attr == "verdict"
            and len(ops) == 1 and isinstance(ops[0], ast.Eq)
            and isinstance(rights[0], ast.Constant)
            and rights[0].value == "not_applicable"
        ):
            target = node
            break
    assert target is not None, (
        "未按 AST 找到 `verdict == \"not_applicable\"` 分支 —— 守卫解析失效，"
        "不是实现缺陷（判定分支结构变了请同步本断言）"
    )
    names = {
        n.id for n in ast.walk(target) if isinstance(n, ast.Name)
    } | {
        n.attr for n in ast.walk(target) if isinstance(n, ast.Attribute)
    }
    assert "was_marked_by_linkage" not in names, (
        "标注分支内读了 provenance —— 那会把「谁标的」变成「是不是不适用」的判据，"
        "等于第二套不适用字段"
    )
    assert "LINEAGE_KEY" not in names and "template_lineage" not in names, (
        "标注分支内读了 lineage 面包屑（同上）"
    )
    # 反向自检：该 If 节点确实覆盖了标注决策（否则上面几条在空节点上恒绿）
    assert {"already_marked", "to_mark", "conflicts"} <= names, (
        f"截到的 If 节点不含标注决策（实得 {sorted(names)[:12]}…）—— AST 定位到了错误分支"
    )


def test_c3_behavioural_breadcrumb_does_not_change_the_plan():
    """行为级：面包屑存在与否不改变纯判定输出（它压根不是判定输入）。"""
    m = _mod()
    scopes = [m.ScopeRow(cycle="J", wp_code="J1", status="not_applicable")]
    mapping = {"五、40": ["J1"]}
    a = m.resolve_linkage_plan(scopes=scopes, section_wp_map=mapping)
    b = m.resolve_linkage_plan(scopes=scopes, section_wp_map=mapping)
    assert [v.verdict for v in a.verdicts] == [v.verdict for v in b.verdicts] == ["not_applicable"]


def test_c4_provenance_reader_is_documented_as_non_criterion():
    """面包屑读取器必须自带"不是判据"的说明（防后续会话当判据用）。"""
    raw = _raw()
    doc = _func_src(raw, "was_marked_by_linkage")
    assert "provenance" in doc.lower(), "was_marked_by_linkage 未标注其 provenance 性质"


# ═══════════════════════════════════════════════════════════════════════════
# 判据 D：纯函数判定规则（两个合取项 + 保守性）
# ═══════════════════════════════════════════════════════════════════════════
def _plan(m, scopes, mapping):
    return m.resolve_linkage_plan(scopes=scopes, section_wp_map=mapping)


def test_d1_cross_cycle_section_needs_all_owners_trimmed():
    """🔴 跨循环共有章节：K3 已裁而 M1 在做 → ``五、42`` **不得**标注。

    registry 实测 ``五、42 → [K3, M1]``。只看"循环是否整体裁剪"会让「K 循环整体裁掉」
    把 M1 owner 的章节一并标成不适用 —— 那会让一段本应披露的内容从交付件消失。
    """
    m = _mod()
    mapping = {"五、42": ["K3", "M1"]}
    scopes = [
        m.ScopeRow(cycle="K", wp_code="K3", status="not_applicable"),
        m.ScopeRow(cycle="M", wp_code="M1", status="execute"),
    ]
    plan = _plan(m, scopes, mapping)
    assert [v.note_section for v in plan.by_verdict("not_applicable")] == []
    assert plan.cycles_fully_trimmed == ["K"], "K 循环应被判为整体裁剪"
    (v,) = plan.verdicts
    assert v.verdict == "applicable" and "M1" in v.narrative

    # 🔴 上面那组**证明不了** all-owners 合取项承重（变异检验实测 GREEN）：
    #    「这些循环都整体裁剪」⟹ 循环内每条 procedure_instances 都已裁 ⟹ 其中的 owner
    #    必然已裁。故第二合取项在正常输入上**蕴含**第一条，去掉第一条不改变结论。
    #
    #    第一合取项唯一真正承重的输入类 = **owner 行的 audit_cycle 为空**：`_load_scopes`
    #    把 NULL 显式转成 ""（`str(r[0] or "").strip()`），空 cycle 不进 `cycle_rows`
    #    ⇒ 该 owner 完全不被循环级判据覆盖。schema 允许（`audit_cycle` 无 NOT NULL、
    #    `(project_id, wp_code)` 无唯一约束），真实库当前 0 行如此 ⇒ 只能由构造输入钉死。
    #
    #    没有下面这组，「移除 all-owners 合取项」的变异恒绿，而它的后果是把一张仍需执行
    #    的底稿对应的附注章节标成"本期不适用"（内容从交付件消失）。
    blank_cycle_scopes = [
        m.ScopeRow(cycle="K", wp_code="K3", status="not_applicable"),
        m.ScopeRow(cycle="", wp_code="M1", status="execute"),
    ]
    plan2 = _plan(m, blank_cycle_scopes, mapping)
    assert plan2.cycles_fully_trimmed == ["K"], "空 cycle 行不应影响 K 的整体裁剪判定"
    assert plan2.by_verdict("not_applicable") == [], (
        "owner M1 的 audit_cycle 为空且仍需执行，却因「其余 owner 的循环已整体裁剪」被标成"
        "不适用 —— all-owners 合取项被绕过了"
    )
    (v2,) = plan2.verdicts
    assert v2.verdict == "applicable" and "M1" in v2.narrative


def test_d2_cross_cycle_section_marked_once_every_owner_trimmed():
    m = _mod()
    mapping = {"五、42": ["K3", "M1"]}
    scopes = [
        m.ScopeRow(cycle="K", wp_code="K3", status="not_applicable"),
        m.ScopeRow(cycle="M", wp_code="M1", status="skip"),
    ]
    plan = _plan(m, scopes, mapping)
    assert [v.note_section for v in plan.by_verdict("not_applicable")] == ["五、42"]


def test_d3_owner_trimmed_but_cycle_not_fully_trimmed_is_not_marked():
    """第二合取项：owner 已裁但**同循环还有别的程序在做** → 不标注（R13.1「整体裁剪」）。"""
    m = _mod()
    mapping = {"五、8": ["G2"]}
    scopes = [
        m.ScopeRow(cycle="G", wp_code="G2", status="not_applicable"),
        m.ScopeRow(cycle="G", wp_code="G4", status="execute"),
    ]
    plan = _plan(m, scopes, mapping)
    assert plan.by_verdict("not_applicable") == []
    assert plan.cycles_fully_trimmed == []
    (v,) = plan.verdicts
    assert "整体裁剪" in v.narrative, f"未说明未达整体裁剪的原因: {v.narrative}"


def test_d4_multiple_instances_per_wp_code_merge_as_and():
    """同一底稿多条程序：只要有一条未裁，该底稿就不算已裁（取最不利）。"""
    m = _mod()
    mapping = {"五、40": ["J1"]}
    scopes = [
        m.ScopeRow(cycle="J", wp_code="J1", status="not_applicable"),
        m.ScopeRow(cycle="J", wp_code="J1", status="execute"),
    ]
    plan = _plan(m, scopes, mapping)
    assert plan.by_verdict("not_applicable") == [], (
        "同一 wp_code 的多条程序按 OR 合并了 —— 有程序仍需执行却把章节标成不适用"
    )

    # 🔴 上面那组**证明不了** AND 合并承重（变异检验实测 GREEN）：两条都在 J 循环，
    #    只要有一条 execute，J 就不算整体裁剪 ⇒ 第二合取项已挡住，合并方向无关。
    #
    #    承重的输入类 = 同一 wp_code **跨循环**重复（schema 允许：`(project_id, wp_code)`
    #    无唯一约束）。J1 在 J 循环已裁（J 只有它 → J 整体裁剪），J1 在 X 循环仍需执行：
    #      AND 合并 → present[J1] 取未裁那条 → cycles=[X] → X 未整体裁剪 → 不标注 ✓
    #      OR  合并 → present[J1] 取已裁那条 → cycles=[J] → J 整体裁剪 → **误标** ✗
    cross_cycle_dup = [
        m.ScopeRow(cycle="J", wp_code="J1", status="not_applicable"),
        m.ScopeRow(cycle="X", wp_code="J1", status="execute"),
    ]
    plan2 = _plan(m, cross_cycle_dup, mapping)
    assert plan2.cycles_fully_trimmed == ["J"], "J 循环应被判为整体裁剪"
    assert plan2.by_verdict("not_applicable") == [], (
        "同一底稿跨循环重复时按 OR 合并了 —— 该底稿在 X 循环仍需执行，"
        "却因它在 J 循环已裁而把附注章节标成不适用"
    )


def test_d5_trimmed_statuses_match_the_platform_definition():
    """"已裁"取值域必须与 ``ProcedureTrimService.is_scope_trimmed`` 同口径。"""
    m = _mod()
    assert m.TRIMMED_SCOPE_STATUSES == frozenset({"skip", "not_applicable"})
    body = _func_src(_code_only(TRIM_SVC_PY.read_text(encoding="utf-8")), "is_scope_trimmed")
    found = set(re.findall(r'"(skip|not_applicable)"', body))
    assert found == {"skip", "not_applicable"}, (
        f"is_scope_trimmed 的取值域变成 {sorted(found)} —— 两侧口径漂移，"
        "被 skip 的底稿会算不算已裁在两处得出不同结论"
    )


def test_d6_execute_only_project_marks_nothing():
    """真实库现状（34 个项目 0 条已裁剪）：全 ``execute`` 时一条都不标。"""
    m = _mod()
    mapping = {"五、4": ["D1"], "五、5": ["D2"]}
    scopes = [
        m.ScopeRow(cycle="D", wp_code="D1", status="execute"),
        m.ScopeRow(cycle="D", wp_code="D2", status="execute"),
    ]
    plan = _plan(m, scopes, mapping)
    assert plan.by_verdict("not_applicable") == []


def test_d7_section_with_no_scope_row_is_skipped_not_marked():
    """owner 一条 ``procedure_instances`` 都没有 → 无判据可依，跳过（不是标注）。"""
    m = _mod()
    plan = _plan(m, [m.ScopeRow(cycle="D", wp_code="D1", status="skip")], {"五、99": ["Z9"]})
    assert plan.skipped_no_scope == ["五、99"]
    assert plan.verdicts == []


def test_d8_pure_function_has_no_io():
    """``resolve_linkage_plan`` 零 IO：无 ``await`` / 无 db / 无 import。"""
    body = _func_src(_code(), "resolve_linkage_plan")
    for token in ("await ", "db.", "sa.", "import ", "session"):
        assert token not in body, f"纯判定函数里出现 {token!r} —— 破坏零 IO，无法单测与变异"


def test_d9_real_registry_multi_owner_cross_cycle_fact_is_locked():
    """把"registry 里确实存在跨循环共有章节"这个事实钉死。

    判据 D1/D2 用的是构造映射；若真实 registry 哪天变成全 1:1，那两条就退化为
    假设性测试。此处对真实文件断言，使"为什么需要 all-owners 合取项"始终有实证。
    """
    from app.services.note_readiness_service import section_workpaper_map

    mapping = section_workpaper_map()
    assert len(mapping) > 100, f"registry section 数异常（{len(mapping)}）"
    multi = {s: v for s, v in mapping.items() if len(v) > 1}
    assert multi, "registry 已无多 owner 章节 —— 请复核 all-owners 合取项是否仍必要"
    cross = {
        s: v for s, v in multi.items() if len({c[0] for c in v}) > 1
    }
    assert cross, (
        "registry 已无**跨循环**共有章节 —— all-owners 合取项的实证消失，"
        "请复核判定规则（不要因此删掉该合取项）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 E：映射真源单一访问器（不自己读 registry JSON）
# ═══════════════════════════════════════════════════════════════════════════
def test_e1_uses_the_single_registry_accessor():
    code = _code()
    assert "from app.services.note_readiness_service import section_workpaper_map" in code, (
        "未经唯一访问器读 section→wp 映射"
    )


def test_e2_does_not_read_the_registry_json_directly():
    """不得自己 open/json.loads registry 文件（那是第二个读取口径）。"""
    code = _code()
    for token in ("note_workpaper_sync_registry", "json.loads", "read_text", "Path("):
        assert token not in code, (
            f"代码里出现 {token!r} —— registry 只准经 section_workpaper_map() 读取，"
            "自读会产生第二份解析口径（复数键 / 空白处理 / 大小写都可能分叉）"
        )


def test_e2_reverse_selfcheck_docstring_mentions_registry():
    raw = _raw()
    assert "note_workpaper_sync_registry" in raw, (
        "raw 侧连 docstring 都不提 registry —— 上一条断言的扫描面可疑"
    )
    assert "note_workpaper_sync_registry" not in _code()


# ═══════════════════════════════════════════════════════════════════════════
# 行为级替身（preview / apply 真跑一遍）
# ═══════════════════════════════════════════════════════════════════════════
class _Res:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return self._rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """按 SQL 文本分流两路：``procedure_instances`` 与 ``disclosure_notes``。"""

    def __init__(self, *, scope_rows, notes, raise_on: set[str] | None = None):
        self.scope_rows = scope_rows
        self.notes = notes
        self.raise_on = raise_on or set()
        self.flushes = 0

    async def execute(self, stmt, params=None):
        text = str(stmt)
        if "procedure_instances" in text:
            if "procedure_instances" in self.raise_on:
                raise RuntimeError("boom: procedure_instances")
            return _Res(self.scope_rows)
        if "disclosure_notes" in text:
            if "disclosure_notes" in self.raise_on:
                raise RuntimeError("boom: disclosure_notes")
            return _Res(self.notes)
        raise AssertionError(f"替身未覆盖的查询: {text[:200]}")

    async def flush(self):
        self.flushes += 1


class _Note:
    """最小 DisclosureNote 替身（属性访问与赋值语义与 ORM 一致即可）。"""

    def __init__(self, note_section, *, is_empty=False, text_content=None,
                 table_data=None, template_lineage=None, section_title="t"):
        self.note_section = note_section
        self.is_empty = is_empty
        self.text_content = text_content
        self.table_data = table_data
        self.template_lineage = template_lineage
        self.section_title = section_title


@pytest.fixture
def stub_env(monkeypatch):
    """把 registry 访问器与 ``flag_modified`` 换成可控替身。

    🔴 **不是 autouse**：首版设成 autouse，于是
    ``test_d9_real_registry_multi_owner_cross_cycle_fact_is_locked`` 拿到的是这个
    3 条的替身映射而不是真实 registry（139 条）⇒ 那条"对真实文件断言"的测试实际在
    断言替身，以「registry section 数异常（3）」的形态假红。替身的作用域必须与
    「要用替身的测试」精确对齐，否则会静默污染同文件里的实证类断言。

    ``flag_modified`` 对非 ORM 实例会抛，故替成 no-op；生产代码里它确实被调用由
    ``test_f12_flag_modified_is_called_for_jsonb`` 做源码级断言。
    """
    import app.services.note_readiness_service as readiness
    import sqlalchemy.orm.attributes as attrs

    monkeypatch.setattr(
        readiness, "section_workpaper_map", lambda: dict(_MAPPING), raising=True
    )
    monkeypatch.setattr(attrs, "flag_modified", lambda *_a, **_k: None, raising=True)


_MAPPING = {"五、40": ["J1"], "五、41": ["J2"], "五、42": ["K3", "M1"]}


def _run(coro):
    return asyncio.run(coro)


def _apply(session, *, year=2025, actor="11111111-1111-1111-1111-111111111111"):
    m = _mod()
    return _run(m.apply_note_linkage(session, "p-1", year, actor_user_id=actor))


def _preview(session, *, year=2025):
    m = _mod()
    return _run(m.preview_note_linkage(session, "p-1", year))


def _all_j_trimmed():
    return [("J", "J1", "not_applicable"), ("J", "J2", "not_applicable")]


def test_f1_marks_is_empty_and_writes_breadcrumb(stub_env):
    m = _mod()
    n1 = _Note("五、40")
    session = _FakeSession(scope_rows=_all_j_trimmed(), notes=[n1])
    out = _apply(session)
    assert out["marked"] == 1 and out["revoked"] == 0
    assert n1.is_empty is True
    assert isinstance(n1.template_lineage, dict)
    crumb = n1.template_lineage[m.LINEAGE_KEY]
    assert crumb["cycles"] == ["J"] and crumb["wp_codes"] == ["J1"]
    assert session.flushes == 1


def test_f2_preview_writes_nothing(stub_env):
    n1 = _Note("五、40")
    session = _FakeSession(scope_rows=_all_j_trimmed(), notes=[n1])
    out = _preview(session)
    assert out["summary"]["to_mark"] == 1
    assert n1.is_empty is False, "preview 改写了 is_empty —— 它必须只读"
    assert n1.template_lineage is None
    assert session.flushes == 0


def test_f3_note_with_content_is_only_reported_never_touched(stub_env):
    """R13.4：有内容 → 进 ``conflicts``，``is_empty`` 与内容都不动。"""
    n1 = _Note("五、40", text_content="审计师录入的披露正文")
    session = _FakeSession(scope_rows=_all_j_trimmed(), notes=[n1])
    out = _apply(session)
    assert out["marked"] == 0
    assert out["summary"]["conflicts"] == 1
    assert out["conflicts"][0]["reason"] == "has_content"
    assert n1.is_empty is False and n1.text_content == "审计师录入的披露正文"
    assert session.flushes == 0, "无写入却发了 flush"


def test_f3b_already_marked_note_that_gained_content_is_not_re_marked(stub_env):
    """已标过 + 后来有了内容 → 仍只进 conflicts，两个方向都不自动动。"""
    m = _mod()
    n1 = _Note(
        "五、40",
        is_empty=True,
        text_content="标注之后补录的内容",
        template_lineage={m.LINEAGE_KEY: {"at": "x"}},
    )
    session = _FakeSession(scope_rows=_all_j_trimmed(), notes=[n1])
    out = _apply(session)
    assert out["marked"] == 0 and out["revoked"] == 0
    assert out["conflicts"][0]["currently_marked"] is True
    assert n1.is_empty is True, "自动撤销了 —— 撤销同样是自动动作，R13.4 两个方向都禁"


def test_f4_revokes_only_its_own_mark_when_trim_undone(stub_env):
    """R13.3：裁剪撤销 → 标注相应撤销；面包屑被清掉。"""
    m = _mod()
    n1 = _Note("五、40", is_empty=True, template_lineage={m.LINEAGE_KEY: {"at": "x"}})
    session = _FakeSession(scope_rows=[("J", "J1", "execute")], notes=[n1])
    out = _apply(session)
    assert out["revoked"] == 1 and out["marked"] == 0
    assert n1.is_empty is False
    assert n1.template_lineage is None or m.LINEAGE_KEY not in n1.template_lineage


def test_f4b_preserves_other_lineage_keys_on_revoke(stub_env):
    m = _mod()
    n1 = _Note(
        "五、40",
        is_empty=True,
        template_lineage={m.LINEAGE_KEY: {"at": "x"}, "deletion_reason": "keep-me"},
    )
    session = _FakeSession(scope_rows=[("J", "J1", "execute")], notes=[n1])
    _apply(session)
    assert n1.template_lineage == {"deletion_reason": "keep-me"}, (
        "撤销时清掉了别人的 lineage 键（note_trim_service 的 deletion_reason 等）"
    )


def test_f5_does_not_revoke_a_user_marked_section(stub_env):
    """审计师手工标的"不适用"（无面包屑）不得被本联动撤销。"""
    n1 = _Note("五、40", is_empty=True, template_lineage=None)
    session = _FakeSession(scope_rows=[("J", "J1", "execute")], notes=[n1])
    out = _apply(session)
    assert out["revoked"] == 0
    assert n1.is_empty is True, "清掉了审计师手工标注 —— provenance 判断失效"
    assert out["skipped_foreign_mark"][0]["reason"] == "marked_by_user"


def test_f6_unlocatable_section_is_skipped_without_raising(stub_env):
    """R13.6：附注侧没有该章节行 → 跳过并记录，不抛。"""
    session = _FakeSession(scope_rows=_all_j_trimmed(), notes=[])
    out = _apply(session)
    assert out["marked"] == 0
    assert {i["note_section"] for i in out["unlocatable"]} == {"五、40", "五、41"}
    assert all(i["reason"] == "no_disclosure_note_row" for i in out["unlocatable"])


def test_f7_idempotent_second_run_writes_nothing(stub_env):
    n1 = _Note("五、40")
    session = _FakeSession(scope_rows=_all_j_trimmed(), notes=[n1])
    first = _apply(session)
    assert first["marked"] == 1
    second = _apply(session)
    assert second["marked"] == 0 and second["revoked"] == 0
    assert second["summary"]["already_marked"] == 1
    assert session.flushes == 1, "幂等第二轮仍发了 flush（有净写入）"


def test_f8_never_touches_table_data_or_text_content(stub_env):
    payload = {"rows": [{"values": [0]}]}
    n1 = _Note("五、40", table_data=payload, text_content=None)
    session = _FakeSession(scope_rows=_all_j_trimmed(), notes=[n1])
    _apply(session)
    assert n1.is_empty is True
    assert n1.table_data is payload, "改写了 table_data —— R13.2 要求保留模板结构"
    assert n1.text_content is None


def test_f9_registry_unavailable_degrades_without_raising():
    m = _mod()
    import app.services.note_readiness_service as readiness

    def _boom():
        raise RuntimeError("registry gone")

    orig = readiness.section_workpaper_map
    readiness.section_workpaper_map = _boom
    try:
        session = _FakeSession(scope_rows=_all_j_trimmed(), notes=[])
        out = _run(m.apply_note_linkage(session, "p-1", 2025))
        assert out["marked"] == 0
        assert out["degradations"] and out["degradations"][0]["stage"] == "registry"
    finally:
        readiness.section_workpaper_map = orig


def test_f10_empty_registry_degrades_and_marks_nothing():
    m = _mod()
    import app.services.note_readiness_service as readiness

    orig = readiness.section_workpaper_map
    readiness.section_workpaper_map = lambda: {}
    try:
        session = _FakeSession(scope_rows=_all_j_trimmed(), notes=[_Note("五、40")])
        out = _run(m.preview_note_linkage(session, "p-1", 2025))
        assert out["summary"]["to_mark"] == 0
        assert out["degradations"], "空映射未记降级 —— 会把「读不到映射」显示成「无可标注章节」"
    finally:
        readiness.section_workpaper_map = orig


def test_f11_preview_and_apply_share_one_classification(stub_env):
    """两条路径必须同源：同一输入下 preview 的分类与 apply 的分类逐键相等。"""
    n1 = _Note("五、40")
    n2 = _Note("五、41", text_content="有内容")
    pv = _preview(_FakeSession(scope_rows=_all_j_trimmed(), notes=[n1, n2]))
    ap = _apply(_FakeSession(
        scope_rows=_all_j_trimmed(),
        notes=[_Note("五、40"), _Note("五、41", text_content="有内容")],
    ))
    assert pv["summary"] == ap["summary"], (
        f"preview 与 apply 分类不一致：{pv['summary']} vs {ap['summary']} —— 双真源"
    )
    code = _code()
    assert _func_src(code, "preview_note_linkage").count("_classify(") == 1
    assert _func_src(code, "apply_note_linkage").count("_classify(") == 1


def test_f12_flag_modified_is_called_for_jsonb():
    """JSONB 列必须整体赋新 dict + ``flag_modified``，否则不发 UPDATE。"""
    code = _code()
    body = _func_src(code, "apply_note_linkage")
    assert body.count("flag_modified(note, \"template_lineage\")") == 2, (
        "标注与撤销两侧都必须 flag_modified —— 未声明 MutableDict 的 JSONB 就地改不标脏"
    )
    for fn in ("_lineage_with_mark", "_lineage_without_mark"):
        fb = _func_src(code, fn)
        assert "dict(lineage)" in fb, f"{fn} 未深拷贝构造新 dict"


# ═══════════════════════════════════════════════════════════════════════════
# 判据 G：router 契约（守卫 + 只读性 + 形参一致）
# ═══════════════════════════════════════════════════════════════════════════
def _routes():
    from app.main import app

    return [r for r in app.routes if "note-linkage" in getattr(r, "path", "")
            and "procedure-trim" in getattr(r, "path", "")]


def test_g1_both_endpoints_exist():
    got = {(sorted(r.methods)[0], r.path) for r in _routes()}
    assert got == {
        ("GET", "/api/projects/{pid}/procedure-trim/note-linkage"),
        ("POST", "/api/projects/{pid}/procedure-trim/note-linkage/apply"),
    }, f"端点集合不符：{sorted(got)}"


def test_g2_endpoints_are_delegator_gated():
    code = _code_only(ROUTER_PY.read_text(encoding="utf-8"))
    for fn in ("trim_note_linkage_preview", "trim_note_linkage_apply"):
        body = _func_src(code, fn)
        sig_start = code.index(f"def {fn}(")
        sig = code[sig_start: code.index("):", sig_start)]
        assert "require_project_delegator_pid" in sig, (
            f"{fn} 未挂项目级 Delegator 守卫 —— 越权可改附注章节的不适用标记"
        )
        assert body, f"{fn} 函数体为空（守卫解析失效）"


def test_g3_get_is_read_only_and_post_commits():
    code = _code_only(ROUTER_PY.read_text(encoding="utf-8"))
    get_body = _func_src(code, "trim_note_linkage_preview")
    assert "commit" not in get_body, "只读预览端点发了 commit"
    assert "preview_note_linkage" in get_body and "apply_note_linkage" not in get_body, (
        "预览端点调了 apply —— GET 变成写操作"
    )
    post_body = _func_src(code, "trim_note_linkage_apply")
    assert "apply_note_linkage" in post_body
    assert "await db.commit()" in post_body, "apply 端点未 commit（service 只 flush，会话关闭即回滚）"
    assert "await db.rollback()" in post_body, "apply 端点未在异常路径 rollback"


def test_g4_get_requires_year_and_apply_takes_year_from_body():
    """``year`` 必须显式要求：缺它就定位不到附注章节行，整份联动静默返空。"""
    code = _code_only(ROUTER_PY.read_text(encoding="utf-8"))
    sig_start = code.index("def trim_note_linkage_preview(")
    sig = code[sig_start: code.index("):", sig_start)]
    assert re.search(r"\byear\s*:\s*int\b", sig), "GET 端点未声明必需的 year 参数"
    assert not re.search(r"\byear\s*:\s*int\s*(?:\||=)", sig), "year 被写成可选/有默认值"

    rm = _router_mod()
    fields = rm.NoteLinkageApplyRequest.model_fields
    assert set(fields) == {"year"}, (
        f"apply 请求体字段集合为 {sorted(fields)} —— 不得让前端传章节清单"
        "（那会产生第二份判定口径，并与当下裁剪状态脱节）"
    )


def test_g5_router_service_kwarg_agreement():
    """router 调 service 的关键字必须与服务形参一致（AST 比对）。"""
    import inspect

    m = _mod()
    tree = ast.parse(ROUTER_PY.read_text(encoding="utf-8"))
    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        fname = node.func.id
        if fname not in ("preview_note_linkage", "apply_note_linkage"):
            continue
        params = set(inspect.signature(getattr(m, fname)).parameters)
        used = {kw.arg for kw in node.keywords if kw.arg}
        assert used <= params, (
            f"{fname} 被以不存在的形参 {sorted(used - params)} 调用 —— 运行时 TypeError → 500"
        )
        checked += 1
    assert checked == 2, f"只比对到 {checked} 个调用（预期 2）—— AST 提取失效"
