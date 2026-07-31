<template>
  <div class="g9-other-noncurrent-financial">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="currentSheet !== '底稿目录'" class="g9-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          :model-value="dualMode.currentMode.value"
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

      <G9TabProcedure
        v-else-if="currentSheet === 'G9A'"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G9TabAdjudication
        v-else-if="currentSheet === 'G9-1'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G9TabDetail
        v-else-if="currentSheet === 'G9-2'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G9TabAdjustment
        v-else-if="currentSheet === 'G9-3'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear ?? undefined"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G9TabFairValueTest
        v-else-if="currentSheet === 'G9-4'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G9TabL3Reconciliation
        v-else-if="currentSheet === 'G9-5'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G9TabVoucherCheck
        v-else-if="currentSheet === 'G9-6'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :year="auditYear ?? undefined"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G9TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G9TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <template v-else-if="currentSheet === '底稿目录'">
        <div class="g9-index-toolbar">
          <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        </div>
        <G9TabDirectory
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

      <!-- 版本链/复核 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG9OtherNoncurrentFinancial — G9 其他非流动金融资产底稿主入口
 */
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent, provide, inject } from 'vue'
import { useG9FormData } from './composables/useG9FormData'
import { useG9DualMode } from './composables/useG9DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { extractG9SheetCode } from './composables/g9SheetLabels'
import { G9_ACCOUNT_CODE } from './composables/g9Constants'
import { parseNum } from './composables/useG9FormulaEngine'
import type { ChecklistResponse } from './composables/useF1FormData'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useHostApplicableStandards } from './composables/hostApplicableStandards'

const G9TabProcedure = defineAsyncComponent(() => import('./g9-other-noncurrent-financial/core/G9TabProcedure.vue'))
const G9TabAdjudication = defineAsyncComponent(() => import('./g9-other-noncurrent-financial/core/G9TabAdjudication.vue'))
const G9TabDetail = defineAsyncComponent(() => import('./g9-other-noncurrent-financial/core/G9TabDetail.vue'))
const G9TabAdjustment = defineAsyncComponent(() => import('./g9-other-noncurrent-financial/core/G9TabAdjustment.vue'))
const G9TabFairValueTest = defineAsyncComponent(() => import('./g9-other-noncurrent-financial/valuation/G9TabFairValueTest.vue'))
const G9TabL3Reconciliation = defineAsyncComponent(() => import('./g9-other-noncurrent-financial/valuation/G9TabL3Reconciliation.vue'))
const G9TabVoucherCheck = defineAsyncComponent(() => import('./g9-other-noncurrent-financial/voucher/G9TabVoucherCheck.vue'))
const G9TabDisclosureListed = defineAsyncComponent(() => import('./g9-other-noncurrent-financial/core/G9TabDisclosureListed.vue'))
const G9TabDisclosureSOE = defineAsyncComponent(() => import('./g9-other-noncurrent-financial/core/G9TabDisclosureSOE.vue'))
const G9TabDirectory = defineAsyncComponent(() => import('./g9-other-noncurrent-financial/core/G9TabDirectory.vue'))
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
const formData = useG9FormData({ wpId: wpIdRef, projectId: computed(() => props.projectId) })
const isReadonly = computed(() => !!props.readonly)
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

/** 审计年度：抽凭引擎 / G9A 回填；优先 htmlData，回退 Runtime */
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

provide('g9VersionTrailRef', versionTrailRef)
provide('g9OpenVersionHistory', openVersionHistory)

const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

const currentSheet = computed(() => extractG9SheetCode(props.sheetName || props.wpCode || ''))

// 适用准则：显式 prop > 本 sheet html_data > runtime context（scaffold 从 render-config
// 顶层注入）。收敛到共享 composable，兼容 v2 对象 / 逗号串 / JSON 串。
const applicableStandards = useHostApplicableStandards({
  htmlData: () => props.htmlData,
})

const HTML_SHEETS = new Set(['G9A', 'G9-1', 'G9-2', 'G9-3', 'G9-4', 'G9-5', 'G9-6', '附注上市', '附注国企', '底稿目录'])
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

const dualMode = useG9DualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

function onDebouncedSave(id: string, d: Partial<ChecklistResponse>) {
  formData.debouncedSave(id, d)
  scheduleAutoSnapshot()
}

function handleG9Writeback(e: Event): void {
  const detail = (e as CustomEvent<{ accountCode?: string; auditedAmount?: number; forceToast?: boolean }>).detail
  if (detail?.accountCode && detail.accountCode !== G9_ACCOUNT_CODE) return
  const amount = parseNum(detail?.auditedAmount)
  if (!Number.isFinite(amount)) return
  void formData.writebackTB(amount, { forceToast: !!detail?.forceToast })
}

async function reloadAll() {
  await formData.loadAll()
}

onMounted(async () => {
  // TB 回写仅听 g9:writeback-trial-balance（substantive:adjudicated 供跨模块刷新，不重复写 TB）
  window.addEventListener('g9:writeback-trial-balance', handleG9Writeback)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g9:writeback-trial-balance', handleG9Writeback)
  formData.flushPending()
})
</script>

<style scoped>
.g9-other-noncurrent-financial { padding: 12px; }
.loading-container { padding: 24px; }
.g9-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.g9-index-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
</style>
