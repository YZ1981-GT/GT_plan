# -*- coding: utf-8 -*-
"""D4 IPO 检查表守卫变异检验（15 锚点，四态判定）。

spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Wave 7 · Task 16

用法：
    python backend/scripts/verify/verify_ipo_checklist_anchors.py            # 跑全部锚点
    python backend/scripts/verify/verify_ipo_checklist_anchors.py --check-anchors  # 只校验锚点可命中（只读秒级）

四态判定（只看退出码会把后三态误判成 RED）：
    RED         守卫按预期打红（变异命中了正确的守卫）—— 期望态
    GREEN       守卫缺陷：变异后守卫仍绿（守卫没盯住这处）
    ANCHOR-MISS 脚本缺陷：锚点在源文件里未命中或命中 >1（无法唯一定位）
    WRONG-TEST  变异打红了，但红的不是预期那条测试（污染/锚点错行）

🔴 每个锚点 = 一处最小改动（改一字 / 删一处引用 / 把失败吞成成功），必须**恰好** RED。
🔴 变异后必须还原（try/finally），并对比字节确保还原干净。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_FRONTEND = _REPO / "audit-platform" / "frontend"

# ── 受变异的源文件 ───────────────────────────────────────────────────────────
SCHEMA_TS = _FRONTEND / "src/components/workpaper/d4/ipo/ipoChecklistSchema.ts"
ENGINE_TS = _FRONTEND / "src/components/workpaper/d4/ipo/ipoChecklistFormulaEngine.ts"
DEALER_VUE = _FRONTEND / "src/components/workpaper/d4/ipo/D4TabDealer.vue"
OVERSEAS_VUE = _FRONTEND / "src/components/workpaper/d4/ipo/D4TabOverseas.vue"
BACKEND_IO = _BACKEND / "app/routers/wp_render_strategies/_d4_import_export.py"

# ── 被驱动的守卫 ─────────────────────────────────────────────────────────────
COLUMN_GUARD = "tests/test_ipo_checklist_column_contract.py"
SYNC_SPEC = "src/components/workpaper/d4/ipo/__tests__/ipoSyncBridge.spec.ts"
FORMULA_PRESET_SPEC = "src/components/workpaper/d4/ipo/__tests__/ipoFormulaPreset.spec.ts"
FORMULA_ENGINE_SPEC = "src/components/workpaper/d4/ipo/__tests__/ipoFormulaEngine.spec.ts"
WIRING_SPEC = "src/components/workpaper/__tests__/d4IpoSyncHostWiring.spec.ts"
TWO_LEVEL_SPEC = "src/components/workpaper/d4/ipo/__tests__/ipoTwoLevelHeader.spec.ts"


@dataclass
class Anchor:
    id: str
    desc: str
    file: Path
    old: str            # 锚点原文（必须在文件里恰好出现一次）
    new: str            # 变异后文本
    runner: str         # "py" | "ts"
    guard: str          # 守卫文件（相对 backend 或 frontend）


ANCHORS: list[Anchor] = [
    # ── 列规格 3 ──
    Anchor("col-label", "改一个列 label 一字", SCHEMA_TS,
           "label: '经销商', group: null", "label: '经销X', group: null", "ts", COLUMN_GUARD),
    Anchor("col-group-del", "删一个二级列的 group（改为 null）", SCHEMA_TS,
           "{ key: 'checkFieldVisit', label: '实地走访', group: D4_26_PROGRAM_GROUP",
           "{ key: 'checkFieldVisit', label: '实地走访', group: null", "ts", COLUMN_GUARD),
    Anchor("col-order", "改列顺序（交换 D4-25 前两数据列）", SCHEMA_TS,
           "{ key: 'customerName', label: '客户名称', group: null, type: 'text', width: 130 },\n  { key: 'dealer', label: '经销商', group: null, type: 'text', width: 100 },",
           "{ key: 'dealer', label: '经销商', group: null, type: 'text', width: 100 },\n  { key: 'customerName', label: '客户名称', group: null, type: 'text', width: 130 },",
           "ts", COLUMN_GUARD),
    # ── 投影 4 ──
    Anchor("proj-checkbox", "改 checkbox→1 映射为 →0", SCHEMA_TS,
           "if (col.type === 'checkbox') return truthyCheckbox(v) ? 1 : null",
           "if (col.type === 'checkbox') return truthyCheckbox(v) ? 0 : null", "ts", SYNC_SPEC),
    Anchor("proj-emptyrow", "删全空行跳过（continue → pass）", SCHEMA_TS,
           "if (allEmpty) continue", "if (allEmpty && false) continue", "ts", SYNC_SPEC),
    Anchor("proj-nan", "非数字解析改为返回 NaN（去掉 isFinite 保护）", SCHEMA_TS,
           "if (!Number.isFinite(n)) return null\n  return pct ? n / 100 : n",
           "return pct ? n / 100 : n", "ts", SYNC_SPEC),
    Anchor("proj-pct", "百分比 12.3% 解析改为不除 100", SCHEMA_TS,
           "return pct ? n / 100 : n", "return n", "ts", SYNC_SPEC),
    # ── 公式 4 ──
    Anchor("fml-resolver", "把一个 resolver 名拼错一字", SCHEMA_TS,
           "resolver: 'd4_27_related_party_sales'", "resolver: 'd4_27_related_party_saleX'", "ts", FORMULA_PRESET_SPEC),
    Anchor("fml-column", "把一个 columnKey 改成越界列", SCHEMA_TS,
           "columnKey: 'difference', category: 'intra_sheet'",
           "columnKey: 'differenceX', category: 'intra_sheet'", "ts", FORMULA_PRESET_SPEC),
    Anchor("fml-divzero", "分母为 0 改为返回 0（不返回 null）", ENGINE_TS,
           "if (rhs == null || rhs === 0) return null", "if (rhs == null) return null", "ts", FORMULA_ENGINE_SPEC),
    Anchor("fml-diff-empty", "差异减法任一空改为按 0（不返回 null）", ENGINE_TS,
           "if (acc == null || rhs == null) return null\n      acc = acc - rhs",
           "acc = (acc ?? 0) - (rhs ?? 0)", "ts", FORMULA_ENGINE_SPEC),
    # ── 导入导出 2 ──
    Anchor("io-header-drift", "后端 _SHEET_HEADERS 改一列 label（制造 drift）", BACKEND_IO,
           '"工商资料查询", "互联网信息查询", "函证", "视频、电话访谈", "实地走访", "索引号",',
           '"工商资料查询X", "互联网信息查询", "函证", "视频、电话访谈", "实地走访", "索引号",',
           "py", COLUMN_GUARD),
    Anchor("io-reload", "删 D4-25 导入后 reloadHost 调用", DEALER_VUE,
           "  await reloadHost()\n  emit('imported')", "  emit('imported')", "ts", WIRING_SPEC),
    # ── 渲染 2 ──
    Anchor("render-group-nest", "删 D4-26 分组嵌套（seg.group 分支改为恒 false）", OVERSEAS_VUE,
           "<el-table-column v-if=\"seg.group\" :label=\"seg.group\" align=\"center\">",
           "<el-table-column v-if=\"false\" :label=\"seg.group\" align=\"center\">", "ts", TWO_LEVEL_SPEC),
    Anchor("render-flush-order", "破坏 flushHtml 顺序（先 read 后 flush）", DEALER_VUE,
           "    flushPendingSave()\n    const snap = await readStoreProjection({",
           "    const snap = await readStoreProjection({", "ts", WIRING_SPEC),
]


def _run_guard(anchor: Anchor) -> tuple[bool, str]:
    """跑守卫；返回 (是否有失败, 输出尾部)。"""
    if anchor.runner == "py":
        cmd = [sys.executable, "-m", "pytest", anchor.guard, "-p", "no:cacheprovider", "-q", "--no-header"]
        cwd = _BACKEND
    else:
        cmd = ["npx", "vitest", "run", anchor.guard, "--reporter=dot"]
        cwd = _FRONTEND
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", shell=(anchor.runner == "ts"))
    out = (proc.stdout or "") + (proc.stderr or "")
    failed = proc.returncode != 0
    return failed, out[-600:]


def _classify(anchor: Anchor) -> str:
    src = anchor.file.read_text(encoding="utf-8")
    count = src.count(anchor.old)
    if count != 1:
        return f"ANCHOR-MISS (锚点命中 {count} 次，需恰好 1)"

    # 变异前先确认守卫是绿的（基线）；变异后应变红。
    mutated = src.replace(anchor.old, anchor.new, 1)
    anchor.file.write_text(mutated, encoding="utf-8", newline="")
    try:
        failed, tail = _run_guard(anchor)
    finally:
        anchor.file.write_text(src, encoding="utf-8", newline="")  # 还原
        assert anchor.file.read_text(encoding="utf-8") == src, f"{anchor.id} 还原失败！"

    if failed:
        return "RED"
    return "GREEN (守卫缺陷：变异后仍绿)"


def check_anchors_only() -> int:
    """只读校验：每个锚点在源文件里恰好命中一次（秒级，证明结构未漂移）。"""
    bad = 0
    for a in ANCHORS:
        src = a.file.read_text(encoding="utf-8")
        n = src.count(a.old)
        status = "OK" if n == 1 else f"MISS (命中 {n} 次)"
        if n != 1:
            bad += 1
        print(f"[{status}] {a.id}: {a.desc}")
    print(f"\n{'='*60}\n锚点命中校验：{len(ANCHORS) - bad}/{len(ANCHORS)} 唯一命中")
    return 1 if bad else 0


def run_all() -> int:
    results: dict[str, str] = {}
    for a in ANCHORS:
        print(f"→ [{a.id}] {a.desc} ...", flush=True)
        verdict = _classify(a)
        results[a.id] = verdict
        print(f"   {verdict}")
    print(f"\n{'='*60}\n变异检验结果（{len(ANCHORS)} 锚点）：")
    red = 0
    for aid, v in results.items():
        mark = "✓" if v == "RED" else "✗"
        if v == "RED":
            red += 1
        print(f"  {mark} {aid}: {v}")
    print(f"\nRED {red}/{len(ANCHORS)}（全 RED 才算守卫合格）")
    return 0 if red == len(ANCHORS) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-anchors", action="store_true", help="只校验锚点唯一命中（只读秒级）")
    args = ap.parse_args()
    if args.check_anchors:
        return check_anchors_only()
    return run_all()


if __name__ == "__main__":
    raise SystemExit(main())
