<template>
  <div class="f2-inventory-main">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="showHtmlToolbar" class="f2-inventory-main-toolbar">
        <el-segmented
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
        <el-tag v-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <template v-else>
        <F2TabProcedure
          v-if="currentSheet === 'F2A'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- F2-21~26 监盘由 f2-stocktake-bundle 承载；Main 仅兼容误路由 -->
        <el-alert
          v-else-if="isStocktakeSheet"
          type="info"
          :closable="false"
          show-icon
          title="监盘底稿（F2-21~26）请通过「F2 存货监盘」包打开"
          description="本组件为存货核心包，监盘已拆至独立入口，避免双路由写库冲突。"
          style="margin: 12px 0"
        />

        <F2TabAdjudication
          v-else-if="currentSheet === 'F2-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :debounced-save="formData.debouncedSave"
          :cross-sheet="crossSheet"
        />

        <F2TabDetailSummary
          v-else-if="currentSheet === 'F2-2'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <F2TabAdjustment
          v-else-if="currentSheet === 'F2-14'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :audit-year="auditYearNum"
        />

        <F2TabPolicy
          v-else-if="currentSheet === 'F2-16'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabOverallAnalysis
          v-else-if="currentSheet === 'F2-18'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :cross-sheet="crossSheet"
        />

        <F2TabProductionSales
          v-else-if="currentSheet === 'F2-19'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabCostComparison
          v-else-if="currentSheet === 'F2-20'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2DetailSheetTurnover
          v-else-if="currentSheet === 'F2-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2DetailSheetOutsourced
          v-else-if="currentSheet === 'F2-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2DetailSheet
          v-else-if="detailConfig"
          :config="detailConfig"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :year="auditYearNum"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2DetailSheetDev
          v-else-if="currentSheet === 'F2-10'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2DetailSheetDevCost
          v-else-if="currentSheet === 'F2-11'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2DetailSheetContractPerf
          v-else-if="currentSheet === 'F2-12'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2DetailSheetBio
          v-else-if="currentSheet === 'F2-13'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2CutoffSheet
          v-else-if="cutoffConfig"
          :config="cutoffConfig"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :bs-date="formData.projectContext.value?.audit_period_end || formData.projectContext.value?.bs_date || ''"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :applicable-standards="applicableStandards"
        />

        <F2TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :applicable-standards="applicableStandards"
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
      </template>

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtF2InventoryMain.vue — F2 存货核心组主入口（比照 GtD4 / GtF3）
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, toRef, inject, defineAsyncComponent } from 'vue'
import { useF2FormData, type ChecklistResponse } from './composables/useF2FormData'
import { useF2CrossSheet } from './composables/useF2CrossSheet'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useF2DualMode } from './composables/useF2DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { getF2DetailConfig } from './f2/detail/f2DetailSheetConfigs'
import { getF2CutoffConfig } from './f2/inspection/f2CutoffSheetConfigs'

// defineAsyncComponent lazy loading — 首屏仅加载当前 sheet 组件（Req 20.7）
const F2TabProcedure = defineAsyncComponent(() => import('./f2/core/F2TabProcedure.vue'))
const F2TabAdjudication = defineAsyncComponent(() => import('./f2/core/F2TabAdjudication.vue'))
const F2TabDetailSummary = defineAsyncComponent(() => import('./f2/core/F2TabDetailSummary.vue'))
const F2TabAdjustment = defineAsyncComponent(() => import('./f2/core/F2TabAdjustment.vue'))
const F2TabDisclosureListed = defineAsyncComponent(() => import('./f2/core/F2TabDisclosureListed.vue'))
const F2TabDisclosureSoe = defineAsyncComponent(() => import('./f2/core/F2TabDisclosureSoe.vue'))
const F2TabPolicy = defineAsyncComponent(() => import('./f2/analysis/F2TabPolicy.vue'))
const F2TabOverallAnalysis = defineAsyncComponent(() => import('./f2/analysis/F2TabOverallAnalysis.vue'))
const F2TabProductionSales = defineAsyncComponent(() => import('./f2/analysis/F2TabProductionSales.vue'))
const F2TabCostComparison = defineAsyncComponent(() => import('./f2/analysis/F2TabCostComparison.vue'))
const F2DetailSheet = defineAsyncComponent(() => import('./f2/detail/F2DetailSheet.vue'))
const F2DetailSheetTurnover = defineAsyncComponent(() => import('./f2/detail/F2DetailSheetTurnover.vue'))
const F2DetailSheetOutsourced = defineAsyncComponent(() => import('./f2/detail/F2DetailSheetOutsourced.vue'))
const F2DetailSheetDev = defineAsyncComponent(() => import('./f2/detail/F2DetailSheetDev.vue'))
const F2DetailSheetDevCost = defineAsyncComponent(() => import('./f2/detail/F2DetailSheetDevCost.vue'))
const F2DetailSheetContractPerf = defineAsyncComponent(() => import('./f2/detail/F2DetailSheetContractPerf.vue'))
const F2DetailSheetBio = defineAsyncComponent(() => import('./f2/detail/F2DetailSheetBio.vue'))
const F2CutoffSheet = defineAsyncComponent(() => import('./f2/inspection/F2CutoffSheet.vue'))
const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
}>()

const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)
const sheetNameRef = computed(() => props.sheetName || '')

const formData = useF2FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const auditYearNum = computed(() => {
  const ctx = formData.projectContext.value
  const raw = ctx?.audit_year ?? ctx?.year
  if (typeof raw === 'number' && raw >= 1900) return raw
  if (typeof raw === 'string' && /^\d{4}$/.test(raw)) return Number(raw)
  const end = ctx?.audit_period_end || ctx?.bs_date || ''
  if (end.length >= 4) {
    const y = parseInt(end.slice(0, 4), 10)
    if (y >= 1900) return y
  }
  return undefined
})

const allResponses = computed(() => formData.allResponses.value)

const crossSheet = useF2CrossSheet({
  allResponses: formData.allResponses,
  projectContext: formData.projectContext,
})

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionToolbar = runtime?.version ?? {
  versionTrailRef: ref<{ openDrawer: () => void } | null>(null),
  openVersionHistory: () => undefined,
  scheduleAutoSnapshot: () => undefined,
  wrapSaveImmediate: (<T,>(fn: T): T => fn),
}
const { versionTrailRef, openVersionHistory } = versionToolbar

provide('f2VersionTrailRef', versionTrailRef)
provide('f2OpenVersionHistory', openVersionHistory)

const dualMode = useF2DualMode({
  wpId: toRef(props, 'wpId'),
  sheetName: sheetNameRef,
  reloadAll: () => formData.loadAll(),
})

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/F2-note-listed|附注披露.*上市|附注.*上市/.test(name)) return '附注上市'
  if (/F2-note-soe|附注披露.*国企|附注.*国企/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(F2A|F2-\d+[A-Z]?)/)
  return m ? m[1] : ''
})

const STOCKTAKE_SHEETS = new Set(['F2-21A', 'F2-21', 'F2-22', 'F2-23', 'F2-24', 'F2-25', 'F2-26'])
const isStocktakeSheet = computed(() => STOCKTAKE_SHEETS.has(currentSheet.value))

const showHtmlToolbar = computed(() => {
  const s = currentSheet.value
  if (isStocktakeSheet.value) return false
  return s.startsWith('F2-') || s === 'F2A' || s.startsWith('附注')
})

const applicableStandards = computed(() =>
  formData.projectContext.value?.applicable_standards ?? [],
)

const detailConfig = computed(() => getF2DetailConfig(currentSheet.value))
const cutoffConfig = computed(() => getF2CutoffConfig(currentSheet.value))

const useGridFallback = computed(() => {
  const code = currentSheet.value
  if (isStocktakeSheet.value) return false
  const htmlSheets = new Set([
    'F2-1', 'F2-2', 'F2-14', 'F2-16', 'F2-18', 'F2-19', 'F2-20', 'F2A',
  ])
  return code && !htmlSheets.has(code) && !code.startsWith('附注')
    && !detailConfig.value && !cutoffConfig.value
})

// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide（真实复核对话）
provide('reloadWorkpaperData', () => formData.loadAll())

// ─── 复核圆点 ─────────────────────────────────────────────────────────────────
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

async function handleF2SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    await formData.saveItemsFromEvent(items)
    versionToolbar.scheduleAutoSnapshot()
  }
}

function handleF2Writeback(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; auditedAmount: number }>).detail
  if (d?.accountCode != null && d.auditedAmount != null) {
    void formData.writebackTrialBalance(d.accountCode, d.auditedAmount)
  }
}

async function selfLoad(): Promise<void> {
  if (props.htmlData?.projectContext) {
    formData.projectContext.value = props.htmlData.projectContext
  }
  try {
    // 结构化首屏只等 checklist + 项目上下文；render-config 后台补齐（F2-29~32 不依赖 sheetCache）
    await formData.loadCritical()
    void formData.selfLoad()
  } catch (err) {
    console.warn('[GtF2InventoryMain] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  window.addEventListener('f2:save-items', handleF2SaveItems)
  window.addEventListener('f2:writeback-trial-balance', handleF2Writeback)
  void selfLoad()
})

onBeforeUnmount(() => {
  window.removeEventListener('f2:save-items', handleF2SaveItems)
  window.removeEventListener('f2:writeback-trial-balance', handleF2Writeback)
})
</script>

<style scoped>
.f2-inventory-main { padding: 12px; }
.loading-container { padding: 24px; }
.f2-inventory-main-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
