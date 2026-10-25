<template>
  <div class="j2-defined-benefit-plan">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 双模式工具栏（目录页不显示） -->
      <div v-if="showModeToolbar" class="j2-mode-toolbar">
        <el-segmented
          v-model="renderMode"
          :options="renderModeOptions"
          size="small"
        />
        <GtEntrySyncCapabilityNotice entry-id="xlsx/j2/gt-j2-defined-benefit-plan" />
        <el-tag v-if="syncBusy" type="warning" size="small">同步中…</el-tag>
        <el-tooltip v-else-if="syncUnavailableReason" :content="syncUnavailableReason" placement="bottom">
          <el-tag type="danger" size="small">在线编辑不可用</el-tag>
        </el-tooltip>
        <el-tooltip v-else-if="syncFeedbackOk" :content="syncFeedbackOk" placement="bottom">
          <el-tag type="success" size="small">已同步</el-tag>
        </el-tooltip>
      </div>

      <!-- OnlyOffice 在线编辑（sync bridge 统一路径） -->
      <!-- 🔴 必须包在带确定高度的容器里，否则 host 的 height:100% 解析成 auto、编辑区被压扁 -->
      <div v-if="renderMode === 'onlyoffice' && isJ2SyncedSheet" class="oo-container">
        <WorkpaperSyncEditorHost
          ref="syncEditorHostRef"
          :descriptor="syncOoDescriptor"
          :bridge="syncBridge"
        />
      </div>

      <!-- HTML 结构化视图：原有子组件分发 -->
      <template v-else>
        <!-- 底稿目录 -->
        <J2TabIndex
          v-if="currentSheet === '底稿目录'"
          :wp-id="wpId"
          :project-id="projectId"
          :all-responses="allResponses"
        />
        <!-- J2A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'J2A'"
          sheet-code="J2A"
          :html-data="htmlData"
          :wp-id="wpId"
          :project-id="projectId"
          :is-readonly="isReadonly"
        />
        <!-- J2-1 审定表 -->
        <J2TabAdjudication
          v-else-if="currentSheet === 'J2-1'"
          :wp-id="wpId"
          :project-id="projectId"
          :html-data="htmlData"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :save-immediate="handleChildSave"
          @save="onSave"
        />
        <!-- J2-2 明细表 -->
        <J2TabDetail
          v-else-if="currentSheet === 'J2-2'"
          :wp-id="wpId"
          :project-id="projectId"
          :html-data="htmlData"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :save-immediate="handleChildSave"
        />
        <!-- J2-3 调整分录 -->
        <J2TabAdjustment
          v-else-if="currentSheet === 'J2-3'"
          :wp-id="wpId"
          :project-id="projectId"
          :html-data="htmlData"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :save-immediate="handleChildSave"
        />
        <!-- J2-4 计提情况检查表 -->
        <J2TabAccrualCheck
          v-else-if="currentSheet === 'J2-4'"
          :wp-id="wpId"
          :project-id="projectId"
          :html-data="htmlData"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :save-immediate="handleChildSave"
        />
        <!-- 附注（上市公司） -->
        <J2TabDisclosureListed
          v-else-if="currentSheet === 'J2附注(上市)'"
          :wp-id="wpId"
          :project-id="projectId"
          :html-data="htmlData"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :save-immediate="handleChildSave"
        />
        <!-- 附注（国有企业） -->
        <J2TabDisclosureSoe
          v-else-if="currentSheet === 'J2附注(国企)'"
          :wp-id="wpId"
          :project-id="projectId"
          :html-data="htmlData"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :save-immediate="handleChildSave"
        />
        <!-- 兜底 -->
        <div v-else class="j2-sheet-placeholder">
          <el-empty :description="`J2 未识别的 sheet: ${currentSheet}`" />
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtJ2DefinedBenefitPlan — J2 设定受益计划主入口组件
 *
 * 按 sheetName v-if 分发到各子组件（defineAsyncComponent lazy 加载）。
 * 科目2221长期应付职工薪酬-设定受益计划（贷方/负债类）：期末=期初+贷方-借方
 *
 * 真双向回写：useWorkpaperSyncBridge + WorkpaperSyncEditorHost（参照 D2 接线模式）。
 * persistence三连环：selfLoad(checklist-responses GET) + allResponses Map + handleChildSave(PUT)
 */
import { computed, ref, onMounted, onBeforeUnmount, defineAsyncComponent, inject, provide, toRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import CycleTabProcedure from '../shared/CycleTabProcedure.vue'
import {
  useChecklistPersistence,
  type ChecklistResponse,
} from '@/composables/workpaper/useChecklistPersistence'
import { collectChecklistResponses } from '@/composables/workpaper/checklistPersistenceHelpers'
import { WorkpaperRuntimeContextKey } from '../composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from '../composables/useWorkpaperReviewThreads'
// ── sync bridge 真双向（替代 legacy useWorkpaperEntryDualMode + GtOnlyOfficeSheet）──
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from '../sync/useWorkpaperSyncBridge'
import { readStoreProjection } from '../sync/workpaperSyncApi'
import { capabilityForEntry } from '../sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from '../sync/WorkpaperSyncEditorHost.vue'
import GtEntrySyncCapabilityNotice from '../sync/GtEntrySyncCapabilityNotice.vue'

// ── defineAsyncComponent lazy loading ───────────────────────────────────────
const J2TabIndex = defineAsyncComponent(() => import('./J2TabIndex.vue'))
const J2TabAdjudication = defineAsyncComponent(() => import('./J2TabAdjudication.vue'))
const J2TabDetail = defineAsyncComponent(() => import('./J2TabDetail.vue'))
const J2TabAdjustment = defineAsyncComponent(() => import('./J2TabAdjustment.vue'))
const J2TabAccrualCheck = defineAsyncComponent(() => import('./J2TabAccrualCheck.vue'))
const J2TabDisclosureListed = defineAsyncComponent(() => import('./J2TabDisclosureListed.vue'))
const J2TabDisclosureSoe = defineAsyncComponent(() => import('./J2TabDisclosureSoe.vue'))

// ── J2 sync 常量 ────────────────────────────────────────────────────────────
type J2RenderMode = 'html' | 'onlyoffice'
const J2_SYNC_ENTRY_ID = 'xlsx/j2/gt-j2-defined-benefit-plan'
/**
 * J2 受管 sheet 集合：sheet 代号 → 后端 sheet_key（与 phase5_j2_defined_benefit 契约一致）。
 * 当前 canary 仅接 J2-2 主明细表；J2-1 审定表等归后续批次。
 */
const J2_MANAGED_SHEET_KEYS: Record<string, string> = {
  'J2-2': 'j22-main-managed',
}
const J2_DEFAULT_SHEET_KEY = 'j22-main-managed'

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

const isLoading = ref(true)
const syncSwitching = ref(false)
const runtime = inject(WorkpaperRuntimeContextKey, null)

/** 统一宿主实例 —— 切回结构化视图前用它 forceSave() */
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)

// 目录页跳转
provide('jumpToSection', (sheetName: string) => emit('navigate-sheet', sheetName))

// 复核圆点
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

/** 当前 sheet 名（从 props.sheetName 提取） */
const currentSheet = computed(() => {
  const sn = props.sheetName || ''
  if (/\bJ2A\b/.test(sn) || sn.includes('实质性程序表')) return 'J2A'
  if (sn.includes('底稿目录')) return '底稿目录'
  if (/(?:^|[^A-Z0-9])J2-1(?!\d)/.test(sn) || sn.includes('审定表')) return 'J2-1'
  if (/(?:^|[^A-Z0-9])J2-2(?!\d)/.test(sn) || sn.includes('明细表')) return 'J2-2'
  if (/(?:^|[^A-Z0-9])J2-3(?!\d)/.test(sn) || sn.includes('调整分录')) return 'J2-3'
  if (/(?:^|[^A-Z0-9])J2-4(?!\d)/.test(sn) || sn.includes('计提') || sn.includes('检查表')) return 'J2-4'
  if (sn.includes('上市')) return 'J2附注(上市)'
  if (sn.includes('国有') || sn.includes('国企')) return 'J2附注(国企)'
  const m = sn.match(/^(J2-\d+)/)
  return m ? m[1] : sn
})

/** 当前 sheet 是否在受管清单内（受管清单内的 sheet 可切在线编辑） */
const isJ2SyncedSheet = computed(() => currentSheet.value in J2_MANAGED_SHEET_KEYS)
/** 当前受管 sheet 对应的后端 sheet_key */
const currentSyncSheetKey = computed(
  () => J2_MANAGED_SHEET_KEYS[currentSheet.value] ?? J2_DEFAULT_SHEET_KEY,
)

const isHtmlSheet = computed(() => currentSheet.value !== '底稿目录')

const showModeToolbar = computed(() =>
  isHtmlSheet.value && currentSheet.value !== 'J2A',
)

// ─── sync bridge 真双向（参照 D2 接线）──────────────────────────────────────
const syncEntryId = ref(J2_SYNC_ENTRY_ID)
const syncSheetKey = computed(() => currentSyncSheetKey.value)
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(syncEntryId.value),
  flushHtml: async () => {
    // 先 flush 前端 debounce 的保存（防投影旧值）
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

/** 避免 :descriptor="syncBridge.descriptor.value" 丢失对 ref 的追踪 */
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)

const syncBusy = computed(
  () =>
    syncSwitching.value
    || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)
const syncUnavailableReason = computed(() => {
  if (!isJ2SyncedSheet.value) {
    return '在线编辑仅开放 J2-2 明细表；当前底稿走结构化视图'
  }
  const err = syncBridge.lastError.value
  return err ? `${err.errorCode}: ${err.message}` : ''
})
const syncFeedbackOk = computed(() => {
  const fb = syncBridge.feedback.value
  return fb.kind === 'success' ? fb.message : ''
})

const renderMode = computed({
  get: (): J2RenderMode => (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'html'),
  set: (v: J2RenderMode) => { void switchRenderMode(v) },
})

const renderModeOptions = computed(() => [
  { label: '结构化视图', value: 'html' as const },
  {
    label: '在线编辑',
    value: 'onlyoffice' as const,
    disabled: !isJ2SyncedSheet.value || !!props.isReadonly,
  },
])

async function switchRenderMode(target: J2RenderMode): Promise<void> {
  if (target === renderMode.value) return
  if (target === 'onlyoffice') {
    if (!isJ2SyncedSheet.value) return
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
      // 未改动直接返回表单，不发 forcesave
      await syncBridge.leaveWithoutSaving()
    } else if (syncBridge.canForcesave.value && syncEditorHostRef.value) {
      await syncEditorHostRef.value.forceSave()
    } else {
      syncBridge.persistMode('html')
    }
  } catch { /* 保持 OO；错误在桥上 */ }
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
    if (fallback.size === 0) ElMessage.warning('J2 保存数据加载失败，请刷新后重试')
  }
  const merged = new Map(allResponses.value)
  for (const [itemId, item] of fallback) {
    if (!merged.has(itemId)) merged.set(itemId, item)
  }
  persistence.hydrate(merged)
}

provide('reloadWorkpaperData', selfLoad)

function handleChildSave(items: ChecklistResponse[]): void {
  for (const { item_id, ...patch } of items) {
    persistence.saveDebounced(item_id, patch)
  }
}

async function onSave(): Promise<void> {
  try {
    await persistence.flush()
    emit('save')
  } catch {
    ElMessage.error('J2 保存失败，数据已保留，可重试')
  }
}

watch(currentSheet, async (nextSheet, previousSheet) => {
  if (nextSheet === previousSheet) return
  try {
    await persistence.flush()
  } catch {
    ElMessage.error('J2 切换底稿时保存失败，数据已保留，可返回后重试')
  }
})

onBeforeUnmount(() => { void persistence.flush().catch(() => undefined) })

onMounted(async () => {
  await selfLoad()
  isLoading.value = false
})
</script>

<style scoped>
.j2-defined-benefit-plan {
  padding: 0;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.j2-mode-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
/* 🔴 必须带视口相关的确定高度：WorkpaperSyncEditorHost 根元素是 height:100% + flex 列 */
.oo-container {
  min-height: 600px;
  height: calc(100vh - 280px);
  overflow: hidden;
  border-radius: 8px;
}
.j2-sheet-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}
</style>
