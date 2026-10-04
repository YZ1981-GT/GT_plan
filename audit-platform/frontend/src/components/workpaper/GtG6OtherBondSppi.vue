<template>
  <div class="g6-other-bond-investment-sppi">
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
      <div class="g6-other-bond-investment-sppi-toolbar">
        <!--
          🔴 原先绑 legacy `dualMode.currentMode` / `dualMode.onModeChange`（本地 ref）⇒ 桥的
          mode 永远不动、descriptor 恒 null，受管 sheet（G6-5 公允价值测试表）切「在线编辑」后
          永远停在「正在打开…」。现在统一走 `switchRenderMode`。
        -->
        <el-segmented
          v-if="isHtmlSheet"
          :model-value="renderMode"
          :options="syncModeOptions"
          size="small"
          @change="switchRenderMode"
        />
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g6-other-bond-sppi" />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value && !isG6SppiSyncManagedSheet" size="small" type="warning">OO不可用</el-tag>
        <el-tag v-if="isG6SppiSyncManagedSheet && syncBusy" size="small" type="info">同步中…</el-tag>
        <el-tag v-if="syncSwitching" size="small" type="info">切换中…</el-tag>
      </div>

      <!-- 双模式：HTML sheet 切到 OnlyOffice -->
      <!-- G6-5 受管 sheet 走 WorkpaperSyncEditorHost 真双向 -->
      <div v-if="isOoMode && isG6SppiSyncManagedSheet" class="oo-container">
        <WorkpaperSyncEditorHost
          v-if="syncOoDescriptor"
          ref="syncEditorHostRef"
          :descriptor="syncOoDescriptor"
          :bridge="syncBridge"
        />
        <div v-else class="oo-loading">正在打开 G6-5 同步编辑器…</div>
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

      <!-- G6-5 公允价值测试表 -->
      <G6TabFairValueTest
        v-else-if="currentSheet === 'fairValueTest'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @imported="onSheetImported"
      />

      <!-- G6-6 利息测算表 -->
      <G6TabInterestCalculation
        v-else-if="currentSheet === 'interestCalculation'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @imported="onSheetImported"
      />

      <!-- G6-7 业务模式分析 -->
      <G6TabBusinessModel
        v-else-if="currentSheet === 'businessModel'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G6-8 SPPI测试 -->
      <G6TabSppiTest
        v-else-if="currentSheet === 'sppiTest'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G6-9 有价证券盘点表 -->
      <G6TabSecuritiesInventory
        v-else-if="currentSheet === 'securitiesInventory'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @imported="onSheetImported"
      />

      <!-- G6-10 盘点倒轧表 -->
      <G6TabInventoryRollForward
        v-else-if="currentSheet === 'inventoryRollForward'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @imported="onSheetImported"
      />

      <!-- 兜底：未迁移/未匹配 sheet → OnlyOffice fallback -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 版本链/复核 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG6OtherBondSppi.vue — G6 其他债权投资(SPPI组)主入口
 *
 * 对齐 G4 SPPI：formData + g6:save-items 持久化 + 双模式 reload + IE imported
 * sheetName正则提取编码(G6-5~G6-10) → v-if分发到6个defineAsyncComponent子组件
 * 未匹配 → OnlyOffice fallback
 */
import { ref, computed, toRef, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { useG6SppiDualMode } from './composables/useG6SppiDualMode'
import { useG6SppiFormData, type ChecklistResponse } from './composables/useG6SppiFormData'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { matchG6SaveItemsEvent } from './composables/g6CrossHelpers'
import http from '@/utils/http'
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
// ── G6_SPPI sync bridge（spec: g4-g6-shared-workbook-three-entry-lanes）──
import {
  gSharedWorkbookSheetOf,
  isGSharedWorkbookManagedSheet,
} from './sync/gSharedWorkbookManagedSheets'
import { useGRenderModeSwitch } from './sync/useGRenderModeSwitch'
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'

// ─── defineAsyncComponent 懒加载所有子组件 ───────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const G6TabFairValueTest = defineAsyncComponent(
  () => import('./g6-other-bond-investment-sppi/fair-value/G6TabFairValueTest.vue'),
)
const G6TabInterestCalculation = defineAsyncComponent(
  () => import('./g6-other-bond-investment-sppi/interest/G6TabInterestCalculation.vue'),
)
const G6TabBusinessModel = defineAsyncComponent(
  () => import('./g6-other-bond-investment-sppi/classification/G6TabBusinessModel.vue'),
)
const G6TabSppiTest = defineAsyncComponent(
  () => import('./g6-other-bond-investment-sppi/classification/G6TabSppiTest.vue'),
)
const G6TabSecuritiesInventory = defineAsyncComponent(
  () => import('./g6-other-bond-investment-sppi/inspection/G6TabSecuritiesInventory.vue'),
)
const G6TabInventoryRollForward = defineAsyncComponent(
  () => import('./g6-other-bond-investment-sppi/inspection/G6TabInventoryRollForward.vue'),
)

// ─── Props ──────────────────────────────────────────────────────────────────
const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

// ─── sheetName 正则 → 编码映射 ──────────────────────────────────────────────
const SHEET_CODE_MAP: Record<string, string> = {
  'G6-5': 'fairValueTest',
  'G6-6': 'interestCalculation',
  'G6-7': 'businessModel',
  'G6-8': 'sppiTest',
  'G6-9': 'securitiesInventory',
  'G6-10': 'inventoryRollForward',
}

const isLoading = ref(true)
const loadError = ref<string | null>(null)
const selfLoadData = ref<Record<string, any> | null>(null)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const isReadonly = computed(() => !!props.readonly)

/** 提取当前sheetName对应的组件标识 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // 正则匹配：G6-5/G6-6/G6-7/G6-8/G6-9/G6-10
  const codeMatch = name.match(/G6-(5|6|7|8|9|10)/)
  if (codeMatch) {
    const code = `G6-${codeMatch[1]}`
    return SHEET_CODE_MAP[code] || ''
  }

  return ''
})

/** 已迁移为HTML专属组件的sheet列表（支持双模式切换） */
const HTML_SHEETS = new Set([
  'fairValueTest',
  'interestCalculation',
  'businessModel',
  'sppiTest',
  'securitiesInventory',
  'inventoryRollForward',
])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))

/** 解析后的 htmlData（优先使用prop，fallback到selfLoad结果） */
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

const formData = useG6SppiFormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
  onAfterSave: () => scheduleAutoSnapshot(),
})

// ─── 双模式切换 ─────────────────────────────────────────────────────────────
const dualMode = useG6SppiDualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

provide('g6VersionTrailRef', versionTrailRef)
provide('g6OpenVersionHistory', openVersionHistory)
provide('reloadWorkpaperData', () => formData.loadAll())
provide('g6SppiFormData', formData)

function onSheetImported(): void {
  void formData.loadAll()
}

async function handleG6SaveItems(e: Event): Promise<void> {
  const items = matchG6SaveItemsEvent(e, props.wpId)
  if (!items?.length) return
  await formData.saveItemsFromEvent(items as ChecklistResponse[])
  scheduleAutoSnapshot()
}

/** 始终 loadAll；htmlData 为空时再拉取 render-config 作 selfLoad */
async function selfLoad(): Promise<void> {
  try {
    await formData.loadAll()
    if (props.htmlData != null) return
    const { data } = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { force_component_type: 'g6-other-bond-investment-sppi' },
    })
    const sheets = data?.sheets ?? data?.data?.sheets
    if (sheets && sheets.length > 0) {
      selfLoadData.value = sheets[0].html_data ?? sheets[0]
    } else {
      const parsed = formData.parseContent()
      if (parsed && Object.keys(parsed).length > 0) {
        selfLoadData.value = parsed as Record<string, any>
      } else {
        selfLoadData.value = data
      }
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

// ─── 生命周期 ───────────────────────────────────────────────────────────────
// ── G6_SPPI sync bridge 接线 ────────────────────────────────
/** 本宿主自己的 entry（**不**拿去建桥，见下方 G6_BRIDGE_ENTRY_ID）。 */
const G6_SPPI_HOST_ENTRY_ID = 'xlsx/gt-g6-other-bond-sppi'
/**
 * 🔴 建桥用的是**共享册 main 的 entry_id**，不是本宿主自己那个。
 *
 * 后端 `phase5_g6_other_bond.ENTRY_ID === 'xlsx/gt-g6-other-bond-main'`（一册多 entry，
 * pointer 靠 entry_id 区分、matcher 用 sheet_keys 互斥，裁决 G46-H2），它唯一的受管行表
 * spec 是 `SPEC_G605`（`公允价值测试表G6-5`，`g605-managed`）—— 那张表由**本宿主**渲染
 * （`currentSheet` 正则 `G6-(5|6|7|8|9|10)`）。
 *
 * 原实现用 `…-sppi` 建桥：那条 entry 没有契约、`adapter_id=null`、受管面为空。
 */
const G6_BRIDGE_ENTRY_ID = 'xlsx/gt-g6-other-bond-main'
/**
 * 🔴 受管判定改用 (hostEntryId, 语义名) 二元组 —— 原先用按**短码**建 map 的
 * `isGSingleRegionManagedSheet`，而本宿主 `currentSheet` 返回**语义名**
 * （`fairValueTest` 等）⇒ 恒 `false`。且 G4-SPPI 与本宿主的语义名集合有交集
 * （两边都有 `securitiesInventory`），单键 map 会串台。
 */
const isG6SppiSyncManagedSheet = computed(() =>
  isGSharedWorkbookManagedSheet(G6_SPPI_HOST_ENTRY_ID, currentSheet.value),
)
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const syncEntryId = ref(G6_BRIDGE_ENTRY_ID)
const syncSheetKey = computed(
  () =>
    gSharedWorkbookSheetOf(G6_SPPI_HOST_ENTRY_ID, currentSheet.value)?.sheetKey ?? 'g605-managed',
)
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(G6_BRIDGE_ENTRY_ID),
  flushHtml: async () => {
    formData.flushPending()
    return await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: G6_BRIDGE_ENTRY_ID,
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
  isManagedSheet: isG6SppiSyncManagedSheet,
  editorHostRef: syncEditorHostRef,
})

const isOoMode = computed(
  () => isHtmlSheet.value && currentSheet.value !== '底稿目录' && renderMode.value === 'onlyoffice',
)

onMounted(async () => {
  window.addEventListener('g6:save-items', handleG6SaveItems)
  await selfLoad()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g6:save-items', handleG6SaveItems)
})
</script>

<style scoped>
.g6-other-bond-investment-sppi { padding: 12px; }
.loading-container { padding: 24px; }
.error-container { padding: 24px; }
.g6-other-bond-investment-sppi-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }

/* ─── 同步编辑器容器 ─── */
/* 🔴 必须带**视口相关的确定高度**：`WorkpaperSyncEditorHost` 根元素是 height:100% + flex 列，
   父级 auto 高度会把编辑区（flex:1; min-height:0）压扁，OnlyOffice 在页面上只剩一条
   （2026-09-22 D4 真栈实证）。模板里用了 `.oo-container` 却不定义它就是这个后果。 */
.oo-container { min-height: 600px; height: calc(100vh - 280px); overflow: hidden; border-radius: 8px; }
.oo-loading { padding: 40px 20px; text-align: center; color: #909399; font-size: 14px; }
</style>
