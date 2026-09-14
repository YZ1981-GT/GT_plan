"""Task 13/14 守卫的变异检验（附注文案卫生 + 可扩位行）。

spec: note-template-columns-and-legacy-snapshot-closure（已归档）
迁移：2026-08-15 由 `e1-variant-recalc-and-mutation-denominator-closure` Task 12 迁到
`_mutation_kit` 共享件 —— 原先 220 行里约 110 行是自带样板（md5 / 跑测试 / 备份还原 /
三态判定），现全部来自共享件，本文件只保留 18 条变异声明。

## 迁移时保持的两处原有语义（**不擅自加强判据**）

1. **判据是「任何新增失败即 RED」**（`want=ANY_RED`）—— 原脚本没有记录每条变异期望
   打红哪条测试，只看差集非空。这是**弱判据**（WRONG-TEST 永不出现），但迁移不该顺手
   改判据：一旦改错就分不清是迁移引入的还是原本就有的。补具体 want 应另立任务。
2. **允许脏基线**（`allow_dirty_baseline=True`）—— 原 docstring 明写「基线可能本就有红」，
   差集 `added = current - baseline` 在脏基线下仍然有效。迁移不该让原本能跑的脚本
   变成不能跑。
   🔴 2026-08-15 实测基线确实非空：`test_shared_table_counts_unchanged` 失败，因
   `note_shared_table_segments.json` 的 counts 由 `{listed:23, soe:6}` 变成
   `{listed:24, soe:8}` —— 并发 K 循环改了 `note_template_*.json` 后重跑生成器，
   共享表段增加而该断言未同步。属并发会话范围，本 spec 只登记不修。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _mutation_kit import ANY_RED, Mutation as Mut, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

BE_ARGS = [
    "backend/tests/test_note_text_hygiene.py",
    "backend/tests/test_note_expandable_rows.py",
    "-q",
    "--tb=no",
    "-rf",
    "-p",
    "no:cacheprovider",
    "--continue-on-collection-errors",
]

#: 🔴 **本脚本不设冻结基线**（传 None），这是有依据的取舍而非遗漏。
#:
#: 冻结基线的价值是「守卫例数不该偷偷变少」。但本脚本的被测面
#:（`test_note_text_hygiene.py` + `test_note_expandable_rows.py`）直接依赖
#: `note_shared_table_segments.json` 与 `note_template_*.json`，而这些文件是并发会话的
#: 高频改动区 —— 2026-08-15 实测：15 分钟内 passed 从 **99 → 97**、既存失败从 1 条 → 3 条。
#: 在这种漂移速度下，冻结基线每次运行都会 WARN，产出的是**噪声而不是信号**，
#: 而噪声 WARN 会让真正的例数下降被淹没。
#:
#: 例数保护改由被测文件自己的守卫承担（它们本就断言共享表张数、行数等结构量）。
#: 若将来该被测面稳定下来（并发改动收口后），应补回冻结基线并注明当时的实测值。
BASELINE_BE_PASSED = None

#: 覆盖面分母 —— 本脚本反证的守卫文件全集。
GUARD_FILES: dict[str, str] = {
    "test_note_text_hygiene.py": "附注文案卫生（假表头行/可扩位保护/fail-closed）",
    "test_note_expandable_rows.py": "可扩位行（row_type 单一真源 / 投影 / 导出 / 空表检测）",
}

FIXER = "backend/scripts/fix/fix_note_text_hygiene.py"
EXPAND_FIX = "backend/scripts/fix/fix_note_expandable_rows.py"
# 🔴 判据已从生成器脚本搬到 service 层（Property 38：单一真源）
# ⇒ M7/M8/M9 必须锚在这里，锚在 build_note_expandable_markers.py 会 ANCHOR-MISS。
JUDGE = "backend/app/services/note_expandable_markers.py"
KIT = "backend/scripts/fix/_note_structure_kit.py"
H_POLICY = "backend/scripts/fix/fix_note_h_policy_chapter_structure.py"
PROJECTOR = "backend/app/services/note_sub_table_projector.py"
EXPORTER = "backend/app/services/note_word_exporter.py"
DETECTOR = "backend/app/services/note_empty_table_detector.py"
SEGMENTS = "backend/app/services/note_shared_table_segments.py"
FE_SKIP = "audit-platform/frontend/src/views/composables/disclosureEmptyTable.ts"


def _m(mid: str, path: str, anchor: str, new: str, why: str) -> Mut:
    """本脚本 18 条变异形态一致（单行 replace + 弱判据），故收成一个构造器。"""
    return Mut(
        id=mid, side="be", path=path, kind="replace",
        anchor=anchor, new=new, want=ANY_RED, why=why,
    )


MUTATIONS: list[Mut] = [
    _m("M1", FIXER,
       '    if _norm_ws(text) in {_norm_ws(h) for h in headers if str(h or "").strip()}:',
       '    if any(_norm_ws(text) in _norm_ws(h) for h in headers if str(h or "").strip()):',
       "prove_header_artifact 改成子串匹配（业务行会被误判成表头残留）"),
    _m("M2", FIXER,
       "    if _HTML_RE.search(text):",
       "    if False:",
       "prove_header_artifact 去掉 HTML 判据（带 <br/> 的假行证明不了）"),
    _m("M3", FIXER,
       "        if MARKERS_MOD.match_label_marker(label) is not None:",
       "        if False:",
       "plan_header_label_rows 去掉可扩位保护（会把 …… 行当假行删）"),
    _m("M4", FIXER,
       "        if proof is None:",
       "        if False:",
       "plan_header_label_rows 去掉 fail-closed（证明不了也删）"),
    _m("M5", FIXER,
       "        if scope == PROBE.SCOPE_PARENT:",
       "        if False:",
       "run_variant 去掉母公司章排除（越界改 A spec 的表）"),
    _m("M6", FIXER,
       "            if section_code_of(num) in declared:",
       "            if False:",
       "run_variant 去掉 text_sections 冲突避让"),
    # 🔴 单行锚点：`    "预留",\n    "…",\n)` 在 MARKERS 与 LABEL_MARKERS 末尾**各出现一次**
    # ⇒ 跨行锚点必命中 2 处（ANCHOR-MISS）。改锚在 LABEL_MARKERS 的声明行上。
    _m("M7", JUDGE,
       "LABEL_MARKERS: tuple[str, ...] = (",
       'LABEL_MARKERS: tuple[str, ...] = ("可改名",',
       "LABEL_MARKERS 加回 可改名（示例行名会被标成零可见内容）"),
    _m("M8", JUDGE,
       "        if cand in normed:",
       "        if any(cand in k or k in cand for k in normed):",
       "match_label_marker 改成包含匹配（业务行被误标）"),
    # 🔴 首版 M9 是**无效变异**：只把第 3 个候选换成 rstrip 到底，而 `base`（原样）
    # 仍是第 1 个候选 ⇒ `......` 照样命中，守卫不红是**正确**的。
    # 要复现原缺陷必须把「原样候选」拿掉，让判定只看被剥空的结果。
    # 🔴 第二版锚点又含 `\n`（CRLF 下 0 命中 = ANCHOR-MISS）—— 同一个坑踩了两次。
    # 第三版：锚在 service 层 `label_candidates` 的**单行** for 语句上。
    _m("M9", JUDGE,
       "    for cand in (base, stripped, tail_trimmed):",
       "    for cand in (stripped.rstrip(_LABEL_TAIL_PUNCT),):",
       "label_candidates 去掉原样候选、只留剥到底的（`......` 被吃空 → 漏标 4 行）"),
    _m("M10", EXPAND_FIX,
       'CONVERTIBLE_FROM = ("data", "")',
       'CONVERTIBLE_FROM = ("data", "", "total", "header_label")',
       "CONVERTIBLE_FROM 扩大（合计行/假表头行会被改标）"),
    _m("M11", PROJECTOR,
       "            if is_zero_visible_row(r):  # 可扩位：零可见内容（Property 33）",
       "            if False:",
       "投影器主路径去掉可扩位过滤"),
    _m("M12", PROJECTOR,
       "                if isinstance(r, dict) and not is_zero_visible_row(r)",
       "                if isinstance(r, dict)",
       "投影器降级路径去掉可扩位过滤"),
    _m("M13", EXPORTER,
       "            rows = [r for r in rows if not _is_zero_visible_row(r)]",
       "            rows = list(rows)",
       "Word 导出去掉可扩位过滤（交付件多出占位行）"),
    _m("M14", DETECTOR,
       '    {"total", "subtotal", "section", "header_label", "expandable"}',
       '    {"total", "subtotal", "section", "header_label"}',
       "空表检测 skip 集合去掉 expandable"),
    _m("M15", SEGMENTS,
       '_TOTAL_ROW_TYPES = frozenset({"total", "header_label"})',
       '_TOTAL_ROW_TYPES = frozenset({"total", "header_label", "expandable"})',
       "把 expandable 当无主行（会把可扩位排除出段可写区）"),
    # 🔴 单行锚点：首版写 `  'expandable',\n])` 含换行，CRLF 工作树下 0 命中
    #（ANCHOR-MISS）—— 自己又踩了一次「跨行锚点」的坑。
    _m("M16", FE_SKIP,
       "  'expandable',",
       "  // 'expandable',",
       "前端 skip 集合去掉 expandable（前后端漂移）"),
    # ── Property 38：`row_type` 判据单一真源，禁写者硬编码 ──────────────────
    _m("M17", KIT,
       '    return {"label": label, "row_type": row_type_for_label(label)}',
       '    return {"label": label, "row_type": "data"}',
       "共享行构造器 data_row 改回硬编码 data（多个 per-cycle 脚本会翻转可扩位）"),
    _m("M18", H_POLICY,
       '                {"label": r, "row_type": _row_type_for_label(r)} for r in spec["rows"]',
       '                {"label": r, "row_type": "data"} for r in spec["rows"]',
       "H 政策章 ADD_TABLES 改回硬编码（深比较整表重写 → 翻回 soe 生物资产 4 行）"),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="附注文案卫生 + 可扩位行守卫变异检验",
            backend_args=BE_ARGS,
            baseline_backend_passed=BASELINE_BE_PASSED,
            # 原脚本 docstring 明写「基线可能本就有红」；当前确有 1 条并发导致的
            # 既存失败（见模块 docstring）。差集判定不受既存失败影响。
            allow_dirty_baseline=True,
        )
    )
