<template>
  <div class="g12-net-hedge-gains">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="currentSheet !== '底稿目录'" class="g12-net-hedge-gains-toolbar">
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

      <G12TabProcedure
        v-else-if="currentSheet === 'G12A'"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G12TabAdjudication
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
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G12TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
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
import { ref, computed, onMounted, defineAsyncComponent, provide } from 'vue'
import { useG12FormData } from './composables/useG12FormData'
import { useG12DualMode } from './composables/useG12DualMode'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import { useWorkpaperReviewProvide } from './composables/useWorkpaperReviewProvide'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import type { ChecklistResponse } from './composables/useF1FormData'

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
const formData = useG12FormData({ wpId: wpIdRef, projectId: projectIdRef })
const isReadonly = computed(() => !!props.readonly)
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/底稿目录/.test(name)) return '底稿目录'
  if (/附注披露/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(G12A|G12-\d+)/)
  return m ? m[1] : ''
})

const HTML_SHEETS = ['G12A', 'G12-1', 'G12-2', 'G12-3', 'G12-4', 'G12-5', 'G12-6', '底稿目录']

const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return HTML_SHEETS.includes(s) || s.startsWith('附注')
})

const dualMode = useG12DualMode({
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
.g12-net-hedge-gains { padding: 12px; }
.g-cycle-tab-index-page { padding: 0; }
.loading-container { padding: 24px; }
.g12-net-hedge-gains-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
</style>
