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
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
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
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G11TabAdjustment
        v-else-if="currentSheet === 'G11-3'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G11TabReturnRateAnalysis
        v-else-if="currentSheet === 'G11-4'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G11TabVoucherCheck
        v-else-if="currentSheet === 'G11-5'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G11TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G11TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <div v-else-if="currentSheet === '底稿目录'" class="g-cycle-tab-index-page">
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
 * GtG11InvestmentIncome — G11 投资收益底稿主入口
 * sheetName v-if 分发（参照 D4/G14 精细模式）
 */
import { ref, computed, onMounted, defineAsyncComponent, provide } from 'vue'
import { useG11FormData } from './composables/useG11FormData'
import { useG11DualMode } from './composables/useG11DualMode'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import { useWorkpaperReviewProvide } from './composables/useWorkpaperReviewProvide'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
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
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

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
const isReadonly = computed(() => !!props.readonly)
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar

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
  reloadAll: () => formData.loadAll(),
})

const useGridFallback = computed(() => {
  const code = currentSheet.value
  return !!code && !isHtmlSheet.value
})

function onDebouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
  formData.debouncedSave(itemId, data)
  versionToolbar.scheduleAutoSnapshot()
}

async function reloadAll() {
  await formData.loadAll()
}

const availableSheets = computed(() =>
  props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets ?? [],
)

useWorkpaperReviewProvide({ wpId: wpIdRef, projectId: projectIdRef })
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: reloadAll,
})

onMounted(async () => {
  await formData.loadAll()
  isLoading.value = false
})
</script>

<style scoped>
.g11-investment-income { padding: 12px; }
.loading-container { padding: 24px; }
.g11-investment-income-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
</style>
