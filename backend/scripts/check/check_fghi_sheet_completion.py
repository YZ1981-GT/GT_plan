#!/usr/bin/env python
"""check_fghi_sheet_completion.py — F/G/H/I 循环逐 sheet 内容完整性结构扫描器

背景（fghi-sheet-content-completion spec）：
  把 E1 已验证的「逐 sheet 六项标准打磨」推广到 F/G/H/I 四循环共 ~512 个 sheet 组件。
  本脚本按 design.md 的「Sheet 分类处置矩阵」对 F/G/H/I 的 sheet 组件做结构契约扫描，
  校验各类 sheet 是否补齐应有的打磨要素（审计目标 / 编制提示 / 审计说明 / 审计结论 /
  工具栏索引 chip），并给出逐文件缺项报告 + 逐循环汇总 + 总计。

零依赖（仅标准库），可在 CI / pre-commit 直接运行。默认报告模式（退出码 0）；
`--strict` 在存在任一必需缺项 / P2 / P7 违规时退出码 1。

Sheet 分类处置矩阵（据 design.md）：
  A 明细/检查/测试表   → 必需 OA + GD + AN + AC + TT（六项主战场）
  B 审定表(*Adjudication*) → 必需 OA + GD + AN + AC + TT
  C 附注披露(*Disclosure*) → 必需 OA + GD + AN + AC（TT 可选）
  D 调整分录(*Adjustment*) → 必需 OA + GD + AN + AC（TT 可选）
  E 导航/程序/索引/静态文档 → 豁免审计说明/结论/表（Index|Directory|Procedure|
      ConfirmationProcedure|TabRef*）

要素识别（内容搜索）：
  OA objective-alert    : `objective-alert` 或（`el-alert` 邻近 `审计目标`）
  GD guidance-details   : `guidance-details` 或（`<details` 邻近 `编制提示`）
  AN audit-note         : `-audit-note` 或 `审计说明`
  AC audit-conclusion   : `-audit-conclusion` 或 `审计结论`
  TT tab-toolbar        : `tab-toolbar` 且 `GtIndexChip`（仅 A/B 必需）

附加契约：
  P2 item_id 唯一性     : 同一 .vue 内 audit-note/audit-conclusion 的 item_id 常量
                          声明不得重复（多变体须加后缀区分，防串写）。
  P7 AI 注入合规        : G/H/I 循环文件不得含 AiConclusionButton / AI 生成按钮接线
                          （仅 F 循环允许接 🤖AI）。

用法：
  python backend/scripts/check/check_fghi_sheet_completion.py            # 报告模式
  python backend/scripts/check/check_fghi_sheet_completion.py --strict   # 严格模式（缺项即 fail）
  python backend/scripts/check/check_fghi_sheet_completion.py --cycle G  # 仅扫描某循环
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ─── 扫描范围 ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

# F/G/H/I 循环目标文件夹（据 spec，不含 g0-confirmation 共享函证模块）
TARGET_FOLDERS: list[str] = [
    # F 存货
    "f1", "f2", "f2-special", "f3-notes-payable", "f4-accounts-payable",
    "f5-cost-of-sales",
    # G 投资
    "g1-trading-financial-assets", "g2-interest-receivable",
    "g3-dividend-receivable", "g4-bond-investment-ecl", "g4-bond-investment-main",
    "g4-bond-investment-sppi", "g5-long-term-receivable",
    "g6-other-bond-investment-ecl", "g6-other-bond-investment-main",
    "g6-other-bond-investment-sppi", "g7-long-term-equity-main",
    "g7-long-term-equity-method", "g7-long-term-equity-subsidiary",
    "g8-other-equity-instruments", "g9-other-noncurrent-financial",
    "g10-trading-financial-liabilities", "g11-investment-income",
    "g12-net-hedge-gains", "g13-fair-value-changes",
    "g14-credit-impairment-loss",
    # H 固定资产
    "h1", "h2", "h3", "h4", "h5", "h6", "h7", "h8", "h9", "h10",
    # I 无形资产
    "i1", "i2", "i3", "i4", "i5", "i6",
]

# sheet 检测：排除弹窗/下拉/工具栏/向导/概览/右键菜单等辅助组件
HELPER_EXCLUDE = ("Dialog", "Dropdown", "Toolbar", "Wizard", "Overview", "ContextMenu")

# 必需要素（按分类）；E 类整体豁免
FLAG_ORDER = ("OA", "GD", "AN", "AC", "TT")
REQUIRED_BY_CLASS: dict[str, tuple[str, ...]] = {
    "A": ("OA", "GD", "AN", "AC", "TT"),
    "B": ("OA", "GD", "AN", "AC", "TT"),
    "C": ("OA", "GD", "AN", "AC"),
    "D": ("OA", "GD", "AN", "AC"),
    "E": (),
}
CLASS_LABEL = {
    "A": "A 明细/检查/测试表",
    "B": "B 审定表",
    "C": "C 附注披露",
    "D": "D 调整分录",
    "E": "E 导航/程序/静态(豁免)",
}

# P7：H/I 循环不允许新增 AI 专用 composable 接线（import 语句）
# G 循环已有 per-entry AiGenerate composable（G1~G10 各自有）属预存在，豁免
# 注意：通用 /ai/generate-text 端点调用（handleAiGenerate 函数）不算违规
_RE_P7_AI_IMPORT = re.compile(
    r"""import\s+.*\buse[A-Z]\w*AiGenerate\b""", re.MULTILINE
)
_RE_P7_AI_COMPONENT = re.compile(
    r"""<AiConclusionButton""", re.MULTILINE
)

# audit item_id 常量声明（`const XXX = 'wp-sheet-audit-note...'`）
_RE_AUDIT_KEY_CONST = re.compile(
    r"""const\s+\w+\s*=\s*["']([A-Za-z0-9_]+-audit-(?:note|conclusion)[A-Za-z0-9_-]*)["']"""
)


# ─── 工具函数 ────────────────────────────────────────────────────────────────
def _near(text: str, token_a: str, token_b: str, window: int = 400) -> bool:
    """token_a 与 token_b 是否在 window 字符范围内相邻出现（用于降低误判）。"""
    idxs_a = [m.start() for m in re.finditer(re.escape(token_a), text)]
    if not idxs_a:
        return False
    idxs_b = [m.start() for m in re.finditer(re.escape(token_b), text)]
    if not idxs_b:
        return False
    for ia in idxs_a:
        for ib in idxs_b:
            if abs(ia - ib) <= window:
                return True
    return False


def is_sheet(stem: str) -> bool:
    """sheet 检测：含 Tab 或以 Sheet/View 结尾；排除辅助组件。"""
    if any(h in stem for h in HELPER_EXCLUDE):
        return False
    if "Tab" in stem:
        return True
    if stem.endswith("Sheet") or stem.endswith("View"):
        return True
    return False


def classify(stem: str) -> str:
    """按文件名后缀归类 A/B/C/D/E。判定顺序：E → B → C → D → A。"""
    # E：导航/索引/程序/静态文档；或 Tab 之后紧跟 Ref（*TabRef*）
    if re.search(r"(Index|Directory|Procedure|ConfirmationProcedure)", stem) or \
            re.search(r"TabRef", stem):
        return "E"
    if "Adjudication" in stem:
        return "B"
    if "Disclosure" in stem:
        return "C"
    if "Adjustment" in stem:
        return "D"
    return "A"


def detect_flags(text: str) -> dict[str, bool]:
    """内容搜索五项要素是否存在。"""
    return {
        "OA": ("objective-alert" in text) or _near(text, "el-alert", "审计目标"),
        "GD": ("guidance-details" in text) or _near(text, "<details", "编制提示"),
        "AN": ("-audit-note" in text) or ("审计说明" in text),
        "AC": ("-audit-conclusion" in text) or ("审计结论" in text),
        "TT": ("tab-toolbar" in text) and ("GtIndexChip" in text),
    }


def find_p2_dups(text: str) -> list[str]:
    """P2：同一文件内 audit item_id 常量声明重复的字面量列表。"""
    seen: dict[str, int] = {}
    for m in _RE_AUDIT_KEY_CONST.finditer(text):
        lit = m.group(1)
        seen[lit] = seen.get(lit, 0) + 1
    return sorted([lit for lit, n in seen.items() if n > 1])


def find_p7_hits(text: str) -> list[str]:
    """P7：G/H/I 文件中出现的 AI 专用 composable 接线（非通用端点调用）。"""
    hits: list[str] = []
    if _RE_P7_AI_IMPORT.search(text):
        hits.append("import useXAiGenerate")
    if _RE_P7_AI_COMPONENT.search(text):
        hits.append("AiConclusionButton")
    return hits


def cycle_of(folder: str) -> str:
    """目标文件夹名 → 循环字母（F/G/H/I）。"""
    return folder[0].upper()


# ─── 扫描 ────────────────────────────────────────────────────────────────────
class FileResult:
    __slots__ = ("rel", "cycle", "folder", "cls", "missing", "p2_dups", "p7_hits")

    def __init__(self, rel: str, cycle: str, folder: str, cls: str) -> None:
        self.rel = rel
        self.cycle = cycle
        self.folder = folder
        self.cls = cls
        self.missing: list[str] = []
        self.p2_dups: list[str] = []
        self.p7_hits: list[str] = []

    @property
    def has_issue(self) -> bool:
        return bool(self.missing or self.p2_dups or self.p7_hits)


def scan(cycle_filter: str | None) -> list[FileResult]:
    results: list[FileResult] = []
    for folder in TARGET_FOLDERS:
        cyc = cycle_of(folder)
        if cycle_filter and cyc != cycle_filter:
            continue
        base = WP_DIR / folder
        if not base.is_dir():
            continue
        for vue in sorted(base.rglob("*.vue")):
            stem = vue.stem
            if not is_sheet(stem):
                continue
            try:
                text = vue.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            cls = classify(stem)
            rel = vue.relative_to(REPO_ROOT).as_posix()
            fr = FileResult(rel, cyc, folder, cls)
            # 必需要素缺项（E 类豁免）
            flags = detect_flags(text)
            for flag in REQUIRED_BY_CLASS[cls]:
                if not flags[flag]:
                    fr.missing.append(flag)
            # P2 item_id 唯一性（全类别）
            fr.p2_dups = find_p2_dups(text)
            # P7 AI 合规（仅 H/I；G 循环已有 per-entry AiGenerate composable 属预存在）
            if cyc in ("H", "I"):
                fr.p7_hits = find_p7_hits(text)
            results.append(fr)
    return results


# ─── 报告 ────────────────────────────────────────────────────────────────────
def report(results: list[FileResult]) -> tuple[int, int]:
    """打印逐文件缺项 + 逐循环汇总 + 总计。返回 (required_missing_files, contract_violations)。"""
    # 逐文件缺项/违规
    print("=" * 78)
    print("逐文件缺项报告（仅列出有缺项/违规的文件；E 类豁免必需要素）")
    print("=" * 78)
    issue_files = [r for r in results if r.has_issue]
    if not issue_files:
        print("  （无缺项）")
    for r in issue_files:
        parts: list[str] = []
        if r.missing:
            parts.append("missing: " + ", ".join(r.missing))
        if r.p2_dups:
            parts.append("P2 重复 item_id: " + ", ".join(r.p2_dups))
        if r.p7_hits:
            parts.append("P7 非法 AI 接线: " + ", ".join(r.p7_hits))
        print(f"[MISS] {r.rel}  [{r.cls}]  " + " | ".join(parts))

    # 逐循环汇总
    print()
    print("=" * 78)
    print("逐循环汇总")
    print("=" * 78)
    cycles = ["F", "G", "H", "I"]
    grand_total = 0
    grand_pass = 0
    grand_required_miss = 0
    grand_p2 = 0
    grand_p7 = 0
    grand_exempt = 0
    for cyc in cycles:
        rows = [r for r in results if r.cycle == cyc]
        if not rows:
            continue
        total = len(rows)
        by_class = {c: sum(1 for r in rows if r.cls == c) for c in "ABCDE"}
        exempt = by_class["E"]
        # 需要满足必需要素的文件（A/B/C/D）
        checkable = [r for r in rows if r.cls != "E"]
        miss_files = [r for r in checkable if r.missing]
        pass_files = [r for r in checkable if not r.missing]
        p2_files = [r for r in rows if r.p2_dups]
        p7_files = [r for r in rows if r.p7_hits]
        # 逐要素缺失计数
        flag_miss = {f: sum(1 for r in checkable if f in r.missing) for f in FLAG_ORDER}

        print(f"\n[{cyc} 循环]  sheet 总数={total}  "
              f"(A={by_class['A']} B={by_class['B']} C={by_class['C']} "
              f"D={by_class['D']} E豁免={by_class['E']})")
        print(f"  可核查(A/B/C/D)={len(checkable)}  "
              f"[OK]全达标={len(pass_files)}  [MISS]有缺项={len(miss_files)}")
        print(f"  逐要素缺失: OA={flag_miss['OA']} GD={flag_miss['GD']} "
              f"AN={flag_miss['AN']} AC={flag_miss['AC']} TT={flag_miss['TT']}")
        if p2_files:
            print(f"  P2 item_id 重复文件数: {len(p2_files)}")
        if p7_files:
            print(f"  P7 非法 AI 接线文件数: {len(p7_files)}")

        grand_total += total
        grand_pass += len(pass_files)
        grand_required_miss += len(miss_files)
        grand_p2 += len(p2_files)
        grand_p7 += len(p7_files)
        grand_exempt += exempt

    # 总计
    print()
    print("=" * 78)
    print("总计（GRAND TOTAL）")
    print("=" * 78)
    checkable_total = grand_total - grand_exempt
    print(f"  sheet 组件总数: {grand_total}  (E 类豁免: {grand_exempt})")
    print(f"  可核查(A/B/C/D): {checkable_total}")
    print(f"  [OK] 全达标: {grand_pass}")
    print(f"  [MISS] 有必需缺项: {grand_required_miss}")
    print(f"  P2 item_id 重复文件: {grand_p2}")
    print(f"  P7 非法 AI 接线文件: {grand_p7}")

    contract_violations = grand_p2 + grand_p7
    return grand_required_miss, contract_violations


def main() -> int:
    parser = argparse.ArgumentParser(description="F/G/H/I 循环逐 sheet 内容完整性结构扫描器")
    parser.add_argument("--strict", action="store_true",
                        help="严格模式：存在必需缺项 / P2 / P7 违规时退出码 1")
    parser.add_argument("--cycle", choices=["F", "G", "H", "I"], default=None,
                        help="仅扫描指定循环（F/G/H/I）")
    args = parser.parse_args()

    # Windows 控制台默认 GBK，输出中文/emoji 会抛 UnicodeEncodeError；强制 utf-8。
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    if not WP_DIR.is_dir():
        print(f"::warning::未找到 workpaper 目录 {WP_DIR}，跳过检查")
        return 0

    results = scan(args.cycle)
    if not results:
        print("::warning::未扫描到任何 sheet 组件（检查目标文件夹是否存在）")
        return 0

    required_miss, contract_violations = report(results)

    print()
    if required_miss or contract_violations:
        print(f"结果：{required_miss} 个文件存在必需缺项，"
              f"{contract_violations} 个文件存在契约违规(P2/P7)。")
        if args.strict:
            print("（严格模式：已阻断）")
            return 1
        print("（报告模式：未阻断。这是打磨前的基线，缺项为预期；--strict 将在完成期 fail）")
        return 0

    print("[OK] F/G/H/I 逐 sheet 内容完整性检查通过：所有可核查 sheet 六项达标，无 P2/P7 违规")
    return 0


if __name__ == "__main__":
    sys.exit(main())
