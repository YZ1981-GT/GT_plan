"""生成合并附注 section_id → 单体附注 note_section 映射配置文件。

用法：
  python scripts/seed/gen_consol_standalone_note_mapping.py
  python scripts/seed/gen_consol_standalone_note_mapping.py --dry-run

输出：backend/data/consol_note_section_mapping.json

映射逻辑：
1. 合并模板的 parent_section（中文科目名）匹配单体模板的 section_title
2. 精确匹配 → label_key 规范化后匹配 → 前缀/包含匹配
3. 未匹配的标为 consol_only（合并特有章节，无单体对应）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

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


def generate(template_type: str) -> list[dict]:
    # 合并模板
    consol_path = DATA / f"consol_note_sections_{template_type}.json"
    consol_tables = _load_json(consol_path)
    if not isinstance(consol_tables, list):
        consol_tables = []

    # 单体模板
    single_path = DATA / f"note_template_{template_type}.json"
    single_data = _load_json(single_path)
    single_sections = single_data.get("sections", []) if isinstance(single_data, dict) else []
    # 只取有表格的章节
    single_with_tables = [s for s in single_sections if s.get("tables")]

    # 按 section_title 索引单体（精确 + 规范化两份索引）
    # 优先八章（主体科目），十章以后的同名章节不覆盖八章的映射
    single_exact: dict[str, dict] = {}
    single_normed: dict[str, dict] = {}
    # 排序：八章优先（section_number 以 "八" 开头的排前面）
    sorted_singles = sorted(single_with_tables, key=lambda s: (
        0 if s.get("section_number", "").startswith("八") else 1,
        s.get("sort_order", 9999),
    ))
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

    # 按 parent_section 分组合并表
    chapters: dict[str, list[dict]] = {}
    for t in consol_tables:
        p = t.get("parent_section", "")
        if p:
            chapters.setdefault(p, []).append(t)

    mappings = []
    stats = {"exact": 0, "normed": 0, "fuzzy": 0, "consol_only": 0}

    for parent, tables in chapters.items():
        single = None
        match_type = "consol_only"

        # 1. 精确匹配
        if parent in single_exact:
            single = single_exact[parent]
            match_type = "exact"
        else:
            # 2. 规范化后匹配
            normed_parent = _norm(parent)
            if normed_parent in single_normed:
                single = single_normed[normed_parent]
                match_type = "normed"
            else:
                # 3. 前缀/包含匹配（处理截断名）
                for sk, sv in single_normed.items():
                    if sk and normed_parent and (
                        sk.startswith(normed_parent) or normed_parent.startswith(sk)
                    ):
                        single = sv
                        match_type = "fuzzy"
                        break

        stats[match_type] = stats.get(match_type, 0) + 1

        for table in tables:
            entry: dict = {
                "consol_section_id": table.get("section_id", ""),
                "consol_parent": parent,
                "consol_title": table.get("title", ""),
                "consol_seq": table.get("seq", 0),
            }
            if single:
                entry["standalone_note_section"] = single.get("section_number", "")
                entry["standalone_section_title"] = single.get("section_title", "")
                entry["match_type"] = match_type
                # 如果合并表有特定 table_name，尝试在单体子表中找对应
                consol_table_name = table.get("title", "")
                single_tables = single.get("tables", [])
                matched_table = None
                for st in single_tables:
                    if _norm(st.get("name", "")) == _norm(consol_table_name):
                        matched_table = st.get("name")
                        break
                entry["standalone_table_name"] = matched_table
            else:
                entry["standalone_note_section"] = None
                entry["standalone_section_title"] = None
                entry["match_type"] = "consol_only"
                entry["standalone_table_name"] = None

            mappings.append(entry)

    return mappings, stats


def main():
    dry_run = "--dry-run" in sys.argv

    result = {"version": 1, "description": "合并附注 → 单体附注章节映射（自动生成）", "mappings": {}}

    for tt in ("soe", "listed"):
        mappings, stats = generate(tt)
        result["mappings"][tt] = mappings
        total = sum(stats.values())
        print(f"\n{tt.upper()}: {total} 个章节组")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        resolved = stats.get("exact", 0) + stats.get("normed", 0) + stats.get("fuzzy", 0)
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
