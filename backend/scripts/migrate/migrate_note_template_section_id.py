"""Sprint A.0.2 — note_template JSON section_id 字段重构（D13 章节序号）.

**目的**：给 `note_template_soe.json` / `note_template_listed.json` 每个 section
注入 D13 字段（保留 `section_number` 作为兼容字段）：

- `section_id`           — 稳定 ID（kebab-case，如 `acct-basis-currency`）
- `level`                — 1~5 层级（1=top chapter，2=sub-section）
- `parent_section_id`    — 父引用，level=1 为 None
- `sort_index`           — 同 (parent, level) 内排序
- `auto_numbering`       — bool，默认 true
- `lock_number`          — bool，默认 false

**背景**：现存 section_number 是非结构化字符串（"四、记账本位币" / "八、1" /
"四、企业合并"），且共享 `四` `八` 等前缀的多个 section 实际是同一 chapter 下
的兄弟节点。本脚本通过：

1. 按 section_number 的 leading 中文数字分组（一/二/三/.../十七）。
2. 为每个 group 注入合成 level=1 chapter（从 ``LEVEL1_TITLES`` 表读，
   如未列出则取 group 第一条 section 的 account_name 作为 chapter 名）。
3. group 中现有 sections 一律降为 level=2，parent_section_id 指向合成 chapter。
4. section_id 由 chapter 路径 + 章节标题 pinyin 组合，保证全文件唯一。

**特别处理**：
- 多个 section 共享相同 leading 数字（如 SOE `四、` 共 36 条）— 全部为同一
  chapter "重要会计政策" 下的 level=2 兄弟。
- `八、1` `八、2` 等纯数字尾号 — 同 leading 处理（合成 chapter "财务报表主要项目注释"）。
- listed 模板 `三、` 同时含「遵循准则声明」和会计政策（73 条）— 仍按 leading
  分组合成 chapter "重要会计政策" 一个。这是数据本身的不规则，不在本脚本范围
  修复（由审计师在 P-6 中标注）。

**幂等性**：
- 已经含 section_id 字段的 section 跳过 ID 派生（仍可被 chapter 关联补全）。
- 多次执行结果稳定（chapter section_id 固定，sort_index 重排）。

**用法**::

    python backend/scripts/migrate_note_template_section_id.py

执行后：
- 原 JSON 备份为 `*.json.bak`（已有备份则跳过备份步骤）。
- 写入新结构（合成 chapter section 排在该 group 首位 + sort_order 微调
  使 chapter 排在 group 内最前）。
- 终端打印每文件的 sections 数 + level 分布 + section_id 唯一性。
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from pypinyin import Style, lazy_pinyin


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATA_DIR = BACKEND_DIR / "data"

# 全部 note_template_*.json — 排除 bindings / multi_standard 等其它 note_template_ 文件
TEMPLATE_GLOB = "note_template_*.json"

# 中文数字 → 阿拉伯数字（用于 chapter index）
_CN_NUM = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
}

# 标准 chapter 名称（按 leading 数字 + 模板类型映射）
# 当 group 实际内容多样时（如 listed 三 = 准则声明 + 会计政策合并），
# 取最常见语义。审计师可后续在 P-7 中精修。
_LEVEL1_TITLES_SOE = {
    "一": "公司基本情况",
    "二": "财务报表编制基础",
    "三": "遵循企业会计准则的声明",
    "四": "重要会计政策、会计估计",
    "五": "重要会计政策、会计估计的变更以及前期差错的更正",
    "六": "税项",
    "七": "合并范围的变化",
    "八": "财务报表主要项目注释",
    "九": "或有事项",
    "十": "资产负债表日后事项",
    "十一": "关联方及关联交易",
    "十二": "股份支付",
    "十三": "承诺事项",
    "十四": "其他重要事项",
}

_LEVEL1_TITLES_LISTED = {
    "一": "公司基本情况",
    "二": "财务报表的编制基础",
    "三": "重要会计政策及会计估计",
    "四": "税项",
    "五": "合并财务报表项目注释",
    "六": "研发支出",
    "七": "在其他主体中的权益",
    "八": "政府补助",
    "九": "金融工具风险管理",
    "十": "公允价值披露",
    "十一": "关联方及关联交易",
    "十二": "股份支付",
    "十三": "承诺及或有事项",
    "十四": "资产负债表日后事项",
    "十五": "其他重要事项",
    "十六": "母公司财务报表主要项目注释",
    "十七": "补充资料",
}

_TITLES_BY_TYPE = {
    "soe": _LEVEL1_TITLES_SOE,
    "listed": _LEVEL1_TITLES_LISTED,
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

_LEAD_CN_RE = re.compile(r"^(十[一二三四五六七八九]?|二十|[一二三四五六七八九十])、(.*)$")
_KEBAB_RE = re.compile(r"[^a-z0-9]+")


def _kebab(text: str) -> str:
    """将任意文本转为 kebab-case ASCII slug（拼音首字母 + 全拼组合）.

    示例:
      记账本位币 → ji-zhang-ben-wei-bi
      货币资金   → huo-bi-zi-jin
      公司基本情况 → gong-si-ji-ben-qing-kuang
    """
    if not text:
        return ""
    text = text.strip()
    # 已经是 ASCII（用于 chapter 兜底，例如 chapter-4）— 直接返回
    if all(ord(c) < 128 for c in text):
        slug = _KEBAB_RE.sub("-", text.lower()).strip("-")
        return slug or "section"
    # 中文 → 拼音全拼
    py_parts = lazy_pinyin(text, style=Style.NORMAL, errors="ignore")
    slug = "-".join(p for p in py_parts if p).lower()
    slug = _KEBAB_RE.sub("-", slug).strip("-")
    # 限长（防止超长 ID 撑爆 VARCHAR(100)）
    if len(slug) > 80:
        slug = slug[:80].rstrip("-")
    return slug or "section"


def _parse_leading(section_number: str) -> tuple[str | None, str]:
    """解析 section_number → (leading_cn, remainder).

    示例:
      "四、记账本位币"  → ("四", "记账本位币")
      "八、1"          → ("八", "1")
      "四、企业合并"    → ("四", "企业合并")
      ""               → (None, "")
    """
    if not section_number:
        return (None, "")
    m = _LEAD_CN_RE.match(section_number)
    if not m:
        return (None, section_number)
    return (m.group(1), m.group(2))


def _make_unique(slug: str, used: set[str]) -> str:
    """如果 slug 已被使用，追加 -2 / -3 / ...直到唯一."""
    if slug not in used:
        used.add(slug)
        return slug
    n = 2
    while f"{slug}-{n}" in used:
        n += 1
    final = f"{slug}-{n}"
    used.add(final)
    return final


# ---------------------------------------------------------------------------
# Core migration
# ---------------------------------------------------------------------------

def migrate_template(path: Path) -> dict[str, Any]:
    """对单个 note_template_*.json 注入 D13 字段并写回.

    Returns:
        统计字典：{file, sections_in, sections_out, levels: {1:N,2:N,...},
                  chapters_synthesized, section_ids_unique}
    """
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    template_type = raw.get("template_type") or _infer_template_type(path)
    sections = raw.get("sections") or []
    titles_table = _TITLES_BY_TYPE.get(template_type, _LEVEL1_TITLES_SOE)

    # 1. 按 leading 中文数字分组，保持原有顺序
    groups: dict[str, list[dict]] = {}
    group_order: list[str] = []  # 保留首次出现顺序
    no_lead: list[dict] = []     # 没有合法 leading 的 section
    for s in sections:
        sn = s.get("section_number", "")
        lead, _rest = _parse_leading(sn)
        if lead is None:
            no_lead.append(s)
            continue
        if lead not in groups:
            groups[lead] = []
            group_order.append(lead)
        groups[lead].append(s)

    # 2. 为每个 group 合成 level=1 chapter section + 派生 ID
    used_ids: set[str] = set()
    chapters: dict[str, dict] = {}
    for lead in group_order:
        chapter_index = _CN_NUM.get(lead, 0)
        chapter_title = titles_table.get(lead) or (
            groups[lead][0].get("account_name")
            or groups[lead][0].get("section_title")
            or f"chapter-{chapter_index or lead}"
        )
        # 合成 chapter section_id：chapter-{idx}-{slug}
        slug_part = _kebab(chapter_title)
        cid_base = f"chapter-{chapter_index:02d}-{slug_part}" if chapter_index else f"chapter-{slug_part}"
        cid = _make_unique(cid_base, used_ids)
        chapters[lead] = {
            "section_id": cid,
            "section_number": f"{lead}",  # 合成节点（用 leading 单字符不冲突现有）
            "section_title": chapter_title,
            "account_name": chapter_title,
            # ContentType enum 只允许 table/text/mixed；合成 chapter 仅作为
            # D13 树形 parent 节点存在（无 tables 也无 text_sections），用 "text"
            # 占位避免 disclosure_engine 落库时 ContentType("chapter") 抛错
            "content_type": "text",
            "scope": "both",
            "level": 1,
            "parent_section_id": None,
            "sort_index": chapter_index,
            "auto_numbering": True,
            "lock_number": False,
            "_synthesized": True,
            "tables": [],
            "text_sections": [],
            "check_presets": [],
            "wide_table_presets": [],
            # 老的 sort_order：让 chapter 排在该 group 内最前
            "sort_order": (chapter_index * 100) - 1 if chapter_index else 0,
        }

    # 3. 给原 sections 注入 D13 字段
    new_sections: list[dict] = []
    # 先按 group_order 顺序输出 chapter + 该 group 的 sub-sections
    for lead in group_order:
        chap = chapters[lead]
        new_sections.append(chap)

        members = groups[lead]
        # sort_index：在 group 内按已有 sort_order 排序
        members_sorted = sorted(
            enumerate(members),
            key=lambda iv: (
                iv[1].get("sort_order", 0),
                iv[0],
            ),
        )
        for new_idx, (_orig_idx, sec) in enumerate(members_sorted):
            sec_out = dict(sec)  # shallow copy
            # 已有 section_id 则保留（幂等）
            existing_sid = sec.get("section_id")
            if existing_sid:
                # 但仍要校验唯一并登记
                if existing_sid in used_ids:
                    # 冲突 → 重新派生
                    existing_sid = None
                else:
                    used_ids.add(existing_sid)
            if not existing_sid:
                # 派生：chapter_id + section_title slug
                title_for_id = sec.get("section_title") or sec.get("account_name") or ""
                slug = _kebab(title_for_id) or _kebab(sec.get("section_number", ""))
                sid_base = f"{chap['section_id']}-{slug}" if slug else chap["section_id"]
                # 限总长 ≤ 95（留 5 字符给 _make_unique 的 -N 后缀）
                if len(sid_base) > 95:
                    sid_base = sid_base[:95].rstrip("-")
                sid = _make_unique(sid_base, used_ids)
                sec_out["section_id"] = sid
            else:
                sec_out["section_id"] = existing_sid

            sec_out["level"] = sec.get("level", 2)
            sec_out["parent_section_id"] = chap["section_id"]
            sec_out["sort_index"] = new_idx
            # auto_numbering 默认 True，如已有则保留
            sec_out["auto_numbering"] = bool(sec.get("auto_numbering", True))
            sec_out["lock_number"] = bool(sec.get("lock_number", False))
            new_sections.append(sec_out)

    # 4. 没有 leading 的 section（理论应为 0）— 标 level=1 无 parent
    for sec in no_lead:
        sec_out = dict(sec)
        existing_sid = sec.get("section_id")
        if not existing_sid:
            slug = _kebab(sec.get("section_title") or sec.get("account_name") or "orphan")
            existing_sid = _make_unique(f"orphan-{slug}", used_ids)
        else:
            used_ids.add(existing_sid)
        sec_out["section_id"] = existing_sid
        sec_out["level"] = sec.get("level", 1)
        sec_out["parent_section_id"] = None
        sec_out["sort_index"] = sec.get("sort_index", 0)
        sec_out["auto_numbering"] = bool(sec.get("auto_numbering", True))
        sec_out["lock_number"] = bool(sec.get("lock_number", False))
        new_sections.append(sec_out)

    # 5. 写入备份 + 新 JSON
    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(path, backup)

    raw["sections"] = new_sections
    path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 6. 统计
    levels: dict[int, int] = {}
    for s in new_sections:
        lv = s.get("level", 0)
        levels[lv] = levels.get(lv, 0) + 1

    section_ids = [s["section_id"] for s in new_sections]
    return {
        "file": path.name,
        "template_type": template_type,
        "sections_in": len(sections),
        "sections_out": len(new_sections),
        "chapters_synthesized": len(chapters),
        "no_lead_count": len(no_lead),
        "levels": dict(sorted(levels.items())),
        "section_ids_unique": len(set(section_ids)) == len(section_ids),
        "section_ids_total": len(section_ids),
        "backup": backup.name if backup.exists() else None,
    }


def _infer_template_type(path: Path) -> str:
    name = path.stem.lower()
    if "listed" in name:
        return "listed"
    if "soe" in name:
        return "soe"
    if "cas" in name:
        return "cas"
    return "soe"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# 排除的 note_template_*.json 文件（不是真正的 note 章节模板）
_EXCLUDE = {
    "note_template_bindings.json",       # cell-binding 元数据
    "note_templates_seed.json",          # 仅 seed 入库参考
    "note_template_metadata.json",       # 假设性兼容
}


def main() -> None:
    targets = sorted(
        p for p in DATA_DIR.glob(TEMPLATE_GLOB) if p.name not in _EXCLUDE
    )
    if not targets:
        print(f"NO matching templates under {DATA_DIR}")
        return

    print(f"Migrating {len(targets)} template file(s):")
    for p in targets:
        print(f"  - {p.name}")
    print()

    all_stats: list[dict[str, Any]] = []
    for p in targets:
        try:
            stats = migrate_template(p)
        except Exception as exc:  # noqa: BLE001 — 脚本侧顶层兜底
            print(f"FAIL: {p.name}: {exc}")
            continue
        all_stats.append(stats)
        print(f"=== {stats['file']} ({stats['template_type']}) ===")
        print(f"  sections: {stats['sections_in']} → {stats['sections_out']}"
              f" (+{stats['chapters_synthesized']} synthesized chapters)")
        print(f"  levels: {stats['levels']}")
        print(f"  section_id 唯一: {stats['section_ids_unique']}"
              f" ({stats['section_ids_total']} ids)")
        if stats.get("no_lead_count"):
            print(f"  WARN: {stats['no_lead_count']} sections with no leading CN-num")
        print(f"  backup: {stats['backup']}")
        print()

    print("DONE.")


if __name__ == "__main__":
    main()
