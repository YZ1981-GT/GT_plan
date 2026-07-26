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
        <el-segmented
          v-if="isHtmlSheet"
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
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
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { useG4SppiDualMode } from '@/composables/useG4SppiDualMode'
import { useG4SppiFormData } from '@/composables/useG4SppiFormData'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import type { ChecklistResponse } from '@/composables/useG4SppiFormData'
import type { AdjustmentEntry } from './composables/useG4MainAdjustment'
import { persistExceptionDraftsToMainWp } from './composables/g4ExceptionRouting'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

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
</style>
