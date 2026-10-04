<template>
  <div class="g13-fair-value-changes">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="currentSheet !== '底稿目录'" class="g13-fair-value-changes-toolbar">
        <!--
          🔴 原先是 `:model-value="dualMode.currentMode.value"` + `@change="dualMode.onModeChange"`
          （legacy 本地 ref）⇒ 桥的 mode 永远不动、descriptor 恒 null，受管 sheet 切「在线编辑」
          后永远停在「正在打开…」。现在统一走 `switchRenderMode`（受管经桥、非受管委派 legacy）。
          顺带修掉 `:options="dualMode.modeOptions"` 漏 `.value` —— 那会把 ComputedRef 对象当
          数组传给 el-segmented，选项渲染不出来（G3 写的是 `.value`，本文件漏了）。
        -->
        <el-segmented
          v-if="isHtmlSheet"
          :model-value="renderMode"
          :options="syncModeOptions"
          size="small"
          @change="switchRenderMode"
        />
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g13-fair-value-changes" />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value && !isG13SyncManagedSheet" size="small" type="warning">OO不可用</el-tag>
        <el-tag v-if="isG13SyncManagedSheet && syncBusy" size="small" type="info">同步中…</el-tag>
        <el-tag v-if="syncSwitching" size="small" type="info">切换中…</el-tag>
      </div>

      <!-- G13-2 明细表受管 sheet 走 WorkpaperSyncEditorHost 真双向 -->
      <div v-if="isOoMode && isG13SyncManagedSheet" class="oo-container">
        <WorkpaperSyncEditorHost
          v-if="syncOoDescriptor"
          ref="syncEditorHostRef"
          :descriptor="syncOoDescriptor"
          :bridge="syncBridge"
        />
        <div v-else class="oo-loading">正在打开 G13-2 同步编辑器…</div>
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

      <G13TabProcedure
        v-else-if="currentSheet === 'G13A'"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G13TabAdjudication
        :html-data="props.htmlData"
        v-else-if="currentSheet === 'G13-1'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G13TabDetail
        v-else-if="currentSheet === 'G13-2'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G13TabAdjustment
        v-else-if="currentSheet === 'G13-3'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G13TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <G13TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <div v-else-if="currentSheet === '底稿目录'" class="g-cycle-tab-index-page">
        <G13TabDirectory
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
      </div>

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

      <!-- 版本链/复核 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted, onBeforeUnmount, defineAsyncComponent, provide, inject } from 'vue'
import { useG13FormData } from './composables/useG13FormData'
import { useG13DualMode } from './composables/useG13DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import type { ChecklistResponse } from './composables/useF1FormData'
import { useHostApplicableStandards } from './composables/hostApplicableStandards'
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
// ── G13 sync bridge（spec: g-cycle-single-region-detail-lanes · Task 15）──
import { isGSingleRegionManagedSheet, gSingleRegionSheetKeyOf } from './sync/gSingleRegionManagedSheets'
import { useGRenderModeSwitch } from './sync/useGRenderModeSwitch'
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'

const G13TabProcedure = defineAsyncComponent(() => import('./g13-fair-value-changes/G13TabProcedure.vue'))
const G13TabAdjudication = defineAsyncComponent(() => import('./g13-fair-value-changes/G13TabAdjudication.vue'))
const G13TabDetail = defineAsyncComponent(() => import('./g13-fair-value-changes/G13TabDetail.vue'))
const G13TabAdjustment = defineAsyncComponent(() => import('./g13-fair-value-changes/G13TabAdjustment.vue'))
const G13TabDisclosureListed = defineAsyncComponent(() => import('./g13-fair-value-changes/G13TabDisclosureListed.vue'))
const G13TabDisclosureSOE = defineAsyncComponent(() => import('./g13-fair-value-changes/G13TabDisclosureSOE.vue'))
const G13TabDirectory = defineAsyncComponent(() => import('./g13-fair-value-changes/G13TabDirectory.vue'))
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
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  (e: 'jump-to-section', sheetName: string): void
}>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const formData = useG13FormData({ wpId: wpIdRef, projectId: projectIdRef })
const isReadonly = computed(() => !!props.readonly)

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)

// 适用准则：显式 prop > 本 sheet html_data > runtime context（scaffold 从 render-config
// 顶层注入）。收敛到共享 composable，兼容 v2 对象 / 逗号串 / JSON 串。
const applicableStandards = useHostApplicableStandards({
  explicit: () => props.applicableStandards,
  htmlData: () => props.htmlData,
})
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('g13VersionTrailRef', versionTrailRef)
provide('g13OpenVersionHistory', openVersionHistory)

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/底稿目录/.test(name)) return '底稿目录'
  if (/附注披露/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(G13A|G13-\d+)/)
  return m ? m[1] : ''
})

const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return ['G13A', 'G13-1', 'G13-2', 'G13-3', '底稿目录'].includes(s) || s.startsWith('附注')
})

const dualMode = useG13DualMode({
  wpId: wpIdRef,
  reloadAll: () => formData.loadAll(),
})

const useGridFallback = computed(() => {
  const code = currentSheet.value
  return !!code && !isHtmlSheet.value
})

function onDebouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
  formData.debouncedSave(itemId, data)
  scheduleAutoSnapshot()
}

// spec: tb-writeback-explicit-publish-gate Task 12：移除 g13:writeback-trial-balance
// 监听器 handleG13Writeback —— TB 回写改由 G13-1 审定表「发布到试算表」显式确认门
// （useG13Adjudication.publishToTb → POST publish-to-tb，科目6101发生额口径）承载。

async function reloadAll() {
  await formData.loadAll()
}

const availableSheets = computed(() => {
  const fromHtml = props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml
  const metaSheets = formData.renderMeta.value?.sheets
  if (Array.isArray(metaSheets) && metaSheets.length) return metaSheets
  // 对齐 G1：无 sheets 元数据时用自加载 render-config 的 sheetCache 兜底，
  // 保证底稿目录架构树非空
  return Object.keys(formData.sheetCache.value).map(sheet_name => ({ sheet_name }))
})

// 复核对话 provider 由 Runtime Boundary(GtWpRenderer) 统一提供 openReviewDialog
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: reloadAll,
})

// ── G13 sync bridge 接线（Task 15 · Requirements 4.7）───────────────────────
const G13_SYNC_ENTRY_ID = 'xlsx/gt-g13-fair-value-changes'
const isG13SyncManagedSheet = computed(() => isGSingleRegionManagedSheet(currentSheet.value))
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const syncEntryId = ref(G13_SYNC_ENTRY_ID)
const syncSheetKey = computed(() => gSingleRegionSheetKeyOf(currentSheet.value) ?? 'g1302-managed')
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(G13_SYNC_ENTRY_ID),
  flushHtml: async () => {
    formData.flushPending()
    return await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: G13_SYNC_ENTRY_ID,
    })
  },
  reloadHtml: () => formData.loadAll(),
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncBusy = computed(() => WP_BRIDGE_IN_FLIGHT_STATES.includes(syncBridge.state.value))

// 🔴 受管 sheet 必须经桥切换 —— 桥建好了但没人调 `switchToOnlyOffice()` 就是空壳
//    （`WorkpaperSyncEditorHost` 自己不 materialize，descriptor 只能由那个方法产出）。
const {
  renderMode,
  modeOptions: syncModeOptions,
  switching: syncSwitching,
  switchRenderMode,
} = useGRenderModeSwitch({
  bridge: syncBridge,
  legacy: dualMode,
  isManagedSheet: isG13SyncManagedSheet,
  editorHostRef: syncEditorHostRef,
})

const isOoMode = computed(
  () => isHtmlSheet.value && currentSheet.value !== '底稿目录' && renderMode.value === 'onlyoffice',
)

onMounted(async () => {

  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {

  formData.flushPending()
})
</script>

<style scoped>
.g13-fair-value-changes { padding: 12px; }
.g-cycle-tab-index-page { padding: 0; }
.loading-container { padding: 24px; }
.g13-fair-value-changes-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }

/* ─── 同步编辑器容器 ─── */
/* 🔴 必须带**视口相关的确定高度**：`WorkpaperSyncEditorHost` 根元素是 height:100% + flex 列，
   父级 auto 高度会把编辑区（flex:1; min-height:0）压扁，OnlyOffice 在页面上只剩一条
   （2026-09-22 D4 真栈实证）。模板里用了 `.oo-container` 却不定义它就是这个后果。 */
.oo-container { min-height: 600px; height: calc(100vh - 280px); overflow: hidden; border-radius: 8px; }
.oo-loading { padding: 40px 20px; text-align: center; color: #909399; font-size: 14px; }
</style>
