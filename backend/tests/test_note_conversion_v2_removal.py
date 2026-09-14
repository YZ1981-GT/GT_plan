"""v2 孤儿函数删除的收口守卫 — Property 24 / 25 / 26.

spec: soe-listed-note-conversion-correctness / Task 10（Requirements 6.1, 6.3, 6.4）

------------------------------------------------------------------------------
裁决：删除 ``convert_disclosure_notes_v2`` / ``preview_conversion_v2``
------------------------------------------------------------------------------

Task 10 的标题写「接线，优先方案」，但那条建议写在 Task 8 之前 —— Task 8/9 已把
正确骨架实现在**生产路径** ``_map_disclosure_notes`` 上，前提已变。逐条实证：

1. **生产路径已接通**：``execute_conversion`` Step 4 调
   ``self._map_disclosure_notes(...)`` 并取其 ``["mapped"]`` 作 ``mapped_notes``。
2. **v2 生产零调用方**：全仓引用只剩本模块自身的 docstring/注释 + 测试。四个
   router（``note_conversion`` / ``standard_conversion``）与 ``event_handlers``
   调的都是 ``preview_conversion`` / ``execute_conversion`` / ``rollback_conversion``。
3. **v2 的三个缺陷已在生产路径上被正确实现**（故「修 v2 三缺陷」无对象）：
   定位键按侧取（``_build_section_mapping_plan`` 的 ``f"{src_side}_section_id"``）、
   ``format_adapted`` 走 ``report.changed`` 事实判据、共有章节真改写
   ``section_id`` + ``note_section``。
4. **生产路径严格更强**：v2 缺别名桥接 / ``binding_id`` 前缀改写 /
   ``section_id IS NULL`` 回填 / 章节号占用检查 / 逐章 savepoint 隔离 /
   ``user_edits_dropped`` 红线告警；且 v2 自带一个缺陷 ——
   ``note_section=sid  # legacy compat`` 把展示用章节号写成 slug。
5. **接线会造双真源**：让 ``execute_conversion`` 再调一次 v2 等于两份实现并存；
   把 v2 改成 delegate 薄壳则它自己成为无调用方的转发层，Property 24 仍红。

⇒ 删除，且按 Requirement 6.3 **先迁移测试断言**（见下方迁移对照表）。

------------------------------------------------------------------------------
本文件的三组断言
------------------------------------------------------------------------------

* ``TestNoOrphanConversionFunctions``  — Property 24：转换服务里每个
  ``convert_*`` / ``_map_*`` 方法都有非测试调用方
* ``TestV2SymbolsFullyRemoved``       — **代码级**引用归零（docstring/注释里的
  留证说明登记进 ``DOCSTRING_ONLY_MENTIONS``，见下）
* ``TestAssertionMigrationComplete``  — Property 26：v2 的 21 个测试的断言
  在生产路径测试里逐条有对应覆盖，且覆盖更强
* ``TestProductionOnlyTests``          — 反向：生产测试里不得有「无人指向」的
  函数，新增能力登记进 ``PRODUCTION_ONLY_TESTS`` 并写明对应 Requirement

------------------------------------------------------------------------------
为什么引用扫描必须是「代码级」而不是全文
------------------------------------------------------------------------------

删除决策本身要留证 —— 服务模块的 docstring 写明「v2 已删除（生产零调用方…）」、
两个测试文件的 docstring 写明「承接已删除的 v2 全部断言」、一条断言消息把
「note_section 写成 sid」标注为「那是 v2 的缺陷形态」。这些**说明文字**是资产
不是残留；裸 ``symbol in source`` 会把它们数成 offender ⇒ 守卫对正确状态恒红。

⇒ 判据改为：``tokenize`` 剥 ``#`` 注释 + ``ast`` 剥 docstring，只在**剩余代码**
里禁止出现 v2 符号；文字提及逐条登记 ``DOCSTRING_ONLY_MENTIONS``，并配双向自检
（登记项必须真含该字样 / 真有代码级引用的替身必须打红 / 条目数只许缩短）。
"""
from __future__ import annotations

import ast
import io
import os
import pathlib
import re
import tokenize
import warnings

import pytest


# ---------------------------------------------------------------------------
# 仓库/backend 根：双哨兵文件向上查找，禁写死回退级数
# ---------------------------------------------------------------------------

def _find_backend_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for cand in [here.parent, *here.parents]:
        if (cand / "data" / "note_template_soe.json").is_file() and (
            cand / "app" / "services" / "note_conversion_service.py"
        ).is_file():
            return cand
    raise AssertionError("未能定位 backend/ 根（缺哨兵文件）")


BACKEND = _find_backend_root()
REPO = BACKEND.parent
CONVERSION_SERVICE = BACKEND / "app" / "services" / "note_conversion_service.py"
PRODUCTION_TEST = BACKEND / "tests" / "services" / "test_note_conversion_section_mapping_production.py"

#: 被删除的 v2 符号
REMOVED_SYMBOLS: tuple[str, ...] = (
    "convert_disclosure_notes_v2",
    "preview_conversion_v2",
)

#: 扫描面：生产代码 + 测试 + 脚本（排除 spec 文档 —— 那里保留删除决策的记载）
_SCAN_DIRS: tuple[pathlib.Path, ...] = (
    BACKEND / "app",
    BACKEND / "tests",
    BACKEND / "scripts",
)

#: 允许残留引用的文件（本守卫自身必须提到这些名字才能断言它们消失）
_REFERENCE_ALLOWLIST: frozenset[str] = frozenset({
    pathlib.Path(__file__).name,
})

#: 只在 docstring / 注释 / 断言消息里提及 v2 符号的文件 —— **有意留证**。
#:
#: 每条 ``(相对路径, 为什么要留证)``。判据是**代码级**扫描（剥注释 + 剥 docstring），
#: 故这些文件不会被 ``test_no_reference_anywhere`` 打红；本表的价值在于：
#:
#: * 双向自检 ①：登记的文件必须**确实**含该字样 —— 否则条目 stale，应移出
#: * 双向自检 ②：条目数封顶且只许缩短 —— 防「往表里再加一条」绕过守卫
#: * 一旦某个登记文件出现**代码级**引用（真调用/真定义），仍会被打红
DOCSTRING_ONLY_MENTIONS: tuple[tuple[str, str], ...] = (
    (
        "backend/app/services/note_conversion_service.py",
        "``_map_disclosure_notes`` 的 docstring 写明「v2 已删除（生产零调用方 + "
        "三缺陷已在本方法修好 + 断言已迁移）」+「不要再造第二份章节转换实现」。"
        "删掉这段留证，下个会话会重新提「接线 v2」或另造一份实现。",
    ),
    (
        "backend/tests/services/test_note_conversion_section_mapping_production.py",
        "模块 docstring 是 21 条断言的迁移对照表（Requirement 6.3 的落点证明），"
        "必须写出源测试所属的 v2 方法名；另 L533 的断言消息把「note_section 写成 "
        "sid」标注为「那是 v2 的缺陷形态」—— 那是断言加强的理由，删了看不懂为何要断。",
    ),
    (
        "backend/tests/test_note_template_diff_integrity.py",
        "两处 docstring：L58 记载「v2 的 step 6 读 fd['section_id'] 恒 None ⇒ "
        "format_adapted_count 恒 0」（Requirement 1.4 选项 A 的实证依据）；L1113 "
        "说明该守卫的标的已由 v2 换成 ``_map_disclosure_notes``。",
    ),
)

#: 登记条目上限：只许缩短，不许增长（新增留证需先在此显式提高上限并说明）
_DOCSTRING_MENTION_LIMIT: int = 3


def _module_docstring_spans(source: str) -> set[int]:
    """返回全部 docstring（模块/类/函数 + 裸字符串表达式语句）占据的行号集合。

    ``ast.get_docstring`` 只覆盖三类节点的首个字符串；模块里还可能有独立的
    ``ast.Expr(Constant(str))`` 语句（多段说明文字），一并纳入。
    """
    rows: set[int] = set()
    try:
        # 抑制被扫文件自身的旧式转义告警（`'\%'` / `'\d'` 等）——
        # 那是被扫文件的既有问题，让它刷屏会掩盖本守卫的真实信号
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source)
    except SyntaxError:
        return rows
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            start = value.lineno
            end = value.end_lineno or start
            rows.update(range(start, end + 1))
    return rows


def _blank_docstring_rows(stripped: str, doc_rows: set[int]) -> str:
    """把 ``doc_rows`` 指定的行整行置空（保留换行，行号不漂移）。

    抽成独立函数只为**单一实现** —— ``_code_level_source``（一次算完）与
    ``read_code_level``（复用已缓存的 stripped）两条路径共用它，
    否则同一「剥 docstring」语义两处实现即双真源，
    ``TestSourceCacheSelfCheck`` 的逐字节相等会变成运气。
    """
    if not doc_rows:
        return stripped
    lines = stripped.splitlines(keepends=True)
    for row in doc_rows:
        idx = row - 1
        if 0 <= idx < len(lines):
            lines[idx] = "\n" if lines[idx].endswith("\n") else ""
    return "".join(lines)


def _code_level_source(source: str) -> str:
    """剥掉 ``#`` 注释与全部 docstring，只留「真代码」。

    普通字符串字面量（字典键名、断言消息里的普通串）**不剥** —— 那些可能是真消费。
    但独立的 docstring 语句一律剥掉。
    """
    return _blank_docstring_rows(_strip_comments(source), _module_docstring_spans(source))


def _strip_comments(source: str) -> str:
    """剥掉 ``#`` 注释（token 级）。docstring 是字符串字面量，**不会**被剥掉。"""
    lines = source.splitlines(keepends=True)
    spans: list[tuple[int, int, int]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                spans.append((tok.start[0], tok.start[1], tok.end[1]))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return "".join(line.split("#", 1)[0] + "\n" for line in source.splitlines())
    for row, col_start, col_end in sorted(spans, reverse=True):
        idx = row - 1
        line = lines[idx]
        lines[idx] = line[:col_start] + " " * (col_end - col_start) + line[col_end:]
    return "".join(lines)


# ---------------------------------------------------------------------------
# 按文件路径的模块级备忘（memoization）
# ---------------------------------------------------------------------------
#
# 为什么需要：``_code_level_source`` / ``_strip_comments`` 的输入是**全仓 .py**
# （实测 4553 文件 / 44.8 MB，单遍 11.86s），而本文件与
# ``test_note_conversion_section_mapping.py`` 合计有 10 个用例各自跑一遍全仓扫描
# （实测前 9 名最慢用例合计 ~74s / 全组 81.7s）。同一输入重复计算 10 次是唯一瓶颈。
#
# 🔴 缓存键为什么必须含 mtime_ns + size 而不能只用路径：
# 同一 pytest 进程内文件理论上不变，但**变异检验脚本**
# （``mutate_note_conversion_section_mapping_guards.py`` 等）的工作方式是
# 「改文件 → 跑测试 → 还原」。若将来有人把变异与测试放进同一进程（或有人在会话内
# 改了源码再重跑），纯路径键会返回**过期结果** ⇒ 变异检验静默变假绿，
# 比「跑得慢」严重得多。
#
# 为什么选 (path, mtime_ns, size) 而不是内容哈希：内容哈希要先把文件读进来
# （读盘本身就是 11.86s 里的主要成本），等于把想省掉的开销又付一遍；而
# ``os.stat`` 只取元数据，比 ``read + sha256`` 便宜一个数量级。纳秒级 mtime
# 与 size 双因子足以覆盖「文件被改写」这一形态（变异脚本一律整文件重写）。
#
# 语义变化仅限「同一输入不再重复计算」—— 判据、扫描面、排除规则一律不动。
# 「命中与未命中产出逐字节相同」由 ``TestSourceCacheSelfCheck`` 钉死。

_CodeCacheKey = tuple[str, int, int]

_CODE_LEVEL_CACHE: dict[_CodeCacheKey, str] = {}
_STRIPPED_CACHE: dict[_CodeCacheKey, str] = {}


def _cache_key(path: pathlib.Path) -> _CodeCacheKey:
    st = path.stat()
    return (str(path), st.st_mtime_ns, st.st_size)


def read_code_level(path: pathlib.Path) -> str:
    """``_code_level_source(path.read_text())`` 的带缓存版本（按文件内容标识）。

    🔴 复用 ``read_stripped`` 而不是自己再调一次 ``_strip_comments``：
    ``_code_level_source`` 的定义就是「先剥注释、再把 docstring 行置空」，
    两个取值入口各剥一遍 = 同一份 tokenize 对全仓做两次（实测 4553 文件 /
    44.8 MB 下 ``_strip_comments`` 单遍 **3.38s**，AST 取 docstring 行 7.03s，
    读盘仅 0.31s）⇒ 复用后 tokenize 只跑一遍。
    产出由构造保证逐字节相同（同一个 ``_blank_docstring_rows``），
    并由 ``TestSourceCacheSelfCheck`` 钉死。

    刻意**不缓存原始文本**：读盘只占 0.31s，而缓存 44.8 MB 原文
    换 0.3s 不值得（三份字符串常驻会把内存推到 130 MB+）。
    """
    key = _cache_key(path)
    cached = _CODE_LEVEL_CACHE.get(key)
    if cached is None:
        cached = _blank_docstring_rows(
            read_stripped(path),
            _module_docstring_spans(path.read_text(encoding="utf-8")),
        )
        _CODE_LEVEL_CACHE[key] = cached
    return cached


def read_stripped(path: pathlib.Path) -> str:
    """``_strip_comments(path.read_text())`` 的带缓存版本（按文件内容标识）。"""
    key = _cache_key(path)
    cached = _STRIPPED_CACHE.get(key)
    if cached is None:
        cached = _strip_comments(path.read_text(encoding="utf-8"))
        _STRIPPED_CACHE[key] = cached
    return cached


def _rest_table_block(doc: str) -> str:
    """抽出 reST simple table（``====`` 分隔线之间的部分），不含表外散文。

    判据只应落在表格块上：散文里会合法出现 v2 源测试名、反例旧名、跨文件用例名，
    扫整份 docstring 必假红（本轮实测踩中）。
    """
    lines = doc.splitlines()
    marks = [i for i, ln in enumerate(lines) if re.fullmatch(r"=+(\s+=+)+\s*", ln)]
    if len(marks) < 2:
        return ""
    return "\n".join(lines[marks[0] : marks[-1] + 1])


def _iter_py_files():
    """扫描面：生产/测试/脚本的 ``.py``。

    排除 ``_wip_*`` —— 那是会话内临时诊断探针（按平台约定收口时删除），它们为了
    复算判据本身会写出被禁符号的字面量。**排除必须在此处统一做**，否则不同判据
    对同一扫描面各排一次会漂移（本轮实测：``_non_test_call_sites`` 排了、两条
    符号残留判据没排 ⇒ 探针把自己打红）。
    """
    for root in _SCAN_DIRS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if path.name.startswith("_wip_"):
                continue
            yield path


# ---------------------------------------------------------------------------
# 源码备忘缓存自检 —— 防「缓存把语义改掉而无人察觉」
# ---------------------------------------------------------------------------

class TestSourceCacheSelfCheck:
    """缓存只许省时间，不许改产出。

    这组断言存在的理由：``read_code_level`` / ``read_stripped`` 是本 spec 全部
    源码级判据的**唯一取值入口**。缓存一旦返回过期或不同的内容，全部判据会静默
    变绿（既有测试全过），而这恰好是变异检验最怕的假绿形态。
    """

    def test_hit_and_miss_are_byte_identical(self) -> None:
        """命中 / 未命中 / 显式绕过缓存，三者逐字节相同。"""
        path = CONVERSION_SERVICE
        raw = path.read_text(encoding="utf-8")
        key = _cache_key(path)

        _CODE_LEVEL_CACHE.pop(key, None)
        _STRIPPED_CACHE.pop(key, None)

        code_miss = read_code_level(path)      # 未命中（真算一遍）
        code_hit = read_code_level(path)       # 命中
        code_direct = _code_level_source(raw)  # 显式绕过缓存

        assert code_miss == code_direct, "首次计算与绕过缓存的产出不同"
        assert code_hit == code_direct, "缓存命中与绕过缓存的产出不同"
        assert code_hit == code_miss, "命中与未命中的产出不同"

        strip_miss = read_stripped(path)
        strip_hit = read_stripped(path)
        strip_direct = _strip_comments(raw)
        assert strip_miss == strip_direct == strip_hit, (
            "read_stripped 的命中/未命中/绕过缓存三者不一致"
        )

        # 锚点：样本非空且剥注释确有作用，否则上面三条是空转
        assert len(code_direct) > 1000, "样本过小，自检无效"
        assert raw.count("#") > code_direct.count("#"), "样本无注释可剥，自检无效"

    def test_cache_is_really_consulted(self) -> None:
        """投毒法：往缓存塞哨兵值，取值入口必须返回它 —— 证明缓存真的在被查。

        若某天有人把 ``read_code_level`` 改回「每次重算」，本条会打红提醒
        「缓存已失效，性能优化被回退」（而不是让优化静默消失）。
        """
        path = CONVERSION_SERVICE
        key = _cache_key(path)
        saved_code = _CODE_LEVEL_CACHE.get(key)
        saved_strip = _STRIPPED_CACHE.get(key)
        sentinel = "# __cache_probe__\n"
        try:
            _CODE_LEVEL_CACHE[key] = sentinel
            _STRIPPED_CACHE[key] = sentinel
            assert read_code_level(path) == sentinel, "read_code_level 未查缓存"
            assert read_stripped(path) == sentinel, "read_stripped 未查缓存"
        finally:
            for cache, saved in ((_CODE_LEVEL_CACHE, saved_code), (_STRIPPED_CACHE, saved_strip)):
                if saved is None:
                    cache.pop(key, None)
                else:
                    cache[key] = saved
        # 复原后必须回到真实产出
        assert read_code_level(path) == _code_level_source(
            path.read_text(encoding="utf-8")
        ), "自检未把缓存复原"

    def test_key_carries_mtime_and_size(self) -> None:
        """键必须含 mtime_ns 与 size，纯路径键会在文件被改后返回过期结果。"""
        path = CONVERSION_SERVICE
        st = path.stat()
        key = _cache_key(path)
        assert key == (str(path), st.st_mtime_ns, st.st_size)

    def test_file_change_invalidates_cache(self, tmp_path: pathlib.Path) -> None:
        """🔴 关键不变量：文件被改写后取值必须反映新内容（变异检验依赖这条）。

        反向自检同时证明「纯路径键」会返回过期结果 —— 那正是不能只用路径的理由。
        """
        probe = tmp_path / "probe.py"
        probe.write_text("x = 1  # old\n", encoding="utf-8")
        first = read_code_level(probe)
        assert "x = 1" in first

        key_before = _cache_key(probe)
        # 变异脚本的形态：整文件重写。显式推进 mtime 防同秒内写入被文件系统合并
        probe.write_text("y = 2  # new\n", encoding="utf-8")
        st = probe.stat()
        os.utime(probe, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))

        key_after = _cache_key(probe)
        assert key_after != key_before, "文件改写后缓存键未变 —— 会返回过期结果"

        second = read_code_level(probe)
        assert "y = 2" in second, "改写后取到的是过期内容 —— 缓存失效判据被破坏"
        assert "x = 1" not in second

        # 反向自检：若键只用路径，第二次会命中第一次的结果（过期）
        path_only: dict[str, str] = {str(probe): first}
        assert path_only[str(probe)] == first, (
            "纯路径键确实会返回过期结果，故键必须含 mtime_ns + size"
        )


# ---------------------------------------------------------------------------
# Property 24 — 无孤儿转换函数
# ---------------------------------------------------------------------------

def _service_methods() -> dict[str, ast.AST]:
    """``NoteConversionService`` 的全部方法（含私有），按名索引。"""
    tree = ast.parse(CONVERSION_SERVICE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "NoteConversionService":
            return {
                m.name: m
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise AssertionError("找不到 NoteConversionService 类")


#: Property 24 的作用面：转换语义的入口/子步骤（``convert_*`` 与 ``_map_*``）
_ORPHAN_SCAN_PREFIXES: tuple[str, ...] = ("convert_", "_map_")


def _method_names_under_scan() -> list[str]:
    return sorted(
        name
        for name in _service_methods()
        if name.startswith(_ORPHAN_SCAN_PREFIXES)
    )


def _non_test_call_sites(method: str) -> list[str]:
    """返回「非测试」的调用点（``self.<method>(`` 或 ``svc.<method>(`` 形态）。

    判据只认**调用形态** ``name(`` —— 只断言标识符出现会被 docstring/注释里的
    提及骗过（平台已登记的弱判据坑）。
    """
    pattern = re.compile(rf"\.{re.escape(method)}\s*\(")
    hits: list[str] = []
    for path in _iter_py_files():
        rel = path.relative_to(REPO).as_posix()
        if "/tests/" in f"/{rel}" or path.name.startswith("test_"):
            continue
        # 注：``_wip_*`` 探针已在 _iter_py_files 统一排除
        body = read_stripped(path)
        if pattern.search(body):
            hits.append(rel)
    return hits


class TestNoOrphanConversionFunctions:
    """Property 24：每个 ``convert_*`` / ``_map_*`` 方法都有非测试调用方。

    ------------------------------------------------------------------
    🔴 判据口径实证（2026-08-07 Task 10 复核，勿按「外部调用方」重写）
    ------------------------------------------------------------------

    本类的 ``_non_test_call_sites`` **把同类内的 ``self.<method>(`` 算作调用方**
    （扫描面包含服务模块自身）。这是**有意**的口径，实测依据：

    * ``_map_disclosure_notes`` / ``_map_report_rows`` 的
      ``external_non_test_callers`` 均为 ``[]``（排除服务文件自身后为空），
      ``self_calls == 1`` —— 两者都由同类的公开入口 ``execute_conversion``
      在 Step 3 / Step 4 调用（实测 line 391 所在方法）。
    * ``execute_conversion`` 自身的外部非测试调用方 =
      ``backend/app/routers/note_conversion.py`` +
      ``backend/app/services/event_handlers/_impl.py``；
      ``preview_conversion`` = ``routers/note_conversion.py`` +
      ``routers/standard_conversion.py``。

    ⇒ ``_map_*`` 是**私有子步骤**，被公开入口调用是正常设计，**不是孤儿**。
    若把判据改成「必须有服务文件之外的调用方」，这两个方法会被误判成孤儿，
    从而逼人把私有子步骤提成公开 API（制造第二个入口 = 双真源）。

    ⚠️ 另一条被本轮实证推翻的记载：曾记「v2 删除后 Property 24 自动转绿」。
    **不成立** —— v2 删除前该 Property 对 ``_map_*`` 就是绿的（self-call 口径），
    对 ``convert_disclosure_notes_v2`` 才是红的（它连 self-call 都没有）。
    删除让扫描面从 4 个方法缩到 2 个，转绿的是「v2 那两个条目消失」而非
    「原本红的条目变绿」。措辞层面的收敛归 Task 11 裁决，本类不改 design.md。
    """

    def test_scan_surface_is_non_empty(self):
        """锚点自检：扫描面非空，否则下一条断言是空转。"""
        names = _method_names_under_scan()
        assert names, "未扫到任何 convert_*/_map_* 方法 —— 判据可能失效"
        # 生产路径的两个核心子步骤必须在扫描面内
        assert "_map_disclosure_notes" in names
        assert "_map_report_rows" in names

    @pytest.mark.parametrize("method", _method_names_under_scan())
    def test_method_has_non_test_caller(self, method: str):
        callers = _non_test_call_sites(method)
        assert callers, (
            f"NoteConversionService.{method} 无非测试调用方 = 孤儿转换函数。"
            "要么接线到生产路径，要么删除（删除前先迁移测试断言）。"
            "详见 spec soe-listed-note-conversion-correctness / Property 24"
        )

    def test_map_methods_are_called_by_public_entry_not_externally(self):
        """登记 Property 24 的口径实证：``_map_*`` 只有 self-call，且调用方是公开入口.

        本条把「同类内调用也算有消费方」这一口径**钉死成正向断言**，防下个会话
        把判据改成「必须有服务文件之外的调用方」而把私有子步骤误判成孤儿。

        实测（2026-08-07）：两个 ``_map_*`` 的 external callers 均为 ``[]``，
        而 ``execute_conversion`` 有 router + event_handlers 两个外部调用方。
        """
        service_rel = CONVERSION_SERVICE.relative_to(REPO).as_posix()
        for method in ("_map_disclosure_notes", "_map_report_rows"):
            callers = _non_test_call_sites(method)
            assert callers == [service_rel], (
                f"{method} 的非测试调用点应恰为服务模块自身（self-call），实测 {callers}。"
                "若出现外部调用方，说明私有子步骤被提成了公开 API（双真源风险），"
                "请先确认是有意设计再更新本断言。"
            )

        # 公开入口必须有服务文件之外的真实消费方，否则整条链才是孤儿
        entry_callers = _non_test_call_sites("execute_conversion")
        external = [rel for rel in entry_callers if rel != service_rel]
        assert external, (
            "execute_conversion 无外部非测试调用方 —— 那才是真孤儿。"
            f"实测调用点: {entry_callers}"
        )

    def test_predicate_rejects_docstring_only_mention(self):
        """反向自检：只在 docstring/注释里提到方法名**不算**调用方。

        这正是 v2 删除前的形态 —— 服务模块自己的 6 处引用全是文字提及。
        """
        fake = (
            'def probe():\n'
            '    """见 :meth:`NoteConversionService.convert_disclosure_notes_v2`。"""\n'
            '    # self.convert_disclosure_notes_v2( 只在注释里\n'
            '    return 0\n'
        )
        pattern = re.compile(r"\.convert_disclosure_notes_v2\s*\(")
        stripped = _strip_comments(fake)
        assert pattern.search(fake), "替身构造有误：原文应含调用形态（在注释里）"
        assert not pattern.search(stripped), (
            "_strip_comments 未剥掉注释里的调用形态 —— 判据会把文字提及当调用方"
        )


# ---------------------------------------------------------------------------
# v2 符号已全仓删除
# ---------------------------------------------------------------------------

class TestV2SymbolsFullyRemoved:
    @pytest.mark.parametrize("symbol", REMOVED_SYMBOLS)
    def test_symbol_not_defined_in_service(self, symbol: str):
        assert symbol not in _service_methods(), (
            f"{symbol} 仍定义在 NoteConversionService 上 —— Task 10 裁决为删除"
        )

    @pytest.mark.parametrize("symbol", REMOVED_SYMBOLS)
    def test_no_reference_anywhere(self, symbol: str):
        """**代码级**扫描（剥 ``#`` 注释 + 剥 docstring）：剩余代码里不得出现 v2 符号。

        判据为什么不是「全文本扫描」：spec Requirement 6.1/6.3 要求删除决策与断言
        迁移**留痕**，那些留痕就写在 docstring / 断言消息里（见
        ``DOCSTRING_ONLY_MENTIONS``）。裸文本判据会把「有意留证的说明文字」
        打红，逼人删掉正是下个会话需要的那份记载。
        """
        registered = {rel for rel, _ in DOCSTRING_ONLY_MENTIONS}
        offenders: list[str] = []
        for path in _iter_py_files():
            rel = path.relative_to(REPO).as_posix()
            if path.name in _REFERENCE_ALLOWLIST or rel in registered:
                continue
            if symbol in read_code_level(path):
                offenders.append(rel)
        assert not offenders, (
            f"{symbol} 在代码级扫描里仍被引用: {offenders}\n"
            "若确为有意留证的说明文字，请登记进 DOCSTRING_ONLY_MENTIONS 并写明理由"
        )

    @pytest.mark.parametrize("symbol", REMOVED_SYMBOLS)
    def test_no_definition_or_call_form_anywhere(self, symbol: str):
        """定义形态 / 调用形态在**任何**文件都不放行（登记表也不豁免）。

        这条是登记表的兜底：某个登记文件哪天真的调用或重新定义了 v2，
        它仍会被打红。
        """
        patterns = (
            re.compile(rf"\bdef\s+{re.escape(symbol)}\s*\("),
            re.compile(rf"\.\s*{re.escape(symbol)}\s*\("),
        )
        offenders: list[str] = []
        for path in _iter_py_files():
            if path.name in _REFERENCE_ALLOWLIST:
                continue
            code = read_code_level(path)
            if any(p.search(code) for p in patterns):
                offenders.append(path.relative_to(REPO).as_posix())
        assert not offenders, (
            f"{symbol} 出现定义或调用形态: {offenders} —— Task 10 裁决为删除"
        )

    # -- 登记表双向自检 ---------------------------------------------------

    def test_registered_files_really_contain_the_mention(self):
        """自检 ②：登记的文件必须**确实**含该字样，否则条目 stale 应移出。"""
        stale: list[str] = []
        for rel, _reason in DOCSTRING_ONLY_MENTIONS:
            path = REPO / rel
            assert path.is_file(), f"登记文件不存在: {rel}"
            raw = path.read_text(encoding="utf-8")
            if not any(sym in raw for sym in REMOVED_SYMBOLS):
                stale.append(rel)
        assert not stale, (
            f"登记项已 stale（文件里已无 v2 提及）: {stale} —— 请从 "
            "DOCSTRING_ONLY_MENTIONS 移出，否则它会变成永久盲区"
        )

    def test_registry_size_is_capped(self):
        """自检 ③：条目数封顶，只许缩短。"""
        assert len(DOCSTRING_ONLY_MENTIONS) <= _DOCSTRING_MENTION_LIMIT, (
            f"留证登记项 {len(DOCSTRING_ONLY_MENTIONS)} 条 > 上限 "
            f"{_DOCSTRING_MENTION_LIMIT} —— 新增留证须先显式提高上限并说明理由"
        )

    @pytest.mark.parametrize(
        "rel,reason",
        DOCSTRING_ONLY_MENTIONS,
        ids=[rel.rsplit("/", 1)[-1] for rel, _ in DOCSTRING_ONLY_MENTIONS],
    )
    def test_registered_entry_has_substantive_reason(self, rel: str, reason: str):
        assert len(reason) >= 30, f"{rel} 的留证理由过短（{len(reason)} 字）"

    def test_predicate_rejects_real_code_level_reference(self):
        """反向自检 ①：真有代码级引用的替身必须被判为 offender。"""
        good = (
            '"""见 convert_disclosure_notes_v2 的删除记载。"""\n'
            "# self.convert_disclosure_notes_v2( 只在注释里\n"
            "x = 1\n"
        )
        bad = (
            '"""说明文字。"""\n'
            "def probe(self):\n"
            "    return self.convert_disclosure_notes_v2(1)\n"
        )
        assert "convert_disclosure_notes_v2" not in _code_level_source(good), (
            "code-level 扫描未剥掉 docstring/注释 —— 留证文字会被误判"
        )
        assert "convert_disclosure_notes_v2" in _code_level_source(bad), (
            "code-level 扫描把真实调用一起剥掉了 —— 判据失效"
        )
        assert re.search(
            r"\.\s*convert_disclosure_notes_v2\s*\(", _code_level_source(bad)
        ), "调用形态判据未命中真实调用"

    def test_v2_test_files_are_gone(self):
        """v2 专属测试文件已删除（断言已迁移到生产路径测试）。"""
        for rel in (
            "tests/services/test_note_conversion_v2.py",
            "tests/services/test_note_conversion_pbt.py",
        ):
            assert not (BACKEND / rel).exists(), (
                f"{rel} 仍存在 —— 它只测 v2；断言已迁移到 "
                "test_note_conversion_section_mapping_production.py"
            )


# ---------------------------------------------------------------------------
# Property 26 — 测试不丢失：断言迁移对照表
# ---------------------------------------------------------------------------

#: v2 的 11 个测试 → 生产路径测试里的对应覆盖。
#:
#: 每条 ``(v2 测试名, 生产测试名, 关系)``；``关系`` ∈
#: ``equivalent``（等价） / ``stronger``（更强） / ``obsolete_by_design``（该断言
#: 锁定的是 v2 的缺陷形态或被生产路径的结构性设计取代）。
#:
#: 🔴 ``obsolete_by_design`` 必须逐条写明理由 —— 它是「测试丢失」与「测试本该
#: 消失」的唯一分界；空理由等于偷偷删断言。
ASSERTION_MIGRATION: tuple[tuple[str, str, str, str], ...] = (
    (
        "test_preview_v2_returns_all_fields",
        "test_preview_plan_exposes_all_buckets",
        "stronger",
        "v2 preview 返回 common/to_archive/to_create 三个清单；生产把同一信息表达为"
        "_build_section_mapping_plan 的 pairs/source_only/target_only，并额外断言"
        "format_diff 与 bridged（别名桥接）两个桶存在 —— v2 无别名桥接概念",
    ),
    (
        "test_preview_v2_same_type_noop",
        "test_same_type_conversion_is_noop",
        "equivalent",
        "同类型切换返回全零结果；该生产测试的 docstring 明写同时承接 preview 与 "
        "convert 两侧的 noop 断言，并额外断言 section_id 未被改写",
    ),
    (
        "test_convert_v2_common_sections_preserved",
        "test_common_section_data_preserved",
        "stronger",
        "v2 只数 common_count 且**不改** section_id；生产断言 section_id/"
        "note_section 真被改写成目标侧取值 + manual 计数不减 + "
        "user_edits_dropped == 0（Property 5/6/9）",
    ),
    (
        "test_convert_v2_soe_only_archived",
        "test_source_only_sections_archived",
        "equivalent",
        "archived == 1 且 is_deleted is True，与 v2 的归档断言逐条对应；"
        "lineage 部分另由 test_archived_sections_have_lineage 承接",
    ),
    (
        "test_convert_v2_listed_only_created",
        "test_target_only_sections_created",
        "equivalent",
        "v2 断言「db.add 被调用 + created 计数」；生产版逐条对应"
        "（`res['created'] > 0` + `sess.added` 非空）。v2 同一测试里那条"
        "`note_section == sid` 的断言另由 test_created_note_section_is_real_number_not_sid"
        "以更强形态承接（见下一行）",
    ),
    (
        "test_convert_v2_listed_only_created",
        "test_created_note_section_is_real_number_not_sid",
        "stronger",
        "v2 只断言 db.add 被调用且 note_section=sid（**缺陷形态**：章节号写成"
        "slug）；生产断言 note_section != section_id（取目标模板真实 "
        "section_number）+ is_empty=true + status=draft（Property 8）",
    ),
    (
        "test_convert_v2_format_diff_adapted",
        "test_format_diff_counts_only_real_changes",
        "stronger",
        "v2 靠 mock 让 adapt 返回不同对象才计数；生产走 report.changed 事实判据，"
        "并断言列改名后 _cell_modes 的 manual 标记跟着走（平台红线）",
    ),
    (
        "test_convert_v2_updates_template_type",
        "test_execute_conversion_updates_template_type",
        "equivalent",
        "template_type 改写归 execute_conversion Step 2；生产测试在完整链路上"
        "断言 UPDATE projects 语句真的被执行且 mapped_notes 是实际改写数",
    ),
    (
        "test_convert_v2_same_type_noop",
        "test_same_type_conversion_is_noop",
        "equivalent",
        "同类型返回全零结果；生产版返回键更多（五桶 + 诊断计数），逐键断言为零",
    ),
    (
        "test_convert_v2_invalid_target_raises",
        "test_invalid_target_type_raises",
        "equivalent",
        "非法 target_type 抛 ValueError；生产测试在一处同时断言 "
        "execute_conversion 与 preview_conversion 两个入口（v2 分两个测试）",
    ),
    (
        "test_preview_v2_invalid_target_raises",
        "test_invalid_target_type_raises",
        "equivalent",
        "同上 —— 两条 v2 测试并为一条生产测试，它对 preview_conversion 也断言了"
        "pytest.raises(ValueError, match='target_type')",
    ),
    (
        "test_pbt_full_roundtrip_soe_listed_soe",
        "test_full_roundtrip_preserves_manual_cells",
        "stronger",
        "v2 的 PBT 实为「deepcopy 后比对」= 在测 copy.deepcopy；生产做真实 "
        "soe→listed→soe 双向改写，断言 sid/章节号回到源侧且 manual 值逐格不变、"
        "两个方向 user_edits_dropped 均为 0（Property 9）",
    ),
    (
        "test_pbt_archived_sections_have_lineage",
        "test_archived_sections_have_lineage",
        "equivalent",
        "archived_sections[0].section_id / archived_at / reason 三者均被断言，"
        "与 v2 的 lineage 断言逐条对应（Requirement 2.3）",
    ),
    (
        "test_pbt_manual_cells_preserved_after_roundtrip",
        "test_manual_cells_are_counted_and_preserved",
        "stronger",
        "原 PBT 只对 table_data 做 copy.deepcopy 再比对，被测对象是标准库而非"
        "生产代码（v2 对共有章节不动 table_data，故它恒绿）。生产测试在真实改写"
        "路径上断言 user_edits_preserved == 3（跨行累加、locked/auto 不计）",
    ),
    (
        "test_pbt_locked_cells_preserved",
        "test_locked_cells_preserved",
        "stronger",
        "原 PBT 亦为 deepcopy 自比；生产版是 hypothesis PBT 跑真实 "
        "_map_disclosure_notes，断言每个 manual/locked 单元格改写前后逐格值与"
        "mode 均不变，且 user_edits_dropped == 0",
    ),
    (
        "test_pbt_empty_table_safe",
        "test_empty_and_none_table_data_are_safe",
        "equivalent",
        "空 rows 的 table_data 不崩；生产版直接跑 _map_disclosure_notes 而非"
        "deepcopy，并额外断言 mapped==1 / failed==[] / table_data 原样保留",
    ),
    (
        "test_roundtrip_preserves_manual_value_simple",
        "test_manual_value_survives_simple_rewrite",
        "stronger",
        "原测试是纯 copy.deepcopy 自比，不触碰任何生产代码；生产同名语义测试在"
        "真实章节改写后断言 manual 值 42.0 逐字不变",
    ),
    (
        "test_roundtrip_empty_rows_safe",
        "test_empty_and_none_table_data_are_safe",
        "stronger",
        "原测试纯 copy.deepcopy 自比；生产版对空 rows 跑真实 "
        "_map_disclosure_notes 并断言 mapped==1 / failed==[]",
    ),
    (
        "test_roundtrip_none_table_data_safe",
        "test_none_table_data_is_safe",
        "stronger",
        "原测试是 copy.deepcopy(None) 自比；生产版对 table_data=None 跑真实"
        "改写路径并断言 mapped==1 / failed==[] / table_data 仍为 None",
    ),
    (
        "test_convert_v2_no_notes_still_works",
        "test_no_notes_still_creates_target_only_sections",
        "equivalent",
        "无存量 note 时不崩且目标独有章节仍被创建；生产额外断言 mapped/archived"
        "为 0 且 failed 为空",
    ),
    (
        "test_preview_v2_counts_manual_cells_correctly",
        "test_manual_cells_are_counted_and_preserved",
        "equivalent",
        "manual 单元格计数（跨行累加、locked/auto 不计），生产断言 "
        "user_edits_preserved == 3 与 v2 的计数期望一致",
    ),
    (
        "test_convert_v2_listed_to_soe_reverses",
        "test_reverse_direction_swaps_archive_and_create",
        "equivalent",
        "listed→soe 时归档/新建方向对调；生产额外断言被归档 note 的 "
        "is_deleted is True 且反向 created > 0",
    ),
)

#: 生产测试里**不承接任何 v2 断言**的用例 —— 本 spec 新增能力。
#:
#: 反向不变量：生产测试的 26 个函数必须「要么被迁移表指向、要么在本表登记」，
#: 不得有无人指向的用例（那说明迁移表与生产测试脱节）。
PRODUCTION_ONLY_TESTS: tuple[tuple[str, str, str], ...] = (
    (
        "test_plan_is_symmetric",
        "1.4",
        "两方向 pair 数相等 —— 别名桥接（SECTION_TITLE_ALIASES）的对称性，v2 无"
        "别名桥接概念故无对应断言",
    ),
    (
        "test_result_has_five_categories",
        "4.2",
        "mapped/archived/created/skipped/failed 五分类返回结构，v2 只返三个清单",
    ),
    (
        "test_no_pending_keys_remain",
        "4.1",
        "Task 9 收口后 archived/created/user_edits_preserved 三键是真实计数而非"
        "None（未测量），v2 时代不存在 pending_keys 概念",
    ),
    (
        "test_legacy_ids_recorded",
        "2.2",
        "源侧 section_id 与旧章节号进 template_lineage.legacy_section_ids /"
        "legacy_note_sections，v2 完全不写 lineage（它连 sid 都不改）",
    ),
    (
        "test_binding_id_prefix_rewritten",
        "2.7",
        "附注公式 binding_id 内嵌章节号，改章节号必须同步重写前缀（rows/_tables/"
        "sub_table_data 三处）且不得误改别的章节号 —— v2 无此能力",
    ),
    (
        "test_idempotent_rerun",
        "4.4",
        "幂等重跑：第二次 mapped==0（已是目标侧取值）。v2 每次都重算 count(*)"
        "故没有幂等语义可断言",
    ),
    (
        "test_empty_field_mapping_does_not_count",
        "4.5",
        "真实 diff 数据 field_mapping 全 null ⇒ format_adapted 必须为 0（假成功"
        "反馈红线）。v2 靠 mock 造非空 mapping，测不到这条",
    ),
    (
        "test_single_failure_does_not_block_others",
        "4.3",
        "逐章节 savepoint 隔离：注入一章 flush 失败，其余章节仍完成且失败项进"
        "failed 桶带 note_id/phase/error。v2 无 savepoint 隔离",
    ),
)

_VALID_RELATIONS: frozenset[str] = frozenset({"equivalent", "stronger", "obsolete_by_design"})

#: ``obsolete_by_design`` 理由必须命中的实证标记之一（指出「被谁承接」或「为何本该消失」）
_OBSOLETE_REASON_MARKERS: tuple[str, ...] = (
    "deepcopy",
    "标准库",
    "缺陷形态",
    "已由",
    "已被",
)


#: 作废理由最小长度（常量化，避免纯函数与其自检各写一份字面量 = 双真源）
_OBSOLETE_REASON_MIN_LEN: int = 30


def _obsolete_reason_ok(reason: str) -> tuple[bool, str]:
    """``obsolete_by_design`` 理由的质量闸（纯函数，便于替身自检）。

    Returns:
        ``(ok, why)``；``why`` ∈ ``ok`` / ``too_short`` / ``no_marker``
    """
    if len(reason) < _OBSOLETE_REASON_MIN_LEN:
        return False, "too_short"
    if not any(marker in reason for marker in _OBSOLETE_REASON_MARKERS):
        return False, "no_marker"
    return True, "ok"


def _production_test_names() -> set[str]:
    tree = ast.parse(PRODUCTION_TEST.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


class TestAssertionMigrationComplete:
    """Property 26：v2 的测试断言在生产路径测试里逐条有对应覆盖。"""

    def test_production_test_file_exists(self):
        assert PRODUCTION_TEST.is_file(), (
            f"生产路径测试缺失: {PRODUCTION_TEST} —— Requirement 6.3 禁止直接删测试"
        )

    def test_migration_table_covers_all_v2_tests(self):
        """迁移表必须覆盖 v2 两个测试文件里的**全部** test 函数。

        清单在删除前由探针实测得出（v2 单测 10 个 + PBT 文件 11 个 = 21 个）。
        """
        expected = {
            # test_note_conversion_v2.py（10）
            "test_preview_v2_returns_all_fields",
            "test_preview_v2_same_type_noop",
            "test_convert_v2_common_sections_preserved",
            "test_convert_v2_soe_only_archived",
            "test_convert_v2_listed_only_created",
            "test_convert_v2_format_diff_adapted",
            "test_convert_v2_updates_template_type",
            "test_convert_v2_same_type_noop",
            "test_convert_v2_invalid_target_raises",
            "test_preview_v2_invalid_target_raises",
            # test_note_conversion_pbt.py（11）
            "test_pbt_manual_cells_preserved_after_roundtrip",
            "test_pbt_locked_cells_preserved",
            "test_pbt_empty_table_safe",
            "test_pbt_full_roundtrip_soe_listed_soe",
            "test_pbt_archived_sections_have_lineage",
            "test_roundtrip_preserves_manual_value_simple",
            "test_roundtrip_empty_rows_safe",
            "test_roundtrip_none_table_data_safe",
            "test_convert_v2_no_notes_still_works",
            "test_preview_v2_counts_manual_cells_correctly",
            "test_convert_v2_listed_to_soe_reverses",
        }
        migrated = {row[0] for row in ASSERTION_MIGRATION}
        assert migrated == expected, (
            f"迁移表与 v2 测试清单不符\n"
            f"漏迁移: {sorted(expected - migrated)}\n"
            f"多出（v2 里不存在）: {sorted(migrated - expected)}"
        )

    @pytest.mark.parametrize(
        "v2_test,prod_test,relation,reason",
        ASSERTION_MIGRATION,
        ids=[f"{row[0]}->{row[1]}" for row in ASSERTION_MIGRATION],
    )
    def test_target_test_exists(self, v2_test, prod_test, relation, reason):
        assert relation in _VALID_RELATIONS, f"非法关系标记: {relation}"
        assert prod_test in _production_test_names(), (
            f"{v2_test} 迁移目标 {prod_test} 在生产路径测试里不存在"
        )

    def test_obsolete_entries_carry_substantive_reason(self):
        """``obsolete_by_design`` 是唯一「不等价迁移」的出口，理由必须实质。

        🔴 本轮实测该关系当前为**零条**（21 条 v2 断言全部找到真实承接测试），故
        本条不能写成 ``parametrize`` —— 空参数集会让 pytest 整条 SKIP，判据变成
        空转（平台已登记的「守卫空转」反模式）。改为：
        ①对现存条目（可能为零）逐条校验 ②**无条件**用替身验证判据本身有效。
        """
        for v2_test, _prod, relation, reason in ASSERTION_MIGRATION:
            if relation != "obsolete_by_design":
                continue
            ok, why = _obsolete_reason_ok(reason)
            assert ok, f"{v2_test} 的作废理由不合格（{why}）: {reason}"

        # 判据自检：不依赖真实数据存在 obsolete 条目
        bad_short = "太短"
        ok, why = _obsolete_reason_ok(bad_short)
        assert not ok and why == "too_short", "短理由未被拒绝 —— 长度闸失效"

        # 🔴 这条替身必须 >= 30 字，否则先被长度闸拦下、`no_marker` 那道闸测不到
        bad_placeholder = (
            "此断言已作废，无需再迁移，保留本条说明以便后续查阅参考使用，暂不处理。"
        )
        assert len(bad_placeholder) >= _OBSOLETE_REASON_MIN_LEN, (
            "替身构造有误：占位理由须足够长才能验到 marker 闸"
        )
        ok, why = _obsolete_reason_ok(bad_placeholder)
        assert not ok and why == "no_marker", (
            "占位式理由（够长但未指出被谁承接/为何本该消失）未被拒绝"
        )

        good = "纯 copy.deepcopy 自比，被测对象是标准库而非生产代码；语义已由真实改写断言覆盖"
        ok, why = _obsolete_reason_ok(good)
        assert ok, f"合格理由被误拒: {why}"

    def test_no_production_test_is_orphaned(self):
        """反向：生产测试的每个用例都必须「被迁移表指向」或「在新增能力表登记」。

        🔴 这条是本轮加的 —— 上一轮迁移表按**预期名**而非实测名写，导致 26 个生产
        测试**一个都没被指向**，而旧的「数量 >= 20」断言照样通过 ⇒ 迁移表与生产
        测试完全脱节却无人察觉。
        """
        names = _production_test_names()
        assert len(names) >= 20, (
            f"生产路径测试仅 {len(names)} 个用例 —— v2 有 21 个断言待承接，"
            "疑似迁移不完整"
        )
        migration_targets = {row[1] for row in ASSERTION_MIGRATION}
        production_only = {row[0] for row in PRODUCTION_ONLY_TESTS}
        unclaimed = sorted(names - migration_targets - production_only)
        assert not unclaimed, (
            f"以下生产测试无人指向（既不承接 v2 断言、也未登记为新增能力）: {unclaimed}\n"
            "要么补进 ASSERTION_MIGRATION 的迁移目标，要么进 PRODUCTION_ONLY_TESTS "
            "并写明对应 Requirement"
        )

    def test_production_docstring_mapping_table_is_not_stale(self):
        """生产测试的模块 docstring 里那份迁移对照表必须引用**磁盘真实**的测试名。

        🔴 本轮实测抓到的缺陷：该 docstring 表写的是**重命名前**的旧名（10 个，如
        ``test_roundtrip_keeps_manual_values`` / ``test_manual_cells_counted``），
        测试后来改名而表没跟上 ⇒ 「迁移留痕」指向不存在的用例，Requirement 6.3
        的可追溯性形同虚设。而 ``ASSERTION_MIGRATION`` 常量是按磁盘校对过的，
        两者不一致时**以常量为权威**。

        🔴 判据必须**只扫表格块**（``====`` 分隔的 reST simple table），不能扫整份
        docstring —— 散文部分会合法地提到①v2 源测试名（「从哪迁来」的记载，磁盘上
        当然没有）②本轮修正说明里作为**反例证据**引用的旧名③本守卫文件自己的
        用例名（交叉引用）。扫整份必对这三类假红（本轮已实测踩中）。
        """
        doc = ast.get_docstring(
            ast.parse(PRODUCTION_TEST.read_text(encoding="utf-8"))
        )
        assert doc, "生产路径测试缺模块 docstring —— 迁移留痕没了"

        table = _rest_table_block(doc)
        assert table, (
            "docstring 里找不到 ``====`` 分隔的迁移对照表 —— "
            "Requirement 6.3 的导读表被删或格式被破坏"
        )

        # 表格右列（本文件对应）才是须落到磁盘的目标名；左列是 v2 源名
        referenced = set(re.findall(r"``(test_[A-Za-z0-9_]+)``", table))
        assert referenced, (
            "表格块里未抽到任何 ``test_xxx`` 引用 —— 正则失效，判据空转"
        )

        on_disk = _production_test_names()
        v2_source_names = {row[0] for row in ASSERTION_MIGRATION}
        # 左列的 v2 源名允许出现（它们本就不在磁盘上）
        stale = sorted(referenced - on_disk - v2_source_names)
        assert not stale, (
            f"docstring 迁移表引用了磁盘上不存在的测试名: {stale}\n"
            "这些是重命名前的旧名 —— 请按 ASSERTION_MIGRATION（权威）更新 docstring"
        )

    def test_rest_table_extractor_self_check(self):
        """``_rest_table_block`` 自检：只取表格块、不吞散文。

        没有这条自检，提取器一旦失效（返回空串）上一条会被 ``assert table``
        拦下；但若它误吞散文，上一条会重新变成「扫整份」的假红发生器。
        """
        sample = (
            "散文里提到 ``test_stale_old_name`` 作为反例。\n"
            "\n"
            "====  ====\n"
            "A     B\n"
            "====  ====\n"
            "``test_src_a``  ``test_dst_a``\n"
            "====  ====\n"
            "\n"
            "尾部散文又提到 ``test_another_old_name``。\n"
        )
        block = _rest_table_block(sample)
        assert "test_dst_a" in block, "表格块内容未被提取"
        assert "test_stale_old_name" not in block, "提取器吞进了表格**之前**的散文"
        assert "test_another_old_name" not in block, "提取器吞进了表格**之后**的散文"

    def test_production_only_table_does_not_overlap_migration(self):
        """``PRODUCTION_ONLY_TESTS`` 与迁移表目标不得重叠。

        重叠 = 同一用例既声称「承接 v2 断言」又声称「v2 没有对应断言」，自相矛盾。
        """
        migration_targets = {row[1] for row in ASSERTION_MIGRATION}
        production_only = {row[0] for row in PRODUCTION_ONLY_TESTS}
        overlap = sorted(migration_targets & production_only)
        assert not overlap, (
            f"以下用例同时出现在迁移表目标与新增能力表: {overlap}\n"
            "一个用例只能是「承接 v2 断言」或「本 spec 新增能力」二者之一"
        )

    @pytest.mark.parametrize(
        "prod_test,requirement,reason",
        PRODUCTION_ONLY_TESTS,
        ids=[row[0] for row in PRODUCTION_ONLY_TESTS],
    )
    def test_production_only_entry_is_valid(
        self, prod_test: str, requirement: str, reason: str
    ):
        """新增能力表的每条：用例真实存在 + 有 Requirement 号 + 理由实质。"""
        assert prod_test in _production_test_names(), (
            f"{prod_test} 在生产路径测试里不存在 —— PRODUCTION_ONLY_TESTS 条目 stale"
        )
        assert re.fullmatch(r"\d+\.\d+", requirement), (
            f"{prod_test} 的 Requirement 号格式非法: {requirement!r}（应形如 4.3）"
        )
        assert len(reason) >= 30, (
            f"{prod_test} 的理由过短（{len(reason)} 字）: {reason}"
        )
        assert "v2" in reason, (
            f"{prod_test} 的理由未说明「v2 为何没有对应断言」: {reason}"
        )
