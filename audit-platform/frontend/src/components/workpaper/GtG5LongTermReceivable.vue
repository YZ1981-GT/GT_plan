<template>
  <div class="g5-long-term-receivable">
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
      <div class="g5-long-term-receivable-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          :model-value="renderMode"
          :options="dualMode.modeOptions"
          size="small"
          @change="(v: any) => dualMode.switchMode(v)"
        />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-button size="small" type="primary" plain @click="openHandbook('preparation')">
          📖 编制手册
        </el-button>
        <el-tag v-if="isHtmlSheet && !isOoAvailable" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && renderMode === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <G5TabProcedure
        v-else-if="currentSheet === 'G5A'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
      />
      <G5TabAdjudication
        v-else-if="currentSheet === 'G5-1'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @imported="onSheetImported"
      />
      <G5TabBalanceDetail
        v-else-if="currentSheet === 'G5-2'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
        :roll-forward-loading="priorYear.loading.value || priorYear.applying.value"
        @imported="onSheetImported"
        @roll-forward="handlePriorYearRollForward"
      />
      <G5TabBadDebtDetail
        v-else-if="currentSheet === 'G5-3'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @imported="onSheetImported"
      />
      <G5TabAdjustment
        v-else-if="currentSheet === 'G5-4'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @imported="onSheetImported"
      />
      <G5TabLeaseAmortization
        v-else-if="currentSheet === 'G5-5'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @imported="onSheetImported"
      />
      <G5TabInstallmentSales
        v-else-if="currentSheet === 'G5-6'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @imported="onSheetImported"
      />
      <G5TabFactoringCheck
        v-else-if="currentSheet === 'G5-7'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @imported="onSheetImported"
      />
      <G5TabEclPolicy
        v-else-if="currentSheet === 'G5-8'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
      />
      <G5TabStageClassification
        v-else-if="currentSheet === 'G5-9'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <G5TabImpairmentCalc
        v-else-if="currentSheet === 'G5-10'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <G5TabReversalWriteoff
        v-else-if="currentSheet === 'G5-11'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @imported="onSheetImported"
      />
      <G5TabVoucherCheck
        v-else-if="currentSheet === 'G5-12'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @imported="onSheetImported"
      />
      <G5TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
      />
      <G5TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
      />
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
        <G5SheetStatusBar :all-responses="formData.allResponses.value" />
      </template>
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <G5PreparationHandbookDialog
        v-model="handbookVisible"
        :initial-tab="handbookTab"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG5LongTermReceivable.vue — G5 长期应收款底稿主入口
 * 对齐 G2/G3/G4：formData + g5:save-items + 附注路由 + 双模式 reload
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useG5DualMode } from './composables/useG5DualMode'
import { useG5LonRecFormData, G5FormDataKey } from './composables/useG5LonRecFormData'
import { buildDirectoryHtmlData } from './composables/gCycleIndexRouting'
import { useG5PriorYearRollForward } from './composables/useG5PriorYearRollForward'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import type { ChecklistResponse } from './composables/useF1FormData'
import { extractG5SheetCode, resolveG5SheetLabel } from './composables/g5SheetLabels'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const G5TabProcedure = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabProcedure.vue'))
const G5TabAdjudication = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabAdjudication.vue'))
const G5TabBalanceDetail = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabBalanceDetail.vue'))
const G5TabBadDebtDetail = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabBadDebtDetail.vue'))
const G5TabAdjustment = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabAdjustment.vue'))
const G5TabDisclosureListed = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabDisclosureListed.vue'))
const G5TabDisclosureSOE = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabDisclosureSOE.vue'))
const G5TabLeaseAmortization = defineAsyncComponent(() => import('./g5-long-term-receivable/measurement/G5TabLeaseAmortization.vue'))
const G5TabInstallmentSales = defineAsyncComponent(() => import('./g5-long-term-receivable/measurement/G5TabInstallmentSales.vue'))
const G5TabFactoringCheck = defineAsyncComponent(() => import('./g5-long-term-receivable/measurement/G5TabFactoringCheck.vue'))
const G5TabEclPolicy = defineAsyncComponent(() => import('./g5-long-term-receivable/measurement/G5TabEclPolicy.vue'))
const G5TabStageClassification = defineAsyncComponent(() => import('./g5-long-term-receivable/impairment/G5TabStageClassification.vue'))
const G5TabImpairmentCalc = defineAsyncComponent(() => import('./g5-long-term-receivable/impairment/G5TabImpairmentCalc.vue'))
const G5TabReversalWriteoff = defineAsyncComponent(() => import('./g5-long-term-receivable/impairment/G5TabReversalWriteoff.vue'))
const G5TabVoucherCheck = defineAsyncComponent(() => import('./g5-long-term-receivable/voucher/G5TabVoucherCheck.vue'))
const G5PreparationHandbookDialog = defineAsyncComponent(
  () => import('./g5-long-term-receivable/G5PreparationHandbookDialog.vue'),
)
const GCycleBIndexExtras = defineAsyncComponent(() => import('./shared/GCycleBIndexExtras.vue'))
const G5SheetStatusBar = defineAsyncComponent(
  () => import('./g5-long-term-receivable/G5SheetStatusBar.vue'),
)

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const isLoading = ref(true)
const loadError = ref<string | null>(null)
const selfLoadData = ref<Record<string, any> | null>(null)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const isReadonly = computed(() => !!props.readonly)

const formData = useG5LonRecFormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
  onAfterSave: () => scheduleAutoSnapshot(),
})
provide(G5FormDataKey, formData)

const priorYear = useG5PriorYearRollForward({
  projectId: projectIdRef,
  wpId: wpIdRef,
  allResponses: formData.allResponses,
  saveImmediate: formData.saveImmediate,
  saveBatch: formData.saveBatch,
})

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
      await formData.loadAll()
    }
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error?.response?.data?.detail || error?.message || '上年结转失败')
  }
}

const currentSheet = computed(() => extractG5SheetCode(props.sheetName || props.wpCode || ''))

const HTML_SHEETS = new Set([
  'G5A', 'G5-1', 'G5-2', 'G5-3', 'G5-4', 'G5-5', 'G5-6', 'G5-7',
  'G5-8', 'G5-9', 'G5-10', 'G5-11', 'G5-12',
  '附注上市', '附注国企', '底稿目录',
])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

const dualMode = useG5DualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

/** 对齐 G1：computed getter/setter 安全包装 dualMode ref 避免模板嵌套 .value */
const renderMode = computed({
  get: () => dualMode.currentMode.value,
  set: (v: string) => { void dualMode.switchMode(v as any) },
})
const isOoAvailable = computed(() => dualMode.isOoAvailable.value)

const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

provide('g5VersionTrailRef', versionTrailRef)
provide('g5OpenVersionHistory', openVersionHistory)
provide('reloadWorkpaperData', () => formData.loadAll())

const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage' = 'preparation'): void {
  handbookTab.value = tab
  handbookVisible.value = true
}
provide('openG5Handbook', openHandbook)

const availableSheets = computed(() => {
  const fromHtml = props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml
  // 对齐 G1：htmlData 无 sheets 时用自加载 render-config 的 sheetCache 兜底，
  // 保证底稿目录架构树非空
  return Object.keys(formData.sheetCache.value).map(sheet_name => ({ sheet_name }))
})

/** 目录页传给 GCycleBIndexExtras 的 htmlData：从 sheetCache 补全 cycle_workpapers（本循环底稿目录 grid） */
const directoryHtmlData = computed(() =>
  buildDirectoryHtmlData(props.htmlData, formData.sheetCache.value),
)

function onDirectoryJump(code: string): void {
  emit('navigate-sheet', code)
}

function onSheetImported(): void {
  void formData.loadAll()
}

async function handleG5SaveItems(e: Event): Promise<void> {
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
  if (d?.accountCode === '1531') {
    void formData.saveImmediate('G5-1-adjudicated-amount', {
      item_id: 'G5-1-adjudicated-amount',
      conclusion: String(d.adjudicatedAmount),
      remark: null,
    })
  }
}

function handleG5Writeback(e: Event): void {
  const d = (e as CustomEvent<{ accountCode?: string; auditedAmount?: number }>).detail
  if (!d || d.accountCode !== '1531') return
  if (typeof d.auditedAmount !== 'number' || !Number.isFinite(d.auditedAmount)) return
  void formData.writebackTrialBalance(d.auditedAmount)
}

async function selfLoad(): Promise<void> {
  try {
    await formData.loadAll()
    if (props.htmlData != null) return
    // 复用 loadAll 已拉取的 render-config，避免二次请求
    const cache = formData.sheetCache.value
    const keys = Object.keys(cache)
    if (keys.length === 0) return
    const wanted = resolveG5SheetLabel(currentSheet.value || 'G5A', keys.map((k) => ({ sheet_name: k })))
    selfLoadData.value = cache[wanted] ?? cache[keys[0]]
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
  window.addEventListener('g5:save-items', handleG5SaveItems)
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
  window.addEventListener('g5:writeback-trial-balance', handleG5Writeback)
  await selfLoad()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g5:save-items', handleG5SaveItems)
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
  window.removeEventListener('g5:writeback-trial-balance', handleG5Writeback)
  formData.flushPending()
})
</script>

<style scoped>
.g5-long-term-receivable { padding: 12px; }
.loading-container { padding: 24px; }
.error-container { padding: 24px; }
.g5-long-term-receivable-toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; }
.g5-index-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
</style>
