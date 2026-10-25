<template>
  <div class="m1-dividends-payable">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- M1 底稿目录（不参与双模式） -->
      <M1TabIndex
        v-if="currentSheet === 'index'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 M1A（复用 GtAProgramConsole，不参与双模式） -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'procedure'"
        :wp-id="props.wpId"
        sheet-name="M1A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- 其余 HTML sheet：结构化 / OnlyOffice 双模式切换 -->
      <template v-else>
        <div class="mode-toggle-bar">
          <el-segmented
            :model-value="renderMode"
            :options="renderModeOptions"
            size="small"
            @change="(v: any) => { renderMode = v }"
          />
          <GtEntrySyncCapabilityNotice :entry-id="M1_SYNC_ENTRY_ID" />
        </div>

        <!-- OnlyOffice 在线编辑（统一路径：只有明细表 M1-2 是受管 sheet m101-managed） -->
        <div v-if="renderMode === 'onlyoffice' && isM1SyncedSheet" class="oo-container">
          <WorkpaperSyncEditorHost
            ref="syncEditorHostRef"
            :descriptor="syncOoDescriptor"
            :bridge="syncBridge"
          />
        </div>

        <!-- 结构化视图（HTML sheet 分支） -->
        <template v-else>
          <!-- M1-1 审定表（负债类贷方+按股东分类+小计） -->
          <M1TabAdjudication
            v-if="currentSheet === 'M1-1'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- 附注披露信息（上市公司） -->
          <M1TabDisclosureListed
            v-else-if="currentSheet === 'disclosure-listed'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- 附注披露信息（国有企业） -->
          <M1TabDisclosureSoe
            v-else-if="currentSheet === 'disclosure-soe'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- M1-2 明细表（按股东列示，27列区段Tab） -->
          <M1TabDetail
            v-else-if="currentSheet === 'M1-2'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- M1-3 调整分录汇总（借贷平衡） -->
          <M1TabAdjustment
            v-else-if="currentSheet === 'M1-3'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- M1-4 外币汇率测算表（13公式） -->
          <M1TabFxRate
            v-else-if="currentSheet === 'M1-4'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- M1-5 应付股利（利润）测算表（接收M6，13公式） -->
          <M1TabDividendCalc
            v-else-if="currentSheet === 'M1-5'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- M1-6 应付股利（利润）检查表 -->
          <M1TabDividendCheck
            v-else-if="currentSheet === 'M1-6'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- OnlyOffice fallback: 未迁移 sheet -->
          <GtOnlyOfficeSheet
            v-else
            :wp-id="props.wpId"
            :sheet-name="props.sheetName"
            style="height: 100%; min-height: 600px"
          />
      </template>
    </template>
    </template>

  </div>
</template>

<script setup lang="ts">
/**
 * GtM1DividendsPayable.vue — M1 应付股利（利润）底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取编码（M1/M1A/M1-1~M1-6），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：2232 应付股利（贷方/负债类！期末=期初+贷方-借方）
 * M股东权益循环唯一负债类科目，宣告分配在贷方增加，实际支付在借方减少。
 * 特殊功能：①外币汇率折算(M1-4) ②接收M6利润分配股利联动(M1-5) ③按股东分类
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated(2232) / adjustment:created / m6:profit-distributed(订阅)
 * - 跨底稿联动: TB回写(2232) + M6利润分配→股利测算核对
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, inject, onMounted, provide, toRef, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const M1TabIndex = defineAsyncComponent(() => import('./m1/core/M1TabIndex.vue'))
const M1TabAdjudication = defineAsyncComponent(() => import('./m1/core/M1TabAdjudication.vue'))
const M1TabDetail = defineAsyncComponent(() => import('./m1/core/M1TabDetail.vue'))
const M1TabAdjustment = defineAsyncComponent(() => import('./m1/core/M1TabAdjustment.vue'))
const M1TabDisclosureListed = defineAsyncComponent(() => import('./m1/core/M1TabDisclosureListed.vue'))
const M1TabDisclosureSoe = defineAsyncComponent(() => import('./m1/core/M1TabDisclosureSoe.vue'))

// Calc (外币汇率 + 股利测算)
const M1TabFxRate = defineAsyncComponent(() => import('./m1/calc/M1TabFxRate.vue'))
const M1TabDividendCalc = defineAsyncComponent(() => import('./m1/calc/M1TabDividendCalc.vue'))

// Inspection (检查表)
const M1TabDividendCheck = defineAsyncComponent(() => import('./m1/inspection/M1TabDividendCheck.vue'))

// Shared
const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

const parentEmit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

/**
 * 子组件目录行点击 / 返回目录 → 通知外层 GtWpRenderer 切换 sheetName。
 * GtWpRenderer 监听的是 `@navigate-sheet`(onChildNavigateSheet)，故此处必须
 * emit `navigate-sheet`（而非 `navigate`），否则二级导航静默失效。
 */
function handleNavigate(sheetName: string) {
  parentEmit('navigate-sheet', sheetName)
}

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

// ─── sheetName → 子组件分发 ──────────────────────────────────────────────────

/**
 * 当前激活的 sheet（由外层 GtWpRenderer 通过 sheetName prop 控制）。
 * GtWpRenderer 传入完整 sheet_name（如"审定表M1-1"），
 * 正则提取编码来匹配子组件。
 *
 * 映射关系：
 *   底稿目录                    → index    → M1TabIndex
 *   应付股利实质性程序表M1      → procedure → GtAProgramConsole (复用)
 *   审定表M1-1                  → M1-1     → M1TabAdjudication
 *   附注披露信息（上市公司）    → disclosure-listed → M1TabDisclosureListed
 *   附注披露信息（国有企业）    → disclosure-soe    → M1TabDisclosureSoe
 *   明细表M1-2                  → M1-2     → M1TabDetail
 *   调整分录汇总M1-3            → M1-3     → M1TabAdjustment
 *   外币汇率测算表M1-4          → M1-4     → M1TabFxRate
 *   应付股利（利润）测算表M1-5  → M1-5     → M1TabDividendCalc
 *   应付股利（利润）检查表M1-6  → M1-6     → M1TabDividendCheck
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // 提取 M1-N 编码（M1-1 ~ M1-6）
  const codeMatch = name.match(/M1-[1-6]/)
  if (codeMatch) return codeMatch[0]

  // 程序表 M1A
  if (name.match(/M1A/) || name.includes('实质性程序表')) return 'procedure'

  // 附注特殊匹配
  if (name.includes('上市公司')) return 'disclosure-listed'
  if (name.includes('国有企业')) return 'disclosure-soe'

  // 底稿目录（默认）
  if (name.includes('底稿目录') || name === 'M1' || name === '') return 'index'

  // 未匹配 → OO fallback
  return name
})

// ─── sync bridge（HTML ↔ OnlyOffice 真双向，参照 D2 统一路径） ──────────────
// 后端 contract 仅声明 1 个受管 sheet：明细表M1-2 → m101-managed（现读 contract 确认）。

const M1_SYNC_ENTRY_ID = 'xlsx/gt-m1-dividends-payable'
const M1_MANAGED_SHEET_KEYS: Record<string, string> = { 'M1-2': 'm101-managed' }

const isM1SyncedSheet = computed(() => currentSheet.value in M1_MANAGED_SHEET_KEYS)
const syncEntryId = ref(M1_SYNC_ENTRY_ID)
const syncSheetKey = computed(() => M1_MANAGED_SHEET_KEYS[currentSheet.value] ?? 'm101-managed')
const syncSwitching = ref(false)
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)

const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(syncEntryId.value),
  flushHtml: async () => {
    const snap = await readStoreProjection({ projectId: props.projectId, wpId: props.wpId, entryId: syncEntryId.value })
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: syncSheetKey.value }
  },
  reloadHtml: async (_minimumRevision: number) => { await selfLoad() },
})

const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
type M1RenderMode = 'html' | 'onlyoffice'

const renderMode = computed({
  get: (): M1RenderMode => (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'html'),
  set: (v: M1RenderMode) => { void switchRenderMode(v) },
})

const renderModeOptions = computed(() => [
  { label: '结构化视图', value: 'html' as const },
  { label: '在线编辑', value: 'onlyoffice' as const, disabled: !isM1SyncedSheet.value || isReadonly.value },
])

async function switchRenderMode(target: M1RenderMode): Promise<void> {
  if (target === renderMode.value) return
  if (target === 'onlyoffice') {
    if (!isM1SyncedSheet.value) return
    syncSwitching.value = true
    try { await syncBridge.switchToOnlyOffice() } catch { /* lastError 已由桥写入 */ } finally { syncSwitching.value = false }
    return
  }
  if (syncBridge.mode.value !== 'oo') { syncBridge.persistMode('html'); return }
  syncSwitching.value = true
  try {
    if (String(syncBridge.state.value) === 'applied') { await syncBridge.reloadAfterApplied() }
    else if (syncBridge.mode.value === 'oo' && !syncBridge.dirty.value) { await syncBridge.leaveWithoutSaving() }
    else if (syncBridge.canForcesave.value && syncEditorHostRef.value) { await syncEditorHostRef.value.forceSave() }
    else { syncBridge.persistMode('html') }
  } catch { /* 保持 OO */ } finally { syncSwitching.value = false }
}

// ─── Runtime Boundary（GtWpRenderer 统一提供 版本/复核/AI/displayPrefs + 挂真实 Host） ───
// 复核对话与版本历史由 Runtime Boundary 统一 provide('openReviewDialog') + version 承载，
// 本主入口不再本地 new GtReviewDialog / useWorkpaperVersionToolbar（避免重复 provider/Host）。
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
provide('scheduleAutoSnapshot', () => runtime?.version.scheduleAutoSnapshot())

// 复核圆点（GtReviewTrigger/GtReviewDot 消费）
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

// ─── selfLoad ────────────────────────────────────────────────────────────────

async function selfLoad() {
  if (props.htmlData) {
    // 从 props 提供的数据初始化
    isLoading.value = false
    return
  }

  // 当 htmlData 为空时（bundle 内嵌场景），自行加载 render-config
  try {
    await http.get(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
  } catch (err) {
    console.warn('[GtM1DividendsPayable] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.m1-dividends-payable {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.mode-toggle-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.oo-container {
  height: 80vh;
  min-height: 600px;
}
</style>
