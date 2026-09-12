<template>
  <div class="d3-prepaid-accounts" :style="{ '--wp-font-size': displayPrefs.fontConfig.tableFont }">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="showModeToolbar" class="d3-mode-toolbar">
        <el-segmented v-model="renderMode" :options="renderModeOptions" size="small" :disabled="isD3DetailSheet && syncBusy" />
        <el-tag v-if="!isD3DetailSheet && !dualMode.ooAvailable.value" size="small" type="warning">OO不可用</el-tag>
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d3-prepaid-accounts" />
      </div>

      <!-- G5-1 D3-2 canary：统一双向路径（descriptor → WorkpaperSyncEditorHost） -->
      <WorkpaperSyncEditorHost
        v-if="renderMode === 'onlyoffice' && isD3DetailSheet"
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
          :html-data="props.htmlData"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />
        <D3TabDetail
          v-else-if="currentSheet === 'D3-2'"
          ref="detailRef"
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
    <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
  </div>
</template>

<script setup lang="ts">
/**
 * GtD3PrepaidAccounts.vue — D3 预收账款底稿主入口（比照 D4 架构）
 *
 * 由外层 GtWpRenderer 的 sheetName 控制当前 sheet，不再使用内部 el-tabs。
 */
import { ref, computed, onMounted, provide, toRef, inject, defineAsyncComponent } from 'vue'
import { useD3FormData } from './composables/useD3FormData'
import { useD3CrossSheet } from './composables/useD3CrossSheet'
import { useD3EntryDualMode, type D3RenderMode } from './composables/useD3EntryDualMode'
import { resolveD3SheetCode } from './composables/useD3SheetRouting'
import { resolveCycleReviewSection } from './composables/cycleReviewSectionMap'
import GtWpReviewRail from './GtWpReviewRail.vue'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useD3ReviewThreads } from './composables/useD3ReviewThreads'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useD3EventBus } from './composables/useD3EventBus'
import { resolveD3SheetLabel } from './composables/d3SheetLabels'
import { normalizeApplicableStandards } from './composables/useF2FormData'
import { useAgingConfig } from '@/composables/useAgingConfig'
import D3TabIndex from './d3/D3TabIndex.vue'
import D3TabProcedure from './d3/D3TabProcedure.vue'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
// G5-1 Phase 5 D3 canary：D3-2 明细走统一双向路径（descriptor → WorkpaperSyncEditorHost），
// 与 GtD1NotesReceivable / GtD7ContractLiabilities 同构；其余 sheet 仍走 useD3EntryDualMode。
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'

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
/** 适用准则（归一后的字符串列表，如 `['soe_standalone','soe','standalone']`） */
const applicableStandards = ref<string[]>([])

const isReadonly = computed(() => !!props.readonly)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)

const {
  allResponses,
  loadAll,
  saveImmediate,
  saveBatch,
  debouncedSave,
  flushPendingSave,
} = useD3FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// 项目账龄配置（subject='D3'）→ 供跨sheet账龄聚合 segment-driven（支持自定义账龄段）
const { segments: agingSegments } = useAgingConfig(projectIdRef, 'D3')
const crossSheet = useD3CrossSheet({ allResponses, segments: agingSegments })
useD3EventBus(allResponses, debouncedSave)

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

const wpIdRefForReview = toRef(props, 'wpId')

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
provide('d3VersionTrailRef', versionTrailRef)
provide('d3OpenVersionHistory', openVersionHistory)

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

const showModeToolbar = computed(() =>
  currentSheet.value !== 'directory' && currentSheet.value !== 'D3' && currentSheet.value !== 'skip'
  && KNOWN_HTML_SHEETS.has(currentSheet.value),
)

const dualMode = useD3EntryDualMode({
  wpId: toRef(props, 'wpId'),
  currentSheet,
  availableSheets,
  reloadAllResponses: () => loadAll(),
})

const ooSheetName = computed(() =>
  dualMode.resolveOoSheetName() || props.sheetName || 'D3-1',
)

// ─── G5-1 D3-2 canary：useWorkpaperSyncBridge + store-projection flush ────────
//
// 🔴 只覆盖 D3-2「预收账款明细」（manifest entry 的 managed sheet = d32-managed）。
// flushHtml 先 flushPendingSave（flush 掉 2s debounce 未落库的行）再 readStoreProjection。
// 不在前端重造 27 列→stable-key 映射；账龄 nested（agingPrior/agingAudited）由服务端
// store-projection + phase5_d3 的 _resolve_json_path/_set_json_path 处理。
const D3_SYNC_ENTRY_ID = 'xlsx/gt-d3-prepaid-accounts'
const D3_MANAGED_SHEET_KEY = 'd32-managed'
const isD3DetailSheet = computed(() => currentSheet.value === 'D3-2')
const syncSwitching = ref(false)
/** 统一宿主实例 —— 切回结构化视图前用它 forceSave()（内部走 room forcesave）。 */
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const syncEntryId = ref(D3_SYNC_ENTRY_ID)
const syncSheetKey = ref(D3_MANAGED_SHEET_KEY)
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(D3_SYNC_ENTRY_ID),
  flushHtml: async () => {
    flushPendingSave()
    const snap = await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: D3_SYNC_ENTRY_ID,
    })
    return {
      expectedRevision: snap.expectedRevision,
      projection: snap.projection,
      sheetKey: D3_MANAGED_SHEET_KEY,
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

// renderMode / 切换：D3-2 走 syncBridge，其余 sheet 沿用 useD3EntryDualMode。
const renderMode = computed({
  get: (): D3RenderMode =>
    isD3DetailSheet.value
      ? (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'html')
      : dualMode.mode.value,
  set: (v: D3RenderMode) => {
    if (isD3DetailSheet.value) void switchRenderMode(v)
    else void dualMode.switchMode(v)
  },
})

const renderModeOptions = computed(() => [
  { label: '结构化视图', value: 'html' as const },
  {
    label: '在线编辑',
    value: 'onlyoffice' as const,
    disabled: isD3DetailSheet.value ? isReadonly.value : !dualMode.ooAvailable.value,
  },
])

async function switchRenderMode(target: D3RenderMode): Promise<void> {
  if (target === renderMode.value) return
  if (target === 'onlyoffice') {
    if (!isD3DetailSheet.value) return
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

// 显示偏好由 Runtime Boundary(GtWpRenderer) 统一 provide；此处仅取 store 供根样式使用。
const displayPrefs = useDisplayPrefsStore()

async function selfLoad(): Promise<void> {
  // 🔴 适用准则必须在早返回**之前**赋值：原实现放在 `responses_snapshot` 早返回之后，
  // 有快照的项目根本走不到 → 门控恒空（两版披露 Tab 都显示「当前项目不适用…」）。
  // 值经 `normalizeApplicableStandards` 归一（render-config 现统一下发字符串列表，
  // 但历史/其它路径可能是 v2 对象或逗号串）。
  applicableStandards.value = normalizeApplicableStandards(
    props.htmlData?.project_context?.applicable_standards
    ?? props.htmlData?.applicable_standards,
  )

  if (props.htmlData?.responses_snapshot) {
    const map = new Map<string, any>()
    for (const [k, v] of Object.entries(props.htmlData.responses_snapshot)) {
      map.set(k, v)
    }
    allResponses.value = map as any
    isLoading.value = false
    return
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

// ─── 行名对齐（formula-row-name-alignment-confirmation 复盘 #4）───────────────
// GtWpRenderer 的 activeComponentRef 指向本顶层 bundle，故对齐行契约在此暴露，
// 内部转发给当前 sheet 的子组件（D3-2 明细 → D3TabDetail）。仅明细表有按客户名取数的行。
const detailRef = ref<{ getRowNameAlignmentRows?: () => unknown[] } | null>(null)
function getRowNameAlignmentRows(): unknown[] {
  if (currentSheet.value === 'D3-2' && detailRef.value?.getRowNameAlignmentRows) {
    return detailRef.value.getRowNameAlignmentRows()
  }
  return []
}

defineExpose({ getRowNameAlignmentRows })
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
