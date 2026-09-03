# -*- coding: utf-8 -*-
"""前端悬空引用门禁的变异检验（四态：RED / GREEN / ANCHOR-MISS / HARNESS-WRITE-FAILED）。

把 2026-09-03 修掉的每一类缺陷各重新注入一次，要求门禁打红。没打红 = 门禁有洞。

两类变异：
* `dangling`  —— 删掉一条 import / 一个实例化，制造「引用了不存在的名字」；
  判据落在 `no-undef` 那条上。
* `missing_export` —— 删掉共享模型的一个 export，制造消费方 import 不到；
  判据落在 `vite optimize` 那条上。
* `abuse` —— 往豁免表塞一个真函数名，判据落在反滥用那条上。

harness 铁律（沿用 Task 61 变异脚本踩过的坑）：pristine 快照起手统一拍、finally 里无条件
全量写回；起手先跑一次基线，红了就拒绝拍快照（否则上一轮残留会被当 pristine，级联出假结论）。

用法::

    python backend/scripts/diagnose/mutate_frontend_dangling_reference_gate.py --check-anchors
    python backend/scripts/diagnose/mutate_frontend_dangling_reference_gate.py --run all
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
FE = _REPO / "audit-platform" / "frontend" / "src"
GATE = _REPO / "backend" / "scripts" / "check" / "check_frontend_dangling_reference_gate.py"
EXEMPTIONS = _REPO / "backend" / "data" / "frontend_dangling_reference_exemptions.json"

@dataclass(frozen=True)
class Mutation:
    mid: str
    kind: str
    target: Path
    anchor: str
    replacement: str
    intent: str


def _m(mid: str, rel: str, anchor: str, replacement: str, intent: str, kind: str = "dangling") -> Mutation:
    return Mutation(mid, kind, FE / rel, anchor, replacement, intent)


MUTATIONS: tuple[Mutation, ...] = (
    _m("M01", "components/workpaper/PrefillDiffPanel.vue",
       "const prefs = useDisplayPrefsStore()\n", "",
       "删掉 store 实例化 —— 模板 formatVal 调 prefs.fmt，面板一打开白屏"),
    _m("M02", "components/workpaper/composables/useH3CrossSheet.ts",
       "  isH3ImpairmentSubject,\n", "",
       "删掉一个判定的 import —— 调整分录汇总一算就抛"),
    _m("M03", "components/workpaper/composables/useF3DisclosureSoe.ts",
       "import { calcSubtotal, parseNum } from './useF3FormulaEngine'",
       "import { calcSubtotal } from './useF3FormulaEngine'",
       "删掉 parseNum —— 披露表录金额就抛"),
    _m("M04", "components/workpaper/composables/useF2FormData.ts",
       "import { normalizeApplicableStandards } from './applicableStandards'\n", "",
       "删掉 normalizeApplicableStandards —— 加载项目上下文就抛"),
    _m("M05", "components/workpaper/composables/useG8VoucherCheck.ts",
       "import { G8_ACCOUNT_CODE } from './g8Constants'\n", "",
       "删掉 G8_ACCOUNT_CODE —— 推送 A13 的确认框就抛"),
)
MUTATIONS = MUTATIONS + (
    _m("M06", "components/workpaper/GtK4OtherCurrentLiabilities.vue",
       "    const k4Codes = k4QueryCodes((props.htmlData as any)?.tb_source_codes)\n", "",
       "删掉 K4 局部码集 —— TB 自动取数就抛"),
    _m("M07", "components/workpaper/GtK6HeldForSale.vue",
       "    const k6AssetCodes = k6QueryCodes((props.htmlData as any)?.tb_source_codes)\n", "",
       "删掉 K6 资产码集 —— 审定回写/TB 取数就抛"),
    _m("M08", "components/workpaper/d2/D2TabAnalysis.vue",
       "import { createExcelJsWorkbook, loadExcelJsWorkbook } from '../composables/useExcelIO'\n", "",
       "删掉 ExcelJS 两个入口 —— 导出/导入 xlsx 就抛"),
    _m("M09", "components/workpaper/confirmation/GtConfirmationSummary.vue",
       "import { ElMessage, ElMessageBox } from 'element-plus'",
       "import { ElMessage } from 'element-plus'",
       "删掉 ElMessageBox —— 从 H0-2 带入就抛"),
    _m("M10", "components/workpaper/g12-net-hedge-gains/hedging/G12TabNetExposureCheck.vue",
       "import { ElMessage } from 'element-plus'\n", "",
       "删掉 ElMessage —— 同步净头寸就抛"),
    _m("M11", "components/workpaper/h9/core/H9TabDetail.vue",
       "  mergeH9LedgerRows,\n", "",
       "删掉 mergeH9LedgerRows —— 从序时账取数就抛"),
    _m("M12", "views/TrialBalance.vue",
       "    const { data } = await api.get(", "    const { data } = await http.get(",
       "把 api 换回不存在的 http —— 余额校验就抛"),
)
MUTATIONS = MUTATIONS + (
    _m("M13", "components/workpaper/h1/inspection/H1TabRelatedParty.vue",
       "      saveAuditNote()\n      ElMessage.success('AI 已生成关联交易审计说明')",
       "      saveNote()\n      ElMessage.success('AI 已生成关联交易审计说明')",
       "把 saveAuditNote 改回不存在的 saveNote —— AI 生成后就抛"),
    _m("M14", "components/workpaper/composables/shared/plAdjudicationModel.ts",
       "export function parseNum(", "function parseNum(",
       "共享模型的 parseNum 去掉 export —— 6 个 K 引擎 re-export 不到，"
       "vite optimize 报缺失导出、dev server 起不来",
       "missing_export"),
    _m("M15", "components/workpaper/composables/useK9FormulaEngine.ts",
       "export { parseNum, calcAuditedAmount }\n", "",
       "K9 去掉 re-export —— 消费方 import 不到（这正是 2026-08-02 那次改瘦的形态）",
       "missing_export"),
)

#: 反滥用变异：往豁免表塞一个**真函数**名（parseNum 全库大量调用位置），
#: 模拟「打红就加一行豁免」的滥用姿势。门禁的 never_called 判据必须抓住它。
ABUSE_MUTATION = Mutation(
    "M16", "abuse", EXEMPTIONS,
    '    { "name": "EventListener", "source": "lib.dom.d.ts", "reason": "addEventListener 回调的类型标注" },',
    '    { "name": "EventListener", "source": "lib.dom.d.ts", "reason": "addEventListener 回调的类型标注" },\n'
    '    { "name": "parseNum", "source": "假称是类型", "reason": "用豁免掩盖一个真的悬空函数" },',
    "往豁免表塞真函数名 parseNum —— 反滥用判据必须打红",
)

ALL_MUTATIONS: tuple[Mutation, ...] = MUTATIONS + (ABUSE_MUTATION,)


def _run_gate(skip_optimize: bool) -> int:
    cmd = [sys.executable, str(GATE)]
    if skip_optimize:
        cmd.append("--skip-optimize")
    proc = subprocess.run(cmd, cwd=str(_REPO), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode


def check_anchors() -> int:
    bad = 0
    for m in ALL_MUTATIONS:
        text = m.target.read_text(encoding="utf-8")
        hits = text.count(m.anchor)
        if hits != 1:
            bad += 1
        print(f"{m.mid} [{m.kind}] " + ("OK" if hits == 1 else f"ANCHOR-MISS(hits={hits})")
              + f"  {m.target.name} :: {m.intent}")
    print(f"anchors {len(ALL_MUTATIONS) - bad}/{len(ALL_MUTATIONS)} OK")
    return 1 if bad else 0

def run_all(only: set[str] | None = None) -> int:
    """变异前先跑基线；红了拒绝拍 pristine 快照（防上一轮残留被当基线级联假结论）。"""
    pre = _run_gate(skip_optimize=False)
    if pre != 0:
        print("HARNESS-DIRTY-TREE：变异前门禁就是红的，拒绝拍 pristine 快照。"
              "先把工作树恢复干净（很可能是上一轮变异残留）再跑。")
        return 2
    selected = [m for m in ALL_MUTATIONS if not only or m.mid in only]
    targets = {m.target for m in selected}
    pristine: dict[Path, str] = {}
    for t in targets:
        text = t.read_text(encoding="utf-8")
        # 🔴 快照完整性校验：本 harness 曾把 TrialBalance.vue 整文件清空（4491 行 -> 0）。
        #    机制是「快照拍在一个已被上一轮中断写坏的文件上」，随后 finally 忠实地把空内容
        #    写回去 —— 损坏被当成基线传播。判据取 HEAD 版本字节数作参照：工作副本不足 HEAD
        #    一半即拒绝拍快照（截断守卫）。
        rel = t.relative_to(_REPO).as_posix()
        head = subprocess.run(["git", "show", "HEAD:" + rel], cwd=str(_REPO),
                              capture_output=True, text=True, encoding="utf-8").stdout
        if head and len(text) * 2 < len(head):
            print("HARNESS-SNAPSHOT-TRUNCATED: " + rel + " 工作副本 " + str(len(text))
                  + " 字节 < HEAD " + str(len(head)) + " 字节的一半，拒绝拍快照。"
                    "先 git checkout 该文件再跑。")
            return 3
        pristine[t] = text
    results: dict[str, str] = {}
    try:
        for m in selected:
            for t, text in pristine.items():
                t.write_text(text, encoding="utf-8", newline="\n")
            original = pristine[m.target]
            if original.count(m.anchor) != 1:
                results[m.mid] = "ANCHOR-MISS(" + str(original.count(m.anchor)) + ")"
                continue
            mutated = original.replace(m.anchor, m.replacement)
            m.target.write_text(mutated, encoding="utf-8", newline="\n")
            if m.target.read_text(encoding="utf-8") != mutated:
                results[m.mid] = "HARNESS-WRITE-FAILED"
                continue
            code = _run_gate(skip_optimize=(m.kind != "missing_export"))
            results[m.mid] = "GREEN" if code == 0 else "RED"
    finally:
        for t, text in pristine.items():
            t.write_text(text, encoding="utf-8", newline="\n")
            assert t.read_text(encoding="utf-8") == text, "还原失败: " + str(t)
    post = _run_gate(skip_optimize=False)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    off = [k for k, v in results.items() if v != "RED"]
    print("RED " + str(len(results) - len(off)) + "/" + str(len(results)) + "；非 RED: " + str(off))
    print("还原后基线: " + ("PASS" if post == 0 else "FAIL"))
    return 1 if off or post != 0 else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-anchors", action="store_true")
    mode.add_argument("--run", choices=["all"])
    parser.add_argument("--only", default=None,
                        help="逗号分隔的 mid 子集，分批跑用（每条变异要跑一遍全量 eslint）")
    args = parser.parse_args(argv)
    only = {x.strip() for x in args.only.split(",")} if args.only else None
    return check_anchors() if args.check_anchors else run_all(only)


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())