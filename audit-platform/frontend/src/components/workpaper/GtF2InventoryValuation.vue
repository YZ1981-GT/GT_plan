<template>
  <div class="f2-inventory-valuation">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="showHtmlToolbar" class="f2-val-toolbar">
        <el-segmented
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
        <el-tag v-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-f2-inventory-valuation" />
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
        <F2TabValuationAvg
          v-if="currentSheet === 'F2-38'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :audit-year="auditYear"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabValuationFifo
          v-else-if="currentSheet === 'F2-39'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :audit-year="auditYear"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabStandardCostTest
          v-else-if="currentSheet === 'F2-40'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :audit-year="auditYear"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabPurchaseInboundCheck
          v-else-if="currentSheet === 'F2-33'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :audit-year="auditYear"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabMaterialUsageCheck
          v-else-if="currentSheet === 'F2-34'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :audit-year="auditYear"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabSubcontractCheck
          v-else-if="currentSheet === 'F2-35'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabImpairmentTest
          v-else-if="currentSheet === 'F2-47'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabProductionCostDetail
          v-else-if="currentSheet === 'F2-41'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabDirectLaborAnalysis
          v-else-if="currentSheet === 'F2-42'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabOverheadDetail
          v-else-if="currentSheet === 'F2-43'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabCostAllocation
          v-else-if="currentSheet === 'F2-44'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabObsoleteInventory
          v-else-if="currentSheet === 'F2-48'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabImpairmentReversal
          v-else-if="currentSheet === 'F2-49'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabRelatedPurchase
          v-else-if="currentSheet === 'F2-52'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
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
 * GtF2InventoryValuation.vue — F2 计价减值组主入口（比照 GtF2InventoryMain / GtF3）
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, toRef, inject, defineAsyncComponent } from 'vue'
import { useF2ValuationFormData, type ChecklistResponse } from './composables/useF2ValuationFormData'
import { useF2ValuationDualMode } from './composables/useF2ValuationDualMode'
import { useF2ReviewDialogProvide } from './composables/useF2ReviewDialogProvide'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
// defineAsyncComponent lazy加载所有子组件（性能优化：13个sheet按需加载）
const F2TabValuationAvg = defineAsyncComponent(() => import('./f2/valuation/F2TabValuationAvg.vue'))
const F2TabValuationFifo = defineAsyncComponent(() => import('./f2/valuation/F2TabValuationFifo.vue'))
const F2TabStandardCostTest = defineAsyncComponent(() => import('./f2/valuation/F2TabStandardCostTest.vue'))
const F2TabPurchaseInboundCheck = defineAsyncComponent(() => import('./f2/valuation/F2TabPurchaseInboundCheck.vue'))
const F2TabMaterialUsageCheck = defineAsyncComponent(() => import('./f2/valuation/F2TabMaterialUsageCheck.vue'))
const F2TabSubcontractCheck = defineAsyncComponent(() => import('./f2/valuation/F2TabSubcontractCheck.vue'))
const F2TabImpairmentTest = defineAsyncComponent(() => import('./f2/valuation/F2TabImpairmentTest.vue'))
const F2TabProductionCostDetail = defineAsyncComponent(() => import('./f2/valuation/F2TabProductionCostDetail.vue'))
const F2TabDirectLaborAnalysis = defineAsyncComponent(() => import('./f2/valuation/F2TabDirectLaborAnalysis.vue'))
const F2TabOverheadDetail = defineAsyncComponent(() => import('./f2/valuation/F2TabOverheadDetail.vue'))
const F2TabCostAllocation = defineAsyncComponent(() => import('./f2/valuation/F2TabCostAllocation.vue'))
const F2TabObsoleteInventory = defineAsyncComponent(() => import('./f2/valuation/F2TabObsoleteInventory.vue'))
const F2TabImpairmentReversal = defineAsyncComponent(() => import('./f2/valuation/F2TabImpairmentReversal.vue'))
const F2TabRelatedPurchase = defineAsyncComponent(() => import('./f2/valuation/F2TabRelatedPurchase.vue'))

const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'

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

const formData = useF2ValuationFormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const allResponses = computed(() => formData.allResponses.value)

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

const dualMode = useF2ValuationDualMode({
  wpId: toRef(props, 'wpId'),
  sheetName: sheetNameRef,
  reloadAll: () => formData.loadAll(),
})

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  const m = name.match(/(F2-\d+)/)
  return m ? m[1] : ''
})

const auditYear = computed(() => {
  const d = formData.projectContext.value?.audit_period_end
    || formData.projectContext.value?.bs_date || ''
  if (d.length >= 4) return parseInt(d.slice(0, 4), 10)
  return new Date().getFullYear() - 1
})

const htmlSheets = new Set([
  'F2-33', 'F2-34', 'F2-35',
  'F2-38', 'F2-39', 'F2-40',
  'F2-41', 'F2-42', 'F2-43', 'F2-44',
  'F2-47', 'F2-48', 'F2-49', 'F2-52',
])

const showHtmlToolbar = computed(() => htmlSheets.has(currentSheet.value))

const useGridFallback = computed(() => {
  const code = currentSheet.value
  return code && !htmlSheets.has(code)
})

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')
useF2ReviewDialogProvide({ wpId: wpIdRef, projectId: projectIdRef })

provide('reloadWorkpaperData', () => formData.loadAll())

async function handleF2ValSaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    await formData.saveItemsFromEvent(items)
    versionToolbar.scheduleAutoSnapshot()
  }
}

async function selfLoad(): Promise<void> {
  try {
    await formData.loadAll()
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  window.addEventListener('f2-val:save-items', handleF2ValSaveItems)
  void selfLoad()
})

onBeforeUnmount(() => {
  window.removeEventListener('f2-val:save-items', handleF2ValSaveItems)
})
</script>

<style scoped>
.f2-inventory-valuation { padding: 12px; }
.loading-container { padding: 24px; }
.f2-val-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
