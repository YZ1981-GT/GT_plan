<template>
  <div class="g12-net-hedge-gains">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="currentSheet !== '底稿目录'" class="g12-net-hedge-gains-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g12-net-hedge-gains" />
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

      <G12TabProcedure
        v-else-if="currentSheet === 'G12A'"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G12TabAdjudication
        :html-data="props.htmlData"
        v-else-if="currentSheet === 'G12-1'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G12TabHedgeDetail
        v-else-if="currentSheet === 'G12-2'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G12TabAdjustment
        v-else-if="currentSheet === 'G12-3'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G12TabFairValueTest
        v-else-if="currentSheet === 'G12-4'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G12TabNetExposureCheck
        v-else-if="currentSheet === 'G12-5'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G12TabVoucherCheck
        v-else-if="currentSheet === 'G12-6'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G12TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        variant="listed"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G12TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <div v-else-if="currentSheet === '底稿目录'" class="g-cycle-tab-index-page">
        <G12TabDirectory
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

      <!-- 版本链/复核 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent, provide, inject } from 'vue'
import { useG12FormData } from './composables/useG12FormData'
import { useG12DualMode } from './composables/useG12DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { G12_ACCOUNT_CODE } from './composables/g12Constants'
import { parseNum } from './composables/useG12FormulaEngine'
import type { ChecklistResponse } from './composables/useF1FormData'
import { useHostApplicableStandards } from './composables/hostApplicableStandards'
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'

const G12TabProcedure = defineAsyncComponent(() => import('./g12-net-hedge-gains/core/G12TabProcedure.vue'))
const G12TabAdjudication = defineAsyncComponent(() => import('./g12-net-hedge-gains/core/G12TabAdjudication.vue'))
const G12TabAdjustment = defineAsyncComponent(() => import('./g12-net-hedge-gains/core/G12TabAdjustment.vue'))
const G12TabDisclosureListed = defineAsyncComponent(() => import('./g12-net-hedge-gains/core/G12TabDisclosureListed.vue'))
const G12TabDisclosureSOE = defineAsyncComponent(() => import('./g12-net-hedge-gains/core/G12TabDisclosureSOE.vue'))
const G12TabDirectory = defineAsyncComponent(() => import('./g12-net-hedge-gains/core/G12TabDirectory.vue'))
const GCycleBIndexExtras = defineAsyncComponent(() => import('./shared/GCycleBIndexExtras.vue'))
const G12TabHedgeDetail = defineAsyncComponent(() => import('./g12-net-hedge-gains/hedging/G12TabHedgeDetail.vue'))
const G12TabFairValueTest = defineAsyncComponent(() => import('./g12-net-hedge-gains/hedging/G12TabFairValueTest.vue'))
const G12TabNetExposureCheck = defineAsyncComponent(() => import('./g12-net-hedge-gains/hedging/G12TabNetExposureCheck.vue'))
const G12TabVoucherCheck = defineAsyncComponent(() => import('./g12-net-hedge-gains/voucher/G12TabVoucherCheck.vue'))
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
const formData = useG12FormData({ wpId: wpIdRef, projectId: projectIdRef })
const isReadonly = computed(() => !!props.readonly)
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('g12VersionTrailRef', versionTrailRef)
provide('g12OpenVersionHistory', openVersionHistory)

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/底稿目录/.test(name)) return '底稿目录'
  // 🔴 「国企」与「国有企业」两种写法都要认（24 份源模板用后者，误判会把国企 TAB
  //    渲染成上市组件；vitest 与 get_diagnostics 都查不出，只有浏览器实测能发现）
  if (/附注披露/.test(name)) return /国企|国有/.test(name) ? '附注国企' : '附注上市'
  const m = name.match(/(G12A|G12-\d+)/)
  return m ? m[1] : ''
})

// 适用准则：显式 prop > 本 sheet html_data > runtime context（scaffold 从 render-config
// 顶层注入）。收敛到共享 composable，兼容 v2 对象 / 逗号串 / JSON 串。
const applicableStandards = useHostApplicableStandards({
  htmlData: () => props.htmlData,
})

const HTML_SHEETS = ['G12A', 'G12-1', 'G12-2', 'G12-3', 'G12-4', 'G12-5', 'G12-6', '底稿目录']

const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return HTML_SHEETS.includes(s) || s.startsWith('附注')
})

const dualMode = useG12DualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

const useGridFallback = computed(() => {
  const code = currentSheet.value
  return !!code && !isHtmlSheet.value
})

function onDebouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
  formData.debouncedSave(itemId, data)
  scheduleAutoSnapshot()
}

function handleG12Writeback(e: Event): void {
  const detail = (e as CustomEvent<{ accountCode?: string; auditedAmount?: number }>).detail
  if (detail?.accountCode && detail.accountCode !== G12_ACCOUNT_CODE) return
  const amount = parseNum(detail?.auditedAmount)
  if (!Number.isFinite(amount)) return
  void formData.writebackTrialBalance(amount)
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
  // TB 回写仅听 g12:writeback-trial-balance（substantive:adjudicated 供跨模块刷新，不重复写 TB）
  window.addEventListener('g12:writeback-trial-balance', handleG12Writeback)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g12:writeback-trial-balance', handleG12Writeback)
  formData.flushPending()
})
</script>

<style scoped>
.g12-net-hedge-gains { padding: 12px; }
.g-cycle-tab-index-page { padding: 0; }
.loading-container { padding: 24px; }
.g12-net-hedge-gains-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
</style>
