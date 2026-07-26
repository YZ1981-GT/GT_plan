<template>
  <div class="g14-credit-impairment-loss">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="currentSheet !== '底稿目录'" class="g14-credit-impairment-loss-toolbar">
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

      <G14TabProcedure
        v-else-if="currentSheet === 'G14A'"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G14TabAdjudication
        v-else-if="currentSheet === 'G14-1'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G14TabDetail
        v-else-if="currentSheet === 'G14-2'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G14TabAdjustment
        v-else-if="currentSheet === 'G14-3'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G14TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G14TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <template v-else-if="currentSheet === '底稿目录'">
        <div class="g14-index-toolbar">
          <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        </div>
        <div class="g-cycle-tab-index-page">
          <G14TabDirectory
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
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent, provide, inject } from 'vue'
import { useG14FormData } from './composables/useG14FormData'
import { useG14DualMode } from './composables/useG14DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { G14_ACCOUNT_CODE } from './composables/g14Constants'
import { parseNum } from './composables/useG14FormulaEngine'
import type { ChecklistResponse } from './composables/useF1FormData'

const G14TabProcedure = defineAsyncComponent(() => import('./g14-credit-impairment-loss/G14TabProcedure.vue'))
const G14TabAdjudication = defineAsyncComponent(() => import('./g14-credit-impairment-loss/G14TabAdjudication.vue'))
const G14TabDetail = defineAsyncComponent(() => import('./g14-credit-impairment-loss/G14TabDetail.vue'))
const G14TabAdjustment = defineAsyncComponent(() => import('./g14-credit-impairment-loss/G14TabAdjustment.vue'))
const G14TabDisclosureListed = defineAsyncComponent(() => import('./g14-credit-impairment-loss/G14TabDisclosureListed.vue'))
const G14TabDisclosureSOE = defineAsyncComponent(() => import('./g14-credit-impairment-loss/G14TabDisclosureSOE.vue'))
const G14TabDirectory = defineAsyncComponent(() => import('./g14-credit-impairment-loss/G14TabDirectory.vue'))
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
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  (e: 'jump-to-section', sheetName: string): void
}>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const formData = useG14FormData({ wpId: wpIdRef, projectId: projectIdRef })
const isReadonly = computed(() => !!props.readonly)
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)

const applicableStandards = computed<string[]>(() => {
  const fromProp = props.applicableStandards
  if (Array.isArray(fromProp) && fromProp.length) return fromProp
  return (
    runtime?.applicableStandards?.value
    ?? props.htmlData?.applicable_standards
    ?? props.htmlData?.applicableStandards
    ?? []
  )
})

const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('g14VersionTrailRef', versionTrailRef)
provide('g14OpenVersionHistory', openVersionHistory)

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/底稿目录/.test(name)) return '底稿目录'
  if (/附注披露/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(G14A|G14-\d+)/)
  return m ? m[1] : ''
})

const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return ['G14A', 'G14-1', 'G14-2', 'G14-3', '底稿目录'].includes(s) || s.startsWith('附注')
})

const dualMode = useG14DualMode({
  wpId: wpIdRef,
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

function handleG14Writeback(e: Event): void {
  const detail = (e as CustomEvent<{ accountCode?: string; auditedAmount?: number }>).detail
  if (detail?.accountCode && detail.accountCode !== G14_ACCOUNT_CODE) return
  const amount = parseNum(detail?.auditedAmount)
  if (!Number.isFinite(amount)) return
  void formData.writebackTrialBalance(amount)
}

async function reloadAll() {
  await formData.loadAll()
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

// 复核对话 provider 由 Runtime Boundary(GtWpRenderer) 统一提供 openReviewDialog
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: reloadAll,
})

onMounted(async () => {
  // TB 回写仅听 g14:writeback-trial-balance（substantive:adjudicated 供跨模块刷新，不重复写 TB）
  window.addEventListener('g14:writeback-trial-balance', handleG14Writeback)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g14:writeback-trial-balance', handleG14Writeback)
  formData.flushPending()
})
</script>

<style scoped>
.g14-credit-impairment-loss { padding: 12px; }
.g-cycle-tab-index-page { padding: 0; }
.g14-index-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.loading-container { padding: 24px; }
.g14-credit-impairment-loss-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
</style>
