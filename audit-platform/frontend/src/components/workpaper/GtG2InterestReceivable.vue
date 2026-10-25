<template>
  <div class="g2-interest-receivable">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="currentSheet !== '底稿目录'" class="g2-interest-receivable-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          :model-value="renderMode"
          :options="renderModeOptions"
          size="small"
          @change="switchRenderMode"
        />
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g2-interest-receivable" />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-button size="small" type="primary" plain @click="openHandbook('preparation')">
          📖 编制手册
        </el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value && !isG2SyncManagedSheet" size="small" type="warning">OO不可用</el-tag>
        <el-tag v-if="isG2SyncManagedSheet && syncBusy" size="small" type="info">同步中…</el-tag>
        <el-tag v-if="syncSwitching" size="small" type="info">切换中…</el-tag>
      </div>

      <!-- G2 canary 受管 sheet（G2-2 明细表）走 WorkpaperSyncEditorHost 真双向 -->
      <!-- 🔴 只传该组件真实声明的两个必填 prop：`descriptor` + `bridge`。F 循环四条 lane 还
           额外传了 wp-id/project-id/readonly —— 那三个**不是** props，会以 DOM 属性形态
           落到根 div 上（readonly 在 div 上无意义），本 lane 不复制。 -->
      <div v-if="isOoMode && isG2SyncManagedSheet" class="oo-container">
        <WorkpaperSyncEditorHost
          v-if="syncOoDescriptor"
          ref="syncEditorHostRef"
          :descriptor="syncOoDescriptor"
          :bridge="syncBridge"
        />
        <div v-else class="oo-loading">正在打开 G2-2 同步编辑器…</div>
      </div>

      <!-- 非受管 sheet 保留 legacy GtOnlyOfficeSheet（假双向，如实登记） -->
      <GtOnlyOfficeSheet
        v-else-if="isOoMode"
        :key="ooSheetName"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="ooSheetName"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
        @fallback="onOoFallback"
      />

      <!-- G2A 程序表（对齐 D4A） -->
      <CycleTabProcedure
        v-else-if="currentSheet === 'G2A'"
        sheet-code="G2A"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      >
        <template #toolbar>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="g2a-handbook-tip"
            title="本表为程序控制台：勾选拟执行程序并填索引。不熟悉编制逻辑？请打开手册。"
          />
          <el-button type="primary" size="small" @click="openHandbook('preparation')">
            📖 编制手册
          </el-button>
          <el-button size="small" @click="openHandbook('usage')">
            使用手册
          </el-button>
        </template>
      </CycleTabProcedure>

      <!-- G2-1 审定表 -->
      <G2TabAdjudication
        :html-data="props.htmlData"
        v-else-if="currentSheet === 'G2-1'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- G2-2 明细表 -->
      <G2TabDetail
        v-else-if="currentSheet === 'G2-2'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- G2-3 坏账准备明细 -->
      <G2TabBadDebtDetail
        v-else-if="currentSheet === 'G2-3'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- G2-4 调整分录汇总（对齐 D4-4 + 调整分录模块联动） -->
      <G2TabAdjustment
        v-else-if="currentSheet === 'G2-4'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear"
        @imported="onSheetImported"
      />

      <!-- G2-5 利息测算表 -->
      <G2TabInterestCalc
        v-else-if="currentSheet === 'G2-5'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- G2-6 长期未收回检查 -->
      <G2TabOverdueCheck
        v-else-if="currentSheet === 'G2-6'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- G2-7 坏账准备测算（单项/账龄组合/其他组合） -->
      <G2TabECLCalc
        v-else-if="currentSheet === 'G2-7'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- G2-8 凭证检查表（借方/贷方区块） -->
      <G2TabVoucherCheck
        v-else-if="currentSheet === 'G2-8'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- 附注披露(上市) -->
      <G2TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
      />

      <!-- 附注披露(国企) -->
      <G2TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
      />

      <!-- 底稿目录（对齐 G1：泳道卡片） -->
      <template v-else-if="currentSheet === '底稿目录'">
        <GCycleBIndexExtras
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName"
          :wp-code="props.wpCode"
          :html-data="directoryHtmlData"
          :available-sheets="availableSheets"
          :all-responses="allResponsesRef"
        />
      </template>

      <!-- 兜底：未迁移 sheet → OnlyOffice -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
      <G2PreparationHandbookDialog
        v-model="handbookVisible"
        :initial-tab="handbookTab"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG2InterestReceivable.vue — G2 应收利息底稿主入口
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 1.1, 9.1~9.3
 * sheetName 分发到 G2 专属子组件（G2-1~G2-8 + 附注），G2A/未迁移走 OnlyOffice
 * 集成：useWorkpaperVersionToolbar(autoSnapshot) + provide('openReviewDialog')
 * EventBus：监听 g2:save-items 持久化 + substantive:adjudicated(1132)
 */
import {
  ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent, toRef,
} from 'vue'
import { useG2IntRecFormData } from './composables/useG2IntRecFormData'
// 🔴 P14：`useG2DualMode` 是**共享基座** `useWorkpaperEntryDualMode` 的 G2 包装（59 行）。
//    接桥 SHALL 保留它、**不内联展开** —— 基座被 30 个循环共同消费，删它会打断多个循环。
import { useG2DualMode } from './composables/useG2DualMode'
import { extractG2SheetCode, buildG2FallbackSheets } from './composables/g2SheetLabels'
import { buildDirectoryHtmlData } from './composables/gCycleIndexRouting'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useHostApplicableStandards } from './composables/hostApplicableStandards'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import type { ChecklistResponse } from './composables/useF1FormData'
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
// ── G2 canary 真双向（spec: g-cycle-sync-foundation-and-first-canary · Task 15）──
// 受管 sheet（G2-2 明细表）走 syncBridge；非受管保留 legacy GtOnlyOfficeSheet（假双向，如实登记）。
import { g2SheetKeyOf, isG2OoWiredRowsSheet } from './sync/g2ManagedSheets'
import { useGRenderModeSwitch } from './sync/useGRenderModeSwitch'
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GCycleBIndexExtras = defineAsyncComponent(() => import('./shared/GCycleBIndexExtras.vue'))
const G2TabAdjudication = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabAdjudication.vue'))
const G2TabDetail = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabDetail.vue'))
const G2TabBadDebtDetail = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabBadDebtDetail.vue'))
const G2TabAdjustment = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabAdjustment.vue'))
const G2TabInterestCalc = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabInterestCalc.vue'))
const G2TabOverdueCheck = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabOverdueCheck.vue'))
const G2TabECLCalc = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabECLCalc.vue'))
const G2TabVoucherCheck = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabVoucherCheck.vue'))
const G2TabDisclosureListed = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabDisclosureListed.vue'))
const G2TabDisclosureSOE = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabDisclosureSOE.vue'))
const G2PreparationHandbookDialog = defineAsyncComponent(
  () => import('./g2-interest-receivable/G2PreparationHandbookDialog.vue'),
)

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
  /** 项目适用准则（上市/国企等），用于附注章节映射 */
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  (e: 'jump-to-section', sheetName: string): void
}>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const formData = useG2IntRecFormData({ wpId: wpIdRef, projectId: projectIdRef })
const allResponsesRef = computed(() => formData.allResponses.value)
const isReadonly = computed(() => !!props.readonly)
// 适用准则：显式 prop > 本 sheet html_data > runtime context（scaffold 从 render-config
// 顶层注入）。收敛到共享 composable，兼容 v2 对象 / 逗号串 / JSON 串。
const applicableStandards = useHostApplicableStandards({
  explicit: () => props.applicableStandards,
  htmlData: () => props.htmlData,
})
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

provide('g2VersionTrailRef', versionTrailRef)
provide('g2OpenVersionHistory', openVersionHistory)

const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

/** 与 G1 对齐：sheetName → 内部分发编码（含底稿目录 / 附注） */
const currentSheet = computed(() => extractG2SheetCode(props.sheetName || props.wpCode || ''))

const MIGRATED_SHEETS = new Set([
  'G2A', 'G2-1', 'G2-2', 'G2-3', 'G2-4', 'G2-5', 'G2-6', 'G2-7', 'G2-8',
  '附注上市', '附注国企', '底稿目录',
])
const isHtmlSheet = computed(() => MIGRATED_SHEETS.has(currentSheet.value))

const availableSheets = computed(() => {
  const fromHtml = props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml
  // 对齐 G1：优先用自加载 render-config 的 sheetCache（真实 sheet 名）
  const cached = Object.keys(formData.sheetCache.value)
  if (cached.length) return cached.map(sheet_name => ({ sheet_name }))
  // 对齐 D4：仍无数据时用静态映射兜底，保证目录与 OO 解析有可用 sheet 名
  return buildG2FallbackSheets()
})

/** 目录页传给 GCycleBIndexExtras 的 htmlData：从 sheetCache 补全 cycle_workpapers（本循环底稿目录 grid） */
const directoryHtmlData = computed(() =>
  buildDirectoryHtmlData(props.htmlData, formData.sheetCache.value),
)

const dualMode = useG2DualMode({
  wpId: wpIdRef,
  currentSheet,
  availableSheets,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

const ooSheetName = computed(
  () => dualMode.resolveOoSheetName() || props.sheetName || '应收利息实质性程序表G2A',
)

// 🔴 2026-09-30 迁移：手写的 renderMode/renderModeOptions/switchRenderMode/syncSwitching（~50 行）
//    替换为共享 `useGRenderModeSwitch`。G2 是 foundation canary，交付时该 composable 还不存在；
//    其余 14 个宿主已全部用它。13 份同构代码只有一份 = 改一处全修、漏一处全漏。
const {
  renderMode,
  modeOptions: renderModeOptions,
  switching: syncSwitching,
  switchRenderMode,
} = useGRenderModeSwitch({
  bridge: syncBridge,
  legacy: dualMode,
  isManagedSheet: isG2SyncManagedSheet,
  editorHostRef: syncEditorHostRef,
})

function onOoFallback(): void {
  dualMode.onOoFallback()
}

// ─── G2 canary sync bridge（Task 15 · Requirements 4.7）─────────────────────────
//
// 受管 sheet 判定**从受管清单派生**（`sync/g2ManagedSheets.ts`），不在宿主内联字面量：
// 那份清单由后端契约测试 `test_g2_frontend_managed_sheet_parity.py` 逐字守护它与 provider
// `all_managed_sheet_names()` / 行表 spec `sheet_key` 一致。F 循环 4 条 lane 都在宿主里内联
// `F*_SHEET_KEY_BY_CODE`（注释说"从 provider 派生"而实现是硬编码），本 lane 照 D3 做实。
const G2_SYNC_ENTRY_ID = 'xlsx/gt-g2-interest-receivable'
/** 当前 sheet 是否走 syncBridge 真双向路径（= 受管行表且已接 OO 直写宿主）。 */
const isG2SyncManagedSheet = computed(() => isG2OoWiredRowsSheet(currentSheet.value))
/**
 * OO 模式判定 —— 与改造前 `isHtmlSheet && currentSheet !== '底稿目录' && renderMode === 'onlyoffice'`
 * 逐条等价，抽出成命名 computed 是因为现在有两个互斥分支（真双向宿主 / legacy OO）共用它。
 */
const isOoMode = computed(
  () => isHtmlSheet.value && currentSheet.value !== '底稿目录' && renderMode.value === 'onlyoffice',
)
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const syncEntryId = ref(G2_SYNC_ENTRY_ID)
/** 受管时取该 sheet 的 `sheet_key`；非受管回落 canary 键（桥此时不挂载，仅保持类型非空）。 */
const syncSheetKey = computed(() => g2SheetKeyOf(currentSheet.value) ?? 'g202-managed')
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(G2_SYNC_ENTRY_ID),
  // 🔴 顺序刚性：先 flushPending 把 HTML debounce 落库，再 readStoreProjection —— 反序会把
  //    未落库的编辑读成空投影（D2 canary 踩过）。
  // 🔴 `readStoreProjection` 的入参类型是 `WorkpaperSyncEntryScope` = 恰三段
  //    `{projectId, wpId, entryId}`。F/D 循环多处还塞了 `sheetKey` —— 那是**多余属性**，
  //    GET `/store-projection` 端点根本不收 sheet_key（它按 provider 的
  //    `all_store_item_ids()` 投影**整个 entry** 的全部受管区），传了会被静默丢弃并让
  //    TS 报 excess property。本 lane 按真实签名传三段。
  flushHtml: async () => {
    formData.flushPending()
    return await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: G2_SYNC_ENTRY_ID,
    })
  },
  reloadHtml: () => formData.loadAll(),
})
/** 避免 `:descriptor="syncBridge.descriptor.value"` 丢失对 ref 的追踪（D1/D2 同款）。 */
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
// 🔴 `WP_BRIDGE_IN_FLIGHT_STATES` 是 `readonly WorkpaperSyncBridgeState[]`（不是 Set）
//    ⇒ 用 `.includes`。桥内部自己也是 `.includes`（useWorkpaperSyncBridge.ts:1320）。
const syncBusy = computed(() => WP_BRIDGE_IN_FLIGHT_STATES.includes(syncBridge.state.value))

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: () => formData.loadAll(),
  wpId: wpIdRef,
})

/** 审计年度：供 G2-4 从调整分录模块取数 */
const auditYear = computed(() =>
  props.htmlData?.project_context?.audit_year
  ?? props.htmlData?.projectContext?.audit_year
  ?? props.htmlData?.audit_year
  ?? null,
)

function onSheetImported(): void {
  void formData.loadAll()
}

const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}

// 复核对话 openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide，子组件 inject 命中祖先
provide('reloadWorkpaperData', () => formData.loadAll())

// ─── 监听 g2:save-items → 保存 + autoSnapshot ───────────────────────────────
async function handleG2SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    for (const it of items) {
      if (it?.item_id) await formData.saveImmediate(it.item_id, it)
    }
    scheduleAutoSnapshot()
  }
}

// ─── 监听 substantive:adjudicated(1132) → 附注刷新 ──────────────────────────
function handleAdjudicated(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
  if (d?.accountCode === '1132') {
    void formData.saveImmediate('G2-1-adjudicated-amount', {
      item_id: 'G2-1-adjudicated-amount',
      conclusion: String(d.adjudicatedAmount),
      remark: null,
    })
  }
}

// spec: tb-writeback-explicit-publish-gate Task 12：移除 g2:writeback-trial-balance
// 监听器 handleG2Writeback —— TB 回写改由 G2-1 审定表「发布到试算表」显式确认门
// （useG2Adjudication.publishToTb → POST publish-to-tb，科目1132余额口径）承载。
// 保留 g2:save-items 与 substantive:adjudicated（供跨模块刷新，不重复写 TB）。

onMounted(async () => {
  window.addEventListener('g2:save-items', handleG2SaveItems)
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g2:save-items', handleG2SaveItems)
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
  formData.flushPending()
})
</script>

<style scoped>
.g2-interest-receivable { padding: 12px; }
.loading-container { padding: 24px; }
.g2-interest-receivable-toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
/* 🔴 在线编辑区必须拿到视口相关的确定高度：WorkpaperSyncEditorHost 根元素是
   height:100% + flex 列，父级为 auto 高度时编辑区被压扁（D4 真栈踩过，
   workpaperSyncEditorHostSizing 守卫覆盖）。 */
.oo-container { min-height: 600px; height: calc(100vh - 200px); }
.oo-loading { display: flex; align-items: center; justify-content: center; height: 100%; color: #909399; }
.g2a-handbook-tip { flex: 1; min-width: 220px; margin-right: 4px; }
.g2-index-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
</style>
