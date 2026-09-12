<template>
  <div class="d7-contract-liabilities">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="showModeToolbar" class="d7-mode-toolbar">
        <el-segmented v-model="renderMode" :options="renderModeOptions" size="small" :disabled="isD7DetailSheet && syncBusy" />
        <el-tag v-if="!isD7DetailSheet && !dualMode.ooAvailable.value" size="small" type="warning">OO不可用</el-tag>
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d7-contract-liabilities" />
      </div>

      <!-- G5-1 D7-2 canary：统一双向路径（descriptor → WorkpaperSyncEditorHost） -->
      <WorkpaperSyncEditorHost
        v-if="renderMode === 'onlyoffice' && isD7DetailSheet"
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
          :html-data="props.htmlData"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediateWithSnapshot"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <D7TabDetail
          v-else-if="currentSheet === 'D7-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediateWithSnapshot"
          :debounced-save="debouncedSave"
        />

        <D7TabAdjustment
          v-else-if="currentSheet === 'D7-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediateWithSnapshot"
          :debounced-save="debouncedSave"
        />

        <D7TabAnalysis
          v-else-if="currentSheet === 'D7-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediateWithSnapshot"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <D7TabLongTerm
          v-else-if="currentSheet === 'D7-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediateWithSnapshot"
          :debounced-save="debouncedSave"
        />

        <D7TabRelatedParty
          v-else-if="currentSheet === 'D7-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediateWithSnapshot"
          :debounced-save="debouncedSave"
        />

        <D7TabVoucherCheck
          v-else-if="currentSheet === 'D7-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :all-responses="allResponses"
          :save-immediate="saveImmediateWithSnapshot"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
          :year="d7Year"
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

    <GtWpReviewRail
      v-if="!isLoading && renderMode !== 'onlyoffice'"
      :section-id="d7ReviewSection.id"
      :section-label="d7ReviewSection.label"
    />
    <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
  </div>
</template>

<script setup lang="ts">
/**
 * GtD7ContractLiabilities.vue — D7 合同负债底稿主入口（比照 D5）
 */
import { ref, computed, onMounted, provide, toRef, inject, defineAsyncComponent } from 'vue'
import { useD7FormData } from './composables/useD7FormData'
import { useD7CrossSheet } from './composables/useD7CrossSheet'
import { useD7EntryDualMode, type D7RenderMode } from './composables/useD7EntryDualMode'
import { resolveD7SheetCode } from './composables/useD7SheetRouting'
import { resolveCycleReviewSection } from './composables/cycleReviewSectionMap'
import { useAgingConfig } from '@/composables/useAgingConfig'
import GtWpReviewRail from './GtWpReviewRail.vue'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useD7ReviewThreads } from './composables/useD7ReviewThreads'
import D7TabIndex from './d7/D7TabIndex.vue'
import D7TabProcedure from './d7/D7TabProcedure.vue'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
// G5-1 Phase 5 D7 canary：D7-2 明细走统一双向路径（descriptor → WorkpaperSyncEditorHost），
// 与 GtD1NotesReceivable / GtD2AccountsReceivable 同构；其余 sheet 仍走 useD7EntryDualMode。
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'

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
  flushPendingSave,
} = useD7FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  htmlData: toRef(props, 'htmlData'),
})

// 项目账龄配置段（subject='D7', 2-period）供跨表账龄聚合按段进行
const { segments: d7AgingSegments } = useAgingConfig(toRef(props, 'projectId'), 'D7')
const crossSheet = useD7CrossSheet({ allResponses, segments: d7AgingSegments })

// ─── Project Context (from render-config) ────────────────────────────
const projectContext = computed(() => {
  const hd = props.htmlData
  return hd?.project_context || hd?.render_config?.project_context || {}
})

const relatedParties = computed<string[]>(() => projectContext.value.related_parties || [])
const d7BsDate = computed<string>(() => projectContext.value.bs_date || '')
const d7TbAmount = computed<number>(() => projectContext.value.tb_amount || 0)

provide('d7RelatedParties', relatedParties)
provide('d7BsDate', d7BsDate)
provide('d7TbAmount', d7TbAmount)

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

async function saveImmediateWithSnapshot(...args: Parameters<typeof saveImmediate>): Promise<void> {
  await saveImmediate(...args)
  scheduleAutoSnapshot()
}

const currentSheet = computed(() => resolveD7SheetCode(props.sheetName || 'D7'))
const d7ReviewSection = computed(() => resolveCycleReviewSection('D7', currentSheet.value))
const d7Year = computed(() => props.year || parseInt(projectContext.value.audit_year || '0') || new Date().getFullYear() - 1)

const availableSheets = computed(() =>
  props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets ?? [],
)

const wpIdRefForReview = toRef(props, 'wpId')

const { getThreadDot, getRowDot } = useD7ReviewThreads(wpIdRefForReview)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)
provide('d7VersionTrailRef', versionTrailRef)
provide('d7OpenVersionHistory', openVersionHistory)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: () => loadAll(),
})

const KNOWN_HTML_SHEETS = new Set([
  'D7', 'D7A', 'D7-1', 'D7-2', 'D7-3', 'D7-4', 'D7-5', 'D7-6', 'D7-7',
  '附注上市', '附注国企',
])

const showModeToolbar = computed(() =>
  currentSheet.value !== 'skip' && currentSheet.value !== 'D7' && KNOWN_HTML_SHEETS.has(currentSheet.value),
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

// ─── G5-1 D7-2 canary：useWorkpaperSyncBridge + store-projection flush ────────
//
// 🔴 只覆盖 D7-2「合同负债明细」（manifest entry 的 managed sheet = d72-managed）。
// flushHtml 先 flushPendingSave（flush 掉 2s debounce 未落库的行）再 readStoreProjection。
// 不在前端重造 27 列→stable-key 映射；账龄 nested（agingPrior/agingAudited）由服务端
// store-projection + phase5_d7 的 _resolve_json_path/_set_json_path 处理。
const D7_SYNC_ENTRY_ID = 'xlsx/gt-d7-contract-liabilities'
const D7_MANAGED_SHEET_KEY = 'd72-managed'
const isD7DetailSheet = computed(() => currentSheet.value === 'D7-2')
const syncSwitching = ref(false)
/** 统一宿主实例 —— 切回结构化视图前用它 forceSave()（内部走 room forcesave）。 */
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const syncEntryId = ref(D7_SYNC_ENTRY_ID)
const syncSheetKey = ref(D7_MANAGED_SHEET_KEY)
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(D7_SYNC_ENTRY_ID),
  flushHtml: async () => {
    flushPendingSave()
    const snap = await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: D7_SYNC_ENTRY_ID,
    })
    return {
      expectedRevision: snap.expectedRevision,
      projection: snap.projection,
      sheetKey: D7_MANAGED_SHEET_KEY,
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

// renderMode / 切换：D7-2 走 syncBridge，其余 sheet 沿用 useD7EntryDualMode。
const renderMode = computed({
  get: (): D7RenderMode =>
    isD7DetailSheet.value
      ? (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'html')
      : dualMode.mode.value,
  set: (v: D7RenderMode) => {
    if (isD7DetailSheet.value) void switchRenderMode(v)
    else void dualMode.switchMode(v)
  },
})

const renderModeOptions = computed(() => [
  { label: '结构化视图', value: 'html' as const },
  {
    label: '在线编辑',
    value: 'onlyoffice' as const,
    disabled: isD7DetailSheet.value ? isReadonly.value : !dualMode.ooAvailable.value,
  },
])

async function switchRenderMode(target: D7RenderMode): Promise<void> {
  if (target === renderMode.value) return
  if (target === 'onlyoffice') {
    if (!isD7DetailSheet.value) return
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
