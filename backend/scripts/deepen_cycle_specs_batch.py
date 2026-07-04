#!/usr/bin/env python3
"""Batch deepen F3-F5/G2-G14: sheetName dispatch + adjudication + formData + backend render."""
from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WP = ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
STRATEGIES = ROOT / "backend" / "app" / "routers" / "wp_render_strategies"
INIT = STRATEGIES / "__init__.py"

SPECS = [
    {"id": "f3-notes-payable", "vue": "GtF3NotesPayable", "short": "F3NotPay", "prefix": "F3", "account": "2201"},
    {"id": "f4-accounts-payable", "vue": "GtF4AccountsPayable", "short": "F4AccPay", "prefix": "F4", "account": "2202"},
    {"id": "f5-cost-of-sales", "vue": "GtF5CostOfSales", "short": "F5CosSal", "prefix": "F5", "account": "6401"},
    {"id": "g2-interest-receivable", "vue": "GtG2InterestReceivable", "short": "G2IntRec", "prefix": "G2", "account": "1132"},
    {"id": "g3-dividend-receivable", "vue": "GtG3DividendReceivable", "short": "G3DivRec", "prefix": "G3", "account": "1131"},
    {"id": "g4-bond-investment-main", "vue": "GtG4BondInvestmentMain", "short": "G4BonInv", "prefix": "G4", "account": "1503"},
    {"id": "g5-long-term-receivable", "vue": "GtG5LongTermReceivable", "short": "G5LonRec", "prefix": "G5", "account": "1531"},
    {"id": "g8-other-equity-instruments", "vue": "GtG8OtherEquityInstruments", "short": "G8OthEqu", "prefix": "G8", "account": "1504"},
    {"id": "g9-other-noncurrent-financial", "vue": "GtG9OtherNoncurrentFinancial", "short": "G9OthNcf", "prefix": "G9", "account": "1505"},
    {"id": "g10-trading-financial-liabilities", "vue": "GtG10TradingFinancialLiabilities", "short": "G10TraFin", "prefix": "G10", "account": "2101"},
    {"id": "g11-investment-income", "vue": "GtG11InvestmentIncome", "short": "G11InvInc", "prefix": "G11", "account": "6111"},
    {"id": "g12-net-hedge-gains", "vue": "GtG12NetHedgeGains", "short": "G12NetHed", "prefix": "G12", "account": "6101"},
    {"id": "g13-fair-value-changes", "vue": "GtG13FairValueChanges", "short": "G13FaiVal", "prefix": "G13", "account": "6102"},
    {"id": "g14-credit-impairment-loss", "vue": "GtG14CreditImpairmentLoss", "short": "G14CreImp", "prefix": "G14", "account": "6702"},
]

FORM_DATA_TMPL = '''import {{ ref, onScopeDispose, type Ref }} from 'vue'
import {{ ElMessage }} from 'element-plus'
import {{ api }} from '@/services/apiProxy'
import type {{ ChecklistResponse }} from './useF1FormData'

export function use{short}FormData(opts: {{ wpId: Ref<string>; projectId: Ref<string> }}) {{
  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({{}})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const itemPrefix = '{prefix}-'

  async function loadResponses() {{
    if (!opts.wpId.value) return
    try {{
      const res = await api.get(`/api/workpapers/${{opts.wpId.value}}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {{
        if (r.item_id?.startsWith(itemPrefix)) {{
          map.set(r.item_id, {{ item_id: r.item_id, conclusion: r.conclusion ?? null, remark: r.remark ?? null }})
        }}
      }}
      allResponses.value = map
    }} catch {{
      ElMessage.warning('{prefix}数据加载失败，可手动填写')
    }}
  }}

  async function loadAll() {{
    isLoading.value = true
    try {{
      await Promise.all([
        loadResponses(),
        (async () => {{
          const res = await api.get(`/api/workpapers/${{opts.wpId.value}}/render-config`, {{
            params: {{ force_component_type: '{id}' }}, _silent: true,
          }} as any)
          const data = res?.data ?? res
          for (const s of data?.sheets ?? data?.data?.sheets ?? []) {{
            sheetCache.value[s.sheet_name || s.name || 'default'] = s.html_data ?? s
          }}
        }})(),
      ])
    }} finally {{ isLoading.value = false }}
  }}

  async function saveImmediate(itemId: string, data: Partial<ChecklistResponse>) {{
    const existing = allResponses.value.get(itemId) || {{ item_id: itemId, conclusion: null, remark: null }}
    const updated = {{ ...existing, ...data }}
    allResponses.value.set(itemId, updated)
    await api.put(`/api/workpapers/${{opts.wpId.value}}/checklist-responses`, {{
      project_id: opts.projectId.value,
      items: [{{ item_id: itemId, conclusion: updated.conclusion, remark: updated.remark }}],
    }})
  }}

  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>) {{
    const existing = allResponses.value.get(itemId) || {{ item_id: itemId, conclusion: null, remark: null }}
    const updated = {{ ...existing, ...data }}
    allResponses.value.set(itemId, updated)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    _debounceTimers.set(itemId, setTimeout(() => {{
      _debounceTimers.delete(itemId)
      void saveImmediate(itemId, updated)
    }}, 2000))
  }}

  function getSheet(name: string) {{ return sheetCache.value[name] ?? {{ rows: [] }} }}

  onScopeDispose(() => {{ for (const t of _debounceTimers.values()) clearTimeout(t) }})

  return {{ isLoading, sheetCache, allResponses, loadAll, getSheet, saveImmediate, debouncedSave }}
}}
'''

MAIN_VUE_TMPL = '''<template>
  <div class="{css}">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div class="{css}-toolbar">
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
      </div>

      <GtOnlyOfficeSheet
        v-if="currentSheet === '{prefix}A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <CycleTabAdjudication
        v-else-if="adjudicationConfig"
        :config="adjudicationConfig"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <GtGridSheet
        v-else-if="useGridFallback"
        :html-data="props.htmlData || formData.getSheet(currentSheet)"
        :readonly="isReadonly"
      />

      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
import {{ ref, computed, onMounted, defineAsyncComponent }} from 'vue'
import {{ use{short}FormData }} from './composables/use{short}FormData'
import {{ useWorkpaperVersionToolbar }} from './composables/useWorkpaperVersionToolbar'
import CycleTabAdjudication from './shared/CycleTabAdjudication.vue'
import {{ getAdjudicationConfig }} from './shared/cycleAdjudicationConfigs'

const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

const props = defineProps<{{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
}}>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const formData = use{short}FormData({{ wpId: wpIdRef, projectId: computed(() => props.projectId) }})
const isReadonly = computed(() => !!props.readonly)
const versionToolbar = useWorkpaperVersionToolbar({{ wpId: wpIdRef, projectId: computed(() => props.projectId) }})
const {{ versionTrailRef }} = versionToolbar

const currentSheet = computed(() => {{
  const name = props.sheetName || props.wpCode || ''
  if (/附注披露/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/({prefix}A|{prefix}-\\d+)/)
  return m ? m[1] : ''
}})

const adjudicationConfig = computed(() => getAdjudicationConfig(currentSheet.value))
const useGridFallback = computed(() => {{
  const code = currentSheet.value
  return !!code && code !== '{prefix}A' && !adjudicationConfig.value && !code.startsWith('附注')
}})

onMounted(async () => {{ await formData.loadAll(); isLoading.value = false }})
</script>

<style scoped>
.{css} {{ padding: 12px; }}
.loading-container {{ padding: 24px; }}
.{css}-toolbar {{ margin-bottom: 8px; }}
</style>
'''

RENDER_PY_TMPL = '''"""{title} — 专属渲染策略."""
from __future__ import annotations
import logging
import sqlalchemy as sa
from ._context import RenderContext

logger = logging.getLogger(__name__)

async def render(ctx: RenderContext) -> dict | None:
    responses_snapshot: dict = {{}}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 800"
            ),
            {{"wp_id": str(ctx.wp_id), "pfx": "{prefix}-%"}},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {{"conclusion": row.conclusion or "", "remark": row.remark or ""}}
    except Exception as e:
        logger.warning("{prefix} render failed: %s", e)
    return {{"account_code": "{account}", "responses_snapshot": responses_snapshot, "prefix": "{prefix}"}}
'''

TITLES = {
    "f3-notes-payable": "F3 应付票据",
    "f4-accounts-payable": "F4 应付账款",
    "f5-cost-of-sales": "F5 主营业务成本",
    "g2-interest-receivable": "G2 应收利息",
    "g3-dividend-receivable": "G3 应收股利",
    "g4-bond-investment-main": "G4 债权投资",
    "g5-long-term-receivable": "G5 长期应收款",
    "g8-other-equity-instruments": "G8 其他权益工具投资",
    "g9-other-noncurrent-financial": "G9 其他非流动金融资产",
    "g10-trading-financial-liabilities": "G10 交易性金融负债",
    "g11-investment-income": "G11 投资收益",
    "g12-net-hedge-gains": "G12 净敞口套期收益",
    "g13-fair-value-changes": "G13 公允价值变动损益",
    "g14-credit-impairment-loss": "G14 信用减值损失",
}


GRID_ONLY_SPECS = [
    {"id": "f2-inventory-special", "vue": "GtF2InventorySpecial", "short": "F2InvSpe", "prefix": "F2"},
    {"id": "f2-inventory-valuation-impairment", "vue": "GtF2InventoryValuation", "short": "F2InvVal", "prefix": "F2"},
    {"id": "g4-bond-investment-sppi", "vue": "GtG4BondInvestmentSppi", "short": "G4BonSpp", "prefix": "G4"},
    {"id": "g4-bond-investment-ecl", "vue": "GtG4BondInvestmentEcl", "short": "G4BonEcl", "prefix": "G4"},
    {"id": "g6-other-bond-investment-main", "vue": "GtG6OtherBondMain", "short": "G6OthBon", "prefix": "G6"},
    {"id": "g6-other-bond-investment-sppi", "vue": "GtG6OtherBondSppi", "short": "G6BonSpp", "prefix": "G6"},
    {"id": "g6-other-bond-investment-ecl", "vue": "GtG6OtherBondEcl", "short": "G6BonEcl", "prefix": "G6"},
    {"id": "g7-long-term-equity-main", "vue": "GtG7LongTermEquityMain", "short": "G7EquMai", "prefix": "G7"},
    {"id": "g7-long-term-equity-method", "vue": "GtG7EquityMethod", "short": "G7EquMet", "prefix": "G7"},
    {"id": "g7-long-term-equity-subsidiary", "vue": "GtG7EquitySubsidiary", "short": "G7EquSub", "prefix": "G7"},
]

GRID_MAIN_VUE_TMPL = '''<template>
  <div class="{css}">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="6" animated /></div>
    <template v-else>
      <div class="{css}-toolbar">
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
      </div>
      <GtGridSheet
        v-if="currentSheet || props.htmlData"
        :html-data="props.htmlData || formData.getSheet(currentSheet)"
        :readonly="isReadonly"
      />
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />
      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>
<script setup lang="ts">
import {{ ref, computed, onMounted, defineAsyncComponent }} from 'vue'
import {{ use{short}FormData }} from './composables/use{short}FormData'
import {{ useWorkpaperVersionToolbar }} from './composables/useWorkpaperVersionToolbar'
const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const props = defineProps<{{ wpId: string; projectId: string; wpCode?: string; sheetName?: string; htmlData?: any; readonly?: boolean }}>()
const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const formData = use{short}FormData({{ wpId: wpIdRef, projectId: computed(() => props.projectId) }})
const isReadonly = computed(() => !!props.readonly)
const versionToolbar = useWorkpaperVersionToolbar({{ wpId: wpIdRef, projectId: computed(() => props.projectId) }})
const {{ versionTrailRef }} = versionToolbar
const currentSheet = computed(() => {{
  const name = props.sheetName || props.wpCode || ''
  const m = name.match(/({prefix}A|{prefix}-\\d+)/)
  return m ? m[1] : ''
}})
onMounted(async () => {{ await formData.loadAll(); isLoading.value = false }})
</script>
<style scoped>.{css} {{ padding: 12px; }} .loading-container {{ padding: 24px; }} .{css}-toolbar {{ margin-bottom: 8px; }}</style>
'''


def patch_init(specs: list[dict]) -> None:
    text = INIT.read_text(encoding="utf-8")
    for s in specs:
        mod = s["id"].replace("-", "_")
        imp = f"from ._{mod} import render as render_{mod}\n"
        if imp not in text:
            text = text.replace(
                "from ._e1_monetary_fund import render as render_e1_monetary_fund\n",
                f"{imp}from ._e1_monetary_fund import render as render_e1_monetary_fund\n",
            )
        entry = f'    "{s["id"]}": render_{mod},\n'
        if f'"{s["id"]}"' not in text:
            text = text.replace("\n}", f"\n{entry}}}", 1)
    INIT.write_text(text, encoding="utf-8")


def main() -> None:
    all_specs = SPECS + GRID_ONLY_SPECS
    for s in SPECS:
        css = s["id"]
        (WP / "composables" / f"use{s['short']}FormData.ts").write_text(
            FORM_DATA_TMPL.format(**s), encoding="utf-8"
        )
        (WP / f"{s['vue']}.vue").write_text(MAIN_VUE_TMPL.format(css=css, **s), encoding="utf-8")
        mod = s["id"].replace("-", "_")
        (STRATEGIES / f"_{mod}.py").write_text(
            RENDER_PY_TMPL.format(title=TITLES[s["id"]], **s), encoding="utf-8"
        )
        print(f"OK {s['id']}")

    for s in GRID_ONLY_SPECS:
        css = s["id"]
        (WP / "composables" / f"use{s['short']}FormData.ts").write_text(
            FORM_DATA_TMPL.format(id=s["id"], prefix=s["prefix"], short=s["short"], account=""), encoding="utf-8"
        )
        (WP / f"{s['vue']}.vue").write_text(GRID_MAIN_VUE_TMPL.format(css=css, **s), encoding="utf-8")
        print(f"OK grid {s['id']}")

    patch_init(SPECS)
    print("INIT patched")


if __name__ == "__main__":
    main()

