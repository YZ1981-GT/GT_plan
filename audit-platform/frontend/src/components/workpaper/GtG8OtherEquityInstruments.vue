<template>
  <div class="g8-other-equity-instruments">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="currentSheet !== '底稿目录'" class="g8-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
      </div>

      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <G8TabProcedure
        v-else-if="currentSheet === 'G8A'"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G8TabAdjudication
        v-else-if="currentSheet === 'G8-1'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G8TabDetail
        v-else-if="currentSheet === 'G8-2'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G8TabAdjustment
        v-else-if="currentSheet === 'G8-3'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G8TabFairValueTest
        v-else-if="currentSheet === 'G8-4'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G8TabDesignationCheck
        v-else-if="currentSheet === 'G8-5'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G8TabVoucherCheck
        v-else-if="currentSheet === 'G8-6'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G8TabDisclosureBase
        v-else-if="currentSheet === '附注上市'"
        variant="listed"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G8TabDisclosureBase
        v-else-if="currentSheet === '附注国企'"
        variant="soe"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <div v-else-if="currentSheet === '底稿目录'" class="g-cycle-tab-index-page">
        <G8TabDirectory
          :all-responses="formData.allResponses.value"
          :available-sheets="availableSheets"
        />
        <GCycleBIndexExtras
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName"
          :wp-code="props.wpCode"
          :html-data="props.htmlData"
          :available-sheets="availableSheets"
        />
      </div>

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

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG8OtherEquityInstruments — G8 其他权益工具投资底稿主入口
 */
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent, provide, inject } from 'vue'
import { useG8FormData } from './composables/useG8FormData'
import { useG8DualMode } from './composables/useG8DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { extractG8SheetCode } from './composables/g8SheetLabels'
import { G8_ACCOUNT_CODE } from './composables/g8Constants'
import { parseNum } from './composables/useG8FormulaEngine'
import type { ChecklistResponse } from './composables/useF1FormData'

const G8TabProcedure = defineAsyncComponent(() => import('./g8-other-equity-instruments/core/G8TabProcedure.vue'))
const G8TabAdjudication = defineAsyncComponent(() => import('./g8-other-equity-instruments/core/G8TabAdjudication.vue'))
const G8TabDetail = defineAsyncComponent(() => import('./g8-other-equity-instruments/core/G8TabDetail.vue'))
const G8TabAdjustment = defineAsyncComponent(() => import('./g8-other-equity-instruments/core/G8TabAdjustment.vue'))
const G8TabFairValueTest = defineAsyncComponent(() => import('./g8-other-equity-instruments/valuation/G8TabFairValueTest.vue'))
const G8TabDesignationCheck = defineAsyncComponent(() => import('./g8-other-equity-instruments/valuation/G8TabDesignationCheck.vue'))
const G8TabVoucherCheck = defineAsyncComponent(() => import('./g8-other-equity-instruments/voucher/G8TabVoucherCheck.vue'))
const G8TabDisclosureBase = defineAsyncComponent(() => import('./g8-other-equity-instruments/core/G8TabDisclosureBase.vue'))
const G8TabDirectory = defineAsyncComponent(() => import('./g8-other-equity-instruments/core/G8TabDirectory.vue'))
const GCycleBIndexExtras = defineAsyncComponent(() => import('./shared/GCycleBIndexExtras.vue'))
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
const formData = useG8FormData({ wpId: wpIdRef, projectId: computed(() => props.projectId) })
const isReadonly = computed(() => !!props.readonly)
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('g8VersionTrailRef', versionTrailRef)
provide('g8OpenVersionHistory', openVersionHistory)
// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide，子组件 inject 命中祖先

const currentSheet = computed(() => extractG8SheetCode(props.sheetName || props.wpCode || ''))

const HTML_SHEETS = new Set(['G8A', 'G8-1', 'G8-2', 'G8-3', 'G8-4', 'G8-5', 'G8-6', '附注上市', '附注国企', '底稿目录'])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))
const useGridFallback = computed(() => !!currentSheet.value && !isHtmlSheet.value)

const availableSheets = computed(() => {
  const sheets = formData.renderMeta.value?.sheets
  return Array.isArray(sheets) ? sheets : []
})

const dualMode = useG8DualMode({ wpId: wpIdRef, reloadAll: () => formData.loadAll() })

function onDebouncedSave(id: string, d: Partial<ChecklistResponse>) {
  formData.debouncedSave(id, d)
  scheduleAutoSnapshot()
}

function handleG8Adjudicated(e: Event): void {
  const detail = (e as CustomEvent<{ accountCode?: string; adjudicatedAmount?: number }>).detail
  if (detail?.accountCode !== G8_ACCOUNT_CODE) return
  const amount = parseNum(detail.adjudicatedAmount)
  void formData.writebackTB(amount)
}

async function reloadAll() {
  await formData.loadAll()
}

onMounted(async () => {
  window.addEventListener('substantive:adjudicated', handleG8Adjudicated)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('substantive:adjudicated', handleG8Adjudicated)
})
</script>

<style scoped>
.g8-other-equity-instruments { padding: 12px; }
.loading-container { padding: 24px; }
.g8-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
</style>
