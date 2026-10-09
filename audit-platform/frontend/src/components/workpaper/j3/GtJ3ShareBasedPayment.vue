<template>
  <div class="j3-share-based-payment">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 双模式工具栏（目录页 / 程序表不显示） -->
      <div v-if="showModeToolbar" class="j3-mode-toolbar">
        <el-segmented
          v-model="renderMode"
          :options="renderModeOptions"
          size="small"
        />
        <GtEntrySyncCapabilityNotice entry-id="xlsx/j3/gt-j3-share-based-payment" />
        <el-tag v-if="syncBusy" type="warning" size="small">同步中…</el-tag>
        <el-tooltip v-else-if="syncUnavailableReason" :content="syncUnavailableReason" placement="bottom">
          <el-tag type="danger" size="small">在线编辑不可用</el-tag>
        </el-tooltip>
        <el-tooltip v-else-if="syncFeedbackOk" :content="syncFeedbackOk" placement="bottom">
          <el-tag type="success" size="small">已同步</el-tag>
        </el-tooltip>
      </div>

      <!-- OnlyOffice 在线编辑（sync bridge 统一路径） -->
      <div v-if="renderMode === 'onlyoffice' && isJ3SyncedSheet" class="oo-container">
        <WorkpaperSyncEditorHost
          ref="syncEditorHostRef"
          :descriptor="syncOoDescriptor"
          :bridge="syncBridge"
        />
      </div>

      <!-- HTML 结构化视图 -->
      <template v-else>
        <!-- 底稿目录（默认页） -->
        <J3TabIndex
          v-if="!currentSheet || currentSheet === 'J3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="props.isReadonly"
          :all-responses="allResponses"
          @navigate-sheet="handleNavigateSheet"
        />

        <!-- J3A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'J3A'"
          sheet-code="J3A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="props.isReadonly"
        />

        <!-- J3-1 股份支付情况表 -->
        <J3TabDetail
          v-else-if="currentSheet === 'J3-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :year="props.year"
          :html-data="props.htmlData"
          :all-responses="allResponses"
          :is-readonly="props.isReadonly"
          :save-immediate="handleChildSave"
        />

        <!-- J3-2 股份支付检查表 -->
        <J3TabCheck
          v-else-if="currentSheet === 'J3-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :year="props.year"
          :html-data="props.htmlData"
          :all-responses="allResponses"
          :is-readonly="props.isReadonly"
          :save-immediate="handleChildSave"
        />

        <!-- IPO 股份支付监管审计要点 -->
        <J3TabIpoFocus
          v-else-if="currentSheet === 'J3-IPO'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :html-data="props.htmlData"
          :all-responses="allResponses"
          :is-readonly="props.isReadonly"
          :save-immediate="handleChildSave"
        />

        <!-- 兜底 -->
        <div v-else class="j3-sheet-placeholder">
          <el-empty :description="`J3 未识别的 sheet: ${currentSheet}`" />
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtJ3ShareBasedPayment — J3 股份支付主入口组件
 *
 * J3 无独立科目（费用端走 K8/K9，权益端走 M4，现金端走 J1）。
 * 真双向回写：useWorkpaperSyncBridge + WorkpaperSyncEditorHost（参照 D2/J2 接线模式）。
 * persistence三连环：selfLoad + allResponses Map + handleChildSave
 */
import { computed, ref, onMounted, onBeforeUnmount, defineAsyncComponent, toRef, inject, provide, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useChecklistPersistence,
  type ChecklistResponse,
} from '@/composables/workpaper/useChecklistPersistence'
import { collectChecklistResponses } from '@/composables/workpaper/checklistPersistenceHelpers'
import { WorkpaperRuntimeContextKey } from '../composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from '../composables/useWorkpaperReviewThreads'
// ── sync bridge 真双向 ──────────────────────────────────────────────────────
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from '../sync/useWorkpaperSyncBridge'
import { readStoreProjection } from '../sync/workpaperSyncApi'
import { capabilityForEntry } from '../sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from '../sync/WorkpaperSyncEditorHost.vue'
import GtEntrySyncCapabilityNotice from '../sync/GtEntrySyncCapabilityNotice.vue'
import CycleTabProcedure from '../shared/CycleTabProcedure.vue'

// defineAsyncComponent 懒加载
const J3TabIndex = defineAsyncComponent(() => import('./core/J3TabIndex.vue'))
const J3TabDetail = defineAsyncComponent(() => import('./core/J3TabDetail.vue'))
const J3TabCheck = defineAsyncComponent(() => import('./core/J3TabCheck.vue'))
const J3TabIpoFocus = defineAsyncComponent(() => import('./core/J3TabIpoFocus.vue'))

// ── J3 sync 常量 ────────────────────────────────────────────────────────────
type J3RenderMode = 'html' | 'onlyoffice'
const J3_SYNC_ENTRY_ID = 'xlsx/j3/gt-j3-share-based-payment'
/**
 * J3 受管 sheet 集合：当前 canary 仅接 J3-1 股份支付情况表（14 列全文本，零公式）。
 * J3 无审定表，无 TB 发布门。
 */
const J3_MANAGED_SHEET_KEYS: Record<string, string> = {
  'J3-1': 'j31-plans-managed',
}
const J3_DEFAULT_SHEET_KEY = 'j31-plans-managed'

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  year?: string | number
  sheetName?: string
  htmlData?: Record<string, unknown> | null
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  save: []
  completed: []
  'navigate-sheet': [sheetName: string]
}>()

/** 目录页跳转 */
provide('jumpToSection', (sheetName: string) => emit('navigate-sheet', sheetName))

const isLoading = ref(true)
const syncSwitching = ref(false)
const runtime = inject(WorkpaperRuntimeContextKey, null)

const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)

/** 当前 sheet 名 */
const currentSheet = computed(() => {
  const sn = props.sheetName || ''
  if (/\bJ3A\b/.test(sn) || sn.includes('实质性程序表')) return 'J3A'
  if (sn.includes('IPO') || sn.includes('股权激励工具') || sn.includes('首发')) return 'J3-IPO'
  const m = sn.match(/(J3-\d+)/)
  if (m) return m[1]
  if (sn.includes('目录') || sn === 'J3') return 'J3'
  return sn
})

const isJ3SyncedSheet = computed(() => currentSheet.value in J3_MANAGED_SHEET_KEYS)
const currentSyncSheetKey = computed(
  () => J3_MANAGED_SHEET_KEYS[currentSheet.value] ?? J3_DEFAULT_SHEET_KEY,
)
const isHtmlSheet = computed(() => currentSheet.value !== 'J3')
const showModeToolbar = computed(() => isHtmlSheet.value && currentSheet.value !== 'J3A')

// ─── sync bridge 真双向 ─────────────────────────────────────────────────────
const syncEntryId = ref(J3_SYNC_ENTRY_ID)
const syncSheetKey = computed(() => currentSyncSheetKey.value)
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(syncEntryId.value),
  flushHtml: async () => {
    await persistence.flush()
    const snap = await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: syncEntryId.value,
    })
    return {
      expectedRevision: snap.expectedRevision,
      projection: snap.projection,
      sheetKey: syncSheetKey.value,
    }
  },
  reloadHtml: async (_minimumRevision: number) => {
    await selfLoad()
  },
})

const syncOoDescriptor = computed(() => syncBridge.descriptor.value)

const syncBusy = computed(
  () =>
    syncSwitching.value
    || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)
const syncUnavailableReason = computed(() => {
  if (!isJ3SyncedSheet.value) {
    return '在线编辑仅开放 J3-1 股份支付情况表；当前底稿走结构化视图'
  }
  const err = syncBridge.lastError.value
  return err ? `${err.errorCode}: ${err.message}` : ''
})
const syncFeedbackOk = computed(() => {
  const fb = syncBridge.feedback.value
  return fb.kind === 'success' ? fb.message : ''
})

const renderMode = computed({
  get: (): J3RenderMode => (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'html'),
  set: (v: J3RenderMode) => { void switchRenderMode(v) },
})

const renderModeOptions = computed(() => [
  { label: '结构化视图', value: 'html' as const },
  {
    label: '在线编辑',
    value: 'onlyoffice' as const,
    disabled: !isJ3SyncedSheet.value || !!props.isReadonly,
  },
])

async function switchRenderMode(target: J3RenderMode): Promise<void> {
  if (target === renderMode.value) return
  if (target === 'onlyoffice') {
    if (!isJ3SyncedSheet.value) return
    syncSwitching.value = true
    try {
      await syncBridge.switchToOnlyOffice()
    } catch { /* lastError / feedback 已由桥写入 */ }
    finally { syncSwitching.value = false }
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
    } else if (syncBridge.mode.value === 'oo' && !syncBridge.dirty.value) {
      await syncBridge.leaveWithoutSaving()
    } else if (syncBridge.canForcesave.value && syncEditorHostRef.value) {
      await syncEditorHostRef.value.forceSave()
    } else {
      syncBridge.persistMode('html')
    }
  } catch { /* 保持 OO */ }
  finally { syncSwitching.value = false }
}

// ─── Persistence Adapter ────────────────────────────────────────────────────
const persistence = useChecklistPersistence({
  wpId: toRef(props, 'wpId'),
  projectId: computed(() => props.projectId || undefined),
  debounceMs: 800,
  onSaved: () => runtime?.version.scheduleAutoSnapshot(),
})
const allResponses = persistence.responses

const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

async function selfLoad(): Promise<void> {
  const snapshot = collectChecklistResponses(
    (props.htmlData as any)?.responses_snapshot,
    (props.htmlData as any)?.allResponses,
    (props.htmlData as any)?.checklist_responses,
  )
  if (snapshot.length > 0) persistence.hydrate(snapshot)
  const fallback = new Map(allResponses.value)
  try {
    await persistence.load()
  } catch {
    if (fallback.size === 0) ElMessage.warning('J3 保存数据加载失败，请刷新后重试')
  }
  const merged = new Map(allResponses.value)
  for (const [itemId, item] of fallback) {
    if (!merged.has(itemId)) merged.set(itemId, item)
  }
  persistence.hydrate(merged)
}

provide('reloadWorkpaperData', selfLoad)

async function handleChildSave(items: ChecklistResponse[]): Promise<void> {
  for (const { item_id, ...patch } of items) {
    persistence.saveDebounced(item_id, patch)
  }
}

function handleNavigateSheet(sheetName: string) {
  emit('navigate-sheet', sheetName)
}

watch(currentSheet, async (nextSheet, prevSheet) => {
  if (nextSheet === prevSheet) return
  try {
    await persistence.flush()
  } catch {
    ElMessage.error('J3 切换底稿时保存失败，数据已保留，可返回后重试')
  }
})

onBeforeUnmount(() => { void persistence.flush().catch(() => undefined) })

onMounted(async () => {
  await selfLoad()
  isLoading.value = false
})
</script>

<style scoped>
.j3-share-based-payment {
  padding: 0;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.j3-mode-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.oo-container {
  min-height: 600px;
  height: calc(100vh - 280px);
  overflow: hidden;
  border-radius: 8px;
}
.j3-sheet-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}
</style>
