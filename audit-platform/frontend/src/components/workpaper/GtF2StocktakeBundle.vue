<template>
  <div class="f2-stocktake-bundle">
    <div v-if="isLoading" class="loading"><el-skeleton :rows="6" animated /></div>
    <template v-else>
      <div class="toolbar">
        <el-segmented v-model="renderMode" :options="dualMode.modeOptions" size="small" :disabled="syncBusy"
        />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-tag v-if="syncBusy" size="small" type="info">同步中…</el-tag>
        <el-tag v-else-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
        <el-tag
          v-else-if="dualMode.currentMode.value === 'onlyoffice' && !dualMode.supportsBidirectionalSync()"
          size="small"
          type="warning"
        >仅预览·无回写</el-tag>
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-f2-stocktake-bundle" />
      </div>

      <div v-if="renderMode === 'onlyoffice' && isF2TSyncManagedSheet" class="oo-container">
        <WorkpaperSyncEditorHost ref="syncEditorHostRef" :descriptor="syncOoDescriptor" :bridge="syncBridge" />
      </div>
      <GtOnlyOfficeSheet
        v-else-if="renderMode === 'onlyoffice'"
        :key="`oo-${activeTab}-${dualMode.ooRemountKey.value}`"
        :wp-id="props.wpId"
        :project-id="projectId"
        :sheet-name="props.sheetName || activeTab"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <template v-else-if="singleSheetMode">
        <component
          :is="tabComponent(activeTab)"
          :key="activeTab"
          :wp-id="props.wpId"
          :project-id="projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />
      </template>

      <el-tabs v-else v-model="activeTab" class="stocktake-tabs">
        <el-tab-pane label="监盘程序表" name="program" lazy>
          <F2TabStocktakeProcedure
            v-if="activeTab === 'program'"
            :wp-id="props.wpId"
            :project-id="projectId"
            :is-readonly="isReadonly"
          />
        </el-tab-pane>
        <el-tab-pane v-for="t in dataTabs" :key="t.id" :label="t.label" :name="t.id" lazy>
          <component
            :is="tabComponent(t.id)"
            v-if="activeTab === t.id"
            :wp-id="props.wpId"
            :project-id="projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </el-tab-pane>
      </el-tabs>
      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtF2StocktakeBundle — F2 存货监盘 HTML 入口 (F2-21A + F2-21~26)
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, provide, inject, toRef, defineAsyncComponent, type Component } from 'vue'
import { useRoute } from 'vue-router'
import { useF2StocktakeFormData, type ChecklistResponse } from './composables/useF2StocktakeFormData'
import { useF2StocktakeDualMode } from './composables/useF2StocktakeDualMode'
import { flushAllF2StocktakeFields } from './composables/useF2StocktakeSheet'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import F2TabStocktakeProcedure from './f2/stocktake/F2TabStocktakeProcedure.vue'
import F2TabStocktakeQuestionnaire from './f2/stocktake/F2TabStocktakeQuestionnaire.vue'
import F2TabStocktakePlan from './f2/stocktake/F2TabStocktakePlan.vue'
import F2TabStocktakeSummary from './f2/stocktake/F2TabStocktakeSummary.vue'
import F2TabStocktakeReconcile from './f2/stocktake/F2TabStocktakeReconcile.vue'
import F2TabStocktakeSampleResult from './f2/stocktake/F2TabStocktakeSampleResult.vue'
import F2TabStocktakeRollforward from './f2/stocktake/F2TabStocktakeRollforward.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'

const props = defineProps<{
  wpId: string
  projectId?: string
  wpCode?: string
  sheetName?: string
  readonly?: boolean
}>()

const route = useRoute()
const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)
const projectId = computed(() => props.projectId || (route.params.projectId as string) || '')

const formData = useF2StocktakeFormData({
  wpId: toRef(props, 'wpId'),
  projectId,
})

const allResponses = computed(() => formData.allResponses.value)

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  const m = name.match(/(F2-21A|F2-2[1-6])/)
  return m ? m[1] : 'F2-21A'
})

// ─── F2-25 canary：useWorkpaperSyncBridge 真双向 ──────────────────────────────
const F2T_SYNC_ENTRY_ID = 'xlsx/gt-f2-stocktake-bundle'
const F2T_SHEET_KEY_BY_CODE: Record<string, string> = { 'F2-25': 'f225-exist' }
const isF2TSyncManagedSheet = computed(() => currentSheet.value in F2T_SHEET_KEY_BY_CODE)
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const syncEntryId = ref(F2T_SYNC_ENTRY_ID)
const syncSheetKey = computed(() => F2T_SHEET_KEY_BY_CODE[currentSheet.value] || 'f225-exist')
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId, wpId: toRef(props, 'wpId'), projectId,
  sheetKey: syncSheetKey, capability: capabilityForEntry(F2T_SYNC_ENTRY_ID),
  flushHtml: async () => {
    formData.flushPendingSave()
    const snap = await readStoreProjection({ projectId: projectId.value, wpId: props.wpId, entryId: F2T_SYNC_ENTRY_ID })
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: syncSheetKey.value }
  },
  reloadHtml: async () => { await formData.loadAll() },
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncSwitching2 = ref(false)
const syncBusy = computed(() =>
  syncSwitching2.value || dualMode.syncing.value
  || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)
type F2TRenderMode = 'html' | 'onlyoffice'
const renderMode = computed({
  get: (): F2TRenderMode => isF2TSyncManagedSheet.value
    ? (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'html') : dualMode.currentMode.value,
  set: (v: F2TRenderMode) => { if (isF2TSyncManagedSheet.value) void switchRenderMode(v); else void dualMode.switchMode(v) },
})
async function switchRenderMode(target: F2TRenderMode): Promise<void> {
  if (target === renderMode.value) return
  if (target === 'onlyoffice') { if (!isF2TSyncManagedSheet.value) return; syncSwitching2.value = true; try { await syncBridge.switchToOnlyOffice() } catch {} finally { syncSwitching2.value = false }; return }
  if (syncBridge.mode.value !== 'oo') { syncBridge.persistMode('html'); return }
  syncSwitching2.value = true
  try {
    if (String(syncBridge.state.value) === 'applied') await syncBridge.reloadAfterApplied()
    else if (syncBridge.mode.value === 'oo' && !syncBridge.dirty.value) await syncBridge.leaveWithoutSaving()
    else if (syncBridge.canForcesave.value && syncEditorHostRef.value) await syncEditorHostRef.value.forceSave()
    else syncBridge.persistMode('html')
  } catch {} finally { syncSwitching2.value = false }
}

const dualMode = useF2StocktakeDualMode({
  wpId: toRef(props, 'wpId'),
  projectId,
  sheetCode: currentSheet,
  flushPending: async () => {
    // 字段编辑 2s debounce；切 OO 前必须立即落库，否则 plan-sync 读到旧数据
    await flushAllF2StocktakeFields()
  },
  reloadAll: () => formData.loadAll(),
})

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

provide('f2VersionTrailRef', versionTrailRef)
provide('f2OpenVersionHistory', openVersionHistory)

provide('reloadWorkpaperData', () => formData.loadAll())

const dataTabs = [
  { id: 'F2-21', label: '盘点问卷' },
  { id: 'F2-22', label: '监盘计划' },
  { id: 'F2-23', label: '监盘小结' },
  { id: 'F2-24', label: '账面核对' },
  { id: 'F2-25', label: '抽盘汇总' },
  { id: 'F2-26', label: '倒轧表' },
]

const singleSheetMode = computed(() => /^F2-2[1-6]$/.test(currentSheet.value))

const activeTab = ref(singleSheetMode.value ? currentSheet.value : 'program')

/** 父级 sheet 页签切换时（F2-21↔F2-22↔F2-23…）组件会复用，必须同步 activeTab */
watch(currentSheet, (code) => {
  if (/^F2-2[1-6]$/.test(code)) {
    activeTab.value = code
  } else if (code === 'F2-21A') {
    activeTab.value = 'program'
  }
})

function tabComponent(id: string): Component {
  const map: Record<string, Component> = {
    'F2-21': F2TabStocktakeQuestionnaire,
    'F2-22': F2TabStocktakePlan,
    'F2-23': F2TabStocktakeSummary,
    'F2-24': F2TabStocktakeReconcile,
    'F2-25': F2TabStocktakeSampleResult,
    'F2-26': F2TabStocktakeRollforward,
  }
  return map[id] || F2TabStocktakeQuestionnaire
}

async function handleSave(e: Event): Promise<void> {
  const detail = (e as CustomEvent<{ items: ChecklistResponse[]; done?: () => void }>).detail
  const items = detail?.items
  try {
    if (Array.isArray(items) && items.length) {
      await formData.saveItemsFromEvent(items)
      scheduleAutoSnapshot()
    }
  } finally {
    detail?.done?.()
  }
}

onMounted(() => {
  window.addEventListener('f2-stocktake:save-items', handleSave)
  void formData.loadAll().finally(() => { isLoading.value = false })
})

onBeforeUnmount(() => {
  window.removeEventListener('f2-stocktake:save-items', handleSave)
})
</script>

<style scoped>
.f2-stocktake-bundle { padding: 12px; height: 100%; display: flex; flex-direction: column; }
.oo-container { min-height: 600px; height: calc(100vh - 200px); }
.loading { padding: 24px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.stocktake-tabs { flex: 1; }
.stocktake-tabs :deep(.el-tabs__content) { overflow: auto; }
</style>
