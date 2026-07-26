<template>
  <div class="g4-bond-investment-main">
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
      <div class="g4-bond-investment-main-toolbar">
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

      <G4TabProcedure
        v-else-if="currentSheet === 'procedure'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G4TabAdjudication
        v-else-if="currentSheet === 'adjudication'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="formData.allResponses.value"
      />

      <G4TabDetail
        v-else-if="currentSheet === 'detail'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="formData.allResponses.value"
        :roll-forward-loading="priorYear.loading.value || priorYear.applying.value"
        @imported="onSheetImported"
        @roll-forward="handlePriorYearRollForward"
      />

      <G4TabAdjustment
        v-else-if="currentSheet === 'adjustment'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="formData.allResponses.value"
        @imported="onSheetImported"
      />

      <G4TabInterestCalc
        v-else-if="currentSheet === 'interestCalc'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="formData.allResponses.value"
        @imported="onSheetImported"
      />

      <G4TabDisclosureListed
        v-else-if="currentSheet === 'disclosureListed'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <G4TabDisclosureSOE
        v-else-if="currentSheet === 'disclosureSOE'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <div v-else-if="currentSheet === 'directory'" class="g-cycle-tab-index-page">
        <div class="g4-index-toolbar">
          <el-button size="small" type="primary" plain @click="openVersionHistory()">
            版本历史
          </el-button>
        </div>
        <G4TabDirectory
          :all-responses="suiteResponses || new Map()"
          :available-sheets="availableSheets"
        />
        <GCycleBIndexExtras
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName"
          :wp-code="'G4'"
          :html-data="directoryHtmlData"
          :available-sheets="availableSheets"
          :all-responses="suiteResponses || new Map()"
        />
      </div>

      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />
      <G4PreparationHandbookDialog
        v-model="handbookVisible"
        :initial-tab="handbookTab"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG4BondInvestmentMain.vue — G4 债权投资底稿(main组)主入口
 * 对齐 G2/G3：formData + g4:save-items 持久化 + 附注路由 + 双模式 reload
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent, watch } from 'vue'
import { useG4MainDualMode } from './composables/useG4MainDualMode'
import { useG4BonInvFormData } from './composables/useG4BonInvFormData'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import type { ChecklistResponse } from './composables/useF1FormData'
import { useG4MainAdjustment, type AdjustmentEntry } from './composables/useG4MainAdjustment'
import { useG4PriorYearRollForward } from './composables/useG4PriorYearRollForward'
import { fetchG4SuiteResponseMap } from './composables/g4CrossHelpers'
import { buildDirectoryHtmlData } from './composables/gCycleIndexRouting'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const G4TabProcedure = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabProcedure.vue'))
const G4TabAdjudication = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabAdjudication.vue'))
const G4TabDetail = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabDetail.vue'))
const G4TabAdjustment = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabAdjustment.vue'))
const G4TabDisclosureListed = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabDisclosureListed.vue'))
const G4TabDisclosureSOE = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabDisclosureSOE.vue'))
const G4TabInterestCalc = defineAsyncComponent(() => import('./g4-bond-investment-main/measurement/G4TabInterestCalc.vue'))
const GCycleBIndexExtras = defineAsyncComponent(() => import('./shared/GCycleBIndexExtras.vue'))
const G4TabDirectory = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabDirectory.vue'))
const G4PreparationHandbookDialog = defineAsyncComponent(
  () => import('./g4-bond-investment-main/G4PreparationHandbookDialog.vue'),
)

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const SHEET_CODE_MAP: Record<string, string> = {
  'G4A': 'procedure',
  'G4-1': 'adjudication',
  'G4-2': 'detail',
  'G4-3': 'adjustment',
  'G4-4': 'interestCalc',
  '附注披露信息（上市公司）': 'disclosureListed',
  '附注披露信息（国企）': 'disclosureSOE',
  '底稿目录': 'directory',
}

const isLoading = ref(true)
const loadError = ref<string | null>(null)
const selfLoadData = ref<Record<string, any> | null>(null)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const isReadonly = computed(() => !!props.readonly)

const formData = useG4BonInvFormData({ wpId: wpIdRef, projectId: projectIdRef })
const adjustmentRouting = useG4MainAdjustment({
  allResponses: formData.allResponses,
  isReadonly,
})
const priorYear = useG4PriorYearRollForward({
  wpId: wpIdRef,
  projectId: projectIdRef,
  allResponses: formData.allResponses,
  saveImmediate: formData.saveImmediate,
  saveBatch: formData.saveBatch,
})
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
const suiteResponses = ref<Map<string, ChecklistResponse>>(new Map())

async function refreshSuiteResponses(): Promise<void> {
  try {
    const merged = await fetchG4SuiteResponseMap(props.projectId, props.wpId)
    // 当前 Main 内存态优先覆盖，避免刚保存未落库时状态滞后
    for (const [key, value] of formData.allResponses.value) {
      merged.set(key, value)
    }
    suiteResponses.value = merged
  } catch {
    suiteResponses.value = new Map(formData.allResponses.value)
  }
}

function openHandbook(tab: 'preparation' | 'usage'): void {
  handbookTab.value = tab
  handbookVisible.value = true
}

async function handlePriorYearRollForward(): Promise<void> {
  try {
    let plan = await priorYear.loadPreview(false)
    if (plan.changes.length === 0) {
      try {
        await ElMessageBox.confirm(
          '没有可结转数据，或本期期初已填写。是否强制覆盖已填期初字段？',
          '上年结转',
          { type: 'warning', confirmButtonText: '强制覆盖', cancelButtonText: '取消' },
        )
      } catch {
        return
      }
      plan = await priorYear.loadPreview(true)
      if (plan.changes.length === 0) {
        ElMessage.info('没有可结转数据')
        return
      }
    }
    if (await priorYear.applyPreview(plan)) {
      ElMessage.success('上年数据结转完成')
    }
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error?.response?.data?.detail || error?.message || '上年结转失败')
  }
}

const currentSheet = computed(() => {
  const name = props.sheetName || ''
  if (SHEET_CODE_MAP[name]) return SHEET_CODE_MAP[name]
  if (/G4-note-listed|附注披露.*上市|附注.*上市/.test(name)) return 'disclosureListed'
  if (/G4-note-soe|附注披露.*国企|附注.*国企/.test(name)) return 'disclosureSOE'
  if (/G4-directory|底稿目录/.test(name)) return 'directory'
  if (/附注/.test(name)) return name.includes('国企') ? 'disclosureSOE' : 'disclosureListed'
  const codeMatch = name.match(/(G4A|G4-[1-4])/)
  if (codeMatch) return SHEET_CODE_MAP[codeMatch[1]] || ''
  return ''
})

const HTML_SHEETS = new Set([
  'procedure', 'adjudication', 'detail', 'adjustment',
  'interestCalc', 'disclosureListed', 'disclosureSOE', 'directory',
])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

const dualMode = useG4MainDualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

const availableSheets = computed(() => {
  const hd = resolvedHtmlData.value
  const fromHtml = hd?.sheets ?? hd?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) {
    // 统一为下划线格式（buildCycleArchitectureHtmlData 期望 sheet_name/component_type）
    return fromHtml.map((s: any) => ({
      sheet_name: s.sheet_name || s.sheetName || s.name || '',
      component_type: s.component_type || s.componentType || 'audit-sheet',
    }))
  }
  // 从 formData sheetCache 取（loadAll 后填充），并从 fallback 表匹配 component_type
  const cacheKeys = Object.keys(formData.sheetCache.value)
  if (cacheKeys.length > 0) {
    return cacheKeys.map(sheet_name => {
      const match = G4_FALLBACK_SHEETS.find(f => sheet_name.includes(f.sheet_name) || f.sheet_name.includes(sheet_name))
      return { sheet_name, component_type: match?.component_type || 'audit-sheet' }
    })
  }
  // 硬编码 fallback 保证底稿架构树不为空
  return G4_FALLBACK_SHEETS
})

/** 目录页传给 GCycleBIndexExtras 的 htmlData：去除 navigation_rows 强制从 availableSheets 重建，并补全 cycle_workpapers */
const directoryHtmlData = computed(() =>
  buildDirectoryHtmlData(resolvedHtmlData.value || props.htmlData, formData.sheetCache.value),
)

/** G4 底稿 sheet 列表（含 component_type 供 GtBArchitectureTree 分组） */
const G4_FALLBACK_SHEETS: Array<{ sheet_name: string; component_type?: string }> = [
  { sheet_name: '债权投资实质性程序表G4A', component_type: 'a-program-console' },
  { sheet_name: '审定表G4-1', component_type: 'audit-sheet' },
  { sheet_name: '明细表G4-2', component_type: 'audit-sheet' },
  { sheet_name: '调整分录汇总G4-3', component_type: 'audit-sheet' },
  { sheet_name: '利息测算表G4-4', component_type: 'audit-sheet' },
  { sheet_name: '业务模式分析G4-5', component_type: 'audit-sheet' },
  { sheet_name: '合同现金流量特征分析G4-6', component_type: 'audit-sheet' },
  { sheet_name: '有价证券盘点表G4-7', component_type: 'audit-sheet' },
  { sheet_name: '盘点倒轧表G4-8', component_type: 'audit-sheet' },
  { sheet_name: '三阶段划分G4-9', component_type: 'audit-sheet' },
  { sheet_name: '减值准备测算表G4-10', component_type: 'audit-sheet' },
  { sheet_name: '预期信用损失计量G4-11', component_type: 'audit-sheet' },
  { sheet_name: '转回核销检查G4-12', component_type: 'audit-sheet' },
  { sheet_name: '凭证检查表G4-13', component_type: 'audit-sheet' },
  { sheet_name: '附注披露信息（上市公司）', component_type: 'c-note-table' },
  { sheet_name: '附注披露信息（国企）', component_type: 'c-note-table' },
  { sheet_name: '底稿目录', component_type: 'b-index' },
]

const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

provide('g4VersionTrailRef', versionTrailRef)
provide('g4OpenVersionHistory', openVersionHistory)
provide('reloadWorkpaperData', () => formData.loadAll())

const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

/** 目录页跳转：G4TabDirectory inject('jumpToSection') → navigate-sheet → GtWpRenderer */
const emit = defineEmits<{ 'navigate-sheet': [sheetName: string] }>()
provide('jumpToSection', (sheetName: string) => emit('navigate-sheet', sheetName))

async function onSheetImported(): Promise<void> {
  await formData.loadAll()
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

function handleAdjudicated(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
  if (d?.accountCode === '1501') {
    void formData.saveImmediate('G4-1-adjudicated-amount', {
      item_id: 'G4-1-adjudicated-amount',
      conclusion: String(d.adjudicatedAmount),
      remark: null,
    })
  }
}

function handleExceptionDrafts(e: Event): void {
  const drafts = (e as CustomEvent<{ drafts: AdjustmentEntry[] }>).detail?.drafts
  if (Array.isArray(drafts) && drafts.length > 0) {
    adjustmentRouting.upsertDraftsFromSource(drafts)
  }
}

async function selfLoad(): Promise<void> {
  try {
    await formData.loadAll()
    if (props.htmlData != null) return
    const { data } = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { force_component_type: 'g4-bond-investment-main' },
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
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
  await selfLoad()
  isLoading.value = false
  if (currentSheet.value === 'directory') {
    void refreshSuiteResponses()
  }
})

watch(
  () => currentSheet.value,
  (sheet) => {
    if (sheet === 'directory') void refreshSuiteResponses()
  },
)

onBeforeUnmount(() => {
  window.removeEventListener('g4:save-items', handleG4SaveItems)
  window.removeEventListener('g4:exception-drafts', handleExceptionDrafts)
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
})
</script>

<style scoped>
.g4-bond-investment-main { padding: 12px; }
.loading-container { padding: 24px; }
.error-container { padding: 24px; }
.g4-bond-investment-main-toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; }
.g4-index-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
</style>
