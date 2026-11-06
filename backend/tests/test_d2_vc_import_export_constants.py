"""D2-7 凭证检查表导入导出 —— 工作表名 / 表头常量前后端对拍。

Spec: .kiro/specs/d2-voucher-check-import-export-endpoints/ Task 1（design §2）

为什么需要这份守卫
------------------
导出由**后端**写表名与表头，导入由**前端**按工作表名找区、按表头认列
（``HEADER_TO_FIELD_MAP``）。两边差一个字，导入就会「未找到工作表」或整列被静默跳过。
既有的 ``test_d2_vc_import_export_endpoints.py`` 只把导出结果与**后端自己的**
``COLUMN_HEADERS`` 相比（自指），任一侧单独改名 / 改顺序它都不会红。本文件补上真正的
跨语言对拍：读前端 ``useD2VcImportExport.ts`` 源码里的字面量，与后端常量逐值、按顺序比对。

为什么两侧都用静态解析（不 import 后端模块）
--------------------------------------------
``_d2_vc_import_export.py`` 顶层 import 了 FastAPI / openpyxl / ``app.core.database`` /
``app.deps`` / ``app.models.core``；``from app.routers...import COLUMN_HEADERS`` 会把整条
重依赖链（含建数据库引擎）拉起来，而本守卫只需要三个字面量。所以后端侧用 ``ast``、前端侧用
自写的 TS 字面量分词器，**本模块零 ``app.*`` import**，不触发 ``app.main``、不建引擎或连接。

静态解析的弱点（有人把常量改成动态构造，AST 读到的就不是运行时值）由
``test_backend_constants_are_plain_literals`` 堵住：三个常量必须是纯字面量，改成表达式即红。
⇒ 在该断言成立的前提下，AST 取到的值与运行时值等价。运行时侧（导出产物真的写了这些值）由
``test_d2_vc_import_export_endpoints.py`` 覆盖，两份合起来形成完整链条。

分母非空
--------
解析抽不到值必须打红（两边都读成空、集合差集恒空 ⇒ 判据恒绿，是本仓反复踩过的坑）：
``test_frontend_literals_are_non_empty`` / ``test_backend_literals_are_non_empty`` 显式钉住
「表头恰 17 项、两个表名非空」；分词器自身另有正负样本自测
（``TestTsLiteralTokenizer``），分词器坏掉会独立打红而不是让对拍恒绿。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# ════════════════════════════════════════════════════════════════════
# 路径与常量名
# ════════════════════════════════════════════════════════════════════

_REPO = Path(__file__).resolve().parents[2]
_BACKEND_FILE = (
    _REPO / "backend" / "app" / "routers" / "wp_render_strategies"
    / "_d2_vc_import_export.py"
)
_FRONTEND_FILE = (
    _REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
    / "composables" / "useD2VcImportExport.ts"
)

#: design §2：17 列。两侧都必须恰好是这个数（分母非空 + 防增删列）。
_EXPECTED_HEADER_COUNT = 17

#: 后端常量名 → 前端常量名
_SHEET_NAME_PAIRS = (
    ("SHEET_CURRENT", "SHEET_NAME_CURRENT"),
    ("SHEET_POST", "SHEET_NAME_POST"),
)


# ════════════════════════════════════════════════════════════════════
# TS 字面量分词器
# ════════════════════════════════════════════════════════════════════

def strip_ts_comments(src: str) -> str:
    """剔除 TS 行注释 / 块注释，但**不动字符串字面量内部**。

    逐字符扫描并跟踪引号状态，所以 ``'http://example'`` 里的 ``//`` 不会被当成注释
    （整行被吞掉是静默丢数据，正是本仓要求规避的形态）。
    """
    out: list[str] = []
    i, n = 0, len(src)
    quote: str | None = None
    while i < n:
        ch = src[i]
        if quote is not None:
            out.append(ch)
            if ch == "\\" and i + 1 < n:          # 转义：原样带走下一个字符
                out.append(src[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _assignment_end(src: str, const_name: str) -> int:
    """返回 ``export const <const_name>...=`` 中 ``=`` 之后的下标。

    🔴 必须从 ``=`` **之后**开始找字面量 —— ``COLUMN_HEADERS: string[] = [...]`` 的类型
    标注里就有一对 ``[]``，从常量名之后直接找 ``[`` 会取到 ``string[]`` 的那一对、
    配平后得到空区间 ⇒ 对拍退化成空集比较而恒绿（本文件的分词器自测抓到过这个 bug）。
    """
    decl = re.search(rf"export\s+const\s+{re.escape(const_name)}\b[^=\n]*=", src)
    assert decl is not None, (
        f"前端 {_FRONTEND_FILE.name} 里找不到 `export const {const_name}` 的赋值；"
        "常量被改名 / 删除 / 不再导出，对拍守卫失去分母"
    )
    return decl.end()


def extract_literal_block(src: str, const_name: str, open_ch: str, close_ch: str) -> str:
    """取 ``export const <const_name> ... = <open_ch> ... <close_ch>`` 的字面量区间。

    括号**配平**扫描且跳过字符串内的括号 —— ``split(close_ch)`` 会在嵌套或字符串里提前
    截断（本仓已记教训）。找不到常量或括号不配平时抛 ``AssertionError``，绝不返回空串。
    """
    start = src.index(open_ch, _assignment_end(src, const_name))
    depth, i, n = 0, start, len(src)
    quote: str | None = None
    while i < n:
        ch = src[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return src[start + 1:i]
        i += 1
    raise AssertionError(
        f"前端 {const_name} 的 `{open_ch}...{close_ch}` 括号不配平，无法取出字面量区间"
    )


_TS_STRING = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|`([^`]*)`")
#: 对象键：带引号或裸标识符，后面紧跟 `:`（值是字符串但后面跟 `,`，据此区分键与值）
_TS_OBJ_KEY = re.compile(
    r"""(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"|([A-Za-z_$][\w$]*))\s*:"""
)


def _one_group(match: re.Match[str]) -> str:
    for g in match.groups():
        if g is not None:
            return g
    raise AssertionError(f"分词器未取到捕获组：{match.group(0)!r}")


def parse_ts_string_array(src: str, const_name: str) -> list[str]:
    """解析 ``export const X: string[] = ['a', 'b', ...]``，按源码顺序返回元素。"""
    block = extract_literal_block(strip_ts_comments(src), const_name, "[", "]")
    return [_one_group(m) for m in _TS_STRING.finditer(block)]


def parse_ts_object_keys(src: str, const_name: str) -> list[str]:
    """解析 ``export const X = { 'k': 'v', ... }``，按源码顺序返回键。"""
    block = extract_literal_block(strip_ts_comments(src), const_name, "{", "}")
    assert "{" not in block, (
        f"前端 {const_name} 出现嵌套对象，本分词器只支持扁平映射，判据可能失准 —— 请更新守卫"
    )
    return [_one_group(m) for m in _TS_OBJ_KEY.finditer(block)]


def parse_ts_string_const(src: str, const_name: str) -> str:
    """解析 ``export const X = 'literal'``。"""
    clean = strip_ts_comments(src)
    tail = clean[_assignment_end(clean, const_name):]
    match = _TS_STRING.match(tail.lstrip())
    assert match is not None, (
        f"前端 {const_name} 的值不是字符串字面量（取到 {tail[:40]!r}），无法静态对拍"
    )
    return _one_group(match)


# ════════════════════════════════════════════════════════════════════
# 后端常量（ast 静态读取）
# ════════════════════════════════════════════════════════════════════

def _backend_assignments() -> dict[str, ast.expr]:
    """模块级常量名 → 赋值表达式节点（``Assign`` 与 ``AnnAssign`` 都收）。"""
    tree = ast.parse(_BACKEND_FILE.read_text(encoding="utf-8"), filename=str(_BACKEND_FILE))
    out: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                out[node.target.id] = node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value
    return out


def _backend_str(name: str) -> str:
    node = _backend_assignments().get(name)
    assert node is not None, f"后端 {_BACKEND_FILE.name} 里找不到模块级常量 `{name}`"
    assert isinstance(node, ast.Constant) and isinstance(node.value, str), (
        f"后端 `{name}` 不是字符串字面量（{type(node).__name__}），静态对拍失效 —— 见本文件 docstring"
    )
    return node.value


def _backend_str_sequence(name: str) -> list[str]:
    node = _backend_assignments().get(name)
    assert node is not None, f"后端 {_BACKEND_FILE.name} 里找不到模块级常量 `{name}`"
    assert isinstance(node, (ast.Tuple, ast.List)), (
        f"后端 `{name}` 不是 tuple / list 字面量（{type(node).__name__}），静态对拍失效"
    )
    values: list[str] = []
    for elt in node.elts:
        assert isinstance(elt, ast.Constant) and isinstance(elt.value, str), (
            f"后端 `{name}` 含非字符串字面量元素（{ast.dump(elt)[:60]}），静态对拍失效"
        )
        values.append(elt.value)
    return values


@pytest.fixture(scope="module")
def frontend_src() -> str:
    assert _FRONTEND_FILE.is_file(), f"前端源码缺失：{_FRONTEND_FILE}"
    return _FRONTEND_FILE.read_text(encoding="utf-8")


# ════════════════════════════════════════════════════════════════════
# 1. 分母非空（解析抽不到值必须红）
# ════════════════════════════════════════════════════════════════════

def test_source_files_exist() -> None:
    assert _BACKEND_FILE.is_file(), f"后端源码缺失：{_BACKEND_FILE}"
    assert _FRONTEND_FILE.is_file(), f"前端源码缺失：{_FRONTEND_FILE}"


def test_frontend_literals_are_non_empty(frontend_src: str) -> None:
    """前端侧分母：表头恰 17 项、两个表名非空、映射恰 17 键。"""
    headers = parse_ts_string_array(frontend_src, "COLUMN_HEADERS")
    assert len(headers) == _EXPECTED_HEADER_COUNT, (
        f"前端 COLUMN_HEADERS 解析出 {len(headers)} 项，design §2 要求 17 列：{headers}"
    )
    assert all(h.strip() for h in headers), f"前端 COLUMN_HEADERS 含空表头：{headers}"
    assert len(set(headers)) == len(headers), f"前端 COLUMN_HEADERS 有重复表头：{headers}"

    for _, fe_name in _SHEET_NAME_PAIRS:
        value = parse_ts_string_const(frontend_src, fe_name)
        assert value.strip(), f"前端 {fe_name} 解析为空，对拍失去分母"

    keys = parse_ts_object_keys(frontend_src, "HEADER_TO_FIELD_MAP")
    assert len(keys) == _EXPECTED_HEADER_COUNT, (
        f"前端 HEADER_TO_FIELD_MAP 解析出 {len(keys)} 个键，应为 17：{keys}"
    )


def test_backend_literals_are_non_empty() -> None:
    """后端侧分母：表头恰 17 项、两个表名非空。"""
    headers = _backend_str_sequence("COLUMN_HEADERS")
    assert len(headers) == _EXPECTED_HEADER_COUNT, (
        f"后端 COLUMN_HEADERS 解析出 {len(headers)} 项，design §2 要求 17 列：{headers}"
    )
    assert all(h.strip() for h in headers), f"后端 COLUMN_HEADERS 含空表头：{headers}"
    assert len(set(headers)) == len(headers), f"后端 COLUMN_HEADERS 有重复表头：{headers}"

    for be_name, _ in _SHEET_NAME_PAIRS:
        assert _backend_str(be_name).strip(), f"后端 {be_name} 为空，对拍失去分母"


def test_backend_constants_are_plain_literals() -> None:
    """后端三个常量必须是纯字面量 ⇒ 静态读到的值 ≡ 运行时值（见本文件 docstring）。"""
    _backend_str("SHEET_CURRENT")
    _backend_str("SHEET_POST")
    _backend_str_sequence("COLUMN_HEADERS")


# ════════════════════════════════════════════════════════════════════
# 2. 前后端逐值对拍
# ════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(("backend_name", "frontend_name"), _SHEET_NAME_PAIRS)
def test_sheet_names_match(frontend_src: str, backend_name: str, frontend_name: str) -> None:
    """工作表名逐值一致。前端按表名找区，差一个字即「未找到工作表」。"""
    assert _backend_str(backend_name) == parse_ts_string_const(frontend_src, frontend_name), (
        f"工作表名漂移：后端 {backend_name}={_backend_str(backend_name)!r} vs "
        f"前端 {frontend_name}={parse_ts_string_const(frontend_src, frontend_name)!r}；"
        "改任一侧必须在同一次提交里改另一侧"
    )


def test_column_headers_match_in_order(frontend_src: str) -> None:
    """17 列表头**按顺序**逐值一致。

    必须是序列比较而不是集合比较 —— 后端按 ``COLUMN_HEADERS`` 顺序写导出列，
    交换两列顺序对集合差集不可见，却会让导出文件的列序与界面不符。
    """
    backend = _backend_str_sequence("COLUMN_HEADERS")
    frontend = parse_ts_string_array(frontend_src, "COLUMN_HEADERS")
    assert backend == frontend, (
        "表头常量漂移（逐值按顺序比对）：\n"
        + "\n".join(
            f"  第 {i + 1} 列: 后端 {b!r} vs 前端 {f!r}"
            for i, (b, f) in enumerate(zip(backend, frontend))
            if b != f
        )
        + (
            f"\n  长度不同：后端 {len(backend)} vs 前端 {len(frontend)}"
            if len(backend) != len(frontend) else ""
        )
    )


def test_header_to_field_map_covers_column_headers(frontend_src: str) -> None:
    """``HEADER_TO_FIELD_MAP`` 键集合 == ``COLUMN_HEADERS`` 集合。

    导入靠它按表头认列：映射里缺某个表头 ⇒ 该列被静默跳过；多出一个键 ⇒ 永远匹配不到。
    """
    headers = parse_ts_string_array(frontend_src, "COLUMN_HEADERS")
    keys = parse_ts_object_keys(frontend_src, "HEADER_TO_FIELD_MAP")
    assert set(keys) == set(headers), (
        f"HEADER_TO_FIELD_MAP 与 COLUMN_HEADERS 不匹配："
        f"映射缺 {sorted(set(headers) - set(keys))}，多出 {sorted(set(keys) - set(headers))}"
    )
    assert len(keys) == len(set(keys)), f"HEADER_TO_FIELD_MAP 有重复键：{keys}"


# ════════════════════════════════════════════════════════════════════
# 3. 分词器自测（防「两边都读成空而恒绿」）
# ════════════════════════════════════════════════════════════════════

class TestTsLiteralTokenizer:
    """分词器坏掉时独立打红，而不是让上面的对拍静默变成空集比较。"""

    _SAMPLE = """
    // 注释里的 COLUMN_HEADERS = ['不该被读到']
    export const SHEET_NAME_X = '甲区'
    /* 块注释 export const SHEET_NAME_X = '乙区' */
    export const COLUMN_HEADERS: string[] = [
      '第一列',  // 行尾注释
      '第二列',
      'http://keep/slashes',
    ]
    export const MAP: Record<string, string> = {
      '第一列': 'first',
      '第二列': 'second',
      'http://keep/slashes': 'third',
    }
    """

    def test_array_elements_parsed_in_order(self) -> None:
        assert parse_ts_string_array(self._SAMPLE, "COLUMN_HEADERS") == [
            "第一列", "第二列", "http://keep/slashes",
        ]

    def test_string_const_parsed(self) -> None:
        assert parse_ts_string_const(self._SAMPLE, "SHEET_NAME_X") == "甲区"

    def test_object_keys_parsed_not_values(self) -> None:
        assert parse_ts_object_keys(self._SAMPLE, "MAP") == [
            "第一列", "第二列", "http://keep/slashes",
        ]

    def test_double_slash_inside_string_is_not_treated_as_comment(self) -> None:
        """``http://`` 不得被当成行注释（否则整行被吞、静默丢元素）。"""
        kept = strip_ts_comments("const a = 'http://x'  // real comment\n")
        assert "http://x" in kept
        assert "real comment" not in kept

    def test_missing_constant_raises_instead_of_returning_empty(self) -> None:
        with pytest.raises(AssertionError, match="NOT_THERE"):
            parse_ts_string_array(self._SAMPLE, "NOT_THERE")
        with pytest.raises(AssertionError, match="NOT_THERE"):
            parse_ts_string_const(self._SAMPLE, "NOT_THERE")
