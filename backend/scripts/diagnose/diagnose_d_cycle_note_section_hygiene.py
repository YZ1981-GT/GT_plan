"""D 循环附注章节卫生诊断（**只读**，无任何删除能力）。

用途
====

本 spec 立项时把 5 个章节列为「孤儿重复章」并计划删除，该判断已被实测推翻
（它们是母公司附注章的正当子节，详见
`backend/tests/services/test_note_d_orphan_sections.py` 的模块 docstring）。

裁决门 B 的答复是 **①只出报告 + 守卫，不删 tracked 数据**，故本脚本：

- 只读 `backend/data/note_template_{listed,soe}.json`，不连库、不写盘（除 `--out`）
- **不提供** `--apply` / `--confirm` / 任何 DELETE 能力
- 输出三段报告：①母公司章归属证据 ②按严判据的真孤儿候选清单（含归属 spec）
  ③D 类 14 个合并章的列元数据健康度

用法
====

    python backend/scripts/diagnose/diagnose_d_cycle_note_section_hygiene.py
    python backend/scripts/diagnose/diagnose_d_cycle_note_section_hygiene.py --out report.txt
    python backend/scripts/diagnose/diagnose_d_cycle_note_section_hygiene.py --variant soe

退出码恒为 0（诊断不做裁决）；`--strict` 时若 D 类合并章出现列元数据缺失则返回 1。

Validates: Requirements 6.2, 6.3
Property: 23
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 母公司章 section_id 前缀（实证值）
PARENT_CHAPTER_PREFIX = {
    "listed": "chapter-16-mu-gong-si-",
    "soe": "chapter-12-mu-gong-si-",
}

# 立项时被列为「孤儿」而后撤回的章号（禁删清单）
WITHDRAWN_ORPHAN_SECTIONS = {
    "listed": ("十六、应收票据", "十六、应收账款", "十六、营业收入与营业成本"),
    "soe": ("十二、应收账款", "十二、营业收入与营业成本"),
}

# D 类 7 循环的合并章章号（listed, soe）
D_CYCLE_MERGED_SECTIONS = {
    "D1": ("五、4", "八、4"),
    "D2": ("五、5", "八、5"),
    "D3": ("五、38", "八、38"),
    "D4": ("五、62", "八、64"),
    "D5": ("五、6", "八、6"),
    "D6": ("五、10", "八、11"),
    "D7": ("五、39", "八、39"),
}

# 表名「表头首格泄漏」特征（严判据用）
LEAK_PATTERNS = (
    "种  类", "种 类", "种类", "类 别", "类别", "项  目", "项 目", "项目",
    "单位名称", "承兑人名称", "名  称", "名称", "账  龄", "票据种类",
    "子公司名称", "被购买方名称", "被合并方名称", "分  类", "内  容",
    "转移方式", "债务重组方式", "信用评级", "结构化主体",
    "本期或本期期末", "上期或上期期末", "合营企业或联营",
)


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
    raise SystemExit(
        "未能定位仓库根（需同时存在 backend/data/note_template_listed.json 与 "
        "audit-platform/frontend/package.json）"
    )


def _load_sections(root: Path, variant: str) -> list[dict]:
    path = root / "backend" / "data" / f"note_template_{variant}.json"
    if not path.exists():
        raise SystemExit(f"模板缺失：{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("sections") or []


def _cols_zero_count(sec: dict) -> int:
    tables = sec.get("tables") or []
    return sum(1 for t in tables if len(t.get("columns") or []) == 0)


def _is_leak_name(name: str) -> bool:
    norm = (name or "").replace("<br/>", "").strip()
    if not norm:
        return True
    return any(p in norm for p in LEAK_PATTERNS)


def _parent_subsections(sections: list[dict], variant: str) -> list[dict]:
    prefix = PARENT_CHAPTER_PREFIX[variant]
    return [
        s
        for s in sections
        if (s.get("parent_section_id") or "").startswith(prefix)
        and (s.get("level") or 0) == 2
    ]


def _strict_orphans(sections: list[dict]) -> list[dict]:
    """严判据：`_aligned_by` 为空 + 全部子表缺 columns + 全部表名都是表头泄漏。"""
    out: list[dict] = []
    for sec in sections:
        tables = sec.get("tables") or []
        if not tables or sec.get("_aligned_by"):
            continue
        if _cols_zero_count(sec) != len(tables):
            continue
        if all(_is_leak_name(t.get("name") or "") for t in tables):
            out.append(sec)
    return out


def _section_number(sec: dict) -> str:
    return (sec.get("section_number") or "").strip()


def _report_parent_chapter(sections: list[dict], variant: str, lines: list[str]) -> None:
    lines.append("")
    lines.append(f"## [{variant}] 段一：母公司章归属证据（禁删锁死的依据）")
    prefix = PARENT_CHAPTER_PREFIX[variant]
    chapters = [
        s
        for s in sections
        if (s.get("section_id") or "").startswith(prefix) and (s.get("level") or 0) == 1
    ]
    if not chapters:
        lines.append(f"  [ERR] 未找到母公司章（前缀 {prefix}）—— 章节结构已变，须重新裁决")
        return
    ch = chapters[0]
    lines.append(
        f"  母公司章: number={_section_number(ch)!r} title={ch.get('section_title')!r}"
    )
    subs = _parent_subsections(sections, variant)
    withdrawn = set(WITHDRAWN_ORPHAN_SECTIONS[variant])
    lines.append(f"  子节数: {len(subs)}（其中曾被列为孤儿的 {len(withdrawn)} 个已标 *）")
    for sec in subs:
        num = _section_number(sec)
        tables = sec.get("tables") or []
        zero = _cols_zero_count(sec)
        mark = " *" if num in withdrawn else "  "
        lines.append(
            f"   {mark} {num:<24} tables={len(tables):>3} 缺列={zero:>3}"
            f" aligned={bool(sec.get('_aligned_by'))!s:<5} scope={sec.get('scope')!r}"
        )
    matched = [
        _section_number(s)
        for s in subs
        if not s.get("_aligned_by")
        and (not (s.get("tables") or []) or _cols_zero_count(s) == len(s["tables"]))
    ]
    lines.append(
        f"  立项判据（_aligned_by 空 + 全部子表缺列）当前命中 {len(matched)} 个: "
        f"{matched}"
    )
    lines.append(
        "  => 该判据描述的是母公司章共性（未补列元数据），不是孤儿特征；"
        "列元数据补齐归 parent-company-note-chapter-and-sourcing spec"
    )


def _report_strict_orphans(sections: list[dict], variant: str, lines: list[str]) -> None:
    lines.append("")
    lines.append(f"## [{variant}] 段二：严判据真孤儿候选（本 spec 不处置，只登记归属）")
    orphans = _strict_orphans(sections)
    withdrawn = set(WITHDRAWN_ORPHAN_SECTIONS[variant])
    overlap = [_section_number(s) for s in orphans if _section_number(s) in withdrawn]
    lines.append(f"  命中 {len(orphans)} 章")
    by_parent: dict[str, list[str]] = {}
    for sec in orphans:
        parent = sec.get("parent_section_id") or "(无父节)"
        by_parent.setdefault(parent, []).append(_section_number(sec))
    for parent, nums in sorted(by_parent.items()):
        lines.append(f"   父节 {parent}")
        for num in nums:
            lines.append(f"     - {num}")
    if overlap:
        lines.append(
            f"  [ERR] 严判据命中了母公司章 {overlap} —— 母公司章表名是真实表名，"
            "命中说明判据实现有误"
        )
    else:
        lines.append("  [OK] 与母公司章零交集（母公司章表名是真实表名，非表头泄漏）")
    lines.append(
        "  => 归属 note-template-columns-and-legacy-snapshot-closure spec"
        "（列元数据补齐），本 spec 不补列也不删除"
    )


def _report_d_cycle_health(
    sections: list[dict], variant: str, lines: list[str]
) -> list[str]:
    lines.append("")
    lines.append(f"## [{variant}] 段三：D 类合并章列元数据健康度（前序 spec 对齐成果）")
    idx = 0 if variant == "listed" else 1
    problems: list[str] = []
    for wp, pair in D_CYCLE_MERGED_SECTIONS.items():
        number = pair[idx]
        hits = [s for s in sections if _section_number(s) == number]
        if len(hits) != 1:
            msg = f"{variant} {wp} {number!r} 命中 {len(hits)} 条（期望 1）"
            problems.append(msg)
            lines.append(f"   [ERR] {wp:<3} {number:<8} {msg}")
            continue
        sec = hits[0]
        tables = sec.get("tables") or []
        zero = _cols_zero_count(sec)
        aligned = bool(sec.get("_aligned_by"))
        ok = tables and zero == 0 and aligned
        flag = "[OK] " if ok else "[ERR]"
        lines.append(
            f"   {flag} {wp:<3} {number:<8} tables={len(tables):>3}"
            f" 缺列={zero:>3} aligned={aligned!s}"
        )
        if not ok:
            problems.append(
                f"{variant} {wp} {number!r}: tables={len(tables)} 缺列={zero}"
                f" aligned={aligned}"
            )
    if not problems:
        lines.append("  [OK] 7 个循环全部列元数据齐备且已对齐")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description="D 循环附注章节卫生诊断（只读，无删除能力）"
    )
    parser.add_argument(
        "--variant",
        choices=("listed", "soe", "both"),
        default="both",
        help="只诊断某一变体（默认 both）",
    )
    parser.add_argument("--out", help="报告落盘路径（默认打印到 stdout）")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="D 类合并章出现列元数据缺失时返回退出码 1",
    )
    args = parser.parse_args()

    root = _repo_root()
    variants = ("listed", "soe") if args.variant == "both" else (args.variant,)

    lines: list[str] = [
        "# D 循环附注章节卫生诊断报告",
        "",
        "本脚本只读，不提供任何删除能力（裁决门 B = 只出报告 + 守卫，不删 tracked 数据）。",
    ]
    problems: list[str] = []
    for variant in variants:
        sections = _load_sections(root, variant)
        lines.append("")
        lines.append(f"{'=' * 72}")
        lines.append(f"变体 {variant}：共 {len(sections)} 个章节")
        _report_parent_chapter(sections, variant, lines)
        _report_strict_orphans(sections, variant, lines)
        problems.extend(_report_d_cycle_health(sections, variant, lines))

    lines.append("")
    lines.append(f"{'=' * 72}")
    lines.append(f"D 类合并章问题数: {len(problems)}")
    for p in problems:
        lines.append(f"  - {p}")

    text = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[OK] report written: {args.out} ({len(text)} chars)")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)

    return 1 if (args.strict and problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
