"""按四版 Word 修复附注种子 JSON 的章节树（可重跑）。

spec: disclosure-note-template-word-realignment Task 4 / 5（design §3.1 / §3.2）

改动：章名（口径不同时 ``scope_titles``）与章 scope；放错章的节改挂到 Word 所在章、编号换章号（旧编号进
``legacy_section_numbers``，``section_id`` 不变）；节标题（截断 / 措辞，旧标题进 ``legacy_titles``）；节 scope
（按单体 / 合并两版 Word 是否出现）；补 Word 有、种子无的节；提示语误做成的章首节改为章正文叶子；章内顺序按 Word 重排。
表格不在本脚本（design §3.3）。

用法（仓库根执行）：
    python backend/scripts/seed/realign_note_templates_to_word.py           # 预演：列出将做的改动
    python backend/scripts/seed/realign_note_templates_to_word.py --write   # 写回两份种子
    python backend/scripts/seed/realign_note_templates_to_word.py --check   # 有待改项 exit 2

写回后再跑应无改动；并发会话也在改种子，运行前先看 ``git status``，改完立即提交。
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts" / "migrate"))

from migrate_note_template_section_id import _kebab, _make_unique  # noqa: E402

from app.services.note_section_catalog import clear_template_caches, template_json_path  # noqa: E402
from app.services.note_word_tree import (  # noqa: E402
    ALLOWLIST_PATH,
    SeedChapter,
    SeedSection,
    VariantMatch,
    split_title_hint,
    WordSection,
    clean_word_heading,
    match_all,
)

ALIGNED_BY = "disclosure-note-template-word-realignment"


def _scope_from(presence: set[str]) -> str:
    if presence >= {"standalone", "consolidated"}:
        return "both"
    return "consolidated_only" if "consolidated" in presence else "standalone_only"


def _seed_title(word_title: str) -> str:
    """种子标题 = Word 标题去尾部括注（括注是给编制人的提示，另存 ``title_hint``，见 ``split_title_hint``）。"""
    return split_title_hint(clean_word_heading(word_title))[0] or clean_word_heading(word_title)


def _word_hint(word_title: str) -> str | None:
    return split_title_hint(clean_word_heading(word_title))[1]


def _set_hint(raw: dict[str, Any], hint: str | None, changes: list[str]) -> None:
    """``title_hint`` = 标题尾部括注里的提示；Word 本次未带提示时保留既有来源的提示。"""
    if not hint or raw.get("title_hint") == hint:
        return
    changes.append(f"标题提示 {raw.get('section_number')}：{raw.get('title_hint')!r} → {hint!r}")
    raw["title_hint"] = hint


def _rename(raw: dict[str, Any], new_title: str, changes: list[str], what: str) -> None:
    old = raw.get("section_title") or ""
    if old == new_title:
        return
    raw.setdefault("legacy_titles", [])
    if old and old not in raw["legacy_titles"]:
        raw["legacy_titles"].append(old)
    raw["section_title"] = new_title
    if raw.get("account_name") == old:
        raw["account_name"] = new_title
    changes.append(f"{what} {raw.get('section_number')}：「{old}」→「{new_title}」")


def _allowed(std: str) -> set[tuple[str, str]]:
    """白名单里本准则的（差异类别, 键）：这些差异有意保留，修复器不动（理由见白名单文件）。"""
    if not ALLOWLIST_PATH.exists():
        return set()
    return {(e["kind"], e["key"]) for e in json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
            if str(e.get("variant", "")).startswith(f"{std}_")}


def _fix_chapters(matches: dict[str, VariantMatch], chapters: list[SeedChapter], changes: list[str],
                  allowed: set[tuple[str, str]] = frozenset()) -> None:
    """章名（以合并版为准，单体版不同则记 scope_titles）、章 scope；章正文叶子随章改名。"""
    titles: dict[str, dict[str, str]] = defaultdict(dict)
    hints: dict[str, dict[str, str]] = defaultdict(dict)
    for m in matches.values():
        for idx, sc in m.chapter_pairs.items():
            word_title = m.word.chapters[idx - 1].title
            titles[sc.code][m.report_scope] = _seed_title(word_title)
            if hint := _word_hint(word_title):
                hints[sc.code][m.report_scope] = hint
    for sc in chapters:
        by_hint = hints.get(sc.code) or {}
        _set_hint(sc.raw, by_hint.get("consolidated") or by_hint.get("standalone")
                  or split_title_hint(sc.raw.get("section_title") or "")[1], changes)
        by_scope = titles.get(sc.code)
        if not by_scope:
            changes.append(f"[未处理] 章 {sc.code}「{sc.title}」两版 Word 都没有")
            continue
        raw = sc.raw
        scope = _scope_from(set(by_scope))
        if raw.get("scope") != scope:
            changes.append(f"章 scope {sc.code}：{raw.get('scope')} → {scope}")
            raw["scope"] = scope
        if ("chapter_title", sc.code) in allowed:
            continue
        base = by_scope.get("consolidated") or by_scope["standalone"]
        old = raw.get("section_title") or ""
        if base != old:
            for s in sc.sections:  # 章正文叶子「X、1 章名」随章改名
                if (s.raw.get("section_title") or "") == old:
                    _rename(s.raw, base, changes, "章正文叶子")
            _rename(raw, base, changes, "章名")
        standalone = by_scope.get("standalone")
        wanted = {"standalone": standalone} if standalone and standalone != base else None
        if raw.get("scope_titles") != wanted:
            changes.append(f"章 {sc.code} 口径章名：{raw.get('scope_titles')} → {wanted}")
            if wanted:
                raw["scope_titles"] = wanted
            else:
                raw.pop("scope_titles", None)


def _presence(matches: dict[str, VariantMatch]) -> tuple[
        dict[int, set[str]], dict[int, set[str]], dict[int, dict[str, str]], dict[int, dict[str, str]]]:
    """（种子节位置 → 出现的口径，→ 应改挂的种子章，→ 各口径 Word 标题〔标题不同或种子标题带括注时〕，→ 各口径标题提示）。"""
    presence: dict[int, set[str]] = defaultdict(set)
    targets: dict[int, set[str]] = defaultdict(set)
    titles: dict[int, dict[str, str]] = defaultdict(dict)
    hints: dict[int, dict[str, str]] = defaultdict(dict)
    for m in matches.values():
        by_pos = m.sections_by_position()
        for pos, (wc, ws) in m.matches.items():
            presence[pos].add(m.report_scope)
            target = m.chapter_pairs.get(wc.index)
            if target is not None and target.code != by_pos[pos].chapter_code:
                targets[pos].add(target.code)
            if ws.norm != by_pos[pos].norm or split_title_hint(by_pos[pos].title)[1]:
                titles[pos][m.report_scope] = _seed_title(ws.title)
            if hint := _word_hint(ws.title):
                hints[pos][m.report_scope] = hint
        for pos in m.body_leaves:
            presence[pos].add(m.report_scope)
    return presence, targets, titles, hints


def _all_codes(sections: list[dict[str, Any]]) -> set[str]:
    out = {s["section_number"] for s in sections}
    return out | {old for s in sections for old in s.get("legacy_section_numbers") or []}


class _Codes:
    """新编号分配：目标章现有编号全是数字 ⇒ 取最大数字 + 1；否则保留「、」后部分只换章号（冲突加「（2）」）。

    「已用」= 现行编号 ∪ 全部旧编号别名（旧编号不再分配，免得指向两节）。国企「五」章不分配数字编号：
    数字 ``五、N`` 是旧国企科目编号，会被 ``normalize_section_code`` 归一到 ``八、N``。
    """

    def __init__(self, std: str, sections: list[dict[str, Any]], other_sections: list[dict[str, Any]]):
        self.std = std
        self.used = _all_codes(sections)
        self.other = _all_codes(other_sections)

    def _top(self, chapter_code: str) -> int:
        pattern = re.compile(rf"{re.escape(chapter_code)}、(\d+)")
        return max((int(m.group(1)) for c in self.used if (m := pattern.fullmatch(c))), default=0)

    def numeric_style(self, chapter_code: str, child_codes: list[str], count: int) -> bool:
        """目标章现有编号全是数字，且要分配的数字编号在另一准则里都没被用过。

        🔴 绑定 / 公式 / 列规则等数据文件只按编号作键、不分准则：上市「八」章若取「八、2」~「八、6」，
        会与国企「八、2」（交易性金融资产）等同号不同义而互相覆盖（2026-10-16 首轮实测：绑定生成后
        上市「八、5」把国企「八、5 应收账款」挤掉）。撞号时整章改用标题式编号。
        """
        if self.std == "soe" and chapter_code == "五":
            return False
        pattern = re.compile(rf"{re.escape(chapter_code)}、\d+")
        if not child_codes or not all(pattern.fullmatch(c) for c in child_codes):
            return False
        top = self._top(chapter_code)
        return not any(f"{chapter_code}、{top + k}" in self.other for k in range(1, count + 1))

    def numeric(self, chapter_code: str) -> str:
        code = f"{chapter_code}、{self._top(chapter_code) + 1}"
        assert code not in self.other, code
        self.used.add(code)
        return code

    def titled(self, chapter_code: str, rest: str) -> str:
        code, k = f"{chapter_code}、{rest}", 2
        while code in self.used:
            code, k = f"{chapter_code}、{rest}（{k}）", k + 1
        self.used.add(code)
        return code


def _word_index(matches: dict[str, VariantMatch], std: str, chapter_code: str, norm: str) -> tuple[int, int]:
    """节在目标章 Word 中的位置（先看合并版，再看单体版），用于按 Word 顺序分配编号。"""
    for rank, variant in enumerate((f"{std}_consolidated", f"{std}_standalone")):
        m = matches[variant]
        idx = next((i for i, c in m.chapter_pairs.items() if c.code == chapter_code), None)
        if idx is None:
            continue
        for k, ws in enumerate(m.word.chapters[idx - 1].sections):
            if ws.norm == norm:
                return rank, k
    return 9, 0


def _text_sections(ws: WordSection) -> list[str]:
    """补节正文：Word 节内段落原文，小标题按层级写成 ``#`` 标题行（与种子既有写法一致）。"""
    return [text if level is None else f"{'#' * level} {text}" for level, text in ws.blocks]


def realign(std: str, data: dict[str, Any], other: dict[str, Any] | None = None) -> list[str]:
    """就地修复一份种子 dict 的章节树，返回改动说明（空 = 已对齐）。

    ``other`` = 另一准则的种子（新编号避开它的编号；缺省读盘上文件）。
    """
    if other is None:
        other = json.loads(template_json_path("listed" if std == "soe" else "soe").read_text(encoding="utf-8"))
    changes: list[str] = []
    matches = match_all(seeds={std: data}, variants=(f"{std}_standalone", f"{std}_consolidated"))
    chapters = matches[f"{std}_consolidated"].chapters
    by_pos: dict[int, SeedSection] = {s.position: s for c in chapters for s in c.sections}
    chapter_by_code = {c.code: c for c in chapters}

    allowed = _allowed(std)
    _fix_chapters(matches, chapters, changes, allowed)
    presence, targets, titles, hints = _presence(matches)
    leaf_positions = {pos for m in matches.values() for pos in m.body_leaves}
    # 标题提示：Word 标题尾部括注为准；Word 没有、种子标题自带的括注（旧 md 来源）也保留成提示，不丢
    for pos, s in by_pos.items():
        word = hints.get(pos) or {}
        _set_hint(s.raw, word.get("consolidated") or word.get("standalone") or split_title_hint(s.title)[1], changes)

    for sc in chapters:  # 提示语误做成的章首节（「九、【企业应当…」）⇒ 章正文叶子
        first = sc.sections[0] if sc.sections else None
        if first and first.title.strip().startswith("【") and first.position not in presence:
            _rename(first.raw, sc.raw["section_title"], changes, "提示语节改为章正文叶子")
            leaf_positions.add(first.position)
            presence[first.position] = {"consolidated", "standalone"} if sc.raw.get("scope") == "both" else (
                {"consolidated"} if sc.raw.get("scope") == "consolidated_only" else {"standalone"})

    for pos, wanted in titles.items():
        if pos not in leaf_positions and ("section_title", by_pos[pos].key) not in allowed:
            _rename(by_pos[pos].raw, wanted.get("consolidated") or wanted["standalone"], changes, "节标题")
    for pos, scopes in presence.items():
        raw, scope = by_pos[pos].raw, _scope_from(scopes)
        if raw.get("scope") != scope:
            changes.append(f"节 scope {raw['section_number']}：{raw.get('scope')} → {scope}")
            raw["scope"] = scope

    conflicts = {pos: t for pos, t in targets.items() if len(t) > 1}
    if conflicts:
        raise SystemExit(f"两版 Word 对同一节给出不同的章：{ {by_pos[p].key: sorted(t) for p, t in conflicts.items()} }")
    moves = {pos: next(iter(t)) for pos, t in targets.items()}
    additions = _collect_additions(matches, std)
    _assign_codes(std, data, chapter_by_code, by_pos, moves, additions, matches, changes, other["sections"])
    _reorder(std, data, chapters, matches, set(moves), additions, leaf_positions, changes)
    return changes


def _collect_additions(matches: dict[str, VariantMatch], std: str) -> dict[tuple[str, str], dict[str, Any]]:
    """Word 有、种子无的节：（种子章编号, 标题键）→ 待建节（出现的口径 + Word 节）。"""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for variant in (f"{std}_consolidated", f"{std}_standalone"):
        m = matches[variant]
        for wc, ws in m.word_unmatched:
            sc = m.chapter_pairs.get(wc.index)
            if sc is None or not ws.norm:
                continue
            item = out.setdefault((sc.code, ws.norm), {"ws": ws, "chapter": sc, "presence": set(), "raw": None})
            item["presence"].add(m.report_scope)
    return out


def _assign_codes(std: str, data: dict[str, Any], chapter_by_code: dict[str, SeedChapter],
                  by_pos: dict[int, SeedSection], moves: dict[int, str],
                  additions: dict[tuple[str, str], dict[str, Any]], matches: dict[str, VariantMatch],
                  changes: list[str], other_sections: list[dict[str, Any]]) -> None:
    """放错章的节与补入的节：按目标章 Word 顺序分配新编号；改挂父节点；旧编号进别名。"""
    codes = _Codes(std, data["sections"], other_sections)
    used_ids = {s.get("section_id") for s in data["sections"] if s.get("section_id")}
    per_chapter: dict[str, list[tuple[tuple[int, int], str, Any]]] = defaultdict(list)
    for pos, target in moves.items():
        s = by_pos[pos]
        per_chapter[target].append((_word_index(matches, std, target, s.norm), "move", s))
    for (target, norm), item in additions.items():
        per_chapter[target].append((_word_index(matches, std, target, norm), "add", item))
    for target, items in per_chapter.items():
        chapter = chapter_by_code[target]
        child_codes = [s.code for s in chapter.sections if s.position not in moves]
        numeric = codes.numeric_style(target, child_codes, len(items))
        for _order, kind, obj in sorted(items, key=lambda x: x[0]):
            if kind == "move":
                raw, old = obj.raw, obj.code
                rest = old.split("、", 1)[1] if "、" in old else obj.title
                new = codes.numeric(target) if numeric else codes.titled(target, rest)
                raw.setdefault("legacy_section_numbers", [])
                if old not in raw["legacy_section_numbers"]:
                    raw["legacy_section_numbers"].append(old)
                raw["section_number"] = new
                raw["parent_section_id"] = chapter.raw["section_id"]
                changes.append(f"改挂 {old} → {new}（{chapter.raw['section_title']}）")
                continue
            ws = obj["ws"]
            title = _seed_title(ws.title)
            new = codes.numeric(target) if numeric else codes.titled(target, title)
            sid = _make_unique(f"{chapter.raw['section_id']}-{_kebab(title)}"[:95].rstrip("-"), used_ids)
            used_ids.add(sid)
            obj["raw"] = {
                "section_number": new, "section_title": title, "account_name": title,
                "content_type": "mixed" if ws.tables else "text", "check_presets": [], "wide_table_presets": [],
                "scope": _scope_from(obj["presence"]), "sort_order": 0, "section_id": sid, "level": 2,
                "parent_section_id": chapter.raw["section_id"], "sort_index": 0,
                "auto_numbering": True, "lock_number": False, "tables": [], "text_sections": _text_sections(ws),
                "_aligned_by": ALIGNED_BY,
            }
            if hint := _word_hint(ws.title):
                obj["raw"]["title_hint"] = hint
            if ws.tables:
                changes.append(f"[待表格口径] 补节 {new} Word 有 {len(ws.tables)} 张表，本脚本只建节不建表")
            changes.append(f"补节 {new}「{title}」（{obj['raw']['scope']}）")


def _insert_after(items: list[dict], prev: dict | None, raw: dict) -> None:
    for k, x in enumerate(items):
        if prev is not None and x is prev:
            items.insert(k + 1, raw)
            return
    items.append(raw)


def _reorder(std: str, data: dict[str, Any], chapters: list[SeedChapter], matches: dict[str, VariantMatch],
             moved: set[int], additions: dict[tuple[str, str], dict[str, Any]], leaf_positions: set[int],
             changes: list[str]) -> None:
    """章内顺序：章正文叶子在前，其余按 Word（先合并版、再补单体版独有）排；Word 没有的节跟在原前一节之后。

    重写 ``sort_order``（第 i 章 = i×100−1，其第 j 个子节 = i×100+j）与 ``sort_index``，文件顺序同排序。
    """
    before = {id(s): (s.get("parent_section_id"), s.get("sort_order"), s.get("sort_index")) for s in data["sections"]}
    placed: set[int] = set()
    layout: list[tuple[dict, list[dict]]] = []
    for sc in chapters:
        items: list[dict] = []
        for s in sc.sections:
            if s.position in leaf_positions and s.position not in moved:
                items.append(s.raw)
                placed.add(id(s.raw))
        for variant in (f"{std}_consolidated", f"{std}_standalone"):
            m = matches[variant]
            idx = next((i for i, c in m.chapter_pairs.items() if c.code == sc.code), None)
            if idx is None:
                continue
            pos_of = {id(ws): pos for pos, (_wc, ws) in m.matches.items()}
            by_pos = m.sections_by_position()
            prev: dict | None = None
            for ws in m.word.chapters[idx - 1].sections:
                if id(ws) in pos_of:
                    raw = by_pos[pos_of[id(ws)]].raw
                else:
                    raw = (additions.get((sc.code, ws.norm)) or {}).get("raw")
                if raw is None:
                    continue
                if id(raw) not in placed:
                    _insert_after(items, prev, raw)
                    placed.add(id(raw))
                prev = raw
        prev = None
        for s in sc.sections:  # Word 里没有、仍留在本章的节：跟在原前一节之后
            if s.position in moved:
                continue
            if id(s.raw) not in placed:
                _insert_after(items, prev, s.raw)
                placed.add(id(s.raw))
            prev = s.raw
        layout.append((sc.raw, items))
    sections: list[dict] = []
    for i, (chapter, items) in enumerate(layout, 1):
        chapter["sort_order"], chapter["sort_index"] = i * 100 - 1, i
        sections.append(chapter)
        if len(items) >= 100:
            raise SystemExit(f"章 {chapter['section_number']} 子节 {len(items)} 个，超出 sort_order 每章 100 位的约定")
        for j, raw in enumerate(items):
            raw["parent_section_id"], raw["level"] = chapter["section_id"], 2
            raw["sort_order"], raw["sort_index"] = i * 100 + j, j
            sections.append(raw)
    lost = [s.get("section_number") for s in data["sections"] if not any(s is x for x in sections)]
    if lost:
        raise SystemExit(f"重排后丢节：{lost}")
    moved_n = sum(1 for s in sections if id(s) in before and before[id(s)] != (
        s.get("parent_section_id"), s.get("sort_order"), s.get("sort_index")))
    if moved_n:
        changes.append(f"重排：{moved_n} 节的父节点 / 排序字段改变")
    data["sections"] = sections


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按四版 Word 修复附注种子 JSON 的章节树")
    parser.add_argument("--std", choices=("soe", "listed"), action="append", help="只处理指定准则（可重复）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="写回种子文件")
    mode.add_argument("--check", action="store_true", help="有待改项 exit 2（不写）")
    args = parser.parse_args(argv)

    pending = 0
    originals = {std: template_json_path(std).read_text(encoding="utf-8") for std in ("soe", "listed")}
    works = {std: copy.deepcopy(json.loads(text)) for std, text in originals.items()}
    for std in args.std or ("soe", "listed"):
        path = template_json_path(std)
        original, work = originals[std], works[std]
        changes = realign(std, work, works["listed" if std == "soe" else "soe"])  # 另一准则用内存中的最新版
        differs = _dump(work) != original  # 以「写回后文本是否不同」为准
        print(f"== {std}：{len(changes)} 项改动{'（文件将变化）' if differs else '（文件不变）'}")
        for line in changes:
            print(f"  {line}")
        if differs:
            pending += 1
            if args.write:
                path.write_text(_dump(work), encoding="utf-8")
                clear_template_caches()
                print(f"  [written] {path.relative_to(BACKEND.parent)}")
    if args.check and pending:
        print(f"🔴 --check：{pending} 份种子与四版 Word 的章节树不一致，请运行 --write")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
