#!/usr/bin/env python
"""修掉披露 Tab 的「同步函数调度自己」缺陷（幂等）。

## 背景（2026-07-30，由 `check_setup_scoped_composables.py` 静态扫出 16 处）

`useDisclosureAutoSync.scheduleAutoSync(fn)` 的语义是「**数据变更后**防抖调度一次同步」。
把它写在 `syncToDisclosureNotes()` **内部**等于调度自己 → 800ms 后再发一次同样的 POST。

两种形态：

**形态 A（8 处：G1 / G2×2 / G3×2 / G6 / H3×2）** —— 成功分支末尾多调一次：

    ElMessage.success(`已同步 ${rows} 行到附注…`)
    autoSync.scheduleAutoSync(syncToDisclosureNotes)   // ← 删掉
    } catch { … }

用户在一次成功同步后会再收到一条莫名的「同步附注失败」（J1 浏览器实测确认过该现象）。

**形态 B（8 处：I4 / I5 / I6 / K1 各 2）** —— **无条件自递归**，更严重：

    async function syncToDisclosureNotes() {
      await disc.syncToNotes()
      autoSync.scheduleAutoSync(syncToDisclosureNotes)  // ← 每次调用都排下一次
    }

实测这 8 个文件里 `scheduleAutoSync` **只出现这一次** → ①用户点一次同步就进入
800ms 周期的无限 POST（直到组件卸载 `cancelPending`）②「自动同步」从未接到任何
数据变更，是**假接入**，而覆盖率守卫 `disclosureAutoSyncCoverage.spec.ts` 只看
「有没有 `scheduleAutoSync`」→ 被这行自递归骗过（与 F2 只 watch 横幅可见性的
「假接入」同款教训）。

故形态 B 不是删一行就完事，必须**真正接上数据变更**：`watch(实际数据, …, { deep: true })`。
watch 目标取自各 `useXDisclosure` 暴露的源数据 ref（不取 `totals` 这类派生 computed）。

🔴 **不加 `_xxxMounted` 一次性防护**（平台铁律：该防护会吞掉"切走再切回后的第一次编辑"；
Vue `watch` 默认 `immediate:false`，挂载本身不触发，本不需要）。

Usage::

    python backend/scripts/fix/fix_disclosure_self_schedule.py --dry-run
    python backend/scripts/fix/fix_disclosure_self_schedule.py
    python backend/scripts/fix/fix_disclosure_self_schedule.py --check

spec: .kiro/specs/j1-disclosure-template-alignment/（Task 17 横向推广）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
WP = _REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

SELF_SCHEDULE_LINE = re.compile(
    r"[ \t]*autoSync\.scheduleAutoSync\(syncToDisclosureNotes\)[ \t]*\r?\n"
)

# ─────────────────── 形态 A：删成功分支里多余的那一行 ───────────────────

FORM_A = [
    "g2-interest-receivable/G2TabDisclosureListed.vue",
    "g2-interest-receivable/G2TabDisclosureSOE.vue",
    "g3-dividend-receivable/G3TabDisclosureListed.vue",
    "g3-dividend-receivable/G3TabDisclosureSOE.vue",
]

# ─────────────────── 形态 B：去自递归 + 接数据变更 ───────────────────
#
# 每条二选一：
#   `disc` + `targets` —— composable 暴露了源数据 ref，watch `() => disc.xxx`
#   `exprs`            —— 无独立 ref（数据在 form data / snapshot 里），直接 watch
#                         **构建同步载荷的表达式**，最忠实于「监听与 syncToDisclosureNotes
#                         构建载荷所用字段一致」这条铁律（不会漏也不会误加）
#
# 🔴 G1SOE / G6SOE / H3×2 原属形态 A，但删掉那一行后 `scheduleAutoSync` 一次不剩
#    —— 说明它们的自动同步**也只靠那行自调度撑着**（同款假接入），由加固后的
#    `disclosureAutoSyncCoverage` 守卫当场暴露 → 一并接上真实数据变更。

FORM_B: dict[str, dict[str, object]] = {
    "g1-trading-financial-assets/core/G1TabDisclosureSOE.vue": {
        # 载荷 = buildG1SoeSyncPayloads(..., dis.getSyncSnapshot())
        "exprs": ["() => JSON.stringify(dis.getSyncSnapshot())"],
    },
    "g6-other-bond-investment-main/core/G6TabDisclosureSOE.vue": {
        # 载荷 = buildSyncData()（内部已含 `_note_texts: noteText`）
        "exprs": ["() => JSON.stringify(buildSyncData())"],
    },
    "h3/core/H3TabDisclosureListed.vue": {
        "exprs": [
            "() => getSectionRows('cost-original')",
            "() => getSectionRows('cost-dep')",
            "() => getSectionRows('cost-impair')",
            "() => getSectionRows('fair-change')",
            "() => sectionTexts",
        ],
    },
    "h3/core/H3TabDisclosureSoe.vue": {
        "exprs": [
            "() => getSectionRows('soe-cost')",
            "() => getSectionRows('soe-cost-dep')",
            "() => getSectionRows('cost-impair')",
            "() => getSectionRows('soe-fair-change')",
            "() => sectionTexts",
        ],
    },
    "i4/core/I4TabDisclosureListed.vue": {
        "disc": "disc",
        "targets": ["rows", "currentPortion", "footnote", "otherNote", "auditNote", "auditConclusion"],
    },
    "i4/core/I4TabDisclosureSoe.vue": {
        "disc": "disc",
        "targets": ["rows", "currentPortion", "footnote", "otherNote", "auditNote", "auditConclusion"],
    },
    "i5/core/I5TabDisclosureListed.vue": {
        "disc": "disc",
        "targets": ["rows", "otherNote", "auditNote", "auditConclusion"],
    },
    "i5/core/I5TabDisclosureSoe.vue": {
        "disc": "disc",
        "targets": ["rows", "otherNote", "auditNote", "auditConclusion"],
    },
    "i6/core/I6TabDisclosureListed.vue": {
        "disc": "disc",
        "targets": [
            "rows", "capitalizationNote", "projectsNote", "supplementNote",
            "auditNote", "auditConclusion",
        ],
    },
    "i6/core/I6TabDisclosureSoe.vue": {
        "disc": "disc",
        "targets": [
            "rows", "capitalizationNote", "projectsNote", "supplementNote",
            "auditNote", "auditConclusion",
        ],
    },
    "k1/core/K1TabDisclosureListed.vue": {
        "disc": "disc",
        "targets": [
            "agingRows", "natureRows", "stage1Rows", "stage2Rows", "stage3Rows",
            "priorStage1Rows", "priorStage2Rows", "priorStage3Rows", "stageMovements",
            "top5Rows", "reversalRows", "continuedInvolvementRows", "noteText",
        ],
    },
    "k1/core/K1TabDisclosureSoe.vue": {
        "disc": "dis",
        "targets": [
            "agingRows", "methodRows", "individualDetailRows", "portfolioAgingRows",
            "otherPortfolioRows", "continuedInvolvementRows", "stageMovements",
            "balanceStageMovements", "top5Rows", "reversalRows", "writeoffDetailRows",
            "govGrantRows", "transferRows", "noteText",
        ],
    },
}

WATCH_MARKER = "// [auto-sync] 监听实际数据"


def _build_watch_block(sources: list[str]) -> str:
    items = ",\n".join(f"    {s}" for s in sources)
    return (
        f"{WATCH_MARKER}（历史实现是 syncToDisclosureNotes 里调度自己 → 800ms 周期无限 POST，\n"
        "// 且让 disclosureAutoSyncCoverage 守卫误判为「已接自动同步」= 假接入）。\n"
        "// 🔴 不加 `_xxxMounted` 一次性防护：Vue watch 默认 immediate:false，挂载本身不触发；\n"
        "//    该防护会吞掉「切走再切回后的第一次编辑」（平台铁律）。\n"
        "watch(\n"
        "  [\n"
        f"{items},\n"
        "  ],\n"
        "  () => autoSync.scheduleAutoSync(syncToDisclosureNotes),\n"
        "  { deep: true },\n"
        ")\n"
    )


def _ensure_watch_import(text: str) -> tuple[str, bool]:
    """确保 `import { ... } from 'vue'` 含 `watch`。"""
    m = re.search(r"import \{([^}]*)\} from 'vue'", text)
    if not m:
        return text, False
    names = [n.strip() for n in m.group(1).split(",") if n.strip()]
    if "watch" in names:
        return text, False
    names.append("watch")
    return text[: m.start(1)] + " " + ", ".join(names) + " " + text[m.end(1):], True


def fix_form_a(path: Path, text: str) -> tuple[str, list[str]]:
    """删掉 `syncToDisclosureNotes` 函数体内的自调度行（只删函数体内的）。"""
    span = _sync_fn_span(text)
    if span is None:
        return text, [f"[WARN] {path.name} 未找到 syncToDisclosureNotes"]
    a, b = span
    inner = text[a:b]
    new_inner, n = SELF_SCHEDULE_LINE.subn("", inner)
    if n == 0:
        return text, []
    return text[:a] + new_inner + text[b:], [f"删除自调度行 ×{n}"]


def _sync_fn_span(text: str) -> tuple[int, int] | None:
    m = re.search(r"\b(?:async\s+)?function\s+syncToDisclosureNotes\s*\(", text)
    if not m:
        return None
    open_idx = text.find("{", m.end())
    if open_idx < 0:
        return None
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return (open_idx, i + 1)
    return None


def _watch_sources(spec: dict[str, object]) -> list[str]:
    if "exprs" in spec:
        return [str(e) for e in spec["exprs"]]  # type: ignore[union-attr]
    disc = str(spec["disc"])
    return [f"() => {disc}.{t}" for t in spec["targets"]]  # type: ignore[union-attr]


def fix_form_b(path: Path, text: str, spec: dict[str, object]) -> tuple[str, list[str]]:
    changes: list[str] = []
    sources = _watch_sources(spec)

    span = _sync_fn_span(text)
    if span is None:
        return text, [f"[WARN] {path.name} 未找到 syncToDisclosureNotes"]
    a, b = span
    inner = text[a:b]
    new_inner, n = SELF_SCHEDULE_LINE.subn("", inner)
    if n:
        text = text[:a] + new_inner + text[b:]
        changes.append(f"去自递归 ×{n}")

    if WATCH_MARKER not in text:
        block = _build_watch_block(sources)
        # 插到 `onBeforeUnmount(...cancelPending())` 之前（两种写法都试），否则放 script 末尾
        for anchor in (
            "onBeforeUnmount(() => autoSync.cancelPending())",
            "onBeforeUnmount(() => { autoSync.cancelPending() })",
            "onBeforeUnmount(() => {\n  autoSync.cancelPending()",
        ):
            if anchor in text:
                text = text.replace(anchor, block + "\n" + anchor, 1)
                break
        else:
            m = re.search(r"\n</script>", text)
            if m is None:
                return text, changes + [f"[WARN] {path.name} 找不到插入点"]
            text = text[: m.start()] + "\n" + block + text[m.start():]
        changes.append(f"接入数据变更 watch（{len(sources)} 个数据源）")

    text, added = _ensure_watch_import(text)
    if added:
        changes.append("import { watch } from 'vue'")
    return text, changes


def check_file(path: Path, form_b: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errs: list[str] = []
    span = _sync_fn_span(text)
    if span is None:
        errs.append("未找到 syncToDisclosureNotes")
        return errs
    a, b = span
    if SELF_SCHEDULE_LINE.search(text[a:b]):
        errs.append("syncToDisclosureNotes 内仍在调度自己")
    if form_b:
        if WATCH_MARKER not in text:
            errs.append("未接入数据变更 watch（自动同步仍是假接入）")
        if not re.search(r"import \{[^}]*\bwatch\b[^}]*\} from 'vue'", text):
            errs.append("未 import watch")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="修掉披露 Tab 的同步自触发（幂等）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

    ok = True
    for rel in FORM_A + list(FORM_B):
        path = WP / rel
        form_b = rel in FORM_B
        if not path.exists():
            print(f"[FATAL] 缺文件 {rel}")
            ok = False
            continue

        if args.check:
            errs = check_file(path, form_b)
            print(f"{'[FAIL]' if errs else '[OK]  '} {rel}" + ("" if not errs else "  " + "; ".join(errs)))
            ok = ok and not errs
            continue

        text = path.read_text(encoding="utf-8")
        if form_b:
            new_text, changes = fix_form_b(path, text, FORM_B[rel])
        else:
            new_text, changes = fix_form_a(path, text)
        if not changes:
            print(f"[SKIP] {rel}（已修）")
            continue
        print(f"[FIX ] {rel}  " + "; ".join(changes))
        if not args.dry_run:
            path.write_text(new_text, encoding="utf-8")

    if args.dry_run:
        print("\n[dry-run] 未写文件")
    print("\n[OK] 全部通过" if ok else "\n[FAIL] 存在未通过项")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
