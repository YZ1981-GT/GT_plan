<template>
  <div class="d5-receivables-financing">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="showModeToolbar" class="d5-mode-toolbar">
        <el-segmented v-model="renderMode" :options="renderModeOptions" size="small" :disabled="isD5DetailSheet && syncBusy" />
        <el-tag v-if="!isD5DetailSheet && !dualMode.ooAvailable.value" size="small" type="warning">OO不可用</el-tag>
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d5-receivables-financing" />
      </div>

      <!-- G5-1 D5-2 canary：统一双向路径（descriptor → WorkpaperSyncEditorHost） -->
      <WorkpaperSyncEditorHost
        v-if="renderMode === 'onlyoffice' && isD5DetailSheet"
        ref="syncEditorHostRef"
        :descriptor="syncOoDescriptor"
        :bridge="syncBridge"
      />

      <!-- 其余 sheet 的在线编辑仍走 legacy GtOnlyOfficeSheet -->
      <GtOnlyOfficeSheet
        v-else-if="renderMode === 'onlyoffice'"
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
          :html-data="props.htmlData"
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
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
// G5-1 Phase 5 D5 canary：D5-2 明细走统一双向路径（descriptor → WorkpaperSyncEditorHost），
// 与 GtD1/GtD3/GtD6/GtD7 同构；其余 sheet 仍走 useD5EntryDualMode。
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'

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
  flushPendingSave,
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

// ─── G5-1 D5-2 canary：useWorkpaperSyncBridge + store-projection flush ────────
//
// 🔴 只覆盖 D5-2「应收款项融资明细」（manifest entry 的 managed sheet = d52-managed）。
const D5_SYNC_ENTRY_ID = 'xlsx/gt-d5-receivables-financing'
const D5_MANAGED_SHEET_KEY = 'd52-managed'
const isD5DetailSheet = computed(() => currentSheet.value === 'D5-2')
const syncSwitching = ref(false)
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const syncEntryId = ref(D5_SYNC_ENTRY_ID)
const syncSheetKey = ref(D5_MANAGED_SHEET_KEY)
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(D5_SYNC_ENTRY_ID),
  flushHtml: async () => {
    flushPendingSave()
    const snap = await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: D5_SYNC_ENTRY_ID,
    })
    return {
      expectedRevision: snap.expectedRevision,
      projection: snap.projection,
      sheetKey: D5_MANAGED_SHEET_KEY,
    }
  },
  reloadHtml: async (_minimumRevision: number) => {
    await loadAll()
  },
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncBusy = computed(
  () =>
    syncSwitching.value
    || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)

// renderMode / 切换：D5-2 走 syncBridge，其余 sheet 沿用 useD5EntryDualMode。
const renderMode = computed({
  get: (): D5RenderMode =>
    isD5DetailSheet.value
      ? (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'html')
      : dualMode.mode.value,
  set: (v: D5RenderMode) => {
    if (isD5DetailSheet.value) void switchRenderMode(v)
    else void dualMode.switchMode(v)
  },
})

const renderModeOptions = computed(() => [
  { label: '结构化视图', value: 'html' as const },
  {
    label: '在线编辑',
    value: 'onlyoffice' as const,
    disabled: isD5DetailSheet.value ? isReadonly.value : !dualMode.ooAvailable.value,
  },
])

async function switchRenderMode(target: D5RenderMode): Promise<void> {
  if (target === renderMode.value) return
  if (target === 'onlyoffice') {
    if (!isD5DetailSheet.value) return
    syncSwitching.value = true
    try {
      await syncBridge.switchToOnlyOffice()
    } catch {
      // lastError / feedback 已由桥写入；保持 html
    } finally {
      syncSwitching.value = false
    }
    return
  }
  // → html
  if (syncBridge.mode.value !== 'oo') {
    syncBridge.persistMode('html')
    return
  }
  syncSwitching.value = true
  try {
    if (String(syncBridge.state.value) === 'applied') {
      await syncBridge.reloadAfterApplied()
    } else if (syncBridge.canForcesave.value && syncEditorHostRef.value) {
      await syncEditorHostRef.value.forceSave()
    } else {
      syncBridge.persistMode('html')
    }
  } catch {
    // 保持 OO；错误在桥上
  } finally {
    syncSwitching.value = false
  }
}

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
