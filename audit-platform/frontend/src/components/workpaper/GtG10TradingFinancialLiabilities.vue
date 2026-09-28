<template>
  <div class="g10-trading-financial-liabilities">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="currentSheet !== '底稿目录'" class="g10-trading-financial-liabilities-toolbar">
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
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g10-trading-financial-liabilities" />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value && !isG10SyncManagedSheet" size="small" type="warning">OO不可用</el-tag>
        <el-tag v-if="isG10SyncManagedSheet && syncBusy" size="small" type="info">同步中…</el-tag>
        <el-tag v-if="syncSwitching" size="small" type="info">切换中…</el-tag>
      </div>

      <!-- G10-2 明细表受管 sheet 走 WorkpaperSyncEditorHost 真双向 -->
      <div v-if="isOoMode && isG10SyncManagedSheet" class="oo-container">
        <WorkpaperSyncEditorHost
          v-if="syncOoDescriptor"
          ref="syncEditorHostRef"
          :descriptor="syncOoDescriptor"
          :bridge="syncBridge"
        />
        <div v-else class="oo-loading">正在打开 G10-2 同步编辑器…</div>
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

      <G10TabProcedure
        v-else-if="currentSheet === 'G10A'"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G10TabAdjudication
        :html-data="props.htmlData"
        v-else-if="currentSheet === 'G10-1'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabDetail
        v-else-if="currentSheet === 'G10-2'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabAdjustment
        v-else-if="currentSheet === 'G10-3'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear ?? undefined"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabClassificationCheck
        v-else-if="currentSheet === 'G10-4'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabFairValueTest
        v-else-if="currentSheet === 'G10-5'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabL3Reconciliation
        v-else-if="currentSheet === 'G10-6'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabVoucherCheck
        v-else-if="currentSheet === 'G10-7'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabDerivativeCheck
        v-else-if="currentSheet === 'G10-8'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <G10TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <div v-else-if="currentSheet === '底稿目录'" class="g-cycle-tab-index-page">
        <G10TabDirectory
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
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG10TradingFinancialLiabilities — G10 交易性金融负债底稿主入口
 * 对齐 G8：formData + g10:save-items + 附注路由 + 双模式 reload
 */
import { ref, computed, toRef, onMounted, onBeforeUnmount, defineAsyncComponent, provide, inject } from 'vue'
import { useG10FormData } from './composables/useG10FormData'
import { offerG10DisclosurePull, G10_OFFER_DISCLOSURE_PULL_EVENT } from './composables/g10DisclosureSync'
import { useG10DualMode } from './composables/useG10DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import type { ChecklistResponse } from './composables/useF1FormData'
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
// ── G10 sync bridge（spec: g-cycle-single-region-detail-lanes · Task 15）──
import { isGSingleRegionManagedSheet, gSingleRegionSheetKeyOf } from './sync/gSingleRegionManagedSheets'
import { useGRenderModeSwitch } from './sync/useGRenderModeSwitch'
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'

const G10TabProcedure = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabProcedure.vue'))
const G10TabAdjudication = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabAdjudication.vue'))
const G10TabDetail = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabDetail.vue'))
const G10TabAdjustment = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabAdjustment.vue'))
const G10TabClassificationCheck = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/classification/G10TabClassificationCheck.vue'))
const G10TabFairValueTest = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/classification/G10TabFairValueTest.vue'))
const G10TabL3Reconciliation = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/classification/G10TabL3Reconciliation.vue'))
const G10TabVoucherCheck = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/voucher/G10TabVoucherCheck.vue'))
const G10TabDerivativeCheck = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/voucher/G10TabDerivativeCheck.vue'))
const G10TabDisclosureListed = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabDisclosureListed.vue'))
const G10TabDisclosureSOE = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabDisclosureSOE.vue'))
const G10TabDirectory = defineAsyncComponent(() => import('./g10-trading-financial-liabilities/core/G10TabDirectory.vue'))
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

const emit = defineEmits<{
  (e: 'jump-to-section', sheetName: string): void
}>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const formData = useG10FormData({ wpId: wpIdRef, projectId: projectIdRef })
const isReadonly = computed(() => !!props.readonly)

const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('g10VersionTrailRef', versionTrailRef)
provide('g10OpenVersionHistory', openVersionHistory)

/** 审计年度：供 G10-3 与中央调整分录模块同步 */
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

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/G10-note-listed|附注披露.*上市|附注.*上市/.test(name)) return '附注上市'
  if (/G10-note-soe|附注披露.*国企|附注.*国企/.test(name)) return '附注国企'
  if (/G10-directory|底稿目录/.test(name)) return '底稿目录'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(G10A|G10-\d+)/)
  return m ? m[1] : ''
})

const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return ['G10A', 'G10-1', 'G10-2', 'G10-3', 'G10-4', 'G10-5', 'G10-6', 'G10-7', 'G10-8', '底稿目录'].includes(s)
    || s.startsWith('附注')
})

const dualMode = useG10DualMode({
  wpId: wpIdRef,
  reloadAll: () => formData.loadAll(),
})

const useGridFallback = computed(() => {
  const code = currentSheet.value
  if (!code) return false
  const htmlSheets = ['G10A', 'G10-1', 'G10-2', 'G10-3', 'G10-4', 'G10-5', 'G10-6', 'G10-7', 'G10-8', '底稿目录']
  if (htmlSheets.includes(code) || code.startsWith('附注')) return false
  return isHtmlSheet.value && dualMode.currentMode.value === 'html'
})

function onDebouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
  formData.debouncedSave(itemId, data)
  scheduleAutoSnapshot()
}

async function handleG10SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    for (const it of items) {
      if (it?.item_id) await formData.saveImmediate(it.item_id, it)
    }
    scheduleAutoSnapshot()
  }
}

function handleG10OfferDisclosurePull(): void {
  void offerG10DisclosurePull(
    formData.allResponses.value,
    formData.debouncedSave,
    auditYear.value,
  )
}

async function reloadAll() {
  await formData.loadAll()
}

// spec: tb-writeback-explicit-publish-gate Task 12：移除 g10:writeback-trial-balance
// 监听器 handleG10Writeback —— TB 回写改由 G10-1 审定表「发布到试算表」显式确认门
// （useG10Adjudication.publishToTb → POST publish-to-tb）承载。保留 g10:save-items 等其他事件。

const availableSheets = computed(() => {
  const fromHtml = props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml
  const metaSheets = formData.renderMeta.value?.sheets
  if (Array.isArray(metaSheets) && metaSheets.length) return metaSheets
  // 对齐 G1：无 sheets 元数据时用自加载 render-config 的 sheetCache 兜底，
  // 保证底稿目录架构树非空
  return Object.keys(formData.sheetCache.value).map(sheet_name => ({ sheet_name }))
})

const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: reloadAll,
})

// ── G10 sync bridge 接线（Task 15 · Requirements 4.7）───────────────────────
const G10_SYNC_ENTRY_ID = 'xlsx/gt-g10-trading-financial-liabilities'
const isG10SyncManagedSheet = computed(() => isGSingleRegionManagedSheet(currentSheet.value))
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const syncEntryId = ref(G10_SYNC_ENTRY_ID)
const syncSheetKey = computed(() => gSingleRegionSheetKeyOf(currentSheet.value) ?? 'g1002-managed')
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(G10_SYNC_ENTRY_ID),
  flushHtml: async () => {
    formData.flushPending()
    return await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: G10_SYNC_ENTRY_ID,
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
  isManagedSheet: isG10SyncManagedSheet,
  editorHostRef: syncEditorHostRef,
})

const isOoMode = computed(
  () => isHtmlSheet.value && currentSheet.value !== '底稿目录' && renderMode.value === 'onlyoffice',
)

onMounted(async () => {
  window.addEventListener('g10:save-items', handleG10SaveItems)
  window.addEventListener(G10_OFFER_DISCLOSURE_PULL_EVENT, handleG10OfferDisclosurePull)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g10:save-items', handleG10SaveItems)
  window.removeEventListener(G10_OFFER_DISCLOSURE_PULL_EVENT, handleG10OfferDisclosurePull)
  formData.flushPending()
})
</script>

<style scoped>
.g10-trading-financial-liabilities { padding: 12px; }
.loading-container { padding: 24px; }
.g10-trading-financial-liabilities-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }

/* ─── 同步编辑器容器 ─── */
/* 🔴 必须带**视口相关的确定高度**：`WorkpaperSyncEditorHost` 根元素是 height:100% + flex 列，
   父级 auto 高度会把编辑区（flex:1; min-height:0）压扁，OnlyOffice 在页面上只剩一条
   （2026-09-22 D4 真栈实证）。模板里用了 `.oo-container` 却不定义它就是这个后果。 */
.oo-container { min-height: 600px; height: calc(100vh - 280px); overflow: hidden; border-radius: 8px; }
.oo-loading { padding: 40px 20px; text-align: center; color: #909399; font-size: 14px; }
</style>
