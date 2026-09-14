"""母公司附注章判据守卫（Task 2，先于任何修订必须先打红）。

三向比对：**源 docx**（唯一裁决者）↔ ``note_template_{listed,soe}.json`` ↔ 本文件登记的事实基线。

设计要点（改动前先读）:

- **判据真源是 ``docs/模版/`` 两份源 docx，不是模板 JSON**（后者是 md 重建产物）。docx 解析一律
  复用 Task 1 的只读提取器 ``backend/scripts/diagnose/extract_parent_company_chapter_facts.py``，
  **不在本文件重抄 python-docx 逻辑**（两份解析会漂移）。
- **源 docx 缺失必须打红，不得 skip**（Requirements 1.2）。fixture 捕获 ``SourceDocxMissingError``
  后走 ``pytest.fail``；另有 ``test_source_docx_missing_is_hard_failure`` 反向自检证明该机制有效。
- 每条核心 Property 的判定逻辑抽成**纯函数 ``check_*``（返回违规清单）**，真实数据与**替身数据**
  共用同一函数 → 反向自检（把结构改坏必红）证明判据非空转，而不是"断言恰好通过"。
- **本文件只读**：不写 ``note_template_*.json``（listed 1.35 MB / soe 851 KB，并发会话会互相回退）。
- ``xfail(strict=True)`` 曾标注「Task 3~7 修完前必红」的断言。**Task 3~7 已全部完成
  （2026-08-06）⇒ 本文件现已无任何 xfail**，全部转正向断言；历次移除的记录见下方
  「已到期并移除的 xfail」注释块。**禁用 skip**（绿守卫会被下个会话当成"已实现"的证据）。

_Requirements: 1.1, 1.3, 1.4, 1.5, 2.4, 3.1, 3.2, 3.3_
"""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import re
import sys
import tokenize
from pathlib import Path
from typing import Any

import pytest

# ── 仓库根定位：双哨兵具体文件向上查找（单哨兵/目录哨兵都会误停） ──────────────
_SENTINELS = (
    Path("backend/data/note_template_listed.json"),
    Path("backend/scripts/diagnose/extract_parent_company_chapter_facts.py"),
)


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for cand in (here, *here.parents):
        if all((cand / s).exists() for s in _SENTINELS):
            return cand
    raise RuntimeError(
        "无法定位仓库根（哨兵: " + " / ".join(str(s) for s in _SENTINELS) + "）"
    )


REPO_ROOT = _find_repo_root()
EXTRACTOR_PATH = (
    REPO_ROOT / "backend" / "scripts" / "diagnose" / "extract_parent_company_chapter_facts.py"
)
TEMPLATE_JSON = {
    "listed": REPO_ROOT / "backend" / "data" / "note_template_listed.json",
    "soe": REPO_ROOT / "backend" / "data" / "note_template_soe.json",
}


def _load_extractor() -> Any:
    """import Task 1 的提取器（scripts/diagnose 不是包，只能按路径加载）。"""
    spec = importlib.util.spec_from_file_location(
        "_extract_parent_company_chapter_facts", EXTRACTOR_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"无法加载提取器: {EXTRACTOR_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


EX = _load_extractor()


# ── 事实基线（全部取自 Task 1 对源 docx 的实测，勿凭记忆改） ─────────────────
PARENT_CHAPTER_SID = {
    # listed 章 slug 本就反映母公司语义（需求 3.2 裁决保留现值）；
    # soe 侧已由 Task 3 从错误 slug `chapter-12-gu-fen-zhi-fu` 改写为母公司语义 slug。
    "listed": "chapter-16-mu-gong-si-cai-wu-bao-biao-zhu-yao-xiang-mu-zhu-shi",
    "soe": "chapter-12-mu-gong-si-cai-wu-bao-biao-de-zhu-yao-xiang-mu-fu-zhu",
}
# Task 3 改写前的旧 slug —— 现在只应出现在 `legacy_aliases` 里（需求 2.3 不丢数据）
PARENT_CHAPTER_SID_LEGACY = {"soe": "chapter-12-gu-fen-zhi-fu"}

# 源 docx Heading 1 原文（唯一裁决者）
DOCX_PARENT_CHAPTER_TITLE = {
    "listed": "公司财务报表主要项目注释",
    "soe": "母公司财务报表的主要项目附注",
}
# JSON 现值（listed 侧多一个「母」字，需求 3.2 已裁决保留）
JSON_PARENT_CHAPTER_TITLE_LISTED = "母公司财务报表主要项目注释"

DOCX_HEADING1_COUNT = {"listed": 17, "soe": 14}
FORBIDDEN_SOE_HEADING1 = "股份支付"
SOE_WRONG_SLUG = "gu-fen-zhi-fu"

# 源 docx 子节（归一标题 → 自有表数量）；0 == 同构子节
DOCX_SECTIONS: dict[str, dict[str, int]] = {
    "listed": {
        "应收票据": 0,
        "应收账款": 0,
        "其他应收款": 0,
        "长期股权投资": 3,
        "营业收入和营业成本": 0,
        "投资收益": 1,
    },
    "soe": {
        "应收账款": 0,
        "其他应收款": 0,
        "长期股权投资": 3,
        "营业收入与营业成本": 0,
        "投资收益": 1,
        "现金流量表补充资料": 1,
    },
}

# 两版不对称的独有子节（需求 1.3，禁对齐）
LISTED_ONLY_SECTION = "应收票据"
SOE_ONLY_SECTION = "现金流量表补充资料"

# 母公司章子节数（需求 4.8）
EXPECTED_SUBSECTION_COUNT = {"listed": 6, "soe": 6}

# 长期股权投资列数：源 docx 目标（Task 5 已把 JSON 还原到该目标态）
LTE_COLS_DOCX = {"listed": [7, 9, 13], "soe": [5, 7, 12]}
# 🔴 Task 5 修订**前**的压扁现值。现已不再等于 JSON 实测值 —— 保留它只为两个目的：
#   1. 登记「曾经压扁成什么样」，供回退检测（若哪天又被压回来，正向断言会红且这里给出对照）
#   2. 反向自检 `check_column_counts` 判据非空转
# **不得**再拿它对 JSON 断言（那正是 Task 5 完成后要移除的 xfail 锚点）。
LTE_COLS_JSON_BEFORE_TASK5 = {"listed": [3, 6, 5], "soe": [5, 7, 5]}
# soe 表 1/表 2 与源一致 —— 需求 4.4 明令不得当压扁改动
SOE_LTE_ALREADY_CORRECT_COLS = (5, 7)

# 🔴 **`CURRENT_MISSING_COLUMNS_COUNT` 已随 Task 7 完成而移除（2026-08-06）**。
#
# 它曾是「仍缺 columns 的表数」进度刻度，历经三次变化：
#   Task 5 前 57/36（母公司章全部表）→ Task 5 后 54/33（补了两版各 3 张长期股权投资表）
#   → Task 6 后 **1/2**（7 个同构子节按合并章整体替换而继承齐备列结构）
#   → Task 7 后 **0/0**（补齐 listed/投资收益 + soe/{投资收益,现金流量表补充资料} 三张）
#
# 降到 0 后它变成恒 0 的死锚点（无论结构怎么退化都只能是「≥0」），故按 tasks.md 的
# 要求改为**正向断言**：母公司章 62/42 张表**全部**有 columns + guidance，规模锚点
# 由 `JSON_PARENT_TABLE_COUNT` 承担（表数一变即打红）。
# 下个会话若想「加回一个允许缺列的数字」——那正是本行要禁止的事。
#
# soe 表 1/表 2 与源一致 —— 需求 4.4 明令不得当压扁改动
SOE_LTE_ALREADY_CORRECT_INDEXES = (0, 1)

# 母公司章表数（JSON 现值）。2026-08-06 Task 6 后实测：同构子节按合并章替换后
# listed 57→62（应收账款 15→17 / 其他应收款 18→21）、soe 36→42（应收账款 11→13 /
# 其他应收款 15→19）—— 母公司侧原先缺的表由合并章补齐，**子节数量未变**（需求 4.8）。
JSON_PARENT_TABLE_COUNT = {"listed": 62, "soe": 42}

# 已登记的两版用语差异：JSON 两版都写「与」，listed 源 docx 写「和」。
# 属用语差异不属结构缺陷，登记在此防下个会话把它当欠账"修正"。
KNOWN_WORDING_DIFF = {
    "listed": {"docx": "营业收入和营业成本", "json": "营业收入与营业成本"},
}


# ── 判定纯函数（真实数据与替身共用，保证判据非空转） ─────────────────────────
def check_chapter_present(
    sections: list[dict[str, Any]], chapter_sid: str, expected_children: int
) -> list[str]:
    """母公司章标题行与全部子节必须存在（Property 1 / 需求 1.5、4.8）。"""
    problems: list[str] = []
    chapter = next((s for s in sections if s.get("section_id") == chapter_sid), None)
    if chapter is None:
        problems.append(f"母公司章不存在: section_id={chapter_sid}（禁删，见已裁决事项 1）")
        return problems
    if chapter.get("level") != 1:
        problems.append(f"母公司章 level 应为 1，实为 {chapter.get('level')!r}")
    kids = [s for s in sections if s.get("parent_section_id") == chapter_sid]
    if len(kids) != expected_children:
        problems.append(
            f"母公司章子节数应为 {expected_children}，实为 {len(kids)}"
            f"（标题: {[k.get('section_title') for k in kids]}）"
        )
    for k in kids:
        if not (k.get("tables") is not None or k.get("text_sections")):
            problems.append(f"子节缺内容: {k.get('section_title')!r}")
    return problems


def check_subsection_asymmetry(
    listed_titles: set[str], soe_titles: set[str]
) -> list[str]:
    """两版子节集合必须不对称且不被强行对齐（Property 3 / 需求 1.3）。双向断言。"""
    problems: list[str] = []
    if LISTED_ONLY_SECTION not in listed_titles:
        problems.append(f"listed 应独有「{LISTED_ONLY_SECTION}」，实际缺失")
    if LISTED_ONLY_SECTION in soe_titles:
        problems.append(f"soe 不应有「{LISTED_ONLY_SECTION}」，两版被强行对齐")
    if SOE_ONLY_SECTION not in soe_titles:
        problems.append(f"soe 应独有「{SOE_ONLY_SECTION}」，实际缺失")
    if SOE_ONLY_SECTION in listed_titles:
        problems.append(f"listed 不应有「{SOE_ONLY_SECTION}」，两版被强行对齐")
    if listed_titles == soe_titles:
        problems.append("两版子节集合相等 —— 违反需求 1.3「不对称且不得对齐」")
    return problems


def check_section_kinds(
    docx_sections: list[dict[str, Any]], expected: dict[str, int]
) -> list[str]:
    """同构子节在源 docx 无自有表；自有表子节有表且表数匹配（Property 4 / 需求 1.4、4.1、4.2）。"""
    problems: list[str] = []
    actual = {s["normalized_title"]: s for s in docx_sections}
    for title, want_tables in expected.items():
        sec = actual.get(title)
        if sec is None:
            problems.append(f"源 docx 缺子节「{title}」")
            continue
        got = sec["own_table_count"]
        if got != want_tables:
            problems.append(f"「{title}」自有表数应为 {want_tables}，源 docx 实为 {got}")
        if want_tables == 0 and not sec["is_isomorphic"]:
            problems.append(f"「{title}」应为同构子节（无自有表），实测 is_isomorphic=False")
        if want_tables > 0 and sec["is_isomorphic"]:
            problems.append(f"「{title}」应为自有表子节，实测被判成同构")
        if want_tables > 0 and len(sec["tables"]) != want_tables:
            problems.append(
                f"「{title}」tables 明细数 {len(sec['tables'])} 与 own_table_count {got} 不一致"
            )
    extra = set(actual) - set(expected)
    if extra:
        problems.append(f"源 docx 出现未登记子节: {sorted(extra)}（子节集合变更需重新裁决）")
    return problems


def check_no_forbidden_heading1(
    heading1_titles: list[str], forbidden: str, expected_count: int
) -> list[str]:
    """国企源 docx 的 Heading 1 中不得含「股份支付」（Property 5 后半 / 需求 2.4）。"""
    problems: list[str] = []
    if len(heading1_titles) != expected_count:
        problems.append(
            f"Heading 1 数量应为 {expected_count}，实为 {len(heading1_titles)}: {heading1_titles}"
        )
    hits = [t for t in heading1_titles if forbidden in t]
    if hits:
        problems.append(
            f"源 docx Heading 1 出现「{forbidden}」: {hits}"
            "（若源模板真加了该章，需求 2.4 的裁决前提失效，必须重新裁决）"
        )
    return problems


def check_listed_title_deviation(json_title: str, docx_title: str) -> list[str]:
    """listed 标题偏差双向锁死（Property 8 / 需求 3.1、3.2、3.3）。任一侧变化即红。"""
    problems: list[str] = []
    if json_title != JSON_PARENT_CHAPTER_TITLE_LISTED:
        problems.append(
            f"JSON 现值应保留「{JSON_PARENT_CHAPTER_TITLE_LISTED}」（需求 3.2），实为「{json_title}」"
        )
    if docx_title != DOCX_PARENT_CHAPTER_TITLE["listed"]:
        problems.append(
            f"源 docx 现值应为「{DOCX_PARENT_CHAPTER_TITLE['listed']}」，实为「{docx_title}」"
            "（源模板已变更 → 需求 3 的偏差裁决必须重做）"
        )
    if json_title == docx_title:
        problems.append("偏差消失：两侧已相等，需求 3 的登记项失去意义，需重新裁决")
    return problems


def check_soe_chapter_title(json_title: str, docx_title: str) -> list[str]:
    """soe 第 12 章标题应逐字取自源 docx Heading 1（Property 5 前半 / 需求 2.1）。"""
    if json_title != docx_title:
        return [f"soe 第 12 章 section_title 应为「{docx_title}」，实为「{json_title}」"]
    return []


def check_slug_free_of(sids: list[str], forbidden_slug: str) -> list[str]:
    """章与子节 section_id 不得带错误 slug（需求 2.2）。"""
    hits = [s for s in sids if forbidden_slug in s]
    if hits:
        return [f"section_id 仍含错误 slug「{forbidden_slug}」: {hits}"]
    return []


def check_tables_have_columns(tables: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """母公司章全部表必须有非空 columns（需求 5.1）。"""
    problems: list[str] = []
    for where, tbl in tables:
        cols = tbl.get("columns")
        if not cols:
            problems.append(f"{where} 表「{tbl.get('name')}」columns 缺失或为空")
    return problems


def check_column_counts(actual: list[int], expected: list[int], label: str) -> list[str]:
    """长期股权投资列数匹配源 docx（design Property 9 / 需求 4.3、4.4）。"""
    if actual != expected:
        return [f"{label} 列数应为 {expected}，实为 {actual}"]
    return []


# ── fixtures（源 docx 缺失必须 fail 不得 skip，Requirements 1.2） ─────────────
@pytest.fixture(scope="module")
def docx_facts() -> dict[str, Any]:
    """源 docx 事实基线（复用 Task 1 提取器，不重抄 docx 解析）。"""
    try:
        return EX.build_facts()
    except EX.SourceDocxMissingError as exc:
        pytest.fail(
            f"源 docx 缺失，判据失效必须打红（Requirements 1.2）: {exc}", pytrace=False
        )
    except EX.ChapterNotFoundError as exc:
        pytest.fail(f"源 docx 中未找到母公司章，判据失效: {exc}", pytrace=False)
    except ImportError as exc:  # python-docx 缺失同样属判据失效
        pytest.fail(f"python-docx 不可用，判据失效必须打红: {exc}", pytrace=False)


@pytest.fixture(scope="module")
def templates() -> dict[str, list[dict[str, Any]]]:
    """两份模板 JSON 的 sections（**只读**，本文件禁写入）。"""
    out: dict[str, list[dict[str, Any]]] = {}
    for variant, path in TEMPLATE_JSON.items():
        if not path.exists():
            pytest.fail(f"{variant} 模板 JSON 不存在: {path}", pytrace=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        out[variant] = data["sections"]
    return out


def _chapter(sections: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    sid = PARENT_CHAPTER_SID[variant]
    ch = next((s for s in sections if s.get("section_id") == sid), None)
    assert ch is not None, f"{variant} 母公司章不存在: {sid}"
    return ch


def _children(sections: list[dict[str, Any]], variant: str) -> list[dict[str, Any]]:
    sid = PARENT_CHAPTER_SID[variant]
    return [s for s in sections if s.get("parent_section_id") == sid]


def _parent_tables(
    sections: list[dict[str, Any]], variant: str
) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for kid in _children(sections, variant):
        for tbl in kid.get("tables") or []:
            out.append((f"{variant}/{kid.get('section_title')}", tbl))
    return out


def _docx_parent(docx_facts: dict[str, Any], variant: str) -> dict[str, Any]:
    return docx_facts["parent_chapter"][variant]


# ── Property 2：判据来自源 docx 而非模板 JSON（需求 1.1、1.2） ────────────────
class TestSourceIsDocx:
    def test_source_docx_paths_registered_and_exist(self) -> None:
        assert set(EX.SOURCE_DOCX) == {"listed", "soe"}
        for variant, path in EX.SOURCE_DOCX.items():
            assert path.exists(), (
                f"{variant} 源 docx 不存在: {path} —— 判据真源缺失必须打红（Requirements 1.2）"
            )

    def test_parent_chapter_located_by_heading1(self, docx_facts: dict[str, Any]) -> None:
        for variant in ("listed", "soe"):
            ch = _docx_parent(docx_facts, variant)
            assert ch["chapter_title"].replace(" ", "") == DOCX_PARENT_CHAPTER_TITLE[
                variant
            ].replace(" ", ""), f"{variant} 母公司章标题与登记不符: {ch['chapter_title']!r}"
            assert ch["body_index"] > 0
            assert ch["top_child_level"] in (2, 3)

    def test_source_docx_missing_is_hard_failure(self, tmp_path: Path) -> None:
        """反向自检：源 docx 缺失时提取器必须抛 SourceDocxMissingError（而非静默返回空）。"""
        missing = tmp_path / "not-exist.docx"
        with pytest.raises(EX.SourceDocxMissingError) as ei:
            EX._load_doc(missing, variant="listed")
        assert str(missing) in str(ei.value), "报错必须打印期望路径"
        assert issubclass(EX.SourceDocxMissingError, FileNotFoundError)

    def test_guard_does_not_self_certify_from_json(self) -> None:
        """反向自检：本守卫文件必须真的 import 源 docx 提取器，不得以 JSON 自证。"""
        src = Path(__file__).read_text(encoding="utf-8")
        assert "extract_parent_company_chapter_facts" in src
        assert "build_facts" in src


# ── Property 1：母公司章存在且不可删除（需求 1.5、4.8） ──────────────────────
class TestChapterPresence:
    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_chapter_and_subsections_exist(
        self, templates: dict[str, list[dict[str, Any]]], variant: str
    ) -> None:
        problems = check_chapter_present(
            templates[variant],
            PARENT_CHAPTER_SID[variant],
            EXPECTED_SUBSECTION_COUNT[variant],
        )
        assert not problems, "母公司章判据违规:\n" + "\n".join(problems)

    def test_docx_subsection_count_matches(self, docx_facts: dict[str, Any]) -> None:
        for variant in ("listed", "soe"):
            secs = _docx_parent(docx_facts, variant)["sections"]
            assert len(secs) == EXPECTED_SUBSECTION_COUNT[variant], (
                f"{variant} 源 docx 子节数应为 {EXPECTED_SUBSECTION_COUNT[variant]}，实为 {len(secs)}"
            )

    def test_selfcheck_deleting_chapter_turns_red(self) -> None:
        """反向自检：删掉母公司章（替身数据）必打红。"""
        stub = [{"section_id": "other", "level": 1}]
        problems = check_chapter_present(stub, PARENT_CHAPTER_SID["soe"], 6)
        assert problems and "不存在" in problems[0]

    def test_selfcheck_dropping_subsection_turns_red(self) -> None:
        """反向自检：子节少一个必打红。"""
        sid = PARENT_CHAPTER_SID["soe"]
        stub: list[dict[str, Any]] = [{"section_id": sid, "level": 1}]
        stub += [
            {"section_id": f"{sid}-k{i}", "parent_section_id": sid, "tables": []}
            for i in range(5)
        ]
        problems = check_chapter_present(stub, sid, 6)
        assert any("子节数应为 6" in p for p in problems)


# ── Property 3：两版子节集合不对称（需求 1.3） ───────────────────────────────
class TestSubsectionAsymmetry:
    def test_json_subsections_asymmetric(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        listed = {c["section_title"] for c in _children(templates["listed"], "listed")}
        soe = {c["section_title"] for c in _children(templates["soe"], "soe")}
        problems = check_subsection_asymmetry(listed, soe)
        assert not problems, "两版子节对称性违规:\n" + "\n".join(problems)

    def test_docx_subsections_asymmetric(self, docx_facts: dict[str, Any]) -> None:
        listed = {
            s["normalized_title"] for s in _docx_parent(docx_facts, "listed")["sections"]
        }
        soe = {s["normalized_title"] for s in _docx_parent(docx_facts, "soe")["sections"]}
        problems = check_subsection_asymmetry(listed, soe)
        assert not problems, "源 docx 两版子节对称性违规:\n" + "\n".join(problems)

    def test_selfcheck_equal_sets_turn_red(self) -> None:
        """反向自检：把两版子节集合改成相等则必红（需求 1.3 的反向断言）。"""
        common = set(DOCX_SECTIONS["listed"]) | set(DOCX_SECTIONS["soe"])
        problems = check_subsection_asymmetry(common, common)
        assert problems, "两版集合相等却未打红 —— 判据空转"
        assert any("强行对齐" in p or "集合相等" in p for p in problems)

    def test_selfcheck_missing_exclusive_section_turns_red(self) -> None:
        listed = set(DOCX_SECTIONS["listed"]) - {LISTED_ONLY_SECTION}
        soe = set(DOCX_SECTIONS["soe"])
        problems = check_subsection_asymmetry(listed, soe)
        assert any(LISTED_ONLY_SECTION in p for p in problems)


# ── Property 4：同构 / 自有表两类清单与源 docx 一致（需求 1.4、4.1、4.2） ─────
class TestSectionKinds:
    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_docx_section_kinds(self, docx_facts: dict[str, Any], variant: str) -> None:
        secs = _docx_parent(docx_facts, variant)["sections"]
        problems = check_section_kinds(secs, DOCX_SECTIONS[variant])
        assert not problems, f"{variant} 同构/自有表清单违规:\n" + "\n".join(problems)

    def test_isomorphic_evidence_registered(self, docx_facts: dict[str, Any]) -> None:
        """同构依据两级：listed 在子节标题、soe 在章首说明（需求 1.4）。"""
        listed = _docx_parent(docx_facts, "listed")
        iso_listed = [s for s in listed["sections"] if s["is_isomorphic"]]
        assert iso_listed, "listed 应有同构子节"
        for s in iso_listed:
            assert s["has_reference_note"], (
                f"listed 同构子节「{s['normalized_title']}」标题应含「披露格式参考附注五、X」，"
                f"实测 reference_text={s['reference_text']!r}"
            )
            assert "披露格式参考附注" in (s["reference_text"] or "")

        soe = _docx_parent(docx_facts, "soe")
        assert soe["chapter_reference_text"], (
            "soe 章首说明应含「应参照上述相应项目的要求加以注释」，实测为空"
        )
        assert "参照" in soe["chapter_reference_text"]
        # soe 的参照声明在章首（第 2 段），不在子节标题里
        for s in soe["sections"]:
            if s["is_isomorphic"]:
                assert not s["has_reference_note"], (
                    f"soe 同构子节「{s['normalized_title']}」的参照声明应在章首说明，不在标题里"
                )

    def test_own_table_counts_match_docx(self, docx_facts: dict[str, Any]) -> None:
        """自有表子节的表数与列数逐一匹配源 docx（需求 4.2、4.3、4.4、4.7）。"""
        listed = {
            s["normalized_title"]: s for s in _docx_parent(docx_facts, "listed")["sections"]
        }
        soe = {s["normalized_title"]: s for s in _docx_parent(docx_facts, "soe")["sections"]}

        lte_l = listed["长期股权投资"]
        assert [t["cols"] for t in lte_l["tables"]] == LTE_COLS_DOCX["listed"]
        assert all(t["two_level_header"] for t in lte_l["tables"]), (
            "listed 长期股权投资 3 表应均为两级表头"
        )

        lte_s = soe["长期股权投资"]
        assert [t["cols"] for t in lte_s["tables"]] == LTE_COLS_DOCX["soe"]
        assert [t["two_level_header"] for t in lte_s["tables"]] == [False, False, True], (
            "soe 长期股权投资只有表 3 是两级表头（表 1/表 2 单级且列数已正确）"
        )

        inv_l = listed["投资收益"]
        assert [t["cols"] for t in inv_l["tables"]] == [3]
        assert [t["rows"] for t in inv_l["tables"]] == [16]
        inv_s = soe["投资收益"]
        assert [t["cols"] for t in inv_s["tables"]] == [3]
        assert [t["rows"] for t in inv_s["tables"]] == [21]

        cf_s = soe["现金流量表补充资料"]
        assert [t["cols"] for t in cf_s["tables"]] == [3]
        assert [t["rows"] for t in cf_s["tables"]] == [31]

    def test_selfcheck_isomorphic_with_table_turns_red(self) -> None:
        """反向自检：给同构子节塞一张表则必红。"""
        stub = [
            {
                "normalized_title": "应收账款",
                "own_table_count": 1,
                "is_isomorphic": False,
                "tables": [{"cols": 3}],
            }
        ]
        problems = check_section_kinds(stub, {"应收账款": 0})
        assert problems and any("自有表数应为 0" in p for p in problems)

    def test_selfcheck_own_table_count_drift_turns_red(self) -> None:
        stub = [
            {
                "normalized_title": "长期股权投资",
                "own_table_count": 2,
                "is_isomorphic": False,
                "tables": [{"cols": 5}, {"cols": 7}],
            }
        ]
        problems = check_section_kinds(stub, {"长期股权投资": 3})
        assert any("应为 3" in p for p in problems)

    def test_selfcheck_extra_section_turns_red(self) -> None:
        stub = [
            {"normalized_title": "应收账款", "own_table_count": 0, "is_isomorphic": True, "tables": []},
            {"normalized_title": "凭空科目", "own_table_count": 0, "is_isomorphic": True, "tables": []},
        ]
        problems = check_section_kinds(stub, {"应收账款": 0})
        assert any("未登记子节" in p for p in problems)


# ── Property 5 后半：soe 源 docx 14 个 Heading 1 不含「股份支付」（需求 2.4） ──
class TestSoeHeading1:
    def test_soe_docx_has_no_share_payment_chapter(self, docx_facts: dict[str, Any]) -> None:
        titles = _docx_parent(docx_facts, "soe")["heading1_titles"]
        problems = check_no_forbidden_heading1(
            titles, FORBIDDEN_SOE_HEADING1, DOCX_HEADING1_COUNT["soe"]
        )
        assert not problems, "soe Heading 1 判据违规:\n" + "\n".join(problems)

    def test_listed_docx_does_have_share_payment_chapter(
        self, docx_facts: dict[str, Any]
    ) -> None:
        """正对照：「股份支付」确实是 listed 侧的章 —— 证明 soe 侧那个章名是串入错误。"""
        titles = _docx_parent(docx_facts, "listed")["heading1_titles"]
        assert len(titles) == DOCX_HEADING1_COUNT["listed"]
        assert any(FORBIDDEN_SOE_HEADING1 in t for t in titles), (
            "listed 源 docx 应含「股份支付」章（soe 的错误章名由此串入）；"
            f"实际 Heading 1: {titles}"
        )

    def test_selfcheck_forbidden_heading_turns_red(self) -> None:
        """反向自检：往 soe Heading 1 清单里塞「股份支付」必红（判据非空转）。"""
        titles = ["公司基本情况"] * 13 + ["股份支付"]
        problems = check_no_forbidden_heading1(titles, FORBIDDEN_SOE_HEADING1, 14)
        assert problems and any("股份支付" in p for p in problems)

    def test_selfcheck_heading_count_drift_turns_red(self) -> None:
        problems = check_no_forbidden_heading1(["a"] * 13, FORBIDDEN_SOE_HEADING1, 14)
        assert any("数量应为 14" in p for p in problems)


# ── Property 8：listed 标题偏差双向锁死（需求 3.1、3.2、3.3） ─────────────────
class TestListedTitleDeviation:
    def test_deviation_locked_both_sides(
        self, templates: dict[str, list[dict[str, Any]]], docx_facts: dict[str, Any]
    ) -> None:
        json_title = _chapter(templates["listed"], "listed")["section_title"]
        docx_title = _docx_parent(docx_facts, "listed")["chapter_title"]
        problems = check_listed_title_deviation(json_title, docx_title)
        assert not problems, "listed 标题偏差锁死违规:\n" + "\n".join(problems)

    def test_deviation_is_exactly_one_char(
        self, templates: dict[str, list[dict[str, Any]]], docx_facts: dict[str, Any]
    ) -> None:
        """偏差登记项：JSON 比源 docx 多一个「母」字（需求 3.1）。"""
        json_title = _chapter(templates["listed"], "listed")["section_title"]
        docx_title = _docx_parent(docx_facts, "listed")["chapter_title"]
        assert json_title == "母" + docx_title, (
            f"偏差形态应为「母」+ 源 docx 原文；JSON={json_title!r} docx={docx_title!r}"
        )

    def test_selfcheck_json_side_change_turns_red(self) -> None:
        problems = check_listed_title_deviation(
            "公司财务报表主要项目注释", DOCX_PARENT_CHAPTER_TITLE["listed"]
        )
        assert problems, "JSON 侧被改成与 docx 相同却未打红"
        assert any("JSON 现值" in p for p in problems)

    def test_selfcheck_docx_side_change_turns_red(self) -> None:
        problems = check_listed_title_deviation(
            JSON_PARENT_CHAPTER_TITLE_LISTED, "母公司财务报表主要项目注释"
        )
        assert problems, "源 docx 侧变化却未打红"
        assert any("源 docx 现值" in p for p in problems)


# ══════════════════════════════════════════════════════════════════════════════
# 以下为「本任务完成时预期必红」的判据 —— 它们描述的是**目标态**，而当前 JSON
# 仍是缺陷态，故一律 xfail(strict=True)：
#   · 当前必须 xfail（红得准 ⇒ 判据有效）
#   · Task 3~7 修完后会变成 XPASS 而 strict=True 让整套打红
#     🔴 届时**必须移除对应 xfail 标记**（这是它存在的唯一目的）
# 禁用 skip —— 绿守卫会被下个会话当成「已实现」的证据。
# ══════════════════════════════════════════════════════════════════════════════

# 🔴 已到期并移除的 xfail（按其存在的唯一目的处置，勿再加回）:
#
# - **Task 3 已完成（2026-08-06）**：soe 第 12 章标题 / section_id / 6 子节前缀已改写，
#   旧 slug 已进 legacy_aliases ⇒ 原 `_XFAIL_SOE_TITLE` / `_XFAIL_SOE_SLUG` 已移除。
# - **Task 5 已完成（2026-08-06）**：长期股权投资 3 表两级表头已还原
#   （listed `[3,6,5]`→`[7,9,13]` / soe `[5,7,5]`→`[5,7,12]`，soe 表 1/表 2 只补
#   `columns` 未动 headers/rows）⇒ 原 `_XFAIL_LTE` 已移除，`TestLongTermEquityTarget`
#   全部转正向断言。
#
# - **Task 7 已完成（2026-08-06）**：母公司章 62/42 张表的 columns 与 guidance 全部
#   齐备（自有表子节最后 3 张由 Task 7 补：listed/投资收益、soe/投资收益、
#   soe/现金流量表补充资料），listed/投资收益 的表头首格泄漏名「项  目」已正名为
#   「投资收益」⇒ 原 `_XFAIL_COLUMNS` 与 `_XFAIL_LISTED_INV_INCOME_LEAK` 已移除，
#   `TestColumnsTarget` 与表名泄漏档全部转正向断言。
#
# 🔴 **本文件现已无任何 xfail** —— 若下个会话又要加，请先问：它描述的是「目标态未做」
# 还是「判据可能失效」？只有前者才配 xfail(strict)，且必须写清移除条件。


# ── Property 5 前半：soe 第十二章标题为母公司章（需求 2.1） ───────────────────
# ── 缺陷现值常量与可复用检查函数（供反向自检复用同一判据） ──────────────
# 2026-08-05 只读探针实测值，Task 3 修完后 xfail(strict) 会自动转红提醒移除本节。
CURRENT_SOE_CHAPTER_TITLE = "股份支付"
BAD_SOE_SLUG_FRAGMENT = "gu-fen-zhi-fu"
# 完整旧 slug（Task 3 改写前的章 sid）。片段 `gu-fen-zhi-fu` 不能单独用于
# 「是否残留」判定 —— listed 侧真有股份支付章、soe 侧「四、…股份支付」子节也带该片段，
# 按片段扫会误伤合法 sid；判残留一律用完整前缀。
BAD_SOE_SLUG_FRAGMENT_FULL = "chapter-12-gu-fen-zhi-fu"


def check_soe_slug_free_of_share_payment(chapter: dict, kids: list[dict]) -> list[str]:
    """返回仍带错误 slug 片段的 section_id 清单；空列表 = 合格。"""
    bad: list[str] = []
    if BAD_SOE_SLUG_FRAGMENT in (chapter.get("section_id") or ""):
        bad.append(chapter["section_id"])
    bad.extend(
        k["section_id"] for k in kids if BAD_SOE_SLUG_FRAGMENT in (k.get("section_id") or "")
    )
    return bad


#: 上游（**合并章**）已存在的 `flat` + `group` 并存缺陷登记。
#:
#: 🔴 为什么要登记而不是修
#: -----------------------
#: 同构子节的列结构真源是**合并章**（需求 4.1，Task 6 做整体替换），母公司侧自行
#: 「纠正」会与合并章分叉 ⇒ `check_isomorphic` 的深相等判据永远报欠账、`--apply`
#: 每轮都报变更（幂等空操作永不成立）。而合并章属本 spec 的**只读源**
#: （Property 28 合并章零回归），不得反向修改。
#:
#: 缺陷本体（2026-08-07 实测）
#: --------------------------
#: `note_sub_table_projector._extract_column_groups` 里
#: `if any(d.get("flat") for d in defs): return []` —— `flat` 标在**任意一列**即对
#: 整表生效并**丢弃全部 `group` 声明**。合并章「营业收入、营业成本按分解信息」
#: （listed 五、62 表[3] / soe 八、64 表[3]）的标签列被加了 `flat: True`，而其余 8 列
#: 带 `group` ⇒ 该表的两级表头**静默降级成单级**。
#:
#: 归属：`d4-…` / 营业收入披露侧（本 spec 范围外）。母公司侧忠实镜像。
#:
#: 键 = `_parent_tables` 的定位标识；值 = (合并章章节号, 表名, 依据)。
UPSTREAM_MERGED_COLUMN_CONFLICTS: dict[tuple[str, str], tuple[str, str, str]] = {
    ("listed/营业收入与营业成本", "营业收入、营业成本按分解信息"): (
        "五、62",
        "营业收入、营业成本按分解信息",
        "合并章该表标签列带 flat: True 而其余 8 列带 group ⇒ 两级表头被 "
        "_extract_column_groups 静默降级成单级。母公司侧按需求 4.1 忠实镜像。",
    ),
    ("soe/营业收入与营业成本", "营业收入分解信息"): (
        "八、64",
        "营业收入分解信息",
        "同 listed 侧：合并章该表标签列带 flat: True 而其余 8 列带 group。",
    ),
}


def check_columns_present(
    tables: list[tuple[str, dict]],
    *,
    upstream_exempt: dict[tuple[str, str], tuple[str, str, str]] | None = None,
) -> list[str]:
    """返回 columns 判据违规的表标识清单；空列表 = 合格。

    ``upstream_exempt`` 只豁免 **flat/group 并存**这一条，且只对登记在
    ``UPSTREAM_MERGED_COLUMN_CONFLICTS`` 里的 `(定位标识, 表名)` 生效 ——
    其余判据（columns 缺失 / 未表态 / 标签列带 group / label 空）一律不豁免。
    豁免的有效性由 ``test_upstream_conflict_registry_still_reproduces`` 与合并章
    **双向锁死**：上游修好后登记项即 stale，必须移除，否则打红。

    入参形态与 ``_parent_tables`` 输出一致：``[(定位标识, 表对象)]``。

    🔴 **表态是「表级」不是「列级」**（需求 5.1 原文「每张表 SHALL 显式表态」）。
    判据必须与后端 ``note_sub_table_projector._extract_column_groups`` 的三态同口径：

    - 任一列带 ``group`` ⇒ 显式分组（**混合分组合法**：rowspan=2 的独立列本身不带 group，
      如「账面价值」「类 别」；逐列要求 group/flat 会把这些合法列判成违规）
    - 任一列带 ``flat`` ⇒ 显式单级（kit ``flat_columns`` 只给**首列**标 flat，
      逐列要求会让 kit 产出的每张单级表都打红）
    - 两者都无 ⇒ 未声明，会退化成 ``_infer_groups_from_headers`` 前缀推断 → 违规

    该口径 2026-08-06 用合并章既有合规表反向验证过：五、4/五、5/五、8/五、62 与
    八、5/八、9/八、64 全部 0 违规（逐列口径下分别报 28/41/72/8 与 31/53/7 项假违规）。
    """
    problems: list[str] = []
    for ident, t in tables:
        cols = t.get("columns") or []
        if not cols:
            problems.append(f"{ident}: columns 缺失或为空")
            continue
        has_group = any(c.get("group") for c in cols)
        has_flat = any(c.get("flat") for c in cols)
        if not has_group and not has_flat:
            problems.append(f"{ident}: columns 未表态（既无 group 也无 flat，会触发前缀推断）")
        if has_group and has_flat:
            exempt = (upstream_exempt or {})
            if (ident, str(t.get("name") or "")) not in exempt:
                problems.append(f"{ident}: columns 表态冲突（flat 与 group 并存）")
        if has_group and cols[0].get("group"):
            problems.append(f"{ident}: 标签列不得带 group")
        for i, c in enumerate(cols):
            if not (c.get("label") or "").strip():
                problems.append(f"{ident}: 第 {i} 列 label 为空")
    return problems


class TestSoeChapterTitleTarget:
    def test_soe_chapter_title_equals_docx_heading1(
        self, templates: dict[str, list[dict[str, Any]]], docx_facts: dict[str, Any]
    ) -> None:
        json_title = _chapter(templates["soe"], "soe")["section_title"]
        docx_title = _docx_parent(docx_facts, "soe")["chapter_title"]
        assert json_title == docx_title, (
            f"soe 第 12 章 section_title 应逐字等于源 docx Heading 1「{docx_title}」，"
            f"实为「{json_title}」"
        )

    def test_soe_chapter_title_no_longer_the_known_defect(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Task 3 已修：章名不得回退成「股份支付」（防并发会话 / 重生成脚本把它写回）。"""
        json_title = _chapter(templates["soe"], "soe")["section_title"]
        assert json_title != CURRENT_SOE_CHAPTER_TITLE, (
            f"soe 章名回退成缺陷现值「{CURRENT_SOE_CHAPTER_TITLE}」—— Task 3 的修订被覆盖"
        )

    def test_soe_chapter_account_name_matches_title(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """其余 13 个 level-1 章实测 section_title == account_name，第 12 章必须同构。

        改标题不同步 account_name 会让它成为全库唯一两者不一致的章。
        """
        ch = _chapter(templates["soe"], "soe")
        assert ch.get("account_name") == ch.get("section_title"), (
            f"account_name={ch.get('account_name')!r} 与 section_title="
            f"{ch.get('section_title')!r} 不一致"
        )
        others = [
            s
            for s in templates["soe"]
            if s.get("level") == 1 and s.get("section_id") != PARENT_CHAPTER_SID["soe"]
        ]
        mismatched = [
            s.get("section_number")
            for s in others
            if s.get("account_name") != s.get("section_title")
        ]
        assert not mismatched, (
            f"其余 level-1 章出现 title != account_name：{mismatched} —— 该同构前提已变，需重新裁决"
        )


# ── Property 6 前半：section_id 反映母公司语义（需求 2.2） ────────────────────
class TestSoeSectionIdTarget:
    def test_soe_chapter_and_children_slug_not_share_payment(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        ch = _chapter(templates["soe"], "soe")
        kids = _children(templates["soe"], "soe")
        problems = check_soe_slug_free_of_share_payment(ch, kids)
        assert not problems, "soe section_id slug 判据违规:\n" + "\n".join(problems)

    def test_soe_slug_reflects_parent_company_semantics(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """需求 2.2：章 sid 反映母公司语义，6 子节 sid 落在该前缀下。"""
        ch = _chapter(templates["soe"], "soe")
        sid = ch["section_id"]
        assert sid == PARENT_CHAPTER_SID["soe"]
        assert sid.startswith("chapter-12-mu-gong-si-"), f"章 sid 未反映母公司语义: {sid}"
        for kid in _children(templates["soe"], "soe"):
            assert kid["section_id"].startswith(sid), (
                f"子节「{kid['section_title']}」sid 未落在新前缀下: {kid['section_id']}"
            )

    def test_old_slug_survives_only_as_legacy_alias(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """需求 2.3：旧 slug 必须进 ``legacy_aliases``（既有 disclosure_notes 行仍可解析），
        且**不得**再出现在任何 ``section_id`` / ``parent_section_id`` 里。"""
        sections = templates["soe"]
        ch = _chapter(sections, "soe")
        assert BAD_SOE_SLUG_FRAGMENT_FULL in (ch.get("legacy_aliases") or []), (
            f"章 legacy_aliases 缺旧 slug「{BAD_SOE_SLUG_FRAGMENT_FULL}」"
        )
        kids = _children(sections, "soe")
        assert len(kids) == EXPECTED_SUBSECTION_COUNT["soe"]
        for kid in kids:
            aliases = kid.get("legacy_aliases") or []
            assert any(
                str(a).startswith(BAD_SOE_SLUG_FRAGMENT_FULL) for a in aliases
            ), f"子节「{kid['section_title']}」legacy_aliases 缺旧 slug: {aliases}"

        # 旧 slug 只许活在 legacy_aliases 里 —— 任何定位字段残留即为改写不彻底
        live = [
            (s.get("section_number"), field, s.get(field))
            for s in sections
            for field in ("section_id", "parent_section_id")
            if BAD_SOE_SLUG_FRAGMENT_FULL in str(s.get(field) or "")
        ]
        assert not live, f"旧 slug 仍残留在定位字段中: {live}"

    def test_rewritten_section_ids_unique_and_within_length_budget(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """改写不得撞键，且母公司章 sid 不得超平台既有 slug 长度上限。

        上限 95 的依据：listed 侧最长 sid 实测恰为 95 且末尾被截断
        （`…-ying-ye-shou-ru-yu-ying-ye-cheng`，源标题「营业收入与营业成本」的 `-ben` 被切掉）。

        ⚠️ 长度断言**只作用于母公司章**（本 spec 改写范围）。全库扫描会命中 soe
        `chapter-05` 一条 **97 字符的预存在 sid**（`…-cha-cuo-de-g-kua-2`，含去重后缀），
        那是 md 重建产物、与本 spec 无关 —— 纳入即产生与 Task 3 无因果的假红。
        """
        sids = [str(s.get("section_id")) for s in templates["soe"]]
        dup = sorted({s for s in sids if sids.count(s) > 1})
        assert not dup, f"section_id 出现重复（改写撞键会让两章互相覆盖）: {dup}"

        ch = _chapter(templates["soe"], "soe")
        parent_sids = [str(ch.get("section_id"))] + [
            str(k.get("section_id")) for k in _children(templates["soe"], "soe")
        ]
        too_long = [s for s in parent_sids if len(s) > 95]
        assert not too_long, (
            f"母公司章 section_id 超 95 字符上限: {[(len(s), s) for s in too_long]}"
        )

    def test_soe_sort_index_unchanged(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Property 7：章序不变（需求 2.5）—— 这条现在就该绿。"""
        ch = _chapter(templates["soe"], "soe")
        assert ch.get("sort_index") == 12, f"soe 母公司章 sort_index 应为 12，实为 {ch.get('sort_index')}"
        assert ch.get("section_number") == "十二"

    def test_selfcheck_slug_check_not_vacuous(self) -> None:
        """反向自检：干净 slug 必绿、脏 slug 必红。"""
        good_ch = {"section_id": "chapter-12-mu-gong-si-x"}
        good_kids = [{"section_id": "chapter-12-mu-gong-si-x-a", "section_title": "a"}]
        assert check_soe_slug_free_of_share_payment(good_ch, good_kids) == []
        bad_kids = [{"section_id": "chapter-12-gu-fen-zhi-fu-a", "section_title": "a"}]
        assert check_soe_slug_free_of_share_payment(good_ch, bad_kids)


# ── Property 12 前半：columns 齐备且显式表态（需求 5.1） ─────────────────────
class TestColumnsTarget:
    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_all_parent_tables_have_columns(
        self, templates: dict[str, list[dict[str, Any]]], variant: str
    ) -> None:
        tables = _parent_tables(templates[variant], variant)
        problems = check_columns_present(
            tables, upstream_exempt=UPSTREAM_MERGED_COLUMN_CONFLICTS
        )
        assert not problems, (
            f"{variant} 母公司章 columns 判据违规（{len(problems)} 项）:\n"
            + "\n".join(problems[:12])
        )

    def test_upstream_conflict_registry_still_reproduces(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """双向锁死上游缺陷登记：登记项必须在**合并章**里仍然复现。

        上游把 `flat` 去掉后本条打红 ⇒ 提醒把登记项移除（豁免不会变成永久盲区）。
        """
        stale: list[str] = []
        for (ident, table_name), (merged_code, merged_table, _why) in (
            UPSTREAM_MERGED_COLUMN_CONFLICTS.items()
        ):
            variant = ident.split("/", 1)[0]
            src = _merged_section(templates[variant], merged_code)
            hits = [
                t for t in (src.get("tables") or [])
                if str(t.get("name") or "") == merged_table
            ]
            if len(hits) != 1:
                stale.append(
                    f"{ident}: 合并章「{merged_code}」里表「{merged_table}」命中 "
                    f"{len(hits)} 张（应为 1）—— 登记项已失效"
                )
                continue
            cols = hits[0].get("columns") or []
            has_group = any(c.get("group") for c in cols)
            has_flat = any(c.get("flat") for c in cols)
            if not (has_group and has_flat):
                stale.append(
                    f"{ident}: 合并章「{merged_code}」表「{merged_table}」的 "
                    f"flat/group 并存已消失（has_group={has_group} has_flat={has_flat}）"
                    " ⇒ 请从 UPSTREAM_MERGED_COLUMN_CONFLICTS 移除该登记项"
                )
            assert table_name == merged_table, (
                f"{ident}: 登记的母公司侧表名 {table_name!r} 与合并章表名 "
                f"{merged_table!r} 不一致（同构替换后两者必须相同）"
            )
        assert not stale, "上游缺陷登记已 stale：\n" + "\n".join(stale)

    @pytest.mark.parametrize(
        "variant,merged_codes",
        [
            ("listed", ("五、4", "五、5", "五、8", "五、62")),
            ("soe", ("八、5", "八、9", "八、64")),
        ],
    )
    def test_apply_pipeline_leaves_merged_chapter_byte_identical(
        self, variant: str, merged_codes: tuple[str, ...]
    ) -> None:
        """Property 28：跑一遍完整 apply 管道，合并章各节序列化后**逐字节不变**。

        🔴 判据形态刻意选「apply 前后对照」而不是「冻结一份合并章快照」——
        合并章由别的 spec（营业收入披露侧）持续在改（2026-08-07 实测它给
        「按分解信息」表加了 `flat`），冻结快照会变成与本 spec 无因果的假红发生器。
        「本 spec 的管道不碰合并章」才是 Property 28 真正要钉的不变量，且它在
        上游任意改动下都稳定。

        用 `--apply` 关闭（`dry_run=True`）的方式跑管道 ⇒ 不写盘、纯内存。
        """
        doc = json.loads(TEMPLATE_JSON[variant].read_text(encoding="utf-8"))
        before = {
            code: json.dumps(
                _merged_section(doc["sections"], code), ensure_ascii=False, sort_keys=True
            )
            for code in merged_codes
        }

        # 只跑 apply_* 系列（`run_variant` 会写盘，故直接调各步；顺序与生产一致）
        for fn_name in (
            "apply_chapter_identity",
            "apply_table_renames",
            "apply_lte_tables",
            "apply_isomorphic",
            "apply_columns",
            "apply_chapter_intro",
            "apply_report_row_codes",
        ):
            getattr(FIX, fn_name)(doc, variant)

        after = {
            code: json.dumps(
                _merged_section(doc["sections"], code), ensure_ascii=False, sort_keys=True
            )
            for code in merged_codes
        }
        drifted = [c for c in merged_codes if before[c] != after[c]]
        assert not drifted, (
            f"{variant} apply 管道改动了合并章 {drifted}（Property 28 合并章零回归）"
        )

    def test_apply_pipeline_characterization_is_not_vacuous(self) -> None:
        """反向自检：同一管道确实**改动了母公司章**（否则上一条是空转）。

        若管道对母公司章也是空操作（例如全部 apply_* 被摘掉），上一条会恒绿而
        毫无信号 —— 本条要求母公司章在「先破坏再跑管道」后被修回来。
        """
        doc = json.loads(TEMPLATE_JSON["soe"].read_text(encoding="utf-8"))
        ch = _chapter(doc["sections"], "soe")
        assert ch is not None
        ch["section_title"] = "股份支付"  # 人为破坏 Task 3 的成果
        for fn_name in (
            "apply_chapter_identity",
            "apply_table_renames",
            "apply_lte_tables",
            "apply_isomorphic",
            "apply_columns",
            "apply_chapter_intro",
            "apply_report_row_codes",
        ):
            getattr(FIX, fn_name)(doc, "soe")
        fixed = _chapter(doc["sections"], "soe")
        assert fixed is not None
        assert fixed.get("section_title") != "股份支付", (
            "apply 管道对母公司章是空操作 ⇒ 上一条 Property 28 断言无信号"
        )

    def test_upstream_exemption_only_covers_flat_group_conflict(self) -> None:
        """反向自检：豁免只放行 flat/group 并存，不得放行其他任何违规。"""
        ident = "listed/营业收入与营业成本"
        name = "营业收入、营业成本按分解信息"
        exempt = UPSTREAM_MERGED_COLUMN_CONFLICTS

        # 1. 登记项 + 仅 flat/group 并存 → 放行
        ok = [(ident, {
            "name": name,
            "columns": [
                {"label": "项目", "is_label": True, "flat": True},
                {"label": "收入", "group": "本期"},
            ],
        })]
        assert check_columns_present(ok, upstream_exempt=exempt) == []

        # 2. 同一张登记表若另有违规（标签列带 group / label 空）仍须打红
        bad = [(ident, {
            "name": name,
            "columns": [
                {"label": "项目", "is_label": True, "flat": True, "group": "X"},
                {"label": "", "group": "本期"},
            ],
        })]
        problems = check_columns_present(bad, upstream_exempt=exempt)
        assert any("标签列不得带 group" in p for p in problems)
        assert any("label 为空" in p for p in problems)
        assert not any("表态冲突" in p for p in problems)

        # 3. 未登记的表出现 flat/group 并存必须打红（豁免不外溢）
        other = [("listed/长期股权投资", {
            "name": "长期股权投资",
            "columns": [
                {"label": "项目", "is_label": True, "flat": True},
                {"label": "收入", "group": "本期"},
            ],
        })]
        assert any(
            "表态冲突" in p
            for p in check_columns_present(other, upstream_exempt=exempt)
        )

        # 4. 不传豁免时登记表也必须打红（证明豁免确实是它在起作用）
        assert any("表态冲突" in p for p in check_columns_present(ok))

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_every_parent_table_has_columns_and_guidance(
        self, templates: dict[str, list[dict[str, Any]]], variant: str
    ) -> None:
        """Task 7 交付判据（需求 5.1 / 5.2 / 5.3）：**全部** 62/42 张表齐备，一张不缺。

        🔴 取代原 ``test_current_missing_columns_scale_is_the_registered_anchor``
        —— 那条锚定的是「还缺几张」这个进度数字，Task 7 把它降到 0 后它就成了恒 0 的
        死锚点。这里改为正向全覆盖断言，**规模锚点仍由 ``JSON_PARENT_TABLE_COUNT``
        承担**（表数一变即打红，防「删掉几张表让缺列数归零」这种伪达成）。
        """
        tables = _parent_tables(templates[variant], variant)
        total = JSON_PARENT_TABLE_COUNT[variant]
        assert len(tables) == total, (
            f"{variant} 母公司章表数应为 {total}，实为 {len(tables)}"
            "（结构确有改动请同步 JSON_PARENT_TABLE_COUNT 与 PARENT_TABLE_CENSUS）"
        )
        no_columns = [n for n, t in tables if not t.get("columns")]
        assert not no_columns, (
            f"{variant} 仍有 {len(no_columns)} 张表缺 columns（需求 5.1 要求全部齐备）："
            f"{no_columns[:12]}"
        )
        no_guidance = [n for n, t in tables if not str(t.get("guidance") or "").strip()]
        assert not no_guidance, (
            f"{variant} 仍有 {len(no_guidance)} 张表缺 guidance（需求 5.2）：{no_guidance[:12]}"
        )
        bold = [n for n, t in tables if "**" in str(t.get("guidance") or "")]
        assert not bold, (
            f"{variant} 有 {len(bold)} 张表 guidance 含 markdown 粗体（需求 5.3 要求纯文本，"
            f"与平台级 fix_note_bold_markers.py 不打架）：{bold[:12]}"
        )

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_lte_tables_already_have_columns(
        self, templates: dict[str, list[dict[str, Any]]], variant: str
    ) -> None:
        """Task 5 交付物正向断言：长期股权投资 3 表 columns 齐备且显式表态。

        本条与上条的差值（total − missing = 3）互为印证，防「补齐规模」被笼统数字掩盖。
        """
        kid = _lte_child(templates[variant], variant)
        tables = kid.get("tables") or []
        assert len(tables) == 3
        problems = check_columns_present(
            [(f"{variant}/长期股权投资[{i}]", t) for i, t in enumerate(tables)]
        )
        assert not problems, "长期股权投资 columns 判据违规:\n" + "\n".join(problems)

    def test_selfcheck_columns_check_not_vacuous(self) -> None:
        """反向自检：齐备且表态的表必绿；缺 columns / 未表态 / 空 label 各必红。"""
        ok = [("t", {"columns": [{"label": "项目", "flat": True}]})]
        assert check_columns_present(ok) == []
        assert check_columns_present([("t", {"columns": []})])
        assert check_columns_present([("t", {"columns": [{"label": "项目"}]})])
        assert check_columns_present([("t", {"columns": [{"label": "", "flat": True}]})])
        # 🔴 两级表真实形态 = **首列是不带 group 的标签列** + 其后列带 group。
        # 替身若只给一列且该列带 group，会撞上本函数「标签列不得带 group」那条规则
        # ⇒ 期望绿实得红（2026-08-06 实测）。
        grouped = [
            (
                "t",
                {
                    "columns": [
                        {"label": "项目"},
                        {"label": "账面余额", "group": "期末余额"},
                    ]
                },
            )
        ]
        assert check_columns_present(grouped) == []
        # 正向钉死「首列带 group 必红」这条规则本身仍有效（否则上面改替身
        # 等于把该规则的自检删掉）。
        assert check_columns_present(
            [("t", {"columns": [{"label": "账面余额", "group": "期末余额"}]})]
        )


# ── Property 9：长期股权投资列数与两级表头匹配源 docx（需求 4.3、4.4、4.5） ───
def _lte_child(sections: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    """定位长期股权投资子节（Task 5 的作用域）。"""
    return next(
        k for k in _children(sections, variant) if k["section_title"] == "长期股权投资"
    )


class TestLongTermEquityTarget:
    """Task 5 已完成（2026-08-06）⇒ 原 ``_XFAIL_LTE`` 按其存在的唯一目的**已移除**，
    全部断言转为正向。判定逻辑一律 import 幂等脚本的 ``check_lte_tables``（单一判据，
    避免守卫与脚本两侧漂移）。"""

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_json_lte_col_counts_match_docx(
        self, templates: dict[str, list[dict[str, Any]]], docx_facts: dict[str, Any], variant: str
    ) -> None:
        kid = _lte_child(templates[variant], variant)
        json_cols = [len(t.get("headers") or []) for t in kid.get("tables") or []]
        docx_secs = {
            s["normalized_title"]: s for s in _docx_parent(docx_facts, variant)["sections"]
        }
        docx_cols = [t["cols"] for t in docx_secs["长期股权投资"]["tables"]]
        assert docx_cols == LTE_COLS_DOCX[variant], "源 docx 列数与登记不符，需重新裁决"
        assert json_cols == docx_cols, (
            f"{variant} 长期股权投资列数应为 {docx_cols}，JSON 实为 {json_cols}"
        )

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_lte_col_counts_no_longer_flattened(
        self, templates: dict[str, list[dict[str, Any]]], variant: str
    ) -> None:
        """回退检测：列数不得回到 Task 5 前的压扁现值（防并发会话 / 重生成脚本压回）。"""
        kid = _lte_child(templates[variant], variant)
        json_cols = [len(t.get("headers") or []) for t in kid.get("tables") or []]
        assert json_cols != LTE_COLS_JSON_BEFORE_TASK5[variant], (
            f"{variant} 长期股权投资列数回退成 Task 5 前的压扁现值 "
            f"{LTE_COLS_JSON_BEFORE_TASK5[variant]} —— Task 5 的修订被覆盖"
        )

    def test_soe_table1_and_table2_already_correct(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """🔴 反向断言（需求 4.4 / 已裁决事项 6）：soe 表 1(5 列)/表 2(7 列) 与源一致，
        **不得**按「两版三张表全压扁」的错误前提去改。"""
        kid = _lte_child(templates["soe"], "soe")
        cols = [len(t.get("headers") or []) for t in kid.get("tables") or []]
        assert (cols[0], cols[1]) == SOE_LTE_ALREADY_CORRECT_COLS, (
            f"soe 长期股权投资表 1/表 2 应保持 {SOE_LTE_ALREADY_CORRECT_COLS} 列"
            f"（与源一致），实为 {(cols[0], cols[1])}"
        )
        assert (cols[0], cols[1]) == tuple(LTE_COLS_DOCX["soe"][:2])

    def test_soe_table1_and_table2_rows_untouched_by_task5(
        self, templates: dict[str, list[dict[str, Any]]], docx_facts: dict[str, Any]
    ) -> None:
        """需求 4.4 的另一半：soe 表 1/表 2 的 ``headers`` 与 ``rows`` 未被 Task 5 改动。

        判据 = headers 逐字等于源 docx 首行表头（去空白）+ 行 label 序列仍是源 docx 首列样本。
        Task 5 对这两张表只补 ``columns``/``guidance``，任何 headers/rows 变化即越界。
        """
        kid = _lte_child(templates["soe"], "soe")
        tables = kid.get("tables") or []
        docx_tables = {
            s["normalized_title"]: s for s in _docx_parent(docx_facts, "soe")["sections"]
        }["长期股权投资"]["tables"]

        def _norm(items: list[Any]) -> list[str]:
            return ["".join(str(x).split()) for x in items]

        for idx in (0, 1):
            assert _norm(tables[idx].get("headers") or []) == _norm(
                docx_tables[idx]["header_row1"]
            ), f"soe 长期股权投资表 {idx + 1} headers 被改动（Task 5 只应补 columns）"
            # 单级表不得被塞两级分组
            assert tables[idx].get("_column_groups") is None, (
                f"soe 长期股权投资表 {idx + 1} 是单级表头，不得有 _column_groups"
            )
            assert any(c.get("flat") for c in tables[idx].get("columns") or []), (
                f"soe 长期股权投资表 {idx + 1} 单级表头须显式标 flat"
            )

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_lte_two_level_header_and_columns_via_script_judge(
        self, templates: dict[str, list[dict[str, Any]]], variant: str
    ) -> None:
        """交叉锁死：直接跑幂等脚本的 ``check_lte_tables``（Property 9/10/12 在本子节的部分）。"""
        errs = FIX.check_lte_tables({"sections": templates[variant]}, variant)
        assert not errs, f"{variant} 长期股权投资欠账（{len(errs)} 项）:\n" + "\n".join(errs)

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_lte_two_level_tables_declare_group(
        self, templates: dict[str, list[dict[str, Any]]], docx_facts: dict[str, Any], variant: str
    ) -> None:
        """需求 4.5：两级表头走 ``ColumnDef.group``；源 docx 判定为单级的表不得有 group。"""
        kid = _lte_child(templates[variant], variant)
        docx_tables = {
            s["normalized_title"]: s for s in _docx_parent(docx_facts, variant)["sections"]
        }["长期股权投资"]["tables"]
        for i, (tbl, dt) in enumerate(zip(kid.get("tables") or [], docx_tables)):
            cols = tbl.get("columns") or []
            has_group = any(c.get("group") for c in cols)
            assert has_group == bool(dt["two_level_header"]), (
                f"{variant} 表[{i}] 两级表头判定不符：源 docx two_level="
                f"{dt['two_level_header']}，columns has_group={has_group}"
            )
            if has_group:
                assert tbl.get("_column_groups"), f"{variant} 表[{i}] 缺 _column_groups"
                assert not cols[0].get("group"), f"{variant} 表[{i}] 标签列不得带 group"

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_lte_expandable_and_group_rows_preserved(
        self, templates: dict[str, list[dict[str, Any]]], variant: str
    ) -> None:
        """Property 10 / 需求 4.6：``…`` 可扩行与 ``一、合营企业``/``①联营企业`` 分组行保留。"""
        kid = _lte_child(templates[variant], variant)
        tables = kid.get("tables") or []
        for idx, keeps in FIX.LTE_PRESERVED_ROW_LABELS[variant].items():
            labels = [str((r or {}).get("label") or "") for r in tables[idx].get("rows") or []]
            missing = [k for k in keeps if k not in labels]
            assert not missing, (
                f"{variant} 表[{idx}] 丢失源 docx 结构行/可扩行 {missing}"
                f"（需求 4.6 禁当占位删除）；现有 labels={labels}"
            )

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_lte_no_header_label_rows_left(
        self, templates: dict[str, list[dict[str, Any]]], variant: str
    ) -> None:
        """两级表头由 group 承载后，压扁残留的 ``header_label`` 行必须已删。"""
        kid = _lte_child(templates[variant], variant)
        left = [
            (i, r.get("label"))
            for i, t in enumerate(kid.get("tables") or [])
            for r in t.get("rows") or []
            if str((r or {}).get("row_type") or "") == "header_label"
        ]
        assert not left, f"{variant} 长期股权投资仍残留 header_label 行: {left}"

    def test_selfcheck_column_count_check_not_vacuous(self) -> None:
        """反向自检：``check_column_counts`` 对压扁现值必红、对目标态必绿。"""
        assert check_column_counts(LTE_COLS_DOCX["listed"], LTE_COLS_DOCX["listed"], "x") == []
        assert check_column_counts(
            LTE_COLS_JSON_BEFORE_TASK5["listed"], LTE_COLS_DOCX["listed"], "x"
        ), "压扁现值未被判红 —— 判据空转"
        # soe 仅表 3 压扁这种「局部压扁」同样要红（最易漏的一档）
        assert check_column_counts(
            LTE_COLS_JSON_BEFORE_TASK5["soe"], LTE_COLS_DOCX["soe"], "x"
        )

    def test_selfcheck_script_lte_judge_not_vacuous(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """反向自检：把结构改坏（删 columns / 删可扩行 / 塞 flat+group）必被脚本判据抓到。"""
        import copy

        base = copy.deepcopy(templates["soe"])
        assert FIX.check_lte_tables({"sections": base}, "soe") == []

        d1 = copy.deepcopy(base)
        _lte_child(d1, "soe")["tables"][2].pop("columns", None)
        assert FIX.check_lte_tables({"sections": d1}, "soe"), "删 columns 未被抓到"

        d2 = copy.deepcopy(base)
        t3 = _lte_child(d2, "soe")["tables"][2]
        t3["rows"] = [r for r in t3["rows"] if str(r.get("label")) != "…"]
        assert FIX.check_lte_tables({"sections": d2}, "soe"), "删「…」可扩行未被抓到"

        d3 = copy.deepcopy(base)
        _lte_child(d3, "soe")["tables"][2]["columns"][1]["flat"] = True
        assert FIX.check_lte_tables({"sections": d3}, "soe"), "flat 与 group 并存未被抓到"

        d4 = copy.deepcopy(base)
        _lte_child(d4, "soe")["tables"][2].pop("_column_groups", None)
        assert FIX.check_lte_tables({"sections": d4}, "soe"), "缺 _column_groups 未被抓到"


# ══════════════════════════════════════════════════════════════════════════════
# Task 4: 表名唯一化守卫（需求 6.3 / 6.4 / 6.6）
#
# 判据分档（**下个会话先读这段再改**）:
#
# - **已 apply 的正名范围**只含两个「自有表子节」`listed/长期股权投资` 与
#   `soe/其他应收款`（脚本 `RENAME_SECTIONS`，用户 2026-08-06 裁决 = 方案 A）。
#   这两个子节的唯一性 / 无空名 / 无泄漏 / legacy_aliases 四条**现在就该全绿**。
# - **listed 侧 4 个同构子节**（应收票据 / 应收账款 / 其他应收款 / 营业收入与营业成本，
#   共 53 张表）仍存在重名与空名，这是**预期状态** —— 它们归 Task 6 按合并章
#   **整体替换** `tables`，在此正名会被那次替换整表覆盖。故按子节挂
#   `xfail(strict=True)`，Task 6 完成时 XPASS 会让整套打红，届时**必须移除该 xfail**。
# - **listed/投资收益**（1 张表，名为 `项  目`）是**第三档**：它是自有表子节（Task 6
#   明令不参与对齐），表名却是表头首格泄漏 ⇒ 既不在已 apply 范围、也不会被 Task 6
#   覆盖 = Task 4 的**残留缺口**。单独挂 xfail 并在此登记，不得混进 Task 6 档掩盖。
#
# 交叉锁死：唯一性 / 泄漏判定一律 import 幂等脚本里的纯函数，**不在本文件重抄**
# （重抄会让 apply 侧与 check 侧漂移 —— 改一侧另一侧不红）。
# ══════════════════════════════════════════════════════════════════════════════

FIX_SCRIPT_PATH = (
    REPO_ROOT / "backend" / "scripts" / "fix" / "fix_note_parent_company_chapter.py"
)


def _load_fix_script() -> Any:
    """import Task 3~7 的幂等脚本（``scripts/fix`` 不是包，只能按路径加载）。

    脚本模块级会 ``sys.path.insert`` 自己所在目录以取 ``_note_structure_kit``，
    故按路径加载即可，无需额外 path 处理。
    """
    spec = importlib.util.spec_from_file_location(
        "_fix_note_parent_company_chapter", FIX_SCRIPT_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"无法加载幂等脚本: {FIX_SCRIPT_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix_script()

# 已 apply 的正名范围（必须与脚本 RENAME_SECTIONS 逐字相等，见交叉锁死用例）
#
# 🔴🔴 **范围修正（2026-08-06）：``soe/其他应收款`` 已移出 Task 4，归 Task 6。**
# 源 docx 实测 ``own_table_count == 0`` ⇒ 按需求 1.4 / 4.1 的定义它是**同构子节**，
# 结构由 Task 6 按合并章整体替换 ⇒ Task 4 在此正名会被那次替换整表覆盖。
# 其旧名（含 Task 4 曾产生的中间名 ``其他应收款（表8..11）`` 与更早的原始名
# ``其他应收款（续）债务人名称``）的迁移记录改由子节级 ``_removed_table_keys`` 承载，
# 见 ``TestIsomorphicScopeCorrection``。
# ``soe`` 键保留为空 dict 与脚本侧对称（两变体都被显式表态过）。
#
# 🔴 **Task 7 追加 ``listed/投资收益``（2026-08-06）**：它是自有表子节，表名是表头首格
# 泄漏「项  目」，不参与 Task 6 对齐 ⇒ 正名按原 ``_XFAIL_LISTED_INV_INCOME_LEAK`` 的
# reason 归 Task 7。正名与 Task 4 共用同一机制（``RENAME_SECTIONS`` + ``_plan_renames``），
# 故登记在同一常量里；**常量名已由 ``TASK4_*`` 改为 ``RENAME_*``** —— 它现在同时承载
# Task 4 与 Task 7 两轮的正名范围，挂 Task 4 的名字会误导下个会话。
RENAME_APPLIED_SCOPE: dict[str, dict[str, str]] = {
    "listed": {"长期股权投资": "长期股权投资", "投资收益": "投资收益"},
    "soe": {},
}

# ``soe/其他应收款`` 在**任何改动之前**（`git show HEAD:` 复算）的原始表名。
#
# 它是表头首格泄漏名（md 重建把 ``headers[0]`` 当表名）。演进链条三段：
#   原始名「其他应收款（续）债务人名称」
#     → Task 4 中间名「其他应收款（表8..11）」（该轮把它误当自有表子节正名）
#     → Task 6 按合并章整体替换 ⇒ 三段旧名全部进子节级 ``_removed_table_keys``
#
# 🔴 它**不是**脚本常量：脚本侧不硬编码任何原始名，迁移记录由
# ``collect_replaced_table_names``（并 ``name`` 与表级 ``legacy_aliases``）在 apply
# 时现算。本常量只作守卫锚点，钉住 2026-08-06 的历史补录事实（14 → 15 个键）。
_ORIGINAL_LEAKED_NAME_SOE_OTHER_RECV = "其他应收款（续）债务人名称"

# 4 处已落盘正名（Task 4 三处 + Task 7 一处）：(表索引, 旧名, 新名)
#
# 🔴 ``listed/投资收益`` 由 **Task 7** 正名（主表 N==1 ⇒ 新名 = 基名本身）。
# 它与 ``listed/长期股权投资`` 表[0] 的旧名相同（都是「项  目」）—— 两者在**不同子节**
# 故不冲突；这也再次说明表级 ``legacy_aliases`` 不可用于全库反向唯一解析。
RENAME_EXPECTED: dict[str, dict[str, list[tuple[int, str, str]]]] = {
    "listed": {
        "长期股权投资": [
            (0, "项  目", "长期股权投资"),
            (1, "被投资单位", "长期股权投资（表2）"),
            (2, "被投资单位", "长期股权投资（表3）"),
        ],
        "投资收益": [
            (0, "项  目", "投资收益"),
        ],
    },
    "soe": {},
}

# 需求 6.6 要求「逐子节输出实际表数与去重后键数」。此处把普查结果**登记成常量**
# 而不是只 print —— 既是输出也是机器可校验的锚点（塌键规模一变即打红）。
# 值 = (表数, 去重后键数)。2026-08-06 **Task 6 apply 后**实测。
#
# 🔴 Task 6 让 7 个同构子节的表集合整体换成合并章成品 ⇒ 表数变化
# （listed 应收账款 15→17 / 其他应收款 18→21；soe 应收账款 11→13 / 其他应收款 15→19）
# 且 **12/12 子节两数相等** —— 合并章表名 100% 唯一，塌键归零。
PARENT_TABLE_CENSUS: dict[str, dict[str, tuple[int, int]]] = {
    "listed": {
        "应收票据": (14, 14),
        "应收账款": (17, 17),
        "其他应收款": (21, 21),
        "长期股权投资": (3, 3),
        "营业收入与营业成本": (6, 6),
        "投资收益": (1, 1),
    },
    "soe": {
        "应收账款": (13, 13),
        "其他应收款": (19, 19),
        "长期股权投资": (3, 3),
        "营业收入与营业成本": (5, 5),
        "投资收益": (1, 1),
        "现金流量表补充资料": (1, 1),
    },
}

# 子节清单 + ASCII 用例 id（pytest 会把中文 id 转义成 \uXXXX，可读性差）
_SUBSECTION_IDS: list[tuple[str, str, str]] = [
    ("listed", "应收票据", "listed-notes-recv"),
    ("listed", "应收账款", "listed-ar"),
    ("listed", "其他应收款", "listed-other-recv"),
    ("listed", "长期股权投资", "listed-lte"),
    ("listed", "营业收入与营业成本", "listed-revenue"),
    ("listed", "投资收益", "listed-inv-income"),
    ("soe", "应收账款", "soe-ar"),
    ("soe", "其他应收款", "soe-other-recv"),
    ("soe", "长期股权投资", "soe-lte"),
    ("soe", "营业收入与营业成本", "soe-revenue"),
    ("soe", "投资收益", "soe-inv-income"),
    ("soe", "现金流量表补充资料", "soe-cashflow"),
]

# ── Task 6 已完成（2026-08-06）⇒ 两个 xfail 已移除，全部转正向断言 ────────────
#
# listed 侧 4 个同构子节的重名（`_XFAIL_TASK6`，4 param）与空名
# （`_XFAIL_TASK6_EMPTY_NAME`，2 param）在 Task 6 按合并章整体替换 `tables` 后
# **双双归零** —— 合并章表名 100% 唯一非空（见 `PARENT_TABLE_CENSUS` 12/12 两数相等）。
# 故这 6 个 param 现在必须绿；`xfail(strict)` 留着会 XPASS 打红。
#
# 🔴 **`_XFAIL_LISTED_INV_INCOME_LEAK` 已随 Task 7 完成而移除（2026-08-06）**。
#
# `listed/投资收益` 是**自有表子节**（Task 6 明令不参与对齐，需求 4.2 / 4.7）⇒ 它的
# 表头首格泄漏名「项  目」不会被合并章替换掉，其正名按该 xfail 原 reason 的指定
# 归入 **Task 7**（补列元数据那一轮）。Task 7 已把 `投资收益` 加进脚本的
# `RENAME_SECTIONS["listed"]`，正名为「投资收益」且旧名进表级 `legacy_aliases`
# ⇒ 12/12 子节的泄漏档现在全部正向绿。
#
# 因此下面的泄漏档参数化**不再需要按子节分档**，直接用 `_SUBSECTION_IDS` 全量。


def _py_code_only(src: str) -> str:
    """剥掉 ``#`` 注释与 docstring 后的代码文本（行列位置保持不变）。

    🔴 **只剥注释与 docstring，不剥普通字符串字面量** —— 这条边界是本 helper 的全部
    要点：真正的消费方往往是 ``entry.get("legacy_aliases")`` 这种**用字符串当字典键**
    的形态（``note_word_exporter`` 即如此），一并剥掉会把真消费方也判成 0 命中，
    判据反而失效（实测：全剥字符串字面量时 ``note_word_exporter`` code 命中由 5 → 0）。

    ``#`` 注释用 ``tokenize`` 剥（``#`` 出现在字符串里时不会误伤）；docstring 用 AST
    定位 module/class/def 的首个字符串常量语句 + 任意位置的裸字符串语句。
    解析失败时原样返回（宁可多报也不漏报）。
    """
    lines = src.splitlines()
    masked: list[list[str]] = [list(line) for line in lines]

    def _blank(lineno: int, col: int, end_lineno: int, end_col: int) -> None:
        for ln in range(lineno, end_lineno + 1):
            idx = ln - 1
            if idx < 0 or idx >= len(masked):
                continue
            start = col if ln == lineno else 0
            end = end_col if ln == end_lineno else len(masked[idx])
            for pos in range(start, min(end, len(masked[idx]))):
                masked[idx][pos] = " "

    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                _blank(tok.start[0], tok.start[1], tok.end[0], tok.end[1])
    except (tokenize.TokenError, IndentationError, SyntaxError):  # pragma: no cover
        return src

    try:
        tree = ast.parse(src)
    except SyntaxError:  # pragma: no cover
        return src
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list):
            for stmt in body:
                if (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                    and stmt.value.end_lineno is not None
                    and stmt.value.end_col_offset is not None
                ):
                    _blank(
                        stmt.value.lineno,
                        stmt.value.col_offset,
                        stmt.value.end_lineno,
                        stmt.value.end_col_offset,
                    )

    return "\n".join("".join(row) for row in masked)


def _parent_subsection(
    sections: list[dict[str, Any]], variant: str, title: str
) -> dict[str, Any]:
    """按标题定位母公司章子节，返回 **section 对象本身**。

    与 ``_subsection_tables`` 的区别：后者只返回 ``tables`` 列表，读不到子节级字段
    （``_removed_table_keys`` / ``section_id`` / ``guidance`` 等）⇒ 需要断言子节级
    迁移记录时必须用本函数，不能复用那个。定位口径与 ``_subsection_tables`` 同源
    （走 ``_children`` 按 ``section_title`` 匹配 + 缺失即断言失败）。
    """
    kid = next(
        (k for k in _children(sections, variant) if k.get("section_title") == title), None
    )
    assert kid is not None, f"{variant} 母公司章缺子节「{title}」"
    return kid


def _subsection_tables(
    sections: list[dict[str, Any]], variant: str, title: str
) -> list[dict[str, Any]]:
    return list(_parent_subsection(sections, variant, title).get("tables") or [])


# ── 判定纯函数（真实数据与替身共用；泄漏判定委托幂等脚本，避免两侧漂移） ──────
def check_names_unique(names: list[str], ident: str) -> list[str]:
    """需求 6.6 判据：同子节内**表名集合大小 == 表数量**（不是只查空串）。

    消息体逐子节输出实际表数与去重后键数，便于定位塌键规模。
    """
    uniq = len(set(names))
    if uniq == len(names):
        return []
    dups = sorted({n for n in names if names.count(n) > 1})
    detail = "; ".join(
        f"「{n if n else '<空名>'}」出现在索引 {[i for i, x in enumerate(names) if x == n]}"
        for n in dups
    )
    return [
        f"{ident} 表名不唯一：表数={len(names)} 去重后键数={uniq} "
        f"塌键={len(names) - uniq} 张；重名 {detail}"
    ]


def check_names_non_empty(names: list[str], ident: str) -> list[str]:
    """需求 6.1：表名非空。表名是 ``sub_table_data`` 的键，空名互相覆盖丢整表。"""
    empties = [i for i, n in enumerate(names) if not n.strip()]
    if empties:
        return [f"{ident} 存在空表名，索引={empties}（共 {len(empties)} 张会塌成 1 键）"]
    return []


def check_no_header_leak(tables: list[dict[str, Any]], ident: str) -> list[str]:
    """需求 6.2：表名不得是表头首格泄漏（md 重建把 ``headers[0]`` 当表名）。

    判定**委托幂等脚本的 ``_is_header_leak``**（单一判据；脚本 apply 与 check
    两侧也用它）。本文件不重抄「去空白后相等」逻辑。
    """
    problems: list[str] = []
    for i, tbl in enumerate(tables):
        name = str(tbl.get("name") or "")
        if FIX._is_header_leak(name, tbl):
            h0 = str((tbl.get("headers") or [""])[0] or "")
            problems.append(
                f"{ident} 表[{i}] 名「{name}」去空白后等于表头首格「{h0}」= 表头首格泄漏"
            )
    return problems


def check_renamed_old_names_in_aliases(
    tables: list[dict[str, Any]], expected: list[tuple[int, str, str]], ident: str
) -> list[str]:
    """需求 6.3：正名后的旧名必须能在**表级** ``legacy_aliases`` 找到。

    ⚠️ 该字段当前**零消费方**（见 ``TestTableLevelAliasHasNoConsumerYet``），
    此处只断言迁移映射已登记，**不代表数据失联已解决**。
    """
    problems: list[str] = []
    for idx, old_name, new_name in expected:
        if idx >= len(tables):
            problems.append(f"{ident} 表[{idx}] 不存在（表数={len(tables)}）")
            continue
        tbl = tables[idx]
        actual = str(tbl.get("name") or "")
        if actual != new_name:
            problems.append(f"{ident} 表[{idx}] 名应为「{new_name}」，实为「{actual}」")
        aliases = tbl.get("legacy_aliases")
        if not isinstance(aliases, list):
            problems.append(f"{ident} 表[{idx}] legacy_aliases 非列表：{aliases!r}")
            continue
        if old_name not in aliases:
            problems.append(
                f"{ident} 表[{idx}]（{new_name}）legacy_aliases 缺旧名「{old_name}」，实为 {aliases}"
            )
    return problems



# ── Property 14：表名唯一非空、无表头首格泄漏（需求 6.1、6.2、6.4、6.6） ──────
class TestTableNameUniqueness:
    """需求 6.4 / 6.6 的唯一性守卫。

    **Task 6 完成后 12/12 子节全部正向断言** —— 4 个 listed 同构子节的重名与
    2 个子节的空名随「按合并章整体替换 tables」一并归零（合并章表名 100% 唯一非空）。
    """

    @pytest.mark.parametrize(
        "variant,title", [(v, t) for v, t, _ in _SUBSECTION_IDS]
    )
    def test_names_unique_within_subsection(
        self, templates: dict[str, list[dict[str, Any]]], variant: str, title: str
    ) -> None:
        tables = _subsection_tables(templates[variant], variant, title)
        names = [str(t.get("name") or "") for t in tables]
        problems = check_names_unique(names, f"{variant}/{title}")
        assert not problems, "\n".join(problems)

    @pytest.mark.parametrize(
        "variant,title", [(v, t) for v, t, _ in _SUBSECTION_IDS]
    )
    def test_names_non_empty(
        self, templates: dict[str, list[dict[str, Any]]], variant: str, title: str
    ) -> None:
        tables = _subsection_tables(templates[variant], variant, title)
        names = [str(t.get("name") or "") for t in tables]
        problems = check_names_non_empty(names, f"{variant}/{title}")
        assert not problems, "\n".join(problems)

    @pytest.mark.parametrize(
        "variant,title", [(v, t) for v, t, _ in _SUBSECTION_IDS]
    )
    def test_no_header_first_cell_leak(
        self, templates: dict[str, list[dict[str, Any]]], variant: str, title: str
    ) -> None:
        tables = _subsection_tables(templates[variant], variant, title)
        problems = check_no_header_leak(tables, f"{variant}/{title}")
        assert not problems, "\n".join(problems)

    @pytest.mark.parametrize("variant,title", [(v, t) for v, t, _ in _SUBSECTION_IDS])
    def test_census_matches_registered_baseline(
        self, templates: dict[str, list[dict[str, Any]]], variant: str, title: str
    ) -> None:
        """需求 6.6 后半：逐子节输出实际表数与去重后键数（登记成锚点，塌键规模一变即红）。

        本条**不挂 xfail** —— 它锚定的是「现状规模」而非「目标态」，Task 6 完成后
        只需更新常量。它是唯一性断言的规模参照：告诉下个会话「还有多少张表塌在一起」。
        """
        tables = _subsection_tables(templates[variant], variant, title)
        names = [str(t.get("name") or "") for t in tables]
        actual = (len(names), len(set(names)))
        expected = PARENT_TABLE_CENSUS[variant][title]
        assert actual == expected, (
            f"{variant}/{title} 普查锚点漂移：实测（表数={actual[0]}, 去重后键数={actual[1]}）"
            f"，登记值（表数={expected[0]}, 去重后键数={expected[1]}）—— "
            "结构确有改动请同步更新 PARENT_TABLE_CENSUS"
        )

    def test_selfcheck_uniqueness_checks_not_vacuous(self) -> None:
        """反向自检：唯一非空必绿；重名 / 空名 / 泄漏各必红（且消息含定位信息）。"""
        assert check_names_unique(["a", "b", "c"], "x") == []
        dup = check_names_unique(["a", "a", "b"], "x")
        assert dup and "表数=3" in dup[0] and "去重后键数=2" in dup[0]
        # 空名同时触发两条判据 —— 唯一性也必须抓到（多张空名会塌成 1 键）
        assert check_names_unique(["", "", "b"], "x")
        assert check_names_non_empty(["a", "b"], "x") == []
        empty = check_names_non_empty(["a", "", " "], "x")
        assert empty and "[1, 2]" in empty[0]

    def test_selfcheck_leak_check_delegates_to_fix_script(self) -> None:
        """反向自检：泄漏判定必须与幂等脚本同口径（含全角空格归一）。"""
        leak = [{"name": "项  目", "headers": ["项目", "期末余额"]}]
        assert check_no_header_leak(leak, "x"), "去空白后相等的泄漏名未被抓到"
        ok = [{"name": "长期股权投资", "headers": ["项目", "期末余额"]}]
        assert check_no_header_leak(ok, "x") == []
        # 无 headers / 空首格一律不判泄漏（避免把「无从判定」当违规）
        assert check_no_header_leak([{"name": "x", "headers": []}], "x") == []
        assert check_no_header_leak([{"name": "x", "headers": [""]}], "x") == []


# ── Property 15：表名正名保留旧映射（需求 6.3） ──────────────────────────────
class TestRenameLegacyAliases:
    """需求 6.3：4 处已落盘正名的旧名必须在**表级** ``legacy_aliases`` 找到。"""

    @pytest.mark.parametrize(
        "variant,title",
        [
            # soe/其他应收款 已移出 Task 4（同构子节，归 Task 6）
            # → 见 TestIsomorphicScopeCorrection
            pytest.param("listed", "长期股权投资", id="listed-lte"),
            # Task 7 追加：自有表子节，泄漏名「项  目」→「投资收益」
            pytest.param("listed", "投资收益", id="listed-inv-income"),
        ],
    )
    def test_renamed_tables_carry_old_name_alias(
        self, templates: dict[str, list[dict[str, Any]]], variant: str, title: str
    ) -> None:
        tables = _subsection_tables(templates[variant], variant, title)
        expected = RENAME_EXPECTED[variant][title]
        problems = check_renamed_old_names_in_aliases(tables, expected, f"{variant}/{title}")
        assert not problems, "\n".join(problems)

    def test_applied_scope_matches_fix_script(self) -> None:
        """交叉锁死：本文件登记的正名范围必须与幂等脚本 ``RENAME_SECTIONS`` 逐字相等。

        任一侧扩大/缩小范围而另一侧没跟上 ⇒ 打红（防守卫与脚本漂移）。
        """
        assert FIX.RENAME_SECTIONS == RENAME_APPLIED_SCOPE, (
            f"脚本 RENAME_SECTIONS={FIX.RENAME_SECTIONS} 与守卫登记范围="
            f"{RENAME_APPLIED_SCOPE} 不一致"
        )
        # 登记的正名明细必须与范围一一对应（防「加了范围忘了明细」）
        for variant, targets in RENAME_APPLIED_SCOPE.items():
            assert set(RENAME_EXPECTED[variant]) == set(targets), (
                f"{variant} RENAME_EXPECTED 子节集合 {sorted(RENAME_EXPECTED[variant])} "
                f"与 RENAME_APPLIED_SCOPE {sorted(targets)} 不一致"
            )

    def test_fix_script_check_reports_zero_debt_for_applied_scope(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """交叉锁死：幂等脚本自己的 ``check_table_renames`` 对已 apply 范围必须 0 欠账。

        这条把「守卫判据」与「脚本判据」双向绑住：脚本判据被削弱（比如去掉唯一性检查）
        时它仍绿，但上面的 ``check_names_unique`` 会红；反之守卫判据被削弱时这条会红。
        """
        for variant in ("listed", "soe"):
            doc = {"sections": templates[variant]}
            errs = FIX.check_table_renames(doc, variant)
            assert not errs, f"{variant} 幂等脚本 check_table_renames 报欠账：{errs}"

    def test_soe_other_recv_is_isomorphic_not_task4_scope(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """范围修正登记（2026-08-06）：``soe/其他应收款`` 归 Task 6，不归 Task 4。

        事实前提 = 源 docx 实测 ``own_table_count == 0``（同构子节，需求 1.4 / 4.1）。
        此前它被当「自有表子节」列入 ``RENAME_SECTIONS`` 并正名成
        ``其他应收款（表8..11）``，那批中间名现已随整体替换进 ``_removed_table_keys``。

        三条断言把范围修正钉死，防下个会话把它加回 Task 4：

        1. 不在 ``FIX.RENAME_SECTIONS["soe"]``；
        2. 在 ``FIX.ISOMORPHIC_SOURCE["soe"]``；
        3. **原始泄漏名** ``其他应收款（续）债务人名称`` 在该子节
           ``_removed_table_keys`` 里 —— 它是 Task 4 apply 时被丢弃的最早名字，
           2026-08-06 从 ``git show HEAD:`` 复算补录（不得硬编码在脚本常量里）。
        """
        assert "其他应收款" not in FIX.RENAME_SECTIONS.get("soe", {}), (
            "soe/其他应收款 是同构子节（源 docx own_table_count=0），"
            "不得列入 RENAME_SECTIONS —— 结构由 Task 6 按合并章整体替换"
        )
        assert "其他应收款" in FIX.ISOMORPHIC_SOURCE.get("soe", {}), (
            "soe/其他应收款 应登记在 ISOMORPHIC_SOURCE（需求 4.1）"
        )

        kid = _parent_subsection(templates["soe"], "soe", "其他应收款")
        removed = list(kid.get(FIX.REMOVED_TABLE_KEYS_FIELD) or [])
        assert _ORIGINAL_LEAKED_NAME_SOE_OTHER_RECV in removed, (
            f"原始泄漏名「{_ORIGINAL_LEAKED_NAME_SOE_OTHER_RECV}」应在 soe/其他应收款 的 "
            f"{FIX.REMOVED_TABLE_KEYS_FIELD} 里（共 {len(removed)} 个键）：{removed}"
        )
        # 🔴 2026-08-07 修正：Task 4 中间名 `其他应收款（表8..11）` 已不在链条里，且
        # **本就不该在**。它们只存在于一次**未提交**的 apply 中间态：那轮先把 soe/其他应收款
        # 当「自有表子节」正名成 `（表8..11）`、再由 Task 6 整体替换并记入 removed。
        # 2026-08-07 两份模板 JSON 曾被 HEAD 版覆盖并由各幂等脚本 `--apply` 完整恢复
        # （见 memory「HEAD 换文件跑同一组会破坏数据」），恢复后管道直接从 **HEAD 名集合**
        # 推导 removed ⇒ 记录的是 HEAD 期原始名本身，中间名不再产生。
        #
        # 实测三证：① 中间名在工作树与 HEAD 出现次数**均为 0**（无处留存，断言它们留痕
        # 等于凭空编造血缘）；② 当前 removed 11 项与「HEAD 名集合 − 合并章新名」推导结果
        # **逐字相等**；③ 原始泄漏名仍在 removed（上一条断言）⇒ 血缘链条完整且更准确
        # （HEAD 是唯一已提交基线）。
        for mid in ("其他应收款（表8）", "其他应收款（表9）", "其他应收款（表10）", "其他应收款（表11）"):
            assert mid not in removed, (
                f"中间名「{mid}」重新出现在 removed 里 —— 要么 soe/其他应收款 被误加回 "
                "Task 4 的 RENAME_SECTIONS（与上面第一条断言矛盾），要么有人手工补了"
                f"不存在的血缘。当前 removed（{len(removed)} 个）：{removed}"
            )

    def test_collect_replaced_table_names_reverse_selfcheck(self) -> None:
        """反向自检：只并 ``name`` 的朴素实现**必**漏掉表级 aliases 里的原始名。

        这是 ``collect_replaced_table_names`` 存在的唯一理由 —— Task 4 正名后，
        原始名只活在表级 ``legacy_aliases`` 里；整体替换丢弃整个表对象，
        若只收集 ``name`` 则原始名彻底无迹可寻。

        🔴 用**替身**构造（Task 4 后的形态：name=中间名 + aliases=原始名）。
        不能拿 ``git show HEAD:`` 的数据做这条自检 —— HEAD 是「一切改动之前」，
        那时表名**就是**原始名且还没有 ``legacy_aliases`` ⇒ 两种实现在 HEAD 上等价，
        用它证明不了差异。
        """
        tables = [
            {"name": "其他应收款（表8）", "legacy_aliases": ["其他应收款（续）债务人名称"]},
            {"name": "其他应收款（表9）", "legacy_aliases": ["其他应收款（续）债务人名称"]},
        ]
        full = FIX.collect_replaced_table_names(tables)
        naive = [str(t.get("name") or "") for t in tables]
        assert _ORIGINAL_LEAKED_NAME_SOE_OTHER_RECV in full, (
            f"collect_replaced_table_names 应收集表级 aliases，实为 {full}"
        )
        assert _ORIGINAL_LEAKED_NAME_SOE_OTHER_RECV not in naive, (
            "朴素实现不应命中原始名，否则这条自检是空转"
        )
        missed = [n for n in full if n not in naive]
        assert missed == [_ORIGINAL_LEAKED_NAME_SOE_OTHER_RECV], (
            f"朴素实现漏掉的应恰为原始名，实为 {missed}"
        )
        # 一对多去重：两张表持同一原始名，收集结果里只出现一次
        assert full.count(_ORIGINAL_LEAKED_NAME_SOE_OTHER_RECV) == 1, (
            f"原始名应去重后只出现一次，实为 {full}"
        )

    def test_selfcheck_alias_check_not_vacuous(self) -> None:
        """反向自检：旧名在 aliases 必绿；缺 alias / 名字没改 / aliases 非列表各必红。"""
        ok = [{"name": "长期股权投资", "legacy_aliases": ["项  目"]}]
        assert check_renamed_old_names_in_aliases(ok, [(0, "项  目", "长期股权投资")], "x") == []
        missing = [{"name": "长期股权投资", "legacy_aliases": []}]
        assert check_renamed_old_names_in_aliases(
            missing, [(0, "项  目", "长期股权投资")], "x"
        )
        not_renamed = [{"name": "项  目", "legacy_aliases": ["项  目"]}]
        assert check_renamed_old_names_in_aliases(
            not_renamed, [(0, "项  目", "长期股权投资")], "x"
        )
        bad_type = [{"name": "长期股权投资", "legacy_aliases": "项  目"}]
        assert check_renamed_old_names_in_aliases(
            bad_type, [(0, "项  目", "长期股权投资")], "x"
        )


# ── 显式登记：表级 legacy_aliases 当前零消费方（不得让守卫读起来像已解决） ────
class TestTableLevelAliasHasNoConsumerYet:
    """🔴 **表级** ``legacy_aliases`` 当前全仓零消费方（2026-08-06 实证）。

    实测 17 处 ``legacy_aliases`` 引用全部落在两类**与本 spec 无关**的地方：

    - ``procedure_models`` / ``procedure_definition_importer`` / ``procedure_reconcile_service``
      / ``procedure_trim_service`` / ``procedure_backfill_runner`` —— 那是
      ``procedure_row_definitions`` 表的列，与附注表名无关；
    - ``note_word_exporter`` —— 读的是 **section 级**章节码别名
      （``_load_section_code_index`` 出来的 ``sections[].legacy_aliases``），
      用于 ``section_code`` → note 的 join，**不看表名**。

    ⇒ Task 4 写入表级 ``legacy_aliases`` 是为 **Task 12 取数接线预留迁移映射**，
    **当前不构成「已解决表名漂移导致的数据失联」** —— 那要等消费方接上才成立。

    本用例把该事实钉成机器可校验的断言：一旦有人把它接进取数/迁移路径，
    这条会打红，提醒回来更新 requirements 6.3 的表述与 Task 12 的依赖说明。
    """

    #: 允许出现 `legacy_aliases` 的文件（含理由）。新增消费方必须在此登记。
    ALLOWED_CONSUMERS: dict[str, str] = {
        # procedure_row_definitions 表的列，与附注表名无关
        "app/models/procedure_models.py": "procedure_row_definitions 表列定义",
        "app/services/procedure_definition_importer.py": "程序表行定义导入",
        "app/services/procedure_reconcile_service.py": "程序表行对账",
        "app/services/procedure_trim_service.py": "程序表裁剪",
        "app/services/procedure_backfill_runner.py": "程序表回填（注释提及）",
        # 附注 section 级章节码别名（不看表名）
        "app/services/note_word_exporter.py": "section 级 section_code 别名 join",
    }

    #: 只在注释/docstring 里**提到**该字段名的文件（不是消费方，不需登记进 allowlist）。
    #:
    #: 🔴 2026-08-07 实测：并发 spec `soe-listed-note-conversion-correctness` 在
    #: `note_conversion_service.py` 的 docstring 里写下「``legacy_aliases`` 列也不存在」
    #: 作为落 `template_lineage` JSONB 的依据说明 —— 裸文本扫描把它数成「未登记消费方」
    #: 而打红（假阳性）。判据改为 **code-level**（剥注释与 docstring 后再扫），
    #: 该文件因此从 raw 2 处 → code 0 处。
    DOCSTRING_ONLY_MENTIONS: dict[str, str] = {
        "app/services/note_conversion_service.py": "docstring 说明 disclosure_notes 无该列",
    }

    def _scan(self) -> tuple[dict[str, int], dict[str, int]]:
        """返回 (raw 命中数, code-level 命中数)，键为 `backend/` 相对路径。"""
        backend_app = REPO_ROOT / "backend" / "app"
        assert backend_app.is_dir(), f"后端目录不存在: {backend_app}"
        raw: dict[str, int] = {}
        code: dict[str, int] = {}
        for py in sorted(backend_app.rglob("*.py")):
            try:
                src = py.read_text(encoding="utf-8")
            except UnicodeDecodeError:  # pragma: no cover
                continue
            if "legacy_aliases" not in src:
                continue
            rel = py.relative_to(REPO_ROOT / "backend").as_posix()
            raw[rel] = src.count("legacy_aliases")
            code[rel] = _py_code_only(src).count("legacy_aliases")
        assert raw, "扫描面为空 —— legacy_aliases 在 backend/app 下一处都没找到，判据失效"
        return raw, code

    def test_no_table_level_consumer_exists(self) -> None:
        _, code = self._scan()
        hits = [rel for rel, n in code.items() if n and rel not in self.ALLOWED_CONSUMERS]
        assert not hits, (
            "出现未登记的 legacy_aliases 引用: "
            + ", ".join(hits)
            + " —— 若这是表级消费方接线，请同步更新 requirements 6.3 的表述"
            "（表级 legacy_aliases 已有消费方 ⇒ 表名漂移的数据失联才算解决）"
            "并把该文件登记进 ALLOWED_CONSUMERS"
        )

    def test_docstring_only_mentions_are_not_counted_as_consumers(self) -> None:
        """反向自检：登记为「仅 docstring 提及」的文件必须 raw 有命中而 code 无命中。

        两条同时断言才能证明 ``_py_code_only`` 真在起作用 —— 只断言 code==0 时，
        「文件里压根没有该字段」也能让它绿（空转）。
        """
        raw, code = self._scan()
        for rel in self.DOCSTRING_ONLY_MENTIONS:
            assert raw.get(rel, 0) > 0, (
                f"{rel} 已无 legacy_aliases 提及，请从 DOCSTRING_ONLY_MENTIONS 移除"
            )
            assert code.get(rel, 0) == 0, (
                f"{rel} 出现 code-level 引用（{code.get(rel)} 处）—— "
                "它已从「docstring 提及」变成真消费方，请移入 ALLOWED_CONSUMERS"
                "并同步更新 requirements 6.3"
            )

    def test_code_level_scanner_keeps_string_key_consumers(self) -> None:
        """反向自检：``_py_code_only`` 不得剥掉普通字符串字面量。

        真消费方多是 ``entry.get("legacy_aliases")`` 形态；若连普通字符串一起剥，
        ``note_word_exporter`` 的 code 命中会由 5 → 0，整条判据静默失效。
        """
        _, code = self._scan()
        rel = "app/services/note_word_exporter.py"
        assert code.get(rel, 0) > 0, (
            f"{rel} 的 code-level 命中为 {code.get(rel)} —— "
            "剥离器把字符串键名也剥掉了，判据已失效"
        )
        # 直接对替身验证边界：docstring 剥、注释剥、字符串键名留
        sample = (
            '"""docstring 提到 legacy_aliases 不算消费。"""\n'
            "# 注释提到 legacy_aliases 也不算\n"
            'x = entry.get("legacy_aliases")\n'
        )
        stripped = _py_code_only(sample)
        assert stripped.count("legacy_aliases") == 1, (
            f"替身应恰剩 1 处（字符串键名），实为 {stripped.count('legacy_aliases')}：{stripped!r}"
        )

    def test_allowlist_entries_are_all_live(self) -> None:
        """反向自检：allowlist 里每条都必须真在引用，防它变成过期死配置。"""
        stale: list[str] = []
        for rel in self.ALLOWED_CONSUMERS:
            path = REPO_ROOT / "backend" / rel
            if not path.exists():
                stale.append(f"{rel}(文件不存在)")
                continue
            if "legacy_aliases" not in path.read_text(encoding="utf-8"):
                stale.append(f"{rel}(已无引用)")
        assert not stale, f"allowlist 出现过期条目，请清理: {stale}"

    def test_note_word_exporter_alias_read_is_section_level(self) -> None:
        """精确断言 ``note_word_exporter`` 读的是 section 级而非表级别名。

        判据 = 该处 alias 读取取自 ``_load_section_code_index`` 的条目并映射到
        ``section_code``；若哪天改成遍历 ``tables[].legacy_aliases``，本条打红。
        """
        src = (
            REPO_ROOT / "backend" / "app" / "services" / "note_word_exporter.py"
        ).read_text(encoding="utf-8")
        assert 'for alias in entry_s.get("legacy_aliases", []) or []:' in src, (
            "note_word_exporter 的 alias 读取形态已变，需重新确认它仍是 section 级"
        )
        assert "alias_to_code[a] = code" in src, "alias → section_code 映射形态已变"
        # 表级读取的特征形态一律不得出现
        for bad in (
            'tbl.get("legacy_aliases"',
            'table.get("legacy_aliases"',
            't.get("legacy_aliases"',
            'tables[].legacy_aliases',
        ):
            assert bad not in src, f"出现表级 legacy_aliases 读取形态: {bad}"


# ══════════════════════════════════════════════════════════════════════════════
# Task 6：同构子节表结构对齐合并章（需求 4.1 / 4.2 / 4.7 / 4.8）
#
# 判据一律 **import 幂等脚本的 `check_isomorphic` / `build_isomorphic_tables` /
# `merge_removed_table_keys`**，不在本文件重抄「深相等」比对 —— 重抄会让 apply 侧与
# check 侧漂移（改一侧另一侧不红），这是本 spec 反复登记的坑。
#
# 🔴 合并章是**只读源**（Property 28）：本节只断言母公司侧与合并章一致，
# 绝不断言合并章"应该长什么样"。合并章预存在的两处 markdown 粗体
# （`listed 五、8` 的「应收政府补助情况」= `**逐项**`；`soe 八、9` 的
# 「按账龄披露其他应收款项」= `**单级 3 列**`）属另一半径，本 spec 不动它们，
# 只在复制管道里剥掉 —— 故「母公司侧无粗体」与「合并章仍有粗体」两条并存且都要断言。
# ══════════════════════════════════════════════════════════════════════════════

# 同构子节 → 合并章 section_number（须与脚本 ISOMORPHIC_SOURCE 逐字相等）
TASK6_ISOMORPHIC_SOURCE: dict[str, dict[str, str]] = {
    "listed": {
        "应收票据": "五、4",
        "应收账款": "五、5",
        "其他应收款": "五、8",
        "营业收入与营业成本": "五、62",
    },
    "soe": {
        "应收账款": "八、5",
        "其他应收款": "八、9",
        "营业收入与营业成本": "八、64",
    },
}

# 合并章源侧**预存在**的 markdown 粗体（2026-08-06 实测，属另一半径不修）。
# 键 = (variant, 合并章 section_number, 表名)
MERGED_CHAPTER_BOLD_TABLES: dict[tuple[str, str], str] = {
    ("listed", "五、8"): "应收政府补助情况",
    ("soe", "八、9"): "按账龄披露其他应收款项",
}

# Task 6 替换后各同构子节的 `_removed_table_keys` 条数（2026-08-06 apply 后实测）
TASK6_REMOVED_KEY_COUNT: dict[str, dict[str, int]] = {
    "listed": {"应收票据": 7, "应收账款": 5, "其他应收款": 7, "营业收入与营业成本": 4},
    # 🔴 soe/其他应收款 由 15 修正为 11（2026-08-07）：15 是「Task 4 中间名也在链条里」
    # 那一版未提交中间态的快照。模板 JSON 经 HEAD 覆盖 + 幂等脚本 `--apply` 恢复后，
    # removed 直接由「HEAD 名集合 − 合并章新名」推导 = 11 项（实测逐字相等），
    # 中间名 `（表8..11）` 在工作树与 HEAD 均 0 命中 ⇒ 不得再要求它们留痕。
    # 详见 `test_soe_other_recv_is_isomorphic_not_task4_scope` 的注释。
    # 其余 6 个同构子节的条数与 HEAD 推导逐字相等，未受该轮影响。
    "soe": {"应收账款": 11, "其他应收款": 11, "营业收入与营业成本": 5},
}


def _task6_params() -> list[Any]:
    out: list[Any] = []
    for variant, mapping in TASK6_ISOMORPHIC_SOURCE.items():
        for title in mapping:
            ident = f"{variant}-{TASK6_ISOMORPHIC_SOURCE[variant][title]}"
            out.append(pytest.param(variant, title, id=ident))
    return out


def _merged_section(
    sections: list[dict[str, Any]], section_number: str
) -> dict[str, Any]:
    hits = [s for s in sections if s.get("section_number") == section_number]
    assert len(hits) == 1, (
        f"合并章「{section_number}」应唯一命中，实为 {len(hits)} 条"
    )
    return hits[0]


class TestIsomorphicAlignment:
    """Property 9 / 11：同构子节表集合与列结构与合并章一致。"""

    def test_source_mapping_matches_fix_script(self) -> None:
        """交叉锁死：守卫登记的映射必须与脚本 ``ISOMORPHIC_SOURCE`` 逐字相等。"""
        assert FIX.ISOMORPHIC_SOURCE == TASK6_ISOMORPHIC_SOURCE, (
            f"脚本 ISOMORPHIC_SOURCE={FIX.ISOMORPHIC_SOURCE} 与守卫登记="
            f"{TASK6_ISOMORPHIC_SOURCE} 不一致"
        )

    def test_isomorphic_and_own_sets_are_disjoint(self) -> None:
        """需求 4.2：自有表子节不得出现在同构映射里（两常量交集必须为空）。"""
        for variant in ("listed", "soe"):
            iso = set(FIX.ISOMORPHIC_SOURCE[variant])
            own = set(FIX.OWN_TABLE_SECTIONS[variant])
            assert not (iso & own), f"{variant} 同构与自有表子节集合相交：{iso & own}"

    def test_fix_script_check_reports_zero_debt(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """交叉锁死主断言：脚本自己的 ``check_isomorphic`` 对两版必须 0 欠账。

        它逐表做**深相等**比对（除表级 ``_aligned_by``/``_aligned_at`` 戳记与已剥离
        的粗体），故「表集合与列结构一致」（需求 4.1）由这一条完整覆盖。
        """
        for variant in ("listed", "soe"):
            errs = FIX.check_isomorphic({"sections": templates[variant]}, variant)
            assert not errs, f"{variant} check_isomorphic 报欠账：{errs}"

    @pytest.mark.parametrize("variant,title", _task6_params())
    def test_table_names_and_columns_match_merged(
        self, templates: dict[str, list[dict[str, Any]]], variant: str, title: str
    ) -> None:
        """逐子节：表名序列与每表列结构（headers/columns/_column_groups）与合并章一致。

        与上一条的差别 = 这条在失败时能指出**具体哪个子节哪张表**，且不依赖脚本
        判据的完整性（脚本判据被削弱时这条仍红）。
        """
        sections = templates[variant]
        src = _merged_section(sections, TASK6_ISOMORPHIC_SOURCE[variant][title])
        got = _subsection_tables(sections, variant, title)
        want = src.get("tables") or []
        assert [str(t.get("name")) for t in got] == [
            str(t.get("name")) for t in want
        ], f"{variant}/{title} 表名序列与合并章不一致"
        for i, (g, w) in enumerate(zip(got, want)):
            where = f"{variant}/{title} 表[{i}]「{g.get('name')}」"
            assert g.get("headers") == w.get("headers"), f"{where} headers 不一致"
            assert g.get("columns") == w.get("columns"), f"{where} columns 不一致"
            assert g.get("_column_groups") == w.get("_column_groups"), (
                f"{where} _column_groups 不一致"
            )

    @pytest.mark.parametrize("variant,title", _task6_params())
    def test_columns_present_and_explicit(
        self, templates: dict[str, list[dict[str, Any]]], variant: str, title: str
    ) -> None:
        """需求 5.1：同构子节全部表 columns 齐备且显式表态 group / flat。

        这是「整体替换即让 Task 7 的 columns 判据天然满足」的机器证明 ——
        合并章那 7 个子节的表本已全部合规。
        """
        tables = _subsection_tables(templates[variant], variant, title)
        problems: list[str] = []
        for i, tbl in enumerate(tables):
            cols = tbl.get("columns") or []
            where = f"{variant}/{title} 表[{i}]「{tbl.get('name')}」"
            if not cols:
                problems.append(f"{where} 缺 columns")
                continue
            has_group = any(c.get("group") for c in cols)
            has_flat = any(c.get("flat") for c in cols)
            if not has_group and not has_flat:
                problems.append(f"{where} columns 未表态（会触发前缀推断）")
            if has_group and cols[0].get("group"):
                problems.append(f"{where} 标签列不得带 group")
            want_groups = FIX.derive_column_groups(cols)
            groups = tbl.get("_column_groups")
            if want_groups and groups != want_groups:
                problems.append(f"{where} _column_groups 与 columns.group 不一致")
        assert not problems, "\n".join(problems)

    @pytest.mark.parametrize("variant,title", _task6_params())
    def test_no_markdown_bold_in_parent_side(
        self, templates: dict[str, list[dict[str, Any]]], variant: str, title: str
    ) -> None:
        """需求 5.3 / Property 12：母公司侧 guidance 不得含 markdown 粗体。

        合并章源侧有 2 处粗体，复制管道必须剥掉；漏剥即打红。
        """
        tables = _subsection_tables(templates[variant], variant, title)
        bold = [
            str(t.get("name"))
            for t in tables
            if "**" in str(t.get("guidance") or "")
        ]
        assert not bold, f"{variant}/{title} guidance 残留 markdown 粗体：{bold}"

    @pytest.mark.parametrize(
        "variant,section_number,table_name",
        [
            pytest.param(v, n, t, id=f"{v}-{n}")
            for (v, n), t in MERGED_CHAPTER_BOLD_TABLES.items()
        ],
    )
    def test_merged_chapter_bold_left_untouched(
        self,
        templates: dict[str, list[dict[str, Any]]],
        variant: str,
        section_number: str,
        table_name: str,
    ) -> None:
        """Property 28 的正面断言：合并章那 2 处粗体**仍在**（本 spec 不得顺手改）。

        它同时是「剥离确实发生在复制管道里、而非改了源」的证明：母公司侧无粗体
        （上一条）+ 合并章有粗体（本条）两者并存，才说明剥离口径正确。
        """
        src = _merged_section(templates[variant], section_number)
        tbl = next(
            (t for t in (src.get("tables") or []) if str(t.get("name")) == table_name),
            None,
        )
        assert tbl is not None, f"合并章「{section_number}」缺表「{table_name}」"
        assert "**" in str(tbl.get("guidance") or ""), (
            f"合并章「{section_number}」表「{table_name}」的 markdown 粗体已消失 —— "
            "本 spec 对合并章只读，若确需修正请另立 spec 并更新本断言"
        )

    @pytest.mark.parametrize("variant,title", _task6_params())
    def test_parent_tables_are_deep_copies(
        self, templates: dict[str, list[dict[str, Any]]], variant: str, title: str
    ) -> None:
        """深拷贝断言：母公司侧与合并章不共享任何 dict 对象。

        共享会让任一侧后续改动互相污染（Task 12 取数接线一改就污染合并章），
        且合并章零回归判据会以诡异方式打红。判据用 ``is`` 身份比较。
        """
        sections = templates[variant]
        src = _merged_section(sections, TASK6_ISOMORPHIC_SOURCE[variant][title])
        got = _subsection_tables(sections, variant, title)
        want = src.get("tables") or []
        shared = [
            str(g.get("name")) for g, w in zip(got, want) if g is w
        ]
        assert not shared, f"{variant}/{title} 与合并章共享同一批 dict 对象：{shared}"

    @pytest.mark.parametrize("variant,title", _task6_params())
    def test_removed_table_keys_disjoint_from_current(
        self, templates: dict[str, list[dict[str, Any]]], variant: str, title: str
    ) -> None:
        """``_removed_table_keys`` 必须与本次写入的表名求过差集（沿用服务端语义）。

        否则消费方接上时会把刚写入的表当孤儿删掉。
        """
        sections = templates[variant]
        kid = next(
            k for k in _children(sections, variant) if k.get("section_title") == title
        )
        removed = kid.get(FIX.REMOVED_TABLE_KEYS_FIELD) or []
        current = {str(t.get("name")) for t in (kid.get("tables") or [])}
        overlap = sorted(set(map(str, removed)) & current)
        assert not overlap, (
            f"{variant}/{title} _removed_table_keys 与现存表名重叠：{overlap} —— "
            "会把刚写入的表当孤儿删"
        )
        assert len(removed) == TASK6_REMOVED_KEY_COUNT[variant][title], (
            f"{variant}/{title} removed 键数应为 "
            f"{TASK6_REMOVED_KEY_COUNT[variant][title]}，实为 {len(removed)} —— "
            "结构确有改动请同步更新 TASK6_REMOVED_KEY_COUNT"
        )

    def test_subsection_count_unchanged(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """需求 4.8：整体替换 tables 不得增删子节（listed 6 / soe 6）。"""
        for variant in ("listed", "soe"):
            kids = _children(templates[variant], variant)
            assert len(kids) == EXPECTED_SUBSECTION_COUNT[variant], (
                f"{variant} 母公司章子节数应为 {EXPECTED_SUBSECTION_COUNT[variant]}，"
                f"实为 {len(kids)}"
            )

    def test_own_table_sections_not_aligned_to_merged(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """需求 4.7 反向断言：投资收益**不得**被套用合并章结构。

        listed 合并章投资收益是 2 张表，母公司侧是 1 张 —— 若哪天有人把自有表子节
        也加进 ISOMORPHIC_SOURCE，这条会红。
        """
        for variant in ("listed", "soe"):
            tables = _subsection_tables(templates[variant], variant, "投资收益")
            assert len(tables) == 1, (
                f"{variant}/投资收益 应为 1 张自有表（需求 4.7），实为 {len(tables)} 张"
            )

    # ── 反向自检：判据非空转 ────────────────────────────────────────────────
    def test_selfcheck_check_isomorphic_detects_table_count_drift(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """删掉母公司侧一张表则 ``check_isomorphic`` 必红（证明它不是死断言）。"""
        doc = json.loads(json.dumps({"sections": templates["soe"]}, ensure_ascii=False))
        kid = next(
            k
            for k in FIX._parent_children(doc["sections"], "soe")
            if k.get("section_title") == "应收账款"
        )
        kid["tables"] = (kid.get("tables") or [])[:-1]
        errs = FIX.check_isomorphic(doc, "soe")
        assert any("表数应与合并章" in e for e in errs), errs

    def test_selfcheck_check_isomorphic_detects_column_drift(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """改坏母公司侧一张表的 columns 则必红（不只查表名与表数）。"""
        doc = json.loads(json.dumps({"sections": templates["listed"]}, ensure_ascii=False))
        kid = next(
            k
            for k in FIX._parent_children(doc["sections"], "listed")
            if k.get("section_title") == "应收票据"
        )
        kid["tables"][0]["columns"] = []
        errs = FIX.check_isomorphic(doc, "listed")
        assert any("与合并章不一致" in e and "columns" in e for e in errs), errs

    def test_selfcheck_build_strips_bold_and_deep_copies(self) -> None:
        """``build_isomorphic_tables``：剥成对粗体 / 深拷贝 / 清表级戳记。"""
        src = [
            {
                "name": "T",
                "guidance": "含**粗体**说明",
                "columns": [{"key": "a", "label": "A", "flat": True}],
                "_aligned_by": "other-spec",
                "_aligned_at": "2026-01-01",
            }
        ]
        out, pairs = FIX.build_isomorphic_tables(src)
        assert pairs == 1
        assert out[0]["guidance"] == "含粗体说明"
        assert "_aligned_by" not in out[0] and "_aligned_at" not in out[0]
        assert out[0] is not src[0]
        assert out[0]["columns"] is not src[0]["columns"]
        assert out[0]["columns"][0] is not src[0]["columns"][0]
        # 源侧逐字未变（纯函数语义）
        assert src[0]["guidance"] == "含**粗体**说明"
        assert src[0]["_aligned_by"] == "other-spec"

        # 🔴 **无粗体**样本同样必须逐层深拷贝（2026-08-06 变异检验 M11 补强）。
        # 只用含粗体样本断言时，「无粗体子树直接返回原对象」这类实现能全绿逃逸 ——
        # 而真实数据里绝大多数表无粗体 ⇒ 母公司侧与合并章会开始共享 dict。
        # `TestIsomorphicAlignment.test_parent_tables_are_deep_copies` 抓不到它：
        # 那条读的是 `json.loads` 出来的两份对象，身份天然不同（判据结构性偏弱），
        # 故深拷贝这条性质的真正防线在**函数层**，即本用例。
        plain = [{"name": "P", "guidance": "无粗体", "columns": [{"key": "a", "flat": True}]}]
        pout, ppairs = FIX.build_isomorphic_tables(plain)
        assert ppairs == 0
        assert pout[0] is not plain[0]
        assert pout[0]["columns"] is not plain[0]["columns"]
        assert pout[0]["columns"][0] is not plain[0]["columns"][0], (
            "无粗体的嵌套 dict 被原样返回 ⇒ 母公司侧与合并章共享对象，"
            "任一侧后续改动会互相污染"
        )

    def test_selfcheck_build_keeps_unpaired_bold(self) -> None:
        """不成对的 ``**`` 是脱敏占位（如「金额为**元」），必须原样保留。"""
        out, pairs = FIX.build_isomorphic_tables(
            [{"name": "T", "guidance": "诉讼金额为**元"}]
        )
        assert pairs == 0
        assert out[0]["guidance"] == "诉讼金额为**元"

    def test_selfcheck_merge_removed_keys_semantics(self) -> None:
        """``merge_removed_table_keys``：并入旧名 / 与新名求差集 / 去重 / 跳空名。"""
        # 旧名与新名相同的不进 removed（否则删掉刚写入的表）
        assert FIX.merge_removed_table_keys(None, ["A", "B"], ["A", "C"]) == ["B"]
        # 空名不登记
        assert FIX.merge_removed_table_keys(None, ["", "  ", "B"], []) == ["B"]
        # 去重且保序
        assert FIX.merge_removed_table_keys(["X"], ["B", "X", "B"], []) == ["X", "B"]
        # 幂等：已在 existing 里的旧名不重复追加
        first = FIX.merge_removed_table_keys(None, ["B"], ["A"])
        assert FIX.merge_removed_table_keys(first, ["B"], ["A"]) == first
        # 反向自检：不求差集的朴素实现会把新表名留在 removed 里
        naive = ["A", "B"]
        assert "A" in naive and "A" not in FIX.merge_removed_table_keys(
            None, ["A", "B"], ["A"]
        )

    def test_selfcheck_find_section_rejects_ambiguous(self) -> None:
        """``_find_section_by_number`` 多命中返回 None（宁缺勿造，不静默取第一条）。"""
        dup = [
            {"section_number": "五、4", "tables": []},
            {"section_number": "五、4", "tables": []},
        ]
        assert FIX._find_section_by_number(dup, "五、4") is None
        one = [{"section_number": "五、4", "tables": []}]
        assert FIX._find_section_by_number(one, "五、4") is one[0]
        assert FIX._find_section_by_number(one, "五、99") is None


# ══════════════════════════════════════════════════════════════════════════════
# Task 7：列元数据与编制指引补齐（Property 12 / 13 / 14 的自有表子节部分）
#
# 覆盖 = 自有表子节里**除长期股权投资以外**的 3 张表（listed/投资收益、
# soe/投资收益、soe/现金流量表补充资料）+ soe 章首说明 5 段。
# 同构子节 7 个由 Task 6 按合并章整体替换而继承齐备列结构 ⇒ 不在本任务范围
# （在此重写会与 `check_isomorphic` 的「与合并章深相等」判据打架）。
# ══════════════════════════════════════════════════════════════════════════════

# Task 7 覆盖的子节（必须与脚本 `COLUMNS_SECTIONS` 逐字相等，见交叉锁死用例）
TASK7_COLUMNS_SECTIONS: dict[str, tuple[str, ...]] = {
    "listed": ("投资收益",),
    "soe": ("投资收益", "现金流量表补充资料"),
}

# 三张表的目标列（key 为数据键，label 为 headers 叶子名）。
# **单级 3 列，全部标 `flat`** —— 源 docx 三张表都是 `项目/来源 | 本期发生额 | 上期发生额`
# 单行表头，不标 flat 会被 `_infer_groups_from_headers` 按「本期/上期」前缀推断出
# 凭空父表头（平台既有铁律）。
TASK7_TARGET_COLUMNS: dict[str, dict[str, list[tuple[str, str]]]] = {
    "listed": {
        "投资收益": [("label", "项目"), ("current", "本期发生额"), ("prior", "上期发生额")],
    },
    "soe": {
        "投资收益": [
            ("label", "产生投资收益的来源"),
            ("current", "本期发生额"),
            ("prior", "上期发生额"),
        ],
        "现金流量表补充资料": [
            ("label", "项目"),
            ("current", "本期发生额"),
            ("prior", "上期发生额"),
        ],
    },
}

# 🔴 源 docx 括注里的**笔误**「也有那个作出说明」（listed 侧）原样保留，禁「顺手修正」。
# soe 侧同位置写的是「也应做出说明」—— 两版用语差异属源模板事实，不得统一。
_LISTED_INV_GUIDANCE_TYPO = "也有那个作出说明"
_SOE_INV_GUIDANCE_CORRECT = "也应做出说明"


class TestTask7OwnTableColumns:
    """Task 7 交付判据：3 张自有表的 columns / guidance 与目标态逐字相符。"""

    def test_scope_matches_fix_script(self) -> None:
        """交叉锁死：守卫登记的覆盖范围 == 脚本 ``COLUMNS_SECTIONS``。

        并断言它恰为「自有表子节 − 长期股权投资」（范围推导可复算，不是手抄清单）。
        """
        assert FIX.COLUMNS_SECTIONS == TASK7_COLUMNS_SECTIONS, (
            f"脚本 COLUMNS_SECTIONS={FIX.COLUMNS_SECTIONS} 与守卫登记="
            f"{TASK7_COLUMNS_SECTIONS} 不一致"
        )
        for variant, titles in FIX.OWN_TABLE_SECTIONS.items():
            derived = tuple(t for t in titles if t != FIX.LTE_SECTION_TITLE)
            assert FIX.COLUMNS_SECTIONS[variant] == derived, (
                f"{variant} COLUMNS_SECTIONS 应恰为「自有表子节 − 长期股权投资」={derived}"
            )
        # 与同构清单不得有交集（同构子节的列结构归 Task 6）
        for variant in ("listed", "soe"):
            overlap = set(FIX.COLUMNS_SECTIONS[variant]) & set(
                FIX.ISOMORPHIC_SOURCE.get(variant) or {}
            )
            assert not overlap, f"{variant} Task 7 范围与同构清单相交：{sorted(overlap)}"

    @pytest.mark.parametrize(
        "variant,title",
        [
            pytest.param("listed", "投资收益", id="listed-inv-income"),
            pytest.param("soe", "投资收益", id="soe-inv-income"),
            pytest.param("soe", "现金流量表补充资料", id="soe-cashflow"),
        ],
    )
    def test_columns_match_target_and_headers(
        self, templates: dict[str, list[dict[str, Any]]], variant: str, title: str
    ) -> None:
        """需求 5.1：columns 齐备、逐字符合目标、与 headers 一一对应、显式 ``flat``。"""
        tables = _subsection_tables(templates[variant], variant, title)
        assert len(tables) == 1, f"{variant}/{title} 应为 1 张表，实为 {len(tables)}"
        tbl = tables[0]
        want = TASK7_TARGET_COLUMNS[variant][title]
        cols = tbl.get("columns") or []
        assert [(str(c.get("key")), str(c.get("label"))) for c in cols] == want, (
            f"{variant}/{title} columns 的 (key,label) 序列与目标不符：{cols}"
        )
        assert list(tbl.get("headers") or []) == [lbl for _, lbl in want], (
            f"{variant}/{title} headers 应等于 columns 的 label 序列（叶子名）"
        )
        assert cols[0].get("is_label") is True, f"{variant}/{title} 首列未标 is_label"
        assert cols[0].get("flat") is True, (
            f"{variant}/{title} 单级表未显式标 flat —— 会触发 _infer_groups_from_headers "
            "按「本期/上期」前缀推断出凭空父表头"
        )
        assert not any(c.get("group") for c in cols), (
            f"{variant}/{title} 单级表不得声明 group（flat 与 group 并存 = 表态冲突）"
        )
        assert tbl.get("_column_groups") is None, (
            f"{variant}/{title} 单级表头不得残留 _column_groups：{tbl.get('_column_groups')!r}"
        )
        # 金额列必须带 format（附注编辑器按它渲染千分符）
        for c in cols[1:]:
            assert c.get("format") == "amount", (
                f"{variant}/{title} 列「{c.get('label')}」缺 format=amount：{c}"
            )

    @pytest.mark.parametrize(
        "variant,title",
        [
            pytest.param("listed", "投资收益", id="listed-inv-income"),
            pytest.param("soe", "投资收益", id="soe-inv-income"),
            pytest.param("soe", "现金流量表补充资料", id="soe-cashflow"),
        ],
    )
    def test_guidance_present_plaintext(
        self, templates: dict[str, list[dict[str, Any]]], variant: str, title: str
    ) -> None:
        """需求 5.2 / 5.3：guidance 非空、纯文本、且只由源 docx 括注 + 「勾稽：」提示组成。"""
        tbl = _subsection_tables(templates[variant], variant, title)[0]
        guidance = str(tbl.get("guidance") or "")
        assert guidance.strip(), f"{variant}/{title} 缺 guidance"
        assert "**" not in guidance, f"{variant}/{title} guidance 含 markdown 粗体"
        assert "勾稽：" in guidance, (
            f"{variant}/{title} guidance 应含「勾稽：」前缀的工具提示（需求 5.2 允许的两类之一）"
        )
        # 禁自造披露要求：除「勾稽：」那行外，其余内容必须能在源 docx 括注 / 章首说明里找到
        assert not re.search(r"(应当|必须)按本平台", guidance), (
            f"{variant}/{title} guidance 出现平台自造措辞：{guidance!r}"
        )

    def test_listed_guidance_keeps_source_typo(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """源模板笔误「也有那个作出说明」原样保留，且两版用语差异不得被统一。

        这条是「逐字取自源 docx」的正向锚点 —— 下个会话「顺手修正」错别字即打红。
        """
        listed_g = str(
            _subsection_tables(templates["listed"], "listed", "投资收益")[0].get("guidance")
        )
        soe_g = str(
            _subsection_tables(templates["soe"], "soe", "投资收益")[0].get("guidance")
        )
        assert _LISTED_INV_GUIDANCE_TYPO in listed_g, (
            f"listed/投资收益 guidance 应原样保留源 docx 笔误「{_LISTED_INV_GUIDANCE_TYPO}」，"
            f"实为：{listed_g!r}"
        )
        assert _SOE_INV_GUIDANCE_CORRECT in soe_g, (
            f"soe/投资收益 guidance 应为源 docx 原文「{_SOE_INV_GUIDANCE_CORRECT}」，实为：{soe_g!r}"
        )
        assert _LISTED_INV_GUIDANCE_TYPO not in soe_g, "两版用语差异被强行统一（soe 侧被写成笔误）"

    def test_rows_untouched_by_task7(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Task 7 只补列元数据与 guidance，``rows`` 一律不动（行集是源 docx 裁决过的）。

        行数锚定源 docx 事实（needs 4.7：listed 16 行含表头 = 15 数据行；soe 21 行含表头
        = 20 数据行；现金流量表补充资料 31 行含表头 = 30 数据行）。
        """
        expected_rows = {
            ("listed", "投资收益"): 15,
            ("soe", "投资收益"): 20,
            ("soe", "现金流量表补充资料"): 30,
        }
        for (variant, title), want in expected_rows.items():
            tbl = _subsection_tables(templates[variant], variant, title)[0]
            rows = tbl.get("rows") or []
            assert len(rows) == want, (
                f"{variant}/{title} rows 应为 {want} 行（源 docx 含表头 {want + 1} 行），"
                f"实为 {len(rows)}"
            )
            assert not any(
                str((r or {}).get("row_type") or "") == "header_label" for r in rows
            ), f"{variant}/{title} 残留 header_label 行"

    def test_task7_steps_are_wired_into_cli(self) -> None:
        """🔴 防「写了函数但没接进 CLI」= additive 注入即死代码。

        源码级断言 ``process()`` 的 apply 流水与 ``_checks()`` 都引用了 Task 7 的四个函数，
        且 ``apply_columns`` 排在 ``apply_table_renames`` **之后**（列规则按表名索引，
        先补列会落到尚未正名的旧表名上 —— 这是 tasks.md 明写的顺序约束）。
        """
        src = FIX_SCRIPT_PATH.read_text(encoding="utf-8")
        body = src[src.index("def process("):]
        body = body[: body.index("\ndef main(")]
        for name in (
            "apply_columns",
            "check_columns",
            "apply_chapter_intro",
            "check_chapter_intro",
        ):
            assert re.search(rf"\b{name}\(", body), f"process() 未调用 {name}（函数成死代码）"
        rename_at = body.index("apply_table_renames(")
        columns_at = body.index("apply_columns(")
        assert rename_at < columns_at, (
            "apply_columns 必须排在 apply_table_renames 之后（列规则按表名索引）"
        )

    def test_fix_script_check_columns_reports_zero_debt(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """交叉锁死：幂等脚本自己的 ``check_columns`` 对当前 JSON 必须 0 欠账。

        它内部除逐表判据外还调 kit 的 ``validate_section``（表名齐备唯一 / headers 无空串
        无 HTML / 同组列名不重复 / ``_column_groups`` 越界 / ``text_sections`` 含裸表名），
        本文件不重抄那批判据 —— 削弱任一侧另一侧会红。
        """
        for variant in ("listed", "soe"):
            errs = FIX.check_columns({"sections": templates[variant]}, variant)
            assert not errs, f"{variant} check_columns 报欠账：{errs}"

    def test_selfcheck_check_own_table_detects_each_defect(self) -> None:
        """反向自检：共用件 ``_check_own_table`` 对八类缺陷逐个必红，合格态必绿。

        🔴 **每条都断言「消息里出现该判据自己的关键词」，不是只断言 errs 非空**
        —— 2026-08-06 变异检验实测：去掉「未表态」那条分支后，本自检**仍然通过**，
        因为「columns 与目标态不一致」这条兜住了（替身把 columns 改坏，自然也就与目标
        不一致）⇒ 一个核心判据被删掉却没打红 = 守卫缺陷。改为关键词断言后，删哪条
        分支哪条自检就红，判据之间不再互相掩盖。
        """
        cols = FIX._inv_columns("项目")
        good_tbl = {
            "name": "投资收益",
            "headers": FIX.headers_of(cols),
            "columns": json.loads(json.dumps(cols, ensure_ascii=False)),
            "guidance": "勾稽：合计行 = 其上各项目之和。",
            "rows": [{"label": "x", "row_type": "data"}],
        }
        spec = {"columns": cols, "guidance": "x", "rebuild_headers": True}
        assert FIX._check_own_table(good_tbl, spec, "t") == []

        def mutate(keyword: str, *, spec_cols: list[dict[str, Any]] | None = None, **over: Any) -> None:
            t = json.loads(json.dumps(good_tbl, ensure_ascii=False))
            t.update(json.loads(json.dumps(over, ensure_ascii=False)))
            use = spec if spec_cols is None else {**spec, "columns": spec_cols}
            errs = FIX._check_own_table(t, use, "t")
            assert any(keyword in e for e in errs), (
                f"缺陷「{keyword}」未被抓到（该判据分支可能已被删）：errs={errs}"
            )

        mutate("缺 columns", columns=[])
        mutate("缺 guidance", guidance="")
        mutate("markdown 粗体", guidance="勾稽：**加粗**")
        mutate("columns=3", headers=["项目", "本期发生额"])  # 长度不符
        # 🔴 标签列名与 headers[0] 不符**必须单列一条** —— 长度相同才能让「长度不符」
        # 这条不参与，否则 `columns[0].label ≠ headers[0]` 判据被删掉也不会红
        # （2026-08-06 第二轮变异检验 B3 实测为 GREEN 才补上本条）。
        mutate("headers[0]", headers=["科目", "本期发生额", "上期发生额"])
        mutate("首列未标 is_label", columns=[{"key": "label", "label": "项目", "flat": True}]
               + json.loads(json.dumps(cols[1:], ensure_ascii=False)),
               spec_cols=[{"key": "label", "label": "项目", "flat": True}]
               + json.loads(json.dumps(cols[1:], ensure_ascii=False)))
        # 未表态（去掉 flat）：**目标态同步去掉**，使「与目标不一致」不参与，
        # 只剩「未表态」这一条能触发 ⇒ 删掉该分支即红
        no_state = json.loads(json.dumps(cols, ensure_ascii=False))
        no_state[0].pop("flat")
        mutate("未表态", columns=no_state, spec_cols=no_state)
        # 表态冲突（flat 与 group 并存）：同样让目标态与之相同，并同步 _column_groups，
        # 使「与目标不一致」「_column_groups 不一致」都不参与
        conflict = json.loads(json.dumps(cols, ensure_ascii=False))
        conflict[1]["group"] = "本期"
        mutate(
            "表态冲突",
            columns=conflict,
            _column_groups=FIX.derive_column_groups(conflict),
            spec_cols=conflict,
        )
        # 标签列带 group（混合分组下的非法形态）
        label_grouped = json.loads(json.dumps(cols, ensure_ascii=False))
        label_grouped[0].pop("flat")
        label_grouped[0]["group"] = "期末"
        label_grouped[1]["group"] = "期末"
        mutate(
            "标签列不得带 group",
            columns=label_grouped,
            _column_groups=FIX.derive_column_groups(label_grouped),
            spec_cols=label_grouped,
        )
        mutate("header_label", rows=[{"label": "本期发生额", "row_type": "header_label"}])
        mutate("残留 _column_groups", _column_groups=[{"group": "本期", "start": 1, "span": 2}])
        mutate("与目标态不一致", columns=[{"key": "label", "label": "项目", "is_label": True,
                                          "flat": True}])

    def test_selfcheck_target_columns_are_not_self_certified(self) -> None:
        """反向自检：守卫的目标列不是从 JSON 反抄的，而是与脚本常量交叉锁死。"""
        for variant, by_title in TASK7_TARGET_COLUMNS.items():
            for title, want in by_title.items():
                specs = FIX.OWN_RULES[variant][title]
                assert len(specs) == 1
                cols = specs[0]["columns"]
                assert [(str(c.get("key")), str(c.get("label"))) for c in cols] == want, (
                    f"{variant}/{title} 脚本 OWN_RULES 的列与守卫登记不一致"
                )


class TestTask7ChapterIntro:
    """Task 7：soe 章首说明 5 段（需求 5.2），listed 侧反向断言不得凭空造文字。"""

    def test_soe_intro_matches_source_docx_verbatim(
        self, templates: dict[str, list[dict[str, Any]]], docx_facts: dict[str, Any]
    ) -> None:
        """判据来自源 docx（Property 2）：模板侧章首段落 ⊇ 源 docx intro_paragraphs，逐字。

        🔴 源 docx 实测是**连续 5 段**（Heading 1 之后、首个子节 Heading 之前）。
        此前脚本常量只存了中间 3 条编号项且把第 3 条末尾的 `）` 截掉（与第 1 段开头的
        `（` 本是一对）—— 那已是改写源文。Task 7 改为整段区间照抄，故这条断言才成立。
        """
        docx_intro = list(_docx_parent(docx_facts, "soe").get("intro_paragraphs") or [])
        assert len(docx_intro) == 5, (
            f"源 docx soe 母公司章章首说明应为 5 段，实为 {len(docx_intro)} 段 —— "
            "源模板已变更，Task 7 的章首内容需重新裁决"
        )
        assert list(FIX.SOE_CHAPTER_INTRO) == docx_intro, (
            "脚本 SOE_CHAPTER_INTRO 与源 docx 章首段落不逐字相等：\n"
            f"  docx : {docx_intro}\n  const: {list(FIX.SOE_CHAPTER_INTRO)}"
        )
        chapter = _chapter(templates["soe"], "soe")
        paras = [str(p) for p in (chapter.get("text_sections") or [])]
        missing = [p for p in docx_intro if p not in paras]
        assert not missing, (
            f"soe 母公司章 text_sections 缺源 docx 章首说明 {len(missing)} 段：{missing}"
        )
        # 三条实质要求必须在其中（tasks.md 点名的那三条）
        for kw in ("应参照上述相应项目的要求加以注释", "反向购买", "资本公积弥补亏损"):
            assert any(kw in p for p in paras), f"soe 章首说明缺「{kw}」相关段落"

    def test_soe_intro_paragraphs_are_body_not_titles(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """章首说明必须作为**披露正文**可见 —— 任一段被判成标题即静默丢弃。

        🔴 这条不是形式主义：`_NUMBERED_TITLE_RE` 会命中 `1、` 前缀，三条编号项**只因
        长度 >20 字**才逃过 20 字长度门。谁把它们缩写或加 `#### ` 前缀，这条立刻红。
        """
        chapter = _chapter(templates["soe"], "soe")
        paras = [str(p) for p in (chapter.get("text_sections") or [])]
        assert paras, "soe 母公司章 text_sections 为空"
        # 判据走幂等脚本 import 进来的 kit 函数（`is_title_paragraph` 复刻后端
        # `disclosure_engine._is_table_title_paragraph`），不在本文件重抄一份
        titled = [p for p in paras if FIX.is_title_paragraph(p)]
        assert not titled, (
            "soe 章首说明有段落会被 disclosure_engine._is_table_title_paragraph 判成标题"
            f"（标题本身不进任何输出 ⇒ 静默丢弃）：{[p[:24] for p in titled]}"
        )
        assert not any(p.lstrip().startswith("#") for p in paras), (
            "章首说明不得带 markdown 标题前缀（`#` 开头一律判标题）"
        )
        assert not any("**" in p for p in paras), "章首说明含 markdown 粗体（需求 5.3）"

    def test_listed_chapter_has_no_fabricated_intro(
        self, templates: dict[str, list[dict[str, Any]]], docx_facts: dict[str, Any]
    ) -> None:
        """listed 侧源 docx 该章无章首说明段落 ⇒ 模板侧也不得有（宁缺勿造）。

        listed 的「参照合并章」口径写在**子节标题**里（`（披露格式参考附注五、X）`），
        已由 `check_section_kinds` 锁死，不需要也不得另造章级文字。
        """
        docx_intro = list(_docx_parent(docx_facts, "listed").get("intro_paragraphs") or [])
        assert docx_intro == [], (
            f"源 docx listed 母公司章出现 {len(docx_intro)} 段章首说明 —— "
            "「listed 侧无章首说明」这一裁决前提失效，需重新裁决"
        )
        assert FIX.CHAPTER_INTRO["listed"] == [], (
            f"脚本 CHAPTER_INTRO['listed'] 应为空，实为 {FIX.CHAPTER_INTRO['listed']}"
        )
        chapter = _chapter(templates["listed"], "listed")
        paras = list(chapter.get("text_sections") or [])
        assert paras == [], (
            f"listed 母公司章 text_sections 应为空，实有 {len(paras)} 段："
            f"{[str(p)[:24] for p in paras]}"
        )

    def test_fix_script_check_chapter_intro_reports_zero_debt(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """交叉锁死：脚本 ``check_chapter_intro`` 对当前 JSON 必须 0 欠账（含 listed 侧空断言）。"""
        for variant in ("listed", "soe"):
            errs = FIX.check_chapter_intro({"sections": templates[variant]}, variant)
            assert not errs, f"{variant} check_chapter_intro 报欠账：{errs}"

    def test_selfcheck_check_chapter_intro_detects_defects(
        self, templates: dict[str, list[dict[str, Any]]]
    ) -> None:
        """反向自检：缺段 / 粗体 / listed 侧凭空造文字 三类必红，合格态必绿。"""
        soe_doc = json.loads(json.dumps({"sections": templates["soe"]}, ensure_ascii=False))
        assert FIX.check_chapter_intro(soe_doc, "soe") == []
        ch = FIX._find_parent_chapter(soe_doc["sections"], "soe")
        assert ch is not None
        # 缺段
        dropped = json.loads(json.dumps(soe_doc, ensure_ascii=False))
        FIX._find_parent_chapter(dropped["sections"], "soe")["text_sections"] = []
        assert FIX.check_chapter_intro(dropped, "soe")
        # 粗体
        bolded = json.loads(json.dumps(soe_doc, ensure_ascii=False))
        FIX._find_parent_chapter(bolded["sections"], "soe")["text_sections"].append("**x**")
        assert FIX.check_chapter_intro(bolded, "soe")
        # listed 侧凭空造文字
        listed_doc = json.loads(
            json.dumps({"sections": templates["listed"]}, ensure_ascii=False)
        )
        assert FIX.check_chapter_intro(listed_doc, "listed") == []
        FIX._find_parent_chapter(listed_doc["sections"], "listed")["text_sections"] = [
            "自造的章首说明"
        ]
        assert FIX.check_chapter_intro(listed_doc, "listed")

    def test_selfcheck_apply_chapter_intro_is_idempotent_and_skips_titles(self) -> None:
        """反向自检：``apply_chapter_intro`` 幂等；且任一段会被判成标题时整体跳过。"""
        doc = {
            "sections": [
                {
                    "section_id": FIX.PARENT_CHAPTER_SID_NEW["soe"],
                    "level": 1,
                    "text_sections": [],
                }
            ]
        }
        first, warns = FIX.apply_chapter_intro(doc, "soe")
        assert len(first) == len(FIX.SOE_CHAPTER_INTRO) and not warns
        again, _ = FIX.apply_chapter_intro(doc, "soe")
        assert again == [], "第二次 apply 应为空操作（幂等）"
        assert doc["sections"][0]["text_sections"] == list(FIX.SOE_CHAPTER_INTRO)

        # 标题段防护：临时把常量换成会被判成标题的短编号段
        original = FIX.SOE_CHAPTER_INTRO
        try:
            FIX.CHAPTER_INTRO["soe"] = ["1、短标题"]
            blank = {
                "sections": [
                    {
                        "section_id": FIX.PARENT_CHAPTER_SID_NEW["soe"],
                        "level": 1,
                        "text_sections": [],
                    }
                ]
            }
            changes, warnings = FIX.apply_chapter_intro(blank, "soe")
            assert changes == [] and warnings, "会被判成标题的段落必须跳过并告警"
            assert blank["sections"][0]["text_sections"] == []
        finally:
            FIX.CHAPTER_INTRO["soe"] = original
        assert FIX.CHAPTER_INTRO["soe"] is original
