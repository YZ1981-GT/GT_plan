<template>
  <div class="g8-other-equity-instruments">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="currentSheet !== '底稿目录'" class="g8-toolbar">
        <!--
          🔴 原先绑 legacy `dualMode.currentMode` / `dualMode.onModeChange`（本地 ref）⇒ 桥的
          mode 永远不动、descriptor 恒 null，受管 sheet 切「在线编辑」后永远停在「正在打开…」。
          现在统一走 `switchRenderMode`：受管 sheet 经桥（四分支保存协议），非受管委派 legacy。
        -->
        <el-segmented
          v-if="isHtmlSheet"
          :model-value="renderMode"
          :options="syncModeOptions"
          size="small"
          @change="switchRenderMode"
        />
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g8-other-equity-instruments" />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value && !isG8SyncManagedSheet" size="small" type="warning">OO不可用</el-tag>
        <el-tag v-if="isG8SyncManagedSheet && syncBusy" size="small" type="info">同步中…</el-tag>
        <el-tag v-if="syncSwitching" size="small" type="info">切换中…</el-tag>
      </div>

      <!-- G8-2 明细表受管 sheet 走 WorkpaperSyncEditorHost 真双向 -->
      <div v-if="isOoMode && isG8SyncManagedSheet" class="oo-container">
        <WorkpaperSyncEditorHost
          v-if="syncOoDescriptor"
          ref="syncEditorHostRef"
          :descriptor="syncOoDescriptor"
          :bridge="syncBridge"
        />
        <div v-else class="oo-loading">正在打开 G8-2 同步编辑器…</div>
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

      <G8TabProcedure
        v-else-if="currentSheet === 'G8A'"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G8TabAdjudication
        :html-data="props.htmlData"
        v-else-if="currentSheet === 'G8-1'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G8TabDetail
        v-else-if="currentSheet === 'G8-2'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G8TabAdjustment
        v-else-if="currentSheet === 'G8-3'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G8TabFairValueTest
        v-else-if="currentSheet === 'G8-4'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G8TabDesignationCheck
        v-else-if="currentSheet === 'G8-5'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G8TabVoucherCheck
        v-else-if="currentSheet === 'G8-6'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :year="auditYear ?? undefined"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G8TabDisclosureBase
        v-else-if="currentSheet === '附注上市'"
        variant="listed"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G8TabDisclosureBase
        v-else-if="currentSheet === '附注国企'"
        variant="soe"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G8TabRefValuationGuidance
        v-else-if="currentSheet === '参考中证协'"
        :html-data="props.htmlData || formData.getSheet(currentSheet)"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="true"
      />

      <template v-else-if="currentSheet === '底稿目录'">
        <div class="g8-index-toolbar">
          <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        </div>
        <G8TabDirectory
          :all-responses="formData.allResponses.value"
          :available-sheets="availableSheets"
        />
        <GCycleBIndexExtras
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName"
          :wp-code="props.wpCode"
          :html-data="props.htmlData"
          :available-sheets="availableSheets"
          :all-responses="formData.allResponses.value"
        />
      </template>

      <GtGridSheet
        v-else-if="useGridFallback"
        :html-data="props.htmlData || formData.getSheet(currentSheet)"
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
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG8OtherEquityInstruments — G8 其他权益工具投资底稿主入口
 * 对齐 G5/G6：formData + g8:save-items + 附注路由 + 双模式 reload
 */
import { ref, computed, toRef, onMounted, onBeforeUnmount, defineAsyncComponent, provide, inject } from 'vue'
import { useG8FormData } from './composables/useG8FormData'
import { useG8DualMode } from './composables/useG8DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { extractG8SheetCode } from './composables/g8SheetLabels'
import type { ChecklistResponse } from './composables/useF1FormData'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useHostApplicableStandards } from './composables/hostApplicableStandards'
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
// ── G8 sync bridge（spec: g-cycle-single-region-detail-lanes · Task 15）──
import { isGSingleRegionManagedSheet, gSingleRegionSheetKeyOf } from './sync/gSingleRegionManagedSheets'
import { useGRenderModeSwitch } from './sync/useGRenderModeSwitch'
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'

const G8TabProcedure = defineAsyncComponent(() => import('./g8-other-equity-instruments/core/G8TabProcedure.vue'))
const G8TabAdjudication = defineAsyncComponent(() => import('./g8-other-equity-instruments/core/G8TabAdjudication.vue'))
const G8TabDetail = defineAsyncComponent(() => import('./g8-other-equity-instruments/core/G8TabDetail.vue'))
const G8TabAdjustment = defineAsyncComponent(() => import('./g8-other-equity-instruments/core/G8TabAdjustment.vue'))
const G8TabFairValueTest = defineAsyncComponent(() => import('./g8-other-equity-instruments/valuation/G8TabFairValueTest.vue'))
const G8TabDesignationCheck = defineAsyncComponent(() => import('./g8-other-equity-instruments/valuation/G8TabDesignationCheck.vue'))
const G8TabVoucherCheck = defineAsyncComponent(() => import('./g8-other-equity-instruments/voucher/G8TabVoucherCheck.vue'))
const G8TabDisclosureBase = defineAsyncComponent(() => import('./g8-other-equity-instruments/core/G8TabDisclosureBase.vue'))
const G8TabDirectory = defineAsyncComponent(() => import('./g8-other-equity-instruments/core/G8TabDirectory.vue'))
const G8TabRefValuationGuidance = defineAsyncComponent(() => import('./g8-other-equity-instruments/reference/G8TabRefValuationGuidance.vue'))
const GCycleBIndexExtras = defineAsyncComponent(() => import('./shared/GCycleBIndexExtras.vue'))
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

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const formData = useG8FormData({ wpId: wpIdRef, projectId: computed(() => props.projectId) })
const isReadonly = computed(() => !!props.readonly)

const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

/** 审计年度：抽凭引擎 / A13 错报 / G8A 回填；优先 htmlData，回退 Runtime */
const auditYear = computed(() => {
  const raw =
    props.htmlData?.project_context?.audit_year
    ?? props.htmlData?.projectContext?.audit_year
    ?? props.htmlData?.audit_year
    ?? runtime?.year?.value
    ?? null
  if (raw == null || raw === '') return null
  const n = Number(raw)
  return Number.isFinite(n) && n >= 1900 ? Math.trunc(n) : null
})

provide('g8VersionTrailRef', versionTrailRef)
provide('g8OpenVersionHistory', openVersionHistory)
provide('reloadWorkpaperData', () => formData.loadAll())

const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

const currentSheet = computed(() => extractG8SheetCode(props.sheetName || props.wpCode || ''))

// 适用准则：显式 prop > 本 sheet html_data > runtime context（scaffold 从 render-config
// 顶层注入）。收敛到共享 composable，兼容 v2 对象 / 逗号串 / JSON 串。
const applicableStandards = useHostApplicableStandards({
  htmlData: () => props.htmlData,
})

const HTML_SHEETS = new Set(['G8A', 'G8-1', 'G8-2', 'G8-3', 'G8-4', 'G8-5', 'G8-6', '附注上市', '附注国企', '底稿目录', '参考中证协'])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))
const useGridFallback = computed(() => !!currentSheet.value && !isHtmlSheet.value)

const availableSheets = computed(() => {
  const fromHtml = props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml
  const metaSheets = formData.renderMeta.value?.sheets
  if (Array.isArray(metaSheets) && metaSheets.length) return metaSheets
  // 对齐 G1：无 sheets 元数据时用自加载 render-config 的 sheetCache 兜底，
  // 保证底稿目录架构树非空
  return Object.keys(formData.sheetCache.value).map(sheet_name => ({ sheet_name }))
})

const dualMode = useG8DualMode({ wpId: wpIdRef, reloadAll: () => formData.loadAll() })

function onDebouncedSave(id: string, d: Partial<ChecklistResponse>) {
  formData.debouncedSave(id, d)
  scheduleAutoSnapshot()
}

async function handleG8SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    for (const it of items) {
      if (it?.item_id) await formData.saveImmediate(it.item_id, it)
    }
    scheduleAutoSnapshot()
  }
}

// spec: tb-writeback-explicit-publish-gate Task 12：移除 g8:writeback-trial-balance
// 监听器 handleG8Writeback —— TB 回写改由 G8-1 审定表「发布到试算表」显式确认门
// （useG8Adjudication.publishToTb → POST publish-to-tb）承载。保留 g8:save-items。

async function reloadAll() {
  await formData.loadAll()
}

// ── G8 sync bridge 接线（Task 15 · Requirements 4.7）───────────────────────
const G8_SYNC_ENTRY_ID = 'xlsx/gt-g8-other-equity-instruments'
const isG8SyncManagedSheet = computed(() => isGSingleRegionManagedSheet(currentSheet.value))
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const syncEntryId = ref(G8_SYNC_ENTRY_ID)
const syncSheetKey = computed(() => gSingleRegionSheetKeyOf(currentSheet.value) ?? 'g802-managed')
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(G8_SYNC_ENTRY_ID),
  flushHtml: async () => {
    formData.flushPending()
    return await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: G8_SYNC_ENTRY_ID,
    })
  },
  reloadHtml: () => formData.loadAll(),
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncBusy = computed(() => WP_BRIDGE_IN_FLIGHT_STATES.includes(syncBridge.state.value))

// 🔴 受管 sheet 必须经桥切换 —— 桥建好了但没人调 `switchToOnlyOffice()` 就是空壳：
//    `WorkpaperSyncEditorHost` 自己不 materialize，descriptor 只能由那个方法产出，
//    于是用户切「在线编辑」后永远停在「正在打开…」，而所有静态门都是绿的。
const {
  renderMode,
  modeOptions: syncModeOptions,
  switching: syncSwitching,
  switchRenderMode,
} = useGRenderModeSwitch({
  bridge: syncBridge,
  legacy: dualMode,
  isManagedSheet: isG8SyncManagedSheet,
  editorHostRef: syncEditorHostRef,
})

const isOoMode = computed(
  () => isHtmlSheet.value && currentSheet.value !== '底稿目录' && renderMode.value === 'onlyoffice',
)

onMounted(async () => {
  window.addEventListener('g8:save-items', handleG8SaveItems)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g8:save-items', handleG8SaveItems)
  formData.flushPending()
})
</script>

<style scoped>
.g8-other-equity-instruments { padding: 12px; }
.loading-container { padding: 24px; }
.g8-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.g8-index-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }

/* ─── 同步编辑器容器 ─── */
/* 🔴 必须带**视口相关的确定高度**：`WorkpaperSyncEditorHost` 根元素是 height:100% + flex 列，
   父级 auto 高度会把编辑区（flex:1; min-height:0）压扁，OnlyOffice 在页面上只剩一条
   （2026-09-22 D4 真栈实证）。模板里用了 `.oo-container` 却不定义它就是这个后果。 */
.oo-container { min-height: 600px; height: calc(100vh - 280px); overflow: hidden; border-radius: 8px; }
.oo-loading { padding: 40px 20px; text-align: center; color: #909399; font-size: 14px; }
</style>
