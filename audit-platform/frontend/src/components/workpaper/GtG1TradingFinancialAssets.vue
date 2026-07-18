<template>
  <div class="g1-trading-financial-assets">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div class="g1-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <CycleTabProcedure
        v-else-if="currentSheet === 'G1A'"
        sheet-code="G1A"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G1TabAdjudication
        v-else-if="currentSheet === 'G1-1'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
      />

      <G1TabFairValueTest
        v-else-if="currentSheet === 'G1-6'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <G1TabDetail
        v-else-if="currentSheet === 'G1-2'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <G1TabAdjustment
        v-else-if="currentSheet === 'G1-3'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <G1TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
      />

      <G1TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
      />

      <G1TabLevel3Reconciliation
        v-else-if="currentSheet === 'G1-7'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <G1TabBusinessModel
        v-else-if="currentSheet === 'G1-8'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
      />

      <G1TabClassification
        v-else-if="currentSheet === 'G1-9'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
      />

      <G1TabContractCashflow
        v-else-if="currentSheet === 'G1-10'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
      />

      <G1TabInventory
        v-else-if="currentSheet === 'G1-4'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <G1TabIncomeCalc
        v-else-if="currentSheet === 'G1-5'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <G1TabSecuritiesCount
        v-else-if="currentSheet === 'G1-11'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <G1TabCountReconciliation
        v-else-if="currentSheet === 'G1-12'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <G1TabVoucherCheck
        v-else-if="currentSheet === 'G1-13'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <G1TabDerivativeCheck
        v-else-if="currentSheet === 'G1-14'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <GtGridSheet
        v-else-if="useGridFallback"
        :html-data="props.htmlData || formData.getSheet(props.sheetName || currentSheet)"
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

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, provide, inject, defineAsyncComponent } from 'vue'
import { useG1TraFinFormData } from './composables/useG1TraFinFormData'
import { useG1DualMode } from './composables/useG1DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import G1TabAdjudication from './g1-trading-financial-assets/core/G1TabAdjudication.vue'
import G1TabFairValueTest from './g1-trading-financial-assets/valuation/G1TabFairValueTest.vue'
import G1TabDetail from './g1-trading-financial-assets/core/G1TabDetail.vue'

const G1TabAdjustment = defineAsyncComponent(() => import('./g1-trading-financial-assets/core/G1TabAdjustment.vue'))
const G1TabDisclosureListed = defineAsyncComponent(() => import('./g1-trading-financial-assets/core/G1TabDisclosureListed.vue'))
const G1TabDisclosureSOE = defineAsyncComponent(() => import('./g1-trading-financial-assets/core/G1TabDisclosureSOE.vue'))
const G1TabLevel3Reconciliation = defineAsyncComponent(() => import('./g1-trading-financial-assets/valuation/G1TabLevel3Reconciliation.vue'))
const G1TabBusinessModel = defineAsyncComponent(() => import('./g1-trading-financial-assets/classification/G1TabBusinessModel.vue'))
const G1TabClassification = defineAsyncComponent(() => import('./g1-trading-financial-assets/classification/G1TabClassification.vue'))
const G1TabContractCashflow = defineAsyncComponent(() => import('./g1-trading-financial-assets/classification/G1TabContractCashflow.vue'))
const G1TabInventory = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabInventory.vue'))
const G1TabIncomeCalc = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabIncomeCalc.vue'))
const G1TabSecuritiesCount = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabSecuritiesCount.vue'))
const G1TabCountReconciliation = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabCountReconciliation.vue'))
const G1TabVoucherCheck = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabVoucherCheck.vue'))
const G1TabDerivativeCheck = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabDerivativeCheck.vue'))

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
const wpIdRef = computed(() => props.wpId)
const isReadonly = computed(() => !!props.readonly)

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

provide('g1VersionTrailRef', versionTrailRef)
provide('g1OpenVersionHistory', openVersionHistory)

// autoSnapshot on save：子组件 debouncedSave → 持久化后触发版本快照（debounce）
const formData = useG1TraFinFormData({
  wpId: wpIdRef,
  projectId: computed(() => props.projectId),
  onAfterSave: () => scheduleAutoSnapshot(),
})

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 模板名多为「附注披露信息（上市公司）/（国企）」；兼容半角括号与缩写
  if (/G1-note-listed|附注披露.*上市|附注.*上市/.test(name)) return '附注上市'
  if (/G1-note-soe|附注披露.*国企|附注.*国企/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(G1A|G1-\d+)/i)
  return m ? m[1].toUpperCase().replace(/^G1A$/i, 'G1A') : ''
})

const MIGRATED_SHEETS = new Set([
  'G1A', 'G1-1', 'G1-2', 'G1-3', 'G1-4', 'G1-5', 'G1-6', 'G1-7',
  'G1-8', 'G1-9', 'G1-10', 'G1-11', 'G1-12', 'G1-13', 'G1-14',
])

const isHtmlSheet = computed(() => {
  const code = currentSheet.value
  return code === 'G1A' || MIGRATED_SHEETS.has(code) || code.startsWith('附注')
})

const sheetNameRef = computed(() => props.sheetName || '')

const dualMode = useG1DualMode({
  wpId: wpIdRef,
  sheetName: sheetNameRef,
  reloadAll: () => formData.loadAll(),
})

const useGridFallback = computed(() => {
  const code = currentSheet.value
  return !!code && code !== 'G1A' && !MIGRATED_SHEETS.has(code) && !code.startsWith('附注')
})

async function selfLoad() {
  await formData.loadAll()
  isLoading.value = false
}

function onSheetImported() {
  void formData.loadAll()
}

onMounted(() => { void selfLoad() })
</script>

<style scoped>
.g1-trading-financial-assets { padding: 12px; }
.loading-container { padding: 24px; }
.g1-toolbar { margin-bottom: 8px; }
</style>
