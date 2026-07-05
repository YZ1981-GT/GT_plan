<template>
  <div class="d4-operating-revenue">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <div v-if="showModeToolbar" class="d4-mode-toolbar">
        <el-segmented v-model="renderMode" :options="renderModeOptions" size="small" />
        <el-tag v-if="!dualMode.ooAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="renderMode === 'onlyoffice'"
        :key="ooSheetName"
        :wp-id="props.wpId"
        :sheet-name="ooSheetName"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @fallback="onOoFallback"
      />

      <template v-else>
      <!-- D4 主sheet (fallback) -->
      <D4TabIndex
        v-if="currentSheet === 'D4' || currentSheet === 'skip'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
        :ipo-group-visible="crossSheet.ipoGroupVisible.value"
        :has-export-business="crossSheet.hasExportBusiness.value"
        :available-sheets="availableSheets"
      />
      <!-- 程序表 D4A -->
      <D4TabProcedure
        v-else-if="currentSheet === 'D4A' || currentSheet === '应收口径'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :html-data="props.htmlData"
        :is-readonly="isReadonly"
      />
      <!-- D4-1 审定表 -->
      <D4TabAdjudication v-else-if="currentSheet === 'D4-1'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <!-- D4-2 主营明细 -->
      <D4TabRevenueDetail v-else-if="currentSheet === 'D4-2'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <!-- D4-3 其他明细 -->
      <D4TabOtherRevenue v-else-if="currentSheet === 'D4-3'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <!-- D4-4 调整分录 -->
      <D4TabAdjustment v-else-if="currentSheet === 'D4-4'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <!-- D4-5 政策检查 -->
      <D4TabPolicyCheck v-else-if="currentSheet === 'D4-5'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <!-- D4-6 ~ D4-11 分析程序 -->
      <D4TabIndicator v-else-if="currentSheet === 'D4-6'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabMarginMonthly v-else-if="currentSheet === 'D4-7'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabProductMargin v-else-if="currentSheet === 'D4-8'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabCustomerStructure v-else-if="currentSheet === 'D4-9'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabCustomerPrice v-else-if="currentSheet === 'D4-10'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabProductPrice v-else-if="currentSheet === 'D4-11'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <!-- D4-12 ~ D4-20 检查程序 -->
      <D4TabContract v-else-if="currentSheet === 'D4-12'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabErpCheck v-else-if="currentSheet === 'D4-13'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabOccurrence v-else-if="currentSheet === 'D4-14'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabCompleteness v-else-if="currentSheet === 'D4-15'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabExport v-else-if="currentSheet === 'D4-16'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabCutoffForward v-else-if="currentSheet === 'D4-17'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabCutoffBackward v-else-if="currentSheet === 'D4-18'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabDiscount v-else-if="currentSheet === 'D4-19'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabReturn v-else-if="currentSheet === 'D4-20'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <!-- D4-21 关联方 -->
      <D4TabRelatedPrice v-else-if="currentSheet === 'D4-21'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <!-- D4-22 ~ D4-32 IPO/舞弊 -->
      <D4TabIpoProcedure
        v-else-if="currentSheet === 'D4-22A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <D4TabIpoIndicator v-else-if="currentSheet === 'D4-22'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabInvoiceCompare v-else-if="currentSheet === 'D4-23'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabThirdParty v-else-if="currentSheet === 'D4-24'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabDealer v-else-if="currentSheet === 'D4-25'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabOverseas v-else-if="currentSheet === 'D4-26'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabUndisclosedRp v-else-if="currentSheet === 'D4-27'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabCustomerChecklist v-else-if="currentSheet === 'D4-28'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabCustomerDetail v-else-if="currentSheet === 'D4-29'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabInterviewSummary v-else-if="currentSheet === 'D4-30'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabInterviewDetail v-else-if="currentSheet === 'D4-31'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabInterviewTemplate v-else-if="currentSheet === 'D4-31T'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabFundFlow v-else-if="currentSheet === 'D4-32'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <!-- D4-33 ~ D4-36 其他收入 -->
      <D4TabOtherMargin v-else-if="currentSheet === 'D4-33'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabOtherContract v-else-if="currentSheet === 'D4-34'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabOtherCheck v-else-if="currentSheet === 'D4-35'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabOtherCutoff v-else-if="currentSheet === 'D4-36'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <!-- 附注（上市/国企） -->
      <D4TabDisclosureListed v-else-if="currentSheet === '附注上市'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <D4TabDisclosureSoe v-else-if="currentSheet === '附注国企'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :is-readonly="isReadonly" />
      <!-- Fallback: 未匹配的 sheetName 默认显示目录 -->
      <D4TabIndex
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
        :ipo-group-visible="crossSheet.ipoGroupVisible.value"
        :has-export-business="crossSheet.hasExportBusiness.value"
        :available-sheets="availableSheets"
      />
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtD4OperatingRevenue.vue — D4 营业收入底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，按 v-if 分发到对应子组件。
 * 不再使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：6001 主营业务收入 + 6051 其他业务收入（损益类/贷方科目）
 * IPO/舞弊组可见性由 business_category 字段控制。
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 */
import { ref, computed, onMounted, provide, toRef, defineAsyncComponent } from 'vue'
import { useD4FormData } from './composables/useD4FormData'
import { useD4CrossSheet } from './composables/useD4CrossSheet'
import { useWorkpaperReviewProvide } from './composables/useWorkpaperReviewProvide'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { useD4ReviewThreads } from './composables/useD4ReviewThreads'
import { useD4EntryDualMode, type D4RenderMode } from './composables/useD4EntryDualMode'
import { isSkipWorkpaperSheet } from './composables/workpaperSkipSheets'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
import D4TabIndex from './d4/core/D4TabIndex.vue'
import D4TabProcedure from './d4/core/D4TabProcedure.vue'
const D4TabAdjudication = defineAsyncComponent(() => import('./d4/core/D4TabAdjudication.vue'))
const D4TabRevenueDetail = defineAsyncComponent(() => import('./d4/core/D4TabRevenueDetail.vue'))
const D4TabOtherRevenue = defineAsyncComponent(() => import('./d4/core/D4TabOtherRevenue.vue'))
const D4TabAdjustment = defineAsyncComponent(() => import('./d4/core/D4TabAdjustment.vue'))
const D4TabDisclosureListed = defineAsyncComponent(() => import('./d4/core/D4TabDisclosureListed.vue'))
const D4TabDisclosureSoe = defineAsyncComponent(() => import('./d4/core/D4TabDisclosureSoe.vue'))

// Policy
const D4TabPolicyCheck = defineAsyncComponent(() => import('./d4/policy/D4TabPolicyCheck.vue'))

// Analysis
const D4TabIndicator = defineAsyncComponent(() => import('./d4/analysis/D4TabIndicator.vue'))
const D4TabMarginMonthly = defineAsyncComponent(() => import('./d4/analysis/D4TabMarginMonthly.vue'))
const D4TabProductMargin = defineAsyncComponent(() => import('./d4/analysis/D4TabProductMargin.vue'))
const D4TabCustomerStructure = defineAsyncComponent(() => import('./d4/analysis/D4TabCustomerStructure.vue'))
const D4TabCustomerPrice = defineAsyncComponent(() => import('./d4/analysis/D4TabCustomerPrice.vue'))
const D4TabProductPrice = defineAsyncComponent(() => import('./d4/analysis/D4TabProductPrice.vue'))

// Inspection
const D4TabContract = defineAsyncComponent(() => import('./d4/inspection/D4TabContract.vue'))
const D4TabErpCheck = defineAsyncComponent(() => import('./d4/inspection/D4TabErpCheck.vue'))
const D4TabOccurrence = defineAsyncComponent(() => import('./d4/inspection/D4TabOccurrence.vue'))
const D4TabCompleteness = defineAsyncComponent(() => import('./d4/inspection/D4TabCompleteness.vue'))
const D4TabExport = defineAsyncComponent(() => import('./d4/inspection/D4TabExport.vue'))
const D4TabCutoffForward = defineAsyncComponent(() => import('./d4/inspection/D4TabCutoffForward.vue'))
const D4TabCutoffBackward = defineAsyncComponent(() => import('./d4/inspection/D4TabCutoffBackward.vue'))
const D4TabDiscount = defineAsyncComponent(() => import('./d4/inspection/D4TabDiscount.vue'))
const D4TabReturn = defineAsyncComponent(() => import('./d4/inspection/D4TabReturn.vue'))

// Related
const D4TabRelatedPrice = defineAsyncComponent(() => import('./d4/related/D4TabRelatedPrice.vue'))

// IPO
const D4TabIpoProcedure = defineAsyncComponent(() => import('./d4/ipo/D4TabIpoProcedure.vue'))
const D4TabIpoIndicator = defineAsyncComponent(() => import('./d4/ipo/D4TabIpoIndicator.vue'))
const D4TabInvoiceCompare = defineAsyncComponent(() => import('./d4/ipo/D4TabInvoiceCompare.vue'))
const D4TabThirdParty = defineAsyncComponent(() => import('./d4/ipo/D4TabThirdParty.vue'))
const D4TabDealer = defineAsyncComponent(() => import('./d4/ipo/D4TabDealer.vue'))
const D4TabOverseas = defineAsyncComponent(() => import('./d4/ipo/D4TabOverseas.vue'))
const D4TabUndisclosedRp = defineAsyncComponent(() => import('./d4/ipo/D4TabUndisclosedRp.vue'))
const D4TabCustomerChecklist = defineAsyncComponent(() => import('./d4/ipo/D4TabCustomerChecklist.vue'))
const D4TabCustomerDetail = defineAsyncComponent(() => import('./d4/ipo/D4TabCustomerDetail.vue'))
const D4TabInterviewSummary = defineAsyncComponent(() => import('./d4/ipo/D4TabInterviewSummary.vue'))
const D4TabInterviewDetail = defineAsyncComponent(() => import('./d4/ipo/D4TabInterviewDetail.vue'))
const D4TabInterviewTemplate = defineAsyncComponent(() => import('./d4/ipo/D4TabInterviewTemplate.vue'))
const D4TabFundFlow = defineAsyncComponent(() => import('./d4/ipo/D4TabFundFlow.vue'))

// Other
const D4TabOtherMargin = defineAsyncComponent(() => import('./d4/other/D4TabOtherMargin.vue'))
const D4TabOtherContract = defineAsyncComponent(() => import('./d4/other/D4TabOtherContract.vue'))
const D4TabOtherCheck = defineAsyncComponent(() => import('./d4/other/D4TabOtherCheck.vue'))
const D4TabOtherCutoff = defineAsyncComponent(() => import('./d4/other/D4TabOtherCutoff.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
  (e: 'jump-to-section', sheetName: string): void
}>()

// ─── Composables ─────────────────────────────────────────────────────────────

const isReadonly = computed(() => !!props.readonly)

const formData = useD4FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const allResponses = computed(() => formData.allResponses.value)

const crossSheet = useD4CrossSheet({
  allResponses: formData.allResponses,
  projectContext: formData.projectContext,
})

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(true)

/**
 * 当前激活的 sheet（由外层 GtWpRenderer 通过 sheetName prop 控制）。
 * GtWpRenderer 传入的是完整 sheet_name（如"营业收入审定表D4-1"），
 * 需要提取末尾的编码部分（D4-1）来匹配子组件。
 */
const currentSheet = computed(() => {
  const name = props.sheetName || 'D4'
  if (isSkipWorkpaperSheet(name)) return 'skip'
  if (name.includes('访谈记录与核对')) return 'D4-31T'
  // 提取末尾的D4编码（D4/D4A/D4-1/D4-22A等格式）
  const match = name.match(/D4(?:-\d+)?[A-Z]?$|D4$|D0-5$/)
  if (match) return match[0]
  // 附注特殊匹配
  if (name.includes('上市')) return '附注上市'
  if (name.includes('国企') || name.includes('国有')) return '附注国企'
  return name
})

const availableSheets = computed(() =>
  props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets ?? [],
)

const wpIdRefForReview = toRef(props, 'wpId')
const projectIdRefForReview = toRef(props, 'projectId')
useWorkpaperReviewProvide({ wpId: wpIdRefForReview, projectId: projectIdRefForReview })

const { getThreadDot, getRowDot } = useD4ReviewThreads(wpIdRefForReview)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: () => formData.loadAll(),
})

const KNOWN_HTML_SHEETS = new Set([
  'D4', 'D4A', 'D4-1', 'D4-2', 'D4-3', 'D4-4', 'D4-5', 'D4-6', 'D4-7', 'D4-8', 'D4-9', 'D4-10', 'D4-11',
  'D4-12', 'D4-13', 'D4-14', 'D4-15', 'D4-16', 'D4-17', 'D4-18', 'D4-19', 'D4-20', 'D4-21',
  'D4-22A', 'D4-22', 'D4-23', 'D4-24', 'D4-25', 'D4-26', 'D4-27', 'D4-28', 'D4-29', 'D4-30', 'D4-31', 'D4-31T', 'D4-32',
  'D4-33', 'D4-34', 'D4-35', 'D4-36', '附注上市', '附注国企',
])

const showModeToolbar = computed(() =>
  currentSheet.value !== 'skip' && KNOWN_HTML_SHEETS.has(currentSheet.value),
)

const dualMode = useD4EntryDualMode({
  wpId: toRef(props, 'wpId'),
  currentSheet,
  availableSheets,
  reloadAllResponses: () => formData.loadAll(),
})

const ooSheetName = computed(() =>
  dualMode.resolveOoSheetName() || props.sheetName || 'D4-1',
)

const renderMode = computed({
  get: () => dualMode.mode.value,
  set: (v: D4RenderMode) => { void dualMode.switchMode(v) },
})

const renderModeOptions = computed(() => [
  { label: '结构化视图', value: 'html' as const },
  {
    label: '在线编辑',
    value: 'onlyoffice' as const,
    disabled: !dualMode.ooAvailable.value,
  },
])

function onOoFallback(): void {
  void dualMode.switchMode('html')
}

async function saveImmediateBatch(
  items: Array<{ item_id: string; conclusion: string | null; remark: string | null }>,
): Promise<void> {
  await formData.saveBatch(items.map(item => ({
    itemId: item.item_id,
    data: { conclusion: item.conclusion, remark: item.remark },
  })))
}



// ─── selfLoad ────────────────────────────────────────────────────────────────

async function selfLoad() {
  if (props.htmlData) {
    // 从 props 提供的数据初始化
    if (props.htmlData.projectContext) {
      formData.projectContext.value = props.htmlData.projectContext
    }
    isLoading.value = false
    return
  }

  // 当 htmlData 为空时（bundle 内嵌场景），自行加载
  try {
    await formData.loadAll()
  } catch (err) {
    console.warn('[GtD4OperatingRevenue] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.d4-operating-revenue {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.d4-mode-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
</style>
