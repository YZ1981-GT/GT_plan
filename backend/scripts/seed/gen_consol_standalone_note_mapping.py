"""生成合并附注 section_id → 单体附注 note_section 映射配置文件。

用法：
  python scripts/seed/gen_consol_standalone_note_mapping.py
  python scripts/seed/gen_consol_standalone_note_mapping.py --dry-run

输出：backend/data/consol_note_section_mapping.json

映射逻辑（逐张合并表）：
1. 表标题 = 单体模板某张子表的表名（规范化口径与运行时读取层 ``_table_key`` 同源）→
   该子表所在单体章节（主章节优先：soe 八、/ listed 五、）。match_type=table_title
2. 「续：」类泛标题跟随同一合并章节上一张表：取单体同章节里紧随其后的续表。match_type=continuation
3. 其余表取同一合并章节（五-N）里表标题命中最多的单体章节，子表名留空。match_type=chapter
4. 整个合并章节都没有表标题命中：按 parent_section（中文科目名）匹配单体 section_title
   （精确 → 规范化 → 前缀）。match_type=exact / normed / fuzzy
5. 仍未匹配的标为 consol_only（合并特有章节，无单体对应）

⚠ 合并模板 ``parent_section`` 自 五-10 起整体错后一章（如 五-11「合同资产」表的 parent 是
「存货」），只按 parent_section 映射会把合同资产拉成存货 —— 所以表标题优先，parent 兜底。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))

from app.services.consol_note_standalone_reader import _table_key  # noqa: E402  与运行时同口径

# ─── 规范化函数（与 consol_note_formula_service.label_key 同源） ──────────

_WS = re.compile(r"[\s\u3000]+")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
# 去行首序号/标记（△ * 减： 其中：等）——与 consol_elimination_sheet_service.clean_row_name 同源
_PREFIX = re.compile(r"^[△*＊·•\s]*(\d+[.、．]?\s*)?")
_MARK = re.compile(r"^(减：|减:|加：|加:|其中：|其中:)")


def _norm(text: str) -> str:
    """去空白、HTML 标签、行首序号/标记。"""
    s = _BR.sub("", str(text or ""))
    s = _WS.sub("", s)
    s = _PREFIX.sub("", s)
    s = _MARK.sub("", s)
    return s.strip()


def _load_json(path: Path) -> list | dict:
    return json.loads(path.read_text(encoding="utf-8"))


#: 单体附注主章节（报表项目注释）：同名子表出现在多章时取它（母公司报表注释等不覆盖）
_MAIN_CHAPTER = {"soe": "八", "listed": "五"}


def _is_generic_continuation(title: str) -> bool:
    """「续：」这类只表示接上一张表的泛标题。"""
    return _norm(title).rstrip(":：") in ("续", "")


def _is_continuation_name(name: str) -> bool:
    return "续" in _table_key(name)


def generate(template_type: str) -> tuple[list[dict], Counter]:
    # 合并模板
    consol_path = DATA / f"consol_note_sections_{template_type}.json"
    consol_tables = _load_json(consol_path)
    if not isinstance(consol_tables, list):
        consol_tables = []

    # 单体模板
    single_path = DATA / f"note_template_{template_type}.json"
    single_data = _load_json(single_path)
    single_sections = single_data.get("sections", []) if isinstance(single_data, dict) else []
    # 只取有表格的章节；主章节优先，其余按文档顺序
    main = _MAIN_CHAPTER.get(template_type, "八")
    sorted_singles = sorted(
        (s for s in single_sections if s.get("tables")),
        key=lambda s: (0 if str(s.get("section_number", "")).startswith(main) else 1, s.get("sort_order", 9999)),
    )

    # 子表名索引：规范化表名 → [(单体章节, 子表名)]（主章节在前）
    by_table: dict[str, list[tuple[dict, str]]] = {}
    for s in sorted_singles:
        for t in s.get("tables") or []:
            key = _table_key(t.get("name"))
            if key and not _is_generic_continuation(t.get("name", "")):
                by_table.setdefault(key, []).append((s, t.get("name")))

    # 按 section_title 索引单体（精确 + 规范化两份索引）——合并章节没有任何表标题命中时兜底
    single_exact: dict[str, dict] = {}
    single_normed: dict[str, dict] = {}
    for s in sorted_singles:
        title = s.get("section_title", "")
        if title:
            # 八章优先：如果已有八章的映射，不被十章等覆盖
            if title not in single_exact:
                single_exact[title] = s
            normed_title = _norm(title)
            if normed_title not in single_normed:
                single_normed[normed_title] = s
        # 也按 account_name 索引
        acct = s.get("account_name", "")
        if acct and acct != title:
            if acct not in single_exact:
                single_exact[acct] = s
            normed_acct = _norm(acct)
            if normed_acct not in single_normed:
                single_normed[normed_acct] = s

    def _by_parent(parent: str) -> tuple[dict | None, str]:
        if parent in single_exact:
            return single_exact[parent], "exact"
        normed_parent = _norm(parent)
        if normed_parent in single_normed:
            return single_normed[normed_parent], "normed"
        for sk, sv in single_normed.items():  # 前缀匹配（处理截断名）
            if sk and normed_parent and (sk.startswith(normed_parent) or normed_parent.startswith(sk)):
                return sv, "fuzzy"
        return None, "consol_only"

    # 按合并章节（五-N）分组，保持模板顺序
    chapters: dict[str, list[dict]] = {}
    for t in consol_tables:
        sid = str(t.get("section_id") or "")
        if sid:
            chapters.setdefault(sid.rsplit("-", 1)[0], []).append(t)

    mappings: list[dict] = []
    stats: Counter = Counter()
    for tables in chapters.values():
        # 1. 逐表按表标题找单体子表
        hits_per_table = [
            [] if _is_generic_continuation(t.get("title", "")) else by_table.get(_table_key(t.get("title")), [])
            for t in tables
        ]
        # 2. 本合并章节的单体章节：只按「表名全模板唯一」的命中投票（同名子表散在多章，如
        #    「收回或转回的坏账准备」八、5 / 八、9 都有，不能参与定章）；全无命中按 parent_section 兜底
        votes = Counter(
            {s["section_number"] for s, _ in hits}.pop()
            for hits in hits_per_table if hits and len({s["section_number"] for s, _ in hits}) == 1
        )
        if votes:
            top = votes.most_common(1)[0][0]
            chapter_single = next(s for hits in hits_per_table for s, _ in hits if s["section_number"] == top)
            fallback_how = "chapter"
        else:
            chapter_single, fallback_how = _by_parent(str(tables[0].get("parent_section") or ""))
        # 定章兜底只认报表项目注释主章节：合并特有章节（合并范围变更等）里标题没命中的表
        # 没有单体对应，不能因为同章有一两张表重名就整章挂到单体某节
        fallback_single = (
            chapter_single
            if chapter_single is not None and str(chapter_single.get("section_number", "")).startswith(main)
            else None
        )

        # 3. 同名子表散在多章时取本章节那一张，否则取主章节在前的那张
        resolved: list[tuple[dict | None, str | None, str]] = []
        for hits in hits_per_table:
            if not hits:
                resolved.append((None, None, ""))
                continue
            in_chapter = [h for h in hits if chapter_single is not None and h[0] is chapter_single]
            s, name = (in_chapter or hits)[0]
            resolved.append((s, name, "table_title"))

        for i, t in enumerate(tables):
            single, table_name, how = resolved[i]
            if single is None and fallback_single is not None:
                single, how = fallback_single, fallback_how
                # 「续：」接上一张表：取单体同章节里紧随上一张子表的续表
                prev_single, prev_table, _ = resolved[i - 1] if i else (None, None, "")
                if _is_generic_continuation(t.get("title", "")) and prev_single is single and prev_table:
                    names = [x.get("name") for x in single.get("tables") or []]
                    if prev_table in names:
                        j = names.index(prev_table)
                        if j + 1 < len(names) and _is_continuation_name(names[j + 1] or ""):
                            table_name, how = names[j + 1], "continuation"
                resolved[i] = (single, table_name, how)
            stats[how or "consol_only"] += 1
            mappings.append({
                "consol_section_id": t.get("section_id", ""),
                "consol_parent": t.get("parent_section", ""),
                "consol_title": t.get("title", ""),
                "consol_seq": t.get("seq", 0),
                "standalone_note_section": single.get("section_number", "") if single else None,
                "standalone_section_title": single.get("section_title", "") if single else None,
                "match_type": how if single else "consol_only",
                "standalone_table_name": table_name if single else None,
            })

    return mappings, stats


def main():
    dry_run = "--dry-run" in sys.argv

    result = {"version": 1, "description": "合并附注 → 单体附注章节映射（自动生成）", "mappings": {}}

    for tt in ("soe", "listed"):
        mappings, stats = generate(tt)
        result["mappings"][tt] = mappings
        total = sum(stats.values())
        print(f"\n{tt.upper()}: {total} 张合并表")
        for k, v in stats.most_common():
            print(f"  {k}: {v}")
        resolved = total - stats.get("consol_only", 0)
        print(f"  已映射: {resolved}/{total} ({resolved*100//max(total,1)}%)")

    # 统计映射条目总数
    total_entries = sum(len(v) for v in result["mappings"].values())
    print(f"\n映射条目总数: {total_entries}")

    out_path = DATA / "consol_note_section_mapping.json"
    if dry_run:
        print(f"\n[DRY RUN] 不写入 {out_path}")
        # 打印几条样例
        for tt in ("soe",):
            print(f"\n{tt} 样例（前 5 条）:")
            for entry in result["mappings"][tt][:5]:
                print(f"  {entry['consol_section_id']}: {entry['consol_parent']}"
                      f" → {entry['standalone_note_section'] or '(无)'}"
                      f" [{entry['match_type']}]")
            # consol_only 的
            only = [e for e in result["mappings"][tt] if e["match_type"] == "consol_only"]
            if only:
                print(f"\n{tt} consol_only（前 5 条）:")
                for entry in only[:5]:
                    print(f"  {entry['consol_section_id']}: {entry['consol_parent']}")
    else:
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {out_path}")


if __name__ == "__main__":
    main()
