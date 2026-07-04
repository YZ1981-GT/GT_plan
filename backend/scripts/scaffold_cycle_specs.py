#!/usr/bin/env python3
"""Scaffold main entry + formula engine + overrides for F/G cycle workpaper specs."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WP = ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
OVERRIDES = ROOT / "backend" / "app" / "data" / "wp_code_overrides.json"
CLASSIFY = ROOT / "backend" / "app" / "services" / "wp_classification_service.py"
REGISTRY = WP / "htmlRendererRegistry.ts"
REGISTRY_SPEC = WP / "__tests__" / "htmlRendererRegistry.spec.ts"

SPECS = [
    {
        "id": "f2-inventory-main",
        "component": "f2-inventory-main",
        "vue": "GtF2InventoryMain",
        "prefix": "F2",
        "title": "存货底稿核心组",
        "account": "debit",
        "tabs": [
            ("procedure", "F2A 程序表"),
            ("adjudication", "F2-1 审定表"),
            ("detail", "F2-2~13 明细"),
            ("adjustment", "F2-14 调整"),
            ("analysis", "F2-16 分析"),
            ("cutoff", "F2-29~32 截止"),
            ("checks", "F2-18~20 检查"),
            ("disclosure", "附注"),
        ],
        "wp_codes": None,  # filled by regex from overrides
    },
    {
        "id": "f2-inventory-special",
        "component": "f2-inventory-special",
        "vue": "GtF2InventorySpecial",
        "prefix": "F2",
        "title": "存货特殊事项",
        "account": "debit",
        "tabs": [("special", "特殊事项")],
        "wp_suffixes": ["-21", "-22", "-23", "-24", "-25", "-26"],
    },
    {
        "id": "f2-inventory-valuation-impairment",
        "component": "f2-inventory-valuation-impairment",
        "vue": "GtF2InventoryValuation",
        "prefix": "F2",
        "title": "存货计价与减值",
        "account": "debit",
        "tabs": [("valuation", "计价减值")],
        "wp_suffixes": ["-33", "-34", "-35", "-38", "-39", "-40", "-41", "-42", "-43", "-44", "-47", "-48", "-49", "-52", "-55", "-56", "-57", "-58", "-61", "-62", "-63", "-64", "-65", "-66", "-67", "-68", "-69", "-70", "-71", "-72"],
    },
    {
        "id": "f3-notes-payable",
        "component": "f3-notes-payable",
        "vue": "GtF3NotesPayable",
        "prefix": "F3",
        "title": "应付票据",
        "account": "credit",
        "tabs": [
            ("procedure", "F3A 程序表"),
            ("adjudication", "F3-1 审定表"),
            ("detail", "F3-2 明细"),
            ("adjustment", "F3-3 调整"),
            ("analysis", "F3-4 分析"),
            ("checks", "F3-5~6 检查"),
            ("disclosure", "附注"),
        ],
    },
    {
        "id": "f4-accounts-payable",
        "component": "f4-accounts-payable",
        "vue": "GtF4AccountsPayable",
        "prefix": "F4",
        "title": "应付账款",
        "account": "credit",
        "tabs": [
            ("procedure", "F4A 程序表"),
            ("adjudication", "F4-1 审定表"),
            ("detail", "F4-2 明细"),
            ("adjustment", "F4-3 调整"),
            ("analysis", "F4-4 分析"),
            ("checks", "F4-5~6 检查"),
            ("disclosure", "附注"),
        ],
    },
    {
        "id": "f5-cost-of-sales",
        "component": "f5-cost-of-sales",
        "vue": "GtF5CostOfSales",
        "prefix": "F5",
        "title": "营业成本",
        "account": "debit",
        "tabs": [
            ("procedure", "F5A 程序表"),
            ("adjudication", "F5-1 审定表"),
            ("detail", "F5-2 明细"),
            ("adjustment", "F5-3 调整"),
            ("analysis", "F5-4 分析"),
            ("checks", "F5-5~6 检查"),
        ],
    },
    {
        "id": "g1-trading-financial-assets",
        "component": "g1-trading-financial-assets",
        "vue": "GtG1TradingFinancialAssets",
        "prefix": "G1",
        "title": "交易性金融资产",
        "account": "debit",
        "tabs": [
            ("procedure", "G1A 程序表"),
            ("adjudication", "G1-1 审定表"),
            ("detail", "G1-2 明细"),
            ("adjustment", "G1-3 调整"),
            ("balance", "G1-4 结存"),
            ("income", "G1-5 收益"),
            ("fv-test", "G1-6 公允价值"),
            ("level3", "G1-7 Level3"),
            ("business", "G1-8 业务模式"),
            ("sppi", "G1-9~10 分类"),
            ("inventory", "G1-11~12 盘点"),
            ("checks", "G1-13 检查"),
            ("disclosure", "附注"),
        ],
    },
    {
        "id": "g2-interest-receivable",
        "component": "g2-interest-receivable",
        "vue": "GtG2InterestReceivable",
        "prefix": "G2",
        "title": "应收利息",
        "account": "debit",
        "tabs": [("procedure", "G2A"), ("adjudication", "G2-1"), ("detail", "G2-2"), ("bad-debt", "G2-3"), ("adjustment", "G2-4"), ("calc", "G2-5~8")],
    },
    {
        "id": "g3-dividend-receivable",
        "component": "g3-dividend-receivable",
        "vue": "GtG3DividendReceivable",
        "prefix": "G3",
        "title": "应收股利",
        "account": "debit",
        "tabs": [("procedure", "G3A"), ("adjudication", "G3-1"), ("detail", "G3-2"), ("adjustment", "G3-3"), ("calc", "G3-4~5")],
    },
    {
        "id": "g4-bond-investment-main",
        "component": "g4-bond-investment-main",
        "vue": "GtG4BondInvestmentMain",
        "prefix": "G4",
        "title": "债权投资主表",
        "account": "debit",
        "tabs": [("core", "G4 核心底稿")],
        "wp_exclude_suffixes": ["-9", "-10", "-11"],
    },
    {
        "id": "g4-bond-investment-sppi",
        "component": "g4-bond-investment-sppi",
        "vue": "GtG4BondInvestmentSppi",
        "prefix": "G4",
        "title": "债权投资SPPI",
        "account": "debit",
        "tabs": [("sppi", "G4 SPPI/业务模式")],
        "wp_suffixes": ["-5", "-6"],
    },
    {
        "id": "g4-bond-investment-ecl",
        "component": "g4-bond-investment-ecl",
        "vue": "GtG4BondInvestmentEcl",
        "prefix": "G4",
        "title": "债权投资ECL",
        "account": "debit",
        "tabs": [("ecl", "G4 减值ECL")],
        "wp_suffixes": ["-9", "-10", "-11"],
    },
    {
        "id": "g5-long-term-receivable",
        "component": "g5-long-term-receivable",
        "vue": "GtG5LongTermReceivable",
        "prefix": "G5",
        "title": "长期应收款",
        "account": "debit",
        "tabs": [("procedure", "G5A"), ("adjudication", "G5-1"), ("detail", "G5-2~3"), ("adjustment", "G5-4"), ("calc", "G5-5~10")],
    },
    {
        "id": "g6-other-bond-investment-main",
        "component": "g6-other-bond-investment-main",
        "vue": "GtG6OtherBondMain",
        "prefix": "G6",
        "title": "其他债权投资主表",
        "account": "debit",
        "tabs": [("core", "G6 核心")],
        "wp_exclude_suffixes": ["-11", "-12", "-13", "-14", "-15"],
    },
    {
        "id": "g6-other-bond-investment-sppi",
        "component": "g6-other-bond-investment-sppi",
        "vue": "GtG6OtherBondSppi",
        "prefix": "G6",
        "title": "其他债权投资SPPI",
        "account": "debit",
        "tabs": [("sppi", "G6 SPPI")],
        "wp_suffixes": ["-7", "-8"],
    },
    {
        "id": "g6-other-bond-investment-ecl",
        "component": "g6-other-bond-investment-ecl",
        "vue": "GtG6OtherBondEcl",
        "prefix": "G6",
        "title": "其他债权投资ECL",
        "account": "debit",
        "tabs": [("ecl", "G6 ECL")],
        "wp_suffixes": ["-11", "-12", "-13", "-14", "-15"],
    },
    {
        "id": "g7-long-term-equity-main",
        "component": "g7-long-term-equity-main",
        "vue": "GtG7LongTermEquityMain",
        "prefix": "G7",
        "title": "长期股权投资主表",
        "account": "debit",
        "tabs": [("core", "G7 核心")],
        "wp_exclude_suffixes": ["-11", "-12", "-13", "-14", "-15", "-16", "-17", "-8", "-9", "-10"],
    },
    {
        "id": "g7-long-term-equity-method",
        "component": "g7-long-term-equity-method",
        "vue": "GtG7EquityMethod",
        "prefix": "G7",
        "title": "长期股权投资权益法",
        "account": "debit",
        "tabs": [("method", "G7 权益法")],
        "wp_suffixes": ["-11", "-12", "-13", "-14", "-15", "-16", "-17"],
    },
    {
        "id": "g7-long-term-equity-subsidiary",
        "component": "g7-long-term-equity-subsidiary",
        "vue": "GtG7EquitySubsidiary",
        "prefix": "G7",
        "title": "长期股权投资子公司",
        "account": "debit",
        "tabs": [("subsidiary", "G7 子公司")],
        "wp_suffixes": ["-8", "-9", "-10"],
    },
    {
        "id": "g8-other-equity-instruments",
        "component": "g8-other-equity-instruments",
        "vue": "GtG8OtherEquityInstruments",
        "prefix": "G8",
        "title": "其他权益工具投资",
        "account": "debit",
        "tabs": [("procedure", "G8A"), ("adjudication", "G8-1"), ("detail", "G8-2"), ("adjustment", "G8-3"), ("fv", "G8-4~6")],
    },
    {
        "id": "g9-other-noncurrent-financial",
        "component": "g9-other-noncurrent-financial",
        "vue": "GtG9OtherNoncurrentFinancial",
        "prefix": "G9",
        "title": "其他非流动金融资产",
        "account": "debit",
        "tabs": [("procedure", "G9A"), ("adjudication", "G9-1"), ("detail", "G9-2"), ("adjustment", "G9-3"), ("fv", "G9-4~6")],
    },
    {
        "id": "g10-trading-financial-liabilities",
        "component": "g10-trading-financial-liabilities",
        "vue": "GtG10TradingFinancialLiabilities",
        "prefix": "G10",
        "title": "交易性金融负债",
        "account": "credit",
        "tabs": [("procedure", "G10A"), ("adjudication", "G10-1"), ("detail", "G10-2"), ("adjustment", "G10-3"), ("checks", "G10-4~8")],
    },
    {
        "id": "g11-investment-income",
        "component": "g11-investment-income",
        "vue": "GtG11InvestmentIncome",
        "prefix": "G11",
        "title": "投资收益",
        "account": "credit",
        "tabs": [("procedure", "G11A"), ("adjudication", "G11-1"), ("detail", "G11-2"), ("adjustment", "G11-3"), ("analysis", "G11-4~6")],
    },
    {
        "id": "g12-net-hedge-gains",
        "component": "g12-net-hedge-gains",
        "vue": "GtG12NetHedgeGains",
        "prefix": "G12",
        "title": "净敞口套期收益",
        "account": "credit",
        "tabs": [("procedure", "G12A"), ("adjudication", "G12-1"), ("detail", "G12-2"), ("adjustment", "G12-3")],
    },
    {
        "id": "g13-fair-value-changes",
        "component": "g13-fair-value-changes",
        "vue": "GtG13FairValueChanges",
        "prefix": "G13",
        "title": "公允价值变动损益",
        "account": "credit",
        "tabs": [("procedure", "G13A"), ("adjudication", "G13-1"), ("detail", "G13-2"), ("adjustment", "G13-3")],
    },
    {
        "id": "g14-credit-impairment-loss",
        "component": "g14-credit-impairment-loss",
        "vue": "GtG14CreditImpairmentLoss",
        "prefix": "G14",
        "title": "信用减值损失",
        "account": "debit",
        "tabs": [("procedure", "G14A"), ("adjudication", "G14-1"), ("detail", "G14-2"), ("adjustment", "G14-3"), ("ecl", "G14-4~6")],
    },
]

FORMULA_TEMPLATE_DEBIT = '''/**
 * {title} — 公式引擎（借方科目）
 */
export function parseNum(val: string | number | null | undefined): number {{
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}}
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {{
  return unadjusted + aje + rje
}}
export function calcEndBalance(prior: number, debit: number, credit: number): number {{
  return prior + debit - credit
}}
export function calcChangeAmount(current: number, prior: number): number {{
  return current - prior
}}
export function calcChangeRate(prior: number, current: number): number | '' | 'N/A' {{
  if (prior === 0 && current === 0) return ''
  if (prior === 0) return 'N/A'
  return (current - prior) / prior
}}
export function calcSubtotal(values: number[]): number {{
  return values.reduce((s, v) => s + v, 0)
}}
export function isChangeRateExceeding(rate: number | '' | 'N/A', threshold: number): boolean {{
  if (rate === '' || rate === 'N/A') return false
  return Math.abs(rate) > threshold
}}
'''

FORMULA_TEMPLATE_CREDIT = FORMULA_TEMPLATE_DEBIT.replace(
    "return prior + debit - credit", "return prior + credit - debit"
).replace("借方科目", "贷方科目")

VUE_TEMPLATE = '''<template>
  <div class="{css}">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div class="{css}-toolbar">
        <el-segmented v-model="dualMode.currentMode.value" :options="dualMode.modeOptions.value" size="small" @change="dualMode.onModeChange" />
      </div>
      <template v-if="dualMode.currentMode.value === 'onlyoffice' && dualMode.ooConfig.value">
        <GtOnlyOfficeSheet :config="dualMode.ooConfig.value" @document-ready="dualMode.onDocumentReady" />
      </template>
      <el-tabs v-else v-model="activeTab" type="border-card" class="{css}-tabs">
{tab_panes}
      </el-tabs>
    </template>
  </div>
</template>
<script setup lang="ts">
import {{ ref, computed, onMounted, provide, defineAsyncComponent }} from 'vue'
import http from '@/utils/http'
import {{ use{short}FormData }} from './composables/use{short}FormData'
import {{ use{short}DualMode }} from './composables/use{short}DualMode'
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const props = defineProps<{{ wpId: string; projectId: string; wpCode?: string; htmlData?: any; readonly?: boolean }}>()
defineEmits<{{ (e: 'save'): void; (e: 'completed'): void }}>()
const isLoading = ref(true)
const activeTab = ref('{default_tab}')
const wpIdRef = computed(() => props.wpId)
const formData = use{short}FormData({{ wpId: wpIdRef, projectId: computed(() => props.projectId) }})
const dualMode = use{short}DualMode({{ wpId: wpIdRef, activeTab }})
provide('openReviewDialog', (id: string) => console.log('[{short}] review', id))
async function selfLoad() {{
  if (!props.htmlData && props.wpId) {{
    try {{
      await http.get(`/api/workpapers/${{props.wpId}}/render-config`, {{
        params: {{ force_component_type: '{component}' }}, _silent: true,
      }} as any)
    }} catch {{ /* noop */ }}
  }}
  await formData.loadAll()
  isLoading.value = false
}}
onMounted(() => {{ selfLoad(); dualMode.checkOOHealth() }})
</script>
<style scoped>.{css} {{ padding: 12px }} .loading-container {{ padding: 24px }}</style>
'''

TAB_PANE = '''        <el-tab-pane name="{name}" label="{label}" lazy>
          <GtGridSheet v-if="activeTab === '{name}'" :html-data="sheetData('{name}')" :readonly="!!readonly" />
        </el-tab-pane>'''

FORM_DATA_TEMPLATE = '''import {{ ref, onScopeDispose, type Ref }} from 'vue'
import {{ api }} from '@/services/apiProxy'
export function use{short}FormData(opts: {{ wpId: Ref<string>; projectId: Ref<string> }}) {{
  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({{}})
  async function loadAll() {{
    isLoading.value = true
    try {{
      const res = await api.get(`/api/workpapers/${{opts.wpId.value}}/render-config`, {{
        params: {{ force_component_type: '{component}' }}, _silent: true,
      }} as any)
      const data = res?.data ?? res
      const sheets = data?.sheets ?? data?.data?.sheets ?? []
      for (const s of sheets) sheetCache.value[s.sheet_name || s.name || 'default'] = s.html_data ?? s
    }} finally {{ isLoading.value = false }}
  }}
  function getSheet(name: string) {{ return sheetCache.value[name] ?? {{ rows: [] }} }}
  onScopeDispose(() => {{}})
  return {{ isLoading, sheetCache, loadAll, getSheet }}
}}
'''

DUAL_MODE_TEMPLATE = '''import {{ ref, type Ref }} from 'vue'
export function use{short}DualMode(opts: {{ wpId: Ref<string>; activeTab: Ref<string> }}) {{
  const currentMode = ref<'html' | 'onlyoffice'>('html')
  const ooConfig = ref<any>(null)
  const ooHealthy = ref<boolean | null>(null)
  const modeOptions = ref([{{ label: 'HTML', value: 'html' }}, {{ label: 'OnlyOffice', value: 'onlyoffice' }}])
  function onModeChange(v: string) {{ currentMode.value = v as 'html' | 'onlyoffice' }}
  function onDocumentReady() {{}}
  async function checkOOHealth() {{ ooHealthy.value = true }}
  return {{ currentMode, ooConfig, ooHealthy, modeOptions, onModeChange, onDocumentReady, checkOOHealth }}
}}
'''


def short_name(component: str) -> str:
    parts = component.split("-")
    return "".join(p[:1].upper() + p[1:3] for p in parts[:3])


def load_overrides() -> dict[str, str]:
    return json.loads(OVERRIDES.read_text(encoding="utf-8"))


def resolve_wp_codes(spec: dict, overrides: dict[str, str]) -> list[str]:
    prefix = spec["prefix"]
    if spec.get("wp_suffixes"):
        return [f"{prefix}{s}" for s in spec["wp_suffixes"]]
    codes = [k for k in overrides if k == prefix or k.startswith(prefix + "-")]
    if spec.get("wp_exclude_suffixes"):
        ex = set(spec["wp_exclude_suffixes"])
        codes = [c for c in codes if not any(c.endswith(s) for s in ex)]
    if spec.get("wp_range"):
        lo, hi = spec["wp_range"]
        filtered = []
        for c in codes:
            if "-" not in c:
                continue
            suffix = c.split("-")[-1]
            if suffix.isdigit() and lo.lstrip("-") <= suffix <= hi.lstrip("-"):
                filtered.append(c)
        codes = filtered
    # f2-inventory-main: exclude special suffixes handled by other specs
    if spec["id"] == "f2-inventory-main":
        special = {"-21", "-22", "-23", "-24", "-25", "-26", "-33", "-34", "-35", "-38", "-39", "-40",
                   "-41", "-42", "-43", "-44", "-47", "-48", "-49", "-52", "-55", "-56", "-57", "-58",
                   "-61", "-62", "-63", "-64", "-65", "-66", "-67", "-68", "-69", "-70", "-71", "-72"}
        codes = [c for c in codes if not any(c.endswith(s) for s in special) and c != "F2-21A" and not c.endswith("A")]
    return sorted(set(codes))


def gen_vue(spec: dict) -> str:
    css = spec["component"].replace("-", "-")
    tabs = spec["tabs"]
    tab_panes = "\n".join(TAB_PANE.format(name=n, label=l) for n, l in tabs)
    short = short_name(spec["component"])
    # fix sheetData helper in script - inject function
    vue = VUE_TEMPLATE.format(
        css=css, component=spec["component"], short=short,
        tab_panes=tab_panes, default_tab=tabs[0][0],
    )
    vue = vue.replace(
        "onMounted(() => { selfLoad(); dualMode.checkOOHealth() })",
        f"function sheetData(tab: string) {{ return formData.getSheet(tab) || props.htmlData }}\n"
        f"const readonly = computed(() => !!props.readonly)\n"
        "onMounted(() => { selfLoad(); dualMode.checkOOHealth() })",
    )
    vue = vue.replace(
        "import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'",
        "import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'\n",
    )
    return vue


def main() -> None:
    overrides = load_overrides()
    new_types: list[str] = []

    for spec in SPECS:
        comp = spec["component"]
        vue_name = spec["vue"]
        short = short_name(comp)
        comp_dir = WP / "composables"

        # formula engine
        fe_path = comp_dir / f"use{short}FormulaEngine.ts"
        if not fe_path.exists():
            tpl = FORMULA_TEMPLATE_CREDIT if spec["account"] == "credit" else FORMULA_TEMPLATE_DEBIT
            fe_path.write_text(tpl.format(title=spec["title"]), encoding="utf-8")

        fd_path = comp_dir / f"use{short}FormData.ts"
        if not fd_path.exists():
            fd_path.write_text(FORM_DATA_TEMPLATE.format(short=short, component=comp), encoding="utf-8")

        dm_path = comp_dir / f"use{short}DualMode.ts"
        if not dm_path.exists():
            dm_path.write_text(DUAL_MODE_TEMPLATE.format(short=short), encoding="utf-8")

        vue_path = WP / f"{vue_name}.vue"
        if not vue_path.exists():
            vue_path.write_text(gen_vue(spec), encoding="utf-8")

        codes = resolve_wp_codes(spec, overrides)
        for code in codes:
            if overrides.get(code) not in ("skip", "f2-stocktake-bundle"):
                overrides[code] = comp
        if spec["prefix"] in overrides and overrides[spec["prefix"]] in ("d-form-table", "univer"):
            overrides[spec["prefix"]] = comp

        new_types.append(comp)
        print(f"Scaffolded {comp}: {len(codes)} wp_codes, {vue_name}.vue")

    OVERRIDES.write_text(json.dumps(overrides, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # VALID_COMPONENT_TYPES
    cls_text = CLASSIFY.read_text(encoding="utf-8")
    for t in new_types:
        if f'"{t}"' not in cls_text:
            cls_text = cls_text.replace(
                '"confirmation-alternative-g06",\n}',
                f'"confirmation-alternative-g06",\n    "{t}",\n}}',
                1,
            )
    CLASSIFY.write_text(cls_text, encoding="utf-8")

    print("Done. Update htmlRendererRegistry manually or re-run registry patch.")


if __name__ == "__main__":
    main()
