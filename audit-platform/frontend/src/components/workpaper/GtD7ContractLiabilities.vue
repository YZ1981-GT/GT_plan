<template>
  <div class="d7-contract-liabilities">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="showModeToolbar" class="d7-mode-toolbar">
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
        <D7TabIndex
          v-if="currentSheet === 'D7' || currentSheet === 'skip'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :available-sheets="availableSheets"
        />

        <D7TabProcedure
          v-else-if="currentSheet === 'D7A'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :html-data="props.htmlData"
          :is-readonly="isReadonly"
        />

        <D7TabAdjudication
          v-else-if="currentSheet === 'D7-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <D7TabDetail
          v-else-if="currentSheet === 'D7-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <D7TabAdjustment
          v-else-if="currentSheet === 'D7-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <D7TabAnalysis
          v-else-if="currentSheet === 'D7-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <D7TabLongTerm
          v-else-if="currentSheet === 'D7-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <D7TabRelatedParty
          v-else-if="currentSheet === 'D7-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <D7TabVoucherCheck
          v-else-if="currentSheet === 'D7-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <D7TabDisclosure
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
          variant="listed"
        />

        <D7TabDisclosure
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
          variant="soe"
        />

        <D7TabIndex
          v-else
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :available-sheets="availableSheets"
        />
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtD7ContractLiabilities.vue — D7 合同负债底稿主入口（比照 D5）
 */
import { computed, onMounted, provide, toRef, defineAsyncComponent } from 'vue'
import { useD7FormData } from './composables/useD7FormData'
import { useD7CrossSheet } from './composables/useD7CrossSheet'
import { useD7EntryDualMode, type D7RenderMode } from './composables/useD7EntryDualMode'
import { resolveD7SheetCode } from './composables/useD7SheetRouting'
import { useWorkpaperReviewProvide } from './composables/useWorkpaperReviewProvide'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { useD7ReviewThreads } from './composables/useD7ReviewThreads'
import D7TabIndex from './d7/D7TabIndex.vue'
import D7TabProcedure from './d7/D7TabProcedure.vue'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'

const D7TabAdjudication = defineAsyncComponent(() => import('./d7/D7TabAdjudication.vue'))
const D7TabDetail = defineAsyncComponent(() => import('./d7/D7TabDetail.vue'))
const D7TabAdjustment = defineAsyncComponent(() => import('./d7/D7TabAdjustment.vue'))
const D7TabAnalysis = defineAsyncComponent(() => import('./d7/D7TabAnalysis.vue'))
const D7TabLongTerm = defineAsyncComponent(() => import('./d7/D7TabLongTerm.vue'))
const D7TabRelatedParty = defineAsyncComponent(() => import('./d7/D7TabRelatedParty.vue'))
const D7TabVoucherCheck = defineAsyncComponent(() => import('./d7/D7TabVoucherCheck.vue'))
const D7TabDisclosure = defineAsyncComponent(() => import('./d7/D7TabDisclosure.vue'))

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
} = useD7FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  htmlData: toRef(props, 'htmlData'),
})

const crossSheet = useD7CrossSheet({ allResponses })

const currentSheet = computed(() => resolveD7SheetCode(props.sheetName || 'D7'))

const availableSheets = computed(() =>
  props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets ?? [],
)

const wpIdRefForReview = toRef(props, 'wpId')
const projectIdRefForReview = toRef(props, 'projectId')
useWorkpaperReviewProvide({ wpId: wpIdRefForReview, projectId: projectIdRefForReview })

const { getThreadDot, getRowDot } = useD7ReviewThreads(wpIdRefForReview)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: () => loadAll(),
})

const KNOWN_HTML_SHEETS = new Set([
  'D7', 'D7A', 'D7-1', 'D7-2', 'D7-3', 'D7-4', 'D7-5', 'D7-6', 'D7-7',
  '附注上市', '附注国企',
])

const showModeToolbar = computed(() =>
  currentSheet.value !== 'skip' && KNOWN_HTML_SHEETS.has(currentSheet.value),
)

const dualMode = useD7EntryDualMode({
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
  set: (v: D7RenderMode) => { void dualMode.switchMode(v) },
})

const renderModeOptions = computed(() => [
  { label: 'HTML精美化', value: 'html' as const },
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

onMounted(async () => {
  await loadAll()
})
</script>

<style scoped>
.d7-contract-liabilities {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.d7-mode-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
</style>
