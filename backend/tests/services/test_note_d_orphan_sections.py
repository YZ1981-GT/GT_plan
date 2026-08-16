"""D 循环「孤儿重复章」立项判断的反向锁死守卫。

背景（2026-08-06 实证，本 spec Task 22）
=======================================

本 spec 立项时把 5 个章节列为「孤儿重复章」并计划建
`scripts/fix/cleanup_d_cycle_orphan_note_sections.py` 删除它们：

    listed: 十六、应收票据 / 十六、应收账款 / 十六、营业收入与营业成本
    soe:    十二、应收账款 / 十二、营业收入与营业成本

**该判断已被实测推翻**：这 5 章的 `parent_section_id` 全部指向母公司附注章
（listed `chapter-16-mu-gong-si-...` / soe `chapter-12-mu-gong-si-...`），
它们是母公司口径重复列示同一批科目的**正当子节**，不是 md 重建残留。

三条否证（本文件逐条断言）
--------------------------

1. 5 章全部挂在母公司章下，`scope='consolidated_only'`（母公司口径专属）。
2. 母公司章共 6 个子节，**全部**是 `_aligned_by=None` + `columns` 全 0 —— 而
   立项清单只列了其中 5 个（listed 漏「其他应收款」「长期股权投资」「投资收益」，
   soe 漏「其他应收款」「长期股权投资」「投资收益」「现金流量表补充资料」）。
   ⇒ 立项的「三条判据」描述的是**母公司章共性**（未补列元数据），而非孤儿特征。
3. 全库 80 个 `*NoteSectionMap.ts` 对这 5 个章号的引用数为 **0**，D 类 7 个 map
   全部指向合并章（`五、4`/`八、4` 等）⇒ 不存在「map 指向孤儿章」的风险需要治。

真正的孤儿在别处
----------------

按「全部子表名都是表头首格泄漏」的严判据实测：listed **23 章**（全在
「三、重要会计政策及会计估计」与「十四、资产负债表日后事项」章下）、soe **0 章**。
这批与 memory 已登记的「listed 163 张 / 53 章非科目章节压根没有对应底稿披露
sheet」是同一批，归 `note-template-columns-and-legacy-snapshot-closure`（C spec）。

母公司章的列元数据补齐归 `parent-company-note-chapter-and-sourcing`（A spec）。

本文件的作用
------------

**禁止后续会话据「_aligned_by 为空 + columns 全 0」再判一次孤儿并删除母公司章。**
删掉它们 = 删掉上市第十六章整章 + 国企母公司附注全部（tracked 数据，不可逆）。

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5
Properties: 21, 22, 23
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------- 路径定位

def _repo_root() -> Path:
    """双哨兵具体文件向上查找，禁写死回退级数。"""
    sentinels = (
        Path("backend") / "data" / "note_template_listed.json",
        Path("audit-platform") / "frontend" / "package.json",
    )
    cur = Path(__file__).resolve()
    for cand in [cur, *cur.parents]:
        if all((cand / s).exists() for s in sentinels):
            return cand
    raise AssertionError(
        "未能定位仓库根（双哨兵 backend/data/note_template_listed.json + "
        "audit-platform/frontend/package.json 均需存在）"
    )


REPO_ROOT = _repo_root()
TEMPLATES = {
    "listed": REPO_ROOT / "backend" / "data" / "note_template_listed.json",
    "soe": REPO_ROOT / "backend" / "data" / "note_template_soe.json",
}
FRONTEND_SRC = REPO_ROOT / "audit-platform" / "frontend" / "src"
DIAGNOSE_SCRIPT = (
    REPO_ROOT
    / "backend"
    / "scripts"
    / "diagnose"
    / "diagnose_d_cycle_note_section_hygiene.py"
)


def _strip_py_comments(src: str) -> str:
    """剥掉 Python 的 docstring / 三引号块与 `#` 行注释。

    守卫按「代码里是否出现某能力」判定时必须先剥注释 —— 否则 docstring 里
    「本脚本不提供 --apply」这句说明会被数成真实能力（平台已登记的坑）。
    """
    out: list[str] = []
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        # 三引号块（含 docstring）
        if src.startswith('"""', i) or src.startswith("'''", i):
            quote = src[i : i + 3]
            end = src.find(quote, i + 3)
            i = n if end == -1 else end + 3
            continue
        # 普通字符串（原样保留，其中可能有合法的 SQL 关键字）
        if ch in ("'", '"'):
            quote = ch
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == quote:
                    break
                j += 1
            out.append(src[i : j + 1])
            i = j + 1
            continue
        # 行注释
        if ch == "#":
            end = src.find("\n", i)
            i = n if end == -1 else end
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# --------------------------------------------------- 被撤回的「孤儿章」清单
# 🔴 这是**禁删清单**，不是待删清单。条目只许减少（若某章将来被 A spec
#    正名或补齐列元数据，可从这里移出），绝不许新增。

WITHDRAWN_ORPHAN_SECTIONS: dict[str, tuple[str, ...]] = {
    "listed": ("十六、应收票据", "十六、应收账款", "十六、营业收入与营业成本"),
    "soe": ("十二、应收账款", "十二、营业收入与营业成本"),
}

# 母公司章的 section_id 前缀（实证值，用于证明归属）
PARENT_CHAPTER_PREFIX = {
    "listed": "chapter-16-mu-gong-si-",
    "soe": "chapter-12-mu-gong-si-",
}

# 母公司章子节总数（实证：两版各 6 个）—— 用于证明「立项清单只覆盖其中一部分」
PARENT_CHAPTER_SUBSECTION_COUNT = {"listed": 6, "soe": 6}

# 🔴 立项判据当年的命中情况**冻结快照**（variant -> (判据命中数, 清单条目数)）
#
# 2026-08-06 首次实测时，立项判据（`_aligned_by` 为空 + 全部子表 `columns` 长度为 0）
# 在母公司章**全部** 6 个子节上同时成立，而立项清单只挑了其中 3（listed）/ 2（soe）个
# ⇒ 判据描述的是母公司章共性（未补列元数据），区分不出「谁是孤儿」。
#
# 该状态**正在被 A spec（parent-company-note-chapter-and-sourcing）逐章消除** ——
# 它的 Task 7 就是给母公司章 93 张表补 `columns`。故本守卫**不得**再断言
# 「columns 必须全 0」（那会把 A spec 的正确进展打红），改为：
#   ① 用归属关系（parent_section_id / scope / level）表达禁删锁死；
#   ② 用本快照把「当年判据是共性」这一历史论证钉住。
HISTORICAL_CRITERIA_SNAPSHOT: dict[str, tuple[int, int]] = {
    "listed": (6, 3),
    "soe": (6, 2),
}

# ---------------------------------------------------------------------------
# 立项判据的历史实证快照（2026-08-06 冻结，**不再连库断言**）
#
# 🔴 为什么冻结而不是持续断言：
#   立项判据是「`_aligned_by` 为空 + 全部子表 `columns` 长度为 0」。该状态正在被
#   A spec（`parent-company-note-chapter-and-sourcing`）主动消除 —— 实测 2026-08-06
#   晚 listed「十六、应收票据」14/14 张子表已补齐 columns。
#
#   若把「全部子节 columns 全 0」写成持续断言，A spec 每补一章本守卫就打红一次，
#   而那是**正确的进展**不是回归 ⇒ 守卫会被当噪声关掉，禁删锁死随之失效。
#
#   故：判据共性作为**一次性历史论证**冻结在此（下表 + 文件头 docstring），
#   持续断言改为与列元数据无关的**结构性判据**：
#     ① 撤回清单 ⊊ 母公司章子节集合（真子集 ⇒ 按共性判据必命中更多，判据不成立）
#     ② 归属不变量：子节无论是否已补列，`parent_section_id` 必须仍指向母公司章
# ---------------------------------------------------------------------------

HISTORICAL_CRITERIA_SNAPSHOT = {
    # variant: (满足立项判据的子节数, 立项清单条目数)
    "listed": (6, 3),
    "soe": (6, 2),
}

# D 类 7 个循环的合并章章号（实证值，用于证明 map 指向的不是母公司章）
D_CYCLE_MERGED_SECTIONS = {
    "d1": ("五、4", "八、4"),
    "d2": ("五、5", "八、5"),
    "d3": ("五、38", "八、38"),
    "d4": ("五、62", "八、64"),
    "d5": ("五、6", "八、6"),
    "d6": ("五、10", "八、11"),
    "d7": ("五、39", "八、39"),
}

# 禁止存在的脚本名片段（防「顺手把删除脚本建回来」）
FORBIDDEN_SCRIPT_PATTERNS = (
    "cleanup_d_cycle_orphan_note_sections",
    "cleanup_orphan_note_sections",
)


# ------------------------------------------------------------------ fixtures

@pytest.fixture(scope="module")
def templates() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for variant, path in TEMPLATES.items():
        assert path.exists(), f"模板缺失：{path}"
        data = json.loads(path.read_text(encoding="utf-8"))
        sections = data.get("sections") or []
        assert sections, f"{variant} 模板 sections 为空，判据无从成立"
        out[variant] = sections
    return out


@pytest.fixture(scope="module")
def note_section_map_sources() -> dict[str, str]:
    """全库 *NoteSectionMap.ts 的源码（文件名 → 源码）。"""
    assert FRONTEND_SRC.exists(), f"前端源码目录缺失：{FRONTEND_SRC}"
    files = sorted(FRONTEND_SRC.rglob("*NoteSectionMap.ts"))
    assert len(files) >= 40, (
        f"扫到 {len(files)} 个 *NoteSectionMap.ts，远少于预期（≥40）"
        "，疑似路径或 glob 失效 ⇒ 后续断言会空转"
    )
    return {f.name: f.read_text(encoding="utf-8") for f in files}


def _find_sections(sections: list[dict], number: str) -> list[dict]:
    return [s for s in sections if (s.get("section_number") or "").strip() == number]


def _cols_zero_count(sec: dict) -> int:
    tables = sec.get("tables") or []
    return sum(1 for t in tables if len(t.get("columns") or []) == 0)


# =========================================================================
# Property 21: 曾被列为孤儿的 5 章仍归属母公司章
# =========================================================================

class TestProperty21WithdrawnSectionsBelongToParentChapter:
    """反向锁死：这 5 章的 parent_section_id 必须仍指向母公司章。

    若某天它们真的变成游离章节（parent 指向别处），本断言打红，提示重新裁决。
    """

    def test_each_withdrawn_section_exists_and_is_unique(self, templates):
        for variant, numbers in WITHDRAWN_ORPHAN_SECTIONS.items():
            for number in numbers:
                hits = _find_sections(templates[variant], number)
                assert len(hits) == 1, (
                    f"{variant} 的 {number!r} 命中 {len(hits)} 条（期望恰 1 条）。"
                    "若为 0 条说明该章已被删除 —— 那正是本守卫要防的事。"
                )

    def test_each_withdrawn_section_parents_to_parent_company_chapter(self, templates):
        for variant, numbers in WITHDRAWN_ORPHAN_SECTIONS.items():
            prefix = PARENT_CHAPTER_PREFIX[variant]
            for number in numbers:
                sec = _find_sections(templates[variant], number)[0]
                parent = sec.get("parent_section_id") or ""
                assert parent.startswith(prefix), (
                    f"{variant} {number!r} 的 parent_section_id={parent!r} "
                    f"不以母公司章前缀 {prefix!r} 开头 ⇒ 归属判断需重新裁决，"
                    "不得据旧结论直接删除"
                )

    def test_each_withdrawn_section_is_consolidated_only(self, templates):
        """母公司章节的 scope 恒为 consolidated_only（仅合并口径显示）。"""
        for variant, numbers in WITHDRAWN_ORPHAN_SECTIONS.items():
            for number in numbers:
                sec = _find_sections(templates[variant], number)[0]
                assert sec.get("scope") == "consolidated_only", (
                    f"{variant} {number!r} 的 scope={sec.get('scope')!r}，"
                    "期望 consolidated_only（母公司章特征）"
                )

    def test_withdrawn_list_only_shrinks(self):
        """条目数上限锁死：listed ≤ 3 / soe ≤ 2，只许减少。"""
        assert len(WITHDRAWN_ORPHAN_SECTIONS["listed"]) <= 3
        assert len(WITHDRAWN_ORPHAN_SECTIONS["soe"]) <= 2

    def test_withdrawn_numbers_carry_parent_chapter_prefix(self):
        """清单里的章号字面必须带母公司章号前缀（listed 十六、/ soe 十二、）。"""
        for variant, numbers in WITHDRAWN_ORPHAN_SECTIONS.items():
            expect = "十六、" if variant == "listed" else "十二、"
            for number in numbers:
                assert number.startswith(expect), (
                    f"{variant} 清单里出现 {number!r}，不带母公司章前缀 {expect!r}"
                    " ⇒ 清单被混入了别的章节，须复核"
                )


# =========================================================================
# Property 21（续）: 「三条判据」是母公司章共性而非孤儿特征
# =========================================================================

class TestProperty21CriteriaIsChapterWideNotOrphanSpecific:
    """立项判据在**全部**母公司章子节上都成立 ⇒ 它区分不出孤儿。

    这是「立项判断被推翻」的核心证据：若判据真能识别孤儿，就不该在同章
    未被列入清单的兄弟子节上同样成立。
    """

    def _parent_subsections(self, sections: list[dict], variant: str) -> list[dict]:
        prefix = PARENT_CHAPTER_PREFIX[variant]
        return [
            s
            for s in sections
            if (s.get("parent_section_id") or "").startswith(prefix)
            and (s.get("level") or 0) == 2
        ]

    def test_parent_chapter_subsection_count(self, templates):
        for variant, expected in PARENT_CHAPTER_SUBSECTION_COUNT.items():
            subs = self._parent_subsections(templates[variant], variant)
            assert len(subs) == expected, (
                f"{variant} 母公司章子节实测 {len(subs)} 个，基线 {expected} 个"
                "。子节增减属 A spec 的改动，需同步本基线"
            )

    def test_withdrawn_list_is_a_strict_subset_of_parent_subsections(self, templates):
        """撤回清单是母公司章子节集合的**真子集** —— 判据不成立的结构性证明。

        立项判据（`_aligned_by` 空 + `columns` 全 0）当年在全部 6 个子节上同时
        成立，而清单只挑了 3（listed）/ 2（soe）个 ⇒ 判据区分不出「谁是孤儿」。

        本断言用**归属关系**表达这一点（与列元数据无关），故 A spec 逐章补列时
        不会打红。
        """
        for variant in TEMPLATES:
            subs = self._parent_subsections(templates[variant], variant)
            sub_numbers = {(s.get("section_number") or "").strip() for s in subs}
            listed = set(WITHDRAWN_ORPHAN_SECTIONS[variant])

            assert listed, f"{variant} 撤回清单为空 ⇒ 禁删锁死失效"
            assert listed.issubset(sub_numbers), (
                f"{variant}：清单里有章节不再挂在母公司章下 ⇒ "
                f"{sorted(listed - sub_numbers)}，归属变了必须重新裁决"
            )
            extra = sorted(sub_numbers - listed)
            assert extra, (
                f"{variant}：清单已覆盖母公司章全部子节 ⇒ 「立项判据描述的是母公司"
                "章共性」这一论证失去证据支撑（当年 listed 6 个子节只列了 3 个），"
                "需重新裁决"
            )

    def test_historical_criteria_snapshot_is_consistent_with_list_size(self):
        """冻结快照与清单条目数交叉锁死（防快照与清单各改一处而漂移）。"""
        for variant, (matched_count, listed_count) in HISTORICAL_CRITERIA_SNAPSHOT.items():
            assert listed_count == len(WITHDRAWN_ORPHAN_SECTIONS[variant]), (
                f"{variant}：历史快照记 {listed_count} 条，清单实为 "
                f"{len(WITHDRAWN_ORPHAN_SECTIONS[variant])} 条 ⇒ 改清单须同步快照"
            )
            assert matched_count == PARENT_CHAPTER_SUBSECTION_COUNT[variant]
            assert matched_count > listed_count, (
                f"{variant}：历史快照显示判据命中数 {matched_count} 不大于清单 "
                f"{listed_count} ⇒ 「判据是共性」的论证不成立"
            )

    def test_parent_subsections_keep_their_parent_regardless_of_columns(self, templates):
        """列元数据补齐**不得**改变归属 —— A spec 补列时本断言仍须绿。

        这是禁删锁死的核心不变量：无论 `columns` / `_aligned_by` 怎么变，
        母公司章子节的 `parent_section_id` 与 `scope` 必须保持不变。
        """
        for variant in TEMPLATES:
            subs = self._parent_subsections(templates[variant], variant)
            prefix = PARENT_CHAPTER_PREFIX[variant]
            for sec in subs:
                number = sec.get("section_number")
                assert (sec.get("parent_section_id") or "").startswith(prefix), (
                    f"{variant} {number!r} 的 parent_section_id 不再指向母公司章"
                )
                assert sec.get("scope") == "consolidated_only", (
                    f"{variant} {number!r} 的 scope={sec.get('scope')!r}，"
                    "母公司章子节应恒为 consolidated_only"
                )
                assert (sec.get("level") or 0) == 2, (
                    f"{variant} {number!r} 的 level={sec.get('level')!r}，期望 2"
                )


# =========================================================================
# Property 22: 无 NoteSectionMap 指向母公司章
# =========================================================================

class TestProperty22NoMapPointsToParentChapter:
    def test_no_note_section_map_references_withdrawn_numbers(
        self, note_section_map_sources
    ):
        all_numbers = [
            n for numbers in WITHDRAWN_ORPHAN_SECTIONS.values() for n in numbers
        ]
        offenders: list[str] = []
        for name, src in note_section_map_sources.items():
            for number in all_numbers:
                if number in src:
                    offenders.append(f"{name} 引用了 {number!r}")
        assert not offenders, (
            "有 *NoteSectionMap.ts 指向母公司章（底稿同步会把合并口径数据写进"
            "母公司章）：\n  " + "\n  ".join(offenders)
        )

    def test_no_map_references_parent_chapter_prefix(self, note_section_map_sources):
        """更宽的一道：任何 `十六、` / `十二、` 章号字面都不许出现。"""
        pattern = re.compile(r"['\"](十六|十二)、[^'\"]{0,24}['\"]")
        offenders: list[str] = []
        for name, src in note_section_map_sources.items():
            for m in pattern.finditer(src):
                offenders.append(f"{name}: {m.group(0)}")
        assert not offenders, (
            "*NoteSectionMap.ts 出现母公司章号字面：\n  " + "\n  ".join(offenders)
        )

    def test_d_cycle_maps_point_to_merged_chapters(self, note_section_map_sources):
        """正向锁死：D 类 7 个 map 必须指向合并章（防被「统一」到母公司章）。"""
        for wp, numbers in D_CYCLE_MERGED_SECTIONS.items():
            fname = f"{wp}NoteSectionMap.ts"
            assert fname in note_section_map_sources, (
                f"{fname} 不在扫描结果里 ⇒ 文件被改名或路径失效，断言会空转"
            )
            src = note_section_map_sources[fname]
            for number in numbers:
                assert number in src, (
                    f"{fname} 未引用合并章 {number!r} ⇒ D 类同步落点可能被改动"
                )


# =========================================================================
# Property 23: 诊断脚本只读，且仓库内不存在删除母公司章的脚本
# =========================================================================


class TestProperty23DiagnoseScriptIsReadOnly:
    """裁决门 B = 只出报告 + 守卫，不删 tracked 数据。

    🔴 变异检验实证：只断言「仓库里不存在 cleanup_* 脚本」**拦不住**「往这份
    诊断脚本里加删除能力」这个变异 —— 删除能力可以长在任何文件里，包括这份
    只读报告脚本自己。故必须对脚本本体做可读性断言。
    """

    def test_diagnose_script_exists(self):
        assert DIAGNOSE_SCRIPT.exists(), (
            f"诊断脚本缺失：{DIAGNOSE_SCRIPT} —— Property 23 的其余断言会空转"
        )

    def test_docstring_declares_read_only(self):
        """模块 docstring 必须显式声明「只读」。

        这是给后续会话的显式契约：看到这行就知道不要给它加写能力。
        """
        src = DIAGNOSE_SCRIPT.read_text(encoding="utf-8")
        head = src[:1500]
        assert "只读" in head, (
            "诊断脚本模块 docstring 未声明「只读」⇒ 后续会话会给它加删除能力"
            "（裁决门 B 已定：不删 tracked 数据）"
        )

    def test_no_mutating_capability_in_code(self):
        """剥注释后不得出现删除 / 写库 / apply 能力。

        🔴 判据落在**剥注释后**的代码上 —— docstring 里会如实写「不提供 --apply」
        这类说明文字，不剥注释会把说明数成真实能力（平台已登记的 stripComments 坑）。
        """
        raw = DIAGNOSE_SCRIPT.read_text(encoding="utf-8")
        code = _strip_py_comments(raw)

        # 反向自检：原文（注释/docstring 里）确实含这些字样，证明剥注释真的生效
        assert any(tok in raw for tok in ("--apply", "删除")), (
            "原始源码里连 '--apply' / '删除' 的说明文字都没有 ⇒ 反向自检失效，"
            "无法证明 _strip_py_comments 起了作用"
        )
        assert "--apply" not in code, (
            "剥注释后仍出现 '--apply' ⇒ 要么真加了该开关，要么剥注释实现失效"
        )

        forbidden = {
            "DELETE FROM": re.compile(r"\bDELETE\s+FROM\b", re.I),
            "UPDATE ... SET": re.compile(r"\bUPDATE\s+\w+\s+SET\b", re.I),
            "db.delete(": re.compile(r"\bdb\.delete\s*\("),
            "session.delete(": re.compile(r"\bsession\.delete\s*\("),
            "--confirm": re.compile(r"--confirm"),
            "sections.pop(": re.compile(r"\bsections\.pop\s*\("),
            "sections.remove(": re.compile(r"\bsections\.remove\s*\("),
            "commit(": re.compile(r"\.commit\s*\("),
        }
        hits = [name for name, pat in forbidden.items() if pat.search(code)]
        assert not hits, (
            "诊断脚本出现了写 / 删能力（裁决门 B = 只出报告，不删 tracked 数据）："
            f"{hits}"
        )

    def test_does_not_write_back_templates(self):
        """唯一允许的写盘目标是 `--out` 报告；不得回写两份模板 JSON。"""
        code = _strip_py_comments(DIAGNOSE_SCRIPT.read_text(encoding="utf-8"))
        for bad in ("write_text", "write_bytes", "json.dump("):
            for m in re.finditer(re.escape(bad), code):
                window = code[max(0, m.start() - 260) : m.start() + 140]
                assert "note_template" not in window, (
                    f"诊断脚本疑似回写模板 JSON（{bad} 附近出现 note_template）"
                )

    def test_script_actually_reads_templates(self):
        """反向自检：脚本确实读了模板 JSON，证明「只读」断言不是在空文件上空转。"""
        code = _strip_py_comments(DIAGNOSE_SCRIPT.read_text(encoding="utf-8"))
        assert "json.loads" in code or "json.load(" in code, (
            "诊断脚本不读 JSON ⇒ 上面的「只读」断言在空文件上也会通过"
        )
        # 路径按 f-string 拼装（`f"note_template_{variant}.json"`），故只断言前缀
        assert "note_template_" in code, "诊断脚本未引用模板文件名"
        assert "read_text" in code, "诊断脚本无读文件行为"

    def test_comment_stripper_self_check(self):
        """`_strip_py_comments` 有效性自检（内联 fixture，不依赖真实文件内容）。"""
        sample = (
            '"""docstring 里提到 --apply 与 DELETE FROM x 都不算能力。"""\n'
            "# 行注释里的 db.delete( 也不算\n"
            "PAT = 'keepme'\n"
            "def f():\n"
            "    return 1\n"
        )
        stripped = _strip_py_comments(sample)
        assert "docstring" not in stripped, "docstring 未被剥除"
        assert "行注释" not in stripped, "行注释未被剥除"
        assert "keepme" in stripped, "字符串字面量被误删（守卫据此仍能抓注入）"


class TestProperty23NoDeletionScriptExists:
    """仓库内不得存在删除「孤儿章」的脚本。"""

    def test_no_cleanup_orphan_script_in_repo(self):
        hits: list[str] = []
        for base in (REPO_ROOT / "backend" / "scripts", REPO_ROOT / "backend" / "app"):
            if not base.exists():
                continue
            for path in base.rglob("*.py"):
                for pat in FORBIDDEN_SCRIPT_PATTERNS:
                    if pat in path.stem:
                        hits.append(str(path.relative_to(REPO_ROOT)))
        assert not hits, (
            "出现了删除「孤儿章」的脚本，而该判断已被实证推翻（这 5 章是母公司章"
            "正当子节，删除会丢 tracked 数据）：\n  " + "\n  ".join(hits)
        )

    def test_no_module_imports_forbidden_cleanup(self):
        """连带禁 import（防脚本改名后仍以别的名字被调用）。"""
        base = REPO_ROOT / "backend"
        hits: list[str] = []
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts or path.name == Path(__file__).name:
                continue
            try:
                src = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for pat in FORBIDDEN_SCRIPT_PATTERNS:
                if f"import {pat}" in src or f"from {pat}" in src:
                    hits.append(f"{path.relative_to(REPO_ROOT)} -> {pat}")
        assert not hits, "存在对已撤回清理脚本的 import：\n  " + "\n  ".join(hits)


# =========================================================================
# 真孤儿的归属登记（只做存在性登记，不在本 spec 处置）
# =========================================================================


class TestRealOrphanCandidatesAreRegisteredElsewhere:
    """按严判据（全部子表名都是表头首格泄漏）实测的真孤儿在别处。

    实测：listed 30 章 / soe 1 章，全在「三、重要会计政策及会计估计」
    「十一、关联方及关联交易」「十二、股份支付」「十四、资产负债表日后事项」
    章下，与 D 循环零交集 ⇒ 归 `note-template-columns-and-legacy-snapshot-closure`
    （C spec，列元数据补齐），本 spec 不补列也不删除。

    本类的作用是把「真孤儿在别处且与母公司章不重叠」这一事实钉住，防后续会话
    把两者混为一谈。
    """

    LEAK_PATTERNS = (
        "种  类", "种 类", "种类", "类 别", "类别", "项  目", "项 目", "项目",
        "单位名称", "承兑人名称", "名  称", "名称", "账  龄", "票据种类",
        "子公司名称", "被购买方名称", "被合并方名称", "分  类", "内  容",
        "转移方式", "债务重组方式", "信用评级", "结构化主体",
        "本期或本期期末", "上期或上期期末", "合营企业或联营",
    )

    def _is_leak(self, name: str) -> bool:
        norm = (name or "").replace("<br/>", "").strip()
        if not norm:
            return True
        return any(p in norm for p in self.LEAK_PATTERNS)

    def _strict_orphans(self, sections: list[dict]) -> list[str]:
        out: list[str] = []
        for sec in sections:
            tables = sec.get("tables") or []
            if not tables:
                continue
            if sec.get("_aligned_by"):
                continue
            if _cols_zero_count(sec) != len(tables):
                continue
            if all(self._is_leak(t.get("name") or "") for t in tables):
                out.append((sec.get("section_number") or "").strip())
        return out

    def test_strict_criteria_actually_matches_something(self, templates):
        """反向自检：严判据在 listed 上必须有命中，否则下面两条断言是空转。"""
        orphans = self._strict_orphans(templates["listed"])
        assert orphans, (
            "严判据在 listed 上零命中 ⇒ 判据实现失效（或 C spec 已全部补齐），"
            "此时下面的「无重叠」断言变成空转，需复核"
        )

    def test_strict_orphans_have_no_overlap_with_d_cycle(self, templates):
        d_numbers = {n for pair in D_CYCLE_MERGED_SECTIONS.values() for n in pair}
        for variant in TEMPLATES:
            orphans = set(self._strict_orphans(templates[variant]))
            overlap = orphans & d_numbers
            assert not overlap, (
                f"{variant}：严判据孤儿与 D 循环合并章重叠 {sorted(overlap)} "
                "⇒ D 类 14 章的列元数据被清空了，属回归"
            )

    def test_strict_orphans_have_no_overlap_with_parent_chapter(self, templates):
        """严判据不命中母公司章 —— 母公司章表名是真实表名不是表头泄漏。"""
        for variant in TEMPLATES:
            orphans = set(self._strict_orphans(templates[variant]))
            withdrawn = set(WITHDRAWN_ORPHAN_SECTIONS[variant])
            overlap = orphans & withdrawn
            assert not overlap, (
                f"{variant}：严判据命中了母公司章 {sorted(overlap)} —— "
                "母公司章的表名是真实表名（如「应收票据」「按账龄披露」），"
                "命中说明判据实现有误"
            )

    def test_d_cycle_merged_sections_have_columns(self, templates):
        """正向锁死：D 类 14 章的列元数据必须齐备（前序 spec 三向对齐的成果）。"""
        for wp, (listed_no, soe_no) in D_CYCLE_MERGED_SECTIONS.items():
            for variant, number in (("listed", listed_no), ("soe", soe_no)):
                hits = _find_sections(templates[variant], number)
                assert len(hits) == 1, f"{variant} {number!r}（{wp}）命中 {len(hits)} 条"
                sec = hits[0]
                tables = sec.get("tables") or []
                assert tables, f"{variant} {number!r}（{wp}）无子表"
                assert _cols_zero_count(sec) == 0, (
                    f"{variant} {number!r}（{wp}）有 {_cols_zero_count(sec)}/"
                    f"{len(tables)} 张子表缺 columns ⇒ 前序对齐成果被回退"
                )
                assert sec.get("_aligned_by"), (
                    f"{variant} {number!r}（{wp}）的 _aligned_by 为空 ⇒ 对齐标记丢失"
                )
