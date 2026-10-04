<template>
  <div class="g4-bond-investment-sppi">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <div v-else-if="loadError" class="error-container">
      <el-card shadow="never">
        <el-result icon="error" title="数据加载失败" :sub-title="loadError">
          <template #extra>
            <el-button type="primary" @click="retrySelfLoad">重试</el-button>
          </template>
        </el-result>
      </el-card>
    </div>
    <template v-else>
      <div class="g4-bond-investment-sppi-toolbar">
        <!--
          🔴 原先绑 legacy `dualMode.currentMode` / `dualMode.onModeChange`（本地 ref）⇒ 桥的
          mode 永远不动、descriptor 恒 null，受管 sheet（G4-7 盘点表）切「在线编辑」后永远停在
          「正在打开…」。现在统一走 `switchRenderMode`：受管经桥，非受管委派 legacy。
        -->
        <el-segmented
          v-if="isHtmlSheet"
          :model-value="renderMode"
          :options="syncModeOptions"
          size="small"
          @change="switchRenderMode"
        />
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g4-bond-investment-sppi" />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value && !isG4SppiSyncManagedSheet" size="small" type="warning">OO不可用</el-tag>
        <el-tag v-if="isG4SppiSyncManagedSheet && syncBusy" size="small" type="info">同步中…</el-tag>
        <el-tag v-if="syncSwitching" size="small" type="info">切换中…</el-tag>
      </div>

      <!-- G4-7 受管 sheet 走 WorkpaperSyncEditorHost 真双向 -->
      <div v-if="isOoMode && isG4SppiSyncManagedSheet" class="oo-container">
        <WorkpaperSyncEditorHost
          v-if="syncOoDescriptor"
          ref="syncEditorHostRef"
          :descriptor="syncOoDescriptor"
          :bridge="syncBridge"
        />
        <div v-else class="oo-loading">正在打开 G4-7 同步编辑器…</div>
      </div>

      <!-- 非受管 sheet 保留 legacy GtOnlyOfficeSheet -->
      <GtOnlyOfficeSheet
        v-else-if="isOoMode"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <G4TabBusinessModel
        v-else-if="currentSheet === 'businessModel'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G4TabSppiTest
        v-else-if="currentSheet === 'sppiTest'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @imported="onSheetImported"
      />

      <G4TabSecuritiesInventory
        v-else-if="currentSheet === 'securitiesInventory'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @imported="onSheetImported"
      />

      <G4TabInventoryReconciliation
        v-else-if="currentSheet === 'inventoryReconciliation'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @imported="onSheetImported"
      />

      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG4BondInvestmentSppi.vue — G4 债权投资底稿(SPPI组)主入口
 * 对齐 G2/Main：formData + g4:save-items 持久化 + 双模式 reload + IE imported
 */
import { ref, computed, toRef, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { useG4SppiDualMode } from '@/composables/useG4SppiDualMode'
import { useG4SppiFormData } from '@/composables/useG4SppiFormData'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import type { ChecklistResponse } from '@/composables/useG4SppiFormData'
import type { AdjustmentEntry } from './composables/useG4MainAdjustment'
import { persistExceptionDraftsToMainWp } from './composables/g4ExceptionRouting'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
// ── G4_SPPI sync bridge（spec: g4-g6-shared-workbook-three-entry-lanes）──
import {
  gSharedWorkbookSheetOf,
  isGSharedWorkbookManagedSheet,
} from './sync/gSharedWorkbookManagedSheets'
import { useGRenderModeSwitch } from './sync/useGRenderModeSwitch'
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const G4TabBusinessModel = defineAsyncComponent(
  () => import('./g4-bond-investment-sppi/classification/G4TabBusinessModel.vue'),
)
const G4TabSppiTest = defineAsyncComponent(
  () => import('./g4-bond-investment-sppi/classification/G4TabSppiTest.vue'),
)
const G4TabSecuritiesInventory = defineAsyncComponent(
  () => import('./g4-bond-investment-sppi/inspection/G4TabSecuritiesInventory.vue'),
)
const G4TabInventoryReconciliation = defineAsyncComponent(
  () => import('./g4-bond-investment-sppi/inspection/G4TabInventoryReconciliation.vue'),
)

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const SHEET_CODE_MAP: Record<string, string> = {
  'G4-5': 'businessModel',
  'G4-6': 'sppiTest',
  'G4-7': 'securitiesInventory',
  'G4-8': 'inventoryReconciliation',
}

const isLoading = ref(true)
const loadError = ref<string | null>(null)
const selfLoadData = ref<Record<string, any> | null>(null)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const isReadonly = computed(() => !!props.readonly)

const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

const formData = useG4SppiFormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
  onAfterSave: () => scheduleAutoSnapshot(),
})

const currentSheet = computed(() => {
  const name = props.sheetName || ''
  const codeMatch = name.match(/G4-([5-8])/)
  if (codeMatch) {
    const code = `G4-${codeMatch[1]}`
    return SHEET_CODE_MAP[code] || ''
  }
  return ''
})

const HTML_SHEETS = new Set([
  'businessModel', 'sppiTest', 'securitiesInventory', 'inventoryReconciliation',
])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

const dualMode = useG4SppiDualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

provide('g4VersionTrailRef', versionTrailRef)
provide('g4OpenVersionHistory', openVersionHistory)
provide('reloadWorkpaperData', () => formData.loadAll())

function onSheetImported(): void {
  void formData.loadAll()
}

async function handleG4SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    for (const it of items) {
      if (it?.item_id) await formData.saveImmediate(it.item_id, it)
    }
    scheduleAutoSnapshot()
  }
}

function handleExceptionDrafts(e: Event): void {
  const drafts = (e as CustomEvent<{ drafts: AdjustmentEntry[] }>).detail?.drafts
  if (!Array.isArray(drafts) || drafts.length === 0) return
  void persistExceptionDraftsToMainWp(drafts, {
    projectId: props.projectId,
  }).then((result) => {
    if (!result) ElMessage.error('未找到 G4 主底稿，异常草稿未写入 G4-3')
  }).catch(() => {
    ElMessage.error('写入 G4-3 异常草稿失败')
  })
}

async function selfLoad(): Promise<void> {
  try {
    await formData.loadAll()
    if (props.htmlData != null) return
    const { data } = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { force_component_type: 'g4-bond-investment-sppi' },
    })
    const sheets = data?.sheets ?? data?.data?.sheets
    if (sheets && sheets.length > 0) {
      selfLoadData.value = sheets[0].html_data ?? sheets[0]
    } else {
      selfLoadData.value = data
    }
  } catch (err: any) {
    loadError.value = err?.message || '加载渲染配置失败'
  }
}

async function retrySelfLoad(): Promise<void> {
  loadError.value = null
  isLoading.value = true
  await selfLoad()
  isLoading.value = false
}

// ── G4_SPPI sync bridge 接线 ────────────────────────────────
/** 本宿主自己的 entry（**不**拿去建桥，见下方 G4_BRIDGE_ENTRY_ID）。 */
const G4_SPPI_HOST_ENTRY_ID = 'xlsx/gt-g4-bond-investment-sppi'
/**
 * 🔴 建桥用的是**共享册 main 的 entry_id**，不是本宿主自己那个。
 *
 * 后端 `phase5_g4_bond_investment.ENTRY_ID === 'xlsx/gt-g4-bond-investment-main'`
 * （一册三 entry，pointer 靠 entry_id 区分、matcher 用 sheet_keys 互斥，裁决 G46-H2），
 * 而它唯一的受管行表 spec 是 `SPEC_G407`（`有价证券盘点表G4-7`，`g407-managed`）——
 * 那张表由**本宿主**渲染（`currentSheet` 正则 `G4-([5-8])`）。
 *
 * 原实现用 `…-sppi` 建桥：那条 entry 没有契约、`adapter_id=null`、受管面为空
 * ⇒ materialize 拿不到任何 sheet。
 */
const G4_BRIDGE_ENTRY_ID = 'xlsx/gt-g4-bond-investment-main'
/**
 * 🔴 受管判定改用 (hostEntryId, 语义名) 二元组。
 *
 * 原实现是 `isGSingleRegionManagedSheet(currentSheet.value)` —— 那个清单按**短码**
 * （`G1-2` 这种）建 map，而本宿主的 `currentSheet` 返回的是**语义名**
 * （`securitiesInventory` 等，经 `SHEET_CODE_MAP` 映射）⇒ 永远命中不到，受管判定恒
 * `false`，`?? 'g407-managed'` 那个 fallback 从未生效过。
 */
const isG4SppiSyncManagedSheet = computed(() =>
  isGSharedWorkbookManagedSheet(G4_SPPI_HOST_ENTRY_ID, currentSheet.value),
)
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const syncEntryId = ref(G4_BRIDGE_ENTRY_ID)
const syncSheetKey = computed(
  () =>
    gSharedWorkbookSheetOf(G4_SPPI_HOST_ENTRY_ID, currentSheet.value)?.sheetKey ?? 'g407-managed',
)
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(G4_BRIDGE_ENTRY_ID),
  flushHtml: async () => {
    formData.flushPending()
    return await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: G4_BRIDGE_ENTRY_ID,
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
  isManagedSheet: isG4SppiSyncManagedSheet,
  editorHostRef: syncEditorHostRef,
})

const isOoMode = computed(
  () => isHtmlSheet.value && currentSheet.value !== '底稿目录' && renderMode.value === 'onlyoffice',
)

onMounted(async () => {
  window.addEventListener('g4:save-items', handleG4SaveItems)
  window.addEventListener('g4:exception-drafts', handleExceptionDrafts)
  await selfLoad()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g4:save-items', handleG4SaveItems)
  window.removeEventListener('g4:exception-drafts', handleExceptionDrafts)
})
</script>

<style scoped>
.g4-bond-investment-sppi { padding: 12px; }
.loading-container { padding: 24px; }
.error-container { padding: 24px; }
.g4-bond-investment-sppi-toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; }

/* ─── 同步编辑器容器 ─── */
/* 🔴 必须带**视口相关的确定高度**：`WorkpaperSyncEditorHost` 根元素是 height:100% + flex 列，
   父级 auto 高度会把编辑区（flex:1; min-height:0）压扁，OnlyOffice 在页面上只剩一条
   （2026-09-22 D4 真栈实证）。模板里用了 `.oo-container` 却不定义它就是这个后果。 */
.oo-container { min-height: 600px; height: calc(100vh - 280px); overflow: hidden; border-radius: 8px; }
.oo-loading { padding: 40px 20px; text-align: center; color: #909399; font-size: 14px; }
</style>
