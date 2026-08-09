"""Task 13/14 守卫的变异检验。

铁律遵循（memory）：
* 备份落 `.bak` 并提供 `--restore`，还原用 `write_bytes` **字节级**
  （`Path.write_text` 在 Windows 会把 LF 转 CRLF → 假 DIRTY）；
* 锚点一律**单行**（CRLF 工作树下跨行锚点必 ANCHOR-MISS）且断言命中数 == 1；
* 判定按**失败测试名集合差集**，不看退出码（基线可能本就有红）；
* 三态区分：RED（新增失败）/ GREEN（守卫缺陷）/ ANCHOR-MISS（脚本缺陷）。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
BACKEND = _HERE.parents[2]
REPO = _HERE.parents[3]
OUT = _HERE.parent / "mutate_note_text_hygiene_and_expandable.txt"
_STAMP = "round2"

TESTS = [
    "backend/tests/test_note_text_hygiene.py",
    "backend/tests/test_note_expandable_rows.py",
]

FIXER = BACKEND / "scripts" / "fix" / "fix_note_text_hygiene.py"
EXPAND_FIX = BACKEND / "scripts" / "fix" / "fix_note_expandable_rows.py"
# 🔴 判据已从生成器脚本搬到 service 层（Property 38：单一真源）
# ⇒ M7/M8/M9 必须锚在这里，锚在 build_note_expandable_markers.py 会 ANCHOR-MISS。
JUDGE = BACKEND / "app" / "services" / "note_expandable_markers.py"
KIT = BACKEND / "scripts" / "fix" / "_note_structure_kit.py"
H_POLICY = BACKEND / "scripts" / "fix" / "fix_note_h_policy_chapter_structure.py"
PROJECTOR = BACKEND / "app" / "services" / "note_sub_table_projector.py"
EXPORTER = BACKEND / "app" / "services" / "note_word_exporter.py"
DETECTOR = BACKEND / "app" / "services" / "note_empty_table_detector.py"
SEGMENTS = BACKEND / "app" / "services" / "note_shared_table_segments.py"
FE_SKIP = (
    REPO / "audit-platform" / "frontend" / "src" / "views" / "composables"
    / "disclosureEmptyTable.ts"
)

# (id, 文件, 单行锚点, 替换成, 说明)
MUTATIONS: list[tuple[str, Path, str, str, str]] = [
    ("M1", FIXER,
     '    if _norm_ws(text) in {_norm_ws(h) for h in headers if str(h or "").strip()}:',
     '    if any(_norm_ws(text) in _norm_ws(h) for h in headers if str(h or "").strip()):',
     "prove_header_artifact 改成子串匹配（业务行会被误判成表头残留）"),
    ("M2", FIXER,
     "    if _HTML_RE.search(text):",
     "    if False:",
     "prove_header_artifact 去掉 HTML 判据（带 <br/> 的假行证明不了）"),
    ("M3", FIXER,
     "        if MARKERS_MOD.match_label_marker(label) is not None:",
     "        if False:",
     "plan_header_label_rows 去掉可扩位保护（会把 …… 行当假行删）"),
    ("M4", FIXER,
     "        if proof is None:",
     "        if False:",
     "plan_header_label_rows 去掉 fail-closed（证明不了也删）"),
    ("M5", FIXER,
     "        if scope == PROBE.SCOPE_PARENT:",
     "        if False:",
     "run_variant 去掉母公司章排除（越界改 A spec 的表）"),
    ("M6", FIXER,
     "            if section_code_of(num) in declared:",
     "            if False:",
     "run_variant 去掉 text_sections 冲突避让"),
    # 🔴 单行锚点：`    "预留",\n    "…",\n)` 在 MARKERS 与 LABEL_MARKERS 末尾**各出现一次**
    # ⇒ 跨行锚点必命中 2 处（ANCHOR-MISS）。改锚在 LABEL_MARKERS 的声明行上。
    ("M7", JUDGE,
     "LABEL_MARKERS: tuple[str, ...] = (",
     'LABEL_MARKERS: tuple[str, ...] = ("可改名",',
     "LABEL_MARKERS 加回 可改名（示例行名会被标成零可见内容）"),
    ("M8", JUDGE,
     "        if cand in normed:",
     "        if any(cand in k or k in cand for k in normed):",
     "match_label_marker 改成包含匹配（业务行被误标）"),
    # 🔴 首版 M9 是**无效变异**：只把第 3 个候选换成 rstrip 到底，而 `base`（原样）
    # 仍是第 1 个候选 ⇒ `......` 照样命中，守卫不红是**正确**的。
    # 要复现原缺陷必须把「原样候选」拿掉，让判定只看被剥空的结果。
    # 🔴 第二版锚点又含 `\n`（CRLF 下 0 命中 = ANCHOR-MISS）—— 同一个坑踩了两次。
    # 第三版：锚在 service 层 `label_candidates` 的**单行** for 语句上。
    ("M9", JUDGE,
     "    for cand in (base, stripped, tail_trimmed):",
     "    for cand in (stripped.rstrip(_LABEL_TAIL_PUNCT),):",
     "label_candidates 去掉原样候选、只留剥到底的（`......` 被吃空 → 漏标 4 行）"),
    ("M10", EXPAND_FIX,
     'CONVERTIBLE_FROM = ("data", "")',
     'CONVERTIBLE_FROM = ("data", "", "total", "header_label")',
     "CONVERTIBLE_FROM 扩大（合计行/假表头行会被改标）"),
    ("M11", PROJECTOR,
     "            if is_zero_visible_row(r):  # 可扩位：零可见内容（Property 33）",
     "            if False:",
     "投影器主路径去掉可扩位过滤"),
    ("M12", PROJECTOR,
     "                if isinstance(r, dict) and not is_zero_visible_row(r)",
     "                if isinstance(r, dict)",
     "投影器降级路径去掉可扩位过滤"),
    ("M13", EXPORTER,
     "            rows = [r for r in rows if not _is_zero_visible_row(r)]",
     "            rows = list(rows)",
     "Word 导出去掉可扩位过滤（交付件多出占位行）"),
    ("M14", DETECTOR,
     '    {"total", "subtotal", "section", "header_label", "expandable"}',
     '    {"total", "subtotal", "section", "header_label"}',
     "空表检测 skip 集合去掉 expandable"),
    ("M15", SEGMENTS,
     '_TOTAL_ROW_TYPES = frozenset({"total", "header_label"})',
     '_TOTAL_ROW_TYPES = frozenset({"total", "header_label", "expandable"})',
     "把 expandable 当无主行（会把可扩位排除出段可写区）"),
    # 🔴 单行锚点：首版写 `  'expandable',\n])` 含换行，CRLF 工作树下 0 命中
    #（ANCHOR-MISS）—— 自己又踩了一次「跨行锚点」的坑。
    ("M16", FE_SKIP,
     "  'expandable',",
     "  // 'expandable',",
     "前端 skip 集合去掉 expandable（前后端漂移）"),
    # ── Property 38：`row_type` 判据单一真源，禁写者硬编码 ──────────────────
    ("M17", KIT,
     '    return {"label": label, "row_type": row_type_for_label(label)}',
     '    return {"label": label, "row_type": "data"}',
     "共享行构造器 data_row 改回硬编码 data（多个 per-cycle 脚本会翻转可扩位）"),
    ("M18", H_POLICY,
     '                {"label": r, "row_type": _row_type_for_label(r)} for r in spec["rows"]',
     '                {"label": r, "row_type": "data"} for r in spec["rows"]',
     "H 政策章 ADD_TABLES 改回硬编码（深比较整表重写 → 翻回 soe 生物资产 4 行）"),
]


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _run_tests() -> set[str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", *TESTS, "-q", "--tb=no", "-rf",
         "-p", "no:cacheprovider", "--continue-on-collection-errors"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env, timeout=1800,
    )
    out = (r.stdout or "") + (r.stderr or "")
    return set(re.findall(r"^(?:FAILED|ERROR)\s+(\S+)", out, re.M))


def restore_all() -> list[str]:
    msgs = []
    for path in {m[1] for m in MUTATIONS}:
        bak = path.with_suffix(path.suffix + ".bak")
        if bak.exists():
            path.write_bytes(bak.read_bytes())
            bak.unlink()
            msgs.append("restored " + path.name)
    return msgs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args(argv)
    if args.restore:
        for m in restore_all():
            print(m)
        return 0

    lines: list[str] = ["stamp=%s" % _STAMP]
    baseline = _run_tests()
    lines.append("baseline 失败集合 = %s" % (sorted(baseline) or "空（全绿）"))
    lines.append("")

    red = green = miss = 0
    for mid, path, anchor, repl, desc in MUTATIONS:
        original = path.read_bytes()
        text = original.decode("utf-8")
        hits = text.count(anchor)
        if hits != 1:
            lines.append("%-4s ANCHOR-MISS hits=%d  %s  [%s]" % (mid, hits, desc, path.name))
            miss += 1
            continue
        # 🔴 **内存优先还原**：`.bak` 曾被外部（并发会话的 tmp 清理）删掉，
        # 导致 `finally` 里 `bak.read_bytes()` 抛 FileNotFoundError、
        # 变异**残留在文件里**（2026-08-08 实测踩到 M4）。故以 `original`
        # 这份内存副本为还原真源，`.bak` 只作二次保险。
        bak = path.with_suffix(path.suffix + ".bak")
        bak.write_bytes(original)
        try:
            path.write_bytes(text.replace(anchor, repl).encode("utf-8"))
            after = _run_tests()
            new = sorted(after - baseline)
            if new:
                lines.append("%-4s RED   +%d  %s" % (mid, len(new), desc))
                for n in new[:4]:
                    lines.append("        %s" % n.split("::", 1)[-1])
                red += 1
            else:
                lines.append("%-4s GREEN 守卫缺陷！  %s" % (mid, desc))
                green += 1
        finally:
            path.write_bytes(original)
            if bak.exists():
                bak.unlink()
            assert _md5(path) == hashlib.md5(original).hexdigest(), (
                "还原失败：%s" % path
            )

    lines.append("")
    lines.append("汇总：RED=%d  GREEN=%d  ANCHOR-MISS=%d  / 共 %d"
                 % (red, green, miss, len(MUTATIONS)))
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if (green == 0 and miss == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
