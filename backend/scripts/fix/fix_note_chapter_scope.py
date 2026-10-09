# -*- coding: utf-8 -*-
"""附注模板章节 scope 与 Word 权威模板对齐（幂等，--check / --dry-run / --apply）。

═══ 判据真源 ═══

致同 Word 附注模板本身就分单体 / 合并两套：
``backend/data/audit_report_templates/disclosure_notes/{soe,listed}_{standalone,consolidated}.docx``。
**某个一级章是否出现在单体报告里，只看单体那份 Word 有没有这个 Heading 1。**
本脚本不做任何「按标题猜」的判断 —— 每条目标态都对应一条 Word 实测事实，
并由 ``check_*`` 在运行时**现读 Word** 复核（不是抄一次写死）。

2026-09-30 实测（两份单体 Word 的 Heading 1 与合并 Word 的差集）：

  ==========  ===============================  =========================================
  变体        仅在合并 Word 里的章              JSON 模板对应的章（修复前 scope）
  ==========  ===============================  =========================================
  listed      公司财务报表主要项目注释          十六 母公司财务报表主要项目注释（both）
  soe         企业合并及合并财务报表            七 合并范围的变化（both）
  soe         母公司财务报表的主要项目附注      十二 母公司财务报表的主要项目附注（both）
  ==========  ===============================  =========================================

  反向（在**单体** Word 里存在、JSON 却标成 consolidated_only）：
  listed 十七「补充资料」—— 单体 Word 第 16 章就是它，3 个子标题（非经常性损益 /
  净资产收益率和每股收益 / 境内外会计准则差异）齐全，而 JSON 把 3 个子节全标了
  ``consolidated_only`` ⇒ 单体报告只剩一个空章标题、内容整章丢失。

═══ 缺陷机理（为什么会出现「章 both、子节全 consolidated_only」） ═══

口径过滤 ``note_section_catalog.section_applies_to_scope`` **逐节扁平判定、不继承父章**。
一级章是 ``migrate_note_template_section_id.py``（aab3d49ee 2026-05-28）按章号前缀**合成**的
占位节，硬编码 ``"scope": "both"``（它不知道章的口径）⇒ 子节全隐藏、章自己留下
⇒ 单体附注出现一个没有正文的空章标题。现算两份模板恰好 4 个此形态，
其中 3 个章本该整体隐藏、1 个（补充资料）是子节被错标。

═══ 动作 ═══

* ``CHAPTER_ONLY_IN_CONSOLIDATED``：章本身 + **全部后代**（任意深度）→ ``consolidated_only``
* ``CHAPTER_IN_BOTH``：章的后代里错标 ``consolidated_only`` 的 → ``both``
  （章本身已是 both；只动 scope 一个字段）

写盘保持原文件行尾；序列化 ``indent=2 + ensure_ascii=False + 尾换行``，写前做恒等往返自检。
DB 存量（单体项目里已生成的这些章节行）由
``fix_standalone_consolidated_only.py`` 按**每个项目自己的 template_type** 清理，
不在本脚本（本脚本只动模板，零 DB 依赖，CI 可跑）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA = REPO_ROOT / "backend" / "data"
DOCX_DIR = DATA / "audit_report_templates" / "disclosure_notes"
TEMPLATES = {v: DATA / f"note_template_{v}.json" for v in ("listed", "soe")}

#: (变体, JSON 一级章 section_number) -> 该章在 Word 里的 Heading 1（去空白后）。
#: 只在**合并** Word 出现、单体 Word 没有 ⇒ 章 + 全部后代 consolidated_only。
CHAPTER_ONLY_IN_CONSOLIDATED: dict[tuple[str, str], str] = {
    ("listed", "十六"): "公司财务报表主要项目注释",
    ("soe", "七"): "企业合并及合并财务报表",
    ("soe", "十二"): "母公司财务报表的主要项目附注",
}

#: 在**单体与合并** Word 都出现 ⇒ 后代里错标 consolidated_only 的改回 both。
CHAPTER_IN_BOTH: dict[tuple[str, str], str] = {
    ("listed", "十七"): "补充资料",
}


# ─────────────────────────── Word 事实（现读，不写死） ───────────────────────────

def _norm(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "")


_HEADING_RE = re.compile(r"^(?:heading|标题)\s*(\d)$", re.IGNORECASE)
_OUTLINE_CACHE: dict[tuple[str, str], list[tuple[int, str]]] = {}


def word_outline(variant: str, report_scope: str) -> list[tuple[int, str]]:
    """读 ``{variant}_{report_scope}.docx`` 的标题大纲 ``[(级别, 去空白文本), ...]``。"""
    key = (variant, report_scope)
    if key in _OUTLINE_CACHE:
        return _OUTLINE_CACHE[key]
    import docx  # python-docx，已是后端依赖

    path = DOCX_DIR / f"{variant}_{report_scope}.docx"
    if not path.is_file():
        raise FileNotFoundError(f"Word 权威模板缺失：{path}（判据真源不存在必须失败，禁跳过）")
    out: list[tuple[int, str]] = []
    for p in docx.Document(str(path)).paragraphs:
        style = ((p.style.name if p.style is not None else "") or "").strip()
        m = _HEADING_RE.match(style)
        if m:
            out.append((int(m.group(1)), _norm(p.text)))
    _OUTLINE_CACHE[key] = out
    return out


def word_heading1(variant: str, report_scope: str) -> list[str]:
    return [t for lv, t in word_outline(variant, report_scope) if lv == 1]


def word_subheadings(variant: str, report_scope: str, h1: str) -> list[str]:
    """``h1`` 这一章下面的全部下级标题（直到下一个 Heading 1）。"""
    out: list[str] = []
    inside = False
    for lv, text in word_outline(variant, report_scope):
        if lv == 1:
            inside = text == h1
            continue
        if inside:
            out.append(text)
    return out


def _child_title_hits(children: list[dict[str, Any]], subs: list[str]) -> tuple[int, int]:
    """JSON 子节标题有几个能在 Word 下级标题里找到（互为子串即算，容括注差异）。"""
    titles = [_norm(c.get("section_title")) for c in children if _norm(c.get("section_title"))]
    hits = sum(1 for t in titles if any(t in s or s in t for s in subs if s))
    return hits, len(titles)


def check_word_facts() -> list[str]:
    """复核两张登记表的每一条都还被 Word 支持（Word 一改即打红，防登记表过期）。

    两层：① 该 Heading 1 在单体/合并 Word 里的有无，符合登记的归类；
    ② **JSON 章 ↔ Word 章的对应关系本身**：JSON 章的子节标题须过半能在该 Word 章的
    下级标题里找到。第 ② 条防的是「章号对上了、但对的是另一章」—— 例如 soe 七 JSON 标题
    是「合并范围的变化」而 Word 是「企业合并及合并财务报表」，标题不同，只有子节能证明是同一章。
    """
    errs: list[str] = []
    for table, kind in ((CHAPTER_ONLY_IN_CONSOLIDATED, "consolidated_only"),
                        (CHAPTER_IN_BOTH, "both")):
        for (variant, num), h1 in table.items():
            cons, stand = word_heading1(variant, "consolidated"), word_heading1(variant, "standalone")
            if kind == "consolidated_only":
                if h1 not in cons:
                    errs.append(f"[{variant}] {num}: 合并 Word 里找不到 Heading 1「{h1}」")
                if h1 in stand:
                    errs.append(f"[{variant}] {num}: 单体 Word 里**有**「{h1}」⇒ 不该整章 consolidated_only")
            elif h1 not in cons or h1 not in stand:
                errs.append(f"[{variant}] {num}: 「{h1}」应同时在单体与合并 Word 出现"
                            f"（合并={h1 in cons} 单体={h1 in stand}）")
            doc = json.loads(TEMPLATES[variant].read_text(encoding="utf-8"))
            sections = doc.get("sections") or []
            ch = _chapter(sections, num)
            if ch is None:
                errs.append(f"[{variant}] JSON 里找不到一级章「{num}」")
                continue
            kids = [s for s in sections if s.get("parent_section_id") == ch["section_id"]]
            hits, total = _child_title_hits(kids, word_subheadings(variant, "consolidated", h1))
            if total == 0 or hits * 2 < total:
                errs.append(f"[{variant}] JSON 章「{num}」的子节只有 {hits}/{total} 能在 Word 章"
                            f"「{h1}」下找到 ⇒ 两者可能不是同一章，登记需重判")
    return errs


# ─────────────────────────── 模板结构 ───────────────────────────

def _chapter(sections: list[dict[str, Any]], num: str) -> dict[str, Any] | None:
    return next(
        (s for s in sections if s.get("level") == 1 and s.get("section_number") == num), None
    )


def descendants(sections: list[dict[str, Any]], root_id: str) -> list[dict[str, Any]]:
    """任意深度后代（按 parent_section_id 展开）。"""
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for s in sections:
        by_parent.setdefault(s.get("parent_section_id"), []).append(s)
    out: list[dict[str, Any]] = []
    stack = [root_id]
    while stack:
        for child in by_parent.get(stack.pop(), []):
            out.append(child)
            stack.append(child["section_id"])
    return out


def _scope(s: dict[str, Any]) -> str:
    return (s.get("scope") or "both").strip()


def plan(doc: dict[str, Any], variant: str) -> tuple[list[tuple[dict, str, str]], list[str]]:
    """返回 (待改清单 [(节, 旧 scope, 新 scope)], 结构错误)。纯函数，不改 doc。"""
    sections = doc.get("sections") or []
    todo: list[tuple[dict, str, str]] = []
    errs: list[str] = []
    for table, target in ((CHAPTER_ONLY_IN_CONSOLIDATED, "consolidated_only"),
                          (CHAPTER_IN_BOTH, "both")):
        for (v, num), _h1 in table.items():
            if v != variant:
                continue
            ch = _chapter(sections, num)
            if ch is None:
                errs.append(f"[{variant}] 找不到一级章「{num}」")
                continue
            kids = descendants(sections, ch["section_id"])
            if not kids:
                errs.append(f"[{variant}] 章「{num}」没有任何子节（结构异常，拒绝改动）")
                continue
            if target == "consolidated_only":
                for s in [ch, *kids]:
                    if _scope(s) != "consolidated_only":
                        todo.append((s, _scope(s), "consolidated_only"))
            else:
                for s in kids:
                    if _scope(s) == "consolidated_only":
                        todo.append((s, "consolidated_only", "both"))
    return todo, errs


def check_invariants(doc: dict[str, Any], variant: str) -> list[str]:
    """通用不变量（与登记表无关，任何章都适用）。

    1. **不得出现「节自身可见、后代全部 consolidated_only」** —— 那就是单体报告里的空章标题。
       只有节**自己带表**时豁免（单体里仍有表可显示）。自己的 ``text_sections`` **不**豁免：
       后代全是合并口径时，章首正文也是合并语境（实测 soe 十二的 5 段章首说明开头就是
       「对已编制合并财务报表的企业…」），不能据此让空壳章留在单体里。
    2. **consolidated_only 的节下面不得挂可见节**（父隐藏、子可见 = 孤儿子节）。
    """
    sections = doc.get("sections") or []
    by_id = {s.get("section_id"): s for s in sections}
    errs: list[str] = []
    for s in sections:
        kids = descendants(sections, s["section_id"])
        if not kids or _scope(s) == "consolidated_only":
            continue
        if all(_scope(k) == "consolidated_only" for k in kids) and not s.get("tables"):
            errs.append(
                f"[{variant}] 「{s.get('section_number')} {s.get('section_title')}」scope="
                f"{_scope(s)!r} 但 {len(kids)} 个后代全是 consolidated_only ⇒ 单体报告出空章标题"
            )
    for s in sections:
        p = by_id.get(s.get("parent_section_id"))
        while p is not None:
            if _scope(p) == "consolidated_only" and _scope(s) != "consolidated_only":
                errs.append(
                    f"[{variant}] 「{s.get('section_number')}」scope={_scope(s)!r} 挂在 "
                    f"consolidated_only 的「{p.get('section_number')}」下 ⇒ 单体里成孤儿子节"
                )
                break
            p = by_id.get(p.get("parent_section_id"))
    return errs


def _dump(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def run_variant(variant: str, *, apply: bool) -> tuple[list[str], list[str]]:
    path = TEMPLATES[variant]
    raw_bytes = path.read_bytes()
    raw = raw_bytes.decode("utf-8").replace("\r\n", "\n")
    doc = json.loads(raw)
    todo, errs = plan(doc, variant)
    changes = [
        f"[{variant}] {s.get('section_number')} {s.get('section_title')}: scope {old!r} → {new!r}"
        for s, old, new in todo
    ]
    if apply and todo and not errs:
        if _dump(json.loads(raw)).rstrip("\n") != raw.rstrip("\n"):
            raise SystemExit(f"[ERR] {path.name} 恒等往返自检失败（序列化形态不一致），拒绝写盘")
        for s, _old, new in todo:
            s["scope"] = new
        text = _dump(doc)
        data = text.encode("utf-8")
        if b"\r\n" in raw_bytes:
            data = data.replace(b"\n", b"\r\n")
        path.write_bytes(data)
    return changes, errs


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--apply", action="store_true", help="写入模板")
    grp.add_argument("--check", action="store_true", help="有欠账则 exit 1（CI 用）")
    ap.add_argument("--dry-run", action="store_true", help="只打印（默认）")
    args = ap.parse_args()

    word_errs = check_word_facts()
    for e in word_errs:
        print(f"  x Word 事实不再支持登记：{e}")

    total_changes = total_errs = 0
    for variant in TEMPLATES:
        changes, errs = run_variant(variant, apply=args.apply)
        for c in changes:
            print(f"  ~ {c}")
        for e in errs:
            print(f"  x {e}")
        total_changes += len(changes)
        total_errs += len(errs)

    inv = []
    for variant, path in TEMPLATES.items():
        inv += check_invariants(json.loads(path.read_text(encoding="utf-8")), variant)
    if args.apply or args.check:
        for e in inv:
            print(f"  x 不变量：{e}")

    mode = "apply" if args.apply else ("check" if args.check else "dry-run")
    pending = 0 if args.apply else total_changes
    debt = pending + total_errs + len(word_errs) + (len(inv) if (args.apply or args.check) else 0)
    print(f"[{mode}] 变更 {total_changes} 处，欠账 {debt} 项")
    if args.check:
        return 1 if debt else 0
    return 1 if (total_errs or word_errs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
