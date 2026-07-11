<template>
  <div class="d3-prepaid-accounts">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="showModeToolbar" class="d3-mode-toolbar">
        <el-segmented v-model="renderMode" :options="renderModeOptions" size="small" />
        <el-tag v-if="!dualMode.ooAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="renderMode === 'onlyoffice'"
        :key="ooSheetName"
        :wp-id="props.wpId"
        :sheet-name="ooSheetName"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @fallback="onOoFallback"
      />

      <template v-else>
        <D3TabIndex
          v-if="currentSheet === 'directory' || currentSheet === 'D3' || currentSheet === 'skip'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :available-sheets="availableSheets"
          :applicable-standards="applicableStandards"
        />

        <D3TabProcedure
          v-else-if="currentSheet === 'D3A'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :html-data="props.htmlData"
          :is-readonly="isReadonly"
        />

        <D3TabAdjudication
          v-else-if="currentSheet === 'D3-1'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />
        <D3TabDetail
          v-else-if="currentSheet === 'D3-2'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />
        <D3TabAdjustment
          v-else-if="currentSheet === 'D3-3'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />
        <D3TabAnalysis
          v-else-if="currentSheet === 'D3-4'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />
        <D3TabLongTerm
          v-else-if="currentSheet === 'D3-5'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />
        <D3TabRelatedParty
          v-else-if="currentSheet === 'D3-6'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />
        <D3TabVoucherCheck
          v-else-if="currentSheet === 'D3-7'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :year="props.year"
        />
        <D3TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
          :applicable-standards="applicableStandards"
        />
        <D3TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
          :applicable-standards="applicableStandards"
        />

        <D3TabIndex
          v-else
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :available-sheets="availableSheets"
          :applicable-standards="applicableStandards"
        />
      </template>
    </template>

    <GtWpReviewRail
      v-if="!isLoading && renderMode !== 'onlyoffice'"
      :section-id="d3ReviewSection.id"
      :section-label="d3ReviewSection.label"
    />
    <GtWpReviewDialogHost />
  </div>
</template>

<script setup lang="ts">
/**
 * GtD3PrepaidAccounts.vue — D3 预收账款底稿主入口（比照 D4 架构）
 *
 * 由外层 GtWpRenderer 的 sheetName 控制当前 sheet，不再使用内部 el-tabs。
 */
import { ref, computed, onMounted, provide, toRef, defineAsyncComponent } from 'vue'
import { useD3FormData } from './composables/useD3FormData'
import { useD3CrossSheet } from './composables/useD3CrossSheet'
import { useD3EntryDualMode, type D3RenderMode } from './composables/useD3EntryDualMode'
import { resolveD3SheetCode } from './composables/useD3SheetRouting'
import { useWorkpaperReviewProvide } from './composables/useWorkpaperReviewProvide'
import { resolveCycleReviewSection } from './composables/cycleReviewSectionMap'
import GtWpReviewDialogHost from './GtWpReviewDialogHost.vue'
import GtWpReviewRail from './GtWpReviewRail.vue'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { useD3ReviewThreads } from './composables/useD3ReviewThreads'
import { useD3EventBus } from './composables/useD3EventBus'
import { resolveD3SheetLabel } from './composables/d3SheetLabels'
import D3TabIndex from './d3/D3TabIndex.vue'
import D3TabProcedure from './d3/D3TabProcedure.vue'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'

const D3TabAdjudication = defineAsyncComponent(() => import('./d3/D3TabAdjudication.vue'))
const D3TabDetail = defineAsyncComponent(() => import('./d3/D3TabDetail.vue'))
const D3TabAdjustment = defineAsyncComponent(() => import('./d3/D3TabAdjustment.vue'))
const D3TabAnalysis = defineAsyncComponent(() => import('./d3/D3TabAnalysis.vue'))
const D3TabLongTerm = defineAsyncComponent(() => import('./d3/D3TabLongTerm.vue'))
const D3TabRelatedParty = defineAsyncComponent(() => import('./d3/D3TabRelatedParty.vue'))
const D3TabVoucherCheck = defineAsyncComponent(() => import('./d3/D3TabVoucherCheck.vue'))
const D3TabDisclosureListed = defineAsyncComponent(() => import('./d3/D3TabDisclosureListed.vue'))
const D3TabDisclosureSoe = defineAsyncComponent(() => import('./d3/D3TabDisclosureSoe.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
  (e: 'jump-to-section', sheetName: string): void
}>()

const isLoading = ref(true)
const applicableStandards = ref('')

const isReadonly = computed(() => !!props.readonly)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)

const {
  allResponses,
  loadAll,
  saveImmediate,
  saveBatch,
  debouncedSave,
} = useD3FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

const crossSheet = useD3CrossSheet({ allResponses })
useD3EventBus(allResponses, debouncedSave)

const wpIdRefForReview = toRef(props, 'wpId')
const projectIdRefForReview = toRef(props, 'projectId')
useWorkpaperReviewProvide({ wpId: wpIdRefForReview, projectId: projectIdRefForReview })

const { getThreadDot, getRowDot } = useD3ReviewThreads(wpIdRefForReview)
provide('d3GetThreadDot', getThreadDot)
provide('d3GetRowDot', getRowDot)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: () => loadAll(),
})
provide('d3CrossSheet', crossSheet)

const currentSheet = computed(() => resolveD3SheetCode(props.sheetName || 'D3'))
const d3ReviewSection = computed(() => resolveCycleReviewSection('D3', currentSheet.value))

const availableSheets = computed(() =>
  props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets ?? [],
)

const KNOWN_HTML_SHEETS = new Set([
  'directory', 'D3', 'D3A',
  'D3-1', 'D3-2', 'D3-3', 'D3-4', 'D3-5', 'D3-6', 'D3-7',
  '附注上市', '附注国企',
])

const showModeToolbar = computed(() => KNOWN_HTML_SHEETS.has(currentSheet.value))

const dualMode = useD3EntryDualMode({
  wpId: toRef(props, 'wpId'),
  currentSheet,
  availableSheets,
  reloadAllResponses: () => loadAll(),
})

const ooSheetName = computed(() =>
  dualMode.resolveOoSheetName() || props.sheetName || 'D3-1',
)

const renderMode = computed({
  get: () => dualMode.mode.value,
  set: (v: D3RenderMode) => { void dualMode.switchMode(v) },
})

const renderModeOptions = computed(() => [
  { label: '结构化视图', value: 'html' as const },
  {
    label: '在线编辑',
    value: 'onlyoffice' as const,
    disabled: !dualMode.ooAvailable.value,
  },
])

function onOoFallback(): void {
  void dualMode.switchMode('html')
}

async function saveImmediateBatch(
  items: Array<{ item_id: string; conclusion: string | null; remark: string | null }>,
): Promise<void> {
  await saveBatch(items.map(item => ({
    itemId: item.item_id,
    data: { conclusion: item.conclusion, remark: item.remark },
  })))
}

provide('displayPrefs', {
  fmtAmount: (v: number) => {
    if (v === 0) return '-'
    const abs = Math.abs(v).toLocaleString('zh-CN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
    return v < 0 ? `(${abs})` : abs
  },
  fmtPercent: (v: number) => (v * 100).toFixed(2) + '%',
})

async function selfLoad(): Promise<void> {
  if (props.htmlData?.responses_snapshot) {
    const map = new Map<string, any>()
    for (const [k, v] of Object.entries(props.htmlData.responses_snapshot)) {
      map.set(k, v)
    }
    allResponses.value = map as any
    isLoading.value = false
    return
  }

  if (props.htmlData?.applicable_standards || props.htmlData?.project_context?.applicable_standards) {
    applicableStandards.value =
      props.htmlData.applicable_standards
      || props.htmlData.project_context?.applicable_standards
      || ''
  }

  try {
    await loadAll()
  } catch (err) {
    console.warn('[GtD3PrepaidAccounts] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

onMounted(() => { void selfLoad() })
</script>

<style scoped>
.d3-prepaid-accounts {
  padding: 12px;
  max-width: 1400px;
  margin: 0 auto;
}
.loading-container {
  padding: 24px;
}
.d3-mode-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
</style>
