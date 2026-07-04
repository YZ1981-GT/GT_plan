#!/usr/bin/env python3
"""Clone D3 prepaid accounts implementation to F1 prepayment (debit account variant)."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WP = ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

REPLACEMENTS = [
    ("d3-prepaid-accounts", "f1-prepayment"),
    ("GtD3PrepaidAccounts", "GtF1Prepayment"),
    ("useD3", "useF1"),
    ("D3Tab", "F1Tab"),
    ("D3-", "F1-"),
    ("'D3", "'F1"),
    ('"D3', '"F1'),
    ("d3/", "f1/"),
    ("./d3/", "./f1/"),
    ("预收账款", "预付账款"),
    ("2203", "1123"),
    ("D3 ", "F1 "),
    ("D3A", "F1A"),
    ("[D3]", "[F1]"),
    ("d3-prepaid", "f1-prepay"),
    ("d3-adjudication", "f1-adjudication"),
    ("d3-tabs", "f1-tabs"),
    ("d3-header", "f1-header"),
    ("贷方科目期末 = 期初审定 + 贷方 - 借方", "借方科目期末 = 期初审定 + 借方 - 贷方"),
]

# Debit account: swap debit/credit in end balance function body
FORMULA_SWAP = """
export function calcEndUnadjustedDebit(priorAudited: number, debit: number, credit: number): number {
  return priorAudited + debit - credit
}

export function calcEndBalance(priorAudited: number, debit: number, credit: number): number {
  return calcEndUnadjustedDebit(priorAudited, debit, credit)
}
"""


def transform(content: str) -> str:
    for old, new in REPLACEMENTS:
        content = content.replace(old, new)
    # voucher check → comprehensive check for F1-7
    content = content.replace("F1TabVoucherCheck", "F1TabComprehensiveCheck")
    content = content.replace("voucher-check", "comprehensive-check")
    content = content.replace("凭证检查", "综合检查")
    return content


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8")
    dst.write_text(transform(text), encoding="utf-8")


def main() -> None:
    # f1 tabs from d3
    d3_dir = WP / "d3"
    f1_dir = WP / "f1"
    if f1_dir.exists():
        shutil.rmtree(f1_dir)
    f1_dir.mkdir(parents=True)

    for vue in d3_dir.glob("*.vue"):
        name = vue.name.replace("D3Tab", "F1Tab")
        if name == "F1TabVoucherCheck.vue":
            name = "F1TabComprehensiveCheck.vue"
        copy_file(vue, f1_dir / name)

    # F1 confirmation procedure tab (stub)
    (f1_dir / "F1TabConfirmationProcedure.vue").write_text(
        """<template>
  <el-empty description="F1 函证程序表（G1A-修订前，待接入 a-program-console）" />
</template>
<script setup lang="ts">
defineProps<{ wpId?: string; projectId?: string; isReadonly?: boolean }>()
</script>
""",
        encoding="utf-8",
    )

    # composables
    comp_dir = WP / "composables"
    for src in comp_dir.glob("useD3*.ts"):
        dst_name = src.name.replace("useD3", "useF1")
        if dst_name == "useF1VoucherCheck.ts":
            dst_name = "useF1ComprehensiveCheck.ts"
        copy_file(src, comp_dir / dst_name)

    # formula engine debit variant
    fe = comp_dir / "useF1FormulaEngine.ts"
    text = fe.read_text(encoding="utf-8")
    text = text.replace(
        "export function calcEndBalance(priorAudited: number, credit: number, debit: number): number {\n  return priorAudited + credit - debit\n}",
        FORMULA_SWAP.strip(),
    )
    text = text.replace(
        "export function calcRelatedPartyEndBalance(prior: number, credit: number, debit: number): number {\n  return prior + credit - debit\n}",
        "export function calcRelatedPartyEndBalance(prior: number, debit: number, credit: number): number {\n  return prior + debit - credit\n}",
    )
    text = text.replace("calcEndBalance(priorAudited, credit, debit)", "calcEndBalance(priorAudited, debit, credit)")
    text = text.replace("D3-2 明细表 O列 = H + N - M", "F1-2 明细表 O列 = H + M - N")
    text = text.replace("贷方科目", "借方科目")
    fe.write_text(text, encoding="utf-8")

    # main entry
    copy_file(WP / "GtD3PrepaidAccounts.vue", WP / "GtF1Prepayment.vue")
    main = (WP / "GtF1Prepayment.vue").read_text(encoding="utf-8")
    main = main.replace("F1TabVoucherCheck", "F1TabComprehensiveCheck")
    main = main.replace("name=\"voucher-check\"", "name=\"comprehensive-check\"")
    main = main.replace("label=\"F1-7 凭证检查\"", "label=\"F1-7 综合检查\"")
    # add confirmation tab before closing el-tabs
    conf_tab = """
          <!-- Tab 10: 函证程序 -->
          <el-tab-pane name="confirmation-procedure" label="函证程序" lazy>
            <F1TabConfirmationProcedure
              v-if="activeTab === 'confirmation-procedure'"
              :wp-id="wpIdRef"
              :project-id="projectIdRef"
              :is-readonly="isReadonly"
            />
          </el-tab-pane>
"""
    main = main.replace(
        "const F1TabComprehensiveCheck = defineAsyncComponent",
        "const F1TabConfirmationProcedure = defineAsyncComponent(() => import('./f1/F1TabConfirmationProcedure.vue'))\nconst F1TabComprehensiveCheck = defineAsyncComponent",
    )
    main = main.replace(
        "        </el-tabs>",
        conf_tab + "\n        </el-tabs>",
    )
    main = main.replace("9个tab-pane", "10个tab-pane")
    (WP / "GtF1Prepayment.vue").write_text(main, encoding="utf-8")

    print("F1 clone complete:", f1_dir, WP / "GtF1Prepayment.vue")


if __name__ == "__main__":
    main()
