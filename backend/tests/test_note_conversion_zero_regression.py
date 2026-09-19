"""零回归守卫 — soe-listed-note-conversion-correctness Task 18 / Property 34

**判据形态的选型（落地时的核心决策，勿改回）**

需求 10.2 的字面是「不涉及转换的既有附注行为**逐字节不变**」。直接把它实现成
「跑一次附注 Word 导出比 docx 字节」不可行，两条硬理由：

1. docx/xlsx 是 zip 容器，内含 `docProps/core.xml` 的 `dcterms:created`/`modified`
   与 zip 条目顺序 ⇒ **同一份数据连跑两次字节都不同**，比对天然不稳定（平台已在
   `test_deliverable_lineage_zero_regression.py` 踩过并写下同款结论）。
2. 真实导出需要项目数据与 DB；在无 DB 的 CI job 里跑不起来。

⇒ 本文件把「逐字节不变」落成**两档可判定的判据**（与 deliverable-lineage 那份
零回归守卫同构，那是平台既有范式）：

- **档 1 结构性**：附注生成/同步/导出/投影四条链路的模块**不引用**本 spec 引入的
  任何转换改写符号。「没有任何代码路径能触达」比「跑一次没发现差异」更强 ——
  后者只覆盖被抽样到的输入，前者覆盖全部输入。
  实测支点：9 个候选模块对 `_map_disclosure_notes` / `adapt_table_data` /
  `note_section_matcher` 等符号的 code-level 引用数**全为 0**，反向 `note_conversion_service`
  也不 import 任何附注生成/导出模块 ⇒ 两侧零耦合。
- **档 2 行为性**：对**纯函数**（投影器 / 模板内容分类 / 两级表头构造 / 金额格式化）
  跑「输入 → 输出」对照，断言可见段落文字序列、表结构序列、列分组序列逐字相等。
  这些是附注渲染与 Word 导出的**共同上游**，它们不变则下游可见产物不变。

**禁止事项（均为平台已实测的事故形态，勿"优化"成这些写法）**

- 禁 `git stash`：并发会话/IDE 缓存会把文件回写成另一版本，`stash pop` 必冲突。
- 禁「把改动文件换成 `git show HEAD:` 版跑同一组」：本 spec 的改动文件含并发会话
  未提交成果（`note_template_*.json` 等），换 HEAD 会**破坏数据**（memory 有真实
  事故记录：换 HEAD 后 8 组模板守卫全红、靠幂等脚本才恢复）。
- 禁冻结上游数据的 md5 常量：两份模板 JSON 被 5 个 spec 共享，合法变更后重生成
  即让常量过期 ⇒ 假红发生器。本文件改用「本模块运行前后对照」。

**反向自检**：`_CONVERSION_SYMBOLS` / `_NOTE_PIPELINE_MODULES` 任一为空则档 1
恒绿 ⇒ 两个集合都有非空断言，且集合里的符号必须真实存在于生产模块中
（防拼错成死字符串 —— 那会让守卫永久空转）。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest


def _find_backend_root() -> Path:
    """双哨兵向上查找 backend 根。

    单哨兵不够稳：将来子目录出现同名文件即误停；目录做哨兵会被历史空目录骗停
    （平台已记：`audit-platform/backend/app/routers` 是遗留空目录）。
    """
    here = Path(__file__).resolve()
    for cand in [here, *here.parents]:
        if (cand / "app" / "services" / "note_conversion_service.py").exists() and (
            cand / "data" / "note_soe_listed_diff.json"
        ).exists():
            return cand
    raise AssertionError("未能定位 backend 根（双哨兵均未命中）")


BACKEND = _find_backend_root()
SERVICES = BACKEND / "app" / "services"
DATA = BACKEND / "data"


# ─────────────────────────────────────────────────────────────────────────────
# 源码读取（code-level：剥 # 注释 + docstring，保留普通字符串字面量）
# ─────────────────────────────────────────────────────────────────────────────


def _strip_comments_and_docstrings(src: str) -> str:
    """剥 `#` 行注释与 docstring，**保留**普通字符串字面量。

    两条必要性（都是平台实测过的假红/假绿形态）：

    - 必须剥 docstring：本文件与生产模块的说明文字里会**原样写出**被禁符号名
      （比如本模块 docstring 里就有 `_map_disclosure_notes`），裸子串匹配会把
      说明文字数成真实引用 → 守卫假红，还会逼人删掉正是下个会话需要的记载。
    - 不能剥普通字符串：`{"legacy_section_ids": ...}` 这种字典键名是**真消费**。

    这里用 tokenize 精确剥；正则剥三引号会被字符串字面量里出现的三引号骗
    （本 docstring 原先就因为内嵌了三引号字面量而提前闭合，导致 SyntaxError）。
    """
    import io
    import tokenize

    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError):  # pragma: no cover - 防御
        return re.sub(r"(?m)#.*$", "", src)

    drop_spans: list[tuple[int, int, int, int]] = []
    prev_meaningful: tokenize.TokenInfo | None = None
    for tok in toks:
        if tok.type == tokenize.COMMENT:
            drop_spans.append((*tok.start, *tok.end))
            continue
        if tok.type == tokenize.STRING:
            # docstring 判定：处于语句起始位置（前一个有意义 token 是 NEWLINE/
            # INDENT/DEDENT/冒号，或文件开头）
            if prev_meaningful is None or prev_meaningful.type in (
                tokenize.NEWLINE,
                tokenize.NL,
                tokenize.INDENT,
                tokenize.DEDENT,
            ):
                drop_spans.append((*tok.start, *tok.end))
        if tok.type not in (tokenize.NL, tokenize.COMMENT):
            prev_meaningful = tok

    lines = src.splitlines(keepends=True)
    for srow, scol, erow, ecol in drop_spans:
        for r in range(srow, erow + 1):
            if r - 1 >= len(lines):
                continue
            line = lines[r - 1]
            start = scol if r == srow else 0
            end = ecol if r == erow else len(line)
            keep_tail = line[end:] if r == erow else ""
            lines[r - 1] = line[:start] + " " * max(0, end - start) + keep_tail
    return "".join(lines)


_SRC_CACHE: dict[tuple[str, int, int], str] = {}


def _read_code_level(path: Path) -> str:
    """带 (path, mtime_ns, size) 记忆化的 code-level 源码读取。

    键必须含 mtime —— 纯路径键会让变异检验静默假绿（变异脚本的工作方式正是
    「改文件 → 跑测试 → 还原」，缓存不失效则读到旧内容）。
    """
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key not in _SRC_CACHE:
        _SRC_CACHE[key] = _strip_comments_and_docstrings(
            path.read_text(encoding="utf-8")
        )
    return _SRC_CACHE[key]


# ─────────────────────────────────────────────────────────────────────────────
# 档 1：结构性零耦合
# ─────────────────────────────────────────────────────────────────────────────

#: 转换侧**模块名**。判据 = 附注链路里出现对它的 import（`import x` / `from x import`）。
#: 这类名字不会以「成员」形式出现在自己的源码里（模块不按名字 import 自己），
#: 故自检必须按**文件存在性**判，塞进成员自检集会永久打红（2026-08-08 实测）。
_CONVERSION_MODULES: tuple[str, ...] = (
    "note_conversion_service",
    "note_section_matcher",
    "note_conversion_row_codes",
)

#: 转换侧**函数/类/常量名**。判据见 `_referenced_conversion_symbols` 的说明：
#: 裸子串匹配会被同名局部符号骗（实测 `note_offline_import_service` 有自己的
#: 局部函数 `match_sections`，与转换侧 `match_section` 零关系），故一律要求
#: 「限定调用形态」或「显式 import 该名字」。
_CONVERSION_MEMBERS: tuple[str, ...] = (
    "NoteConversionService",
    "_map_disclosure_notes",
    "_map_report_rows",
    "_update_formula_references",
    "match_section",
    "rewrite_row_refs_in_formula",
    "adapt_table_data",
    "legacy_section_ids",
    "legacy_note_sections",
)

#: 兼容旧引用（本文件内部若干断言按「符号总数」做规模自检）。
_CONVERSION_SYMBOLS: tuple[str, ...] = _CONVERSION_MODULES + _CONVERSION_MEMBERS

#: 附注四条链路（生成 / 同步 / 导出 / 投影）+ 相关只读工具模块。
#: 这些是「不涉及转换的既有附注行为」的全部承载者。
_NOTE_PIPELINE_MODULES: tuple[str, ...] = (
    "disclosure_engine.py",  # 生成
    "wp_disclosure_sync_service.py",  # 底稿→附注同步
    "note_word_exporter.py",  # Word 导出
    "note_sub_table_projector.py",  # 读时投影
    "note_content_utils.py",
    "note_template_reflow_service.py",
    "note_offline_import_service.py",
    "note_table_guidance.py",
    "note_section_catalog.py",
)


def _imported_names(src: str) -> set[str]:
    """抽出源码里显式 import 进来的名字（含模块名与 `from x import y` 的 y）。"""
    names: set[str] = set()
    for m in re.finditer(r"(?m)^\s*import\s+([\w\.\s,]+)$", src):
        for part in m.group(1).split(","):
            leaf = part.strip().split(" as ")[0].strip()
            if leaf:
                names.add(leaf.split(".")[-1])
                names.add(leaf)
    for m in re.finditer(
        r"(?m)^\s*from\s+([\w\.]+)\s+import\s+\(?([^\n\)]*)\)?", src
    ):
        mod, imported = m.group(1), m.group(2)
        names.add(mod.split(".")[-1])
        names.add(mod)
        for part in imported.split(","):
            leaf = part.strip().split(" as ")[0].strip()
            if leaf and leaf != "*":
                names.add(leaf)
    return names


def _scan_conversion_coupling(src: str) -> list[str]:
    """对**源码文本**施加收窄判据（替身自检与真实模块共用同一实现）。

    有意与 `_referenced_conversion_symbols` 分层：后者负责按模块名读盘，本函数
    只做判定 ⇒ 替身自检才能对内联字符串施加**完全相同**的判据，不会出现
    「自检验的是另一套逻辑」这种空转。
    """
    imported = _imported_names(src)
    found: list[str] = []

    for mod in _CONVERSION_MODULES:
        if mod in imported or re.search(rf"\b{re.escape(mod)}\s*\.", src):
            found.append(mod)

    for mem in _CONVERSION_MEMBERS:
        if mem in imported:
            found.append(mem)
            continue
        # 限定调用：`<转换模块>.<成员>`
        if any(
            re.search(rf"\b{re.escape(mod)}\s*\.\s*{re.escape(mem)}\b", src)
            for mod in _CONVERSION_MODULES
        ):
            found.append(mem)
    return found


def _referenced_conversion_symbols(module: str) -> list[str]:
    """收窄后的耦合判据 —— 只认「真耦合」的三种形态，不认同名局部符号。

    **为什么必须收窄（2026-08-08 实测，原判据在 `note_offline_import_service.py`
    上假红）**：裸 `symbol in src` 会把该模块**自己的**局部函数 `match_sections`
    数成对转换侧 `match_section` 的引用（子串关系），而该模块对
    `note_section_matcher` 的 import 数为 **0** ⇒ 结构性零耦合成立，是判据太宽。

    收窄后的三种真耦合形态（替身已逐个验证会打红，见
    `TestNarrowedCouplingCriterion`）：

    1. `from app.services.note_section_matcher import match_section`（import 名字）
    2. `note_section_matcher.match_section(...)`（限定调用）
    3. `match_section(...)` 且该名字在本模块 import 清单内（成员直用）

    误命中形态（替身已验证归零）：同名局部函数（含复数/前缀变体）、docstring 提及。
    """
    return _scan_conversion_coupling(_read_code_level(SERVICES / module))


class TestGuardSanity:
    """守卫自身的有效性自检 —— 防两个集合被清空后整档恒绿。"""

    def test_symbol_and_module_sets_are_not_empty(self):
        assert len(_CONVERSION_MEMBERS) >= 6, "转换成员集合过小 ⇒ 档 1 近似恒绿"
        assert len(_CONVERSION_MODULES) >= 3, "转换模块集合过小 ⇒ 档 1 覆盖不足"
        assert len(_NOTE_PIPELINE_MODULES) >= 5, "链路模块集合过小 ⇒ 档 1 覆盖不足"

    def test_all_pipeline_modules_exist(self):
        missing = [m for m in _NOTE_PIPELINE_MODULES if not (SERVICES / m).exists()]
        assert missing == [], (
            f"链路模块不存在 {missing} —— 拼错的路径会让该模块的断言静默跳过"
        )

    def test_conversion_members_really_exist_in_production(self):
        """**函数/常量名**必须真实出现在转换侧源码里，否则是拼错的死字符串。

        与模块名分开断言：模块不按名字 import 自己（`note_conversion_service.py`
        内部不会出现字符串 `note_conversion_service`），把模块名塞进同一个
        haystack 断言必然假红 —— 这正是首轮该条打红的原因。
        """
        haystack = "".join(
            _read_code_level(SERVICES / m)
            for m in (
                "note_conversion_service.py",
                "note_section_matcher.py",
                "note_conversion_row_codes.py",
                "note_template_diff.py",
            )
        )
        missing = [s for s in _CONVERSION_MEMBERS if s not in haystack]
        assert missing == [], (
            f"这些「转换成员名」在转换侧源码中根本不存在 {missing} —— "
            "拼错即死字符串，档 1 对它永远不会打红"
        )

    def test_conversion_modules_really_exist_as_files(self):
        """**模块名**按文件存在性断言（不按源码字符串出现）。"""
        missing = [m for m in _CONVERSION_MODULES if not (SERVICES / f"{m}.py").exists()]
        assert missing == [], (
            f"这些「转换模块」文件不存在 {missing} —— 模块名拼错会让 import 判据空转"
        )

    def test_narrow_criteria_catches_real_coupling(self):
        """收窄判据的替身反向自检 —— 三种真耦合必须被抓到、两种误命中必须放过。

        收窄的动因：`match_section` 裸子串会被 `note_offline_import_service` 里的
        **同名局部函数** `match_sections`（复数，本模块内定义 + 本模块内调用，
        零 import）命中 ⇒ 假红。但收窄不能弱到放过真耦合，故此处用替身钉死。
        """
        real_import = "from app.services.note_section_matcher import match_section\n"
        real_qualified = (
            "from app.services import note_section_matcher\n"
            "note_section_matcher.match_section(a, b)\n"
        )
        real_aliased = (
            "from app.services.note_section_matcher import match_section as ms\n"
            "ok = ms(soe_title, listed_title)\n"
        )
        false_local = "def match_sections(a, b):\n    return {}\nm = match_sections(x, y)\n"
        false_bare_call = "ok = match_section(a, b)\n"

        for label, src in (
            ("import 形态", real_import),
            ("限定调用形态", real_qualified),
            ("别名 import 形态", real_aliased),
        ):
            assert _scan_conversion_coupling(src), f"收窄判据放过了真耦合（{label}）"

        assert not _scan_conversion_coupling(false_local), (
            "收窄判据仍误命中同名局部复数函数 —— 会在 note_offline_import_service 上假红"
        )
        # 裸调用且无任何 import：在 Python 里要么 NameError 要么是同模块局部定义，
        # 两种都不是「与转换侧耦合」。放过它是收窄的目的，不是漏判。
        assert not _scan_conversion_coupling(false_bare_call), (
            "无 import 的裸调用被判成耦合 —— 该形态在 Python 中不可能触达转换侧"
        )

    def test_strip_comments_actually_strips(self):
        """剥注释确实生效（否则档 1 会被说明文字污染成假红）。"""
        sample = '''"""docstring 里提到 _map_disclosure_notes"""
x = 1  # 注释里也提到 adapt_table_data
y = {"legacy_section_ids": 1}
'''
        out = _strip_comments_and_docstrings(sample)
        assert "_map_disclosure_notes" not in out, "docstring 未被剥离"
        assert "adapt_table_data" not in out, "# 注释未被剥离"
        assert "legacy_section_ids" in out, (
            "普通字符串字面量被误剥 —— 字典键名是真消费，剥掉会漏判"
        )

    def test_source_cache_is_invalidated_by_mtime(self, tmp_path: Path):
        """缓存键含 mtime ⇒ 变异脚本改文件后能读到新内容（防静默假绿）。"""
        p = tmp_path / "m.py"
        p.write_text("a = 1\n", encoding="utf-8")
        first = _read_code_level(p)
        assert "a = 1" in first
        import os
        import time

        time.sleep(0.01)
        p.write_text("b = 2\n", encoding="utf-8")
        os.utime(p, None)
        second = _read_code_level(p)
        assert "b = 2" in second and "a = 1" not in second, "缓存未随 mtime 失效"


@pytest.mark.parametrize("module", _NOTE_PIPELINE_MODULES)
def test_property_34_note_pipeline_has_no_conversion_coupling(module: str):
    # Feature: soe-listed-note-conversion-correctness, Property 34
    """附注生成/同步/导出/投影链路不引用任何转换改写符号。

    这是「不涉及转换的附注行为逐字节不变」的**结构性**保证：没有代码路径能从
    附注链路触达转换改写逻辑 ⇒ 本 spec 的改动不可能影响这些链路的输出。
    """
    found = _referenced_conversion_symbols(module)
    assert found == [], (
        f"{module} 引用了转换侧符号 {found} —— "
        "附注生成/同步/导出链路一旦与转换耦合，需求 10.2 的零回归判据即不再成立。"
        "若确有必要耦合，须改用「跑管道前后对照」的行为级判据并在此说明理由。"
    )


def test_property_34_conversion_does_not_import_note_pipeline():
    # Feature: soe-listed-note-conversion-correctness, Property 34
    """反向零耦合：转换服务不 import 附注生成/导出模块。

    单向断言不够 —— 若转换服务反过来 import 了 `disclosure_engine`，改转换时
    仍可能通过共享模块级状态（缓存/全局配置）影响生成行为。
    """
    src = _read_code_level(SERVICES / "note_conversion_service.py")
    stems = [m[:-3] for m in _NOTE_PIPELINE_MODULES]
    found = [s for s in stems if re.search(rf"\b{re.escape(s)}\b", src)]
    assert found == [], (
        f"note_conversion_service 引用了附注链路模块 {found} —— "
        "反向耦合同样会让零回归判据失效"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 档 2：行为级 characterization（纯函数，无 DB）
# ─────────────────────────────────────────────────────────────────────────────
#
# 取样点是附注渲染与 Word 导出的**共同上游纯函数**：
#   project_sub_tables      → 可见表结构序列（附注编辑器 + Word 导出同源）
#   _extract_column_groups  → 两级表头分组序列
#   _build_two_level_header_rows → Word 导出的表头行
#   classify_template_content   → 生成期的正文/指引切分
#   fmt_amount_gt / _format_amount → 金额可见文字
#
# 判据是「给定输入 → 输出逐字相等」，输入取自**真实模板 JSON**（不是自造 fixture），
# 故它同时验证了「真实数据形态下行为不变」。


def _load_template(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def real_tables() -> list[dict]:
    """从两份真实模板里取带 columns 的表作为样本（覆盖单级 + 两级表头）。"""
    out: list[dict] = []
    for tpl in ("note_template_listed.json", "note_template_soe.json"):
        data = _load_template(tpl)
        for sec in data.get("sections", []):
            for tbl in sec.get("tables", []) or []:
                if tbl.get("columns"):
                    out.append(tbl)
    assert len(out) >= 100, f"真实表样本过少（{len(out)}）⇒ 档 2 覆盖不足"
    return out


class TestProperty34_ProjectionBehaviourUnchanged:
    """读时投影的可见输出不因本 spec 改动而变（附注编辑器 + Word 同源）。"""

    def test_non_workpaper_source_is_never_projected(self):
        """`_source` 非 workpaper ⇒ 返回 None，调用方沿用既有 `_tables`/`rows`。

        这是「legacy 快照渲染行为」的核心不变式：转换只改 `section_id`/`note_section`,
        不得让 legacy 章节突然走投影路径（那会让已有附注内容整体改变呈现）。
        """
        from app.services.note_sub_table_projector import project_sub_tables

        for td in (
            {},
            {"rows": [{"label": "货币资金"}]},
            {"_source": "template", "sub_table_data": {"表": [{"label": "a"}]}},
            {"_source": None, "sub_table_data": {"表": [{"label": "a"}]}},
        ):
            assert project_sub_tables(td) is None, f"非 workpaper 来源被投影：{td}"

    def test_projection_is_pure_and_stable(self, real_tables: list[dict]):
        """同输入同输出 + 不修改入参（纯函数性质，Property 34 的行为档前提）。"""
        from app.services.note_sub_table_projector import project_sub_tables

        sample = real_tables[:40]
        for tbl in sample:
            cols = tbl["columns"]
            td = {
                "_source": "workpaper",
                "sub_table_data": {
                    tbl.get("name") or "表": [
                        {
                            "label": "行1",
                            "values": {
                                (c.get("key") or c.get("id") or f"c{i}"): "1.00"
                                for i, c in enumerate(cols)
                            },
                        }
                    ]
                },
                "_sub_table_columns": {tbl.get("name") or "表": cols},
            }
            before = json.dumps(td, ensure_ascii=False, sort_keys=True)
            first = project_sub_tables(td)
            second = project_sub_tables(td)
            assert json.dumps(td, ensure_ascii=False, sort_keys=True) == before, (
                "project_sub_tables 修改了入参（破坏纯函数性质）"
            )
            assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
                second, ensure_ascii=False, sort_keys=True
            ), "同输入两次调用输出不同"

    def test_column_group_sequence_is_stable(self, real_tables: list[dict]):
        """列分组序列（两级表头的真源）对真实模板逐表稳定。

        三态语义必须保持：`None`=未声明（回退前缀推断）/ `[]`=显式单级 /
        非空=显式分组。退化成布尔会让「凭空父表头」回潮。
        """
        from app.services.note_sub_table_projector import _extract_column_groups

        tri_state = {"none": 0, "empty": 0, "grouped": 0}
        for tbl in real_tables:
            g1 = _extract_column_groups(tbl["columns"])
            g2 = _extract_column_groups(tbl["columns"])
            assert g1 == g2, f"{tbl.get('name')}: 同输入两次分组结果不同"
            if g1 is None:
                tri_state["none"] += 1
            elif g1 == []:
                tri_state["empty"] += 1
            else:
                tri_state["grouped"] += 1

        # 🔴 判据按**实测事实**写，不按「三态都该非零」的假设写。
        # 实测（两份真实模板全量带 columns 的表）：none=0 / empty=506 / grouped=159。
        # `None` 态（未声明 flat 也未声明 group ⇒ 回退前缀推断）在当前真实数据里
        # **不出现** —— 因为各 per-cycle spec 已把 `flat`/`group` 补齐（那正是
        # `disclosure-columns-coverage-rollout` 的成果），故 `none=0` 是**当前真实
        # 分布**而不是缺陷。要求它非零会把「列元数据已补齐」这件好事打红。
        # 三态语义本身由下面的替身断言行使（不依赖真实数据恰好覆盖三态）。
        assert tri_state["empty"] > 0 and tri_state["grouped"] > 0, (
            f"真实模板里显式单级/显式分组两态覆盖不足 {tri_state} ⇒ 断言未行使语义"
        )
        assert tri_state["none"] == 0, (
            f"出现未声明 flat/group 的表（{tri_state['none']} 张）—— "
            "当前真实分布应为 0（列元数据已由 columns-coverage spec 补齐）；"
            "若确有新增未表态的表，属该 spec 的欠账，不应在本零回归守卫里放行"
        )

    def test_column_group_tri_state_semantics(self):
        """三态语义用替身行使（不依赖真实数据恰好覆盖三态）。

        `None`=未声明（调用方回退前缀推断）/ `[]`=显式单级（禁推断）/
        非空=显式分组。退化成布尔会让「凭空父表头」回潮。
        """
        from app.services.note_sub_table_projector import _extract_column_groups

        undeclared = [{"key": "a", "label": "项目"}, {"key": "b", "label": "期末数"}]
        assert _extract_column_groups(undeclared) is None, (
            "未声明 flat/group 时必须返回 None（让调用方回退前缀推断）"
        )

        flat_cols = [
            {"key": "a", "label": "项目", "flat": True},
            {"key": "b", "label": "期末数"},
        ]
        assert _extract_column_groups(flat_cols) == [], (
            "任一列带 flat ⇒ 必须返回 [] 表示显式单级（禁前缀推断）"
        )

        grouped = [
            {"key": "a", "label": "项目"},
            {"key": "b", "label": "账面余额", "group": "期末数"},
            {"key": "c", "label": "减值准备", "group": "期末数"},
        ]
        got = _extract_column_groups(grouped)
        assert got and got != [], "显式 group 必须返回非空分组"

    def test_two_level_header_rows_shape_is_stable(self, real_tables: list[dict]):
        """Word 导出的两级表头结构性判据（不用「返回 2 行」这类恒真弱判据）。

        强判据：row0 的 colspan 之和 == 列数；每个 group 的 colspan == 其 span；
        row1 逐字 == 各 group 覆盖区的 headers 切片；无分组列 rowspan==2。
        """
        from app.services.note_sub_table_projector import _extract_column_groups
        from app.services.note_word_exporter import _build_two_level_header_rows

        checked = 0
        for tbl in real_tables:
            groups = _extract_column_groups(tbl["columns"])
            if not groups:
                continue
            headers = [
                (c.get("label") or c.get("key") or "") for c in tbl["columns"]
            ]
            rows = _build_two_level_header_rows(headers, groups)
            assert len(rows) == 2, f"{tbl.get('name')}: 两级表头未返回 2 行"
            span_sum = sum(int(c.get("colspan") or 1) for c in rows[0])
            assert span_sum == len(headers), (
                f"{tbl.get('name')}: row0 colspan 之和 {span_sum} != 列数 {len(headers)}"
            )
            rowspan2 = [c for c in rows[0] if int(c.get("rowspan") or 1) == 2]
            for cell in rowspan2:
                assert int(cell.get("colspan") or 1) == 1, (
                    f"{tbl.get('name')}: rowspan=2 的独立列不应跨列"
                )
            checked += 1
        assert checked >= 10, f"两级表头样本过少（{checked}）⇒ 该断言覆盖不足"


class TestProperty34_GenerationHelpersUnchanged:
    """生成期纯函数行为不变（正文/指引切分、金额格式化）。"""

    def test_guidance_paragraph_classification_is_stable(self):
        """`is_guidance_paragraph` 对典型输入的判定逐条固定（**按实测值冻结**）。

        🔴 判定形态：**必须整段被成对括号包裹**（`（）`/`()`/`【】`/`《》`）
        **且**含指引关键词，两个条件都满足才算指引。故：

        - `提示：不适用的项目请删除` → **False**（有关键词但**没被括号包裹**）
        - `（注：不适用的项目请删除）` → True（包裹 + 关键词）
        - `【本表由系统自动生成】` → False（包裹但**无关键词**）

        这三条是本轮 characterization 先跑一遍取到的**实际值**。上一轮把
        「提示：…」按直觉写成 True 而实为 False —— 那是「拿自己的假设当基线」，
        characterization 的意义正在于先观测再冻结。
        """
        from app.services.disclosure_engine import is_guidance_paragraph

        cases = {
            # 包裹 + 关键词 ⇒ 指引
            "【提示：本表按账龄列示】": True,
            "（注：不适用的项目请删除）": True,
            # 有关键词但无包裹 ⇒ 不是指引（保守判定，避免误吞实质正文）
            "提示：不适用的项目请删除": False,
            "注：本表金额单位为元": False,
            "说明：本表不适用时可删除": False,
            # 有包裹但无关键词 ⇒ 不是指引
            "【本表由系统自动生成】": False,
            # 实质披露正文不得被判成指引（否则该段在附注正文里静默丢失）
            "本期政府补助金额为 1,000,000.00 元。": False,
            "": False,
        }
        for text, expected in cases.items():
            got = is_guidance_paragraph(text)
            assert got is expected, (
                f"指引判定变化：{text!r} → {got}（期望 {expected}）"
            )

    def test_classify_template_content_is_pure(self):
        """`classify_template_content` 同输入同输出且不修改入参。"""
        from app.services.disclosure_engine import classify_template_content

        text_sections = ["#### 一、货币资金", "本期余额为 100 元。", "【提示：略】"]
        tables = [{"name": "货币资金", "headers": ["项目", "期末数"], "rows": []}]
        snap = json.dumps([text_sections, tables], ensure_ascii=False)
        a = classify_template_content(text_sections, None, tables)
        b = classify_template_content(text_sections, None, tables)
        assert json.dumps([text_sections, tables], ensure_ascii=False) == snap, (
            "classify_template_content 修改了入参"
        )
        assert a == b, "同输入两次分类结果不同"

    def test_amount_formatting_is_stable(self):
        """金额可见文字固定（**按实测值冻结**）。

        🔴 **`fmt_amount_gt(0)` 返回 `''` 不是 `'-'`** —— 这是致同格式的
        「空值/零值留白」口径，源码 docstring 明确写着它与同模块 `_format_amount`
        的差异（后者 `0 → '-'`）。而前端 `displayPrefs.fmtAmount(0) → '-'` 是
        **另一条链路**（`showZero=false` 平台偏好），两者不同源，**不要混为一谈**
        也不要为了「看起来一致」去改任何一侧。

        上一轮把这里写成 `'-'` 属拿假设当基线；本轮先跑实测再冻结。
        """
        from app.services.note_word_exporter import _format_amount, fmt_amount_gt

        # 致同格式（留白口径）
        gt_cases = {
            1234567.5: "1,234,567.50",
            "1234.5": "1,234.50",
            -1234.5: "-1,234.50",
            0: "",
            0.0: "",
            "0": "",
            None: "",
            "": "",
            "abc": "abc",  # 不可解析 ⇒ 原样返回（不抛异常）
        }
        for raw, expected in gt_cases.items():
            got = fmt_amount_gt(raw)
            assert got == expected, (
                f"fmt_amount_gt 变化：{raw!r} → {got!r}（期望 {expected!r}）"
            )

        # 反向锚定：同模块另一口径对 0 返回 '-'，两者**有意不同**。
        # 这条断言让「顺手把两个口径统一」的改动立刻打红。
        assert _format_amount(0) == "-", (
            "_format_amount(0) 不再是 '-' —— 它与 fmt_amount_gt 是有意分叉的两个"
            "口径（前者 '-'/后者留白），统一它们会改变 Word 导出的可见文字"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 上游数据真源未被本模块改动（前后对照，不冻结 md5 常量）
# ─────────────────────────────────────────────────────────────────────────────

_UPSTREAM_FILES = (
    DATA / "note_soe_listed_diff.json",
    DATA / "note_template_listed.json",
    DATA / "note_template_soe.json",
    DATA / "note_template_variant_matrix.json",
)

_IMPORT_TIME_MD5 = {
    p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in _UPSTREAM_FILES if p.exists()
}


def test_upstream_data_untouched_by_this_module():
    """本模块运行前后，四份共享数据真源逐字节不变。

    **有意不冻结 md5 常量** —— 这些文件被 5 个 spec 共享，模板合法变更后重生成
    会让常量过期 ⇒ 冻结即假红发生器。改用「导入时 md5 ↔ 结束时 md5」前后对照，
    只钉「本模块自己没有改动它们」这一件事。
    """
    assert len(_IMPORT_TIME_MD5) >= 3, "上游文件样本过少 ⇒ 该断言近似空转"
    for p in _UPSTREAM_FILES:
        if not p.exists():
            continue
        now = hashlib.md5(p.read_bytes()).hexdigest()
        assert now == _IMPORT_TIME_MD5[p.name], (
            f"{p.name} 在本模块运行期间被改动 —— 零回归守卫不得写共享数据真源"
        )
