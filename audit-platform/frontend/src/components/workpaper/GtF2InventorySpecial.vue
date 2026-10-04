<template>
  <div class="f2-inventory-special">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="showHtmlToolbar" class="f2-spe-toolbar">
        <el-segmented v-model="renderMode" :options="dualMode.modeOptions" size="small" :disabled="isF2SSyncManagedSheet && syncBusy"
        />
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
        <el-tag v-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
        <el-tag v-if="isIpoSheet && !formData.isIpoProject.value" size="small" type="info">IPO专项（当前项目不可见）</el-tag>
        <el-tag v-if="isF2SSyncManagedSheet && syncBusy" size="small" type="info">同步中…</el-tag>
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-f2-inventory-special" />
      </div>

      <el-alert
        v-if="externalAdjudicated.dataUpdatedVisible.value"
        title="关联审定数据已更新（科目 1405）"
        type="info"
        show-icon
        :closable="false"
        class="data-updated-bar"
      />

      <div v-if="renderMode === 'onlyoffice' && isF2SSyncManagedSheet" class="oo-container">
        <WorkpaperSyncEditorHost ref="syncEditorHostRef" :descriptor="syncOoDescriptor" :bridge="syncBridge" />
      </div>
      <GtOnlyOfficeSheet
        v-else-if="renderMode === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <template v-else-if="showIpoBlocked">
        <el-empty description="此底稿仅适用于 IPO/上市/新三板/重组项目" />
      </template>

      <template v-else>
        <F2ContractCostTestExample
          v-if="isContractCostExampleSheet"
        />

        <F2InterviewCheckExample
          v-else-if="isInterviewExampleSheet"
        />

        <F2TabContractProcedure
          v-else-if="currentSheet === 'F2-55A'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <F2TabIpoProcedure
          v-else-if="currentSheet === 'F2-61A'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <F2TabContractCostDetail
          v-else-if="currentSheet === 'F2-55'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabContractCostCheck
          v-else-if="currentSheet === 'F2-56'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :audit-year="auditYear"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabImpairment
          v-else-if="currentSheet === 'F2-57'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabLossContract
          v-else-if="currentSheet === 'F2-58'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabPurchasePrice
          v-else-if="currentSheet === 'F2-61'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabUnitPrice
          v-else-if="currentSheet === 'F2-62'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabCapacityEnergy
          v-else-if="currentSheet === 'F2-63'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabUnitConsumption
          v-else-if="currentSheet === 'F2-64'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabRelatedPartyInquiry
          v-else-if="currentSheet === 'F2-65'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabRelatedPartyMarket
          v-else-if="currentSheet === 'F2-66'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabUndisclosedParty
          v-else-if="currentSheet === 'F2-67'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabSupplierStructure
          v-else-if="currentSheet === 'F2-68'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabSupplierChecklist
          v-else-if="currentSheet === 'F2-69'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabInterviewSummary
          v-else-if="currentSheet === 'F2-71'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabSupplierInfoCheck
          v-else-if="currentSheet === 'F2-70'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabInterviewDetail
          v-else-if="currentSheet === 'F2-72'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

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

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, provide, toRef, inject, defineAsyncComponent } from 'vue'
import { useF2SpecialFormData, type ChecklistResponse } from './composables/useF2SpecialFormData'
import { useF2SpecialDualMode } from './composables/useF2SpecialDualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useF2SpeExternalAdjudicated } from './composables/useF2SpeExternalAdjudicated'
import { isContractCostTestExampleSheet } from './f2-special/contract/f2ContractCostTestExampleData'
import { isInterviewCheckExampleSheet } from './f2-special/ipo/f2InterviewCheckExampleData'

// defineAsyncComponent lazy loading — 首屏仅加载当前 sheet 组件（对齐D4标准）
const F2TabContractProcedure = defineAsyncComponent(() => import('./f2-special/contract/F2TabContractProcedure.vue'))
const F2TabContractCostDetail = defineAsyncComponent(() => import('./f2-special/contract/F2TabContractCostDetail.vue'))
const F2TabContractCostCheck = defineAsyncComponent(() => import('./f2-special/contract/F2TabContractCostCheck.vue'))
const F2TabImpairment = defineAsyncComponent(() => import('./f2-special/contract/F2TabImpairment.vue'))
const F2TabLossContract = defineAsyncComponent(() => import('./f2-special/contract/F2TabLossContract.vue'))
const F2TabIpoProcedure = defineAsyncComponent(() => import('./f2-special/ipo/F2TabIpoProcedure.vue'))
const F2TabPurchasePrice = defineAsyncComponent(() => import('./f2-special/ipo/F2TabPurchasePrice.vue'))
const F2TabUnitPrice = defineAsyncComponent(() => import('./f2-special/ipo/F2TabUnitPrice.vue'))
const F2TabCapacityEnergy = defineAsyncComponent(() => import('./f2-special/ipo/F2TabCapacityEnergy.vue'))
const F2TabUnitConsumption = defineAsyncComponent(() => import('./f2-special/ipo/F2TabUnitConsumption.vue'))
const F2TabRelatedPartyInquiry = defineAsyncComponent(() => import('./f2-special/ipo/F2TabRelatedPartyInquiry.vue'))
const F2TabRelatedPartyMarket = defineAsyncComponent(() => import('./f2-special/ipo/F2TabRelatedPartyMarket.vue'))
const F2TabUndisclosedParty = defineAsyncComponent(() => import('./f2-special/ipo/F2TabUndisclosedParty.vue'))
const F2TabSupplierStructure = defineAsyncComponent(() => import('./f2-special/ipo/F2TabSupplierStructure.vue'))
const F2TabSupplierChecklist = defineAsyncComponent(() => import('./f2-special/ipo/F2TabSupplierChecklist.vue'))
const F2TabInterviewSummary = defineAsyncComponent(() => import('./f2-special/ipo/F2TabInterviewSummary.vue'))
const F2TabSupplierInfoCheck = defineAsyncComponent(() => import('./f2-special/ipo/F2TabSupplierInfoCheck.vue'))
const F2TabInterviewDetail = defineAsyncComponent(() => import('./f2-special/ipo/F2TabInterviewDetail.vue'))
const F2ContractCostTestExample = defineAsyncComponent(
  () => import('./f2-special/contract/F2ContractCostTestExample.vue'),
)
const F2InterviewCheckExample = defineAsyncComponent(
  () => import('./f2-special/ipo/F2InterviewCheckExample.vue'),
)

const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
}>()

const CONTRACT_HTML = ['F2-55A', 'F2-55', 'F2-56', 'F2-57', 'F2-58']
const IPO_HTML = [
  'F2-61A',
  'F2-61', 'F2-62', 'F2-63', 'F2-64', 'F2-65', 'F2-66', 'F2-67', 'F2-68', 'F2-69', 'F2-71',
  'F2-70', 'F2-72',
]

const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

const formData = useF2SpecialFormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const allResponses = computed(() => formData.allResponses.value)

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionToolbar = runtime?.version ?? {
  versionTrailRef: ref<{ openDrawer: () => void } | null>(null),
  openVersionHistory: () => undefined,
  scheduleAutoSnapshot: () => undefined,
  wrapSaveImmediate: (<T,>(fn: T): T => fn),
}
const { versionTrailRef, openVersionHistory } = versionToolbar

provide('f2VersionTrailRef', versionTrailRef)
provide('f2OpenVersionHistory', openVersionHistory)

// ─── F2-57 canary：useWorkpaperSyncBridge 真双向 ──────────────────────────────
const F2S_SYNC_ENTRY_ID = 'xlsx/gt-f2-inventory-special'
const F2S_SHEET_KEY_BY_CODE: Record<string, string> = { 'F2-57': 'f257-managed' }
const isF2SSyncManagedSheet = computed(() => currentSheet.value in F2S_SHEET_KEY_BY_CODE)
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const syncEntryId = ref(F2S_SYNC_ENTRY_ID)
const syncSheetKey = computed(() => F2S_SHEET_KEY_BY_CODE[currentSheet.value] || 'f257-managed')
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey, capability: capabilityForEntry(F2S_SYNC_ENTRY_ID),
  flushHtml: async () => {
    formData.flushPendingSave()
    const snap = await readStoreProjection({ projectId: props.projectId, wpId: props.wpId, entryId: F2S_SYNC_ENTRY_ID })
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: syncSheetKey.value }
  },
  reloadHtml: async () => { await formData.loadAll() },
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncSwitching = ref(false)
const syncBusy = computed(() =>
  syncSwitching.value || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)
type F2SRenderMode = 'html' | 'onlyoffice'
const renderMode = computed({
  get: (): F2SRenderMode => isF2SSyncManagedSheet.value
    ? (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'html') : dualMode.currentMode.value,
  set: (v: F2SRenderMode) => { if (isF2SSyncManagedSheet.value) void switchRenderMode(v); else void dualMode.switchMode(v) },
})
async function switchRenderMode(target: F2SRenderMode): Promise<void> {
  if (target === renderMode.value) return
  if (target === 'onlyoffice') { if (!isF2SSyncManagedSheet.value) return; syncSwitching.value = true; try { await syncBridge.switchToOnlyOffice() } catch {} finally { syncSwitching.value = false }; return }
  if (syncBridge.mode.value !== 'oo') { syncBridge.persistMode('html'); return }
  syncSwitching.value = true
  try {
    if (String(syncBridge.state.value) === 'applied') await syncBridge.reloadAfterApplied()
    else if (syncBridge.mode.value === 'oo' && !syncBridge.dirty.value) await syncBridge.leaveWithoutSaving()
    else if (syncBridge.canForcesave.value && syncEditorHostRef.value) await syncEditorHostRef.value.forceSave()
    else syncBridge.persistMode('html')
  } catch {} finally { syncSwitching.value = false }
}

const dualMode = useF2SpecialDualMode({
  wpId: toRef(props, 'wpId'),
  reloadAll: () => formData.loadAll(),
})

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  const m = name.match(/(F2A|F2-\d+[A-Z]?)/)
  return m ? m[1] : ''
})

const isContractCostExampleSheet = computed(() =>
  isContractCostTestExampleSheet(props.sheetName),
)

const isInterviewExampleSheet = computed(() =>
  isInterviewCheckExampleSheet(props.sheetName),
)

const auditYear = computed(() => {
  const d = formData.projectContext.value?.audit_period_end
    || formData.projectContext.value?.bs_date || ''
  if (d.length >= 4) return parseInt(d.slice(0, 4), 10)
  return new Date().getFullYear() - 1
})

const isIpoSheet = computed(() => IPO_HTML.includes(currentSheet.value))

const showIpoBlocked = computed(() =>
  isIpoSheet.value && !formData.isIpoProject.value && dualMode.currentMode.value === 'html',
)

const isHtmlSheet = computed(() => {
  const c = currentSheet.value
  if (CONTRACT_HTML.includes(c)) return true
  if (IPO_HTML.includes(c) && formData.isIpoProject.value) return true
  return false
})

const showHtmlToolbar = computed(() => isHtmlSheet.value)

const useGridFallback = computed(() => {
  if (isContractCostExampleSheet.value || isInterviewExampleSheet.value) return false
  const code = currentSheet.value
  return code && !isHtmlSheet.value && !showIpoBlocked.value
})

// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide（真实复核对话）
const externalAdjudicated = useF2SpeExternalAdjudicated({
  onRefresh: () => formData.loadAll(),
})

provide('reloadWorkpaperData', () => formData.loadAll())

async function handleF2SpeSaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    await formData.saveItemsFromEvent(items)
    versionToolbar.scheduleAutoSnapshot()
  }
}

async function selfLoad(): Promise<void> {
  try {
    await formData.loadAll()
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  window.addEventListener('f2-spe:save-items', handleF2SpeSaveItems)
  void selfLoad()
})

onBeforeUnmount(() => {
  window.removeEventListener('f2-spe:save-items', handleF2SpeSaveItems)
})
</script>

<style scoped>
.f2-inventory-special { padding: 12px; }
.oo-container { min-height: 600px; height: calc(100vh - 200px); }
.loading-container { padding: 24px; }
.f2-spe-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.data-updated-bar { margin-bottom: 8px; }
</style>
