<template>
  <div class="d5-receivables-financing">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="showModeToolbar" class="d5-mode-toolbar">
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
        <D5TabIndex
          v-if="currentSheet === 'D5' || currentSheet === 'skip'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :available-sheets="availableSheets"
        />

        <D5TabProcedure
          v-else-if="currentSheet === 'D5A'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :html-data="props.htmlData"
          :is-readonly="isReadonly"
        />

        <D5TabAdjudication
          v-else-if="currentSheet === 'D5-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <D5TabDetail
          v-else-if="currentSheet === 'D5-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :year="props.year"
          :bs-date="periodEnd"
        />

        <D5TabAdjustment
          v-else-if="currentSheet === 'D5-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <D5TabFairValue
          v-else-if="currentSheet === 'D5-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :period-end="periodEnd"
          :default-discount-rate="defaultDiscountRate"
        />

        <D5TabDisclosure
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <D5TabDisclosure
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <D5TabIndex
          v-else
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :available-sheets="availableSheets"
        />
      </template>
    </template>

    <GtWpReviewRail
      v-if="!isLoading && renderMode !== 'onlyoffice'"
      :section-id="d5ReviewSection.id"
      :section-label="d5ReviewSection.label"
    />
    <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
  </div>
</template>

<script setup lang="ts">
/**
 * GtD5ReceivablesFinancing.vue — D5 应收款项融资底稿主入口（比照 D4）
 */
import { ref, computed, onMounted, provide, toRef, inject, defineAsyncComponent } from 'vue'
import { useD5FormData } from './composables/useD5FormData'
import { useD5CrossSheet } from './composables/useD5CrossSheet'
import { useD5EntryDualMode, type D5RenderMode } from './composables/useD5EntryDualMode'
import { resolveD5SheetCode } from './composables/useD5SheetRouting'
import { resolveCycleReviewSection } from './composables/cycleReviewSectionMap'
import GtWpReviewRail from './GtWpReviewRail.vue'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useD5ReviewThreads } from './composables/useD5ReviewThreads'
import { parseNum } from './composables/useD5FormulaEngine'
import D5TabIndex from './d5/D5TabIndex.vue'
import D5TabProcedure from './d5/D5TabProcedure.vue'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'

const D5TabAdjudication = defineAsyncComponent(() => import('./d5/D5TabAdjudication.vue'))
const D5TabDetail = defineAsyncComponent(() => import('./d5/D5TabDetail.vue'))
const D5TabAdjustment = defineAsyncComponent(() => import('./d5/D5TabAdjustment.vue'))
const D5TabFairValue = defineAsyncComponent(() => import('./d5/D5TabFairValue.vue'))
const D5TabDisclosure = defineAsyncComponent(() => import('./d5/D5TabDisclosure.vue'))

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

const isReadonly = computed(() => !!props.readonly)

const {
  allResponses,
  isLoading,
  loadAll,
  saveImmediate,
  debouncedSave,
  saveBatch,
} = useD5FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const crossSheet = useD5CrossSheet({ allResponses })

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

const currentSheet = computed(() => resolveD5SheetCode(props.sheetName || 'D5'))
const d5ReviewSection = computed(() => resolveCycleReviewSection('D5', currentSheet.value))

const availableSheets = computed(() =>
  props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets ?? [],
)

const wpIdRefForReview = toRef(props, 'wpId')

const { getThreadDot, getRowDot } = useD5ReviewThreads(wpIdRefForReview)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)
provide('d5VersionTrailRef', versionTrailRef)
provide('d5OpenVersionHistory', openVersionHistory)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: () => loadAll(),
})

const KNOWN_HTML_SHEETS = new Set([
  'D5', 'D5A', 'D5-1', 'D5-2', 'D5-3', 'D5-4', '附注上市', '附注国企',
])

const showModeToolbar = computed(() =>
  currentSheet.value !== 'skip' && currentSheet.value !== 'D5' && KNOWN_HTML_SHEETS.has(currentSheet.value),
)

const dualMode = useD5EntryDualMode({
  wpId: toRef(props, 'wpId'),
  currentSheet,
  availableSheets,
  reloadAllResponses: () => loadAll(),
})

const ooSheetName = computed(() =>
  dualMode.resolveOoSheetName() || props.sheetName || '底稿目录',
)

const renderMode = computed({
  get: () => dualMode.mode.value,
  set: (v: D5RenderMode) => { void dualMode.switchMode(v) },
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
  scheduleAutoSnapshot()
}

const periodEnd = computed(() => {
  const fromHtml = props.htmlData?.project_context?.period_end
  if (fromHtml) return fromHtml
  return props.year ? `${props.year}-12-31` : '2025-12-31'
})

const defaultDiscountRate = computed(() => {
  const resp = allResponses.value.get('D5-4-default-rate')
  return parseNum(resp?.remark)
})

const d5TbAmount = computed(() => {
  const resp = allResponses.value.get('D5-1-tb-amount')
  if (resp?.remark) return parseNum(resp.remark)
  // 从 htmlData project_context 回退
  return parseNum(props.htmlData?.project_context?.tb_amount)
})

provide('d5TbAmount', d5TbAmount)
provide('d5BsDate', periodEnd)

onMounted(async () => {
  await loadAll()
})
</script>

<style scoped>
.d5-receivables-financing {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.d5-mode-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
</style>
