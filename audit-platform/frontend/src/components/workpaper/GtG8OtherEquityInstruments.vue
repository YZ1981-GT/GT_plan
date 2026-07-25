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
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G8TabAdjustment
        v-else-if="currentSheet === 'G8-3'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G8TabFairValueTest
        v-else-if="currentSheet === 'G8-4'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G8TabDesignationCheck
        v-else-if="currentSheet === 'G8-5'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G8TabVoucherCheck
        v-else-if="currentSheet === 'G8-6'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :year="auditYear ?? undefined"
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

      <G8TabRefValuationGuidance
        v-else-if="currentSheet === '参考中证协'"
        :html-data="props.htmlData || formData.getSheet(currentSheet)"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="true"
      />

      <template v-else-if="currentSheet === '底稿目录'">
        <div class="g8-index-toolbar">
          <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        </div>
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
          :all-responses="formData.allResponses.value"
        />
      </template>

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
  </div>
</template>

<script setup lang="ts">
/**
 * GtG8OtherEquityInstruments — G8 其他权益工具投资底稿主入口
 * 对齐 G5/G6：formData + g8:save-items + 附注路由 + 双模式 reload
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
const G8TabRefValuationGuidance = defineAsyncComponent(() => import('./g8-other-equity-instruments/reference/G8TabRefValuationGuidance.vue'))
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

const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

/** 审计年度：抽凭引擎 / A13 错报 / G8A 回填；优先 htmlData，回退 Runtime */
const auditYear = computed(() => {
  const raw =
    props.htmlData?.project_context?.audit_year
    ?? props.htmlData?.projectContext?.audit_year
    ?? props.htmlData?.audit_year
    ?? runtime?.year?.value
    ?? null
  if (raw == null || raw === '') return null
  const n = Number(raw)
  return Number.isFinite(n) && n >= 1900 ? Math.trunc(n) : null
})

provide('g8VersionTrailRef', versionTrailRef)
provide('g8OpenVersionHistory', openVersionHistory)
provide('reloadWorkpaperData', () => formData.loadAll())

const currentSheet = computed(() => extractG8SheetCode(props.sheetName || props.wpCode || ''))

const HTML_SHEETS = new Set(['G8A', 'G8-1', 'G8-2', 'G8-3', 'G8-4', 'G8-5', 'G8-6', '附注上市', '附注国企', '底稿目录', '参考中证协'])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))
const useGridFallback = computed(() => !!currentSheet.value && !isHtmlSheet.value)

const availableSheets = computed(() => {
  const fromHtml = props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml
  const metaSheets = formData.renderMeta.value?.sheets
  if (Array.isArray(metaSheets) && metaSheets.length) return metaSheets
  // 对齐 G1：无 sheets 元数据时用自加载 render-config 的 sheetCache 兜底，
  // 保证底稿目录架构树非空
  return Object.keys(formData.sheetCache.value).map(sheet_name => ({ sheet_name }))
})

const dualMode = useG8DualMode({ wpId: wpIdRef, reloadAll: () => formData.loadAll() })

function onDebouncedSave(id: string, d: Partial<ChecklistResponse>) {
  formData.debouncedSave(id, d)
  scheduleAutoSnapshot()
}

async function handleG8SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    for (const it of items) {
      if (it?.item_id) await formData.saveImmediate(it.item_id, it)
    }
    scheduleAutoSnapshot()
  }
}

function handleG8Writeback(e: Event): void {
  const detail = (e as CustomEvent<{ accountCode?: string; auditedAmount?: number; forceToast?: boolean }>).detail
  if (detail?.accountCode && detail.accountCode !== G8_ACCOUNT_CODE) return
  const amount = parseNum(detail?.auditedAmount)
  if (!Number.isFinite(amount)) return
  void formData.writebackTB(amount, { forceToast: !!detail?.forceToast })
}

async function reloadAll() {
  await formData.loadAll()
}

onMounted(async () => {
  window.addEventListener('g8:save-items', handleG8SaveItems)
  // TB 回写仅听 g8:writeback-trial-balance（substantive:adjudicated 供跨模块刷新，不重复写 TB）
  window.addEventListener('g8:writeback-trial-balance', handleG8Writeback)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g8:save-items', handleG8SaveItems)
  window.removeEventListener('g8:writeback-trial-balance', handleG8Writeback)
  formData.flushPending()
})
</script>

<style scoped>
.g8-other-equity-instruments { padding: 12px; }
.loading-container { padding: 24px; }
.g8-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.g8-index-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
</style>
