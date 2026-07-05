<template>
  <div class="d6-contract-assets">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="showModeToolbar" class="d6-mode-toolbar">
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
        <D6TabIndex
          v-if="currentSheet === 'D6' || currentSheet === 'skip'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :available-sheets="availableSheets"
        />

        <D6TabProcedure
          v-else-if="currentSheet === 'D6A'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :html-data="props.htmlData"
          :is-readonly="isReadonly"
        />

        <D6TabAdjudication
          v-else-if="currentSheet === 'D6-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <D6TabDetail
          v-else-if="currentSheet === 'D6-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <D6TabImpairmentDetail
          v-else-if="currentSheet === 'D6-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <D6TabAdjustment
          v-else-if="currentSheet === 'D6-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <D6TabRelatedParty
          v-else-if="currentSheet === 'D6-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <D6TabInspection
          v-else-if="currentSheet === 'D6-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <D6TabPolicyCheck
          v-else-if="currentSheet === 'D6-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <D6TabEclCalculation
          v-else-if="currentSheet === 'D6-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <D6TabWriteoffCheck
          v-else-if="currentSheet === 'D6-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <D6TabDisclosure
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
          variant="listed"
        />

        <D6TabDisclosure
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
          variant="soe"
        />

        <D6TabIndex
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
 * GtD6ContractAssets.vue — D6 合同资产底稿主入口（比照 D5）
 */
import { computed, onMounted, provide, toRef, defineAsyncComponent } from 'vue'
import { useD6FormData } from './composables/useD6FormData'
import { useD6CrossSheet } from './composables/useD6CrossSheet'
import { useD6EntryDualMode, type D6RenderMode } from './composables/useD6EntryDualMode'
import { resolveD6SheetCode } from './composables/useD6SheetRouting'
import { useWorkpaperReviewProvide } from './composables/useWorkpaperReviewProvide'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { useD6ReviewThreads } from './composables/useD6ReviewThreads'
import D6TabIndex from './d6/D6TabIndex.vue'
import D6TabProcedure from './d6/D6TabProcedure.vue'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'

const D6TabAdjudication = defineAsyncComponent(() => import('./d6/D6TabAdjudication.vue'))
const D6TabDetail = defineAsyncComponent(() => import('./d6/D6TabDetail.vue'))
const D6TabImpairmentDetail = defineAsyncComponent(() => import('./d6/D6TabImpairmentDetail.vue'))
const D6TabAdjustment = defineAsyncComponent(() => import('./d6/D6TabAdjustment.vue'))
const D6TabRelatedParty = defineAsyncComponent(() => import('./d6/D6TabRelatedParty.vue'))
const D6TabInspection = defineAsyncComponent(() => import('./d6/D6TabInspection.vue'))
const D6TabPolicyCheck = defineAsyncComponent(() => import('./d6/D6TabPolicyCheck.vue'))
const D6TabEclCalculation = defineAsyncComponent(() => import('./d6/D6TabEclCalculation.vue'))
const D6TabWriteoffCheck = defineAsyncComponent(() => import('./d6/D6TabWriteoffCheck.vue'))
const D6TabDisclosure = defineAsyncComponent(() => import('./d6/D6TabDisclosure.vue'))

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
} = useD6FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  htmlData: toRef(props, 'htmlData'),
})

const crossSheet = useD6CrossSheet({ allResponses })

const currentSheet = computed(() => resolveD6SheetCode(props.sheetName || 'D6'))

const availableSheets = computed(() =>
  props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets ?? [],
)

const wpIdRefForReview = toRef(props, 'wpId')
const projectIdRefForReview = toRef(props, 'projectId')
useWorkpaperReviewProvide({ wpId: wpIdRefForReview, projectId: projectIdRefForReview })

const { getThreadDot, getRowDot } = useD6ReviewThreads(wpIdRefForReview)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: () => loadAll(),
})

const KNOWN_HTML_SHEETS = new Set([
  'D6', 'D6A', 'D6-1', 'D6-2', 'D6-3', 'D6-4', 'D6-5', 'D6-6', 'D6-7', 'D6-8', 'D6-9',
  '附注上市', '附注国企',
])

const showModeToolbar = computed(() =>
  currentSheet.value !== 'skip' && KNOWN_HTML_SHEETS.has(currentSheet.value),
)

const dualMode = useD6EntryDualMode({
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
  set: (v: D6RenderMode) => { void dualMode.switchMode(v) },
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

onMounted(async () => {
  await loadAll()
})
</script>

<style scoped>
.d6-contract-assets {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.d6-mode-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
</style>
