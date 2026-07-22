<template>
  <div class="g11-investment-income">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="currentSheet !== '底稿目录'" class="g11-investment-income-toolbar">
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

      <el-alert
        v-if="showCrossAlert && crossValidation.detailCrossValidation.value"
        type="warning"
        :closable="false"
        class="g11-cross-alert"
        data-testid="g11-page-cross-alert"
      >
        {{ crossValidation.detailCrossValidation.value }}
        <span class="g11-cross-chips">
          <GtIndexChip
            label="G11-1"
            :prevent-navigate="true"
            :validate="false"
            @click="jumpToG11Sheet('G11-1')"
          />
          <GtIndexChip
            label="G11-2"
            :prevent-navigate="true"
            :validate="false"
            @click="jumpToG11Sheet('G11-2')"
          />
        </span>
      </el-alert>

      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <G11TabProcedure
        v-else-if="currentSheet === 'G11A'"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G11TabAdjudication
        v-else-if="currentSheet === 'G11-1'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G11TabDetailAnalysis
        v-else-if="currentSheet === 'G11-2'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :html-data="props.htmlData"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G11TabAdjustment
        v-else-if="currentSheet === 'G11-3'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G11TabReturnRateAnalysis
        v-else-if="currentSheet === 'G11-4'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G11TabVoucherCheck
        v-else-if="currentSheet === 'G11-5'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G11TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G11TabDisclosureSOE
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
        <div class="g-cycle-tab-index-page">
          <G11TabDirectory
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
 * GtG11InvestmentIncome — G11 投资收益底稿主入口
 * sheetName v-if 分发（参照 D4/G14 精细模式）
 */
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent, provide, inject } from 'vue'
import { useG11FormData } from './composables/useG11FormData'
import { useG11DualMode } from './composables/useG11DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { G11_ACCOUNT_CODE } from './composables/g11Constants'
import { parseNum } from './composables/useG11FormulaEngine'
import { useG11CrossValidation } from './composables/useG11CrossValidation'
import { resolveG11SheetLabel } from './composables/g11SheetLabels'
import { offerG11DisclosurePull, G11_OFFER_DISCLOSURE_PULL_EVENT, promptForG11DisclosureSource } from './composables/g11DisclosureSync'
import GtIndexChip from './GtIndexChip.vue'
import type { ChecklistResponse } from './composables/useF1FormData'

const G11TabProcedure = defineAsyncComponent(() => import('./g11-investment-income/core/G11TabProcedure.vue'))
const G11TabAdjudication = defineAsyncComponent(() => import('./g11-investment-income/core/G11TabAdjudication.vue'))
const G11TabDetailAnalysis = defineAsyncComponent(() => import('./g11-investment-income/core/G11TabDetailAnalysis.vue'))
const G11TabAdjustment = defineAsyncComponent(() => import('./g11-investment-income/core/G11TabAdjustment.vue'))
const G11TabReturnRateAnalysis = defineAsyncComponent(() => import('./g11-investment-income/analysis/G11TabReturnRateAnalysis.vue'))
const G11TabVoucherCheck = defineAsyncComponent(() => import('./g11-investment-income/voucher/G11TabVoucherCheck.vue'))
const G11TabDisclosureListed = defineAsyncComponent(() => import('./g11-investment-income/core/G11TabDisclosureListed.vue'))
const G11TabDisclosureSOE = defineAsyncComponent(() => import('./g11-investment-income/core/G11TabDisclosureSOE.vue'))
const G11TabDirectory = defineAsyncComponent(() => import('./g11-investment-income/core/G11TabDirectory.vue'))
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
const formData = useG11FormData({ wpId: wpIdRef, projectId: projectIdRef })
const crossValidation = useG11CrossValidation(formData.allResponses)
const isReadonly = computed(() => !!props.readonly)
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const auditYear = computed(() => {
  const y =
    props.htmlData?.project_context?.audit_year
    ?? props.htmlData?.projectContext?.audit_year
    ?? props.htmlData?.audit_year
    ?? runtime?.year?.value
  const n = Number(y)
  return Number.isFinite(n) && n > 0 ? n : null
})
const applicableStandards = computed<string[]>(() => {
  const raw =
    props.htmlData?.project_context?.applicable_standards
    ?? props.htmlData?.projectContext?.applicable_standards
    ?? props.htmlData?.applicable_standards
    ?? runtime?.applicableStandards?.value
  return Array.isArray(raw) ? raw.map(String) : []
})
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('g11VersionTrailRef', versionTrailRef)
provide('g11OpenVersionHistory', openVersionHistory)

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/底稿目录/.test(name)) return '底稿目录'
  if (/附注披露/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(G11A|G11-\d+)/)
  return m ? m[1] : ''
})

const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return ['G11A', 'G11-1', 'G11-2', 'G11-3', 'G11-4', 'G11-5', '底稿目录'].includes(s) || s.startsWith('附注')
})

const dualMode = useG11DualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

const useGridFallback = computed(() => {
  const code = currentSheet.value
  return !!code && !isHtmlSheet.value
})

const showCrossAlert = computed(() =>
  ['G11-1', 'G11-2', 'G11-3', 'G11-4'].includes(currentSheet.value),
)

function jumpToG11Sheet(code: string): void {
  emit('jump-to-section', resolveG11SheetLabel(code, availableSheets.value))
}

function onDebouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
  formData.debouncedSave(itemId, data)
  scheduleAutoSnapshot()
}

function handleG11Writeback(e: Event): void {
  const detail = (e as CustomEvent<{ accountCode?: string; auditedAmount?: number }>).detail
  if (detail?.accountCode && detail.accountCode !== G11_ACCOUNT_CODE) return
  const amount = parseNum(detail?.auditedAmount)
  if (!Number.isFinite(amount)) return
  void formData.writebackTrialBalance(amount)
}

function handleG11OfferDisclosurePull(e: Event): void {
  const source = (e as CustomEvent<{ source?: string }>).detail?.source
  void offerG11DisclosurePull(
    formData.allResponses.value,
    formData.debouncedSave,
    promptForG11DisclosureSource(source),
  )
}

async function reloadAll() {
  await formData.loadAll()
}

const availableSheets = computed(() => {
  const metaSheets = formData.renderMeta.value?.sheets
  if (Array.isArray(metaSheets) && metaSheets.length) return metaSheets
  const fromHtml = props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml
  // 对齐 G1：无 sheets 元数据时用自加载 render-config 的 sheetCache 兜底，
  // 保证底稿目录架构树非空
  return Object.keys(formData.sheetCache.value).map(sheet_name => ({ sheet_name }))
})

// 复核对话 provider 由 Runtime Boundary(GtWpRenderer) 统一提供 openReviewDialog
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: reloadAll,
})

onMounted(async () => {
  // TB 回写仅听 g11:writeback-trial-balance（substantive:adjudicated 供跨模块刷新，不重复写 TB）
  window.addEventListener('g11:writeback-trial-balance', handleG11Writeback)
  window.addEventListener(G11_OFFER_DISCLOSURE_PULL_EVENT, handleG11OfferDisclosurePull)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g11:writeback-trial-balance', handleG11Writeback)
  window.removeEventListener(G11_OFFER_DISCLOSURE_PULL_EVENT, handleG11OfferDisclosurePull)
  formData.flushPending()
})
</script>

<style scoped>
.g11-investment-income { padding: 12px; }
.loading-container { padding: 24px; }
.g11-investment-income-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.g11-cross-alert { margin-bottom: 8px; }
.g11-cross-chips { margin-left: 8px; display: inline-flex; gap: 6px; }
.g-cycle-tab-index-page { display: flex; flex-direction: column; gap: 12px; }
</style>
