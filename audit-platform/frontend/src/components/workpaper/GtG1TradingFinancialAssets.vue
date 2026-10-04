<template>
  <div class="g1-trading-financial-assets">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="currentSheet !== '底稿目录'" class="g1-toolbar">
        <!--
          🔴 原先 `@change` 直接 `dualMode.switchMode(v)`（legacy 本地 ref）⇒ 桥的 mode 永远
          不动。现在统一走 `switchRenderMode`：受管 sheet（G1-2）经桥，非受管委派 legacy。
        -->
        <el-segmented
          v-if="isHtmlSheet"
          :model-value="renderMode"
          :options="syncModeOptions"
          size="small"
          @change="switchRenderMode"
        />
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g1-trading-financial-assets" />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-button size="small" type="primary" plain @click="openHandbook('preparation')">
          📖 编制手册
        </el-button>
        <el-tag v-if="isHtmlSheet && dualMode.fetchingConfig.value" size="small" type="info">拉取中…</el-tag>
        <el-tag v-else-if="isHtmlSheet && renderMode === 'onlyoffice' && dualMode.ooConfigReady.value" size="small" type="success">已拉取</el-tag>
        <el-tag v-else-if="isHtmlSheet && !dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <!-- 全局勾稽告警（排除当前tab特定告警，避免重复） -->
      <el-alert
        v-if="g1TbDiff !== 0 && currentSheet !== 'G1-1'"
        type="warning"
        :closable="false"
        show-icon
        class="g1-global-alert"
      >
        <template #title>
          G1-1审定合计 与 试算表1501 差异 {{ g1TbDiffFmt }}（审定{{ g1AdjudicatedFmt }} vs TB{{ g1TbClosingFmt }}）
        </template>
      </el-alert>

      <!--
        G1-2 明细表受管 sheet 走 WorkpaperSyncEditorHost 真双向。
        🔴 本宿主原先**建了桥却既不挂 `WorkpaperSyncEditorHost` 也不调
        `switchToOnlyOffice()`** —— `syncBridge` / `syncOoDescriptor` / `syncSwitching`
        全是死代码，OO 模式一律渲染 legacy `GtOnlyOfficeSheet`（假双向）。这比「挂了却不
        驱动」更隐蔽：`bridgeMaterializeDriven` 判据只扫「挂了 EditorHost 的宿主」，
        本文件因为没挂而根本没进扫描面。
      -->
      <div v-if="isOoMode && isG1SyncManagedSheet" class="oo-container">
        <WorkpaperSyncEditorHost
          v-if="syncOoDescriptor"
          ref="syncEditorHostRef"
          :descriptor="syncOoDescriptor"
          :bridge="syncBridge"
        />
        <div v-else class="oo-loading">正在打开 G1-2 同步编辑器…</div>
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

      <CycleTabProcedure
        v-else-if="currentSheet === 'G1A'"
        sheet-code="G1A"
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
            class="g1a-handbook-tip"
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

      <G1TabAdjudication
        v-else-if="currentSheet === 'G1-1'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :html-data="resolvedHtmlData"
        @imported="onSheetImported"
      />

      <G1TabFairValueTest
        v-else-if="currentSheet === 'G1-6'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <G1TabDetail
        v-else-if="currentSheet === 'G1-2'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <G1TabAdjustment
        v-else-if="currentSheet === 'G1-3'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear"
        @imported="onSheetImported"
      />

      <G1TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
      />

      <G1TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
      />

      <G1TabLevel3Reconciliation
        v-else-if="currentSheet === 'G1-7'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <G1TabBusinessModel
        v-else-if="currentSheet === 'G1-8'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
      />

      <G1TabClassification
        v-else-if="currentSheet === 'G1-9'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <G1TabContractCashflow
        v-else-if="currentSheet === 'G1-10'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <G1TabInventory
        v-else-if="currentSheet === 'G1-4'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <G1TabIncomeCalc
        v-else-if="currentSheet === 'G1-5'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <G1TabSecuritiesCount
        v-else-if="currentSheet === 'G1-11'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <G1TabCountReconciliation
        v-else-if="currentSheet === 'G1-12'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        @imported="onSheetImported"
      />

      <G1TabVoucherCheck
        v-else-if="currentSheet === 'G1-13'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :bs-date="g1BsDate"
        @imported="onSheetImported"
      />

      <G1TabDerivativeCheck
        v-else-if="currentSheet === 'G1-14'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- 底稿目录优先走 b-index（对齐 F2）；此处仅作非 B- 分类时的 Host 兜底 -->
      <template v-else-if="currentSheet === '底稿目录'">
        <GCycleBIndexExtras
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName"
          :wp-code="props.wpCode"
          :html-data="directoryHtmlData"
          :available-sheets="availableSheets"
          :all-responses="formData.allResponses.value"
        />
        <G1SheetStatusBar :all-responses="formData.allResponses.value" />
      </template>

      <GtGridSheet
        v-else-if="useGridFallback"
        :html-data="props.htmlData || formData.getSheet(props.sheetName || currentSheet)"
        :readonly="isReadonly"
      />

      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
      <G1PreparationHandbookDialog
        v-model="handbookVisible"
        :initial-tab="handbookTab"
      />
    </template>
    <input
      ref="ieFileRef"
      type="file"
      accept=".xlsx,.xls"
      hidden
      @change="onToolbarImportFile"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { useG1TraFinFormData } from './composables/useG1TraFinFormData'
import { useG1DualMode, type G1RenderMode } from './composables/useG1DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useHostApplicableStandards } from './composables/hostApplicableStandards'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { extractG1SheetCode } from './composables/g1SheetLabels'
import { buildDirectoryHtmlData } from './composables/gCycleIndexRouting'
import { useG1ImportExport, resolveG1ImportableSheet } from './composables/useG1ImportExport'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import G1TabAdjudication from './g1-trading-financial-assets/core/G1TabAdjudication.vue'
import G1TabFairValueTest from './g1-trading-financial-assets/valuation/G1TabFairValueTest.vue'
import G1TabDetail from './g1-trading-financial-assets/core/G1TabDetail.vue'
import G1TabAdjustment from './g1-trading-financial-assets/core/G1TabAdjustment.vue'
import G1TabInventory from './g1-trading-financial-assets/inspection/G1TabInventory.vue'
import G1TabBusinessModel from './g1-trading-financial-assets/classification/G1TabBusinessModel.vue'
import G1TabDerivativeCheck from './g1-trading-financial-assets/inspection/G1TabDerivativeCheck.vue'
import G1PreparationHandbookDialog from './g1-trading-financial-assets/G1PreparationHandbookDialog.vue'
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
// ── G1 sync bridge（spec: g-cycle-single-region-detail-lanes · Task 15）──
import { isGSingleRegionManagedSheet, gSingleRegionSheetKeyOf } from './sync/gSingleRegionManagedSheets'
import { useGRenderModeSwitch } from './sync/useGRenderModeSwitch'
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'

const G1TabDisclosureListed = defineAsyncComponent(() => import('./g1-trading-financial-assets/core/G1TabDisclosureListed.vue'))
const G1TabDisclosureSOE = defineAsyncComponent(() => import('./g1-trading-financial-assets/core/G1TabDisclosureSOE.vue'))
const G1TabLevel3Reconciliation = defineAsyncComponent(() => import('./g1-trading-financial-assets/valuation/G1TabLevel3Reconciliation.vue'))
const G1TabClassification = defineAsyncComponent(() => import('./g1-trading-financial-assets/classification/G1TabClassification.vue'))
const G1TabContractCashflow = defineAsyncComponent(() => import('./g1-trading-financial-assets/classification/G1TabContractCashflow.vue'))
const G1TabIncomeCalc = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabIncomeCalc.vue'))
const G1TabSecuritiesCount = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabSecuritiesCount.vue'))
const G1TabCountReconciliation = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabCountReconciliation.vue'))
const G1TabVoucherCheck = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabVoucherCheck.vue'))
const GCycleBIndexExtras = defineAsyncComponent(() => import('./shared/GCycleBIndexExtras.vue'))
const G1SheetStatusBar = defineAsyncComponent(() => import('./g1-trading-financial-assets/G1SheetStatusBar.vue'))

const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'jump-to-section', sheetName: string): void
}>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const isReadonly = computed(() => !!props.readonly)

const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage' = 'preparation') {
  handbookTab.value = tab
  handbookVisible.value = true
}

/** 审计年度：供 G1-3 从调整分录模块取数 */
const auditYear = computed(() =>
  props.htmlData?.project_context?.audit_year
  ?? props.htmlData?.projectContext?.audit_year
  ?? props.htmlData?.audit_year
  ?? null,
)

/** 资产负债表日：供 G1-13 凭证检查/G1-4 结存/G1-12 盘点倒轧 */
const g1BsDate = computed(() =>
  props.htmlData?.project_context?.bs_date
  ?? props.htmlData?.projectContext?.bs_date
  ?? (auditYear.value ? `${auditYear.value}-12-31` : ''),
)

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

provide('g1VersionTrailRef', versionTrailRef)
provide('g1OpenVersionHistory', openVersionHistory)

const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

const formData = useG1TraFinFormData({
  wpId: wpIdRef,
  projectId: computed(() => props.projectId),
  onAfterSave: () => scheduleAutoSnapshot(),
})

// 适用准则：显式 prop > 本 sheet html_data > runtime context（scaffold 从 render-config
// 顶层注入）。收敛到共享 composable，兼容 v2 对象 / 逗号串 / JSON 串。
const applicableStandards = useHostApplicableStandards({
  htmlData: () => props.htmlData,
})

// ─── 全局勾稽告警 computed ────────────────────────────────────────────────────
const g1Adjudicated = computed(() => {
  const raw = formData.allResponses.value.get('G1-1-adjudicated-amount')?.conclusion
  return raw ? parseFloat(raw) : 0
})
const g1TbClosing = computed(() => {
  const tb = props.htmlData?.tb_values ?? resolvedHtmlData.value?.tb_values
  return tb?.closing ?? 0
})
const g1TbDiff = computed(() => {
  const adj = g1Adjudicated.value
  const tb = g1TbClosing.value
  if (!adj && !tb) return 0
  return Math.abs(adj - tb) < 1 ? 0 : adj - tb
})
const fmtNum = (v: number) => v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const g1TbDiffFmt = computed(() => fmtNum(g1TbDiff.value))
const g1AdjudicatedFmt = computed(() => fmtNum(g1Adjudicated.value))
const g1TbClosingFmt = computed(() => fmtNum(g1TbClosing.value))

const currentSheet = computed(() => extractG1SheetCode(props.sheetName || props.wpCode || ''))

/** 优先用外层已渲染的 htmlData；否则从 loadAll 的 sheetCache 取当前表 */
const resolvedHtmlData = computed(() => {
  if (props.htmlData != null) return props.htmlData
  const cache = formData.sheetCache.value
  const keys = Object.keys(cache)
  if (!keys.length) return null
  const code = currentSheet.value
  const hit = keys.find((k) => extractG1SheetCode(k) === code)
  return hit ? cache[hit] : cache[keys[0]]
})
const MIGRATED_SHEETS = new Set([
  'G1A', 'G1-1', 'G1-2', 'G1-3', 'G1-4', 'G1-5', 'G1-6', 'G1-7',
  'G1-8', 'G1-9', 'G1-10', 'G1-11', 'G1-12', 'G1-13', 'G1-14',
  '附注上市', '附注国企', '底稿目录',
])

const isHtmlSheet = computed(() => MIGRATED_SHEETS.has(currentSheet.value))

const sheetNameRef = computed(() => props.sheetName || '')

const availableSheets = computed(() => {
  const fromHtml = props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml
  return Object.keys(formData.sheetCache.value).map(sheet_name => ({ sheet_name }))
})

/** 目录页传给 GCycleBIndexExtras 的 htmlData：从 sheetCache 补全 cycle_workpapers（本循环底稿目录 grid） */
const directoryHtmlData = computed(() =>
  buildDirectoryHtmlData(props.htmlData, formData.sheetCache.value),
)

const dualMode = useG1DualMode({
  wpId: wpIdRef,
  currentSheet,
  availableSheets,
  sheetName: sheetNameRef,
  projectId: computed(() => props.projectId),
  reloadAll: () => formData.loadAll(),
})

const ooSheetName = computed(
  () => dualMode.resolveOoSheetName() || props.sheetName || 'G1-1',
)

// 🔴 原先这里有 `renderMode` computed（get/set 包 legacy `dualMode`）+ `renderModeOptions`，
//    setter 直接 `dualMode.switchMode(v)` ⇒ 受管 sheet 也只翻 legacy 本地 ref，桥的 mode
//    永远不动。两者现由下方 `useGRenderModeSwitch` 提供（受管以桥为真源）。

function onOoFallback(): void {
  dualMode.onOoFallback()
}

const useGridFallback = computed(() => {
  const code = currentSheet.value
  return !!code && !isHtmlSheet.value
})

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: () => formData.loadAll(),
  wpId: wpIdRef,
})

async function selfLoad() {
  await formData.loadAll()
  isLoading.value = false
}

function onSheetImported() {
  void formData.loadAll()
}

// spec: tb-writeback-explicit-publish-gate Task 12：移除 handleG1Writeback（旧 TB 回写路径）
// —— TB 回写改由 G1-1 审定表「发布到试算表」显式确认门（G1TabAdjudication.handlePublishToTb）承载。

function handleAdjudicated(payload: any): void {
  const code = payload?.accountCode ?? payload?.account_codes?.[0]
  if (code !== '1501') return
  const amount = payload?.auditedAmount ?? payload?.audited_amount
  if (typeof amount !== 'number' || !Number.isFinite(amount)) return
  void formData.saveImmediate('G1-1-adjudicated-amount', {
    item_id: 'G1-1-adjudicated-amount',
    conclusion: String(amount),
    remark: null,
  })
}

/** window兼容监听器（供crossWpEventBridge旧生产者） */
function handleAdjudicatedWindow(e: Event): void {
  const d = (e as CustomEvent).detail
  handleAdjudicated(d)
}

const ie = useG1ImportExport({ wpId: wpIdRef })
const ieFileRef = ref<HTMLInputElement | null>(null)

function handleExportData() {
  const sheet = resolveG1ImportableSheet(currentSheet.value)
  if (!sheet) {
    ElMessage.info('当前底稿暂不支持导出数据')
    return
  }
  void ie.exportData(sheet)
}

function handleImport() {
  const sheet = resolveG1ImportableSheet(currentSheet.value)
  if (!sheet) {
    ElMessage.info('当前底稿暂不支持导入')
    return
  }
  ieFileRef.value?.click()
}

async function onToolbarImportFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const sheet = resolveG1ImportableSheet(currentSheet.value)
  if (!sheet) return
  // 导入前打快照，便于回退
  await (runtime?.version.createImportSnapshot?.() ?? Promise.resolve())
  const result = await ie.importData(sheet, file)
  if (result) onSheetImported()
}

defineExpose({
  handleExportData,
  handleImport,
  handleImportClick: handleImport,
})

// ── G1 sync bridge 接线（Task 15 · Requirements 4.7）───────────────────────
const G1_SYNC_ENTRY_ID = 'xlsx/gt-g1-trading-financial-assets'
const isG1SyncManagedSheet = computed(() => isGSingleRegionManagedSheet(currentSheet.value))
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const syncEntryId = ref(G1_SYNC_ENTRY_ID)
const syncSheetKey = computed(() => gSingleRegionSheetKeyOf(currentSheet.value) ?? 'g102-managed')
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(G1_SYNC_ENTRY_ID),
  flushHtml: async () => {
    formData.flushPending()
    return await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: G1_SYNC_ENTRY_ID,
    })
  },
  reloadHtml: () => formData.loadAll(),
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncBusy = computed(() => WP_BRIDGE_IN_FLIGHT_STATES.includes(syncBridge.state.value))

// 🔴 受管 sheet 必须经桥切换 —— 桥建好了但没人调 `switchToOnlyOffice()` 就是空壳。
const {
  renderMode,
  modeOptions: syncModeOptions,
  switching: syncSwitching,
  switchRenderMode,
} = useGRenderModeSwitch({
  bridge: syncBridge,
  legacy: dualMode,
  isManagedSheet: isG1SyncManagedSheet,
  editorHostRef: syncEditorHostRef,
})

const isOoMode = computed(
  () => isHtmlSheet.value && currentSheet.value !== '底稿目录' && renderMode.value === 'onlyoffice',
)

onMounted(() => {
  // eventBus 订阅（crossWpEventBridge已双向桥接，优先mitt）
  // spec: tb-writeback-explicit-publish-gate Task 12：移除 g1:writeback-trial-balance 监听
  // （TB 回写改由 G1-1 审定表「发布到试算表」显式确认门承载）；保留 substantive:adjudicated
  // 供审定数落库/附注刷新（不写 TB）。
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  window.addEventListener('substantive:adjudicated', handleAdjudicatedWindow)
  void selfLoad()
})

onBeforeUnmount(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicated)
  window.removeEventListener('substantive:adjudicated', handleAdjudicatedWindow)
  formData.flushPending()
})
</script>

<style scoped>
.g1-trading-financial-assets { padding: 12px; }
.loading-container { padding: 24px; }
.g1-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
.g1-index-toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
.g1a-handbook-tip { flex: 1; min-width: 220px; margin-right: 4px; }
.g-cycle-tab-index-page { padding: 0; }
.g1-global-alert { margin-bottom: 8px; }

/* ─── 同步编辑器容器 ─── */
/* 🔴 必须带**视口相关的确定高度**：`WorkpaperSyncEditorHost` 根元素是 height:100% + flex 列，
   父级 auto 高度会把编辑区（flex:1; min-height:0）压扁，OnlyOffice 在页面上只剩一条
   （2026-09-22 D4 真栈实证）。模板里用了 `.oo-container` 却不定义它就是这个后果。 */
.oo-container { min-height: 600px; height: calc(100vh - 280px); overflow: hidden; border-radius: 8px; }
.oo-loading { padding: 40px 20px; text-align: center; color: #909399; font-size: 14px; }
</style>
