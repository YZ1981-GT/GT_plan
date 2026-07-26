<template>
  <div class="g10-trading-financial-liabilities">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="currentSheet !== '底稿目录'" class="g10-trading-financial-liabilities-toolbar">
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

      <G10TabProcedure
        v-else-if="currentSheet === 'G10A'"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G10TabAdjudication
        v-else-if="currentSheet === 'G10-1'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabDetail
        v-else-if="currentSheet === 'G10-2'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabAdjustment
        v-else-if="currentSheet === 'G10-3'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear ?? undefined"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabClassificationCheck
        v-else-if="currentSheet === 'G10-4'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabFairValueTest
        v-else-if="currentSheet === 'G10-5'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabL3Reconciliation
        v-else-if="currentSheet === 'G10-6'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabVoucherCheck
        v-else-if="currentSheet === 'G10-7'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabDerivativeCheck
        v-else-if="currentSheet === 'G10-8'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <div v-else-if="currentSheet === '底稿目录'" class="g-cycle-tab-index-page">
        <G10TabDirectory
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
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG10TradingFinancialLiabilities — G10 交易性金融负债底稿主入口
 * 对齐 G8：formData + g10:save-items + 附注路由 + 双模式 reload
 */
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent, provide, inject } from 'vue'
import { useG10FormData } from './composables/useG10FormData'
import { G10_ACCOUNT_CODE } from './composables/g10Constants'
import { offerG10DisclosurePull, G10_OFFER_DISCLOSURE_PULL_EVENT } from './composables/g10DisclosureSync'
import { parseNum } from './composables/useG10FormulaEngine'
import { useG10DualMode } from './composables/useG10DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import type { ChecklistResponse } from './composables/useF1FormData'

const G10TabProcedure = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabProcedure.vue'))
const G10TabAdjudication = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabAdjudication.vue'))
const G10TabDetail = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabDetail.vue'))
const G10TabAdjustment = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabAdjustment.vue'))
const G10TabClassificationCheck = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/classification/G10TabClassificationCheck.vue'))
const G10TabFairValueTest = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/classification/G10TabFairValueTest.vue'))
const G10TabL3Reconciliation = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/classification/G10TabL3Reconciliation.vue'))
const G10TabVoucherCheck = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/voucher/G10TabVoucherCheck.vue'))
const G10TabDerivativeCheck = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/voucher/G10TabDerivativeCheck.vue'))
const G10TabDisclosureListed = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabDisclosureListed.vue'))
const G10TabDisclosureSOE = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabDisclosureSOE.vue'))
const G10TabDirectory = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabDirectory.vue'))
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

const emit = defineEmits<{
  (e: 'jump-to-section', sheetName: string): void
}>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const formData = useG10FormData({ wpId: wpIdRef, projectId: projectIdRef })
const isReadonly = computed(() => !!props.readonly)

const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('g10VersionTrailRef', versionTrailRef)
provide('g10OpenVersionHistory', openVersionHistory)

/** 审计年度：供 G10-3 与中央调整分录模块同步 */
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

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/G10-note-listed|附注披露.*上市|附注.*上市/.test(name)) return '附注上市'
  if (/G10-note-soe|附注披露.*国企|附注.*国企/.test(name)) return '附注国企'
  if (/G10-directory|底稿目录/.test(name)) return '底稿目录'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(G10A|G10-\d+)/)
  return m ? m[1] : ''
})

const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return ['G10A', 'G10-1', 'G10-2', 'G10-3', 'G10-4', 'G10-5', 'G10-6', 'G10-7', 'G10-8', '底稿目录'].includes(s)
    || s.startsWith('附注')
})

const dualMode = useG10DualMode({
  wpId: wpIdRef,
  reloadAll: () => formData.loadAll(),
})

const useGridFallback = computed(() => {
  const code = currentSheet.value
  if (!code) return false
  const htmlSheets = ['G10A', 'G10-1', 'G10-2', 'G10-3', 'G10-4', 'G10-5', 'G10-6', 'G10-7', 'G10-8', '底稿目录']
  if (htmlSheets.includes(code) || code.startsWith('附注')) return false
  return isHtmlSheet.value && dualMode.currentMode.value === 'html'
})

function onDebouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
  formData.debouncedSave(itemId, data)
  scheduleAutoSnapshot()
}

async function handleG10SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    for (const it of items) {
      if (it?.item_id) await formData.saveImmediate(it.item_id, it)
    }
    scheduleAutoSnapshot()
  }
}

function handleG10OfferDisclosurePull(): void {
  void offerG10DisclosurePull(
    formData.allResponses.value,
    formData.debouncedSave,
    auditYear.value,
  )
}

async function reloadAll() {
  await formData.loadAll()
}

function handleG10Writeback(e: Event): void {
  const detail = (e as CustomEvent<{ accountCode?: string; auditedAmount?: number; forceToast?: boolean }>).detail
  if (detail?.accountCode && detail.accountCode !== G10_ACCOUNT_CODE) return
  const amount = parseNum(detail?.auditedAmount)
  if (!Number.isFinite(amount)) return
  void formData.writebackTB(amount, { forceToast: !!detail?.forceToast })
}

const availableSheets = computed(() => {
  const fromHtml = props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml
  const metaSheets = formData.renderMeta.value?.sheets
  if (Array.isArray(metaSheets) && metaSheets.length) return metaSheets
  // 对齐 G1：无 sheets 元数据时用自加载 render-config 的 sheetCache 兜底，
  // 保证底稿目录架构树非空
  return Object.keys(formData.sheetCache.value).map(sheet_name => ({ sheet_name }))
})

const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: reloadAll,
})

onMounted(async () => {
  window.addEventListener('g10:save-items', handleG10SaveItems)
  window.addEventListener('g10:writeback-trial-balance', handleG10Writeback)
  window.addEventListener(G10_OFFER_DISCLOSURE_PULL_EVENT, handleG10OfferDisclosurePull)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g10:save-items', handleG10SaveItems)
  window.removeEventListener('g10:writeback-trial-balance', handleG10Writeback)
  window.removeEventListener(G10_OFFER_DISCLOSURE_PULL_EVENT, handleG10OfferDisclosurePull)
  formData.flushPending()
})
</script>

<style scoped>
.g10-trading-financial-liabilities { padding: 12px; }
.loading-container { padding: 24px; }
.g10-trading-financial-liabilities-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
</style>
