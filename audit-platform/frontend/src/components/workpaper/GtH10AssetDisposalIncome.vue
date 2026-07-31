<template>
  <div class="h10-asset-disposal-income">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== '底稿目录'" class="h10-toolbar">
        <el-segmented
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-tag v-if="dualMode.ooConfigReady.value" size="small" type="success">OnlyOffice 拉取成功</el-tag>
        <el-tag v-else-if="dualMode.fetchingConfig.value" size="small" type="info">拉取中…</el-tag>
        <el-tag v-else-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && currentSheet !== '底稿目录' && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
        @fallback="dualMode.onOoLoadFailed"
      />

      <H10TabProcedure
        v-else-if="currentSheet === 'H10A'"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <HiFourTableSourcePanel
        v-if="props.htmlData?.hi_extraction_enabled"
        :wp-code="'H10'"
        :segments="getHiExtractionSegments('H10')"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
        @refresh-complete="selfLoad()"
      />
      <H10TabAdjudication
        v-else-if="currentSheet === 'H10-1'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        :writeback-trial-balance="formData.writebackTrialBalance"
        @imported="reloadAll"
      />

      <H10TabDetail
        v-else-if="currentSheet === 'H10-2'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <H10TabAdjustment
        v-else-if="currentSheet === 'H10-3'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <H10TabCheck
        v-else-if="currentSheet === 'H10-4'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :year="runtime?.year?.value"
        :debounced-save="onDebouncedSave"
      />

      <H10TabDisclosureBase
        v-else-if="currentSheet === '附注上市'"
        variant="listed"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <H10TabDisclosureBase
        v-else-if="currentSheet === '附注国企'"
        variant="soe"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <div v-else-if="currentSheet === '底稿目录'" class="h-cycle-tab-index-page">
        <H10TabDirectory
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
          :show-architecture="false"
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

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtH10AssetDisposalIncome — H10 资产处置损益主入口
 * 科目 6115 损益类；EventBus: disposal:completed(H6) / substantive:adjudicated(6115)
 */
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent, provide, inject} from 'vue'
import { useH10FormData } from './composables/useH10FormData'
import { useH10DualMode } from './composables/useH10DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewProvide } from './composables/useWorkpaperReviewProvide'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { H10_ACCOUNT_CODE } from './composables/h10Constants'
import type { ChecklistResponse } from './composables/useF1FormData'
import HiFourTableSourcePanel from './shared/HiFourTableSourcePanel.vue'
import { getHiExtractionSegments } from './composables/hiExtractionSegments'
import { useHostApplicableStandards } from './composables/hostApplicableStandards'

const H10TabProcedure = defineAsyncComponent(() => import('./h10/core/H10TabProcedure.vue'))
const H10TabAdjudication = defineAsyncComponent(() => import('./h10/core/H10TabAdjudication.vue'))
const H10TabDetail = defineAsyncComponent(() => import('./h10/core/H10TabDetail.vue'))
const H10TabAdjustment = defineAsyncComponent(() => import('./h10/core/H10TabAdjustment.vue'))
const H10TabCheck = defineAsyncComponent(() => import('./h10/inspection/H10TabCheck.vue'))
const H10TabDisclosureBase = defineAsyncComponent(() => import('./h10/core/H10TabDisclosureBase.vue'))
const H10TabDirectory = defineAsyncComponent(() => import('./h10/core/H10TabDirectory.vue'))
const GCycleBIndexExtras = defineAsyncComponent(() => import('./shared/GCycleBIndexExtras.vue'))
const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{ (e: 'jump-to-section', sheetName: string): void }>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const formData = useH10FormData({ wpId: wpIdRef, projectId: projectIdRef })
const isReadonly = computed(() => !!props.readonly)
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)

// 适用准则：显式 prop > 本 sheet html_data > runtime context（scaffold 从 render-config
// 顶层注入）。收敛到共享 composable，兼容 v2 对象 / 逗号串 / JSON 串。
const applicableStandards = useHostApplicableStandards({
  explicit: () => props.applicableStandards,
  htmlData: () => props.htmlData,
})

const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('h10VersionTrailRef', versionTrailRef)
provide('h10OpenVersionHistory', openVersionHistory)

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/底稿目录/.test(name)) return '底稿目录'
  if (/附注披露/.test(name)) {
    return name.includes('国有') || name.includes('国企') ? '附注国企' : '附注上市'
  }
  const m = name.match(/(H10A|H10-\d+)/)
  return m ? m[1] : ''
})

const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return ['H10A', 'H10-1', 'H10-2', 'H10-3', 'H10-4', '底稿目录'].includes(s) || s.startsWith('附注')
})

const dualMode = useH10DualMode({ wpId: wpIdRef, projectId: projectIdRef, reloadAll: () => formData.loadAll() })
const useGridFallback = computed(() => !!currentSheet.value && !isHtmlSheet.value)

function onDebouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
  formData.debouncedSave(itemId, data)
  scheduleAutoSnapshot()
}

async function reloadAll() {
  await formData.loadAll()
}

const availableSheets = computed(() =>
  props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets ?? [],
)

function handleDisposalCompleted(ev: Event) {
  const detail = (ev as CustomEvent).detail ?? {}
  formData.handleDisposalCompleted(detail)
}

function handleSourceDisposalUpdated(ev: Event) {
  const detail = (ev as CustomEvent).detail ?? {}
  formData.handleSourceDisposalUpdated(detail)
}

function handleSubstantiveAdjudicated(ev: Event) {
  const detail = (ev as CustomEvent).detail ?? {}
  if (detail.accountCode === H10_ACCOUNT_CODE && detail.wpCode && detail.wpCode !== 'H10') {
    void formData.writebackTrialBalance(Number(detail.adjudicatedAmount ?? detail.auditedAmount ?? 0))
  }
}

useWorkpaperReviewProvide({ wpId: wpIdRef, projectId: projectIdRef })
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({ onJumpToSection: sheetLabel => emit('jump-to-section', sheetLabel), reloadFn: reloadAll })

onMounted(async () => {
  window.addEventListener('disposal:completed', handleDisposalCompleted)
  window.addEventListener('disposal:source-updated', handleSourceDisposalUpdated)
  window.addEventListener('substantive:adjudicated', handleSubstantiveAdjudicated)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('disposal:completed', handleDisposalCompleted)
  window.removeEventListener('disposal:source-updated', handleSourceDisposalUpdated)
  window.removeEventListener('substantive:adjudicated', handleSubstantiveAdjudicated)
})
</script>

<style scoped>
.h10-asset-disposal-income { padding: 12px; }
.loading-container { padding: 24px; }
.h10-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
</style>
